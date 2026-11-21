import { ArrowRight, Check } from "lucide-react";
import { Container, SectionHeading } from "../ui/primitives";
import { Reveal } from "../Motion";
import { DOMAINS, type Domain } from "@/lib/site";

/** Custom SVG visual per domain — no stock imagery. */
function Visual({ d }: { d: Domain }) {
  const c = d.accent;
  return (
    <svg viewBox="0 0 320 120" className="h-28 w-full" aria-hidden="true" preserveAspectRatio="none">
      <defs>
        <linearGradient id={`v-${d.slug}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={c} stopOpacity="0.5" />
          <stop offset="1" stopColor={c} stopOpacity="0" />
        </linearGradient>
      </defs>
      {d.slug === "sports" && (
        <>
          {[0, 1, 2, 3, 4, 5, 6].map((i) => (
            <rect key={i} x={20 + i * 42} y={110 - [30, 55, 80, 95, 70, 40, 22][i]} width="26" height={[30, 55, 80, 95, 70, 40, 22][i]} rx="4" fill={c} opacity={0.25 + i * 0.07} />
          ))}
        </>
      )}
      {d.slug === "business" && (
        <>
          {[0, 1, 2].map((r) =>
            [0, 1, 2].map((k) => (
              <rect key={`${r}${k}`} x={70 + k * 62} y={10 + r * 34} width="56" height="28" rx="5" fill={c} opacity={0.15 + ((r * 3 + k) % 4) * 0.2} />
            )),
          )}
        </>
      )}
      {d.slug === "politics" && (
        <>
          <path d="M20 100 A 140 90 0 0 1 300 100" fill="none" stroke={c} strokeOpacity="0.25" strokeWidth="18" />
          <path d="M20 100 A 140 90 0 0 1 190 17" fill="none" stroke={c} strokeWidth="18" strokeOpacity="0.8" />
          <path d="M190 17 A 140 90 0 0 1 270 52" fill="none" stroke="#22d3ee" strokeWidth="18" strokeOpacity="0.7" />
        </>
      )}
      {d.slug === "finance" && (
        <>
          <path d="M0 90 C40 80 60 30 100 50 S160 100 200 55 S280 20 320 30 V120 H0Z" fill={`url(#v-${d.slug})`} />
          <path d="M0 90 C40 80 60 30 100 50 S160 100 200 55 S280 20 320 30" fill="none" stroke={c} strokeWidth="2.5" />
        </>
      )}
    </svg>
  );
}

export function Pillars() {
  return (
    <section id="intelligence" className="py-20 lg:py-28">
      <Container>
        <SectionHeading
          eyebrow="Four intelligence pillars"
          title="One platform. Four domains of strategic decision-making."
          sub="Each pillar combines probability, simulation, and game theory — and shows its assumptions."
        />
        <div className="grid gap-6 md:grid-cols-2">
          {DOMAINS.map((d, i) => (
            <Reveal key={d.slug} delay={(i % 2) * 0.08}>
              <article className="glass glow-ring flex h-full flex-col rounded-3xl p-6 transition-shadow sm:p-8">
                <div className="mb-5 overflow-hidden rounded-2xl border border-line bg-bg/50 p-3">
                  <Visual d={d} />
                </div>
                <div className="mb-2 flex items-center gap-2 text-sm font-semibold" style={{ color: d.accent }}>
                  <d.icon className="h-5 w-5" aria-hidden="true" />
                  {d.name}
                </div>
                <h3 className="text-2xl font-bold tracking-tight">{d.headline}</h3>
                <p className="mt-3 text-sm leading-relaxed text-muted sm:text-base">{d.description}</p>
                <ul className="mt-5 grid gap-2 sm:grid-cols-2">
                  {d.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm text-ink/90">
                      <Check className="mt-0.5 h-4 w-4 shrink-0" style={{ color: d.accent }} aria-hidden="true" />
                      {f}
                    </li>
                  ))}
                </ul>
                <a
                  href={`/#${d.slug}`}
                  className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-violet transition-colors hover:text-ink"
                >
                  {d.cta} <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </a>
              </article>
            </Reveal>
          ))}
        </div>
      </Container>
    </section>
  );
}
