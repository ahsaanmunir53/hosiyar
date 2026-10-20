// Guilloché: the fine, interwoven line work printed on banknotes and passports to make them
// hard to copy. Each band is a set of modulated circles whose phases shift line by line,
// which produces the familiar woven "rope" pattern.

export interface BandSpec {
  radius: number;
  amp: number;
  lobes: number;
  lines: number;
  amp2: number;
  lobes2: number;
  z: number;
  speed: number; // radians per second around z
  opacity: number;
}

export const BANDS: BandSpec[] = [
  { radius: 2.02, amp: 0.012, lobes: 96, lines: 2, amp2: 0, lobes2: 1, z: -0.02, speed: 0.02, opacity: 0.35 },
  { radius: 1.8, amp: 0.13, lobes: 24, lines: 12, amp2: 0.02, lobes2: 72, z: 0.0, speed: 0.04, opacity: 0.42 },
  { radius: 1.38, amp: 0.17, lobes: 12, lines: 14, amp2: 0.045, lobes2: 36, z: 0.08, speed: -0.06, opacity: 0.5 },
  { radius: 0.98, amp: 0.07, lobes: 18, lines: 9, amp2: 0.0, lobes2: 1, z: -0.1, speed: 0.09, opacity: 0.45 },
];

export const POINTS_PER_LINE = 720;

export interface LineData {
  positions: Float32Array;
  params: Float32Array;
}

export function bandLines(spec: BandSpec, points = POINTS_PER_LINE): LineData[] {
  const out: LineData[] = [];
  for (let j = 0; j < spec.lines; j++) {
    const phase = (j / spec.lines) * Math.PI * 2;
    const positions = new Float32Array(points * 3);
    const params = new Float32Array(points);
    for (let i = 0; i < points; i++) {
      const th = (i / points) * Math.PI * 2;
      const r = spec.radius + spec.amp * Math.sin(spec.lobes * th + phase) + spec.amp2 * Math.sin(spec.lobes2 * th - phase * 0.5);
      positions[i * 3] = r * Math.cos(th);
      positions[i * 3 + 1] = r * Math.sin(th);
      positions[i * 3 + 2] = spec.z;
      params[i] = i / points + j * 0.031;
    }
    out.push({ positions, params });
  }
  return out;
}

// A heraldic shield outline in a unit box, used for the extruded centre piece.
export function shieldOutline(): [number, number][] {
  const pts: [number, number][] = [];
  const w = 0.62;
  const top = 0.72;
  pts.push([0, top + 0.06]);
  pts.push([w * 0.55, top]);
  pts.push([w, top - 0.08]);
  const steps = 24;
  for (let i = 1; i <= steps; i++) {
    const k = i / steps;
    const x = w * Math.cos((k * Math.PI) / 2) ** 0.85;
    const y = top - 0.08 - k * 1.42 + Math.sin(k * Math.PI) * 0.05;
    pts.push([x, y]);
  }
  const mirrored = pts
    .slice(1, -1)
    .reverse()
    .map(([x, y]) => [-x, y] as [number, number]);
  return [...pts, ...mirrored];
}
