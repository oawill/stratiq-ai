"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Renders its children only once it is near the viewport, inside a box of fixed height so nothing shifts when they appear.
 * Used for heavy visualizations so they cost nothing until the visitor scrolls toward them.
 */
export function LazyMount({ children, className = "", margin = "400px" }: { children: ReactNode; className?: string; margin?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || ready) return;
    if (typeof IntersectionObserver === "undefined") {
      const t = setTimeout(() => setReady(true), 0);   // very old browsers: just show the content
      return () => clearTimeout(t);
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setReady(true);
          io.disconnect();
        }
      },
      { rootMargin: margin },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [ready, margin]);
  return (
    <div ref={ref} className={className}>
      {ready ? children : <div aria-hidden="true" className="h-full w-full animate-pulse rounded-2xl bg-white/[0.03]" />}
    </div>
  );
}
