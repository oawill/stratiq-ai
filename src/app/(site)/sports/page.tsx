import type { Metadata } from "next";
import { DomainPage } from "@/components/pages/DomainPage";
import { DOMAINS } from "@/lib/site";

const d = DOMAINS.find((x) => x.slug === "sports")!;
export const metadata: Metadata = {
  title: { absolute: `${d.name} — ${d.headline}` },
  description: d.description,
  alternates: { canonical: "/sports" },
  openGraph: { title: `${d.name} — ${d.headline}`, description: d.description },
};

export default function Page() {
  return <DomainPage slug="sports" />;
}
