import { requireSession } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import type { Overview } from "@/lib/types";
import { Badge, Empty, PageTitle, Panel } from "@/components/dashboard/ui";
import { ControlCenter } from "@/components/dashboard/control/ControlCenter";

export default async function Page() {
  const s = await requireSession();
  let o: Overview | null = null;
  try {
    o = await apiFetch<Overview>(s, "overview");
  } catch {
    o = null; // the personalised overview below loads on its own; only the model reference is skipped
  }
  const brier = (name: string) => (o ? o.metrics.filter((m) => m.name === name) : []);

  return (
    <>
      <PageTitle title={`Welcome, ${s.name.split(" ")[0]}`} sub="Your intelligence workspace. Every number here comes from your database or is labeled demonstration data." />

      <ControlCenter />

      {o && (
        <details className="mt-8 group">
          <summary className="cursor-pointer text-sm font-semibold text-muted hover:text-ink">Models and evaluation reference</summary>
          <div className="mt-4 grid gap-4 lg:grid-cols-3">
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
            </Panel>
            <Panel title="Model performance" badge={<Badge tone="amber">Fictional data only</Badge>}>
              {["poisson-maher"].map((name) => {
                const rows = brier(name);
                const get = (k: string) => rows.find((r) => r.metric === k);
                const b = get("brier"), bb = get("baseline_brier");
                return b && bb ? (
                  <div key={name} className="text-sm">
                    <div className="mb-1 font-mono">{name}@{rows[0].version}</div>
                    <div>Brier {b.value.toFixed(4)} <span className="text-xs text-muted">vs baseline {bb.value.toFixed(4)}</span></div>
                    <p className="mt-2 text-xs text-muted">Rolling-origin backtest on {b.sample_size} matches of the {b.dataset}. Scores on synthetic data say nothing about real-world accuracy.</p>
                  </div>
                ) : <Empty key={name}>No validated metrics yet.</Empty>;
              })}
            </Panel>
          </div>
        </details>
      )}
    </>
  );
}
