# backend/services/lfs_service.py

"""
Git LFS (Large File Storage) detection, configuration, and file-routing utilities.
REQ-3.2.4
"""

import os
import subprocess

# Extensions tracked by LFS regardless of file size
LFS_EXTENSIONS = {'.csv', '.mat', '.zip', '.h5', '.sim', '.raw'}

# Files larger than this threshold are flagged for LFS regardless of extension
LFS_SIZE_THRESHOLD_BYTES = 10 * 1024 * 1024  # 10 MB

# .gitattributes lines written when LFS is configured
_LFS_PATTERNS = [
    "# Git LFS tracked file patterns (REQ-3.2.4)",
    "*.csv filter=lfs diff=lfs merge=lfs -text",
    "*.mat filter=lfs diff=lfs merge=lfs -text",
    "*.zip filter=lfs diff=lfs merge=lfs -text",
    "*.h5  filter=lfs diff=lfs merge=lfs -text",
    "*.sim filter=lfs diff=lfs merge=lfs -text",
    "*.raw filter=lfs diff=lfs merge=lfs -text",
]


def is_lfs_available() -> bool:
    """
    Returns True if git-lfs is installed and accessible on the system PATH.
    """
    try:
        result = subprocess.run(
            ["git", "lfs", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def configure_lfs(workspace_dir: str) -> dict:
    """
    Configures Git LFS for the workspace by writing .gitattributes with LFS
    track patterns. Hook installation (`git lfs install --local`) is intentionally
    skipped: on Windows, GitPython fails to execute hooks whose paths contain
    spaces, causing workspace creation to crash. For a local-only editor with no
    remote push, the .gitattributes filter entries are sufficient to mark files
    for LFS tracking.

    Returns:
        dict — { lfs_configured, gitattributes_path }
    """
    gitattributes_path = os.path.join(workspace_dir, ".gitattributes")
    with open(gitattributes_path, "w", encoding="utf-8") as f:
        f.write("\n".join(_LFS_PATTERNS) + "\n")

    return {"lfs_configured": True, "gitattributes_path": gitattributes_path}


def should_use_lfs(filename: str, file_bytes: bytes) -> bool:
    """
    Returns True if a file should be handled by LFS based on its
    extension or size exceeding the threshold.
    """
    ext = os.path.splitext(filename)[1].lower()
    return ext in LFS_EXTENSIONS or len(file_bytes) > LFS_SIZE_THRESHOLD_BYTES


def disable_lfs(workspace_dir: str) -> dict:
    """
    Disables Git LFS for the workspace by removing all LFS filter lines from
    .gitattributes. If the file becomes empty after removal it is deleted entirely.

    Returns:
        dict — { lfs_configured: False, gitattributes_removed: bool }
    """
    gitattributes_path = os.path.join(workspace_dir, ".gitattributes")

    if not os.path.exists(gitattributes_path):
        return {"lfs_configured": False, "gitattributes_removed": False}

    with open(gitattributes_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    kept = [
        line for line in lines
        if "filter=lfs" not in line and not line.strip().startswith("# Git LFS")
    ]

    # Strip blank lines left over at the top/bottom
    stripped = [l for l in kept if l.strip()]

    if stripped:
        with open(gitattributes_path, "w", encoding="utf-8") as f:
            f.writelines(stripped)
        return {"lfs_configured": False, "gitattributes_removed": False}
    else:
        os.remove(gitattributes_path)
        return {"lfs_configured": False, "gitattributes_removed": True}


def get_lfs_storage_usage(workspace_dir: str) -> dict:
    """
    Returns LFS storage usage for the workspace by walking the local
    LFS object store at .git/lfs/objects/.

    Returns:
        dict — { lfs_available, lfs_configured, total_bytes, total_mb, file_count }
    """
    lfs_available = is_lfs_available()
    gitattributes_path = os.path.join(workspace_dir, ".gitattributes")
    lfs_configured = os.path.exists(gitattributes_path) and "filter=lfs" in open(
        gitattributes_path, encoding="utf-8"
    ).read()

    lfs_objects_dir = os.path.join(workspace_dir, ".git", "lfs", "objects")
    total_bytes = 0
    file_count = 0
    if os.path.exists(lfs_objects_dir):
        for root, _, files in os.walk(lfs_objects_dir):
            for fname in files:
                fp = os.path.join(root, fname)
                total_bytes += os.path.getsize(fp)
                file_count += 1

    return {
        "lfs_available": lfs_available,
        "lfs_configured": lfs_configured,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "file_count": file_count,
    }
