"""Historical league results: read season files, validate every row, and check each season is complete. Pure; no database.

Nothing is invented or repaired: a row that cannot be trusted is rejected with a reason and counted, conflicting records are
reported (never resolved by picking one), and a season is only called complete when every check passes.
"""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from . import datasets as ds
from .football_teams import canonical

COMPETITIONS = {
    "EPL": {"name": "English Premier League", "division": "E0", "clubs": 20, "season_matches": 380, "club_matches": 38},
}
SEASON_START_MONTH = 8   # matches from August start a season, earlier months belong to the one before (2019/20 ended in July 2020)
EXPECTED_SEASONS = 10
MAX_STORED_ISSUES = 50   # how many rejected rows / conflicts a report lists in full; the counts are always exact
MAX_ROWS_PER_COMPETITION = 20_000


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def season_label(d: date) -> str:
    y = d.year if d.month >= SEASON_START_MONTH else d.year - 1
    return f"{y}/{(y + 1) % 100:02d}"


def season_year(label: str) -> int:
    return int(label.split("/")[0])


def active_season(today: date | None = None) -> str:
    return season_label(today or today_utc())


def expected_seasons(today: date | None = None, n: int = EXPECTED_SEASONS) -> list[str]:
    """The n most recent seasons that have finished (everything before the one in progress)."""
    y = season_year(active_season(today))
    return [f"{s}/{(s + 1) % 100:02d}" for s in range(y - n, y)]


def match_hash(rows: list[tuple]) -> str:
    return hashlib.sha256("\n".join(f"{d}|{h}|{a}|{hg}|{ag}" for d, h, a, hg, ag in rows).encode()).hexdigest()


# ------------------------------------------------------------------ reading one source file
@dataclass
class Row:
    season: str
    date: date
    home: str
    away: str
    hg: int
    ag: int
    line: int

    @property
    def key(self) -> tuple:
        return (self.season, self.date, self.home, self.away)


@dataclass
class Source:
    competition: str
    rows: list[Row] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)       # {"line", "reason"}, capped for storage; rejected_count is exact
    rejected_count: int = 0
    duplicates: list[dict] = field(default_factory=list)     # identical repeat of a fixture, dropped
    duplicate_count: int = 0
    conflicts: list[dict] = field(default_factory=list)      # same fixture, different scores: neither is accepted
    conflict_count: int = 0
    unplayed: int = 0
    rows_read: int = 0
    unknown_clubs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def reject(self, line: int, reason: str) -> None:
        self.rejected_count += 1
        if len(self.rejected) < MAX_STORED_ISSUES:
            self.rejected.append({"line": line, "reason": reason})


