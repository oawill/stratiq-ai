"""Political scenario mathematics. Exact where possible (Fractions), seeded where random, never LLM-driven.

Everything here is a *scenario tool*: it computes the consequences of assumptions the user enters
(seat counts, vote shares, turnout rates, criterion weights). It contains no polling data, makes no
election forecast, and works only with aggregate groups, never individuals.
"""
from __future__ import annotations

import heapq
import math
import random
from decimal import Decimal
from fractions import Fraction
from typing import Any

MAX_PARTIES = 12
MAX_SEATS = 650
MAX_BLOCS = 12
MAX_ALTS, MAX_CRITERIA = 12, 12
METHODS = ("dhondt", "sainte_lague", "hare")


class PoliticsError(ValueError):
    pass


def _frac(x: Any, what: str = "value") -> Fraction:
    if isinstance(x, bool) or not isinstance(x, (int, float, str, Fraction)):
        raise PoliticsError(f"{what} must be a number")
    try:
        f = Fraction(x) if isinstance(x, (int, Fraction)) else Fraction(Decimal(str(x)))
    except Exception as e:  # noqa: BLE001
        raise PoliticsError(f"{what} must be a number") from e
    if isinstance(x, float) and not math.isfinite(x):
        raise PoliticsError(f"{what} must be finite")
    return f


# ================================================================== coalitions & voting power
def _quota(fraction: Any) -> Fraction:
    q = _frac(fraction, "quota fraction")
    if not (Fraction(1, 2) <= q < 1):
        raise PoliticsError("quota fraction must be at least 0.5 and below 1")
    return q


def coalition_analysis(names: list[str], seats: list[int], positions: list[float] | None = None, fraction: Any = 0.5) -> dict:
    n = len(names)
    if not 2 <= n <= MAX_PARTIES:
        raise PoliticsError(f"between 2 and {MAX_PARTIES} parties are needed")
    if len(set(names)) != n:
        raise PoliticsError("party names must be unique")
    if len(seats) != n or any(isinstance(s, bool) or not isinstance(s, int) or s < 0 for s in seats):
        raise PoliticsError("seats must be non-negative whole numbers")
    total = sum(seats)
    if total < 1:
        raise PoliticsError("total seats must be at least 1")
    if positions is not None and (len(positions) != n or any(not math.isfinite(p) for p in positions)):
        raise PoliticsError("positions must be finite numbers, one per party")
    q = _quota(fraction)
    need = math.floor(q * total) + 1  # smallest winning seat count (win iff seats > q * total)

    N = 1 << n
    sums = [0] * N
    for m in range(1, N):
        low = (m & -m).bit_length() - 1
        sums[m] = sums[m & (m - 1)] + seats[low]
    win = [s >= need for s in sums]
    full = N - 1

    fact = [math.factorial(k) for k in range(n + 1)]
    swings = [0] * n
    shapley = [Fraction(0)] * n
    for i in range(n):
        bit = 1 << i
        for m in range(N):
            if m & bit:
                continue
            if not win[m] and win[m | bit]:
                swings[i] += 1
                k = bin(m).count("1")
                shapley[i] += Fraction(fact[k] * fact[n - k - 1], fact[n])
    tot_sw = sum(swings) or 1

    minimal: list[int] = []
    for m in range(1, N):
        if win[m] and all(not win[m ^ (1 << i)] for i in range(n) if m & (1 << i)):
            minimal.append(m)

    order: list[int] | None = None
    if positions is not None:
        order = sorted(range(n), key=lambda i: (positions[i], i))
    rank_of = {p: r for r, p in enumerate(order)} if order else None

    def connected(m: int) -> bool | None:
        if rank_of is None:
            return None
        rs = sorted(rank_of[i] for i in range(n) if m & (1 << i))
        return rs[-1] - rs[0] + 1 == len(rs)

    def members(m: int) -> list[int]:
        return [i for i in range(n) if m & (1 << i)]

    ranked = []
    for m in minimal:
        mem = members(m)
        rng = None if positions is None else max(positions[i] for i in mem) - min(positions[i] for i in mem)
        ranked.append({
            "parties": mem, "seats": sums[m], "surplus": sums[m] - need, "size": len(mem),
            "ideological_range": rng, "connected": connected(m),
        })
    ranked.sort(key=lambda r: (r["surplus"], r["size"], r["ideological_range"] if r["ideological_range"] is not None else 0.0, r["parties"]))

    dictators = [i for i in range(n) if win[1 << i]]
    veto = [i for i in range(n) if not win[full ^ (1 << i)] and win[full]]
    dummies = [i for i in range(n) if swings[i] == 0]
    parties = []
    for i in range(n):
        parties.append({
            "name": names[i], "seats": seats[i], "seat_share": seats[i] / total,
            "shapley_shubik": float(shapley[i]), "shapley_shubik_exact": str(shapley[i]),
            "banzhaf_raw_swings": swings[i], "banzhaf_normalised": swings[i] / tot_sw,
            "banzhaf_probability": swings[i] / (1 << (n - 1)),
            "is_dictator": i in dictators, "is_veto": i in veto, "is_dummy": i in dummies,
        })
    return {
        "total_seats": total, "quota_fraction": float(q), "seats_needed": need,
        "parties": parties,
        "winning_coalitions": sum(win),
        "minimal_winning_count": len(minimal),
        "minimal_winning": ranked[:30],
        "connected_minimal_winning": None if positions is None else sum(1 for r in ranked if r["connected"]),
        "single_party_majority": [names[i] for i in dictators],
        "notes": _coalition_notes(names, dictators, veto, dummies, seats, shapley, total),
    }


