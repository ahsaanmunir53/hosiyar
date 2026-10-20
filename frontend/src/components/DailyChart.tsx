import { useState } from "react";
import type { Stats, Verdict } from "../api";
import { useLang } from "../i18n";

// Validated (dataviz validator, dark surface #12302A): lightness band, chroma, CVD and contrast all pass.
export const VERDICT_COLORS: Record<Verdict, string> = {
  likely_scam: "#DC4C74",
  suspicious: "#B98D2E",
  no_red_flags: "#35A07F",
};
const ORDER: Verdict[] = ["likely_scam", "suspicious", "no_red_flags"];

export default function DailyChart({ daily }: { daily: Stats["daily"] }) {
  const { t, lang } = useLang();
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);

  const W = 720;
  const H = 260;
  const pad = { l: 34, r: 12, t: 16, b: 30 };
  const innerW = W - pad.l - pad.r;
  const innerH = H - pad.t - pad.b;
  const totals = daily.map((d) => ORDER.reduce((s, v) => s + (d[v] || 0), 0));
  const max = Math.max(4, ...totals);
  const niceMax = Math.ceil(max / 4) * 4;
  const slot = innerW / daily.length;
  const barW = Math.min(30, slot - 6);
  const y = (v: number) => pad.t + innerH - (v / niceMax) * innerH;
  const fmtDate = (iso: string) =>
    new Date(iso + "T00:00:00").toLocaleDateString(lang === "ur" ? "ur-PK" : "en-GB", { day: "numeric", month: "short" });
  const rtl = lang === "ur";

  return (
    <div className="chart">
      <div className="chart__top">
        <ul className="legend">
          {ORDER.map((v) => (
            <li key={v}>
              <span className="legend__swatch" style={{ background: VERDICT_COLORS[v] }} />
              {t(`verdict_${v}`)}
            </li>
          ))}
        </ul>
        <button type="button" className="btn btn--ghost btn--small" onClick={() => setTable((x) => !x)}>
          {table ? t("show_chart") : t("show_table")}
        </button>
      </div>

      {table ? (
        <div className="table-wrap">
          <table className="datatable">
            <thead>
              <tr>
                <th>{t("date")}</th>
                {ORDER.map((v) => (
                  <th key={v}>{t(`verdict_${v}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {daily.map((d) => (
                <tr key={d.date}>
                  <td>{fmtDate(d.date)}</td>
                  {ORDER.map((v) => (
                    <td key={v}>{d[v] || 0}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="chart__plot">
          <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t("daily_title")} style={{ direction: "ltr" }}>
            {[0, 0.25, 0.5, 0.75, 1].map((f) => {
              const v = Math.round(niceMax * f);
              return (
                <g key={f}>
                  <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} className="chart__grid" />
                  <text x={pad.l - 8} y={y(v) + 4} className="chart__tick" textAnchor="end">
                    {v}
                  </text>
                </g>
              );
            })}
            {daily.map((d, i) => {
              const idx = rtl ? daily.length - 1 - i : i;
              const x = pad.l + idx * slot + (slot - barW) / 2;
              let acc = 0;
              const segs = ORDER.map((v) => {
                const n = d[v] || 0;
                const bottom = y(acc);
                acc += n;
                return { v, n, bottom, top: y(acc) };
              }).filter((s) => s.n > 0);
              return (
                <g key={d.date} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                  <rect x={pad.l + idx * slot} y={pad.t} width={slot} height={innerH} fill="transparent" />
                  {segs.map((s, j) => {
                    // 2px surface gap between stacked segments; only the top segment gets rounded ends.
                    const bottom = j > 0 ? s.bottom - 2 : s.bottom;
                    const h = Math.max(0, bottom - s.top);
                    const r = j === segs.length - 1 ? Math.min(4, h / 2) : 0;
                    const path =
                      `M${x},${bottom}V${s.top + r}Q${x},${s.top} ${x + r},${s.top}` +
                      `H${x + barW - r}Q${x + barW},${s.top} ${x + barW},${s.top + r}V${bottom}Z`;
                    return <path key={s.v} d={path} fill={VERDICT_COLORS[s.v]} opacity={hover === null || hover === i ? 1 : 0.45} />;
                  })}
                  {(i % 2 === 0 || daily.length <= 8) && (
                    <text x={x + barW / 2} y={H - 10} textAnchor="middle" className="chart__tick">
                      {fmtDate(d.date)}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
          {hover !== null && (
            <div
              className="tooltip"
              style={{
                left: `${(((rtl ? daily.length - 1 - hover : hover) + 0.5) * slot + pad.l) / W * 100}%`,
              }}
            >
              <strong>{fmtDate(daily[hover].date)}</strong>
              {ORDER.map((v) => (
                <span key={v}>
                  <i style={{ background: VERDICT_COLORS[v] }} />
                  {t(`verdict_${v}`)}: {daily[hover][v] || 0}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
