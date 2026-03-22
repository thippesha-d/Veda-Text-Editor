# backend/services/branch_service.py

"""
Semantic Branch Management using Git Worktrees.
Each branch lives in its own linked worktree directory — no git checkout needed.
REQ-3.2.3
"""

import os
import re
import time
from git import Repo, GitCommandError, InvalidGitRepositoryError
from backend.services.git_service import auto_commit

_INVALID_BRANCH_RE = re.compile(r'[\x00-\x1f\x7f ~^:?*\[\\]|\.\.|\.$|^@\{|@\{|\.lock$')


def _validate_branch_name(name: str) -> None:
    """Raises ValueError if name is not a legal Git branch name."""
    if not name or not name.strip():
        raise ValueError("Branch name cannot be empty.")
    if _INVALID_BRANCH_RE.search(name):
        raise ValueError(
            f"Invalid branch name '{name}'. Branch names may not contain spaces, "
            "special characters (~^:?*[\\..@ sequences), or end with .lock."
        )
    if name.startswith('-'):
        raise ValueError("Branch name cannot start with a dash.")


def _get_repo(workspace_path: str) -> Repo:
    """Return the GitPython Repo for a given workspace path."""
    try:
        return Repo(workspace_path)
    except InvalidGitRepositoryError:
        raise ValueError(f"No git repository found at: {workspace_path}")


def _get_worktree_path(workspace_path: str, branch_name: str) -> str:
    """Return the sibling path where the worktree for branch_name should live."""
    abs_path = os.path.abspath(workspace_path)
    parent = os.path.dirname(abs_path)
    main_name = os.path.basename(abs_path)
    return os.path.join(parent, f"{main_name}__{branch_name}")


def _parse_worktree_list(output: str) -> list:
    """Parse `git worktree list --porcelain` output into a list of dicts."""
    worktrees = []
    current = {}
    branch_prefix = 'refs/heads/'
    for line in output.splitlines():
        if line.startswith('worktree '):
            if current:
                worktrees.append(current)
            current = {'path': line[len('worktree '):].strip()}
        elif line.startswith('HEAD '):
            current['sha'] = line[len('HEAD '):].strip()[:7]
        elif line.startswith('branch '):
            ref = line[len('branch '):].strip()
            current['branch'] = ref[len(branch_prefix):] if ref.startswith(branch_prefix) else ref
        elif line.strip() == 'detached':
            current['branch'] = '(detached)'
    if current:
        worktrees.append(current)
    return worktrees


def list_worktrees(workspace_path: str) -> list:
    """
    Lists all worktrees for the workspace with metadata.

    Returns:
        list[dict] — each entry: { name, path, sha, timestamp, message, active }
    """
    repo = _get_repo(workspace_path)
    abs_workspace = os.path.abspath(workspace_path)

    output = repo.git.worktree('list', '--porcelain')
    raw = _parse_worktree_list(output)

    # Build a lookup of branch name → last commit for metadata
    branch_commits = {b.name: b.commit for b in repo.branches}

    result = []
    for wt in raw:
        path = wt.get('path', '')
        branch = wt.get('branch', '(unknown)')
        commit = branch_commits.get(branch)
        result.append({
            'name': branch,
            'path': path,
            'sha': wt.get('sha', ''),
            'timestamp': commit.committed_date if commit else None,
            'message': commit.message.strip().splitlines()[0] if commit else '',
            'active': os.path.abspath(path) == abs_workspace,
        })

    repo.close()
    return result


