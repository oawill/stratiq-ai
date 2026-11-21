# SimLab (Phase 4)

SimLab is the scenario-simulation part of the dashboard, at **Dashboard, SimLab** (`/dashboard/simulations`; `/dashboard/simlab` redirects there). It has five tabs: **Scenario types**, **Sports simulator**, **Monte Carlo runs**, **Saved scenarios** and **Compare results**.

The one rule every scenario follows: what is **calibrated from data** is shown apart from what is **your assumption**, and a scenario is "what the model would output if your assumptions were true", never a forecast and never advice.

## What is functional, by domain

| Domain | Where | What it does | Calibrated from data | Hypothetical |
|---|---|---|---|---|
| Sports | SimLab, Sports simulator | Baseline plus up to three scenarios for a hypothetical matchup or an imported fixture: probabilities, expected goals, markets, exact-score table, deltas, saved versions, export | Attack, defence, home advantage, league scoring rate and (if a backtest has run) the low-score correction, all estimated from your imported matches before the cutoff | Every slider: attack, defence, home advantage, tempo, and assumed absences |
| Business | Strategy (`/dashboard/business`) | Two-player payoff matrices, pure and mixed Nash equilibria, best replies, dominance, sensitivity, pricing scenarios | Nothing, unless you import data | Payoffs, demand sensitivity, competitor reaction |
| Politics | Politics (`/dashboard/politics`) | Turnout, seat allocation under a stated rule, coalitions, policy tools | Only data you import | Swings, turnout shifts, coalition choices |
| Markets | Markets (`/dashboard/finance`) | Portfolio Monte Carlo, stress tests, historical risk from your returns | Only data you import | Shocks and forward-looking inputs; educational only |
| Any formula | SimLab, Monte Carlo runs | Seeded Monte Carlo of variables and outputs you define, with history and comparison | None | All inputs |

The Politics and Markets tools and the Strategy payoff-matrix tool existed before SimLab and are linked from the overview rather than rebuilt. Their scenarios are stored in `strategic_scenarios` (so the library, comments, the assistant and exports keep working) and are brought into SimLab's saved list, comparison and export; see "One saved list" below.

## The sports scenario model (`stratiq/sports_sim.py`, version 1.0.0)

```
baseline (calibrated):   lambda_home = mu * attack_home * defence_away * home_advantage
                         lambda_away = mu * attack_away * defence_home
scenario (assumptions):  attack      *= attack_multiplier * (1 - missing_attack_loss)
                         defence     *= defence_multiplier * (1 + missing_defence_loss)
                         home_adv    *= home_advantage_multiplier
                         both lambda *= tempo_multiplier          (lambdas capped to 0.05 to 6)
scorelines:              Poisson(lambda_home) x Poisson(lambda_away), with the Dixon-Coles low-score
                         correction when a tuned rho exists; renormalised to 1
```

Home win, draw and away win are sums over that grid, so they add to 100%; displayed percentages are rounded with the largest-remainder method so they add to exactly 100.0. Ranges: multipliers 0.5 to 1.5 (tempo 0.8 to 1.2), absences 0 to 50%. The model is deterministic: no random numbers, so the stored seed is empty.

**What is not validated.** The baseline is estimated from results and can be backtested. The slider adjustments cannot: no backtest has tested whether moving one predicts anything, the models were not trained on lineups, injuries or tempo, and the screen says so. A pairing is only called a scheduled fixture when it is one you imported; any other pairing is labelled "a hypothetical matchup: this pairing is not a scheduled match".

## Saved runs, versions, access and limits (`stratiq/simlab_api.py`, migration `0014_simlab_runs.sql`)

