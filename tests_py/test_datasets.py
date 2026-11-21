"""CSV parsing and validation (pure), and the dataset API: storage, isolation, plan limits and use in each module."""
import math
import random
from datetime import date, timedelta

import pytest

from stratiq import datasets as ds
from .conftest import hdr, make_user
from .test_billing import subscribe
from .test_team import workspace_with


# ------------------------------------------------------------------ fixtures: small, deterministic, clearly synthetic files
def sports_csv(n_rounds=8, teams=("Ash", "Birch", "Cedar", "Dune", "Elm", "Fir"), skew=True):
    rnd = random.Random(7)
    start = date(2024, 1, 6)
    rows = ["date,home_team,away_team,home_goals,away_goals"]
    d = start
    for _ in range(n_rounds):
        for i, h in enumerate(teams):
            a = teams[(i + 1 + _) % len(teams)]
            if a == h:
                continue
            strong = 1.6 if (skew and h == "Ash") else 1.2
            rows.append(f"{d},{h},{a},{int(rnd.random() * strong * 2.2)},{int(rnd.random() * 2.2)}")
        d += timedelta(days=7)
    return "\n".join(rows)


def returns_csv(n=30, assets=("AAA", "BBB"), start=date(2023, 1, 31)):
    rnd = random.Random(3)
    rows = ["date," + ",".join(assets)]
    d = start
    for _ in range(n):
        rows.append(f"{d}," + ",".join(f"{rnd.gauss(0.8, 4):.2f}" for _ in assets))
        d += timedelta(days=30)
    return "\n".join(rows)


SEATS = "party,seats\nAlpha,40\nBeta,35\nGamma,15\nDelta,10\n"
SERIES = "month,demand\n" + "\n".join(f"{i},{100 + 8 * math.sin(i) + (i % 5)}" for i in range(1, 31))


# ------------------------------------------------------------------ sports parsing
def test_sports_parse_ok():
    p = ds.parse_sports(sports_csv())
    assert p.kind == "sports_results" and p.row_count >= 30
    assert p.summary["teams"] == 6 and p.summary["first_date"] < p.summary["last_date"]
    assert p.sha256 == ds.parse_sports(sports_csv()).sha256  # same content, same fingerprint
    assert p.sha256 != ds.parse_sports(sports_csv(skew=False)).sha256


def test_sports_accepts_alias_columns_semicolons_and_a_bom():
    text = "﻿" + sports_csv().replace(",", ";").replace("home_team", "home").replace("away_team", "away").replace("home_goals", "home_score").replace("away_goals", "away_score")
    assert ds.parse_sports(text).summary["teams"] == 6


@pytest.mark.parametrize("mutate,expect", [
    (lambda t: t.replace("2024-01-06", "Jan 6 2024", 1), "YYYY-MM-DD"),
    (lambda t: t.replace("2024-01-13", "2999-01-13", 1), "future"),
    (lambda t: t.replace(",Ash,", ",Ash,", 1).replace("Birch,", "Ash,", 1), "both 'Ash'"),
    (lambda t: t.replace("\n", "\nx,", 1), "has 6 values"),
    (lambda t: t.replace("date,", "when,", 1), "Missing column"),
])
def test_sports_errors_are_specific(mutate, expect):
    with pytest.raises(ds.DataError) as e:
        ds.parse_sports(mutate(sports_csv()))
    assert any(expect in m for m in e.value.errors), e.value.errors


def test_sports_goal_validation_and_minimums():
    head = "date,home_team,away_team,home_goals,away_goals\n"
    with pytest.raises(ds.DataError) as e:
        ds.parse_sports(head + "2024-01-01,A,B,99,0\n2024-01-02,A,B,x,0")
    assert sum("goals" in m for m in e.value.errors) == 2
    with pytest.raises(ds.DataError, match="At least 30"):
        ds.parse_sports(sports_csv(n_rounds=2))
    two_teams = head + "\n".join(f"2024-01-{d:02d},A,B,1,0" for d in range(1, 29)) + "\n" + "\n".join(f"2024-02-{d:02d},B,A,0,1" for d in range(1, 11))
    with pytest.raises(ds.DataError, match="Between 4 and 200"):
        ds.parse_sports(two_teams)


def test_error_lists_are_capped_and_numbered():
    text = "date,home_team,away_team,home_goals,away_goals\n" + "\n".join("nope,A,B,1,1" for _ in range(100))
    with pytest.raises(ds.DataError) as e:
        ds.parse_sports(text)
    assert len(e.value.errors) == ds.MAX_ERRORS and e.value.errors[0].startswith("Line 2:")


