# backend/services/doi_service.py

"""
DOI health validation service.
Queries Crossref REST API to classify each DOI as:
    valid | retracted | corrected | expression-of-concern | not-found
REQ-3.3.2
"""

import time
from typing import Optional

import httpx

# ---------------------------------------------------------------------------
# In-memory result cache  (doi -> { result, cached_at })
# ---------------------------------------------------------------------------
_CACHE: dict = {}
_CACHE_TTL = 24 * 60 * 60  # 24 hours in seconds

_CROSSREF_BASE = "https://api.crossref.org/works"
# Crossref polite-pool header — avoids rate-limit throttling
_POLITE_MAILTO = "veda-editor@local"


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _get_cached(doi: str) -> Optional[dict]:
    entry = _CACHE.get(doi)
    if entry and (time.time() - entry["cached_at"]) < _CACHE_TTL:
        return entry["result"]
    return None


def _set_cache(doi: str, result: dict) -> None:
    _CACHE[doi] = {"result": result, "cached_at": time.time()}


def clear_cache() -> None:
    """Clears the in-memory DOI cache (used in tests)."""
    _CACHE.clear()


# ---------------------------------------------------------------------------
# Crossref API query with exponential backoff
# ---------------------------------------------------------------------------

def _query_crossref(doi: str) -> dict:
    """
    Queries Crossref REST API for DOI metadata.
    Returns the 'message' dict on success, {} on 404, {} after all retries.
    Respects Retry-After on 429 responses.
    """
    url = f"{_CROSSREF_BASE}/{doi}"
    headers = {"User-Agent": f"VedaEditor/1.0 (mailto:{_POLITE_MAILTO})"}
    delay = 1.0

    for _ in range(4):
        try:
            resp = httpx.get(url, headers=headers, timeout=10.0, follow_redirects=True)
            if resp.status_code == 200:
                return resp.json().get("message", {})
            if resp.status_code == 404:
                return {}
            if resp.status_code == 429:
                delay = float(resp.headers.get("Retry-After", delay * 2))
                time.sleep(delay)
                delay *= 2
                continue
        except Exception:
            pass
        time.sleep(delay)
        delay *= 2

    return {}


# ---------------------------------------------------------------------------
# Status classification
# ---------------------------------------------------------------------------

def _classify(data: dict) -> tuple:
    """
    Inspects Crossref 'message' dict and returns (status, flag_reason).
    Checks:
      - relation.is-retracted-by  → retracted
      - update-to[].label         → retracted / corrected / expression-of-concern
    """
    if not data:
        return "not-found", ""

    # Explicit retraction relation
    if data.get("relation", {}).get("is-retracted-by"):
        return "retracted", "Retraction notice linked via Crossref relation"

    # update-to entries signal corrections or expressions of concern
    for upd in data.get("update-to", []):
        label = upd.get("label", "").lower()
        if "retract" in label:
            return "retracted", upd.get("label", "Retraction")
        if "expression of concern" in label:
            return "expression-of-concern", upd.get("label", "Expression of concern")
        if "correct" in label or "erratum" in label:
            return "corrected", upd.get("label", "Correction")

    return "valid", ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_doi(doi: str) -> dict:
    """
    Validates a single DOI and returns its status record.

    Returns:
        {
            doi:         str,
            status:      "valid" | "retracted" | "corrected" |
                         "expression-of-concern" | "not-found",
            title:       str,
            authors:     list[str],   # first 3 authors
            year:        int | None,
            flag_reason: str,
        }
    """
    cached = _get_cached(doi)
    if cached:
        return cached

    data = _query_crossref(doi)
    status, flag_reason = _classify(data)

    # Extract title
    title = ""
    raw_title = data.get("title")
    if isinstance(raw_title, list) and raw_title:
        title = raw_title[0]
    elif isinstance(raw_title, str):
        title = raw_title

    # Extract first 3 authors
    authors: list[str] = []
    for a in data.get("author", [])[:3]:
        name = f"{a.get('given', '')} {a.get('family', '')}".strip()
        if name:
            authors.append(name)

    # Extract publication year
    year = None
    for date_field in ("published-print", "published-online", "created"):
        parts = (data.get(date_field) or {}).get("date-parts", [[]])
        if parts and parts[0]:
            year = parts[0][0]
            break

    result = {
        "doi": doi,
        "status": status,
        "title": title,
        "authors": authors,
        "year": year,
        "flag_reason": flag_reason,
    }

    _set_cache(doi, result)
    return result
