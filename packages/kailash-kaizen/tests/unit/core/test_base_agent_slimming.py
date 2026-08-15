"""
Tests for SPEC-04: BaseAgent Slimming.

Validates that:
1. base_agent.py stays under 1,015 LOC (re-anchored to the architectural
   invariant by #2119; see test for the budget history)
2. Extracted modules exist and are importable
3. AgentLoop produces identical results to the original inline code
4. MCPMixin methods are accessible via BaseAgent
5. A2AMixin methods are accessible via BaseAgent
6. @deprecated decorator works correctly
7. isinstance(agent, BaseAgent) still works
"""

from pathlib import Path

import pytest

# =========================================================================
# Line count enforcement
# =========================================================================


class TestBaseAgentLineCount:
    """Enforce that base_agent.py stays under 1,015 lines."""

    def test_base_agent_under_1015_lines(self):
        # Budget history: 1000 -> 1010 (2026-07-18, #1779) -> 1015 (2026-07-19,
        # #1720 Wave-2b) -> 1070 (2026-08-11, #2030/#2022) -> back to 1015
        # (2026-08-15, #2119).
        #
        # The first three raises each had a stated reason, but the cumulative
        # effect was a guard that could no longer fail before the architectural
        # invariant in tests/regression/test_loc_invariants.py (limit 1015) did
        # — so it had stopped guarding anything. #2119 resolved the overshoot
        # the way the invariant intended, by EXTRACTION rather than by another
        # raise (extract_* -> OutputExtractionMixin, the Control Protocol trio
        # -> ControlProtocolMixin), which brought the file to 922 and made this
        # budget re-anchorable to the invariant it should never have drifted
        # above.
        #
        # This number may be TIGHTENED freely. Raising it needs the same
        # justification an extraction would have needed, per
        # rules/refactor-invariants.md — a guard that only ever moves in the
        # direction of the code records what happened rather than what was
        # intended.
        path = Path(__file__).parent.parent.parent.parent / (
            "src/kaizen/core/base_agent.py"
        )
        lines = path.read_text().splitlines()
        assert len(lines) < 1015, (
            f"base_agent.py has grown to {len(lines)} lines (budget: <1015). "
            f"This likely indicates a merge regression that re-inlined mixin "
            f"code. MCP methods belong in MCPMixin, A2A in A2AMixin, the "
            f"extract_* accessors in OutputExtractionMixin, and the "
            f"ask/approve/report helpers in ControlProtocolMixin. "
            f"See journal/0003-RISK-spec04-silent-regression-via-parallel-merge.md"
        )

    def test_extracted_modules_exist(self):
        base = Path(__file__).parent.parent.parent.parent / "src/kaizen/core"
        assert (base / "agent_loop.py").exists(), "agent_loop.py not found"
        assert (base / "mcp_mixin.py").exists(), "mcp_mixin.py not found"
        assert (base / "a2a_mixin.py").exists(), "a2a_mixin.py not found"
        assert (base / "deprecation.py").exists(), "deprecation.py not found"
        # #2030 — the log-hygiene helpers must stay extracted, not drift back
        # into base_agent.py where the line-count guard would mask them.
        assert (base / "_log_hygiene.py").exists(), "_log_hygiene.py not found"
        # #2119 — same contract for the two units extracted to restore the
        # 1015 invariant. A merge that re-inlines either one puts ~150 lines
        # back into base_agent.py.
        assert (
            base / "output_extraction_mixin.py"
        ).exists(), "output_extraction_mixin.py not found"
        assert (
            base / "control_protocol_mixin.py"
        ).exists(), "control_protocol_mixin.py not found"


# =========================================================================
# Module imports
# =========================================================================


