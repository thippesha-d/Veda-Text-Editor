# backend/tests/test_lifecycle_service.py

"""
Unit tests for the article lifecycle state machine (REQ-3.4.1–3.4.4).
All tests use a temporary directory — no network access required.
"""

import json
import os
import time
import pytest

from backend.services.lifecycle_service import (
    get_state,
    transition_state,
    set_article_doi,
    add_alert,
    acknowledge_alerts,
    poll_article_doi,
    STATES,
    _VALID_TRANSITIONS,
    _INITIAL_STATE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_workspace(tmp_path, state=None, article_doi=None):
    """Creates a minimal workspace.json in tmp_path."""
    manifest = {
        "workspace_id": "test-id",
        "name": "Test",
        "created_at": time.time(),
        "git_sha": "abc123",
        "assets": [],
    }
    if state:
        manifest["state"] = state
    if article_doi:
        manifest["article_doi"] = article_doi
    path = tmp_path / "workspace.json"
    path.write_text(json.dumps(manifest))
    return str(tmp_path)


# ---------------------------------------------------------------------------
# STATES constant
# ---------------------------------------------------------------------------

def test_states_contains_all_required():
    required = {"draft", "submitted", "under_review", "preprint", "published", "retracted"}
    assert required == set(STATES.keys())


# ---------------------------------------------------------------------------
# get_state — defaults for new workspace
# ---------------------------------------------------------------------------

def test_get_state_defaults_to_draft(tmp_path):
    ws = _make_workspace(tmp_path)
    data = get_state(ws)
    assert data["state"] == "draft"
    assert data["state_label"] == "Draft"
    assert data["state_history"] == []
    assert data["article_doi"] is None
    assert data["publisher_url"] is None
    assert data["alerts"] == []


def test_get_state_allowed_transitions_from_draft(tmp_path):
    ws = _make_workspace(tmp_path)
    data = get_state(ws)
    assert set(data["allowed_transitions"]) == {"submitted", "preprint"}


def test_get_state_raises_for_missing_workspace(tmp_path):
    with pytest.raises(FileNotFoundError):
        get_state(str(tmp_path / "nonexistent"))


# ---------------------------------------------------------------------------
# transition_state — valid transitions
# ---------------------------------------------------------------------------

def test_transition_draft_to_submitted(tmp_path):
    ws = _make_workspace(tmp_path)
    result = transition_state(ws, "submitted")
    assert result["state"] == "submitted"


def test_transition_draft_to_preprint(tmp_path):
    ws = _make_workspace(tmp_path)
    result = transition_state(ws, "preprint")
    assert result["state"] == "preprint"


def test_transition_submitted_to_under_review(tmp_path):
    ws = _make_workspace(tmp_path, state="submitted")
    result = transition_state(ws, "under_review")
    assert result["state"] == "under_review"


def test_transition_under_review_to_published(tmp_path):
    ws = _make_workspace(tmp_path, state="under_review")
    result = transition_state(ws, "published")
    assert result["state"] == "published"


def test_transition_published_to_retracted(tmp_path):
    ws = _make_workspace(tmp_path, state="published")
    result = transition_state(ws, "retracted")
    assert result["state"] == "retracted"
    assert result["allowed_transitions"] == []


def test_transition_records_history(tmp_path):
    ws = _make_workspace(tmp_path)
    transition_state(ws, "submitted", note="First submission")
    data = get_state(ws)
    assert len(data["state_history"]) == 1
    entry = data["state_history"][0]
    assert entry["from"] == "draft"
    assert entry["to"] == "submitted"
    assert entry["note"] == "First submission"
    assert entry["timestamp"] > 0


def test_transition_persists_to_manifest(tmp_path):
    ws = _make_workspace(tmp_path)
    transition_state(ws, "submitted")
    manifest = json.loads((tmp_path / "workspace.json").read_text())
    assert manifest["state"] == "submitted"


# ---------------------------------------------------------------------------
# transition_state — invalid transitions
# ---------------------------------------------------------------------------

def test_transition_invalid_raises_value_error(tmp_path):
    ws = _make_workspace(tmp_path)
    with pytest.raises(ValueError, match="not allowed"):
        transition_state(ws, "published")


def test_transition_unknown_state_raises_value_error(tmp_path):
    ws = _make_workspace(tmp_path)
    with pytest.raises(ValueError, match="Unknown state"):
        transition_state(ws, "rejected")


def test_transition_retracted_is_terminal(tmp_path):
    ws = _make_workspace(tmp_path, state="retracted")
    with pytest.raises(ValueError):
        transition_state(ws, "draft")


# ---------------------------------------------------------------------------
# set_article_doi
# ---------------------------------------------------------------------------

def test_set_article_doi_in_preprint(tmp_path):
    ws = _make_workspace(tmp_path, state="preprint")
    result = set_article_doi(ws, "10.1234/test.2024")
    assert result["article_doi"] == "10.1234/test.2024"


def test_set_article_doi_in_published(tmp_path):
    ws = _make_workspace(tmp_path, state="published")
    result = set_article_doi(ws, "10.1234/test.2024", publisher_url="https://example.com")
    assert result["article_doi"] == "10.1234/test.2024"
    assert result["publisher_url"] == "https://example.com"


def test_set_article_doi_rejected_in_draft(tmp_path):
    ws = _make_workspace(tmp_path)
    with pytest.raises(ValueError, match="only be set"):
        set_article_doi(ws, "10.1234/test.2024")


def test_set_article_doi_invalid_format(tmp_path):
    ws = _make_workspace(tmp_path, state="preprint")
    with pytest.raises(ValueError, match="Invalid DOI"):
        set_article_doi(ws, "not-a-doi")


def test_set_article_doi_empty_clears(tmp_path):
    ws = _make_workspace(tmp_path, state="preprint", article_doi="10.1234/old")
    result = set_article_doi(ws, "")
    assert result["article_doi"] is None


# ---------------------------------------------------------------------------
# add_alert / acknowledge_alerts
# ---------------------------------------------------------------------------

def test_add_alert_appended_to_manifest(tmp_path):
    ws = _make_workspace(tmp_path)
    add_alert(ws, "retracted", "Article was retracted.")
    data = get_state(ws)
    assert len(data["alerts"]) == 1
    assert data["alerts"][0]["type"] == "retracted"
    assert not data["alerts"][0]["acknowledged"]


def test_add_alert_writes_log_file(tmp_path):
    ws = _make_workspace(tmp_path)
    add_alert(ws, "corrected", "Correction issued.")
    log_path = tmp_path / "alerts.log"
    assert log_path.exists()
    assert "corrected" in log_path.read_text()


def test_add_alert_deduplicates_within_24h(tmp_path):
    ws = _make_workspace(tmp_path)
    add_alert(ws, "retracted", "Same message.")
    add_alert(ws, "retracted", "Same message.")
    data = get_state(ws)
    assert len(data["alerts"]) == 1


def test_acknowledge_alerts(tmp_path):
    ws = _make_workspace(tmp_path)
    add_alert(ws, "retracted", "Article retracted.")
    result = acknowledge_alerts(ws)
    assert all(a["acknowledged"] for a in result["alerts"])


# ---------------------------------------------------------------------------
# poll_article_doi — no DOI registered
# ---------------------------------------------------------------------------

def test_poll_no_doi_returns_none(tmp_path):
    ws = _make_workspace(tmp_path)
    result = poll_article_doi(ws)
    assert result is None


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def test_full_lifecycle_pipeline(tmp_path):
    ws = _make_workspace(tmp_path)
    # Draft → Submitted → Under Review → Published → Retracted
    transition_state(ws, "submitted")
    transition_state(ws, "under_review")
    transition_state(ws, "published")
    set_article_doi(ws, "10.5678/my.article")
    transition_state(ws, "retracted")

    data = get_state(ws)
    assert data["state"] == "retracted"
    assert data["article_doi"] == "10.5678/my.article"
    assert len(data["state_history"]) == 4
    assert data["allowed_transitions"] == []
