"""AI Analyst API: authenticated chat over the read-only tools, with private conversation history.

Safety properties (each tested):
  * Everything is scoped to the signed-in person's workspace; conversations to the person as well. Another member cannot read, list or delete them.
  * Per-person (RATE_PER_MINUTE, RATE_PER_DAY) rate limits and a workspace token budget for language-model use. Over the budget the Analyst still answers,
    from records with its built-in rules, and says so.
  * The audit log records metadata about each question (tools used, mode, tokens, latency, cost) but never the question or the answer, so no personal text
    is logged. Credentials are server-side only and never appear in any response.
  * `save: false` answers a question without storing anything. Conversations older than the retention period are deleted.
"""
from __future__ import annotations

import csv  # noqa: F401  (kept for parity with other exports)
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, StringConstraints

from . import analyst_core as core
from . import analyst_llm as llm
from . import analyst_tools as at
from . import plans
from .db import get_conn
from .security import Auth

router = APIRouter(prefix="/api/v1/analyst", tags=["analyst"])
RATE_PER_MINUTE = 10
RATE_PER_DAY = 200
MAX_STORED_JSON = 24_000
MAX_CONVERSATIONS = 200


def retention_days() -> int:
    try:
        return max(1, int(os.environ.get("ANALYST_RETENTION_DAYS", "90")))
    except ValueError:
        return 90


def daily_token_budget() -> int:
    try:
        return max(0, int(os.environ.get("ANALYST_DAILY_TOKEN_BUDGET", "300000")))
    except ValueError:
        return 300_000


class ChatBody(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=core.MAX_QUESTION)]
    conversation_id: uuid.UUID | None = None
    save: bool = True


def _today():
    return datetime.now(timezone.utc).date()


def _purge(conn, p) -> None:
    conn.execute("delete from analyst_conversations where workspace_id=%s and user_id=%s and updated_at < now() - make_interval(days => %s)", (p.workspace_id, p.user_id, retention_days()))


def _limit(conn, p) -> None:
    m = conn.execute("select count(*) n from audit_logs where workspace_id=%s and user_id=%s and action='analyst.chat' and created_at > now() - interval '1 minute'", (p.workspace_id, p.user_id)).fetchone()["n"]
    if m >= RATE_PER_MINUTE:
        raise HTTPException(429, f"Too many questions: at most {RATE_PER_MINUTE} per minute. Wait a moment and try again.")
    d = conn.execute("select count(*) n from audit_logs where workspace_id=%s and user_id=%s and action='analyst.chat' and created_at > now() - interval '1 day'", (p.workspace_id, p.user_id)).fetchone()["n"]
    if d >= RATE_PER_DAY:
        raise HTTPException(429, f"You have reached the limit of {RATE_PER_DAY} questions in 24 hours.")


def _tokens_today(conn, p) -> int:
    return int(conn.execute("select coalesce(sum((detail->>'tokens')::int), 0) n from audit_logs where workspace_id=%s and action='analyst.chat' and created_at > now() - interval '1 day'", (p.workspace_id,)).fetchone()["n"])


def _cap(v):
    s = json.dumps(v, default=str)
    return s if len(s) <= MAX_STORED_JSON else json.dumps({"truncated": True})


def _own(conn, p, cid: uuid.UUID):
    row = conn.execute("select * from analyst_conversations where id=%s and workspace_id=%s and user_id=%s", (cid, p.workspace_id, p.user_id)).fetchone()
    if not row:
        raise HTTPException(404, "Conversation not found")
    return row


def suggested(conn, p) -> list[str]:
    ctx = at.Ctx(conn, p, _today())
    ms = ctx.history()
    out: list[str] = []
    if ms:
        up = conn.execute("select home_team, away_team from football_fixtures where status not in ('cancelled','postponed','suspended') and workspace_id=%s and fixture_date >= %s order by fixture_date limit 1", (p.workspace_id, ctx.today)).fetchone()
        last = ms[-1]
        home, away = (up["home_team"], up["away_team"]) if up else (last[1], last[2])
        out += [f"Why is {home} favoured over {away}?", f"How has {home} performed at home?", f"What are the likeliest scorelines for {home} v {away}?", "How well has the model performed historically?", "How fresh is my data?"]
    else:
        out += ["How fresh is my data?", "What can you not tell me?"]
    n = conn.execute("select (select count(*) from simlab_runs where workspace_id=%s) + (select count(*) from strategic_scenarios where workspace_id=%s) n", (p.workspace_id, p.workspace_id)).fetchone()["n"]
    if n:
        out += ["Explain my latest simulation", "Compare my last two simulations"] if n >= 2 else ["Explain my latest simulation"]
    out.append("What can you not tell me?" if "What can you not tell me?" not in out else "Which scenarios should I try next?")
    return out[:8]


