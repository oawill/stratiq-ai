"use client";

import { useMemo, useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { matchProbabilities, poissonPmf } from "@/lib/poisson";

export function SportsDemo() {
  const [homeXg, setHome] = useState(1.6);
  const [awayXg, setAway] = useState(1.1);
  const m = useMemo(() => matchProbabilities(homeXg, awayXg), [homeXg, awayXg]);

  const outcomes = [
    { name: "Team A win", p: m.home, c: "#8055f6" },
    { name: "Draw", p: m.draw, c: "#94a3b8" },
    { name: "Team B win", p: m.away, c: "#22d3ee" },
  ];
  const goals = Array.from({ length: 7 }, (_, k) => ({
    k,
    A: +(poissonPmf(k, homeXg) * 100).toFixed(1),
    B: +(poissonPmf(k, awayXg) * 100).toFixed(1),
  }));

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div>
        <p className="mb-4 rounded-lg border border-cyan/30 bg-cyan/10 px-3 py-2 text-xs font-semibold text-cyan">
          Interactive demonstration — not a live match prediction.
        </p>
        <h3 className="text-xl font-bold">Team A <span className="text-muted">vs</span> Team B</h3>
        <p className="text-xs text-muted">Fictional fixture.</p>

        <div className="mt-6 space-y-5">
          <Slider id="xg-a" label="Team A expected goals" value={homeXg} set={setHome} />
          <Slider id="xg-b" label="Team B expected goals" value={awayXg} set={setAway} />
        </div>

        <div className="mt-6 grid grid-cols-3 gap-3 text-center">
          {outcomes.map((o) => (
            <div key={o.name} className="rounded-xl border border-line bg-card/70 p-3">
              <div className="text-[11px] text-muted">{o.name}</div>
              <div className="font-mono text-xl font-bold" style={{ color: o.c }}>
                {(o.p * 100).toFixed(1)}%
              </div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-muted">
          Most likely scoreline: {m.mostLikely.home}–{m.mostLikely.away} (
          {(m.mostLikely.p * 100).toFixed(1)}%). Combined expected goals: {(homeXg + awayXg).toFixed(2)}.
        </p>
        <div className="mt-4 rounded-xl border border-line bg-bg/60 p-3 text-xs leading-relaxed text-muted">
          <strong className="text-ink">Model assumptions:</strong> goals for each team are independent
          Poisson variables with mean equal to the expected goals above; no home advantage, form,
          injuries, or correlation are modeled; probabilities are summed over a 0–10 goal grid and
          renormalised. P(k) = λ^k · e^(−λ) / k!
        </div>
      </div>

      <div className="space-y-4">
        <div className="rounded-xl border border-line bg-card/50 p-3">
          <h4 className="mb-1 text-sm font-semibold">Outcome probabilities</h4>
          <div className="h-40" role="img" aria-label={`Team A ${(m.home * 100).toFixed(1)} percent, draw ${(m.draw * 100).toFixed(1)} percent, Team B ${(m.away * 100).toFixed(1)} percent`}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={outcomes.map((o) => ({ name: o.name, p: +(o.p * 100).toFixed(1), c: o.c }))} layout="vertical" margin={{ left: 10, right: 20 }}>
                <XAxis type="number" domain={[0, 100]} hide />
                <YAxis type="category" dataKey="name" width={80} tick={{ fill: "#94a3b8", fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip cursor={false} contentStyle={{ background: "#17213a", border: "1px solid #334155", borderRadius: 8 }} formatter={(v) => `${v}%`} />
                <Bar dataKey="p" radius={6} isAnimationActive>
                  {outcomes.map((o) => (
                    <Cell key={o.name} fill={o.c} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="rounded-xl border border-line bg-card/50 p-3">
          <h4 className="mb-1 text-sm font-semibold">Goal distribution (% chance of exactly k goals)</h4>
          <div className="h-44" role="img" aria-label="Poisson goal distribution for both teams">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={goals}>
                <XAxis dataKey="k" tick={{ fill: "#94a3b8", fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis hide />
                <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} contentStyle={{ background: "#17213a", border: "1px solid #334155", borderRadius: 8 }} formatter={(v) => `${v}%`} />
                <Bar dataKey="A" name="Team A" fill="#8055f6" radius={[4, 4, 0, 0]} />
                <Bar dataKey="B" name="Team B" fill="#22d3ee" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}

function Slider({ id, label, value, set }: { id: string; label: string; value: number; set: (n: number) => void }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm">
        <label htmlFor={id} className="text-muted">{label}</label>
        <output htmlFor={id} className="font-mono font-semibold">{value.toFixed(2)}</output>
      </div>
      <input
        id={id}
        type="range"
        min={0.2}
        max={4}
        step={0.05}
        value={value}
        onChange={(e) => set(parseFloat(e.target.value))}
        className="h-2 w-full cursor-pointer accent-[#8055f6]"
      />
    </div>
  );
}
