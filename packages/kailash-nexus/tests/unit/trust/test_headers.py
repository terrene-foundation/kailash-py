"""Unit tests for EATP header extraction.

TDD: These tests are written FIRST before the implementation.
Following the 3-tier testing strategy - Tier 1 (Unit Tests).

Tests cover:
1. Valid header extraction with all headers present
2. Missing optional headers with graceful fallback
3. Malformed JSON handling
4. Invalid base64 handling
5. Case-insensitive header matching
6. Empty headers (no EATP headers)
7. Round-trip conversion (context -> headers -> context)
8. Delegation chain comma format parsing
9. Delegation chain JSON array format parsing
10. has_human_origin method verification
"""

import base64
import json
import os
import sys
from pathlib import Path

import pytest

# Add src to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from nexus.trust.headers import EATPHeaderExtractor, ExtractedEATPContext


class TestExtractedEATPContext:
    """Test ExtractedEATPContext dataclass and its methods."""

    def test_is_valid_returns_true_when_trace_id_and_agent_id_present(self):
        """Test is_valid() returns True when required fields present."""
        context = ExtractedEATPContext(
            trace_id="trace-123",
            agent_id="agent-456",
            human_origin=None,
            delegation_chain=[],
            delegation_depth=0,
            constraints={},
            session_id=None,
            signature=None,
            raw_headers={},
        )
        assert context.is_valid() is True

    def test_is_valid_returns_false_when_trace_id_missing(self):
        """Test is_valid() returns False when trace_id is None."""
        context = ExtractedEATPContext(
            trace_id=None,
            agent_id="agent-456",
            human_origin=None,
            delegation_chain=[],
            delegation_depth=0,
            constraints={},
            session_id=None,
            signature=None,
            raw_headers={},
        )
        assert context.is_valid() is False

    def test_is_valid_returns_false_when_agent_id_missing(self):
        """Test is_valid() returns False when agent_id is None."""
        context = ExtractedEATPContext(
            trace_id="trace-123",
            agent_id=None,
            human_origin=None,
            delegation_chain=[],
            delegation_depth=0,
            constraints={},
            session_id=None,
            signature=None,
            raw_headers={},
        )
        assert context.is_valid() is False

    def test_has_human_origin_returns_true_when_present(self):
        """Test has_human_origin() returns True when human_origin is set."""
        context = ExtractedEATPContext(
            trace_id="trace-123",
            agent_id="agent-456",
            human_origin={"user_id": "user-789", "timestamp": "2024-01-01T00:00:00Z"},
            delegation_chain=[],
            delegation_depth=0,
            constraints={},
            session_id=None,
            signature=None,
            raw_headers={},
        )
        assert context.has_human_origin() is True

    def test_has_human_origin_returns_false_when_none(self):
        """Test has_human_origin() returns False when human_origin is None."""
        context = ExtractedEATPContext(
            trace_id="trace-123",
            agent_id="agent-456",
            human_origin=None,
            delegation_chain=[],
            delegation_depth=0,
            constraints={},
            session_id=None,
            signature=None,
            raw_headers={},
        )
        assert context.has_human_origin() is False


