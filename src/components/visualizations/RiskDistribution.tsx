import type { Distribution } from "@/lib/landing/markets";
import { START } from "@/lib/landing/markets";

/**
 * Histogram of possible portfolio values after the horizon (starting from 100). Bars below the starting value are drawn in red, the
 * median and 5th percentile are marked, and the exact figures are repeated in text beside the chart.
 */
export function RiskDistribution({ d }: { d: Distribution }) {
  const W = 520, H = 190, padB = 24, padT = 14;
  const lo = d.bins[0].from, hi = d.bins[d.bins.length - 1].to;
  const x = (v: number) => ((v - lo) / (hi - lo)) * W;
  const max = Math.max(...d.bins.map((b) => b.probability));
  const h = (p: number) => (p / max) * (H - padB - padT);
  const marks = [{ v: d.quantiles.q05, label: "5th pct", colour: "#FB7185" }, { v: d.quantiles.q50, label: "Median", colour: "#00E5FF" }, { v: d.quantiles.q95, label: "95th pct", colour: "#34D399" }];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Distribution of simulated portfolio value from ${lo.toFixed(0)} to ${hi.toFixed(0)}. Median ${d.quantiles.q50.toFixed(1)}, 5th percentile ${d.quantiles.q05.toFixed(1)}, 95th percentile ${d.quantiles.q95.toFixed(1)}. Chance of loss ${(d.lossProbability * 100).toFixed(0)} percent.`} className="h-auto w-full">
      {d.bins.map((b, i) => {
        const mid = (b.from + b.to) / 2;
        return <rect key={i} x={x(b.from) + 0.5} width={Math.max(1, x(b.to) - x(b.from) - 1)} y={H - padB - h(b.probability)} height={h(b.probability)} rx="2" fill={mid < START ? "#FB7185" : "#2563EB"} opacity={mid < START ? 0.7 : 0.75} className="transition-all duration-700" />;
      })}
      {START > lo && START < hi && <><line x1={x(START)} x2={x(START)} y1={padT - 4} y2={H - padB} stroke="#F8FAFC" strokeDasharray="3 3" opacity="0.7" /><text x={x(START)} y={padT - 5} textAnchor="middle" fontSize="9" fill="#F8FAFC">start 100</text></>}
      {marks.map((m) => <g key={m.label}><line x1={x(m.v)} x2={x(m.v)} y1={padT + 6} y2={H - padB} stroke={m.colour} strokeWidth="1.5" /><text x={x(m.v)} y={H - 8} textAnchor="middle" fontSize="9" fill={m.colour}>{m.label} {m.v.toFixed(0)}</text></g>)}
    </svg>
  );
}

/** Fan chart: the range of portfolio value over time (5th to 95th percentile, 25th to 75th, and the median) from the same model. */
export function FanChart({ points }: { points: { t: number; q05: number; q25: number; q50: number; q75: number; q95: number }[] }) {
  const W = 520, H = 190, pad = 28;
  const tMax = points[points.length - 1].t;
  const lo = Math.min(...points.map((p) => p.q05), START) * 0.99, hi = Math.max(...points.map((p) => p.q95), START) * 1.01;
  const x = (t: number) => pad + (t / tMax) * (W - pad - 6);
  const y = (v: number) => 8 + (1 - (v - lo) / (hi - lo)) * (H - 28);
  const band = (a: "q05" | "q25", b: "q95" | "q75") => `${points.map((p, i) => `${i ? "L" : "M"}${x(p.t)} ${y(p[b])}`).join(" ")} ${[...points].reverse().map((p) => `L${x(p.t)} ${y(p[a])}`).join(" ")} Z`;
  const last = points[points.length - 1];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Range of portfolio value over time. At the end the median is ${last.q50.toFixed(1)} and 90 percent of outcomes fall between ${last.q05.toFixed(1)} and ${last.q95.toFixed(1)}.`} className="h-auto w-full">
      <line x1={pad} x2={W - 6} y1={y(START)} y2={y(START)} stroke="#F8FAFC" strokeDasharray="3 3" opacity="0.5" />
      <path d={band("q05", "q95")} fill="#2563EB" opacity="0.22" className="transition-all duration-700" />
      <path d={band("q25", "q75")} fill="#00E5FF" opacity="0.22" className="transition-all duration-700" />
      <path d={points.map((p, i) => `${i ? "L" : "M"}${x(p.t)} ${y(p.q50)}`).join(" ")} fill="none" stroke="#00E5FF" strokeWidth="2" />
      <text x={pad - 4} y={y(START) + 3} textAnchor="end" fontSize="9" fill="#94A3B8">100</text>
      <text x={W - 6} y={H - 4} textAnchor="end" fontSize="9" fill="#94A3B8">{Math.round(tMax * 12)} month{Math.round(tMax * 12) === 1 ? "" : "s"}</text>
      <text x={pad} y={H - 4} fontSize="9" fill="#94A3B8">today</text>
    </svg>
  );
}