def create_worktree(workspace_path: str, branch_name: str) -> dict:
    """
    Creates a new branch and a linked Git worktree for it.
    Auto-commits unsaved changes on the current worktree first.

    Returns:
        dict — { branch_name, worktree_path }
    """
    _validate_branch_name(branch_name)

    repo = _get_repo(workspace_path)
    existing_branches = [b.name for b in repo.branches]
    repo.close()

    if branch_name in existing_branches:
        raise ValueError(f"Branch '{branch_name}' already exists. Choose a different name.")

    worktree_path = _get_worktree_path(workspace_path, branch_name)
    if os.path.exists(worktree_path):
        raise ValueError(f"Worktree path already exists: {worktree_path}")

    auto_commit(workspace_path, "pre-worktree-save")

    repo = _get_repo(workspace_path)
    try:
        repo.git.worktree('add', '-b', branch_name, worktree_path)
    except GitCommandError as e:
        repo.close()
        raise ValueError(f"Failed to create worktree: {e.stderr or str(e)}")
    repo.close()

    return {'branch_name': branch_name, 'worktree_path': worktree_path}


def switch_worktree(workspace_path: str, branch_name: str) -> dict:
    """
    Returns the path of the existing worktree for branch_name.
    No git checkout needed — the editor simply points at the new worktree path.

    Returns:
        dict — { branch_name, worktree_path }
    """
    worktrees = list_worktrees(workspace_path)

    active = next((wt for wt in worktrees if wt['active']), None)
    if active and active['name'] == branch_name:
        raise ValueError(f"Already on branch '{branch_name}'.")

    target = next((wt for wt in worktrees if wt['name'] == branch_name), None)
    if not target:
        raise ValueError(f"No worktree found for branch '{branch_name}'.")

    return {'branch_name': branch_name, 'worktree_path': target['path']}


def merge_worktree(workspace_path: str, source_branch: str) -> dict:
    """
    Merges source_branch into the active worktree's branch using --no-ff.
    Auto-commits any unsaved changes first.
    On conflict, returns conflict details instead of raising.

    Returns:
        dict — { status: 'success'|'conflict', message, sha }
    """
    repo = _get_repo(workspace_path)
    existing = [b.name for b in repo.branches]

    if source_branch not in existing:
        repo.close()
        raise ValueError(f"Branch '{source_branch}' does not exist.")

    active_branch = repo.active_branch.name
    if source_branch == active_branch:
        repo.close()
        raise ValueError(f"Cannot merge a branch into itself. Source and target are both '{active_branch}'.")

    repo.close()
    auto_commit(workspace_path, "pre-merge-save")

    repo = _get_repo(workspace_path)
    try:
        repo.git.merge('--no-ff', source_branch, '-m',
                       f"Merge branch '{source_branch}' into {active_branch}: {time.strftime('%Y-%m-%d %H:%M')}")
        sha = repo.active_branch.commit.hexsha[:7]
        repo.close()
        return {'status': 'success', 'message': f"Merged '{source_branch}' into '{active_branch}'.", 'sha': sha}
    except GitCommandError as e:
        conflict_text = str(e.stderr or e.stdout or str(e))
        repo.git.merge('--abort')
        repo.close()
        return {
            'status': 'conflict',
            'message': f"Merge conflict between '{source_branch}' and '{active_branch}'. Merge aborted.",
            'conflict_details': conflict_text,
            'sha': None,
        }


def remove_worktree(workspace_path: str, branch_name: str) -> dict:
    """
    Removes the worktree for branch_name and deletes the associated branch.
    Refuses to remove the currently active worktree.

    Returns:
        dict — { removed_branch }
    """
    _validate_branch_name(branch_name)
    worktrees = list_worktrees(workspace_path)

    target = next((wt for wt in worktrees if wt['name'] == branch_name), None)
    if not target:
        raise ValueError(f"No worktree found for branch '{branch_name}'.")

    if target['active']:
        raise ValueError(
            f"Cannot remove the currently active worktree '{branch_name}'. Switch to another branch first."
        )

    repo = _get_repo(workspace_path)
    try:
        repo.git.worktree('remove', '--force', target['path'])
    except GitCommandError as e:
        repo.close()
        raise ValueError(f"Failed to remove worktree: {e.stderr or str(e)}")

    try:
        repo.delete_head(branch_name, force=True)
    except Exception:
        pass

    repo.close()
    return {'removed_branch': branch_name}
