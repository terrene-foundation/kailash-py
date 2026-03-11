"""
E2E Tests for Documentation UX Improvements

Tests validate that documentation exists and contains required content.

These tests follow TDD: They will FAIL initially until documentation is created.
This is expected behavior - we write tests FIRST, then implement.
"""

import os
import re
from pathlib import Path

import pytest

# Base path for Nexus documentation (relative to test file)
NEXUS_ROOT = Path(__file__).parent.parent.parent
NEXUS_DOCS_BASE = NEXUS_ROOT / "docs"


def test_fastapi_mount_documentation_exists():
    """Test that FastAPI mount behavior documentation exists with required sections."""
    doc_path = NEXUS_DOCS_BASE / "technical" / "fastapi-mount-behavior.md"

    # File must exist
    assert doc_path.exists(), f"Documentation not found at {doc_path}"

    content = doc_path.read_text()

    # Check for key concepts (flexible matching)
    assert re.search(
        r"#+ Understanding.*FastAPI.*Mount", content, re.IGNORECASE
    ), "Missing 'Understanding FastAPI Mount Behavior' section"

    # Must explain that mounted routes don't appear in OpenAPI (case-insensitive)
    assert (
        "do not appear" in content.lower() and "openapi" in content.lower()
    ), "Missing explanation of OpenAPI behavior"

    # Must include endpoint patterns
    assert (
        "/execute" in content and "/workflow/info" in content
    ), "Missing endpoint pattern examples"

    # Must link to FastAPI official docs
    assert "fastapi.tiangolo.com" in content, "Missing link to FastAPI documentation"


def test_workflow_registration_guide_updated():
    """Test that workflow registration guide includes endpoint patterns."""
    doc_path = NEXUS_DOCS_BASE / "user-guides" / "workflow-registration.md"

    assert doc_path.exists(), f"Documentation not found at {doc_path}"

    content = doc_path.read_text()

    # Must mention endpoint patterns
    assert "endpoint" in content.lower(), "Missing endpoint information"

    # Must show POST /execute pattern
    assert "/execute" in content, "Missing /execute endpoint example"

    # Must show GET /workflow/info pattern
    assert "/workflow/info" in content, "Missing /workflow/info endpoint example"

    # Must have example curl commands or code
    assert (
        "curl" in content.lower() or "requests.post" in content
    ), "Missing usage examples"


def test_basic_usage_includes_discovery():
    """Test that basic usage guide includes endpoint discovery methods."""
    doc_path = NEXUS_DOCS_BASE / "getting-started" / "basic-usage.md"

    assert doc_path.exists(), f"Documentation not found at {doc_path}"

    content = doc_path.read_text()

    # Must have discovery section
    assert re.search(
        r"discover", content, re.IGNORECASE
    ), "Missing endpoint discovery section"

    # Must show how to list workflows
    assert "/workflows" in content, "Missing workflow listing endpoint"

    # Must explain endpoint patterns
    assert (
        "/execute" in content or "endpoint" in content.lower()
    ), "Missing endpoint pattern information"


def test_documentation_index_updated():
    """Test that documentation index includes new FastAPI mount behavior doc."""
    doc_path = NEXUS_DOCS_BASE / "README.md"

    assert doc_path.exists(), f"Documentation index not found at {doc_path}"

    content = doc_path.read_text()

    # Must reference new technical documentation
    assert (
        "fastapi" in content.lower() or "mount" in content.lower()
    ), "Missing reference to FastAPI mount behavior documentation"
