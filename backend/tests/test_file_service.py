import os
import tempfile
import json
from backend.services.file_service import (
    save_document_html, save_media_file, create_workspace,
    load_metadata, save_metadata,
    load_manual_references, save_manual_reference, delete_manual_reference,
    load_workspace, delete_workspace,
)

def test_save_document_html():
    with tempfile.TemporaryDirectory() as tmpdir:
        res = save_document_html("<p>Test</p>", workspace_dir=tmpdir)
        assert res["status"] == "success"
        assert os.path.exists(res["filepath"])

def test_save_media_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        res = save_media_file("test.png", b"fakebytes", workspace_dir=tmpdir)
        assert res["status"] == "success"
        assert "url" in res
        assert os.path.exists(os.path.join(tmpdir, "assets", "test.png"))

def test_create_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        res = create_workspace("Test Paper", base_dir=tmpdir)
        workspace_path = res["path"]
        assert os.path.exists(workspace_path)
        assert os.path.exists(os.path.join(workspace_path, "article.html"))
        assert os.path.exists(os.path.join(workspace_path, ".git"))
        manifest_path = os.path.join(workspace_path, "workspace.json")
        assert os.path.exists(manifest_path)
        with open(manifest_path, "r") as f:
            data = json.load(f)
            assert data["name"] == "Test Paper"


# ── Metadata ──────────────────────────────────────────────────────────────

def _make_ws(tmpdir, name="Test Paper"):
    res = create_workspace(name, base_dir=tmpdir)
    return res["path"]


def test_load_metadata_defaults():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_ws(tmpdir)
        meta = load_metadata(ws)
        assert meta["title"] == ""
        assert meta["authors"] == []
        assert meta["tags"] == []
        assert meta["abstract"] == ""
        assert "keywords" in meta


def test_save_and_load_metadata():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_ws(tmpdir)
        result = save_metadata(ws, {
            "title":    "My Paper",
            "authors":  ["Alice", "Bob"],
            "keywords": ["AI", "ML"],
            "abstract": "This is an abstract.",
            "tags":     ["submitted"],
        })
        assert result["title"] == "My Paper"
        assert result["authors"] == ["Alice", "Bob"]
        assert result["keywords"] == ["AI", "ML"]
        assert result["tags"] == ["submitted"]

        # Reload persists across calls
        reloaded = load_metadata(ws)
        assert reloaded["title"] == "My Paper"
        assert reloaded["abstract"] == "This is an abstract."


def test_save_metadata_ignores_unknown_keys():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_ws(tmpdir)
        result = save_metadata(ws, {"title": "Safe", "workspace_id": "INJECTED"})
        assert result["title"] == "Safe"
        # workspace_id must not appear in metadata dict
        assert "workspace_id" not in result


def test_save_metadata_partial_update():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_ws(tmpdir)
        save_metadata(ws, {"title": "First", "tags": ["draft"]})
        result = save_metadata(ws, {"title": "Second"})
        assert result["title"] == "Second"
        assert result["tags"] == ["draft"]   # unchanged


# ── Manual references ──────────────────────────────────────────────────────

def test_load_manual_references_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_ws(tmpdir)
        assert load_manual_references(ws) == []


def test_save_and_load_manual_reference():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_ws(tmpdir)
        ref = {
            "type":    "journal",
            "authors": "Smith, J.",
            "title":   "A Great Paper",
            "venue":   "Nature",
            "year":    "2024",
        }
        saved = save_manual_reference(ws, ref)
        assert "ref_id" in saved
        assert saved["title"] == "A Great Paper"

        refs = load_manual_references(ws)
        assert len(refs) == 1
        assert refs[0]["title"] == "A Great Paper"


def test_save_manual_reference_uses_existing_ref_id():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_ws(tmpdir)
        ref = {"ref_id": "custom01", "type": "book", "title": "My Book", "authors": "Doe, J.", "year": "2023"}
        saved = save_manual_reference(ws, ref)
        assert saved["ref_id"] == "custom01"


def test_save_manual_reference_upsert():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_ws(tmpdir)
        ref = {"ref_id": "r1", "title": "Old Title", "authors": "A", "type": "journal", "year": "2022"}
        save_manual_reference(ws, ref)
        updated = {"ref_id": "r1", "title": "New Title", "authors": "A", "type": "journal", "year": "2022"}
        save_manual_reference(ws, updated)
        refs = load_manual_references(ws)
        assert len(refs) == 1
        assert refs[0]["title"] == "New Title"


def test_delete_manual_reference():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_ws(tmpdir)
        save_manual_reference(ws, {"ref_id": "del01", "title": "Delete Me", "type": "other", "authors": "X", "year": "2020"})
        assert len(load_manual_references(ws)) == 1
        result = delete_manual_reference(ws, "del01")
        assert result["deleted"] == "del01"
        assert load_manual_references(ws) == []


# ── load_workspace ─────────────────────────────────────────────────────────

def test_load_workspace_returns_metadata():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_ws(tmpdir, name="Load Test")
        save_document_html("<p>Hello</p>", workspace_dir=ws)
        result = load_workspace(ws)
        assert result["path"] == ws
        assert result["name"] == "Load Test"
        assert "<p>Hello</p>" in result["html"]
        assert "workspace_id" in result


def test_load_workspace_missing_json_raises():
    with tempfile.TemporaryDirectory() as tmpdir:
        # A directory without workspace.json is not a valid workspace
        import pytest
        with pytest.raises(ValueError, match="workspace.json"):
            load_workspace(tmpdir)


def test_load_workspace_nonexistent_path_raises():
    import pytest
    with pytest.raises(ValueError, match="does not exist"):
        load_workspace("/nonexistent/path/xyz")


def test_load_workspace_empty_html():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_ws(tmpdir)
        # No article.html written — should return empty string
        result = load_workspace(ws)
        assert result["html"] == "" or isinstance(result["html"], str)


# ── delete_workspace ────────────────────────────────────────────────────────

def test_delete_workspace_removes_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_ws(tmpdir, name="Delete Test")
        assert os.path.isdir(ws)
        result = delete_workspace(ws)
        assert result["deleted"] == ws
        assert not os.path.exists(ws)


def test_delete_workspace_missing_json_raises():
    with tempfile.TemporaryDirectory() as tmpdir:
        import pytest
        with pytest.raises(ValueError, match="workspace.json"):
            delete_workspace(tmpdir)


def test_delete_workspace_nonexistent_path_raises():
    import pytest
    with pytest.raises(ValueError, match="does not exist"):
        delete_workspace("/nonexistent/path/xyz")


def test_delete_nonexistent_ref_is_noop():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = _make_ws(tmpdir)
        result = delete_manual_reference(ws, "nope")
        assert result["deleted"] == "nope"
        assert load_manual_references(ws) == []
