# backend/api/references_router.py

"""
References API — DOI validation endpoint.
REQ-3.3.1 / REQ-3.3.2
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter
from pydantic import BaseModel

from fastapi import HTTPException
from backend.services.doi_service import validate_doi
from backend.services.file_service import (
    load_manual_references,
    save_manual_reference,
    delete_manual_reference,
)

router = APIRouter()

# Thread pool for synchronous Crossref HTTP calls (keeps the async event loop free)
_executor = ThreadPoolExecutor(max_workers=4)

# Hard cap per request to prevent abuse
_MAX_DOIS_PER_REQUEST = 20


class ValidateRequest(BaseModel):
    dois: list[str]


import os

class ManualRefRequest(BaseModel):
    workspace_path: str
    ref: dict

class ManualRefDeleteRequest(BaseModel):
    workspace_path: str


@router.get("/api/references/manual")
async def get_manual_references(workspace_path: str):
    if not os.path.exists(workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        return {"refs": load_manual_references(workspace_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/references/manual")
async def add_manual_reference(payload: ManualRefRequest):
    if not os.path.exists(payload.workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        saved = save_manual_reference(payload.workspace_path, payload.ref)
        return {"status": "success", "ref": saved}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/references/manual/{ref_id}")
async def remove_manual_reference(ref_id: str, workspace_path: str):
    if not os.path.exists(workspace_path):
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        return delete_manual_reference(workspace_path, ref_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/references/validate")
async def validate_references(payload: ValidateRequest):
    """
    Validates up to 20 DOIs per request against the Crossref REST API.

    Request body:  { "dois": ["10.xxxx/...", ...] }
    Response:      { "status": "success", "results": [{ doi, status, title,
                     authors, year, flag_reason }, ...] }

    status values: valid | retracted | corrected | expression-of-concern | not-found
    """
    dois = payload.dois[:_MAX_DOIS_PER_REQUEST]
    if not dois:
        return {"status": "success", "results": []}

    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(_executor, validate_doi, doi) for doi in dois]
    results = await asyncio.gather(*tasks)

    return {"status": "success", "results": list(results)}
