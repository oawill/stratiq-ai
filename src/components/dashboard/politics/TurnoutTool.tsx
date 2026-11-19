"use client";

import { useMemo } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Loader2, Plus, X } from "lucide-react";
import type { PolTurnout } from "@/lib/types";
import { Badge, ErrorPanel, Panel } from "../ui";
import { SaveBar, field, num, pc, useAnalysis } from "./shared";

export interface TurnoutDraft {
  parties: string[];
  blocs: { name: string; electorate: string; turnout: string; prefs: string[] }[]; // turnout & prefs in percent
  method: "dhondt" | "sainte_lague" | "hare"; seats: string; threshold: string;
  sweepMode: "bloc" | "all_shift"; sweepBloc: number; lo: string; hi: string; // percent (bloc: turnout %, shift: percentage points)
}

export const defaultTurnout = (): TurnoutDraft => ({
  parties: ["Alpha", "Beta", "Gamma"],
  blocs: [
    { name: "Urban", electorate: "400000", turnout: "55", prefs: ["50", "30", "20"] },
    { name: "Suburban", electorate: "350000", turnout: "62", prefs: ["35", "40", "25"] },
    { name: "Rural", electorate: "250000", turnout: "70", prefs: ["20", "35", "45"] },
  ],
  method: "dhondt", seats: "60", threshold: "0", sweepMode: "bloc", sweepBloc: 0, lo: "30", hi: "90",
});

export function turnoutBody(d: TurnoutDraft) {
  const parties = d.parties.map((p) => p.trim());
  if (parties.some((p) => !p) || new Set(parties).size !== parties.length) return null;
  const blocs = [];
  for (const b of d.blocs) {
    const prefs = b.prefs.map((x) => num(x) / 100);
    const e = num(b.electorate), t = num(b.turnout) / 100;
    if (!b.name.trim() || !(e > 0) || !(t >= 0 && t <= 1) || prefs.some((x) => !(x >= 0))) return null;
    if (Math.abs(prefs.reduce((a, x) => a + x, 0) - 1) > 1e-6) return null;
    blocs.push({ name: b.name.trim(), electorate: e, turnout: t, prefs: Object.fromEntries(parties.map((p, i) => [p, prefs[i]])) });
  }
  if (new Set(blocs.map((b) => b.name)).size !== blocs.length) return null;
  const seats = num(d.seats), th = num(d.threshold) / 100, lo = num(d.lo) / 100, hi = num(d.hi) / 100;
  if (!Number.isInteger(seats) || seats < 1 || seats > 650 || !(th >= 0 && th < 1)) return null;
  const sweep = lo < hi && Number.isFinite(lo) && Number.isFinite(hi)
    ? { mode: d.sweepMode, bloc: d.sweepMode === "bloc" ? Math.min(d.sweepBloc, blocs.length - 1) : null, lo, hi } : null;
  if (!sweep) return null;
  return { parties, blocs, method: d.method, seats, threshold: th, sweep };
}

function prefProblem(d: TurnoutDraft): string | null {
  const parties = d.parties.map((p) => p.trim());
  if (parties.some((p) => !p)) return "Name every party.";
  if (new Set(parties).size !== parties.length) return "Party names must be different.";
  for (const b of d.blocs) {
    if (!b.name.trim()) return "Name every bloc.";
    if (!(num(b.electorate) > 0)) return `${b.name}: electorate must be a positive number.`;
    const t = num(b.turnout);
    if (!(t >= 0 && t <= 100)) return `${b.name}: turnout must be 0–100%.`;
    const ps = b.prefs.map(num);
    if (ps.some((x) => !(x >= 0))) return `${b.name}: preference shares must be numbers of at least 0.`;
    const s = ps.reduce((a, x) => a + x, 0);
    if (Math.abs(s - 100) > 1e-4) return `${b.name}: preference shares add up to ${s.toFixed(2)}%, not 100%. Use “Normalise”.`;
  }
  if (new Set(d.blocs.map((b) => b.name.trim())).size !== d.blocs.length) return "Bloc names must be different.";
  const lo = num(d.lo), hi = num(d.hi);
  if (!(lo < hi)) return "Sweep start must be below the end.";
  if (d.sweepMode === "bloc" && !(lo >= 0 && hi <= 100)) return "Turnout sweep must stay within 0–100%.";
  if (d.sweepMode === "all_shift" && !(lo >= -100 && hi <= 100)) return "Shift must stay within ±100 percentage points.";
  const s = num(d.seats);
  if (!Number.isInteger(s) || s < 1 || s > 650) return "Seats must be a whole number from 1 to 650.";
  return null;
}

