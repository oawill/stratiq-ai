"use client";

import { useMemo } from "react";
import { Loader2, Plus, X } from "lucide-react";
import type { PolPolicy } from "@/lib/types";
import { Badge, ErrorPanel, Panel } from "../ui";
import { SaveBar, field, num, pc, useAnalysis } from "./shared";

export interface PolicyDraft {
  alts: string[];
  criteria: { name: string; weight: string; direction: "benefit" | "cost" }[];
  scores: string[][]; // scores[alt][criterion]
  seed: string;
}

// Illustrative numbers only: they exist to show how the method works, not to describe any real policy.
export const defaultPolicy = (): PolicyDraft => ({
  alts: ["Option A", "Option B", "Option C", "Option D"],
  criteria: [
    { name: "Cost to taxpayers ($m)", weight: "3", direction: "cost" },
    { name: "Benefit to target group (index)", weight: "4", direction: "benefit" },
    { name: "Months to implement", weight: "2", direction: "cost" },
    { name: "Stakeholder acceptance (1–10, assumed)", weight: "2", direction: "benefit" },
  ],
  scores: [["120", "70", "18", "6"], ["80", "55", "10", "8"], ["200", "90", "24", "4"], ["60", "40", "6", "7"]],
  seed: "",
});

export function policyBody(d: PolicyDraft) {
  const scores = d.scores.map((r) => r.map(num));
  const criteria = d.criteria.map((c) => ({ name: c.name.trim(), weight: num(c.weight), direction: c.direction }));
  const alts = d.alts.map((a) => a.trim());
  if (alts.some((a) => !a) || new Set(alts).size !== alts.length) return null;
  if (criteria.some((c) => !c.name || !(c.weight >= 0)) || new Set(criteria.map((c) => c.name)).size !== criteria.length) return null;
  if (criteria.reduce((a, c) => a + c.weight, 0) <= 0) return null;
  if (scores.some((r) => r.some((x) => !Number.isFinite(x)))) return null;
  const seed = d.seed.trim() === "" ? undefined : num(d.seed);
  if (seed !== undefined && !(Number.isInteger(seed) && seed >= 0 && seed < 2 ** 31)) return null;
  return { alternatives: alts, criteria, scores, seed: seed ?? null, samples: 5000 };
}

function problem(d: PolicyDraft): string | null {
  const alts = d.alts.map((a) => a.trim());
  if (alts.some((a) => !a)) return "Name every alternative.";
  if (new Set(alts).size !== alts.length) return "Alternative names must be different.";
  const names = d.criteria.map((c) => c.name.trim());
  if (names.some((n) => !n)) return "Name every criterion.";
  if (new Set(names).size !== names.length) return "Criterion names must be different.";
  if (d.criteria.some((c) => !(num(c.weight) >= 0))) return "Weights must be numbers of at least 0.";
  if (d.criteria.reduce((a, c) => a + num(c.weight), 0) <= 0) return "At least one weight must be above 0.";
  if (d.scores.some((r) => r.some((x) => !Number.isFinite(num(x))))) return "Every score must be a number.";
  if (d.seed.trim() !== "" && !(Number.isInteger(num(d.seed)) && num(d.seed) >= 0)) return "Seed must be a whole number or empty.";
  return null;
}

