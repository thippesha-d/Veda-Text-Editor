# backend/api/lifecycle_router.py
"""
REST endpoints for the article lifecycle state machine (REQ-3.4.1–3.4.4).

GET  /api/lifecycle/state               - current state + metadata
POST /api/lifecycle/transition          - transition to a new state
GET  /api/lifecycle/history             - state transition history
POST /api/lifecycle/article-doi         - register article DOI / publisher URL
POST /api/lifecycle/alerts/acknowledge  - dismiss all active alerts
POST /api/lifecycle/poll                - immediate Crossref poll for own DOI
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.lifecycle_service import (
    get_state,
    transition_state,
    set_article_doi,
    acknowledge_alerts,
    poll_article_doi,
)

router = APIRouter()


class TransitionRequest(BaseModel):
    workspace_path: str
    new_state: str
    note: str = ""


class ArticleDoiRequest(BaseModel):
    workspace_path: str
    doi: str
    publisher_url: str = ""


class WorkspaceRequest(BaseModel):
    workspace_path: str


@router.get("/api/lifecycle/state")
async def get_lifecycle_state(workspace_path: str):
    try:
        return get_state(workspace_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/lifecycle/history")
async def get_lifecycle_history(workspace_path: str):
    try:
        data = get_state(workspace_path)
        return {"history": data["state_history"]}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/lifecycle/transition")
async def lifecycle_transition(payload: TransitionRequest):
    try:
        return transition_state(payload.workspace_path, payload.new_state, payload.note)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/lifecycle/article-doi")
async def set_lifecycle_doi(payload: ArticleDoiRequest):
    try:
        return set_article_doi(payload.workspace_path, payload.doi, payload.publisher_url)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/lifecycle/alerts/acknowledge")
async def acknowledge_lifecycle_alerts(payload: WorkspaceRequest):
    try:
        return acknowledge_alerts(payload.workspace_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/lifecycle/poll")
async def poll_lifecycle(payload: WorkspaceRequest):
    try:
        alert = poll_article_doi(payload.workspace_path)
        return {"alert": alert}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
