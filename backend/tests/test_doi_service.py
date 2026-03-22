# backend/tests/test_doi_service.py

"""
Unit tests for the DOI health validation service (REQ-3.3.2).
All Crossref HTTP calls are mocked — no network access required.
"""

import time
from unittest.mock import patch, MagicMock

import pytest

from backend.services.doi_service import (
    validate_doi,
    _classify,
    _get_cached,
    _set_cache,
    clear_cache,
    _query_crossref,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _mock_resp(status_code: int, json_data: dict | None = None):
    """Returns a MagicMock that mimics an httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.headers = {}
    return resp


# ──────────────────────────────────────────────────────────────────────────────
# _classify
# ──────────────────────────────────────────────────────────────────────────────

def test_classify_empty_returns_not_found():
    status, reason = _classify({})
    assert status == "not-found"
    assert reason == ""


def test_classify_none_like_returns_not_found():
    status, _ = _classify(None)
    assert status == "not-found"


def test_classify_retracted_via_relation():
    data = {"relation": {"is-retracted-by": [{"id": "10.1234/retraction"}]}}
    status, reason = _classify(data)
    assert status == "retracted"
    assert "retract" in reason.lower()


def test_classify_retracted_via_update_to_label():
    data = {"update-to": [{"label": "Retraction"}]}
    status, reason = _classify(data)
    assert status == "retracted"
    assert reason == "Retraction"


def test_classify_corrected_via_erratum():
    data = {"update-to": [{"label": "Erratum"}]}
    status, reason = _classify(data)
    assert status == "corrected"
    assert reason == "Erratum"


def test_classify_corrected_via_correction():
    data = {"update-to": [{"label": "Correction"}]}
    status, reason = _classify(data)
    assert status == "corrected"


def test_classify_expression_of_concern():
    data = {"update-to": [{"label": "Expression of Concern"}]}
    status, reason = _classify(data)
    assert status == "expression-of-concern"


def test_classify_valid_with_no_flags():
    data = {"title": ["A Great Paper"], "author": [{"family": "Smith"}]}
    status, reason = _classify(data)
    assert status == "valid"
    assert reason == ""


# ──────────────────────────────────────────────────────────────────────────────
# Cache behaviour
# ──────────────────────────────────────────────────────────────────────────────

def test_cache_stores_and_retrieves():
    clear_cache()
    fake = {"doi": "10.9999/test", "status": "valid", "title": "T", "authors": [], "year": 2020, "flag_reason": ""}
    _set_cache("10.9999/test", fake)
    assert _get_cached("10.9999/test") == fake


def test_cache_miss_returns_none():
    clear_cache()
    assert _get_cached("10.0000/nonexistent") is None


def test_cache_expires_after_ttl(monkeypatch):
    clear_cache()
    fake = {"doi": "10.9999/ttl", "status": "valid", "title": "", "authors": [], "year": None, "flag_reason": ""}
    _set_cache("10.9999/ttl", fake)
    # Fast-forward time past TTL
    import backend.services.doi_service as ds
    monkeypatch.setattr(ds, "_CACHE_TTL", -1)  # negative TTL = always expired
    assert _get_cached("10.9999/ttl") is None


# ──────────────────────────────────────────────────────────────────────────────
# _query_crossref
# ──────────────────────────────────────────────────────────────────────────────

def test_query_crossref_returns_message_on_200():
    payload = {"message": {"title": ["My Paper"], "author": []}}
    with patch("backend.services.doi_service.httpx.get", return_value=_mock_resp(200, payload)):
        result = _query_crossref("10.1234/abc")
    assert result["title"] == ["My Paper"]


def test_query_crossref_returns_empty_on_404():
    with patch("backend.services.doi_service.httpx.get", return_value=_mock_resp(404)):
        result = _query_crossref("10.1234/notfound")
    assert result == {}


def test_query_crossref_retries_on_500():
    """After repeated 500 errors all retries are exhausted; returns {}."""
    with patch("backend.services.doi_service.httpx.get", return_value=_mock_resp(500)), \
         patch("backend.services.doi_service.time.sleep"):
        result = _query_crossref("10.1234/err")
    assert result == {}


def test_query_crossref_handles_exception():
    """Network-level exceptions are caught; returns {}."""
    with patch("backend.services.doi_service.httpx.get", side_effect=Exception("conn error")), \
         patch("backend.services.doi_service.time.sleep"):
        result = _query_crossref("10.1234/exc")
    assert result == {}


# ──────────────────────────────────────────────────────────────────────────────
# validate_doi — full integration (mocked HTTP)
# ──────────────────────────────────────────────────────────────────────────────

def _crossref_payload(title="Test Paper", authors=None, year=2021,
                      update_to=None, relation=None):
    payload = {
        "title": [title],
        "author": authors or [{"given": "Jane", "family": "Doe"}],
        "published-print": {"date-parts": [[year]]},
    }
    if update_to:
        payload["update-to"] = update_to
    if relation:
        payload["relation"] = relation
    return {"message": payload}


def test_validate_doi_valid():
    clear_cache()
    with patch("backend.services.doi_service.httpx.get",
               return_value=_mock_resp(200, _crossref_payload())):
        r = validate_doi("10.1234/valid")
    assert r["status"] == "valid"
    assert r["title"] == "Test Paper"
    assert r["year"] == 2021
    assert "Jane Doe" in r["authors"]
    assert r["flag_reason"] == ""


def test_validate_doi_retracted():
    clear_cache()
    payload = _crossref_payload(update_to=[{"label": "Retraction"}])
    with patch("backend.services.doi_service.httpx.get",
               return_value=_mock_resp(200, payload)):
        r = validate_doi("10.1234/retracted")
    assert r["status"] == "retracted"
    assert r["flag_reason"] == "Retraction"


def test_validate_doi_not_found():
    clear_cache()
    with patch("backend.services.doi_service.httpx.get", return_value=_mock_resp(404)):
        r = validate_doi("10.9999/missing")
    assert r["status"] == "not-found"
    assert r["title"] == ""
    assert r["authors"] == []
    assert r["year"] is None


def test_validate_doi_uses_cache_on_second_call():
    clear_cache()
    with patch("backend.services.doi_service.httpx.get",
               return_value=_mock_resp(200, _crossref_payload())) as mock_get:
        validate_doi("10.1234/cached")
        validate_doi("10.1234/cached")   # second call should hit cache
    assert mock_get.call_count == 1


def test_validate_doi_corrected():
    clear_cache()
    payload = _crossref_payload(update_to=[{"label": "Erratum"}])
    with patch("backend.services.doi_service.httpx.get",
               return_value=_mock_resp(200, payload)):
        r = validate_doi("10.1234/corrected")
    assert r["status"] == "corrected"


def test_validate_doi_expression_of_concern():
    clear_cache()
    payload = _crossref_payload(update_to=[{"label": "Expression of Concern"}])
    with patch("backend.services.doi_service.httpx.get",
               return_value=_mock_resp(200, payload)):
        r = validate_doi("10.1234/eoc")
    assert r["status"] == "expression-of-concern"
