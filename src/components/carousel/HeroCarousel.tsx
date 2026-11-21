"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import { ButtonLink } from "../ui/primitives";
import { usePrefersReducedMotion } from "../landing/usePrefersReducedMotion";
import { CarouselVisual } from "./CarouselVisuals";
import { INITIAL_WHEEL, LOCK_MS, TRANSITION_MS, clampIndex, swipeIntent, wheelIntent } from "./input";
import { SLIDES, slideIndexFromHash } from "./slides";

const ease = [0.22, 1, 0.36, 1] as const;

/** Fades and lifts its content in when the slide becomes active, staggered by `order`. */
function Rise({ active, reduce, order, className, children }: { active: boolean; reduce: boolean; order: number; className?: string; children: ReactNode }) {
  return (
    <motion.div className={className} initial={false} animate={{ opacity: active ? 1 : 0, y: active || reduce ? 0 : 18 }} transition={{ duration: reduce ? 0 : 0.6, delay: active && !reduce ? 0.25 + order * 0.08 : 0, ease }}>
      {children}
    </motion.div>
  );
}

const isEditable = (t: EventTarget | null) => t instanceof HTMLElement && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName));

/**
 * The home page's full-screen carousel: four intelligence capabilities as slides of one page.
 * Wheel/trackpad, swipe, arrow buttons, arrow keys, pagination dots and `#sports` style links all move between slides without a page load.
 * The carousel only owns the wheel while the page is at the top and a slide is left to show; after the last slide the page scrolls normally.
 */
