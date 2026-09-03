"""Snapshot of Israeli cities/settlements and their streets.

Source: data.gov.il dataset "רשימת רחובות בישראל" (Israel Population and
Immigration Authority), resource `bf185c7f-1a4e-4662-88c5-fa118a244bda`,
fetched 2026-09-03 via the CKAN `datastore_search` API, filtered to
`street_name_status == "official"` (synonyms excluded). 1,314 distinct
cities/settlements, 63,575 street entries.

This SUPERSEDES the earlier Wikipedia-sourced local-authorities list — it's an
official government address registry rather than a community-maintained
encyclopedia scrape, and city + street data now come from the same single
source, so a city returned by `GET /localities` always has a (possibly empty)
matching entry at `GET /localities/{city}/streets`.

This is a snapshot, not a live feed — the source dataset updates weekly on
data.gov.il. To refresh: page through `datastore_search` for this resource_id
with `filters={"street_name_status": "official"}`, group records by
`city_name` into sorted `street_name` lists, and overwrite
`streets_by_city.json` with the result.
"""

import json
from pathlib import Path

_DATA_FILE = Path(__file__).resolve().parent / "streets_by_city.json"

with _DATA_FILE.open(encoding="utf-8") as f:
    CITY_STREETS: dict[str, list[str]] = json.load(f)

CITIES: list[str] = sorted(CITY_STREETS)
KNOWN_CITIES: frozenset[str] = frozenset(CITY_STREETS)
