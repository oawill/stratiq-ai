"use client";

import { useMemo, useState } from "react";
import { bestResponseRow, buildDuopolyGame, DEFAULT_DUOPOLY, PRICE_LEVELS, pureNash } from "@/lib/game";

export function StrategyDemo() {
  const [unitCost, setUnitCost] = useState(DEFAULT_DUOPOLY.unitCost);
  const [sensitivity, setSensitivity] = useState(DEFAULT_DUOPOLY.sensitivity);
  const [a, setA] = useState(1);
  const [b, setB] = useState(1);

  const game = useMemo(
    () => buildDuopolyGame({ ...DEFAULT_DUOPOLY, unitCost, sensitivity }),
    [unitCost, sensitivity],
  );
  const ne = useMemo(() => pureNash(game), [game]);
  const isNe = (r: number, c: number) => ne.some((n) => n.row === r && n.col === c);
  const [pa, pb] = game.payoffs[a][b];
  const br = bestResponseRow(game, b);

  // Compare A's strategies against the chosen B response.
  const compare = game.payoffs.map((row, r) => ({ r, payoff: row[b][0] }));
  const maxPayoff = Math.max(...compare.map((c) => Math.abs(c.payoff)), 1);

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div>
        <p className="mb-4 rounded-lg border border-cyan/30 bg-cyan/10 px-3 py-2 text-xs font-semibold text-cyan">
          Hypothetical assumptions — an illustration of game theory, not a business forecast.
        </p>
        <h3 className="text-xl font-bold">Two-company pricing game</h3>

        <fieldset className="mt-5">
          <legend className="mb-2 text-sm text-muted">Company A pricing strategy</legend>
          <Choice name="a" value={a} set={setA} />
        </fieldset>
        <fieldset className="mt-4">
          <legend className="mb-2 text-sm text-muted">Company B response</legend>
          <Choice name="b" value={b} set={setB} />
        </fieldset>

        <div className="mt-5 grid grid-cols-2 gap-4">
          <NumSlider id="uc" label="Unit cost ($)" min={2} max={10} step={0.5} value={unitCost} set={setUnitCost} />
          <NumSlider id="sn" label="Price sensitivity" min={0.01} max={0.12} step={0.01} value={sensitivity} set={setSensitivity} />
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3 text-center">
          <div className="rounded-xl border border-line bg-card/70 p-3">
            <div className="text-[11px] text-muted">Company A profit</div>
            <div className="font-mono text-xl font-bold text-violet">${pa.toLocaleString()}</div>
          </div>
          <div className="rounded-xl border border-line bg-card/70 p-3">
            <div className="text-[11px] text-muted">Company B profit</div>
            <div className="font-mono text-xl font-bold text-cyan">${pb.toLocaleString()}</div>
          </div>
        </div>
        <p className="mt-3 text-xs text-muted">
          A&apos;s best response to B&apos;s &ldquo;{PRICE_LEVELS[b].label}&rdquo; price:{" "}
          <strong className="text-ink">{br.map((i) => PRICE_LEVELS[i].label).join(" / ")}</strong>.
        </p>
        <div className="mt-4 rounded-xl border border-line bg-bg/60 p-3 text-xs leading-relaxed text-muted">
          <strong className="text-ink">Model:</strong> A&apos;s market share = 0.5 + sensitivity × (p<sub>B</sub> − p<sub>A</sub>),
          clamped to [0,1]; total demand = 1000 × (1.6 − average price / 20); profit = quantity × (price −
          unit cost) − $1,500 fixed cost. All parameters are illustrative.
        </div>
      </div>

      <div className="space-y-4">
        <div className="overflow-x-auto rounded-xl border border-line bg-card/50 p-3">
          <h4 className="mb-2 text-sm font-semibold">Payoff matrix (A profit, B profit)</h4>
          <table className="w-full min-w-[420px] border-separate border-spacing-1 text-center text-xs">
            <caption className="sr-only">Payoff matrix, rows are Company A price, columns are Company B price</caption>
            <thead>
              <tr>
                <th scope="col" className="text-muted"><span className="sr-only">A \ B</span></th>
                {game.colLabels.map((l) => (
                  <th key={l} scope="col" className="pb-1 font-medium text-muted">B: {l}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {game.payoffs.map((row, r) => (
                <tr key={r}>
                  <th scope="row" className="pr-1 text-right font-medium text-muted">A: {game.rowLabels[r]}</th>
                  {row.map((p, c) => (
                    <td
                      key={c}
                      className={`rounded-lg px-1 py-2 font-mono ${
                        r === a && c === b ? "ring-2 ring-cyan" : ""
                      } ${isNe(r, c) ? "bg-success/20" : "bg-primary/10"}`}
                    >
                      {p[0].toLocaleString()} , {p[1].toLocaleString()}
                      {isNe(r, c) && <div className="text-[10px] font-semibold text-success">Nash</div>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-muted" aria-live="polite">
            {ne.length
              ? `Pure Nash equilibri${ne.length > 1 ? "a" : "um"}: ${ne
                  .map((n) => `A ${PRICE_LEVELS[n.row].label} / B ${PRICE_LEVELS[n.col].label}`)
                  .join("; ")}.`
              : "No pure-strategy Nash equilibrium under these assumptions (a mixed equilibrium would exist)."}
          </p>
        </div>

        <div className="rounded-xl border border-line bg-card/50 p-3">
          <h4 className="mb-3 text-sm font-semibold">Compare A&apos;s alternatives (vs B: {PRICE_LEVELS[b].label})</h4>
          <ul className="space-y-2">
            {compare.map((c) => (
              <li key={c.r}>
                <div className="flex justify-between text-xs">
                  <span className="text-muted">A: {PRICE_LEVELS[c.r].label}</span>
                  <span className="font-mono">${c.payoff.toLocaleString()}</span>
                </div>
                <div className="h-2 rounded-full bg-white/5">
                  <div
                    className="h-full rounded-full bg-primary transition-all duration-500"
                    style={{ width: `${Math.max(2, (Math.max(c.payoff, 0) / maxPayoff) * 100)}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function Choice({ name, value, set }: { name: string; value: number; set: (n: number) => void }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {PRICE_LEVELS.map((l, i) => (
        <label
          key={l.label}
          className={`cursor-pointer rounded-xl border px-3 py-2 text-center text-sm transition-colors has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-cyan ${
            value === i ? "border-primary bg-primary/20 text-ink" : "border-line text-muted hover:border-violet/50"
          }`}
        >
          <input type="radio" name={name} checked={value === i} onChange={() => set(i)} className="sr-only" />
          {l.label} <span className="font-mono text-xs">${l.price}</span>
        </label>
      ))}
    </div>
  );
}

function NumSlider(p: { id: string; label: string; min: number; max: number; step: number; value: number; set: (n: number) => void }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs">
        <label htmlFor={p.id} className="text-muted">{p.label}</label>
        <output htmlFor={p.id} className="font-mono">{p.value}</output>
      </div>
      <input id={p.id} type="range" min={p.min} max={p.max} step={p.step} value={p.value} onChange={(e) => p.set(parseFloat(e.target.value))} className="w-full cursor-pointer accent-[#8055f6]" />
    </div>
  );
}
