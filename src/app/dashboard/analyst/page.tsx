import type { Metadata } from "next";
import { PageTitle } from "@/components/dashboard/ui";
import { AnalystWorkspace } from "@/components/dashboard/analyst/AnalystWorkspace";

export const metadata: Metadata = { title: "AI Analyst" };

export default function Page() {
  return (
    <>
      <PageTitle title="AI Analyst" sub="Ask about the Premier League data you imported, the model's forecasts and backtests, and your saved simulations. Every answer is built from retrieved records and shows its sources, timestamps and assumptions. It has no live feeds and cannot run anything for you." />
      <AnalystWorkspace />
    </>
  );
}
