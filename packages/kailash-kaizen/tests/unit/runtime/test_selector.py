"""
Unit Tests for Runtime Selector (Tier 1)

Tests RuntimeSelector and SelectionStrategy for intelligent runtime selection.

Coverage:
- SelectionStrategy enum values
- RuntimeSelector initialization
- _analyze_requirements() method
- _get_capable_runtimes() method
- Selection strategies:
  - CAPABILITY_MATCH
  - COST_OPTIMIZED
  - LATENCY_OPTIMIZED
  - PREFERRED
  - BALANCED
- get_all_capabilities()
- get_capable_runtimes_for_task()
- explain_selection()
"""

from typing import Any, AsyncIterator, Dict, List, Optional

import pytest

from kaizen.runtime.adapter import RuntimeAdapter
from kaizen.runtime.capabilities import RuntimeCapabilities
from kaizen.runtime.context import ExecutionContext, ExecutionResult
from kaizen.runtime.selector import RuntimeSelector, SelectionStrategy


class MockAdapter(RuntimeAdapter):
    """Mock adapter for testing selector."""

    def __init__(
        self,
        runtime_name: str,
        capabilities_config: Optional[Dict[str, Any]] = None,
    ):
        config = capabilities_config or {}
        self._capabilities = RuntimeCapabilities(
            runtime_name=runtime_name,
            provider=config.get("provider", "test"),
            supports_streaming=config.get("supports_streaming", True),
            supports_tool_calling=config.get("supports_tool_calling", True),
            supports_parallel_tools=config.get("supports_parallel_tools", False),
            supports_vision=config.get("supports_vision", False),
            supports_audio=config.get("supports_audio", False),
            supports_code_execution=config.get("supports_code_execution", False),
            supports_file_access=config.get("supports_file_access", False),
            supports_web_access=config.get("supports_web_access", False),
            supports_interrupt=config.get("supports_interrupt", False),
            max_context_tokens=config.get("max_context_tokens"),
            cost_per_1k_input_tokens=config.get("cost_per_1k_input_tokens"),
            cost_per_1k_output_tokens=config.get("cost_per_1k_output_tokens"),
            typical_latency_ms=config.get("typical_latency_ms"),
            native_tools=config.get("native_tools", []),
            supported_models=config.get("supported_models", []),
        )

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return self._capabilities

    async def execute(self, context, on_progress=None) -> ExecutionResult:
        return ExecutionResult.from_success("done", self._capabilities.runtime_name)

    async def stream(self, context) -> AsyncIterator[str]:
        yield "chunk"

    async def interrupt(self, session_id: str, mode: str = "graceful") -> bool:
        return True

    def map_tools(self, kaizen_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return kaizen_tools

    def normalize_result(self, raw_result: Any) -> ExecutionResult:
        return ExecutionResult.from_success(
            str(raw_result), self._capabilities.runtime_name
        )


class TestSelectionStrategy:
    """Test SelectionStrategy enum."""

    def test_all_strategies_exist(self):
        """Test all expected strategies are defined."""
        assert SelectionStrategy.CAPABILITY_MATCH.value == "capability_match"
        assert SelectionStrategy.COST_OPTIMIZED.value == "cost_optimized"
        assert SelectionStrategy.LATENCY_OPTIMIZED.value == "latency_optimized"
        assert SelectionStrategy.PREFERRED.value == "preferred"
        assert SelectionStrategy.BALANCED.value == "balanced"

    def test_strategy_count(self):
        """Test expected number of strategies."""
        strategies = list(SelectionStrategy)
        assert len(strategies) == 5


class TestRuntimeSelectorInit:
    """Test RuntimeSelector initialization."""

    def test_init_with_runtimes(self):
        """Test initialization with runtimes dict."""
        runtimes = {
            "runtime_a": MockAdapter("runtime_a"),
            "runtime_b": MockAdapter("runtime_b"),
        }

        selector = RuntimeSelector(runtimes)

        assert len(selector.runtimes) == 2
        assert selector.default_runtime == "kaizen_local"

    def test_init_with_default_runtime(self):
        """Test initialization with custom default."""
        runtimes = {"my_default": MockAdapter("my_default")}

        selector = RuntimeSelector(runtimes, default_runtime="my_default")

        assert selector.default_runtime == "my_default"

    def test_init_empty_runtimes(self):
        """Test initialization with empty runtimes."""
        selector = RuntimeSelector({})

        assert len(selector.runtimes) == 0


class TestAnalyzeRequirements:
    """Test _analyze_requirements method."""

    @pytest.fixture
    def selector(self):
        return RuntimeSelector({"test": MockAdapter("test")})

    def test_analyze_empty_task(self, selector):
        """Test analyzing minimal task."""
        context = ExecutionContext(task="Hello")
        reqs = selector._analyze_requirements(context)

        # No specific requirements
        assert isinstance(reqs, list)

    def test_analyze_task_with_tools(self, selector):
        """Test tool-based requirement detection."""
        context = ExecutionContext(
            task="Do something",
            tools=[{"name": "my_tool"}],
        )

        reqs = selector._analyze_requirements(context)

        assert "tool_calling" in reqs

    def test_analyze_file_tool_requirement(self, selector):
        """Test file tool detection."""
        context = ExecutionContext(
            task="Process",
            tools=[{"name": "read_file"}],
        )

        reqs = selector._analyze_requirements(context)

        assert "file_access" in reqs

    def test_analyze_web_tool_requirement(self, selector):
        """Test web tool detection."""
        context = ExecutionContext(
            task="Process",
            tools=[{"function": {"name": "web_fetch"}}],
        )

        reqs = selector._analyze_requirements(context)

        assert "web_access" in reqs

    def test_analyze_bash_tool_requirement(self, selector):
        """Test code execution tool detection."""
        context = ExecutionContext(
            task="Run",
            tools=[{"name": "bash_command"}],
        )

        reqs = selector._analyze_requirements(context)

        assert "code_execution" in reqs

    def test_analyze_vision_from_task(self, selector):
        """Test vision requirement from task text."""
        context = ExecutionContext(task="Analyze this image and describe it")

        reqs = selector._analyze_requirements(context)

        assert "vision" in reqs

    def test_analyze_audio_from_task(self, selector):
        """Test audio requirement from task text."""
        context = ExecutionContext(task="Listen to this audio file")

        reqs = selector._analyze_requirements(context)

        assert "audio" in reqs

    def test_analyze_code_execution_from_task(self, selector):
        """Test code execution from task text."""
        context = ExecutionContext(task="Run the test suite")

        reqs = selector._analyze_requirements(context)

        assert "code_execution" in reqs

    def test_analyze_file_access_from_task(self, selector):
        """Test file access from task text."""
        context = ExecutionContext(task="Read the config file")

        reqs = selector._analyze_requirements(context)

        assert "file_access" in reqs

    def test_analyze_web_access_from_task(self, selector):
        """Test web access from task text."""
        context = ExecutionContext(task="Fetch data from URL")

        reqs = selector._analyze_requirements(context)

        assert "web_access" in reqs

    def test_analyze_interrupt_for_long_tasks(self, selector):
        """Test interrupt requirement for long-running tasks."""
        context = ExecutionContext(
            task="Long task",
            timeout_seconds=120.0,  # > 60 seconds
        )

        reqs = selector._analyze_requirements(context)

        assert "interrupt" in reqs

    def test_analyze_no_duplicate_requirements(self, selector):
        """Test requirements are deduplicated."""
        context = ExecutionContext(
            task="Read file and process image",
            tools=[{"name": "read_file"}],
        )

        reqs = selector._analyze_requirements(context)

        # Should not have duplicates
        assert len(reqs) == len(set(reqs))


class TestGetCapableRuntimes:
    """Test _get_capable_runtimes method."""

    @pytest.fixture
    def selector_with_varied_runtimes(self):
        runtimes = {
            "full_caps": MockAdapter(
                "full_caps",
                {
                    "supports_vision": True,
                    "supports_file_access": True,
                    "supports_code_execution": True,
                    "supports_web_access": True,
                },
            ),
            "basic_caps": MockAdapter("basic_caps"),
            "vision_only": MockAdapter("vision_only", {"supports_vision": True}),
        }
        return RuntimeSelector(runtimes)

    def test_get_capable_empty_requirements(self, selector_with_varied_runtimes):
        """Test all runtimes capable with no requirements."""
        capable = selector_with_varied_runtimes._get_capable_runtimes([])

        assert len(capable) == 3

    def test_get_capable_vision_requirement(self, selector_with_varied_runtimes):
        """Test filtering by vision requirement."""
        capable = selector_with_varied_runtimes._get_capable_runtimes(["vision"])

        names = [name for name, _ in capable]
        assert "full_caps" in names
        assert "vision_only" in names
        assert "basic_caps" not in names

    def test_get_capable_multiple_requirements(self, selector_with_varied_runtimes):
        """Test filtering by multiple requirements."""
        capable = selector_with_varied_runtimes._get_capable_runtimes(
            ["vision", "file_access"]
        )

        names = [name for name, _ in capable]
        assert "full_caps" in names
        assert len(names) == 1  # Only full_caps meets both

    def test_get_capable_no_matches(self, selector_with_varied_runtimes):
        """Test when no runtime meets requirements."""
        capable = selector_with_varied_runtimes._get_capable_runtimes(["audio"])

        assert len(capable) == 0


class TestSelectCapabilityMatch:
    """Test CAPABILITY_MATCH selection strategy."""

    def test_select_capability_match_prefers_default(self):
        """Test that default runtime is preferred if capable."""
        runtimes = {
            "kaizen_local": MockAdapter("kaizen_local"),
            "other": MockAdapter("other"),
        }
        selector = RuntimeSelector(runtimes, default_runtime="kaizen_local")
        context = ExecutionContext(task="Simple task")

        selected = selector.select(context, SelectionStrategy.CAPABILITY_MATCH)

        assert selected.capabilities.runtime_name == "kaizen_local"

    def test_select_capability_match_fallback(self):
        """Test fallback when default is not capable."""
        runtimes = {
            "kaizen_local": MockAdapter("kaizen_local"),
            "capable": MockAdapter("capable", {"supports_vision": True}),
        }
        selector = RuntimeSelector(runtimes, default_runtime="kaizen_local")
        context = ExecutionContext(task="Analyze image")

        selected = selector.select(context, SelectionStrategy.CAPABILITY_MATCH)

        assert selected.capabilities.runtime_name == "capable"


class TestSelectCostOptimized:
    """Test COST_OPTIMIZED selection strategy."""

    def test_select_cost_optimized(self):
        """Test selecting cheapest runtime."""
        runtimes = {
            "expensive": MockAdapter(
                "expensive",
                {
                    "cost_per_1k_input_tokens": 0.10,
                    "cost_per_1k_output_tokens": 0.30,
                },
            ),
            "cheap": MockAdapter(
                "cheap",
                {
                    "cost_per_1k_input_tokens": 0.001,
                    "cost_per_1k_output_tokens": 0.002,
                },
            ),
        }
        selector = RuntimeSelector(runtimes)
        context = ExecutionContext(task="Test task")

        selected = selector.select(context, SelectionStrategy.COST_OPTIMIZED)

        assert selected.capabilities.runtime_name == "cheap"

    def test_select_cost_optimized_with_constraints(self):
        """Test cost optimization respects capability requirements."""
        runtimes = {
            "cheap_no_vision": MockAdapter(
                "cheap_no_vision",
                {
                    "cost_per_1k_input_tokens": 0.001,
                    "supports_vision": False,
                },
            ),
            "expensive_vision": MockAdapter(
                "expensive_vision",
                {
                    "cost_per_1k_input_tokens": 0.10,
                    "supports_vision": True,
                },
            ),
        }
        selector = RuntimeSelector(runtimes)
        context = ExecutionContext(task="Analyze this image")

        selected = selector.select(context, SelectionStrategy.COST_OPTIMIZED)

        # Must select the one with vision, even if expensive
        assert selected.capabilities.runtime_name == "expensive_vision"


class TestSelectLatencyOptimized:
    """Test LATENCY_OPTIMIZED selection strategy."""

    def test_select_latency_optimized(self):
        """Test selecting fastest runtime."""
        runtimes = {
            "slow": MockAdapter("slow", {"typical_latency_ms": 500.0}),
            "fast": MockAdapter("fast", {"typical_latency_ms": 50.0}),
        }
        selector = RuntimeSelector(runtimes)
        context = ExecutionContext(task="Test")

        selected = selector.select(context, SelectionStrategy.LATENCY_OPTIMIZED)

        assert selected.capabilities.runtime_name == "fast"


class TestSelectPreferred:
    """Test PREFERRED selection strategy."""

    def test_select_preferred_when_capable(self):
        """Test using preferred runtime when capable."""
        runtimes = {
            "default": MockAdapter("default"),
            "preferred": MockAdapter("preferred"),
        }
        selector = RuntimeSelector(runtimes, default_runtime="default")
        context = ExecutionContext(
            task="Test",
            preferred_runtime="preferred",
        )

        selected = selector.select(context, SelectionStrategy.PREFERRED)

        assert selected.capabilities.runtime_name == "preferred"

    def test_select_preferred_fallback(self):
        """Test fallback when preferred is not capable."""
        runtimes = {
            "default": MockAdapter("default", {"supports_vision": True}),
            "preferred": MockAdapter("preferred", {"supports_vision": False}),
        }
        selector = RuntimeSelector(runtimes, default_runtime="default")
        context = ExecutionContext(
            task="Analyze image",
            preferred_runtime="preferred",
        )

        selected = selector.select(context, SelectionStrategy.PREFERRED)

        # Should fall back because preferred lacks vision
        assert selected.capabilities.runtime_name == "default"

    def test_select_preferred_no_preference(self):
        """Test when no preference is set."""
        runtimes = {
            "default": MockAdapter("default"),
            "other": MockAdapter("other"),
        }
        selector = RuntimeSelector(runtimes, default_runtime="default")
        context = ExecutionContext(task="Test")

        selected = selector.select(context, SelectionStrategy.PREFERRED)

        # Should use capability match (prefers default)
        assert selected.capabilities.runtime_name == "default"


class TestSelectBalanced:
    """Test BALANCED selection strategy."""

    def test_select_balanced(self):
        """Test balanced selection between cost and latency."""
        runtimes = {
            "expensive_fast": MockAdapter(
                "expensive_fast",
                {
                    "cost_per_1k_input_tokens": 0.10,
                    "cost_per_1k_output_tokens": 0.30,
                    "typical_latency_ms": 50.0,
                },
            ),
            "cheap_slow": MockAdapter(
                "cheap_slow",
                {
                    "cost_per_1k_input_tokens": 0.001,
                    "cost_per_1k_output_tokens": 0.002,
                    "typical_latency_ms": 500.0,
                },
            ),
            "balanced": MockAdapter(
                "balanced",
                {
                    "cost_per_1k_input_tokens": 0.02,
                    "cost_per_1k_output_tokens": 0.06,
                    "typical_latency_ms": 100.0,
                },
            ),
        }
        selector = RuntimeSelector(runtimes)
        context = ExecutionContext(task="Test")

        selected = selector.select(context, SelectionStrategy.BALANCED)

        # Balanced should have best combined score
        assert selected.capabilities.runtime_name == "balanced"


class TestSelectFallbacks:
    """Test fallback behavior when no runtime meets requirements."""

    def test_fallback_to_default(self):
        """Test fallback to default when no runtime is capable."""
        runtimes = {
            "default": MockAdapter("default"),
            "other": MockAdapter("other"),
        }
        selector = RuntimeSelector(runtimes, default_runtime="default")
        # Require audio which no runtime supports
        context = ExecutionContext(task="Listen to this audio recording")

        selected = selector.select(context, SelectionStrategy.CAPABILITY_MATCH)

        # Should fall back to default
        assert selected.capabilities.runtime_name == "default"

    def test_fallback_returns_none_when_default_missing(self):
        """Test fallback when default runtime doesn't exist."""
        runtimes = {"only_one": MockAdapter("only_one")}
        selector = RuntimeSelector(runtimes, default_runtime="nonexistent")
        context = ExecutionContext(task="Listen to audio")

        selected = selector.select(context, SelectionStrategy.CAPABILITY_MATCH)

        # Default doesn't exist, returns None
        assert selected is None


class TestGetAllCapabilities:
    """Test get_all_capabilities method."""

    def test_get_all_capabilities(self):
        """Test getting capabilities for all runtimes."""
        runtimes = {
            "runtime_a": MockAdapter("runtime_a", {"supports_vision": True}),
            "runtime_b": MockAdapter("runtime_b", {"supports_audio": True}),
        }
        selector = RuntimeSelector(runtimes)

        caps = selector.get_all_capabilities()

        assert len(caps) == 2
        assert caps["runtime_a"].supports_vision is True
        assert caps["runtime_b"].supports_audio is True


class TestGetCapableRuntimesForTask:
    """Test get_capable_runtimes_for_task method."""

    def test_get_capable_runtimes_for_task(self):
        """Test getting capable runtime names for a task."""
        runtimes = {
            "with_vision": MockAdapter("with_vision", {"supports_vision": True}),
            "without_vision": MockAdapter("without_vision"),
        }
        selector = RuntimeSelector(runtimes)
        context = ExecutionContext(task="Analyze this screenshot")

        capable = selector.get_capable_runtimes_for_task(context)

        assert "with_vision" in capable
        assert "without_vision" not in capable


class TestExplainSelection:
    """Test explain_selection method."""

    def test_explain_capability_match(self):
        """Test explanation for capability match."""
        runtimes = {"kaizen_local": MockAdapter("kaizen_local")}
        selector = RuntimeSelector(runtimes, default_runtime="kaizen_local")
        context = ExecutionContext(task="Simple task")

        explanation = selector.explain_selection(
            context, SelectionStrategy.CAPABILITY_MATCH
        )

        assert explanation["strategy"] == "capability_match"
        assert explanation["selected"] == "kaizen_local"
        assert "kaizen_local" in explanation["capable_runtimes"]
        assert "default" in explanation["reason"].lower()

    def test_explain_cost_optimized(self):
        """Test explanation for cost optimization."""
        runtimes = {
            "cheap": MockAdapter("cheap", {"cost_per_1k_input_tokens": 0.001}),
        }
        selector = RuntimeSelector(runtimes)
        context = ExecutionContext(task="Test")

        explanation = selector.explain_selection(
            context, SelectionStrategy.COST_OPTIMIZED
        )

        assert explanation["strategy"] == "cost_optimized"
        assert "cost" in explanation["reason"].lower()

    def test_explain_latency_optimized(self):
        """Test explanation for latency optimization."""
        runtimes = {"fast": MockAdapter("fast", {"typical_latency_ms": 50.0})}
        selector = RuntimeSelector(runtimes)
        context = ExecutionContext(task="Test")

        explanation = selector.explain_selection(
            context, SelectionStrategy.LATENCY_OPTIMIZED
        )

        assert explanation["strategy"] == "latency_optimized"
        assert "latency" in explanation["reason"].lower()

    def test_explain_preferred(self):
        """Test explanation for preferred runtime."""
        runtimes = {"my_preferred": MockAdapter("my_preferred")}
        selector = RuntimeSelector(runtimes)
        context = ExecutionContext(
            task="Test",
            preferred_runtime="my_preferred",
        )

        explanation = selector.explain_selection(context, SelectionStrategy.PREFERRED)

        assert explanation["strategy"] == "preferred"
        assert "preferred" in explanation["reason"].lower()

    def test_explain_balanced(self):
        """Test explanation for balanced selection."""
        runtimes = {"balanced": MockAdapter("balanced")}
        selector = RuntimeSelector(runtimes)
        context = ExecutionContext(task="Test")

        explanation = selector.explain_selection(context, SelectionStrategy.BALANCED)

        assert explanation["strategy"] == "balanced"
        assert "balance" in explanation["reason"].lower()

    def test_explain_no_capable_runtime(self):
        """Test explanation when no runtime is capable."""
        runtimes = {"basic": MockAdapter("basic")}
        selector = RuntimeSelector(runtimes, default_runtime="basic")
        context = ExecutionContext(task="Listen to audio file")

        explanation = selector.explain_selection(
            context, SelectionStrategy.CAPABILITY_MATCH
        )

        assert explanation["selected"] == "basic"
        # Fell back to default
        assert len(explanation["capable_runtimes"]) == 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_select_with_empty_runtimes(self):
        """Test selection with no registered runtimes."""
        selector = RuntimeSelector({})
        context = ExecutionContext(task="Test")

        selected = selector.select(context)

        assert selected is None

    def test_analyze_requirements_empty_tools_list(self):
        """Test analyzing context with empty tools list."""
        selector = RuntimeSelector({"test": MockAdapter("test")})
        context = ExecutionContext(task="Test", tools=[])

        reqs = selector._analyze_requirements(context)

        assert "tool_calling" not in reqs

    def test_conversation_history_handling(self):
        """Test that conversation history is considered."""
        selector = RuntimeSelector({"test": MockAdapter("test")})
        context = ExecutionContext(
            task="Continue",
            conversation_history=[
                {"role": "user", "content": "Previous message"},
            ],
        )

        # Should not raise
        reqs = selector._analyze_requirements(context)
        assert isinstance(reqs, list)
