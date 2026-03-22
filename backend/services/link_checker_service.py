# backend/services/link_checker_service.py

"""
URL / Link-Rot Detection service.
Extracts HTTP/HTTPS URLs from saved HTML, checks each one using a HEAD-then-GET
strategy, and persists results to a per-workspace link-check log.
REQ-3.3.3
"""

import json
import os
import re
import ssl as _ssl
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from typing import Optional

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_WORKERS = 5           # concurrent requests (REQ-3.3.3 cap)
_REQUEST_TIMEOUT = 10.0    # seconds per request
_MAX_REDIRECTS = 5
_LOG_FILENAME = "link_check_log.json"

# HTTP status → link status classification
_STATUS_ALIVE   = "alive"
_STATUS_DEAD    = "dead"
_STATUS_REDIRECT = "redirect"
_STATUS_SERVER_ERROR = "server_error"
_STATUS_ACCESS_DENIED = "access_denied"
_STATUS_UNREACHABLE = "unreachable"
_STATUS_SSL_WARNING = "ssl_warning"
_STATUS_UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# URL extraction
# ---------------------------------------------------------------------------

class _LinkExtractor(HTMLParser):
    """Collects href/src values that start with http:// or https://."""

    def __init__(self):
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag, attrs):
        for attr, value in attrs:
            if attr in ("href", "src") and value and re.match(r"https?://", value, re.I):
                self.urls.append(value.split("#")[0].rstrip("/"))  # strip fragment & trailing slash


def extract_urls(html_content: str) -> list[str]:
    """
    Extracts unique HTTP/HTTPS URLs from an HTML document.
    Also scans plain text (not just attributes) for bare URLs.
    """
    parser = _LinkExtractor()
    parser.feed(html_content)

    # Also find bare URLs in text nodes via regex
    bare = re.findall(r"https?://[^\s<>\"')\]]+", html_content)
    all_urls = parser.urls + bare

    seen: set[str] = set()
    unique: list[str] = []
    for url in all_urls:
        url = url.rstrip(".,;:)}]")
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


# ---------------------------------------------------------------------------
# Single URL check
# ---------------------------------------------------------------------------

def _classify_status_code(code: int) -> str:
    if 200 <= code <= 299:
        return _STATUS_ALIVE
    if code in (301, 302, 303, 307, 308):
        return _STATUS_REDIRECT
    if code == 403:
        return _STATUS_ACCESS_DENIED
    if code == 404:
        return _STATUS_DEAD
    if 500 <= code <= 599:
        return _STATUS_SERVER_ERROR
    return _STATUS_UNKNOWN


def check_url(url: str) -> dict:
    """
    Checks a single URL using HEAD first, falls back to GET on 405.
    Follows up to _MAX_REDIRECTS hops.

    Returns:
        { url, status, http_code, checked_at }
    status ∈ { alive, dead, redirect, server_error, access_denied,
               unreachable, ssl_warning, unknown }
    """
    checked_at = time.time()
    http_code: Optional[int] = None

    try:
        with httpx.Client(
            timeout=_REQUEST_TIMEOUT,
            max_redirects=_MAX_REDIRECTS,
            follow_redirects=True,
            verify=True,
        ) as client:
            try:
                resp = client.head(url)
            except httpx.HTTPStatusError:
                resp = None
            else:
                if resp.status_code == 405:
                    resp = client.get(url)

            if resp is not None:
                http_code = resp.status_code
                link_status = _classify_status_code(http_code)
                return {"url": url, "status": link_status, "http_code": http_code, "checked_at": checked_at}

    except _ssl.SSLError:
        return {"url": url, "status": _STATUS_SSL_WARNING, "http_code": None, "checked_at": checked_at}
    except (httpx.ConnectError, socket.gaierror, OSError):
        return {"url": url, "status": _STATUS_UNREACHABLE, "http_code": None, "checked_at": checked_at}
    except (httpx.TimeoutException, httpx.ReadTimeout, httpx.ConnectTimeout):
        return {"url": url, "status": _STATUS_UNREACHABLE, "http_code": None, "checked_at": checked_at}
    except Exception:
        pass

    return {"url": url, "status": _STATUS_UNKNOWN, "http_code": http_code, "checked_at": checked_at}


# ---------------------------------------------------------------------------
# Batch check (concurrency-limited)
# ---------------------------------------------------------------------------

def check_urls(urls: list[str]) -> list[dict]:
    """
    Checks all provided URLs with up to _MAX_WORKERS concurrent requests.
    Returns results in the same order as the input list.
    """
    if not urls:
        return []

    results: dict[str, dict] = {}

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(check_url, url): url for url in urls}
        for future in as_completed(futures):
            result = future.result()
            results[result["url"]] = result

    return [results.get(url, {"url": url, "status": _STATUS_UNKNOWN, "http_code": None, "checked_at": time.time()}) for url in urls]


# ---------------------------------------------------------------------------
# Workspace log persistence
# ---------------------------------------------------------------------------

def _log_path(workspace_dir: str) -> str:
    return os.path.join(workspace_dir, _LOG_FILENAME)


def load_link_log(workspace_dir: str) -> list[dict]:
    """Loads the existing link-check log for the workspace, or returns []."""
    path = _log_path(workspace_dir)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_link_log(workspace_dir: str, entries: list[dict]) -> None:
    """Writes the link-check log to disk."""
    with open(_log_path(workspace_dir), "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


def run_link_check(workspace_dir: str, html_content: str) -> list[dict]:
    """
    Extracts URLs from html_content, checks each one, merges with the
    existing log (most-recent result per URL wins), persists to disk,
    and returns the updated log.
    """
    urls = extract_urls(html_content)
    fresh = check_urls(urls)

    # Merge: start from old log, overwrite with fresh results
    old_log = load_link_log(workspace_dir)
    by_url: dict[str, dict] = {entry["url"]: entry for entry in old_log}
    for entry in fresh:
        by_url[entry["url"]] = entry

    merged = list(by_url.values())
    save_link_log(workspace_dir, merged)
    return merged
