import type { Metadata } from "next";
import Link from "next/link";
import { PageTitle } from "@/components/dashboard/ui";
import { ReportClient } from "@/components/dashboard/reports/ReportClient";
import { BriefingsClient } from "@/components/dashboard/reports/BriefingsClient";
import { LibraryClient } from "@/components/dashboard/reports/LibraryClient";

export const metadata: Metadata = { title: "Reports" };

const TABS = [
  { id: "evidence", label: "Evidence report" },
  { id: "briefings", label: "Briefings" },
  { id: "library", label: "Saved intelligence" },
] as const;

export default async function Page({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab } = await searchParams;
  const current = TABS.find((t) => t.id === tab)?.id ?? "evidence";
  return (
    <>
      <PageTitle title="Reports" sub="An evidence report for this workspace, your briefings, and everything you have saved. Evidence is read from stored records, and forecasts are kept apart from what was observed." />
      <nav aria-label="Reports sections" className="mb-5 flex flex-wrap gap-2 print:hidden">
        {TABS.map((t) => (
          <Link key={t.id} href={t.id === "evidence" ? "/dashboard/reports" : `/dashboard/reports?tab=${t.id}`} aria-current={t.id === current ? "page" : undefined}
            className={`rounded-xl border px-4 py-2 text-sm font-semibold ${t.id === current ? "border-violet bg-violet/15 text-ink" : "border-line text-muted hover:bg-white/5 hover:text-ink"}`}>{t.label}</Link>
        ))}
      </nav>
      {current === "evidence" && <ReportClient />}
      {current === "briefings" && <BriefingsClient />}
      {current === "library" && <LibraryClient />}
    </>
  );
}
