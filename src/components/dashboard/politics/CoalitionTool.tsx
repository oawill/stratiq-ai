"use client";

import { useMemo, useState } from "react";
import { Loader2, Plus, X } from "lucide-react";
import { post } from "@/lib/client";
import type { PolAllocate, PolCoalition, PolSimulation } from "@/lib/types";
import { Badge, ErrorPanel, Panel } from "../ui";
import { SaveBar, field, num, pc, useAnalysis } from "./shared";

export interface CoalitionDraft {
  parties: { name: string; seats: string; position: string; votes: string }[];
  quota: "majority" | "three_fifths" | "two_thirds" | "custom";
  custom: string; // percent
  method: "dhondt" | "sainte_lague" | "hare";
  totalSeats: string; threshold: string; // percent
  concentration: string; iterations: string; seed: string; candidates: string;
}

export const defaultCoalition = (): CoalitionDraft => ({
  parties: [
    { name: "Alpha", seats: "38", position: "1", votes: "" }, { name: "Beta", seats: "30", position: "2", votes: "" },
    { name: "Gamma", seats: "17", position: "3", votes: "" }, { name: "Delta", seats: "9", position: "4", votes: "" },
    { name: "Epsilon", seats: "6", position: "5", votes: "" },
  ],
  quota: "majority", custom: "60", method: "dhondt", totalSeats: "100", threshold: "0", concentration: "200", iterations: "2000", seed: "", candidates: "",
});

const QUOTAS = { majority: 0.5, three_fifths: 0.6, two_thirds: 2 / 3 } as const;
export const quotaFraction = (d: CoalitionDraft) => (d.quota === "custom" ? num(d.custom) / 100 : QUOTAS[d.quota]);

export function coalitionBody(d: CoalitionDraft) {
  const q = quotaFraction(d);
  if (!(q >= 0.5 && q < 1)) return null;
  const withPos = d.parties.every((p) => p.position.trim() !== "");
  const parties = d.parties.map((p) => ({ name: p.name.trim(), seats: num(p.seats), position: withPos ? num(p.position) : null }));
  if (parties.some((p) => !p.name || !Number.isInteger(p.seats) || p.seats < 0 || (p.position !== null && !Number.isFinite(p.position)))) return null;
  if (new Set(parties.map((p) => p.name)).size !== parties.length || parties.reduce((a, p) => a + p.seats, 0) < 1) return null;
  return { parties, quota_fraction: q === 2 / 3 ? 0.6667 : q };
}

function Status({ p }: { p: PolCoalition["parties"][number] }) {
  return (
    <span className="flex flex-wrap gap-1">
      {p.is_dictator && <Badge tone="violet">Can win alone</Badge>}
      {p.is_veto && <Badge tone="amber">Veto</Badge>}
      {p.is_dummy && p.seats > 0 && <Badge tone="muted">Dummy</Badge>}
    </span>
  );
}

