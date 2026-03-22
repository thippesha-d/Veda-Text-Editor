# backend/tests/test_branch_service.py

"""
Unit tests for backend/services/branch_service.py (Git Worktree implementation).
REQ-3.2.3 — Semantic Branch Management
"""

import os
import pytest
from git import Repo

from backend.services.branch_service import (
    create_worktree,
    switch_worktree,
    list_worktrees,
    merge_worktree,
    remove_worktree,
)


@pytest.fixture
def workspace(tmp_path):
    """
    Creates a fresh git workspace with an initial commit.
    The workspace lives at tmp_path/workspace so that sibling worktrees
    (tmp_path/workspace__<branch>) are also inside tmp_path and get cleaned up.
    """
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    repo = Repo.init(str(ws_dir))
    repo.config_writer().set_value("user", "name", "Test User").release()
    repo.config_writer().set_value("user", "email", "test@test.com").release()
    article = ws_dir / "article.html"
    article.write_text("<p>Initial</p>", encoding="utf-8")
    repo.index.add(["article.html"])
    repo.index.commit("Initial workspace created")
    repo.close()
    return str(ws_dir)


# ────────────────────────────────────────────────────────────────
# TEST: list_worktrees
# ────────────────────────────────────────────────────────────────

def test_list_worktrees_returns_main(workspace):
    """list_worktrees must return at least the main worktree with active=True."""
    worktrees = list_worktrees(workspace)
    assert isinstance(worktrees, list)
    assert len(worktrees) >= 1
    active = [wt for wt in worktrees if wt["active"]]
    assert len(active) == 1
    assert active[0]["sha"] != ""
    assert active[0]["path"] != ""


# ────────────────────────────────────────────────────────────────
# TEST: create_worktree
# ────────────────────────────────────────────────────────────────

def test_create_worktree(workspace):
    """create_worktree must create a new branch and worktree directory."""
    result = create_worktree(workspace, "draft-v1")
    assert result["branch_name"] == "draft-v1"
    assert os.path.isdir(result["worktree_path"])
    names = [wt["name"] for wt in list_worktrees(workspace)]
    assert "draft-v1" in names


def test_create_worktree_already_exists_raises(workspace):
    """create_worktree must raise ValueError if branch already exists."""
    create_worktree(workspace, "existing-branch")
    with pytest.raises(ValueError, match="already exists"):
        create_worktree(workspace, "existing-branch")


def test_create_worktree_invalid_name_raises(workspace):
    """create_worktree must raise ValueError for invalid git branch names."""
    with pytest.raises(ValueError):
        create_worktree(workspace, "bad~name")
    with pytest.raises(ValueError):
        create_worktree(workspace, "")


# ────────────────────────────────────────────────────────────────
# TEST: switch_worktree
# ────────────────────────────────────────────────────────────────

def test_switch_worktree(workspace):
    """switch_worktree must return the worktree path for the target branch."""
    result = create_worktree(workspace, "feature-x")
    worktree_path = result["worktree_path"]

    switch_result = switch_worktree(workspace, "feature-x")
    assert switch_result["branch_name"] == "feature-x"
    assert os.path.abspath(switch_result["worktree_path"]) == os.path.abspath(worktree_path)


def test_switch_to_same_branch_raises(workspace):
    """switch_worktree must raise ValueError when already on the target branch."""
    active = next(wt["name"] for wt in list_worktrees(workspace) if wt["active"])
    with pytest.raises(ValueError, match="Already on branch"):
        switch_worktree(workspace, active)


def test_switch_to_nonexistent_branch_raises(workspace):
    """switch_worktree must raise ValueError for a branch with no worktree."""
    with pytest.raises(ValueError, match="No worktree found"):
        switch_worktree(workspace, "ghost-branch")


def test_switch_worktree_content_isolation(workspace):
    """
    Each worktree has independent article.html content.
    After switch, the returned path contains the feature content, not the main content.
    This directly tests the bug where switching branches overwrote the editor with stale content.
    """
    # Write distinct content in the main worktree
    main_article = os.path.join(workspace, "article.html")
    with open(main_article, "w", encoding="utf-8") as f:
        f.write("<p>Main branch content</p>")

    # Create a feature worktree
    result = create_worktree(workspace, "feature-content")
    worktree_path = result["worktree_path"]

    # Write different content into the feature worktree
    feature_article = os.path.join(worktree_path, "article.html")
    with open(feature_article, "w", encoding="utf-8") as f:
        f.write("<p>Feature branch content</p>")

    # Switch returns the correct worktree path
    switch_result = switch_worktree(workspace, "feature-content")
    assert os.path.abspath(switch_result["worktree_path"]) == os.path.abspath(worktree_path)

    # Content at the returned path is the feature content
    with open(os.path.join(switch_result["worktree_path"], "article.html"), encoding="utf-8") as f:
        feature_content = f.read()
    assert "Feature branch content" in feature_content
    assert "Main branch content" not in feature_content

    # Main workspace content is unaffected
    with open(main_article, encoding="utf-8") as f:
        main_content = f.read()
    assert "Main branch content" in main_content


# ────────────────────────────────────────────────────────────────
# TEST: merge_worktree
# ────────────────────────────────────────────────────────────────

def test_merge_worktree_success(workspace):
    """merge_worktree must return status=success on a clean merge."""
    create_worktree(workspace, "feature-merge")

    # Add a commit in the new worktree
    result = switch_worktree(workspace, "feature-merge")
    worktree_path = result["worktree_path"]
    article = os.path.join(worktree_path, "article.html")
    with open(article, "a", encoding="utf-8") as f:
        f.write("<p>Feature content</p>")
    repo = Repo(worktree_path)
    repo.index.add(["article.html"])
    repo.index.commit("Feature commit")
    repo.close()

    # Merge feature-merge into the main worktree
    result = merge_worktree(workspace, "feature-merge")
    assert result["status"] == "success"
    assert result["sha"] is not None


def test_merge_self_raises(workspace):
    """merge_worktree must raise ValueError when merging a branch into itself."""
    active = next(wt["name"] for wt in list_worktrees(workspace) if wt["active"])
    with pytest.raises(ValueError, match="Cannot merge a branch into itself"):
        merge_worktree(workspace, active)


# ────────────────────────────────────────────────────────────────
# TEST: remove_worktree
# ────────────────────────────────────────────────────────────────

def test_remove_worktree(workspace):
    """remove_worktree must remove the worktree directory and branch."""
    create_worktree(workspace, "to-remove")
    result = remove_worktree(workspace, "to-remove")
    assert result["removed_branch"] == "to-remove"
    names = [wt["name"] for wt in list_worktrees(workspace)]
    assert "to-remove" not in names


def test_remove_active_worktree_raises(workspace):
    """remove_worktree must raise ValueError when trying to remove the active worktree."""
    active = next(wt["name"] for wt in list_worktrees(workspace) if wt["active"])
    with pytest.raises(ValueError, match="Cannot remove the currently active worktree"):
        remove_worktree(workspace, active)


def test_remove_nonexistent_worktree_raises(workspace):
    """remove_worktree must raise ValueError for a branch with no worktree."""
    with pytest.raises(ValueError, match="No worktree found"):
        remove_worktree(workspace, "ghost-branch-xyz")