@pytest.mark.parametrize("text,expect", [("", "empty"), ("   \n", "empty"), ("a,a\n1,2", "different"), ("x\n" * 3, "")])
def test_generic_file_problems(text, expect):
    with pytest.raises(ds.DataError) as e:
        ds.parse_sports(text)
    assert expect in " ".join(e.value.errors)


def test_size_limits():
    with pytest.raises(ds.DataError, match="larger than"):
        ds.read_csv("a,b\n" + "1,2\n" * 600_000)
    with pytest.raises(ds.DataError, match="At most 20,000"):
        ds.read_csv("a,b\n" + "1,2\n" * 20_001)
    with pytest.raises(ds.DataError, match="At most 12 columns"):
        ds.read_csv(",".join(f"c{i}" for i in range(13)) + "\n1")


# ------------------------------------------------------------------ returns
def test_returns_percent_decimal_and_frequency():
    p = ds.parse_returns(returns_csv())
    assert p.summary["observations"] == 30 and p.summary["periods_per_year"] == 12 and p.summary["assets"] == ["AAA", "BBB"]
    first = float(returns_csv().splitlines()[1].split(",")[1])
    assert math.isclose(p.data["returns"]["AAA"][0], first / 100, rel_tol=1e-9)
    dec = ds.parse_returns("AAA,BBB\n" + "\n".join("0.01,-0.02" for _ in range(25)), unit="decimal")
    assert dec.data["returns"]["BBB"][0] == -0.02 and any("frequency" in w for w in dec.warnings)


def test_prices_become_returns():
    prices = "date,X\n" + "\n".join(f"{date(2024, 1, 1) + timedelta(days=i)},{100 * 1.01 ** i:.6f}" for i in range(25))
    p = ds.parse_returns(prices, values="prices")
    assert p.summary["observations"] == 24 and p.summary["converted_from_prices"] and p.summary["periods_per_year"] == 252
    assert all(math.isclose(x, 0.01, abs_tol=1e-6) for x in p.data["returns"]["X"])
    with pytest.raises(ds.DataError, match="greater than 0"):
        ds.parse_returns(prices.replace("100.000000", "0", 1), values="prices")


@pytest.mark.parametrize("mutate,expect", [
    (lambda t: t.replace("2023-01-31", "2030-01-01", 1), "strictly increasing"),
    (lambda t: t + "\n2030-01-01,1,2,3", "has 4 values"),
    (lambda t: t + "\n2030-01-01,abc,1", "not a number"),
    (lambda t: t + "\n2030-01-01,,1", "blank"),
    (lambda t: t + "\n2030-01-01,-150,1", "-100%"),
])
def test_returns_errors(mutate, expect):
    with pytest.raises(ds.DataError) as e:
        ds.parse_returns(mutate(returns_csv()))
    assert expect in " ".join(e.value.errors), e.value.errors


def test_returns_minimums_and_asset_cap():
    with pytest.raises(ds.DataError, match="At least 20"):
        ds.parse_returns(returns_csv(n=10))
    with pytest.raises(ds.DataError, match="At most 10 assets"):
        ds.parse_returns(returns_csv(assets=tuple(f"A{i}" for i in range(11))))
    with pytest.raises(ds.DataError, match="column names"):
        ds.parse_returns("1,2\n" + "1,2\n" * 25)


# ------------------------------------------------------------------ seats and series
def test_seats():
    p = ds.parse_seats(SEATS)
    assert p.data["parties"][0] == {"name": "Alpha", "seats": 40} and p.summary == {"parties": 4, "total_seats": 100}
    assert ds.parse_seats("party,seats,position\nA,5,-0.5\nB,5,0.5").data["parties"][1]["position"] == 0.5
    for bad, msg in [("party,seats\nA,5", "Between 2"), ("party,seats\nA,5\nA,6", "twice"), ("party,seats\nA,x\nB,2", "whole number"),
                     ("party,seats\nA,0\nB,0", "greater than zero"), ("party,seats\nA,-1\nB,2", "between 0")]:
        with pytest.raises(ds.DataError, match=msg):
            ds.parse_seats(bad)


