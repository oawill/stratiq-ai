# Billing and plans (Phase 4)

Built against **Stripe test mode only**. No Stripe key exists in this project yet, no money has moved, and nothing was created in Stripe. Billing stays dormant until you do the steps at the bottom.

## Plans

| Plan | Price | Saved forecasts | Saved scenarios | Saved simulation runs | Iterations per run | Exports |
|---|---|---|---|---|---|---|
| Explorer (free) | $0 | 10 | 3 | 3 | 10,000 | No |
| Sports Pro | $12 / month | Unlimited | 3 | 3 | 10,000 | No |
| Strategy Pro | $59 / month | Unlimited | Unlimited | Unlimited | 200,000 | Yes |

Annual billing is 12 months less 20%: Sports Pro $115.20 / year, Strategy Pro $566.40 / year. Enterprise stays contact-us. Strategy Pro includes everything in Sports Pro. The caps are my proposal: change them in `stratiq/plans.py` (they are enforced there) and the labels in `src/components/sections/PricingTable.tsx`.

Plans belong to a **workspace** (the owner or an admin buys it), not to a person. Only owners and admins can start checkout or open the billing portal.

## How it works

- **Enforcement** is server-side in the Python API (`stratiq/plans.py`): saving a forecast, scenario or simulation run, simulation size, and report/workspace exports return HTTP 402 with `{"code": "plan_limit"}` when the plan does not allow them. The browser cannot bypass it.
- **It is off by default.** Until `BILLING_ENFORCED=1` is set on the deployment, every workspace has Strategy Pro limits (the early-access behavior), and the billing page says so. This is why existing users and production are unaffected by this release.
- **Stripe Checkout** (hosted by Stripe) starts a subscription; the **customer portal** handles card changes, plan changes, invoices and cancellation. We never see card details.
- **Webhook** `POST /api/stripe/webhook` verifies Stripe's signature, processes each event id once, re-reads the subscription from Stripe so out-of-order events cannot leave stale state, and writes the `subscriptions` row. Access follows status: `active`, `trialing` and `past_due` keep the plan (past due while Stripe retries the card); anything else drops to Explorer. Data is never deleted on downgrade, you just cannot save more than the cap.
- Prices are found by lookup key (`velqorin_<plan>_<month|year>`), so no price ids live in env vars.
- A live Stripe key is refused unless `STRIPE_ALLOW_LIVE=1`.

## Your steps

1. Create a Stripe account and stay in **test mode**.
2. Put the test secret key in `.env.local` as `STRIPE_SECRET_KEY=sk_test_...` (not in chat), then run `node scripts/stripe-setup.mjs`. It creates the products and four prices idempotently.
3. For local testing install the Stripe CLI and run `stripe listen --forward-to localhost:3000/api/stripe/webhook`; it prints a `whsec_...` secret: set it as `STRIPE_WEBHOOK_SECRET` in `.env.local`. Use test card `4242 4242 4242 4242`.
4. In the Stripe dashboard (test mode), enable the **customer portal** (Settings, Billing, Customer portal) with cancellation and plan switching as you want.
5. To go live later: add a live webhook endpoint `https://<your domain>/api/stripe/webhook` for the events `customer.subscription.created`, `.updated` and `.deleted`; set production `STRIPE_SECRET_KEY` (live), `STRIPE_WEBHOOK_SECRET`, `STRIPE_ALLOW_LIVE=1`; run the setup script once with `--live`; apply migration `0006_billing.sql` to the production database (`node scripts/migrate.mjs` with production credentials); then set `BILLING_ENFORCED=1` and redeploy.
6. Legal: update the Terms and Privacy Policy for payments (Stripe as a processor, refunds, taxes, the billing entity). Consider Stripe Tax if you sell across jurisdictions. Both are for you and your lawyer; nothing here is tax or legal advice.

## What was tested, and what was not

- Tested: all plan limits, status rules, per-workspace isolation and exports gating (13 Python tests), the plan catalog and Stripe-to-database mapping (unit tests), anonymous access to the billing endpoints, and the billing page in the e2e suite.
- **Not tested: the real Stripe round trip** (checkout, webhook delivery, portal), because there is no Stripe test key yet. Run steps 1 to 3 and complete a test purchase before trusting it.
