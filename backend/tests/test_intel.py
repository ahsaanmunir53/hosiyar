"""Review queue, campaigns, watchlist, lookups, exports, alerts and retention."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
import stix2
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select

from app.agent.graph import build_graph
from app.agent.state import Deps
from app.core.redaction import phone_fingerprint
from app.db.models import AlertLog, Analysis, Campaign, Report, WatchlistEntry
from app.db.session import init_db, make_engine, make_sessionmaker
from app.intel import alerts, family, retention, rule_ideas
from app.intel.lookup import guess_kind, lookup
from app.intel.reports import reject_report
from app.intel.stix import build_bundle
from app.intel.takedown import takedown_info
from app.memory import store as memory
from app.memory.embeddings import HashingEmbeddings
from app.tools import links as link_tools
from tests.fakes import FakeLLM


@pytest.fixture
async def env(settings):
    engine = make_engine(settings)
    await init_db(engine)
    store = InMemoryStore(index={"dims": 768, "embed": HashingEmbeddings(768), "fields": ["text"]})
    await memory.seed_pattern_library(store, "local768")
    saver = InMemorySaver()
    deps = Deps(settings=settings, llm=None, store=store, embed_provider="local768",
                sessionmaker=make_sessionmaker(engine), http=None, checkpointer=saver)
    graph = build_graph(deps, saver)

    async def check(text, thread, **extra):
        return await graph.ainvoke({"mode": "analyze", "text": text, "channel": "test", "extra_signals": [], "file_info": None, **extra},
                                   {"configurable": {"thread_id": thread}})

    deps.graph = graph
    yield deps, check
    await engine.dispose()


SCAM_A = "HBL: your account is blocked. Verify at hbl-verify.top/login and share the OTP to unlock it."
SCAM_B = "Dear HBL customer, unusual sign-in. Confirm your account at hbl-verify.top/secure with your OTP now."


async def test_reports_sharing_a_domain_form_one_campaign(env):
    deps, check = env
    a = await check(SCAM_A, "a", share=True, user_hash="u1")
    b = await check(SCAM_B, "b", share=True, user_hash="u2")
    assert a["report_status"] == b["report_status"] == "approved"
    async with deps.sessionmaker() as session:
        reports = (await session.execute(select(Report))).scalars().all()
        campaigns = (await session.execute(select(Campaign))).scalars().all()
    assert len({r.campaign_id for r in reports}) == 1
    assert campaigns[0].report_count == 2
    assert "hbl-verify.top" in campaigns[0].label


async def test_rejecting_a_report_removes_it_from_memory_and_campaign(env):
    deps, check = env
    a = await check(SCAM_A, "a", share=True)
    await reject_report(deps, a["analysis_id"], reviewer="analyst@example.org", note="test")
    assert await deps.store.aget(("community", "local768"), a["analysis_id"]) is None
    async with deps.sessionmaker() as session:
        assert (await session.execute(select(Campaign))).scalars().all() == []


async def test_stix_bundle_is_valid(env):
    deps, check = env
    await check(SCAM_A, "a", share=True)
    await check(SCAM_B, "b", share=True)
    bundle = await build_bundle(deps.sessionmaker)
    parsed = stix2.parse(json.dumps(bundle), allow_custom=False)
    types = sorted({o.type for o in parsed.objects})
    assert types == ["campaign", "identity", "indicator", "relationship"]
    patterns = {o.pattern for o in parsed.objects if o.type == "indicator"}
    assert "[domain-name:value = 'hbl-verify.top']" in patterns
    # Phone and account fingerprints are never exported.
    assert "phone" not in json.dumps(bundle).lower()
    again = await build_bundle(deps.sessionmaker)
    assert {o["id"] for o in again["objects"]} == {o["id"] for o in bundle["objects"]}


async def test_watchlist_hit_is_decisive(env):
    deps, check = env
    fp = phone_fingerprint("03331234567", deps.settings.fingerprint_secret)
    async with deps.sessionmaker() as session:
        session.add(WatchlistEntry(kind="phone_fp", value=fp, label="0333-***-4567", added_by="a@x.org"))
        await session.commit()
    state = await check("Salam, kal 03331234567 par rabta karna", "w")
    hit = next(h for h in state["rule_hits"] if h["id"] == "watchlist_match")
    assert hit["hard"] is True
    assert state["verdict"] == "likely_scam"


@pytest.mark.parametrize(
    ("value", "kind"),
    [("0300-1234567", "phone"), ("+923001234567", "phone"), ("8171", "phone"), ("hbl-verify.top", "link"),
     ("https://bit.ly/abc", "link"), ("PK36SCBL0000001123456702", "account"), ("0123 0104567890", "account")],
)
def test_lookup_guesses_kind(value, kind):
    assert guess_kind(value) == kind


async def test_lookup_reports_and_never_stores_the_value(env):
    deps, check = env
    await check("Ammi ye mera naya number hai, foran 20000 easypaisa kar dein 03211234567, mushkil mein hoon", "a",
                share=True, user_hash="u1", channel="telegram")
    await check("Ammi naya number hai, 03211234567 par foran 15000 bhej dein, mushkil mein hoon", "b",
                share=True, user_hash="u2", channel="telegram")
    found = await lookup(deps, "0321 1234567")
    assert found["status"] == "reported" and found["confirmed_reports"] == 2
    assert "1234567" not in found["display"]
    unknown = await lookup(deps, "03009999999")
    assert unknown["status"] == "no_reports"
    site = await lookup(deps, "hbl.com")
    assert site["status"] == "official"
    fake = await lookup(deps, "jazzcash-reward.xyz")
    assert fake["status"] == "lookalike"
    shortcode = await lookup(deps, "8171")
    assert shortcode["shortcode_note"]["en"].startswith("BISP")


@respx.mock
async def test_takedown_finds_registrar_abuse_contact(settings):
    link_tools._RDAP_CACHE.clear()
    respx.get("https://rdap.org/domain/hbl-verify.top").mock(return_value=httpx.Response(200, json={
        "events": [{"eventAction": "registration", "eventDate": "2026-10-01T00:00:00Z"}],
        "entities": [{"roles": ["registrar"], "vcardArray": ["vcard", [["version", {}, "text", "4.0"], ["fn", {}, "text", "Example Registrar"]]],
                      "entities": [{"roles": ["abuse"], "vcardArray": ["vcard", [["email", {}, "text", "abuse@registrar.example"]]]}]}],
    }))
    async with httpx.AsyncClient() as client:
        info = await takedown_info(settings.model_copy(update={"enable_network_checks": True}), client, "http://hbl-verify.top/login")
    assert info["registrar"] == "Example Registrar"
    assert info["abuse_email"] == "abuse@registrar.example"
    assert info["mailto"].startswith("mailto:abuse@registrar.example?subject=")
    assert "hbl-verify[.]top" in info["email"]["body"]
    official = await takedown_info(settings, None, "https://www.hbl.com")
    assert official["official"]["key"] == "hbl" and "mailto" not in official


@respx.mock
async def test_family_alert_flow(env):
    deps, check = env
    sent = respx.post("https://api.telegram.org/botTOKEN/sendMessage").mock(return_value=httpx.Response(200, json={"ok": True}))
    code = await family.create_code(deps.sessionmaker, "member1")
    assert await family.link_guardian(deps.sessionmaker, code.lower(), "555") is True
    assert await family.link_guardian(deps.sessionmaker, code, "666") is False  # one guardian per code
    async with httpx.AsyncClient() as client:
        n = await family.alert_guardians(deps.sessionmaker, client, "TOKEN", "member1", "account_takeover")
    assert n == 1
    body = json.loads(sent.calls[-1].request.content)
    assert body["chat_id"] == "555" and "Account takeover" in body["text"]
    assert (await family.status(deps.sessionmaker, "member1"))["guardians"] == 1
    assert await family.remove_guardian(deps.sessionmaker, "555") == 1


async def test_weekly_summary_and_message(env):
    deps, check = env
    await check(SCAM_A, "a", share=True)
    result = await alerts.send_weekly(deps, chat_id=None)
    assert result["delivered"] is False
    assert result["summary"]["flagged"] == 1
    assert "hbl-verify[.]top" in result["text"]
    latest = await alerts.latest_weekly(deps.sessionmaker)
    assert latest["flagged"] == 1


async def test_retention_purge_and_forget(env):
    deps, check = env
    old = datetime.now(UTC) - timedelta(days=400)
    await check(SCAM_A, "a", share=True, user_hash="me")
    pending = await check("Aap ka inaam nikla hai, 03451234567 par rabta karein", "p", share=True, user_hash="me")
    async with deps.sessionmaker() as session:
        row = await session.get(Report, pending["analysis_id"])
        row.created_at = old
        session.add(Analysis(id="old-1", created_at=old, verdict="no_red_flags", score=0, category="none", language="en",
                             rules_version="x"))
        session.add(AlertLog(kind="weekly", created_at=old, summary={}))
        await session.commit()
    deleted = await retention.purge(deps)
    assert deleted["pending_reports"] == 1 and deleted["analyses"] >= 1 and deleted["alerts"] == 1

    from app.api.service import run_analysis

    thread, _ = await run_analysis(deps.graph, text="Ammi main aa raha hoon", user_hash="me", channel="test")
    assert (await deps.graph.aget_state({"configurable": {"thread_id": thread}})).values
    gone = await retention.forget(deps, "me")
    assert not (await deps.graph.aget_state({"configurable": {"thread_id": thread}})).values
    assert gone["analyses"] >= 1 and gone["reports_unlinked"] == 1
    async with deps.sessionmaker() as session:
        assert (await session.execute(select(Report.reporter_hash))).scalars().all() == [None]


def test_rule_idea_validation():
    legit = [{"id": "l1", "text": "Your HBL OTP is 123456. Do not share it."}, {"id": "l2", "text": "Ammi main aa raha hoon"}]
    good = rule_ideas.test_pattern(r"tasdeeqi fee", ["Raqam ke liye 600 rupay tasdeeqi fee bhejein"], legit)
    assert good["passes"] is True
    broad = rule_ideas.test_pattern(r"otp|hoon", ["send otp"], legit)
    assert broad["passes"] is False and broad["false_positives"] == ["l1", "l2"]
    broken = rule_ideas.test_pattern(r"(unclosed", ["x"], legit)
    assert broken["valid"] is False
    slow = rule_ideas.test_pattern(r"(a|ab|b)+$", ["ab" * 2000 + "!"], legit)
    assert slow["timeouts"] == 1 and slow["passes"] is False


async def test_rule_idea_agent_proposes_and_tests(env):
    deps, _ = env
    deps.llm = FakeLLM(json_reply='{"signal": "fee_request", "pattern": "tasdeeqi fee", "rationale": "Verification fee wording."}')
    row = await rule_ideas.suggest(deps, ["BISP: raqam ke liye 600 rupay tasdeeqi fee bhejein"], "analyst@example.org")
    assert row.signal == "fee_request"
    assert row.test_results["passes"] is True
    assert row.test_results["negatives"] > 20  # the eval sets' legitimate messages


async def test_unreviewed_sites_and_text_stay_private(env):
    """A report that is auto-approved because of an OTP request must not publish an innocent
    website, or its text, until a person reviews it."""
    from app.db.stats import compute_stats
    from app.intel.reports import approve_report, campaign_list

    deps, check = env
    text = "Your account is blocked. Share the OTP you received now. Details at bakery-lahore.com"
    a = await check(text, "a", share=True, user_hash="u1")
    assert a["report_status"] == "approved"
    assert (await lookup(deps, "bakery-lahore.com"))["status"] == "no_reports"
    assert "bakery-lahore.com" not in json.dumps(await build_bundle(deps.sessionmaker))
    assert (await alerts.weekly_summary(deps.sessionmaker))["domains"] == []
    for c in await campaign_list(deps, min_reports=1):
        assert c["indicators"] == []
    assert (await compute_stats(deps.sessionmaker))["recent_reports"] == []
    later = await check("Share the OTP you received now, account blocked", "b")
    assert all(m["excerpt"] == "" for m in later["memory_matches"] if m["source"] == "community")

    await approve_report(deps, a["analysis_id"], reviewer="analyst@example.org")
    assert (await lookup(deps, "bakery-lahore.com"))["status"] == "reported"
    recent = (await compute_stats(deps.sessionmaker))["recent_reports"]
    assert len(recent) == 1 and recent[0]["id"] != a["analysis_id"]
    again = await check("Share the OTP you received now, account blocked", "c")
    assert any(m["excerpt"] for m in again["memory_matches"] if m["source"] == "community")


async def test_rejected_report_leaves_the_dashboard(env):
    from app.db.stats import compute_stats
    from app.intel.reports import approve_report

    deps, check = env
    a = await check(SCAM_A, "a", share=True)
    await approve_report(deps, a["analysis_id"], reviewer="analyst@example.org")
    assert len((await compute_stats(deps.sessionmaker))["recent_reports"]) == 1
    await reject_report(deps, a["analysis_id"], reviewer="analyst@example.org")
    assert (await compute_stats(deps.sessionmaker))["recent_reports"] == []
