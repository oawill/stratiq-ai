"""Historical football data: reading and validating season files, team names, completeness, import/export, and the features
built on it. All data here is SYNTHETIC: real club names, random scores. No provider data is used or stored in the repository."""
import hashlib
import random
from datetime import date, timedelta

import pytest

from stratiq import datasets as ds
from stratiq import football_features as ff
from stratiq import football_history as fh
from stratiq.football_teams import CLUBS, canonical
from .conftest import hdr, make_user
from .test_engine import _poisson
from .test_team import workspace_with

TODAY = date(2026, 11, 20)
POOL = sorted(CLUBS)          # 34 clubs
assert len(POOL) == 34


def raw_name(club: str) -> str:
    return CLUBS[club][0] if CLUBS[club] else club   # write files with a provider-style spelling


def season_rows(year: int, seed: int | None = None, clubs: list[str] | None = None):
    """A full double round robin (380 matches) with random Poisson scores. Returns (date, home, away, hg, ag) with canonical names."""
    clubs = clubs or [POOL[(3 * (year - 2016) + j) % len(POOL)] for j in range(20)]
    rnd = random.Random(seed if seed is not None else year)
    strength = {c: 0.6 + 1.0 * rnd.random() for c in clubs}
    pairs = [(h, a) for h in clubs for a in clubs if h != a]
    rnd.shuffle(pairs)
    start = date(year, 8, 12)
    out = []
    for i, (h, a) in enumerate(pairs):
        d = start + timedelta(days=7 * (i // 10) + (i % 2))
        out.append((d, h, a, _poisson(rnd, 1.35 * strength[h] / strength[a] ** 0.5), _poisson(rnd, 1.1 * strength[a] / strength[h] ** 0.5)))
    return sorted(out)


def fd_csv(rows, slash=True, short_year=False, div="E0", extra=None):
    """Football-data-style layout: many columns, provider spellings, day-first dates, half-time columns that must be ignored."""
    lines = ["Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,B365H,B365D,B365A"]
    for d, h, a, hg, ag in rows:
        ds_ = d.strftime("%d/%m/%y") if short_year else d.strftime("%d/%m/%Y")
        ds_ = ds_ if slash else d.isoformat()
        lines.append(f"{div},{ds_},15:00,{raw_name(h)},{raw_name(a)},{hg},{ag},H,9,9,2.1,3.3,3.4")
    lines += extra or []
    return "\n".join(lines) + "\n"


def five_csv(rows):
    return fh.export_csv(rows)


ALL = {y: season_rows(y) for y in range(2016, 2026)}


# ------------------------------------------------------------------ seasons and team names
def test_season_boundaries():
    assert fh.season_label(date(2020, 7, 26)) == "2019/20"      # the 2019/20 season finished in July 2020
    assert fh.season_label(date(2020, 9, 12)) == "2020/21"
    assert fh.season_label(date(2024, 8, 17)) == "2024/25"
    assert fh.season_label(date(2025, 5, 25)) == "2024/25"
    assert fh.active_season(TODAY) == "2026/27"
    assert fh.expected_seasons(TODAY) == ["2016/17", "2017/18", "2018/19", "2019/20", "2020/21", "2021/22", "2022/23", "2023/24", "2024/25", "2025/26"]


@pytest.mark.parametrize("raw,standard", [
    ("Man United", "Manchester United"), ("Man Utd", "Manchester United"), ("Manchester Utd", "Manchester United"),
    ("Man City", "Manchester City"), ("Manchester City", "Manchester City"), ("Spurs", "Tottenham"), ("Tottenham", "Tottenham"),
    ("Wolves", "Wolves"), ("Wolverhampton", "Wolves"), ("Newcastle", "Newcastle United"), ("Newcastle United", "Newcastle United"),
    ("Nott'm Forest", "Nottingham Forest"), ("Nottingham Forest", "Nottingham Forest"), ("Nott’m Forest", "Nottingham Forest"),
    ("West Ham", "West Ham United"), ("  west   ham UNITED ", "West Ham United"), ("West Brom", "West Bromwich Albion"),
])
def test_team_names_are_standardised(raw, standard):
    assert canonical(raw) == (standard, True)


def test_unknown_clubs_are_kept_not_guessed_and_different_clubs_never_merge():
    assert canonical("  Plymouth   Argyle ") == ("Plymouth Argyle", False)
    # every spelling in the dictionary means exactly one club, and the clubs that look alike stay apart
    seen = {}
    for club, aliases in CLUBS.items():
        for spelling in (club, *aliases):
            assert seen.setdefault(spelling.lower(), club) == club
    assert canonical("Man City")[0] != canonical("Man United")[0]
    assert canonical("Sheffield United")[0] != canonical("Newcastle United")[0] != canonical("West Ham United")[0]
    assert canonical("Leeds")[0] != canonical("Leicester")[0]


def test_every_club_of_the_ten_seasons_is_present():
    assert len(POOL) == 34 and {"Hull City", "Huddersfield Town", "Luton Town", "Ipswich Town", "Cardiff City", "Swansea City"} <= set(POOL)


# ------------------------------------------------------------------ reading a file
def test_football_data_layout_reads_with_half_time_and_odds_ignored():
    src = fh.read_source(fd_csv(ALL[2024]), today=TODAY)
    assert len(src.rows) == 380 and src.rejected_count == 0 and src.unknown_clubs == []
    assert {r.season for r in src.rows} == {"2024/25"}
    assert {(r.date, r.home, r.away, r.hg, r.ag) for r in src.rows} == set(ALL[2024])     # full-time scores, canonical names
    assert any("day/month/year" in w for w in src.warnings)
    assert not any(r.hg == 9 for r in src.rows)


def test_two_digit_years_iso_dates_and_the_five_column_format_all_read_the_same():
    a = fh.read_source(fd_csv(ALL[2022]), today=TODAY)
    b = fh.read_source(fd_csv(ALL[2022], short_year=True), today=TODAY)
    c = fh.read_source(fd_csv(ALL[2022], slash=False), today=TODAY)
    d = fh.read_source(five_csv(ALL[2022]), today=TODAY)
    assert [(r.date, r.home, r.away, r.hg, r.ag) for r in a.rows] == [(r.date, r.home, r.away, r.hg, r.ag) for r in b.rows] == [(r.date, r.home, r.away, r.hg, r.ag) for r in c.rows] == [(r.date, r.home, r.away, r.hg, r.ag) for r in d.rows]
    assert any("no division column" in w for w in d.warnings)


def test_invalid_rows_are_rejected_one_by_one_with_the_line_and_reason():
    good = ["E0,12/08/2022,15:00,Arsenal,Chelsea,2,1"] * 0
    rows = [
        "E0,13/08/2022,15:00,Arsenal,Chelsea,2,1",         # 2 ok
        "E0,13/08/2022,15:00,Everton,Fulham,-1,0",          # 3 negative
        "E0,13/08/2022,15:00,Brentford,Burnley,1.5,0",      # 4 fractional
        "E0,13/08/2022,15:00,Liverpool,Watford,31,0",       # 5 out of range
        "E0,13/08/2022,15:00,Leeds,Stoke,abc,0",            # 6 non-numeric
        "E0,13/08/2022,15:00,Hull,Cardiff,,",               # 7 missing score, date has passed
        "E0,31/02/2022,15:00,Swansea,Luton,1,1",            # 8 not a calendar date
        "E0,13/08/2022,15:00,Ipswich,Ipswich,1,1",          # 9 same club
        "E1,13/08/2022,15:00,Norwich,Southampton,1,1",      # 10 another division
        "E0,13/08/2022,15:00, ,Burnley,1,1",                # 11 blank name
        "E0,13/08/2022,15:00,Wolves,Spurs,1",               # 12 short row
        "E0,20/08/2022,15:00,Brighton,Fulham,0,0",          # 13 ok
    ]
    src = fh.read_source("Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG\n" + "\n".join(rows) + "\n", today=TODAY)
    assert len(src.rows) == 2 and src.rejected_count == 10
    by_line = {r["line"]: r["reason"] for r in src.rejected}
    assert set(by_line) == {3, 4, 5, 6, 7, 8, 9, 10, 11, 12}
    assert "between 0 and 30" in by_line[3] and "whole numbers" in by_line[4] and "between 0 and 30" in by_line[5] and "whole numbers" in by_line[6]
    assert "no full-time score" in by_line[7] and "valid date" in by_line[8] and "both" in by_line[9] and "E1" in by_line[10] and "1 to 60" in by_line[11] and "values" in by_line[12]
    assert good == []


def test_unplayed_future_fixtures_are_skipped_not_accepted_and_not_errors():
    rows = ALL[2025][:40]
    text = fd_csv(rows, extra=["E0,05/12/2026,15:00,Arsenal,Chelsea,,,,,,,,", "E0,05/12/2026,15:00,Everton,Fulham,3,3,D,0,0,2,3,3"])
    src = fh.read_source(text, today=TODAY)
    assert src.unplayed == 2 and len(src.rows) == 40 and src.rejected_count == 0       # even a scored future row is not trusted


def test_missing_columns_and_empty_files_are_file_level_errors():
    with pytest.raises(ds.DataError, match="Missing column"):
        fh.read_source("Date,HomeTeam,AwayTeam\n01/01/2024,Arsenal,Chelsea\n", today=TODAY)
    with pytest.raises(ds.DataError):
        fh.read_source("", today=TODAY)
    with pytest.raises(ds.DataError, match="No usable matches"):
        fh.read_source("Date,HomeTeam,AwayTeam,FTHG,FTAG\n01/01/2024,Arsenal,Arsenal,1,1\n", today=TODAY)


def test_identical_repeats_are_dropped_and_conflicting_scores_are_flagged_not_picked():
    rows = ALL[2023][:50]
    d, h, a, hg, ag = rows[0]
    text = fd_csv(rows, extra=[f"E0,{d.strftime('%d/%m/%Y')},15:00,{raw_name(h)},{raw_name(a)},{hg},{ag},H,0,0,2,3,3",             # identical repeat
                               f"E0,{rows[1][0].strftime('%d/%m/%Y')},15:00,{raw_name(rows[1][1])},{raw_name(rows[1][2])},{rows[1][3] + 1},{rows[1][4]},H,0,0,2,3,3"])   # same fixture, other score
    src = fh.read_source(text, today=TODAY)
    assert src.duplicate_count == 1 and src.conflict_count == 1
    assert len(src.rows) == 49 and (rows[1][0], rows[1][1], rows[1][2]) not in {(r.date, r.home, r.away) for r in src.rows}
    assert src.conflicts[0]["found"][0].startswith(f"{rows[1][3]}-{rows[1][4]}")


def test_several_seasons_need_the_combined_option_and_strays_are_rejected():
    two = ALL[2016][:60] + ALL[2017][:60]
    with pytest.raises(ds.DataError, match="several seasons"):
        fh.read_source(five_csv(two), today=TODAY)
    both = fh.read_source(five_csv(two), combined=True, today=TODAY)
    assert {r.season for r in both.rows} == {"2016/17", "2017/18"}
    stray = fh.read_source(five_csv(ALL[2018][:60] + [ALL[2020][0]]), today=TODAY)       # one match from another season
    assert len(stray.rows) == 60 and stray.rejected_count == 1 and "belongs to season 2020/21" in stray.rejected[0]["reason"]


def test_new_clubs_are_flagged_and_kept():
    rows = ALL[2024][:40]
    text = fd_csv(rows, extra=["E0,01/05/2025,15:00,Plymouth,Arsenal,1,0,H,0,0,2,3,3"])
    src = fh.read_source(text, today=TODAY)
    assert src.unknown_clubs == ["Plymouth"] and any("not in the team dictionary" in w for w in src.warnings)


def test_size_and_row_limits():
    with pytest.raises(ds.DataError, match="MB"):
        fh.read_source("date,home_team,away_team,home_goals,away_goals\n" + ("x" * 2_100_000), today=TODAY)
    many = "date,home_team,away_team,home_goals,away_goals\n" + "2024-01-01,Arsenal,Chelsea,1,1\n" * 20_001
    with pytest.raises(ds.DataError, match="20,000"):
        fh.read_source(many, today=TODAY)
    wide = "Date,HomeTeam,AwayTeam,FTHG,FTAG," + ",".join(f"c{i}" for i in range(210)) + "\n"
    with pytest.raises(ds.DataError, match="columns"):
        fh.read_source(wide, today=TODAY)


# ------------------------------------------------------------------ completeness
def stored(rows, season):
    return [(d, h, a, hg, ag) for d, h, a, hg, ag in rows]


def test_a_full_season_passes_every_check():
    rep = fh.season_report(stored(ALL[2019], "2019/20"), "2019/20", today=TODAY)
    assert rep["status"] == "complete" and rep["matches"] == 380 and rep["clubs"] == 20 and all(c["ok"] for c in rep["checks"]) and rep["missing_count"] == 0


def test_a_missing_match_makes_the_season_incomplete_and_names_the_fixture():
    rows = list(ALL[2019])
    gone = rows.pop(100)
    rep = fh.season_report(rows, "2019/20", today=TODAY)
    assert rep["status"] == "incomplete" and rep["matches"] == 379
    assert f"{gone[1]} v {gone[2]}" in rep["missing_fixtures"] and rep["missing_count"] == 1
    assert not next(c for c in rep["checks"] if c["name"] == "380 matches")["ok"]


def test_a_misspelt_club_splits_a_team_and_is_caught():
    rows = [(d, "Brighton FC" if h == "Brighton & Hove Albion" else h, a, hg, ag) for d, h, a, hg, ag in season_rows(2019, clubs=[POOL[i] for i in range(20)])] if False else []
    base = season_rows(2019)
    victim = base[0][1]
    rows = [(d, ("Mystery FC" if h == victim and i % 2 else h), a, hg, ag) for i, (d, h, a, hg, ag) in enumerate(base)]
    rep = fh.season_report(rows, "2019/20", today=TODAY)
    assert rep["status"] == "incomplete" and rep["clubs"] == 21 and not next(c for c in rep["checks"] if c["name"] == "20 clubs")["ok"]


def test_the_season_in_progress_is_not_an_error():
    part = season_rows(2026)[:120]
    part = [(d, h, a, hg, ag) for d, h, a, hg, ag in part if d <= TODAY]
    rep = fh.season_report(part, "2026/27", today=TODAY)
    assert rep["status"] == "in_progress"
    ov = fh.overview([(("2026/27"), *m) for m in part] + [("2024/25", *m) for m in ALL[2024]], today=TODAY)
    assert ov["completed_seasons"] == ["2024/25"] and ov["incomplete_seasons"] == [] and ov["active_season"] == "2026/27"
    assert ov["quality"] == "needs_review" and "2016/17" in ov["not_imported"]        # most of the ten are still to import


def test_ten_seasons_overview_is_good():
    rows = [(f"{y}/{(y + 1) % 100:02d}", *m) for y in range(2016, 2026) for m in ALL[y]]
    ov = fh.overview(rows, today=TODAY)
    assert ov["total_matches"] == 3800 and ov["total_seasons"] == 10 and len(ov["completed_seasons"]) == 10 and ov["quality"] == "good"
    assert ov["unique_clubs"] == 34 and ov["not_imported"] == [] and ov["earliest"].startswith("2016-08")


def test_export_is_exactly_five_columns_fits_the_upload_limits_and_round_trips():
    allrows = [m for y in range(2016, 2026) for m in ALL[y]]
    text = fh.export_csv(allrows)
    lines = text.strip().split("\n")
    assert lines[0] == "date,home_team,away_team,home_goals,away_goals" and len(lines) == 3801
    assert all(len(l.split(",")) == 5 for l in lines)
    assert len(text.encode()) < 2_000_000
    parsed = ds.parse_sports(text)                        # the existing Data Workspace validator accepts it unchanged
    assert parsed.row_count == 3800 and parsed.summary["teams"] == 34
    with pytest.raises(ValueError):
        fh.export_csv([(date(2024, 1, 1), 'A,B', "C", 1, 1)])


# ------------------------------------------------------------------ features: nothing from the future
def flat(years):
    return [m for y in years for m in ALL[y]]


def test_profile_form_and_h2h_use_only_earlier_matches():
    rows = flat(range(2016, 2019))
    before = date(2017, 12, 1)
    team = rows[0][1]
    opp = rows[0][2]
    base = (ff.team_profile(rows, team, before), ff.head_to_head(rows, team, opp, before), ff.elo_ratings(rows, before), ff.league_baseline(rows, before))
    tampered = [m if m[0] < before else (m[0], m[1], m[2], 9, 0) for m in rows]
    assert (ff.team_profile(tampered, team, before), ff.head_to_head(tampered, team, opp, before), ff.elo_ratings(tampered, before), ff.league_baseline(tampered, before)) == base
    assert base[0]["played"] == sum(1 for m in rows if m[0] < before and team in (m[1], m[2]))


def test_a_fixture_view_never_includes_the_fixture_or_what_followed():
    rows = flat(range(2016, 2018))
    target = rows[500]
    before = target[0]
    view = ff.fixture_view(rows, target[1], target[2], before)
    same = ff.fixture_view([m for m in rows if m[0] < before], target[1], target[2], before)
    assert view == same and view["matches_used"] == sum(1 for m in rows if m[0] < before)
    changed = [m if m != target else (m[0], m[1], m[2], m[3] + 5, m[4]) for m in rows]
    assert ff.fixture_view(changed, target[1], target[2], before) == view


def test_profile_numbers_are_right_on_a_small_known_league():
    d = date
    rows = [(d(2024, 1, 1), "Arsenal", "Chelsea", 2, 0), (d(2024, 1, 8), "Chelsea", "Arsenal", 1, 1), (d(2024, 1, 15), "Arsenal", "Everton", 0, 0),
            (d(2024, 1, 22), "Everton", "Arsenal", 1, 3), (d(2024, 1, 29), "Arsenal", "Fulham", 4, 1)]
    p = ff.team_profile(rows, "Arsenal", d(2024, 2, 5))
    assert (p["played"], p["wins"], p["draws"], p["losses"]) == (5, 3, 2, 0)
    assert p["win_rate"] == 0.6 and p["points_per_match"] == 2.2 and p["goals_for_per_match"] == 2.0 and p["goals_against_per_match"] == 0.6
    assert p["clean_sheet_rate"] == 0.4 and p["failed_to_score_rate"] == 0.2 and p["average_goals_per_match"] == 2.6
    assert p["home"]["played"] == 3 and p["away"]["played"] == 2
    assert p["form_last_5"]["results"] == "WDDWW" and p["form_last_10"]["matches"] == 5 and p["form_last_5"]["points_per_match"] == 2.2
    assert ff.team_profile(rows, "Arsenal", d(2024, 1, 15))["played"] == 2          # the 15th itself is not yet known on the 15th
    h2h = ff.head_to_head(rows, "Arsenal", "Chelsea", d(2024, 2, 5))
    assert (h2h["meetings"], h2h["wins_a"], h2h["wins_b"], h2h["draws"], h2h["goals_a"], h2h["goals_b"]) == (2, 1, 0, 1, 3, 1)
    assert "not provider-supplied" in p["goal_rate_note"]


def test_elo_is_zero_sum_chronological_and_same_day_matches_are_independent():
    rows = flat([2016])
    r = ff.elo_ratings(rows)
    assert abs(sum(r.values()) - 1500 * len(r)) < 1e-6
    a = [(date(2024, 1, 1), "A", "B", 3, 0), (date(2024, 1, 1), "B", "C", 0, 1)]
    swapped = [a[1], a[0]]
    assert ff.elo_ratings(a) == ff.elo_ratings(swapped)
    strong = [(date(2024, 1, i + 1), "A", "B", 3, 0) for i in range(10)]
    assert ff.elo_ratings(strong)["A"] > 1500 > ff.elo_ratings(strong)["B"]


def test_chronological_evaluation_splits_by_time_not_at_random():
    rows = flat(range(2016, 2020))
    res = ff.chronological_evaluation(rows, per_period=40)
    assert res["ok"] and [p["name"] for p in res["periods"]] == ["training", "validation", "test"]
    tr, va, te = res["periods"]
    assert tr["last"] <= va["first"] and va["last"] <= te["first"] and tr["first"] < tr["last"]
    assert tr["matches"] + va["matches"] + te["matches"] == len(rows) == res["matches"]
    for per in (va, te):
        assert per["scored"] == 40 and per["log_loss"] > 0 and 0 <= per["accuracy"] <= 1 and per["reliability"]
    assert ff.chronological_evaluation(rows[:90])["ok"] is False
    assert ff.calibration_error(te["reliability"]) >= 0


# ------------------------------------------------------------------ API
def post(client, h, path, body):
    return client.post(f"/api/v1/football/{path}", json=body, headers=h)


def get(client, h, path):
    return client.get(f"/api/v1/football/{path}", headers=h)


def season_name(y):
    return f"{y}/{(y + 1) % 100:02d}"


def import_all(client, h, years=range(2016, 2026)):
    out = {}
    for y in years:
        r = post(client, h, "import", {"filename": f"E0_{y}.csv", "csv": fd_csv(ALL[y])})
        assert r.status_code == 200, r.text
        out[y] = r.json()
    return out


def test_requires_auth(client):
    assert client.get("/api/v1/football/summary").status_code == 401
    assert client.post("/api/v1/football/import", json={"csv": "x"}).status_code == 401


def test_ten_seasons_import_complete_and_summary(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    empty = get(client, h, "summary").json()
    assert empty["total_matches"] == 0 and empty["quality"] == "empty" and empty["last_import"] is None
    res = import_all(client, h)
    for y, r in res.items():
        assert r["new"] == 380 and r["rejected"] == 0 and r["conflicts"] == 0 and r["status"] == "ok"
        assert r["seasons"][0]["status"] == "complete" and r["seasons"][0]["season"] == season_name(y) and r["missing"] == 0
    s = get(client, h, "summary").json()
    assert s["total_matches"] == 3800 and s["total_seasons"] == 10 and s["unique_clubs"] == 34 and s["quality"] == "good"
    assert len(s["completed_seasons"]) == 10 and s["not_imported"] == [] and s["last_import"]["status"] == "ok"
    assert s["earliest"] < s["latest"]
    assert conn.execute("select count(*) n from match_history where workspace_id=%s", (wid,)).fetchone()["n"] == 3800


def test_repeating_an_import_creates_no_duplicates(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    import_all(client, h, [2020])
    again = post(client, h, "import", {"filename": "again.csv", "csv": fd_csv(ALL[2020])}).json()
    assert again["new"] == 0 and again["unchanged"] == 380 and again["conflicts"] == 0 and again["status"] == "ok"
    assert conn.execute("select count(*) n from match_history where workspace_id=%s", (wid,)).fetchone()["n"] == 380
    # the same season written in another layout (five columns, ISO dates) is the same fixtures
    five = post(client, h, "import", {"csv": five_csv(ALL[2020])}).json()
    assert five["new"] == 0 and five["unchanged"] == 380


def test_a_changed_score_is_a_conflict_and_is_never_overwritten(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    import_all(client, h, [2021])
    rows = list(ALL[2021])
    d, hm, aw, hg, ag = rows[7]
    rows[7] = (d, hm, aw, hg + 2, ag)
    r = post(client, h, "import", {"csv": fd_csv(rows)}).json()
    assert r["conflicts"] == 1 and r["new"] == 0 and r["status"] == "needs_review" and "stored" in r["conflict_rows"][0]["found"][0]
    kept = conn.execute("select home_goals from match_history where workspace_id=%s and match_date=%s and home_team=%s", (wid, d, hm)).fetchone()
    assert kept["home_goals"] == hg


def test_a_partly_bad_file_stores_the_valid_rows_reports_the_rest_and_the_season_is_incomplete(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    rows = fd_csv(ALL[2022][:370]) + "E0,20/05/2023,15:00,Arsenal,Chelsea,-3,1\nE0,20/05/2023,15:00,Everton,Fulham,,\n"
    r = post(client, h, "import", {"filename": "partial.csv", "csv": rows}).json()
    assert r["new"] == 370 and r["rejected"] == 2 and r["status"] == "needs_review"
    assert r["seasons"][0]["status"] == "incomplete" and r["seasons"][0]["matches"] == 370 and r["missing"] > 0
    s = get(client, h, "summary").json()
    assert s["quality"] == "needs_review" and s["incomplete_seasons"] == ["2022/23"] and s["completed_seasons"] == []
    rep = get(client, h, "report").json()
    assert rep["imports"][0]["filename"] == "partial.csv" and rep["imports"][0]["report"]["rejected_rows"][0]["line"] == 372


def test_dry_run_checks_without_storing(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    r = post(client, h, "import", {"csv": fd_csv(ALL[2019]), "dry_run": True}).json()
    assert r["dry_run"] and r["new"] == 380 and r["seasons"][0]["status"] == "complete" and "id" not in r
    assert get(client, h, "summary").json()["total_matches"] == 0
    assert conn.execute("select count(*) n from match_imports where workspace_id=%s", (wid,)).fetchone()["n"] == 0


def test_bad_files_are_422_with_reasons_and_store_nothing(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    r = post(client, h, "import", {"csv": "Date,HomeTeam,AwayTeam\n01/01/2024,A,B\n"})
    assert r.status_code == 422 and "Missing column" in r.json()["detail"]["errors"][0]
    r = post(client, h, "import", {"csv": five_csv(ALL[2016][:50] + ALL[2017][:50])})
    assert r.status_code == 422 and "several seasons" in r.json()["detail"]["errors"][0]
    assert post(client, h, "import", {"competition": "LALIGA", "csv": "x"}).status_code == 422
    assert get(client, h, "summary").json()["total_matches"] == 0


def test_combined_file_imports_every_season_in_one_go(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    allrows = [m for y in range(2016, 2026) for m in ALL[y]]
    r = post(client, h, "import", {"filename": "combined.csv", "combined": True, "csv": five_csv(allrows)}).json()
    assert r["new"] == 3800 and len(r["seasons"]) == 10 and all(s["status"] == "complete" for s in r["seasons"])


def test_roles_and_privacy(client, conn):
    wid, users = workspace_with(conn, "owner", "member", "viewer", "admin")
    (_, ho), (_, hm), (_, hv), (_, ha) = users
    assert post(client, hv, "import", {"csv": fd_csv(ALL[2016])}).status_code == 403
    assert post(client, hv, "import", {"csv": fd_csv(ALL[2016]), "dry_run": True}).status_code == 200      # checking is read-only
    assert post(client, hm, "import", {"csv": fd_csv(ALL[2016])}).status_code == 200
    assert get(client, hv, "summary").json()["total_matches"] == 380                                       # viewers can read
    assert client.delete("/api/v1/football/seasons?season=2016/17", headers=hm).status_code == 403
    uid2, wid2 = make_user(conn)
    other = hdr(uid2, wid2)
    assert get(client, other, "summary").json()["total_matches"] == 0
    assert get(client, other, "matches").json()["total"] == 0
    assert get(client, other, "export").status_code == 404
    assert client.delete("/api/v1/football/seasons?season=2016/17", headers=other).status_code == 404
    assert client.delete("/api/v1/football/seasons?season=2016/17", headers=ha).status_code == 204
    assert get(client, ho, "summary").json()["total_matches"] == 0
    assert client.delete("/api/v1/football/seasons?season=2016-17", headers=ho).status_code == 422


def test_view_filter_and_export_match_what_was_imported(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    import_all(client, h, [2016, 2017, 2018])
    team = ALL[2016][0][1]
    m = get(client, h, f"matches?team={team}&season=2016/17&limit=500").json()
    assert m["total"] == 38 and all(team in (x["home_team"], x["away_team"]) and x["season"] == "2016/17" for x in m["matches"])
    assert get(client, h, "matches?limit=10&offset=0").json()["total"] == 1140 and len(get(client, h, "matches?limit=10").json()["matches"]) == 10
    ex = get(client, h, "export?season=2017/18").json()
    assert ex["rows"] == 380 and ex["columns"] == ["date", "home_team", "away_team", "home_goals", "away_goals"] and ex["filename"] == "velqorin_epl_2017-18.csv"
    assert hashlib.sha256(ex["csv"].encode()).hexdigest() == ex["sha256"]
    assert ex["csv"].splitlines()[0] == "date,home_team,away_team,home_goals,away_goals"
    assert [tuple(l.split(",")) for l in ex["csv"].splitlines()[1:]] == [(d.isoformat(), a, b, str(x), str(y)) for d, a, b, x, y in ALL[2017]]
    full = get(client, h, "export").json()
    assert full["rows"] == 1140 and full["bytes"] < 2_000_000


def test_stored_matches_become_a_sports_dataset_the_existing_tools_use(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    import_all(client, h, [2018, 2019])
    r = post(client, h, "dataset", {"name": "EPL 2018-20", "seasons": ["2018/19", "2019/20"]})
    assert r.status_code == 201, r.text
    did = r.json()["id"]
    assert r.json()["kind"] == "sports_results" and r.json()["row_count"] == 760
    teams = sorted(r.json()["summary"]["team_matches"])
    f = client.post(f"/api/v1/data/datasets/{did}/forecast", json={"home": teams[0], "away": teams[1]}, headers=h)
    assert f.status_code == 200 and abs(sum(f.json()["outputs"][k] for k in ("p_home", "p_draw", "p_away")) - 1) < 1e-4
    assert client.post(f"/api/v1/data/datasets/{did}/backtest", json={}, headers=h).status_code == 200
    assert post(client, hdr(*make_user(conn)), "dataset", {"name": "x"}).status_code == 404


def test_team_and_fixture_endpoints_use_only_what_came_before(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    import_all(client, h, [2016, 2017])
    target = ALL[2017][200]
    d, home, away = target[0], target[1], target[2]
    f = get(client, h, f"fixture?home={home}&away={away}&before={d.isoformat()}").json()
    assert f["matches_used"] == sum(1 for m in ALL[2016] + ALL[2017] if m[0] < d)
    assert abs(f["projection"]["p_home"] + f["projection"]["p_draw"] + f["projection"]["p_away"] - 1) < 1e-4 and "not provider-supplied" in f["projection_note"]
    t = get(client, h, f"team?team={home}&before={d.isoformat()}").json()
    assert t["played"] == sum(1 for m in ALL[2016] + ALL[2017] if m[0] < d and home in (m[1], m[2]))
    assert get(client, h, f"team?team=Nobody").status_code == 422
    assert get(client, h, f"fixture?home={home}&away={home}").status_code == 422
    assert get(client, h, f"team?team={home}&before=2999-01-01").status_code == 422
    assert get(client, h, f"fixture?home={home}&away={away}&before=2016-08-15").status_code == 422     # too little earlier history


def test_evaluation_endpoint_reports_validation_and_test_periods(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    assert post(client, h, "evaluation", {}).status_code == 404
    import_all(client, h, [2016, 2017, 2018])
    r = post(client, h, "evaluation", {})
    assert r.status_code == 200, r.text
    names = [p["name"] for p in r.json()["periods"]]
    assert names == ["training", "validation", "test"] and r.json()["periods"][2]["log_loss"] > 0
    assert r.json() == post(client, h, "evaluation", {}).json()        # deterministic
