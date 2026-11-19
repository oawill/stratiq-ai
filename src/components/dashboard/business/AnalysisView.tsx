"use client";

import type { Dominance, GameAnalysis } from "@/lib/types";
import { Badge } from "../ui";

export interface GameDef {
  players: [string, string];
  rows: string[];
  cols: string[];
  payoffs: number[][][];
}

const num = (n: number) => (Number.isInteger(n) ? String(n) : String(+n.toFixed(4)));

/** Deterministic plain-language summary built from solver output only (no model-written numbers). */
export function summarise(g: GameDef, a: GameAnalysis): string[] {
  const [P, Q] = g.players;
  const out: string[] = [];
  if (a.pure_nash.length === 0) {
    out.push("No outcome is stable under pure strategies: at every cell at least one player gains by switching.");
  } else if (a.pure_nash.length === 1) {
    const n = a.pure_nash[0];
    out.push(
      `The only pure Nash equilibrium is ${P}: ${g.rows[n.row]} and ${Q}: ${g.cols[n.col]} (payoffs ${num(n.payoffs[0])} and ${num(n.payoffs[1])}). Neither player can do better by changing only their own choice.`,
    );
  } else {
    out.push(
      `There are ${a.pure_nash.length} pure Nash equilibria: ${a.pure_nash.map((n) => `(${g.rows[n.row]}, ${g.cols[n.col]})`).join(", ")}. The matrix alone does not say which one will occur.`,
    );
  }
  const d = a.dominance;
  if (d.row.strictly_dominant !== null) out.push(`${g.rows[d.row.strictly_dominant]} is a strictly dominant strategy for ${P}: it is best whatever ${Q} does.`);
  if (d.col.strictly_dominant !== null) out.push(`${g.cols[d.col.strictly_dominant]} is a strictly dominant strategy for ${Q}: it is best whatever ${P} does.`);
  if (a.mixed_2x2) {
    out.push(
      `A mixed equilibrium also exists: ${P} plays ${g.rows[0]} with probability ${a.mixed_2x2.row_probs_exact[0]} and ${Q} plays ${g.cols[0]} with probability ${a.mixed_2x2.col_probs_exact[0]}.`,
    );
  }
  for (const n of a.notes) if (!n.startsWith("No pure-strategy")) out.push(n);
  return out;
}

function domText(g: GameDef, who: "row" | "col", d: Dominance) {
  const names = who === "row" ? g.rows : g.cols;
  const lines: string[] = [];
  if (d.strictly_dominant !== null) lines.push(`Strictly dominant: ${names[d.strictly_dominant]}`);
  else if (d.weakly_dominant !== null) lines.push(`Weakly dominant: ${names[d.weakly_dominant]}`);
  else lines.push("No dominant strategy");
  for (const x of d.strictly_dominated) lines.push(`${names[x.strategy]} is strictly dominated by ${names[x.by]}`);
  for (const x of d.weakly_dominated) lines.push(`${names[x.strategy]} is weakly dominated by ${names[x.by]}`);
  return lines;
}

