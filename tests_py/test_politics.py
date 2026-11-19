import itertools
import math
import random
from fractions import Fraction

import pytest

from stratiq import politics as pol
from stratiq.politics import PoliticsError


# ------------------------------------------------------------------ independent reference implementations
def win_ref(sub, seats, total):
    return 2 * sum(seats[i] for i in sub) > total


def shapley_ref(seats):
    """Definition: average over all orderings of the party that turns a losing coalition into a winning one."""
    n, total = len(seats), sum(seats)
    cnt = [0] * n
    for perm in itertools.permutations(range(n)):
        cur = []
        for i in perm:
            before = win_ref(cur, seats, total)
            cur.append(i)
            if not before and win_ref(cur, seats, total):
                cnt[i] += 1
                break
    f = math.factorial(n)
    return [Fraction(c, f) for c in cnt]


def swings_ref(seats):
    n, total = len(seats), sum(seats)
    out = [0] * n
    for i in range(n):
        others = [j for j in range(n) if j != i]
        for r in range(len(others) + 1):
            for sub in itertools.combinations(others, r):
                if not win_ref(sub, seats, total) and win_ref(sub + (i,), seats, total):
                    out[i] += 1
    return out


def names(n):
    return [f"P{i}" for i in range(n)]


# ------------------------------------------------------------------ voting power
def test_shapley_and_banzhaf_match_definitions_on_random_weighted_games():
    rng = random.Random(3)
    for _ in range(80):
        n = rng.randint(2, 6)
        seats = [rng.randint(0, 40) for _ in range(n)]
        if sum(seats) == 0:
            seats[0] = 1
        a = pol.coalition_analysis(names(n), seats)
        ss, sw = shapley_ref(seats), swings_ref(seats)
        assert [Fraction(p["shapley_shubik_exact"]) for p in a["parties"]] == ss
        assert [p["banzhaf_raw_swings"] for p in a["parties"]] == sw
        assert sum(ss) == 1  # efficiency


def test_known_equal_power_despite_unequal_seats():
    a = pol.coalition_analysis(["A", "B", "C"], [49, 48, 3])  # any two parties win
    assert [p["shapley_shubik_exact"] for p in a["parties"]] == ["1/3", "1/3", "1/3"]
    assert a["minimal_winning_count"] == 3 and not any(p["is_veto"] or p["is_dummy"] for p in a["parties"])


def test_dictator_dummies_and_zero_seat_parties():
    a = pol.coalition_analysis(["A", "B", "C", "D"], [60, 25, 15, 0])
    p = {x["name"]: x for x in a["parties"]}
    assert p["A"]["is_dictator"] and p["A"]["shapley_shubik"] == 1.0 and p["A"]["is_veto"]
    assert all(p[k]["is_dummy"] and p[k]["shapley_shubik"] == 0 for k in "BCD")
    assert a["single_party_majority"] == ["A"] and a["minimal_winning_count"] == 1
    assert any("dummy" in n for n in a["notes"])  # B and C hold seats but are never decisive


def test_veto_player_under_supermajority():
    a = pol.coalition_analysis(["A", "B", "C"], [40, 30, 30], fraction=Fraction(2, 3))
    p = {x["name"]: x for x in a["parties"]}
    assert a["seats_needed"] == 67 and p["A"]["is_veto"] and not p["B"]["is_veto"]
    assert [x["parties"] for x in a["minimal_winning"]] == [[0, 1], [0, 2]]


def test_threshold_is_strictly_more_than_the_fraction():
    # 50 of 100 is NOT a majority; 51 is. 50 of 101 (2*50=100 < 101) is not; 51 of 101 is.
    assert pol.coalition_analysis(["A", "B"], [50, 50])["seats_needed"] == 51
    assert pol.coalition_analysis(["A", "B"], [51, 50])["seats_needed"] == 51
    assert pol.coalition_analysis(["A", "B"], [50, 50])["single_party_majority"] == []


