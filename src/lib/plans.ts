import { annualTotal } from "./pricing";

/** Paid plan catalog. The Python API (stratiq/plans.py) enforces what each plan allows; this file is what is sold. */
export type PaidPlan = "sports_pro" | "strategy_pro";
export type Interval = "month" | "year";

export const PAID_PLANS: Record<PaidPlan, { name: string; monthly: number }> = {
  sports_pro: { name: "Sports Pro", monthly: 12 },
  strategy_pro: { name: "Strategy Pro", monthly: 59 },
};

export const isPaidPlan = (x: unknown): x is PaidPlan => x === "sports_pro" || x === "strategy_pro";
export const isInterval = (x: unknown): x is Interval => x === "month" || x === "year";

/** Stripe price lookup key: lets code find prices without copying price ids into environment variables. */
export const lookupKey = (plan: PaidPlan, interval: Interval) => `velqorin_${plan}_${interval}`;

/** Amount in cents for one billing period (annual = 12 months less the shared annual discount). */
export function priceCents(plan: PaidPlan, interval: Interval): number {
  const monthly = PAID_PLANS[plan].monthly;
  return Math.round((interval === "month" ? monthly : annualTotal(monthly)) * 100);
}