def _coalition_notes(names, dictators, veto, dummies, seats, shapley, total) -> list[str]:
    out = []
    if dictators:
        out.append(f"{', '.join(names[i] for i in dictators)} can reach the threshold alone.")
    if veto and not dictators:
        out.append(f"Veto player(s): {', '.join(names[i] for i in veto)} (no winning coalition exists without them).")
    dm = [names[i] for i in dummies if seats[i] > 0]
    if dm:
        out.append(f"{', '.join(dm)} hold seats but are dummy players: they are never decisive in any coalition.")
    big = max(range(len(names)), key=lambda i: (float(shapley[i]) - seats[i] / total))
    gap = float(shapley[big]) - seats[big] / total
    if gap > 0.05:
        out.append(f"{names[big]}'s voting power ({float(shapley[big]) * 100:.1f}%) exceeds its seat share ({seats[big] / total * 100:.1f}%).")
    return out


# ================================================================== seat allocation
def allocate(method: str, n_seats: int, votes: list[Any], threshold: Any = 0, exact: bool = True) -> list[int]:
    """Seats by D'Hondt, Sainte-Laguë or Hare largest remainder.

    Parties below `threshold` (a fraction of valid votes, inclusive) are excluded. Ties at the cutoff are
    broken by larger vote total, then by list order. `exact=False` uses floats (faster, for Monte Carlo).
    """
    if method not in METHODS:
        raise PoliticsError(f"method must be one of {', '.join(METHODS)}")
    if isinstance(n_seats, bool) or not isinstance(n_seats, int) or not 1 <= n_seats <= MAX_SEATS:
        raise PoliticsError(f"seats must be a whole number from 1 to {MAX_SEATS}")
    conv = (lambda v: _frac(v, "votes")) if exact else float
    v = [conv(x) for x in votes]
    if any(x < 0 for x in v) or len(v) < 1:
        raise PoliticsError("votes must be non-negative")
    total = sum(v)
    if total <= 0:
        raise PoliticsError("total votes must be positive")
    th = _frac(threshold, "threshold") if exact else float(threshold)
    if not 0 <= th < 1:
        raise PoliticsError("threshold must be between 0 and 1")
    eligible = [i for i in range(len(v)) if v[i] > 0 and v[i] / total >= th]
    if not eligible:
        raise PoliticsError("no party reaches the threshold")
    out = [0] * len(v)
    if method == "hare":
        quota = sum(v[i] for i in eligible) / n_seats
        for i in eligible:
            out[i] = int(math.floor(v[i] / quota))
        left = n_seats - sum(out)
        rem = sorted(eligible, key=lambda i: (-(v[i] / quota - out[i]), -v[i], i))
        for i in rem[:left]:
            out[i] += 1
        return out
    # next divisor for a party that already holds k seats: D'Hondt k+1, Sainte-Lague 2k+1
    divisor = (lambda k: k + 1) if method == "dhondt" else (lambda k: 2 * k + 1)
    heap = [(-(v[i] / divisor(0)), -v[i], i, 0) for i in eligible]
    heapq.heapify(heap)
    for _ in range(n_seats):
        _, _, i, k = heapq.heappop(heap)
        out[i] += 1
        k += 1
        heapq.heappush(heap, (-(v[i] / divisor(k)), -v[i], i, k))
    return out


