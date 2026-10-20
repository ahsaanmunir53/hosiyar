import { useEffect, useState } from "react";
import { getQuality, type EvalSet, type Quality } from "../api";
import { useLang } from "../i18n";

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

function SetTable({ title, set }: { title: string; set: EvalSet }) {
  const { t } = useLang();
  return (
    <section className="panel">
      <h2 className="panel__title">{title}</h2>
      <p className="muted">
        {set.messages} · {set.scam} scam · {set.legit} legit
      </p>
      <div className="table-wrap">
        <table className="datatable">
          <thead>
            <tr>
              <th></th>
              <th>{t("eval_precision")}</th>
              <th>{t("eval_recall")}</th>
              <th>{t("eval_flagged")}</th>
              <th>{t("eval_fp")}</th>
              <th>{t("q_missed")}</th>
            </tr>
          </thead>
          <tbody>
            {set.runs.map((r) => (
              <tr key={r.name}>
                <td>
                  {r.name}
                  {r.model !== "none" && <span className="muted"> · {r.model}</span>}
                </td>
                <td>{pct(r.strict.precision)}</td>
                <td>{pct(r.strict.recall)}</td>
                <td>{pct(r.flagged.recall)}</td>
                <td>
                  {r.flagged.fp} / {set.legit}
                </td>
                <td dir="ltr" className="mono small">
                  {[...r.missed, ...r.false_alarms].join(", ") || t("q_none")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Breakdown({ title, data }: { title: string; data: Record<string, { n: number; caught: number; flagged: number }> }) {
  const rows = Object.entries(data);
  return (
    <section className="panel">
      <h2 className="panel__title">{title}</h2>
      <ul className="hbars hbars--stack">
        {rows.map(([k, v]) => (
          <li key={k}>
            <span className="hbars__label">{k.replace(/_/g, " ")}</span>
            <span className="hbars__track" aria-hidden="true">
              <span className="hbars__fill hbars__fill--soft" style={{ width: `${(v.flagged / v.n) * 100}%` }} />
              <span className="hbars__fill hbars__fill--over" style={{ width: `${(v.caught / v.n) * 100}%` }} />
            </span>
            <span className="hbars__value">
              {v.caught}/{v.n}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function QualityPage() {
  const { t } = useLang();
  const [q, setQ] = useState<Quality | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getQuality()
      .then(setQ)
      .catch(() => setFailed(true));
  }, []);

  const memory = q?.eval?.test.runs.find((r) => r.name === "rules + pattern memory") ?? q?.eval?.test.runs[0];
  const red = q?.redteam?.runs[0];
  return (
    <main className="page page--how">
      <header className="pagehead">
        <h1>{t("quality_title")}</h1>
        <p>{t("quality_sub")}</p>
        <p className="notice">{t("q_honest")}</p>
      </header>
      {failed && <p className="form-error">{t("err_network")}</p>}
      {!q && !failed && <p className="muted">{t("loading")}</p>}
      {q?.eval && (
        <>
          <section className="kpis">
            <div className="kpi">
              <span className="kpi__value">{memory ? pct(memory.strict.precision) : "—"}</span>
              <span className="kpi__label">{t("eval_precision")}</span>
            </div>
            <div className="kpi">
              <span className="kpi__value">{memory ? pct(memory.flagged.recall) : "—"}</span>
              <span className="kpi__label">{t("eval_flagged")}</span>
            </div>
            <div className="kpi">
              <span className="kpi__value">{memory ? memory.flagged.fp : "—"}</span>
              <span className="kpi__label">{t("eval_fp")}</span>
            </div>
            <div className="kpi">
              <span className="kpi__value">{red ? `${red.passed}/${red.total}` : "—"}</span>
              <span className="kpi__label">{t("q_redteam")}</span>
            </div>
          </section>
          <SetTable title={t("q_test")} set={q.eval.test} />
          {q.eval.test_ai && <SetTable title={t("q_ai")} set={q.eval.test_ai} />}
          {memory && (
            <div className="twocol">
              <Breakdown title={t("q_by_category")} data={memory.by_category} />
              <Breakdown title={t("q_by_language")} data={memory.by_language} />
            </div>
          )}
          <SetTable title={t("q_dev")} set={q.eval.dev} />
        </>
      )}
      {red && (
        <section className="panel">
          <h2 className="panel__title">
            {t("q_redteam")} · {red.passed}/{red.total} {t("q_passed")}
          </h2>
          <div className="table-wrap">
            <table className="datatable">
              <thead>
                <tr>
                  <th>{t("q_attack")}</th>
                  <th>{t("q_expect")}</th>
                  <th>{t("q_got")}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {red.cases.map((c) => (
                  <tr key={c.id}>
                    <td>{c.attack}</td>
                    <td>{c.expect.replace(/_/g, " ")}</td>
                    <td>
                      {t(`verdict_${c.verdict}`)} ({c.score})
                    </td>
                    <td>{c.passed ? <span className="tag tag--good">✓</span> : <span className="tag tag--bad">✗</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {q?.eval && (
        <p className="field__hint">
          {t("q_generated")}: {new Date(q.eval.generated_at).toLocaleString()} · {t("meta_rules")} {q.eval.rules_version}
        </p>
      )}
    </main>
  );
}
