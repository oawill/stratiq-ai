import type { Metadata } from "next";
import { PageTitle } from "@/components/dashboard/ui";
import { FinanceWorkspace } from "@/components/dashboard/finance/FinanceWorkspace";

export const metadata: Metadata = { title: "Financial Intelligence" };

export default function Page() {
  return (
    <>
      <PageTitle
        title="Financial Intelligence"
        sub="Educational portfolio risk tools: Monte Carlo simulation, Value at Risk and Expected Shortfall, stress tests and historical analysis of data you supply. Not investment advice, not a forecast, and nothing here can place a trade."
      />
      <FinanceWorkspace />
    </>
  );
}