def read_source(text: str, competition: str = "EPL", combined: bool = False, today: date | None = None) -> Source:
    """Parse a results file (football-data layout or the five-column format). File-level problems raise DataError;
    row-level problems are collected so one bad row does not hide the rest."""
    comp = COMPETITIONS.get(competition)
    if not comp:
        raise ds.DataError([f"Unknown competition '{competition}'."])
    today = today or today_utc()
    header, body = ds.read_csv(text, ds.SPORTS_MAX_COLS)
    col = ds._columns(header, ds.SPORTS_COLS, set(ds.SPORTS_COLS))
    low = [h.lower() for h in header]
    div_col = low.index("div") if "div" in low else None
    src = Source(competition)
    src.rows_read = len(body)
    if div_col is None:
        src.warnings.append("The file has no division column, so it cannot be checked that these are Premier League matches. You are responsible for choosing the right file.")
    unknown: set[str] = set()
    slash = False
    cand: list[Row] = []
    for i, r in enumerate(body, start=2):
        if len(r) != len(header):
            src.reject(i, f"has {len(r)} values but the header has {len(header)} columns.")
            continue
        raw_date = r[col["date"]]
        try:
            d, was_slash = ds._match_date(raw_date)
            slash = slash or was_slash
        except ValueError:
            src.reject(i, f"date '{raw_date}' is not a valid date (use YYYY-MM-DD or DD/MM/YYYY).")
            continue
        if d > today:
            src.unplayed += 1       # a fixture that has not been played is skipped, not an error
            continue
        if div_col is not None and r[div_col] and r[div_col].upper() != comp["division"]:
            src.reject(i, f"division '{r[div_col]}' is not {comp['division']} ({comp['name']}).")
            continue
        names = []
        for raw in (r[col["home"]], r[col["away"]]):
            if not raw.strip() or len(raw.strip()) > 60:
                names.append(None)
                continue
            name, known = canonical(raw)
            if not known:
                unknown.add(name)
            names.append(name)
        if None in names:
            src.reject(i, "team names must be 1 to 60 characters.")
            continue
        home, away = names
        if home == away:
            src.reject(i, f"home and away are both '{home}'.")
            continue
        hg_raw, ag_raw = r[col["hg"]].strip(), r[col["ag"]].strip()
        if not hg_raw or not ag_raw:
            src.reject(i, f"{home} v {away} on {d} has no full-time score although the date has passed.")
            continue
        try:
            hg, ag = int(hg_raw), int(ag_raw)
        except ValueError:
            src.reject(i, f"goals '{hg_raw}' and '{ag_raw}' must be whole numbers.")
            continue
        if not (0 <= hg <= 30 and 0 <= ag <= 30):
            src.reject(i, "goals must be between 0 and 30.")
            continue
        cand.append(Row(season_label(d), d, home, away, hg, ag, i))
    if slash:
        src.warnings.append("Dates written with slashes were read as day/month/year (17/08/2024 is 17 August 2024).")
    if unknown:
        src.unknown_clubs = sorted(unknown)
        src.warnings.append(f"Club name(s) not in the team dictionary, kept exactly as written: {', '.join(sorted(unknown)[:8])}. If one is a different spelling of a club already imported, the season will show as incomplete.")

    by_season = Counter(r.season for r in cand)
    if not combined and len(by_season) > 1:
        big = [s for s, n in by_season.items() if n >= 20]
        if len(big) > 1:
            raise ds.DataError([f"This file contains several seasons ({', '.join(sorted(big))}). Tick 'Combined file' to import it, or split it into one file per season."])
        main = by_season.most_common(1)[0][0]
        kept = []
        for r in cand:
            if r.season == main:
                kept.append(r)
            else:
                src.reject(r.line, f"{r.home} v {r.away} on {r.date} belongs to season {r.season}, but this file is season {main}.")
        cand = kept

    seen: dict[tuple, Row] = {}
    clashing: set[tuple] = set()
    for r in cand:
        first = seen.get(r.key)
        if first is None:
            seen[r.key] = r
        elif (first.hg, first.ag) == (r.hg, r.ag):
            src.duplicate_count += 1
            if len(src.duplicates) < MAX_STORED_ISSUES:
                src.duplicates.append({"line": r.line, "season": r.season, "date": r.date.isoformat(), "home": r.home, "away": r.away})
        else:
            clashing.add(r.key)
            src.conflict_count += 1
            if len(src.conflicts) < MAX_STORED_ISSUES:
                src.conflicts.append({"season": r.season, "date": r.date.isoformat(), "home": r.home, "away": r.away,
                                      "found": [f"{first.hg}-{first.ag} (line {first.line})", f"{r.hg}-{r.ag} (line {r.line})"]})
    src.rows = sorted((r for k, r in seen.items() if k not in clashing), key=lambda r: (r.date, r.home, r.away))
    if clashing:
        src.warnings.append(f"{len(clashing)} fixture(s) appear with different scores. Neither version was accepted; check the source and import again.")
    if not src.rows:
        raise ds.DataError(["No usable matches in this file."] + [f"Line {x['line']}: {x['reason']}" for x in src.rejected[:10]])
    return src


