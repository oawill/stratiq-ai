# Cinematic landing page

The home page (`/`) is one continuous scroll through five sections (Home, Sports, Strategy, Politics, Markets), then the trust and conversion sections. It is an enhancement: every route, API, model, sign-in and billing flow is unchanged.

## What is on the page

| Order | Section | What it contains |
|---|---|---|
| 1 | **Home** (`#home`) | "From Data to Strategic Advantage", two calls to action, a rotating globe of data nodes with four module cards (Sports, Strategy, Political, Market Intelligence) that scroll to their sections |
| 2 | **Sports** (`#sports`) | Fictional fixtures: win/draw/loss probabilities with an uncertainty band, expected goals, a scoreline grid, form, team-strength bars, an illustrative pitch heatmap, four example scenarios, free choice of any two teams |
| 3 | **Strategy** (`#strategy`) | Four business scenarios drive a payoff matrix (pure Nash equilibria and best replies marked), a leader-first decision tree, an outcome chart and a sensitivity table |
| 4 | **Politics** (`#politics`) | A fictional country with a keyboard-operable map; turnout, regional swing and coalition assumptions; seats with simulated ranges; forecast, hypothetical and fictional-history clearly separated |
| 5 | **Markets** (`#markets`) | A simulated candlestick series with regime strip and volatility, risk distribution, fan chart, bull/base/bear comparison, stress tests, controlled by scenario, risk tolerance and horizon |
| | Transition bands | Between sections an SVG band crossfades one section's motif into the next (network to pitch, grid to board, tree to map, map to chart) |
| | Workflow, How it works, Capabilities, Methodology and performance disclosures (`#performance`), Pricing (`#pricing`), Early access (`#early-access`), Footer | The existing sections, kept intact, plus a four-step Data, Analysis, Simulation, Decision intelligence strip |

## Honesty rules the page follows

- Every demonstration carries a visible badge (for example "Fictional teams · simulated demonstration data · not a real prediction"). Teams, parties, regions, prices and returns are invented; the crests are placeholders.
- No live fixtures, results, market data or model performance are shown or implied. The Sports panel says it says nothing about the accuracy of the VELQORIN models.
- Politics is a neutral, fictional country with neutral party labels. Forecast, hypothetical and historical content are tagged separately; the page states that a fictional country has no election history.
- Markets never shows a return as an outcome to expect. Results are ranges under stated assumptions, and the text says "scenarios, not predictions or guaranteed returns".
- The math is on screen next to each demo and is tested (below).

## Where the logic lives

Presentation is separate from logic. Pure, seeded, deterministic functions are in `src/lib/landing/` and have 33 unit tests (`landing.test.ts`):

| File | Logic | Reuses |
|---|---|---|
| `football.ts` | expected goals, Poisson probabilities, uncertainty range (each side's expected goals moved 15%), scenarios, strength index, pitch heat | `lib/poisson.ts` |
| `strategy.ts` | profits, payoff matrix, equilibria, best replies, decision tree, sensitivity | `lib/game.ts` (same demand model as the Strategy simulator) |
| `politics.ts` | vote adjustment (swing, turnout elasticity), D'Hondt seats, 400-run seeded uncertainty, coalition majority probability | |
| `markets.ts` | lognormal portfolio value, quantiles, loss probability, expected shortfall, fan, stress tests, seeded candles, regimes | |
| `stats.ts` | seeded generator, normal CDF and inverse | |

The tests check internal consistency rather than just running the code: probabilities sum to one; the strategy equilibria match a brute-force search; the strategy model equals the existing simulator exactly; lognormal quantiles round-trip; the expected-shortfall formula matches a 200,000-draw simulation; D'Hondt hands out exactly the seats; the same seed always gives the same result.

Components: `src/components/landing/` (navigation, hero, section shells, panels, transitions, progress) and `src/components/visualizations/` (globe, probability chart, pitch, scoreline grid, payoff matrix, decision tree, outcome chart, election map, seat chart, market chart, risk distribution and fan).

## Design system

The cinematic palette applies only inside `.cine` (`src/app/globals.css`): background `#030B1C`, secondary `#07152B`, electric cyan `#00E5FF`, intelligence blue `#2563EB`, strategic violet `#8B5CF6`, text `#F8FAFC`, muted `#94A3B8`. The existing landing sections read the same CSS variables, so they take the theme without edits, and the dashboard keeps its own palette. Button fills use violet-600 (`#7C3AED`) so white text meets 4.5:1 contrast; the brand violet is used for accents.

The brand is written **VELQORIN**. velqorin.ai is the website address, as decided earlier (and enforced by an e2e check); the page does not use "VELQORIN.ai" as a name.

## Motion and performance

- Hero text appears with CSS only, so the largest paint never waits for JavaScript.
- Section panels mount only when the visitor scrolls near them (`LazyMount`) and are code-split; each placeholder is sized to the measured panel height at phone, tablet and desktop widths to avoid layout shift.
- The globe pauses when off screen or in a background tab, draws one still frame for reduced motion, and cleans up on unmount. No 3D engine, no video, no images.
- Reduced motion: transition bands and the hero parallax are shown still. The preference is read with `useSyncExternalStore` so server-rendered styles are corrected right after hydration.
- Navigation highlights the section crossing the middle of the viewport (one IntersectionObserver) and clears when none does. Smooth scrolling is CSS (`scroll-behavior`), with no scroll snapping or scroll trapping.

## Measured results (production build, Lighthouse 13, local)

| | Performance | Accessibility | Best practices | SEO | LCP | CLS | TBT |
|---|---|---|---|---|---|---|---|
| Desktop | 100 | 100 | 96 | 100 | 0.2 s | 0 | 0 ms |
| Mobile (simulated throttling) | 100 | 100 | 96 | 100 | 0.9 s | 0 | 30 ms |

The 4 points off Best practices are a console 404 for `/_vercel/insights/script.js`, which only exists when deployed on Vercel. These are lab numbers on one machine against `localhost`, not field data.

## Tests

- `npm run test` (vitest): 48 tests, 33 of them for the landing logic.
- e2e (`e2e/workflow.spec.ts`): "cinematic landing page" covers navigation and active highlighting, the hero module links, every demo (probabilities sum to 100, scenarios change results, the map works from the keyboard, bear is riskier than bull), the conversion sections, the phone menu and no sideways scrolling at 375 px, and reduced motion. The phone test also checks `/`.

## Not done, and recommendations

- **Real application screenshots** were not added: the app's data in development is fictional, and a screenshot would blur the line between a demonstration and the product. Add them once there is real, licensed content to show.
- The old home-page pieces (`sections/Hero.tsx`, `sections/Demo.tsx`, `demo/*`, `DashboardMock.tsx`, `ParticleField.tsx`) are no longer used on the home page. They were left untouched; delete them when convenient.
- The globe's four module nodes are fixed positions; there is no per-node tooltip.
- Field Core Web Vitals can only be measured after deployment.
