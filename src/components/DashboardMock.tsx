"use client";

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  Briefcase,
  Eye,
  FlaskConical,
  Landmark,
  LayoutGrid,
  LineChart,
} from "lucide-react";
import { buildDuopolyGame, pureNash } from "@/lib/game";
import { matchProbabilities } from "@/lib/poisson";

const SIDEBAR = [
  { label: "Overview", icon: LayoutGrid },
  { label: "Sports", icon: Activity },
  { label: "Strategy", icon: Briefcase },
  { label: "Politics", icon: Landmark },
  { label: "Markets", icon: LineChart },
  { label: "SimLab", icon: FlaskConical },
  { label: "Watchlists", icon: Eye },
];

const CARDS = [
  { name: "Sports", color: "#22d3ee", value: "3 scenarios", icon: Activity },
  { name: "Strategy", color: "#8055f6", value: "9 strategies", icon: Briefcase },
  { name: "Politics", color: "#a78bfa", value: "4 coalitions", icon: Landmark },
  { name: "Markets", color: "#10b981", value: "5 regimes", icon: LineChart },
];

export function DashboardMock() {
  const [active, setActive] = useState("Overview");
  const game = useMemo(() => buildDuopolyGame(), []);
  const ne = useMemo(() => pureNash(game), [game]);
  const [sel, setSel] = useState<{ r: number; c: number }>(ne[0] ? { r: ne[0].row, c: ne[0].col } : { r: 1, c: 1 });
  const m = useMemo(() => matchProbabilities(1.6, 1.1), []);

  const flat = game.payoffs.flat().map((p) => p[0]);
  const lo = Math.min(...flat);
  const hi = Math.max(...flat);
  const isNe = (r: number, c: number) => ne.some((n) => n.row === r && n.col === c);

  const probs = [
    { k: "Home", v: m.home, c: "#8055f6" },
    { k: "Draw", v: m.draw, c: "#94a3b8" },
    { k: "Away", v: m.away, c: "#22d3ee" },
  ];

  return (
    <div className="glass relative w-full overflow-hidden rounded-2xl shadow-[0_30px_80px_-20px_rgba(128,85,246,0.45)]">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <div className="flex gap-1.5" aria-hidden="true">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]/70" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]/70" />
        </div>
        <span className="rounded-full border border-cyan/40 bg-cyan/10 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-cyan">
          Demonstration data
        </span>
      </div>
      <div className="flex">
        <nav aria-label="Dashboard preview sections" className="hidden w-32 shrink-0 border-r border-line p-2 sm:block">
          {SIDEBAR.map((s) => (
            <button
              key={s.label}
              type="button"
              onClick={() => setActive(s.label)}
              aria-current={active === s.label}
              className={`mb-0.5 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] transition-colors ${
                active === s.label ? "bg-primary/20 text-ink" : "text-muted hover:bg-white/5"
              }`}
            >
              <s.icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {s.label}
            </button>
          ))}
        </nav>
        <div className="min-w-0 flex-1 space-y-3 p-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {CARDS.map((c) => (
              <div key={c.name} className="rounded-xl border border-line bg-card/70 p-2.5">
                <div className="flex items-center gap-1.5 text-[10px] text-muted">
                  <c.icon className="h-3 w-3" style={{ color: c.color }} aria-hidden="true" />
                  {c.name}
                </div>
                <div className="mt-1 text-sm font-bold">{c.value}</div>
                <svg viewBox="0 0 60 16" className="mt-1 h-4 w-full" aria-hidden="true">
                  <polyline
                    fill="none"
                    stroke={c.color}
                    strokeWidth="1.5"
                    points="0,12 10,9 20,11 30,5 40,7 50,3 60,5"
                  />
                </svg>
              </div>
            ))}
          </div>

          <div className="grid gap-3 md:grid-cols-5">
            <div className="rounded-xl border border-line bg-card/70 p-3 md:col-span-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-semibold">Game Theory Simulation</p>
                <span className="text-[10px] text-muted">Row payoff · hypothetical pricing</span>
              </div>
              <div className="grid grid-cols-[auto_repeat(3,1fr)] gap-1 text-[10px]">
                <span />
                {game.colLabels.map((l) => (
                  <span key={l} className="text-center text-muted">
                    B: {l.split(" ")[0]}
                  </span>
                ))}
                {game.payoffs.map((row, r) => (
                  <Row
                    key={r}
                    label={`A: ${game.rowLabels[r].split(" ")[0]}`}
                    cells={row.map((p, c) => {
                      const t = (p[0] - lo) / (hi - lo || 1);
                      return (
                        <button
                          key={c}
                          type="button"
                          onClick={() => setSel({ r, c })}
                          aria-label={`A ${game.rowLabels[r]}, B ${game.colLabels[c]}: A payoff ${p[0]}, B payoff ${p[1]}`}
                          className={`relative rounded-md py-2 text-center font-mono text-[11px] font-semibold transition-transform hover:scale-105 ${
                            sel.r === r && sel.c === c ? "ring-2 ring-cyan" : ""
                          }`}
                          style={{ background: `rgba(128,85,246,${0.12 + t * 0.7})` }}
                        >
                          {p[0]}
                          {isNe(r, c) && (
                            <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-success" title="Pure Nash equilibrium" />
                          )}
                        </button>
                      );
                    })}
                  />
                ))}
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-muted">
                A: {game.rowLabels[sel.r]} vs B: {game.colLabels[sel.c]} →{" "}
                <span className="font-mono text-ink">
                  {game.payoffs[sel.r][sel.c][0]} / {game.payoffs[sel.r][sel.c][1]}
                </span>
                {isNe(sel.r, sel.c) && <span className="text-success"> · pure Nash equilibrium</span>}
              </p>
            </div>

            <div className="rounded-xl border border-line bg-card/70 p-3 md:col-span-2">
              <p className="mb-0.5 text-xs font-semibold">Match Prediction</p>
              <p className="mb-2 text-[10px] text-muted">Team A vs Team B · fictional</p>
              <div className="space-y-2">
                {probs.map((p, i) => (
                  <div key={p.k}>
                    <div className="flex justify-between text-[10px]">
                      <span className="text-muted">{p.k}</span>
                      <span className="font-mono">{(p.v * 100).toFixed(1)}%</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-white/5">
                      <motion.div
                        className="h-full rounded-full"
                        style={{ background: p.c }}
                        initial={{ width: 0 }}
                        animate={{ width: `${p.v * 100}%` }}
                        transition={{ duration: 0.9, delay: 0.2 + i * 0.12 }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-[10px] text-muted">xG 1.6 – 1.1 · Poisson model</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ label, cells }: { label: string; cells: React.ReactNode[] }) {
  return (
    <>
      <span className="self-center pr-1 text-muted">{label}</span>
      {cells}
    </>
  );
}
