"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Menu, X } from "lucide-react";
import { Logo } from "../Logo";
import { ButtonLink } from "../ui/primitives";
import { NAV_TARGETS } from "./sections";
import { useActiveSection } from "./useActiveSection";

const LINKS = [
  { id: "home", label: "Home" },
  { id: "sports", label: "Sports" },
  { id: "strategy", label: "Strategy" },
  { id: "politics", label: "Politics" },
  { id: "markets", label: "Markets" },
  { id: "pricing", label: "Pricing" },
] as const;

/** Fixed, translucent navigation for the landing page. Anchors scroll smoothly (CSS) and the current section is highlighted. */
export function LandingNavigation() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const active = useActiveSection(NAV_TARGETS);
  const button = useRef<HTMLButtonElement>(null);

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

  const linkClass = (id: string) =>
    `rounded-lg px-3 py-2 text-sm transition-colors ${active === id ? "bg-white/10 text-ink" : "text-muted hover:text-ink"}`;

  return (
    <header className={`fixed inset-x-0 top-0 z-50 border-b transition-colors duration-300 ${scrolled || open ? "border-line bg-night/80 backdrop-blur-xl" : "border-transparent bg-night/20 backdrop-blur-sm"}`}>
      <a href="#main" className="skip-link">Skip to content</a>
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Logo />
        <nav aria-label="Primary" className="hidden items-center gap-1 lg:flex">
          {LINKS.map((l) => (
            <a key={l.id} href={`#${l.id}`} aria-current={active === l.id ? "location" : undefined} className={linkClass(l.id)}>{l.label}</a>
          ))}
        </nav>
        <div className="hidden items-center gap-2 lg:flex">
          <ButtonLink href="/login" variant="ghost" className="px-4 py-2">Log In</ButtonLink>
          <ButtonLink href="/early-access" className="px-4 py-2">Get Early Access</ButtonLink>
        </div>
        <button ref={button} type="button" className="rounded-lg p-2 text-ink lg:hidden" aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open} aria-controls="landing-menu" onClick={() => setOpen((v) => !v)}>
          {open ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>
      {open && (
        <div id="landing-menu" className="fixed inset-x-0 bottom-0 top-16 overflow-y-auto bg-night/95 px-4 pb-10 pt-4 lg:hidden">
          <nav aria-label="Mobile" className="flex flex-col gap-1">
            {LINKS.map((l) => (
              <a key={l.id} href={`#${l.id}`} onClick={() => setOpen(false)} aria-current={active === l.id ? "location" : undefined} className={`rounded-xl px-3 py-3 text-lg font-semibold ${active === l.id ? "bg-white/10" : ""}`}>{l.label}</a>
            ))}
            <Link href="/how-it-works" onClick={() => setOpen(false)} className="rounded-xl px-3 py-3 text-lg font-semibold text-muted">How It Works</Link>
          </nav>
          <div className="mt-6 grid gap-3">
            <ButtonLink href="/early-access" onClick={() => setOpen(false)}>Get Early Access</ButtonLink>
            <ButtonLink href="/login" variant="secondary" onClick={() => setOpen(false)}>Log In</ButtonLink>
          </div>
        </div>
      )}
    </header>
  );
}
