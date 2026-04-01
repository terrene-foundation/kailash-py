# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures for MCP platform server integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_PROJECT = (
    Path(__file__).resolve().parent.parent.parent / "fixtures" / "mcp_test_project"
)


@pytest.fixture
def fixture_project() -> Path:
    """Path to the MCP test fixture project."""
    assert FIXTURE_PROJECT.is_dir(), f"Fixture project not found at {FIXTURE_PROJECT}"
    return FIXTURE_PROJECT
