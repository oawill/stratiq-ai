import Link from "next/link";
import { brand } from "@/lib/brand";
import { Logo } from "./Logo";
import { Container } from "./ui/primitives";
import { DOMAINS } from "@/lib/site";

export function Footer() {
  return (
    <footer className="mt-24 border-t border-line bg-bg2/40">
      <Container className="grid gap-10 py-14 md:grid-cols-4">
        <div className="md:col-span-1">
          <Logo />
          <p className="mt-4 text-sm leading-relaxed text-muted">
            Predict. Simulate. Strategize.
            <br />
            Strategic intelligence for a complex world.
          </p>
        </div>
        <div>
          <h2 className="mb-3 text-sm font-semibold">Intelligence</h2>
          <ul className="space-y-2 text-sm text-muted">
            {DOMAINS.map((d) => (
              <li key={d.slug}>
                <Link className="hover:text-ink" href={`/${d.slug}`}>
                  {d.name}
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="mb-3 text-sm font-semibold">Company</h2>
          <ul className="space-y-2 text-sm text-muted">
            <li><Link className="hover:text-ink" href="/how-it-works">How It Works</Link></li>
            <li><Link className="hover:text-ink" href="/pricing">Pricing</Link></li>
            <li><Link className="hover:text-ink" href="/about">About</Link></li>
            <li><Link className="hover:text-ink" href="/early-access">Early Access</Link></li>
            <li><Link className="hover:text-ink" href="/login">Log In</Link></li>
          </ul>
        </div>
        <div className="text-sm leading-relaxed text-muted">
          <h2 className="mb-3 text-sm font-semibold text-ink">Important</h2>
          {brand.name} provides probabilistic analysis, not certainty, and not financial, legal, or betting
          advice. All figures on this site are labeled demonstration or sample data unless stated otherwise.
        </div>
      </Container>
      <div className="border-t border-line py-5 text-center text-xs text-muted">
        © 2026 {brand.name}. All rights reserved. · {brand.domain} ·{" "}
        <Link className="hover:text-ink" href="/terms">Terms</Link> ·{" "}
        <Link className="hover:text-ink" href="/privacy">Privacy</Link>
      </div>
    </footer>
  );
}
