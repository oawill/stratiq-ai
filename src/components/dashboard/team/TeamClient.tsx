"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Copy, Loader2, UserPlus } from "lucide-react";
import { call } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel, dt } from "../ui";
import { field } from "../analysis";

interface Member { user_id: string; name: string; email: string; role: string; joined_at: string }
interface Invite { id: string; email: string; role: string; created_at: string; expires_at: string; invited_by_name: string | null }
interface Team { me: { user_id: string; role: string }; members: Member[]; invites: Invite[]; seats: { members: number; pending: number; cap: number | null } }
interface Activity { id: number; kind: string; summary: string; created_at: string; user_name: string | null }
interface Created { email: string; role: string; link: string; emailed: boolean }

const ROLE_HELP: Record<string, string> = {
  owner: "Full control, including billing and ownership.",
  admin: "Manages members and viewers.",
  member: "Reads and saves work, and comments.",
  viewer: "Read-only.",
};
const tone = (r: string) => (r === "owner" ? "violet" : r === "admin" ? "cyan" : "muted");

async function invitePost(email: string, role: string): Promise<Created> {
  const res = await fetch("/api/team/invites", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, role }) });
  const j = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(j.error ?? "Could not create the invitation.");
  return j as Created;
}

export function TeamClient() {
  const router = useRouter();
  const [team, setTeam] = useState<Team | null>(null);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [created, setCreated] = useState<Created | null>(null);
  const [copied, setCopied] = useState(false);

  const fetchAll = () => Promise.all([call<Team>("team/members"), call<{ activity: Activity[] }>("team/activity?limit=30")]);
  const apply = ([t, a]: [Team, { activity: Activity[] }]) => {
    setTeam(t);
    setActivity(a.activity);
    setErr(null);
  };
  const load = useCallback(() => fetchAll().then(apply, (e) => setErr(e instanceof Error ? e.message : "Could not load the team.")), []);
  useEffect(() => {
    let live = true;
    fetchAll().then((r) => live && apply(r), (e) => live && setErr(e instanceof Error ? e.message : "Could not load the team."));
    return () => {
      live = false;
    };
  }, []);

  async function act(key: string, fn: () => Promise<unknown>) {
    setBusy(key);
    setErr(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(null);
    }
  }

  async function sendInvite(e: React.FormEvent) {
    e.preventDefault();
    setCreated(null);
    setCopied(false);
    await act("invite", async () => {
      setCreated(await invitePost(email, role));
      setEmail("");
    });
  }

  if (!team) return err ? <ErrorPanel message={err} /> : <p className="text-sm text-muted" aria-busy="true">Loading team…</p>;

  const me = team.me;
  const isOwner = me.role === "owner";
  const isAdmin = isOwner || me.role === "admin";
  const seatText = team.seats.cap === null ? `${team.seats.members} members` : `${team.seats.members + team.seats.pending} of ${team.seats.cap} seats used`;
  const canManage = (m: Member) => m.user_id !== me.user_id && m.role !== "owner" && (isOwner || m.role === "member" || m.role === "viewer");
  const assignable = isOwner ? ["admin", "member", "viewer"] : ["member", "viewer"];

  return (
    <div className="space-y-4">
      {err && <ErrorPanel message={err} />}

      <Panel title="Members" badge={<Badge tone="muted">{seatText}</Badge>}>
        <ul className="divide-y divide-line" aria-label="Workspace members">
          {team.members.map((m) => (
            <li key={m.user_id} className="flex flex-wrap items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold">{m.name}{m.user_id === me.user_id && <span className="font-normal text-muted"> (you)</span>}</div>
                <div className="truncate text-xs text-muted">{m.email} · joined {dt(m.joined_at)}</div>
              </div>
              {isAdmin && canManage(m) ? (
                <>
                  <label className="sr-only" htmlFor={`role-${m.user_id}`}>Role for {m.name}</label>
                  <select id={`role-${m.user_id}`} className={field} value={m.role} disabled={busy !== null} onChange={(e) => act(`role-${m.user_id}`, () => call(`team/members/${m.user_id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role: e.target.value }) }))}>
                    {assignable.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                  <button type="button" disabled={busy !== null} onClick={() => confirm(`Remove ${m.name} from this workspace?`) && act(`rm-${m.user_id}`, () => call(`team/members/${m.user_id}`, { method: "DELETE" }))} className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-red-400/60 disabled:opacity-60">Remove</button>
                </>
              ) : (
                <Badge tone={tone(m.role)}>{m.role}</Badge>
              )}
              {isOwner && m.role !== "owner" && (
                <button type="button" disabled={busy !== null} onClick={() => confirm(`Make ${m.name} the owner? You will become an admin.`) && act(`tr-${m.user_id}`, () => call("team/transfer", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: m.user_id }) }))} className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-violet/60 disabled:opacity-60">Make owner</button>
              )}
            </li>
          ))}
        </ul>
        <dl className="mt-3 grid gap-1 text-xs text-muted sm:grid-cols-2">
          {Object.entries(ROLE_HELP).map(([r, d]) => <div key={r}><dt className="inline font-semibold text-ink">{r}: </dt><dd className="inline">{d}</dd></div>)}
        </dl>
        {!isOwner && (
          <button type="button" disabled={busy !== null} onClick={() => confirm("Leave this workspace? You will lose access to its saved work.") && act("leave", async () => { await call("team/leave", { method: "POST" }); router.push("/dashboard"); router.refresh(); })} className="mt-4 rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-red-400/60 disabled:opacity-60">Leave workspace</button>
        )}
      </Panel>

      {isAdmin && (
        <Panel title="Invite someone">
          <form onSubmit={sendInvite} className="flex flex-wrap items-end gap-3">
            <div className="min-w-56 flex-1">
              <label htmlFor="inv-email" className="mb-1 block text-xs font-medium text-muted">Email address</label>
              <input id="inv-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="teammate@company.com" className={`${field} w-full`} />
            </div>
            <div>
              <label htmlFor="inv-role" className="mb-1 block text-xs font-medium text-muted">Role</label>
              <select id="inv-role" value={role} onChange={(e) => setRole(e.target.value)} className={field}>
                {assignable.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <button type="submit" disabled={busy !== null || !email.trim()} className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
              {busy === "invite" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <UserPlus className="h-4 w-4" aria-hidden="true" />} Create invitation
            </button>
          </form>
          {created && (
            <div role="status" className="mt-4 rounded-xl border border-success/40 bg-success/10 p-3 text-sm">
              <p>
                Invitation created for <strong>{created.email}</strong> as {created.role}.{" "}
                {created.emailed ? "We also emailed them the link." : "Email delivery is not set up, so share this link with them yourself."} It works once, only for that address, for 7 days, and is shown only now.
              </p>
              <div className="mt-2 flex items-center gap-2">
                <input readOnly aria-label="Invitation link" value={created.link} onFocus={(e) => e.currentTarget.select()} className={`${field} w-full font-mono text-xs`} />
                <button type="button" onClick={() => navigator.clipboard.writeText(created.link).then(() => setCopied(true))} className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-line px-3 py-2 text-xs font-semibold hover:border-violet/60"><Copy className="h-3.5 w-3.5" aria-hidden="true" />{copied ? "Copied" : "Copy"}</button>
              </div>
            </div>
          )}
          <h3 className="mb-2 mt-5 text-sm font-semibold">Pending invitations</h3>
          {team.invites.length === 0 ? <Empty>No pending invitations.</Empty> : (
            <ul className="divide-y divide-line" aria-label="Pending invitations">
              {team.invites.map((i) => (
                <li key={i.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
                  <span className="min-w-0 flex-1 truncate">{i.email} <span className="text-xs text-muted">· {i.role} · expires {dt(i.expires_at)}</span></span>
                  <button type="button" disabled={busy !== null} onClick={() => act(`rv-${i.id}`, () => call(`team/invites/${i.id}`, { method: "DELETE" }))} className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-red-400/60 disabled:opacity-60">Cancel</button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      )}

      <Panel title="Activity">
        {activity.length === 0 ? <Empty>Nothing yet. Saved work, comments and team changes appear here.</Empty> : (
          <ul className="divide-y divide-line" aria-label="Workspace activity">
            {activity.map((a) => (
              <li key={a.id} className="flex flex-wrap items-baseline gap-x-3 py-2 text-sm">
                <span className="min-w-0 flex-1">{a.summary}{a.user_name && <span className="text-muted"> · {a.user_name}</span>}</span>
                <span className="text-[11px] text-muted">{dt(a.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
