"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { call } from "@/lib/client";
import { Badge, Panel } from "../../ui";
import { field } from "../../analysis";
import { FixtureList } from "./FixtureList";
import { HistoryTab } from "./HistoryTab";
import { MatchIntel } from "./MatchIntel";
import { useZone } from "./useZone";
import { TABS, ZONES, stamp, type TabId } from "./live";

interface Provider { configured: boolean; provider: string; rate_limit_per_minute: number; health: { last_success_at: string | null; last_failure_at: string | null; consecutive_failures: number; last_error: string | null }; note: string; capabilities: Record<string, boolean | string> }

/** The Live Predictions workspace: tabs, a time-zone choice shared by every tab, and an honest provider status line. */
export function LivePredictions({ tab, fixture }: { tab: TabId; fixture?: string }) {
  const [tz, changeZone] = useZone();
  const [provider, setProvider] = useState<Provider | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const loadProvider = useCallback(() => call<Provider>("football/live/provider").then(setProvider, () => setProvider(null)), []);
  useEffect(() => { const t = setTimeout(loadProvider, 0); return () => clearTimeout(t); }, [loadProvider]);

  async function sync() {
    setBusy(true); setMsg(null);
    try {
      const r = await call<{ status: string; message?: string; created?: number; updated?: number; unchanged?: number }>("football/live/sync", { method: "POST" });
      setMsg(r.status === "complete" ? `Synchronised: ${r.created} new, ${r.updated} updated, ${r.unchanged} unchanged.${r.created === 0 && r.updated === 0 && r.unchanged === 0 ? " The provider returned no fixtures for this period." : ""}` : r.message ?? r.status);
      await loadProvider(); setVersion((n) => n + 1);
    } catch (e) { setMsg(e instanceof Error ? e.message : "Could not synchronise."); } finally { setBusy(false); }
  }

  const zones = ZONES.includes(tz) ? ZONES : [tz, ...ZONES];
  return (
    <div className="space-y-4">
      <Panel>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="text-sm">
            {provider ? (
              <>
                <p className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">Fixtures: {provider.provider}</span>
                  <Badge tone={!provider.configured ? "amber" : provider.health.last_success_at ? (provider.health.consecutive_failures ? "amber" : "green") : "muted"}>
                    {!provider.configured ? "Not connected" : provider.health.last_success_at ? (provider.health.consecutive_failures ? "Problems" : "Connected") : "Not yet synchronised"}
                  </Badge>
                </p>
                <p className="mt-0.5 text-xs text-muted">
                  {!provider.configured ? "No provider key is configured on the server, so only fixtures you imported are shown." : `Last successful fetch ${stamp(provider.health.last_success_at, tz)}.`} {provider.note}
                </p>
              </>
            ) : <p className="text-xs text-muted" aria-busy="true">Checking the fixture provider…</p>}
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div><label htmlFor="live-tz" className="mb-1 block text-xs text-muted">Time zone</label>
              <select id="live-tz" value={tz} onChange={(e) => changeZone(e.target.value)} className={field}>{zones.map((z) => <option key={z} value={z}>{z.replace(/_/g, " ")}</option>)}</select></div>
            <button type="button" onClick={sync} disabled={busy || provider?.configured === false} className="inline-flex items-center gap-2 rounded-xl border border-line px-3 py-2 text-sm font-semibold hover:bg-white/5 disabled:opacity-50">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />} Refresh fixtures
            </button>
          </div>
        </div>
        {msg && <p role="status" className="mt-2 text-xs text-muted">{msg}</p>}
      </Panel>

      <nav aria-label="Live predictions sections" className="flex max-w-full flex-wrap gap-2">
        {TABS.map((t) => (
          <Link key={t.id} href={t.id === "today" ? "/dashboard/sports/live" : `/dashboard/sports/live?tab=${t.id}`} aria-current={t.id === tab ? "page" : undefined}
            className={`rounded-xl border px-4 py-2 text-sm font-semibold ${t.id === tab ? "border-violet bg-violet/15 text-ink" : "border-line text-muted hover:bg-white/5 hover:text-ink"}`}>{t.label}</Link>
        ))}
        <Link href="/dashboard/sports?tab=football" className="rounded-xl border border-line px-4 py-2 text-sm font-semibold text-muted hover:bg-white/5 hover:text-ink">Model performance</Link>
      </nav>

      <div key={`${tab}-${version}-${tz}`}>
        {tab === "today" && <FixtureList mode="today" tz={tz} />}
        {tab === "upcoming" && <FixtureList mode="upcoming" tz={tz} />}
        {tab === "completed" && <FixtureList mode="completed" tz={tz} />}
        {tab === "intel" && <MatchIntel tz={tz} fixtureId={fixture} />}
        {tab === "history" && <HistoryTab tz={tz} fixtureId={fixture} />}
      </div>
      <p className="text-xs text-muted">Forecasts are model estimates made before kickoff, shown with the time they were made. They are not certainties and not betting or financial advice.</p>
    </div>
  );
}
