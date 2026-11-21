"""Exact all-equilibria solver (support enumeration) for small two-player games."""
import random
from fractions import Fraction

import pytest

from stratiq import gametheory as gt


def game(payoffs, rows=None, cols=None):
    R, C = len(payoffs), len(payoffs[0])
    return gt.build_game(rows or [f"R{i}" for i in range(R)], cols or [f"C{j}" for j in range(C)], payoffs)


def is_nash_exact(g, e):
    """Independent check from the exact strings: no pure deviation improves either player's expected payoff."""
    x = [Fraction(v) for v in e["row_probs_exact"]]
    y = [Fraction(v) for v in e["col_probs_exact"]]
    assert sum(x) == 1 and sum(y) == 1 and min(x) >= 0 and min(y) >= 0
    row_pay = [sum(g.A[i][j] * y[j] for j in range(g.C)) for i in range(g.R)]
    col_pay = [sum(g.B[i][j] * x[i] for i in range(g.R)) for j in range(g.C)]
    v, u = sum(x[i] * row_pay[i] for i in range(g.R)), sum(y[j] * col_pay[j] for j in range(g.C))
    return max(row_pay) == v and max(col_pay) == u


def test_matching_pennies_has_only_the_fifty_fifty_mixed_equilibrium():
    g = game([[(1, -1), (-1, 1)], [(-1, 1), (1, -1)]])
    out = gt.mixed_equilibria(g)
    assert out["attempted"] and out["count"] == 1
    e = out["equilibria"][0]
    assert e["type"] == "mixed" and e["row_probs_exact"] == ["1/2", "1/2"] and e["col_probs_exact"] == ["1/2", "1/2"] and e["expected_payoffs"] == [0.0, 0.0]
    assert gt.pure_nash(g) == []


def test_battle_of_the_sexes_has_two_pure_and_one_mixed_equilibrium():
    g = game([[(2, 1), (0, 0)], [(0, 0), (1, 2)]])
    out = gt.mixed_equilibria(g)
    assert out["count"] == 3 and sorted(e["type"] for e in out["equilibria"]) == ["mixed", "pure", "pure"]
    mixed = next(e for e in out["equilibria"] if e["type"] == "mixed")
    assert mixed["row_probs_exact"] == ["2/3", "1/3"] and mixed["col_probs_exact"] == ["1/3", "2/3"]
    assert mixed["expected_payoffs"] == pytest.approx([2 / 3, 2 / 3])
    assert all(is_nash_exact(g, e) for e in out["equilibria"])


def test_prisoners_dilemma_has_one_pure_equilibrium_and_nothing_mixed():
    g = game([[(3, 3), (0, 5)], [(5, 0), (1, 1)]])
    out = gt.mixed_equilibria(g)
    assert out["count"] == 1 and out["equilibria"][0]["type"] == "pure" and out["equilibria"][0]["row_support"] == [1] and out["equilibria"][0]["col_support"] == [1]


def test_rock_paper_scissors_is_the_uniform_mix():
    g = game([[(0, 0), (-1, 1), (1, -1)], [(1, -1), (0, 0), (-1, 1)], [(-1, 1), (1, -1), (0, 0)]], ["Rock", "Paper", "Scissors"], ["Rock", "Paper", "Scissors"])
    out = gt.mixed_equilibria(g)
    assert out["count"] == 1 and out["equilibria"][0]["row_probs_exact"] == ["1/3"] * 3 and out["equilibria"][0]["col_probs_exact"] == ["1/3"] * 3


def test_a_three_by_three_coordination_game_has_seven_equilibria():
    g = game([[(1, 1) if i == j else (0, 0) for j in range(3)] for i in range(3)])
    out = gt.mixed_equilibria(g)
    assert out["count"] == 7                                           # 3 pure, 3 two-strategy mixes, 1 fully mixed: 2^3 - 1
    assert sorted(len(e["row_support"]) for e in out["equilibria"]) == [1, 1, 1, 2, 2, 2, 3]
    assert all(is_nash_exact(g, e) for e in out["equilibria"])


def test_every_returned_equilibrium_is_a_nash_equilibrium_and_every_pure_one_is_found():
    rnd = random.Random(11)
    for _ in range(60):
        R, C = rnd.randint(2, 4), rnd.randint(2, 4)
        g = game([[(rnd.randint(-5, 9), rnd.randint(-5, 9)) for _ in range(C)] for _ in range(R)])
        out = gt.mixed_equilibria(g)
        assert all(is_nash_exact(g, e) for e in out["equilibria"])
        pure = {(e["row_support"][0], e["col_support"][0]) for e in out["equilibria"] if e["type"] == "pure"}
        assert pure == set(gt.pure_nash(g))                              # agrees with the pure-strategy detector


def test_the_general_solver_agrees_with_the_two_by_two_formula():
    rnd = random.Random(5)
    checked = 0
    for _ in range(80):
        g = game([[(rnd.randint(-4, 8), rnd.randint(-4, 8)) for _ in range(2)] for _ in range(2)])
        formula = gt.mixed_2x2(g)
        found = [e for e in gt.mixed_equilibria(g)["equilibria"] if e["type"] == "mixed"]
        if formula is None:
            continue                                                  # the formula only covers a completely mixed 2x2 equilibrium; degenerate games are skipped
        assert len(found) == 1 and found[0]["row_probs_exact"] == formula["row_probs_exact"] and found[0]["col_probs_exact"] == formula["col_probs_exact"]
        checked += 1
    assert checked > 10


def test_large_games_are_not_attempted_and_say_so():
    big = gt.build_game([f"r{i}" for i in range(7)], [f"c{i}" for i in range(7)], [[[i % 3, j % 3] for j in range(7)] for i in range(7)])
    out = gt.mixed_equilibria(big)
    assert out["attempted"] is False and "up to 6 x 6" in out["reason"] and out["equilibria"] == []
    assert gt.analyse(big)["equilibria"]["attempted"] is False                    # analysis still works for the pure-strategy parts


def test_analysis_explains_each_equilibrium_and_states_its_assumptions():
    g = game([[(2, 1), (0, 0)], [(0, 0), (1, 2)]], ["Opera", "Football"], ["Opera", "Football"])
    a = gt.analyse(g)
    assert a["equilibria"]["count"] == 3 and len(a["equilibrium_explanations"]) == 3
    assert any("randomises" in t and "indifferent" in t for t in a["equilibrium_explanations"])
    assert any("best reply" in t for t in a["equilibrium_explanations"])
    assert "simultaneously" in a["assumptions"] and "not a recommendation" in a["assumptions"]
    assert a["mixed_2x2"]["row_probs_exact"] == ["2/3", "1/3"]                    # the earlier 2x2 field is unchanged
    assert "See the mixed equilibrium." not in " ".join(gt.analyse(game([[(3, 3), (0, 5)], [(5, 0), (1, 1)]]))["notes"])


def test_matching_pennies_analysis_points_to_the_mixed_equilibrium():
    a = gt.analyse(game([[(1, -1), (-1, 1)], [(-1, 1), (1, -1)]]))
    assert "No pure-strategy Nash equilibrium exists." in a["notes"][0] and "mixed equilibrium" in a["notes"][0]
