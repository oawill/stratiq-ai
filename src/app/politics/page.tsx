import type { Metadata } from "next";
import { DomainPage } from "@/components/pages/DomainPage";
import { DOMAINS } from "@/lib/site";

const d = DOMAINS.find((x) => x.slug === "politics")!;
export const metadata: Metadata = {
  title: d.name,
  description: d.description,
  alternates: { canonical: "/politics" },
  openGraph: { title: d.name + " | STRATIQ AI", description: d.description },
};

export default function Page() {
  return <DomainPage slug="politics" />;
}
