# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for M1-04: AgentSpec (frozen dataclass blueprint).

Covers:
- Construction with all fields
- Frozen immutability (AD-L3-15)
- Validation: spec_id non-empty
- Validation: no duplicate tool_ids
- to_dict / from_dict round-trip
- Default field values
"""

from __future__ import annotations

import pytest

from kaizen.l3.factory.spec import AgentSpec


class TestAgentSpecConstruction:
    """Test AgentSpec construction and default values."""

    def test_minimal_construction(self):
        """AgentSpec with required fields only uses sane defaults."""
        spec = AgentSpec(
            spec_id="reviewer-v1",
            name="Code Reviewer",
            description="Reviews code for correctness",
        )
        assert spec.spec_id == "reviewer-v1"
        assert spec.name == "Code Reviewer"
        assert spec.description == "Reviews code for correctness"
        assert spec.capabilities == []
        assert spec.tool_ids == []
        assert spec.envelope == {}
        assert spec.memory_config == {}
        assert spec.max_lifetime is None
        assert spec.max_children is None
        assert spec.max_depth is None
        assert spec.required_context_keys == []
        assert spec.produced_context_keys == []
        assert spec.metadata == {}

    def test_full_construction(self):
        """AgentSpec with all fields explicitly set."""
        spec = AgentSpec(
            spec_id="analyzer-v2",
            name="Deep Analyzer",
            description="Performs deep analysis of code",
            capabilities=["code-review", "style-check"],
            tool_ids=["tool-search", "tool-lint"],
            envelope={"financial_limit": 100.0},
            memory_config={"backend": "session"},
            max_lifetime=3600.0,
            max_children=5,
            max_depth=3,
            required_context_keys=["project_id"],
            produced_context_keys=["analysis_result"],
            metadata={"version": "2.0"},
        )
        assert spec.capabilities == ["code-review", "style-check"]
        assert spec.tool_ids == ["tool-search", "tool-lint"]
        assert spec.envelope == {"financial_limit": 100.0}
        assert spec.memory_config == {"backend": "session"}
        assert spec.max_lifetime == 3600.0
        assert spec.max_children == 5
        assert spec.max_depth == 3
        assert spec.required_context_keys == ["project_id"]
        assert spec.produced_context_keys == ["analysis_result"]
        assert spec.metadata == {"version": "2.0"}


class TestAgentSpecFrozen:
    """AD-L3-15: AgentSpec is a frozen (immutable) dataclass."""

    def test_cannot_modify_spec_id(self):
        spec = AgentSpec(spec_id="s1", name="N", description="D")
        with pytest.raises(AttributeError):
            spec.spec_id = "s2"  # type: ignore[misc]

    def test_cannot_modify_name(self):
        spec = AgentSpec(spec_id="s1", name="N", description="D")
        with pytest.raises(AttributeError):
            spec.name = "New"  # type: ignore[misc]

    def test_cannot_modify_max_children(self):
        spec = AgentSpec(spec_id="s1", name="N", description="D", max_children=5)
        with pytest.raises(AttributeError):
            spec.max_children = 10  # type: ignore[misc]


class TestAgentSpecValidation:
    """Validation rules in __post_init__."""

    def test_empty_spec_id_raises(self):
        """spec_id must be non-empty."""
        with pytest.raises(ValueError, match="spec_id"):
            AgentSpec(spec_id="", name="N", description="D")

    def test_whitespace_only_spec_id_raises(self):
        """spec_id that is only whitespace is invalid."""
        with pytest.raises(ValueError, match="spec_id"):
            AgentSpec(spec_id="   ", name="N", description="D")

    def test_duplicate_tool_ids_raises(self):
        """tool_ids must not contain duplicates."""
        with pytest.raises(ValueError, match="tool_ids"):
            AgentSpec(
                spec_id="s1",
                name="N",
                description="D",
                tool_ids=["tool-a", "tool-b", "tool-a"],
            )

    def test_unique_tool_ids_accepted(self):
        """Non-duplicate tool_ids pass validation."""
        spec = AgentSpec(
            spec_id="s1",
            name="N",
            description="D",
            tool_ids=["tool-a", "tool-b", "tool-c"],
        )
        assert spec.tool_ids == ["tool-a", "tool-b", "tool-c"]

    def test_empty_tool_ids_accepted(self):
        """Empty tool_ids list is valid."""
        spec = AgentSpec(spec_id="s1", name="N", description="D", tool_ids=[])
        assert spec.tool_ids == []


class TestAgentSpecSerialization:
    """to_dict() / from_dict() round-trip."""

    def test_to_dict_contains_all_fields(self):
        spec = AgentSpec(
            spec_id="s1",
            name="Worker",
            description="Does work",
            capabilities=["cap1"],
            tool_ids=["tool1"],
            envelope={"financial_limit": 50.0},
            memory_config={"backend": "persistent"},
            max_lifetime=1800.0,
            max_children=3,
            max_depth=2,
            required_context_keys=["key1"],
            produced_context_keys=["key2"],
            metadata={"env": "prod"},
        )
        d = spec.to_dict()
        assert d["spec_id"] == "s1"
        assert d["name"] == "Worker"
        assert d["description"] == "Does work"
        assert d["capabilities"] == ["cap1"]
        assert d["tool_ids"] == ["tool1"]
        assert d["envelope"] == {"financial_limit": 50.0}
        assert d["memory_config"] == {"backend": "persistent"}
        assert d["max_lifetime"] == 1800.0
        assert d["max_children"] == 3
        assert d["max_depth"] == 2
        assert d["required_context_keys"] == ["key1"]
        assert d["produced_context_keys"] == ["key2"]
        assert d["metadata"] == {"env": "prod"}

    def test_from_dict_round_trip(self):
        original = AgentSpec(
            spec_id="s1",
            name="Worker",
            description="Does work",
            capabilities=["cap1", "cap2"],
            tool_ids=["t1"],
            envelope={"limit": 100},
            memory_config={},
            max_lifetime=600.0,
            max_children=None,
            max_depth=5,
            required_context_keys=["ctx_a"],
            produced_context_keys=["ctx_b"],
            metadata={"key": "val"},
        )
        d = original.to_dict()
        restored = AgentSpec.from_dict(d)
        assert restored == original

    def test_from_dict_minimal(self):
        """from_dict with only required fields uses defaults."""
        d = {
            "spec_id": "s1",
            "name": "N",
            "description": "D",
        }
        spec = AgentSpec.from_dict(d)
        assert spec.spec_id == "s1"
        assert spec.capabilities == []
        assert spec.tool_ids == []
        assert spec.max_lifetime is None
        assert spec.max_children is None
        assert spec.max_depth is None

    def test_to_dict_none_lifetime_included(self):
        """None fields are serialized as None."""
        spec = AgentSpec(spec_id="s1", name="N", description="D")
        d = spec.to_dict()
        assert d["max_lifetime"] is None
        assert d["max_children"] is None
        assert d["max_depth"] is None
