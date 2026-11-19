"use client";

import { useEffect, useState } from "react";
import { Loader2, Save } from "lucide-react";
import { post } from "@/lib/client";
import type { PolKind } from "@/lib/types";

export const field = "rounded-lg border border-line bg-bg/70 px-2 py-1.5 text-sm focus:border-violet focus:outline-none focus:ring-2 focus:ring-violet/40";
export const pc = (x: number, d = 1) => `${(x * 100).toFixed(d)}%`;

/** Debounced live analysis. `body` null = inputs not valid yet. The result is keyed to its inputs, so stale results are never shown. */
export function useAnalysis<T>(path: string, body: unknown | null, delay = 350) {
  const key = body ? `${path}|${JSON.stringify(body)}` : "";
  const [res, setRes] = useState<{ key: string; data?: T; error?: string } | null>(null);
  useEffect(() => {
    if (!key) return;
    const t = setTimeout(() => {
      post<T>(path, JSON.parse(key.slice(path.length + 1)))
        .then((data) => setRes({ key, data }))
        .catch((e) => setRes({ key, error: e instanceof Error ? e.message : "Request failed" }));
    }, delay);
    return () => clearTimeout(t);
  }, [key, path, delay]);
  const cur = res && res.key === key ? res : null;
  return { loading: !!key && !cur, data: cur?.data, error: cur?.error };
}

/** Parse a user-entered number; empty or invalid gives NaN. */
export const num = (s: string) => (s.trim() === "" ? NaN : Number(s));

export function SaveBar({ kind, inputs, valid, onSaved }: { kind: PolKind; inputs: unknown; valid: boolean; onSaved: () => void }) {
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  async function save() {
    if (!title.trim()) return setMsg({ ok: false, text: "Give the scenario a title first." });
    setBusy(true); setMsg(null);
    try {
      await post("politics/scenarios", { kind, title: title.trim(), notes: notes.trim() || null, inputs });
      setMsg({ ok: true, text: "Saved. Find it under Saved & compare." });
      onSaved();
    } catch (e) { setMsg({ ok: false, text: e instanceof Error ? e.message : "Could not save" }); } finally { setBusy(false); }
  }
  return (
    <div className="grid gap-3 sm:grid-cols-5">
      <div className="sm:col-span-2">
        <label htmlFor={`save-title-${kind}`} className="mb-1 block text-xs text-muted">Scenario title</label>
        <input id={`save-title-${kind}`} value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} className={`${field} w-full`} />
      </div>
      <div className="sm:col-span-2">
        <label htmlFor={`save-notes-${kind}`} className="mb-1 block text-xs text-muted">Notes (optional)</label>
        <input id={`save-notes-${kind}`} value={notes} maxLength={2000} onChange={(e) => setNotes(e.target.value)} className={`${field} w-full`} />
      </div>
      <div className="flex items-end">
        <button type="button" onClick={save} disabled={busy || !valid} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />} Save
        </button>
      </div>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`text-sm sm:col-span-5 ${msg.ok ? "text-success" : "text-red-300"}`}>{msg.text}</p>}
    </div>
  );
}
