# backend/tests/test_lfs_service.py

"""
Regression tests for backend/services/lfs_service.py
REQ-3.2.4 — Git LFS for Large Files
"""

import os
import pytest
from unittest.mock import patch

from backend.services.lfs_service import (
    is_lfs_available,
    configure_lfs,
    disable_lfs,
    should_use_lfs,
    get_lfs_storage_usage,
    LFS_EXTENSIONS,
    LFS_SIZE_THRESHOLD_BYTES,
)


# ────────────────────────────────────────────────────────────────
# TEST: is_lfs_available
# ────────────────────────────────────────────────────────────────

def test_is_lfs_available_returns_bool():
    """is_lfs_available must always return a bool regardless of system state."""
    result = is_lfs_available()
    assert isinstance(result, bool)


def test_is_lfs_available_false_when_git_lfs_missing():
    """is_lfs_available must return False when git-lfs is not on PATH."""
    with patch("backend.services.lfs_service.subprocess.run", side_effect=FileNotFoundError):
        assert is_lfs_available() is False


def test_is_lfs_available_false_on_nonzero_returncode():
    """is_lfs_available must return False when git lfs version exits non-zero."""
    import subprocess
    mock_result = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
    with patch("backend.services.lfs_service.subprocess.run", return_value=mock_result):
        assert is_lfs_available() is False


def test_is_lfs_available_true_on_zero_returncode():
    """is_lfs_available must return True when git lfs version exits zero."""
    import subprocess
    mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="git-lfs/3.0.0", stderr="")
    with patch("backend.services.lfs_service.subprocess.run", return_value=mock_result):
        assert is_lfs_available() is True


# ────────────────────────────────────────────────────────────────
# TEST: should_use_lfs
# ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("filename", [
    "data.csv", "model.mat", "archive.zip",
    "dataset.h5", "sim.sim", "capture.raw",
])
def test_should_use_lfs_tracked_extensions(filename):
    """should_use_lfs must return True for all LFS-tracked extensions."""
    assert should_use_lfs(filename, b"small content") is True


def test_should_use_lfs_large_file_any_extension():
    """should_use_lfs must return True for any file exceeding the size threshold."""
    large_content = b"x" * (LFS_SIZE_THRESHOLD_BYTES + 1)
    assert should_use_lfs("document.pdf", large_content) is True


def test_should_use_lfs_small_image_not_tracked():
    """should_use_lfs must return False for small images with untracked extensions."""
    assert should_use_lfs("photo.png", b"small image data") is False


def test_should_use_lfs_exactly_at_threshold_not_tracked():
    """should_use_lfs must return False for files exactly at (not over) the threshold."""
    content = b"x" * LFS_SIZE_THRESHOLD_BYTES
    assert should_use_lfs("file.pdf", content) is False


# ────────────────────────────────────────────────────────────────
# TEST: configure_lfs
# ────────────────────────────────────────────────────────────────

def test_configure_lfs_writes_gitattributes(tmp_path):
    """configure_lfs must write .gitattributes with LFS filter patterns."""
    import subprocess
    mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("backend.services.lfs_service.subprocess.run", return_value=mock_result):
        result = configure_lfs(str(tmp_path))

    assert result["lfs_configured"] is True
    gitattributes = tmp_path / ".gitattributes"
    assert gitattributes.exists()
    content = gitattributes.read_text(encoding="utf-8")
    assert "filter=lfs" in content
    for ext in LFS_EXTENSIONS:
        assert f"*{ext}" in content


def test_configure_lfs_does_not_run_git_lfs_install(tmp_path):
    """configure_lfs must NOT invoke git lfs install --local.
    On Windows, hook scripts written by git-lfs contain unquoted paths
    which GitPython fails to execute when the path contains spaces."""
    import subprocess
    with patch("backend.services.lfs_service.subprocess.run") as mock_run:
        configure_lfs(str(tmp_path))

    mock_run.assert_not_called()


# ────────────────────────────────────────────────────────────────
# TEST: get_lfs_storage_usage
# ────────────────────────────────────────────────────────────────

def test_get_lfs_storage_usage_no_lfs_objects(tmp_path):
    """get_lfs_storage_usage must return zero counts when no LFS objects exist."""
    with patch("backend.services.lfs_service.is_lfs_available", return_value=False):
        result = get_lfs_storage_usage(str(tmp_path))

    assert result["total_bytes"] == 0
    assert result["total_mb"] == 0.0
    assert result["file_count"] == 0
    assert result["lfs_available"] is False
    assert result["lfs_configured"] is False