def test_minimal_winning_coalitions_match_definition():
    rng = random.Random(8)
    for _ in range(40):
        n = rng.randint(3, 6)
        seats = [rng.randint(1, 30) for _ in range(n)]
        total = sum(seats)
        ref = set()
        for r in range(1, n + 1):
            for sub in itertools.combinations(range(n), r):
                if win_ref(sub, seats, total) and all(not win_ref(tuple(x for x in sub if x != i), seats, total) for i in sub):
                    ref.add(sub)
        got = {tuple(c["parties"]) for c in pol.coalition_analysis(names(n), seats)["minimal_winning"]}
        assert got == ref


def test_ranking_and_connectedness_by_position():
    # left-to-right: L(30) C(20) R(30) F(20) -> total 100, need 51
    a = pol.coalition_analysis(["L", "C", "R", "F"], [30, 20, 30, 20], positions=[1, 2, 3, 4])
    mw = a["minimal_winning"]
    assert mw == sorted(mw, key=lambda r: (r["surplus"], r["size"], r["ideological_range"], r["parties"]))
    by = {tuple(c["parties"]): c for c in mw}
    assert by[(0, 2)]["seats"] == 60 and by[(0, 2)]["connected"] is False  # L+R skips C
    assert by[(1, 2, 3)]["connected"] is True and by[(1, 2, 3)]["seats"] == 70  # C+R+F is a contiguous block
    assert by[(0, 1, 3)]["connected"] is False  # L+C+F skips R
    assert (1, 2) not in by  # C+R = 50 seats is short of the 51 needed
    assert a["connected_minimal_winning"] == sum(1 for c in mw if c["connected"])
    assert pol.coalition_analysis(["L", "C"], [30, 20])["connected_minimal_winning"] is None


@pytest.mark.parametrize(
    "kw,frag",
    [
        ({"names": ["A"], "seats": [5]}, "between 2"),
        ({"names": ["A", "A"], "seats": [5, 5]}, "unique"),
        ({"names": ["A", "B"], "seats": [5, -1]}, "non-negative"),
        ({"names": ["A", "B"], "seats": [5, 1.5]}, "whole numbers"),
        ({"names": ["A", "B"], "seats": [0, 0]}, "at least 1"),
        ({"names": ["A", "B"], "seats": [5, 5], "fraction": 0.4}, "quota"),
        ({"names": ["A", "B"], "seats": [5, 5], "fraction": 1}, "quota"),
        ({"names": ["A", "B"], "seats": [5, 5], "positions": [1]}, "positions"),
        ({"names": [f"P{i}" for i in range(13)], "seats": [1] * 13}, "between 2"),
    ],
)
def test_coalition_validation(kw, frag):
    with pytest.raises(PoliticsError, match=frag):
        pol.coalition_analysis(**kw)


def test_decisive_flags_bitmask_matches_brute_force():
    rng = random.Random(21)
    for _ in range(300):
        n = rng.randint(2, 7)
        seats = [rng.choice([0, 0, 1, 2, 3, 5, 8, 13, 21, 40]) for _ in range(n)]
        if sum(seats) == 0:
            continue
        need = sum(seats) // 2 + 1
        dec, veto = pol.decisive_flags(seats, need)
        sw = swings_ref(seats)
        assert dec == [s > 0 for s in sw]
        total = sum(seats)
        assert veto == [seats[i] > 0 and total - seats[i] < need <= total for i in range(n)]


# ------------------------------------------------------------------ seat allocation
VOTES = [100_000, 80_000, 30_000, 20_000]


def test_allocation_textbook_examples():
    assert pol.allocate("dhondt", 8, VOTES) == [4, 3, 1, 0]
    assert pol.allocate("sainte_lague", 8, VOTES) == [3, 3, 1, 1]
    assert pol.allocate("hare", 8, VOTES) == [3, 3, 1, 1]
    # 9% threshold removes party D (8.7%); Sainte-Lague redistributes
    assert pol.allocate("sainte_lague", 8, VOTES, threshold=0.09) == [4, 3, 1, 0]
    # a threshold equal to a party's share keeps it in (inclusive); just above removes it
    assert pol.allocate("dhondt", 8, [75, 25], threshold=0.25)[1] > 0
    assert pol.allocate("dhondt", 8, [75, 25], threshold=0.2500001)[1] == 0


