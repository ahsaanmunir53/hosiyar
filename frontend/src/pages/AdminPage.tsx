import { useCallback, useEffect, useState, type FormEvent } from "react";
import { adminDelete, adminGet, adminPost, ApiError, login } from "../api";
import { useLang } from "../i18n";

/* The review panel is for analysts, so it is in English only. */

interface Session {
  token: string;
  email: string;
  role: "admin" | "analyst";
}

interface ReportRow {
  id: string;
  created_at: string;
  status: string;
  auto_approved: boolean;
  channel: string;
  source_kind: string;
  verdict: string;
  score: number;
  category: string;
  text: string;
  rules: string[];
  hard_rules: string[];
  brands: string[];
  reviewed_by: string | null;
  note: string | null;
  indicators: { kind: string; value: string }[];
}

interface CampaignRow {
  id: string;
  label: string;
  report_count: number;
  first_seen: string;
  last_seen: string;
  indicators: { kind: string; value: string }[];
}

interface Idea {
  id: string;
  status: string;
  signal: string;
  pattern: string;
  rationale: string;
  examples: string[];
  model: string;
  test: { valid: boolean; error: string | null; matched: number; positives: number; false_positives: string[]; negatives: number; timeouts: number; passes: boolean };
  snippet: string | null;
}

const KEY = "hs_admin_session";

function loadSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

function saveSession(s: Session | null) {
  try {
    if (s) sessionStorage.setItem(KEY, JSON.stringify(s));
    else sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: the session lives in memory only */
  }
}

const when = (iso: string) => new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });

function download(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function useApi(onExpired: () => void) {
  return useCallback(
    async <T,>(fn: () => Promise<T>): Promise<T | null> => {
      try {
        return await fn();
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) onExpired();
        throw e;
      }
    },
    [onExpired],
  );
}

function Login({ onLogin }: { onLogin: (s: Session) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await login(email, password);
      onLogin({ token: r.token, email: r.email, role: r.role });
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 0 ? err.message : "Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel admin-login">
      <h2 className="panel__title">Analyst login</h2>
      <p className="muted">For reviewers who approve shared reports, manage the watchlist and export indicators.</p>
      <form className="checkform" onSubmit={submit}>
        <label className="field">
          <span className="field__label">Email</span>
          <input type="text" inputMode="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} dir="ltr" />
        </label>
        <label className="field">
          <span className="field__label">Password</span>
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} dir="ltr" />
        </label>
        {error && <p className="form-error">{error}</p>}
        <div className="form-actions">
          <button className="btn btn--primary" type="submit" disabled={busy}>
            {busy ? "Logging in…" : "Log in"}
          </button>
        </div>
      </form>
    </section>
  );
}