# ================================================================== turnout model & sensitivity
def _check_model(parties: list[str], blocs: list[dict]) -> None:
    if not 2 <= len(parties) <= MAX_PARTIES or len(set(parties)) != len(parties):
        raise PoliticsError(f"between 2 and {MAX_PARTIES} uniquely named parties are needed")
    if not 1 <= len(blocs) <= MAX_BLOCS:
        raise PoliticsError(f"between 1 and {MAX_BLOCS} electorate blocs are needed")
    names = set()
    for b in blocs:
        if b["name"] in names:
            raise PoliticsError("bloc names must be unique")
        names.add(b["name"])
        if _frac(b["electorate"], "electorate") <= 0:
            raise PoliticsError(f"bloc '{b['name']}': electorate must be positive")
        t = _frac(b["turnout"], "turnout")
        if not 0 <= t <= 1:
            raise PoliticsError(f"bloc '{b['name']}': turnout must be between 0 and 1")
        prefs = b["prefs"]
        if set(prefs) != set(parties):
            raise PoliticsError(f"bloc '{b['name']}': give a preference share for every party")
        ps = [_frac(prefs[p], "preference") for p in parties]
        if any(x < 0 for x in ps) or abs(sum(ps) - 1) > Fraction(1, 10**6):
            raise PoliticsError(f"bloc '{b['name']}': preference shares must be non-negative and sum to 100%")


def _evaluate(parties, blocs, turnouts: list[Fraction], method, n_seats, threshold) -> dict:
    votes = [Fraction(0)] * len(parties)
    for b, t in zip(blocs, turnouts):
        e = _frac(b["electorate"])
        for j, p in enumerate(parties):
            votes[j] += e * t * _frac(b["prefs"][p])
    total = sum(votes)
    seats = allocate(method, n_seats, votes, threshold) if total > 0 else [0] * len(parties)
    top = max(range(len(parties)), key=lambda j: (seats[j], votes[j], -j))
    maj = [j for j in range(len(parties)) if 2 * seats[j] > n_seats]
    return {
        "votes": [float(v) for v in votes], "vote_share": [float(v / total) if total else 0.0 for v in votes],
        "seats": seats, "largest": parties[top], "majority_party": parties[maj[0]] if maj else None,
        "turnout_overall": float(sum(_frac(b["electorate"]) * t for b, t in zip(blocs, turnouts)) / sum(_frac(b["electorate"]) for b in blocs)),
    }


def _signature(ev: dict) -> tuple:
    return (tuple(ev["seats"]), ev["largest"], ev["majority_party"])


