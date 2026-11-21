import { Check } from "lucide-react";
import { brand } from "@/lib/brand";
import { ButtonLink, Container, Eyebrow, PreviewBadge } from "../ui/primitives";
import { CtaSignup } from "../sections/CtaSignup";
import { DOMAINS, type Domain } from "@/lib/site";

const STATUS: Record<Domain["slug"], { live: string; soon: string[] }> = {
  sports: {
    live: "Poisson match-probability demo on the home page (interactive, runs in your browser).",
    soon: ["Real fixture data and team ratings", "Backtesting dashboard", "Player-level analytics"],
  },
  business: {
    live: "Two-company pricing game with payoff matrix and pure Nash detection on the home page.",
    soon: ["Custom payoff builders", "Market-entry analysis", "Monte Carlo scenario comparison"],
  },
  politics: {
    live: "No interactive demo yet — this domain is in design.",
    soon: ["Aggregate scenario modeling", "Coalition analysis", "Turnout sensitivity"],
  },
  finance: {
    live: "No interactive demo yet — this domain is in design.",
    soon: ["Regime analysis", "Portfolio stress tests", "Macro sensitivity"],
  },
};

export function DomainPage({ slug }: { slug: Domain["slug"] }) {
  const d = DOMAINS.find((x) => x.slug === slug)!;
  const st = STATUS[slug];
  return (
    <>
      <section className="relative overflow-hidden py-16 sm:py-24">
        <div className="pointer-events-none absolute -top-32 left-1/2 h-96 w-[800px] -translate-x-1/2 rounded-full blur-[120px]" style={{ background: `${d.accent}30` }} aria-hidden="true" />
        <Container className="relative">
          <div className="mb-4 flex items-center gap-3">
            <Eyebrow>{d.name}</Eyebrow>
            <PreviewBadge>Preview</PreviewBadge>
          </div>
          <h1 className="max-w-3xl text-4xl font-extrabold tracking-tight sm:text-6xl">{d.headline}</h1>
          <p className="mt-6 max-w-2xl text-lg text-muted">{d.description}</p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <ButtonLink href="/early-access">Get Early Access</ButtonLink>
            {(slug === "sports" || slug === "business") && (
              <ButtonLink href="/#sports" variant="secondary">Try the interactive demo</ButtonLink>
            )}
          </div>
        </Container>
      </section>
      <Container className="grid gap-6 pb-8 md:grid-cols-2">
        <div className="glass rounded-3xl p-6 sm:p-8">
          <h2 className="mb-4 text-xl font-bold">Planned capabilities</h2>
          <ul className="space-y-3">
            {d.features.map((f) => (
              <li key={f} className="flex items-start gap-2.5">
                <Check className="mt-0.5 h-5 w-5 shrink-0" style={{ color: d.accent }} aria-hidden="true" />
                {f}
              </li>
            ))}
          </ul>
        </div>
        <div className="glass rounded-3xl p-6 sm:p-8">
          <h2 className="mb-3 text-xl font-bold">What works today</h2>
          <p className="text-sm text-muted">{st.live}</p>
          <h3 className="mb-2 mt-6 flex items-center gap-2 text-sm font-semibold">
            Coming soon <PreviewBadge>Roadmap</PreviewBadge>
          </h3>
          <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted">
            {st.soon.map((s) => <li key={s}>{s}</li>)}
          </ul>
          {(slug === "politics" || slug === "finance") && (
            <p className="mt-6 rounded-lg border border-line bg-bg/60 p-3 text-xs text-muted">
              {slug === "politics"
                ? "Political modeling is nonpartisan, aggregate, and scenario-based. It does not target individuals or endorse any party or candidate."
                : "Financial analysis is educational scenario modeling, not investment advice. " + brand.name + " is not a licensed financial advisor."}
            </p>
          )}
        </div>
      </Container>
      <CtaSignup source={`domain-${slug}`} />
    </>
  );
}
