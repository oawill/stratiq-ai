"""Turns structured analytical results into explanations and reports.

The engines remain the only source of numbers. Everything here either (a) formats numbers an engine already
produced into sentences, or (b) checks that any text a language model wrote contains no number that is not in
those results (`verify_grounded`). Nothing in this module computes a forecast or invents a figure.
"""
from __future__ import annotations

import html as _html
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

DISCLAIMER = {
    "sports": "Probabilities from a statistical model on a fictional development dataset. Not a prediction of the match result and not betting advice.",
    "business": "Equilibria follow from the payoffs the user entered. They are not forecasts of real competitor behavior.",
    "politics": "Scenario arithmetic on entered assumptions. Not a poll, not a validated election forecast.",
    "finance": "Educational scenario analysis. Not investment advice, not a forecast, and not connected to any broker.",
    "simulation": "Results describe the entered assumptions, not real-world outcomes.",
}


# ================================================================== formatting
def pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


def money(x: float) -> str:
    return f"{'-' if x < 0 else ''}${abs(x):,.0f}"


def num(x: float) -> str:
    """Plain decimal notation (never scientific): whole numbers with separators from 1,000 up, four significant digits below."""
    if x == 0:
        return "0"
    if abs(x) >= 1000:
        return f"{x:,.0f}"
    s = f"{x:.4g}"
    if "e" in s:
        s = f"{x:.8f}".rstrip("0").rstrip(".")
    return s


@dataclass
class Metric:
    label: str
    value: Any
    fmt: str = "num"  # pct | money | num | int | text

    def text(self) -> str:
        v = self.value
        if self.fmt == "pct":
            return pct(v)
        if self.fmt == "money":
            return money(v)
        if self.fmt == "int":
            return f"{int(v):,}"
        if self.fmt == "num":
            return num(v)
        return str(v)


@dataclass
class Facts:
    kind: str
    domain: str
    title: str
    subject: str
    metrics: list[Metric] = field(default_factory=list)
    overview: list[str] = field(default_factory=list)
    uncertainty: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    reproduction: dict[str, str] = field(default_factory=dict)

    @property
    def notice(self) -> str:
        return DISCLAIMER[self.domain]

    def sections(self) -> list[dict]:
        return [
            {"id": "overview", "title": "What this shows", "items": self.overview},
            {"id": "uncertainty", "title": "How certain is it?", "items": self.uncertainty},
            {"id": "assumptions", "title": "Assumptions behind it", "items": self.assumptions},
            {"id": "limitations", "title": "Limitations", "items": self.limitations},
            {"id": "next", "title": "What to explore next", "items": self.next_steps},
        ]

    def to_dict(self) -> dict:
        return {
            "kind": self.kind, "domain": self.domain, "title": self.title, "subject": self.subject, "notice": self.notice,
            "metrics": [{"label": m.label, "value": m.text(), "raw": m.value if m.fmt != "text" else None} for m in self.metrics],
            "sections": self.sections(), "reproduction": self.reproduction,
        }


# ================================================================== grounding check
_NUM = re.compile(r"(?<![\w.])([-+−]?)(\$?)(\d[\d,]*(?:\.\d+)?)\s?(%|k\b|m\b|bn\b)?", re.I)
_MULT = {"k": 1e3, "m": 1e6, "bn": 1e9}


def numbers_in(text: str) -> list[dict]:
    out = []
    for m in _NUM.finditer(text):
        sign, dollar, digits, suffix = m.groups()
        raw = m.group(0).strip()
        try:
            v = float(digits.replace(",", ""))
        except ValueError:
            continue
        s = (suffix or "").lower()
        if s in _MULT:
            v *= _MULT[s]
        if sign in ("-", "−"):
            v = -v
        out.append({"raw": raw, "value": v, "unit": bool(dollar or s == "%"), "percent": s == "%", "line_start": text[: m.start()].rstrip(" \t").endswith("\n") or m.start() == 0})
    return out