def test_get_lfs_storage_usage_counts_objects(tmp_path):
    """get_lfs_storage_usage must sum sizes of files in .git/lfs/objects/."""
    lfs_dir = tmp_path / ".git" / "lfs" / "objects" / "ab" / "cd"
    lfs_dir.mkdir(parents=True)
    (lfs_dir / "object1").write_bytes(b"x" * 1024)
    (lfs_dir / "object2").write_bytes(b"x" * 2048)

    with patch("backend.services.lfs_service.is_lfs_available", return_value=True):
        result = get_lfs_storage_usage(str(tmp_path))

    assert result["total_bytes"] == 3072
    assert result["file_count"] == 2
    assert result["lfs_available"] is True


def test_get_lfs_storage_usage_detects_configured(tmp_path):
    """get_lfs_storage_usage must report lfs_configured=True when .gitattributes has filter=lfs."""
    gitattributes = tmp_path / ".gitattributes"
    gitattributes.write_text("*.csv filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8")

    with patch("backend.services.lfs_service.is_lfs_available", return_value=True):
        result = get_lfs_storage_usage(str(tmp_path))

    assert result["lfs_configured"] is True


# ────────────────────────────────────────────────────────────────
# TEST: disable_lfs
# ────────────────────────────────────────────────────────────────

def test_disable_lfs_removes_lfs_lines(tmp_path):
    """disable_lfs must remove all filter=lfs lines from .gitattributes."""
    gitattributes = tmp_path / ".gitattributes"
    gitattributes.write_text(
        "# Git LFS tracked file patterns (REQ-3.2.4)\n"
        "*.csv filter=lfs diff=lfs merge=lfs -text\n"
        "*.zip filter=lfs diff=lfs merge=lfs -text\n",
        encoding="utf-8",
    )
    result = disable_lfs(str(tmp_path))
    assert result["lfs_configured"] is False
    assert result["gitattributes_removed"] is True
    assert not gitattributes.exists()


def test_disable_lfs_preserves_non_lfs_lines(tmp_path):
    """disable_lfs must keep any non-LFS lines in .gitattributes."""
    gitattributes = tmp_path / ".gitattributes"
    gitattributes.write_text(
        "# Git LFS tracked file patterns (REQ-3.2.4)\n"
        "*.csv filter=lfs diff=lfs merge=lfs -text\n"
        "*.py text eol=lf\n",
        encoding="utf-8",
    )
    result = disable_lfs(str(tmp_path))
    assert result["lfs_configured"] is False
    assert result["gitattributes_removed"] is False
    assert gitattributes.exists()
    content = gitattributes.read_text(encoding="utf-8")
    assert "filter=lfs" not in content
    assert "*.py text eol=lf" in content


def test_disable_lfs_no_gitattributes_is_noop(tmp_path):
    """disable_lfs must return cleanly when .gitattributes does not exist."""
    result = disable_lfs(str(tmp_path))
    assert result["lfs_configured"] is False
    assert result["gitattributes_removed"] is False


def test_enable_lfs_after_disable_reconfigures(tmp_path):
    """configure_lfs called after disable_lfs must restore LFS filter lines."""
    gitattributes = tmp_path / ".gitattributes"
    gitattributes.write_text("*.csv filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8")
    disable_lfs(str(tmp_path))
    assert not gitattributes.exists()

    result = configure_lfs(str(tmp_path))
    assert result["lfs_configured"] is True
    assert gitattributes.exists()
    content = gitattributes.read_text(encoding="utf-8")
    assert "filter=lfs" in content


def test_enable_lfs_on_fresh_workspace_writes_gitattributes(tmp_path):
    """configure_lfs on a workspace with no .gitattributes must create the file."""
    assert not (tmp_path / ".gitattributes").exists()
    result = configure_lfs(str(tmp_path))
    assert result["lfs_configured"] is True
    assert (tmp_path / ".gitattributes").exists()


def test_enable_then_disable_cycle(tmp_path):
    """LFS can be toggled on and off repeatedly without corruption."""
    configure_lfs(str(tmp_path))
    disable_lfs(str(tmp_path))
    configure_lfs(str(tmp_path))
    disable_lfs(str(tmp_path))
    assert not (tmp_path / ".gitattributes").exists()


def test_disable_lfs_then_get_status_shows_unconfigured(tmp_path):
    """After disable_lfs, get_lfs_storage_usage must report lfs_configured=False."""
    gitattributes = tmp_path / ".gitattributes"
    gitattributes.write_text("*.csv filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8")

    disable_lfs(str(tmp_path))

    with patch("backend.services.lfs_service.is_lfs_available", return_value=True):
        status = get_lfs_storage_usage(str(tmp_path))
    assert status["lfs_configured"] is False
