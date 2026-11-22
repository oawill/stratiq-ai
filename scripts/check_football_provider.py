"""Verify real connectivity to football-data.org with the server's key. Run this yourself; the automated tests never touch the network.

    set FOOTBALL_DATA_API_KEY=...        (PowerShell: $env:FOOTBALL_DATA_API_KEY = "...")
    .venv\\Scripts\\python scripts/check_football_provider.py

It makes ONE request (the current Premier League season, the same call the application makes), prints what came back, and never prints the key.
It changes nothing: no database is touched. Exit code 0 means the provider answered and its data normalised cleanly; anything else is explained below.
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stratiq import football_provider as fp  # noqa: E402
from stratiq.football_history import season_label  # noqa: E402


def main() -> int:
    if not fp.configured():
        print("FOOTBALL_DATA_API_KEY is not set in this shell, so nothing was requested. Set it and run again.")
        return 2
    now = datetime.now(timezone.utc)
    year = fp.season_start_year(now.date())
    print(f"Requesting Premier League season {season_label(now.date())} from {fp.PROVIDER} ...")
    adapter = fp.FootballDataOrg()
    started = time.monotonic()
    try:
        matches = adapter.season_matches("EPL", year)
    except fp.ProviderError as e:
        print(f"FAILED: {fp.scrub(str(e))} (HTTP {e.status}, retryable: {e.retryable})")
        return 1
    elapsed = time.monotonic() - started
    fixtures = [f for f in (fp.normalise_match(m) for m in matches) if f]
    print(f"OK: HTTP 200 in {elapsed:.1f}s, {len(matches)} matches returned, {len(fixtures)} usable after validation, {len(matches) - len(fixtures)} rejected.")
    print("Rate-limit headers:", adapter.last_headers or "none returned")
    print("Statuses:", dict(Counter(f.status for f in fixtures)))
    unknown = sorted({w.split(': ', 1)[1] for f in fixtures for w in f.warnings if w.startswith("Unrecognised club name")})
    print("Unrecognised club names:", unknown or "none")
    upcoming = sorted((f for f in fixtures if f.kickoff_utc > now and f.status == "scheduled"), key=lambda f: f.kickoff_utc)[:3]
    for f in upcoming:
        print(f"  next: {f.kickoff_utc:%Y-%m-%d %H:%M} UTC  {f.home} v {f.away}  (provider id {f.provider_fixture_id})")
    if not upcoming:
        print("  No upcoming scheduled fixtures in this season's data (normal between seasons).")
    print("Note: free-plan schedules and scores can be delayed by the provider. Injuries are not supplied by this provider.")
    return 0 if not unknown else 3


if __name__ == "__main__":
    raise SystemExit(main())