# ------------------------------------------------------------------ is a season complete?
def season_report(matches: list[tuple], season: str, competition: str = "EPL", today: date | None = None) -> dict:
    """matches: (date, home, away, hg, ag) tuples already stored for one season. Runs every completeness check."""
    comp = COMPETITIONS[competition]
    today = today or today_utc()
    y = season_year(season)
    lo, hi = date(y, 7, 1), date(y + 1, 7, 31)   # sanity window for dates (2019/20 finished on 26 July 2020)
    clubs = Counter()
    home_n, away_n = Counter(), Counter()
    pairs = Counter()
    bad_dates = 0
    for d, h, a, hg, ag in matches:
        clubs[h] += 1
        clubs[a] += 1
        home_n[h] += 1
        away_n[a] += 1
        pairs[(h, a)] += 1
        if not (lo <= d <= hi) or d > today or season_label(d) != season:
            bad_dates += 1
    n = len(matches)
    dup_pairs = sum(1 for v in pairs.values() if v > 1)
    short = sorted((c, k) for c, k in clubs.items() if k != comp["club_matches"])   # (club, matches played)
    uneven = sorted(c for c in clubs if home_n[c] != comp["club_matches"] // 2 or away_n[c] != comp["club_matches"] // 2)
    missing: list[str] = []
    if len(clubs) == comp["clubs"]:
        names = sorted(clubs)
        missing = [f"{h} v {a}" for h in names for a in names if h != a and (h, a) not in pairs]
    checks = [
        {"name": f"{comp['clubs']} clubs", "ok": len(clubs) == comp["clubs"], "detail": f"{len(clubs)} found"},
        {"name": f"{comp['season_matches']} matches", "ok": n == comp["season_matches"], "detail": f"{n} found"},
        {"name": f"{comp['club_matches']} matches for every club", "ok": not short,
         "detail": "all clubs" if not short else "; ".join(f"{c} {k}" for c, k in short[:6])},
        {"name": "19 home and 19 away for every club", "ok": not uneven, "detail": "all clubs" if not uneven else f"{len(uneven)} club(s) differ: {', '.join(uneven[:4])}"},
        {"name": "every pair meets once at each ground", "ok": len(clubs) == comp["clubs"] and not missing and not dup_pairs,
         "detail": "complete" if not missing and not dup_pairs else f"{len(missing)} fixture(s) missing" + (f", {dup_pairs} repeated" if dup_pairs else "")},
        {"name": "dates belong to the season", "ok": bad_dates == 0, "detail": "all dates" if not bad_dates else f"{bad_dates} outside"},
    ]
    ok = all(c["ok"] for c in checks)
    status = "complete" if ok else ("in_progress" if season == active_season(today) else "incomplete")
    return {
        "season": season, "status": status, "matches": n, "clubs": len(clubs), "checks": checks,
        "missing_fixtures": missing[:20], "missing_count": len(missing),
        "first_date": min((m[0] for m in matches), default=None), "last_date": max((m[0] for m in matches), default=None),
    }


def overview(rows: list[tuple], competition: str = "EPL", today: date | None = None, expected_n: int = EXPECTED_SEASONS) -> dict:
    """rows: (season, date, home, away, hg, ag) for everything stored. Season table plus the headline numbers."""
    today = today or today_utc()
    by: dict[str, list[tuple]] = defaultdict(list)
    for s, d, h, a, hg, ag in rows:
        by[s].append((d, h, a, hg, ag))
    seasons = [season_report(by[s], s, competition, today) for s in sorted(by)]
    exp = expected_seasons(today, expected_n)
    present = {s["season"] for s in seasons}
    not_imported = [s for s in exp if s not in present]
    completed = [s["season"] for s in seasons if s["status"] == "complete"]
    clubs = {x for _, _, h, a, *_ in rows for x in (h, a)}
    dates = [r[1] for r in rows]
    incomplete = [s["season"] for s in seasons if s["status"] == "incomplete"]
    if not rows:
        quality = "empty"
    elif incomplete or any(s in not_imported for s in exp):
        quality = "needs_review"
    else:
        quality = "good"
    return {
        "competition": competition, "competition_name": COMPETITIONS[competition]["name"],
        "total_matches": len(rows), "total_seasons": len(seasons), "unique_clubs": len(clubs), "clubs": sorted(clubs),
        "earliest": min(dates).isoformat() if dates else None, "latest": max(dates).isoformat() if dates else None,
        "completed_seasons": completed, "incomplete_seasons": incomplete, "expected_seasons": exp, "not_imported": not_imported,
        "active_season": active_season(today), "quality": quality,
        "seasons": [{**s, "first_date": s["first_date"].isoformat() if s["first_date"] else None, "last_date": s["last_date"].isoformat() if s["last_date"] else None} for s in seasons],
    }


def export_csv(rows: list[tuple]) -> str:
    """Exactly five columns, in this order. rows: (date, home, away, hg, ag), already sorted by the caller."""
    out = ["date,home_team,away_team,home_goals,away_goals"]
    for d, h, a, hg, ag in rows:
        for name in (h, a):
            if "," in name or '"' in name or "\n" in name:
                raise ValueError(f"Club name {name!r} cannot be written to CSV safely")
        out.append(f"{d.isoformat() if isinstance(d, date) else d},{h},{a},{hg},{ag}")
    return "\n".join(out) + "\n"
