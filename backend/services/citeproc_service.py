# backend/services/citeproc_service.py

"""
CSL-based citation formatting service.
REQ-3.3.4

Supports five built-in styles via Python formatters (APA, IEEE, Nature,
Chicago, Vancouver) and the Harvard style via citeproc-py's bundled CSL file.
Falls back to APA when an unknown style name is requested.

CSL-JSON input format  (per entry):
    {
        "id":              str,           # citation key used in document
        "type":            str,           # "article-journal", "book", etc.
        "title":           str | [str],
        "author":          [{"family": str, "given": str}, ...],
        "issued":          {"date-parts": [[year, month?, day?]]},
        "container-title": str,           # journal / book title
        "volume":          str | int,
        "issue":           str | int,
        "page":            str,
        "DOI":             str,
    }
"""

import os
from typing import Optional

# ---------------------------------------------------------------------------
# Available styles
# ---------------------------------------------------------------------------

STYLES: dict[str, str] = {
    "apa":       "APA (7th ed.)",
    "ieee":      "IEEE",
    "nature":    "Nature",
    "chicago":   "Chicago (Author-Date)",
    "vancouver": "Vancouver",
    "harvard":   "Harvard",
}

_FALLBACK_STYLE = "apa"


# ---------------------------------------------------------------------------
# CSL-JSON field accessors
# ---------------------------------------------------------------------------

def _authors(ref: dict, max_count: int = 6) -> list[str]:
    """Returns formatted author strings 'Family, G.'"""
    result = []
    for a in ref.get("author", []):
        family = a.get("family", "")
        given  = a.get("given", "")
        init   = f"{given[0]}." if given else ""
        if family:
            result.append(f"{family}, {init}" if init else family)
    return result


def _year(ref: dict) -> str:
    for field in ("issued", "published-print", "published-online", "created"):
        v = ref.get(field)
        if isinstance(v, dict):
            parts = v.get("date-parts", [[]])
            if parts and parts[0]:
                return str(parts[0][0])
    return "n.d."


def _title(ref: dict) -> str:
    t = ref.get("title", "")
    return t[0] if isinstance(t, list) and t else (t or "")


def _journal(ref: dict) -> str:
    return str(ref.get("container-title", ""))


def _vol(ref: dict) -> str:
    return str(ref.get("volume", ""))


def _issue(ref: dict) -> str:
    return str(ref.get("issue", ""))


def _pages(ref: dict) -> str:
    return str(ref.get("page", ""))


def _doi_url(ref: dict) -> str:
    doi = ref.get("DOI", "")
    return f"https://doi.org/{doi}" if doi else ""


def _doi_link(ref: dict) -> str:
    """Returns an HTML hyperlink for the DOI, or empty string if none."""
    url = _doi_url(ref)
    doi = ref.get("DOI", "")
    return f'<a href="{url}">{doi}</a>' if doi else ""


# ---------------------------------------------------------------------------
# Style-specific formatters
# Each returns { "inline": str, "bibliography_html": str }
# ---------------------------------------------------------------------------

def _format_apa(ref: dict, number: int = 0) -> dict:
    """APA 7th edition (Author-Date)."""
    authors = _authors(ref)
    year    = _year(ref)
    title   = _title(ref)
    journal = _journal(ref)
    volume  = _vol(ref)
    issue   = _issue(ref)
    pages   = _pages(ref)

    if not authors:
        author_str   = "Unknown"
        inline_auth  = "Unknown"
    elif len(authors) <= 2:
        author_str  = " & ".join(authors)
        inline_auth = " & ".join(a.split(",")[0] for a in authors)
    else:
        author_str  = ", ".join(authors[:-1]) + ", & " + authors[-1]
        inline_auth = authors[0].split(",")[0] + " et al."

    inline = f"({inline_auth}, {year})"

    parts = [f"{author_str} ({year}). {title}."]
    if journal:
        entry = f"<i>{journal}</i>"
        if volume:
            entry += f", <i>{volume}</i>"
            if issue:
                entry += f"({issue})"
        if pages:
            entry += f", {pages}"
        parts.append(entry + ".")
    doi_url = _doi_url(ref)
    if doi_url:
        parts.append(f'<a href="{doi_url}">{doi_url}</a>')

    return {"inline": inline, "bibliography_html": " ".join(parts)}


