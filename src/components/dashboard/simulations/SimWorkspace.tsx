"use client";

import { useEffect, useMemo, useState } from "react";
import { Download, Loader2, Play, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { call, post } from "@/lib/client";
import type { DistType, SimCompare, SimRun, SimRunRow } from "@/lib/types";
import { Badge, Empty, ErrorPanel, Panel, dt } from "../ui";
import { useAdvanced } from "../useAdvanced";
import { Histogram, OutputCard, Provenance, fmt } from "./Results";
import { DIST_FIELDS, DOMAINS, TEMPLATES, type DomainId, type SimTemplate } from "./templates";

/* ------------------------------------------------------------------ draft model */
interface VarDraft { name: string; type: DistType; params: Record<string, string> }
interface OutDraft { name: string; expr: string; threshold: string }
interface Draft { title: string; domain: DomainId; iterations: number; seed: string; notes: string; vars: VarDraft[]; outs: OutDraft[] }

const ITERATIONS = [1000, 10000, 50000, 100000, 200000];

const fromTemplate = (t: SimTemplate): Draft => ({
  title: t.name, domain: t.domain, iterations: 10000, seed: "", notes: "",
  vars: t.vars.map((v) => ({ ...v, params: { ...v.params } })), outs: t.outs.map((o) => ({ ...o })),
});
const blank = (domain: DomainId): Draft => ({
  title: "", domain, iterations: 10000, seed: "", notes: "",
  vars: [{ name: "x", type: "normal", params: { ...DIST_FIELDS.normal.defaults } }],
  outs: [{ name: "result", expr: "x", threshold: "" }],
});

type Model = { variables: { name: string; dist: Record<string, unknown> }[]; outputs: { name: string; expr: string; threshold: number | null }[] };

function toModel(d: Draft): { model: Model } | { error: string } {
  const variables: Model["variables"] = [];
  for (const v of d.vars) {
    const dist: Record<string, unknown> = { type: v.type };
    if (v.type === "discrete") {
      const items = v.params.values.split(",").map((p) => p.trim()).filter(Boolean).map((p) => p.split(":").map((x) => Number(x.trim())));
      if (items.length < 2 || items.some((i) => i.length !== 2 || i.some((x) => !Number.isFinite(x)))) return { error: `"${v.name}": enter values as value:probability, e.g. 0:0.5, 1:0.5` };
      dist.values = items.map(([value, p]) => ({ value, p }));
    } else {
      for (const f of DIST_FIELDS[v.type].fields) {
        const n = Number(v.params[f.key]);
        if (v.params[f.key]?.trim() === "" || !Number.isFinite(n)) return { error: `"${v.name}": ${f.label} must be a number.` };
        dist[f.key] = n;
      }
    }
    variables.push({ name: v.name.trim(), dist });
  }
  const outputs: Model["outputs"] = [];
  for (const o of d.outs) {
    const th = o.threshold.trim() === "" ? null : Number(o.threshold);
    if (th !== null && !Number.isFinite(th)) return { error: `"${o.name}": threshold must be a number or empty.` };
    outputs.push({ name: o.name.trim(), expr: o.expr.trim(), threshold: th });
  }
  return { model: { variables, outputs } };
}

function seedOf(d: Draft): { seed: number | null } | { error: string } {
  if (d.seed.trim() === "") return { seed: null };
  const n = Number(d.seed);
  if (!Number.isInteger(n) || n < 0 || n >= 2 ** 31) return { error: "Seed must be a whole number from 0 to 2147483647 (or leave empty for a random seed)." };
  return { seed: n };
}

function draftFromRun(r: SimRun): Draft {
  return {
    title: `${r.title} (copy)`, domain: (DOMAINS.find((d) => d[0] === r.domain)?.[0] ?? "general") as DomainId, iterations: ITERATIONS.includes(r.iterations) ? r.iterations : 10000,
    seed: String(r.seed), notes: r.config.notes ?? "",
    vars: r.config.variables.map((v) => {
      const type = v.dist.type as DistType;
      const params: Record<string, string> = {};
      if (type === "discrete") params.values = (v.dist.values as { value: number; p: number }[]).map((x) => `${x.value}:${x.p}`).join(", ");
      else for (const f of DIST_FIELDS[type].fields) params[f.key] = String(v.dist[f.key]);
      return { name: v.name, type, params };
    }),
    outs: r.config.outputs.map((o) => ({ name: o.name, expr: o.expr, threshold: o.threshold == null ? "" : String(o.threshold) })),
  };
}

const field = "rounded-lg border border-line bg-bg/70 px-2 py-1.5 text-sm focus:border-violet focus:outline-none focus:ring-2 focus:ring-violet/40";

/* ------------------------------------------------------------------ editor */
function Editor({ d, set, onRun, running, runError }: { d: Draft; set: (d: Draft) => void; onRun: () => void; running: boolean; runError: string | null }) {
  const model = useMemo(() => toModel(d), [d]);
  const modelKey = "model" in model ? JSON.stringify(model.model) : "";
  const [check, setCheck] = useState<{ key: string; ok: true; pilot: Record<string, { mean: number }> } | { key: string; ok: false; error: string } | null>(null);

  useEffect(() => {
    if (!modelKey) return;
    const t = setTimeout(() => {
      post<{ pilot: Record<string, { mean: number }> }>("simulations/validate", JSON.parse(modelKey))
        .then((r) => setCheck({ key: modelKey, ok: true, pilot: r.pilot }))
        .catch((e) => setCheck({ key: modelKey, ok: false, error: e instanceof Error ? e.message : "Invalid model" }));
    }, 450);
    return () => clearTimeout(t);
  }, [modelKey]);
  const current = check && check.key === modelKey ? check : null;
  const seed = seedOf(d);

  const setVar = (i: number, v: Partial<VarDraft>) => set({ ...d, vars: d.vars.map((x, j) => (j === i ? { ...x, ...v } : x)) });
  const setOut = (i: number, o: Partial<OutDraft>) => set({ ...d, outs: d.outs.map((x, j) => (j === i ? { ...x, ...o } : x)) });
  const canRun = "model" in model && !("error" in seed) && current?.ok === true && d.title.trim() !== "" && !running;

  return (
    <div className="space-y-4">
      <Panel title="1 · Scenario">
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label htmlFor="sim-domain" className="mb-1 block text-xs text-muted">Domain</label>
            <select id="sim-domain" value={d.domain} onChange={(e) => set({ ...d, domain: e.target.value as DomainId })} className={`${field} w-full`}>
              {DOMAINS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select>
          </div>
          <div className="sm:col-span-2">
            <label htmlFor="sim-template" className="mb-1 block text-xs text-muted">Start from an illustrative template</label>
            <select id="sim-template" value="" onChange={(e) => { const t = TEMPLATES.find((x) => x.id === e.target.value); if (t) set(fromTemplate(t)); else if (e.target.value === "blank") set(blank(d.domain)); }} className={`${field} w-full`}>
              <option value="">Choose…</option>
              <option value="blank">Blank scenario</option>
              {TEMPLATES.filter((t) => t.domain === d.domain || d.domain === "general").map((t) => <option key={t.id} value={t.id}>{DOMAINS.find((x) => x[0] === t.domain)![1]}: {t.name}</option>)}
            </select>
          </div>
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <div className="sm:col-span-3">
            <label htmlFor="sim-title" className="mb-1 block text-xs text-muted">Title</label>
            <input id="sim-title" value={d.title} maxLength={120} onChange={(e) => set({ ...d, title: e.target.value })} className={`${field} w-full`} />
          </div>
          <div>
            <label htmlFor="sim-iter" className="mb-1 block text-xs text-muted">Monte Carlo runs</label>
            <select id="sim-iter" value={d.iterations} onChange={(e) => set({ ...d, iterations: Number(e.target.value) })} className={`${field} w-full`}>
              {ITERATIONS.map((n) => <option key={n} value={n}>{n.toLocaleString()}</option>)}
            </select>
          </div>
          <div className="sm:col-span-2">
            <label htmlFor="sim-seed" className="mb-1 block text-xs text-muted">Random seed (same seed = same results)</label>
            <div className="flex gap-2">
              <input id="sim-seed" inputMode="numeric" value={d.seed} placeholder="random (recorded)" onChange={(e) => set({ ...d, seed: e.target.value })} className={`${field} w-full font-mono`} />
              <button type="button" onClick={() => set({ ...d, seed: String(Math.floor(Math.random() * 2 ** 31)) })} className="whitespace-nowrap rounded-lg border border-line px-3 text-xs font-semibold hover:border-violet/60">Pick one</button>
            </div>
            {"error" in seed && <p role="alert" className="mt-1 text-xs text-amber-300">{seed.error}</p>}
          </div>
        </div>
      </Panel>

      <Panel title="2 · Input variables" badge={<span className="text-xs text-muted">each drawn independently</span>}>
        <ul className="space-y-3">
          {d.vars.map((v, i) => (
            <li key={i} className="rounded-xl border border-line bg-card/40 p-3">
              <div className="flex flex-wrap items-end gap-2">
                <div className="w-32"><label htmlFor={`v-name-${i}`} className="mb-1 block text-[11px] text-muted">Name</label><input id={`v-name-${i}`} value={v.name} maxLength={30} onChange={(e) => setVar(i, { name: e.target.value })} className={`${field} w-full font-mono`} /></div>
                <div className="w-44"><label htmlFor={`v-type-${i}`} className="mb-1 block text-[11px] text-muted">Distribution</label>
                  <select id={`v-type-${i}`} value={v.type} onChange={(e) => { const t = e.target.value as DistType; setVar(i, { type: t, params: { ...DIST_FIELDS[t].defaults } }); }} className={`${field} w-full`}>
                    {(Object.keys(DIST_FIELDS) as DistType[]).map((t) => <option key={t} value={t}>{DIST_FIELDS[t].label}</option>)}
                  </select></div>
                {DIST_FIELDS[v.type].fields.map((f) => (
                  <div key={f.key} className={v.type === "discrete" ? "min-w-48 flex-1" : "w-24"}>
                    <label htmlFor={`v-${i}-${f.key}`} className="mb-1 block text-[11px] text-muted">{f.label}</label>
                    <input id={`v-${i}-${f.key}`} inputMode="decimal" value={v.params[f.key] ?? ""} onChange={(e) => setVar(i, { params: { ...v.params, [f.key]: e.target.value } })} className={`${field} w-full font-mono`} />
                  </div>
                ))}
                {d.vars.length > 1 && <button type="button" onClick={() => set({ ...d, vars: d.vars.filter((_, j) => j !== i) })} aria-label={`Remove variable ${v.name}`} className="rounded p-2 text-muted hover:text-red-300"><X className="h-4 w-4" /></button>}
              </div>
              <p className="mt-1 text-[11px] text-muted">{DIST_FIELDS[v.type].help}</p>
            </li>
          ))}
        </ul>
        {d.vars.length < 12 && <button type="button" onClick={() => set({ ...d, vars: [...d.vars, { name: `x${d.vars.length + 1}`, type: "normal", params: { ...DIST_FIELDS.normal.defaults } }] })} className="mt-3 inline-flex items-center gap-1 rounded-lg border border-dashed border-line px-3 py-1.5 text-xs text-muted hover:text-ink"><Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add variable</button>}
      </Panel>

      <Panel title="3 · Outputs (formulas)" badge={<span className="text-xs text-muted">+ − × ÷ ** % · min max abs sqrt exp log log10 floor ceil clip · comparisons · if/else</span>}>
        <ul className="space-y-3">
          {d.outs.map((o, i) => (
            <li key={i} className="flex flex-wrap items-end gap-2 rounded-xl border border-line bg-card/40 p-3">
              <div className="w-32"><label htmlFor={`o-name-${i}`} className="mb-1 block text-[11px] text-muted">Name</label><input id={`o-name-${i}`} value={o.name} maxLength={30} onChange={(e) => setOut(i, { name: e.target.value })} className={`${field} w-full font-mono`} /></div>
              <div className="min-w-52 flex-1"><label htmlFor={`o-expr-${i}`} className="mb-1 block text-[11px] text-muted">Formula</label><input id={`o-expr-${i}`} value={o.expr} maxLength={500} onChange={(e) => setOut(i, { expr: e.target.value })} className={`${field} w-full font-mono`} /></div>
              <div className="w-28"><label htmlFor={`o-th-${i}`} className="mb-1 block text-[11px] text-muted">P(output &gt; …)</label><input id={`o-th-${i}`} inputMode="decimal" value={o.threshold} placeholder="optional" onChange={(e) => setOut(i, { threshold: e.target.value })} className={`${field} w-full font-mono`} /></div>
              {d.outs.length > 1 && <button type="button" onClick={() => set({ ...d, outs: d.outs.filter((_, j) => j !== i) })} aria-label={`Remove output ${o.name}`} className="rounded p-2 text-muted hover:text-red-300"><X className="h-4 w-4" /></button>}
            </li>
          ))}
        </ul>
        {d.outs.length < 5 && <button type="button" onClick={() => set({ ...d, outs: [...d.outs, { name: `out${d.outs.length + 1}`, expr: "", threshold: "" }] })} className="mt-3 inline-flex items-center gap-1 rounded-lg border border-dashed border-line px-3 py-1.5 text-xs text-muted hover:text-ink"><Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add output</button>}
        <p className="mt-3 text-[11px] text-muted">Outputs can use input variables and earlier outputs. Formulas are parsed and checked; they are never executed as arbitrary code.</p>
      </Panel>

      <Panel title="4 · Check & run">
        <div aria-live="polite" className="mb-3 text-sm">
          {"error" in model ? <p className="text-amber-300">{model.error}</p>
            : !current ? <p className="flex items-center gap-2 text-muted"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Checking model…</p>
            : current.ok ? <p className="text-success">Model is valid. Pilot of 200 draws (throw-away): {Object.entries(current.pilot).map(([k, v]) => `${k} ≈ ${fmt(v.mean)}`).join(", ")}.</p>
            : <p role="alert" className="text-red-300">{current.error}</p>}
        </div>
        <div>
          <label htmlFor="sim-notes" className="mb-1 block text-xs text-muted">Notes / assumptions (optional)</label>
          <textarea id="sim-notes" rows={2} maxLength={2000} value={d.notes} onChange={(e) => set({ ...d, notes: e.target.value })} className={`${field} w-full`} />
        </div>
        <button type="button" onClick={onRun} disabled={!canRun} className="mt-3 inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50">
          {running ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Play className="h-4 w-4" aria-hidden="true" />} Run simulation
        </button>
        {d.title.trim() === "" && <span className="ml-3 text-xs text-muted">Add a title to enable Run.</span>}
        {runError && <p role="alert" className="mt-2 text-sm text-red-300">{runError}</p>}
      </Panel>
    </div>
  );
}

/* ------------------------------------------------------------------ run view */
const STATUS_TONE = { queued: "muted", running: "cyan", completed: "green", failed: "amber", cancelled: "muted" } as const;

function RunView({ id, expectHash, adv, onEdit, onReproduce }: { id: string; expectHash?: string; adv: boolean; onEdit: (r: SimRun) => void; onReproduce: (r: SimRun) => void }) {
  const [run, setRun] = useState<SimRun | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const r = await call<SimRun>(`simulations/runs/${id}`);
        if (!live) return;
        setRun(r); setErr(null);
        if (r.status === "queued" || r.status === "running") timer = setTimeout(tick, 900);
      } catch (e) {
        if (!live) return;
        setErr(e instanceof Error ? e.message : "Could not load the run");
        timer = setTimeout(tick, 3000);
      }
    };
    tick();
    return () => { live = false; if (timer) clearTimeout(timer); };
  }, [id]);

  async function cancel() {
    setBusy(true);
    try { await post(`simulations/runs/${id}/cancel`, {}); } catch (e) { setErr(e instanceof Error ? e.message : "Could not cancel"); } finally { setBusy(false); }
  }

  if (!run) return err ? <ErrorPanel message={err} /> : <p className="text-sm text-muted" aria-busy="true">Loading run…</p>;
  const active = run.status === "queued" || run.status === "running";
  const pct = Math.round(run.progress * 100);
  const thr = Object.fromEntries(run.config.outputs.map((o) => [o.name, o.threshold]));
  return (
    <div className="space-y-4">
      <Panel title={run.title} badge={<Badge tone={STATUS_TONE[run.status]}>{run.status}</Badge>}>
        <p className="text-xs text-muted">{DOMAINS.find((d) => d[0] === run.domain)?.[1]} · {run.iterations.toLocaleString()} runs · seed {run.seed} · started by {run.created_by_name} · {dt(run.created_at)}</p>
        {active && (
          <div className="mt-3">
            <div className="flex justify-between text-xs text-muted"><span>{run.status === "queued" ? "Waiting for a worker…" : "Running…"}</span><span className="font-mono">{pct}%</span></div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-white/10" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Simulation progress">
              <div className="h-full rounded-full bg-primary transition-all duration-300" style={{ width: `${pct}%` }} />
            </div>
            <button type="button" onClick={cancel} disabled={busy} className="mt-3 rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-red-400/60 disabled:opacity-60">Cancel run</button>
          </div>
        )}
        {run.status === "failed" && <div className="mt-3"><ErrorPanel message={run.error ?? "The run failed."} /></div>}
        {run.status === "cancelled" && <p className="mt-3 text-sm text-muted">This run was cancelled. No results were stored.</p>}
        {err && <p role="alert" className="mt-2 text-sm text-red-300">{err}</p>}
        {run.status === "completed" && run.result && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {expectHash && (run.result.result_hash === expectHash
              ? <Badge tone="green">Reproduced: identical to the original run</Badge>
              : <Badge tone="amber">Differs from the original run</Badge>)}
            {(["md", "csv", "json"] as const).map((f) => (
              <a key={f} href={`/app-api/simulations/runs/${id}/report?format=${f}`} download className="inline-flex items-center gap-1 rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-violet/60"><Download className="h-3.5 w-3.5" aria-hidden="true" /> {f === "md" ? "Report (Markdown)" : f.toUpperCase()}</a>
            ))}
            <button type="button" onClick={() => onReproduce(run)} className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-violet/60">Reproduce with same seed</button>
          </div>
        )}
        <button type="button" onClick={() => onEdit(run)} className="mt-3 rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-violet/60">Edit as new simulation</button>
      </Panel>
      {run.result && Object.entries(run.result.outputs).map(([name, o]) => <OutputCard key={name} name={name} o={o} adv={adv} n={run.result!.iterations} seed={run.result!.seed} threshold={thr[name]} />)}
      {run.result && adv && <Provenance r={run.result} />}
      {run.result && !adv && <p className="text-xs text-muted">Turn on <strong>Advanced analytics</strong> for percentiles, sensitivity, convergence and provenance.</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ runs list & comparison */
function CompareView({ data }: { data: SimCompare }) {
  const cell = "border-t border-line px-3 py-1.5 text-sm font-mono";
  return (
    <div className="space-y-4">
      {data.outputs.map((row) => (
        <Panel key={row.output} title={`Comparison: ${row.output}`}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left">
              <caption className="sr-only">Comparison of {row.output} across runs</caption>
              <thead><tr className="text-[11px] text-muted">{["Run", "Mean", "Std dev", "5%", "Median", "95%", "P(>thr)", "Mean vs first (95% CI)"].map((h) => <th key={h} scope="col" className="px-3 py-1 font-normal">{h}</th>)}</tr></thead>
              <tbody>{row.runs.map((r, i) => r && (
                <tr key={i}>
                  <th scope="row" className={`${cell} font-sans font-semibold`}>{r.title}<div className="text-[10px] font-normal text-muted">seed {r.seed} · {r.iterations.toLocaleString()}</div></th>
                  <td className={cell}>{fmt(r.mean)}</td><td className={cell}>{fmt(r.sd)}</td><td className={cell}>{fmt(r.p05)}</td><td className={cell}>{fmt(r.p50)}</td><td className={cell}>{fmt(r.p95)}</td>
                  <td className={cell}>{r.prob_above ? `${(r.prob_above.p * 100).toFixed(1)}%` : "—"}</td>
                  <td className={cell}>{row.diff_vs_first[i] ? `${row.diff_vs_first[i]!.mean_diff >= 0 ? "+" : ""}${fmt(row.diff_vs_first[i]!.mean_diff)} (${fmt(row.diff_vs_first[i]!.ci95[0])} to ${fmt(row.diff_vs_first[i]!.ci95[1])})` : "baseline"}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {data.runs.map((r) => r.histograms[row.output] && (
              <div key={r.id}><div className="mb-1 truncate text-xs font-semibold">{r.title}</div><Histogram h={r.histograms[row.output]} label={`${row.output} (${r.title})`} /></div>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-muted">Each histogram has its own horizontal scale. Differences use independent-sample standard errors; they describe sampling noise only, not model risk.</p>
        </Panel>
      ))}
    </div>
  );
}

function RunsList({ openId, onOpen }: { openId: string | null; onOpen: (id: string) => void }) {
  // Refetch whenever a different run is opened or created (openId changes), and while any run is active.
  const [runs, setRuns] = useState<SimRunRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<string[]>([]);
  const [cmp, setCmp] = useState<SimCompare | null>(null);
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);
  const anyActive = !!runs?.some((r) => r.status === "queued" || r.status === "running");

  useEffect(() => {
    let live = true;
    call<{ runs: SimRunRow[] }>("simulations/runs").then((d) => live && (setRuns(d.runs), setErr(null))).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [tick, openId]);
  useEffect(() => {
    if (!anyActive) return;
    const t = setTimeout(() => setTick((n) => n + 1), 2500);
    return () => clearTimeout(t);
  }, [anyActive, tick]);

  const toggle = (id: string) => { setCmp(null); setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length < 4 ? [...s, id] : s)); };
  async function compare() {
    setBusy(true); setErr(null);
    try { setCmp(await post<SimCompare>("simulations/compare", { ids: sel })); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } finally { setBusy(false); }
  }
  async function remove(r: SimRunRow) {
    if (!window.confirm(`Delete "${r.title}"? This cannot be undone.`)) return;
    try { await call(`simulations/runs/${r.id}`, { method: "DELETE" }); setSel((s) => s.filter((x) => x !== r.id)); setCmp(null); setTick((n) => n + 1); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); }
  }
  return (
    <div className="space-y-4">
      <Panel title="Simulation runs" badge={<button type="button" onClick={() => setTick((n) => n + 1)} className="inline-flex items-center gap-1 text-xs text-violet hover:underline"><RefreshCw className="h-3 w-3" aria-hidden="true" /> Refresh</button>}>
        {err && <div className="mb-3"><ErrorPanel message={err} /></div>}
        {runs === null && !err ? <p className="text-sm text-muted" aria-busy="true">Loading…</p> : runs && runs.length === 0 ? <Empty>No runs yet. Configure one in “New simulation”.</Empty> : (
          <ul className="divide-y divide-line">
            {runs?.map((r) => (
              <li key={r.id} className={`flex flex-wrap items-center gap-3 py-2.5 ${openId === r.id ? "bg-primary/5" : ""}`}>
                <input type="checkbox" disabled={r.status !== "completed"} checked={sel.includes(r.id)} onChange={() => toggle(r.id)} aria-label={`Select ${r.title} for comparison`} className="h-4 w-4 accent-[#8055f6] disabled:opacity-30" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold">{r.title}</div>
                  <div className="text-[11px] text-muted">{DOMAINS.find((d) => d[0] === r.domain)?.[1]} · {r.iterations.toLocaleString()} runs · seed {r.seed} · {dt(r.created_at)}</div>
                </div>
                {(r.status === "running" || r.status === "queued") && <span className="font-mono text-xs text-muted">{Math.round(r.progress * 100)}%</span>}
                <Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge>
                <button type="button" onClick={() => onOpen(r.id)} className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-violet/60">Open</button>
                <button type="button" onClick={() => remove(r)} disabled={r.status === "running" || r.status === "queued"} aria-label={`Delete ${r.title}`} className="rounded-lg p-1.5 text-muted hover:text-red-300 disabled:opacity-30"><Trash2 className="h-4 w-4" /></button>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-3 flex items-center gap-3">
          <button type="button" onClick={compare} disabled={sel.length < 2 || busy} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
            {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Compare selected ({sel.length})
          </button>
          <span className="text-xs text-muted">Pick 2–4 completed runs.</span>
        </div>
      </Panel>
      {cmp && <CompareView data={cmp} />}
    </div>
  );
}

/* ------------------------------------------------------------------ main */
export function SimWorkspace() {
  const [tab, setTab] = useState<"new" | "runs">("new");
  const [adv, setAdv] = useAdvanced();
  const [draft, setDraft] = useState<Draft>(() => fromTemplate(TEMPLATES.find((t) => t.id === "launch")!));
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [expectHash, setExpectHash] = useState<string | undefined>();

  async function start(d: Draft, hashToMatch?: string) {
    const m = toModel(d), s = seedOf(d);
    if ("error" in m) return setRunError(m.error);
    if ("error" in s) return setRunError(s.error);
    setRunning(true); setRunError(null);
    try {
      const r = await post<{ id: string }>("simulations/runs", { ...m.model, title: d.title.trim(), domain: d.domain, iterations: d.iterations, seed: s.seed, notes: d.notes.trim() || null });
      setExpectHash(hashToMatch); setOpenId(r.id); setTab("runs");
    } catch (e) { setRunError(e instanceof Error ? e.message : "Could not start the run"); } finally { setRunning(false); }
  }

  const TABS = [["new", "New simulation"], ["runs", "Runs & results"]] as const;
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div role="tablist" aria-label="Simulation Lab" className="inline-flex rounded-xl border border-line bg-bg/60 p-1" onKeyDown={(e) => { if (e.key === "ArrowRight" || e.key === "ArrowLeft") setTab(tab === "new" ? "runs" : "new"); }}>
          {TABS.map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} tabIndex={tab === id ? 0 : -1} onClick={() => setTab(id)} className={`rounded-lg px-4 py-2 text-sm font-semibold ${tab === id ? "bg-primary text-white" : "text-muted hover:text-ink"}`}>{label}</button>)}
        </div>
        <Badge tone="amber">Inputs are your assumptions</Badge>
        <label className="ml-auto flex cursor-pointer items-center gap-2 text-sm"><input type="checkbox" checked={adv} onChange={(e) => setAdv(e.target.checked)} className="h-4 w-4 accent-[#8055f6]" /> Advanced analytics</label>
      </div>
      <div role="tabpanel">
        {tab === "new" ? (
          <Editor d={draft} set={setDraft} onRun={() => start(draft)} running={running} runError={runError} />
        ) : (
          <div className="space-y-4">
            <RunsList openId={openId} onOpen={(id) => { setExpectHash(undefined); setOpenId(id); }} />
            {openId && (
              <RunView
                key={openId}
                id={openId}
                expectHash={expectHash}
                adv={adv}
                onEdit={(r) => { setDraft(draftFromRun(r)); setTab("new"); }}
                onReproduce={(r) => start({ ...draftFromRun(r), title: `${r.title} (reproduction)` }, r.result?.result_hash)}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
