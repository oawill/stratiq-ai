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

---

## Application (Phase 2 — Steps 1–4)

Authenticated workspace at `/dashboard` (sign up at `/signup`). Built so far: auth, dashboard shell, overview, Sports Intelligence (Poisson engine), Business Strategy (game-theory solver), Simulation Lab (Monte Carlo), Prediction History, Workspace, Settings. Politics and Finance pages exist only as clearly labeled "not built yet" placeholders.

### Architecture
- **Next.js** handles pages and sessions (scrypt passwords; session cookie token stored only as a SHA-256 hash in Postgres).
- **FastAPI** (`stratiq/api.py`, versioned at `/api/v1`) owns all analytics. Browsers never call it directly: Next mints a 60-second HS256 token (`INTERNAL_API_SECRET`) per request, and the API re-verifies workspace membership in the database on every call.
- **Engine** (`stratiq/`): `poisson.py` (scoreline math), `ratings.py` (Maher-style attack/defence fit), `model.py` (prediction + assumptions), `backtest.py` (rolling-origin evaluation), `dataset.py` (seeded FICTIONAL leagues).
- **Business Strategy** (`stratiq/gametheory.py`, `stratiq/business_api.py`): exact rational-arithmetic solver for two-player games up to 8×8 — best responses, pure Nash, strict/weak dominance, iterated elimination, Pareto/welfare, completely mixed equilibrium (2×2 only) and exact piecewise payoff sensitivity. Scenarios are saved per workspace and can be compared (2–4). No LLM is involved.
- **Simulation Lab** (`stratiq/simulation.py`, `simulation_runner.py`, `simulation_api.py`, `worker.py`): seeded Monte Carlo over 10 distributions (normal, lognormal, uniform, triangular, beta, Bernoulli, binomial, Poisson, constant, discrete) with user formulas. Formulas are parsed with `ast`, checked against a strict whitelist and compiled — never passed to an unrestricted `eval`. Results: mean ± CI, percentiles, histogram, P(output > threshold), Spearman-rank sensitivity, convergence, and a reproducibility hash. Jobs run asynchronously (queued → running → completed/failed/cancelled) with progress, cancellation and stale-worker detection; export as Markdown, CSV or JSON; compare 2–4 runs.
- Predictions are immutable (DB trigger). Each stores model version, feature cutoff, inputs, outputs, assumptions and an input hash.

### Local setup
```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # Windows; use .venv/bin on macOS/Linux
node scripts/migrate.mjs                      # apply SQL migrations
.venv/Scripts/python -m stratiq.seed          # fictional dataset + real backtest
.venv/Scripts/python -m uvicorn stratiq.api:app --port 8000
npm run dev                                   # in another terminal
```
Simulation jobs run in a background thread of the API process. On hosts where the API is serverless, run a long-lived worker instead: `.venv/Scripts/python -m stratiq.worker`.
Extra env vars: `INTERNAL_API_SECRET` (32+ chars), `PY_API_URL` (default `http://127.0.0.1:8000`).

### Tests
`npm test` (TypeScript math) · `.venv/Scripts/python -m pytest` (engine unit tests + API integration tests; each API test runs in a transaction that is always rolled back).

### Limitations
- Simulation inputs are drawn independently (no correlation); sensitivity is rank correlation, not causal. Exact reproduction holds on the same Python version (the engine records it). In-process job threads need a long-lived API process; serverless needs the standalone worker.
- Business payoffs are user-entered assumptions; templates are illustrative, not market data. Mixed equilibria exist only for 2×2 games; there is no support-enumeration solver for larger games, and no weak-dominance elimination.
- All sports data is **fictional**; backtest metrics are on simulated data and say nothing about real-world accuracy.
- The Python API is not yet configured for Vercel deployment; the deployed marketing site does not include the dashboard until that is done.
- Dev and the deployed site share one Neon database.
- No Playwright end-to-end suite yet (workflow was verified manually in a browser).
- Workspaces are single-member; no invites, password reset, or profile editing.
