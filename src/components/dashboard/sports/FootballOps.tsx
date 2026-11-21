"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { call, post } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel, dt } from "../ui";
import { NoHistory } from "./FootballMatch";

interface Drift {
  status: "ok" | "watch" | "drift" | "insufficient";
  window: number;
  needed: number;
  scored_total: number;
  note?: string;
  performance?: { recent_log_loss: number; baseline_log_loss: number; excess: number; z: number; status: string };
  calibration?: { mean_predicted_home_win: number; actual_home_win_rate: number; z: number; status: string };
}
interface Monitor {
  has_history: boolean;
  model?: string;
  run_id: string | null;
  trained_on_matches: number | null;
  matches_now: number;
  matches_since_training: number;
  days_since_training: number | null;
  drift: Drift;
  retrain: { retrain: boolean; reasons: string[]; policy?: { new_matches: number; age_days: number; age_needs_new_matches: number; drift: string } };
}
interface JobRun { id: string; kind: string; trigger: string; status: string; started_at: string; finished_at: string | null; detail: { retrain?: { status?: string; accepted?: boolean }; status?: string; accepted?: boolean; reason?: string; scored?: number } }
interface Status { monitor: Monitor; runs: JobRun[]; scheduler_configured: boolean }

const TONE = { ok: "green", watch: "amber", drift: "amber", insufficient: "muted" } as const;
const LABEL = { ok: "On track", watch: "Watch", drift: "Drifting", insufficient: "Not enough results yet" } as const;
const f3 = (v: number) => v.toFixed(3);