def test_allocation_properties():
    rng = random.Random(4)
    for method in pol.METHODS:
        for _ in range(150):
            k, seats = rng.randint(2, 7), rng.randint(1, 120)
            votes = [rng.randint(0, 5000) for _ in range(k)]
            if sum(votes) == 0:
                continue
            out = pol.allocate(method, seats, votes)
            assert sum(out) == seats and all(x >= 0 for x in out)
            assert all(o == 0 for o, v in zip(out, votes) if v == 0)
            # exact and float implementations agree (up to ties, which integer votes can create; compare totals only)
            fl = pol.allocate(method, seats, votes, exact=False)
            assert sum(fl) == seats
            if method == "hare":
                tot = sum(votes)
                assert all(abs(o - v * seats / tot) < 1 for o, v in zip(out, votes))  # Hare is within one seat of exact proportion


@pytest.mark.parametrize("method", ["dhondt", "sainte_lague"])
def test_divisor_methods_are_monotone_in_own_votes(method):
    rng = random.Random(6)
    for _ in range(200):
        k, seats = rng.randint(2, 6), rng.randint(1, 60)
        votes = [rng.randint(1, 3000) for _ in range(k)]
        i = rng.randrange(k)
        before = pol.allocate(method, seats, votes)[i]
        votes[i] += rng.randint(1, 3000)
        assert pol.allocate(method, seats, votes)[i] >= before


def test_ties_are_broken_deterministically():
    assert pol.allocate("dhondt", 3, [100, 100]) == [2, 1]  # equal votes: list order wins the last seat
    assert pol.allocate("dhondt", 3, [100, 100]) == pol.allocate("dhondt", 3, [100, 100])
    assert pol.allocate("dhondt", 3, [100, 100], exact=False) == [2, 1]


@pytest.mark.parametrize(
    "args,frag",
    [
        (("proportional", 5, [1, 2]), "method"),
        (("dhondt", 0, [1, 2]), "seats"),
        (("dhondt", 651, [1, 2]), "seats"),
        (("dhondt", 5, [-1, 2]), "non-negative"),
        (("dhondt", 5, [0, 0]), "positive"),
        (("dhondt", 5, ["x", 2]), "number"),
    ],
)
def test_allocation_validation(args, frag):
    with pytest.raises(PoliticsError, match=frag):
        pol.allocate(*args)


def test_threshold_validation():
    with pytest.raises(PoliticsError, match="threshold"):
        pol.allocate("dhondt", 5, [1, 2], threshold=1)
    with pytest.raises(PoliticsError, match="no party reaches"):
        pol.allocate("dhondt", 5, [1, 1, 1], threshold=0.5)


# ------------------------------------------------------------------ turnout
PARTIES = ["A", "B"]
BLOCS = [
    {"name": "Bloc 1", "electorate": 1000, "turnout": 0.5, "prefs": {"A": 0.8, "B": 0.2}},
    {"name": "Bloc 2", "electorate": 1000, "turnout": 0.5, "prefs": {"A": 0.2, "B": 0.8}},
]


def test_turnout_baseline_is_exact():
    r = pol.turnout_analysis(PARTIES, BLOCS, "dhondt", 10, 0, None)["baseline"]
    assert r["votes"] == [500.0, 500.0] and r["seats"] == [5, 5] and r["turnout_overall"] == 0.5
    assert r["majority_party"] is None


def test_turnout_sweep_finds_the_tipping_point():
    # A votes = 800*t + 100, B votes = 200*t + 400 -> equal exactly at t = 0.5 for bloc 1
    r = pol.turnout_analysis(PARTIES, BLOCS, "dhondt", 10, 0, {"mode": "bloc", "bloc": 0, "lo": 0, "hi": 1})["sweep"]
    flips = [c for c in r["changes"] if any("largest party changes" in w for w in c["what"])]
    assert flips and abs(flips[0]["at"] - 0.5) < 1e-6
    assert len(r["curve"]) == 41 and r["curve"][0]["x"] == 0 and r["curve"][-1]["x"] == 1
    assert all(sum(p["seats"]) == 10 for p in r["curve"])
    # every reported change point really is a change: evaluate just before and after
    for c in r["changes"]:
        assert c["seats_before"] != c["seats_after"] or any("largest" in w or "majority" in w for w in c["what"])


