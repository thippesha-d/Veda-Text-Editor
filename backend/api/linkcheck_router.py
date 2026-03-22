# backend/api/linkcheck_router.py

"""
Link-check API endpoints.
REQ-3.3.3
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.link_checker_service import (
    run_link_check,
    load_link_log,
)

router = APIRouter()

# Thread pool — link checks are synchronous HTTP calls
_executor = ThreadPoolExecutor(max_workers=5)


class LinkCheckRequest(BaseModel):
    workspace_path: str
    html_content: str


@router.post("/api/links/check")
async def trigger_link_check(payload: LinkCheckRequest):
    """
    Extracts all HTTP/HTTPS URLs from html_content, checks each one,
    persists results to the workspace link-check log, and returns the
    updated log.

    Response: { status, results: [{ url, status, http_code, checked_at }] }
    status values per entry:
        alive | dead | redirect | server_error | access_denied |
        unreachable | ssl_warning | unknown
    """
    import os
    if not os.path.exists(payload.workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found")

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        _executor,
        run_link_check,
        payload.workspace_path,
        payload.html_content,
    )
    return {"status": "success", "results": results}


@router.get("/api/links/status")
async def get_link_status(workspace_path: str):
    """
    Returns the persisted link-check log for the workspace without
    triggering a new check.
    """
    import os
    if not os.path.exists(workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found")

    log = load_link_log(workspace_path)
    return {"status": "success", "results": log}
