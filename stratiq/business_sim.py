"""Business scenario model: price, volume, revenue and gross profit for one product, with a one-at-a-time sensitivity analysis.

Pure and deterministic. EVERY INPUT IS A HYPOTHETICAL ASSUMPTION: nothing here is estimated from data, and the model is a deliberate
simplification (constant-elasticity demand), not a forecast of any real market.

THE MODEL (version SIM_VERSION)
    reachable customers   = market_size * adoption_rate
    effective elasticity  = demand_sensitivity * (1 - competitor_reaction)
    units(price)          = reachable customers * (price / reference_price) ** (-effective elasticity)
    revenue               = price * units
    gross profit          = (price - unit_cost) * units
    gross margin          = gross profit / revenue

  adoption_rate        share of the market that adopts the product at the reference price (0 to 1).
  demand_sensitivity   how strongly volume falls as price rises (a 10% price rise cuts volume by about 10% * sensitivity); 0 means volume ignores price.
  competitor_reaction  share of your price move that competitors match (0 to 1). A matched move changes nobody's relative price, so customers do not
                       switch: reaction mutes the volume response. This is a documented simplification, not a model of competitor behaviour.

  With effective elasticity e > 1, gross profit is maximised at price = unit_cost * e / (e - 1). With e <= 1 volume barely responds to price, so gross
  profit keeps rising with price and there is no interior maximum; the result says so instead of inventing one.
"""
from __future__ import annotations

import math

SIM_VERSION = "1.0.0"

# key: (lowest, highest, label, plain meaning)
INPUTS: dict[str, tuple[float, float, str, str]] = {
    "market_size": (1, 1e9, "Market size (potential customers)", "How many customers could buy in the period."),
    "adoption_rate": (0.0, 1.0, "Adoption rate at the reference price", "The share of the market that adopts at the reference price."),
    "reference_price": (0.01, 1e7, "Reference price", "The price at which adoption_rate applies."),
    "price": (0.01, 1e7, "Price", "The price you are testing."),
    "unit_cost": (0.0, 1e7, "Unit cost", "What each unit costs you to supply."),
    "demand_sensitivity": (0.0, 10.0, "Demand sensitivity", "How strongly volume falls as price rises."),
    "competitor_reaction": (0.0, 1.0, "Competitor reaction", "The share of your price moves that competitors match."),
}
SWEEP_POINTS = 11
SENSITIVITY_STEP = 0.10          # each input is moved down and up by 10% (clamped to its allowed range) in turn

DOCUMENTATION = (
    "units = market size x adoption rate x (price / reference price) ^ (-effective elasticity), where effective elasticity = demand sensitivity x (1 - competitor reaction). "
    "Revenue = price x units; gross profit = (price - unit cost) x units. All inputs are your assumptions: none is estimated from data, and the constant-elasticity form "
    "is a simplification. Competitor reaction is modelled only as muting the volume response."
)


