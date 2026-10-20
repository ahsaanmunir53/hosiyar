import { useEffect, useState } from "react";
import { ApiError, getCampaigns, getLatestAlert, getStats, type Campaign, type Stats, type WeeklyAlert } from "../api";
import DailyChart, { VERDICT_COLORS } from "../components/DailyChart";
import { useLang } from "../i18n";

const CATEGORY: Record<string, { en: string; ur: string; roman: string }> = {
  account_takeover: { en: "Account takeover", ur: "اکاؤنٹ پر قبضہ", roman: "Account par qabza" },
  government_benefit: { en: "Fake government payment", ur: "جعلی سرکاری امداد", roman: "Jaali sarkari imdad" },
  government_notice: { en: "Government notice or fine", ur: "سرکاری نوٹس یا جرمانہ", roman: "Sarkari notice ya jurmana" },
  bank_wallet: { en: "Bank or wallet impersonation", ur: "جعلی بینک یا والیٹ", roman: "Jaali bank ya wallet" },
  family_emergency: { en: "Fake family emergency", ur: "جعلی رشتہ دار ایمرجنسی", roman: "Jaali rishtedar emergency" },
  job_task: { en: "Job or task scam", ur: "جعلی نوکری", roman: "Jaali naukri" },
  investment: { en: "Investment scam", ur: "سرمایہ کاری فراڈ", roman: "Investment fraud" },
  prize: { en: "Prize or lottery scam", ur: "انعام یا لاٹری فراڈ", roman: "Inaam ya lottery fraud" },
  delivery: { en: "Parcel scam", ur: "پارسل فراڈ", roman: "Parcel fraud" },
  loan: { en: "Loan scam", ur: "قرض فراڈ", roman: "Qarz fraud" },
  utility: { en: "Utility bill scam", ur: "بل فراڈ", roman: "Bill fraud" },
  phishing_link: { en: "Phishing link", ur: "فشنگ لنک", roman: "Phishing link" },
  malicious_file: { en: "Dangerous file", ur: "خطرناک فائل", roman: "Khatarnak file" },
  other: { en: "Other", ur: "دیگر", roman: "Deegar" },
};

function Bars({ rows }: { rows: { label: string; count: number }[] }) {
  const { t } = useLang();
  if (!rows.length) return <p className="muted">{t("nothing_yet")}</p>;
  const max = Math.max(...rows.map((r) => r.count));
  return (
    <ul className="hbars">
      {rows.map((r) => (
        <li key={r.label}>
          <span className="hbars__label">{r.label}</span>
          <span className="hbars__track">
            <span className="hbars__fill" style={{ width: `${(r.count / max) * 100}%` }} />
          </span>
          <span className="hbars__value">{r.count}</span>
        </li>
      ))}
    </ul>
  );
}

