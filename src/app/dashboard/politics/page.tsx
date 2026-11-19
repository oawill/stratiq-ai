import type { Metadata } from "next";
import { PageTitle } from "@/components/dashboard/ui";
import { PoliticsWorkspace } from "@/components/dashboard/politics/PoliticsWorkspace";

export const metadata: Metadata = { title: "Political Intelligence" };

export default function Page() {
  return (
    <>
      <PageTitle
        title="Political Intelligence"
        sub="Nonpartisan scenario tools for coalition arithmetic, voting power, turnout sensitivity and policy trade-offs. Everything is computed from assumptions you enter. There is no polling data, no forecast, and no individual-level analysis."
      />
      <PoliticsWorkspace />
    </>
  );
}
