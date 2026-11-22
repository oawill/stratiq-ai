"""Football data provider layer: one adapter per provider, all returning the same normalised fixtures.

Only football-data.org is implemented. What it offers (checked on its pricing and coverage pages, not assumed):
  * Free tier: Premier League fixtures, scores and league tables, 10 requests a minute, schedules and scores delayed.
  * Lineups, squads and cards need a paid tier; pre-match odds and per-match statistics are paid add-ons.
  * No injury or suspension feed was found, so `capabilities` says so and nothing here pretends otherwise.
The API key is read from the server environment (FOOTBALL_DATA_API_KEY) and only ever sent to the provider as a header: it is never
returned, logged or stored, and error text is scrubbed of it.

The adapter does no database work. It takes an injectable `httpx.Client` (tests give it a mock transport) and an injectable sleep,
retries only what is safe to retry (network errors, 429, 5xx) with exponential backoff and a total time budget, and raises `ProviderError`
with a plain-language message.
"""
from __future__ import annotations

import os
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from .football_history import SEASON_START_MONTH, season_label
from .football_teams import canonical

PROVIDER = "football-data.org"
BASE_URL = "https://api.football-data.org/v4"
COMPETITION_CODE = {"EPL": "PL"}
DEFAULT_PER_MINUTE = 10          # the free tier; override with FOOTBALL_DATA_RATE_PER_MINUTE on a paid plan
MAX_ATTEMPTS = 3
TIME_BUDGET_SECONDS = 35.0       # the API function limit is 60 seconds
REQUEST_TIMEOUT = 10.0

CAPABILITIES = {
    "fixtures": True, "kickoff_times": True, "match_status": True, "final_scores": True, "standings": True,
    "recent_form": "derived from stored results, not supplied by the provider",
    "injuries_suspensions": False, "lineups": "paid tier only", "odds": "paid add-on only", "advanced_statistics": "paid add-on only",
}

# provider status -> ours. Anything not listed is rejected rather than guessed.
STATUS = {"SCHEDULED": "scheduled", "TIMED": "scheduled", "IN_PLAY": "in_play", "LIVE": "in_play", "PAUSED": "paused", "FINISHED": "finished",
          "AWARDED": "awarded", "POSTPONED": "postponed", "SUSPENDED": "suspended", "CANCELED": "cancelled", "CANCELLED": "cancelled"}
INACTIVE = ("postponed", "suspended", "cancelled")    # never forecast, never listed as upcoming
FINAL = ("finished", "awarded")