def allowed_numbers(facts: Facts) -> set[float]:
    blobs = [facts.title, facts.subject]
    for sec in facts.sections():
        blobs += sec["items"]
    blobs += [f"{m.label}: {m.text()}" for m in facts.metrics] + list(facts.reproduction.values())
    allowed: set[float] = set()
    for b in blobs:
        for n in numbers_in(b):
            allowed.add(abs(n["value"]))
    for m in facts.metrics:
        if isinstance(m.value, (int, float)) and not isinstance(m.value, bool) and math.isfinite(m.value):
            v = abs(float(m.value))
            allowed.update({v, v * 100})
    return allowed


def _matches(v: float, allowed: set[float]) -> bool:
    if v in allowed:
        return True
    for a in allowed:
        for d in (-3, -2, -1, 0, 1, 2, 3):
            if v != 0 and round(a, d) == v:
                return True
        if a and abs(v - a) <= 1e-9 * max(1.0, a):
            return True
    return False


def verify_grounded(text: str, facts: Facts) -> tuple[bool, list[str]]:
    """True iff every number in `text` can be traced to the facts (allowing rounding).

    Small whole numbers (0-10) without a % or $ sign are allowed as ordinary counting words and list numbering."""
    allowed = allowed_numbers(facts)
    bad = []
    for n in numbers_in(text):
        v = abs(n["value"])
        if not n["unit"] and float(v).is_integer() and v <= 10:
            continue
        if not _matches(v, allowed):
            bad.append(n["raw"])
    return (not bad), bad


# ================================================================== builders: sports
def facts_prediction(title: str, inputs: dict, outputs: dict, assumptions: list[str], limitations: list[str], model: str, created: str, cutoff: str) -> Facts:
    h, a = inputs.get("home_name") or inputs["home_team"], inputs.get("away_name") or inputs["away_team"]
    ph, pd, pa = outputs["p_home"], outputs["p_draw"], outputs["p_away"]
    lead, lp = (h, ph) if ph >= pa else (a, pa)
    top = outputs["top_scorelines"][0]
    f = Facts("prediction", "sports", title, f"{h} vs {a}")
    f.metrics = [Metric(f"{h} win", ph, "pct"), Metric("Draw", pd, "pct"), Metric(f"{a} win", pa, "pct"), Metric(f"Expected goals ({h})", outputs["home_xg"]),
                 Metric(f"Expected goals ({a})", outputs["away_xg"]), Metric("Both teams score", outputs["p_btts"], "pct"), Metric("Over 2.5 goals", outputs["p_over_2_5"], "pct"),
                 Metric("Earlier matches used", inputs["matches_used"], "int")]
    f.overview = [
        f"The model gives {h} a {pct(ph)} chance of winning, a draw {pct(pd)}, and {a} {pct(pa)}.",
        f"Expected goals are {num(outputs['home_xg'])} for {h} and {num(outputs['away_xg'])} for {a}. The single most likely scoreline is {top['home']}–{top['away']} at {pct(top['p'])}.",
        f"Both teams score in {pct(outputs['p_btts'])} of the model's outcomes and more than 2.5 goals are scored in {pct(outputs['p_over_2_5'])}.",
    ]
    f.uncertainty = [
        f"{lead} is the favourite at {pct(lp)}, which means the model expects it not to win in {pct(1 - lp)} of outcomes. A probability is not a prediction of what will happen.",
        f"Ratings were fitted on {inputs['matches_used']} earlier matches ({inputs['home_team_matches']} for {h} and {inputs['away_team_matches']} for {a}); fewer matches mean less certain ratings.",
    ]
    f.assumptions = list(assumptions) + [f"Only matches before the feature cutoff ({cutoff}) were used; dataset: {inputs['dataset']}."]
    f.limitations = list(limitations)
    f.next_steps = ["Compare this fixture with others in the same league to see how the probabilities move.",
                    "Open the Methodology tab to see how the model scores on its backtest and what it ignores.",
                    "Run a retrospective forecast on a finished fixture to see how the model would have done."]
    f.reproduction = {"Model": model, "Created": created, "Feature cutoff": cutoff, "Retrospective": "yes" if inputs.get("retrospective") else "no"}
    return f