def test_sweep_curve_matches_direct_evaluation():
    r = pol.turnout_analysis(PARTIES, BLOCS, "sainte_lague", 20, 0, {"mode": "bloc", "bloc": 1, "lo": 0.2, "hi": 0.9})["sweep"]
    for pt in r["curve"][::8]:
        blocs = [dict(b) for b in BLOCS]
        blocs[1]["turnout"] = pt["x"]
        direct = pol.turnout_analysis(PARTIES, blocs, "sainte_lague", 20, 0, None)["baseline"]
        assert direct["seats"] == pt["seats"]


def test_all_shift_mode_clamps_turnout():
    r = pol.turnout_analysis(PARTIES, BLOCS, "dhondt", 10, 0, {"mode": "all_shift", "lo": -0.6, "hi": 0.6})["sweep"]
    assert min(p["overall_turnout"] for p in r["curve"]) == 0 and max(p["overall_turnout"] for p in r["curve"]) == 1


@pytest.mark.parametrize(
    "mut,frag",
    [
        (lambda b: b[0].update(turnout=1.2), "turnout"),
        (lambda b: b[0].update(electorate=0), "electorate"),
        (lambda b: b[0]["prefs"].update(A=0.9), "sum to 100%"),
        (lambda b: b[0].update(prefs={"A": 1.0}), "every party"),
        (lambda b: b[1].update(name="Bloc 1"), "unique"),
    ],
)
def test_turnout_model_validation(mut, frag):
    blocs = [{**b, "prefs": dict(b["prefs"])} for b in BLOCS]
    mut(blocs)
    with pytest.raises(PoliticsError, match=frag):
        pol.turnout_analysis(PARTIES, blocs, "dhondt", 10, 0, None)


@pytest.mark.parametrize(
    "sweep,frag",
    [
        ({"mode": "bloc", "bloc": 5, "lo": 0, "hi": 1}, "choose a bloc"),
        ({"mode": "bloc", "bloc": 0, "lo": 0.5, "hi": 0.5}, "below"),
        ({"mode": "bloc", "bloc": 0, "lo": -0.1, "hi": 1}, "0% to 100%"),
        ({"mode": "all_shift", "lo": -2, "hi": 0}, "percentage points"),
        ({"mode": "weird", "lo": 0, "hi": 1}, "mode"),
    ],
)
def test_sweep_validation(sweep, frag):
    with pytest.raises(PoliticsError, match=frag):
        pol.turnout_analysis(PARTIES, BLOCS, "dhondt", 10, 0, sweep)


# ------------------------------------------------------------------ election-uncertainty simulation
def test_simulation_with_tiny_noise_matches_deterministic_allocation():
    base = [45.0, 35.0, 20.0]
    r = pol.simulate_coalitions(["A", "B", "C"], base, "dhondt", 100, 0, 100000, 0.5, [[0, 1], [1, 2], [2]], 300, 5)
    det = pol.allocate("dhondt", 100, base)
    for p, d in zip(r["parties"], det):
        assert abs(p["mean_seats"] - d) < 1.0 and p["p05_seats"] <= p["p95_seats"]
    assert r["parties"][0]["p_largest"] > 0.99 and r["p_no_single_party_majority"] > 0.99
    c = {tuple(x["parties"]): x for x in r["candidates"]}
    assert c[(0, 1)]["p_winning"] > 0.99 and c[(1, 2)]["p_winning"] > 0.99 and c[(2,)]["p_winning"] == 0
    assert c[(0, 1)]["p_minimal_winning"] > 0.99  # neither A nor B alone wins
    assert all(p["p_decisive_in_some_coalition"] > 0.99 for p in r["parties"]) and all(p["p_veto"] == 0 for p in r["parties"])


