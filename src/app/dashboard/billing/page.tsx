import type { Metadata } from "next";
import { requireSession } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { billingConfigured } from "@/lib/stripe";
import { BillingActions } from "@/components/dashboard/billing/BillingActions";
import { Badge, ErrorPanel, PageTitle, Panel } from "@/components/dashboard/ui";

export const metadata: Metadata = { title: "Plan & Billing" };

interface PlanInfo {
  plan: string;
  name: string;
  enforced: boolean;
  limits: { predictions: number | null; scenarios: number | null; runs: number | null; iterations: number; exports: boolean; seats: number };
  usage: { predictions: number; scenarios: number; runs: number };
  subscription: { status: string; billing_interval: string; current_period_end: string | null; cancel_at_period_end: boolean } | null;
}

const cap = (n: number | null) => (n === null ? "Unlimited" : String(n));

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const s = await requireSession();
  const q = await searchParams;
  let info: PlanInfo;
  try {
    info = await apiFetch<PlanInfo>(s, "billing/plan");
  } catch (e) {
    return (<><PageTitle title="Plan & Billing" /><ErrorPanel message={e instanceof Error ? e.message : "Billing information is unavailable."} /></>);
  }
  const canManage = s.role === "owner" || s.role === "admin";
  const sub = info.subscription;
  const rows: [string, string, string][] = [
    ["Saved forecasts", String(info.usage.predictions), cap(info.limits.predictions)],
    ["Saved scenarios", String(info.usage.scenarios), cap(info.limits.scenarios)],
    ["Saved simulation runs", String(info.usage.runs), cap(info.limits.runs)],
    ["Max iterations per simulation", "", info.limits.iterations.toLocaleString("en-US")],
    ["Team seats (members and pending invitations)", "", String(info.limits.seats)],
    ["Report and workspace exports", "", info.limits.exports ? "Included" : "Not included"],
  ];
  return (
    <>
      <PageTitle title="Plan & Billing" sub={`Plan for the workspace "${s.workspaceName}". Plans apply to the whole workspace.`} />
      {q.checkout === "success" && (
        <p role="status" className="mb-4 rounded-lg border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">
          Thanks. Your payment went through; the plan below updates as soon as Stripe confirms it (usually seconds). Refresh if it still shows the old plan.
        </p>
      )}
      {q.checkout === "cancelled" && <p className="mb-4 rounded-lg border border-line px-4 py-3 text-sm text-muted">Checkout was cancelled. You have not been charged.</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Current plan" badge={<Badge tone="violet">{info.name}</Badge>}>
          {!info.enforced && (
            <p className="mb-3 text-sm text-muted">Early access: every feature is included while billing is not yet enforced. The limits below start to apply when paid plans launch.</p>
          )}
          {sub && (
            <p className="mb-3 text-sm text-muted">
              Status: <span className="text-ink">{sub.status}</span>
              {sub.current_period_end && <> · {sub.cancel_at_period_end ? "ends" : "renews"} {new Date(sub.current_period_end).toLocaleDateString("en-US", { dateStyle: "medium" })}</>}
              {" · billed "}{sub.billing_interval === "year" ? "yearly" : "monthly"}
            </p>
          )}
          <table className="w-full text-sm">
            <tbody className="divide-y divide-line">
              {rows.map(([label, used, limit]) => (
                <tr key={label}>
                  <td className="py-2 text-muted">{label}</td>
                  <td className="py-2 text-right">{used ? `${used} of ${limit}` : limit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title={sub ? "Manage subscription" : "Upgrade"}>
          {billingConfigured() ? (
            <BillingActions current={info.plan} canManage={canManage} hasSubscription={!!sub} />
          ) : (
            <p className="text-sm text-muted">Paid plans are not available yet. Nothing here will charge you.</p>
          )}
          <p className="mt-4 text-xs text-muted">Payments are handled by Stripe; we never see or store your card details.</p>
        </Panel>
      </div>
    </>
  );
}
