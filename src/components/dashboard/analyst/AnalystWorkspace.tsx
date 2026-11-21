"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Loader2, MessageSquarePlus, RotateCcw, Send, Trash2 } from "lucide-react";
import { call } from "@/lib/client";
import { Badge, ErrorPanel, Panel, dt } from "../ui";
import { field } from "../analysis";

interface Citation { id: string; kind: string; label: string; source: string; retrieved_at: string; window: string | null; model_version: string | null; href: string | null }
interface Block { type: "table" | "bars" | "proposal"; title: string; columns?: string[]; rows?: (string | number | null)[][]; items?: { label: string; value: number }[]; unit?: string; detail?: string; adjustments?: Record<string, number>; matchup?: string; action?: string }
interface Trust { data_sources: string[]; retrieved_at: string | null; observation_windows: string[]; model_versions: string[]; assumptions: string[]; limitations: string[]; unavailable: string[] }
interface ToolCall { tool: string; ok: boolean; available: boolean | null; reason: string | null }
interface Msg { id: string; role: "user" | "assistant"; text: string; blocks: Block[]; proposals: Block[]; citations: Citation[]; trust: Trust | null; tools: ToolCall[]; mode?: string; notices: string[]; pending?: boolean; status?: string; error?: string }
interface ConvRow { id: string; title: string; updated_at: string; messages: number }
interface Status { llm_configured: boolean; mode: string; retention_days: number; suggested_questions: string[]; limits: { per_minute: number; per_day: number; max_question_chars: number; max_tool_calls: number }; tools: { name: string; description: string }[]; note: string }

const MODE_LABEL: Record<string, string> = { grounded_rules: "Built-in rules over retrieved records", language_model: "Language model, checked against retrieved records" };
let counter = 0;
const uid = () => `m${Date.now()}-${counter++}`;

function pctText(v: unknown): string {
  return typeof v === "number" ? `${(v * 100).toFixed(1)}%` : String(v ?? "n/a");
}
function cell(col: string, v: string | number | null): string {
  if (v === null || v === undefined) return "n/a";
  if (typeof v === "number") return /probab/i.test(col) ? pctText(v) : Number.isInteger(v) ? String(v) : String(Math.round(v * 1000) / 1000);
  return v;
}

function Blocks({ blocks }: { blocks: Block[] }) {
  return (
    <div className="space-y-3">
      {blocks.map((b, i) => b.type === "bars" ? (
        <figure key={i} className="rounded-xl border border-line p-3">
          <figcaption className="mb-2 text-xs font-semibold text-muted">{b.title}</figcaption>
          <ul className="space-y-1.5" aria-label={b.title}>{(b.items ?? []).map((it) => (
            <li key={it.label}><div className="flex justify-between text-xs"><span>{it.label}</span><span className="font-mono">{(it.value * 100).toFixed(1)}%</span></div>
              <div className="h-2 rounded bg-white/10" aria-hidden="true"><div className="h-2 rounded bg-cyan" style={{ width: `${Math.max(1, it.value * 100)}%` }} /></div></li>
          ))}</ul>
        </figure>
      ) : b.type === "table" ? (
        <div key={i} className="overflow-x-auto rounded-xl border border-line p-3">
          <table className="w-full text-xs"><caption className="mb-1 text-left font-semibold text-muted">{b.title}</caption>
            <thead><tr className="text-left text-[11px] text-muted">{(b.columns ?? []).map((c) => <th key={c} scope="col" className="pr-3 font-normal">{c}</th>)}</tr></thead>
            <tbody className="font-mono">{(b.rows ?? []).map((r, ri) => <tr key={ri} className="border-t border-line">{r.map((v, ci) => <td key={ci} className="py-1 pr-3">{cell((b.columns ?? [])[ci] ?? "", v)}</td>)}</tr>)}</tbody></table>
        </div>
      ) : null)}
    </div>
  );
}

function Proposals({ items }: { items: Block[] }) {
  if (!items.length) return null;
  return (
    <div className="space-y-2" role="group" aria-label="Suggested hypothetical scenarios">
      {items.map((p, i) => (
        <div key={i} className="rounded-xl border-2 border-dashed border-amber-400/60 p-3 text-sm">
          <p className="font-semibold">{p.title} <Badge tone="amber">Suggestion: needs your approval</Badge></p>
          <p className="mt-1 text-xs text-muted">{p.matchup}. {p.detail}</p>
          <p className="mt-1 font-mono text-xs">{Object.entries(p.adjustments ?? {}).map(([k, v]) => `${k.replace(/_/g, " ")} = ${v}`).join("; ")}</p>
          <p className="mt-1 text-xs text-amber-200">{p.action} <a href="/dashboard/simulations" className="underline">Open SimLab</a></p>
        </div>
      ))}
    </div>
  );
}