function SeatCalculator({ d, set }: { d: CoalitionDraft; set: (d: CoalitionDraft) => void }) {
  const votes = d.parties.map((p) => num(p.votes));
  const seats = num(d.totalSeats), th = num(d.threshold) / 100;
  const body = votes.every((v) => Number.isFinite(v) && v >= 0) && votes.some((v) => v > 0) && Number.isInteger(seats) && seats >= 1 && seats <= 650 && th >= 0 && th < 1
    ? { method: d.method, seats, threshold: th, parties: d.parties.map((p, i) => ({ name: p.name.trim() || `Party ${i + 1}`, votes: votes[i] })) } : null;
  const a = useAnalysis<PolAllocate>("politics/allocate", body);
  return (
    <Panel title="Seat calculator" badge={<Badge tone="muted">Optional</Badge>}>
      <p className="mb-3 text-xs text-muted">Enter scenario vote totals (any unit) to see how an allocation rule turns votes into seats. These are assumptions you type, not polls.</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <div><label htmlFor="alloc-method" className="mb-1 block text-xs text-muted">Allocation rule</label>
          <select id="alloc-method" value={d.method} onChange={(e) => set({ ...d, method: e.target.value as CoalitionDraft["method"] })} className={`${field} w-full`}>
            <option value="dhondt">D&apos;Hondt</option><option value="sainte_lague">Sainte-Laguë</option><option value="hare">Largest remainder (Hare)</option>
          </select></div>
        <div><label htmlFor="alloc-seats" className="mb-1 block text-xs text-muted">Seats to allocate</label><input id="alloc-seats" inputMode="numeric" value={d.totalSeats} onChange={(e) => set({ ...d, totalSeats: e.target.value })} className={`${field} w-full font-mono`} /></div>
        <div><label htmlFor="alloc-th" className="mb-1 block text-xs text-muted">Threshold (% of votes)</label><input id="alloc-th" inputMode="decimal" value={d.threshold} onChange={(e) => set({ ...d, threshold: e.target.value })} className={`${field} w-full font-mono`} /></div>
      </div>
      <p className="mt-2 text-[11px] text-muted">Fill the “Votes” column in the party table above.</p>
      <div aria-live="polite" className="mt-3 text-sm">
        {!body ? <p className="text-muted">Enter votes for the parties to calculate seats.</p> : a.loading ? <p className="flex items-center gap-2 text-muted"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Calculating…</p>
          : a.error ? <p role="alert" className="text-red-300">{a.error}</p> : a.data && (
            <div>
              <table className="w-full max-w-md text-sm"><thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="font-normal">Party</th><th scope="col" className="font-normal">Vote share</th><th scope="col" className="font-normal">Seats</th></tr></thead>
                <tbody className="font-mono">{a.data.parties.map((p) => <tr key={p.name}><td className="font-sans">{p.name}</td><td>{pc(p.vote_share)}</td><td>{p.seats}</td></tr>)}</tbody></table>
              <button type="button" onClick={() => set({ ...d, parties: d.parties.map((p, i) => ({ ...p, seats: String(a.data!.parties[i].seats) })) })} className="mt-3 rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-violet/60">Use these seats in the analysis</button>
            </div>)}
      </div>
    </Panel>
  );
}

