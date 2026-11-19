import { Container } from "../ui/primitives";
import { brand } from "@/lib/brand";
import { EarlyAccessForm } from "../EarlyAccessForm";

export function CtaSignup({ source = "home" }: { source?: string }) {
  return (
    <section id="early-access" className="relative py-20 lg:py-24">
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent via-primary/10 to-transparent" aria-hidden="true" />
      <Container className="relative grid items-center gap-10 lg:grid-cols-2">
        <div>
          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-cyan">Early access</p>
          <h2 className="text-3xl font-bold tracking-tight sm:text-5xl">
            Make better decisions <span className="text-gradient">under uncertainty.</span>
          </h2>
          <p className="mt-4 max-w-lg text-muted">
            {brand.name} does not promise certainty. Join the early-access list and help shape a platform
            built on transparent models, honest probabilities, and strategic reasoning.
          </p>
        </div>
        <EarlyAccessForm source={source} />
      </Container>
    </section>
  );
}
