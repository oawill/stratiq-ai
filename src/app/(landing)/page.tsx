import type { Metadata } from "next";
import { brand } from "@/lib/brand";
import { IntelligenceHero } from "@/components/landing/IntelligenceHero";
import { Pillars } from "@/components/sections/Pillars";
import { HowItWorks } from "@/components/sections/HowItWorks";
import { Transparency } from "@/components/sections/Transparency";
import { PricingTable } from "@/components/sections/PricingTable";
import { CtaSignup } from "@/components/sections/CtaSignup";

export const metadata: Metadata = {
  title: { absolute: brand.homeTitle },
  alternates: { canonical: "/" },
};

export default function Home() {
  return (
    <>
      <IntelligenceHero />
      <Pillars />
      <HowItWorks />
      <Transparency />
      <PricingTable />
      <CtaSignup />
    </>
  );
}
