import type { ReactNode } from "react";
import { Container } from "../ui/primitives";

/** Shared shell for legal pages. Every legal page carries a visible draft notice until counsel has reviewed it. */
export function LegalPage({ title, updated, children }: { title: string; updated: string; children: ReactNode }) {
  return (
    <Container className="max-w-3xl py-16">
      <p role="note" className="mb-8 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
        Draft for legal review. This document has not yet been reviewed by a lawyer, and bracketed items such as [date] are placeholders to complete before launch.
      </p>
      <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl">{title}</h1>
      <p className="mt-3 text-sm text-muted">Last updated: {updated}</p>
      <div className="mt-8 space-y-4 text-base leading-relaxed text-muted [&_h2]:pt-4 [&_h2]:text-xl [&_h2]:font-bold [&_h2]:text-ink [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-6">
        {children}
      </div>
    </Container>
  );
}
