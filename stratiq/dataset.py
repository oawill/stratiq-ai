"""Seeded FICTIONAL football dataset for development. Not real teams, not real results."""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

DATA_SOURCE = "fictional-dev-dataset"

LEAGUES = {
    "nfl-fict": {
        "name": "Northern Premier League (Fictional)",
        "country": "Fictionia",
        "teams": [
            "Northgate Rovers", "Eastvale United", "Harbour City", "Ironbridge Athletic",
            "Kestrel Park", "Millbrook Town", "Redfield Wanderers", "Silverlake FC",
            "Stonehaven", "Thornbury Albion", "Westmoor Dynamo", "Wychwood Rangers",
        ],
    },
    "csd-fict": {
        "name": "Coastal Division (Fictional)",
        "country": "Fictionia",
        "teams": [
            "Bayside Mariners", "Cliffhaven", "Driftwood Rovers", "Lighthouse Athletic",
            "Pebble Bay", "Saltmarsh United", "Seagull Town", "Tidewater FC",
        ],
    },
}


def team_id(league_id: str, name: str) -> str:
    return f"{league_id}:" + "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def _poisson_sample(rng: random.Random, lam: float) -> int:
    limit = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _round_robin(teams: list[str]) -> list[list[tuple[str, str]]]:
    """Circle-method double round robin. Returns rounds of (home, away) pairs."""
    t = list(teams)
    n = len(t)
    rounds = []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = t[i], t[n - 1 - i]
            pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))
        rounds.append(pairs)
        t = [t[0]] + [t[-1]] + t[1:-1]
    return rounds + [[(b, a) for a, b in rd] for rd in rounds]


def generate(league_id: str, seed: int, now: datetime | None = None, scheduled_rounds: int = 2):
    """Return (true_params, matches). Hidden strengths drive simulated scores."""
    now = now or datetime.now(timezone.utc)
    meta = LEAGUES[league_id]
    rng = random.Random(f"{seed}:{league_id}")
    teams = meta["teams"]
    strength = {t: (math.exp(rng.gauss(0, 0.28)), math.exp(rng.gauss(0, 0.28))) for t in teams}
    mu, gamma = 1.25, 1.28
    rounds = _round_robin(teams)
    n_rounds = len(rounds)
    first_scheduled = n_rounds - scheduled_rounds
    # Last finished round was 3 days ago; weekly cadence.
    base = (now - timedelta(days=3)).replace(hour=15, minute=0, second=0, microsecond=0)
    matches = []
    for r, pairs in enumerate(rounds):
        kickoff = base + timedelta(days=7 * (r - first_scheduled + 1))
        for home, away in pairs:
            row = {
                "league_id": league_id,
                "home": home,
                "away": away,
                "kickoff": kickoff,
                "status": "scheduled" if r >= first_scheduled else "finished",
                "home_goals": None,
                "away_goals": None,
            }
            if row["status"] == "finished":
                ah, dh = strength[home]
                aa, da = strength[away]
                row["home_goals"] = _poisson_sample(rng, mu * ah * da * gamma)
                row["away_goals"] = _poisson_sample(rng, mu * aa * dh)
            matches.append(row)
    return {"mu": mu, "gamma": gamma, "strength": strength}, matches
