import type { Metadata } from "next";
import { requireSession } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import type { League } from "@/lib/types";
import { ErrorPanel, PageTitle } from "@/components/dashboard/ui";
import { SportsWorkspace } from "@/components/dashboard/sports/SportsWorkspace";

export const metadata: Metadata = { title: "Sports Intelligence" };

export default async function Page({ searchParams }: { searchParams: Promise<{ league?: string; team?: string }> }) {
  const s = await requireSession();
  const sp = await searchParams;
  let leagues: League[];
  try {
    leagues = (await apiFetch<{ leagues: League[] }>(s, "sports/leagues")).leagues;
  } catch (e) {
    return (<><PageTitle title="Sports Intelligence" /><ErrorPanel message={e instanceof Error ? e.message : "The analytics service is unavailable."} /></>);
  }
  return (
    <>
      <PageTitle title="Sports Intelligence" sub="Poisson match forecasts. Start simple, then switch on Advanced analytics for scorelines, ratings and history." />
      <SportsWorkspace leagues={leagues} initialLeague={sp.league} initialTeam={sp.team} />
    </>
  );
}
