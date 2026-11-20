import type { Metadata } from "next";
import { createHash } from "node:crypto";
import Link from "next/link";
import { Suspense } from "react";
import { redirect } from "next/navigation";
import { getSession } from "@/lib/auth";
import { getPool } from "@/lib/db";
import { ButtonLink } from "@/components/ui/primitives";
import { AcceptButton } from "./AcceptButton";

export const metadata: Metadata = { title: "Workspace Invitation", robots: { index: false, follow: false } };

const Card = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div className="glass rounded-3xl p-8">
    <h1 className="text-2xl font-extrabold tracking-tight">{title}</h1>
    <div className="mt-4 space-y-4 text-sm leading-relaxed text-muted">{children}</div>
  </div>
);

async function Content({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const pool = getPool();
  const valid = /^[A-Za-z0-9_-]{20,100}$/.test(token);
  const inv =
    valid && pool
      ? (
          await pool.query(
            `select i.email, i.role, i.workspace_id, w.name workspace, u.name inviter
               from workspace_invites i join workspaces w on w.id = i.workspace_id left join users u on u.id = i.invited_by
              where i.token_hash = $1 and i.accepted_at is null and i.revoked_at is null and i.expires_at > now()`,
            [createHash("sha256").update(token).digest("hex")],
          )
        ).rows[0]
      : undefined;

  if (!inv) {
    return (
      <Card title="Invitation not available">
        <p>This invitation link is invalid, has expired, was cancelled, or has already been used. Ask the workspace owner for a new one.</p>
        <Link href="/login" className="text-violet underline">Go to log in</Link>
      </Card>
    );
  }

  const session = await getSession();
  const next = encodeURIComponent(`/invite/${token}`);
  const summary = (
    <p>
      {inv.inviter ?? "A teammate"} invited <strong className="text-ink">{inv.email}</strong> to join the workspace <strong className="text-ink">{inv.workspace}</strong> as <strong className="text-ink">{inv.role}</strong>.
    </p>
  );

  if (!session) {
    return (
      <Card title="You're invited">
        {summary}
        <p>Sign in or create an account using <strong className="text-ink">{inv.email}</strong> to accept.</p>
        <div className="flex flex-col gap-3 sm:flex-row">
          <ButtonLink href={`/signup?next=${next}`} className="flex-1">Create account</ButtonLink>
          <ButtonLink href={`/login?next=${next}`} variant="secondary" className="flex-1">Log in</ButtonLink>
        </div>
      </Card>
    );
  }
  if (session.email.toLowerCase() !== inv.email) {
    return (
      <Card title="Wrong account">
        {summary}
        <p>You are signed in as <strong className="text-ink">{session.email}</strong>. Sign out and use the invited address to accept.</p>
        <Link href="/dashboard" className="text-violet underline">Back to the dashboard</Link>
      </Card>
    );
  }
  const already = (await pool!.query("select 1 from workspace_members where workspace_id=$1 and user_id=$2", [inv.workspace_id, session.userId])).rowCount;
  if (already) redirect("/dashboard");
  return (
    <Card title="You're invited">
      {summary}
      <AcceptButton token={token} />
    </Card>
  );
}

export default function Page(props: { params: Promise<{ token: string }> }) {
  return (
    <Suspense fallback={<div className="glass h-64 rounded-3xl" />}>
      <Content {...props} />
    </Suspense>
  );
}
