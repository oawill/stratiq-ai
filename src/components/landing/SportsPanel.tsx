"use client";

import { useMemo, useState } from "react";
import { FIXTURES, SCENARIOS, TEAMS, forecast, paramsFor, pitchHeat, pointsPerMatch, strengthIndex, type DemoTeam, type Result } from "@/lib/landing/football";
import { FootballPitch } from "../visualizations/FootballPitch";
import { ProbabilityChart } from "../visualizations/ProbabilityChart";
import { ScorelineGrid } from "../visualizations/ScorelineGrid";

const team = (id: string) => TEAMS.find((t) => t.id === id)!;
const chip: Record<Result, string> = { W: "border-emerald-400/50 bg-emerald-400/15 text-emerald-200", D: "border-slate-400/40 bg-slate-400/10 text-slate-200", L: "border-rose-400/50 bg-rose-400/15 text-rose-200" };

function Crest({ t }: { t: DemoTeam }) {
  // A placeholder crest: initials on the team colour. No real club badge is used.
  return <span aria-hidden="true" className="flex h-11 w-11 items-center justify-center rounded-full border text-xs font-bold" style={{ borderColor: `${t.colour}99`, background: `${t.colour}22`, color: t.colour }}>{t.short}</span>;
}

function Bar({ value, colour }: { value: number; colour: string }) {
  return <span className="block h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.07]"><span className="block h-full rounded-full transition-all duration-700" style={{ width: `${Math.max(0, Math.min(100, value))}%`, background: colour }} /></span>;
}

function Strength({ label, home, away, h, a, hc, ac }: { label: string; home: number; away: number; h: string; a: string; hc: string; ac: string }) {
  return (
    <div className="grid grid-cols-[3.2rem_1fr_auto_1fr_3.2rem] items-center gap-2 text-xs">
      <span className="text-right font-mono" style={{ color: hc }}>{h}</span>
      <Bar value={home} colour={hc} />
      <span className="w-24 text-center text-[11px] text-muted">{label}</span>
      <Bar value={away} colour={ac} />
      <span className="font-mono" style={{ color: ac }}>{a}</span>
    </div>
  );
}

const spreadWord = (w: number) => (w < 0.08 ? "narrow" : w < 0.15 ? "moderate" : "wide");

