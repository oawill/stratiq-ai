import Link from "next/link";
import { Logo } from "@/components/Logo";
import { brand } from "@/lib/brand";

export default function NotFound() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center px-4 py-24 text-center">
      <Logo />
      <p className="mt-10 font-mono text-sm text-cyan">404</p>
      <h1 className="mt-2 text-3xl font-extrabold tracking-tight sm:text-4xl">This page could not be found</h1>
      <p className="mt-3 max-w-md text-muted">The page you were looking for does not exist on {brand.name}, or it has moved.</p>
      <div className="mt-8 flex gap-3">
        <Link href="/" className="rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-white hover:bg-[#9168ff]">Back to {brand.shortName}</Link>
        <Link href="/dashboard" className="rounded-xl border border-line bg-white/5 px-5 py-3 text-sm font-semibold hover:bg-white/10">Open dashboard</Link>
      </div>
    </main>
  );
}
