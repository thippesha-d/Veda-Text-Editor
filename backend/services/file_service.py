# backend/services/file_service.py
import os
import stat
import shutil
import time
import json
import uuid
from backend.services.git_service import init_workspace_repo
from backend.services.lfs_service import should_use_lfs, LFS_SIZE_THRESHOLD_BYTES

def save_document_html(html_content: str, workspace_dir: str = "./workspace") -> dict:
    """
    Saves the provided HTML content to the local workspace directory.
    Creates the directory if it does not exist.
    """
    if not os.path.exists(workspace_dir):
        os.makedirs(workspace_dir, exist_ok=True)
        
    filepath = os.path.join(workspace_dir, "article.html")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    return {
        "status": "success",
        "saved_at": time.time(),
        "filepath": filepath,
        "bytes": len(html_content.encode("utf-8"))
    }

def save_media_file(filename: str, file_bytes: bytes, workspace_dir: str = "./workspace") -> dict:
    """
    Saves an uploaded media asset to the workspace/assets directory.
    Returns the relative path for the frontend to consume.
    """
    assets_dir = os.path.join(workspace_dir, "assets")
    if not os.path.exists(assets_dir):
        os.makedirs(assets_dir, exist_ok=True)
        
    filepath = os.path.join(assets_dir, filename)
    
    with open(filepath, "wb") as f:
        f.write(file_bytes)
        
    # Return string path relative to the active mount
    return {
        "status": "success",
        "saved_at": time.time(),
        "url": f"/assets/{filename}",
        "bytes": len(file_bytes),
        "lfs_tracked": should_use_lfs(filename, file_bytes),
        "lfs_size_threshold_mb": LFS_SIZE_THRESHOLD_BYTES // (1024 * 1024),
    }

def load_document_html(workspace_dir: str) -> str:
    """
    Reads and returns the HTML content of article.html from the workspace directory.
    Returns an empty string if the file does not exist.
    """
    filepath = os.path.join(workspace_dir, "article.html")
    if not os.path.exists(filepath):
        return ""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Metadata helpers  (REQ Feature-7)
# ---------------------------------------------------------------------------

_METADATA_DEFAULTS = {
    "title":    "",
    "authors":  [],
    "abstract": "",
    "keywords": [],
    "tags":     [],
    "journal":  "",
    "version":  "1",
}


def load_metadata(workspace_dir: str) -> dict:
    """Returns document metadata from workspace.json with defaults for missing fields."""
    path = os.path.join(workspace_dir, "workspace.json")
    if not os.path.exists(path):
        return dict(_METADATA_DEFAULTS)
    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    stored = manifest.get("metadata", {})
    return {**_METADATA_DEFAULTS, **stored}


def save_metadata(workspace_dir: str, metadata: dict) -> dict:
    """Persists allowed metadata fields to workspace.json['metadata']."""
    path = os.path.join(workspace_dir, "workspace.json")
    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    existing = manifest.get("metadata", {})
    allowed = set(_METADATA_DEFAULTS.keys())
    for key, val in metadata.items():
        if key in allowed:
            existing[key] = val
    manifest["metadata"] = existing
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return load_metadata(workspace_dir)


# ---------------------------------------------------------------------------
# Manual references helpers  (REQ Feature-5)
# ---------------------------------------------------------------------------

def load_manual_references(workspace_dir: str) -> list:
    """Returns the manual_references list from workspace.json."""
    path = os.path.join(workspace_dir, "workspace.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("manual_references", [])


def save_manual_reference(workspace_dir: str, ref: dict) -> dict:
    """Adds or updates (by ref_id) a manual reference in workspace.json."""
    import uuid as _uuid
    path = os.path.join(workspace_dir, "workspace.json")
    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    refs = manifest.get("manual_references", [])
    if not ref.get("ref_id"):
        ref["ref_id"] = str(_uuid.uuid4())[:8]
    refs = [r for r in refs if r.get("ref_id") != ref["ref_id"]]
    refs.append(ref)
    manifest["manual_references"] = refs
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return ref


def delete_manual_reference(workspace_dir: str, ref_id: str) -> dict:
    """Removes a manual reference by ref_id from workspace.json."""
    path = os.path.join(workspace_dir, "workspace.json")
    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    manifest["manual_references"] = [
        r for r in manifest.get("manual_references", [])
        if r.get("ref_id") != ref_id
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return {"deleted": ref_id}


# ---------------------------------------------------------------------------

def load_workspace(workspace_dir: str) -> dict:
    """
    Validates and loads an existing workspace directory.
    Returns workspace metadata and current document HTML.
    Raises ValueError if the path is not a valid Veda workspace.
    """
    workspace_dir = os.path.abspath(workspace_dir)
    if not os.path.isdir(workspace_dir):
        raise ValueError(f"Path does not exist or is not a directory: {workspace_dir}")

    manifest_path = os.path.join(workspace_dir, "workspace.json")
    if not os.path.exists(manifest_path):
        raise ValueError(f"Not a valid Veda workspace (missing workspace.json): {workspace_dir}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    html_content = load_document_html(workspace_dir)

    return {
        "workspace_id": manifest.get("workspace_id", ""),
        "name":         manifest.get("name", os.path.basename(workspace_dir)),
        "path":         workspace_dir,
        "git_sha":      manifest.get("git_sha", ""),
        "html":         html_content,
    }


def delete_workspace(workspace_dir: str) -> dict:
    """
    Permanently removes the workspace directory and all its contents.
    Raises ValueError if the path is not a valid Veda workspace.
    """
    workspace_dir = os.path.abspath(workspace_dir)
    if not os.path.isdir(workspace_dir):
        raise ValueError(f"Path does not exist: {workspace_dir}")

    manifest_path = os.path.join(workspace_dir, "workspace.json")
    if not os.path.exists(manifest_path):
        raise ValueError(f"Not a valid Veda workspace (missing workspace.json): {workspace_dir}")

    def _remove_readonly(func, path, _exc):
        """onerror handler: clear read-only bit (set by git on Windows) then retry."""
        os.chmod(path, stat.S_IWRITE)
        func(path)

    shutil.rmtree(workspace_dir, onerror=_remove_readonly)
    return {"deleted": workspace_dir}


def create_workspace(name: str, base_dir: str = "./workspace") -> dict:
    """
    Creates a physical directory for a new article workspace,
    generates an initial article file, initializes a Git repo,
    and returns the workspace metadata.
    """
    workspace_id = str(uuid.uuid4())
    # Create a unique folder for the workspace using name and id
    safe_name = "".join([c if c.isalnum() else "_" for c in name])
    workspace_dir = os.path.join(base_dir, f"{safe_name}_{workspace_id[:8]}")
    
    if not os.path.exists(workspace_dir):
        os.makedirs(workspace_dir, exist_ok=True)
        
    git_result = init_workspace_repo(workspace_dir)
    
    # Write workspace manifest
    manifest = {
        "workspace_id": workspace_id,
        "name": name,
        "created_at": time.time(),
        "git_sha": git_result["git_sha"],
        "assets": []
    }
    manifest_path = os.path.join(workspace_dir, "workspace.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        
    return {
        "workspace_id": workspace_id,
        "path": workspace_dir,
        "git_sha": git_result["git_sha"],
        "name": name
    }
