// Creates the Stripe products and prices the app sells, idempotently (prices are found by lookup key, never duplicated).
// Usage: node scripts/stripe-setup.mjs            (reads STRIPE_SECRET_KEY from env or .env.local; TEST keys only)
//        node scripts/stripe-setup.mjs --live      (required for an sk_live_ key; creates real products, still no charges)
// Keep the catalog below in sync with src/lib/plans.ts and src/lib/pricing.ts (annual = 12 months less 20%).
import fs from "node:fs";
import Stripe from "stripe";

if (fs.existsSync(".env.local")) {
  for (const l of fs.readFileSync(".env.local", "utf8").split(/\r?\n/)) {
    const m = /^([A-Z_0-9]+)=(.*)$/.exec(l);
    if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^"|"$/g, "");
  }
}
const key = process.env.STRIPE_SECRET_KEY;
if (!key) throw new Error("STRIPE_SECRET_KEY is not set (put a TEST key in .env.local).");
const live = key.startsWith("sk_live_");
if (live && !process.argv.includes("--live")) throw new Error("This is a LIVE key. Re-run with --live if you really mean to create live products.");
if (!live && !key.startsWith("sk_test_")) throw new Error("STRIPE_SECRET_KEY does not look like a Stripe secret key.");
console.log(live ? "mode: LIVE" : "mode: test");

const ANNUAL_DISCOUNT = 0.2;
const PLANS = { sports_pro: { name: "Sports Pro", monthly: 12 }, strategy_pro: { name: "Strategy Pro", monthly: 59 } };
const stripe = new Stripe(key);

for (const [plan, { name, monthly }] of Object.entries(PLANS)) {
  let product;
  const found = await stripe.products.search({ query: `metadata['plan']:'${plan}' AND active:'true'` });
  if (found.data[0]) product = found.data[0];
  else product = await stripe.products.create({ name: `VELQORIN ${name}`, metadata: { plan } });
  for (const interval of ["month", "year"]) {
    const lookup_key = `velqorin_${plan}_${interval}`;
    const existing = await stripe.prices.list({ lookup_keys: [lookup_key], active: true, limit: 1 });
    if (existing.data[0]) {
      console.log("exists ", lookup_key, existing.data[0].id);
      continue;
    }
    const cents = Math.round((interval === "month" ? monthly : monthly * 12 * (1 - ANNUAL_DISCOUNT)) * 100);
    const price = await stripe.prices.create({
      product: product.id,
      currency: "usd",
      unit_amount: cents,
      recurring: { interval },
      lookup_key,
      metadata: { plan },
    });
    console.log("created", lookup_key, price.id, `${(cents / 100).toFixed(2)} USD / ${interval}`);
  }
}
console.log("done. Next: create the webhook endpoint (see BILLING.md) and set STRIPE_WEBHOOK_SECRET.");
