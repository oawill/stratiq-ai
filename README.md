# VELQORIN

*Intelligence Beyond Prediction.* Formerly named STRATIQ AI: see [REBRAND.md](REBRAND.md) for what changed and which internal identifiers intentionally kept the old name.

Premium dark-mode marketing site and analysis workspace for VELQORIN. Next.js 16 (App Router, Cache Components), TypeScript, Tailwind CSS 4, Framer Motion, Recharts, Lucide, PostgreSQL via `pg`.

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

## Environments and databases
| | Database | Used by |
|---|---|---|
| Production | `neondb` (managed by the Vercel–Neon integration) | the deployed site only |
| Development / tests | `stratiq_dev` (same Neon project, separate database) | `npm run dev`, `npm run test:py`, `npm run test:e2e` |

- `.env.local` must point `DATABASE_URL` / `DATABASE_URL_UNPOOLED` at the **development** database and set `APP_ENV=development`. The Python tests, the e2e teardown and `stratiq.seed --reset` refuse to run unless `APP_ENV` is `development` or `test`.
- **Do not run `vercel env pull` into `.env.local`**: it would overwrite the development URLs with production ones. Pull into `.env.production.local` if you need the production values.
- Create the dev database once: `create database stratiq_dev;` (as the Neon owner role), then `node scripts/migrate.mjs` and `python -m stratiq.seed` (the migrate script prints the target database name).
- After running the e2e suite against the deployed site, clean up its test accounts with `E2E_DATABASE_URL=<production url> npx playwright test` (the teardown only touches `e2e-*@stratiq.test` accounts).
- Both databases share one Neon project and role. For full credential isolation, provision a second Neon resource.

## Deploy (Vercel)
The Next.js app and the FastAPI service deploy together: `api/index.py` exposes the FastAPI app as a Python function and `vercel.json` rewrites `/api/v1/*` to it (the public docs are disabled in production, and every route requires the internal token).
1. Apply the migrations to the production database (`node scripts/migrate.mjs`) and seed it once (`python -m stratiq.seed`).
2. Set environment variables: `DATABASE_URL`, `INTERNAL_API_SECRET` (32+ chars), `PY_API_URL` (the production URL), `ADMIN_PASSWORD`, `ADMIN_SESSION_SECRET`, `NEXT_PUBLIC_SITE_URL`; optionally `ANTHROPIC_API_KEY`.
3. `vercel deploy --prod`. Then verify with `E2E_BASE_URL=https://your-site npm run test:e2e` (creates and removes `e2e-*@stratiq.test` accounts).
Because serverless functions freeze after responding, simulation jobs run inside the request when `VERCEL` or `SIMULATION_INLINE=1` is set (progress is then not visible mid-run and cancellation is not possible); on a long-lived host they run in the background as before.

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

## Application (Phase 2 — Steps 1–7)

Authenticated workspace at `/dashboard` (sign up at `/signup`). Built so far: auth, dashboard shell, overview, VELQORIN Sports (Poisson engine), VELQORIN Strategy (game-theory solver), VELQORIN SimLab (Monte Carlo), VELQORIN Politics, VELQORIN Markets, Prediction History, Workspace, Settings. All five analytical modules are built, plus the assistant, a workspace library, reports and exports.

