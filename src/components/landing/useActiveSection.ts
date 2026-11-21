"use client";

import { useEffect, useState } from "react";

/**
 * Which of the given section ids is crossing the middle of the viewport, or null when none is. Keeps the set of sections currently
 * crossing it (entries only report changes), uses one IntersectionObserver and disconnects it on unmount.
 */
export function useActiveSection(ids: readonly string[]): string | null {
  const [active, setActive] = useState<string | null>(null);
  const key = ids.join(",");
  useEffect(() => {
    const order = key.split(",");
    const els = order.map((id) => document.getElementById(id)).filter((e): e is HTMLElement => !!e);
    if (!els.length || typeof IntersectionObserver === "undefined") return;
    const visible = new Set<string>();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) visible.add(e.target.id);
          else visible.delete(e.target.id);
        }
        setActive(order.find((id) => visible.has(id)) ?? null);
      },
      { rootMargin: "-45% 0px -50% 0px", threshold: 0 },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [key]);
  return active;
}
