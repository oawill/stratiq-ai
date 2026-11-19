"use client";

import { useSyncExternalStore } from "react";

const listeners = new Set<() => void>();
function read() {
  try {
    return localStorage.getItem("stratiq_adv") === "1";
  } catch {
    return false;
  }
}

/** Progressive-disclosure preference shared by every module (persisted per browser). */
export function useAdvanced() {
  const adv = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => {
        listeners.delete(cb);
      };
    },
    read,
    () => false,
  );
  const set = (v: boolean) => {
    try {
      localStorage.setItem("stratiq_adv", v ? "1" : "0");
    } catch {}
    listeners.forEach((l) => l());
  };
  return [adv, set] as const;
}
