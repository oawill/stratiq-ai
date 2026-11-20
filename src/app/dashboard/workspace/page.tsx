import type { Metadata } from "next";
import Link from "next/link";
import { requireSession } from "@/lib/auth";
import { getPool } from "@/lib/db";
import { Badge, ErrorPanel, PageTitle, Panel } from "@/components/dashboard/ui";
import { LibraryClient } from "@/components/dashboard/workspace/LibraryClient";

export const metadata: Metadata = { title: "My Workspace" };

export default async function Page() {
  const s = await requireSession();
  const pool = getPool();
  let members: { name: string; email: string; role: string }[] = [];
  try {
    // Scoped to the caller's own workspace id from the server-side session.
    members = (await pool!.query(
      `select u.name, u.email, m.role from workspace_members m join users u on u.id = m.user_id
        where m.workspace_id = $1 order by m.created_at`, [s.workspaceId])).rows;
  } catch {
    return (<><PageTitle title="My Workspace" /><ErrorPanel message="Could not load workspace members." /></>);
  }
  return (
    <>
      <PageTitle title="My Workspace" sub="Everything you save is private to this workspace. Switch workspaces, browse and search your saved work, and export it." />
      <Panel title={s.workspaceName} badge={<Badge tone="violet">{s.role}</Badge>}>
        <ul className="divide-y divide-line">
          {members.map((m) => (
            <li key={m.email} className="flex items-center justify-between py-2.5 text-sm">
              <span>{m.name} <span className="text-muted">· {m.email}</span></span>
              <Badge tone="muted">{m.role}</Badge>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-muted">Invite teammates and manage roles on the <Link href="/dashboard/team" className="text-violet underline">Team page</Link>.</p>
      </Panel>
      <LibraryClient role={s.role} />
    </>
  );
}
