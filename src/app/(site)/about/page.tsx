import type { Metadata } from "next";
import { brand } from "@/lib/brand";
import { Container } from "@/components/ui/primitives";
import { CtaSignup } from "@/components/sections/CtaSignup";

export const metadata: Metadata = {
  title: "About",
  description: `${brand.name} helps people make better decisions under uncertainty.`,
  alternates: { canonical: "/about" },
};

export default function Page() {
  return (
    <>
      <Container className="max-w-3xl py-16">
        <h1 className="text-4xl font-extrabold tracking-tight sm:text-6xl">About {brand.name}</h1>
        <div className="mt-8 space-y-5 text-lg leading-relaxed text-muted">
          <p>
            {brand.name} is an early-stage predictive analytics and strategic intelligence platform combining machine learning,
            probability modeling, game theory, and Monte Carlo simulation across sports, business,
            politics, and finance.
          </p>
          <p>
            <strong className="text-ink">We do not promise certainty.</strong> We help people reason
            about uncertainty: what might happen, how likely it is, and how strategic choices change
            the picture.
          </p>
          <h2 className="pt-4 text-2xl font-bold text-ink">Our principles</h2>
          <ul className="list-disc space-y-2 pl-6 text-base">
            <li>Calculations are mathematical and reproducible; language models only explain them.</li>
            <li>We publish evaluation results — and say &ldquo;evaluation in progress&rdquo; until we have them.</li>
            <li>Demonstration data is always labeled as demonstration data.</li>
            <li>Political modeling is nonpartisan and aggregate. Financial content is educational, not advice.</li>
          </ul>
        </div>
      </Container>
      <CtaSignup source="about" />
    </>
  );
}
