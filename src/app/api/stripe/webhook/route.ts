import { NextResponse } from "next/server";
import type Stripe from "stripe";
import { getPool } from "@/lib/db";
import { subscriptionToRow, upsertSubscription } from "@/lib/billing";
import { getStripe } from "@/lib/stripe";

// Stripe -> our database. The signature is verified over the raw body; each event id is processed once.
const HANDLED = new Set(["customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"]);

export async function POST(req: Request) {
  const stripe = getStripe();
  const secret = process.env.STRIPE_WEBHOOK_SECRET;
  const pool = getPool();
  if (!stripe || !secret || !pool) return NextResponse.json({ error: "Billing is not configured." }, { status: 503 });

  const signature = req.headers.get("stripe-signature");
  if (!signature) return NextResponse.json({ error: "Missing signature." }, { status: 400 });
  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(await req.text(), signature, secret);
  } catch {
    return NextResponse.json({ error: "Invalid signature." }, { status: 400 });
  }
  if (!HANDLED.has(event.type)) return NextResponse.json({ received: true, ignored: true });

  const client = await pool.connect();
  try {
    await client.query("begin");
    const fresh = await client.query("insert into stripe_events (event_id, type) values ($1,$2) on conflict do nothing", [event.id, event.type]);
    if (fresh.rowCount === 0) {
      await client.query("rollback");
      return NextResponse.json({ received: true, duplicate: true });
    }
    // Re-read the subscription so out-of-order deliveries cannot leave stale state behind.
    const id = (event.data.object as Stripe.Subscription).id;
    const sub = await stripe.subscriptions.retrieve(id);
    const row = subscriptionToRow(sub);
    if (row) await upsertSubscription(client, row);
    await client.query("commit");
    return NextResponse.json({ received: true });
  } catch (e) {
    await client.query("rollback").catch(() => {});
    console.error("stripe webhook failed", event.type, e instanceof Error ? e.message : e);
    return NextResponse.json({ error: "Processing failed." }, { status: 500 }); // Stripe retries
  } finally {
    client.release();
  }
}
