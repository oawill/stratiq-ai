import type { Metadata } from "next";
import { brand } from "@/lib/brand";
import { DomainPage } from "@/components/pages/DomainPage";
import { DOMAINS } from "@/lib/site";

const d = DOMAINS.find((x) => x.slug === "business")!;
export const metadata: Metadata = {
  title: d.name,
  description: d.description,
  alternates: { canonical: "/business" },
  openGraph: { title: `${d.name} | ${brand.name}`, description: d.description },
};

export default function Page() {
  return <DomainPage slug="business" />;
}
