import type { Metadata } from "next";
import { PageTitle } from "@/components/dashboard/ui";
import { WatchlistClient } from "@/components/dashboard/watchlists/WatchlistClient";

export const metadata: Metadata = { title: "Watchlists" };

export default function Page() {
  return (
    <>
      <PageTitle title="Watchlists" sub="Follow clubs, fixtures and competitions from your imported data, and keep your own notes on companies, indicators, elections and instruments. Your list is private to you; sports statuses are calculated from your own imports, not a live feed." />
      <WatchlistClient />
    </>
  );
}