# ================================================================== builders: simulation
def _dist_text(d: dict) -> str:
    t = d.get("type")
    args = ", ".join(f"{k} {v}" for k, v in d.items() if k not in ("type", "values"))
    if t == "discrete":
        args = ", ".join(f"{x['value']}:{x['p']}" for x in d.get("values", []))
    return f"{t}({args})"


def facts_simulation(title: str, domain: str, config: dict, result: dict, limitations: list[str], model_assumptions: list[str]) -> Facts:
    f = Facts("simulation", domain if domain in DISCLAIMER else "simulation", title, f"Monte Carlo simulation, {result['iterations']:,} runs")
    for name, o in result["outputs"].items():
        s = o["stats"]
        f.metrics += [Metric(f"{name}: mean", s["mean"]), Metric(f"{name}: 95% interval for the mean", f"{num(s['ci95_mean'][0])} to {num(s['ci95_mean'][1])}", "text"),
                      Metric(f"{name}: 5th percentile", s["p05"]), Metric(f"{name}: median", s["p50"]), Metric(f"{name}: 95th percentile", s["p95"])]
        f.overview.append(f"Across {result['iterations']:,} runs, {name} averaged {num(s['mean'])} (95% interval for the mean {num(s['ci95_mean'][0])} to {num(s['ci95_mean'][1])}); the middle 90% of runs fall between {num(s['p05'])} and {num(s['p95'])}.")
        if o.get("prob_above"):
            p = o["prob_above"]
            f.metrics.append(Metric(f"{name}: share of runs above {num(p['threshold'])}", p["p"], "pct"))
            f.overview.append(f"{name} was above {num(p['threshold'])} in {pct(p['p'])} of runs.")
            f.uncertainty.append(f"The {pct(p['p'])} figure for {name} has a standard error of {pct(p['se'], 2)} from using {result['iterations']:,} runs; more runs narrow it.")
        top = o["sensitivity"][0] if o["sensitivity"] else None
        if top and abs(top["spearman"]) > 0.1:
            f.overview.append(f"The input most associated with {name} is {top['variable']} (rank correlation {top['spearman']:+.2f}). This is association, not proof of cause.")
            f.next_steps.append(f"Change the range of {top['variable']} and re-run to see how much {name} depends on it.")
        f.uncertainty.append(f"The spread of {name} (standard deviation {num(s['sd'])}) comes from the uncertainty you put into the inputs; the engine adds no uncertainty of its own beyond sampling noise.")
    f.assumptions = [f"{v['name']} ~ {_dist_text(v['dist'])}" for v in config["variables"]] + [f"{o['name']} = {o['expr']}" for o in config["outputs"]] + list(model_assumptions)
    f.limitations = list(limitations)
    f.next_steps += ["Re-run with a different seed to see how much results move by chance alone.", "Save a second run with a changed assumption and compare the two in the Runs tab."]
    f.reproduction = {"Seed": str(result["seed"]), "Iterations": f"{result['iterations']:,}", "Engine": f"monte-carlo {result['engine_version']}", "Python": result["python_version"], "Result hash": result["result_hash"]}
    return f