/** Monitoring, the retraining policy and a log of automated runs. It only reports and, when a person asks, retrains: nothing here is hidden automation. */
export function OpsTab() {
  const [s, setS] = useState<Status | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    call<Status>("football/jobs/status").then((d) => live && (setS(d), setErr(null)), (e) => live && setErr(e instanceof Error ? e.message : "Could not load model status."));
    return () => { live = false; };
  }, [tick]);

  async function act(kind: "monitor" | "retrain" | "force") {
    setBusy(kind); setErr(null); setMsg(null);
    try {
      if (kind === "monitor") {
        const r = await post<{ scored: number }>("football/jobs/monitor", {});
        setMsg(`Checked. ${r.scored} finished forecast${r.scored === 1 ? " was" : "s were"} scored.`);
      } else {
        const r = await post<{ status: string; reason?: string; accepted?: boolean; verdict?: { reason: string } }>("football/jobs/retrain", { force: kind === "force" });
        setMsg(r.status === "skipped" ? (r.reason ?? "Retraining is not due.") : r.status === "failed" ? `Retraining failed: ${r.reason}` : r.accepted ? "Retrained. The new models are now used for forecasts." : `Retrained, but the previous models stay in use. ${r.verdict?.reason ?? ""}`);
      }
      setTick((t) => t + 1);
    } catch (e) { setErr(e instanceof Error ? e.message : "The action failed."); } finally { setBusy(null); }
  }

  if (err && !s) return /Import some match history/.test(err) ? <NoHistory /> : <ErrorPanel message={err} />;
  if (!s) return <p className="text-sm text-muted" aria-busy="true">Loading…</p>;
  const m = s.monitor;
  if (!m.has_history) return <NoHistory />;
  const d = m.drift;
  return (
    <div className="space-y-4">
      <Panel title="Model health" badge={<Badge tone={TONE[d.status]}>{LABEL[d.status]}</Badge>}>
        <p className="text-sm leading-relaxed">{d.note ?? (d.status === "ok" ? "Recent tracked forecasts are doing about as well as the backtest said they would." : "")}</p>
        <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
          <div><dt className="text-xs text-muted">Watching</dt><dd>{m.model === "ensemble" ? "Calibrated ensemble" : "Dixon-Coles"}</dd></div>
          <div><dt className="text-xs text-muted">Scored live forecasts</dt><dd>{d.scored_total} (needs {d.needed} to judge drift)</dd></div>
          <div><dt className="text-xs text-muted">Trained on</dt><dd>{m.trained_on_matches === null ? "Nothing yet" : `${m.trained_on_matches.toLocaleString()} matches; ${m.matches_since_training.toLocaleString()} added since`}{m.days_since_training !== null && `, ${m.days_since_training} days ago`}</dd></div>
        </dl>
        {d.performance && d.calibration && (
          <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
            <div><dt className="text-xs text-muted">Log loss, recent vs backtest test period</dt><dd className="font-mono">{f3(d.performance.recent_log_loss)} vs {f3(d.performance.baseline_log_loss)} ({d.performance.excess >= 0 ? "+" : ""}{f3(d.performance.excess)}, z {d.performance.z.toFixed(1)})</dd></div>
            <div><dt className="text-xs text-muted">Home wins, predicted vs actual</dt><dd className="font-mono">{(d.calibration.mean_predicted_home_win * 100).toFixed(1)}% vs {(d.calibration.actual_home_win_rate * 100).toFixed(1)}% (z {d.calibration.z.toFixed(1)})</dd></div>
          </dl>
        )}
      </Panel>

      <Panel title="Retraining" badge={<Badge tone={m.retrain.retrain ? "amber" : "green"}>{m.retrain.retrain ? "Due" : "Not due"}</Badge>}>
        {m.retrain.reasons.length > 0 ? <ul className="list-disc space-y-1 pl-5 text-sm">{m.retrain.reasons.map((r) => <li key={r}>{r}</li>)}</ul> : <p className="text-sm text-muted">No retraining trigger has been met.</p>}
        {m.retrain.policy && <p className="mt-2 text-xs leading-relaxed text-muted">Policy: retrain when {m.retrain.policy.new_matches} or more matches have been added, when the models are {m.retrain.policy.age_days} days old and at least {m.retrain.policy.age_needs_new_matches} matches have been added, or when drift is flagged ({m.retrain.policy.drift}). A retrain moves the validation and test seasons forward to the newest data and replaces the live models only if its validation log loss is not clearly worse than the previous run&apos;s; either way the full results are kept as a backtest run.</p>}
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" disabled={busy !== null} onClick={() => act("monitor")} className="inline-flex items-center gap-2 rounded-xl border border-violet/60 px-4 py-2 text-sm font-semibold text-violet hover:bg-violet/10 disabled:opacity-50">{busy === "monitor" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Check now</button>
          <button type="button" disabled={busy !== null || !m.retrain.retrain} onClick={() => act("retrain")} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy === "retrain" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Retrain now</button>
          <button type="button" disabled={busy !== null} onClick={() => act("force")} className="inline-flex items-center gap-2 rounded-xl border border-line px-4 py-2 text-sm font-semibold text-muted hover:text-ink disabled:opacity-50">{busy === "force" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Retrain anyway</button>
        </div>
        {busy && busy !== "monitor" && <p role="status" className="mt-2 text-xs text-muted">Replaying every fixture and refitting the models. This can take up to a minute on ten seasons.</p>}
        {msg && <p role="status" className="mt-3 text-sm">{msg}</p>}
        {err && <p role="alert" className="mt-3 text-sm text-red-300">{err}</p>}
      </Panel>

      <Panel title="Automation">
        <p className="text-sm leading-relaxed">{s.scheduler_configured ? "A scheduler secret is configured on the server, so a scheduled job can call the cycle below." : "No scheduler is configured, so nothing runs by itself: every check and retrain here happens when someone presses a button."}</p>
        <p className="mt-2 text-xs leading-relaxed text-muted">A scheduled cycle scores forecasts whose results have arrived, stores a tracked forecast for each fixture in the next 14 days, checks drift, and retrains only when the policy above says it is due (at most one workspace per run). It is started by an authenticated call to <span className="font-mono">/api/v1/football/jobs/scheduled</span>; see FOOTBALL.md.</p>
      </Panel>

      <Panel title="Recent runs">
        {s.runs.length === 0 ? <Empty>No runs yet.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Recent monitoring and retraining runs</caption>
              <thead><tr className="text-left text-[11px] text-muted">{["When", "Kind", "Started by", "Result"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
              <tbody>{s.runs.map((r) => {
                const rt = r.kind === "scheduled" ? r.detail.retrain : r.detail;
                const result = r.status === "failed" ? "Failed" : rt?.status === "complete" ? (rt.accepted ? "Retrained and accepted" : "Retrained, kept previous models") : r.kind === "monitor" ? `Checked, ${r.detail.scored ?? 0} scored` : r.kind === "scheduled" ? "Cycle completed, no retrain" : "Skipped";
                return <tr key={r.id} className="border-t border-line"><td className="py-1.5 pr-3 font-mono text-xs">{dt(r.started_at)}</td><td className="pr-3 capitalize">{r.kind}</td><td className="pr-3">{r.trigger === "schedule" ? "Scheduler" : "A person"}</td><td>{result}</td></tr>;
              })}</tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
