import type { Metadata } from "next";
import { brand } from "@/lib/brand";
import { requireSession } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import type { League } from "@/lib/types";
import { ErrorPanel, PageTitle } from "@/components/dashboard/ui";
import { SportsWorkspace } from "@/components/dashboard/sports/SportsWorkspace";

export const metadata: Metadata = { title: { absolute: `${brand.products.sports.name} | Dashboard` } };

export default async function Page({ searchParams }: { searchParams: Promise<{ league?: string; team?: string }> }) {
  const s = await requireSession();
  const sp = await searchParams;
  let leagues: League[];
  try {
    leagues = (await apiFetch<{ leagues: League[] }>(s, "sports/leagues")).leagues;
  } catch (e) {
    return (<><PageTitle title={brand.products.sports.name} /><ErrorPanel message={e instanceof Error ? e.message : "The analytics service is unavailable."} /></>);
  }
  return (
    <>
      <PageTitle title={brand.products.sports.name} sub="Poisson match forecasts. Start simple, then switch on Advanced analytics for scorelines, ratings and history." />
      <SportsWorkspace leagues={leagues} initialLeague={sp.league} initialTeam={sp.team} />
    </>
  );
}