# ================================================================== builders: business
def facts_business(title: str, definition: dict, analysis: dict, limitations: list[str], model_assumptions: list[str]) -> Facts:
    P, Q = definition["players"]
    R, C = definition["row_strategies"], definition["col_strategies"]
    f = Facts("business", "business", title, f"{P} vs {Q}: {len(R)}×{len(C)} game")
    nash = analysis["pure_nash"]
    f.metrics = [Metric("Pure Nash equilibria", len(nash), "int"), Metric("Pareto-optimal outcomes", len(analysis["pareto_optimal"]), "int"), Metric("Highest combined payoff", analysis["max_welfare"]["value"])]
    if not nash:
        f.overview.append("No outcome is stable under pure strategies: at every cell at least one player gains by switching.")
    for n in nash:
        f.overview.append(f"{P} playing {R[n['row']]} and {Q} playing {C[n['col']]} is a pure Nash equilibrium: payoffs {num(n['payoffs'][0])} and {num(n['payoffs'][1])}, and neither player gains by changing only their own choice.")
        f.metrics.append(Metric(f"Equilibrium ({R[n['row']]}, {C[n['col']]}) payoffs", f"{num(n['payoffs'][0])} / {num(n['payoffs'][1])}", "text"))
    d = analysis["dominance"]
    for who, names, idx in ((P, R, d["row"]["strictly_dominant"]), (Q, C, d["col"]["strictly_dominant"])):
        if idx is not None:
            f.overview.append(f"{names[idx]} is a strictly dominant strategy for {who}: it is the best response whatever the other player does.")
    if analysis.get("mixed_2x2"):
        m = analysis["mixed_2x2"]
        f.overview.append(f"A mixed equilibrium also exists: {P} plays {R[0]} with probability {m['row_probs_exact'][0]} and {Q} plays {C[0]} with probability {m['col_probs_exact'][0]}.")
    for note in analysis["notes"]:
        f.overview.append(note)
    if len(nash) > 1:
        f.uncertainty.append(f"There are {len(nash)} equilibria, so the payoffs alone do not say which one will occur.")
    f.uncertainty.append("The only uncertainty here is in the payoffs you entered; the solver itself is exact. Small payoff changes can move the equilibrium, which the sensitivity tool shows exactly.")
    f.assumptions = list(model_assumptions) + [f"{P} chooses among: {', '.join(R)}. {Q} chooses among: {', '.join(C)}."] + ([definition["notes"]] if definition.get("notes") else [])
    f.limitations = list(limitations)
    f.next_steps = ["Use the sensitivity tool on the payoff you are least sure about to see where the equilibrium changes.",
                    "Save a variant with a different payoff and compare the two scenarios side by side.",
                    "Check whether the efficient outcome differs from the equilibrium, and what would be needed to reach it."]
    return f


# ================================================================== builders: politics
def facts_coalition(title: str, inputs: dict, a: dict, limitations: list[str], model_assumptions: list[str]) -> Facts:
    f = Facts("coalition", "politics", title, f"Coalition arithmetic, {len(a['parties'])} parties, {a['total_seats']} seats")
    f.metrics = [Metric("Seats needed to win", a["seats_needed"], "int"), Metric("Minimal winning coalitions", a["minimal_winning_count"], "int")]
    for p in a["parties"]:
        f.metrics.append(Metric(f"{p['name']}: seat share / voting power", f"{pct(p['seat_share'])} / {pct(p['shapley_shubik'])}", "text"))
    f.overview = [f"A coalition needs {a['seats_needed']} of {a['total_seats']} seats to win. There are {a['winning_coalitions']} winning coalitions, of which {a['minimal_winning_count']} are minimal (no member can leave without losing)."]
    for p in sorted(a["parties"], key=lambda x: -x["shapley_shubik"])[:3]:
        f.overview.append(f"{p['name']} holds {pct(p['seat_share'])} of the seats and {pct(p['shapley_shubik'])} of the voting power (Shapley–Shubik).")
    f.overview += list(a["notes"])
    f.uncertainty = ["Seat counts are inputs, so this describes the stated seat distribution exactly. Voting power says how often a party is decisive across hypothetical coalitions, not which coalition will form."]
    f.assumptions = list(model_assumptions) + [f"Quota: more than {pct(inputs['quota_fraction'], 1)} of seats."]
    f.limitations = list(limitations)
    f.next_steps = ["Try a different winning threshold (for example two-thirds) to see who gains a veto.", "Enter left–right positions to see which minimal coalitions are ideologically connected.", "Use the election-uncertainty scenarios to see how often each coalition would reach a majority."]
    return f