export function HeroCarousel() {
  const [index, setIndex] = useState(0);
  const reduce = usePrefersReducedMotion();
  const root = useRef<HTMLElement>(null);
  const indexRef = useRef(0);
  const wheel = useRef(INITIAL_WHEEL);
  const touch = useRef<{ x: number; y: number } | null>(null);
  const count = SLIDES.length;

  const go = useCallback(
    (to: number, scrollToTop = false) => {
      const n = clampIndex(to, count);
      if (scrollToTop) window.scrollTo({ top: 0, behavior: "auto" });
      if (n === indexRef.current) return;
      indexRef.current = n;
      wheel.current = { ...wheel.current, lockedUntil: performance.now() + LOCK_MS };
      setIndex(n);
      try {
        window.history.replaceState(window.history.state, "", `#${SLIDES[n].id}`);
      } catch {
        /* the address bar is a convenience; the carousel works without it */
      }
    },
    [count],
  );

  // Wheel and trackpad. Registered natively because React's onWheel is passive and cannot cancel page scrolling.
  useEffect(() => {
    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.defaultPrevented) return; // pinch-zoom or already handled
      const r = wheelIntent(wheel.current, { deltaX: e.deltaX, deltaY: e.deltaY, time: e.timeStamp, scrollY: window.scrollY, index: indexRef.current, count });
      wheel.current = r.state;
      if (r.prevent) e.preventDefault();
      if (r.action === "next") go(indexRef.current + 1);
      else if (r.action === "prev") go(indexRef.current - 1);
    };
    window.addEventListener("wheel", onWheel, { passive: false });
    return () => window.removeEventListener("wheel", onWheel);
  }, [count, go]);

  // Arrow keys, while the carousel is what the visitor is looking at.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.repeat || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey || isEditable(e.target)) return;
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const h = root.current?.offsetHeight ?? 0;
      if (window.scrollY > h * 0.5) return;
      e.preventDefault();
      go(indexRef.current + (e.key === "ArrowRight" ? 1 : -1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

  // Links such as /#business choose a slide, both on arrival and later (header menu, browser back).
  useEffect(() => {
    const fromHash = () => {
      const i = slideIndexFromHash(window.location.hash);
      if (i >= 0) go(i, true);
    };
    const t = setTimeout(fromHash, 0);
    window.addEventListener("hashchange", fromHash);
    return () => {
      clearTimeout(t);
      window.removeEventListener("hashchange", fromHash);
    };
  }, [go]);

  const active = SLIDES[index];
  return (
    <section
      ref={root}
      id="solutions"
      aria-roledescription="carousel"
      aria-label="VELQORIN intelligence capabilities"
      className="relative h-svh min-h-[580px] touch-pan-y overflow-hidden"
      onTouchStart={(e) => {
        touch.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      }}
      onTouchEnd={(e) => {
        const s = touch.current;
        touch.current = null;
        if (!s) return;
        const t = e.changedTouches[0];
        const intent = swipeIntent(t.clientX - s.x, t.clientY - s.y);
        if (intent) go(indexRef.current + (intent === "next" ? 1 : -1));
      }}
    >
      <h1 className="sr-only">VELQORIN: strategic intelligence for sports, business, politics and finance</h1>
      {SLIDES.map((s, i) => {
        const on = i === index;
        return (
          <motion.div
            key={s.id}
            id={s.id}
            role="group"
            aria-roledescription="slide"
            aria-label={`${i + 1} of ${count}: ${s.label}`}
            aria-hidden={!on}
            inert={!on}
            className="absolute inset-0"
            initial={false}
            animate={{ opacity: on ? 1 : 0, x: reduce || on ? 0 : i < index ? -48 : 48 }}
            transition={{ duration: reduce ? 0 : TRANSITION_MS / 1000, ease }}
          >
            <div aria-hidden="true" className="absolute inset-0" style={{ background: s.background }} />
            <div aria-hidden="true" className="absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-night to-transparent" />
            <div className="relative mx-auto grid h-full max-w-7xl items-center gap-4 px-4 pb-28 pt-20 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:gap-10 lg:px-8 lg:pb-24">
              <div>
                <Rise active={on} reduce={reduce} order={0}>
                  <p className="mb-3 flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.25em]" style={{ color: s.accent }}>
                    <span className="font-mono text-base opacity-70">0{i + 1}</span>
                    <span className="h-px w-10" style={{ background: s.accent, opacity: 0.6 }} aria-hidden="true" />
                    {s.eyebrow}
                  </p>
                </Rise>
                <Rise active={on} reduce={reduce} order={1}>
                  <h2 className="text-3xl font-extrabold leading-[1.08] tracking-tight sm:text-5xl lg:text-6xl">{s.headline}</h2>
                </Rise>
                <Rise active={on} reduce={reduce} order={2}>
                  <p className="mt-4 max-w-xl text-base leading-relaxed text-muted sm:text-lg">{s.text}</p>
                </Rise>
                <Rise active={on} reduce={reduce} order={3} className="hidden sm:block">
                  <ul className="mt-5 flex flex-wrap gap-2">
                    {s.points.map((p) => (
                      <li key={p} className="rounded-full border border-line bg-white/5 px-3 py-1 text-xs text-ink">{p}</li>
                    ))}
                  </ul>
                </Rise>
                <Rise active={on} reduce={reduce} order={4}>
                  <div className="mt-6 flex flex-col gap-3 sm:flex-row">
                    <ButtonLink href={s.demoHref} className="py-3.5">{s.demoLabel} <ArrowRight className="h-4 w-4" aria-hidden="true" /></ButtonLink>
                    <ButtonLink href="/signup" variant="secondary" className="py-3.5">Get Started</ButtonLink>
                  </div>
                </Rise>
              </div>
              <Rise active={on} reduce={reduce} order={2} className="mx-auto w-full max-w-md lg:max-w-xl">
                <CarouselVisual kind={s.visual} accent={s.accent} active={on} reduce={reduce} />
              </Rise>
            </div>
          </motion.div>
        );
      })}

      <div className="absolute inset-x-0 bottom-0 z-10">
        <div role="progressbar" aria-label="Slide progress" aria-valuemin={1} aria-valuemax={count} aria-valuenow={index + 1} aria-valuetext={`Slide ${index + 1} of ${count}`} className="h-0.5 w-full bg-white/10">
          <motion.div className="h-full origin-left" style={{ background: active.accent }} initial={false} animate={{ scaleX: (index + 1) / count }} transition={{ duration: reduce ? 0 : TRANSITION_MS / 1000, ease }} />
        </div>
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <span className="flex items-center gap-4 text-xs text-muted">
            <span className="font-mono" aria-hidden="true">0{index + 1} / 0{count}</span>
            <span className="hidden md:inline">Intelligence Beyond Prediction</span>
          </span>
          <div className="flex items-center gap-3">
            <button type="button" aria-label="Previous slide" disabled={index === 0} onClick={() => go(index - 1)} className="flex h-11 w-11 items-center justify-center rounded-full border border-line bg-white/5 text-ink transition-colors hover:bg-white/10 disabled:opacity-35 disabled:hover:bg-white/5">
              <ChevronLeft className="h-5 w-5" aria-hidden="true" />
            </button>
            <div className="flex items-center" role="group" aria-label="Choose a slide">
              {SLIDES.map((s, i) => (
                <button key={s.id} type="button" aria-label={`Go to slide ${i + 1}: ${s.label}`} aria-current={i === index ? "true" : undefined} onClick={() => go(i)} className="group flex h-11 w-9 items-center justify-center">
                  <span className="block h-2 rounded-full transition-all duration-300 group-hover:bg-white/60" style={i === index ? { width: 28, background: s.accent, boxShadow: `0 0 12px ${s.accent}` } : { width: 8, background: "rgba(255,255,255,0.3)" }} />
                </button>
              ))}
            </div>
            <button type="button" aria-label="Next slide" disabled={index === count - 1} onClick={() => go(index + 1)} className="flex h-11 w-11 items-center justify-center rounded-full border border-line bg-white/5 text-ink transition-colors hover:bg-white/10 disabled:opacity-35 disabled:hover:bg-white/5">
              <ChevronRight className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
          <span className="hidden w-14 text-right text-xs text-muted sm:block" aria-hidden="true">{index === count - 1 ? "Scroll ↓" : ""}</span>
        </div>
      </div>
      <p className="sr-only" aria-live="polite">{`Slide ${index + 1} of ${count}: ${active.label}`}</p>
    </section>
  );
}
