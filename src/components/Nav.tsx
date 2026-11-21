"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, Menu, X } from "lucide-react";
import { Logo } from "./Logo";
import { ButtonLink } from "./ui/primitives";
import { DOMAINS, NAV } from "@/lib/site";

export function Nav() {
  const [open, setOpen] = useState(false);
  const [dd, setDd] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const ddRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setDd(false);
        setOpen(false);
      }
    };
    const onClick = (e: MouseEvent) => {
      if (ddRef.current && !ddRef.current.contains(e.target as Node)) setDd(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, []);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <header
      className={`sticky top-0 z-50 border-b transition-colors ${
        scrolled || open ? "border-line bg-bg/85 backdrop-blur-xl" : "border-transparent bg-transparent"
      }`}
    >
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Logo />
        <nav aria-label="Primary" className="hidden items-center gap-1 lg:flex">
          {NAV.map((item) =>
            "dropdown" in item ? (
              <div key={item.label} className="relative" ref={ddRef}>
                <button
                  type="button"
                  aria-expanded={dd}
                  aria-haspopup="true"
                  aria-controls="intel-menu"
                  onClick={() => setDd((v) => !v)}
                  className="flex items-center gap-1 rounded-lg px-3 py-2 text-sm text-muted transition-colors hover:text-ink"
                >
                  {item.label}
                  <ChevronDown className={`h-4 w-4 transition-transform ${dd ? "rotate-180" : ""}`} />
                </button>
                {dd && (
                  <div
                    id="intel-menu"
                    className="glass absolute left-1/2 top-full mt-2 w-72 -translate-x-1/2 rounded-2xl p-2 shadow-2xl"
                  >
                    {DOMAINS.map((d) => (
                      <a
                        key={d.slug}
                        href={`/#${d.slug}`}
                        onClick={() => setDd(false)}
                        className="flex items-start gap-3 rounded-xl p-3 transition-colors hover:bg-white/5"
                      >
                        <d.icon className="mt-0.5 h-5 w-5" style={{ color: d.accent }} aria-hidden="true" />
                        <span>
                          <span className="block text-sm font-semibold">{d.name}</span>
                          <span className="block text-xs text-muted">{d.headline}</span>
                        </span>
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <Link
                key={item.label}
                href={item.href}
                className="rounded-lg px-3 py-2 text-sm text-muted transition-colors hover:text-ink"
              >
                {item.label}
              </Link>
            ),
          )}
        </nav>
        <div className="hidden items-center gap-2 lg:flex">
          <ButtonLink href="/login" variant="ghost" className="px-4 py-2">
            Log In
          </ButtonLink>
          <ButtonLink href="/early-access" className="px-4 py-2">
            Get Early Access
          </ButtonLink>
        </div>
        <button
          type="button"
          className="rounded-lg p-2 text-ink lg:hidden"
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          aria-controls="mobile-menu"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>
      {open && (
        <div
          id="mobile-menu"
          className="fixed inset-x-0 top-16 bottom-0 overflow-y-auto bg-bg/98 px-4 pb-10 pt-4 lg:hidden"
        >
          <nav aria-label="Mobile" className="flex flex-col gap-1">
            {NAV.map((item) => (
              <div key={item.label}>
                <Link
                  href={item.href}
                  onClick={() => setOpen(false)}
                  className="block rounded-xl px-3 py-3 text-lg font-semibold"
                >
                  {item.label}
                </Link>
                {"dropdown" in item && (
                  <div className="mb-2 ml-3 grid gap-1 border-l border-line pl-3">
                    {DOMAINS.map((d) => (
                      <a
                        key={d.slug}
                        href={`/#${d.slug}`}
                        onClick={() => setOpen(false)}
                        className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted"
                      >
                        <d.icon className="h-4 w-4" style={{ color: d.accent }} aria-hidden="true" />
                        {d.name}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </nav>
          <div className="mt-6 grid gap-3">
            <ButtonLink href="/early-access" onClick={() => setOpen(false)}>
              Get Early Access
            </ButtonLink>
            <ButtonLink href="/login" variant="secondary" onClick={() => setOpen(false)}>
              Log In
            </ButtonLink>
          </div>
        </div>
      )}
    </header>
  );
}