def facts_turnout(title: str, inputs: dict, a: dict, limitations: list[str], model_assumptions: list[str]) -> Facts:
    b = a["baseline"]
    f = Facts("turnout", "politics", title, f"Turnout sensitivity, {len(a['parties'])} parties")
    for i, n in enumerate(a["parties"]):
        f.metrics.append(Metric(f"{n}: vote share / seats", f"{pct(b['vote_share'][i])} / {b['seats'][i]}", "text"))
    f.metrics.append(Metric("Overall turnout", b["turnout_overall"], "pct"))
    f.overview = [f"At the entered turnout rates ({pct(b['turnout_overall'])} overall) the largest party is {b['largest']} and {('the single-party majority is held by ' + b['majority_party']) if b['majority_party'] else 'no party has a single-party majority'}."]
    sw = a.get("sweep")
    if sw:
        if sw["changes"]:
            c0 = sw["changes"][0]
            f.overview.append(f"Sweeping the chosen turnout changes the outcome {len(sw['changes'])} time(s); the first tipping point is at {pct(c0['at'], 2)}: {'; '.join(c0['what'])}.")
        else:
            f.overview.append("Across the swept range the seat allocation does not change.")
        f.uncertainty.append("Tipping points are exact consequences of the entered blocs, preferences and allocation rule. They are not estimates of real turnout.")
    f.uncertainty.append("Bloc sizes, turnout rates and preferences are assumptions you entered, not polling data.")
    f.assumptions = list(model_assumptions) + [f"Allocation: {inputs['method']} with {inputs['seats']} seats and a {pct(inputs['threshold'])} threshold.", f"Blocs: {', '.join(x['name'] for x in inputs['blocs'])} (aggregate groups only)."]
    f.limitations = list(limitations)
    f.next_steps = ["Sweep a different bloc to see which one matters most to the outcome.", "Change the allocation rule or threshold and compare the tipping points.", "Save variants and compare them in Saved & compare."]
    return f


def facts_policy(title: str, inputs: dict, a: dict, limitations: list[str], model_assumptions: list[str]) -> Facts:
    f = Facts("policy", "politics", title, f"Policy trade-offs, {len(a['alternatives'])} alternatives")
    byrank = sorted(a["alternatives"], key=lambda x: x["rank"])
    for x in byrank:
        f.metrics.append(Metric(f"#{x['rank']} {x['name']}: weighted score / chance of ranking first", f"{x['weighted_score']:.3f} / {pct(x['p_top'])}", "text"))
    f.overview = [f"With your weights, the ranking is {' > '.join(a['ranking'])}."]
    top = byrank[0]
    f.overview.append(f"{top['name']} ranks first with a weighted score of {top['weighted_score']:.3f}; it ranks first in {pct(top['p_top'])} of {a['samples']:,} random weightings.")
    nd = [x["name"] for x in a["alternatives"] if x["pareto_optimal"]]
    f.overview.append(f"{len(nd)} alternative(s) are Pareto-optimal (not beaten on every criterion by another): {', '.join(nd)}.")
    for s in a["weight_sensitivity"]:
        if s.get("stable_range"):
            lo, hi = s["stable_range"]
            f.overview.append(f"The top choice stays the same while the weight on {s['criterion']} is between {pct(lo, 1)} and {pct(hi, 1)}.")
    f.uncertainty = ["The ranking depends on the weights, which are value judgements. The stability ranges and rank probabilities show how much.", f"Random weightings use seed {a['seed']}, so the probabilities reproduce exactly."]
    f.assumptions = list(model_assumptions) + [f"Criteria and weights: {', '.join(c['name'] + ' (' + str(c['weight']) + ', ' + c['direction'] + ')' for c in inputs['criteria'])}."]
    f.limitations = list(limitations)
    f.next_steps = ["Change the weight of the criterion with the narrowest stable range and see whether the ranking flips.", "Check whether a dominated alternative has non-quantified benefits worth adding as a criterion."]
    f.reproduction = {"Seed": str(a["seed"]), "Weight samples": f"{a['samples']:,}"}
    return f


