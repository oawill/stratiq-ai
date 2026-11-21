"""Gradient-boosted decision trees for football 1X2 outcomes, in pure Python (no numpy, no external ML library). Deterministic.

What it is: a multiclass (home / draw / away) boosted-tree model in the style of XGBoost's softmax objective: each round fits one
small regression tree per class to the gradient of the log loss, with a learning rate, an L2 penalty on leaf values, a minimum leaf
size and row/feature subsampling drawn from a seeded generator. Split search uses histograms over at most `BINS` quantile bins.

What it uses: only features computed from results played strictly BEFORE each fixture's date (`FormState`): the Elo rating gap, form,
goals scored and conceded, home-only and away-only form and rest days. It does not use injuries, odds, expected goals or squad data.
"""
from __future__ import annotations

import bisect
import math
import random
from collections import deque
from datetime import date

from .football_models import M, outcome

FEATURES = ["elo_gap", "ppg5_home", "ppg5_away", "gf10_home", "ga10_home", "gf10_away", "ga10_away", "venue_ppg_home", "venue_ppg_away",
            "rest_home", "rest_away", "form_diff", "goal_diff_form"]
BINS = 12
MIN_LEAF = 25
LAMBDA = 1.0
LEARNING_RATE = 0.08
DEFAULT = {"max_depth": 3, "max_rounds": 150, "subsample": 0.6, "colsample": 0.7, "seed": 7}
_PPG, _GOALS, _REST = 1.35, 1.4, 7.0      # neutral values for a club with no history yet (before any league average is known)


# ------------------------------------------------------------------ features (leak-free)
class FormState:
    """Rolling per-club results, updated one date at a time so a fixture never sees its own date's results."""

    def __init__(self) -> None:
        self.recent: dict[str, deque] = {}     # last 10 results, any venue: (gf, ga, points)
        self.home: dict[str, deque] = {}       # last 6 at home
        self.away: dict[str, deque] = {}       # last 6 away
        self.last: dict[str, date] = {}

    @staticmethod
    def _pts(gf: int, ga: int) -> int:
        return 3 if gf > ga else 1 if gf == ga else 0

    def update(self, m: M) -> None:
        d, h, a, hg, ag = m
        for team, gf, ga, venue in ((h, hg, ag, self.home), (a, ag, hg, self.away)):
            self.recent.setdefault(team, deque(maxlen=10)).append((gf, ga, self._pts(gf, ga)))
            venue.setdefault(team, deque(maxlen=6)).append((gf, ga, self._pts(gf, ga)))
            self.last[team] = d

    @staticmethod
    def _avg(rows, idx: int, n: int, default: float) -> float:
        rows = list(rows)[-n:] if rows else []
        return sum(r[idx] for r in rows) / len(rows) if rows else default

    def vector(self, home: str, away: str, on: date, elo_gap: float) -> list[float]:
        rh, ra = self.recent.get(home), self.recent.get(away)
        ppg_h, ppg_a = self._avg(rh, 2, 5, _PPG), self._avg(ra, 2, 5, _PPG)
        gf_h, ga_h = self._avg(rh, 0, 10, _GOALS), self._avg(rh, 1, 10, _GOALS)
        gf_a, ga_a = self._avg(ra, 0, 10, _GOALS), self._avg(ra, 1, 10, _GOALS)
        rest = lambda t: min(14.0, float((on - self.last[t]).days)) if t in self.last else _REST
        return [elo_gap, ppg_h, ppg_a, gf_h, ga_h, gf_a, ga_a, self._avg(self.home.get(home), 2, 6, _PPG), self._avg(self.away.get(away), 2, 6, _PPG),
                rest(home), rest(away), ppg_h - ppg_a, (gf_h - ga_h) - (gf_a - ga_a)]


def feature_rows(ms: list[M], pre: list[tuple[float, float]], home_adv: float) -> list[list[float]]:
    """One feature vector per match (in order). Matches sharing a date are all described from the state before that date."""
    st = FormState()
    out: list[list[float]] = []
    i, n = 0, len(ms)
    while i < n:
        j = i
        while j < n and ms[j][0] == ms[i][0]:
            m = ms[j]
            out.append(st.vector(m[1], m[2], m[0], pre[j][0] + home_adv - pre[j][1]))
            j += 1
        for k in range(i, j):
            st.update(ms[k])
        i = j
    return out


def live_vector(prior: list[M], home: str, away: str, on: date, elo_gap: float) -> list[float]:
    st = FormState()
    for m in prior:
        st.update(m)
    return st.vector(home, away, on, elo_gap)


# ------------------------------------------------------------------ boosted trees
def _softmax(scores: list[float]) -> list[float]:
    mx = max(scores)
    e = [math.exp(s - mx) for s in scores]
    t = sum(e)
    return [x / t for x in e]


