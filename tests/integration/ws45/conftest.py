# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for WS-4.5 cross-framework integration tests."""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_PROJECT = Path(__file__).parent.parent.parent / "fixtures" / "mcp_test_project"
