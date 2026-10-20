import { useMemo } from "react";
import { BANDS, bandLines } from "./geometry";
import type { SealStatus } from "./Seal3D";

const COLORS: Record<SealStatus, string> = {
  idle: "#9fe3c8",
  scanning: "#b9f0dc",
  no_red_flags: "#5ccfa5",
  suspicious: "#e7b54c",
  likely_scam: "#f2668c",
};

// Static guilloché drawing for browsers without WebGL.
export default function SealFallback({ status }: { status: SealStatus }) {
  const paths = useMemo(
    () =>
      BANDS.flatMap((spec) =>
        bandLines(spec, 360).map(({ positions }) => {
          let d = "";
          for (let i = 0; i < positions.length; i += 3) {
            d += `${i === 0 ? "M" : "L"}${(positions[i] * 100).toFixed(1)} ${(-positions[i + 1] * 100).toFixed(1)}`;
          }
          return { d: d + "Z", opacity: spec.opacity };
        }),
      ),
    [],
  );
  return (
    <svg viewBox="-240 -240 480 480" className="seal-fallback" aria-hidden="true">
      {paths.map((p, i) => (
        <path key={i} d={p.d} fill="none" stroke={COLORS[status]} strokeWidth={0.5} opacity={p.opacity + 0.15} />
      ))}
    </svg>
  );
}
