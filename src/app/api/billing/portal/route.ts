import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";
import { getPool } from "@/lib/db";
import { SITE_URL } from "@/lib/site";
import { getStripe } from "@/lib/stripe";

export async function POST(req: Request) {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  const origin = req.headers.get("origin");
  if (!origin || new URL(origin).host !== req.headers.get("host")) return NextResponse.json({ error: "Cross-origin request blocked." }, { status: 403 });
  if (session.role !== "owner" && session.role !== "admin") return NextResponse.json({ error: "Only workspace owners and admins can manage billing." }, { status: 403 });

  const stripe = getStripe();
  const pool = getPool();
  if (!stripe || !pool) return NextResponse.json({ error: "Billing is not available yet." }, { status: 503 });
  const row = (await pool.query("select stripe_customer_id from subscriptions where workspace_id=$1", [session.workspaceId])).rows[0];
  if (!row) return NextResponse.json({ error: "This workspace has no subscription yet." }, { status: 404 });
  try {
    const portal = await stripe.billingPortal.sessions.create({ customer: row.stripe_customer_id, return_url: `${SITE_URL}/dashboard/billing` });
    return NextResponse.json({ url: portal.url });
  } catch (e) {
    console.error("portal failed", e instanceof Error ? e.message : e);
    return NextResponse.json({ error: "Could not open billing. Please try again." }, { status: 502 });
  }
}
