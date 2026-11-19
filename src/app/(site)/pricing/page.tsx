import type { Metadata } from "next";
import { brand } from "@/lib/brand";
import { PricingTable } from "@/components/sections/PricingTable";
import { Container } from "@/components/ui/primitives";

export const metadata: Metadata = {
  title: "Pricing",
  description: `Proposed launch pricing for ${brand.name}. Billing is not live yet; all plans lead to early-access registration.`,
  alternates: { canonical: "/pricing" },
};

export default function Page() {
  return (
    <>
      <Container className="pt-16 text-center">
        <h1 className="text-4xl font-extrabold tracking-tight sm:text-6xl">Pricing</h1>
        <p className="mx-auto mt-4 max-w-xl text-muted">
          Proposed launch prices. Billing is not live yet — choosing a plan registers your interest.
        </p>
      </Container>
      <PricingTable heading={false} />
    </>
  );
}
