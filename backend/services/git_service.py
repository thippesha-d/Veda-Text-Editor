# backend/services/git_service.py
import os
import re
import time
import json
import uuid
import git
from git import Repo
from backend.services.lfs_service import is_lfs_available, configure_lfs

def init_workspace_repo(workspace_dir: str) -> dict:
    """
    Initializes a new Git repository in the specified workspace directory,
    creates a default .gitignore, and makes an initial commit.
    """
    # Create directory if it doesn't exist
    if not os.path.exists(workspace_dir):
        os.makedirs(workspace_dir, exist_ok=True)

    # Initialize repository
    repo = Repo.init(workspace_dir)

    # Write default .gitignore
    gitignore_path = os.path.join(workspace_dir, ".gitignore")
    with open(gitignore_path, "w", encoding="utf-8") as f:
        f.write("# OS Files\n")
        f.write(".DS_Store\n")
        f.write("Thumbs.db\n\n")
        f.write("# Python\n")
        f.write("__pycache__/\n")
        f.write("*.pyc\n\n")
        f.write("# Environment\n")
        f.write(".env\n")

    # Write an initial document file if not present
    doc_path = os.path.join(workspace_dir, "article.html")
    if not os.path.exists(doc_path):
        with open(doc_path, "w", encoding="utf-8") as f:
            f.write("<h1>New Article</h1><p>Start writing here...</p>")

    # Configure Git LFS if available — never block workspace creation on failure
    lfs_result = None
    try:
        if is_lfs_available():
            lfs_result = configure_lfs(workspace_dir)
    except Exception:
        lfs_result = None

    # Add all files to the index
    files_to_stage = [".gitignore", "article.html"]
    if lfs_result and os.path.exists(os.path.join(workspace_dir, ".gitattributes")):
        files_to_stage.append(".gitattributes")
    repo.index.add(files_to_stage)

    # Commit the changes; uses default git config or sets a fallback if not configured globally
    try:
        commit = repo.index.commit("Initial workspace created")
    except Exception as commit_err:
        # If user name/email are not configured in Git, configure locally for this repo
        with repo.config_writer() as cw:
            cw.set_value("user", "name", os.environ.get("GIT_USER_NAME", "Veda Editor"))
            cw.set_value("user", "email", os.environ.get("GIT_USER_EMAIL", "veda@local"))
        commit = repo.index.commit("Initial workspace created")

    repo_sha = commit.hexsha
    repo.close()

    return {
        "git_sha": repo_sha,
        "repo_path": workspace_dir,
        "lfs_configured": lfs_result is not None,
    }

def get_branch_diff(workspace_dir: str, branch_a: str, branch_b: str) -> dict:
    """
    Returns the unified diff between two branches.
    branch_a is the base; branch_b is compared against it.
    """
    repo = Repo(workspace_dir)
    try:
        diff_text = repo.git.diff(branch_a, branch_b, unified=3)
        return {
            "diff":     diff_text,
            "branch_a": branch_a,
            "branch_b": branch_b,
            "empty":    diff_text.strip() == "",
        }
    finally:
        repo.close()


def get_conflicts(workspace_dir: str) -> dict:
    """
    Returns a list of currently conflicted files in the workspace
    (files with unresolved merge conflict markers).
    Each entry contains the file path and full content including conflict markers.
    """
    repo = Repo(workspace_dir)
    try:
        unmerged_paths = list(repo.index.unmerged_blobs().keys())
        conflicts = []
        for rel_path in unmerged_paths:
            abs_path = os.path.join(workspace_dir, rel_path)
            content = ""
            if os.path.exists(abs_path):
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            conflicts.append({"file": rel_path, "content": content})
        return {"conflicts": conflicts, "has_conflicts": len(conflicts) > 0}
    finally:
        repo.close()