def turnout_analysis(parties: list[str], blocs: list[dict], method: str, n_seats: int, threshold: Any, sweep: dict | None) -> dict:
    _check_model(parties, blocs)
    base_t = [_frac(b["turnout"]) for b in blocs]
    out: dict[str, Any] = {"baseline": _evaluate(parties, blocs, base_t, method, n_seats, threshold), "parties": parties}
    if sweep is None:
        return out
    mode = sweep.get("mode")
    lo, hi = _frac(sweep.get("lo"), "range start"), _frac(sweep.get("hi"), "range end")
    if lo >= hi:
        raise PoliticsError("range start must be below range end")
    if mode == "bloc":
        j = sweep.get("bloc")
        if not isinstance(j, int) or not 0 <= j < len(blocs):
            raise PoliticsError("choose a bloc to vary")
        if not (0 <= lo and hi <= 1):
            raise PoliticsError("turnout range must stay within 0% to 100%")

        def at(x: Fraction):
            t = list(base_t)
            t[j] = x
            return t
    elif mode == "all_shift":
        if not (-1 <= lo and hi <= 1):
            raise PoliticsError("shift must stay within -100 to +100 percentage points")

        def at(x: Fraction):
            return [min(Fraction(1), max(Fraction(0), t + x)) for t in base_t]
    else:
        raise PoliticsError("sweep mode must be 'bloc' or 'all_shift'")

    steps = 40
    xs = [lo + (hi - lo) * Fraction(i, steps) for i in range(steps + 1)]
    evs = [_evaluate(parties, blocs, at(x), method, n_seats, threshold) for x in xs]
    curve = [{"x": float(x), "overall_turnout": e["turnout_overall"], "vote_share": e["vote_share"], "seats": e["seats"]} for x, e in zip(xs, evs)]
    changes = []
    for a in range(steps):
        sa, sb = _signature(evs[a]), _signature(evs[a + 1])
        if sa == sb:
            continue
        l, r = xs[a], xs[a + 1]
        for _ in range(40):  # bisection to ~1e-12 of the step
            mid = (l + r) / 2
            if _signature(_evaluate(parties, blocs, at(mid), method, n_seats, threshold)) == sa:
                l = mid
            else:
                r = mid
        what = []
        if evs[a]["seats"] != evs[a + 1]["seats"]:
            what.append("seat allocation changes")
        if evs[a]["largest"] != evs[a + 1]["largest"]:
            what.append(f"largest party changes: {evs[a]['largest']} → {evs[a + 1]['largest']}")
        if evs[a]["majority_party"] != evs[a + 1]["majority_party"]:
            what.append(f"single-party majority: {evs[a]['majority_party'] or 'none'} → {evs[a + 1]['majority_party'] or 'none'}")
        changes.append({"at": float((l + r) / 2), "what": what, "seats_before": evs[a]["seats"], "seats_after": evs[a + 1]["seats"]})
        if len(changes) >= 60:
            break
    out["sweep"] = {"mode": mode, "bloc": sweep.get("bloc"), "range": [float(lo), float(hi)], "curve": curve, "changes": changes,
                    "note": "Change points are located by bisection between 41 grid points; two changes closer than one grid step may appear as one."}
    return out


# ================================================================== election-uncertainty Monte Carlo
def decisive_flags(seats: list[int], need: int) -> tuple[list[bool], list[bool]]:
    """(decisive_in_some_coalition, veto) per party using subset-sum bitmasks (fast; exact).

    Party i is decisive iff some coalition of the others has a seat sum s with need - seats[i] <= s < need.
    Party i is a veto player iff the others together cannot reach `need`."""
    n, tot = len(seats), sum(seats)
    decisive, veto = [False] * n, [False] * n
    for i in range(n):
        if seats[i] == 0:
            continue
        reach = 1
        for j in range(n):
            if j != i and seats[j]:
                reach |= reach << seats[j]
        lo = max(0, need - seats[i])
        decisive[i] = bool(reach & (((1 << (need - lo)) - 1) << lo)) if need > lo else False
        veto[i] = tot - seats[i] < need <= tot
    return decisive, veto