def validate(inputs: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for k, (lo, hi, label, _) in INPUTS.items():
        if k not in inputs:
            raise ValueError(f"'{label}' is required.")
        v = inputs[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f"'{label}' must be a finite number.")
        if not lo <= v <= hi:
            raise ValueError(f"'{label}' must be between {lo:g} and {hi:g}.")
        out[k] = float(v)
    extra = set(inputs) - set(INPUTS)
    if extra:
        raise ValueError(f"Unknown input(s): {', '.join(sorted(extra))}.")
    return out


def effective_elasticity(x: dict) -> float:
    return x["demand_sensitivity"] * (1.0 - x["competitor_reaction"])


def units_at(x: dict, price: float) -> float:
    return x["market_size"] * x["adoption_rate"] * (price / x["reference_price"]) ** (-effective_elasticity(x))


def outcome(x: dict, price: float | None = None) -> dict:
    p = x["price"] if price is None else price
    u = units_at(x, p)
    revenue = p * u
    gp = (p - x["unit_cost"]) * u
    return {"price": p, "units": u, "revenue": revenue, "gross_profit": gp, "gross_margin": (gp / revenue) if revenue > 0 else None}


def optimal_price(x: dict) -> dict:
    e = effective_elasticity(x)
    if e > 1.0 and x["unit_cost"] > 0:
        p = x["unit_cost"] * e / (e - 1.0)
        return {"exists": True, "price": p, "note": f"With an effective elasticity of {e:.2f}, gross profit is highest at price = unit cost x e / (e - 1)."}
    if e > 1.0:
        return {"exists": False, "price": None, "note": "With zero unit cost and elasticity above 1, revenue falls as price rises, so gross profit is highest at the lowest price you allow."}
    return {"exists": False, "price": None, "note": f"With an effective elasticity of {e:.2f} (1 or below) volume barely responds to price, so gross profit keeps rising with price: there is no interior best price in this model."}


def price_sweep(x: dict, points: int = SWEEP_POINTS) -> list[dict]:
    lo, hi = max(0.01, x["price"] * 0.5), x["price"] * 1.5
    step = (hi - lo) / (points - 1)
    return [outcome(x, lo + i * step) for i in range(points)]


def sensitivity(x: dict) -> list[dict]:
    """Move each input down and up by 10% (kept inside its allowed range), one at a time, and report the change in revenue and gross profit."""
    base = outcome(x)
    rows = []
    for k, (lo, hi, label, _) in INPUTS.items():
        row = {"key": k, "label": label, "base_value": x[k], "low": None, "high": None}
        for side, factor in (("low", 1 - SENSITIVITY_STEP), ("high", 1 + SENSITIVITY_STEP)):
            v = min(hi, max(lo, x[k] * factor))
            if v == x[k]:
                continue
            o = outcome({**x, k: v})
            row[side] = {"value": v, "revenue_change": o["revenue"] - base["revenue"], "gross_profit_change": o["gross_profit"] - base["gross_profit"],
                         "gross_profit_change_percent": ((o["gross_profit"] / base["gross_profit"] - 1) * 100) if base["gross_profit"] else None}
        rows.append(row)
    rows.sort(key=lambda r: -max(abs(s["gross_profit_change"]) for s in (r["low"], r["high"]) if s) if (r["low"] or r["high"]) else 0)
    return rows


def run(inputs: dict, scenarios: list[dict] | None = None) -> dict:
    """The base case plus up to three named alternative scenarios, each overriding some inputs."""
    x = validate(inputs)
    scenarios = scenarios or []
    if len(scenarios) > 3:
        raise ValueError("At most 3 alternative scenarios can be compared with the base case.")
    names = {"base case"}
    alts = []
    for i, sc in enumerate(scenarios):
        name = (sc.get("name") or f"Scenario {i + 1}").strip()[:60]
        if name.lower() in names:
            raise ValueError(f"Scenario names must be unique and cannot be 'Base case' ('{name}').")
        names.add(name.lower())
        y = validate({**x, **(sc.get("overrides") or {})})
        o = outcome(y)
        b = outcome(x)
        alts.append({"name": name, "overrides": {k: y[k] for k in y if y[k] != x[k]}, "inputs": y, **o, "optimal_price": optimal_price(y),
                     "change_vs_base": {"units": o["units"] - b["units"], "revenue": o["revenue"] - b["revenue"], "gross_profit": o["gross_profit"] - b["gross_profit"]}})
    return {"label": "HYPOTHETICAL: every input is your assumption. Not a forecast of any real market, and not financial or business advice.",
            "documentation": DOCUMENTATION, "inputs": x, "input_meanings": {k: {"label": v[2], "meaning": v[3], "range": [v[0], v[1]]} for k, v in INPUTS.items()},
            "effective_elasticity": effective_elasticity(x), "base": {"name": "Base case", **outcome(x), "optimal_price": optimal_price(x)},
            "scenarios": alts, "price_sweep": price_sweep(x), "sensitivity": sensitivity(x),
            "calibrated_parameters": [], "validation_status": "Nothing in this model is calibrated from data: every input is a hypothetical assumption and the demand form is a simplification.",
            "provenance": {"model": "business_sim", "model_version": SIM_VERSION, "deterministic": True, "random_seed": None, "input_data": "none: all inputs entered by the user"}}
