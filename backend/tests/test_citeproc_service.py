# backend/tests/test_citeproc_service.py

"""
Unit tests for the CSL-based citation formatting service (REQ-3.3.4).
No network access required — all tests use in-process data.
"""

import pytest

from backend.services.citeproc_service import (
    format_citations,
    _authors,
    _year,
    _title,
    _format_apa,
    _format_ieee,
    _format_nature,
    _format_chicago,
    _format_vancouver,
    STYLES,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

def _ref(id="smith2020", year=2020, authors=None, title="A Great Paper",
         journal="Nature", volume="10", issue="2", pages="123-130", doi="10.1234/abc"):
    return {
        "id":              id,
        "type":            "article-journal",
        "title":           title,
        "author":          authors or [{"family": "Smith", "given": "John"},
                                       {"family": "Doe",   "given": "Jane"}],
        "issued":          {"date-parts": [[year]]},
        "container-title": journal,
        "volume":          volume,
        "issue":           issue,
        "page":            pages,
        "DOI":             doi,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Field accessors
# ──────────────────────────────────────────────────────────────────────────────

def test_authors_two():
    ref = _ref()
    result = _authors(ref)
    assert result == ["Smith, J.", "Doe, J."]


def test_authors_empty():
    assert _authors({}) == []


def test_year_from_issued():
    ref = _ref(year=2021)
    assert _year(ref) == "2021"


def test_year_missing_returns_nd():
    assert _year({}) == "n.d."


def test_title_string():
    assert _title({"title": "Hello World"}) == "Hello World"


def test_title_list():
    assert _title({"title": ["Hello World"]}) == "Hello World"


def test_title_missing():
    assert _title({}) == ""


# ──────────────────────────────────────────────────────────────────────────────
# Per-style formatter output
# ──────────────────────────────────────────────────────────────────────────────

def test_format_apa_inline():
    r = _format_apa(_ref(), 0)
    assert "Smith" in r["inline"]
    assert "2020" in r["inline"]


def test_format_apa_bibliography_contains_journal():
    r = _format_apa(_ref(), 0)
    assert "Nature" in r["bibliography_html"]


def test_format_ieee_inline_is_bracketed_number():
    r = _format_ieee(_ref(), 3)
    assert r["inline"] == "[3]"


def test_format_ieee_bibliography_starts_with_number():
    r = _format_ieee(_ref(), 1)
    assert r["bibliography_html"].startswith("[1]")


def test_format_nature_inline_is_superscript():
    r = _format_nature(_ref(), 2)
    assert r["inline"] == "<sup>2</sup>"


def test_format_nature_bibliography_starts_with_number():
    r = _format_nature(_ref(), 2)
    assert r["bibliography_html"].startswith("2.")


def test_format_chicago_inline_author_year():
    r = _format_chicago(_ref(), 0)
    assert "Smith" in r["inline"]
    assert "2020" in r["inline"]


def test_format_vancouver_inline_parenthesised():
    r = _format_vancouver(_ref(), 4)
    assert r["inline"] == "(4)"


def test_format_vancouver_bibliography_starts_with_number():
    r = _format_vancouver(_ref(), 4)
    assert r["bibliography_html"].startswith("4.")


# ──────────────────────────────────────────────────────────────────────────────
# format_citations — full pipeline
# ──────────────────────────────────────────────────────────────────────────────

def test_format_citations_apa_returns_inline_and_bib():
    refs = [_ref("r1")]
    result = format_citations(refs, ["r1"], style="apa")
    assert result["style"] == "apa"
    assert "r1" in result["inline_map"]
    assert "Smith" in result["inline_map"]["r1"]
    assert result["bibliography_html"] != ""
    assert result["unresolved_keys"] == []


def test_format_citations_ieee_numeric():
    refs = [_ref("r1"), _ref("r2", year=2019, title="Another Paper")]
    result = format_citations(refs, ["r1", "r2"], style="ieee")
    assert result["inline_map"]["r1"] == "[1]"
    assert result["inline_map"]["r2"] == "[2]"


def test_format_citations_nature_superscript():
    refs = [_ref("r1")]
    result = format_citations(refs, ["r1"], style="nature")
    assert result["inline_map"]["r1"] == "<sup>1</sup>"


def test_format_citations_unresolved_key_reported():
    refs = [_ref("r1")]
    result = format_citations(refs, ["r1", "missing_key"], style="apa")
    assert "missing_key" in result["unresolved_keys"]
    assert "r1" in result["inline_map"]


def test_format_citations_duplicate_keys_same_inline():
    """Same key cited twice must produce the same inline citation."""
    refs = [_ref("r1")]
    result = format_citations(refs, ["r1", "r1"], style="ieee")
    assert result["inline_map"]["r1"] == "[1]"
    # Duplicate key — still only one bibliography entry
    assert result["bibliography_html"].count("[1]") == 1


def test_format_citations_empty_references():
    result = format_citations([], [], style="apa")
    assert result["inline_map"] == {}
    assert result["bibliography_html"] == ""
    assert result["unresolved_keys"] == []


def test_format_citations_unknown_style_falls_back_to_apa():
    refs = [_ref("r1")]
    result = format_citations(refs, ["r1"], style="nonexistent_style_xyz")
    # Should fall back to APA — inline uses author-year format
    assert "Smith" in result["inline_map"]["r1"]


def test_format_citations_bibliography_order_apa_alphabetical():
    """APA bibliography must be alphabetically ordered by family name."""
    refs = [
        _ref("zz", authors=[{"family": "Zorro", "given": "A."}], title="Z Paper"),
        _ref("aa", authors=[{"family": "Aardvark", "given": "B."}], title="A Paper"),
    ]
    result = format_citations(refs, ["zz", "aa"], style="apa")
    bib = result["bibliography_html"]
    assert bib.index("Aardvark") < bib.index("Zorro")


def test_format_citations_bibliography_order_ieee_appearance():
    """IEEE bibliography must follow first-appearance order."""
    refs = [
        _ref("first",  title="First Paper"),
        _ref("second", title="Second Paper"),
    ]
    result = format_citations(refs, ["second", "first"], style="ieee")
    bib = result["bibliography_html"]
    # "second" cited first → [1] should appear before [2]
    assert bib.index("[1]") < bib.index("[2]")
    assert "[1]" in result["inline_map"]["second"]
    assert "[2]" in result["inline_map"]["first"]


def test_styles_dict_contains_required_styles():
    required = {"apa", "ieee", "nature", "chicago", "vancouver", "harvard"}
    assert required.issubset(set(STYLES.keys()))
