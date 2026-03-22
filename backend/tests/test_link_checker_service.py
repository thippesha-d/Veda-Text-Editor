# backend/tests/test_link_checker_service.py

"""
Unit tests for the URL / link-rot detection service (REQ-3.3.3).
All HTTP calls are mocked — no network access required.
"""

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from backend.services.link_checker_service import (
    extract_urls,
    check_url,
    check_urls,
    load_link_log,
    save_link_log,
    run_link_check,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _mock_client(head_code=200, get_code=None):
    """
    Returns a context-manager mock for httpx.Client that simulates
    HEAD returning head_code; if head_code==405, GET returns get_code.
    """
    head_resp = MagicMock()
    head_resp.status_code = head_code

    get_resp = MagicMock()
    get_resp.status_code = get_code or head_code

    client_instance = MagicMock()
    client_instance.__enter__ = MagicMock(return_value=client_instance)
    client_instance.__exit__ = MagicMock(return_value=False)
    client_instance.head.return_value = head_resp
    client_instance.get.return_value = get_resp
    return client_instance


# ──────────────────────────────────────────────────────────────────────────────
# extract_urls
# ──────────────────────────────────────────────────────────────────────────────

def test_extract_urls_from_href():
    html = '<a href="https://example.com/page">link</a>'
    urls = extract_urls(html)
    assert "https://example.com/page" in urls


def test_extract_urls_from_src():
    html = '<img src="https://example.com/img.png">'
    urls = extract_urls(html)
    assert "https://example.com/img.png" in urls


def test_extract_urls_bare_in_text():
    html = '<p>See https://example.com/paper for details.</p>'
    urls = extract_urls(html)
    assert any("example.com/paper" in u for u in urls)


def test_extract_urls_deduplicates():
    html = '<a href="https://dup.com/">A</a> <a href="https://dup.com/">B</a>'
    urls = extract_urls(html)
    assert urls.count("https://dup.com") == 1


def test_extract_urls_ignores_non_http():
    html = '<a href="ftp://old.example.com">ftp</a> <a href="mailto:a@b.com">mail</a>'
    urls = extract_urls(html)
    assert not any("ftp://" in u or "mailto:" in u for u in urls)


def test_extract_urls_strips_trailing_punctuation():
    html = '<p>Visit https://example.com/page, for more.</p>'
    urls = extract_urls(html)
    assert not any(u.endswith(',') for u in urls)


def test_extract_urls_empty_html():
    assert extract_urls('') == []
    assert extract_urls('<p>No links here.</p>') == []


# ──────────────────────────────────────────────────────────────────────────────
# check_url  (HEAD/GET strategy + status classification)
# ──────────────────────────────────────────────────────────────────────────────

def test_check_url_alive_200():
    with patch("backend.services.link_checker_service.httpx.Client",
               return_value=_mock_client(200)):
        r = check_url("https://example.com")
    assert r["status"] == "alive"
    assert r["http_code"] == 200


def test_check_url_dead_404():
    with patch("backend.services.link_checker_service.httpx.Client",
               return_value=_mock_client(404)):
        r = check_url("https://example.com/gone")
    assert r["status"] == "dead"
    assert r["http_code"] == 404


def test_check_url_redirect_301():
    with patch("backend.services.link_checker_service.httpx.Client",
               return_value=_mock_client(301)):
        r = check_url("https://example.com/moved")
    assert r["status"] == "redirect"


def test_check_url_server_error_500():
    with patch("backend.services.link_checker_service.httpx.Client",
               return_value=_mock_client(500)):
        r = check_url("https://example.com/broken")
    assert r["status"] == "server_error"


def test_check_url_access_denied_403():
    with patch("backend.services.link_checker_service.httpx.Client",
               return_value=_mock_client(403)):
        r = check_url("https://example.com/protected")
    assert r["status"] == "access_denied"


def test_check_url_falls_back_to_get_on_405():
    """HEAD returns 405 → service must fall back to GET."""
    client_mock = _mock_client(head_code=405, get_code=200)
    with patch("backend.services.link_checker_service.httpx.Client",
               return_value=client_mock):
        r = check_url("https://example.com/no-head")
    client_mock.get.assert_called_once()
    assert r["status"] == "alive"


def test_check_url_ssl_error():
    import ssl as _ssl
    client_mock = MagicMock()
    client_mock.__enter__ = MagicMock(return_value=client_mock)
    client_mock.__exit__ = MagicMock(return_value=False)
    client_mock.head.side_effect = _ssl.SSLError("bad cert")
    with patch("backend.services.link_checker_service.httpx.Client",
               return_value=client_mock):
        r = check_url("https://self-signed.example.com")
    assert r["status"] == "ssl_warning"
    assert r["http_code"] is None


def test_check_url_timeout():
    import httpx as _httpx
    client_mock = MagicMock()
    client_mock.__enter__ = MagicMock(return_value=client_mock)
    client_mock.__exit__ = MagicMock(return_value=False)
    client_mock.head.side_effect = _httpx.TimeoutException("timed out")
    with patch("backend.services.link_checker_service.httpx.Client",
               return_value=client_mock):
        r = check_url("https://slow.example.com")
    assert r["status"] == "unreachable"


def test_check_url_connect_error():
    import httpx as _httpx
    client_mock = MagicMock()
    client_mock.__enter__ = MagicMock(return_value=client_mock)
    client_mock.__exit__ = MagicMock(return_value=False)
    client_mock.head.side_effect = _httpx.ConnectError("no route")
    with patch("backend.services.link_checker_service.httpx.Client",
               return_value=client_mock):
        r = check_url("https://dead.example.com")
    assert r["status"] == "unreachable"


def test_check_url_includes_checked_at():
    with patch("backend.services.link_checker_service.httpx.Client",
               return_value=_mock_client(200)):
        r = check_url("https://example.com")
    assert isinstance(r["checked_at"], float)
    assert r["checked_at"] > 0


# ──────────────────────────────────────────────────────────────────────────────
# check_urls  (batch)
# ──────────────────────────────────────────────────────────────────────────────

def test_check_urls_returns_result_per_url():
    with patch("backend.services.link_checker_service.httpx.Client",
               return_value=_mock_client(200)):
        results = check_urls(["https://a.com", "https://b.com"])
    assert len(results) == 2
    assert all(r["status"] == "alive" for r in results)


def test_check_urls_empty_list():
    assert check_urls([]) == []


# ──────────────────────────────────────────────────────────────────────────────
# Log persistence
# ──────────────────────────────────────────────────────────────────────────────

def test_save_and_load_link_log(tmp_path):
    entries = [{"url": "https://x.com", "status": "alive", "http_code": 200, "checked_at": 1234567890.0}]
    save_link_log(str(tmp_path), entries)
    loaded = load_link_log(str(tmp_path))
    assert loaded == entries


def test_load_link_log_missing_file(tmp_path):
    assert load_link_log(str(tmp_path)) == []


def test_load_link_log_corrupt_file(tmp_path):
    path = tmp_path / "link_check_log.json"
    path.write_text("not json")
    assert load_link_log(str(tmp_path)) == []


# ──────────────────────────────────────────────────────────────────────────────
# run_link_check  (end-to-end with mocked HTTP)
# ──────────────────────────────────────────────────────────────────────────────

def test_run_link_check_persists_and_returns_results(tmp_path):
    html = '<a href="https://example.com">link</a>'
    with patch("backend.services.link_checker_service.httpx.Client",
               return_value=_mock_client(200)):
        results = run_link_check(str(tmp_path), html)

    assert any(r["url"] == "https://example.com" and r["status"] == "alive" for r in results)
    log_file = tmp_path / "link_check_log.json"
    assert log_file.exists()


def test_run_link_check_merges_with_existing_log(tmp_path):
    old_entry = {"url": "https://old.com", "status": "alive", "http_code": 200, "checked_at": 1.0}
    save_link_log(str(tmp_path), [old_entry])

    html = '<a href="https://new.com">new</a>'
    with patch("backend.services.link_checker_service.httpx.Client",
               return_value=_mock_client(200)):
        results = run_link_check(str(tmp_path), html)

    urls = {r["url"] for r in results}
    assert "https://old.com" in urls
    assert "https://new.com" in urls


def test_run_link_check_updates_existing_url(tmp_path):
    """A URL that already has an old log entry should be overwritten with fresh result."""
    old_entry = {"url": "https://example.com", "status": "alive", "http_code": 200, "checked_at": 1.0}
    save_link_log(str(tmp_path), [old_entry])

    html = '<a href="https://example.com">link</a>'
    with patch("backend.services.link_checker_service.httpx.Client",
               return_value=_mock_client(404)):
        results = run_link_check(str(tmp_path), html)

    entry = next(r for r in results if r["url"] == "https://example.com")
    assert entry["status"] == "dead"