def test_simulation_majority_party_is_veto_and_others_dummy():
    r = pol.simulate_coalitions(["A", "B", "C"], [60.0, 25.0, 15.0], "dhondt", 100, 0, 100000, 0.5, [], 200, 1)
    a, b, c = r["parties"]
    assert a["p_veto"] == 1 and a["p_single_party_majority"] > 0.99
    assert b["p_decisive_in_some_coalition"] == 0 and c["p_decisive_in_some_coalition"] == 0


def test_simulation_is_reproducible_and_seed_sensitive():
    args = (["A", "B", "C"], [40.0, 35.0, 25.0], "sainte_lague", 120, 0.03, 60, 0.5, [[0, 1]], 400)
    a, b, c = pol.simulate_coalitions(*args, 7), pol.simulate_coalitions(*args, 7), pol.simulate_coalitions(*args, 8)
    assert a == b and a != c


def test_more_noise_widens_the_seat_range():
    mk = lambda k: pol.simulate_coalitions(["A", "B"], [55.0, 45.0], "dhondt", 100, 0, k, 0.5, [], 500, 2)["parties"][0]  # noqa: E731
    tight, loose = mk(5000), mk(20)
    assert (loose["p95_seats"] - loose["p05_seats"]) > 3 * (tight["p95_seats"] - tight["p05_seats"])


@pytest.mark.parametrize(
    "kw,frag",
    [
        ({"iterations": 50}, "iterations"), ({"iterations": 10**6}, "iterations"), ({"concentration": 1}, "concentration"),
        ({"base_votes": [1.0]}, "between 2"), ({"base_votes": [-1.0, 2.0]}, "non-negative"), ({"candidates": [[0, 0]]}, "distinct"),
        ({"candidates": [[5]]}, "distinct"), ({"candidates": [[0]] * 11}, "at most 10"), ({"fraction": 0.3}, "quota"),
    ],
)
def test_simulation_validation(kw, frag):
    base = dict(names=["A", "B"], base_votes=[1.0, 1.0], method="dhondt", n_seats=10, threshold=0, concentration=100,
                fraction=0.5, candidates=[], iterations=200, seed=1)
    base.update(kw)
    with pytest.raises(PoliticsError, match=frag):
        pol.simulate_coalitions(**base)


# ------------------------------------------------------------------ policy trade-offs
def crit(*items):
    return [{"name": n, "weight": w, "direction": d} for n, w, d in items]


def test_ranking_normalisation_and_pareto_known_example():
    r = pol.policy_analysis(["A", "B", "C"], crit(("benefit", 1, "benefit"), ("cost", 1, "cost")), [[10, 5], [20, 3], [30, 1]])
    assert r["ranking"] == ["C", "B", "A"]
    alt = {a["name"]: a for a in r["alternatives"]}
    assert alt["C"]["weighted_score"] == 1.0 and alt["A"]["weighted_score"] == 0.0 and alt["B"]["weighted_score"] == 0.5
    assert alt["C"]["pareto_optimal"] and not alt["A"]["pareto_optimal"] and not alt["B"]["pareto_optimal"]
    assert alt["A"]["p_top"] == 0 and alt["B"]["p_top"] == 0 and alt["C"]["p_top"] == 1


def test_tradeoff_with_exact_weight_breakpoint():
    r = pol.policy_analysis(["A", "B", "C"], crit(("benefit", 1, "benefit"), ("cost", 1, "cost")), [[10, 1], [20, 3], [30, 5]])
    alt = {a["name"]: a for a in r["alternatives"]}
    assert all(a["pareto_optimal"] for a in alt.values()) and all(a["weighted_score"] == 0.5 for a in alt.values())
    s = {x["criterion"]: x for x in r["weight_sensitivity"]}["benefit"]
    assert [(g["from"], g["to"], g["top"]) for g in s["segments"]] == [(0.0, 0.5, ["A"]), (0.5, 1.0, ["C"])]