- Every run is stored in `simlab_runs` with its inputs, outputs, model name and version, provenance (cutoff, data-through date, matches used, data SHA-256, whether tuned settings were used, generation time) and seed (null for the sports model).
- **Versioning.** Running with "save as a new version" links the run to its parent: same `scenario_key`, `version + 1`, `parent_id`. Every version stays retrievable.
- **Access.** Anyone in the workspace can read; members, admins and owners can run; a run is deleted by its author or an admin, and deletions are written to the audit log. Runs are never visible across workspaces.
- **Limits.** 20 runs per person per minute and 300 per workspace per day (HTTP 429); each saved run counts toward the plan's saved-scenario quota. Exports follow the existing Strategy Pro rule (all workspaces while billing is not enforced).
- **Export.** CSV, a printable page (use the browser's Print, then Save as PDF: there is no server-side PDF generator) and JSON. Each carries the hypothetical label, the model and the provenance, and each export is audit-logged.
- **Compare.** One run already compares a baseline with up to three scenarios; the Compare tab puts two saved runs side by side (for example two versions, or two fixtures).

## One saved list across every store (Phase 5)

Sports runs and business-pricing runs are stored in `simlab_runs`. Political and financial scenarios (and Strategy payoff games) stay in `strategic_scenarios`, because the workspace library, comments, the assistant's explanations and the library exports all read that table; moving them would have broken those. Instead SimLab reads both:

- **Saved scenarios tab** (`GET /api/v1/simlab/saved`): every domain in one newest-first list, filterable by domain, grouped by scenario with its version chain, showing where it is stored and its engine and version.
- **Version lineage and provenance on political and financial scenarios** (`stratiq/scenario_meta.py`): a new scenario gets `scenario_key`, `version`, `parent_id` and a `provenance` block (engine, engine version, random seed, time, where the inputs came from) inside its definition. The shared save bar offers "Save as the next version of the scenario I just saved", so the chain is built from the Politics and Markets pages. Scenarios saved before this existed list as version 1 with no provenance, can start a chain, and are labelled "saved before provenance was recorded".
- **Open, export, delete.** `GET /simlab/scenarios/{id}` returns the stored summary, notice, provenance and a link back to the workspace; `/simlab/scenarios/{id}/export` gives CSV or JSON (plan rule as for other exports, audit-logged); deletion follows the existing rule (author or admin, audit-logged). The library's own report export still works for these scenarios.
- **Compare.** Two to four political or financial scenarios of the same type can be compared from SimLab, using each module's existing comparison; the result is a side-by-side table of the stored summaries.
- **Limits.** Saving a political or financial scenario now counts toward the plan's saved-scenario quota and the same per-person (20 per minute) and per-workspace (300 per day) rate limits as SimLab runs, counted across both tables.

## Game theory (`stratiq/gametheory.py`)

The exact (fraction) solver already did pure Nash, best responses, dominance, iterated elimination, welfare and sensitivity. Phase 4 adds `mixed_equilibria`: **every pure and mixed Nash equilibrium of games up to 6 x 6, by support enumeration in exact arithmetic**, with a plain-language explanation per equilibrium and a statement of the assumptions (two players, known payoffs, simultaneous one-shot choice, each maximising their own payoff; an equilibrium is a prediction of stable play, not a recommendation). For a game with tied payoffs there can be a continuum of equilibria; only isolated ones are listed, and the result says so. The earlier 2 x 2 `mixed_2x2` field is unchanged, and a test checks the general solver agrees with it. It is separate from the probabilistic match model.

## Tests

`tests_py/test_simlab.py` (32): percentage normalisation, Poisson grid, direction of every assumption, validation, calibrated-versus-speculative labelling, scheduled-versus-hypothetical, reproducibility, no leakage past the cutoff, persistence with provenance, versioning, privacy, roles, rate limits, quota, exports. `tests_py/test_mixed_equilibria.py` (10): matching pennies, battle of the sexes, prisoner's dilemma, rock-paper-scissors, a 3 x 3 coordination game (7 equilibria), a randomised check that every returned equilibrium is exactly a Nash equilibrium and every pure one is found. End-to-end steps in `e2e/workflow.spec.ts`.

## Not done, and next steps

- Political and financial scenarios are listed, versioned, compared and exported through SimLab but still stored in `strategic_scenarios`; they are not rows of `simlab_runs`. Merging the two tables would mean updating the library, comments and assistant code that read the older one.
- Strategy payoff games appear in the saved list but have no stored summary, provenance or version chain of their own beyond what they already had; open them in Strategy.
- The SimLab export of a political or financial scenario is its stored summary, not a full analysis report; the library's report export remains the fuller document.
- There is no server-side PDF; the printable page covers it.
- Slider effects have never been backtested. A useful follow-up is a calibration study on real data: for historical matches where a key player was absent, does the assumed attack loss move the forecast in the right direction and by roughly the right amount?
