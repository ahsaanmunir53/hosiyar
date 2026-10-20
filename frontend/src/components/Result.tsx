import type { Analysis, LinkReport, TraceStep } from "../api";
import { useLang } from "../i18n";
import type { Submitted } from "../pages/CheckPage";
import ComplaintPack from "./ComplaintPack";
import FileInfoPanel from "./FileInfoPanel";
import Followup from "./Followup";
import ReadAloud from "./ReadAloud";
import Takedown from "./Takedown";

function Stamp({ verdict, score }: { verdict: Analysis["verdict"]; score: number }) {
  const { t } = useLang();
  return (
    <div className={`stamp stamp--${verdict}`} role="img" aria-label={`${t(`verdict_${verdict}`)}, ${score}/100 ${t("risk_score")}`}>
      <svg viewBox="0 0 120 120" aria-hidden="true">
        <circle cx="60" cy="60" r="56" className="stamp__outer" />
        <circle cx="60" cy="60" r="47" className="stamp__inner" />
        <circle
          cx="60"
          cy="60"
          r="51.5"
          className="stamp__arc"
          pathLength={100}
          strokeDasharray={`${Math.max(score, 2)} 100`}
          transform="rotate(-90 60 60)"
        />
      </svg>
      <div className="stamp__body">
        <span className="stamp__score">{score}</span>
        <span className="stamp__label">{t("risk_score")}</span>
      </div>
    </div>
  );
}

function isRisky(link: LinkReport): boolean {
  return Boolean(
    !link.official_brand &&
      (link.lookalike_brand || link.safe_browsing_threats.length || link.risky_tld || link.homograph_of ||
        (link.domain_age_days !== null && link.domain_age_days < 90)),
  );
}

