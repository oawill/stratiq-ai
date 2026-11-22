# Launch checklist: velqorin.ai

Everything in the code is ready and inactive until you do the steps below. Nothing here has been changed in Vercel, DNS or any email provider.

## What was built (Phase 3)

| Item | Where | Active when |
|---|---|---|
| Terms of Use and Privacy Policy **drafts** | `/terms`, `/privacy`, linked from the footer, sitemap and the early-access consent line | Already live, with a visible "draft for legal review" banner |
| Redirect from the old hosts to the new domain | `next.config.ts` | `NEXT_PUBLIC_SITE_URL` points at a host other than `stratiq-ai.vercel.app` |
| Transactional email (early-access confirmation, account welcome) | `src/lib/email.ts` | `RESEND_API_KEY` and `EMAIL_FROM` are set |
| Page analytics (cookieless) | `<Analytics />` in `src/app/layout.tsx` | Web Analytics is enabled for the Vercel project |
| Structured server error logging | `src/instrumentation.ts` | Always (one JSON line per unhandled error in Vercel logs) |

## Your steps, in order

1. **Confirm you own `velqorin.ai`** and check trademark availability for "VELQORIN" (not legal advice).
2. **Add the domain** in the Vercel project (`velqorin.ai` and `www.velqorin.ai`), then create the DNS records Vercel shows at your registrar. Wait for the certificate.
3. **Set production env vars, then redeploy**:
   - `NEXT_PUBLIC_SITE_URL=https://velqorin.ai`
   - `PY_API_URL=https://velqorin.ai`
   - Order matters: the redirect leaves `/api`, `/app-api` and `/_next` alone, so the web app can still reach its Python function while `PY_API_URL` is being switched.
4. **Email** (optional, can come later): create a Resend account, verify the `velqorin.ai` sending domain (SPF/DKIM records), then set `RESEND_API_KEY` and `EMAIL_FROM` (for example `VELQORIN <hello@velqorin.ai>`). Without them no email is sent. Addresses ending in `.test` are never emailed.
5. **Analytics**: enable Web Analytics on the Vercel project (Project, Analytics tab). It is cookieless.
6. **Legal**: have a lawyer finish both pages. Replace every bracketed placeholder ([legal entity name], [privacy contact email], [date], and so on) and delete the draft banner in `src/components/pages/LegalPage.tsx`. Update the provider list in the Privacy Policy to match what you actually enable.
7. **Verify after the redeploy**:
   - `E2E_BASE_URL=https://velqorin.ai E2E_DATABASE_URL=<production url> npm run test:e2e`
   - `https://stratiq-ai.vercel.app/pricing` should answer with a permanent redirect to `https://velqorin.ai/pricing`.
   - Check the social preview with each platform's link debugger, and submit `https://velqorin.ai/sitemap.xml` to search consoles.
8. Optional: rename the Vercel project and GitHub repo so internal names match. This is cosmetic.

## Not done, by design

- No DNS, domain, env var or provider account was touched.
- No legal text is final. The drafts describe what the app actually collects today (see the Privacy Policy) but make no claims about entity, jurisdiction or retention.

## Status after Phase 12 (checked on https://stratiq-ai.vercel.app)

**Verified**

| Check | Result |
|---|---|
| Lighthouse 13 on the live home page (carousel layout), desktop / mobile with simulated throttling | Performance 100 / 100, accessibility 100 / 100, best practices 100 / 100, SEO 100 / 100. LCP 0.5 s / 1.1 s, CLS 0, TBT 0 ms / 80 ms. Lab numbers from one machine, not field data. |
| `/_vercel/insights/script.js` | Answers 200 on the live site, so the page-analytics script loads. Confirm in the Vercel dashboard (Analytics tab) that Web Analytics is switched on and receiving views. |
| `robots.txt` and `sitemap.xml` | Live. The sitemap lists the home page, how-it-works, pricing, about, early-access, terms and privacy; the four old domain pages are gone and redirect (308) to the carousel slides. |
| Security headers | HSTS was already sent by the platform. Phase 12 adds `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Content-Security-Policy: frame-ancestors 'none'`, a strict `Referrer-Policy` and a restrictive `Permissions-Policy` (in `next.config.ts`; covered by an e2e check once deployed). A full script-restricting CSP is **not** set: it needs per-request nonces and page-by-page testing. |

**Needs you (nothing below has been done, and none of it can be done from the code)**

1. **Real football accuracy.** Import your ten Premier League seasons (Data, Historical Football Data), then Sports, Football intelligence, Model performance, Run chronological backtest. Until then no accuracy figure for any model is real.
2. **Scheduled football jobs.** `vercel.json` now declares two crons (every 10 minutes for the light live tick, daily at 04:00 UTC for the heavy cycle). They take effect on the next deploy and need Vercel Pro (Hobby allows daily only). Set `CRON_SECRET` (16+ random characters) in the Vercel project first: without it both endpoints do not exist and nothing runs. Live fixtures also need `FOOTBALL_DATA_API_KEY` (see LIVE_FOOTBALL.md).
3. **Stripe.** Follow BILLING.md steps 1 to 3 with a test key, complete a test purchase, check the webhook and the billing portal, and only then set `BILLING_ENFORCED=1`. The real Stripe round trip has never been exercised.
4. **Domain, email, legal**: steps 1 to 6 above (own the domain, DNS and env vars, Resend, lawyer-finished Terms and Privacy).
5. **Real-device check of the carousel.** Swipe, the menu and the Solutions dropdown on an actual iPhone (Safari) and an Android phone. Automated checks cover Chromium with emulated touch only.
