"use client";

import { useCallback, useEffect, useState } from "react";
import { MessageSquare } from "lucide-react";
import { call, post } from "@/lib/client";
import type { AssistantItemType } from "@/lib/types";
import { dt } from "../ui";
import { field } from "../analysis";

interface Comment { id: string; parent_id: string | null; body: string; created_at: string; author_name: string; mine: boolean; can_delete: boolean }

function Composer({ itemType, itemId, parentId, onDone, placeholder }: { itemType: AssistantItemType; itemId: string; parentId?: string; onDone: () => void; placeholder: string }) {
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await post("comments", { item_type: itemType, item_id: itemId, body, parent_id: parentId });
      setBody("");
      onDone();
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Could not post the comment.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-start gap-2">
      <label className="sr-only" htmlFor={`c-${parentId ?? itemId}`}>{placeholder}</label>
      <textarea id={`c-${parentId ?? itemId}`} value={body} onChange={(e) => setBody(e.target.value)} placeholder={placeholder} maxLength={2000} rows={2} className={`${field} min-w-48 flex-1`} />
      <button type="submit" disabled={busy || !body.trim()} className="rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">{busy ? "Posting…" : parentId ? "Reply" : "Comment"}</button>
      {err && <p role="alert" className="w-full text-xs text-red-300">{err}</p>}
    </form>
  );
}

/** Threaded comments on one saved item. Viewers see the thread; posting is refused by the server for them. */
export function CommentsPanel({ type, id, canWrite }: { type: AssistantItemType; id: string; canWrite: boolean }) {
  const [items, setItems] = useState<Comment[] | null>(null);
  const [replying, setReplying] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const path = `comments?item_type=${type}&item_id=${id}`;
  const load = useCallback(
    () => call<{ comments: Comment[] }>(path).then((d) => { setItems(d.comments); setErr(null); }, (e) => setErr(e instanceof Error ? e.message : "Could not load comments.")),
    [path],
  );
  useEffect(() => {
    let live = true;
    call<{ comments: Comment[] }>(path).then((d) => { if (live) { setItems(d.comments); setErr(null); } }, (e) => live && setErr(e instanceof Error ? e.message : "Could not load comments."));
    return () => {
      live = false;
    };
  }, [path]);

  const del = (cid: string) => call(`comments/${cid}`, { method: "DELETE" }).then(load, (e) => setErr(e instanceof Error ? e.message : "Could not delete."));
  if (err) return <p role="alert" className="text-xs text-red-300">{err}</p>;
  if (!items) return <p className="text-xs text-muted" aria-busy="true">Loading comments…</p>;
  const top = items.filter((c) => !c.parent_id);
  const row = (c: Comment, reply = false) => (
    <li key={c.id} className={reply ? "ml-6 border-l border-line pl-3" : ""}>
      <p className="text-[11px] text-muted"><span className="font-semibold text-ink">{c.author_name}</span> · {dt(c.created_at)}</p>
      <p className="whitespace-pre-wrap text-sm">{c.body}</p>
      <p className="mt-0.5 flex gap-3 text-[11px]">
        {!reply && canWrite && <button type="button" onClick={() => setReplying(replying === c.id ? null : c.id)} className="text-violet underline">Reply</button>}
        {c.can_delete && <button type="button" onClick={() => del(c.id)} className="text-muted underline hover:text-ink">Delete</button>}
      </p>
      {replying === c.id && <div className="mt-2"><Composer itemType={type} itemId={id} parentId={c.id} placeholder="Write a reply" onDone={() => { setReplying(null); load(); }} /></div>}
    </li>
  );
  return (
    <div className="space-y-3" aria-label="Comments">
      {top.length === 0 ? <p className="text-xs text-muted">No comments yet.</p> : (
        <ul className="space-y-3">
          {top.map((c) => (
            <div key={c.id}>
              {row(c)}
              <ul className="mt-2 space-y-2">{items.filter((r) => r.parent_id === c.id).map((r) => row(r, true))}</ul>
            </div>
          ))}
        </ul>
      )}
      {canWrite ? <Composer itemType={type} itemId={id} placeholder="Add a comment" onDone={load} /> : <p className="text-xs text-muted">Viewers can read comments but not post.</p>}
    </div>
  );
}

export function CommentsToggle({ type, id, canWrite }: { type: AssistantItemType; id: string; canWrite: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="w-full">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-violet/60"><MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />{open ? "Hide comments" : "Comments"}</button>
      {open && <div className="mt-3"><CommentsPanel type={type} id={id} canWrite={canWrite} /></div>}
    </div>
  );
}