def test_series_and_fitting():
    p = ds.parse_series(SERIES)
    assert p.summary["observations"] == 30 and p.summary["columns"]["demand"]["n"] == 30
    f = ds.fit_distribution(p.data["columns"]["demand"], "auto")
    assert f["dist"]["type"] in ("normal", "lognormal") and f["stats"]["n"] == 30 and "sample" in f["note"]
    assert f["dist"]["mean"] == pytest.approx(f["stats"]["mean"], rel=1e-6)
    # Strongly right-skewed positive data picks lognormal; negative values cannot be lognormal.
    rng = random.Random(1)
    skewed = [math.exp(rng.gauss(0, 1)) for _ in range(200)]
    assert ds.fit_distribution(skewed)["chosen"] == "lognormal"
    with pytest.raises(ds.DataError, match="strictly positive"):
        ds.fit_distribution([-1.0, 1.0] * 15, "lognormal")
    with pytest.raises(ds.DataError, match="do not vary"):
        ds.fit_distribution([5.0] * 30)
    with pytest.raises(ds.DataError, match="At least 20"):
        ds.fit_distribution([1.0, 2.0, 3.0])
    tri = ds.fit_distribution(p.data["columns"]["demand"], "triangular")["dist"]
    assert tri["low"] <= tri["mode"] <= tri["high"]


def test_fitted_distributions_are_accepted_by_simlab():
    from stratiq import simulation as sim
    for kind in ("normal", "lognormal", "triangular"):
        data = [100 + (i * 7919 % 97) / 10 for i in range(60)]
        sim.make_sampler(ds.fit_distribution(data, kind)["dist"])  # raises ConfigError if SimLab would refuse it


# ------------------------------------------------------------------ API
def post(client, h, path, body):
    return client.post(f"/api/v1/data/{path}", json=body, headers=h)


def upload(client, h, kind="sports_results", name="Test data", csv=None, **opts):
    csv = csv if csv is not None else {"sports_results": sports_csv(), "market_returns": returns_csv(), "political_seats": SEATS, "series": SERIES}[kind]
    return post(client, h, "datasets", {"kind": kind, "name": name, "csv": csv, "options": opts})


def test_requires_auth(client):
    for method, path in [("get", "/api/v1/data/datasets"), ("post", "/api/v1/data/preview"), ("post", "/api/v1/data/datasets")]:
        assert getattr(client, method)(path).status_code == 401


