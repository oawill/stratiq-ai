import type { Metadata } from "next";
import { PageTitle } from "@/components/dashboard/ui";
import { WatchlistClient } from "@/components/dashboard/watchlists/WatchlistClient";

export const metadata: Metadata = { title: "Watchlists" };

export default function Page() {
  return (
    <>
      <PageTitle title="Watchlists" sub="Keep an eye on Premier League clubs and upcoming fixtures from your imported data. Your list is private to you; statuses are calculated from your own imports, not a live feed." />
      <WatchlistClient />
    </>
  );
}
