# STRATIQ AI — Landing Page

Premium dark-mode marketing site for STRATIQ AI. Next.js 16 (App Router, Cache Components), TypeScript, Tailwind CSS 4, Framer Motion, Recharts, Lucide, PostgreSQL via `pg`.

## Setup

```bash
npm install
cp .env.example .env.local   # fill in values
npm run dev
```

### Database (early-access signups)
Apply `supabase/migrations/0001_early_access.sql` to any PostgreSQL (Supabase SQL editor, `psql`, etc.), then set `DATABASE_URL` (server-side only; never `NEXT_PUBLIC_`). If `DATABASE_URL` is missing or the write fails, the API returns an error — it never pretends a signup succeeded. Duplicate emails return HTTP 409.

### Admin
`/admin` requires `ADMIN_PASSWORD` and a 32+ char `ADMIN_SESSION_SECRET`. Authorization is checked server-side on every request (HMAC-signed, httpOnly, 8h cookie). It lists signups plus counts by interest, source and day.

## Scripts
`npm run dev` · `npm run build` · `npm run lint` · `npm run typecheck` · `npm test`

## Deploy (Vercel)
Import the repo, set the env vars from `.env.example`, deploy. Apply the migration to the production database first.

## Where the math lives
- `src/lib/poisson.ts` — independent-Poisson match probabilities
- `src/lib/game.ts` — payoff matrix, best responses, pure Nash equilibria, hypothetical duopoly model
- `src/lib/pricing.ts` — annual discount (`ANNUAL_DISCOUNT`, configurable)
- Tests: `tests/math.test.ts`

## Known limitations
- Phase 13 is partial: admin lists signups and basic counts; no CMS, no conversion funnel/analytics provider wired (add one at the marked integration point in `layout.tsx`).
- Spam protection = honeypot + minimum fill time + per-instance rate limit + zod validation. No CAPTCHA; add Vercel BotID/Turnstile and WAF rate limiting for production.
- `/login` is a labeled "coming soon" page; there are no user accounts yet.
- Politics and Finance pages are previews with no interactive demos.
- Performance dashboard is a clearly labeled sample; no accuracy claims are made.
- Lighthouse scores have not been measured yet. No OG image asset is included.
- Signup flow verified against validation/no-DB paths only; not tested against a live database.
