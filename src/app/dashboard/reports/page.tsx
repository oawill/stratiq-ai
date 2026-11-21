import type { Metadata } from "next";
import { PageTitle } from "@/components/dashboard/ui";
import { ReportClient } from "@/components/dashboard/reports/ReportClient";

export const metadata: Metadata = { title: "Reports" };

export default function Page() {
  return (
    <>
      <PageTitle title="Reports" sub="An evidence report for this workspace: where the data came from, what the backtests measured on past matches, and how tracked forecasts have done, kept in separate sections." />
      <ReportClient />
    </>
  );
}
