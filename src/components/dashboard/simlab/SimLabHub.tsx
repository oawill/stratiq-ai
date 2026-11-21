"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { Activity, Briefcase, Landmark, LineChart } from "lucide-react";
import { Badge, Panel } from "../ui";
import { SimWorkspace } from "../simulations/SimWorkspace";
import { CompareTab, RunViewer, SavedTab } from "./SavedScenarios";
import { BusinessSimulator } from "./BusinessSimulator";
import { SportsSimulator } from "./SportsSimulator";

const TABS = [["overview", "Scenario types"], ["sports", "Sports simulator"], ["business", "Business simulator"], ["montecarlo", "Monte Carlo runs"], ["saved", "Saved scenarios"], ["compare", "Compare results"]] as const;
type TabId = (typeof TABS)[number][0];

const CARDS = [
  { icon: Activity, accent: "#00E5FF", name: "Sports", status: "Functional", tab: "sports" as TabId, href: null,
    what: "Change assumptions about a Premier League fixture (attack, defence, tempo, home advantage, absences) and compare up to three scenarios with a baseline calibrated from your imported matches.",
    calibrated: "Baseline attack, defence, home advantage and league scoring rate, estimated from results before the cutoff.", speculative: "Every adjustment you make. None has been tested by a backtest.", cta: "Open the sports simulator" },
  { icon: Briefcase, accent: "#8B5CF6", name: "Business", status: "Functional", tab: "business" as TabId, href: null,
    what: "A pricing simulator (market size, adoption, price, unit cost, demand sensitivity, competitor reaction; revenue, gross profit, sensitivity), plus two-player strategy games with pure and mixed Nash equilibria in Strategy.",
    calibrated: "Nothing: this model is not fitted to data, so every input is an assumption.", speculative: "All of it: demand sensitivity, competitor reaction and adoption are your assumptions.", cta: "Open the business simulator", extra: { href: "/dashboard/business", label: "Open Strategy (payoff matrices)" } },
  { icon: Landmark, accent: "#60A5FA", name: "Politics", status: "Functional", tab: null, href: "/dashboard/politics",
    what: "Nonpartisan turnout, seat-allocation and coalition scenarios under a documented electoral rule, kept separate from official results.",
    calibrated: "Only data you import (with its source) is treated as data.", speculative: "Turnout shifts, swings and coalition choices are hypothetical.", cta: "Open Politics" },
  { icon: LineChart, accent: "#34D399", name: "Markets", status: "Functional", tab: null, href: "/dashboard/finance",
    what: "Portfolio risk and stress testing: your returns, volatility, correlations and shocks; seeded Monte Carlo, drawdown and loss measures, with limitations stated.",
    calibrated: "Only data you import.", speculative: "Scenario shocks and forward-looking inputs. Educational, not investment advice.", cta: "Open Markets" },
];

/** SimLab: one place for scenario simulation across the four domains. Sports has the dedicated simulator; the others link to their working tools. */
export function SimLabHub() {
  const [tab, setTab] = useState<TabId>("overview");
  const [opened, setOpened] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const bump = useCallback(() => setTick((t) => t + 1), []);
  const onKey = (e: React.KeyboardEvent) => {
    const i = TABS.findIndex((t) => t[0] === tab);
    if (e.key === "ArrowRight") setTab(TABS[(i + 1) % TABS.length][0]);
    if (e.key === "ArrowLeft") setTab(TABS[(i + TABS.length - 1) % TABS.length][0]);
  };
  return (
    <div>
      <div role="tablist" aria-label="SimLab" onKeyDown={onKey} className="mb-4 inline-flex max-w-full overflow-x-auto rounded-xl border border-line bg-bg/60 p-1">
        {TABS.map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} tabIndex={tab === id ? 0 : -1} onClick={() => setTab(id)} className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-semibold ${tab === id ? "bg-primary text-white" : "text-muted hover:text-ink"}`}>{label}</button>)}
      </div>
      <div role="tabpanel">
        {tab === "overview" && (
          <div className="space-y-4">
            <p className="max-w-3xl text-sm leading-relaxed text-muted">SimLab runs what-if scenarios. In every scenario the parts <strong className="text-ink">calibrated from data</strong> are kept apart from the parts that are <strong className="text-ink">your assumptions</strong>, and every saved run records its model version, inputs, data provenance and time. A scenario says what a model would output if your assumptions were true. It is not a forecast and not advice.</p>
            <ul className="grid gap-4 md:grid-cols-2" aria-label="Scenario types">
              {CARDS.map((c) => (
                <li key={c.name} className="glass flex flex-col rounded-2xl p-5" style={{ borderColor: `${c.accent}40` }}>
                  <div className="mb-2 flex items-center justify-between"><span className="flex items-center gap-2 font-bold"><c.icon className="h-5 w-5" style={{ color: c.accent }} aria-hidden="true" /> {c.name}</span><Badge tone="green">{c.status}</Badge></div>
                  <p className="text-sm leading-relaxed">{c.what}</p>
                  <dl className="mt-3 space-y-1.5 text-xs leading-relaxed text-muted"><div><dt className="inline font-semibold text-ink">Calibrated: </dt><dd className="inline">{c.calibrated}</dd></div><div><dt className="inline font-semibold text-amber-200">Hypothetical: </dt><dd className="inline">{c.speculative}</dd></div></dl>
                  <div className="mt-4 flex flex-wrap gap-2">{c.tab ? <button type="button" onClick={() => setTab(c.tab!)} className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white">{c.cta}</button> : <Link href={c.href!} className="inline-flex rounded-xl border border-violet/60 px-4 py-2 text-sm font-semibold text-violet hover:bg-violet/10">{c.cta}</Link>}{"extra" in c && c.extra && <Link href={c.extra.href} className="inline-flex rounded-xl border border-violet/60 px-4 py-2 text-sm font-semibold text-violet hover:bg-violet/10">{c.extra.label}</Link>}</div>
                </li>
              ))}
            </ul>
            <Panel title="Also in SimLab"><p className="text-sm text-muted">The <button type="button" className="text-violet underline" onClick={() => setTab("montecarlo")}>Monte Carlo runs</button> tab runs seeded simulations of any formula you define (same seed, same results), with history and comparison. <button type="button" className="text-violet underline" onClick={() => setTab("saved")}>Saved scenarios</button> lists saved sports and business simulations with their versions, and <button type="button" className="text-violet underline" onClick={() => setTab("compare")}>Compare results</button> puts two saved sports simulations side by side.</p></Panel>
          </div>
        )}
        {tab === "sports" && <SportsSimulator onSaved={bump} />}
        {tab === "business" && <BusinessSimulator onSaved={bump} />}
        {tab === "montecarlo" && <SimWorkspace />}
        {tab === "saved" && (
          <div className="space-y-4">
            {opened && <div><button type="button" onClick={() => setOpened(null)} className="mb-2 text-xs text-violet underline">Close</button><RunViewer id={opened} /></div>}
            <SavedTab tick={tick} onOpen={(id) => setOpened(id)} />
          </div>
        )}
        {tab === "compare" && <CompareTab tick={tick} />}
      </div>
    </div>
  );
}
