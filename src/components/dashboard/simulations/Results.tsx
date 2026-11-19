"use client";

import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SimOutput, SimResult } from "@/lib/types";
import { Badge, Panel } from "../ui";

export const fmt = (n: number) => (Number.isFinite(n) ? new Intl.NumberFormat("en-US", { maximumSignificantDigits: 4 }).format(n) : "—");
const tip = { background: "#17213a", border: "1px solid #334155", borderRadius: 8 };
const axis = { fill: "#94a3b8", fontSize: 11 };

export function Histogram({ h, threshold, label }: { h: SimOutput["histogram"]; threshold?: number | null; label: string }) {
  const total = h.counts.reduce((a, b) => a + b, 0);
  const data = h.counts.map((c, i) => ({ x: fmt((h.edges[i] + h.edges[i + 1]) / 2), from: h.edges[i], to: h.edges[i + 1], pct: (c / total) * 100 }));
  const th = threshold != null ? data.find((d) => threshold >= d.from && threshold <= d.to)?.x : undefined;
  return (
    <div className="h-52" role="img" aria-label={`Histogram of ${label} across all runs`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} barCategoryGap={1}>
          <CartesianGrid vertical={false} stroke="rgba(148,163,184,0.12)" />
          <XAxis dataKey="x" tick={axis} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={28} />
          <YAxis hide />
          <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} contentStyle={tip} formatter={(v) => [`${Number(v).toFixed(2)}% of runs`, ""]} labelFormatter={(l) => `≈ ${l}`} />
          {th && <ReferenceLine x={th} stroke="#22d3ee" strokeDasharray="4 3" label={{ value: `threshold ${fmt(threshold!)}`, fill: "#22d3ee", fontSize: 10, position: "top" }} />}
          <Bar dataKey="pct" fill="#8055f6" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function Convergence({ c, label }: { c: SimOutput["convergence"]; label: string }) {
  return (
    <div className="h-40" role="img" aria-label={`Running mean of ${label} as runs accumulate`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={c}>
          <CartesianGrid vertical={false} stroke="rgba(148,163,184,0.12)" />
          <XAxis dataKey="n" tick={axis} axisLine={false} tickLine={false} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : v)} />
          <YAxis domain={["auto", "auto"]} tick={axis} axisLine={false} tickLine={false} width={48} tickFormatter={fmt} />
          <Tooltip contentStyle={tip} formatter={(v) => [fmt(Number(v)), "running mean"]} labelFormatter={(l) => `after ${Number(l).toLocaleString()} runs`} />
          <Line type="monotone" dataKey="mean" stroke="#22d3ee" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function SensitivityBars({ s }: { s: SimOutput["sensitivity"] }) {
  return (
    <ul className="space-y-1.5">
      {s.map((x) => (
        <li key={x.variable} className="grid grid-cols-[7rem_1fr_3.5rem] items-center gap-2 text-sm">
          <span className="truncate font-mono text-xs">{x.variable}</span>
          <div className="relative h-3 rounded bg-white/5" role="img" aria-label={`${x.variable}: rank correlation ${x.spearman.toFixed(2)}`}>
            <div className="absolute inset-y-0 left-1/2 w-px bg-line" />
            <div
              className={`absolute inset-y-0 rounded ${x.spearman >= 0 ? "bg-primary" : "bg-cyan"}`}
              style={x.spearman >= 0 ? { left: "50%", width: `${Math.abs(x.spearman) * 50}%` } : { right: "50%", width: `${Math.abs(x.spearman) * 50}%` }}
            />
          </div>
          <span className="text-right font-mono text-xs">{x.spearman >= 0 ? "+" : ""}{x.spearman.toFixed(2)}</span>
        </li>
      ))}
    </ul>
  );
}

/** Deterministic summary assembled from computed numbers only. */
export function summary(name: string, o: SimOutput, n: number, seed: number): string {
  const s = o.stats;
  let t = `Across ${n.toLocaleString()} runs (seed ${seed}), ${name} averaged ${fmt(s.mean)} (95% CI ${fmt(s.ci95_mean[0])} to ${fmt(s.ci95_mean[1])}). The middle 90% of outcomes lie between ${fmt(s.p05)} and ${fmt(s.p95)}.`;
  if (o.prob_above) t += ` ${name} exceeded ${fmt(o.prob_above.threshold)} in ${(o.prob_above.p * 100).toFixed(1)}% of runs (±${(o.prob_above.se * 100).toFixed(1)} points standard error).`;
  const top = o.sensitivity[0];
  if (top && Math.abs(top.spearman) > 0.1) t += ` The input most associated with ${name} is ${top.variable} (rank correlation ${top.spearman >= 0 ? "+" : ""}${top.spearman.toFixed(2)}).`;
  return t;
}

export function OutputCard({ name, o, adv, n, seed, threshold }: { name: string; o: SimOutput; adv: boolean; n: number; seed: number; threshold?: number | null }) {
  const s = o.stats;
  const tiles: [string, string][] = [["Mean", fmt(s.mean)], ["Median", fmt(s.p50)], ["5th – 95th pct", `${fmt(s.p05)} – ${fmt(s.p95)}`]];
  if (o.prob_above) tiles.push([`P(> ${fmt(o.prob_above.threshold)})`, `${(o.prob_above.p * 100).toFixed(1)}%`]);
  return (
    <Panel title={name} badge={<span className="font-mono text-[11px] text-muted">{o.expr}</span>}>
      <dl className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {tiles.map(([k, v]) => (
          <div key={k} className="rounded-xl border border-line bg-card/60 p-3"><dt className="text-[11px] text-muted">{k}</dt><dd className="font-mono text-lg font-bold">{v}</dd></div>
        ))}
      </dl>
      <Histogram h={o.histogram} threshold={threshold ?? o.prob_above?.threshold} label={name} />
      <p className="mt-2 text-sm leading-relaxed text-muted">{summary(name, o, n, seed)}</p>
      {adv && (
        <div className="mt-4 space-y-4 border-t border-line pt-4">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] text-sm">
              <caption className="sr-only">Distribution statistics for {name}</caption>
              <thead><tr className="text-left text-[11px] text-muted">{["Min", "5%", "25%", "50%", "75%", "95%", "Max", "Std dev", "SE of mean"].map((h) => <th key={h} scope="col" className="pr-2 font-normal">{h}</th>)}</tr></thead>
              <tbody className="font-mono"><tr>{[s.min, s.p05, s.p25, s.p50, s.p75, s.p95, s.max, s.sd, s.se_mean].map((v, i) => <td key={i} className="pr-2">{fmt(v)}</td>)}</tr></tbody>
            </table>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div><h3 className="mb-2 text-sm font-semibold">Sensitivity <span className="font-normal text-muted">(Spearman rank correlation)</span></h3><SensitivityBars s={o.sensitivity} />
              <p className="mt-2 text-[11px] text-muted">Association, not causation. Inputs are drawn independently.</p></div>
            <div><h3 className="mb-1 text-sm font-semibold">Convergence <span className="font-normal text-muted">(running mean)</span></h3><Convergence c={o.convergence} label={name} /></div>
          </div>
        </div>
      )}
    </Panel>
  );
}

export function Provenance({ r }: { r: SimResult }) {
  const row = (k: string, v: string) => <div key={k} className="flex justify-between gap-3"><dt className="text-muted">{k}</dt><dd className="truncate text-right font-mono">{v}</dd></div>;
  return (
    <Panel title="Provenance" badge={<Badge tone="green">Reproducible</Badge>}>
      <dl className="grid gap-x-8 gap-y-1 text-xs sm:grid-cols-2">
        {row("Seed", String(r.seed))}{row("Iterations", r.iterations.toLocaleString())}{row("Engine", `monte-carlo ${r.engine_version}`)}{row("Python", r.python_version)}
        {row("Runtime", `${r.runtime_ms} ms`)}{row("Result hash", r.result_hash.slice(0, 20) + "…")}
      </dl>
      <h3 className="mb-1 mt-4 text-sm font-semibold">Input variables as drawn</h3>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-xs">
          <thead><tr className="text-left text-muted"><th scope="col" className="font-normal">Variable</th><th scope="col" className="font-normal">Distribution</th><th scope="col" className="font-normal">Mean</th><th scope="col" className="font-normal">Std dev</th><th scope="col" className="font-normal">Range</th></tr></thead>
          <tbody>{Object.entries(r.inputs).map(([k, v]) => (
            <tr key={k} className="border-t border-line"><td className="py-1 font-mono">{k}</td><td>{String(v.dist.type)}</td><td className="font-mono">{fmt(v.realised_mean)}</td><td className="font-mono">{fmt(v.realised_sd)}</td><td className="font-mono">{fmt(v.realised_min)} – {fmt(v.realised_max)}</td></tr>
          ))}</tbody>
        </table>
      </div>
      <p className="mt-3 text-[11px] leading-relaxed text-muted">The same seed and configuration reproduce these draws exactly on the same Python version. Results describe the entered assumptions, not a forecast of real outcomes.</p>
    </Panel>
  );
}
