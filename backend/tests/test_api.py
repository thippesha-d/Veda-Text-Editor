import os
import tempfile
import pytest
from fastapi.testclient import TestClient

# Mock the environment variable BEFORE importing app to isolate tests
os.environ["WORKSPACE_DIR"] = tempfile.mkdtemp()

from backend.main import app

client = TestClient(app)

def test_save_document():
    # First create a workspace so there's a valid git repo to commit into
    create_res = client.post("/api/workspace/create", json={"name": "Save Test Workspace"})
    ws_path = create_res.json()["path"]
    response = client.put("/api/document/save", json={"html": "<p>API Test</p>", "workspace_path": ws_path})
    assert response.status_code == 200
    assert response.json()["status"] == "success"

def test_upload_media():
    files = {"file": ("test.png", b"fake_png_data", "image/png")}
    response = client.post("/api/media/upload", files=files)
    assert response.status_code == 200
    assert "url" in response.json()

def test_create_workspace():
    response = client.post("/api/workspace/create", json={"name": "API New Paper"})
    assert response.status_code == 200
    data = response.json()
    assert "workspace_id" in data
    assert "git_sha" in data

def test_trigger_commit_and_status():
    # Setup workspace
    create_res = client.post("/api/workspace/create", json={"name": "Auto Commit Test API"})
    ws_path = create_res.json()["path"]
    
    # Make a manual edit to the file so it's dirty
    with open(os.path.join(ws_path, "article.html"), "a", encoding="utf-8") as f:
        f.write("<p>Auto commit change</p>")

    # Trigger Commit
    res = client.post("/api/document/commit", json={"workspace_path": ws_path, "trigger": "Timer"})
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    
    # Poll Status
    res_status = client.get(f"/api/workspace/status?workspace_path={ws_path}")
    assert res_status.status_code == 200
    data = res_status.json()
    assert data["git_sha"] is not None
    assert data["last_auto_commit"] is not None


# ──────────────────────────────────────────────────────────────────
# REGRESSION TESTS — Issues fixed during development
# ──────────────────────────────────────────────────────────────────

def test_save_writes_to_workspace_folder():
    """REG-01: Save must write article.html inside the specific workspace, not the global dir."""
    create_res = client.post("/api/workspace/create", json={"name": "Reg Save Workspace"})
    ws_path = create_res.json()["path"]

    content = "<p>Regression content</p>"
    res = client.put("/api/document/save", json={"html": content, "workspace_path": ws_path})
    assert res.status_code == 200

    # Verify file landed in the right workspace folder
    article_path = os.path.join(ws_path, "article.html")
    assert os.path.exists(article_path), "article.html must be inside the workspace folder"
    with open(article_path, encoding="utf-8") as f:
        assert content in f.read()


def test_save_triggers_git_commit():
    """REG-02: Saving a document must create a git commit so history is preserved."""
    import subprocess
    create_res = client.post("/api/workspace/create", json={"name": "Reg Commit Workspace"})
    ws_path = create_res.json()["path"]

    # First save (initial commit may already exist from workspace init; save again with content)
    client.put("/api/document/save", json={"html": "<p>Commit test</p>", "workspace_path": ws_path})

    # Check git log — there should be at least one commit
    result = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=ws_path, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert len(result.stdout.strip().splitlines()) >= 1, "Expected at least one git commit after save"


def test_media_upload_stored_in_workspace():
    """REG-03: Uploaded images must land in the workspace assets/ subfolder, not a global folder."""
    create_res = client.post("/api/workspace/create", json={"name": "Reg Asset Workspace"})
    ws_path = create_res.json()["path"]

    files = {"file": ("photo.png", b"fake_png_bytes", "image/png")}
    data = {"workspace_path": ws_path}
    res = client.post("/api/media/upload", files=files, data=data)
    assert res.status_code == 200

    # Verify the file landed inside the workspace assets/
    assets_dir = os.path.join(ws_path, "assets")
    assert os.path.isdir(assets_dir), "assets/ folder must be created inside the workspace"
    saved_files = os.listdir(assets_dir)
    assert len(saved_files) == 1, "Exactly one asset should be saved"


def test_media_upload_url_is_workspace_scoped():
    """REG-04: The returned URL must reference the specific workspace folder, not /assets/."""
    create_res = client.post("/api/workspace/create", json={"name": "Reg URL Workspace"})
    ws_path = create_res.json()["path"]

    files = {"file": ("chart.png", b"fake_png_bytes", "image/png")}
    data = {"workspace_path": ws_path}
    res = client.post("/api/media/upload", files=files, data=data)
    assert res.status_code == 200

    url = res.json()["url"]
    assert url.startswith("/api/workspace/assets/"), \
        f"URL must be workspace-scoped, got: {url}"
    assert "/assets/" not in url.replace("/api/workspace/assets/", ""), \
        "URL must not fall back to the old global /assets/ route"


def test_media_upload_without_workspace_falls_back_gracefully():
    """REG-05: Upload with no workspace_path must not crash — graceful fallback to global dir."""
    files = {"file": ("fallback.png", b"fake_png_bytes", "image/png")}
    res = client.post("/api/media/upload", files=files)
    assert res.status_code == 200
    assert "url" in res.json()


