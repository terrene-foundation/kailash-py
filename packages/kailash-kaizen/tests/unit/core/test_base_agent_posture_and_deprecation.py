# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for BaseAgent SPEC-04 Wave 1G -- posture typing + @deprecated decorators.

Covers CRITICAL #3 and #4 from the convergence spec compliance audit v2:

- ``BaseAgentConfig.posture`` is typed ``Optional[AgentPosture]`` and
  coerces legacy string inputs while rejecting unknown values.
- The seven extension-point slots on ``BaseAgent`` carry the
  ``@deprecated`` decorator (detected via the ``_deprecated`` marker that
  the decorator sets on the wrapped function).
- Vanilla ``BaseAgent`` construction and execution emit zero
  ``DeprecationWarning`` from the extension-point slots (internal callers
  go through ``_invoke_extension_point``).
- Direct external invocation of a deprecated slot DOES emit the warning.
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
        # Annotation is ``Optional[AgentPosture]`` which reduces to
        # ``typing.Optional[kailash.trust.envelope.AgentPosture]``. Accept
        # either the raw class or the string form.
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


class TestSevenExtensionPointsDeprecated:
    """Every extension point MUST carry ``@deprecated`` (SPEC-04 CRITICAL #3)."""

    @pytest.mark.parametrize("name", _EXTENSION_POINTS)
    def test_slot_is_decorated(self, name: str) -> None:
        slot = getattr(BaseAgent, name)
        # The ``deprecated`` decorator in ``kaizen.core.deprecation`` sets
        # ``_deprecated`` and ``_deprecated_message`` attributes on the
        # wrapper function; assert both are present so a future refactor
        # that drops the wrapper fails loudly.
        assert (
            getattr(slot, "_deprecated", False) is True
        ), f"{name} is missing the @deprecated wrapper"
        assert "deprecated" in slot._deprecated_message.lower()

    def test_all_seven_slots_decorated(self) -> None:
        decorated = [
            name
            for name in _EXTENSION_POINTS
            if getattr(getattr(BaseAgent, name), "_deprecated", False)
        ]
        assert (
            len(decorated) == 7
        ), f"expected 7 decorated extension points, got {len(decorated)}: {decorated}"

    def test_decorator_count_matches_spec(self) -> None:
        # SPEC-04 validation criterion: ``grep -c "@deprecated"`` in
        # base_agent.py MUST return 7. We assert the semantic equivalent
        # via runtime introspection.
        slot_names = _EXTENSION_POINTS
        wrapped = sum(
            1 for name in slot_names if hasattr(getattr(BaseAgent, name), "_deprecated")
        )
        assert wrapped == 7


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
            or "BaseAgent extension points are deprecated" in str(w.message)
        ]
        assert offenders == [], (
            f"expected zero extension-point warnings on vanilla construction, "
            f"got {[str(w.message) for w in offenders]}"
        )

    def test_direct_slot_invocation_emits_warning(self) -> None:
        agent = BaseAgent(config=BaseAgentConfig(), mcp_servers=[])
        with pytest.warns(
            DeprecationWarning, match="BaseAgent extension points are deprecated"
        ):
            agent._default_signature()

    @pytest.mark.parametrize("name", _EXTENSION_POINTS)
    def test_every_slot_emits_warning_when_called_directly(self, name: str) -> None:
        agent = BaseAgent(config=BaseAgentConfig(), mcp_servers=[])
        slot = getattr(agent, name)
        # Call with the smallest possible argument set that satisfies each
        # method signature. The arity varies: signature/strategy/prompt
        # take no args; validate/hooks/error take 1-2.
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            try:
                if name in {
                    "_default_signature",
                    "_default_strategy",
                    "_generate_system_prompt",
                }:
                    slot()
                elif name == "_validate_signature_output":
                    slot({"response": "ok"})
                elif name in {"_pre_execution_hook", "_post_execution_hook"}:
                    slot({})
                elif name == "_handle_error":
                    try:
                        slot(ValueError("x"), {"inputs": {}})
                    except Exception:
                        pass
            except Exception:
                # Some impls may raise on trivial args; the warning still
                # fires before the body executes.
                pass
        deps = [w for w in captured if issubclass(w.category, DeprecationWarning)]
        assert deps, f"expected DeprecationWarning on direct call to {name}"
