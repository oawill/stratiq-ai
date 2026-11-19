import type { Metadata } from "next";
import { HowItWorks } from "@/components/sections/HowItWorks";
import { Transparency } from "@/components/sections/Transparency";
import { Container } from "@/components/ui/primitives";
import { CtaSignup } from "@/components/sections/CtaSignup";

export const metadata: Metadata = {
  title: "How It Works",
  description: "The STRATIQ AI methodology: ingest, predict, simulate, understand — with transparent, evaluable models.",
  alternates: { canonical: "/how-it-works" },
};

export default function Page() {
  return (
    <>
      <Container className="pt-16 text-center">
        <h1 className="text-4xl font-extrabold tracking-tight sm:text-6xl">Platform Methodology</h1>
        <p className="mx-auto mt-4 max-w-2xl text-muted">
          Probabilities come from statistical models and explicit simulations — never from a language
          model guessing. AI is used to explain results, not to invent them.
        </p>
      </Container>
      <HowItWorks />
      <Transparency />
      <CtaSignup source="how-it-works" />
    </>
  );
}
