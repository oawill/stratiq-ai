import type { Metadata } from "next";
import { PageTitle } from "@/components/dashboard/ui";
import { BusinessWorkspace } from "@/components/dashboard/business/BusinessWorkspace";

export const metadata: Metadata = { title: "Business Strategy" };

export default function Page() {
  return (
    <>
      <PageTitle
        title="Business Strategy"
        sub="Define two competitors, enter payoffs, and an exact, deterministic solver finds equilibria, best responses and dominant strategies. Nothing here is a forecast of real competitor behavior."
      />
      <BusinessWorkspace />
    </>
  );
}
