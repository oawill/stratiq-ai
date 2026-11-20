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
