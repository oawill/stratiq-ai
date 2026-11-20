import type { Metadata } from "next";
import { brand } from "@/lib/brand";
import { PageTitle } from "@/components/dashboard/ui";
import { SimWorkspace } from "@/components/dashboard/simulations/SimWorkspace";

export const metadata: Metadata = { title: { absolute: `${brand.products.simlab.name} | Dashboard` } };

export default function Page() {
  return (
    <>
      <PageTitle
        title={brand.products.simlab.name}
        sub="Define uncertain inputs and formulas, then run a seeded Monte Carlo simulation in the background. Same seed, same results. Outputs describe your assumptions, not real-world forecasts."
      />
      <SimWorkspace />
    </>
  );
}