def clone_repo(remote_url: str, base_dir: str = "./workspace") -> dict:
    """
    Clones a remote Git repository into a new workspace directory under base_dir.
    Creates workspace.json and article.html if they don't exist in the cloned repo.
    Returns workspace metadata compatible with load_workspace.
    """
    repo_slug = re.sub(r'\.git$', '', remote_url.rstrip('/').split('/')[-1])
    safe_slug = "".join(c if c.isalnum() else '_' for c in repo_slug) or "repo"
    ws_id = str(uuid.uuid4())[:8]
    target_dir = os.path.join(base_dir, f"{safe_slug}_{ws_id}")
    os.makedirs(base_dir, exist_ok=True)

    repo = Repo.clone_from(remote_url, target_dir)
    sha = repo.head.commit.hexsha if not repo.head.is_detached else ""
    repo.close()

    # Create workspace.json if the cloned repo doesn't have one
    manifest_path = os.path.join(target_dir, "workspace.json")
    if not os.path.exists(manifest_path):
        manifest = {
            "workspace_id": ws_id,
            "name": safe_slug,
            "created_at": time.time(),
            "git_sha": sha,
            "assets": [],
            "remote_url": remote_url,
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    # Create article.html if missing
    article_path = os.path.join(target_dir, "article.html")
    if not os.path.exists(article_path):
        with open(article_path, "w", encoding="utf-8") as f:
            f.write("<h1>New Article</h1><p>Start writing here...</p>")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    with open(article_path, "r", encoding="utf-8") as f:
        html = f.read()

    return {
        "workspace_id": manifest.get("workspace_id", ws_id),
        "name": manifest.get("name", safe_slug),
        "path": target_dir,
        "git_sha": sha,
        "html": html,
        "remote_url": remote_url,
    }


def get_remote(workspace_dir: str, remote_name: str = "origin") -> dict:
    """
    Returns the fetch URL of the named remote, or None if not configured.
    """
    repo = Repo(workspace_dir)
    try:
        try:
            remote = repo.remote(remote_name)
            return {"remote": remote_name, "url": remote.url}
        except ValueError:
            return {"remote": remote_name, "url": None}
    finally:
        repo.close()


def set_remote(workspace_dir: str, remote_url: str, remote_name: str = "origin") -> dict:
    """
    Adds the named remote if it doesn't exist, or updates its URL if it does.
    """
    repo = Repo(workspace_dir)
    try:
        try:
            remote = repo.remote(remote_name)
            remote.set_url(remote_url)
            action = "updated"
        except ValueError:
            repo.create_remote(remote_name, remote_url)
            action = "added"
        return {"remote": remote_name, "url": remote_url, "action": action}
    finally:
        repo.close()


def auto_commit(workspace_dir: str, trigger_reason: str = "Timer") -> dict | None:
    """
    Commits any tracked or untracked changes in the workspace if they exist.
    Updates workspace.json with the timestamp BEFORE committing so it is
    included in the commit (not left as a post-commit dirty file).
    """
    if not os.path.exists(workspace_dir):
        return None
        
    repo = Repo(workspace_dir)
    
    # Check if there are changes
    if not repo.is_dirty(untracked_files=True):
        repo.close()
        return None
    
    repo.close()

    # Update workspace.json BEFORE staging so the update is included in the commit
    manifest_path = os.path.join(workspace_dir, "workspace.json")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["last_auto_commit"] = time.time()
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass  # If workspace.json is malformed, skip update; still commit other files

    repo = Repo(workspace_dir)
    repo.git.add(A=True)
    
    try:
        commit = repo.index.commit(f"Auto-save: {time.strftime('%Y-%m-%d %H:%M:%S')} Trigger: {trigger_reason}")
    except Exception:
        with repo.config_writer() as cw:
            cw.set_value("user", "name", os.environ.get("GIT_USER_NAME", "Veda Editor"))
            cw.set_value("user", "email", os.environ.get("GIT_USER_EMAIL", "veda@local"))
        commit = repo.index.commit(f"Auto-save: {time.strftime('%Y-%m-%d %H:%M:%S')} Trigger: {trigger_reason}")

    sha = commit.hexsha

    # Write the final SHA back into workspace.json and do a second minimal commit
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["git_sha"] = sha
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            repo.git.add(manifest_path)
            if repo.is_dirty():
                repo.index.commit(f"Update workspace metadata: {sha[:7]}")
        except Exception:
            pass

    repo.close()
    return {"git_sha": sha, "repo_path": workspace_dir, "trigger": trigger_reason}