function Uncertainty({ d, set }: { d: CoalitionDraft; set: (d: CoalitionDraft) => void }) {
  const [res, setRes] = useState<PolSimulation | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const names = d.parties.map((p) => p.name.trim());
  async function run() {
    setBusy(true); setErr(null);
    try {
      const votes = d.parties.map((p) => num(p.votes));
      if (votes.some((v) => !Number.isFinite(v)) || votes.every((v) => v === 0)) throw new Error("Fill the Votes column for every party first.");
      const cands = d.candidates.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean).map((s) => s.split("+").map((n) => n.trim()));
      setRes(await post<PolSimulation>("politics/simulate", {
        method: d.method, seats: num(d.totalSeats), threshold: num(d.threshold) / 100, concentration: num(d.concentration), quota_fraction: quotaFraction(d) === 2 / 3 ? 0.6667 : quotaFraction(d),
        iterations: num(d.iterations), seed: d.seed.trim() === "" ? null : num(d.seed), candidates: cands, parties: d.parties.map((p, i) => ({ name: names[i], votes: votes[i] })),
      }));
    } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); setRes(null); } finally { setBusy(false); }
  }
  return (
    <Panel title="Election-uncertainty scenarios" badge={<Badge tone="amber">Scenario noise, not polling error</Badge>}>
      <p className="mb-3 text-xs leading-relaxed text-muted">Adds seeded random variation around your entered vote shares, converts them to seats with the rule above, and reports how often each coalition would have a majority. “Concentration” is a knob: higher means vote shares stay closer to what you entered. It is not a measured error.</p>
      <div className="grid gap-3 sm:grid-cols-4">
        <div><label htmlFor="u-conc" className="mb-1 block text-xs text-muted">Concentration</label><input id="u-conc" inputMode="decimal" value={d.concentration} onChange={(e) => set({ ...d, concentration: e.target.value })} className={`${field} w-full font-mono`} /></div>
        <div><label htmlFor="u-iter" className="mb-1 block text-xs text-muted">Runs (100–5000)</label><input id="u-iter" inputMode="numeric" value={d.iterations} onChange={(e) => set({ ...d, iterations: e.target.value })} className={`${field} w-full font-mono`} /></div>
        <div><label htmlFor="u-seed" className="mb-1 block text-xs text-muted">Seed</label><input id="u-seed" inputMode="numeric" value={d.seed} placeholder="random" onChange={(e) => set({ ...d, seed: e.target.value })} className={`${field} w-full font-mono`} /></div>
        <div className="sm:col-span-4"><label htmlFor="u-cands" className="mb-1 block text-xs text-muted">Candidate coalitions to track (e.g. “Alpha+Beta, Beta+Gamma+Delta”)</label><input id="u-cands" value={d.candidates} onChange={(e) => set({ ...d, candidates: e.target.value })} className={`${field} w-full`} /></div>
      </div>
      <button type="button" onClick={run} disabled={busy} className="mt-3 inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Run scenarios</button>
      {err && <p role="alert" className="mt-2 text-sm text-red-300">{err}</p>}
      {res && (
        <div className="mt-4 space-y-4">
          <p className="text-xs text-muted">{res.iterations.toLocaleString()} runs · seed {res.seed} · {res.seats_needed} seats needed · no single-party majority in {pc(res.p_no_single_party_majority)} of runs.</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm"><caption className="sr-only">Seat outcomes across scenario runs</caption>
              <thead><tr className="text-left text-[11px] text-muted">{["Party", "Mean seats", "5–95%", "Largest", "Alone majority", "Decisive somewhere", "Veto"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
              <tbody className="font-mono">{res.parties.map((p) => (
                <tr key={p.name} className="border-t border-line"><td className="py-1 font-sans">{p.name}</td><td>{p.mean_seats.toFixed(1)}</td><td>{p.p05_seats}–{p.p95_seats}</td><td>{pc(p.p_largest, 0)}</td><td>{pc(p.p_single_party_majority, 0)}</td><td>{pc(p.p_decisive_in_some_coalition, 0)}</td><td>{pc(p.p_veto, 0)}</td></tr>))}</tbody></table>
          </div>
          {res.candidates.length > 0 && (
            <table className="w-full max-w-lg text-sm"><caption className="sr-only">Candidate coalition outcomes</caption>
              <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="font-normal">Coalition</th><th scope="col" className="font-normal">Has a majority</th><th scope="col" className="font-normal">…and is minimal</th></tr></thead>
              <tbody className="font-mono">{res.candidates.map((c, i) => <tr key={i} className="border-t border-line"><td className="py-1 font-sans">{c.parties.map((j) => names[j]).join(" + ")}</td><td>{pc(c.p_winning)}</td><td>{pc(c.p_minimal_winning)}</td></tr>)}</tbody></table>
          )}
          <p className="text-[11px] text-muted">{res.note} A &ldquo;majority&rdquo; share is not the chance that this government forms: parties also weigh policy and relationships, which this tool does not model.</p>
        </div>
      )}
    </Panel>
  );
}

export function CoalitionTool({ d, set, adv, onSaved }: { d: CoalitionDraft; set: (d: CoalitionDraft) => void; adv: boolean; onSaved: () => void }) {
  const body = useMemo(() => coalitionBody(d), [d]);
  const a = useAnalysis<PolCoalition>("politics/coalitions", body);
  const setP = (i: number, v: Partial<CoalitionDraft["parties"][number]>) => set({ ...d, parties: d.parties.map((p, j) => (j === i ? { ...p, ...v } : p)) });
  const names = d.parties.map((p) => p.name.trim());
  return (
    <div className="space-y-4">
      <Panel title="1 · Parties and seats" badge={<span className="text-xs text-muted">illustrative starting values</span>}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <caption className="sr-only">Parties</caption>
            <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="font-normal">Party</th><th scope="col" className="font-normal">Seats</th><th scope="col" className="font-normal">Left–right position (optional)</th><th scope="col" className="font-normal">Votes (seat calculator)</th><th /></tr></thead>
            <tbody>
              {d.parties.map((p, i) => (
                <tr key={i}>
                  <td className="pr-2 pb-1"><input aria-label={`Party ${i + 1} name`} value={p.name} maxLength={60} onChange={(e) => setP(i, { name: e.target.value })} className={`${field} w-full`} /></td>
                  <td className="pr-2 pb-1"><input aria-label={`${p.name} seats`} inputMode="numeric" value={p.seats} onChange={(e) => setP(i, { seats: e.target.value })} className={`${field} w-24 font-mono`} /></td>
                  <td className="pr-2 pb-1"><input aria-label={`${p.name} position`} inputMode="decimal" value={p.position} placeholder="e.g. 3.5" onChange={(e) => setP(i, { position: e.target.value })} className={`${field} w-28 font-mono`} /></td>
                  <td className="pr-2 pb-1"><input aria-label={`${p.name} votes`} inputMode="decimal" value={p.votes} onChange={(e) => setP(i, { votes: e.target.value })} className={`${field} w-28 font-mono`} /></td>
                  <td>{d.parties.length > 2 && <button type="button" aria-label={`Remove ${p.name}`} onClick={() => set({ ...d, parties: d.parties.filter((_, j) => j !== i) })} className="rounded p-1.5 text-muted hover:text-red-300"><X className="h-4 w-4" /></button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {d.parties.length < 12 && <button type="button" onClick={() => set({ ...d, parties: [...d.parties, { name: `Party ${d.parties.length + 1}`, seats: "0", position: "", votes: "" }] })} className="mt-2 inline-flex items-center gap-1 rounded-lg border border-dashed border-line px-3 py-1.5 text-xs text-muted hover:text-ink"><Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add party</button>}
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div><label htmlFor="quota" className="mb-1 block text-xs text-muted">Seats needed to win a vote</label>
            <select id="quota" value={d.quota} onChange={(e) => set({ ...d, quota: e.target.value as CoalitionDraft["quota"] })} className={`${field} w-full`}>
              <option value="majority">Simple majority (more than 50%)</option><option value="three_fifths">Three-fifths (more than 60%)</option><option value="two_thirds">Two-thirds (more than 66.7%)</option><option value="custom">Custom…</option>
            </select></div>
          {d.quota === "custom" && <div><label htmlFor="quota-c" className="mb-1 block text-xs text-muted">More than (% of seats, 50–99.9)</label><input id="quota-c" inputMode="decimal" value={d.custom} onChange={(e) => set({ ...d, custom: e.target.value })} className={`${field} w-full font-mono`} /></div>}
        </div>
      </Panel>

      <Panel title="2 · Coalition arithmetic and voting power" badge={<Badge tone="green">Exact</Badge>}>
        <div aria-live="polite">
          {!body ? <p className="text-sm text-amber-300">Enter a name and a whole number of seats for every party (names must be different, with at least one seat overall).</p>
            : a.loading ? <p className="flex items-center gap-2 text-sm text-muted"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Calculating…</p>
            : a.error ? <ErrorPanel message={a.error} />
            : a.data && (
              <div className="space-y-4">
                <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {([["Total seats", a.data.total_seats], ["Seats needed", a.data.seats_needed], ["Winning coalitions", a.data.winning_coalitions], ["Minimal winning", a.data.minimal_winning_count]] as const).map(([k, v]) => (
                    <div key={k} className="rounded-xl border border-line bg-card/60 p-3"><dt className="text-[11px] text-muted">{k}</dt><dd className="font-mono text-xl font-bold">{v}</dd></div>))}
                </dl>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[520px] text-sm">
                    <caption className="sr-only">Seat share and voting power by party</caption>
                    <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="font-normal">Party</th><th scope="col" className="font-normal">Seat share</th><th scope="col" className="font-normal">Voting power (Shapley–Shubik)</th>{adv && <th scope="col" className="font-normal">Banzhaf</th>}<th scope="col" className="font-normal">Role</th></tr></thead>
                    <tbody>{a.data.parties.map((p) => (
                      <tr key={p.name} className="border-t border-line">
                        <th scope="row" className="py-2 pr-3 text-left font-semibold">{p.name}</th>
                        <td className="pr-3 font-mono">{pc(p.seat_share)}</td>
                        <td className="pr-3">
                          <div className="flex items-center gap-2"><div className="h-2 w-28 overflow-hidden rounded bg-white/10" role="img" aria-label={`${p.name}: ${pc(p.shapley_shubik)} of voting power`}><div className="h-full bg-primary" style={{ width: `${p.shapley_shubik * 100}%` }} /></div><span className="font-mono">{pc(p.shapley_shubik)}</span></div>
                        </td>
                        {adv && <td className="pr-3 font-mono">{pc(p.banzhaf_normalised)} <span className="text-[10px] text-muted">({p.banzhaf_raw_swings} swings)</span></td>}
                        <td><Status p={p} /></td>
                      </tr>))}</tbody>
                  </table>
                </div>
                {a.data.notes.length > 0 && <ul className="space-y-1 rounded-xl border border-line bg-bg/50 p-3 text-sm">{a.data.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
                <div>
                  <h3 className="mb-1 text-sm font-semibold">Minimal winning coalitions <span className="font-normal text-muted">(ranked by fewest surplus seats, then fewest parties{a.data.connected_minimal_winning !== null ? ", then narrowest range" : ""})</span></h3>
                  {a.data.minimal_winning.length === 0 ? <p className="text-sm text-muted">None.</p> : (
                    <ul className="divide-y divide-line">
                      {a.data.minimal_winning.slice(0, adv ? 30 : 6).map((c, i) => (
                        <li key={i} className="flex flex-wrap items-center gap-2 py-1.5 text-sm">
                          <span className="font-semibold">{c.parties.map((j) => names[j]).join(" + ")}</span>
                          <span className="font-mono text-xs text-muted">{c.seats} seats · surplus {c.surplus}</span>
                          {c.connected === true && <Badge tone="green">Connected</Badge>}{c.connected === false && <Badge tone="muted">Not connected</Badge>}
                        </li>))}
                    </ul>
                  )}
                  <p className="mt-2 text-[11px] text-muted">A ranking by stated criteria, not a prediction of which government forms. Voting power measures how often a party is decisive across hypothetical coalitions; it ignores policy fit.{a.data.connected_minimal_winning !== null && ` ${a.data.connected_minimal_winning} minimal coalition(s) are ideologically connected on the positions you entered.`}</p>
                </div>
                {adv && <p className="text-[11px] text-muted">Exact Shapley–Shubik values: {a.data.parties.map((p) => `${p.name} ${p.shapley_shubik_exact}`).join(" · ")}</p>}
              </div>)}
        </div>
      </Panel>

      <SeatCalculator d={d} set={set} />
      {adv && <Uncertainty d={d} set={set} />}
      {!adv && <p className="text-xs text-muted">Turn on <strong>Advanced analytics</strong> for Banzhaf indices, more coalitions and the election-uncertainty scenarios.</p>}
      <Panel title="Save this scenario"><SaveBar kind="coalition" inputs={body} valid={!!body && !a.error} onSaved={onSaved} /></Panel>
    </div>
  );
}
