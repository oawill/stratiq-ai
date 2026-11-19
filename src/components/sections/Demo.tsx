"use client";

import { useState } from "react";
import { brand } from "@/lib/brand";
import { Container, SectionHeading } from "../ui/primitives";
import { SportsDemo } from "../demo/SportsDemo";
import { StrategyDemo } from "../demo/StrategyDemo";

const TABS = [
  { id: "sports", label: "Sports Prediction" },
  { id: "strategy", label: "Strategy Simulator" },
] as const;

export function Demo() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("sports");
  return (
    <section id="demo" className="py-20 lg:py-24">
      <Container>
        <SectionHeading
          eyebrow="Interactive demo"
          title={`See ${brand.name} in Action`}
          sub="Real calculations, running in your browser. No paid AI API, no live predictions."
        />
        <div className="glass rounded-3xl p-4 sm:p-8">
          <div role="tablist" aria-label="Demonstrations" className="mb-6 inline-flex rounded-xl border border-line bg-bg/60 p-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                id={`tab-${t.id}`}
                aria-selected={tab === t.id}
                aria-controls={`panel-${t.id}`}
                tabIndex={tab === t.id ? 0 : -1}
                onClick={() => setTab(t.id)}
                onKeyDown={(e) => {
                  if (e.key === "ArrowRight" || e.key === "ArrowLeft") setTab(tab === "sports" ? "strategy" : "sports");
                }}
                className={`rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
                  tab === t.id ? "bg-primary text-white" : "text-muted hover:text-ink"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
            {tab === "sports" ? <SportsDemo /> : <StrategyDemo />}
          </div>
        </div>
      </Container>
    </section>
  );
}
