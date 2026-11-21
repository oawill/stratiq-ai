import type { Metadata } from "next";
import { PageTitle } from "@/components/dashboard/ui";
import { DataClient } from "@/components/dashboard/data/DataClient";

export const metadata: Metadata = { title: "Data" };

export default function Page() {
  return (
    <>
      <PageTitle title="Data" sub="Bring your own data. Uploads are validated line by line, stored privately in this workspace, and used by Sports, Markets, Politics and SimLab. We do not supply or scrape market data." />
      <DataClient />
    </>
  );
}
