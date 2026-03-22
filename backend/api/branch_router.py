# backend/api/branch_router.py

"""
REST API endpoints for Semantic Branch Management (Git Worktrees).
REQ-3.2.3
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.branch_service import (
    create_worktree,
    switch_worktree,
    list_worktrees,
    merge_worktree,
    remove_worktree,
)
from backend.services.git_service import get_branch_diff, get_conflicts
import os

router = APIRouter()


class BranchCreatePayload(BaseModel):
    workspace_path: str
    branch_name: str


class BranchSwitchPayload(BaseModel):
    workspace_path: str
    branch_name: str


class BranchMergePayload(BaseModel):
    workspace_path: str
    source_branch: str


class BranchDeletePayload(BaseModel):
    workspace_path: str
    branch_name: str


@router.post("/api/branch/create")
async def api_create_worktree(payload: BranchCreatePayload):
    """
    Creates a new branch and a linked worktree for it.
    Auto-commits unsaved work before branching.
    """
    if not os.path.exists(payload.workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found.")
    try:
        result = create_worktree(payload.workspace_path, payload.branch_name)
        return {"status": "success", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/branch/switch")
async def api_switch_worktree(payload: BranchSwitchPayload):
    """
    Returns the worktree path for the target branch.
    No git checkout — the frontend repoints the editor at the new path.
    """
    if not os.path.exists(payload.workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found.")
    try:
        result = switch_worktree(payload.workspace_path, payload.branch_name)
        return {"status": "success", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/branch/list")
async def api_list_worktrees(workspace_path: str):
    """
    Returns all worktrees with metadata:
    [{ name, path, sha, timestamp, message, active }]
    """
    if not os.path.exists(workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found.")
    try:
        worktrees = list_worktrees(workspace_path)
        return {"status": "success", "branches": worktrees}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/branch/merge")
async def api_merge_worktree(payload: BranchMergePayload):
    """
    Merges source_branch into the active worktree's branch using --no-ff.
    Returns conflict details if merge fails, without auto-resolving.
    """
    if not os.path.exists(payload.workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found.")
    try:
        result = merge_worktree(payload.workspace_path, payload.source_branch)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/branch/diff")
async def api_branch_diff(workspace_path: str, branch_a: str, branch_b: str):
    """
    Returns unified diff between branch_a (base) and branch_b (compare).
    """
    if not os.path.exists(workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found.")
    try:
        result = get_branch_diff(workspace_path, branch_a, branch_b)
        return {"status": "success", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/branch/conflicts")
async def api_branch_conflicts(workspace_path: str):
    """
    Returns all currently conflicted files with their content
    (including <<<<<<< / ======= / >>>>>>> markers).
    """
    if not os.path.exists(workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found.")
    try:
        result = get_conflicts(workspace_path)
        return {"status": "success", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/branch/delete")
async def api_remove_worktree(payload: BranchDeletePayload):
    """
    Removes the worktree and deletes the associated branch.
    Refuses to remove the currently active worktree.
    """
    if not os.path.exists(payload.workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found.")
    try:
        result = remove_worktree(payload.workspace_path, payload.branch_name)
        return {"status": "success", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
