"""Cross-SDK test fixtures for semantic parity validation.

Per SPEC-09 §8.2, JSON parsing uses strict=True to detect parser differential
vulnerabilities (BOM handling, duplicate keys, trailing commas).
"""

import json
from pathlib import Path

import pytest

VECTOR_ROOT = Path(__file__).parent.parent.parent / "fixtures" / "cross-sdk"


@pytest.fixture(scope="session")
def vector_dir() -> Path:
    """Root directory containing cross-SDK test vectors."""
    return VECTOR_ROOT


@pytest.fixture(scope="session")
def load_vector():
    """Load a JSON test vector with strict parsing.

    Per SPEC-09 §8.2 canonical parser config: strict=True rejects
    duplicate keys, BOMs, and trailing commas to ensure both Python
    and Rust parsers reach the same conclusion on every input.
    """

    def _load(subdir: str, filename: str) -> dict:
        vector_path = VECTOR_ROOT / subdir / filename
        if not vector_path.exists():
            raise FileNotFoundError(f"Test vector not found: {vector_path}")
        text = vector_path.read_text()
        return json.loads(text, strict=True)

    return _load
