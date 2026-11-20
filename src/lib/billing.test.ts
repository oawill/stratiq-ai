import { describe, expect, it } from "vitest";
import type Stripe from "stripe";
import { subscriptionToRow } from "./billing";
import { lookupKey, priceCents } from "./plans";

function sub(over: Partial<Record<string, unknown>> = {}, interval: "month" | "year" = "month"): Stripe.Subscription {
  return {
    id: "sub_1",
    status: "active",
    customer: "cus_1",
    cancel_at_period_end: false,
    metadata: { workspace_id: "11111111-1111-1111-1111-111111111111", plan: "strategy_pro" },
    items: { data: [{ current_period_end: 1_800_000_000, price: { recurring: { interval } } }] },
    ...over,
  } as unknown as Stripe.Subscription;
}

describe("plan catalog", () => {
  it("prices match the published plans, with the 20% annual discount", () => {
    expect(priceCents("sports_pro", "month")).toBe(1200);
    expect(priceCents("strategy_pro", "month")).toBe(5900);
    expect(priceCents("sports_pro", "year")).toBe(11520);
    expect(priceCents("strategy_pro", "year")).toBe(56640);
  });
  it("uses stable lookup keys", () => {
    expect(lookupKey("sports_pro", "year")).toBe("velqorin_sports_pro_year");
  });
});

describe("subscriptionToRow", () => {
  it("maps a subscription created by our checkout", () => {
    const r = subscriptionToRow(sub());
    expect(r).toMatchObject({ workspaceId: "11111111-1111-1111-1111-111111111111", plan: "strategy_pro", status: "active", interval: "month", customerId: "cus_1", subscriptionId: "sub_1", cancelAtPeriodEnd: false });
    expect(r?.currentPeriodEnd?.toISOString()).toBe(new Date(1_800_000_000 * 1000).toISOString());
  });
  it("handles an expanded customer object and yearly billing", () => {
    expect(subscriptionToRow(sub({ customer: { id: "cus_9" } }, "year"))).toMatchObject({ customerId: "cus_9", interval: "year" });
  });
  it("ignores subscriptions it did not create or that name an unknown plan", () => {
    expect(subscriptionToRow(sub({ metadata: {} }))).toBeNull();
    expect(subscriptionToRow(sub({ metadata: { workspace_id: "w", plan: "free_forever" } }))).toBeNull();
  });
});
