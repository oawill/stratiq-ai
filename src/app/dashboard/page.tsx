import Link from "next/link";
import { Activity, ArrowRight, History } from "lucide-react";
import { requireSession } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import type { Overview } from "@/lib/types";
import { Badge, Empty, ErrorPanel, PageTitle, Panel, Stat, dt, pct } from "@/components/dashboard/ui";

export default async function Page() {
  const s = await requireSession();
  let o: Overview;
  try {
    o = await apiFetch<Overview>(s, "overview");
  } catch (e) {
    return (
      <>
        <PageTitle title="Overview" />
        <ErrorPanel message={e instanceof Error ? e.message : "The analytics service is unavailable."} />
      </>
    );
  }
  const brier = (name: string) => o.metrics.filter((m) => m.name === name);

  return (
    <>
      <PageTitle title={`Welcome, ${s.name.split(" ")[0]}`} sub="Your intelligence workspace. Every number here comes from your database or is labeled demonstration data." />

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Forecasts saved" value={o.counts.predictions} hint="in this workspace" />
        <Stat label="Saved simulations" value={o.counts.simulations} hint="Simulation Lab coming" />
        <Stat label="Saved scenarios" value={o.saved_scenarios} hint="Business Strategy" />
        <Stat label="Models registered" value={o.models.length} hint="see below" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Quick actions" className="lg:col-span-1">
          <div className="grid gap-2">
            <Link href="/dashboard/sports" className="flex items-center gap-3 rounded-xl border border-line bg-white/5 p-3 text-sm font-medium hover:border-violet/50">
              <Activity className="h-4 w-4 text-cyan" aria-hidden="true" /> New sports forecast <ArrowRight className="ml-auto h-4 w-4" aria-hidden="true" />
            </Link>
            <Link href="/dashboard/history" className="flex items-center gap-3 rounded-xl border border-line bg-white/5 p-3 text-sm font-medium hover:border-violet/50">
              <History className="h-4 w-4 text-violet" aria-hidden="true" /> Review prediction history <ArrowRight className="ml-auto h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
        </Panel>

        <Panel title="Recent forecasts" className="lg:col-span-2" badge={<Link href="/dashboard/history" className="text-xs text-violet underline">View all</Link>}>
          {o.recent_predictions.length === 0 ? (
            <Empty>No forecasts yet. Open Sports Intelligence, pick a fixture, and save a forecast.</Empty>
          ) : (
            <ul className="divide-y divide-line">
              {o.recent_predictions.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                  <div>
                    <div className="font-medium">{p.inputs.home_name} vs {p.inputs.away_name}</div>
                    <div className="text-[11px] text-muted">{dt(p.created_at)} · {p.model_name}@{p.model_version}</div>
                  </div>
                  <div className="font-mono text-xs text-muted">
                    H {pct(p.outputs.p_home)} · D {pct(p.outputs.p_draw)} · A {pct(p.outputs.p_away)}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel title="Available prediction models" className="lg:col-span-2">
          <ul className="grid gap-3 sm:grid-cols-2">
            {o.models.map((m) => (
              <li key={m.id} className="rounded-xl border border-line bg-card/50 p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-sm font-semibold">{m.name}@{m.version}</span>
                  <Badge tone={m.status === "active" ? "green" : "amber"}>{m.status}</Badge>
                </div>
                <p className="mt-1 line-clamp-3 text-xs text-muted">{m.description}</p>
                <div className="mt-2 text-[11px] capitalize text-muted">Domain: {m.domain}</div>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-muted">Political, Financial and Simulation models are not built yet and are not listed.</p>
        </Panel>

        <Panel title="Saved simulations" className="lg:col-span-1">
          {o.saved_simulations.length === 0 ? (
            <Empty>None yet. The Simulation Lab arrives in a later step.</Empty>
          ) : (
            <ul className="space-y-2 text-sm">{o.saved_simulations.map((x) => <li key={x.id}>{x.domain} · {x.status} · {dt(x.created_at)}</li>)}</ul>
          )}
        </Panel>

        <Panel title="Model performance" className="lg:col-span-2" badge={<Badge tone="amber">Fictional data only</Badge>}>
          {["poisson-maher"].map((name) => {
            const rows = brier(name);
            const get = (k: string) => rows.find((r) => r.metric === k);
            const b = get("brier"), bb = get("baseline_brier"), l = get("log_loss"), bl = get("baseline_log_loss");
            return b && bb && l && bl ? (
              <div key={name}>
                <div className="mb-2 font-mono text-sm">{name}@{rows[0].version}</div>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-xl border border-line p-3"><div className="text-xs text-muted">Brier score (lower is better)</div><div className="font-mono text-lg">{b.value.toFixed(4)} <span className="text-xs text-muted">vs baseline {bb.value.toFixed(4)}</span></div></div>
                  <div className="rounded-xl border border-line p-3"><div className="text-xs text-muted">Log loss (lower is better)</div><div className="font-mono text-lg">{l.value.toFixed(4)} <span className="text-xs text-muted">vs baseline {bl.value.toFixed(4)}</span></div></div>
                </div>
                <p className="mt-2 text-xs text-muted">Rolling-origin backtest on {b.sample_size} matches of the {b.dataset}. Scores on synthetic data say nothing about real-world accuracy.</p>
              </div>
            ) : <Empty key={name}>Evaluation in progress. No validated metrics yet.</Empty>;
          })}
        </Panel>

        <Panel title="Recent analysis activity" className="lg:col-span-1">
          {o.activity.length === 0 ? <Empty>No activity yet.</Empty> : (
            <ul className="space-y-2">{o.activity.map((a) => <li key={a.id} className="text-sm">{a.summary}<div className="text-[11px] text-muted">{dt(a.created_at)}</div></li>)}</ul>
          )}
        </Panel>
      </div>
    </>
  );
}
