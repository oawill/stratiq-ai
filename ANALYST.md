# AI Analyst (Phase 6)

A conversational analyst inside the dashboard (**Dashboard, AI Analyst**, `/dashboard/analyst`). It explains and compares what is already in the workspace: imported Premier League results, the models' forecasts and backtests, saved forecasts and saved SimLab scenarios. It does not produce statistics of its own, does not browse, and cannot run or change anything.

## Repository audit (what existed, what was missing)

| Area | Before this phase |
|---|---|
| Dashboard, navigation, auth | Present: one shell, `Auth` principal with workspace and role, short-lived signed tokens. |
| Existing AI | `stratiq/assistant.py` explains **one stored result at a time** ("Explain" buttons). Deterministic sentences from the engines' numbers; optional Anthropic text accepted only if every number traces to the facts (`explain.verify_grounded`). No tools, no conversation, no question routing. |
| Sports engine, data, backtests, saved forecasts | Present (Phases 2 to 3): team profiles, fixture snapshots, Elo/Poisson/Dixon-Coles/boosted trees/ensemble, backtests, tracked live forecasts, freshness, provenance. |
| SimLab and saved scenarios | Present (Phases 4 to 5): sports and pricing runs, political/financial/strategy scenarios, versions, provenance. |
| Live provider integrations | **None, by design.** Nothing is fetched from any provider; data exists only if the user imports it. The Analyst says so. |
| Conversational interface, tool layer, citations, memory, per-answer trust panel, rate limits and cost logging for AI use | **Missing**, built in this phase. |

## How an answer is made

Two methods, one contract. The page shows which was used.

1. **Built-in rules (always available, no credentials).** The question is routed by intent to the read-only tools (club names are recognised by name and alias; follow-ups reuse the clubs, fixture or simulation from earlier in the conversation). The answer text is then assembled from the tools' own records. Every figure is read from a record and formatted, never calculated or recalled.
2. **Language model (only if `ANTHROPIC_API_KEY` is set).** The model chooses tools and sees only their validated results, then writes the answer. The text is shown **only if every number, date and season in it appears in the retrieved records and every `[S#]` source it cites exists**; otherwise it is discarded and the built-in answer is shown, with the reason. A model answer that retrieved nothing is also discarded.

Either way an answer carries: **citations** (what the source is, retrieval time, observation window, model version), **assumptions**, **limitations**, what is **not available**, and which tools were called.

## Tools (`stratiq/analyst_tools.py`)

All read-only, typed (pydantic, unknown fields rejected), workspace-scoped, parameterised SQL only. None takes SQL, a query string or a URL.

| Tool | Returns |
|---|---|
| `team_statistics` | Record, goals, home/away split, form, clean sheets, Elo, with coverage and sample notes |
| `compare_teams` | Two clubs side by side plus head-to-head |
| `fixture_details` | The model's forecast for an imported fixture or a hypothetical pairing: probabilities, expected goals, five likeliest scorelines, drivers, model version, data cutoff, factors used and not available. Never saved by this tool |
| `saved_predictions` | Forecasts the user saved before matches, with results and how each scored |
| `model_evaluation` | Latest backtest, test period only, with sample sizes, gains, warnings, whether the data changed since |
| `simlab_scenarios` | List saved runs and scenarios, or open one |
| `compare_simulations` | Baselines, scenarios and **parameter differences** of 2 to 4 saved scenarios of one domain |
| `source_freshness` | Freshness, sources with provenance as typed by the importer, latest backtest time, and "no live feed" |
| `domain_capabilities` | What can and cannot be used per domain (sports, business, politics, markets) |

Business, Politics and Markets answers exist only for **saved scenarios** (hypothetical, user-entered) and are labelled as such; nothing live is available for them and the Analyst says so. Political answers state they are not polls or forecasts; financial answers state they are scenario analysis, not investment advice.

## SimLab integration

