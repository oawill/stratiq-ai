"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, Plus, Save, Trash2, X } from "lucide-react";
import type { CompareRow, GameAnalysis, ScenarioFull, ScenarioListRow, SensitivityResult } from "@/lib/types";
import { Badge, Empty, ErrorPanel, Panel, dt } from "../ui";
import { CompareExplain, ExplainToggle } from "../assistant/AssistantPanel";
import { useAdvanced } from "../useAdvanced";
import { AnalysisView, NashBadge, type GameDef } from "./AnalysisView";
import { TEMPLATES, type Template } from "./templates";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/app-api/${path}`, init);
  if (res.status === 204) return undefined as T;
  const j = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = j.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map((x: { msg?: string }) => x.msg).join("; ") : "Request failed");
  }
  return j as T;
}
const post = <T,>(path: string, body: unknown) =>
  call<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

const MAX_UI = 6;

interface Draft {
  title: string;
  notes: string;
  players: [string, string];
  rows: string[];
  cols: string[];
  cells: string[][][]; // cells[r][c] = [rowPlayerPayoff, colPlayerPayoff] as typed text
}

const fromTemplate = (t: Template): Draft => ({
  title: t.name,
  notes: "",
  players: [...t.players],
  rows: [...t.rows],
  cols: [...t.cols],
  cells: t.payoffs.map((r) => r.map((c) => c.map(String))),
});

const blank = (): Draft => ({
  title: "",
  notes: "",
  players: ["Player A", "Player B"],
  rows: ["Strategy 1", "Strategy 2"],
  cols: ["Strategy 1", "Strategy 2"],
  cells: [[["0", "0"], ["0", "0"]], [["0", "0"], ["0", "0"]]],
});

function parse(d: Draft): { game: GameDef } | { error: string } {
  const dup = (xs: string[]) => new Set(xs.map((x) => x.trim())).size !== xs.length;
  if (d.players.some((p) => !p.trim())) return { error: "Name both players." };
  if (d.players[0].trim() === d.players[1].trim()) return { error: "The two players need different names." };
  if (d.rows.some((x) => !x.trim()) || d.cols.some((x) => !x.trim())) return { error: "Every strategy needs a name." };
  if (dup(d.rows) || dup(d.cols)) return { error: "Strategy names must be unique for each player." };
  const payoffs: number[][][] = [];
  for (let r = 0; r < d.rows.length; r++) {
    const row: number[][] = [];
    for (let c = 0; c < d.cols.length; c++) {
      const cell = d.cells[r][c].map((s) => (s.trim() === "" ? NaN : Number(s)));
      if (cell.some((v) => !Number.isFinite(v) || Math.abs(v) > 1e9)) return { error: `Payoff in row "${d.rows[r]}", column "${d.cols[c]}" must be a number (at most 1,000,000,000 in size).` };
      row.push(cell);
    }
    payoffs.push(row);
  }
  return {
    game: { players: [d.players[0].trim(), d.players[1].trim()], rows: d.rows.map((x) => x.trim()), cols: d.cols.map((x) => x.trim()), payoffs },
  };
}

const matrixBody = (g: GameDef) => ({ row_strategies: g.rows, col_strategies: g.cols, payoffs: g.payoffs });
const field = "rounded-lg border border-line bg-bg/70 px-2 py-1.5 text-sm focus:border-violet focus:outline-none focus:ring-2 focus:ring-violet/40";

/* ------------------------------------------------------------------ editor */
function Editor({ d, set }: { d: Draft; set: (d: Draft) => void }) {
  const R = d.rows.length, C = d.cols.length;
  const rename = (kind: "rows" | "cols", i: number, v: string) => set({ ...d, [kind]: d[kind].map((x, j) => (j === i ? v : x)) });
  const setCell = (r: number, c: number, k: 0 | 1, v: string) =>
    set({ ...d, cells: d.cells.map((row, ri) => row.map((cell, ci) => (ri === r && ci === c ? (k === 0 ? [v, cell[1]] : [cell[0], v]) : cell))) });
  const addRow = () => set({ ...d, rows: [...d.rows, `Strategy ${R + 1}`], cells: [...d.cells, Array.from({ length: C }, () => ["0", "0"])] });
  const addCol = () => set({ ...d, cols: [...d.cols, `Strategy ${C + 1}`], cells: d.cells.map((r) => [...r, ["0", "0"]]) });
  const delRow = (i: number) => set({ ...d, rows: d.rows.filter((_, j) => j !== i), cells: d.cells.filter((_, j) => j !== i) });
  const delCol = (i: number) => set({ ...d, cols: d.cols.filter((_, j) => j !== i), cells: d.cells.map((r) => r.filter((_, j) => j !== i)) });
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        {[0, 1].map((i) => (
          <div key={i}>
            <label htmlFor={`player-${i}`} className="mb-1 block text-xs text-muted">{i === 0 ? "Row player (competitor 1)" : "Column player (competitor 2)"}</label>
            <input id={`player-${i}`} value={d.players[i]} maxLength={60} onChange={(e) => set({ ...d, players: i === 0 ? [e.target.value, d.players[1]] : [d.players[0], e.target.value] })} className={`${field} w-full`} />
          </div>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] border-separate border-spacing-1 text-sm">
          <caption className="sr-only">Payoff entry grid</caption>
          <thead>
            <tr>
              <th scope="col" className="text-[11px] font-normal text-muted">{d.players[0] || "Row"} ↓ / {d.players[1] || "Column"} →</th>
              {d.cols.map((c, ci) => (
                <th key={ci} scope="col" className="align-bottom">
                  <div className="flex items-center gap-1">
                    <input aria-label={`Column strategy ${ci + 1} name`} value={c} maxLength={60} onChange={(e) => rename("cols", ci, e.target.value)} className={`${field} w-full min-w-24 font-semibold`} />
                    {C > 2 && <button type="button" onClick={() => delCol(ci)} aria-label={`Remove column strategy ${c}`} className="rounded p-1 text-muted hover:text-red-300"><X className="h-3.5 w-3.5" /></button>}
                  </div>
                </th>
              ))}
              <th scope="col">{C < MAX_UI && <button type="button" onClick={addCol} className="flex items-center gap-1 whitespace-nowrap rounded-lg border border-dashed border-line px-2 py-1.5 text-xs text-muted hover:text-ink"><Plus className="h-3.5 w-3.5" aria-hidden="true" /> Column</button>}</th>
            </tr>
          </thead>
          <tbody>
            {d.rows.map((r, ri) => (
              <tr key={ri}>
                <th scope="row">
                  <div className="flex items-center gap-1">
                    <input aria-label={`Row strategy ${ri + 1} name`} value={r} maxLength={60} onChange={(e) => rename("rows", ri, e.target.value)} className={`${field} w-full min-w-24 font-semibold`} />
                    {R > 2 && <button type="button" onClick={() => delRow(ri)} aria-label={`Remove row strategy ${r}`} className="rounded p-1 text-muted hover:text-red-300"><X className="h-3.5 w-3.5" /></button>}
                  </div>
                </th>
                {d.cols.map((c, ci) => (
                  <td key={ci} className="rounded-lg border border-line bg-card/40 p-1">
                    <div className="flex gap-1">
                      <input inputMode="decimal" aria-label={`${d.players[0]} payoff: ${r} vs ${c}`} value={d.cells[ri][ci][0]} onChange={(e) => setCell(ri, ci, 0, e.target.value)} className={`${field} w-full min-w-14 text-right font-mono text-violet`} />
                      <input inputMode="decimal" aria-label={`${d.players[1]} payoff: ${r} vs ${c}`} value={d.cells[ri][ci][1]} onChange={(e) => setCell(ri, ci, 1, e.target.value)} className={`${field} w-full min-w-14 text-right font-mono text-cyan`} />
                    </div>
                  </td>
                ))}
                <td />
              </tr>
            ))}
            {R < MAX_UI && (
              <tr><td><button type="button" onClick={addRow} className="flex items-center gap-1 whitespace-nowrap rounded-lg border border-dashed border-line px-2 py-1.5 text-xs text-muted hover:text-ink"><Plus className="h-3.5 w-3.5" aria-hidden="true" /> Row</button></td></tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">Each cell: <span className="font-semibold text-violet">{d.players[0] || "row player"}</span> payoff, then <span className="font-semibold text-cyan">{d.players[1] || "column player"}</span> payoff. These are your assumptions, not forecasts.</p>
    </div>
  );
}

/* ------------------------------------------------------------------ sensitivity */
function Sensitivity({ g, gameKey }: { g: GameDef; gameKey: string }) {
  const [cell, setCell] = useState({ r: 0, c: 0 });
  const [player, setPlayer] = useState<"row" | "col">("row");
  const val = g.payoffs[Math.min(cell.r, g.rows.length - 1)]?.[Math.min(cell.c, g.cols.length - 1)]?.[player === "row" ? 0 : 1] ?? 0;
  const [lo, setLo] = useState("");
  const [hi, setHi] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [out, setOut] = useState<{ key: string; data: SensitivityResult } | null>(null);
  const r = Math.min(cell.r, g.rows.length - 1), c = Math.min(cell.c, g.cols.length - 1);
  const loN = lo === "" ? val - 5 : Number(lo), hiN = hi === "" ? val + 5 : Number(hi);
  const name = (x: { row: number; col: number }) => `(${g.rows[x.row]}, ${g.cols[x.col]})`;

  async function run() {
    setBusy(true); setErr(null);
    try {
      const data = await post<SensitivityResult>("business/sensitivity", { ...matrixBody(g), row: r, col: c, player, lo: loN, hi: hiN });
      setOut({ key: gameKey, data });
    } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } finally { setBusy(false); }
  }
  const shown = out && out.key === gameKey ? out.data : null;
  const total = shown ? shown.range[1] - shown.range[0] : 1;
  return (
    <Panel title="Payoff sensitivity" badge={<Badge tone="violet">Exact</Badge>}>
      <p className="mb-3 text-sm text-muted">Vary one payoff and see exactly where the set of pure Nash equilibria changes.</p>
      <div className="grid gap-3 sm:grid-cols-5">
        <div className="sm:col-span-2">
          <label htmlFor="sens-cell" className="mb-1 block text-xs text-muted">Payoff to vary</label>
          <select id="sens-cell" value={`${r}:${c}:${player}`} onChange={(e) => { const [a, b, p] = e.target.value.split(":"); setCell({ r: +a, c: +b }); setPlayer(p as "row" | "col"); setLo(""); setHi(""); setOut(null); }} className={`${field} w-full`}>
            {g.rows.flatMap((rn, ri) => g.cols.flatMap((cn, ci) => (["row", "col"] as const).map((p) => (
              <option key={`${ri}:${ci}:${p}`} value={`${ri}:${ci}:${p}`}>{g.players[p === "row" ? 0 : 1]} @ ({rn}, {cn}) = {g.payoffs[ri][ci][p === "row" ? 0 : 1]}</option>
            ))))}
          </select>
        </div>
        <div><label htmlFor="sens-lo" className="mb-1 block text-xs text-muted">From</label><input id="sens-lo" inputMode="decimal" value={lo} placeholder={String(val - 5)} onChange={(e) => setLo(e.target.value)} className={`${field} w-full font-mono`} /></div>
        <div><label htmlFor="sens-hi" className="mb-1 block text-xs text-muted">To</label><input id="sens-hi" inputMode="decimal" value={hi} placeholder={String(val + 5)} onChange={(e) => setHi(e.target.value)} className={`${field} w-full font-mono`} /></div>
        <div className="flex items-end"><button type="button" onClick={run} disabled={busy || !Number.isFinite(loN) || !Number.isFinite(hiN)} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-3 py-2 text-sm font-semibold text-white disabled:opacity-60">{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Run</button></div>
      </div>
      {err && <p role="alert" className="mt-2 text-sm text-red-300">{err}</p>}
      {out && !shown && <p className="mt-3 text-sm text-amber-300">The matrix changed since this result. Run again.</p>}
      {shown && (
        <div className="mt-4 space-y-3">
          <div className="flex h-8 overflow-hidden rounded-lg border border-line" role="img" aria-label="Equilibrium regions across the varied range">
            {shown.segments.map((s, i) => (
              <div key={i} style={{ width: `${((s.to - s.from) / total) * 100}%` }} className={`flex items-center justify-center overflow-hidden px-1 text-[10px] font-semibold ${s.pure_nash.length ? "bg-success/25 text-success" : "bg-amber-400/20 text-amber-300"} ${i ? "border-l border-bg" : ""}`}>{s.pure_nash.length}</div>
            ))}
          </div>
          <ul className="space-y-1.5 text-sm">
            {shown.segments.map((s, i) => (
              <li key={i} className="rounded-lg border border-line p-2">
                <span className="font-mono text-xs text-muted">{s.from} → {s.to}</span>{" "}
                {s.pure_nash.length ? <>pure Nash: {s.pure_nash.map(name).join(", ")}</> : <>no pure Nash equilibrium</>}
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted">
            {shown.thresholds.length ? <>Equilibria change exactly at: {shown.thresholds.join(", ")} (where the varied payoff ties with a payoff it is compared against). At a tie point: {shown.at_points.filter((p) => shown.thresholds.includes(p.value)).map((p) => `${p.value} → ${p.pure_nash.map(name).join(", ") || "none"}`).join("; ")}.</> : <>No change in equilibria anywhere in this range.</>}
          </p>
        </div>
      )}
    </Panel>
  );
}

/* ------------------------------------------------------------------ saved scenarios & comparison */
function CompareTable({ rows }: { rows: CompareRow[] }) {
  const cell = "border-t border-line px-3 py-2 align-top text-sm";
  const nm = (x: { row: string; col: string }) => `(${x.row}, ${x.col})`;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px] text-left">
        <caption className="sr-only">Scenario comparison</caption>
        <thead><tr><th scope="col" className="px-3 py-2 text-xs font-normal text-muted">&nbsp;</th>{rows.map((r) => <th key={r.id} scope="col" className="px-3 py-2 text-sm font-semibold">{r.title}</th>)}</tr></thead>
        <tbody>
          <tr><th scope="row" className={`${cell} font-normal text-muted`}>Players</th>{rows.map((r) => <td key={r.id} className={cell}>{r.players.join(" vs ")}</td>)}</tr>
          <tr><th scope="row" className={`${cell} font-normal text-muted`}>Size</th>{rows.map((r) => <td key={r.id} className={cell}>{r.row_strategies.length} × {r.col_strategies.length}</td>)}</tr>
          <tr><th scope="row" className={`${cell} font-normal text-muted`}>Pure Nash equilibria</th>{rows.map((r) => <td key={r.id} className={cell}>{r.pure_nash.length ? r.pure_nash.map((n) => <div key={nm(n)}>{nm(n)} <span className="font-mono text-xs text-muted">→ {n.payoffs.join(" / ")}</span></div>) : "None"}</td>)}</tr>
          <tr><th scope="row" className={`${cell} font-normal text-muted`}>Strictly dominant strategy</th>{rows.map((r) => <td key={r.id} className={cell}><div>{r.players[0]}: {r.row_dominant ?? "none"}</div><div>{r.players[1]}: {r.col_dominant ?? "none"}</div></td>)}</tr>
          <tr><th scope="row" className={`${cell} font-normal text-muted`}>Highest combined payoff</th>{rows.map((r) => <td key={r.id} className={cell}><span className="font-mono">{r.max_welfare.value}</span> at {r.max_welfare.cells.map(nm).join(", ")}</td>)}</tr>
          <tr><th scope="row" className={`${cell} font-normal text-muted`}>Mixed equilibrium (2×2)</th>{rows.map((r) => <td key={r.id} className={cell}>{r.mixed_2x2 ? <>{r.players[0]} plays {r.row_strategies[0]} w.p. {r.mixed_2x2.row_probs_exact[0]}<br />{r.players[1]} plays {r.col_strategies[0]} w.p. {r.mixed_2x2.col_probs_exact[0]}</> : "—"}</td>)}</tr>
          <tr><th scope="row" className={`${cell} font-normal text-muted`}>Notes</th>{rows.map((r) => <td key={r.id} className={`${cell} text-xs text-muted`}>{r.notes.join(" ") || "—"}</td>)}</tr>
        </tbody>
      </table>
    </div>
  );
}

function SavedPanel({ onLoad }: { onLoad: (s: ScenarioFull) => void }) {
  const [list, setList] = useState<ScenarioListRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<string[]>([]);
  const [cmp, setCmp] = useState<CompareRow[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let live = true;
    call<{ scenarios: ScenarioListRow[] }>("business/scenarios").then((d) => live && setList(d.scenarios)).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [reload]);

  const toggle = (id: string) => { setCmp(null); setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length < 4 ? [...s, id] : s)); };
  async function load(id: string) {
    setBusy(id); setErr(null);
    try { onLoad(await call<ScenarioFull>(`business/scenarios/${id}`)); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } finally { setBusy(null); }
  }
  async function remove(s: ScenarioListRow) {
    if (!window.confirm(`Delete "${s.title}"? This cannot be undone.`)) return;
    setBusy(s.id); setErr(null);
    try { await call(`business/scenarios/${s.id}`, { method: "DELETE" }); setSel((x) => x.filter((i) => i !== s.id)); setCmp(null); setReload((n) => n + 1); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } finally { setBusy(null); }
  }
  async function compare() {
    setBusy("cmp"); setErr(null);
    try { setCmp((await post<{ scenarios: CompareRow[] }>("business/compare", { ids: sel })).scenarios); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } finally { setBusy(null); }
  }
  return (
    <div className="space-y-4">
      <Panel title="Saved scenarios" badge={<span className="text-xs text-muted">Select 2–4 to compare</span>}>
        {err && <div className="mb-3"><ErrorPanel message={err} /></div>}
        {list === null && !err ? <p className="text-sm text-muted" aria-busy="true">Loading…</p> : list && list.length === 0 ? <Empty>No saved scenarios yet. Build one in the workspace tab and press Save.</Empty> : (
          <ul className="divide-y divide-line">
            {list?.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-3 py-2.5">
                <input type="checkbox" checked={sel.includes(s.id)} onChange={() => toggle(s.id)} aria-label={`Select ${s.title} for comparison`} className="h-4 w-4 accent-[#8055f6]" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold">{s.title}</div>
                  <div className="text-[11px] text-muted">{s.players.join(" vs ")} · {s.rows_n}×{s.cols_n} · {s.created_by_name} · {dt(s.created_at)}</div>
                </div>
                <NashBadge n={s.nash_n} />
                <button type="button" onClick={() => load(s.id)} disabled={busy === s.id} className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-violet/60 disabled:opacity-60">Open</button>
                <button type="button" onClick={() => remove(s)} disabled={busy === s.id} aria-label={`Delete ${s.title}`} className="rounded-lg p-1.5 text-muted hover:text-red-300 disabled:opacity-60"><Trash2 className="h-4 w-4" /></button>
              <ExplainToggle type="scenario" id={s.id} title={s.title} />
              </li>
            ))}
          </ul>
        )}
        <div className="mt-3">
          <button type="button" onClick={compare} disabled={sel.length < 2 || busy === "cmp"} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
            {busy === "cmp" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Compare selected ({sel.length})
          </button>
        </div>
        {sel.length >= 2 && <CompareExplain key={sel.join(",")} type="scenario" ids={sel} />}
      </Panel>
      {cmp && <Panel title="Scenario comparison"><CompareTable rows={cmp} /></Panel>}
    </div>
  );
}

/* ------------------------------------------------------------------ main */
type Solved = { key: string; analysis: GameAnalysis } | { key: string; error: string };

export function BusinessWorkspace() {
  const [tab, setTab] = useState<"work" | "saved">("work");
  const [adv, setAdv] = useAdvanced();
  const [draft, setDraft] = useState<Draft>(() => fromTemplate(TEMPLATES[0]));
  const [templateId, setTemplateId] = useState(TEMPLATES[0].id);
  const [solved, setSolved] = useState<Solved | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [version, setVersion] = useState(0);

  const parsed = useMemo(() => parse(draft), [draft]);
  const game = "game" in parsed ? parsed.game : null;
  const key = game ? JSON.stringify(matrixBody(game)) : "";

  useEffect(() => {
    if (!game) return;
    const t = setTimeout(() => {
      post<GameAnalysis>("business/solve", matrixBody(game))
        .then((analysis) => setSolved({ key, analysis }))
        .catch((e) => setSolved({ key, error: e instanceof Error ? e.message : "Could not solve" }));
    }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const current = solved && solved.key === key ? solved : null;
  const edit = (d: Draft) => { setDraft(d); setSaveMsg(null); };

  async function save() {
    if (!game) return;
    if (!draft.title.trim()) { setSaveMsg({ ok: false, text: "Give the scenario a title first." }); return; }
    setSaving(true); setSaveMsg(null);
    try {
      await post("business/scenarios", { ...matrixBody(game), title: draft.title.trim(), notes: draft.notes.trim() || null, players: game.players });
      setSaveMsg({ ok: true, text: "Saved. Find it under Saved & compare." });
      setVersion((v) => v + 1);
    } catch (e) { setSaveMsg({ ok: false, text: e instanceof Error ? e.message : "Could not save" }); } finally { setSaving(false); }
  }

  const TABS = [["work", "Scenario workspace"], ["saved", "Saved & compare"]] as const;
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div role="tablist" aria-label="Business modules" className="inline-flex rounded-xl border border-line bg-bg/60 p-1" onKeyDown={(e) => { if (e.key === "ArrowRight" || e.key === "ArrowLeft") setTab(tab === "work" ? "saved" : "work"); }}>
          {TABS.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={tab === id} tabIndex={tab === id ? 0 : -1} onClick={() => setTab(id)} className={`rounded-lg px-4 py-2 text-sm font-semibold ${tab === id ? "bg-primary text-white" : "text-muted hover:text-ink"}`}>{label}</button>
          ))}
        </div>
        <Badge tone="amber">Payoffs are your assumptions</Badge>
        <label className="ml-auto flex cursor-pointer items-center gap-2 text-sm">
          <input type="checkbox" checked={adv} onChange={(e) => setAdv(e.target.checked)} className="h-4 w-4 accent-[#8055f6]" /> Advanced analytics
        </label>
      </div>

      <div role="tabpanel">
        {tab === "saved" ? (
          <SavedPanel
            key={version}
            onLoad={(s) => {
              setDraft({ title: s.title, notes: s.notes ?? "", players: [s.players[0], s.players[1]], rows: s.row_strategies, cols: s.col_strategies, cells: s.payoffs.map((r) => r.map((c) => c.map(String))) });
              setTemplateId(""); setSaveMsg(null); setTab("work");
            }}
          />
        ) : (
          <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
              <Panel className="lg:col-start-1" title="1 · Define the scenario">
                <div className="mb-4 grid gap-3 sm:grid-cols-2">
                  <div>
                    <label htmlFor="tpl" className="mb-1 block text-xs text-muted">Start from a template</label>
                    <select id="tpl" value={templateId} onChange={(e) => { const t = TEMPLATES.find((x) => x.id === e.target.value); if (t) { setTemplateId(t.id); edit(fromTemplate(t)); } }} className={`${field} w-full`}>
                      {templateId === "" && <option value="">Custom / saved scenario</option>}
                      {TEMPLATES.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </select>
                  </div>
                  <div className="flex items-end"><button type="button" onClick={() => { setTemplateId(""); edit(blank()); }} className="w-full rounded-lg border border-line px-3 py-2 text-sm font-semibold hover:border-violet/60">New blank scenario</button></div>
                </div>
                {TEMPLATES.find((t) => t.id === templateId) && <p className="mb-3 text-xs text-muted">{TEMPLATES.find((t) => t.id === templateId)!.blurb} Illustrative numbers, not market data.</p>}
                <Editor d={draft} set={(d) => { edit(d); setTemplateId(""); }} />
              </Panel>
              <Panel className="lg:col-start-2" title="2 · Equilibrium analysis" badge={<Badge tone="green">Deterministic solver</Badge>}>
                {"error" in parsed ? <p role="alert" className="text-sm text-amber-300">{parsed.error}</p>
                  : !current ? <p className="flex items-center gap-2 text-sm text-muted" aria-busy="true"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Solving…</p>
                  : "error" in current ? <ErrorPanel message={current.error} />
                  : <AnalysisView g={parsed.game} a={current.analysis} adv={adv} />}
              </Panel>
              {adv && game && <div className="min-w-0 lg:col-start-2"><Sensitivity g={game} gameKey={key} /></div>}
              <Panel className="lg:col-start-1" title="3 · Save">
                <div className="space-y-3">
                  <div><label htmlFor="sc-title" className="mb-1 block text-xs text-muted">Scenario title</label><input id="sc-title" value={draft.title} maxLength={120} onChange={(e) => edit({ ...draft, title: e.target.value })} className={`${field} w-full`} /></div>
                  <div><label htmlFor="sc-notes" className="mb-1 block text-xs text-muted">Notes (optional)</label><textarea id="sc-notes" value={draft.notes} maxLength={2000} rows={2} onChange={(e) => edit({ ...draft, notes: e.target.value })} className={`${field} w-full`} /></div>
                  <button type="button" onClick={save} disabled={saving || !game} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
                    {saving ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />} Save scenario
                  </button>
                  {saveMsg && <p role={saveMsg.ok ? "status" : "alert"} className={`text-sm ${saveMsg.ok ? "text-success" : "text-red-300"}`}>{saveMsg.text}</p>}
                </div>
              </Panel>
          </div>
        )}
      </div>
    </div>
  );
}
