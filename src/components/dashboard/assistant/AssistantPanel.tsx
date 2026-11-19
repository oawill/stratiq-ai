"use client";

import { useEffect, useState } from "react";
import { FileText, Loader2, ShieldCheck, Sparkles } from "lucide-react";
import { call, post } from "@/lib/client";
import type { AssistantItemType, AssistantResult, AssistantStatus } from "@/lib/types";
import { Badge, ErrorPanel } from "../ui";
import { field } from "../analysis";

const TOPICS = [
  ["all", "Explain everything"], ["overview", "What does this show?"], ["uncertainty", "How certain is it?"],
  ["assumptions", "What does it assume?"], ["limitations", "What are the limits?"], ["next", "What should I explore next?"],
] as const;

function Result({ r }: { r: AssistantResult }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {r.mode === "language_model"
          ? <Badge tone="violet"><span className="inline-flex items-center gap-1"><ShieldCheck className="h-3 w-3" aria-hidden="true" /> Language model · every number verified against the results</span></Badge>
          : <Badge tone="green">Computed explanation · built from the engine&apos;s own numbers</Badge>}
      </div>
      {r.grounding.reason && <p role="status" className="rounded-lg border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-xs text-amber-200">{r.grounding.reason}{r.grounding.offending_numbers.length > 0 && <> Numbers not found in the results: {r.grounding.offending_numbers.join(", ")}.</>}</p>}
      {r.narrative && <p className="whitespace-pre-wrap rounded-xl border border-violet/30 bg-violet/5 p-3 text-sm leading-relaxed">{r.narrative}</p>}
      {r.sections.map((s) => (
        <section key={s.id} aria-label={s.title}>
          <h4 className="mb-1 text-sm font-semibold">{r.narrative ? `${s.title} (computed)` : s.title}</h4>
          <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-muted">{s.items.map((i) => <li key={i}>{i}</li>)}</ul>
        </section>
      ))}
      <details className="rounded-lg border border-line p-2 text-xs">
        <summary className="cursor-pointer font-semibold">The numbers behind this ({r.metrics.length})</summary>
        <dl className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">{r.metrics.map((m) => <div key={m.label} className="flex justify-between gap-3"><dt className="text-muted">{m.label}</dt><dd className="font-mono">{m.value}</dd></div>)}</dl>
        {Object.keys(r.reproduction).length > 0 && <dl className="mt-2 border-t border-line pt-2">{Object.entries(r.reproduction).map(([k, v]) => <div key={k} className="flex justify-between gap-3"><dt className="text-muted">{k}</dt><dd className="truncate font-mono">{v}</dd></div>)}</dl>}
      </details>
      <p className="text-[11px] leading-relaxed text-muted">{r.notice}</p>
    </div>
  );
}

export function AssistantPanel({ type, id, title }: { type: AssistantItemType; id: string; title?: string }) {
  const [status, setStatus] = useState<AssistantStatus | null>(null);
  const [res, setRes] = useState<AssistantResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => { let live = true; call<AssistantStatus>("assistant/status").then((s) => live && setStatus(s)).catch(() => {}); return () => { live = false; }; }, []);

  async function ask(focus: string, question?: string) {
    setBusy(focus); setErr(null);
    try { setRes(await post<AssistantResult>("assistant/explain", { type, id, focus, question: question || null })); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } finally { setBusy(null); }
  }
  const reports = (["html", "md", "json"] as const).map((f) => ({ f, href: `/app-api/library/report?type=${type}&id=${id}&format=${f}` }));
  return (
    <div className="rounded-2xl border border-violet/30 bg-violet/5 p-4" role="region" aria-label={`Assistant${title ? `: ${title}` : ""}`}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Sparkles className="h-4 w-4 text-violet" aria-hidden="true" />
        <h3 className="text-sm font-semibold">Assistant{title ? `: ${title}` : ""}</h3>
        {status && <Badge tone={status.llm_configured ? "violet" : "muted"}>{status.llm_configured ? "Language model available" : "Computed explanations only"}</Badge>}
      </div>
      <p className="mb-3 text-xs leading-relaxed text-muted">{status?.note ?? "The assistant explains results the engines already computed. It cannot change them or create new numbers."}</p>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Choose what to explain">
        {TOPICS.map(([f, label]) => (
          <button key={f} type="button" onClick={() => ask(f)} disabled={busy !== null} className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-bg/60 px-3 py-1.5 text-xs font-semibold hover:border-violet/60 disabled:opacity-60">
            {busy === f && <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />}{label}
          </button>))}
      </div>
      {status?.llm_configured && (
        <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (q.trim()) ask("all", q.trim()); }}>
          <label htmlFor={`q-${id}`} className="sr-only">Ask a question about these results</label>
          <input id={`q-${id}`} value={q} maxLength={500} onChange={(e) => setQ(e.target.value)} placeholder="Ask about these results…" className={`${field} min-w-0 flex-1`} />
          <button type="submit" disabled={busy !== null || !q.trim()} className="rounded-lg bg-primary px-3 text-xs font-semibold text-white disabled:opacity-50">Ask</button>
        </form>)}
      <div aria-live="polite" className="mt-4">
        {err && <ErrorPanel message={err} />}
        {busy && !res && <p className="text-sm text-muted" aria-busy="true">Preparing explanation…</p>}
        {res && <Result r={res} />}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-3">
        <span className="text-xs text-muted">Report:</span>
        {reports.map(({ f, href }) => <a key={f} href={href} {...(f === "html" ? { target: "_blank", rel: "noopener" } : { download: true })} className="inline-flex items-center gap-1 rounded-lg border border-line px-2.5 py-1 text-xs font-semibold hover:border-violet/60"><FileText className="h-3 w-3" aria-hidden="true" />{f === "html" ? "Print / PDF view" : f === "md" ? "Markdown" : "JSON"}</a>)}
      </div>
    </div>
  );
}

/** Explains the differences between 2–4 saved items of the same type. */
export function CompareExplain({ type, ids }: { type: "simulation" | "scenario"; ids: string[] }) {
  const [res, setRes] = useState<AssistantResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function run() {
    setBusy(true); setErr(null);
    try { setRes(await post<AssistantResult>("assistant/compare", { type, ids })); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); setRes(null); } finally { setBusy(false); }
  }
  return (
    <div className="mt-3">
      <button type="button" onClick={run} disabled={busy || ids.length < 2} className="inline-flex items-center gap-2 rounded-xl border border-violet/50 px-4 py-2 text-sm font-semibold text-violet hover:bg-violet/10 disabled:opacity-50">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Sparkles className="h-4 w-4" aria-hidden="true" />} Explain the differences
      </button>
      <div aria-live="polite" className="mt-3">
        {err && <ErrorPanel message={err} />}
        {res && <div className="rounded-2xl border border-violet/30 bg-violet/5 p-4"><Result r={res} /></div>}
      </div>
    </div>
  );
}

/** A button that opens the assistant for one item beneath it. */
export function ExplainToggle({ type, id, title }: { type: AssistantItemType; id: string; title?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="w-full">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="inline-flex items-center gap-1.5 rounded-lg border border-violet/50 px-3 py-1.5 text-xs font-semibold text-violet hover:bg-violet/10"><Sparkles className="h-3.5 w-3.5" aria-hidden="true" />{open ? "Hide assistant" : "Explain"}</button>
      {open && <div className="mt-3"><AssistantPanel type={type} id={id} title={title} /></div>}
    </div>
  );
}