# ──────────────────────────────────────────────────────────────────
# REQ-3.2.3 — Branch API Endpoint Tests
# ──────────────────────────────────────────────────────────────────

def _new_workspace(name: str) -> str:
    """Helper: create a workspace and return its path."""
    res = client.post("/api/workspace/create", json={"name": name})
    assert res.status_code == 200
    return res.json()["path"]


def test_api_branch_list():
    """GET /api/branch/list must return at least one branch after workspace creation."""
    ws = _new_workspace("Branch List WS")
    res = client.get("/api/branch/list", params={"workspace_path": ws})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert isinstance(data["branches"], list)
    assert len(data["branches"]) >= 1
    assert any(b["active"] for b in data["branches"])


def test_api_branch_create():
    """POST /api/branch/create must create a new branch visible in list."""
    ws = _new_workspace("Branch Create WS")
    res = client.post("/api/branch/create", json={
        "workspace_path": ws,
        "branch_name": "test-feature",
        "base_branch": "",
    })
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert res.json()["branch_name"] == "test-feature"

    list_res = client.get("/api/branch/list", params={"workspace_path": ws})
    names = [b["name"] for b in list_res.json()["branches"]]
    assert "test-feature" in names


def test_api_branch_switch():
    """POST /api/branch/switch must change the active branch."""
    ws = _new_workspace("Branch Switch WS")
    client.post("/api/branch/create", json={"workspace_path": ws, "branch_name": "switch-target", "base_branch": ""})

    res = client.post("/api/branch/switch", json={"workspace_path": ws, "branch_name": "switch-target"})
    assert res.status_code == 200
    assert res.json()["branch_name"] == "switch-target"
    assert "worktree_path" in res.json()


def test_api_branch_delete():
    """DELETE /api/branch/delete must remove a non-active branch."""
    ws = _new_workspace("Branch Delete WS")
    client.post("/api/branch/create", json={"workspace_path": ws, "branch_name": "to-delete", "base_branch": ""})

    res = client.request("DELETE", "/api/branch/delete", json={"workspace_path": ws, "branch_name": "to-delete"})
    assert res.status_code == 200
    assert res.json()["removed_branch"] == "to-delete"

    list_res = client.get("/api/branch/list", params={"workspace_path": ws})
    names = [b["name"] for b in list_res.json()["branches"]]
    assert "to-delete" not in names


def test_api_switch_then_load_returns_new_content():
    """
    Full switch flow: create worktree → write unique content → switch → load.
    Verifies that /api/document/load returns the new worktree's content after switch,
    not the original workspace content. This is the exact bug that was reported.
    """
    import os
    ws = _new_workspace("Switch Load WS")

    # Create feature worktree
    create_res = client.post("/api/branch/create", json={
        "workspace_path": ws,
        "branch_name": "feature-load",
    })
    assert create_res.status_code == 200
    worktree_path = create_res.json()["worktree_path"]

    # Write unique content directly into the feature worktree
    with open(os.path.join(worktree_path, "article.html"), "w", encoding="utf-8") as f:
        f.write("<p>Feature-specific content</p>")

    # Switch returns the worktree path
    switch_res = client.post("/api/branch/switch", json={
        "workspace_path": ws,
        "branch_name": "feature-load",
    })
    assert switch_res.status_code == 200
    new_path = switch_res.json()["worktree_path"]

    # Load document from the new worktree path — must contain feature content
    load_res = client.get("/api/document/load", params={"workspace_path": new_path})
    assert load_res.status_code == 200
    assert "Feature-specific content" in load_res.json()["html"]

    # Load from original path — must still contain original content
    orig_load = client.get("/api/document/load", params={"workspace_path": ws})
    assert orig_load.status_code == 200
    assert "Feature-specific content" not in orig_load.json()["html"]


def test_api_branch_create_duplicate_returns_400():
    """POST /api/branch/create with a duplicate name must return HTTP 400."""
    ws = _new_workspace("Branch Dup WS")
    client.post("/api/branch/create", json={"workspace_path": ws, "branch_name": "dup-branch", "base_branch": ""})
    res = client.post("/api/branch/create", json={"workspace_path": ws, "branch_name": "dup-branch", "base_branch": ""})
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"]


# ──────────────────────────────────────────────────────────────────────────────
# REQ-3.3.1 / REQ-3.3.2  —  DOI validation endpoint
# ──────────────────────────────────────────────────────────────────────────────

def test_api_validate_dois_empty_list():
    """POST /api/references/validate with empty list must return empty results."""
    res = client.post("/api/references/validate", json={"dois": []})
    assert res.status_code == 200
    assert res.json()["results"] == []