def simulate_coalitions(names: list[str], base_votes: list[float], method: str, n_seats: int, threshold: float,
                        concentration: float, fraction: Any, candidates: list[list[int]], iterations: int, seed: int) -> dict:
    """Seeded scenario noise on vote shares (Dirichlet), then seats and coalition arithmetic.

    This is NOT a polling-error model: `concentration` is a scenario knob (higher = vote shares stay near the
    entered values). Results say what follows from the assumptions."""
    n = len(names)
    if not 2 <= n <= 10 or len(base_votes) != n:
        raise PoliticsError("between 2 and 10 parties are supported for simulation")
    if not 100 <= iterations <= 5000:
        raise PoliticsError("iterations must be between 100 and 5000")
    if not (math.isfinite(concentration) and 5 <= concentration <= 100000):
        raise PoliticsError("concentration must be between 5 and 100000")
    if any(not math.isfinite(v) or v < 0 for v in base_votes) or sum(base_votes) <= 0:
        raise PoliticsError("base votes must be non-negative with a positive total")
    q = _quota(fraction)
    for c in candidates:
        if not c or any(not 0 <= i < n for i in c) or len(set(c)) != len(c):
            raise PoliticsError("each candidate coalition must list distinct valid parties")
    if len(candidates) > 10:
        raise PoliticsError("at most 10 candidate coalitions")
    rng = random.Random(seed)
    tot = sum(base_votes)
    alpha = [max(concentration * v / tot, 1e-9) for v in base_votes]
    need = math.floor(q * n_seats) + 1

    seat_sum = [0] * n
    seat_all: list[list[int]] = [[] for _ in range(n)]
    largest = [0] * n
    nondummy = [0] * n
    veto = [0] * n
    single_majority = [0] * n
    cand_win = [0] * len(candidates)
    cand_min = [0] * len(candidates)
    hung = 0
    for _ in range(iterations):
        g = [rng.gammavariate(a, 1.0) for a in alpha]
        s = sum(g)
        seats = allocate(method, n_seats, [x / s for x in g], threshold, exact=False)
        for i in range(n):
            seat_sum[i] += seats[i]
            seat_all[i].append(seats[i])
        top = max(range(n), key=lambda i: (seats[i], g[i]))
        largest[top] += 1
        if max(seats) >= need:
            single_majority[seats.index(max(seats))] += 1
        else:
            hung += 1
        dec, vet = decisive_flags(seats, need)
        for i in range(n):
            nondummy[i] += dec[i]
            veto[i] += vet[i]
        for k, c in enumerate(candidates):
            cs = sum(seats[i] for i in c)
            if cs >= need:
                cand_win[k] += 1
                if all(cs - seats[i] < need for i in c):
                    cand_min[k] += 1
    pct = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(p * len(xs)))]  # noqa: E731
    return {
        "seed": seed, "iterations": iterations, "seats_needed": need,
        "parties": [{
            "name": names[i], "mean_seats": seat_sum[i] / iterations, "p05_seats": pct(seat_all[i], 0.05), "p95_seats": pct(seat_all[i], 0.95),
            "p_largest": largest[i] / iterations, "p_single_party_majority": single_majority[i] / iterations,
            "p_decisive_in_some_coalition": nondummy[i] / iterations, "p_veto": veto[i] / iterations,
        } for i in range(n)],
        "p_no_single_party_majority": hung / iterations,
        "candidates": [{"parties": c, "p_winning": cand_win[k] / iterations, "p_minimal_winning": cand_min[k] / iterations} for k, c in enumerate(candidates)],
        "note": "Scenario arithmetic on entered vote shares with seeded noise; not a forecast.",
    }


