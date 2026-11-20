import type { Metadata } from "next";
import { DomainPage } from "@/components/pages/DomainPage";
import { DOMAINS } from "@/lib/site";

const d = DOMAINS.find((x) => x.slug === "business")!;
export const metadata: Metadata = {
  title: { absolute: `${d.name} — ${d.headline}` },
  description: d.description,
  alternates: { canonical: "/business" },
  openGraph: { title: `${d.name} — ${d.headline}`, description: d.description },
};

export default function Page() {
  return <DomainPage slug="business" />;
}
