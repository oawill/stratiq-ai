"use client";

import { useEffect, useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import { call, post } from "@/lib/client";
import type { PolCompare, PolKind, PolScenarioFull, PolScenarioRow } from "@/lib/types";
import { Badge, Empty, ErrorPanel, Panel, dt } from "../ui";
import { useAdvanced } from "../useAdvanced";
import { CoalitionTool, defaultCoalition, type CoalitionDraft } from "./CoalitionTool";
import { PolicyTool, defaultPolicy, type PolicyDraft } from "./PolicyTool";
import { TurnoutTool, defaultTurnout, type TurnoutDraft } from "./TurnoutTool";
import { pc } from "./shared";

type Tab = "coalition" | "turnout" | "policy" | "saved";
const TABS: [Tab, string][] = [["coalition", "Coalitions & voting power"], ["turnout", "Turnout sensitivity"], ["policy", "Policy trade-offs"], ["saved", "Saved & compare"]];
const KIND_LABEL: Record<PolKind, string> = { coalition: "Coalition", turnout: "Turnout", policy: "Policy" };

const pct = (x: number) => String(+(x * 100).toFixed(6));

/* eslint-disable @typescript-eslint/no-explicit-any */
function coalitionFrom(i: any): CoalitionDraft {
  const q: number = i.quota_fraction;
  const base = defaultCoalition();
  return {
    ...base,
    parties: i.parties.map((p: any) => ({ name: p.name, seats: String(p.seats), position: p.position == null ? "" : String(p.position), votes: "" })),
    quota: q === 0.5 ? "majority" : q === 0.6 ? "three_fifths" : q === 0.6667 ? "two_thirds" : "custom",
    custom: pct(q),
  };
}
function turnoutFrom(i: any): TurnoutDraft {
  const sw = i.sweep;
  return {
    parties: i.parties,
    blocs: i.blocs.map((b: any) => ({ name: b.name, electorate: String(b.electorate), turnout: pct(b.turnout), prefs: i.parties.map((p: string) => pct(b.prefs[p])) })),
    method: i.method, seats: String(i.seats), threshold: pct(i.threshold),
    sweepMode: sw?.mode ?? "bloc", sweepBloc: sw?.bloc ?? 0, lo: sw ? pct(sw.lo) : "30", hi: sw ? pct(sw.hi) : "90",
  };
}
function policyFrom(i: any): PolicyDraft {
  return {
    alts: i.alternatives, criteria: i.criteria.map((c: any) => ({ name: c.name, weight: String(c.weight), direction: c.direction })),
    scores: i.scores.map((r: number[]) => r.map(String)), seed: i.seed == null ? "" : String(i.seed),
  };
}

function CompareTable({ data }: { data: PolCompare }) {
  const th = "px-3 py-1 text-left text-[11px] font-normal text-muted";
  const td = "border-t border-line px-3 py-1.5 font-mono text-sm";
  const heads = data.scenarios.map((s) => <th key={s.id} scope="col" className={th}>{s.title}</th>);
  if (data.kind === "coalition") {
    const names = [...new Set(data.scenarios.flatMap((s) => s.summary.parties.map((p: any) => p.name as string)))];
    return (
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px]"><caption className="sr-only">Coalition scenario comparison</caption>
          <thead><tr><th scope="col" className={th}>Party</th>{heads}</tr></thead>
          <tbody>
            {names.map((n) => (
              <tr key={n}><th scope="row" className={`${td} font-sans font-semibold`}>{n}</th>
                {data.scenarios.map((s) => { const p = s.summary.parties.find((x: any) => x.name === n); return <td key={s.id} className={td}>{p ? <>{p.seats} seats · power {pc(p.shapley_shubik)}{p.veto && <Badge tone="amber">veto</Badge>}{p.dummy && p.seats > 0 && <Badge tone="muted">dummy</Badge>}</> : "—"}</td>; })}</tr>))}
            <tr><th scope="row" className={`${td} font-sans`}>Seats needed</th>{data.scenarios.map((s) => <td key={s.id} className={td}>{s.summary.seats_needed} of {s.summary.total_seats}</td>)}</tr>
            <tr><th scope="row" className={`${td} font-sans`}>Minimal winning coalitions</th>{data.scenarios.map((s) => <td key={s.id} className={td}>{s.summary.minimal_winning_count}</td>)}</tr>
          </tbody>
        </table>
      </div>
    );
  }
  if (data.kind === "turnout") {
    const names = [...new Set(data.scenarios.flatMap((s) => s.summary.parties.map((p: any) => p.name as string)))];
    return (
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px]"><caption className="sr-only">Turnout scenario comparison</caption>
          <thead><tr><th scope="col" className={th}>Party</th>{heads}</tr></thead>
          <tbody>
            {names.map((n) => (
              <tr key={n}><th scope="row" className={`${td} font-sans font-semibold`}>{n}</th>
                {data.scenarios.map((s) => { const p = s.summary.parties.find((x: any) => x.name === n); return <td key={s.id} className={td}>{p ? `${pc(p.vote_share)} votes · ${p.seats} seats` : "—"}</td>; })}</tr>))}
            <tr><th scope="row" className={`${td} font-sans`}>Largest party</th>{data.scenarios.map((s) => <td key={s.id} className={td}>{s.summary.largest}</td>)}</tr>
            <tr><th scope="row" className={`${td} font-sans`}>Single-party majority</th>{data.scenarios.map((s) => <td key={s.id} className={td}>{s.summary.majority_party ?? "none"}</td>)}</tr>
            <tr><th scope="row" className={`${td} font-sans`}>Overall turnout</th>{data.scenarios.map((s) => <td key={s.id} className={td}>{pc(s.summary.turnout)}</td>)}</tr>
            <tr><th scope="row" className={`${td} font-sans`}>First tipping points</th>{data.scenarios.map((s) => <td key={s.id} className={td}>{s.summary.change_points ? (s.summary.change_points.length ? s.summary.change_points.map((c: number) => `${(c * 100).toFixed(2)}`).join(", ") : "none") : "no sweep"}</td>)}</tr>
          </tbody>
        </table>
      </div>
    );
  }
  const names = [...new Set(data.scenarios.flatMap((s) => s.summary.alternatives.map((a: any) => a.name as string)))];
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px]"><caption className="sr-only">Policy scenario comparison</caption>
        <thead><tr><th scope="col" className={th}>Alternative</th>{heads}</tr></thead>
        <tbody>
          {names.map((n) => (
            <tr key={n}><th scope="row" className={`${td} font-sans font-semibold`}>{n}</th>
              {data.scenarios.map((s) => { const a = s.summary.alternatives.find((x: any) => x.name === n); return <td key={s.id} className={td}>{a ? <>#{a.rank} · {a.score.toFixed(3)} · top in {pc(a.p_top, 0)}{a.pareto && <Badge tone="green">Pareto</Badge>}</> : "—"}</td>; })}</tr>))}
          <tr><th scope="row" className={`${td} font-sans`}>Ranking</th>{data.scenarios.map((s) => <td key={s.id} className={`${td} text-xs`}>{s.summary.ranking.join(" > ")}</td>)}</tr>
        </tbody>
      </table>
    </div>
  );
}

function SavedPanel({ onOpen }: { onOpen: (s: PolScenarioFull) => void }) {
  const [list, setList] = useState<PolScenarioRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<string[]>([]);
  const [cmp, setCmp] = useState<PolCompare | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    call<{ scenarios: PolScenarioRow[] }>("politics/scenarios").then((d) => live && setList(d.scenarios)).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [tick]);

  const kindOf = (id: string) => list?.find((s) => s.id === id)?.kind;
  const toggle = (id: string) => {
    setCmp(null); setErr(null);
    setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length >= 4 ? s : s.length && kindOf(s[0]) !== kindOf(id) ? [id] : [...s, id]));
  };
  async function open(id: string) {
    setBusy(id); setErr(null);
    try { onOpen(await call<PolScenarioFull>(`politics/scenarios/${id}`)); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } finally { setBusy(null); }
  }
  async function remove(s: PolScenarioRow) {
    if (!window.confirm(`Delete "${s.title}"? This cannot be undone.`)) return;
    setBusy(s.id);
    try { await call(`politics/scenarios/${s.id}`, { method: "DELETE" }); setSel((x) => x.filter((i) => i !== s.id)); setCmp(null); setTick((n) => n + 1); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } finally { setBusy(null); }
  }
  async function compare() {
    setBusy("cmp"); setErr(null);
    try { setCmp(await post<PolCompare>("politics/compare", { ids: sel })); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } finally { setBusy(null); }
  }
  return (
    <div className="space-y-4">
      <Panel title="Saved political scenarios" badge={<span className="text-xs text-muted">Compare 2–4 of the same type</span>}>
        {err && <div className="mb-3"><ErrorPanel message={err} /></div>}
        {list === null && !err ? <p className="text-sm text-muted" aria-busy="true">Loading…</p> : list && list.length === 0 ? <Empty>No saved scenarios yet. Build one in a tool and press Save.</Empty> : (
          <ul className="divide-y divide-line">
            {list?.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-3 py-2.5">
                <input type="checkbox" checked={sel.includes(s.id)} onChange={() => toggle(s.id)} aria-label={`Select ${s.title} for comparison`} className="h-4 w-4 accent-[#8055f6]" />
                <div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold">{s.title}</div><div className="text-[11px] text-muted">{s.created_by_name} · {dt(s.created_at)}</div></div>
                <Badge tone="violet">{KIND_LABEL[s.kind]}</Badge>
                <button type="button" onClick={() => open(s.id)} disabled={busy === s.id} className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-violet/60 disabled:opacity-60">Open</button>
                <button type="button" onClick={() => remove(s)} disabled={busy === s.id} aria-label={`Delete ${s.title}`} className="rounded-lg p-1.5 text-muted hover:text-red-300 disabled:opacity-60"><Trash2 className="h-4 w-4" /></button>
              </li>))}
          </ul>)}
        <div className="mt-3"><button type="button" onClick={compare} disabled={sel.length < 2 || busy === "cmp"} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy === "cmp" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Compare selected ({sel.length})</button></div>
      </Panel>
      {cmp && <Panel title={`${KIND_LABEL[cmp.kind]} scenario comparison`}><CompareTable data={cmp} /><p className="mt-2 text-[11px] text-muted">{"Scenario arithmetic on entered assumptions. Not a poll, not a validated election forecast."}</p></Panel>}
    </div>
  );
}

