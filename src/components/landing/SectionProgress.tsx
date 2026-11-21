"use client";

import { motion, useScroll, useSpring } from "framer-motion";
import { CINE_SECTIONS } from "./sections";
import { useActiveSection } from "./useActiveSection";

/** A thin reading-progress bar across the top and, on large screens, a dot rail on the right edge that shows where you are. */
export function SectionProgress() {
  const active = useActiveSection(CINE_SECTIONS.map((s) => s.id));
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 140, damping: 30, mass: 0.4 });
  return (
    <>
      <motion.div aria-hidden="true" style={{ scaleX }} className="fixed inset-x-0 top-0 z-[60] h-0.5 origin-left bg-gradient-to-r from-ion via-azure to-royal" />
      <nav aria-label="Sections" className="fixed right-4 top-1/2 z-40 hidden -translate-y-1/2 flex-col gap-3 xl:flex">
        {CINE_SECTIONS.map((s) => {
          const on = active === s.id;
          return (
            <a key={s.id} href={`#${s.id}`} aria-label={`Go to ${s.label}`} aria-current={on ? "location" : undefined} className="group relative flex h-4 w-4 items-center justify-center">
              <span className={`block rounded-full transition-all ${on ? "h-3 w-3" : "h-2 w-2 bg-white/25 group-hover:bg-white/60"}`} style={on ? { background: s.accent, boxShadow: `0 0 12px ${s.accent}` } : undefined} />
              <span className="pointer-events-none absolute right-6 whitespace-nowrap rounded-md bg-night2/95 px-2 py-1 text-xs text-ink opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">{s.label}</span>
            </a>
          );
        })}
      </nav>
    </>
  );
}
