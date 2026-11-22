import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PageTitle } from "@/components/dashboard/ui";
import { MatchPage } from "@/components/dashboard/sports/live/MatchPage";

export const metadata: Metadata = { title: "Match intelligence" };

export default async function Page({ params }: { params: Promise<{ fixtureId: string }> }) {
  const { fixtureId } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(fixtureId)) notFound();
  return (
    <>
      <PageTitle title="Match intelligence" sub="One fixture in full: the forecast and how it changed, the history behind it, and, once played, how it turned out. Each section says whether it is historical statistics, current verified information or a model estimate." />
      <MatchPage fixtureId={fixtureId} />
    </>
  );
}
