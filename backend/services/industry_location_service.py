"""Search and enrich the Government industrial-park catalogue.

The CSV is the source of truth for recommendations.  Google Places is only used
to enrich the short-list with live place information when a server-side API key
is configured.  This separation prevents an LLM or map search from inventing
industrial park availability data.
"""

from __future__ import annotations

import asyncio
import csv
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx


DATASET_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "Industry_Location"
    / "IILB_Park_Report (2).csv"
)
GOOGLE_PLACES_URL = "https://places.googleapis.com/v1/places:searchText"

# Words that add no intent when matching a natural-language location request.
STOP_WORDS = {
    "a", "an", "and", "area", "best", "for", "find", "in", "industrial",
    "industry", "location", "locations", "me", "near", "of", "park", "parks",
    "please", "show", "the", "to", "with",
}


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _tokens(value: str) -> set[str]:
    # Light stemming handles common catalogue/query variants such as textile/textiles.
    return {
        token.rstrip("s")
        for token in _normalise(value).split()
        if token not in STOP_WORDS and len(token) > 1
    }


def _as_float(value: str | None) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


@lru_cache(maxsize=1)
def load_industry_locations() -> list[dict[str, Any]]:
    """Read the source CSV once per process and return normalized records."""
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Industry location data was not found at {DATASET_PATH}")

    with DATASET_PATH.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))

    locations: list[dict[str, Any]] = []
    for row in rows:
        name = (row.get("Park Name") or "").strip()
        if not name:
            continue
        locations.append(
            {
                "id": (row.get("Park ID") or row.get("SrNO") or name).strip(),
                "name": name,
                "state": (row.get("State") or "").strip(),
                "district": (row.get("District") or "").strip(),
                "sector": (row.get("Sector") or "Mixed").strip(),
                "industrial_park_type": (row.get("Industrial Park Type") or "").strip(),
                "park_type": (row.get("Park Type") or "").strip(),
                "land_category": (row.get("Land Category") or "").strip(),
                "land_available_hectares": _as_float(row.get("Land Available (ha.)")),
                "total_land_hectares": _as_float(row.get("Total Land Area (ha.)")),
                "plug_and_play": (row.get("Plug And Play") or "").strip().lower() == "yes",
                "updated_at": (row.get("Update Date") or "").strip(),
            }
        )
    return locations


def _score_location(location: dict[str, Any], query: str) -> tuple[float, list[str]]:
    """Score a catalogue record and retain the exact reasons shown to users."""
    query_normalised = _normalise(query)
    query_terms = _tokens(query)
    reasons: list[str] = []
    score = 0.0

    fields = {
        "park name": _normalise(location["name"]),
        "district": _normalise(location["district"]),
        "state": _normalise(location["state"]),
        "sector": _normalise(location["sector"]),
        "park type": _normalise(location["industrial_park_type"]),
    }

    # Exact location and sector matches are intentionally weighted above capacity.
    # A generic name such as "Textile Park" should not outrank a requested city.
    name_terms = _tokens(location["name"])
    sector_terms = _tokens(location["sector"])
    if name_terms and name_terms.issubset(query_terms) and name_terms != sector_terms:
        score += 16
        reasons.append("Matches requested park name")

    for label, weight in (("district", 12), ("state", 10), ("sector", 14), ("park type", 6)):
        value = fields[label]
        if value and value in query_normalised:
            score += weight
            if label in {"district", "state", "sector"}:
                reasons.append(f"Matches requested {label}: {location[label.replace(' ', '_')]}")

    searchable = " ".join(fields.values())
    matched_terms = query_terms.intersection(_tokens(searchable))
    score += len(matched_terms) * 3

    available = location["land_available_hectares"]
    if available > 0:
        # A small tie-breaker: the query still decides the ordering.
        score += min(5.0, available / 20)
        reasons.append(f"{available:g} ha reported available")
    if location["plug_and_play"]:
        score += 2
        reasons.append("Plug-and-play facility reported")

    if not reasons:
        reasons.append("Catalogue match; refine the query with a state, district, or sector")
    return score, reasons[:3]