@router.get("/status")
def status(p: Auth, conn=Depends(get_conn)):
    _purge(conn, p)
    s = llm.status()
    return {**s, "mode": "language_model_with_grounding_check" if s["llm_configured"] else "grounded_rules", "retention_days": retention_days(),
            "limits": {"per_minute": RATE_PER_MINUTE, "per_day": RATE_PER_DAY, "max_question_chars": core.MAX_QUESTION, "max_tool_calls": core.MAX_TOOL_CALLS},
            "tools": [{"name": t.name, "description": t.description} for t in at.TOOLS.values()], "suggested_questions": suggested(conn, p),
            "note": "The Analyst only uses data in your workspace. It has no live feeds, cannot run simulations, and answers are shown only when every number traces to a retrieved record."}


def _chunks(text: str, size: int = 90) -> list[str]:
    words, out, cur = text.split(" "), [], ""
    for w in words:
        if cur and len(cur) + len(w) + 1 > size:
            out.append(cur + " ")
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        out.append(cur)
    return out


def _events(conversation_id, ans: dict, notices: list[str]) -> list[dict]:
    ev: list[dict] = [{"type": "meta", "conversation_id": str(conversation_id) if conversation_id else None, "mode": ans["mode"]}, {"type": "status", "text": "Retrieving records from your workspace"}]
    ev += [{"type": "tool", "tool": t["tool"], "args": t["args"], "ok": t["ok"], "available": t["available"], "reason": t["reason"]} for t in ans["tool_calls"]]
    ev.append({"type": "sources", "citations": ans["citations"]})
    for n in notices + ans["notes"]:
        ev.append({"type": "notice", "text": n})
    ev += [{"type": "delta", "text": c} for c in _chunks(ans["text"])]
    ev += [{"type": "blocks", "blocks": ans["blocks"]}, {"type": "proposals", "proposals": ans["proposals"]}, {"type": "trust", "trust": ans["trust"]},
           {"type": "done", "mode": ans["mode"], "grounding": ans["grounding"], "usage": {k: v for k, v in ans["usage"].items() if k != "cost_usd"} | {"cost_usd": ans["usage"]["cost_usd"]}}]
    return ev


@router.post("/chat")
def chat(body: ChatBody, p: Auth, conn=Depends(get_conn), stream: bool = True):
    """Answer one question. The reply is a stream of newline-delimited JSON events (or a single JSON object with `stream=false`)."""
    _limit(conn, p)
    _purge(conn, p)
    conv, history, state = None, [], core.empty_state()
    if body.conversation_id:
        conv = _own(conn, p, body.conversation_id)
        state = core.clean_state(conv["state"])
        history = [{"role": m["role"], "content": m["content"]} for m in conn.execute("select role, content from analyst_messages where conversation_id=%s order by created_at desc limit 8", (conv["id"],)).fetchall()][::-1]
    notices: list[str] = []
    allow_llm = True
    if _tokens_today(conn, p) >= daily_token_budget():
        allow_llm = False
        notices.append("This workspace has used its daily language-model token budget, so this answer was built from your records with the built-in rules.")
    provider = llm.get_provider()
    try:
        ans = core.answer(at.Ctx(conn, p, _today()), body.message, state, history, provider, allow_llm)
    except ValueError as e:
        raise HTTPException(422, str(e))
    cid = conv["id"] if conv else None
    if body.save:
        if not conv:
            n = conn.execute("select count(*) n from analyst_conversations where workspace_id=%s and user_id=%s", (p.workspace_id, p.user_id)).fetchone()["n"]
            if n >= MAX_CONVERSATIONS:
                raise HTTPException(422, f"You can keep up to {MAX_CONVERSATIONS} conversations. Delete some to save more.")
            title = at.clean(re.sub(r"\s+", " ", body.message).strip(), 120) or "Conversation"
            cid = conn.execute("insert into analyst_conversations (workspace_id, user_id, title, state) values (%s,%s,%s,%s) returning id", (p.workspace_id, p.user_id, title, json.dumps(ans["state"]))).fetchone()["id"]
        else:
            conn.execute("update analyst_conversations set state=%s, updated_at=now() where id=%s", (json.dumps(ans["state"]), cid))
        conn.execute("insert into analyst_messages (conversation_id, workspace_id, user_id, role, content) values (%s,%s,%s,'user',%s)", (cid, p.workspace_id, p.user_id, body.message))
        conn.execute("""insert into analyst_messages (conversation_id, workspace_id, user_id, role, content, blocks, citations, trust, tool_calls, proposals, mode, usage)
                        values (%s,%s,%s,'assistant',%s,%s,%s,%s,%s,%s,%s,%s)""",
                     (cid, p.workspace_id, p.user_id, ans["text"][:8000], _cap(ans["blocks"]), _cap(ans["citations"]), _cap(ans["trust"]), _cap(ans["tool_calls"]), _cap(ans["proposals"]), ans["mode"], json.dumps(ans["usage"])))
    u = ans["usage"]
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'analyst.chat',%s)",
                 (p.workspace_id, p.user_id, json.dumps({"conversation_id": str(cid) if cid else None, "saved": body.save, "tools": [t["tool"] for t in ans["tool_calls"]], "intents": ans["intents"], "mode": ans["mode"],
                                                          "provider": u.get("provider"), "model": u.get("model"), "tokens": u.get("input_tokens", 0) + u.get("output_tokens", 0), "latency_ms": u["latency_ms"], "cost_usd": u.get("cost_usd"),
                                                          "rejected": ans["grounding"]["rejected"]})))
    events = _events(cid, ans, notices)
    if not stream:
        return {"conversation_id": str(cid) if cid else None, "answer": ans["text"], "events": events, **{k: ans[k] for k in ("blocks", "proposals", "citations", "trust", "tool_calls", "mode", "grounding", "notes")}, "notices": notices}
    return StreamingResponse((json.dumps(e, default=str) + "\n" for e in events), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})


