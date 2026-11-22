import type { Metadata } from "next";
import { PageTitle } from "@/components/dashboard/ui";
import { LivePredictions } from "@/components/dashboard/sports/live/LivePredictions";
import { TABS, type TabId } from "@/components/dashboard/sports/live/live";

export const metadata: Metadata = { title: "Live Predictions" };

export default async function Page({ searchParams }: { searchParams: Promise<{ tab?: string; fixture?: string }> }) {
  const sp = await searchParams;
  const tab: TabId = TABS.find((t) => t.id === sp.tab)?.id ?? "today";
  const fixture = sp.fixture && /^[0-9a-f-]{36}$/i.test(sp.fixture) ? sp.fixture : undefined;
  return (
    <>
      <PageTitle title="Live Predictions" sub="Upcoming Premier League fixtures from a licensed provider, with versioned pre-match forecasts. Each forecast is a model estimate made before kickoff and kept, never overwritten." />
      <LivePredictions tab={tab} fixture={fixture} />
    </>
  );
}
