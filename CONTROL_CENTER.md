# Personalized Intelligence Control Center (Phase 7)

The Overview page is now a per-person control center: what you track, what changed, your alerts, your briefing, your recent predictions and scenarios. Nothing on it is estimated or invented. Every widget is read from records that belong to the signed-in person (or their workspace, for shared saved work) and says so plainly when it has nothing to show.

## Repository audit (what existed, what was missing)

| Area | Before this phase |
|---|---|
| Overview | Static counts and a models list. Not personal, not customizable. |
| Watchlists | Premier League clubs and fixtures only. No notes, groups, search, paging or other domains. |
| Alerts, notifications | The header bell showed recent activity. No rules, no history, no read state. |
| Briefings | Missing. |
| Saved work | Spread over History, Workspace library, SimLab, Analyst conversations. No single place. |
| Preferences | Missing. |

## What was added

| Module | Where | Notes |
|---|---|---|
| Preferences | `stratiq/preferences_api.py`, table `user_preferences` | Layout, domains, density, quiet hours, briefing frequency. Validated against fixed lists; reading always returns a complete valid object. Per person (not per workspace or browser). |
| Overview | `stratiq/control_center_api.py`, `src/components/dashboard/control/` | Seven widgets: intelligence brief, tracked items, what changed, alerts, recent predictions, saved scenarios, quick actions. Show/hide, reorder (up/down buttons, keyboard accessible), preferred domains, density, save, restore default. Hidden widgets are not computed. |
| Universal watchlists | `stratiq/watchlist_api.py` | Sports: clubs, fixtures, the competition (computed from your imported results). Business: companies, indicators. Politics: elections, indicators. Markets: instruments, indicators. Notes, groups, search (`%` and `_` are literal), domain/type/group filters, paging, 50-item cap, one item per entity. |
| Alerts and notifications | `stratiq/alerts.py`, `stratiq/notifications_api.py`, tables `alert_rules`, `notifications` | In-app only. See below. |
| Briefings | `stratiq/briefings_api.py`, table `briefings` | Daily or weekly, chosen domains, observed vs forecast vs note, citations. See below. |
| Saved intelligence | `GET /api/v1/saved-intelligence` | Predictions, football forecasts, simulations, scenarios, Analyst conversations, briefings. Search, type filter, sort, paging, export links, delete where allowed. |
| Navigation | `src/components/dashboard/nav.ts`, `Shell.tsx` | Overview, the five product areas, AI Analyst, Watchlists, Reports, Notifications (unread badge), Data, Settings; less-used tools stay under "Workspace tools". Global search also offers quick actions. |
| Indexes | migration `0016` | `match_history_imported_idx`, `football_predictions_live_idx`, notification/briefing/watchlist indexes. |

## Honesty rules

* **No feed is implied.** Business, politics and markets watchlist items are your own notes. Each says "No data feed is connected ... nothing here updates automatically". Only sports items are computed, and only from results and fixtures you imported.
* **No invented activity.** A new workspace sees empty states with a hint, not sample numbers.
* **Alerts are opt-in.** No rule exists until you switch one on. Suggested starter rules are created only when you press the button.
* **Email and push do not exist.** Nothing is ever sent outside the app. The API and UI say this (`channels`).
* **Briefings separate what happened from forecasts.** Each line is `observed` (recorded in your data), `forecast` (a model estimate made before an event) or `note` (your own note or a limitation, such as a missing feed or data freshness). Every line cites its source, retrieval time and window. A note is never counted as a change: a briefing with only notes is reported as "nothing new". Briefings are generated only if you press the button or chose daily/weekly (default: off), and only when a full period has passed.

## Alerts in detail

Rule kinds: a result for a club you watch, a watched fixture coming up (1 to 14 days), a forecast you saved was scored, data may be stale, model drift or retraining due, briefing ready. Rules are per person.

* **Deduplication.** Each event has a key; a repeated event is counted as a duplicate and never notified twice (unique `workspace_id, user_id, dedupe_key`). Deleting a notification is a soft delete, so the event does not notify again.
* **Only new events.** A rule notifies about things that happened after it was created.
* **Quiet hours.** Start, end (may cross midnight) and your UTC offset. Notifications created inside quiet hours are held back (`visible_after`) and appear when the period ends. Nothing is dropped.
* **Rate limits.** 10 per rule and 30 per person per day. Deleting does not free up room. Evaluation runs at most once a minute per person.
* **Retention.** Notifications are removed after 90 days, briefings after 90 days.
* **When rules run.** There is no background worker: rules are evaluated when the notification list or count is read (the app polls the count every minute while open) and when the overview loads. A person who never opens the app is not notified until they do.

## Privacy and security

Preferences, watchlist items, alert rules, notifications and briefings are private to the person: another member of the same workspace sees none of them. Saved simulations and scenarios are shared inside the workspace (existing rule: only the author or an admin can delete). Analyst conversations and briefings in the library are only the caller's. All queries are parameterised and scoped by workspace and user; list endpoints are paged (max 50); text inputs are stripped of control characters and length-limited.

## Tests

`tests_py/test_control_center.py` covers preference validation and persistence (including cross-user isolation and restore), watchlist ownership, search, paging and the no-feed labelling, alert dedupe, quiet hours, rate limits, opt-in, soft delete and retention, briefing generation (empty, observed vs forecast, citations, scheduling, privacy), the overview's empty states, domain filtering and hidden widgets, and the saved-intelligence library. `e2e/workflow.spec.ts` adds browser steps for customizing and restoring the layout, universal watchlists, notifications, briefings, the library, settings and the 375px no-horizontal-scroll check.

## Not included

* Email and push delivery (no mailer is wired to the Python API; would imply an unsupported channel).
* Market, business or political data feeds, so their watchlist items cannot show live changes.
* Scheduled background evaluation; add a cron call to `POST /api/v1/alert-rules/evaluate` equivalent per workspace if wanted.
* Drag-and-drop reordering (up/down buttons are used so it works by keyboard and on phones).
* Deploying: migration `0016_control_center.sql` is applied to the dev database only.
