import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { getPool } from "@/lib/db";
import { isInterval, isPaidPlan, lookupKey } from "@/lib/plans";
import { SITE_URL } from "@/lib/site";
import { getStripe } from "@/lib/stripe";

const PAID_STATUSES = ["active", "trialing", "past_due"];

export async function POST(req: Request) {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  // Same-origin only (the session cookie is SameSite=Lax; this is defence in depth).
  const origin = req.headers.get("origin");
  if (!origin || new URL(origin).host !== req.headers.get("host")) return NextResponse.json({ error: "Cross-origin request blocked." }, { status: 403 });
  if (session.role !== "owner" && session.role !== "admin") return NextResponse.json({ error: "Only workspace owners and admins can change the plan." }, { status: 403 });

  const stripe = getStripe();
  const pool = getPool();
  if (!stripe || !pool) return NextResponse.json({ error: "Billing is not available yet." }, { status: 503 });

  let body: { plan?: unknown; interval?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid request." }, { status: 400 });
  }
  if (!isPaidPlan(body.plan) || !isInterval(body.interval)) return NextResponse.json({ error: "Unknown plan." }, { status: 422 });

  const existing = (await pool.query("select status, stripe_customer_id from subscriptions where workspace_id=$1", [session.workspaceId])).rows[0];
  if (existing && PAID_STATUSES.includes(existing.status)) {
    return NextResponse.json({ error: "This workspace already has a subscription. Use Manage billing to change it." }, { status: 409 });
  }

  try {
    const prices = await stripe.prices.list({ lookup_keys: [lookupKey(body.plan, body.interval)], active: true, limit: 1 });
    const price = prices.data[0];
    if (!price) return NextResponse.json({ error: "This plan is not set up in Stripe yet." }, { status: 503 });
    const checkout = await stripe.checkout.sessions.create({
      mode: "subscription",
      line_items: [{ price: price.id, quantity: 1 }],
      client_reference_id: session.workspaceId,
      ...(existing?.stripe_customer_id ? { customer: existing.stripe_customer_id } : { customer_email: session.email }),
      subscription_data: { metadata: { workspace_id: session.workspaceId, plan: body.plan } },
      allow_promotion_codes: true,
      success_url: `${SITE_URL}/dashboard/billing?checkout=success`,
      cancel_url: `${SITE_URL}/dashboard/billing?checkout=cancelled`,
    });
    return NextResponse.json({ url: checkout.url });
  } catch (e) {
    console.error("checkout failed", e instanceof Error ? e.message : e);
    return NextResponse.json({ error: "Could not start checkout. Please try again." }, { status: 502 });
  }
}
