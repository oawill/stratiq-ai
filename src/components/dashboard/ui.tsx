import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

export function PageTitle({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight sm:text-3xl">{title}</h1>
        {sub && <p className="mt-1 max-w-2xl text-sm text-muted">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

export function Panel({ title, children, className = "", badge }: { title?: string; children: ReactNode; className?: string; badge?: ReactNode }) {
  return (
    <section className={`glass min-w-0 rounded-2xl p-4 sm:p-5 ${className}`}>
      {title && (
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">{title}</h2>
          {badge}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="glass rounded-2xl p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 font-mono text-2xl font-bold">{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-muted">{hint}</div>}
    </div>
  );
}

export function Badge({ children, tone = "cyan" }: { children: ReactNode; tone?: "cyan" | "green" | "violet" | "muted" | "amber" }) {
  const c = {
    cyan: "border-cyan/40 bg-cyan/10 text-cyan",
    green: "border-success/40 bg-success/10 text-success",
    violet: "border-violet/40 bg-violet/10 text-violet",
    muted: "border-line bg-white/5 text-muted",
    amber: "border-amber-400/40 bg-amber-400/10 text-amber-300",
  }[tone];
  return <span className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${c}`}>{children}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-muted">{children}</p>;
}

export function ErrorPanel({ message }: { message: string }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-2xl border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-200">
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
      <div>
        <div className="font-semibold">Something went wrong</div>
        <div className="mt-0.5 opacity-90">{message}</div>
      </div>
    </div>
  );
}

export const pct = (x: number, d = 1) => `${(x * 100).toFixed(d)}%`;
export const dt = (s: string) =>
  new Date(s).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) + " UTC";