class TestEATPHeaderExtractor:
    """Test EATPHeaderExtractor class."""

    @pytest.fixture
    def extractor(self):
        """Create EATPHeaderExtractor instance."""
        return EATPHeaderExtractor()

    def test_extract_valid_headers_all_present(self, extractor):
        """Test extracting all valid EATP headers with is_valid() True."""
        human_origin = {"user_id": "user-123", "auth_method": "oauth2"}
        constraints = {"max_tokens": 1000, "allowed_tools": ["read", "write"]}

        headers = {
            "X-EATP-Trace-ID": "trace-abc-123",
            "X-EATP-Agent-ID": "agent-def-456",
            "X-EATP-Human-Origin": base64.b64encode(
                json.dumps(human_origin).encode()
            ).decode(),
            "X-EATP-Delegation-Chain": "agent-1,agent-2,agent-3",
            "X-EATP-Delegation-Depth": "3",
            "X-EATP-Constraints": base64.b64encode(
                json.dumps(constraints).encode()
            ).decode(),
            "X-EATP-Session-ID": "session-ghi-789",
            "X-EATP-Signature": "sig-xyz-000",
        }

        context = extractor.extract(headers)

        assert context.trace_id == "trace-abc-123"
        assert context.agent_id == "agent-def-456"
        assert context.human_origin == human_origin
        assert context.delegation_chain == ["agent-1", "agent-2", "agent-3"]
        assert context.delegation_depth == 3
        assert context.constraints == constraints
        assert context.session_id == "session-ghi-789"
        assert context.signature == "sig-xyz-000"
        assert context.is_valid() is True
        assert context.has_human_origin() is True
        # Verify raw headers are stored
        assert "X-EATP-Trace-ID" in context.raw_headers

    def test_extract_missing_headers_optional_fields_none(self, extractor):
        """Test extracting with only required headers, optional fields None."""
        headers = {
            "X-EATP-Trace-ID": "trace-123",
            "X-EATP-Agent-ID": "agent-456",
        }

        context = extractor.extract(headers)

        assert context.trace_id == "trace-123"
        assert context.agent_id == "agent-456"
        assert context.human_origin is None
        assert context.delegation_chain == []
        assert context.delegation_depth == 0
        assert context.constraints == {}
        assert context.session_id is None
        assert context.signature is None
        assert context.is_valid() is True

    def test_extract_malformed_json_human_origin_becomes_none(self, extractor):
        """Test that malformed JSON in human_origin results in None."""
        # Invalid JSON that's valid base64
        invalid_json = base64.b64encode(b"not valid json {").decode()

        headers = {
            "X-EATP-Trace-ID": "trace-123",
            "X-EATP-Agent-ID": "agent-456",
            "X-EATP-Human-Origin": invalid_json,
        }

        context = extractor.extract(headers)

        assert context.trace_id == "trace-123"
        assert context.agent_id == "agent-456"
        assert context.human_origin is None  # Should be None due to malformed JSON
        assert context.is_valid() is True

    def test_extract_invalid_base64_graceful_fallback(self, extractor):
        """Test that invalid base64 in constraints falls back gracefully."""
        # Try with completely invalid base64
        headers = {
            "X-EATP-Trace-ID": "trace-123",
            "X-EATP-Agent-ID": "agent-456",
            "X-EATP-Constraints": "!!!invalid-base64!!!",
        }

        context = extractor.extract(headers)

        assert context.trace_id == "trace-123"
        assert context.agent_id == "agent-456"
        assert context.constraints == {}  # Should fallback to empty dict
        assert context.is_valid() is True

    def test_extract_case_insensitive_headers(self, extractor):
        """Test that header extraction is case-insensitive."""
        headers = {
            "x-eatp-trace-id": "trace-lowercase",
            "X-EATP-AGENT-ID": "agent-uppercase",
            "X-Eatp-Session-Id": "session-mixedcase",
        }

        context = extractor.extract(headers)

        assert context.trace_id == "trace-lowercase"
        assert context.agent_id == "agent-uppercase"
        assert context.session_id == "session-mixedcase"
        assert context.is_valid() is True

    def test_extract_no_headers_is_valid_false(self, extractor):
        """Test that empty headers dict results in is_valid() False, no exceptions."""
        headers = {}

        context = extractor.extract(headers)

        assert context.trace_id is None
        assert context.agent_id is None
        assert context.human_origin is None
        assert context.delegation_chain == []
        assert context.delegation_depth == 0
        assert context.constraints == {}
        assert context.session_id is None
        assert context.signature is None
        assert context.is_valid() is False
        assert context.has_human_origin() is False

    def test_to_headers_roundtrip(self, extractor):
        """Test creating context, converting to headers, extracting again."""
        original_context = ExtractedEATPContext(
            trace_id="trace-roundtrip-123",
            agent_id="agent-roundtrip-456",
            human_origin={"user": "test", "verified": True},
            delegation_chain=["agent-a", "agent-b"],
            delegation_depth=2,
            constraints={"max_depth": 5},
            session_id="session-roundtrip",
            signature="sig-roundtrip",
            raw_headers={},
        )

        # Convert to headers
        headers = extractor.to_headers(original_context)

        # Extract from headers
        extracted_context = extractor.extract(headers)

        # Verify all fields match
        assert extracted_context.trace_id == original_context.trace_id
        assert extracted_context.agent_id == original_context.agent_id
        assert extracted_context.human_origin == original_context.human_origin
        assert extracted_context.delegation_chain == original_context.delegation_chain
        assert extracted_context.delegation_depth == original_context.delegation_depth
        assert extracted_context.constraints == original_context.constraints
        assert extracted_context.session_id == original_context.session_id
        assert extracted_context.signature == original_context.signature

    def test_delegation_chain_comma_format(self, extractor):
        """Test parsing comma-separated delegation chain: 'agent-1,agent-2,agent-3'."""
        headers = {
            "X-EATP-Trace-ID": "trace-123",
            "X-EATP-Agent-ID": "agent-456",
            "X-EATP-Delegation-Chain": "agent-1,agent-2,agent-3",
        }

        context = extractor.extract(headers)

        assert context.delegation_chain == ["agent-1", "agent-2", "agent-3"]

    def test_delegation_chain_json_format(self, extractor):
        """Test parsing JSON array delegation chain: ['agent-1', 'agent-2']."""
        chain_json = json.dumps(["agent-1", "agent-2", "agent-3"])

        headers = {
            "X-EATP-Trace-ID": "trace-123",
            "X-EATP-Agent-ID": "agent-456",
            "X-EATP-Delegation-Chain": chain_json,
        }

        context = extractor.extract(headers)

        assert context.delegation_chain == ["agent-1", "agent-2", "agent-3"]

    def test_has_human_origin_methods_both_cases(self, extractor):
        """Test has_human_origin() method for both True and False cases."""
        # Case 1: With human origin
        headers_with_origin = {
            "X-EATP-Trace-ID": "trace-123",
            "X-EATP-Agent-ID": "agent-456",
            "X-EATP-Human-Origin": base64.b64encode(
                json.dumps({"user": "test"}).encode()
            ).decode(),
        }
        context_with_origin = extractor.extract(headers_with_origin)
        assert context_with_origin.has_human_origin() is True

        # Case 2: Without human origin
        headers_without_origin = {
            "X-EATP-Trace-ID": "trace-123",
            "X-EATP-Agent-ID": "agent-456",
        }
        context_without_origin = extractor.extract(headers_without_origin)
        assert context_without_origin.has_human_origin() is False


