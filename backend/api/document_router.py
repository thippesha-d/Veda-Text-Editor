# backend/api/document_router.py
from fastapi import APIRouter, HTTPException, File, UploadFile, Form
from pydantic import BaseModel
from backend.services.file_service import (
    save_document_html, save_media_file, create_workspace, load_document_html,
    load_metadata, save_metadata, load_workspace, delete_workspace,
)
from backend.services.git_service import auto_commit, clone_repo, get_remote, set_remote
from backend.services.lfs_service import get_lfs_storage_usage, configure_lfs, disable_lfs

class WorkspacePayload(BaseModel):
    name: str

import os
import uuid
import json

router = APIRouter()

class DocumentPayload(BaseModel):
    html: str
    workspace_path: str = ""

@router.put("/api/document/save")
async def save_document(payload: DocumentPayload):
    """
    Saves the HTML payload to the active workspace folder, then commits.
    """
    try:
        # Use provided workspace_path if valid, else fall back to global workspace dir
        workspace_dir = payload.workspace_path \
            if payload.workspace_path and os.path.exists(payload.workspace_path) \
            else os.environ.get("WORKSPACE_DIR", "./workspace")
        
        result = save_document_html(payload.html, workspace_dir=workspace_dir)
        
        # Trigger an immediate git commit so the save is reflected in history
        commit = auto_commit(workspace_dir, "Manual")
        result["commit"] = commit
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/media/upload")
async def upload_media(file: UploadFile = File(...), workspace_path: str = Form(default="")):
    """
    Receives a multipart image binary from the editor, assigns a UUID,
    and saves it to the workspace-specific assets/ subdirectory.
    """
    try:
        ext = os.path.splitext(file.filename)[1] or ".png"
        new_filename = f"{uuid.uuid4()}{ext}"
        
        file_bytes = await file.read()
        
        # Use provided workspace path, fall back to global workspace dir
        target_dir = workspace_path if workspace_path and os.path.exists(workspace_path) \
            else os.environ.get("WORKSPACE_DIR", "./workspace")
        
        result = save_media_file(new_filename, file_bytes, workspace_dir=target_dir)
        
        # Derive workspace_id from the folder name (format: safe_name_XXXXXXXX)
        folder_name = os.path.basename(target_dir)
        workspace_id = folder_name  # pass full folder name so client can construct URL
        
        result["url"] = f"/api/workspace/assets/{workspace_id}/{new_filename}"
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/workspace/create")
async def create_new_workspace(payload: WorkspacePayload):
    """
    Initializes a new article workspace and Git repository.
    """
    try:
        base_dir = os.environ.get("WORKSPACE_DIR", "./workspace")
        result = create_workspace(payload.name, base_dir=base_dir)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class CommitRequest(BaseModel):
    workspace_path: str
    trigger: str = "Manual"

@router.post("/api/document/commit")
async def trigger_commit(payload: CommitRequest):
    if not os.path.exists(payload.workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found")
    res = auto_commit(payload.workspace_path, payload.trigger)
    return {"status": "success", "commit": res}

@router.get("/api/document/load")
async def load_document(workspace_path: str):
    """
    Returns the current HTML content of article.html from the workspace.
    Called after branch switches to reload the editor with the new branch's content.
    """
    if not os.path.exists(workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found")
    html = load_document_html(workspace_path)
    return {"status": "success", "html": html}


@router.get("/api/workspace/status")
async def get_workspace_status(workspace_path: str):
    if not os.path.exists(workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found")
    manifest_path = os.path.join(workspace_path, "workspace.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {"status": "success", "git_sha": data.get("git_sha"), "last_auto_commit": data.get("last_auto_commit")}
    return {"status": "success", "git_sha": None, "last_auto_commit": None}


class MetadataPayload(BaseModel):
    workspace_path: str
    metadata: dict

@router.get("/api/document/metadata")
async def get_document_metadata(workspace_path: str):
    if not os.path.exists(workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        return load_metadata(workspace_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/api/document/metadata")
async def update_document_metadata(payload: MetadataPayload):
    if not os.path.exists(payload.workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        return save_metadata(payload.workspace_path, payload.metadata)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class LoadWorkspacePayload(BaseModel):
    workspace_path: str

@router.post("/api/workspace/load")
async def load_existing_workspace(payload: LoadWorkspacePayload):
    """
    Validates and loads an existing workspace directory.
    Returns workspace metadata and current document HTML.
    """
    try:
        result = load_workspace(payload.workspace_path)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class DeleteWorkspacePayload(BaseModel):
    workspace_path: str

@router.delete("/api/workspace/delete")
async def delete_existing_workspace(payload: DeleteWorkspacePayload):
    """
    Permanently deletes a workspace directory and all its contents.
    """
    try:
        result = delete_workspace(payload.workspace_path)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class LfsTogglePayload(BaseModel):
    workspace_path: str

@router.post("/api/workspace/lfs-enable")
async def enable_lfs_for_workspace(payload: LfsTogglePayload):
    """
    Enables Git LFS for the workspace by writing LFS filter patterns to
    .gitattributes.
    """
    if not os.path.exists(payload.workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        result = configure_lfs(payload.workspace_path)
        return {"status": "success", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/workspace/lfs-disable")
async def disable_lfs_for_workspace(payload: LfsTogglePayload):
    """
    Removes LFS filter lines from .gitattributes, effectively disabling LFS
    for the workspace. Deletes .gitattributes entirely if no other lines remain.
    """
    if not os.path.exists(payload.workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        result = disable_lfs(payload.workspace_path)
        return {"status": "success", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CloneWorkspacePayload(BaseModel):
    remote_url: str

@router.post("/api/workspace/clone")
async def clone_from_remote(payload: CloneWorkspacePayload):
    """Clones a remote Git repository and initialises it as a Veda workspace."""
    try:
        base_dir = os.environ.get("WORKSPACE_DIR", "./workspace")
        result = clone_repo(payload.remote_url, base_dir=base_dir)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/workspace/remote")
async def get_workspace_remote(workspace_path: str):
    """Returns the current origin remote URL for the workspace (None if not set)."""
    if not os.path.exists(workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        result = get_remote(workspace_path)
        return {"status": "success", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RemotePayload(BaseModel):
    workspace_path: str
    remote_url: str

@router.post("/api/workspace/remote")
async def set_workspace_remote(payload: RemotePayload):
    """Adds or updates the origin remote URL for the workspace."""
    if not os.path.exists(payload.workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        result = set_remote(payload.workspace_path, payload.remote_url)
        return {"status": "success", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/workspace/lfs-status")
async def get_lfs_status(workspace_path: str):
    """
    Returns LFS availability and local object store usage for the workspace.
    Used by the frontend to display the LFS badge in the workspace bar.
    """
    if not os.path.exists(workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        result = get_lfs_storage_usage(workspace_path)
        return {"status": "success", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