# ================================================================== builders: finance
def facts_fin_mc(title: str, inputs: dict, a: dict, limitations: list[str], model_assumptions: list[str]) -> Facts:
    t, an = a["terminal"], a["analytics"]
    f = Facts("fin_montecarlo", "finance", title, f"Monte Carlo risk simulation over {a['horizon_years']:.1f} years")
    f.metrics = [Metric("Starting value", a["initial_value"], "money"), Metric("Median final value", t["median_value"], "money"), Metric("5th percentile value", t["p5_value"], "money"),
                 Metric("95th percentile value", t["p95_value"], "money"), Metric("Chance of ending lower", a["p_loss"], "pct"), Metric("Average worst drawdown", a["max_drawdown"]["mean"], "pct"),
                 Metric("Assumed portfolio return", an["expected_return"], "pct"), Metric("Portfolio volatility", an["volatility"], "pct")]
    f.overview = [f"Starting from {money(a['initial_value'])}, the median simulated value after {a['horizon_years']:.1f} years is {money(t['median_value'])}; the 5th to 95th percentile range is {money(t['p5_value'])} to {money(t['p95_value'])}.",
                  f"The portfolio ended lower than it started in {pct(a['p_loss'])} of simulated futures, and the average worst peak-to-trough drawdown was {pct(a['max_drawdown']['mean'])}."]
    for r in a["risk"]:
        f.metrics.append(Metric(f"{pct(r['confidence'], 0)} VaR / Expected Shortfall", f"{pct(r['mc_var'])} / {pct(r['mc_es'])}", "text"))
        f.overview.append(f"At {pct(r['confidence'], 0)} confidence, Value at Risk is {pct(r['mc_var'])} ({money(r['mc_var'] * a['initial_value'])}): in {pct(1 - r['confidence'], 0)} of futures the loss is at least that. The average loss in those worst futures (Expected Shortfall) is {pct(r['mc_es'])}.")
    f.uncertainty = [f"Results come from {a['iterations']:,} simulated paths with seed {a['seed']}; a different seed would move tail figures like VaR more than the median.",
                     "Every figure is conditional on the assumed returns, volatilities and correlations. If those are wrong, the risk figures are wrong by the same amount, however precise they look."]
    if a["terminal"]["analytic_mean_value"] is not None:
        f.uncertainty.append(f"Model check: the exact expected final value under these assumptions is {money(a['terminal']['analytic_mean_value'])}; the simulated mean was {money(t['mean_value'])}.")
    f.assumptions = list(model_assumptions) + [f"Assets: {', '.join(x['name'] + ' ' + pct(x['weight'], 0) for x in an['assets'])}.", f"Shocks: {a['model']['tails']}; rebalancing: {a['model']['rebalance']}."]
    f.limitations = list(limitations)
    f.next_steps = ["Switch to fat-tailed shocks and compare VaR and Expected Shortfall.", "Raise the volatility of the riskiest asset and see how its share of risk changes.", "Save two allocations with the same seed and compare them like for like."]
    f.reproduction = {"Seed": str(a["seed"]), "Simulations": f"{a['iterations']:,}", "Engine": f"financial-risk-tools {a['engine_version']}", "Python": a["python_version"], "Result hash": a["result_hash"]}
    return f


def facts_fin_stress(title: str, inputs: dict, a: dict, limitations: list[str], model_assumptions: list[str]) -> Facts:
    f = Facts("fin_stress", "finance", title, f"Stress test, {len(a['scenarios'])} hypothetical scenarios")
    for s in a["scenarios"]:
        f.metrics.append(Metric(f"{s['name']}: portfolio return", s["portfolio_return"], "pct"))
        f.overview.append(f"In '{s['name']}' the portfolio would move by {pct(s['portfolio_return'])} ({money(s['pnl'])} on {money(inputs['initial_value'])}), leaving {money(s['value_after'])}.")
    f.overview.append(f"The worst of the scenarios you entered is '{a['worst']}'.")
    f.uncertainty = ["These are instant revaluations under hypothetical shocks. They say what would happen if the shocks occurred, not how likely they are."]
    f.assumptions = list(model_assumptions) + [f"Weights: {', '.join(x['name'] + ' ' + pct(x['weight'], 0) for x in inputs['assets'])}."]
    f.limitations = list(limitations)
    f.next_steps = ["Use reverse stress to find how large a shock would be needed to reach a loss you could not tolerate.", "Add a scenario that hits several assets at once, because losses often arrive together."]
    return f