export function PayoffMatrix({ g, a, showBR }: { g: GameDef; a: GameAnalysis; showBR: boolean }) {
  const isNash = (r: number, c: number) => a.pure_nash.some((n) => n.row === r && n.col === c);
  const rowBR = (r: number, c: number) => a.best_responses.row_to_col[c].includes(r);
  const colBR = (r: number, c: number) => a.best_responses.col_to_row[r].includes(c);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[360px] border-separate border-spacing-1 text-center text-sm">
        <caption className="sr-only">Payoff matrix. Each cell lists {g.players[0]}&apos;s payoff then {g.players[1]}&apos;s payoff.</caption>
        <thead>
          <tr>
            <th scope="col" className="text-[11px] font-normal text-muted">{g.players[0]} ↓ / {g.players[1]} →</th>
            {g.cols.map((c) => <th key={c} scope="col" className="px-1 pb-1 font-semibold">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {g.rows.map((r, ri) => (
            <tr key={r}>
              <th scope="row" className="pr-2 text-right font-semibold">{r}</th>
              {g.cols.map((c, ci) => {
                const p = g.payoffs[ri][ci];
                const nash = isNash(ri, ci);
                return (
                  <td
                    key={c}
                    aria-label={`${g.players[0]} plays ${r}, ${g.players[1]} plays ${c}: payoffs ${num(p[0])} and ${num(p[1])}${nash ? ", Nash equilibrium" : ""}`}
                    className={`rounded-lg border px-2 py-2.5 font-mono ${nash ? "border-success bg-success/15" : "border-line bg-card/50"}`}
                  >
                    <span className={showBR && rowBR(ri, ci) ? "font-bold text-violet underline decoration-2 underline-offset-4" : ""}>{num(p[0])}</span>
                    <span className="text-muted">, </span>
                    <span className={showBR && colBR(ri, ci) ? "font-bold text-cyan underline decoration-2 underline-offset-4" : ""}>{num(p[1])}</span>
                    {nash && <div className="mt-0.5 font-sans text-[10px] font-semibold uppercase tracking-wide text-success">Nash</div>}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {showBR && (
        <p className="mt-1 text-[11px] text-muted">
          <span className="font-bold text-violet underline decoration-2 underline-offset-4">Underlined</span> {g.players[0]} payoff = {g.players[0]}&apos;s best response to that column ·{" "}
          <span className="font-bold text-cyan underline decoration-2 underline-offset-4">underlined</span> {g.players[1]} payoff = {g.players[1]}&apos;s best response to that row. A Nash equilibrium has both underlined.
        </p>
      )}
    </div>
  );
}

export function AnalysisView({ g, a, adv }: { g: GameDef; a: GameAnalysis; adv: boolean }) {
  const ie = a.iterated_elimination;
  return (
    <div className="space-y-4">
      <PayoffMatrix g={g} a={a} showBR={adv} />
      <ul className="space-y-1.5 rounded-xl border border-line bg-bg/50 p-3 text-sm leading-relaxed">
        {summarise(g, a).map((t) => <li key={t}>{t}</li>)}
      </ul>
      {adv && (
        <div className="space-y-4 border-t border-line pt-4">
          <div className="grid gap-3 sm:grid-cols-2">
            {(["row", "col"] as const).map((who, i) => (
              <div key={who} className="rounded-xl border border-line p-3">
                <h3 className="mb-1 text-sm font-semibold">Dominance · {g.players[i]}</h3>
                <ul className="space-y-0.5 text-sm text-muted">{domText(g, who, a.dominance[who]).map((l) => <li key={l}>{l}</li>)}</ul>
              </div>
            ))}
          </div>
          <div className="rounded-xl border border-line p-3">
            <h3 className="mb-1 text-sm font-semibold">Iterated elimination of strictly dominated strategies</h3>
            {ie.steps.length === 0 ? <p className="text-sm text-muted">No strategy is strictly dominated, so nothing is eliminated.</p> : (
              <ol className="list-decimal space-y-0.5 pl-5 text-sm text-muted">
                {ie.steps.map((s, i) => (
                  <li key={i}>
                    {s.player === "row" ? `${g.players[0]}: ${g.rows[s.eliminated]}` : `${g.players[1]}: ${g.cols[s.eliminated]}`} is eliminated (dominated by {s.player === "row" ? g.rows[s.by] : g.cols[s.by]})
                  </li>
                ))}
              </ol>
            )}
            <p className="mt-2 text-xs text-muted">
              Survivors: {g.players[0]} → {ie.remaining_rows.map((r) => g.rows[r]).join(", ")} · {g.players[1]} → {ie.remaining_cols.map((c) => g.cols[c]).join(", ")}
            </p>
          </div>
          {a.mixed_2x2 && (
            <div className="rounded-xl border border-line p-3 text-sm">
              <h3 className="mb-1 text-sm font-semibold">Completely mixed equilibrium (2×2)</h3>
              <p className="text-muted">
                {g.players[0]}: {g.rows[0]} {a.mixed_2x2.row_probs_exact[0]} ({(a.mixed_2x2.row_probs[0] * 100).toFixed(1)}%), {g.rows[1]} {a.mixed_2x2.row_probs_exact[1]} ·{" "}
                {g.players[1]}: {g.cols[0]} {a.mixed_2x2.col_probs_exact[0]} ({(a.mixed_2x2.col_probs[0] * 100).toFixed(1)}%), {g.cols[1]} {a.mixed_2x2.col_probs_exact[1]}
              </p>
              <p className="mt-1 text-xs text-muted">Expected payoffs: {num(a.mixed_2x2.expected_payoffs[0])} and {num(a.mixed_2x2.expected_payoffs[1])}.</p>
            </div>
          )}
          <div className="rounded-xl border border-line p-3 text-sm">
            <h3 className="mb-1 text-sm font-semibold">Efficiency</h3>
            <p className="text-muted">
              Pareto-optimal outcomes: {a.pareto_optimal.map((c) => `(${g.rows[c.row]}, ${g.cols[c.col]})`).join(", ")}.<br />
              Highest combined payoff ({num(a.max_welfare.value)}): {a.max_welfare.cells.map((c) => `(${g.rows[c.row]}, ${g.cols[c.col]})`).join(", ")}.
            </p>
          </div>
        </div>
      )}
      {!adv && <p className="text-xs text-muted">Turn on <strong>Advanced analytics</strong> for best responses, dominance, elimination steps, mixed equilibrium, efficiency and sensitivity.</p>}
    </div>
  );
}

export function NashBadge({ n }: { n: number | null }) {
  if (n === null) return <Badge tone="muted">—</Badge>;
  return <Badge tone={n ? "green" : "amber"}>{n} pure Nash</Badge>;
}
