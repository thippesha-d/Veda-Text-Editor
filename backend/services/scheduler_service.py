# backend/services/scheduler_service.py
import os
import time
import threading
from backend.services.git_service import auto_commit

# ---------------------------------------------------------------------------
# Auto-commit loop
# ---------------------------------------------------------------------------

def background_auto_commit_loop(interval_seconds: int = 300):
    """
    Periodically scans the workspace directory and auto-commits changes.
    """
    while True:
        time.sleep(interval_seconds)
        base_dir = os.environ.get("WORKSPACE_DIR", "./workspace")
        if os.path.exists(base_dir):
            # Iterate through all created workspaces
            for item in os.listdir(base_dir):
                workspace_dir = os.path.join(base_dir, item)
                if os.path.isdir(workspace_dir) and os.path.exists(os.path.join(workspace_dir, ".git")):
                    try:
                        auto_commit(workspace_dir, "Timer")
                    except Exception as e:
                        print(f"Auto-commit check failed for {workspace_dir}: {e}")

# ---------------------------------------------------------------------------
# Article DOI poll loop  (REQ-3.4.3 — 24-hour background poll)
# ---------------------------------------------------------------------------

_DOI_POLL_INTERVAL = 86400  # 24 hours


def _doi_poll_loop():
    """
    Runs once every 24 hours; queries Crossref for each workspace's
    article_doi and generates alerts for adverse events (retraction, etc.).
    """
    while True:
        time.sleep(_DOI_POLL_INTERVAL)
        base_dir = os.environ.get("WORKSPACE_DIR", "./workspace")
        if not os.path.exists(base_dir):
            continue
        for item in os.listdir(base_dir):
            workspace_dir = os.path.join(base_dir, item)
            manifest_path = os.path.join(workspace_dir, "workspace.json")
            if os.path.isdir(workspace_dir) and os.path.exists(manifest_path):
                try:
                    from backend.services.lifecycle_service import poll_article_doi
                    poll_article_doi(workspace_dir)
                except Exception as e:
                    print(f"DOI poll failed for {workspace_dir}: {e}")


# ---------------------------------------------------------------------------

def start_scheduler():
    """Starts the auto-commit and DOI-poll loops as daemon threads."""
    interval = int(os.environ.get("AUTO_COMMIT_INTERVAL", "300"))
    t1 = threading.Thread(target=background_auto_commit_loop, args=(interval,), daemon=True)
    t1.start()

    t2 = threading.Thread(target=_doi_poll_loop, daemon=True)
    t2.start()

    return t1