def facts_fin_hist(title: str, inputs: dict, a: dict, limitations: list[str], model_assumptions: list[str]) -> Facts:
    p = a["portfolio"]
    f = Facts("fin_historical", "finance", title, f"Historical analysis of {p['periods']} periods of user-supplied returns")
    f.metrics = [Metric("Compound annual growth", p["cagr"], "pct"), Metric("Annualised volatility", p["annualised_vol"], "pct"), Metric("Maximum drawdown", p["max_drawdown"], "pct"), Metric("Worst single period", p["worst_period"], "pct")]
    f.overview = [f"Over {p['periods']} periods the portfolio compounded at {pct(p['cagr'])} per year with annualised volatility {pct(p['annualised_vol'])}; its worst fall from a peak was {pct(p['max_drawdown'])}."]
    for r in a["risk"]:
        f.metrics.append(Metric(f"{pct(r['confidence'], 0)} historical VaR / ES (one period)", f"{pct(r['historical']['var'], 2)} / {pct(r['historical']['es'], 2)}", "text"))
        f.overview.append(f"At {pct(r['confidence'], 0)} confidence the historical one-period VaR is {pct(r['historical']['var'], 2)} and Expected Shortfall {pct(r['historical']['es'], 2)}, based on the worst {r['tail_observations']} observation(s).")
        if r.get("warning"):
            f.uncertainty.append(f"At {pct(r['confidence'], 0)}: {r['warning']}")
        k = r["kupiec_parametric"]
        f.uncertainty.append(f"A normal-distribution VaR at {pct(r['confidence'], 0)} was exceeded {k['exceedances']} times against about {num(k['expected'])} expected (Kupiec p-value {k['p_value']:.3f}).")
    f.uncertainty.append("The data was supplied by the user and is not verified; results describe that past data only.")
    f.assumptions = list(model_assumptions) + [f"Weights: {', '.join(n + ' ' + pct(w, 0) for n, w in zip(a['names'], a['weights']))}, rebalanced every period.", a["provenance"]]
    f.limitations = list(limitations)
    f.next_steps = ["Compare normal and historical VaR: a large gap suggests fat tails.", "Test different weights to see which series drives the drawdown."]
    return f


# ================================================================== comparison text
def compare_text(kind: str, scenarios: list[dict]) -> list[str]:
    """Differences between saved scenarios of the same kind, from their stored summaries (numbers only from those)."""
    t = [s["title"] for s in scenarios]
    S = [s["summary"] for s in scenarios]
    out: list[str] = []
    if kind == "simulation":
        for row in S:  # S is a list of per-output rows
            name = row["output"]
            runs = [r for r in row["runs"] if r]
            base = runs[0]
            out.append(f"For {name}, '{base['title']}' averaged {num(base['mean'])}.")
            for r, d in zip(row["runs"][1:], row["diff_vs_first"][1:]):
                if r and d:
                    sig = "does not exclude zero" if d["ci95"][0] <= 0 <= d["ci95"][1] else "excludes zero"
                    out.append(f"'{r['title']}' averaged {num(r['mean'])}, a difference of {num(d['mean_diff'])} (95% interval {num(d['ci95'][0])} to {num(d['ci95'][1])}), which {sig}: {'the gap could be sampling noise' if sig.startswith('does') else 'the gap is larger than sampling noise alone'}.")
        return out
    if kind == "business":
        for ti, s in zip(t, S):
            nash = ", ".join(f"({n['row']}, {n['col']})" for n in s["pure_nash"]) or "none"
            out.append(f"'{ti}': pure Nash equilibria: {nash}; highest combined payoff {num(s['max_welfare'])}.")
        return out
    if kind == "coalition":
        for ti, s in zip(t, S):
            top = max(s["parties"], key=lambda p: p["shapley_shubik"])
            out.append(f"'{ti}': {s['seats_needed']} of {s['total_seats']} seats needed; {s['minimal_winning_count']} minimal winning coalitions; most voting power: {top['name']} ({pct(top['shapley_shubik'])}).")
        return out
    if kind == "turnout":
        for ti, s in zip(t, S):
            out.append(f"'{ti}': largest party {s['largest']}; single-party majority {s['majority_party'] or 'none'}; overall turnout {pct(s['turnout'])}.")
        return out
    if kind == "policy":
        for ti, s in zip(t, S):
            out.append(f"'{ti}': ranking {' > '.join(s['ranking'])}.")
        return out
    if kind == "montecarlo":
        for ti, s in zip(t, S):
            r = s["risk"][-1]
            out.append(f"'{ti}': median final value {money(s['median_value'])}, chance of ending lower {pct(s['p_loss'])}, {pct(r['confidence'], 0)} VaR {pct(r['var'])} and Expected Shortfall {pct(r['es'])} (seed {s['seed']}).")
        if len({s["seed"] for s in S}) > 1:
            out.append("The scenarios used different random seeds, so part of each difference is simulation noise.")
        return out
    if kind == "stress":
        for ti, s in zip(t, S):
            out.append(f"'{ti}': worst scenario '{s['worst']}'.")
        return out
    if kind == "historical":
        for ti, s in zip(t, S):
            out.append(f"'{ti}': compound annual growth {pct(s['cagr'])}, annualised volatility {pct(s['annualised_vol'])}, maximum drawdown {pct(s['max_drawdown'])}.")
        return out
    return out


