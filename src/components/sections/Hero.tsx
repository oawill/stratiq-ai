import { CheckCircle2 } from "lucide-react";
import { brand } from "@/lib/brand";
import { ButtonLink, Container } from "../ui/primitives";
import { DashboardMock } from "../DashboardMock";
import { ParticleField } from "../ParticleField";

const VALUES = [
  "Measurable predictive performance",
  "Multi-scenario and game-theoretic analysis",
  "Explainable, evidence-based strategic insights",
];

// "Predict Outcomes." leads in the gradient; the remaining sentences follow in plain text.
const [LEAD, ...REST] = brand.heroHeadline.split(". ").map((part, i, all) => (i < all.length - 1 ? `${part}.` : part));

export function Hero() {
  return (
    <section id="product" className="relative overflow-hidden pb-16 pt-10 sm:pt-16 lg:pb-24">
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        <div className="grid-bg absolute inset-0" />
        <div className="absolute -top-40 left-1/2 h-[480px] w-[900px] -translate-x-1/2 rounded-full bg-primary/25 blur-[120px]" />
        <div className="absolute right-0 top-40 h-72 w-72 rounded-full bg-cyan/10 blur-[110px]" />
        <ParticleField />
      </div>
      <Container className="relative grid items-center gap-12 lg:grid-cols-[1fr_1.15fr] lg:gap-10">
        <div>
          <p className="mb-5 text-xs font-semibold uppercase tracking-[0.25em] text-cyan">
            {brand.tagline}
          </p>
          <h1 className="text-[2.3rem] font-extrabold leading-[1.08] tracking-tight sm:text-5xl lg:text-[3.2rem]">
            <span className="text-gradient">{LEAD}</span> {REST.join(" ")}
          </h1>
          <p className="mt-6 max-w-xl text-base leading-relaxed text-muted sm:text-lg">
            {brand.description}
          </p>
          <ul className="mt-6 space-y-2.5">
            {VALUES.map((v) => (
              <li key={v} className="flex items-start gap-2.5 text-sm text-ink/90 sm:text-base">
                <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" aria-hidden="true" />
                {v}
              </li>
            ))}
          </ul>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <ButtonLink href="/early-access" className="py-3.5">
              Get Early Access
            </ButtonLink>
            <ButtonLink href="#demo" variant="secondary" className="py-3.5">
              Explore the Platform
            </ButtonLink>
          </div>
          <p className="mt-5 text-xs text-muted">
            {brand.name} does not promise certainty. It helps you decide under uncertainty.
          </p>
        </div>
        <div className="min-w-0">
          <DashboardMock />
        </div>
      </Container>
    </section>
  );
}
