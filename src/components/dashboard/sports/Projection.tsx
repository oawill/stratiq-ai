"use client";

import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SportsInputs, SportsOutputs } from "@/lib/types";
import { pct } from "../ui";

export function Outcomes({ o, home, away }: { o: SportsOutputs; home: string; away: string }) {
  const rows = [
    { k: "Home win", name: home, v: o.p_home, c: "#8055f6" },
    { k: "Draw", name: "Draw", v: o.p_draw, c: "#94a3b8" },
    { k: "Away win", name: away, v: o.p_away, c: "#22d3ee" },
  ];
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full" role="img" aria-label={`Home ${pct(o.p_home)}, draw ${pct(o.p_draw)}, away ${pct(o.p_away)}`}>
        {rows.map((r) => <div key={r.k} style={{ width: `${r.v * 100}%`, background: r.c }} className="transition-all duration-500" />)}
      </div>
      <dl className="mt-4 grid grid-cols-3 gap-3 text-center">
        {rows.map((r) => (
          <div key={r.k} className="rounded-xl border border-line bg-card/60 p-3">
            <dt className="truncate text-[11px] text-muted">{r.k}</dt>
            <dd className="font-mono text-2xl font-bold" style={{ color: r.c }}>{pct(r.v)}</dd>
            <div className="truncate text-[10px] text-muted">{r.name}</div>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function GoalsChart({ grid, home, away }: { grid: number[][]; home: string; away: string }) {
  const n = grid.length;
  const data = Array.from({ length: n }, (_, k) => ({
    k,
    home: +(grid[k].reduce((a, b) => a + b, 0) * 100).toFixed(1),
    away: +(grid.reduce((a, r) => a + r[k], 0) * 100).toFixed(1),
  }));
  return (
    <div className="h-44" role="img" aria-label="Probability of each goal count for both teams">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <XAxis dataKey="k" tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis hide />
          <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} contentStyle={{ background: "#17213a", border: "1px solid #334155", borderRadius: 8 }} formatter={(v) => `${v}%`} labelFormatter={(l) => `${l} goals`} />
          <Bar dataKey="home" name={home} fill="#8055f6" radius={[4, 4, 0, 0]} />
          <Bar dataKey="away" name={away} fill="#22d3ee" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Heatmap({ grid, home, away }: { grid: number[][]; home: string; away: string }) {
  const max = Math.max(...grid.flat());
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[320px] border-separate border-spacing-0.5 text-center text-[11px]">
        <caption className="sr-only">Probability of each scoreline. Rows are {home} goals, columns are {away} goals.</caption>
        <thead>
          <tr>
            <th scope="col" className="text-[10px] font-normal text-muted">H＼A</th>
            {grid[0].map((_, a) => <th key={a} scope="col" className="font-mono font-normal text-muted">{a}</th>)}
          </tr>
        </thead>
        <tbody>
          {grid.map((row, h) => (
            <tr key={h}>
              <th scope="row" className="font-mono font-normal text-muted">{h}</th>
              {row.map((p, a) => (
                <td key={a} title={`${home} ${h} – ${a} ${away}: ${pct(p, 2)}`} className="rounded font-mono" style={{ background: `rgba(128,85,246,${0.06 + (p / max) * 0.8})`, padding: "5px 0" }}>
                  {p >= 0.001 ? (p * 100).toFixed(1) : "·"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-[10px] text-muted">Cells show % probability. Rows: {home} goals · Columns: {away} goals · grid shown to 6 goals.</p>
    </div>
  );
}

export function RatingsTable({ i, home, away }: { i: SportsInputs; home: string; away: string }) {
  return (
    <table className="w-full text-sm">
      <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="py-1 font-normal">Team</th><th scope="col" className="font-normal">Attack ×</th><th scope="col" className="font-normal">Defence ×</th><th scope="col" className="font-normal">Matches</th></tr></thead>
      <tbody className="font-mono">
        <tr><td className="py-1 font-sans">{home}</td><td>{i.home_attack.toFixed(3)}</td><td>{i.home_defence.toFixed(3)}</td><td>{i.home_team_matches}</td></tr>
        <tr><td className="py-1 font-sans">{away}</td><td>{i.away_attack.toFixed(3)}</td><td>{i.away_defence.toFixed(3)}</td><td>{i.away_team_matches}</td></tr>
      </tbody>
    </table>
  );
}

export function Plain({ o, home, away, retrospective }: { o: SportsOutputs; home: string; away: string; retrospective?: boolean }) {
  const lead = o.p_home >= o.p_away ? home : away;
  const leadP = Math.max(o.p_home, o.p_away);
  return (
    <p className="text-sm leading-relaxed text-muted">
      {retrospective ? "Using only matches played before kickoff, the" : "The"} model gives {lead} the higher chance of winning ({pct(leadP)}), with a draw at {pct(o.p_draw)}.
      Expected goals are {o.home_xg.toFixed(2)} for {home} and {o.away_xg.toFixed(2)} for {away}. These are probabilities under stated assumptions, not a
      prediction of the result: even the favourite fails to win about {Math.round((1 - leadP) * 10)} times in 10.
    </p>
  );
}