def _maps_search_link(location: dict[str, Any]) -> str:
    place_query = ", ".join(
        part for part in (location["name"], location["district"], location["state"], "India") if part
    )
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(place_query)}"


async def _enrich_with_google_place(location: dict[str, Any], client: httpx.AsyncClient, api_key: str) -> dict[str, Any] | None:
    """Retrieve a narrowly scoped, live Google Places result for one park."""
    text_query = ", ".join(
        part for part in (location["name"], location["district"], location["state"], "India") if part
    )
    try:
        response = await client.post(
            GOOGLE_PLACES_URL,
            headers={
                "X-Goog-Api-Key": api_key,
                # Ask only for fields rendered by the UI; field masks affect billing.
                "X-Goog-FieldMask": (
                    "places.id,places.displayName,places.formattedAddress,places.location,"
                    "places.businessStatus,places.rating,places.userRatingCount,"
                    "places.websiteUri,places.googleMapsLinks"
                ),
            },
            json={"textQuery": text_query, "maxResultCount": 1},
        )
        response.raise_for_status()
        places = response.json().get("places", [])
        if not places:
            return None
        place = places[0]
        maps_links = place.get("googleMapsLinks") or {}
        return {
            "source": "google_places",
            "place_id": place.get("id"),
            "name": (place.get("displayName") or {}).get("text"),
            "formatted_address": place.get("formattedAddress"),
            "latitude": (place.get("location") or {}).get("latitude"),
            "longitude": (place.get("location") or {}).get("longitude"),
            "business_status": place.get("businessStatus"),
            "rating": place.get("rating"),
            "user_rating_count": place.get("userRatingCount"),
            "website_uri": place.get("websiteUri"),
            "maps_uri": maps_links.get("placeUri"),
        }
    except (httpx.HTTPError, ValueError):
        # Catalogue recommendations must remain available when Google is down,
        # misconfigured, or has no matching place.
        return None


async def search_industry_locations(query: str, limit: int = 5, enrich: bool = True) -> dict[str, Any]:
    """Rank catalogue entries and optionally add live Google Places details."""
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("A location, state, district, or industrial sector is required.")

    ranked = []
    for location in load_industry_locations():
        score, reasons = _score_location(location, clean_query)
        ranked.append((score, location, reasons))

    ranked.sort(key=lambda item: (-item[0], -item[1]["land_available_hectares"], item[1]["name"]))
    selected = ranked[:limit]
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")

    google_results: list[dict[str, Any] | None] = [None] * len(selected)
    google_enabled = bool(enrich and api_key)
    if google_enabled and selected:
        async with httpx.AsyncClient(timeout=8.0) as client:
            google_results = await asyncio.gather(
                *[_enrich_with_google_place(location, client, api_key) for _, location, _ in selected]
            )

    results: list[dict[str, Any]] = []
    for (score, location, reasons), google_place in zip(selected, google_results):
        maps_url = (google_place or {}).get("maps_uri") or _maps_search_link(location)
        results.append(
            {
                **location,
                "score": round(score, 2),
                "match_reasons": reasons,
                "maps_url": maps_url,
                "live_place": google_place,
                "summary": (
                    f"{location['name']} is a {location['industrial_park_type'] or 'listed industrial park'} "
                    f"in {location['district']}, {location['state']}. "
                    f"Sector: {location['sector']}. "
                    f"Reported available land: {location['land_available_hectares']:g} ha."
                ),
            }
        )

    return {
        "query": clean_query,
        "total_catalogue_locations": len(load_industry_locations()),
        "google_places_enrichment": "enabled" if google_enabled else "not_configured",
        "results": results,
        "disclaimer": (
            "Land and facility fields come from the local industrial-park catalogue. "
            "Verify current availability with the relevant industrial development authority."
        ),
    }
