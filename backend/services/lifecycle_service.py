# backend/services/lifecycle_service.py
"""
Article Lifecycle State Machine (REQ-3.4.1–3.4.4).

States: draft | submitted | under_review | preprint | published | retracted

Valid transitions:
    draft        → submitted | preprint
    submitted    → under_review | draft
    under_review → published | preprint | draft
    preprint     → published | draft
    published    → retracted
    retracted    → (terminal)

workspace.json lifecycle additions:
    state:          str                          # current state key
    state_history:  [{from, to, timestamp, note}]
    article_doi:    str | null                   # own published DOI
    publisher_url:  str | null
    alerts:         [{type, message, timestamp, acknowledged}]
"""

import json
import os
import re
import time
from typing import Optional

# ---------------------------------------------------------------------------
# State machine constants
# ---------------------------------------------------------------------------

STATES: dict[str, str] = {
    "draft":        "Draft",
    "submitted":    "Submitted",
    "under_review": "Under Review",
    "preprint":     "Pre-print",
    "published":    "Published",
    "retracted":    "Retracted",
}

_INITIAL_STATE = "draft"

_VALID_TRANSITIONS: dict[str, set] = {
    "draft":        {"submitted", "preprint"},
    "submitted":    {"under_review", "draft"},
    "under_review": {"published", "preprint", "draft"},
    "preprint":     {"published", "draft"},
    "published":    {"retracted"},
    "retracted":    set(),
}

_ARTICLE_DOI_ENABLED_STATES: set = {"preprint", "published"}

# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

def _manifest_path(workspace_dir: str) -> str:
    return os.path.join(workspace_dir, "workspace.json")


def _load_manifest(workspace_dir: str) -> dict:
    path = _manifest_path(workspace_dir)
    if not os.path.exists(path):
        raise FileNotFoundError(f"workspace.json not found in {workspace_dir}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_manifest(workspace_dir: str, manifest: dict) -> None:
    with open(_manifest_path(workspace_dir), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def _ensure_lifecycle_fields(manifest: dict) -> dict:
    """Adds lifecycle fields with defaults if absent (supports older workspaces)."""
    manifest.setdefault("state", _INITIAL_STATE)
    manifest.setdefault("state_history", [])
    manifest.setdefault("article_doi", None)
    manifest.setdefault("publisher_url", None)
    manifest.setdefault("alerts", [])
    return manifest


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_state(workspace_dir: str) -> dict:
    """
    Returns the current lifecycle state and related metadata.

    Returns:
        {
            state:               str,
            state_label:         str,
            state_history:       list,
            article_doi:         str | None,
            publisher_url:       str | None,
            alerts:              list,
            allowed_transitions: [str],
        }
    """
    manifest = _ensure_lifecycle_fields(_load_manifest(workspace_dir))
    state = manifest["state"]
    return {
        "state":               state,
        "state_label":         STATES.get(state, state),
        "state_history":       manifest["state_history"],
        "article_doi":         manifest.get("article_doi"),
        "publisher_url":       manifest.get("publisher_url"),
        "alerts":              manifest.get("alerts", []),
        "allowed_transitions": sorted(_VALID_TRANSITIONS.get(state, set())),
    }


def transition_state(workspace_dir: str, new_state: str, note: str = "") -> dict:
    """
    Transitions the article to new_state if the transition is valid.

    Raises:
        ValueError: if new_state is not a valid transition from current state.
        FileNotFoundError: if workspace.json is missing.

    Returns: same structure as get_state().
    """
    manifest = _ensure_lifecycle_fields(_load_manifest(workspace_dir))
    current = manifest["state"]

    if new_state not in STATES:
        raise ValueError(f"Unknown state: {new_state!r}")

    allowed = _VALID_TRANSITIONS.get(current, set())
    if new_state not in allowed:
        raise ValueError(
            f"Transition {current!r} → {new_state!r} is not allowed. "
            f"Valid transitions: {sorted(allowed)}"
        )

    manifest["state"] = new_state
    manifest["state_history"].append({
        "from":      current,
        "to":        new_state,
        "timestamp": time.time(),
        "note":      note,
    })
    _save_manifest(workspace_dir, manifest)
    return get_state(workspace_dir)


def set_article_doi(workspace_dir: str, doi: str, publisher_url: str = "") -> dict:
    """
    Sets the article's own published DOI and optional publisher URL.
    Only permitted when state is preprint or published (REQ-3.4.2).

    Raises:
        ValueError: if state does not permit DOI registration, or DOI format invalid.

    Returns: same structure as get_state().
    """
    manifest = _ensure_lifecycle_fields(_load_manifest(workspace_dir))
    state = manifest["state"]
    if state not in _ARTICLE_DOI_ENABLED_STATES:
        raise ValueError(
            f"Article DOI can only be set in states: "
            f"{sorted(_ARTICLE_DOI_ENABLED_STATES)}. Current state: {state!r}"
        )

    doi_clean = doi.strip()
    if doi_clean and not re.match(r"^10\.\d{4,}/", doi_clean):
        raise ValueError(f"Invalid DOI format: {doi_clean!r}")

    manifest["article_doi"] = doi_clean or None
    manifest["publisher_url"] = publisher_url.strip() or None
    _save_manifest(workspace_dir, manifest)
    return get_state(workspace_dir)


def add_alert(workspace_dir: str, alert_type: str, message: str) -> dict:
    """
    Appends an adverse-event alert to workspace.json and alerts.log (REQ-3.4.4).
    Idempotent: deduplicates the same (type, message) within a 24h window.

    Returns: the alert dict (new or existing duplicate).
    """
    manifest = _ensure_lifecycle_fields(_load_manifest(workspace_dir))
    now = time.time()

    # Dedup within 24 h
    window = now - 86400
    for existing in manifest["alerts"]:
        if (
            existing.get("type") == alert_type
            and existing.get("message") == message
            and existing.get("timestamp", 0) > window
        ):
            return existing

    alert = {
        "type":         alert_type,
        "message":      message,
        "timestamp":    now,
        "acknowledged": False,
    }
    manifest["alerts"].append(alert)
    _save_manifest(workspace_dir, manifest)

    # Append to human-readable log
    log_path = os.path.join(workspace_dir, "alerts.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}] "
            f"[{alert_type}] {message}\n"
        )

    return alert


def acknowledge_alerts(workspace_dir: str) -> dict:
    """
    Marks all unacknowledged alerts as acknowledged.
    Returns: same structure as get_state().
    """
    manifest = _ensure_lifecycle_fields(_load_manifest(workspace_dir))
    for alert in manifest.get("alerts", []):
        alert["acknowledged"] = True
    _save_manifest(workspace_dir, manifest)
    return get_state(workspace_dir)


def poll_article_doi(workspace_dir: str) -> Optional[dict]:
    """
    Queries Crossref for the article's own DOI (REQ-3.4.3).
    Generates alerts for retraction / correction / expression-of-concern.

    Returns the newly created alert dict if an adverse event was detected, else None.
    """
    try:
        manifest = _ensure_lifecycle_fields(_load_manifest(workspace_dir))
        doi = manifest.get("article_doi")
        if not doi:
            return None

        from backend.services.doi_service import validate_doi
        result = validate_doi(doi)
        status = result.get("status", "valid")

        if status in ("retracted", "corrected", "expression-of-concern"):
            flag_reason = result.get("flag_reason", "")
            message = (
                f"Article DOI {doi} has status '{status}'."
                + (f" Reason: {flag_reason}" if flag_reason else "")
            )
            return add_alert(workspace_dir, status, message)

    except Exception:
        pass

    return None
