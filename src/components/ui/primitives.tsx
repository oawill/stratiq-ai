import Link from "next/link";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { ComponentProps, ReactNode } from "react";

export const cn = (...a: Parameters<typeof clsx>) => twMerge(clsx(a));

const base =
  "inline-flex items-center justify-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold transition-all duration-200 whitespace-nowrap";
const variants = {
  primary:
    "bg-primary text-white shadow-[0_8px_30px_-8px_rgba(128,85,246,0.8)] hover:brightness-110 hover:-translate-y-0.5",
  secondary: "border border-line bg-white/5 text-ink hover:bg-white/10 hover:border-violet/50",
  ghost: "text-muted hover:text-ink",
} as const;

export function ButtonLink({
  variant = "primary",
  className,
  ...props
}: ComponentProps<typeof Link> & { variant?: keyof typeof variants }) {
  return <Link className={cn(base, variants[variant], className)} {...props} />;
}

export function Button({
  variant = "primary",
  className,
  ...props
}: ComponentProps<"button"> & { variant?: keyof typeof variants }) {
  return (
    <button
      className={cn(base, variants[variant], "disabled:opacity-60 disabled:pointer-events-none", className)}
      {...props}
    />
  );
}

export function Container({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8", className)} {...props} />;
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <p className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-cyan">{children}</p>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  sub,
  center = true,
}: {
  eyebrow?: string;
  title: ReactNode;
  sub?: string;
  center?: boolean;
}) {
  return (
    <div className={cn("mb-12 max-w-3xl", center && "mx-auto text-center")}>
      {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
      <h2 className="text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">{title}</h2>
      {sub && <p className="mt-4 text-base leading-relaxed text-muted sm:text-lg">{sub}</p>}
    </div>
  );
}

export function PreviewBadge({ children = "Preview" }: { children?: ReactNode }) {
  return (
    <span className="rounded-full border border-cyan/40 bg-cyan/10 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-cyan">
      {children}
    </span>
  );
}