class ProviderError(Exception):
    """A provider problem in words a person can read. `retryable` is true for outages and rate limits."""

    def __init__(self, message: str, retryable: bool = False, status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.retryable, self.status, self.retry_after = retryable, status, retry_after


class NotConfigured(ProviderError):
    pass


@dataclass
class Fixture:
    provider_fixture_id: str
    competition: str
    season: str
    matchday: int | None
    kickoff_utc: datetime
    status: str
    home: str
    away: str
    raw_home: str
    raw_away: str
    venue: str | None = None
    home_goals: int | None = None
    away_goals: int | None = None
    provider_updated_at: datetime | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def local_date(self):
        return self.kickoff_utc.date()


def configured() -> bool:
    return bool(os.environ.get("FOOTBALL_DATA_API_KEY", "").strip())


def per_minute_limit() -> int:
    try:
        return max(1, min(int(os.environ.get("FOOTBALL_DATA_RATE_PER_MINUTE", DEFAULT_PER_MINUTE)), 120))
    except ValueError:
        return DEFAULT_PER_MINUTE


def scrub(text: str) -> str:
    """Remove the key (and anything that looks like a token header) from text before it is stored or shown."""
    key = os.environ.get("FOOTBALL_DATA_API_KEY", "")
    if key:
        text = text.replace(key, "[key]")
    return re.sub(r"(?i)(x-auth-token\W+)\S+", r"\1[key]", text)[:300]


def _parse_ts(v) -> datetime | None:
    if not isinstance(v, str) or not v:
        return None
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(timezone.utc) if d.tzinfo else d.replace(tzinfo=timezone.utc)


_SUFFIX = re.compile(r"\s+(?:FC|AFC)$", re.I)


def normalise_team(raw: str) -> tuple[str, bool]:
    """Provider names carry a club suffix ("Arsenal FC"). Map to the platform's standard name; unknown clubs are kept as written."""
    tidy = _SUFFIX.sub("", re.sub(r"\s+", " ", (raw or "").strip()))
    return canonical(tidy)


def season_start_year(d) -> int:
    return d.year if d.month >= SEASON_START_MONTH else d.year - 1


def normalise_match(m: dict, competition: str = "EPL") -> Fixture | None:
    """One provider match to a Fixture, or None when it cannot be trusted (missing id, teams, kickoff, or an unknown status)."""
    if not isinstance(m, dict) or m.get("id") is None:
        return None
    status = STATUS.get(str(m.get("status", "")).upper())
    kick = _parse_ts(m.get("utcDate"))
    h, a = (m.get("homeTeam") or {}), (m.get("awayTeam") or {})
    raw_h, raw_a = str(h.get("name") or "").strip(), str(a.get("name") or "").strip()
    if not status or not kick or not raw_h or not raw_a or raw_h == raw_a:
        return None
    home, hk = normalise_team(raw_h)
    away, ak = normalise_team(raw_a)
    warnings = [f"Unrecognised club name: {n}" for n, k in ((raw_h, hk), (raw_a, ak)) if not k]
    ft = (m.get("score") or {}).get("fullTime") or {}
    hg, ag = ft.get("home"), ft.get("away")
    final_ok = status in FINAL and isinstance(hg, int) and isinstance(ag, int) and 0 <= hg <= 50 and 0 <= ag <= 50
    if status in FINAL and not final_ok:
        warnings.append("Finished, but the provider has not supplied a full-time score yet.")
    md = m.get("matchday")
    venue = m.get("venue")
    return Fixture(
        provider_fixture_id=str(m["id"]), competition=competition, season=season_label(kick.date()),
        matchday=md if isinstance(md, int) and 0 < md < 100 else None, kickoff_utc=kick, status=status, home=home, away=away, raw_home=raw_h, raw_away=raw_a,
        venue=str(venue).strip()[:120] if venue else None, home_goals=hg if final_ok else None, away_goals=ag if final_ok else None,
        provider_updated_at=_parse_ts(m.get("lastUpdated")), warnings=warnings)


class FootballDataOrg:
    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None, sleep=time.sleep, clock=time.monotonic, jitter=random.random):
        self.key = (api_key if api_key is not None else os.environ.get("FOOTBALL_DATA_API_KEY", "")).strip()
        self.client = client or httpx.Client(timeout=REQUEST_TIMEOUT)
        self.sleep, self.clock, self.jitter = sleep, clock, jitter
        self.requests_made = 0
        self.last_headers: dict = {}

    def _get(self, path: str, params: dict | None = None) -> dict:
        if not self.key:
            raise NotConfigured("No football-data.org key is configured on the server (FOOTBALL_DATA_API_KEY).")
        start, last = self.clock(), None
        for attempt in range(MAX_ATTEMPTS):
            try:
                self.requests_made += 1
                r = self.client.get(BASE_URL + path, params=params, headers={"X-Auth-Token": self.key})
            except httpx.HTTPError as e:
                last = ProviderError(f"The provider could not be reached ({type(e).__name__}).", retryable=True)
            else:
                self.last_headers = {k.lower(): v for k, v in r.headers.items() if k.lower().startswith(("x-requests", "x-requestcounter", "retry-after"))}
                if r.status_code == 200:
                    try:
                        body = r.json()
                    except ValueError:
                        raise ProviderError("The provider returned something that was not JSON.", retryable=True, status=200) from None
                    if not isinstance(body, dict):
                        raise ProviderError("The provider returned an unexpected response shape.", retryable=True, status=200)
                    return body
                if r.status_code in (401, 403):
                    raise ProviderError("The provider rejected the server's key (or the plan does not include this data).", status=r.status_code)
                if r.status_code == 404:
                    raise ProviderError("The provider has no such competition or season.", status=404)
                if r.status_code == 429 or r.status_code >= 500:
                    try:
                        ra = float(r.headers.get("retry-after", ""))
                    except ValueError:
                        ra = None
                    last = ProviderError("The provider is rate limiting requests." if r.status_code == 429 else f"The provider is having problems (HTTP {r.status_code}).",
                                         retryable=True, status=r.status_code, retry_after=ra)
                else:
                    raise ProviderError(f"The provider refused the request (HTTP {r.status_code}).", status=r.status_code)
            if attempt == MAX_ATTEMPTS - 1:
                break
            wait = min(last.retry_after if last.retry_after is not None else 2 ** attempt + self.jitter() * 0.5, 15.0)
            if self.clock() - start + wait > TIME_BUDGET_SECONDS:
                break
            self.sleep(wait)
        raise last

    def season_matches(self, competition: str, season_year: int) -> list[dict]:
        """Every match of one season in one request. One call keeps well inside the free plan's rate limit and covers every window."""
        code = COMPETITION_CODE.get(competition)
        if not code:
            raise ProviderError(f"{competition} is not a competition this provider is configured for.")
        body = self._get(f"/competitions/{code}/matches", {"season": season_year})
        ms = body.get("matches")
        if not isinstance(ms, list):
            raise ProviderError("The provider's response had no match list.", retryable=True, status=200)
        return ms
