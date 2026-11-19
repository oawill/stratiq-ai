"""Deterministic two-player normal-form game solver. Exact rational arithmetic; no randomness, no AI.

A game is payoffs[r][c] = (row_player_payoff, col_player_payoff).
All arithmetic uses fractions.Fraction built from the decimal text of each input, so sums,
ties and mixed-strategy probabilities are exact (e.g. 0.1 + 0.2 equals 0.3 as decimals).
Values arriving as binary floats are interpreted by their shortest decimal representation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

MAX_STRATEGIES = 8
MAX_ABS = 1e9


class GameError(ValueError):
    pass


def _frac(x: float | int | str) -> Fraction:
    if isinstance(x, bool):
        raise GameError("payoffs must be numbers")
    try:
        f = Fraction(Decimal(str(x)))
    except Exception as e:  # noqa: BLE001
        raise GameError("payoffs must be numbers") from e
    return f


@dataclass(frozen=True)
class Game:
    rows: list[str]
    cols: list[str]
    A: list[list[Fraction]]  # row player's payoffs
    B: list[list[Fraction]]  # column player's payoffs

    @property
    def R(self) -> int:
        return len(self.rows)

    @property
    def C(self) -> int:
        return len(self.cols)


def build_game(rows: list[str], cols: list[str], payoffs: list[list[list[float]]]) -> Game:
    R, C = len(rows), len(cols)
    if not (2 <= R <= MAX_STRATEGIES and 2 <= C <= MAX_STRATEGIES):
        raise GameError(f"each player needs between 2 and {MAX_STRATEGIES} strategies")
    if len(set(rows)) != R or len(set(cols)) != C:
        raise GameError("strategy names must be unique within a player")
    if len(payoffs) != R or any(len(r) != C for r in payoffs):
        raise GameError("payoff matrix shape must match the strategies")
    A, B = [], []
    for r in range(R):
        ra, rb = [], []
        for c in range(C):
            cell = payoffs[r][c]
            if len(cell) != 2:
                raise GameError("each cell needs exactly two payoffs")
            for v in cell:
                if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > MAX_ABS:
                    raise GameError(f"payoffs must be finite numbers with magnitude at most {MAX_ABS:g}")
            ra.append(_frac(cell[0]))
            rb.append(_frac(cell[1]))
        A.append(ra)
        B.append(rb)
    return Game(list(rows), list(cols), A, B)


def _f(x: Fraction) -> float:
    return float(x)


# ------------------------------------------------------------------ best responses & Nash
def row_best_responses(g: Game) -> list[list[int]]:
    """For each column c: the row strategies that maximise the row player's payoff."""
    out = []
    for c in range(g.C):
        m = max(g.A[r][c] for r in range(g.R))
        out.append([r for r in range(g.R) if g.A[r][c] == m])
    return out


def col_best_responses(g: Game) -> list[list[int]]:
    """For each row r: the column strategies that maximise the column player's payoff."""
    out = []
    for r in range(g.R):
        m = max(g.B[r][c] for c in range(g.C))
        out.append([c for c in range(g.C) if g.B[r][c] == m])
    return out


def pure_nash(g: Game) -> list[tuple[int, int]]:
    rb, cb = row_best_responses(g), col_best_responses(g)
    return [(r, c) for r in range(g.R) for c in range(g.C) if r in rb[c] and c in cb[r]]


# ------------------------------------------------------------------ dominance
def _dominates(vals_i: list[Fraction], vals_k: list[Fraction], strict: bool) -> bool:
    if strict:
        return all(a > b for a, b in zip(vals_i, vals_k))
    return all(a >= b for a, b in zip(vals_i, vals_k)) and any(a > b for a, b in zip(vals_i, vals_k))


def _row_vec(g: Game, r: int, cols: list[int]) -> list[Fraction]:
    return [g.A[r][c] for c in cols]


def _col_vec(g: Game, c: int, rows: list[int]) -> list[Fraction]:
    return [g.B[r][c] for r in rows]


