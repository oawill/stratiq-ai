import type { Metadata } from "next";
import { requireSession } from "@/lib/auth";
import { PageTitle } from "@/components/dashboard/ui";
import { TeamClient } from "@/components/dashboard/team/TeamClient";

export const metadata: Metadata = { title: "Team" };

export default async function Page() {
  const s = await requireSession();
  return (
    <>
      <PageTitle title="Team" sub={`Members, invitations and activity for the workspace "${s.workspaceName}". Everything saved here is shared with the people listed.`} />
      <TeamClient />
    </>
  );
}