### Architecture
- **Next.js** handles pages and sessions (scrypt passwords; session cookie token stored only as a SHA-256 hash in Postgres).
- **FastAPI** (`stratiq/api.py`, versioned at `/api/v1`) owns all analytics. Browsers never call it directly: Next mints a 60-second HS256 token (`INTERNAL_API_SECRET`) per request, and the API re-verifies workspace membership in the database on every call.
- **Engine** (`stratiq/`): `poisson.py` (scoreline math), `ratings.py` (Maher-style attack/defence fit), `model.py` (prediction + assumptions), `backtest.py` (rolling-origin evaluation, plus `evaluate()` for uploaded data with a baseline, paired gain and reliability table), `dataset.py` (seeded FICTIONAL leagues).
- **VELQORIN Strategy** (`stratiq/gametheory.py`, `stratiq/business_api.py`): exact rational-arithmetic solver for two-player games up to 8×8 — best responses, pure Nash, strict/weak dominance, iterated elimination, Pareto/welfare, completely mixed equilibrium (2×2 only) and exact piecewise payoff sensitivity. Scenarios are saved per workspace and can be compared (2–4). No LLM is involved.
- **VELQORIN SimLab** (`stratiq/simulation.py`, `simulation_runner.py`, `simulation_api.py`, `worker.py`): seeded Monte Carlo over 10 distributions (normal, lognormal, uniform, triangular, beta, Bernoulli, binomial, Poisson, constant, discrete) with user formulas. Formulas are parsed with `ast`, checked against a strict whitelist and compiled — never passed to an unrestricted `eval`. Results: mean ± CI, percentiles, histogram, P(output > threshold), Spearman-rank sensitivity, convergence, and a reproducibility hash. Jobs run asynchronously (queued → running → completed/failed/cancelled) with progress, cancellation and stale-worker detection; export as Markdown, CSV or JSON; compare 2–4 runs.
- **VELQORIN Politics** (`stratiq/politics.py`, `politics_api.py`): nonpartisan, aggregate, scenario-only tools. Exact Shapley–Shubik and Banzhaf voting power, minimal/connected winning coalitions, D'Hondt / Sainte-Laguë / Hare seat allocation with thresholds, turnout sweeps with bisected tipping points, seeded election-uncertainty simulation, and multi-criteria policy analysis (Pareto set, exact weight-stability breakpoints, rank acceptability). It stores no polling data, makes no forecasts, and takes no individual-level input. Scenarios are saved per workspace and compared within a type.
- **VELQORIN Markets** (`stratiq/finance.py`, `finance_api.py`): educational, long-only, no leverage or shorting, and no trading of any kind. Portfolio analytics with Euler risk contributions; empirical and normal Value at Risk / Expected Shortfall (with a Kupiec backtest); instantaneous stress tests with reverse stress; a seeded multi-asset Monte Carlo (Cholesky-correlated lognormal returns, optional Student-t shocks, rebalanced or buy-and-hold, fan chart, drawdown statistics); and historical analysis of **user-supplied** return series. No market-data provider is configured (`GET /api/v1/finance/data-sources` says so); supplied data is labeled unverified. Scenarios are saved per workspace and compared within a type.
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
Extra env vars: `INTERNAL_API_SECRET` (32+ chars), `PY_API_URL` (default `http://127.0.0.1:8000`). Optional: `ANTHROPIC_API_KEY` (and `ASSISTANT_MODEL`) to enable the language-model mode of the assistant.

### Assistant, library and exports (Step 7)
- **Assistant** (`stratiq/explain.py`, `assistant.py`, `assistant_api.py`): explains a saved forecast, scenario or completed simulation run, or the differences between 2–4 of them. Explanations are always available in **computed** mode: sentences assembled from the engines' own numbers (what it shows, uncertainty, assumptions, limitations, what to explore next). If `ANTHROPIC_API_KEY` is set, a language model may rewrite the explanation and answer free-form questions, but its text is shown **only if every number in it matches the computed results** (rounding allowed); otherwise it is discarded, the computed explanation is shown, and the user is told why. The model gets only the structured results (no names, emails or ids), has no tools, and its output is displayed as plain text. The model path is tested with fake clients; it has not been exercised against the live API.
- **Library** (`/dashboard/workspace`): everything saved in the workspace, searchable, with per-item Explain and printable reports (HTML/Markdown/JSON), and a whole-workspace JSON export. Users can create and switch between workspaces; data is isolated per workspace.
- Simulation runs also keep their own Markdown/CSV/JSON reports.

### Tests
`npm test` (TypeScript math) · `npm run test:py` (Python engine unit tests + API integration tests; each API test runs in a transaction that is always rolled back) · `npm run test:e2e` (Playwright end-to-end workflow: landing page → sign-up → every module → library/export → workspace switching → sign-out, plus a 375 px mobile layout check; run `npm run build` first and `npx playwright install chromium` once). The e2e suite creates `e2e-*@stratiq.test` accounts in the configured database and removes them afterwards in `e2e/teardown.mjs`; point `DATABASE_URL` at a disposable database if you do not want it touching shared data.

### Limitations
- The assistant's computed explanations are templates over the engines' numbers, not open-ended reasoning; free-form questions need a configured language model. Reports are HTML/Markdown/JSON (use the browser's Print for PDF).
- The e2e suite runs on Chromium only.
- Finance models use constant volatility and correlation (no volatility clustering, regimes, costs, taxes or liquidity); Monte Carlo is synchronous with a work cap (use fewer simulations/assets for long horizons); the "normal approximation" VaR is a rough comparator over long horizons; there is no licensed market-data integration yet.
- Political tools model a single national list (no districts or compensatory seats); coalition power ignores policy fit unless positions are entered; the election-uncertainty "concentration" is a scenario knob, not a measured polling error; 2/3 is entered as 0.6667.
- Simulation inputs are drawn independently (no correlation); sensitivity is rank correlation, not causal. Exact reproduction holds on the same Python version (the engine records it). In-process job threads need a long-lived API process; serverless needs the standalone worker.
- Business payoffs are user-entered assumptions; templates are illustrative, not market data. Mixed equilibria exist only for 2×2 games; there is no support-enumeration solver for larger games, and no weak-dominance elimination.
- All sports data is **fictional**; backtest metrics are on simulated data and say nothing about real-world accuracy.
- The Python API is not yet configured for Vercel deployment; the deployed marketing site does not include the dashboard until that is done.
- Dev and the deployed site share one Neon database.
- No Playwright end-to-end suite yet (workflow was verified manually in a browser).
- Workspaces are single-member; no invites, password reset, or profile editing.
