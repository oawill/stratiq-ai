import Stripe from "stripe";

let cached: Stripe | null | undefined;

/**
 * Stripe client, or null when billing is not configured. Live keys are refused unless STRIPE_ALLOW_LIVE=1, so a live key
 * cannot be used by accident while billing is still being tested.
 */
export function getStripe(): Stripe | null {
  if (cached !== undefined) return cached;
  const key = process.env.STRIPE_SECRET_KEY;
  if (!key || (key.startsWith("sk_live_") && process.env.STRIPE_ALLOW_LIVE !== "1")) {
    if (key) console.error("STRIPE_SECRET_KEY is a live key but STRIPE_ALLOW_LIVE is not 1; billing disabled");
    cached = null;
  } else {
    cached = new Stripe(key);
  }
  return cached;
}

export const billingConfigured = () => getStripe() !== null;