export default function TrendsPage() {
  const { t, pick, lang } = useLang();
  const [stats, setStats] = useState<Stats | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[] | null>(null);
  const [alert, setAlert] = useState<WeeklyAlert | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getStats()
      .then(setStats)
      .catch((e) => setError(e instanceof ApiError && e.status !== 0 ? e.message : t("err_network")));
    getCampaigns()
      .then((r) => setCampaigns(r.campaigns))
      .catch(() => setCampaigns([]));
    getLatestAlert()
      .then((r) => setAlert(r.alert))
      .catch(() => setAlert(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const locale = lang === "ur" ? "ur-PK" : "en-GB";
  const date = (iso: string) => new Date(iso).toLocaleDateString(locale);
  // "2026-10-20" is a calendar day; read it as local time so it does not shift by a day.
  const day = (ymd: string) => {
    const [y, m, d] = ymd.slice(0, 10).split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString(locale);
  };

  const fmt = (n: number) => n.toLocaleString(lang === "ur" ? "ur-PK" : "en-PK");

  return (
    <main className="page page--trends">
      <header className="pagehead">
        <h1>{t("trends_title")}</h1>
        <p>{t("trends_sub")}</p>
        {stats?.includes_sample_data && <p className="notice">{t("sample_note")}</p>}
      </header>

      {error && <p className="form-error">{error}</p>}
      {!stats && !error && <p className="muted">{t("loading")}</p>}

      {stats && (
        <>
          <section className="kpis">
            <div className="kpi">
              <span className="kpi__value">{fmt(stats.total_checks)}</span>
              <span className="kpi__label">{t("kpi_checks")}</span>
            </div>
            {(["likely_scam", "suspicious", "no_red_flags"] as const).map((v) => (
              <div className="kpi" key={v}>
                <span className="kpi__value">{fmt(stats.verdicts[v] ?? 0)}</span>
                <span className="kpi__label">
                  <i className="kpi__dot" style={{ background: VERDICT_COLORS[v] }} />
                  {t(`verdict_${v}`)}
                </span>
              </div>
            ))}
          </section>

          <section className="panel">
            <h2 className="panel__title">{t("daily_title")}</h2>
            <DailyChart daily={stats.daily} />
          </section>

          <div className="twocol">
            <section className="panel">
              <h2 className="panel__title">{t("categories_title")}</h2>
              <Bars rows={stats.top_categories.map((c) => ({ label: pick(CATEGORY[c.category] ?? CATEGORY.other), count: c.count }))} />
            </section>
            <section className="panel">
              <h2 className="panel__title">{t("brands_title")}</h2>
              <Bars rows={stats.top_brands.map((b) => ({ label: b.brand.toUpperCase(), count: b.count }))} />
            </section>
          </div>

          <div className="twocol twocol--top">
            <section className="panel">
              <h2 className="panel__title">{t("campaigns_title")}</h2>
              <p className="muted small">{t("campaigns_sub")}</p>
              {campaigns && campaigns.length === 0 && <p className="muted">{t("nothing_yet")}</p>}
              <ul className="campaigns">
                {campaigns?.map((c) => (
                  <li key={c.id}>
                    <span className="campaigns__count">{c.report_count}</span>
                    <div>
                      <strong>{pick(CATEGORY[c.category] ?? CATEGORY.other)}</strong>
                      {c.brands.length > 0 && <span className="muted"> · {c.brands.map((b) => b.toUpperCase()).join(", ")}</span>}
                      <p className="campaigns__meta">
                        {c.report_count} {t("reports_word")} · {t("last_seen")} {date(c.last_seen)}
                      </p>
                      {c.indicators.length > 0 && (
                        <p className="campaigns__domains" dir="ltr">
                          {c.indicators.slice(0, 4).map((i) => (
                            <code key={i.value}>{i.value.replace(/\./g, "[.]")}</code>
                          ))}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
            <section className="panel panel--alert">
              <h2 className="panel__title">{t("weekly_title")}</h2>
              {alert === null && <p className="muted">{t("weekly_none")}</p>}
              {alert && (
                <>
                  <p className="muted small">
                    {day(alert.from)} → {day(alert.to)} · {alert.flagged} {t("weekly_flagged")}
                  </p>
                  <ol className="steps">
                    {alert.top_categories.map((c) => (
                      <li key={c.category}>
                        {pick(CATEGORY[c.category] ?? CATEGORY.other)} <span className="muted">({c.count})</span>
                      </li>
                    ))}
                  </ol>
                  {alert.domains.length > 0 && (
                    <p className="campaigns__domains" dir="ltr">
                      <span className="field__label">{t("weekly_avoid")}: </span>
                      {alert.domains.map((d) => (
                        <code key={d}>{d.replace(/\./g, "[.]")}</code>
                      ))}
                    </p>
                  )}
                </>
              )}
            </section>
          </div>

          <section className="panel">
            <h2 className="panel__title">{t("recent_title")}</h2>
            {stats.recent_reports.length === 0 ? (
              <p className="muted">{t("nothing_yet")}</p>
            ) : (
              <ul className="recent">
                {stats.recent_reports.map((r) => (
                  <li key={r.id}>
                    <p dir="auto">{r.excerpt}</p>
                    <span className="recent__meta">
                      <i className="kpi__dot" style={{ background: VERDICT_COLORS[r.verdict] }} />
                      {t(`verdict_${r.verdict}`)} · {pick(CATEGORY[r.category] ?? CATEGORY.other)} ·{" "}
                      {new Date(r.created_at).toLocaleDateString(lang === "ur" ? "ur-PK" : "en-GB")}
                      {r.sample && <span className="tag tag--muted">{t("sample_tag")}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </main>
  );
}