export function PoliticsWorkspace() {
  const [tab, setTab] = useState<Tab>("coalition");
  const [adv, setAdv] = useAdvanced();
  const [coalition, setCoalition] = useState<CoalitionDraft>(defaultCoalition);
  const [turnout, setTurnout] = useState<TurnoutDraft>(defaultTurnout);
  const [policy, setPolicy] = useState<PolicyDraft>(defaultPolicy);
  const [version, setVersion] = useState(0);
  const bump = () => setVersion((v) => v + 1);

  function open(s: PolScenarioFull) {
    if (s.kind === "coalition") setCoalition(coalitionFrom(s.inputs));
    else if (s.kind === "turnout") setTurnout(turnoutFrom(s.inputs));
    else setPolicy(policyFrom(s.inputs));
    setTab(s.kind);
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div role="tablist" aria-label="Political Intelligence tools" className="inline-flex max-w-full overflow-x-auto rounded-xl border border-line bg-bg/60 p-1"
          onKeyDown={(e) => { const i = TABS.findIndex((t) => t[0] === tab); if (e.key === "ArrowRight") setTab(TABS[(i + 1) % TABS.length][0]); if (e.key === "ArrowLeft") setTab(TABS[(i + TABS.length - 1) % TABS.length][0]); }}>
          {TABS.map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} tabIndex={tab === id ? 0 : -1} onClick={() => setTab(id)} className={`whitespace-nowrap rounded-lg px-4 py-2 text-sm font-semibold ${tab === id ? "bg-primary text-white" : "text-muted hover:text-ink"}`}>{label}</button>)}
        </div>
        <Badge tone="amber">Scenario assumptions · not a forecast</Badge>
        <label className="ml-auto flex cursor-pointer items-center gap-2 text-sm"><input type="checkbox" checked={adv} onChange={(e) => setAdv(e.target.checked)} className="h-4 w-4 accent-[#8055f6]" /> Advanced analytics</label>
      </div>
      <div role="tabpanel">
        {tab === "coalition" && <CoalitionTool d={coalition} set={setCoalition} adv={adv} onSaved={bump} />}
        {tab === "turnout" && <TurnoutTool d={turnout} set={setTurnout} adv={adv} onSaved={bump} />}
        {tab === "policy" && <PolicyTool d={policy} set={setPolicy} adv={adv} onSaved={bump} />}
        {tab === "saved" && <SavedPanel key={version} onOpen={open} />}
      </div>
    </div>
  );
}
