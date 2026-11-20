import type { Metadata } from "next";
import { brand } from "@/lib/brand";
import { PageTitle } from "@/components/dashboard/ui";
import { FinanceWorkspace } from "@/components/dashboard/finance/FinanceWorkspace";

export const metadata: Metadata = { title: { absolute: `${brand.products.markets.name} | Dashboard` } };

export default function Page() {
  return (
    <>
      <PageTitle
        title={brand.products.markets.name}
        sub="Educational portfolio risk tools: Monte Carlo simulation, Value at Risk and Expected Shortfall, stress tests and historical analysis of data you supply. Not investment advice, not a forecast, and nothing here can place a trade."
      />
      <FinanceWorkspace />
    </>
  );
}
