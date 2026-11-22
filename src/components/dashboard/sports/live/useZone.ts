"use client";

import { useCallback, useEffect, useState } from "react";
import { validZone } from "./live";

const KEY = "velqorin.live.timezone";

/** The time zone used to display kickoff times: the person's last choice, else the browser's, else UTC. Applied after mount so server and first client render agree. */
export function useZone(): [string, (z: string) => void] {
  const [tz, setTz] = useState("UTC");
  useEffect(() => {
    let saved: string | null = null;
    try { saved = window.localStorage.getItem(KEY); } catch { /* storage unavailable */ }
    const browser = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const pick = validZone(saved) ? saved : validZone(browser) ? browser : "UTC";
    const t = setTimeout(() => setTz(pick), 0);
    return () => clearTimeout(t);
  }, []);
  const change = useCallback((z: string) => { setTz(z); try { window.localStorage.setItem(KEY, z); } catch { /* ignore */ } }, []);
  return [tz, change];
}