def dominance(g: Game) -> dict:
    def analyse(n: int, vec, names: list[str]) -> dict:
        strict_dom, weak_dom = None, None
        strictly_dominated, weakly_dominated = [], []
        for i in range(n):
            if all(_dominates(vec(i), vec(k), True) for k in range(n) if k != i):
                strict_dom = i
            if all(_dominates(vec(i), vec(k), False) for k in range(n) if k != i):
                weak_dom = i
        for k in range(n):
            for i in range(n):
                if i == k:
                    continue
                if _dominates(vec(i), vec(k), True):
                    strictly_dominated.append({"strategy": k, "by": i})
                    break
            else:
                for i in range(n):
                    if i != k and _dominates(vec(i), vec(k), False):
                        weakly_dominated.append({"strategy": k, "by": i})
                        break
        return {
            "strictly_dominant": strict_dom,
            "weakly_dominant": weak_dom if strict_dom is None else None,
            "strictly_dominated": strictly_dominated,
            "weakly_dominated": weakly_dominated,
        }

    allc, allr = list(range(g.C)), list(range(g.R))
    return {
        "row": analyse(g.R, lambda r: _row_vec(g, r, allc), g.rows),
        "col": analyse(g.C, lambda c: _col_vec(g, c, allr), g.cols),
    }


def iterated_elimination(g: Game) -> dict:
    """Iterated elimination of strictly dominated pure strategies."""
    rows, cols = list(range(g.R)), list(range(g.C))
    steps: list[dict] = []
    changed = True
    while changed:
        changed = False
        for r in list(rows):
            if len(rows) <= 1:
                break
            for i in rows:
                if i != r and _dominates(_row_vec(g, i, cols), _row_vec(g, r, cols), True):
                    rows.remove(r)
                    steps.append({"player": "row", "eliminated": r, "by": i})
                    changed = True
                    break
        for c in list(cols):
            if len(cols) <= 1:
                break
            for j in cols:
                if j != c and _dominates(_col_vec(g, j, rows), _col_vec(g, c, rows), True):
                    cols.remove(c)
                    steps.append({"player": "col", "eliminated": c, "by": j})
                    changed = True
                    break
    return {"steps": steps, "remaining_rows": rows, "remaining_cols": cols}


# ------------------------------------------------------------------ mixed (2x2 only)
def mixed_2x2(g: Game) -> dict | None:
    """The completely mixed equilibrium of a 2x2 game, if one exists."""
    if g.R != 2 or g.C != 2:
        return None
    A, B = g.A, g.B
    dq = A[0][0] - A[0][1] - A[1][0] + A[1][1]
    dp = B[0][0] - B[1][0] - B[0][1] + B[1][1]
    if dq == 0 or dp == 0:
        return None
    q = (A[1][1] - A[0][1]) / dq  # P(column plays strategy 0)
    p = (B[1][1] - B[1][0]) / dp  # P(row plays strategy 0)
    if not (0 < p < 1 and 0 < q < 1):
        return None
    row_pay = q * A[0][0] + (1 - q) * A[0][1]
    col_pay = p * B[0][0] + (1 - p) * B[1][0]
    return {
        "row_probs": [_f(p), _f(1 - p)],
        "col_probs": [_f(q), _f(1 - q)],
        "row_probs_exact": [str(p), str(1 - p)],
        "col_probs_exact": [str(q), str(1 - q)],
        "expected_payoffs": [_f(row_pay), _f(col_pay)],
    }


