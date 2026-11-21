"""Parsing and validation of user-supplied CSV data. Pure functions: no database, no network.

Every parser returns a Parsed: `data` (normalized content that gets stored), `summary` (what the interface shows) and `warnings`.
Invalid input raises DataError carrying line-numbered messages, so people can fix their file instead of guessing.
Nothing is ever repaired or imputed silently: blank, non-numeric or impossible cells are rejected.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

KINDS = ("sports_results", "market_returns", "political_seats", "series")
MAX_CHARS = 2_000_000   # fits Vercel's 4.5 MB request limit with room to spare
MAX_ROWS = 20_000
MAX_COLS = 12
MAX_ERRORS = 20
MIN_OBS = 20


class DataError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors[:3]))
        self.errors = errors[:MAX_ERRORS]


@dataclass
class Parsed:
    kind: str
    data: dict
    summary: dict
    row_count: int
    warnings: list[str] = field(default_factory=list)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ------------------------------------------------------------------ generic CSV reading
def read_csv(text: str, max_cols: int = MAX_COLS) -> tuple[list[str], list[list[str]]]:
    """Header and rows (with blank lines dropped), after size and shape checks."""
    if not isinstance(text, str) or not text.strip():
        raise DataError(["The file is empty."])
    if len(text) > MAX_CHARS:
        raise DataError([f"The file is larger than {MAX_CHARS // 1_000_000} MB. Split it or remove columns you do not need."])
    text = text.lstrip("﻿")
    first = text.splitlines()[0]
    delim = "\t" if "\t" in first else ";" if first.count(";") > first.count(",") else ","
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    header, body = rows[0], rows[1:]
    if len(header) > max_cols:
        raise DataError([f"At most {max_cols} columns are supported; found {len(header)}."])
    if len(set(h.lower() for h in header)) != len(header):
        raise DataError(["Column names must be different from each other."])
    if len(body) > MAX_ROWS:
        raise DataError([f"At most {MAX_ROWS:,} data rows are supported; found {len(body):,}."])
    return header, body


class _Errors:
    def __init__(self):
        self.items: list[str] = []

    def add(self, line: int, msg: str):
        if len(self.items) < MAX_ERRORS:
            self.items.append(f"Line {line}: {msg}")

    def raise_if_any(self):
        if self.items:
            raise DataError(self.items)


def _columns(header: list[str], spec: dict[str, tuple[str, ...]], required: set[str]) -> dict[str, int]:
    """Map canonical column names to indexes using case-insensitive aliases; complain about missing required ones."""
    low = [h.lower() for h in header]
    out: dict[str, int] = {}
    for canon, aliases in spec.items():
        for a in aliases:
            if a in low:
                out[canon] = low.index(a)
                break
    missing = [c for c in required if c not in out]
    if missing:
        wanted = "; ".join(f"{c} (or {', '.join(spec[c][1:])})" if len(spec[c]) > 1 else c for c in missing)
        raise DataError([f"Missing column(s): {wanted}. Found: {', '.join(header)}."])
    return out


def _num(s: str) -> float:
    s = s.strip().rstrip("%").replace(" ", "")
    if s == "" or s.lower() in ("nan", "inf", "-inf", "infinity", "-infinity"):
        raise ValueError
    v = float(s)
    if not math.isfinite(v):
        raise ValueError
    return v


# ------------------------------------------------------------------ sports results
SPORTS_COLS = {"date": ("date", "kickoff", "match_date"), "home": ("home_team", "home", "hometeam"), "away": ("away_team", "away", "awayteam"),
               "hg": ("home_goals", "home_score", "fthg"), "ag": ("away_goals", "away_score", "ftag")}
SPORTS_MAX_COLS = 200  # results files from public archives carry many extra columns (odds, shots, cards); only five are used


def _match_date(s: str) -> tuple[date, bool]:
    """ISO dates, or day-first slash dates (DD/MM/YYYY or DD/MM/YY, as used by football-data.co.uk). Returns (date, was_slash)."""
    try:
        return date.fromisoformat(s), False
    except ValueError:
        pass
    parts = s.split("/")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        dd, mm, yy = int(parts[0]), int(parts[1]), int(parts[2])
        if len(parts[2]) == 2:
            yy += 1900 if yy >= 70 else 2000
        if len(parts[2]) in (2, 4):
            return date(yy, mm, dd), True
    raise ValueError(s)


def parse_sports(text: str) -> Parsed:
    header, body = read_csv(text, SPORTS_MAX_COLS)
    col = _columns(header, SPORTS_COLS, set(SPORTS_COLS))
    errs, matches, seen = _Errors(), [], set()
    warnings: list[str] = []
    slash_dates = False
    today = datetime.now(timezone.utc).date()
    for i, r in enumerate(body, start=2):
        if len(r) != len(header):
            errs.add(i, f"has {len(r)} values but the header has {len(header)} columns.")
            continue
        try:
            d, slash = _match_date(r[col["date"]])
            slash_dates = slash_dates or slash
        except ValueError:
            errs.add(i, f"date '{r[col['date']]}' is not in YYYY-MM-DD or DD/MM/YYYY format.")
            continue
        if d > today:
            errs.add(i, f"date {d} is in the future. Upload played matches only.")
            continue
        home, away = r[col["home"]], r[col["away"]]
        if not home or not away or len(home) > 60 or len(away) > 60:
            errs.add(i, "team names must be 1 to 60 characters.")
            continue
        if home.lower() == away.lower():
            errs.add(i, f"home and away are both '{home}'.")
            continue
        try:
            hg, ag = int(r[col["hg"]]), int(r[col["ag"]])
        except ValueError:
            errs.add(i, "goals must be whole numbers.")
            continue
        if not (0 <= hg <= 30 and 0 <= ag <= 30):
            errs.add(i, "goals must be between 0 and 30.")
            continue
        key = (d, home, away)
        if key in seen:
            warnings.append(f"Line {i}: {home} v {away} on {d} appears more than once.")
        seen.add(key)
        matches.append([d.isoformat(), home, away, hg, ag])
    errs.raise_if_any()
    if slash_dates:
        warnings.append("Dates written with slashes were read as day/month/year (for example 17/08/2024 is 17 August 2024). Check the date range below.")
    matches.sort(key=lambda m: (m[0], m[1], m[2]))
    counts: dict[str, int] = {}
    for _, h, a, _, _ in matches:
        counts[h] = counts.get(h, 0) + 1
        counts[a] = counts.get(a, 0) + 1
    if len(matches) < 30:
        raise DataError([f"Only {len(matches)} match(es) found. At least 30 are needed to fit team ratings."])
    if not 4 <= len(counts) <= 200:
        raise DataError([f"Found {len(counts)} team(s). Between 4 and 200 are supported."])
    thin = sorted(t for t, n in counts.items() if n < 5)
    if thin:
        warnings.append(f"{len(thin)} team(s) have fewer than 5 matches, so their ratings will be uncertain: {', '.join(thin[:8])}{'…' if len(thin) > 8 else ''}.")
    total = sum(m[3] + m[4] for m in matches)
    summary = {"matches": len(matches), "teams": len(counts), "first_date": matches[0][0], "last_date": matches[-1][0],
               "mean_goals_per_match": round(total / len(matches), 3), "team_matches": dict(sorted(counts.items()))}
    return Parsed("sports_results", {"matches": matches}, summary, len(matches), warnings)


# ------------------------------------------------------------------ market returns / generic series
DATE_NAMES = ("date", "time", "period", "month", "day", "year", "datetime")


def _split_date(header: list[str], body: list[list[str]]) -> tuple[int | None, list[int]]:
    # A first column called date/month/year/... is a date column only if its values are ISO dates. A column named "month"
    # holding 1, 2, 3 is ordinary data and must not be treated (and rejected) as a date.
    di = None
    if header[0].lower() in DATE_NAMES and body:
        try:
            date.fromisoformat(body[0][0])
            di = 0
        except (ValueError, IndexError):
            di = None
    return di, [i for i in range(len(header)) if i != di]


def _periods_per_year(dates: list[date]) -> int:
    gaps = sorted((b - a).days for a, b in zip(dates, dates[1:]))
    med = gaps[len(gaps) // 2]
    return 252 if med <= 4 else 52 if med <= 10 else 12 if med <= 40 else 4 if med <= 120 else 1


def _read_numeric_table(text: str, what: str, min_value: float | None):
    header, body = read_csv(text)
    di, vi = _split_date(header, body)
    names = [header[i] for i in vi]
    if not names:
        raise DataError(["Add at least one data column besides the date."])
    if any(not n or len(n) > 40 for n in names) or any(_is_number(n) for n in names):
        raise DataError(["The first row must hold column names (1 to 40 characters, not numbers)."])
    errs, dates, cols = _Errors(), [], {n: [] for n in names}
    for ln, r in enumerate(body, start=2):
        if len(r) != len(header):
            errs.add(ln, f"has {len(r)} values but the header has {len(header)} columns.")
            continue
        if di is not None:
            try:
                dates.append(date.fromisoformat(r[di]))
            except ValueError:
                errs.add(ln, f"date '{r[di]}' is not in YYYY-MM-DD format.")
                continue
        for i, n in zip(vi, names):
            try:
                v = _num(r[i])
            except ValueError:
                errs.add(ln, f"{what} '{r[i]}' in column '{n}' is blank or not a number.")
                continue
            if min_value is not None and v <= min_value:
                errs.add(ln, f"{what} {r[i]} in column '{n}' must be greater than {min_value:g}.")
                continue
            cols[n].append(v)
    errs.raise_if_any()
    if di is not None and any(b <= a for a, b in zip(dates, dates[1:])):
        raise DataError(["Dates must be strictly increasing (oldest first) with no repeats."])
    return names, dates, cols


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def parse_returns(text: str, values: str = "returns", unit: str = "percent") -> Parsed:
    """values: 'returns' (per-period) or 'prices' (converted to simple returns). unit applies to returns only."""
    if values not in ("returns", "prices") or unit not in ("percent", "decimal"):
        raise DataError(["values must be 'returns' or 'prices'; unit must be 'percent' or 'decimal'."])
    names, dates, cols = _read_numeric_table(text, "price" if values == "prices" else "return", 0.0 if values == "prices" else None)
    from . import finance as fin
    if len(names) > fin.MAX_ASSETS:
        raise DataError([f"At most {fin.MAX_ASSETS} assets are supported; found {len(names)}."])
    if values == "prices":
        rets = {n: [b / a - 1 for a, b in zip(v, v[1:])] for n, v in cols.items()}
        if dates:
            dates = dates[1:]
    else:
        div = 100.0 if unit == "percent" else 1.0
        rets = {n: [x / div for x in v] for n, v in cols.items()}
    n_obs = len(next(iter(rets.values())))
    if n_obs < MIN_OBS:
        raise DataError([f"Only {n_obs} return observation(s) found. At least {MIN_OBS} are needed."])
    bad = [n for n, v in rets.items() if any(x <= -1 for x in v)]
    if bad:
        raise DataError([f"Column(s) {', '.join(bad)} contain a return of -100% or worse, which is not possible."])
    ppy = _periods_per_year(dates) if dates else None
    warnings = [] if ppy else ["No date column, so the observation frequency is unknown. Set periods per year yourself when you analyze it."]
    per = ppy or 12
    stats = {n: {"mean_annual": round(statistics.fmean(v) * per, 6), "vol_annual": round(statistics.stdev(v) * math.sqrt(per), 6)} for n, v in rets.items()}
    data = {"names": names, "returns": {n: [round(x, 10) for x in v] for n, v in rets.items()}, "dates": [d.isoformat() for d in dates] if dates else None, "periods_per_year": ppy}
    summary = {"observations": n_obs, "assets": names, "periods_per_year": ppy, "first_date": dates[0].isoformat() if dates else None,
               "last_date": dates[-1].isoformat() if dates else None, "stats": stats, "converted_from_prices": values == "prices"}
    return Parsed("market_returns", data, summary, n_obs, warnings)


def parse_series(text: str) -> Parsed:
    names, dates, cols = _read_numeric_table(text, "value", None)
    n_obs = len(next(iter(cols.values())))
    if n_obs < MIN_OBS:
        raise DataError([f"Only {n_obs} row(s) found. At least {MIN_OBS} are needed to describe a distribution."])
    summary = {"observations": n_obs, "columns": {n: describe(v) for n, v in cols.items()}}
    data = {"names": names, "columns": {n: v for n, v in cols.items()}, "dates": [d.isoformat() for d in dates] if dates else None}
    return Parsed("series", data, summary, n_obs)


# ------------------------------------------------------------------ political seats
def parse_seats(text: str) -> Parsed:
    from . import politics as pol
    header, body = read_csv(text)
    col = _columns(header, {"party": ("party", "name"), "seats": ("seats", "seat"), "position": ("position",)}, {"party", "seats"})
    errs, parties, names = _Errors(), [], set()
    for ln, r in enumerate(body, start=2):
        if len(r) != len(header):
            errs.add(ln, f"has {len(r)} values but the header has {len(header)} columns.")
            continue
        name = r[col["party"]]
        if not name or len(name) > 40:
            errs.add(ln, "party names must be 1 to 40 characters.")
            continue
        if name.lower() in names:
            errs.add(ln, f"party '{name}' is listed twice.")
            continue
        names.add(name.lower())
        try:
            seats = int(r[col["seats"]])
        except ValueError:
            errs.add(ln, "seats must be a whole number.")
            continue
        if not 0 <= seats <= 100_000:
            errs.add(ln, "seats must be between 0 and 100,000.")
            continue
        p = {"name": name, "seats": seats}
        if "position" in col and r[col["position"]] != "":
            try:
                pos = _num(r[col["position"]])
            except ValueError:
                errs.add(ln, "position must be a number.")
                continue
            if not -1000 <= pos <= 1000:
                errs.add(ln, "position must be between -1000 and 1000.")
                continue
            p["position"] = pos
        parties.append(p)
    errs.raise_if_any()
    if not 2 <= len(parties) <= pol.MAX_PARTIES:
        raise DataError([f"Found {len(parties)} part(ies). Between 2 and {pol.MAX_PARTIES} are supported."])
    total = sum(p["seats"] for p in parties)
    if total <= 0:
        raise DataError(["Total seats must be greater than zero."])
    return Parsed("political_seats", {"parties": parties}, {"parties": len(parties), "total_seats": total}, len(parties))


# ------------------------------------------------------------------ descriptive statistics and distribution fitting
def _quantile(sorted_v: list[float], q: float) -> float:
    k = (len(sorted_v) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return sorted_v[lo] + (sorted_v[hi] - sorted_v[lo]) * (k - lo)


def describe(v: list[float]) -> dict:
    s = sorted(v)
    return {"n": len(v), "mean": round(statistics.fmean(v), 6), "sd": round(statistics.stdev(v), 6), "min": s[0], "p5": round(_quantile(s, 0.05), 6),
            "median": round(_quantile(s, 0.5), 6), "p95": round(_quantile(s, 0.95), 6), "max": s[-1]}


def fit_distribution(v: list[float], kind: str = "auto") -> dict:
    """A distribution definition SimLab accepts, fitted to the data by moments, plus how it was chosen and the sample statistics.
    'auto' uses lognormal for strictly positive, clearly right-skewed data and normal otherwise. Triangular uses min, median-ish mode, max."""
    if len(v) < MIN_OBS:
        raise DataError([f"At least {MIN_OBS} observations are needed to fit a distribution."])
    st = describe(v)
    mean, sd = st["mean"], st["sd"]
    if sd <= 0:
        raise DataError(["The values do not vary (zero spread), so there is nothing to fit. Use a constant instead."])
    skew = sum(((x - mean) / sd) ** 3 for x in v) / len(v)
    positive = st["min"] > 0
    chosen = kind
    reason = "chosen by you"
    if kind == "auto":
        chosen, reason = ("lognormal", f"all values are positive and the data is right-skewed (skewness {skew:.2f})") if positive and skew > 0.5 else \
            ("normal", f"the data is roughly symmetric (skewness {skew:.2f})" if abs(skew) <= 0.5 else f"normal used despite skewness {skew:.2f}, because lognormal needs strictly positive, right-skewed data")
    if chosen == "lognormal":
        if not positive:
            raise DataError(["Lognormal needs strictly positive values."])
        dist = {"type": "lognormal", "mean": round(mean, 6), "sd": round(sd, 6)}
    elif chosen == "normal":
        dist = {"type": "normal", "mean": round(mean, 6), "sd": round(sd, 6)}
    elif chosen == "triangular":
        lo, hi = st["min"], st["max"]
        if not lo < hi:
            raise DataError(["The values do not vary, so a triangular range cannot be fitted."])
        dist = {"type": "triangular", "low": lo, "mode": min(max(st["median"], lo), hi), "high": hi}
    else:
        raise DataError(["distribution must be auto, normal, lognormal or triangular."])
    return {"dist": dist, "chosen": chosen, "reason": reason, "stats": st, "skewness": round(skew, 4),
            "note": "Fitted to the sample by matching its moments. It describes this sample, not the future; check it before relying on it."}


def parse(kind: str, text: str, options: dict | None = None) -> Parsed:
    o = options or {}
    if kind == "sports_results":
        return parse_sports(text)
    if kind == "market_returns":
        return parse_returns(text, str(o.get("values", "returns")), str(o.get("unit", "percent")))
    if kind == "political_seats":
        return parse_seats(text)
    if kind == "series":
        return parse_series(text)
    raise DataError([f"Unknown data kind '{kind}'."])


def hist_matches(matches: list[list]):
    """Stored sports matches -> engine HistMatch objects (kickoff at noon UTC on the match date)."""
    from .model import HistMatch
    return [HistMatch(h, a, hg, ag, datetime.combine(date.fromisoformat(d), datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=12)) for d, h, a, hg, ag in matches]
