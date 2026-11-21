"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, Menu, X } from "lucide-react";
import { Logo } from "../Logo";
import { ButtonLink } from "../ui/primitives";
import { SLIDES } from "../carousel/slides";
import { useActiveSection } from "./useActiveSection";

const LINKS = [
  { id: "intelligence", label: "Platform" },
  { id: "how", label: "How It Works" },
  { id: "pricing", label: "Pricing" },
] as const;
const TARGETS = ["solutions", "intelligence", "how", "pricing"] as const;

/**
 * The one header of the home page: VELQORIN | Platform | Solutions | How It Works | Pricing | Get Started.
 * Every item except Get Started moves within the page (Solutions opens a menu of the four carousel slides), so nothing reloads.
 */
export function LandingNavigation() {
  const [open, setOpen] = useState(false);
  const [solutions, setSolutions] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const active = useActiveSection(TARGETS);
  const button = useRef<HTMLButtonElement>(null);
  const solutionsRoot = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open]);

  useEffect(() => {
    if (!solutions) return;
    const onDown = (e: MouseEvent) => {
      if (!solutionsRoot.current?.contains(e.target as Node)) setSolutions(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSolutions(false);
        solutionsRoot.current?.querySelector("button")?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [solutions]);

  const itemClass = (on: boolean) => `rounded-lg px-3 py-2 text-sm transition-colors ${on ? "bg-white/10 text-ink" : "text-muted hover:text-ink"}`;

  return (
    <header className={`fixed inset-x-0 top-0 z-50 border-b transition-colors duration-300 ${scrolled || open ? "border-line bg-night/80 backdrop-blur-xl" : "border-transparent bg-night/20 backdrop-blur-sm"}`}>
      <a href="#main" className="skip-link">Skip to content</a>
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Logo />
        <nav aria-label="Primary" className="hidden items-center gap-1 lg:flex">
          <a href="#intelligence" aria-current={active === "intelligence" ? "location" : undefined} className={itemClass(active === "intelligence")}>Platform</a>
          <div ref={solutionsRoot} className="relative">
            <button type="button" aria-expanded={solutions} aria-controls="solutions-menu" onClick={() => setSolutions((v) => !v)} className={`inline-flex items-center gap-1 ${itemClass(active === "solutions" || solutions)}`}>
              Solutions <ChevronDown className={`h-4 w-4 transition-transform ${solutions ? "rotate-180" : ""}`} aria-hidden="true" />
            </button>
            {solutions && (
              <ul id="solutions-menu" className="absolute left-0 top-full mt-2 w-64 rounded-2xl border border-line bg-night2/95 p-2 shadow-2xl backdrop-blur-xl">
                {SLIDES.map((s) => (
                  <li key={s.id}>
                    <a href={`#${s.id}`} onClick={() => setSolutions(false)} className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-ink hover:bg-white/10">
                      <span className="h-2 w-2 rounded-full" style={{ background: s.accent }} aria-hidden="true" />
                      {s.label}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {LINKS.slice(1).map((l) => (
            <a key={l.id} href={`#${l.id}`} aria-current={active === l.id ? "location" : undefined} className={itemClass(active === l.id)}>{l.label}</a>
          ))}
        </nav>
        <div className="hidden lg:block">
          <ButtonLink href="/signup" className="px-4 py-2">Get Started</ButtonLink>
        </div>
        <button ref={button} type="button" className="rounded-lg p-2 text-ink lg:hidden" aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open} aria-controls="landing-menu" onClick={() => setOpen((v) => !v)}>
          {open ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>
      {open && (
        <div id="landing-menu" className="fixed inset-x-0 bottom-0 top-16 overflow-y-auto bg-night/95 px-4 pb-10 pt-4 lg:hidden">
          <nav aria-label="Mobile" className="flex flex-col gap-1">
            <a href="#intelligence" onClick={() => setOpen(false)} className="rounded-xl px-3 py-3 text-lg font-semibold">Platform</a>
            <p className="px-3 pt-3 text-xs font-semibold uppercase tracking-[0.2em] text-muted">Solutions</p>
            {SLIDES.map((s) => (
              <a key={s.id} href={`#${s.id}`} onClick={() => setOpen(false)} className="flex items-center gap-3 rounded-xl px-3 py-3 text-lg font-semibold">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: s.accent }} aria-hidden="true" />
                {s.label}
              </a>
            ))}
            {LINKS.slice(1).map((l) => (
              <a key={l.id} href={`#${l.id}`} onClick={() => setOpen(false)} className="rounded-xl px-3 py-3 text-lg font-semibold">{l.label}</a>
            ))}
          </nav>
          <div className="mt-6 grid gap-3">
            <ButtonLink href="/signup" onClick={() => setOpen(false)}>Get Started</ButtonLink>
            <Link href="/login" onClick={() => setOpen(false)} className="py-2 text-center text-sm text-muted hover:text-ink">Already have an account? Log in</Link>
          </div>
        </div>
      )}
    </header>
  );
}
