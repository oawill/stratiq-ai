import type { PoolClient } from "pg";
import type Stripe from "stripe";
import { isInterval, isPaidPlan, type Interval, type PaidPlan } from "./plans";

export interface SubscriptionRow {
  workspaceId: string;
  plan: PaidPlan;
  status: string;
  interval: Interval;
  customerId: string;
  subscriptionId: string;
  currentPeriodEnd: Date | null;
  cancelAtPeriodEnd: boolean;
}

/** Maps a Stripe subscription to our row. Returns null when it was not created by our checkout (no workspace or plan metadata). */
export function subscriptionToRow(sub: Stripe.Subscription): SubscriptionRow | null {
  const workspaceId = sub.metadata?.workspace_id;
  const plan = sub.metadata?.plan;
  const item = sub.items.data[0];
  const interval = item?.price.recurring?.interval;
  if (!workspaceId || !isPaidPlan(plan) || !isInterval(interval)) return null;
  const end = item.current_period_end;
  return {
    workspaceId,
    plan,
    status: sub.status,
    interval,
    customerId: typeof sub.customer === "string" ? sub.customer : sub.customer.id,
    subscriptionId: sub.id,
    currentPeriodEnd: typeof end === "number" ? new Date(end * 1000) : null,
    cancelAtPeriodEnd: sub.cancel_at_period_end,
  };
}

export async function upsertSubscription(db: Pick<PoolClient, "query">, r: SubscriptionRow) {
  await db.query(
    `insert into subscriptions (workspace_id, plan, status, billing_interval, stripe_customer_id, stripe_subscription_id, current_period_end, cancel_at_period_end, updated_at)
     values ($1,$2,$3,$4,$5,$6,$7,$8, now())
     on conflict (workspace_id) do update set plan=excluded.plan, status=excluded.status, billing_interval=excluded.billing_interval,
       stripe_customer_id=excluded.stripe_customer_id, stripe_subscription_id=excluded.stripe_subscription_id,
       current_period_end=excluded.current_period_end, cancel_at_period_end=excluded.cancel_at_period_end, updated_at=now()`,
    [r.workspaceId, r.plan, r.status, r.interval, r.customerId, r.subscriptionId, r.currentPeriodEnd, r.cancelAtPeriodEnd],
  );
}