class TestExtractedModuleImports:
    """Verify that all extracted modules are importable."""

    def test_import_agent_loop(self):
        from kaizen.core.agent_loop import AgentLoop, AgentLoopConfig

        assert AgentLoop is not None
        assert AgentLoopConfig is not None

    def test_import_mcp_mixin(self):
        from kaizen.core.mcp_mixin import MCPMixin

        assert MCPMixin is not None

    def test_import_a2a_mixin(self):
        from kaizen.core.a2a_mixin import A2AMixin

        assert A2AMixin is not None

    def test_import_deprecation(self):
        from kaizen.core.deprecation import deprecated

        assert deprecated is not None
        assert callable(deprecated)


# =========================================================================
# MRO and isinstance
# =========================================================================


class TestBaseAgentMRO:
    """Verify that BaseAgent inherits from the correct mixins."""

    def test_isinstance_still_works(self):
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

        config = BaseAgentConfig()
        agent = BaseAgent(config=config, mcp_servers=[])
        assert isinstance(agent, BaseAgent)

    def test_mcp_mixin_in_mro(self):
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.mcp_mixin import MCPMixin

        assert issubclass(BaseAgent, MCPMixin)

    def test_a2a_mixin_in_mro(self):
        from kaizen.core.a2a_mixin import A2AMixin
        from kaizen.core.base_agent import BaseAgent

        assert issubclass(BaseAgent, A2AMixin)

    def test_output_extraction_mixin_in_mro(self):
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.output_extraction_mixin import OutputExtractionMixin

        assert issubclass(BaseAgent, OutputExtractionMixin)

    def test_control_protocol_mixin_in_mro(self):
        from kaizen.core.base_agent import BaseAgent
        from kaizen.core.control_protocol_mixin import ControlProtocolMixin

        assert issubclass(BaseAgent, ControlProtocolMixin)

    def test_node_in_mro(self):
        from kailash.nodes.base import Node
        from kaizen.core.base_agent import BaseAgent

        assert issubclass(BaseAgent, Node)

    def test_extracted_methods_still_resolve_on_baseagent(self):
        """#2119 — the extractions must be invisible at the public API.

        Existence alone would pass even if a method were left behind as a
        stub, so this also drives each accessor and asserts the coercion the
        inline versions performed.
        """
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

        agent = BaseAgent(config=BaseAgentConfig(), mcp_servers=[])

        for name in (
            "extract_list",
            "extract_dict",
            "extract_float",
            "extract_str",
            "ask_user_question",
            "request_approval",
            "report_progress",
        ):
            assert hasattr(agent, name), f"{name} no longer resolves on BaseAgent"

        # A JSON-string payload must still be coerced to the declared type,
        # and a malformed one must still fall back to the default.
        assert agent.extract_list({"a": '["x"]'}, "a") == ["x"]
        assert agent.extract_dict({"a": '{"k": 1}'}, "a") == {"k": 1}
        assert agent.extract_float({"a": "0.5"}, "a") == 0.5
        assert agent.extract_str({"a": None}, "a", "dflt") == "dflt"
        assert agent.extract_list({"a": "not json"}, "a", default=["d"]) == ["d"]

    def test_mcp_methods_accessible(self):
        """All MCPMixin methods must be accessible on BaseAgent instances."""
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

        config = BaseAgentConfig()
        agent = BaseAgent(config=config, mcp_servers=[])

        mcp_methods = [
            "has_mcp_support",
            "discover_mcp_tools",
            "execute_tool",
            "execute_mcp_tool",
            "discover_tools",
            "discover_mcp_resources",
            "read_mcp_resource",
            "discover_mcp_prompts",
            "get_mcp_prompt",
            "setup_mcp_client",
            "call_mcp_tool",
            "expose_as_mcp_server",
        ]
        for method_name in mcp_methods:
            assert hasattr(
                agent, method_name
            ), f"MCPMixin method '{method_name}' not accessible on BaseAgent"

    def test_a2a_methods_accessible(self):
        """All A2AMixin methods must be accessible on BaseAgent instances."""
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

        config = BaseAgentConfig()
        agent = BaseAgent(config=config, mcp_servers=[])

        a2a_methods = [
            "to_a2a_card",
            "_extract_primary_capabilities",
            "_extract_secondary_capabilities",
            "_get_collaboration_style",
            "_get_performance_metrics",
            "_get_resource_requirements",
            "_infer_domain",
            "_extract_keywords",
            "_get_agent_type",
            "_get_agent_description",
            "_get_agent_tags",
            "_get_specializations",
        ]
        for method_name in a2a_methods:
            assert hasattr(
                agent, method_name
            ), f"A2AMixin method '{method_name}' not accessible on BaseAgent"


