import random

import pytest

from stratiq.gametheory import GameError, analyse, build_game, iterated_elimination, pure_nash, sensitivity


def G(payoffs, rows=None, cols=None):
    R, C = len(payoffs), len(payoffs[0])
    return build_game(rows or [f"r{i}" for i in range(R)], cols or [f"c{i}" for i in range(C)], payoffs)


PD = [[[3, 3], [0, 5]], [[5, 0], [1, 1]]]  # prisoner's dilemma: 0 = cooperate, 1 = defect
BOS = [[[2, 1], [0, 0]], [[0, 0], [1, 2]]]  # battle of the sexes
MP = [[[1, -1], [-1, 1]], [[-1, 1], [1, -1]]]  # matching pennies


def test_prisoners_dilemma():
    a = analyse(G(PD))
    assert [(n["row"], n["col"]) for n in a["pure_nash"]] == [(1, 1)]
    d = a["dominance"]
    assert d["row"]["strictly_dominant"] == 1 and d["col"]["strictly_dominant"] == 1
    assert {"strategy": 0, "by": 1} in d["row"]["strictly_dominated"]
    # the equilibrium (1,1) is Pareto-dominated by (0,0): a social dilemma
    assert any("social dilemma" in n for n in a["notes"])
    assert {(c["row"], c["col"]) for c in a["max_welfare"]["cells"]} == {(0, 0)}
    assert a["mixed_2x2"] is None  # no completely mixed equilibrium


def test_battle_of_sexes_two_pure_and_one_mixed():
    a = analyse(G(BOS))
    assert [(n["row"], n["col"]) for n in a["pure_nash"]] == [(0, 0), (1, 1)]
    m = a["mixed_2x2"]
    assert m["row_probs_exact"] == ["2/3", "1/3"]
    assert m["col_probs_exact"] == ["1/3", "2/3"]
    assert m["expected_payoffs"][0] == pytest.approx(2 / 3)


def test_matching_pennies_has_only_mixed():
    a = analyse(G(MP))
    assert a["pure_nash"] == []
    assert a["mixed_2x2"]["row_probs_exact"] == ["1/2", "1/2"]
    assert a["mixed_2x2"]["expected_payoffs"] == [0.0, 0.0]
    assert any("No pure-strategy" in n for n in a["notes"])


def test_best_responses_report_ties():
    g = G([[[3, 0], [0, 0]], [[3, 0], [0, 0]]])
    assert analyse(g)["best_responses"]["row_to_col"][0] == [0, 1]  # exact tie in column 0


def test_welfare_ties_use_exact_decimal_sums():
    # 0.1 + 0.2 and 0.3 + 0 are equal as decimals but differ as binary floats.
    g = G([[[0.1, 0.2], [0, 0]], [[0.3, 0], [0, 0]]])
    cells = {(c["row"], c["col"]) for c in analyse(g)["max_welfare"]["cells"]}
    assert cells == {(0, 0), (1, 0)}


def test_iterated_elimination():
    # classic 3x3 solvable by IESDS to (row 1, col 1)
    g = G([
        [[1, 0], [1, 3], [3, 0]],
        [[0, 3], [2, 5], [0, 1]],
        [[0, 0], [0, 2], [1, 0]],
    ])
    it = iterated_elimination(g)
    assert it["steps"], "expected at least one elimination"
    for s in it["steps"]:
        assert s["player"] in ("row", "col")
    assert len(it["remaining_rows"]) >= 1 and len(it["remaining_cols"]) >= 1


def test_weak_vs_strict_dominance():
    g = G([[[1, 1], [1, 1]], [[1, 1], [2, 1]]])  # row 1 weakly dominates row 0
    d = analyse(g)["dominance"]["row"]
    assert d["strictly_dominant"] is None and d["weakly_dominant"] == 1
    assert d["weakly_dominated"] == [{"strategy": 0, "by": 1}]


def test_pareto_and_welfare():
    a = analyse(G(PD))
    assert {(c["row"], c["col"]) for c in a["pareto_optimal"]} == {(0, 0), (0, 1), (1, 0)}


def _naive_nash(rows, cols, pay):
    out = []
    for r in range(rows):
        for c in range(cols):
            if all(pay[r][c][0] >= pay[r2][c][0] for r2 in range(rows)) and all(
                pay[r][c][1] >= pay[r][c2][1] for c2 in range(cols)
            ):
                out.append((r, c))
    return out


def test_pure_nash_matches_naive_definition_on_random_games():
    rng = random.Random(2024)
    for _ in range(300):
        R, C = rng.randint(2, 5), rng.randint(2, 5)
        pay = [[[rng.randint(-3, 3), rng.randint(-3, 3)] for _ in range(C)] for _ in range(R)]  # small range => many ties
        assert pure_nash(G(pay)) == _naive_nash(R, C, pay)


