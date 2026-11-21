import type { Metadata } from "next";
import { brand } from "@/lib/brand";
import { PageTitle } from "@/components/dashboard/ui";
import { SimLabHub } from "@/components/dashboard/simlab/SimLabHub";

export const metadata: Metadata = { title: { absolute: `${brand.products.simlab.name} | Dashboard` } };

export default function Page() {
  return (
    <>
      <PageTitle
        title={brand.products.simlab.name}
        sub="Scenario simulation across Sports, Business, Politics and Markets. Calibrated parameters are kept apart from your assumptions, and every saved run records its model, inputs and data provenance. Outputs describe hypotheticals, not real-world forecasts."
      />
      <SimLabHub />
    </>
  );
}