# =========================================================================
# Deprecation decorator
# =========================================================================


class TestDeprecationDecorator:
    """Verify the @deprecated decorator works correctly."""

    def test_deprecated_emits_warning(self):
        from kaizen.core.deprecation import deprecated

        @deprecated("Use new_func() instead.")
        def old_func():
            return 42

        with pytest.warns(DeprecationWarning, match="Use new_func"):
            result = old_func()

        assert result == 42

    def test_deprecated_with_since(self):
        from kaizen.core.deprecation import deprecated

        @deprecated("Use new_func() instead.", since="2.5.0")
        def old_func():
            return 42

        with pytest.warns(DeprecationWarning, match="v2.5.0"):
            result = old_func()

        assert result == 42

    def test_deprecated_preserves_functools_wraps(self):
        from kaizen.core.deprecation import deprecated

        @deprecated("Use new_func() instead.")
        def old_func():
            """Old function docstring."""
            return 42

        assert old_func.__name__ == "old_func"
        assert old_func.__doc__ == "Old function docstring."
        assert old_func._deprecated is True

    def test_deprecated_preserves_args_kwargs(self):
        from kaizen.core.deprecation import deprecated

        @deprecated("Use new_func() instead.")
        def old_func(a, b, c=3):
            return a + b + c

        with pytest.warns(DeprecationWarning):
            assert old_func(1, 2) == 6
            assert old_func(1, 2, c=10) == 13


# =========================================================================
# AgentLoop
# =========================================================================


class TestAgentLoopConfig:
    """Verify AgentLoopConfig factory."""

    def test_from_agent(self):
        from kaizen.core.agent_loop import AgentLoopConfig
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

        config = BaseAgentConfig(max_cycles=20, temperature=0.5, max_tokens=2048)
        agent = BaseAgent(config=config, mcp_servers=[])

        loop_config = AgentLoopConfig.from_agent(agent)
        assert loop_config.max_cycles == 20
        assert loop_config.temperature == 0.5
        assert loop_config.max_tokens == 2048

    def test_defaults(self):
        from kaizen.core.agent_loop import AgentLoopConfig

        lc = AgentLoopConfig()
        assert lc.max_cycles == 10
        assert lc.temperature == 0.7
        assert lc.max_tokens == 4096


# =========================================================================
# Subclass compatibility
# =========================================================================


class TestSubclassCompatibility:
    """Verify that subclasses of BaseAgent still work correctly."""

    def test_subclass_with_custom_signature(self):
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
        from kaizen.signatures import InputField, OutputField, Signature

        class QASignature(Signature):
            question: str = InputField(desc="Question")
            answer: str = OutputField(desc="Answer")

        class QAAgent(BaseAgent):
            def _default_signature(self):
                return QASignature()

        config = BaseAgentConfig()
        agent = QAAgent(config=config, mcp_servers=[])
        assert isinstance(agent, BaseAgent)
        assert isinstance(agent, QAAgent)
        assert isinstance(agent.signature, QASignature)

    def test_subclass_with_custom_strategy(self):
        from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

        class CustomStrategy:
            async def execute(self, agent, inputs, **kwargs):
                return {"result": "custom"}

        class CustomAgent(BaseAgent):
            def _default_strategy(self):
                return CustomStrategy()

        config = BaseAgentConfig()
        agent = CustomAgent(config=config, mcp_servers=[])
        assert isinstance(agent.strategy, CustomStrategy)
