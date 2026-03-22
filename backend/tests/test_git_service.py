import os
import tempfile
from backend.services.git_service import (
    init_workspace_repo, get_branch_diff, get_conflicts,
    clone_repo, get_remote, set_remote,
)
from git import Repo

def test_init_workspace_repo():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws_path = os.path.join(tmpdir, "my_repo")
        res = init_workspace_repo(ws_path)
        assert "git_sha" in res
        assert os.path.exists(os.path.join(ws_path, ".git"))
        assert os.path.exists(os.path.join(ws_path, ".gitignore"))

def _make_repo_with_two_branches(tmpdir):
    """Helper: init repo, add a second branch with a different file."""
    ws_path = os.path.join(tmpdir, "repo")
    init_workspace_repo(ws_path)
    repo = Repo(ws_path)
    repo.git.checkout("-b", "feature")
    with open(os.path.join(ws_path, "article.html"), "a", encoding="utf-8") as f:
        f.write("<p>Feature content</p>")
    repo.git.add(A=True)
    repo.index.commit("Feature change")
    repo.git.checkout("master")
    repo.close()
    return ws_path


def test_get_branch_diff_has_changes():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws_path = _make_repo_with_two_branches(tmpdir)
        res = get_branch_diff(ws_path, "master", "feature")
        assert "diff" in res
        assert res["branch_a"] == "master"
        assert res["branch_b"] == "feature"
        assert res["empty"] is False
        assert "Feature content" in res["diff"]


def test_get_branch_diff_no_changes():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws_path = os.path.join(tmpdir, "repo")
        init_workspace_repo(ws_path)
        repo = Repo(ws_path)
        repo.git.checkout("-b", "feature")
        repo.git.checkout("master")
        repo.close()
        res = get_branch_diff(ws_path, "master", "feature")
        assert res["empty"] is True
        assert res["diff"].strip() == ""


def test_get_conflicts_no_conflict():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws_path = os.path.join(tmpdir, "repo")
        init_workspace_repo(ws_path)
        res = get_conflicts(ws_path)
        assert res["has_conflicts"] is False
        assert res["conflicts"] == []


def test_clone_repo_creates_workspace():
    with tempfile.TemporaryDirectory() as src_dir:
        # Create a bare-style local "remote" repo to clone from
        init_workspace_repo(src_dir)
        with tempfile.TemporaryDirectory() as target_base:
            res = clone_repo(src_dir, base_dir=target_base)
            assert "path" in res
            assert os.path.isdir(res["path"])
            assert os.path.exists(os.path.join(res["path"], "workspace.json"))
            assert os.path.exists(os.path.join(res["path"], "article.html"))
            assert res["git_sha"] != ""


def test_clone_repo_uses_repo_name():
    with tempfile.TemporaryDirectory() as src_dir:
        init_workspace_repo(src_dir)
        with tempfile.TemporaryDirectory() as target_base:
            res = clone_repo(src_dir, base_dir=target_base)
            # target directory name should start with the slug derived from src_dir
            folder = os.path.basename(res["path"])
            assert len(folder) > 0


def test_get_remote_no_remote():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws_path = os.path.join(tmpdir, "repo")
        init_workspace_repo(ws_path)
        res = get_remote(ws_path)
        assert res["remote"] == "origin"
        assert res["url"] is None


def test_set_remote_adds_and_updates():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws_path = os.path.join(tmpdir, "repo")
        init_workspace_repo(ws_path)

        # Add remote
        res = set_remote(ws_path, "https://github.com/example/repo.git")
        assert res["action"] == "added"
        assert res["url"] == "https://github.com/example/repo.git"

        # Verify get_remote returns it
        fetched = get_remote(ws_path)
        assert fetched["url"] == "https://github.com/example/repo.git"

        # Update remote
        res2 = set_remote(ws_path, "https://github.com/example/repo2.git")
        assert res2["action"] == "updated"
        assert res2["url"] == "https://github.com/example/repo2.git"


def test_auto_commit():
    from backend.services.git_service import auto_commit
    with tempfile.TemporaryDirectory() as tmpdir:
        ws_path = os.path.join(tmpdir, "my_repo")
        init_workspace_repo(ws_path)
        
        # Test no changes -> returns None
        res_none = auto_commit(ws_path, "Timer")
        assert res_none is None
        
        # Test with changes
        with open(os.path.join(ws_path, "article.html"), "a", encoding="utf-8") as f:
            f.write("Some changes.")
            
        res = auto_commit(ws_path, "word_delta")
        assert res is not None
        assert res["trigger"] == "word_delta"
        assert res["git_sha"] != ""
