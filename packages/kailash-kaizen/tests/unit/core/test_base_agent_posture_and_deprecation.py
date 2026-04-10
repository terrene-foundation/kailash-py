# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for BaseAgent SPEC-04 — posture typing + extension point architecture.

- ``BaseAgentConfig.posture`` is typed ``Optional[AgentPosture]`` and
  coerces legacy string inputs while rejecting unknown values.
- The seven extension points are direct methods on BaseAgent (no shims).
- Subclass overrides win via normal MRO — no dispatcher needed.
- Vanilla ``BaseAgent`` construction emits zero ``DeprecationWarning``.
"""

from __future__ import annotations

import dataclasses
import warnings

import pytest
from kailash.trust.envelope import AgentPosture

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

_EXTENSION_POINTS = (
    "_default_signature",
    "_default_strategy",
    "_generate_system_prompt",
    "_validate_signature_output",
    "_pre_execution_hook",
    "_post_execution_hook",
    "_handle_error",
)


class TestBaseAgentConfigPostureType:
    """``BaseAgentConfig.posture`` is typed ``Optional[AgentPosture]``."""

    def test_posture_field_annotation_is_agent_posture(self) -> None:
        fields = {f.name: f.type for f in dataclasses.fields(BaseAgentConfig)}
        annotation = fields["posture"]
        assert "AgentPosture" in str(annotation)

    def test_none_is_default(self) -> None:
        config = BaseAgentConfig()
        assert config.posture is None

    def test_accepts_enum_instance(self) -> None:
        config = BaseAgentConfig(posture=AgentPosture.SUPERVISED)
        assert config.posture is AgentPosture.SUPERVISED

    def test_accepts_and_coerces_string(self) -> None:
        config = BaseAgentConfig(posture="supervised")
        assert isinstance(config.posture, AgentPosture)
        assert config.posture is AgentPosture.SUPERVISED

    def test_rejects_unknown_string_with_clear_error(self) -> None:
        with pytest.raises(ValueError, match="posture must be"):
            BaseAgentConfig(posture="nonexistent")

    def test_rejects_wrong_type(self) -> None:
        with pytest.raises(TypeError, match="posture must be"):
            BaseAgentConfig(posture=42)  # type: ignore[arg-type]

    def test_round_trip_all_postures(self) -> None:
        for posture in AgentPosture:
            config = BaseAgentConfig(posture=posture.value)
            assert config.posture is posture


class TestSevenExtensionPointsAreDirect:
    """Extension points are direct methods — no dispatcher, no decorator."""

    @pytest.mark.parametrize("name", _EXTENSION_POINTS)
    def test_extension_point_is_callable(self, name: str) -> None:
        assert callable(getattr(BaseAgent, name))

    def test_all_seven_exist(self) -> None:
        for name in _EXTENSION_POINTS:
            assert hasattr(BaseAgent, name), f"{name} missing from BaseAgent"

    @pytest.mark.parametrize("name", _EXTENSION_POINTS)
    def test_no_deprecated_decorator(self, name: str) -> None:
        """Extension points should NOT have deprecated decorators (removed in SPEC-04)."""
        slot = getattr(BaseAgent, name)
        assert not getattr(
            slot, "_deprecated", False
        ), f"{name} still has @deprecated — shim layer should be removed"

    def test_subclass_override_wins_via_mro(self) -> None:
        """Subclass overrides should work via normal Python MRO."""

        class CustomAgent(BaseAgent):
            def _default_signature(self):
                return "custom"

        agent = CustomAgent(config=BaseAgentConfig(), mcp_servers=[])
        assert agent._default_signature() == "custom"


class TestVanillaBaseAgentIsWarningFree:
    """Vanilla ``BaseAgent`` must not emit deprecation warnings."""

    def test_construction_emits_no_extension_warnings(self) -> None:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            BaseAgent(config=BaseAgentConfig(), mcp_servers=[])
        offenders = [
            w
            for w in captured
            if issubclass(w.category, DeprecationWarning)
            and "extension point" in str(w.message).lower()
        ]
        assert offenders == [], (
            f"expected zero extension-point warnings on vanilla construction, "
            f"got {[str(w.message) for w in offenders]}"
        )

    def test_direct_call_emits_no_warning(self) -> None:
        """Direct calls to extension points should NOT emit warnings anymore."""
        agent = BaseAgent(config=BaseAgentConfig(), mcp_servers=[])
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            agent._default_signature()
        deps = [w for w in captured if issubclass(w.category, DeprecationWarning)]
        assert not deps, "extension points should not emit deprecation warnings"


class TestPostureImmutability:
    """SPEC-04 §10.3: posture is immutable after construction."""

    def test_posture_mutation_blocked(self) -> None:
        config = BaseAgentConfig(posture=AgentPosture.SUPERVISED)
        with pytest.raises(AttributeError, match="immutable after construction"):
            config.posture = AgentPosture.AUTONOMOUS

    def test_posture_set_during_construction_works(self) -> None:
        config = BaseAgentConfig(posture="supervised")
        assert config.posture is AgentPosture.SUPERVISED

    def test_non_guarded_fields_still_mutable(self) -> None:
        config = BaseAgentConfig()
        config.model = "gpt-4o"
        assert config.model == "gpt-4o"

    def test_replace_creates_new_config_with_different_posture(self) -> None:
        import dataclasses

        original = BaseAgentConfig(posture=AgentPosture.SUPERVISED)
        updated = dataclasses.replace(original, posture=AgentPosture.AUTONOMOUS)
        assert original.posture is AgentPosture.SUPERVISED
        assert updated.posture is AgentPosture.AUTONOMOUS
