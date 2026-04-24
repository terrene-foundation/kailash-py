# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Root conftest for kailash-ml tests."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Marker registration (IT-1 — GPU CI runner acquisition)
#
# These markers are added here so pytest --collect-only exits 0 without
# "unknown mark" warnings and so the CI matrix filter `-m 'cuda or gpu'`
# works correctly on both the self-hosted GPU runner and ubuntu-latest
# (where cuda/gpu tests are auto-deselected because no GPU is present).
#
# MUST: only add markers here — do NOT rewrite any existing conftest logic.
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Register GPU-related markers for kailash-ml test suite."""
    config.addinivalue_line(
        "markers",
        "cuda: tests that require a CUDA-capable GPU "
        "(runs-on: [self-hosted, cuda, gpu] in CI)",
    )
    config.addinivalue_line(
        "markers",
        "gpu: tests that require any GPU backend "
        "(CUDA, MPS/Metal, or ROCm); "
        "superset of the cuda marker",
    )
    config.addinivalue_line(
        "markers",
        "mps: tests that require Apple MPS / Metal GPU " "(macos-14 runner in CI)",
    )
