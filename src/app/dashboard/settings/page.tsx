import type { Metadata } from "next";
import { requireSession } from "@/lib/auth";
import { logout } from "@/app/(auth)/actions";
import { Badge, PageTitle, Panel } from "@/components/dashboard/ui";
import { Button } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "Settings" };

export default async function Page() {
  const s = await requireSession();
  return (
    <>
      <PageTitle title="Settings" />
      <div className="grid max-w-2xl gap-4">
        <Panel title="Account">
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-muted">Name</dt><dd>{s.name}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Email</dt><dd>{s.email}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Workspace</dt><dd>{s.workspaceName}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Role</dt><dd>{s.role}</dd></div>
          </dl>
          <p className="mt-4 flex items-center gap-2 text-xs text-muted">Editing profile and password <Badge tone="muted">Coming soon</Badge></p>
        </Panel>
        <Panel title="Session">
          <form action={logout}><Button type="submit" variant="secondary">Sign out</Button></form>
        </Panel>
      </div>
    </>
  );
}
