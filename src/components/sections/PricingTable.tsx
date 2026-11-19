"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { ButtonLink, Container, SectionHeading } from "../ui/primitives";
import { ANNUAL_DISCOUNT, annualMonthly, annualTotal } from "@/lib/pricing";

const TIERS = [
  { name: "Explorer", monthly: 0, blurb: "Learn the fundamentals.", features: ["Basic demonstrations", "Limited scenarios", "Public educational content"] },
  { name: "Sports Pro", monthly: 12, blurb: "For serious match analysis.", features: ["Advanced match forecasts", "Team comparisons", "Prediction history", "Model performance insights"], featured: false },
  { name: "Strategy Pro", monthly: 59, blurb: "For analysts and strategists.", features: ["Advanced game theory tools", "Monte Carlo simulations", "Saved scenarios", "Scenario comparisons", "Report exports"], featured: true },
  { name: "Enterprise", monthly: null, blurb: "For teams and organizations.", features: ["Team workspaces", "Advanced permissions", "API access", "Organization reporting", "Custom integrations"] },
];

export function PricingTable({ heading = true }: { heading?: boolean }) {
  const [annual, setAnnual] = useState(false);
  return (
    <section id="pricing" className="py-20 lg:py-24">
      <Container>
        {heading && (
          <SectionHeading eyebrow="Pricing" title="Simple pricing, proposed for launch" sub="Billing is not live yet. Every plan currently leads to early-access registration." />
        )}
        <div className="mb-10 flex items-center justify-center gap-3 text-sm">
          <span className={annual ? "text-muted" : "font-semibold"}>Monthly</span>
          <button
            type="button"
            role="switch"
            aria-checked={annual}
            aria-label="Annual billing"
            onClick={() => setAnnual((v) => !v)}
            className={`relative h-7 w-12 rounded-full transition-colors ${annual ? "bg-primary" : "bg-white/15"}`}
          >
            <span className={`absolute top-0.5 h-6 w-6 rounded-full bg-white transition-all ${annual ? "left-[22px]" : "left-0.5"}`} />
          </button>
          <span className={annual ? "font-semibold" : "text-muted"}>
            Annual <span className="text-success">(save {Math.round(ANNUAL_DISCOUNT * 100)}%)</span>
          </span>
        </div>
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          {TIERS.map((t) => (
            <div
              key={t.name}
              className={`glass flex flex-col rounded-3xl p-6 ${t.featured ? "border-primary/70 shadow-[0_0_50px_-15px_rgba(128,85,246,0.8)]" : ""}`}
            >
              {t.featured && <span className="mb-2 w-fit rounded-full bg-primary/20 px-2.5 py-0.5 text-[11px] font-semibold text-violet">Most capable</span>}
              {heading ? <h3 className="text-lg font-bold">{t.name}</h3> : <h2 className="text-lg font-bold">{t.name}</h2>}
              <p className="text-sm text-muted">{t.blurb}</p>
              <div className="my-5">
                {t.monthly === null ? (
                  <div className="text-3xl font-extrabold">Custom</div>
                ) : t.monthly === 0 ? (
                  <div className="text-3xl font-extrabold">Free</div>
                ) : (
                  <>
                    <div className="text-3xl font-extrabold">
                      ${annual ? annualMonthly(t.monthly) : t.monthly}
                      <span className="text-sm font-normal text-muted">/month</span>
                    </div>
                    {annual && (
                      <div className="mt-1 text-xs text-muted">
                        ${annualTotal(t.monthly)} billed yearly = ${t.monthly} × 12 × (1 − {ANNUAL_DISCOUNT})
                      </div>
                    )}
                  </>
                )}
              </div>
              <ul className="mb-6 flex-1 space-y-2">
                {t.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden="true" />
                    {f}
                  </li>
                ))}
              </ul>
              <ButtonLink href={`/early-access?plan=${encodeURIComponent(t.name)}`} variant={t.featured ? "primary" : "secondary"}>
                {t.monthly === null ? "Contact via early access" : "Join early access"}
              </ButtonLink>
            </div>
          ))}
        </div>
        <p className="mt-6 text-center text-xs text-muted">
          Prices are proposed launch prices and may change. Annual discount is configurable in <code>src/lib/pricing.ts</code>.
        </p>
      </Container>
    </section>
  );
}