# ================================================================== reports
def report_markdown(f: Facts, generated: str) -> str:
    L = [f"# {f.title}", "", f"*{f.subject}*  ", f"Generated {generated}", "", f"> {f.notice}", "", "## Key results", "", "| Measure | Value |", "|---|---|"]
    L += [f"| {m.label} | {m.text()} |" for m in f.metrics]
    for sec in f.sections():
        if sec["items"]:
            L += ["", f"## {sec['title']}", ""] + [f"- {x}" for x in sec["items"]]
    if f.reproduction:
        L += ["", "## Reproduction details", ""] + [f"- **{k}:** {v}" for k, v in f.reproduction.items()]
    L += ["", "---", "Numbers in this report were computed by the STRATIQ AI engines from the stated assumptions. Explanatory text is assembled from those numbers.", ""]
    return "\n".join(L)


def report_html(f: Facts, generated: str) -> str:
    e = _html.escape
    parts = [f"<h1>{e(f.title)}</h1>", f"<p class='sub'>{e(f.subject)} · generated {e(generated)}</p>", f"<p class='notice'>{e(f.notice)}</p>",
             "<h2>Key results</h2><table><tbody>" + "".join(f"<tr><th>{e(m.label)}</th><td>{e(m.text())}</td></tr>" for m in f.metrics) + "</tbody></table>"]
    for sec in f.sections():
        if sec["items"]:
            parts.append(f"<h2>{e(sec['title'])}</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in sec["items"]) + "</ul>")
    if f.reproduction:
        parts.append("<h2>Reproduction details</h2><ul>" + "".join(f"<li><strong>{e(k)}:</strong> {e(v)}</li>" for k, v in f.reproduction.items()) + "</ul>")
    parts.append("<footer>Numbers in this report were computed by the STRATIQ AI engines from the stated assumptions. Explanatory text is assembled from those numbers.</footer>")
    css = ("body{font:15px/1.55 system-ui,sans-serif;max-width:780px;margin:2rem auto;padding:0 1rem;color:#111}h1{margin-bottom:.2rem}.sub{color:#555;margin-top:0}"
           ".notice{background:#f3f0ff;border-left:4px solid #8055f6;padding:.6rem .9rem}table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #ddd;padding:.35rem .5rem;text-align:left}"
           "th{font-weight:600;width:55%}footer{margin-top:2rem;color:#666;font-size:.85rem}@media print{body{margin:0}}")
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{e(f.title)}</title><meta name='viewport' content='width=device-width,initial-scale=1'><style>{css}</style></head><body>{''.join(parts)}</body></html>"


def report_json(f: Facts, generated: str) -> str:
    return json.dumps({"generated": generated, **f.to_dict()}, indent=2)
