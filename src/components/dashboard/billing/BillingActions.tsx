"use client";

import { useState } from "react";
import { Button } from "@/components/ui/primitives";
import { annualMonthly } from "@/lib/pricing";
import { PAID_PLANS, type Interval, type PaidPlan } from "@/lib/plans";

async function go(path: string, body?: unknown): Promise<string> {
  const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });
  const j = await res.json().catch(() => ({}));
  if (!res.ok || !j.url) throw new Error(j.error ?? "Something went wrong.");
  return j.url as string;
}

/** Upgrade buttons (no subscription) or Manage billing (has one). Only owners and admins see the buttons. */
export function BillingActions({ current, canManage, hasSubscription }: { current: string; canManage: boolean; hasSubscription: boolean }) {
  const [interval, setInterval] = useState<Interval>("month");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  if (!canManage) return <p className="text-sm text-muted">Only workspace owners and admins can change the plan.</p>;

  async function run(label: string, fn: () => Promise<string>) {
    setBusy(label);
    setErr(null);
    try {
      window.location.assign(await fn());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong.");
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      {hasSubscription && (
        <Button type="button" variant="secondary" disabled={busy !== null} onClick={() => run("portal", () => go("/api/billing/portal"))}>
          {busy === "portal" ? "Opening…" : "Manage billing"}
        </Button>
      )}
      {!hasSubscription && (
        <>
          <div className="flex items-center gap-2 text-sm" role="group" aria-label="Billing interval">
            {(["month", "year"] as const).map((i) => (
              <button
                key={i}
                type="button"
                aria-pressed={interval === i}
                onClick={() => setInterval(i)}
                className={`rounded-lg border px-3 py-1.5 ${interval === i ? "border-violet bg-violet/15 font-semibold" : "border-line text-muted hover:text-ink"}`}
              >
                {i === "month" ? "Monthly" : "Annual (save 20%)"}
              </button>
            ))}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {(Object.keys(PAID_PLANS) as PaidPlan[]).map((p) => (
              <div key={p} className="rounded-xl border border-line bg-white/5 p-4">
                <p className="font-semibold">{PAID_PLANS[p].name}</p>
                <p className="mt-1 text-2xl font-extrabold">
                  ${interval === "month" ? PAID_PLANS[p].monthly : annualMonthly(PAID_PLANS[p].monthly)}
                  <span className="text-sm font-normal text-muted"> / month{interval === "year" ? ", billed yearly" : ""}</span>
                </p>
                <Button type="button" className="mt-3 w-full" disabled={busy !== null || current === p} onClick={() => run(p, () => go("/api/billing/checkout", { plan: p, interval }))}>
                  {busy === p ? "Redirecting…" : `Choose ${PAID_PLANS[p].name}`}
                </Button>
              </div>
            ))}
          </div>
        </>
      )}
      {err && <p role="alert" className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">{err}</p>}
    </div>
  );
}