# ------------------------------------------------------------------ welfare
def welfare(g: Game) -> dict:
    cells = [(r, c) for r in range(g.R) for c in range(g.C)]
    pareto = []
    for r, c in cells:
        a, b = g.A[r][c], g.B[r][c]
        dominated = any(
            (g.A[r2][c2] >= a and g.B[r2][c2] >= b) and (g.A[r2][c2] > a or g.B[r2][c2] > b)
            for r2, c2 in cells
            if (r2, c2) != (r, c)
        )
        if not dominated:
            pareto.append((r, c))
    best = max(g.A[r][c] + g.B[r][c] for r, c in cells)
    return {
        "pareto_optimal": [{"row": r, "col": c} for r, c in pareto],
        "max_welfare": {"value": _f(best), "cells": [{"row": r, "col": c} for r, c in cells if g.A[r][c] + g.B[r][c] == best]},
    }


# ------------------------------------------------------------------ top-level analysis
def analyse(g: Game) -> dict:
    nash = pure_nash(g)
    w = welfare(g)
    notes = []
    if not nash:
        notes.append("No pure-strategy Nash equilibrium exists." + (" See the mixed equilibrium." if mixed_2x2(g) else ""))
    nash_cells = [{"row": r, "col": c, "payoffs": [_f(g.A[r][c]), _f(g.B[r][c])]} for r, c in nash]
    nash_set = {(r, c) for r, c in nash}
    pareto_set = {(x["row"], x["col"]) for x in w["pareto_optimal"]}
    if nash and all(cell not in pareto_set for cell in nash_set):
        notes.append("Every pure equilibrium is Pareto-dominated: both players could do better at another outcome (a social dilemma).")
    return {
        "pure_nash": nash_cells,
        "best_responses": {"row_to_col": row_best_responses(g), "col_to_row": col_best_responses(g)},
        "dominance": dominance(g),
        "iterated_elimination": iterated_elimination(g),
        "mixed_2x2": mixed_2x2(g),
        **w,
        "notes": notes,
    }


# ------------------------------------------------------------------ sensitivity (exact, piecewise)
def sensitivity(g: Game, row: int, col: int, player: str, lo: float, hi: float) -> dict:
    """Vary one payoff over [lo, hi] and report exactly how the pure-Nash set changes.

    The equilibrium set only changes where the varied payoff ties with another payoff it is
    compared against (same column for the row player, same row for the column player), so the
    result is exact: test every threshold and the midpoint between thresholds.
    """
    if player not in ("row", "col"):
        raise GameError("player must be 'row' or 'col'")
    if not (0 <= row < g.R and 0 <= col < g.C):
        raise GameError("cell is out of range")
    if not (math.isfinite(lo) and math.isfinite(hi)) or lo >= hi:
        raise GameError("range must satisfy lo < hi")
    L, H = _frac(lo), _frac(hi)
    if player == "row":
        others = [g.A[r][col] for r in range(g.R) if r != row]
    else:
        others = [g.B[row][c] for c in range(g.C) if c != col]
    thresholds = sorted({t for t in others if L < t < H})
    points = [L] + thresholds + [H]
    def ne_at(v: Fraction):
        return tuple(pure_nash(_with_payoff(g, row, col, player, v)))

    pack = lambda ne: [{"row": r, "col": c} for r, c in ne]  # noqa: E731
    at_points = [{"value": _f(p), "pure_nash": pack(ne_at(p))} for p in points]
    segments: list[dict] = []
    for lo_v, hi_v in zip(points, points[1:]):
        ne = ne_at((lo_v + hi_v) / 2)
        if segments and segments[-1]["_ne"] == ne:
            segments[-1]["to"] = _f(hi_v)
        else:
            segments.append({"from": _f(lo_v), "to": _f(hi_v), "_ne": ne})
    for seg in segments:
        seg["pure_nash"] = pack(seg.pop("_ne"))
    return {
        "player": player,
        "cell": {"row": row, "col": col},
        "range": [lo, hi],
        "thresholds": [_f(t) for t in thresholds],
        "segments": segments,
        "at_points": at_points,
    }


def _with_payoff(g: Game, row: int, col: int, player: str, v: Fraction) -> Game:
    A = [r[:] for r in g.A]
    B = [r[:] for r in g.B]
    (A if player == "row" else B)[row][col] = v
    return Game(g.rows, g.cols, A, B)
