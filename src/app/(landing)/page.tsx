import type { Metadata } from "next";
import { brand } from "@/lib/brand";
import { IntelligenceHero } from "@/components/landing/IntelligenceHero";
import { SportsSection } from "@/components/landing/SportsSection";
import { StrategySection } from "@/components/landing/StrategySection";
import { PoliticsSection } from "@/components/landing/PoliticsSection";
import { MarketsSection } from "@/components/landing/MarketsSection";
import { SectionTransition } from "@/components/landing/SectionTransition";
import { WorkflowStrip } from "@/components/landing/WorkflowStrip";
import { HowItWorks } from "@/components/sections/HowItWorks";
import { Pillars } from "@/components/sections/Pillars";
import { Transparency } from "@/components/sections/Transparency";
import { PricingTable } from "@/components/sections/PricingTable";
import { CtaSignup } from "@/components/sections/CtaSignup";

export const metadata: Metadata = {
  title: { absolute: brand.homeTitle },
  alternates: { canonical: "/" },
};

/**
 * One continuous page: five cinematic sections joined by transition bands, then the trust and conversion sections
 * (workflow, how it works, capabilities, methodology and performance disclosures, pricing, early access).
 */
export default function Home() {
  return (
    <>
      <IntelligenceHero />
      <SectionTransition kind="home-sports" />
      <SportsSection />
      <SectionTransition kind="sports-strategy" />
      <StrategySection />
      <SectionTransition kind="strategy-politics" />
      <PoliticsSection />
      <SectionTransition kind="politics-markets" />
      <MarketsSection />
      <WorkflowStrip />
      <HowItWorks />
      <Pillars />
      <Transparency />
      <PricingTable />
      <CtaSignup />
    </>
  );
}