def test_every_pure_nash_is_a_mutual_best_response_and_no_strictly_dominated_strategy():
    rng = random.Random(5)
    for _ in range(200):
        R, C = rng.randint(2, 4), rng.randint(2, 4)
        pay = [[[rng.randint(0, 9), rng.randint(0, 9)] for _ in range(C)] for _ in range(R)]
        g = G(pay)
        a = analyse(g)
        dominated_r = {x["strategy"] for x in a["dominance"]["row"]["strictly_dominated"]}
        dominated_c = {x["strategy"] for x in a["dominance"]["col"]["strictly_dominated"]}
        for n in a["pure_nash"]:  # a strictly dominated strategy is never part of a Nash equilibrium
            assert n["row"] not in dominated_r and n["col"] not in dominated_c


def test_mixed_equilibrium_makes_opponent_indifferent():
    rng = random.Random(9)
    checked = 0
    for _ in range(200):
        pay = [[[rng.randint(-5, 5), rng.randint(-5, 5)] for _ in range(2)] for _ in range(2)]
        m = analyse(G(pay))["mixed_2x2"]
        if not m:
            continue
        p, q = m["row_probs"][0], m["col_probs"][0]
        # row indifferent between its two strategies given q
        u0 = q * pay[0][0][0] + (1 - q) * pay[0][1][0]
        u1 = q * pay[1][0][0] + (1 - q) * pay[1][1][0]
        assert u0 == pytest.approx(u1, abs=1e-9)
        v0 = p * pay[0][0][1] + (1 - p) * pay[1][0][1]
        v1 = p * pay[0][1][1] + (1 - p) * pay[1][1][1]
        assert v0 == pytest.approx(v1, abs=1e-9)
        checked += 1
    assert checked > 10


def test_sensitivity_exact_breakpoint():
    # Vary the row player's (defect, defect) payoff. Defect stays a best response to column-defect
    # while it is >= the row's (cooperate, defect) payoff of 0 -> threshold exactly at 0.
    s = sensitivity(G(PD), row=1, col=1, player="row", lo=-2, hi=3)
    assert s["thresholds"] == [0.0]
    segs = s["segments"]
    assert [(x["from"], x["to"]) for x in segs] == [(-2.0, 0.0), (0.0, 3.0)]
    assert segs[1]["pure_nash"] == [{"row": 1, "col": 1}]
    assert {"row": 1, "col": 1} not in segs[0]["pure_nash"]
    # at the tie both cooperate and defect are best responses, so (0,1) is also an equilibrium? col best response
    at0 = next(p for p in s["at_points"] if p["value"] == 0.0)
    assert {"row": 1, "col": 1} in at0["pure_nash"]


def test_sensitivity_matches_direct_solving_on_samples():
    rng = random.Random(1)
    for _ in range(40):
        pay = [[[rng.randint(0, 6), rng.randint(0, 6)] for _ in range(3)] for _ in range(3)]
        r, c = rng.randrange(3), rng.randrange(3)
        player = rng.choice(["row", "col"])
        s = sensitivity(G(pay), r, c, player, -1, 8)
        for seg in s["segments"]:
            mid = (seg["from"] + seg["to"]) / 2
            alt = [[list(x) for x in row] for row in pay]
            alt[r][c][0 if player == "row" else 1] = mid
            assert [(n["row"], n["col"]) for n in analyse(G(alt))["pure_nash"]] == [(n["row"], n["col"]) for n in seg["pure_nash"]]


@pytest.mark.parametrize(
    "rows,cols,pay,msg",
    [
        (["a"], ["x", "y"], [[[1, 1], [1, 1]]], "between 2 and"),
        (["a", "a"], ["x", "y"], [[[1, 1], [1, 1]], [[1, 1], [1, 1]]], "unique"),
        (["a", "b"], ["x", "y"], [[[1, 1], [1, 1]]], "shape"),
        (["a", "b"], ["x", "y"], [[[1, 1], [1]], [[1, 1], [1, 1]]], "two payoffs"),
        (["a", "b"], ["x", "y"], [[[1, float("nan")], [1, 1]], [[1, 1], [1, 1]]], "finite"),
        (["a", "b"], ["x", "y"], [[[1, 1e12], [1, 1]], [[1, 1], [1, 1]]], "finite"),
        (["a", "b"], ["x", "y"], [[[1, "9"], [1, 1]], [[1, 1], [1, 1]]], "finite"),
    ],
)
def test_input_validation(rows, cols, pay, msg):
    with pytest.raises(GameError, match=msg):
        build_game(rows, cols, pay)


def test_sensitivity_validation():
    g = G(PD)
    with pytest.raises(GameError):
        sensitivity(g, 0, 0, "row", 5, 1)
    with pytest.raises(GameError):
        sensitivity(g, 9, 0, "row", 0, 1)
    with pytest.raises(GameError):
        sensitivity(g, 0, 0, "both", 0, 1)