function Queue({ session, call }: { session: Session; call: ReturnType<typeof useApi> }) {
  const [status, setStatus] = useState("pending");
  const [rows, setRows] = useState<ReportRow[] | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    call(() => adminGet<{ counts: Record<string, number>; reports: ReportRow[] }>(session.token, `/api/admin/reports?status=${status}`))
      .then((r) => {
        if (r) {
          setRows(r.reports);
          setCounts(r.counts);
        }
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, [call, session.token, status]);

  useEffect(load, [load]);

  async function decide(id: string, action: "approve" | "reject") {
    try {
      await call(() => adminPost(session.token, `/api/admin/reports/${id}/${action}`, { note: notes[id] || null }));
      load();
    } catch (e) {
      setError(String((e as Error).message));
    }
  }

  return (
    <section className="panel">
      <div className="admin-bar">
        <h2 className="panel__title">Review queue</h2>
        <div className="segmented">
          {["pending", "approved", "rejected", "all"].map((s) => (
            <button key={s} type="button" className={s === status ? "is-active" : ""} onClick={() => setStatus(s)}>
              {s} {s !== "all" && counts[s] !== undefined ? `(${counts[s]})` : ""}
            </button>
          ))}
        </div>
      </div>
      <p className="field__hint">
        Reports are approved automatically only when a decisive, pattern-backed rule fired. Approving adds the redacted text to the
        scam memory and makes its numbers count as reported.
      </p>
      {error && <p className="form-error">{error}</p>}
      {rows && rows.length === 0 && <p className="muted">Nothing here.</p>}
      <ul className="queue">
        {rows?.map((r) => (
          <li key={r.id} className={`queue__item queue__item--${r.verdict}`}>
            <div className="queue__meta">
              <span className={`tag ${r.verdict === "likely_scam" ? "tag--bad" : "tag--warn"}`}>
                {r.verdict.replace(/_/g, " ")} · {r.score}
              </span>
              <span className="tag">{r.category.replace(/_/g, " ")}</span>
              <span className="tag tag--muted">
                {r.channel} · {r.source_kind}
              </span>
              {r.auto_approved && <span className="tag tag--good">auto-approved</span>}
              {r.reviewed_by && <span className="tag tag--muted">by {r.reviewed_by}</span>}
              <span className="muted small">{when(r.created_at)}</span>
            </div>
            <p className="queue__text" dir="auto">
              {r.text}
            </p>
            <p className="queue__rules">
              {r.rules.map((id) => (
                <code key={id} className={r.hard_rules.includes(id) ? "is-hard" : ""}>
                  {id}
                </code>
              ))}
            </p>
            {r.indicators.length > 0 && (
              <p className="queue__rules" dir="ltr">
                {r.indicators.map((i) => (
                  <span key={i.kind + i.value} className="tag tag--muted">
                    {i.kind}: {i.value}
                  </span>
                ))}
              </p>
            )}
            {r.status !== "rejected" || status === "all" ? (
              <div className="queue__actions">
                <input type="text" placeholder="Note (optional)" value={notes[r.id] ?? ""} onChange={(e) => setNotes({ ...notes, [r.id]: e.target.value })} />
                {r.status !== "approved" || !r.reviewed_by ? (
                  <button type="button" className="btn btn--primary btn--small" onClick={() => decide(r.id, "approve")}>
                    {r.status === "approved" ? "Confirm" : "Approve"}
                  </button>
                ) : null}
                {r.status !== "rejected" && (
                  <button type="button" className="btn btn--ghost btn--small" onClick={() => decide(r.id, "reject")}>
                    Reject
                  </button>
                )}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Campaigns({ session, call }: { session: Session; call: ReturnType<typeof useApi> }) {
  const [rows, setRows] = useState<CampaignRow[] | null>(null);
  useEffect(() => {
    call(() => adminGet<{ campaigns: CampaignRow[] }>(session.token, "/api/admin/campaigns?min_reports=1")).then((r) => r && setRows(r.campaigns)).catch(() => setRows([]));
  }, [call, session.token]);

  async function exportOne(id?: string) {
    const bundle = await call(() => adminGet(session.token, `/api/admin/export/stix${id ? `?campaign_id=${id}` : ""}`));
    if (bundle) download(`hoshiyar-stix-${id ?? "all"}-${new Date().toISOString().slice(0, 10)}.json`, bundle);
  }

  return (
    <section className="panel">
      <div className="admin-bar">
        <h2 className="panel__title">Campaigns</h2>
        <button type="button" className="btn btn--ghost btn--small" onClick={() => exportOne()}>
          Export all as STIX 2.1
        </button>
      </div>
      <p className="field__hint">Grouped by a shared website, URL, number or account, or by very similar wording in the same category.</p>
      {rows && rows.length === 0 && <p className="muted">No campaigns yet.</p>}
      <ul className="queue">
        {rows?.map((c) => (
          <li key={c.id} className="queue__item">
            <div className="queue__meta">
              <strong>{c.label}</strong>
              <span className="tag">
                {c.report_count} {c.report_count === 1 ? "report" : "reports"}
              </span>
              <span className="muted small">
                {when(c.first_seen)} → {when(c.last_seen)}
              </span>
              <button type="button" className="btn btn--ghost btn--small" onClick={() => exportOne(c.id)}>
                STIX
              </button>
            </div>
            <p className="queue__rules" dir="ltr">
              {c.indicators.map((i) => (
                <span key={i.kind + i.value} className="tag tag--muted">
                  {i.kind}: {i.kind.endsWith("_fp") ? `${i.value.slice(0, 8)}…` : i.value}
                </span>
              ))}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Watchlist({ session, call }: { session: Session; call: ReturnType<typeof useApi> }) {
  const [rows, setRows] = useState<{ id: number; kind: string; label: string; note: string | null; added_by: string }[]>([]);
  const [kind, setKind] = useState("domain");
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    call(() => adminGet<{ entries: typeof rows }>(session.token, "/api/admin/watchlist")).then((r) => r && setRows(r.entries)).catch(() => undefined);
  }, [call, session.token]);
  useEffect(load, [load]);

  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await call(() => adminPost(session.token, "/api/admin/watchlist", { kind, value, note: note || null }));
      setValue("");
      setNote("");
      load();
    } catch (err) {
      setError(String((err as Error).message));
    }
  }

  return (
    <section className="panel">
      <h2 className="panel__title">Watchlist</h2>
      <p className="field__hint">A match is a decisive rule. Phone numbers and accounts are stored only as fingerprints with a masked label.</p>
      <form className="inline-form" onSubmit={add}>
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="domain">website</option>
          <option value="phone">phone number</option>
          <option value="account">bank account</option>
        </select>
        <input type="text" value={value} onChange={(e) => setValue(e.target.value)} placeholder="hbl-verify.top or 0300 1234567" dir="ltr" />
        <input type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note" />
        <button type="submit" className="btn btn--primary btn--small">
          Add
        </button>
      </form>
      {error && <p className="form-error">{error}</p>}
      <ul className="plainlist">
        {rows.map((r) => (
          <li key={r.id}>
            <span className="tag">{r.kind.replace("_fp", "")}</span> <code dir="ltr">{r.label}</code>
            {r.note && <span className="muted"> · {r.note}</span>}
            <span className="muted small"> · {r.added_by}</span>
            <button type="button" className="linkbtn" onClick={() => call(() => adminDelete(session.token, `/api/admin/watchlist/${r.id}`)).then(load)}>
              remove
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Official({ session, call }: { session: Session; call: ReturnType<typeof useApi> }) {
  const [data, setData] = useState<{ built_in: { name: string; kind: string; domains: string[] }[]; extra: { id: number; domain: string; name: string; kind: string; added_by: string }[] } | null>(null);
  const [form, setForm] = useState({ domain: "", name: "", kind: "bank" });
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    call(() => adminGet<NonNullable<typeof data>>(session.token, "/api/admin/official-domains")).then((r) => r && setData(r)).catch(() => undefined);
  }, [call, session.token]);
  useEffect(load, [load]);

  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await call(() => adminPost(session.token, "/api/admin/official-domains", form));
      setForm({ domain: "", name: "", kind: form.kind });
      load();
    } catch (err) {
      setError(String((err as Error).message));
    }
  }

  return (
    <section className="panel">
      <h2 className="panel__title">Official websites</h2>
      <p className="field__hint">
        A site listed here is never flagged as a look-alike. Listing a domain wrongly would hide real scams, so only admins can add one.
      </p>
      {session.role === "admin" && (
        <form className="inline-form" onSubmit={add}>
          <input type="text" value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} placeholder="bank.example.com" dir="ltr" />
          <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Name" />
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            {["bank", "wallet", "government", "telecom", "courier", "platform", "utility"].map((k) => (
              <option key={k}>{k}</option>
            ))}
          </select>
          <button type="submit" className="btn btn--primary btn--small">
            Add
          </button>
        </form>
      )}
      {error && <p className="form-error">{error}</p>}
      <ul className="plainlist">
        {data?.extra.map((r) => (
          <li key={r.id}>
            <code dir="ltr">{r.domain}</code> · {r.name} <span className="tag tag--muted">{r.kind}</span>
            <span className="muted small"> · {r.added_by}</span>
            {session.role === "admin" && (
              <button type="button" className="linkbtn" onClick={() => call(() => adminDelete(session.token, `/api/admin/official-domains/${r.id}`)).then(load)}>
                remove
              </button>
            )}
          </li>
        ))}
      </ul>
      {data && (
        <details>
          <summary className="muted">{data.built_in.length} built-in organisations</summary>
          <p className="small muted" dir="ltr">
            {data.built_in.map((b) => `${b.name} (${b.domains.join(", ")})`).join(" · ")}
          </p>
        </details>
      )}
    </section>
  );
}

function RuleIdeas({ session, call }: { session: Session; call: ReturnType<typeof useApi> }) {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [examples, setExamples] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    call(() => adminGet<{ ideas: Idea[] }>(session.token, "/api/admin/rule-ideas")).then((r) => r && setIdeas(r.ideas)).catch(() => undefined);
  }, [call, session.token]);
  useEffect(load, [load]);

  async function generate(source: "reports" | "dev_misses" | "examples") {
    setBusy(true);
    setError(null);
    try {
      const list =
        source === "examples"
          ? examples
              .split(/\n{2,}|\n-{3,}\n/)
              .map((x) => x.trim())
              .filter(Boolean)
              .slice(0, 8)
          : [];
      await call(() => adminPost(session.token, "/api/admin/rule-ideas", { source, examples: list }));
      load();
    } catch (err) {
      setError(String((err as Error).message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <h2 className="panel__title">Rule ideas</h2>
      <p className="field__hint">
        An AI agent proposes one regular expression from scams the rules missed. It is then tested here: it must match at least one
        missed scam, none of the legitimate messages in the evaluation sets, and finish quickly. Nothing is applied automatically; an
        accepted idea gives a code snippet for a developer.
      </p>
      <div className="form-actions wrap">
        <button type="button" className="btn btn--ghost btn--small" disabled={busy} onClick={() => generate("reports")}>
          Learn from missed reports
        </button>
        <button type="button" className="btn btn--ghost btn--small" disabled={busy} onClick={() => generate("dev_misses")}>
          Learn from dev-set misses
        </button>
      </div>
      <label className="field">
        <span className="field__label">Or paste examples (one per paragraph)</span>
        <textarea rows={3} value={examples} onChange={(e) => setExamples(e.target.value)} dir="auto" />
      </label>
      <div className="form-actions">
        <button type="button" className="btn btn--primary btn--small" disabled={busy || !examples.trim()} onClick={() => generate("examples")}>
          {busy ? "Thinking…" : "Suggest from examples"}
        </button>
      </div>
      {error && <p className="form-error">{error}</p>}
      <ul className="queue">
        {ideas.map((i) => (
          <li key={i.id} className="queue__item">
            <div className="queue__meta">
              <span className={`tag ${i.test.passes ? "tag--good" : "tag--bad"}`}>{i.test.passes ? "tests pass" : "tests fail"}</span>
              <span className="tag">{i.signal}</span>
              <span className="tag tag--muted">{i.status}</span>
              <span className="muted small">{i.model}</span>
            </div>
            <code className="queue__pattern" dir="ltr">
              {i.pattern}
            </code>
            <p className="small">{i.rationale}</p>
            <p className="small muted">
              matched {i.test.matched}/{i.test.positives} missed scams · {i.test.false_positives.length} of {i.test.negatives} legitimate
              messages {i.test.false_positives.length > 0 && `(${i.test.false_positives.join(", ")})`}
              {i.test.timeouts > 0 && ` · ${i.test.timeouts} timeouts`}
              {i.test.error && ` · ${i.test.error}`}
            </p>
            {i.status === "proposed" && (
              <div className="queue__actions">
                <button
                  type="button"
                  className="btn btn--primary btn--small"
                  disabled={!i.test.passes}
                  onClick={() => call(() => adminPost(session.token, `/api/admin/rule-ideas/${i.id}/accept`)).then(load)}
                >
                  Accept
                </button>
                <button type="button" className="btn btn--ghost btn--small" onClick={() => call(() => adminPost(session.token, `/api/admin/rule-ideas/${i.id}/reject`)).then(load)}>
                  Reject
                </button>
              </div>
            )}
            {i.snippet && <pre className="complaint__text">{i.snippet}</pre>}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Users({ session, call }: { session: Session; call: ReturnType<typeof useApi> }) {
  const [users, setUsers] = useState<{ id: number; email: string; role: string; active: boolean; last_login_at: string | null }[]>([]);
  const [form, setForm] = useState({ email: "", password: "", role: "analyst" });
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    call(() => adminGet<{ users: typeof users }>(session.token, "/api/admin/users")).then((r) => r && setUsers(r.users)).catch(() => undefined);
  }, [call, session.token]);
  useEffect(load, [load]);

  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await call(() => adminPost(session.token, "/api/admin/users", form));
      setForm({ email: "", password: "", role: "analyst" });
      load();
    } catch (err) {
      setError(String((err as Error).message));
    }
  }

  return (
    <section className="panel">
      <h2 className="panel__title">Users</h2>
      <form className="inline-form" onSubmit={add}>
        <input type="text" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="email" dir="ltr" />
        <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="password (10+ characters)" dir="ltr" />
        <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          <option>analyst</option>
          <option>admin</option>
        </select>
        <button type="submit" className="btn btn--primary btn--small">
          Create
        </button>
      </form>
      {error && <p className="form-error">{error}</p>}
      <ul className="plainlist">
        {users.map((u) => (
          <li key={u.id}>
            <code dir="ltr">{u.email}</code> <span className="tag">{u.role}</span>
            {!u.active && <span className="tag tag--bad">inactive</span>}
            <span className="muted small"> · last login {u.last_login_at ? when(u.last_login_at) : "never"}</span>
            {u.email !== session.email && (
              <button
                type="button"
                className="linkbtn"
                onClick={() => call(() => adminPost(session.token, `/api/admin/users/${u.id}/${u.active ? "deactivate" : "activate"}`)).then(load)}
              >
                {u.active ? "deactivate" : "activate"}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function Overview({ session, call }: { session: Session; call: ReturnType<typeof useApi> }) {
  const [o, setO] = useState<{ reports: Record<string, number>; campaigns: number; watchlist: number; indicators: Record<string, number> } | null>(null);
  const [purged, setPurged] = useState<Record<string, number> | null>(null);
  useEffect(() => {
    call(() => adminGet<NonNullable<typeof o>>(session.token, "/api/admin/overview")).then((r) => r && setO(r)).catch(() => undefined);
  }, [call, session.token]);
  return (
    <>
      <section className="kpis">
        <div className="kpi">
          <span className="kpi__value">{o?.reports.pending ?? 0}</span>
          <span className="kpi__label">waiting for review</span>
        </div>
        <div className="kpi">
          <span className="kpi__value">{o?.reports.approved ?? 0}</span>
          <span className="kpi__label">approved reports</span>
        </div>
        <div className="kpi">
          <span className="kpi__value">{o?.campaigns ?? 0}</span>
          <span className="kpi__label">campaigns (2+ reports)</span>
        </div>
        <div className="kpi">
          <span className="kpi__value">{o?.watchlist ?? 0}</span>
          <span className="kpi__label">on the watchlist</span>
        </div>
      </section>
      {session.role === "admin" && (
        <section className="panel">
          <h2 className="panel__title">Data</h2>
          <p className="field__hint">Runs the retention purge now (it also runs at start-up and from the scheduled job).</p>
          <button type="button" className="btn btn--ghost btn--small" onClick={() => call(() => adminPost<{ deleted: Record<string, number> }>(session.token, "/api/admin/purge")).then((r) => r && setPurged(r.deleted))}>
            Purge old data now
          </button>
          {purged && (
            <p className="notice notice--good" dir="ltr">
              {Object.entries(purged)
                .map(([k, v]) => `${k}: ${v}`)
                .join(" · ")}
            </p>
          )}
        </section>
      )}
    </>
  );
}

const TABS = ["overview", "queue", "campaigns", "watchlist", "official", "ideas", "users"] as const;
type Tab = (typeof TABS)[number];
const TAB_LABEL: Record<Tab, string> = {
  overview: "Overview",
  queue: "Review queue",
  campaigns: "Campaigns",
  watchlist: "Watchlist",
  official: "Official sites",
  ideas: "Rule ideas",
  users: "Users",
};

export default function AdminPage() {
  const { setLang, lang } = useLang();
  const [session, setSession] = useState<Session | null>(loadSession);
  const [tab, setTab] = useState<Tab>("overview");

  useEffect(() => {
    // The panel's text is English; keep the layout left-to-right while it is open.
    if (lang === "ur") setLang("en");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const logout = useCallback(() => {
    saveSession(null);
    setSession(null);
  }, []);
  const call = useApi(logout);

  return (
    <main className="page page--how page--admin">
      <header className="pagehead">
        <h1>Review panel</h1>
        <p>Approve shared reports, follow campaigns, keep the watchlist and export indicators for CERTs and police.</p>
      </header>
      {!session ? (
        <Login
          onLogin={(s) => {
            saveSession(s);
            setSession(s);
          }}
        />
      ) : (
        <>
          <div className="admin-bar">
            <div className="segmented segmented--scroll" role="tablist">
              {TABS.filter((x) => x !== "users" || session.role === "admin").map((x) => (
                <button key={x} type="button" role="tab" aria-selected={tab === x} className={tab === x ? "is-active" : ""} onClick={() => setTab(x)}>
                  {TAB_LABEL[x]}
                </button>
              ))}
            </div>
            <span className="muted small">
              {session.email} · {session.role}{" "}
              <button type="button" className="linkbtn" onClick={logout}>
                log out
              </button>
            </span>
          </div>
          {tab === "overview" && <Overview session={session} call={call} />}
          {tab === "queue" && <Queue session={session} call={call} />}
          {tab === "campaigns" && <Campaigns session={session} call={call} />}
          {tab === "watchlist" && <Watchlist session={session} call={call} />}
          {tab === "official" && <Official session={session} call={call} />}
          {tab === "ideas" && <RuleIdeas session={session} call={call} />}
          {tab === "users" && session.role === "admin" && <Users session={session} call={call} />}
        </>
      )}
    </main>
  );
}