def _edges(col: list[float]) -> list[float]:
    """Up to BINS-1 distinct split candidates from the quantiles of a feature column."""
    s = sorted(col)
    n = len(s)
    cand = sorted({s[min(n - 1, (n * k) // BINS)] for k in range(1, BINS)})
    return [c for c in cand if c > s[0]]


def _grow(rows: list[int], binned: list[list[int]], edges: list[list[float]], g: list[float], h: list[float], feats: list[int], depth: int, max_depth: int) -> list:
    """Return a tree as nested lists: leaf = [value]; split = [feature, threshold, left, right] (left when value < threshold)."""
    G = sum(g[i] for i in rows)
    H = sum(h[i] for i in rows)
    leaf = [-G / (H + LAMBDA) * LEARNING_RATE]
    if depth >= max_depth or len(rows) < 2 * MIN_LEAF:
        return leaf
    parent = G * G / (H + LAMBDA)
    best, best_gain = None, 1e-9
    for f in feats:
        nb = len(edges[f]) + 1
        if nb < 2:
            continue
        gh = [0.0] * nb
        hh = [0.0] * nb
        cc = [0] * nb
        col = binned[f]
        for i in rows:
            b = col[i]
            gh[b] += g[i]
            hh[b] += h[i]
            cc[b] += 1
        gl = hl = 0.0
        cl = 0
        for b in range(nb - 1):
            gl += gh[b]
            hl += hh[b]
            cl += cc[b]
            cr = len(rows) - cl
            if cl < MIN_LEAF or cr < MIN_LEAF:
                continue
            gain = gl * gl / (hl + LAMBDA) + (G - gl) ** 2 / (H - hl + LAMBDA) - parent
            if gain > best_gain:
                best, best_gain = (f, b), gain
    if best is None:
        return leaf
    f, b = best
    col = binned[f]
    left = [i for i in rows if col[i] <= b]
    right = [i for i in rows if col[i] > b]
    return [f, edges[f][b], _grow(left, binned, edges, g, h, feats, depth + 1, max_depth), _grow(right, binned, edges, g, h, feats, depth + 1, max_depth)]


def _tree_value(t: list, x: list[float]) -> float:
    while len(t) == 4:
        t = t[2] if x[t[0]] < t[1] else t[3]
    return t[0]


def _tree_gain_walk(t: list, imp: dict[int, int]) -> None:
    if len(t) == 4:
        imp[t[0]] = imp.get(t[0], 0) + 1
        _tree_gain_walk(t[2], imp)
        _tree_gain_walk(t[3], imp)


def raw_scores(model: dict, x: list[float], rounds: int | None = None) -> list[float]:
    s = list(model["base"])
    for r in model["trees"][: rounds if rounds is not None else len(model["trees"])]:
        for k in range(3):
            s[k] += _tree_value(r[k], x)
    return s


def predict(model: dict, x: list[float], rounds: int | None = None) -> list[float]:
    return _softmax(raw_scores(model, x, rounds))


def _log_loss(probs: list[float], y: int) -> float:
    return -math.log(max(probs[y], 1e-12))


def fit(X: list[list[float]], y: list[int], params: dict | None = None, X_val: list[list[float]] | None = None, y_val: list[int] | None = None) -> dict:
    """Train on (X, y). With validation rows, training stops adding rounds once validation log loss has not improved for 8 rounds and the
    model keeps its best round count (`rounds`). Returns a JSON-serialisable model."""
    p = {**DEFAULT, **(params or {})}
    n, nf = len(X), len(X[0])
    if n < 4 * MIN_LEAF:
        raise ValueError(f"At least {4 * MIN_LEAF} training matches are needed for the boosted-tree model; {n} were given.")
    rnd = random.Random(p["seed"])
    edges = [_edges([r[f] for r in X]) for f in range(nf)]
    binned = [[bisect.bisect_right(edges[f], r[f]) for r in X] for f in range(nf)]
    freq = [max(1e-6, sum(1 for v in y if v == k) / n) for k in range(3)]
    base = [math.log(q) for q in freq]
    model: dict = {"features": FEATURES, "base": base, "trees": [], "learning_rate": LEARNING_RATE, "params": {k: p[k] for k in ("max_depth", "max_rounds", "subsample", "colsample", "seed")}}
    F = [list(base) for _ in range(n)]
    Fv = [list(base) for _ in range(len(X_val))] if X_val else None
    best_ll, best_round, since = math.inf, 0, 0
    curve = []
    for r in range(p["max_rounds"]):
        probs = [_softmax(row) for row in F]
        rows = [i for i in range(n) if rnd.random() < p["subsample"]] or list(range(n))
        feats = sorted(rnd.sample(range(nf), max(2, round(nf * p["colsample"]))))
        trees = []
        for k in range(3):
            g = [pr[k] - (1.0 if y[i] == k else 0.0) for i, pr in enumerate(probs)]
            h = [max(pr[k] * (1 - pr[k]), 1e-6) for pr in probs]
            trees.append(_grow(rows, binned, edges, g, h, feats, 0, p["max_depth"]))
        model["trees"].append(trees)
        for i in range(n):
            x = X[i]
            for k in range(3):
                F[i][k] += _tree_value(trees[k], x)
        if Fv is not None:
            for i, x in enumerate(X_val):
                for k in range(3):
                    Fv[i][k] += _tree_value(trees[k], x)
            ll = sum(_log_loss(_softmax(Fv[i]), y_val[i]) for i in range(len(X_val))) / len(X_val)
            curve.append(ll)
            if ll < best_ll - 1e-5:
                best_ll, best_round, since = ll, r + 1, 0
            else:
                since += 1
                if since >= 8:
                    break
    model["rounds"] = best_round if Fv is not None else len(model["trees"])
    model["rounds"] = max(1, model["rounds"])
    model["trees"] = model["trees"][: model["rounds"]]
    imp: dict[int, int] = {}
    for rd in model["trees"]:
        for t in rd:
            _tree_gain_walk(t, imp)
    total = sum(imp.values()) or 1
    model["importance"] = {FEATURES[f]: imp.get(f, 0) / total for f in sorted(imp, key=lambda f: -imp[f])}
    model["training_matches"] = n
    if curve:
        model["validation_curve"] = [round(v, 5) for v in curve]
    return model