/** The interactive football demonstration: fictional teams, the Poisson model from lib/poisson, everything labelled illustrative. */
export default function SportsPanel() {
  const [homeId, setHome] = useState("north");
  const [awayId, setAway] = useState("river");
  const [scenario, setScenario] = useState("base");
  const [side, setSide] = useState<"home" | "away">("home");
  const home = team(homeId);
  const away = team(awayId);
  const sc = SCENARIOS.find((s) => s.id === scenario)!;
  const params = useMemo(() => sc.apply(paramsFor(home, away)), [sc, home, away]);
  const f = useMemo(() => forecast(params), [params]);
  const heatTeam = side === "home" ? home : away;
  const heat = useMemo(() => pitchHeat(side === "home" ? params.homeAttack : params.awayAttack, heatTeam.width), [side, params, heatTeam]);
  const spread = Math.max(...(["home", "draw", "away"] as const).map((k) => f.intervals[k].hi - f.intervals[k].lo));
  const pickFixture = (id: string) => { const x = FIXTURES.find((q) => q.id === id)!; setHome(x.home); setAway(x.away); setScenario("base"); };
  const activeFixture = FIXTURES.find((x) => x.home === homeId && x.away === awayId)?.id;

  return (
    <div className="grid gap-5 lg:grid-cols-12">
      <div className="glass space-y-5 rounded-3xl p-5 lg:col-span-5">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Demonstration fixtures</p>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Demonstration fixtures">
            {FIXTURES.map((x) => (
              <button key={x.id} type="button" aria-pressed={activeFixture === x.id} onClick={() => pickFixture(x.id)} className={`rounded-lg border px-3 py-2 text-left text-xs transition-colors ${activeFixture === x.id ? "border-ion/70 bg-ion/10 text-ink" : "border-line text-muted hover:text-ink"}`}>{x.label}</button>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {([["Home team", homeId, setHome, awayId], ["Away team", awayId, setAway, homeId]] as const).map(([label, value, set, other]) => (
            <div key={label}>
              <label htmlFor={`sp-${label}`} className="mb-1 block text-xs text-muted">{label}</label>
              <select id={`sp-${label}`} value={value} onChange={(e) => set(e.target.value)} className="w-full rounded-xl border border-line bg-night/70 px-3 py-2 text-sm focus:border-ion focus:outline-none focus:ring-2 focus:ring-ion/40">
                {TEAMS.filter((t) => t.id !== other).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
          ))}
        </div>
        <fieldset>
          <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Example match scenarios</legend>
          <div className="grid gap-2">
            {SCENARIOS.map((s) => (
              <label key={s.id} className={`flex cursor-pointer items-start gap-2.5 rounded-xl border p-2.5 text-sm transition-colors ${scenario === s.id ? "border-ion/60 bg-ion/10" : "border-line hover:bg-white/5"}`}>
                <input type="radio" name="sp-scenario" value={s.id} checked={scenario === s.id} onChange={() => setScenario(s.id)} className="mt-1 accent-[#00E5FF]" />
                <span><span className="font-semibold">{s.label}</span><span className="block text-xs text-muted">{s.note}</span></span>
              </label>
            ))}
          </div>
        </fieldset>
      </div>

      <div className="space-y-5 lg:col-span-7">
        <div className="glass rounded-3xl p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3"><Crest t={home} /><div><p className="font-bold">{home.name}</p><p className="text-xs text-muted">Home</p></div></div>
            <span className="font-mono text-xs text-muted">vs</span>
            <div className="flex items-center gap-3 text-right"><div><p className="font-bold">{away.name}</p><p className="text-xs text-muted">Away</p></div><Crest t={away} /></div>
          </div>
          <div className="mt-5 grid gap-6 md:grid-cols-2">
            <div aria-live="polite">
              <ProbabilityChart
                caption={`Win, draw and loss probabilities for ${home.name} against ${away.name}`}
                bars={[
                  { key: "h", label: `${home.name} win`, value: f.probs.home, lo: f.intervals.home.lo, hi: f.intervals.home.hi, colour: home.colour },
                  { key: "d", label: "Draw", value: f.probs.draw, lo: f.intervals.draw.lo, hi: f.intervals.draw.hi, colour: "#94A3B8" },
                  { key: "a", label: `${away.name} win`, value: f.probs.away, lo: f.intervals.away.lo, hi: f.intervals.away.hi, colour: away.colour },
                ]}
              />
              <dl className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
                <div className="rounded-lg border border-line p-2"><dt className="text-muted">Expected goals</dt><dd className="font-mono text-sm font-bold">{f.xg.home.toFixed(2)} – {f.xg.away.toFixed(2)}</dd></div>
                <div className="rounded-lg border border-line p-2"><dt className="text-muted">Likeliest score</dt><dd className="font-mono text-sm font-bold">{f.topScorelines[0].home}–{f.topScorelines[0].away}</dd></div>
                <div className="rounded-lg border border-line p-2"><dt className="text-muted">Spread</dt><dd className="font-mono text-sm font-bold capitalize">{spreadWord(spread)}</dd></div>
              </dl>
              <p className="mt-3 text-xs leading-relaxed text-muted">
                The pale band on each bar is how far that probability moves if each side&apos;s expected goals were {Math.round(0.15 * 100)}% higher or lower. It shows how sensitive this demonstration model is to its inputs. It is not a confidence score, and no accuracy is claimed.
              </p>
            </div>
            <ScorelineGrid grid={f.probs.grid} covered={f.probs.covered} home={home.short} away={away.short} />
          </div>
        </div>

        <div className="grid gap-5 md:grid-cols-2">
          <div className="glass rounded-3xl p-5">
            <div className="mb-3 flex items-center justify-between gap-2">
              <h3 className="text-sm font-bold">Attacking zones</h3>
              <div role="group" aria-label="Team shown on the pitch" className="inline-flex rounded-lg border border-line p-0.5 text-xs">
                {(["home", "away"] as const).map((k) => <button key={k} type="button" aria-pressed={side === k} onClick={() => setSide(k)} className={`rounded-md px-2.5 py-1 ${side === k ? "bg-white/10 text-ink" : "text-muted"}`}>{k === "home" ? home.short : away.short}</button>)}
              </div>
            </div>
            <FootballPitch heat={heat} colour={heatTeam.colour} label={`${heatTeam.name} attacking zones`} />
            <p className="mt-2 text-[11px] text-muted">Illustrative zones generated from the demonstration attack rating. Not player-tracking data.</p>
          </div>
          <div className="glass space-y-4 rounded-3xl p-5">
            <h3 className="text-sm font-bold">Form and team strength</h3>
            <div className="space-y-2">
              {[home, away].map((t) => (
                <div key={t.id} className="flex items-center justify-between gap-2 text-xs">
                  <span className="w-28 truncate font-semibold" style={{ color: t.colour }}>{t.name}</span>
                  <span className="flex gap-1" aria-label={`Last five results: ${t.form.join(", ")}`}>{t.form.map((r, i) => <span key={i} className={`flex h-6 w-6 items-center justify-center rounded border text-[11px] font-bold ${chip[r]}`}>{r}</span>)}</span>
                  <span className="font-mono text-muted">{pointsPerMatch(t.form).toFixed(1)} pts</span>
                </div>
              ))}
            </div>
            <div className="space-y-2.5 border-t border-line pt-3">
              <Strength label="Attack" home={(params.homeAttack / 1.6) * 100} away={(params.awayAttack / 1.6) * 100} h={params.homeAttack.toFixed(2)} a={params.awayAttack.toFixed(2)} hc={home.colour} ac={away.colour} />
              <Strength label="Defence" home={((1.6 - params.homeDefence) / 1.2) * 100} away={((1.6 - params.awayDefence) / 1.2) * 100} h={params.homeDefence.toFixed(2)} a={params.awayDefence.toFixed(2)} hc={home.colour} ac={away.colour} />
              <Strength label="Overall" home={strengthIndex({ attack: params.homeAttack, defence: params.homeDefence })} away={strengthIndex({ attack: params.awayAttack, defence: params.awayDefence })} h={strengthIndex({ attack: params.homeAttack, defence: params.homeDefence }).toFixed(0)} a={strengthIndex({ attack: params.awayAttack, defence: params.awayDefence }).toFixed(0)} hc={home.colour} ac={away.colour} />
            </div>
            <p className="text-[11px] leading-relaxed text-muted">Defence is goals conceded relative to average (lower is better). Overall is a 0–100 index, 50 being average.</p>
          </div>
        </div>

        <div role="note" className="rounded-2xl border border-line bg-night2/60 p-4 text-xs leading-relaxed text-muted">
          <strong className="text-ink">How this works:</strong> expected goals = league mean ({1.35}) × own attack × opponent&apos;s goals conceded × home advantage ({1.12} for the home side). Goals for each side are treated as independent Poisson variables, and the probabilities are summed over a 0–10 goal grid and renormalised. The teams, form and ratings are invented for this demonstration. It is not a real prediction and says nothing about the accuracy of the VELQORIN models.
        </div>
      </div>
    </div>
  );
}
