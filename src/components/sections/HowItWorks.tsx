"use client";

import { motion } from "framer-motion";
import { Database, Lightbulb, LineChart, Shuffle } from "lucide-react";
import { Container, SectionHeading } from "../ui/primitives";

const STEPS = [
  { n: "01", title: "Ingest Data", icon: Database, text: "Historical records, market information, performance metrics, and structured scenario inputs." },
  { n: "02", title: "Predict", icon: LineChart, text: "Statistical models and machine learning estimate potential outcomes." },
  { n: "03", title: "Simulate", icon: Shuffle, text: "Game theory and Monte Carlo methods evaluate alternative strategic scenarios." },
  { n: "04", title: "Understand", icon: Lightbulb, text: "Explainable AI translates analytical results into understandable decision intelligence." },
];

export function HowItWorks() {
  return (
    <section id="how" className="py-20 lg:py-24">
      <Container>
        <SectionHeading eyebrow="Methodology" title="How STRATIQ AI Works" />
        <ol className="relative grid gap-6 md:grid-cols-4">
          <svg className="pointer-events-none absolute left-0 top-9 hidden h-2 w-full md:block" aria-hidden="true" preserveAspectRatio="none" viewBox="0 0 100 2">
            <line x1="12" x2="88" y1="1" y2="1" stroke="#8055f6" strokeOpacity="0.6" strokeWidth="0.4" vectorEffect="non-scaling-stroke" className="flow-line" />
          </svg>
          {STEPS.map((s, i) => (
            <motion.li
              key={s.n}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-40px" }}
              transition={{ delay: i * 0.12, duration: 0.5 }}
              className="glass relative rounded-2xl p-6"
            >
              <div className="relative z-10 mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-primary/50 bg-bg shadow-[0_0_30px_-6px_rgba(128,85,246,0.7)]">
                <s.icon className="h-6 w-6 text-violet" aria-hidden="true" />
              </div>
              <div className="font-mono text-xs text-cyan">{s.n}</div>
              <h3 className="mt-1 text-lg font-bold">{s.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{s.text}</p>
            </motion.li>
          ))}
        </ol>
      </Container>
    </section>
  );
}