class TestEATPHeaderExtractorEdgeCases:
    """Test edge cases and error handling in EATP header extraction."""

    @pytest.fixture
    def extractor(self):
        """Create EATPHeaderExtractor instance."""
        return EATPHeaderExtractor()

    def test_delegation_depth_non_integer_defaults_to_zero(self, extractor):
        """Test that non-integer delegation depth defaults to 0."""
        headers = {
            "X-EATP-Trace-ID": "trace-123",
            "X-EATP-Agent-ID": "agent-456",
            "X-EATP-Delegation-Depth": "not-a-number",
        }

        context = extractor.extract(headers)

        assert context.delegation_depth == 0

    def test_delegation_chain_empty_string(self, extractor):
        """Test that empty delegation chain string results in empty list."""
        headers = {
            "X-EATP-Trace-ID": "trace-123",
            "X-EATP-Agent-ID": "agent-456",
            "X-EATP-Delegation-Chain": "",
        }

        context = extractor.extract(headers)

        assert context.delegation_chain == []

    def test_constraints_direct_json_when_base64_fails(self, extractor):
        """Test that direct JSON is tried when base64 decoding fails."""
        # Direct JSON (not base64 encoded)
        constraints_json = json.dumps({"key": "value"})

        headers = {
            "X-EATP-Trace-ID": "trace-123",
            "X-EATP-Agent-ID": "agent-456",
            "X-EATP-Constraints": constraints_json,
        }

        context = extractor.extract(headers)

        # Should fall back to direct JSON parsing
        assert context.constraints == {"key": "value"}

    def test_to_headers_with_none_values_excludes_them(self, extractor):
        """Test that to_headers excludes None values."""
        context = ExtractedEATPContext(
            trace_id="trace-123",
            agent_id="agent-456",
            human_origin=None,
            delegation_chain=[],
            delegation_depth=0,
            constraints={},
            session_id=None,
            signature=None,
            raw_headers={},
        )

        headers = extractor.to_headers(context)

        assert "X-EATP-Trace-ID" in headers
        assert "X-EATP-Agent-ID" in headers
        assert "X-EATP-Human-Origin" not in headers
        assert "X-EATP-Session-ID" not in headers
        assert "X-EATP-Signature" not in headers

    def test_whitespace_in_delegation_chain_trimmed(self, extractor):
        """Test that whitespace around delegation chain items is trimmed."""
        headers = {
            "X-EATP-Trace-ID": "trace-123",
            "X-EATP-Agent-ID": "agent-456",
            "X-EATP-Delegation-Chain": " agent-1 , agent-2 , agent-3 ",
        }

        context = extractor.extract(headers)

        assert context.delegation_chain == ["agent-1", "agent-2", "agent-3"]

    def test_raw_headers_contains_original_eatp_headers(self, extractor):
        """Test that raw_headers contains original EATP headers."""
        headers = {
            "X-EATP-Trace-ID": "trace-123",
            "X-EATP-Agent-ID": "agent-456",
            "Content-Type": "application/json",  # Non-EATP header
            "Authorization": "Bearer token",  # Non-EATP header
        }

        context = extractor.extract(headers)

        # Should contain EATP headers
        assert "X-EATP-Trace-ID" in context.raw_headers
        assert "X-EATP-Agent-ID" in context.raw_headers
        # Should NOT contain non-EATP headers
        assert "Content-Type" not in context.raw_headers
        assert "Authorization" not in context.raw_headers

    def test_negative_delegation_depth(self, extractor):
        """Test that negative delegation depth is handled."""
        headers = {
            "X-EATP-Trace-ID": "trace-123",
            "X-EATP-Agent-ID": "agent-456",
            "X-EATP-Delegation-Depth": "-5",
        }

        context = extractor.extract(headers)

        # Negative values should be parsed but implementation may clamp to 0
        # or allow negative - the key is no exception
        assert isinstance(context.delegation_depth, int)