const COLORS = ["#8055f6", "#22d3ee", "#10b981", "#f59e0b", "#f472b6", "#a78bfa", "#60a5fa", "#fb7185"];

export function TurnoutTool({ d, set, adv, onSaved }: { d: TurnoutDraft; set: (d: TurnoutDraft) => void; adv: boolean; onSaved: () => void }) {
  const body = useMemo(() => turnoutBody(d), [d]);
  const problem = prefProblem(d);
  const a = useAnalysis<PolTurnout>("politics/turnout", problem ? null : body);
  const setBloc = (i: number, v: Partial<TurnoutDraft["blocs"][number]>) => set({ ...d, blocs: d.blocs.map((b, j) => (j === i ? { ...b, ...v } : b)) });
  const setPref = (i: number, k: number, v: string) => setBloc(i, { prefs: d.blocs[i].prefs.map((x, j) => (j === k ? v : x)) });
  const normalise = (i: number) => {
    const ps = d.blocs[i].prefs.map(num);
    const s = ps.reduce((acc, x) => acc + (Number.isFinite(x) ? x : 0), 0);
    if (s > 0) setBloc(i, { prefs: ps.map((x) => String(+(((Number.isFinite(x) ? x : 0) / s) * 100).toFixed(4))) });
  };
  const renameParty = (k: number, v: string) => set({ ...d, parties: d.parties.map((p, j) => (j === k ? v : p)) });
  const addParty = () => set({ ...d, parties: [...d.parties, `Party ${d.parties.length + 1}`], blocs: d.blocs.map((b) => ({ ...b, prefs: [...b.prefs, "0"] })) });
  const delParty = (k: number) => set({ ...d, parties: d.parties.filter((_, j) => j !== k), blocs: d.blocs.map((b) => ({ ...b, prefs: b.prefs.filter((_, j) => j !== k) })) });
  const addBloc = () => set({ ...d, blocs: [...d.blocs, { name: `Bloc ${d.blocs.length + 1}`, electorate: "100000", turnout: "60", prefs: d.parties.map((_, k) => (k === 0 ? "100" : "0")) }] });
  const delBloc = (i: number) => set({ ...d, blocs: d.blocs.filter((_, j) => j !== i), sweepBloc: Math.max(0, Math.min(d.sweepBloc, d.blocs.length - 2)) });

  const seatsNum = num(d.seats);
  const sweep = a.data?.sweep;
  const chart = sweep?.curve.map((p) => ({ x: +(p.x * 100).toFixed(2), ...Object.fromEntries(a.data!.parties.map((n, k) => [n, +((p.seats[k] / seatsNum) * 100).toFixed(2)])) }));
  return (
    <div className="space-y-4">
      <Panel title="1 · Aggregate electorate blocs" badge={<Badge tone="amber">Your assumptions, not polls</Badge>}>
        <p className="mb-3 text-xs leading-relaxed text-muted">Each bloc is an <strong>aggregate group</strong> (a region, an age band, any label you choose) with a size, a turnout rate, and the share of its voters who prefer each party. The tool never handles individuals and offers no way to identify or target anyone.</p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <caption className="sr-only">Blocs, turnout and party preference shares</caption>
            <thead>
              <tr className="text-left text-[11px] text-muted">
                <th scope="col" className="font-normal">Bloc</th><th scope="col" className="font-normal">Electorate</th><th scope="col" className="font-normal">Turnout %</th>
                {d.parties.map((p, k) => (
                  <th key={k} scope="col" className="font-normal">
                    <div className="flex items-center gap-1"><input aria-label={`Party ${k + 1} name`} value={p} maxLength={60} onChange={(e) => renameParty(k, e.target.value)} className={`${field} w-24 text-xs font-semibold text-ink`} />
                      {d.parties.length > 2 && <button type="button" aria-label={`Remove party ${p}`} onClick={() => delParty(k)} className="rounded p-1 hover:text-red-300"><X className="h-3 w-3" /></button>}</div>
                  </th>
                ))}
                <th scope="col" className="font-normal">Sum %</th><th />
              </tr>
            </thead>
            <tbody>
              {d.blocs.map((b, i) => {
                const sum = b.prefs.map(num).reduce((x, y) => x + (Number.isFinite(y) ? y : 0), 0);
                return (
                  <tr key={i}>
                    <td className="pr-2 pb-1"><input aria-label={`Bloc ${i + 1} name`} value={b.name} maxLength={60} onChange={(e) => setBloc(i, { name: e.target.value })} className={`${field} w-28`} /></td>
                    <td className="pr-2 pb-1"><input aria-label={`${b.name} electorate`} inputMode="numeric" value={b.electorate} onChange={(e) => setBloc(i, { electorate: e.target.value })} className={`${field} w-28 font-mono`} /></td>
                    <td className="pr-2 pb-1"><input aria-label={`${b.name} turnout percent`} inputMode="decimal" value={b.turnout} onChange={(e) => setBloc(i, { turnout: e.target.value })} className={`${field} w-20 font-mono`} /></td>
                    {b.prefs.map((x, k) => <td key={k} className="pr-2 pb-1"><input aria-label={`${b.name} preference for ${d.parties[k]} percent`} inputMode="decimal" value={x} onChange={(e) => setPref(i, k, e.target.value)} className={`${field} w-20 font-mono`} /></td>)}
                    <td className={`pr-2 font-mono text-xs ${Math.abs(sum - 100) > 1e-4 ? "text-amber-300" : "text-muted"}`}>{+sum.toFixed(2)} {Math.abs(sum - 100) > 1e-4 && <button type="button" onClick={() => normalise(i)} className="ml-1 rounded border border-line px-1.5 py-0.5 font-sans text-[10px] hover:border-violet/60">Normalise</button>}</td>
                    <td>{d.blocs.length > 1 && <button type="button" aria-label={`Remove bloc ${b.name}`} onClick={() => delBloc(i)} className="rounded p-1.5 text-muted hover:text-red-300"><X className="h-4 w-4" /></button>}</td>
                  </tr>);
              })}
            </tbody>
          </table>
        </div>
        <div className="mt-2 flex gap-2">
          {d.blocs.length < 12 && <button type="button" onClick={addBloc} className="inline-flex items-center gap-1 rounded-lg border border-dashed border-line px-3 py-1.5 text-xs text-muted hover:text-ink"><Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add bloc</button>}
          {d.parties.length < 12 && <button type="button" onClick={addParty} className="inline-flex items-center gap-1 rounded-lg border border-dashed border-line px-3 py-1.5 text-xs text-muted hover:text-ink"><Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add party</button>}
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div><label htmlFor="t-method" className="mb-1 block text-xs text-muted">Allocation rule</label>
            <select id="t-method" value={d.method} onChange={(e) => set({ ...d, method: e.target.value as TurnoutDraft["method"] })} className={`${field} w-full`}><option value="dhondt">D&apos;Hondt</option><option value="sainte_lague">Sainte-Laguë</option><option value="hare">Largest remainder (Hare)</option></select></div>
          <div><label htmlFor="t-seats" className="mb-1 block text-xs text-muted">Seats</label><input id="t-seats" inputMode="numeric" value={d.seats} onChange={(e) => set({ ...d, seats: e.target.value })} className={`${field} w-full font-mono`} /></div>
          <div><label htmlFor="t-th" className="mb-1 block text-xs text-muted">Threshold (% of votes)</label><input id="t-th" inputMode="decimal" value={d.threshold} onChange={(e) => set({ ...d, threshold: e.target.value })} className={`${field} w-full font-mono`} /></div>
        </div>
      </Panel>

      <Panel title="2 · Turnout sweep">
        <div className="grid gap-3 sm:grid-cols-4">
          <div className="sm:col-span-2"><label htmlFor="t-mode" className="mb-1 block text-xs text-muted">Vary</label>
            <select id="t-mode" value={d.sweepMode === "bloc" ? `bloc:${d.sweepBloc}` : "all"} onChange={(e) => { const v = e.target.value; if (v === "all") set({ ...d, sweepMode: "all_shift", lo: "-10", hi: "10" }); else set({ ...d, sweepMode: "bloc", sweepBloc: Number(v.split(":")[1]), lo: "30", hi: "90" }); }} className={`${field} w-full`}>
              {d.blocs.map((b, i) => <option key={i} value={`bloc:${i}`}>Turnout of {b.name || `bloc ${i + 1}`}</option>)}
              <option value="all">All blocs together (± percentage points)</option>
            </select></div>
          <div><label htmlFor="t-lo" className="mb-1 block text-xs text-muted">From {d.sweepMode === "bloc" ? "(% turnout)" : "(pp)"}</label><input id="t-lo" inputMode="decimal" value={d.lo} onChange={(e) => set({ ...d, lo: e.target.value })} className={`${field} w-full font-mono`} /></div>
          <div><label htmlFor="t-hi" className="mb-1 block text-xs text-muted">To</label><input id="t-hi" inputMode="decimal" value={d.hi} onChange={(e) => set({ ...d, hi: e.target.value })} className={`${field} w-full font-mono`} /></div>
        </div>
      </Panel>

      <Panel title="3 · Results" badge={<Badge tone="green">Exact arithmetic</Badge>}>
        <div aria-live="polite">
          {problem ? <p className="text-sm text-amber-300">{problem}</p>
            : a.loading ? <p className="flex items-center gap-2 text-sm text-muted"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Calculating…</p>
            : a.error ? <ErrorPanel message={a.error} />
            : a.data && (
              <div className="space-y-4">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[360px] text-sm"><caption className="sr-only">Baseline result</caption>
                    <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="font-normal">Party</th><th scope="col" className="font-normal">Vote share</th><th scope="col" className="font-normal">Seats</th><th scope="col" className="font-normal">Seat share</th></tr></thead>
                    <tbody className="font-mono">{a.data.parties.map((n, k) => <tr key={n} className="border-t border-line"><td className="py-1 font-sans font-semibold">{n}</td><td>{pc(a.data!.baseline.vote_share[k])}</td><td>{a.data!.baseline.seats[k]}</td><td>{pc(a.data!.baseline.seats[k] / seatsNum)}</td></tr>)}</tbody></table>
                </div>
                <p className="text-sm text-muted">Baseline overall turnout {pc(a.data.baseline.turnout_overall)} · largest party <strong className="text-ink">{a.data.baseline.largest}</strong> · single-party majority: <strong className="text-ink">{a.data.baseline.majority_party ?? "none"}</strong>.</p>
                {sweep && chart && (
                  <>
                    <div className="h-64" role="img" aria-label="Seat share for each party as turnout varies">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chart}>
                          <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
                          <XAxis dataKey="x" type="number" domain={["dataMin", "dataMax"]} tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} unit={d.sweepMode === "bloc" ? "%" : " pp"} />
                          <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} width={40} unit="%" domain={[(min: number) => Math.max(0, Math.floor(min - 4)), (max: number) => Math.min(100, Math.ceil(max + 4))]} allowDecimals={false} />
                          <Tooltip contentStyle={{ background: "#17213a", border: "1px solid #334155", borderRadius: 8 }} formatter={(v) => `${v}% of seats`} labelFormatter={(l) => `${d.sweepMode === "bloc" ? "Turnout" : "Shift"} ${l}${d.sweepMode === "bloc" ? "%" : " pp"}`} />
                          <Legend />
                          <ReferenceLine y={50} stroke="#94a3b8" strokeDasharray="4 3" ifOverflow="hidden" label={{ value: "majority", fill: "#94a3b8", fontSize: 10, position: "insideTopRight" }} />
                          {a.data.parties.map((n, k) => <Line key={n} type="stepAfter" dataKey={n} stroke={COLORS[k % COLORS.length]} strokeWidth={2} dot={false} />)}
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                    <div>
                      <h3 className="mb-1 text-sm font-semibold">Tipping points</h3>
                      {sweep.changes.length === 0 ? <p className="text-sm text-muted">The seat allocation does not change anywhere in this range.</p> : (
                        <ul className="space-y-1.5 text-sm">
                          {sweep.changes.slice(0, adv ? 60 : 8).map((c, i) => (
                            <li key={i} className="rounded-lg border border-line p-2"><span className="font-mono">{d.sweepMode === "bloc" ? `${(c.at * 100).toFixed(3)}%` : `${c.at >= 0 ? "+" : ""}${(c.at * 100).toFixed(3)} pp`}</span> — {c.what.join("; ")}
                              <div className="font-mono text-[11px] text-muted">{c.seats_before.join("/")} → {c.seats_after.join("/")}</div></li>))}
                        </ul>)}
                      {!adv && sweep.changes.length > 8 && <p className="mt-1 text-xs text-muted">Showing 8 of {sweep.changes.length}. Turn on Advanced analytics to see all.</p>}
                      <p className="mt-2 text-[11px] text-muted">{sweep.note} Seat order lists parties as: {a.data.parties.join(" / ")}.</p>
                    </div>
                  </>
                )}
              </div>)}
        </div>
      </Panel>
      <Panel title="Save this scenario"><SaveBar kind="turnout" inputs={body} valid={!!body && !problem && !a.error} onSaved={onSaved} /></Panel>
    </div>
  );
}
