"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { Activity, Briefcase, ChevronDown, Landmark, LineChart, type LucideIcon } from "lucide-react";
import { brand } from "@/lib/brand";
import { ButtonLink, Container } from "../ui/primitives";

// The globe is drawn on a canvas that is only fetched in the browser; its box has a fixed size, so nothing shifts when it arrives.
const Globe = dynamic(() => import("../visualizations/IntelligenceGlobe").then((m) => m.IntelligenceGlobe), {
  ssr: false,
  loading: () => <div aria-hidden="true" className="absolute inset-[12%] animate-pulse rounded-full bg-white/[0.03]" />,
});

interface Module {
  id: string;
  href: string;
  title: string;
  icon: LucideIcon;
  accent: string;
  points: string[];
  pos: string;
  line: [number, number];
}

const MODULES: Module[] = [
  { id: "sports", href: "#sports", title: "Sports Intelligence", icon: Activity, accent: "#00E5FF", points: ["Match prediction", "Probability distribution", "Team comparison"], pos: "lg:left-0 lg:top-[4%]", line: [27, 17] },
  { id: "strategy", href: "#strategy", title: "Strategy Intelligence", icon: Briefcase, accent: "#8B5CF6", points: ["Game theory", "Competitive simulations", "Decision optimization"], pos: "lg:right-0 lg:top-[10%]", line: [73, 23] },
  { id: "politics", href: "#politics", title: "Political Intelligence", icon: Landmark, accent: "#60A5FA", points: ["Election forecasting", "Coalition scenarios", "Turnout modeling"], pos: "lg:bottom-[8%] lg:left-0", line: [27, 80] },
  { id: "markets", href: "#markets", title: "Market Intelligence", icon: LineChart, accent: "#34D399", points: ["Market regimes", "Risk forecasting", "Scenario analysis"], pos: "lg:bottom-[2%] lg:right-0", line: [73, 86] },
];

/** The first section: headline, calls to action, and the intelligence globe with four modules that scroll to their sections. */
export function IntelligenceHero() {
  const [hot, setHot] = useState<number | null>(null);
  const reduce = useReducedMotion();
  const { scrollY } = useScroll();
  const drift = useTransform(scrollY, [0, 900], [0, reduce ? 0 : 110]);
  const fade = useTransform(scrollY, [0, 700], [1, reduce ? 1 : 0.35]);

  return (
    <section id="home" aria-labelledby="home-title" className="cine-section cine-section-full flex items-center overflow-hidden pb-16 pt-28 lg:pb-12 lg:pt-24">
      <motion.div aria-hidden="true" style={{ y: drift, opacity: fade }} className="pointer-events-none absolute inset-0">
        <div className="grid-bg absolute inset-0" />
        <div className="absolute -top-32 left-1/2 h-[460px] w-[880px] -translate-x-1/2 rounded-full bg-azure/25 blur-[130px]" />
        <div className="absolute right-0 top-48 h-72 w-72 rounded-full bg-ion/10 blur-[110px]" />
        <div className="absolute bottom-0 left-0 h-64 w-64 rounded-full bg-royal/15 blur-[110px]" />
      </motion.div>

      <Container className="relative grid items-center gap-12 lg:grid-cols-[1fr_1.1fr] lg:gap-6">
        <div>
          <p className="cine-rise mb-5 text-xs font-semibold uppercase tracking-[0.25em] text-ion">{brand.tagline}</p>
          <h1 id="home-title" className="cine-rise-2 text-[2.5rem] font-extrabold leading-[1.05] tracking-tight sm:text-6xl lg:text-[4rem]">
            From Data to <span className="text-gradient">Strategic Advantage</span>
          </h1>
          <p className="cine-rise-3 mt-6 max-w-xl text-base leading-relaxed text-muted sm:text-lg">
            AI-powered prediction, simulation, and decision intelligence across sports, business, politics, and financial markets.
          </p>
          <div className="cine-rise-3 mt-8 flex flex-col gap-3 sm:flex-row">
            <ButtonLink href="#sports" className="py-3.5">Explore the Platform</ButtonLink>
            <ButtonLink href="/early-access" variant="secondary" className="py-3.5">Get Early Access</ButtonLink>
          </div>
          <p className="cine-rise-3 mt-5 text-xs text-muted">
            {brand.name} does not promise certainty. It helps you decide under uncertainty.{" "}
            <a href="/how-it-works" className="text-ion underline-offset-4 hover:underline">See How It Works</a>
          </p>
        </div>

        <div className="relative min-w-0 lg:aspect-square lg:min-h-[560px]">
          <div className="relative mx-auto aspect-square w-full max-w-sm lg:absolute lg:inset-0 lg:max-w-none">
            <Globe highlight={hot} />
          </div>
          <svg aria-hidden="true" viewBox="0 0 100 100" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 hidden h-full w-full lg:block">
            {MODULES.map((m, i) => (
              <line key={m.id} x1="50" y1="50" x2={m.line[0]} y2={m.line[1]} stroke={m.accent} strokeWidth="1.2" vectorEffect="non-scaling-stroke" className="flow-line" opacity={hot === i ? 0.95 : 0.35} />
            ))}
          </svg>
          <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:mt-0 lg:contents">
            {MODULES.map((m, i) => (
              <a
                key={m.id}
                href={m.href}
                aria-label={`${m.title}: jump to the ${m.id} section`}
                onMouseEnter={() => setHot(i)}
                onMouseLeave={() => setHot(null)}
                onFocus={() => setHot(i)}
                onBlur={() => setHot(null)}
                className={`glass group rounded-2xl p-4 transition-all duration-300 hover:-translate-y-1 lg:absolute lg:w-[44%] ${m.pos}`}
                style={{ boxShadow: hot === i ? `0 0 0 1px ${m.accent}66, 0 16px 44px -16px ${m.accent}88` : undefined }}
              >
                <span className="flex items-center gap-2.5 text-sm font-bold">
                  <m.icon className="h-5 w-5" style={{ color: m.accent }} aria-hidden="true" />
                  {m.title}
                </span>
                <ul className="mt-2 space-y-1 text-xs text-muted">
                  {m.points.map((p) => (
                    <li key={p} className="flex items-center gap-2"><span className="h-1 w-1 rounded-full" style={{ background: m.accent }} aria-hidden="true" />{p}</li>
                  ))}
                </ul>
              </a>
            ))}
          </div>
        </div>
      </Container>
      <a href="#sports" aria-label="Scroll to the Sports section" className="cine-pulse absolute bottom-5 left-1/2 hidden -translate-x-1/2 text-muted hover:text-ink lg:block">
        <ChevronDown className="h-6 w-6" aria-hidden="true" />
      </a>
    </section>
  );
}
