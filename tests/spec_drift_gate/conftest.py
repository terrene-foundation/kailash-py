# Shared fixtures + path setup for spec_drift_gate tests.
#
# The gate ships as a top-level script at scripts/spec_drift_gate.py and is
# imported under the package name `spec_drift_gate` for testing. This conftest
# adds the scripts/ directory to sys.path so the tests can import it.

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


import pytest


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def fixtures_dir() -> Path:
    return REPO_ROOT / "tests" / "fixtures" / "spec_drift_gate"