It can explain a saved simulation (baseline versus scenarios, parameters changed, the validation status, top sensitivities for pricing runs) and compare saved ones. It can **suggest** hypothetical scenarios, shown as proposals marked "needs your approval". It never creates, runs or edits anything: no tool writes, and the proposal tells the user to run it themselves in SimLab.

## Safety, privacy and limits

- **Prompt injection.** Text written by people (club names, scenario titles and notes, file names) is stripped of control characters, length-capped, and reaches a model only inside tool results; the system prompt is fixed and never contains data. The model can call only the registered tools with validated arguments. A request inside data to run SQL, call an unknown tool, or reveal rules is refused by the tool layer and ignored by the model rules. Tests exercise these paths with scripted fake providers.
- **Credentials** are read from the server environment only. They never appear in responses, prompts, logs or the audit log (tested).
- **Rate limits:** 10 questions per person per minute and 200 per day (unsaved questions count), a daily workspace token budget (`ANALYST_DAILY_TOKEN_BUDGET`, default 300,000) after which the Analyst keeps answering with the built-in rules, 6 tool calls per question, 600-character questions, 30 s per model call and 50 s overall, and a 900-token reply cap.
- **Cost logging:** tokens, latency, provider and model are logged per question; dollars only if you set `ANALYST_PRICE_IN_PER_MTOK` and `ANALYST_PRICE_OUT_PER_MTOK`. No price is assumed.
- **Audit log:** metadata only (tools, mode, tokens, latency, cost), never the question or answer.
- **Memory (migration `0015_analyst.sql`).** Conversations are private to the person: another member, even an owner, cannot read, list, continue, export or delete them. Stored: questions, answers, display blocks, citations, and up to four remembered subjects (clubs, a fixture, a saved simulation). Raw tool results are not stored. Conversations are deleted after `ANALYST_RETENTION_DAYS` (default 90) of inactivity; people can delete one or all, and can ask with "Don't save".
- **Export:** a conversation exports as Markdown or a printable page with timestamps, sources, windows, model versions, assumptions and limitations (same plan rule as other exports; audit-logged).

## Tests

`tests_py/test_analyst.py` covers: entity extraction and routing; follow-ups; the grounding check (numbers, dates, seasons, rounding); tool argument validation and rejection of unknown tools and extra arguments; every tool being read-only (table counts unchanged); tool outputs equal to the engines' own numbers; missing data (empty workspace, no backtest, unknown club, no fixture); isolation between workspaces and between people; chat with citations and trust panel; every number in a 15-question set traced to retrieved records; honest refusal of injuries, odds and news; persistence, memory, deletion, retention and "don't save"; rate limits (including unsaved), token budget, audit-log privacy, credentials; SimLab explain, compare and suggest-only; and, with scripted fake providers, grounded model answers accepted, ungrounded or mis-cited ones discarded, provider failures, unknown tools, extra arguments, tool-call limits, injection in saved data, cost logging. End-to-end steps are in `e2e/workflow.spec.ts`.

## Not done, and honest limits

- **No real language model was exercised.** No provider key exists in this project, so the provider adapter and the model loop were tested only with scripted fake providers. Try it with a key in a non-production environment before relying on it. The built-in rules mode is what runs today.
- **Streaming is event streaming, not token streaming.** The answer is assembled on the server (retrieval, and the model call if configured), then sent to the browser as a stream of events (tools, sources, text in pieces, blocks, trust panel). The first byte arrives after retrieval. True token streaming from the provider would need the database connection to outlive the request.
- The built-in rules answer a fixed set of question shapes (favourite and factors, scorelines, a club's record and home form, comparison, model record, saved predictions, freshness, simulations, capabilities). Other phrasings get guidance, not a guess. Language-model mode handles free-form phrasing within the same tools.
- Politics and Markets have no data-driven tools beyond saved scenarios because no trustworthy source for them is connected. Business has pricing runs and payoff games only.
- Contextual charts are limited to probability bars and tables; there are no time-series charts because the tools return none.