def test_api_validate_dois_returns_result_per_doi():
    """Each DOI in the request must produce exactly one result entry."""
    from unittest.mock import patch
    from backend.services import doi_service

    doi_service.clear_cache()

    fake_result = {
        "doi": "10.1234/test",
        "status": "valid",
        "title": "Mock Paper",
        "authors": ["Alice Smith"],
        "year": 2023,
        "flag_reason": "",
    }
    with patch("backend.services.doi_service.httpx.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "message": {
                "title": ["Mock Paper"],
                "author": [{"given": "Alice", "family": "Smith"}],
                "published-print": {"date-parts": [[2023]]},
            }
        }
        res = client.post("/api/references/validate", json={"dois": ["10.1234/test"]})

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert len(data["results"]) == 1
    r = data["results"][0]
    assert r["doi"] == "10.1234/test"
    assert r["status"] == "valid"
    assert r["title"] == "Mock Paper"
    assert r["year"] == 2023


def test_api_validate_dois_caps_at_20():
    """Requests with more than 20 DOIs must only process the first 20."""
    from unittest.mock import patch
    from backend.services.doi_service import clear_cache

    clear_cache()

    many_dois = [f"10.{1000 + i}/x" for i in range(25)]
    with patch("backend.services.doi_service.httpx.get") as mock_get:
        mock_get.return_value.status_code = 404
        res = client.post("/api/references/validate", json={"dois": many_dois})

    assert res.status_code == 200
    assert len(res.json()["results"]) == 20


# ──────────────────────────────────────────────────────────────────────────────
# REQ-3.3.3  —  Link-check endpoints
# ──────────────────────────────────────────────────────────────────────────────

def test_api_link_check_returns_results():
    """POST /api/links/check must return a result entry per extracted URL."""
    from unittest.mock import patch, MagicMock

    ws = _new_workspace("LinkCheck WS")
    html = '<a href="https://example.com">link</a>'

    head_resp = MagicMock()
    head_resp.status_code = 200
    client_mock = MagicMock()
    client_mock.__enter__ = MagicMock(return_value=client_mock)
    client_mock.__exit__ = MagicMock(return_value=False)
    client_mock.head.return_value = head_resp

    with patch("backend.services.link_checker_service.httpx.Client", return_value=client_mock):
        res = client.post("/api/links/check", json={"workspace_path": ws, "html_content": html})

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert any(r["url"] == "https://example.com" for r in data["results"])


def test_api_link_check_unknown_workspace():
    """POST /api/links/check with a non-existent path must return 404."""
    res = client.post("/api/links/check", json={
        "workspace_path": "/nonexistent/path",
        "html_content": "<p>hi</p>"
    })
    assert res.status_code == 404


def test_api_link_status_returns_log():
    """GET /api/links/status must return the persisted log."""
    from unittest.mock import patch, MagicMock
    from backend.services.link_checker_service import save_link_log

    ws = _new_workspace("LinkStatus WS")
    save_link_log(ws, [{"url": "https://stored.com", "status": "alive", "http_code": 200, "checked_at": 1.0}])

    res = client.get("/api/links/status", params={"workspace_path": ws})
    assert res.status_code == 200
    data = res.json()
    assert any(r["url"] == "https://stored.com" for r in data["results"])


# ──────────────────────────────────────────────────────────────────────────────
# REQ-3.3.4  —  Citation formatting endpoints
# ──────────────────────────────────────────────────────────────────────────────

_SAMPLE_REF = {
    "id":              "smith2020",
    "type":            "article-journal",
    "title":           "A Test Paper",
    "author":          [{"family": "Smith", "given": "John"}],
    "issued":          {"date-parts": [[2020]]},
    "container-title": "Test Journal",
    "volume":          "5",
    "page":            "1-10",
    "DOI":             "10.9999/test",
}


def test_api_citations_format_apa():
    res = client.post("/api/citations/format", json={
        "references":    [_SAMPLE_REF],
        "citation_keys": ["smith2020"],
        "style":         "apa",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "smith2020" in data["inline_map"]
    assert "Smith" in data["inline_map"]["smith2020"]
    assert data["bibliography_html"] != ""
    assert data["unresolved_keys"] == []


def test_api_citations_format_ieee_numeric():
    res = client.post("/api/citations/format", json={
        "references":    [_SAMPLE_REF],
        "citation_keys": ["smith2020"],
        "style":         "ieee",
    })
    assert res.status_code == 200
    assert res.json()["inline_map"]["smith2020"] == "[1]"


def test_api_citations_unresolved_key():
    res = client.post("/api/citations/format", json={
        "references":    [_SAMPLE_REF],
        "citation_keys": ["smith2020", "ghost_key"],
        "style":         "apa",
    })
    assert res.status_code == 200
    assert "ghost_key" in res.json()["unresolved_keys"]


def test_api_citations_empty_request():
    res = client.post("/api/citations/format", json={
        "references": [], "citation_keys": [], "style": "apa"
    })
    assert res.status_code == 200
    assert res.json()["inline_map"] == {}


def test_api_citations_list_styles():
    res = client.get("/api/citations/styles")
    assert res.status_code == 200
    ids = [s["id"] for s in res.json()["styles"]]
    for style in ("apa", "ieee", "nature", "chicago", "vancouver", "harvard"):
        assert style in ids