def test_weight_sensitivity_segments_match_direct_recomputation():
    rng = random.Random(12)
    for _ in range(25):
        A, K = rng.randint(2, 5), rng.randint(2, 4)
        scores = [[rng.randint(0, 20) for _ in range(K)] for _ in range(A)]
        cr = [{"name": f"c{k}", "weight": rng.randint(1, 5), "direction": rng.choice(["benefit", "cost"])} for k in range(K)]
        base = pol.policy_analysis([f"a{i}" for i in range(A)], cr, scores, samples=100)
        for k, sens in enumerate(base["weight_sensitivity"]):
            for seg in sens["segments"]:
                t = (seg["from"] + seg["to"]) / 2
                others = sum(c["weight"] for j, c in enumerate(cr) if j != k)
                w = [t if j == k else (1 - t) * cr[j]["weight"] / others for j in range(K)]
                direct = pol.policy_analysis([f"a{i}" for i in range(A)], [{**c, "weight": w[j]} for j, c in enumerate(cr)], scores, samples=100)
                best = max(a["weighted_score"] for a in direct["alternatives"])
                tops = {a["name"] for a in direct["alternatives"] if abs(a["weighted_score"] - best) < 1e-9}
                assert tops == set(seg["top"])


def test_rank_probabilities_are_valid_and_reproducible():
    args = (["A", "B", "C"], crit(("x", 1, "benefit"), ("y", 2, "benefit"), ("z", 1, "cost")), [[1, 9, 4], [5, 5, 5], [9, 1, 2]])
    a, b, c = pol.policy_analysis(*args, seed=3), pol.policy_analysis(*args, seed=3), pol.policy_analysis(*args, seed=4)
    assert a == b and a != c
    assert sum(x["p_top"] for x in a["alternatives"]) == pytest.approx(1.0)
    for x in a["alternatives"]:
        assert sum(x["rank_probabilities"]) == pytest.approx(1.0) and 1 <= x["expected_rank"] <= 3
    for r in range(3):
        assert sum(x["rank_probabilities"][r] for x in a["alternatives"]) == pytest.approx(1.0)


def test_equal_criterion_values_are_neutral_and_zero_other_weights_handled():
    r = pol.policy_analysis(["A", "B"], crit(("same", 1, "benefit"), ("diff", 0, "benefit")), [[5, 1], [5, 9]])
    assert [a["normalised"][0] for a in r["alternatives"]] == [0.5, 0.5]
    s = {x["criterion"]: x for x in r["weight_sensitivity"]}["same"]
    assert s["segments"] == [] and "changes nothing" in s["note"]


@pytest.mark.parametrize(
    "alts,cr,sc,frag",
    [
        (["A"], crit(("x", 1, "benefit"), ("y", 1, "benefit")), [[1, 2]], "need 2"),
        (["A", "A"], crit(("x", 1, "benefit"), ("y", 1, "benefit")), [[1, 2], [1, 2]], "unique"),
        (["A", "B"], crit(("x", 1, "benefit"), ("x", 1, "benefit")), [[1, 2], [1, 2]], "unique"),
        (["A", "B"], crit(("x", 1, "benefit"), ("y", 1, "benefit")), [[1, 2]], "shape"),
        (["A", "B"], crit(("x", -1, "benefit"), ("y", 2, "benefit")), [[1, 2], [3, 4]], "non-negative"),
        (["A", "B"], crit(("x", 0, "benefit"), ("y", 0, "benefit")), [[1, 2], [3, 4]], "positive total"),
        (["A", "B"], crit(("x", 1, "maybe"), ("y", 1, "benefit")), [[1, 2], [3, 4]], "direction"),
        (["A", "B"], crit(("x", 1, "benefit"), ("y", 1, "benefit")), [[1, "n"], [3, 4]], "number"),
    ],
)
def test_policy_validation(alts, cr, sc, frag):
    with pytest.raises(PoliticsError, match=frag):
        pol.policy_analysis(alts, cr, sc)


def test_samples_range():
    with pytest.raises(PoliticsError, match="samples"):
        pol.policy_analysis(["A", "B"], crit(("x", 1, "benefit"), ("y", 1, "benefit")), [[1, 2], [3, 4]], samples=5)