# ================================================================== policy trade-offs (multi-criteria)
def policy_analysis(alts: list[str], criteria: list[dict], scores: list[list[Any]], seed: int = 0, samples: int = 5000) -> dict:
    A, K = len(alts), len(criteria)
    if not 2 <= A <= MAX_ALTS or not 2 <= K <= MAX_CRITERIA:
        raise PoliticsError(f"need 2 to {MAX_ALTS} alternatives and 2 to {MAX_CRITERIA} criteria")
    if len(set(alts)) != A or len({c["name"] for c in criteria}) != K:
        raise PoliticsError("alternative and criterion names must be unique")
    if len(scores) != A or any(len(r) != K for r in scores):
        raise PoliticsError("score table shape must match alternatives and criteria")
    if not 100 <= samples <= 20000:
        raise PoliticsError("samples must be between 100 and 20000")
    w = [_frac(c["weight"], "weight") for c in criteria]
    if any(x < 0 for x in w) or sum(w) <= 0:
        raise PoliticsError("weights must be non-negative with a positive total")
    for c in criteria:
        if c["direction"] not in ("benefit", "cost"):
            raise PoliticsError("direction must be 'benefit' or 'cost'")
    raw = [[_frac(x, "score") for x in r] for r in scores]
    W = sum(w)
    wn = [x / W for x in w]
    norm: list[list[Fraction]] = [[Fraction(0)] * K for _ in range(A)]
    for k in range(K):
        col = [raw[a][k] for a in range(A)]
        lo, hi = min(col), max(col)
        for a in range(A):
            if hi == lo:
                norm[a][k] = Fraction(1, 2)
            elif criteria[k]["direction"] == "benefit":
                norm[a][k] = (raw[a][k] - lo) / (hi - lo)
            else:
                norm[a][k] = (hi - raw[a][k]) / (hi - lo)
    total = [sum(wn[k] * norm[a][k] for k in range(K)) for a in range(A)]
    order = sorted(range(A), key=lambda a: (-total[a], a))
    rank = {a: r + 1 for r, a in enumerate(order)}

    def dominated(a: int) -> bool:
        return any(all(norm[b][k] >= norm[a][k] for k in range(K)) and any(norm[b][k] > norm[a][k] for k in range(K)) for b in range(A) if b != a)

    pareto = [a for a in range(A) if not dominated(a)]

    # exact one-at-a-time weight sensitivity: criterion k gets weight t, the others share 1-t in their current proportions
    sens = []
    for k in range(K):
        others = W - w[k]
        if others == 0:
            sens.append({"criterion": criteria[k]["name"], "current_weight": float(wn[k]), "segments": [], "stable_range": None,
                         "note": "All other weights are zero, so varying this weight changes nothing."})
            continue
        R = [sum(w[j] * norm[a][j] for j in range(K) if j != k) / others for a in range(A)]
        line = lambda a, t: t * norm[a][k] + (1 - t) * R[a]  # noqa: E731
        bps = {Fraction(0), Fraction(1)}
        for a in range(A):
            for b in range(a + 1, A):
                den = (norm[a][k] - norm[b][k]) - (R[a] - R[b])
                if den != 0:
                    t = (R[b] - R[a]) / den
                    if 0 < t < 1:
                        bps.add(t)
        pts = sorted(bps)
        segs = []
        for lo_t, hi_t in zip(pts, pts[1:]):
            mid = (lo_t + hi_t) / 2
            best = max(line(a, mid) for a in range(A))
            top = [a for a in range(A) if line(a, mid) == best]
            if segs and segs[-1]["_top"] == top:
                segs[-1]["to"] = float(hi_t)
                segs[-1]["_to"] = hi_t
            else:
                segs.append({"from": float(lo_t), "to": float(hi_t), "_top": top, "_from": lo_t, "_to": hi_t})
        cur = wn[k]
        stable = next(((s["_from"], s["_to"]) for s in segs if s["_from"] <= cur <= s["_to"]), None)
        sens.append({
            "criterion": criteria[k]["name"], "current_weight": float(cur),
            "segments": [{"from": s["from"], "to": s["to"], "top": [alts[a] for a in s["_top"]]} for s in segs],
            "stable_range": None if stable is None else [float(stable[0]), float(stable[1])],
        })

    # rank acceptability: Dirichlet(1,...,1) random weights (seeded)
    rng = random.Random(seed)
    nf = [[float(x) for x in r] for r in norm]
    rank_counts = [[0] * A for _ in range(A)]
    for _ in range(samples):
        e = [-math.log(1.0 - rng.random()) for _ in range(K)]
        s = sum(e)
        ws = [x / s for x in e]
        sc = [sum(ws[k] * nf[a][k] for k in range(K)) for a in range(A)]
        for r, a in enumerate(sorted(range(A), key=lambda a: (-sc[a], a))):
            rank_counts[a][r] += 1
    return {
        "weights_normalised": [float(x) for x in wn],
        "alternatives": [{
            "name": alts[a], "normalised": [float(x) for x in norm[a]], "weighted_score": float(total[a]), "rank": rank[a],
            "pareto_optimal": a in pareto,
            "rank_probabilities": [c / samples for c in rank_counts[a]],
            "p_top": rank_counts[a][0] / samples, "expected_rank": sum((r + 1) * c for r, c in enumerate(rank_counts[a])) / samples,
        } for a in range(A)],
        "ranking": [alts[a] for a in order],
        "weight_sensitivity": sens, "seed": seed, "samples": samples,
        "notes": ["Scores are normalised 0–1 per criterion (min–max; cost criteria inverted). Weights express value judgements entered by the user, not facts."],
    }