def test_preview_reports_problems_without_saving(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    ok = post(client, h, "preview", {"kind": "market_returns", "csv": returns_csv()}).json()
    assert ok["ok"] and ok["summary"]["observations"] == 30 and ok["sha256"]
    bad = post(client, h, "preview", {"kind": "sports_results", "csv": "date,home,away,home_goals,away_goals\nx,A,B,1,1"}).json()
    assert bad["ok"] is False and bad["errors"][0].startswith("Line 2:")
    assert client.get("/api/v1/data/datasets", headers=h).json()["datasets"] == []


def test_upload_list_get_and_delete(client, conn):
    wid, [(o, ho), (m, hm), (v, hv)] = workspace_with(conn, "owner", "member", "viewer")
    made = upload(client, hm, name="League A")
    assert made.status_code == 201, made.text
    did = made.json()["id"]
    listing = client.get("/api/v1/data/datasets?kind=sports_results", headers=hv).json()["datasets"]
    assert [d["name"] for d in listing] == ["League A"] and listing[0]["created_by_name"] == "T"
    assert client.get("/api/v1/data/datasets?kind=series", headers=hv).json()["datasets"] == []
    assert client.get(f"/api/v1/data/datasets/{did}", headers=hv).json()["summary"]["teams"] == 6
    data = client.get(f"/api/v1/data/datasets/{did}/data", headers=hv).json()
    assert data["sha256"] == made.json()["sha256"] and len(data["data"]["matches"]) == made.json()["row_count"]
    assert upload(client, hv).status_code == 403                                   # viewers cannot upload
    assert client.delete(f"/api/v1/data/datasets/{did}", headers=hv).status_code == 403
    other, ho2 = make_user(conn, "member", workspace_id=wid)
    assert client.delete(f"/api/v1/data/datasets/{did}", headers=hdr(other, wid)).status_code == 403   # another member
    assert client.delete(f"/api/v1/data/datasets/{did}", headers=ho).status_code == 204              # the owner can
    assert client.get(f"/api/v1/data/datasets/{did}", headers=ho).status_code == 404
    assert conn.execute("select count(*) n from audit_logs where workspace_id=%s and action in ('dataset.create','dataset.delete')", (wid,)).fetchone()["n"] == 2


def test_invalid_uploads_are_422_with_line_errors_and_store_nothing(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    r = upload(client, h, csv="date,home_team,away_team,home_goals,away_goals\n2024-01-01,A,A,1,1")
    assert r.status_code == 422 and r.json()["detail"]["errors"]
    assert upload(client, h, name="   ").status_code == 422
    assert post(client, h, "datasets", {"kind": "astrology", "name": "x", "csv": "a"}).status_code == 422
    assert conn.execute("select count(*) n from datasets where workspace_id=%s", (wid,)).fetchone()["n"] == 0


def test_datasets_are_private_to_their_workspace(client, conn):
    a_uid, a_ws = make_user(conn)
    b_uid, b_ws = make_user(conn)
    ha, hb = hdr(a_uid, a_ws), hdr(b_uid, b_ws)
    did = upload(client, ha).json()["id"]
    assert client.get("/api/v1/data/datasets", headers=hb).json()["datasets"] == []
    for method, path in [("get", f"datasets/{did}"), ("get", f"datasets/{did}/data"), ("delete", f"datasets/{did}")]:
        assert getattr(client, method)(f"/api/v1/data/{path}", headers=hb).status_code == 404
    assert post(client, hb, f"datasets/{did}/forecast", {"home": "Ash", "away": "Birch"}).status_code == 404
    assert post(client, hb, f"datasets/{did}/fit", {"column": "demand"}).status_code == 404


def test_dataset_limits_follow_the_plan(client, conn, monkeypatch):
    monkeypatch.setenv("BILLING_ENFORCED", "1")
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    assert upload(client, h, name="one").status_code == 201                     # Explorer: 1 dataset
    r = upload(client, h, name="two")
    assert r.status_code == 402 and r.json()["detail"]["code"] == "plan_limit"
    subscribe(conn, wid, "strategy_pro")
    assert upload(client, h, name="two").status_code == 201


# ------------------------------------------------------------------ module integration
def test_sports_forecast_from_uploaded_results(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    did = upload(client, h, name="My league").json()["id"]
    r = post(client, h, f"datasets/{did}/forecast", {"home": "Ash", "away": "Birch"})
    assert r.status_code == 200, r.text
    f = r.json()
    o = f["outputs"]
    assert f["id"] is None and abs(o["p_home"] + o["p_draw"] + o["p_away"] - 1) < 1e-4
    assert f["inputs"]["dataset"] == "My league" and f["inputs"]["dataset_sha256"] and f["inputs"]["matches_used"] >= 30
    assert conn.execute("select count(*) n from predictions where workspace_id=%s", (wid,)).fetchone()["n"] == 0   # not saved
    # Ratings come from the uploaded data: the strongest home side is favoured over the same fixture reversed.
    flip = post(client, h, f"datasets/{did}/forecast", {"home": "Birch", "away": "Ash"}).json()["outputs"]
    assert o["p_home"] > flip["p_home"]
    # Deterministic: the same data and fixture give the same numbers.
    assert post(client, h, f"datasets/{did}/forecast", {"home": "Ash", "away": "Birch"}).json()["outputs"] == o


def test_saved_dataset_forecast_is_an_immutable_prediction_that_the_library_and_assistant_understand(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    did = upload(client, h, name="My league").json()["id"]
    saved = post(client, h, f"datasets/{did}/forecast", {"home": "Ash", "away": "Birch", "save": True}).json()
    pid = saved["id"]
    row = conn.execute("select subject_type, inputs from predictions where id=%s", (pid,)).fetchone()
    assert row["subject_type"] == "sports_dataset" and row["inputs"]["dataset_id"] == did
    items = client.get("/api/v1/library/items", headers=h).json()["items"]
    assert any(i["id"] == pid and "Ash vs Birch" in i["title"] for i in items)
    r = client.get(f"/api/v1/library/report?type=prediction&id={pid}&format=json", headers=h)
    assert r.status_code == 200
    ex = client.post("/api/v1/assistant/explain", json={"type": "prediction", "id": pid, "focus": "all", "use_llm": False}, headers=h)
    assert ex.status_code == 200, ex.text


def test_forecast_validation_and_viewer_cannot_save(client, conn):
    wid, [(o, ho), (v, hv)] = workspace_with(conn, "owner", "viewer")
    did = upload(client, ho).json()["id"]
    assert post(client, ho, f"datasets/{did}/forecast", {"home": "Ash", "away": "Ash"}).status_code == 422
    assert post(client, ho, f"datasets/{did}/forecast", {"home": "Ash", "away": "Nobody"}).status_code == 422
    assert post(client, hv, f"datasets/{did}/forecast", {"home": "Ash", "away": "Birch"}).status_code == 200      # reading is fine
    assert post(client, hv, f"datasets/{did}/forecast", {"home": "Ash", "away": "Birch", "save": True}).status_code == 403
    series = upload(client, ho, kind="series", name="s").json()["id"]
    assert post(client, ho, f"datasets/{series}/forecast", {"home": "Ash", "away": "Birch"}).status_code == 422   # wrong kind


def test_returns_dataset_feeds_the_historical_risk_tool(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    did = upload(client, h, kind="market_returns", name="Funds").json()["id"]
    exp = client.get(f"/api/v1/data/datasets/{did}/returns-csv", headers=h).json()
    assert exp["unit"] == "decimal" and exp["names"] == ["AAA", "BBB"] and exp["periods_per_year"] == 12
    series = {n: [float(x) for x in col] for n, col in zip(exp["names"], zip(*[r.split(",") for r in exp["csv"].splitlines()[1:]]))}
    r = client.post("/api/v1/finance/historical", json={"series": series, "weights": {"AAA": 0.5, "BBB": 0.5}, "periods_per_year": exp["periods_per_year"]}, headers=h)
    assert r.status_code == 200, r.text


def test_series_dataset_fits_a_distribution_that_a_simulation_runs_with(client, conn, monkeypatch):
    from stratiq import simulation_api
    monkeypatch.setattr(simulation_api, "launch", lambda rid: None)
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    did = upload(client, h, kind="series", name="Demand history").json()["id"]
    fit = post(client, h, f"datasets/{did}/fit", {"column": "demand"})
    assert fit.status_code == 200, fit.text
    body = fit.json()
    assert body["dataset"]["sha256"] and body["column"] == "demand" and body["stats"]["n"] == 30
    assert post(client, h, f"datasets/{did}/fit", {"column": "nope"}).status_code == 404
    run = client.post("/api/v1/simulations/runs", headers=h, json={
        "title": "From data", "domain": "business", "iterations": 1000, "seed": 1,
        "variables": [{"name": "demand", "dist": body["dist"]}], "outputs": [{"name": "revenue", "expr": "demand * 10"}]})
    assert run.status_code == 201, run.text


def test_political_seats_dataset_feeds_the_coalition_tool(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    did = upload(client, h, kind="political_seats", name="Parliament").json()["id"]
    parties = client.get(f"/api/v1/data/datasets/{did}/data", headers=h).json()["data"]["parties"]
    r = client.post("/api/v1/politics/coalitions", json={"parties": parties, "quota_fraction": 0.5}, headers=h)
    assert r.status_code == 200, r.text


# ------------------------------------------------------------------ public-archive layout (football-data.co.uk style)
def archive_csv(slash=True, extra_cols=130):
    """A synthetic file in the common archive layout: day-first dates, HomeTeam/AwayTeam/FTHG/FTAG, and many unused columns."""
    rows = [sports_csv().splitlines()[0]]  # placeholder to reuse team logic below
    parsed = ds.parse_sports(sports_csv())
    pad = ",".join(f"X{i}" for i in range(extra_cols))
    out = [f"Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,{pad}"]
    for d, h, a, hg, ag in parsed.data["matches"]:
        dt = date.fromisoformat(d)
        ds_ = dt.strftime("%d/%m/%Y") if slash else d
        out.append(f"E0,{ds_},15:00,{h},{a},{hg},{ag},H," + ",".join("1.5" for _ in range(extra_cols)))
    return "\n".join(out)


def test_archive_layout_is_accepted_with_a_day_first_warning():
    p = ds.parse_sports(archive_csv())
    ref = ds.parse_sports(sports_csv())
    assert p.summary["matches"] == ref.summary["matches"] and p.summary["first_date"] == ref.summary["first_date"]
    assert p.data == ref.data
    assert any("day/month/year" in w for w in p.warnings)
    assert not any("day/month/year" in w for w in ds.parse_sports(archive_csv(slash=False)).warnings)


def test_two_digit_years_and_impossible_dates():
    assert ds._match_date("17/08/96")[0] == date(1996, 8, 17) and ds._match_date("05/01/24")[0] == date(2024, 1, 5)
    for bad in ("31/02/2024", "2024/01/05", "5/1", "aa/bb/cccc"):
        with pytest.raises(ValueError):
            ds._match_date(bad)
    with pytest.raises(ds.DataError, match="DD/MM/YYYY"):
        ds.parse_sports(archive_csv().replace("/", "-", 2))


def test_very_wide_files_are_only_allowed_for_sports():
    with pytest.raises(ds.DataError, match="At most 200 columns"):
        ds.parse_sports(archive_csv(extra_cols=250))
    with pytest.raises(ds.DataError, match="At most 12 columns"):
        ds.parse_returns("date," + ",".join(f"A{i}" for i in range(40)) + "\n" + "2024-01-01," + ",".join("1" for _ in range(40)))
