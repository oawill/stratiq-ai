import type { ReactNode } from "react";
import { Container } from "../ui/primitives";
import { Reveal } from "../Motion";

/** Marks demonstration content so it is never mistaken for live data or a verified result. */
export function DemoBadge({ children = "Simulated demonstration data" }: { children?: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-300/40 bg-amber-300/10 px-3 py-1 text-[11px] font-semibold text-amber-200">
      <span className="h-1.5 w-1.5 rounded-full bg-amber-300" aria-hidden="true" />
      {children}
    </span>
  );
}

/** The frame shared by the four product sections: anchor id, numbered eyebrow, headline, supporting text and a background layer. */
export function SectionShell({
  id,
  index,
  eyebrow,
  title,
  sub,
  accent,
  background,
  children,
}: {
  id: string;
  index: string;
  eyebrow: string;
  title: ReactNode;
  sub: string;
  accent: string;
  background?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="cine-section cine-section-full overflow-hidden py-20 lg:py-28">
      {background && <div aria-hidden="true" className="pointer-events-none absolute inset-0">{background}</div>}
      <Container className="relative">
        <Reveal className="mb-10 max-w-3xl">
          <p className="mb-3 flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.25em]" style={{ color: accent }}>
            <span className="font-mono text-base opacity-70">{index}</span>
            <span className="h-px w-10" style={{ background: accent, opacity: 0.6 }} aria-hidden="true" />
            {eyebrow}
          </p>
          <h2 id={`${id}-title`} className="text-3xl font-extrabold leading-tight tracking-tight sm:text-4xl lg:text-5xl">{title}</h2>
          <p className="mt-4 max-w-2xl text-base leading-relaxed text-muted sm:text-lg">{sub}</p>
        </Reveal>
        {children}
      </Container>
    </section>
  );
}
