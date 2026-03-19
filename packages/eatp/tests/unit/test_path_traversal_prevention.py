# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for path traversal prevention (PS3).

Verifies that validate_id() rejects path traversal attacks while
preserving backward compatibility with existing ID formats.
"""

from __future__ import annotations

import pytest

from eatp.store.filesystem import validate_id


class TestValidateIdTraversalAttacks:
    """PS3: Path traversal attempts must be rejected."""

    def test_rejects_parent_directory_traversal(self):
        """IDs containing '..' must be rejected."""
        with pytest.raises(ValueError, match="path traversal"):
            validate_id("..")

    def test_rejects_embedded_traversal(self):
        """IDs with '../' embedded must be rejected."""
        with pytest.raises(ValueError, match="path traversal"):
            validate_id("../../../etc/passwd")

    def test_rejects_backslash_traversal(self):
        """IDs with '..\\' embedded must be rejected."""
        with pytest.raises(ValueError, match="path traversal"):
            validate_id("..\\..\\windows\\system32")

    def test_rejects_null_bytes(self):
        """IDs with null bytes must be rejected."""
        with pytest.raises(ValueError, match="null"):
            validate_id("agent\x00id")

    def test_rejects_empty_id(self):
        """Empty IDs must be rejected."""
        with pytest.raises(ValueError, match="empty"):
            validate_id("")

    def test_rejects_whitespace_only(self):
        """Whitespace-only IDs must be rejected."""
        with pytest.raises(ValueError, match="empty"):
            validate_id("   ")

    def test_rejects_dot_only(self):
        """Single dot ID must be rejected (current directory reference)."""
        with pytest.raises(ValueError, match="path traversal"):
            validate_id(".")

    def test_rejects_absolute_path(self):
        """IDs starting with / must be rejected."""
        with pytest.raises(ValueError, match="path traversal"):
            validate_id("/etc/passwd")

    def test_rejects_windows_absolute_path(self):
        """IDs with Windows drive letters must be rejected."""
        with pytest.raises(ValueError, match="path traversal"):
            validate_id("C:\\Windows\\System32")

    def test_rejects_excessively_long_id(self):
        """IDs exceeding 1024 characters must be rejected."""
        with pytest.raises(ValueError, match="maximum length"):
            validate_id("a" * 1025)

    def test_accepts_max_length_id(self):
        """IDs at exactly 1024 characters must be accepted."""
        assert validate_id("a" * 1024) == "a" * 1024


class TestValidateIdBackwardCompat:
    """PS3: Valid IDs must continue to work."""

    def test_accepts_simple_alphanumeric(self):
        """Simple alphanumeric IDs must pass."""
        assert validate_id("agent001") == "agent001"

    def test_accepts_hyphens(self):
        """IDs with hyphens must pass."""
        assert validate_id("agent-001") == "agent-001"

    def test_accepts_underscores(self):
        """IDs with underscores must pass."""
        assert validate_id("agent_001") == "agent_001"

    def test_accepts_dots_in_id(self):
        """IDs with dots must pass (backward compat: agent.v1.prod)."""
        assert validate_id("agent.v1.prod") == "agent.v1.prod"

    def test_accepts_colons_in_id(self):
        """IDs with colons pass validation (handled by _safe_filename hashing)."""
        assert validate_id("urn:eatp:agent:001") == "urn:eatp:agent:001"

    def test_accepts_mixed_case(self):
        """Mixed case IDs must pass."""
        assert validate_id("Agent-V1-Prod") == "Agent-V1-Prod"

    def test_accepts_numeric_only(self):
        """Numeric-only IDs must pass."""
        assert validate_id("12345") == "12345"

    def test_accepts_uuid_format(self):
        """UUID-formatted IDs must pass."""
        assert validate_id("550e8400-e29b-41d4-a716-446655440000") == "550e8400-e29b-41d4-a716-446655440000"

    def test_returns_stripped_id(self):
        """Leading/trailing whitespace should be stripped."""
        assert validate_id("  agent-001  ") == "agent-001"


class TestValidateIdErrorMessages:
    """PS3: Error messages must be clear and actionable."""

    def test_traversal_error_includes_id(self):
        """Error should mention the problematic ID."""
        with pytest.raises(ValueError, match="path traversal") as exc_info:
            validate_id("../secret")
        assert "../secret" in str(exc_info.value) or "path traversal" in str(exc_info.value)

    def test_null_byte_error_is_clear(self):
        """Error should clearly indicate null byte issue."""
        with pytest.raises(ValueError, match="null"):
            validate_id("agent\x00evil")