def _format_ieee(ref: dict, number: int = 1) -> dict:
    """IEEE (Numeric, [N])."""
    authors = _authors(ref)
    year    = _year(ref)
    title   = _title(ref)
    journal = _journal(ref)
    volume  = _vol(ref)
    issue   = _issue(ref)
    pages   = _pages(ref)

    if len(authors) > 6:
        author_str = ", ".join(authors[:6]) + " et al."
    else:
        author_str = ", ".join(authors)

    inline = f"[{number}]"

    parts: list[str] = []
    if author_str:
        parts.append(author_str + ",")
    parts.append(f'"{title},"')
    if journal:
        parts.append(f"<i>{journal}</i>,")
    if volume:
        parts.append(f"vol. {volume},")
    if issue:
        parts.append(f"no. {issue},")
    if pages:
        parts.append(f"pp. {pages},")
    parts.append(f"{year}.")
    doi_link = _doi_link(ref)
    if doi_link:
        parts.append(f"doi: {doi_link}")

    bib_html = f"[{number}] " + " ".join(parts)
    return {"inline": inline, "bibliography_html": bib_html}


def _format_nature(ref: dict, number: int = 1) -> dict:
    """Nature (Numeric, superscript inline)."""
    authors = _authors(ref)
    year    = _year(ref)
    title   = _title(ref)
    journal = _journal(ref)
    volume  = _vol(ref)
    pages   = _pages(ref)

    if len(authors) > 6:
        author_str = ", ".join(authors[:6]) + " et al."
    else:
        author_str = ", ".join(authors)

    inline = f"<sup>{number}</sup>"

    parts = []
    if author_str:
        parts.append(author_str + ".")
    parts.append(f"{title}.")
    if journal:
        entry = f"<i>{journal}</i>"
        if volume:
            entry += f" <b>{volume}</b>"
        if pages:
            entry += f", {pages}"
        entry += f" ({year})."
        parts.append(entry)
    doi_link = _doi_link(ref)
    if doi_link:
        parts.append(doi_link)

    bib_html = f"{number}. " + " ".join(parts)
    return {"inline": inline, "bibliography_html": bib_html}


def _format_chicago(ref: dict, number: int = 0) -> dict:
    """Chicago Author-Date."""
    authors = _authors(ref)
    year    = _year(ref)
    title   = _title(ref)
    journal = _journal(ref)
    volume  = _vol(ref)
    issue   = _issue(ref)
    pages   = _pages(ref)

    if not authors:
        author_str  = "Unknown"
        inline_auth = "Unknown"
    elif len(authors) <= 3:
        if len(authors) == 1:
            author_str = authors[0]
        else:
            author_str = ", ".join(authors[:-1]) + ", and " + authors[-1]
        inline_auth = " and ".join(a.split(",")[0] for a in authors)
    else:
        author_str  = authors[0] + " et al."
        inline_auth = authors[0].split(",")[0] + " et al."

    inline = f"({inline_auth} {year})"

    parts = [f"{author_str}. {year}."]
    parts.append(f'"{title}."')
    if journal:
        entry = f"<i>{journal}</i>"
        if volume:
            entry += f" {volume}"
            if issue:
                entry += f" ({issue})"
        if pages:
            entry += f": {pages}"
        parts.append(entry + ".")
    doi_link = _doi_link(ref)
    if doi_link:
        parts.append(doi_link)

    return {"inline": inline, "bibliography_html": " ".join(parts)}


def _format_vancouver(ref: dict, number: int = 1) -> dict:
    """Vancouver (Numeric, (N) inline)."""
    authors = _authors(ref)
    year    = _year(ref)
    title   = _title(ref)
    journal = _journal(ref)
    volume  = _vol(ref)
    issue   = _issue(ref)
    pages   = _pages(ref)

    if len(authors) > 6:
        author_str = ", ".join(authors[:6]) + ", et al."
    else:
        author_str = ", ".join(authors)

    inline = f"({number})"

    parts: list[str] = []
    if author_str:
        parts.append(author_str + ".")
    parts.append(f"{title}.")
    if journal:
        entry = journal
        if year:
            entry += f" {year}"
        if volume:
            entry += f";{volume}"
            if issue:
                entry += f"({issue})"
        if pages:
            entry += f":{pages}"
        parts.append(entry + ".")
    doi_link = _doi_link(ref)
    if doi_link:
        parts.append(doi_link)

    bib_html = f"{number}. " + " ".join(parts)
    return {"inline": inline, "bibliography_html": bib_html}


# ---------------------------------------------------------------------------
# citeproc-py pathway  (Harvard style — bundled CSL file)
# ---------------------------------------------------------------------------

