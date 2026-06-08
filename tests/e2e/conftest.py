"""Shared fixtures for e2e tests — these tests require pxr (Pixar USD)."""

from __future__ import annotations

import pytest

pxr = pytest.importorskip("pxr")


@pytest.fixture
def stage_file(tmp_path):
    """Create a minimal stage and return its path."""
    from dcc_mcp_openusd.runtime import create_stage

    path = tmp_path / "scene.usda"
    create_stage(str(path), name="e2e_test")
    return path