function Sources({ m }: { m: Msg }) {
  if (!m.citations.length && !m.trust && !m.tools.length) return null;
  const t = m.trust;
  return (
    <details className="rounded-xl border border-line p-3 text-xs">
      <summary className="cursor-pointer text-sm font-semibold">Sources and how this answer was made</summary>
      <div className="mt-3 space-y-3">
        {m.mode && <p><span className="text-muted">Method: </span>{MODE_LABEL[m.mode] ?? m.mode}.</p>}
        {m.tools.length > 0 && <p><span className="text-muted">Records retrieved: </span>{m.tools.map((x) => `${x.tool}${x.ok ? (x.available === false ? " (no data)" : "") : " (not allowed)"}`).join(", ")}</p>}
        {m.citations.length > 0 && (
          <ol className="space-y-1.5" aria-label="Sources">{m.citations.map((c) => (
            <li key={c.id} id={`src-${m.id}-${c.id}`} className="rounded-lg bg-white/5 p-2"><span className="font-mono font-semibold">[{c.id}]</span> {c.label}<br />
              <span className="text-muted">{c.source}. Retrieved {dt(c.retrieved_at)}.{c.window && ` Window: ${c.window}.`}{c.model_version && ` Model version: ${c.model_version}.`}</span>{c.href && <> <a href={c.href} className="text-violet underline">Open</a></>}</li>
          ))}</ol>
        )}
        {t && t.assumptions.length > 0 && <div><p className="font-semibold">Key assumptions</p><ul className="list-disc pl-5 text-muted">{t.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></div>}
        {t && t.limitations.length > 0 && <div><p className="font-semibold">Known limitations</p><ul className="list-disc pl-5 text-muted">{t.limitations.map((a) => <li key={a}>{a}</li>)}</ul></div>}
        {t && t.unavailable.length > 0 && <div><p className="font-semibold">Not available</p><ul className="list-disc pl-5 text-muted">{t.unavailable.map((a) => <li key={a}>{a}</li>)}</ul></div>}
      </div>
    </details>
  );
}

function AnswerText({ m }: { m: Msg }) {
  const parts = m.text.split(/\n{2,}/);
  const linkify = (s: string) => s.split(/(\[S\d+\])/g).map((tok, i) => {
    const id = /^\[(S\d+)\]$/.exec(tok)?.[1];
    return id ? <a key={i} href={`#src-${m.id}-${id}`} aria-label={`Source ${id}`} className="align-super text-[10px] text-cyan underline" onClick={(e) => { const d = (e.currentTarget.closest("[data-msg]")?.querySelector("details") as HTMLDetailsElement | null); if (d) d.open = true; }}>{id}</a> : <span key={i}>{tok}</span>;
  });
  return <div className="space-y-2 text-sm leading-relaxed">{parts.map((p, i) => <p key={i}>{linkify(p)}</p>)}</div>;
}

function fromStored(m: { id: string; role: "user" | "assistant"; content: string; blocks: Block[] | null; citations: Citation[] | null; trust: Trust | null; tool_calls: ToolCall[] | null; proposals: Block[] | null; mode: string | null }): Msg {
  return { id: m.id, role: m.role, text: m.content, blocks: m.blocks ?? [], proposals: m.proposals ?? [], citations: m.citations ?? [], trust: m.trust, tools: m.tool_calls ?? [], mode: m.mode ?? undefined, notices: [] };
}

/** The AI Analyst: ask about the user's own data, forecasts and saved simulations. Answers carry sources, timestamps and assumptions. */
export function AnalystWorkspace() {
  const [status, setStatus] = useState<Status | null>(null);
  const [convs, setConvs] = useState<ConvRow[] | null>(null);
  const [cid, setCid] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [save, setSave] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [lastQ, setLastQ] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  const loadList = useCallback(() => call<{ conversations: ConvRow[] }>("analyst/conversations").then((d) => setConvs(d.conversations), (e) => setErr(e instanceof Error ? e.message : "Could not load conversations.")), []);
  useEffect(() => {
    let live = true;
    call<Status>("analyst/status").then((s) => live && setStatus(s), (e) => live && setErr(e instanceof Error ? e.message : "Could not load the Analyst."));
    const t = setTimeout(() => { if (live) loadList(); }, 0);
    return () => { live = false; clearTimeout(t); };
  }, [loadList]);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [msgs]);

  async function open(id: string) {
    setErr(null);
    try {
      const c = await call<{ id: string; messages: Parameters<typeof fromStored>[0][] }>(`analyst/conversations/${id}`);
      setCid(c.id); setMsgs(c.messages.map(fromStored));
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not open that conversation."); }
  }
  function fresh() { setCid(null); setMsgs([]); setErr(null); setLastQ(null); }
  async function remove(id: string) {
    try { await call(`analyst/conversations/${id}`, { method: "DELETE" }); if (id === cid) fresh(); loadList(); } catch (e) { setErr(e instanceof Error ? e.message : "Could not delete that."); }
  }
  async function removeAll() {
    if (!window.confirm("Delete all of your Analyst conversations? This cannot be undone.")) return;
    try { await call("analyst/conversations", { method: "DELETE" }); fresh(); loadList(); } catch (e) { setErr(e instanceof Error ? e.message : "Could not delete them."); }
  }

  async function ask(q: string) {
    const text = q.trim();
    if (!text || busy) return;
    setBusy(true); setErr(null); setLastQ(text); setInput("");
    const mine: Msg = { id: uid(), role: "user", text, blocks: [], proposals: [], citations: [], trust: null, tools: [], notices: [] };
    const draft: Msg = { id: uid(), role: "assistant", text: "", blocks: [], proposals: [], citations: [], trust: null, tools: [], notices: [], pending: true, status: "Thinking…" };
    setMsgs((m) => [...m, mine, draft]);
    const patch = (f: (d: Msg) => Msg) => setMsgs((all) => all.map((x) => (x.id === draft.id ? f(x) : x)));
    try {
      const res = await fetch("/app-api/analyst/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: text, conversation_id: cid ?? undefined, save }) });
      if (!res.ok || !res.body) {
        const j = await res.json().catch(() => ({}));
        throw new Error(typeof j.detail === "string" ? j.detail : "The Analyst could not answer. Try again.");
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let nl: number;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          const e = JSON.parse(line);
          if (e.type === "meta" && e.conversation_id) setCid(e.conversation_id);
          else if (e.type === "status") patch((d) => ({ ...d, status: e.text }));
          else if (e.type === "tool") patch((d) => ({ ...d, status: `Retrieved ${e.tool.replace(/_/g, " ")}…`, tools: [...d.tools, { tool: e.tool, ok: e.ok, available: e.available, reason: e.reason }] }));
          else if (e.type === "sources") patch((d) => ({ ...d, citations: e.citations }));
          else if (e.type === "notice") patch((d) => ({ ...d, notices: [...d.notices, e.text] }));
          else if (e.type === "delta") patch((d) => ({ ...d, text: d.text + e.text, status: undefined }));
          else if (e.type === "blocks") patch((d) => ({ ...d, blocks: e.blocks }));
          else if (e.type === "proposals") patch((d) => ({ ...d, proposals: e.proposals }));
          else if (e.type === "trust") patch((d) => ({ ...d, trust: e.trust }));
          else if (e.type === "done") patch((d) => ({ ...d, pending: false, mode: e.mode, status: undefined }));
        }
      }
      patch((d) => ({ ...d, pending: false }));
      if (save) loadList();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Something went wrong.";
      setMsgs((all) => all.filter((x) => x.id !== draft.id));
      setErr(msg);
    } finally { setBusy(false); }
  }

  if (err && !status) return <ErrorPanel message={err} />;
  if (!status) return <p className="text-sm text-muted" aria-busy="true">Loading the Analyst…</p>;
  return (
    <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
      <aside aria-label="Conversations" className="space-y-3">
        <button type="button" onClick={fresh} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white"><MessageSquarePlus className="h-4 w-4" aria-hidden="true" /> New conversation</button>
        <details className="glass rounded-2xl p-3 lg:open" open>
          <summary className="cursor-pointer text-sm font-semibold">History {convs ? `(${convs.length})` : ""}</summary>
          {!convs ? <p className="mt-2 text-xs text-muted" aria-busy="true">Loading…</p> : convs.length === 0 ? <p className="mt-2 text-xs text-muted">No saved conversations yet.</p> : (
            <ul className="mt-2 space-y-1" aria-label="Saved conversations">{convs.map((c) => (
              <li key={c.id} className={`flex items-center justify-between gap-1 rounded-lg px-2 py-1.5 text-xs ${c.id === cid ? "bg-primary/20" : "hover:bg-white/5"}`}>
                <button type="button" onClick={() => open(c.id)} className="min-w-0 flex-1 truncate text-left" aria-current={c.id === cid ? "true" : undefined}>{c.title}</button>
                <button type="button" onClick={() => remove(c.id)} aria-label={`Delete conversation ${c.title}`} className="text-muted hover:text-red-300"><Trash2 className="h-3.5 w-3.5" aria-hidden="true" /></button>
              </li>
            ))}</ul>
          )}
          {convs && convs.length > 0 && <button type="button" onClick={removeAll} className="mt-3 text-xs text-muted underline hover:text-red-300">Delete all conversations</button>}
          <p className="mt-3 text-[11px] leading-relaxed text-muted">Private to you. Conversations are deleted automatically after {status.retention_days} days. Choose “Don&apos;t save” to ask without keeping anything.</p>
        </details>
      </aside>

      <section aria-label="Conversation" className="min-w-0 space-y-3">
        <div className="rounded-xl border border-line bg-white/5 p-3 text-xs leading-relaxed text-muted">
          <Badge tone={status.llm_configured ? "violet" : "green"}>{status.llm_configured ? "Language model + grounding check" : "Built-in rules over your records"}</Badge> {status.note}
        </div>
        <div className="space-y-4" aria-live="polite" aria-busy={busy}>
          {msgs.length === 0 && (
            <Panel title="Ask about your data, forecasts and simulations">
              <p className="mb-3 text-sm text-muted">Try one of these. Every answer shows where each number came from.</p>
              <ul className="flex flex-wrap gap-2" aria-label="Suggested questions">{status.suggested_questions.map((q) => <li key={q}><button type="button" onClick={() => ask(q)} disabled={busy} className="rounded-full border border-line px-3 py-1.5 text-left text-xs hover:bg-white/10 disabled:opacity-50">{q}</button></li>)}</ul>
            </Panel>
          )}
          {msgs.map((m) => m.role === "user" ? (
            <div key={m.id} className="ml-auto max-w-[85%] rounded-2xl bg-primary/25 px-4 py-2.5 text-sm"><span className="sr-only">You asked: </span>{m.text}</div>
          ) : (
            <article key={m.id} data-msg className="glass max-w-full space-y-3 rounded-2xl p-4" aria-label="Analyst answer">
              {m.pending && !m.text && <p className="flex items-center gap-2 text-sm text-muted"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> {m.status ?? "Thinking…"}</p>}
              {m.notices.map((n) => <p key={n} role="note" className="rounded-lg border border-amber-300/40 bg-amber-300/10 p-2 text-xs text-amber-200">{n}</p>)}
              {m.text && <AnswerText m={m} />}
              {m.pending && m.text && <p className="text-xs text-muted" aria-hidden="true">…</p>}
              {m.blocks.length > 0 && <Blocks blocks={m.blocks} />}
              <Proposals items={m.proposals} />
              {!m.pending && <Sources m={m} />}
              {!m.pending && cid && m === msgs[msgs.length - 1] && (
                <div className="flex flex-wrap gap-3 text-xs">
                  <a href={`/app-api/analyst/conversations/${cid}/export?format=md`} download className="inline-flex items-center gap-1 text-violet underline"><Download className="h-3.5 w-3.5" aria-hidden="true" /> Export sourced summary (Markdown)</a>
                  <a href={`/app-api/analyst/conversations/${cid}/export?format=html`} download className="text-violet underline">Printable page</a>
                </div>
              )}
            </article>
          ))}
          <div ref={end} />
        </div>
        {err && (
          <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-red-400/40 bg-red-400/10 p-3 text-sm text-red-200">
            <span>{err}</span>
            {lastQ && <button type="button" onClick={() => ask(lastQ)} disabled={busy} className="inline-flex items-center gap-1 rounded-lg border border-red-300/50 px-3 py-1 text-xs hover:bg-red-400/10"><RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /> Try again</button>}
          </div>
        )}
        <form onSubmit={(e) => { e.preventDefault(); ask(input); }} className="space-y-2">
          <label htmlFor="an-input" className="sr-only">Ask the Analyst</label>
          <div className="flex gap-2">
            <textarea id="an-input" value={input} onChange={(e) => setInput(e.target.value)} maxLength={status.limits.max_question_chars} rows={2} placeholder="Ask about a club, a fixture, the model, or a saved simulation…"
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input); } }} className={`${field} min-h-[3rem] flex-1 resize-y`} />
            <button type="submit" disabled={busy || !input.trim()} className="inline-flex items-center gap-2 self-end rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50" aria-label="Send question">{busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4" aria-hidden="true" />} Ask</button>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
            <label className="inline-flex items-center gap-2"><input type="checkbox" checked={!save} onChange={(e) => setSave(!e.target.checked)} /> Don&apos;t save this conversation</label>
            <span>{input.length}/{status.limits.max_question_chars} · up to {status.limits.per_minute} questions a minute · probabilities are estimates, not advice</span>
          </div>
        </form>
      </section>
    </div>
  );
}