def _csl_path(style_name: str) -> Optional[str]:
    """Returns path to the bundled .csl file for style_name, or None."""
    try:
        import citeproc as _cp
        data_dir = os.path.join(os.path.dirname(_cp.__file__), "data", "styles")
        path = os.path.join(data_dir, f"{style_name}.csl")
        return path if os.path.exists(path) else None
    except Exception:
        return None


def _format_with_citeproc(
    references: list[dict],
    citation_keys: list[str],
    style_name: str,
) -> Optional[dict]:
    """
    Formats using citeproc-py + a bundled .csl file.
    Returns None if the style file cannot be found or citeproc-py errors.
    """
    style_path = _csl_path(style_name)
    if not style_path:
        return None
    try:
        from citeproc import CitationStylesStyle, CitationStylesBibliography
        from citeproc import Citation, CitationItem
        from citeproc.source.json import CiteProcJSON

        bib_source   = CiteProcJSON(references)
        style_obj    = CitationStylesStyle(style_path, locale="en-US", validate=False)
        bibliography = CitationStylesBibliography(style_obj, bib_source)

        inline_map: dict[str, str] = {}
        ref_ids = {r.get("id") for r in references}
        for key in citation_keys:
            if key in ref_ids:
                cit      = Citation([CitationItem(key)])
                bibliography.register(cit)
                rendered = bibliography.cite(cit, lambda x, y: None)
                inline_map[key] = rendered or ""

        bib_items = bibliography.bibliography()
        bib_html  = "\n".join(f'<p class="bib-entry">{str(item)}</p>' for item in bib_items)

        return {"inline_map": inline_map, "bibliography_html": bib_html}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Formatter dispatch
# ---------------------------------------------------------------------------

_FORMATTERS = {
    "apa":       _format_apa,
    "ieee":      _format_ieee,
    "nature":    _format_nature,
    "chicago":   _format_chicago,
    "vancouver": _format_vancouver,
}

_AUTHOR_DATE_STYLES = {"apa", "chicago", "harvard"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def format_citations(
    references: list[dict],
    citation_keys: list[str],
    style: str = "apa",
) -> dict:
    """
    Formats citations for the given CSL-JSON references.

    Args:
        references:    List of CSL-JSON dicts (each MUST have an "id" field).
        citation_keys: Ordered list of citation key strings appearing in the
                       document (duplicates allowed — each unique key rendered once).
        style:         One of the STYLES keys (default "apa").

    Returns:
        {
            style:             str,
            inline_map:        { key: inline_html },
            bibliography_html: str,    # full bibliography as HTML
            unresolved_keys:   [str],  # keys with no matching reference
        }
    """
    style = style.lower().strip()

    # Try citeproc-py for Harvard (or any style with a bundled .csl file)
    if style not in _FORMATTERS:
        cp_result = _format_with_citeproc(references, citation_keys, style)
        if cp_result:
            resolved   = set(cp_result["inline_map"].keys())
            unresolved = [k for k in citation_keys if k not in resolved]
            return {
                "style":             style,
                "inline_map":        cp_result["inline_map"],
                "bibliography_html": cp_result["bibliography_html"],
                "unresolved_keys":   list(set(unresolved)),
            }
        # Style not found — fall back to APA with a notification
        style = _FALLBACK_STYLE

    formatter  = _FORMATTERS[style]
    ref_by_id  = {r.get("id", ""): r for r in references}

    # First-appearance order → citation number for numeric styles
    seen_order: list[str] = []
    for key in citation_keys:
        if key not in seen_order and key in ref_by_id:
            seen_order.append(key)

    inline_map:   dict[str, str] = {}
    unresolved:   list[str]      = []

    for key in citation_keys:
        if key not in ref_by_id:
            unresolved.append(key)
            continue
        if key not in inline_map:
            number          = seen_order.index(key) + 1 if key in seen_order else 1
            inline_map[key] = formatter(ref_by_id[key], number)["inline"]

    # Bibliography order: alphabetical (author-date) or appearance (numeric)
    if style in _AUTHOR_DATE_STYLES:
        bib_keys = sorted(
            seen_order,
            key=lambda k: (ref_by_id[k].get("author") or [{}])[0].get("family", ""),
        )
    else:
        bib_keys = seen_order

    bib_entries: list[str] = []
    for key in bib_keys:
        number = seen_order.index(key) + 1
        entry  = formatter(ref_by_id[key], number)
        bib_entries.append(f'<p class="bib-entry">{entry["bibliography_html"]}</p>')

    return {
        "style":             style,
        "inline_map":        inline_map,
        "bibliography_html": "\n".join(bib_entries),
        "unresolved_keys":   list(set(unresolved)),
    }
