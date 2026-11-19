import type { Metadata } from "next";
import { brand } from "@/lib/brand";
import { PageTitle } from "@/components/dashboard/ui";
import { PoliticsWorkspace } from "@/components/dashboard/politics/PoliticsWorkspace";

export const metadata: Metadata = { title: brand.products.politics.name };

export default function Page() {
  return (
    <>
      <PageTitle
        title={brand.products.politics.name}
        sub="Nonpartisan scenario tools for coalition arithmetic, voting power, turnout sensitivity and policy trade-offs. Everything is computed from assumptions you enter. There is no polling data, no forecast, and no individual-level analysis."
      />
      <PoliticsWorkspace />
    </>
  );
}