@router.get("/conversations")
def conversations(p: Auth, conn=Depends(get_conn)):
    _purge(conn, p)
    rows = conn.execute("""select c.id, c.title, c.created_at, c.updated_at, (select count(*) from analyst_messages m where m.conversation_id=c.id) messages from analyst_conversations c
                           where c.workspace_id=%s and c.user_id=%s order by c.updated_at desc limit 100""", (p.workspace_id, p.user_id)).fetchall()
    return {"conversations": rows, "retention_days": retention_days()}


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    c = _own(conn, p, conversation_id)
    msgs = conn.execute("select id, role, content, blocks, citations, trust, tool_calls, proposals, mode, usage, created_at from analyst_messages where conversation_id=%s order by created_at", (c["id"],)).fetchall()
    return {"id": str(c["id"]), "title": c["title"], "state": c["state"], "created_at": c["created_at"], "updated_at": c["updated_at"], "messages": msgs, "retention_days": retention_days()}


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    c = _own(conn, p, conversation_id)
    conn.execute("delete from analyst_conversations where id=%s", (c["id"],))
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'analyst.delete',%s)", (p.workspace_id, p.user_id, json.dumps({"conversation_id": str(c["id"])})))


@router.delete("/conversations", status_code=200)
def delete_all(p: Auth, conn=Depends(get_conn)):
    n = conn.execute("delete from analyst_conversations where workspace_id=%s and user_id=%s", (p.workspace_id, p.user_id)).rowcount
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'analyst.delete_all',%s)", (p.workspace_id, p.user_id, json.dumps({"deleted": n})))
    return {"deleted": n}


def _md(title: str, msgs: list[dict], stamp: str) -> str:
    L = [f"# AI Analyst: {title}", "", f"Exported {stamp}. The Analyst answers only from records in this workspace. Probabilities are estimates, not certainties; simulations are hypothetical; none of this is betting, investment, voting or legal advice.", ""]
    for m in msgs:
        if m["role"] == "user":
            L += [f"## Question ({m['created_at'].isoformat()[:16].replace('T', ' ')} UTC)", "", m["content"], ""]
            continue
        L += [f"### Answer (method: {'language model with a grounding check' if m['mode'] == 'language_model' else 'built-in rules over retrieved records'})", "", m["content"], ""]
        tr = m["trust"] or {}
        if m["citations"]:
            L += ["**Sources**", ""] + [f"- [{c['id']}] {c['label']}: {c['source']}; retrieved {c['retrieved_at'][:19].replace('T', ' ')} UTC; window: {c.get('window') or 'n/a'}" + (f"; model version: {c['model_version']}" if c.get("model_version") else "") for c in m["citations"]] + [""]
        if tr.get("assumptions"):
            L += ["**Assumptions**", ""] + [f"- {a}" for a in tr["assumptions"]] + [""]
        if tr.get("limitations"):
            L += ["**Limitations**", ""] + [f"- {a}" for a in tr["limitations"]] + [""]
        if tr.get("unavailable"):
            L += ["**Not available**", ""] + [f"- {a}" for a in tr["unavailable"]] + [""]
    return "\n".join(L)


@router.get("/conversations/{conversation_id}/export")
def export(conversation_id: uuid.UUID, p: Auth, conn=Depends(get_conn), format: Literal["md", "html"] = "md"):
    plans.check_exports(conn, p.workspace_id)
    c = _own(conn, p, conversation_id)
    msgs = conn.execute("select role, content, citations, trust, mode, created_at from analyst_messages where conversation_id=%s order by created_at", (c["id"],)).fetchall()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    md = _md(c["title"], msgs, stamp)
    slug = re.sub(r"[^a-z0-9]+", "-", c["title"].lower()).strip("-")[:40] or "analysis"
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'analyst.export',%s)", (p.workspace_id, p.user_id, json.dumps({"conversation_id": str(c["id"]), "format": format})))
    if format == "md":
        return Response(md, media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{slug}.md"'})
    body = "".join(f"<p>{escape(line)}</p>" if not line.startswith(("#", "- ")) else (f"<h2>{escape(line.lstrip('# '))}</h2>" if line.startswith("#") else f"<li>{escape(line[2:])}</li>") for line in md.split("\n") if line.strip())
    html = (f"<!doctype html><html lang='en'><meta charset='utf-8'><title>{escape(c['title'])}</title><style>body{{font:14px/1.5 system-ui,sans-serif;max-width:820px;margin:2rem auto;padding:0 1rem;color:#111}}</style>{body}</html>")
    return Response(html, media_type="text/html; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{slug}.html"'})
