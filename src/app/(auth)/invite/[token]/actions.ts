"use server";

import { createHash } from "node:crypto";
import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth";
import { getPool } from "@/lib/db";

export interface AcceptState {
  error?: string;
}

/** Joins the workspace named by a valid invitation. The signed-in user's email must be the one the invitation was sent to. */
export async function acceptInvite(token: string): Promise<AcceptState> {
  const session = await getSession();
  const pool = getPool();
  if (!session) return { error: "Please sign in first." };
  if (!pool) return { error: "Invitations are temporarily unavailable." };
  if (!/^[A-Za-z0-9_-]{20,100}$/.test(token)) return { error: "This invitation link is not valid." };

  const client = await pool.connect();
  try {
    await client.query("begin");
    const inv = (
      await client.query(
        `select id, workspace_id, email, role from workspace_invites
          where token_hash = $1 and accepted_at is null and revoked_at is null and expires_at > now() for update`,
        [createHash("sha256").update(token).digest("hex")],
      )
    ).rows[0];
    if (!inv) {
      await client.query("rollback");
      return { error: "This invitation is no longer valid. Ask for a new one." };
    }
    if (inv.email !== session.email.toLowerCase()) {
      await client.query("rollback");
      return { error: "This invitation was sent to a different email address." };
    }
    await client.query("insert into workspace_members (workspace_id, user_id, role) values ($1,$2,$3) on conflict do nothing", [inv.workspace_id, session.userId, inv.role]);
    await client.query("update workspace_invites set accepted_at = now() where id = $1", [inv.id]);
    await client.query("update users set active_workspace_id = $1 where id = $2", [inv.workspace_id, session.userId]);
    await client.query("insert into activity_history (workspace_id, user_id, kind, summary) values ($1,$2,'member.joined',$3)", [inv.workspace_id, session.userId, `${session.name} joined as ${inv.role}`]);
    await client.query("insert into audit_logs (workspace_id, user_id, action, detail) values ($1,$2,'member.joined',$3)", [inv.workspace_id, session.userId, JSON.stringify({ invite_id: inv.id, role: inv.role })]);
    await client.query("commit");
  } catch (e) {
    await client.query("rollback").catch(() => {});
    console.error("accept invite failed", e instanceof Error ? e.message : e);
    return { error: "Could not accept the invitation. Please try again." };
  } finally {
    client.release();
  }
  redirect("/dashboard");
}
