"""One place that decides what each club is called, in every season and every import.

Every Premier League club from 2016/17 to 2025/26 is listed, with the spellings public results files use for it. A name that is
not in the dictionary is NOT guessed at or merged with anything: it is kept as written (whitespace tidied) and the import warns,
so a new club (or a new spelling) shows up in the validation report instead of silently becoming a different team.
"""
from __future__ import annotations

import re

# canonical name -> spellings seen in public results files (matched case-insensitively, ignoring dots and extra spaces)
CLUBS: dict[str, tuple[str, ...]] = {
    "Arsenal": (),
    "Aston Villa": ("Villa",),
    "Bournemouth": ("AFC Bournemouth",),
    "Brentford": (),
    "Brighton & Hove Albion": ("Brighton", "Brighton and Hove Albion", "Brighton & Hove"),
    "Burnley": (),
    "Cardiff City": ("Cardiff",),
    "Chelsea": (),
    "Crystal Palace": ("C Palace", "Palace"),
    "Everton": (),
    "Fulham": (),
    "Huddersfield Town": ("Huddersfield",),
    "Hull City": ("Hull",),
    "Ipswich Town": ("Ipswich",),
    "Leeds United": ("Leeds", "Leeds Utd"),
    "Leicester City": ("Leicester",),
    "Liverpool": (),
    "Luton Town": ("Luton",),
    "Manchester City": ("Man City", "Manchester C"),
    "Manchester United": ("Man United", "Man Utd", "Manchester Utd", "Manchester U"),
    "Middlesbrough": ("Middlesborough", "Boro"),
    "Newcastle United": ("Newcastle", "Newcastle Utd"),
    "Norwich City": ("Norwich",),
    "Nottingham Forest": ("Nott'm Forest", "Nottm Forest", "Notts Forest", "Forest"),
    "Sheffield United": ("Sheffield Utd", "Sheffield U"),
    "Southampton": (),
    "Stoke City": ("Stoke",),
    "Sunderland": (),
    "Swansea City": ("Swansea",),
    "Tottenham": ("Spurs", "Tottenham Hotspur"),
    "Watford": (),
    "West Bromwich Albion": ("West Brom", "West Bromwich"),
    "West Ham United": ("West Ham", "West Ham Utd"),
    "Wolves": ("Wolverhampton", "Wolverhampton Wanderers"),
}


def _key(name: str) -> str:
    s = name.replace("’", "'").replace("`", "'").lower().replace(".", "")
    return re.sub(r"\s+", " ", s).strip()


_LOOKUP: dict[str, str] = {}
for _canon, _aliases in CLUBS.items():
    for _spelling in (_canon, *_aliases):
        _k = _key(_spelling)
        if _LOOKUP.get(_k, _canon) != _canon:   # one spelling can only ever mean one club
            raise RuntimeError(f"Team dictionary is ambiguous: {_spelling!r} maps to {_LOOKUP[_k]!r} and {_canon!r}")
        _LOOKUP[_k] = _canon


def canonical(name: str) -> tuple[str, bool]:
    """(standard name, known). Unknown names are returned tidied but unchanged, with known=False."""
    tidy = re.sub(r"\s+", " ", name.strip())
    hit = _LOOKUP.get(_key(tidy))
    return (hit, True) if hit else (tidy, False)
