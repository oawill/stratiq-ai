import type { Metadata } from "next";
import { Hero } from "@/components/sections/Hero";
import { Pillars } from "@/components/sections/Pillars";
import { Demo } from "@/components/sections/Demo";
import { HowItWorks } from "@/components/sections/HowItWorks";
import { Transparency } from "@/components/sections/Transparency";
import { PricingTable } from "@/components/sections/PricingTable";
import { CtaSignup } from "@/components/sections/CtaSignup";

export const metadata: Metadata = {
  title: { absolute: "STRATIQ AI — Strategic Intelligence for a Complex World" },
  alternates: { canonical: "/" },
};

export default function Home() {
  return (
    <>
      <Hero />
      <Pillars />
      <Demo />
      <HowItWorks />
      <Transparency />
      <PricingTable />
      <CtaSignup />
    </>
  );
}