export function PolicyTool({ d, set, adv, onSaved }: { d: PolicyDraft; set: (d: PolicyDraft) => void; adv: boolean; onSaved: () => void }) {
  const body = useMemo(() => policyBody(d), [d]);
  const prob = problem(d);
  const a = useAnalysis<PolPolicy>("politics/policy", prob ? null : body);
  const setScore = (i: number, k: number, v: string) => set({ ...d, scores: d.scores.map((r, x) => (x === i ? r.map((c, y) => (y === k ? v : c)) : r)) });
  const setCrit = (k: number, v: Partial<PolicyDraft["criteria"][number]>) => set({ ...d, criteria: d.criteria.map((c, j) => (j === k ? { ...c, ...v } : c)) });
  const addAlt = () => set({ ...d, alts: [...d.alts, `Option ${d.alts.length + 1}`], scores: [...d.scores, d.criteria.map(() => "0")] });
  const addCrit = () => set({ ...d, criteria: [...d.criteria, { name: `Criterion ${d.criteria.length + 1}`, weight: "1", direction: "benefit" }], scores: d.scores.map((r) => [...r, "0"]) });
  const delAlt = (i: number) => set({ ...d, alts: d.alts.filter((_, j) => j !== i), scores: d.scores.filter((_, j) => j !== i) });
  const delCrit = (k: number) => set({ ...d, criteria: d.criteria.filter((_, j) => j !== k), scores: d.scores.map((r) => r.filter((_, j) => j !== k)) });
  const res = a.data;
  const byRank = res ? [...res.alternatives].sort((x, y) => x.rank - y.rank) : [];
  return (
    <div className="space-y-4">
      <Panel title="1 · Alternatives, criteria and weights" badge={<Badge tone="amber">Weights are value judgements</Badge>}>
        <p className="mb-3 text-xs leading-relaxed text-muted">Score each alternative on each criterion in its own units. Mark whether more is better (<em>benefit</em>) or worse (<em>cost</em>). Weights say how much each criterion matters to you; the tool shows how sensitive the ranking is to them. Starting values are illustrative.</p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <caption className="sr-only">Criteria, weights, and scores for each alternative</caption>
            <thead>
              <tr className="align-bottom text-left text-[11px] text-muted">
                <th scope="col" className="font-normal">Alternative</th>
                {d.criteria.map((c, k) => (
                  <th key={k} scope="col" className="min-w-36 pr-2 font-normal">
                    <div className="flex items-center gap-1"><input aria-label={`Criterion ${k + 1} name`} value={c.name} maxLength={60} onChange={(e) => setCrit(k, { name: e.target.value })} className={`${field} w-full text-xs font-semibold text-ink`} />
                      {d.criteria.length > 2 && <button type="button" aria-label={`Remove criterion ${c.name}`} onClick={() => delCrit(k)} className="rounded p-1 hover:text-red-300"><X className="h-3 w-3" /></button>}</div>
                    <div className="mt-1 flex gap-1">
                      <input aria-label={`${c.name} weight`} inputMode="decimal" value={c.weight} onChange={(e) => setCrit(k, { weight: e.target.value })} className={`${field} w-14 font-mono`} />
                      <select aria-label={`${c.name} direction`} value={c.direction} onChange={(e) => setCrit(k, { direction: e.target.value as "benefit" | "cost" })} className={`${field} flex-1 text-xs`}><option value="benefit">more is better</option><option value="cost">less is better</option></select>
                    </div>
                  </th>
                ))}
                <th />
              </tr>
            </thead>
            <tbody>
              {d.alts.map((alt, i) => (
                <tr key={i}>
                  <th scope="row" className="pr-2 pt-1"><input aria-label={`Alternative ${i + 1} name`} value={alt} maxLength={60} onChange={(e) => set({ ...d, alts: d.alts.map((x, j) => (j === i ? e.target.value : x)) })} className={`${field} w-full font-semibold`} /></th>
                  {d.criteria.map((c, k) => <td key={k} className="pr-2 pt-1"><input aria-label={`${alt}: ${c.name}`} inputMode="decimal" value={d.scores[i][k]} onChange={(e) => setScore(i, k, e.target.value)} className={`${field} w-full font-mono`} /></td>)}
                  <td className="pt-1">{d.alts.length > 2 && <button type="button" aria-label={`Remove ${alt}`} onClick={() => delAlt(i)} className="rounded p-1.5 text-muted hover:text-red-300"><X className="h-4 w-4" /></button>}</td>
                </tr>))}
            </tbody>
          </table>
        </div>
        <div className="mt-2 flex gap-2">
          {d.alts.length < 12 && <button type="button" onClick={addAlt} className="inline-flex items-center gap-1 rounded-lg border border-dashed border-line px-3 py-1.5 text-xs text-muted hover:text-ink"><Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add alternative</button>}
          {d.criteria.length < 12 && <button type="button" onClick={addCrit} className="inline-flex items-center gap-1 rounded-lg border border-dashed border-line px-3 py-1.5 text-xs text-muted hover:text-ink"><Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add criterion</button>}
        </div>
      </Panel>

      <Panel title="2 · Ranking and trade-offs" badge={<Badge tone="green">Deterministic</Badge>}>
        <div aria-live="polite">
          {prob ? <p className="text-sm text-amber-300">{prob}</p>
            : a.loading ? <p className="flex items-center gap-2 text-sm text-muted"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Calculating…</p>
            : a.error ? <ErrorPanel message={a.error} />
            : res && (
              <div className="space-y-4">
                <ol className="space-y-2">
                  {byRank.map((x) => (
                    <li key={x.name} className="rounded-xl border border-line bg-card/40 p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-sm text-muted">#{x.rank}</span><span className="font-semibold">{x.name}</span>
                        {x.pareto_optimal ? <Badge tone="green">Pareto-optimal</Badge> : <Badge tone="muted">Dominated</Badge>}
                        <span className="ml-auto font-mono text-sm">{x.weighted_score.toFixed(3)}</span>
                      </div>
                      <div className="mt-2 h-2 overflow-hidden rounded bg-white/10" role="img" aria-label={`${x.name}: weighted score ${x.weighted_score.toFixed(3)} of 1`}><div className="h-full bg-primary" style={{ width: `${x.weighted_score * 100}%` }} /></div>
                      {adv && <div className="mt-2 text-[11px] text-muted">Normalised (0–1, higher is better): {x.normalised.map((v, k) => `${d.criteria[k].name.split(" (")[0]} ${v.toFixed(2)}`).join(" · ")}</div>}
                    </li>))}
                </ol>
                <p className="text-xs leading-relaxed text-muted">Pareto-optimal means no other alternative is at least as good on every criterion and better on one: it can only be rejected by weighing criteria against each other, which is a value judgement. {res.notes[0]}</p>
                {adv && (
                  <div className="space-y-4 border-t border-line pt-4">
                    <div>
                      <h3 className="mb-1 text-sm font-semibold">How stable is the ranking? <span className="font-normal text-muted">(exact, one weight at a time)</span></h3>
                      <ul className="space-y-2 text-sm">
                        {res.weight_sensitivity.map((s) => (
                          <li key={s.criterion} className="rounded-lg border border-line p-2">
                            <div className="font-semibold">{s.criterion} <span className="font-mono text-xs font-normal text-muted">(now {pc(s.current_weight, 0)} of total weight)</span></div>
                            {s.note ? <p className="text-xs text-muted">{s.note}</p> : (
                              <>
                                <div className="mt-1 flex h-5 overflow-hidden rounded border border-line" role="img" aria-label={`Top-ranked alternative as the weight of ${s.criterion} varies from 0 to 100 percent`}>
                                  {s.segments.map((g, i) => <div key={i} style={{ width: `${(g.to - g.from) * 100}%` }} title={`${pc(g.from, 1)}–${pc(g.to, 1)}: ${g.top.join(" / ")}`} className={`flex items-center justify-center overflow-hidden px-1 text-[10px] font-semibold ${i % 2 ? "bg-primary/30" : "bg-cyan/25"}`}>{g.top.join("/")}</div>)}
                                </div>
                                <p className="mt-1 text-[11px] text-muted">{s.segments.map((g) => `${pc(g.from, 1)}–${pc(g.to, 1)}: ${g.top.join(" / ")}`).join("  ·  ")}{s.stable_range && ` — the current top choice holds for weights between ${pc(s.stable_range[0], 1)} and ${pc(s.stable_range[1], 1)}.`}</p>
                              </>)}
                          </li>))}
                      </ul>
                    </div>
                    <div>
                      <h3 className="mb-1 text-sm font-semibold">Rank acceptability <span className="font-normal text-muted">({res.samples.toLocaleString()} random weight sets, seed {res.seed})</span></h3>
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[420px] text-sm"><caption className="sr-only">Probability of each rank across random weights</caption>
                          <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="font-normal">Alternative</th>{res.alternatives.map((_, r) => <th key={r} scope="col" className="font-normal">Rank {r + 1}</th>)}<th scope="col" className="font-normal">Expected</th></tr></thead>
                          <tbody className="font-mono">{byRank.map((x) => <tr key={x.name} className="border-t border-line"><td className="py-1 font-sans font-semibold">{x.name}</td>{x.rank_probabilities.map((p, r) => <td key={r} style={{ background: `rgba(128,85,246,${p * 0.7})` }} className="px-1">{pc(p, 0)}</td>)}<td>{x.expected_rank.toFixed(2)}</td></tr>)}</tbody></table>
                      </div>
                      <p className="mt-1 text-[11px] text-muted">Weights drawn uniformly from all possible weightings. An alternative that ranks first under many weightings is a robust choice; one that wins only under a narrow set of weights depends on a specific value judgement.</p>
                    </div>
                    <div className="max-w-xs"><label htmlFor="p-seed" className="mb-1 block text-xs text-muted">Seed for random weights (empty = random)</label><input id="p-seed" inputMode="numeric" value={d.seed} onChange={(e) => set({ ...d, seed: e.target.value })} className={`${field} w-full font-mono`} /></div>
                  </div>
                )}
                {!adv && <p className="text-xs text-muted">Turn on <strong>Advanced analytics</strong> for weight-stability analysis and rank acceptability.</p>}
              </div>)}
        </div>
      </Panel>
      <Panel title="Save this scenario"><SaveBar kind="policy" inputs={body} valid={!!body && !prob && !a.error} onSaved={onSaved} /></Panel>
    </div>
  );
}