function LinkCard({ link, flagged }: { link: LinkReport; flagged: boolean }) {
  const { t } = useLang();
  const domain = link.final_registered_domain || link.registered_domain || link.url;
  return (
    <li className="linkcard">
      <code className="linkcard__url" dir="ltr">
        {link.url.replace(/^https?:\/\//, "")}
      </code>
      <div className="linkcard__facts">
        {link.official_brand && (
          <span className="tag tag--good">
            {t("link_official")} {link.official_brand.name}
          </span>
        )}
        {link.lookalike_brand && (
          <span className="tag tag--bad">
            {t("link_lookalike")} {link.lookalike_brand.name}
          </span>
        )}
        {link.homograph_of && (
          <span className="tag tag--bad">
            {t("link_homograph")} <bdi dir="ltr">{link.homograph_of}</bdi>
          </span>
        )}
        {link.is_shortener && (
          <span className="tag">
            {t("link_short")}
            {link.expanded_url ? ` → ${link.expanded_url.replace(/^https?:\/\//, "")}` : ""}
          </span>
        )}
        {link.safe_browsing_threats.length > 0 && <span className="tag tag--bad">{t("link_sb")}</span>}
        {link.risky_tld && !link.official_brand && <span className="tag tag--warn">{t("link_risky_tld")}</span>}
        {link.domain_age_days !== null ? (
          <span className={`tag ${link.domain_age_days < 90 ? "tag--warn" : ""}`}>
            {domain}: {link.domain_age_days} {t("link_age")}
          </span>
        ) : (
          !link.official_brand && <span className="tag tag--muted">{t("link_unknown_age")}</span>
        )}
      </div>
      {flagged && isRisky(link) && <Takedown url={link.expanded_url || link.url} />}
    </li>
  );
}

// Phone numbers and web addresses keep left-to-right order inside Urdu text.
const LTR_TOKEN = /((?:https?:\/\/)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:\/\S*)?|\d[\d-]{3,}\d)/gi;

// Turn the domain mentioned in a step into a link instead of repeating it.
function StepText({ text, link }: { text: string; link?: string | null }) {
  const domain = link?.replace(/^https?:\/\//, "") ?? "";
  const bare = domain.replace(/^www\./, "");
  return (
    <>
      {text.split(LTR_TOKEN).map((part, i) => {
        if (i % 2 === 0) return part;
        if (link && (part === domain || part === bare)) {
          return (
            <a key={i} href={link} target="_blank" rel="noreferrer" dir="ltr">
              {part}
            </a>
          );
        }
        return (
          <bdi key={i} dir="ltr">
            {part}
          </bdi>
        );
      })}
    </>
  );
}

function trailLabel(step: TraceStep, t: (k: string) => string): string {
  for (const key of [`trail_${step.step}_${step.by}`, `trail_${step.step}`]) {
    const label = t(key);
    if (label !== key) return label;
  }
  return step.step;
}

function trailDetail(step: TraceStep, t: (k: string) => string): string | null {
  const d = step.detail as Record<string, unknown>;
  if (step.step === "read_with_ai") {
    if (typeof d.summary === "string") {
      const extra = [d.model, d.cached ? t("cached") : null].filter(Boolean).join(" · ");
      return extra ? `${d.summary} · ${extra}` : d.summary;
    }
    const errors = d.errors as string[] | undefined;
    if (errors?.length) return errors.join(" · ");
  }
  if (step.step === "plan") {
    const chosen = (d.specialists as string[]) ?? [];
    return chosen.length ? `${chosen.join(" + ")} · ${d.why}` : String(d.why ?? "");
  }
  if (step.step === "link_agent" || step.step === "memory_agent") {
    if (typeof d.summary === "string" && d.summary) return typeof d.model === "string" ? `${d.summary} · ${d.model}` : d.summary;
    const errors = d.errors as string[] | undefined;
    return errors?.length ? errors.join(" · ") : null;
  }
  if (step.step === "lookup_indicators") {
    return `${d.reported_numbers ?? 0} · ${d.reported_accounts ?? 0} · ${d.watchlist ?? 0}`;
  }
  if (step.step === "check_link" && step.by === "agent") {
    const args = d.args as { url?: string } | undefined;
    return `${args?.url ?? ""}${d.ok === false ? ` · ${t("refused")}` : ""}`;
  }
  if (step.step === "check_link" && step.by === "guard") return ((d.urls as string[]) ?? []).join(", ");
  if (step.step === "search_similar_reports" && step.by === "agent") {
    const args = d.args as { description?: string } | undefined;
    return args?.description ?? null;
  }
  if (step.step === "assess") return `${d.score}/100 · ${(d.rules as string[])?.length ?? 0} rules`;
  if (step.step === "prepare") {
    const red = d.redacted as Record<string, number> | undefined;
    const n = red ? Object.values(red).reduce((a, b) => a + b, 0) : 0;
    const signals = ((d.pattern_signals as string[]) ?? []).filter((x) => x !== "has_phone").length;
    return `${n} ${t("trail_removed")} · ${signals} ${t("trail_signals")}`;
  }
  if (step.step === "search_similar_reports" && step.by === "guard") return `${d.found ?? 0} ${t("trail_found")}`;
  return null;
}

const OTHER_LANGS = new Set(["ps", "sd", "pa", "pa_roman"]);

export default function Result({ result, submitted, onReset }: { result: Analysis; submitted: Submitted | null; onReset: () => void }) {
  const { t, pick, lang } = useLang();
  const explanation = result.explanation.language === lang ? result.explanation.text : result.explanation.templates[lang];
  const viaAI = result.explanation.source === "ai" && result.explanation.language === lang;
  const reasons = result.reasons;
  const redactions = Object.entries(result.redactions);
  const degraded = result.degraded.includes("ai_off")
    ? t("degraded_ai_off")
    : result.degraded.some((d) => d.endsWith("_failed"))
      ? t("degraded_ai_failed")
      : null;

  return (
    <section className={`result result--${result.verdict}`} aria-live="polite" aria-labelledby="verdict-heading">
      <div className="result__head">
        <Stamp verdict={result.verdict} score={result.score} />
        <div className="result__summary">
          <h2 id="verdict-heading" className="result__verdict">
            {t(`verdict_${result.verdict}`)}
          </h2>
          {result.verdict !== "no_red_flags" && <p className="result__category">{pick(result.category.label)}</p>}
          <p className="result__explain" dir="auto">
            {explanation}
          </p>
          <p className="result__source">{viaAI ? t("written_by_ai") : t("written_by_rules")}</p>
          <div className="result__tools">
            <ReadAloud text={[t(`verdict_${result.verdict}`), explanation, ...result.next_steps.slice(0, 3).map((s) => pick(s.text))].join(". ")} />
            {result.verdict !== "no_red_flags" && <ComplaintPack result={result} submitted={submitted} />}
          </div>
          {OTHER_LANGS.has(result.source_language) && (
            <p className="notice">
              {t("lang_note")} {t(`lang_${result.source_language}`)}. {t("lang_note_tail")}
            </p>
          )}
          {degraded && <p className="notice">{degraded}</p>}
          {result.shared && (
            <p className={`notice ${result.report_status === "pending" ? "" : "notice--good"}`}>
              {result.report_status === "pending" ? t("report_pending") : t("shared_yes")}
            </p>
          )}
        </div>
      </div>

      <div className="result__grid">
        <div className="result__col">
          <section className="panel">
            <h3>{t("why_title")}</h3>
            {reasons.length === 0 && <p className="muted">{t("why_empty")}</p>}
            <ol className="reasons">
              {reasons.map((r) => (
                <li key={r.id} className={`reason ${r.hard ? "is-hard" : ""} ${r.weight < 0 ? "is-good" : ""}`}>
                  <div className="reason__head">
                    <span className="reason__title">{pick(r.title)}</span>
                    <span className="reason__pts" dir="ltr">
                      {r.weight > 0 ? `+${r.weight}` : r.weight}
                    </span>
                  </div>
                  <p className="reason__why">{pick(r.why)}</p>
                  <div className="reason__meta">
                    {r.hard && <span className="tag tag--bad">{t("decisive")}</span>}
                    {r.weight < 0 && <span className="tag tag--good">{t("reassuring")}</span>}
                    {r.sources.map((s) => (
                      <span key={s} className="tag tag--muted">
                        {t(`src_${s}`)}
                      </span>
                    ))}
                  </div>
                  {r.evidence.length > 0 && (
                    <ul className="evidence">
                      {r.evidence.slice(0, 2).map((e) => (
                        <li key={e} dir="auto">
                          {e}
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ol>
          </section>

          {result.file_info && <FileInfoPanel info={result.file_info} />}

          {result.links.length > 0 && (
            <section className="panel">
              <h3>{t("links_title")}</h3>
              <ul className="links">
                {result.links.map((l) => (
                  <LinkCard key={l.url} link={l} flagged={result.verdict !== "no_red_flags"} />
                ))}
              </ul>
            </section>
          )}

          {(result.similar.length > 0 || result.reported_number_count > 0 || result.reported_account_count > 0) && (
            <section className="panel">
              <h3>{t("similar_title")}</h3>
              {result.reported_number_count > 0 && <p className="notice notice--bad">{t("number_seen")}</p>}
              {result.reported_account_count > 0 && <p className="notice notice--bad">{t("account_seen")}</p>}
              <ul className="similar">
                {result.similar.map((s) => (
                  <li key={s.key}>
                    {s.excerpt ? <p dir="auto">{s.excerpt}</p> : <p className="muted">{t("similar_hidden")}</p>}
                    <span className="similar__meta">
                      {Math.round(s.similarity * 100)}% {t("similar_match")} ·{" "}
                      {s.source === "community" ? t("similar_community") : t("similar_pattern")}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <div className="result__col">
          <section className="panel panel--steps">
            <h3>{t("steps_title")}</h3>
            <ol className="steps">
              {result.next_steps.map((s) => (
                <li key={s.id} className={s.urgent ? "is-urgent" : ""}>
                  <StepText text={pick(s.text)} link={s.link} />
                </li>
              ))}
            </ol>
          </section>

          <section className="panel">
            <h3>{t("trail_title")}</h3>
            <ol className="trail">
              {result.investigation.map((step, i) => {
                const detail = trailDetail(step, t);
                return (
                  <li key={i} className={`trail__item trail__item--${step.by}`}>
                    <span className="trail__by">{t(`by_${step.by}`)}</span>
                    <span className="trail__label">{trailLabel(step, t)}</span>
                    {detail && (
                      <span className="trail__detail" dir="auto">
                        {detail}
                      </span>
                    )}
                  </li>
                );
              })}
            </ol>
          </section>

          <section className="panel">
            <h3>{t("analyzed_title")}</h3>
            <p className="analyzed" dir="auto">
              {result.analyzed_text}
            </p>
            {redactions.length > 0 && (
              <p className="field__hint">
                {t("redacted_note")}: {redactions.map(([k, n]) => `${n} ${t(`red_${k}`)}`).join(", ")}
              </p>
            )}
          </section>
        </div>
      </div>

      <Followup threadId={result.thread_id} />

      <footer className="result__meta">
        <span>
          {t("meta_model")}: {result.model === "none" ? "—" : result.model}
        </span>
        <span>
          {t("meta_rules")}: {result.rules_version}
        </span>
        <button type="button" className="btn btn--ghost" onClick={onReset}>
          {t("new_check")}
        </button>
      </footer>
    </section>
  );
}
