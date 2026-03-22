# backend/api/citations_router.py

"""
Citations API — CSL formatting endpoint.
REQ-3.3.4
"""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.citeproc_service import format_citations, STYLES

router = APIRouter()


class FormatRequest(BaseModel):
    references: list[dict]        # CSL-JSON entries, each with an "id" field
    citation_keys: list[str]      # keys appearing in the document
    style: str = "apa"            # target citation style


@router.post("/api/citations/format")
async def format_citation_list(payload: FormatRequest):
    """
    Formats citations for the given CSL-JSON references.

    Request body:
        {
          "references":    [{ "id": "key", "type": "article-journal", ... }],
          "citation_keys": ["key1", "key2", ...],
          "style":         "apa" | "ieee" | "nature" | "chicago" | "vancouver" | "harvard"
        }

    Response:
        {
          "status":             "success",
          "style":              str,
          "inline_map":         { key: inline_citation_html },
          "bibliography_html":  str,
          "unresolved_keys":    [str]
        }
    """
    result = format_citations(
        references=payload.references,
        citation_keys=payload.citation_keys,
        style=payload.style,
    )
    return {"status": "success", **result}


@router.get("/api/citations/styles")
async def list_styles():
    """Returns the available citation style names and their display labels."""
    return {
        "status": "success",
        "styles": [{"id": k, "label": v} for k, v in STYLES.items()],
    }
