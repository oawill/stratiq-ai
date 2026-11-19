"use client";

import { Logo } from "@/components/Logo";
import { brand } from "@/lib/brand";

export default function GlobalRouteError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="flex flex-1 flex-col items-center justify-center px-4 py-24 text-center">
      <Logo />
      <h1 className="mt-10 text-3xl font-extrabold tracking-tight sm:text-4xl">Something went wrong</h1>
      <p className="mt-3 max-w-md text-muted">{brand.name} hit an unexpected error. Your saved work is not affected. You can try again.</p>
      <button type="button" onClick={reset} className="mt-8 rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-white hover:bg-[#9168ff]">Try again</button>
    </main>
  );
}
