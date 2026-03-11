# Pipeline Edge Case Test Matrix - Phase 3

**Total Tests**: 127+

**Test File**: `tests/core/pipelines/test_pipeline_as_agent_edge_cases.py`

**Status**: PLANNED (Phase 3, TODO-174)

**Purpose**: Ensure pipeline-as-agent composability is bulletproof with exhaustive edge case coverage.

---

## Test Summary by Category

| Category | Test Count | Focus Area | Priority | Estimated Time |
|----------|------------|------------|----------|----------------|
| 1. Nesting Depth | 5 | 1, 2, 3, 5, 10 levels | P0 | 2 hours |
| 2. Pipeline Combinations | 81 | All 9x9 pattern pairs | P0 | 4 hours |
| 3. Error Handling | 7 | Failures, timeouts, recovery | P0 | 3 hours |
| 4. State Management | 5 | State isolation, concurrency | P0 | 2 hours |
| 5. Performance | 5 | Scalability, memory, speed | P1 | 2 hours |
| 6. A2A Integration | 4 | Semantic matching, fallback | P0 | 2 hours |
| 7. MCP Integration | 3 | MCP tool, resources, agents | P1 | 1 hour |
| 8. Special Cases | 5 | Edge inputs, circular deps | P0 | 2 hours |
| 9. Serialization | 4 | JSON, nested, A2A cards | P2 | 1 hour |
| 10. Observability | 4 | Tracing, metrics, logging | P1 | 1 hour |
| **TOTAL** | **127** | **Comprehensive coverage** | **P0** | **20 hours** |

---

## Category 1: Nesting Depth Tests (5 tests)

**Purpose**: Validate pipeline nesting works at all depths from 1 to 10 levels.

**Priority**: P0 - CRITICAL (core composability feature)

### Test Details

| Test # | Test Name | Description | Input | Expected Output | Edge Cases |
|--------|-----------|-------------|-------|-----------------|------------|
| 1.1 | `test_nesting_1_level` | No nesting, baseline | Pipeline with 3 agents | Results from all 3 agents | N/A |
| 1.2 | `test_nesting_2_levels` | Pipeline contains pipeline | Outer(Inner(agents)) | Results propagated correctly | Inner pipeline fails |
| 1.3 | `test_nesting_3_levels` | 3-level nesting | L1(L2(L3(agents))) | Correct result depth | Result unwrapping |
| 1.4 | `test_nesting_5_levels` | 5-level nesting (stress) | L1→L2→L3→L4→L5 | Performance acceptable (<500ms) | Stack depth |
| 1.5 | `test_nesting_10_levels` | Maximum depth | L1→L2→...→L10 | No stack overflow | Recursion limit |

### Test Implementation

```python
class TestNestingDepth:
    """Test pipeline nesting at various depths."""

    def test_nesting_1_level(self, mock_agents):
        """Test 1: No nesting, baseline validation."""
        pipeline = Pipeline.sequential([mock_agents[0], mock_agents[1], mock_agents[2]])
        result = pipeline.run(data="test")

        assert result is not None
        assert "final_output" in result
        assert "intermediate_results" in result
        assert len(result["intermediate_results"]) == 3

    def test_nesting_2_levels(self, mock_agents):
        """Test 2: Pipeline contains pipeline (2 levels)."""
        # Inner pipeline
        inner = Pipeline.sequential([mock_agents[0], mock_agents[1]])

        # Outer pipeline contains inner as agent
        outer = Pipeline.sequential([inner.to_agent(), mock_agents[2]])

        result = outer.run(data="test")

        assert result is not None
        assert "final_output" in result
        # Verify inner pipeline executed
        assert len(result["intermediate_results"]) == 2

    def test_nesting_3_levels(self, mock_agents):
        """Test 3: 3-level nesting."""
        l3 = Pipeline.sequential([mock_agents[0]])
        l2 = Pipeline.sequential([l3.to_agent(), mock_agents[1]])
        l1 = Pipeline.sequential([l2.to_agent(), mock_agents[2]])

        result = l1.run(data="test")

        assert result is not None
        assert "final_output" in result

    def test_nesting_5_levels(self, mock_agents):
        """Test 4: 5-level nesting (stress test)."""
        l5 = Pipeline.sequential([mock_agents[0]])
        l4 = Pipeline.sequential([l5.to_agent()])
        l3 = Pipeline.sequential([l4.to_agent()])
        l2 = Pipeline.sequential([l3.to_agent()])
        l1 = Pipeline.sequential([l2.to_agent()])

        start = time.time()
        result = l1.run(data="test")
        duration = time.time() - start

        assert result is not None
        assert duration < 0.5  # <500ms

    def test_nesting_10_levels(self, mock_agents):
        """Test 5: 10-level nesting (maximum depth)."""
        pipeline = Pipeline.sequential([mock_agents[0]])
        for i in range(9):
            pipeline = Pipeline.sequential([pipeline.to_agent()])

        # Should not raise RecursionError
        result = pipeline.run(data="test")
        assert result is not None
```

---

## Category 2: Pipeline Combinations (81 tests)

**Purpose**: Validate ALL combinations of 9 patterns nested within each other (9x9 matrix).

**Priority**: P0 - CRITICAL (ensure pattern composability)

### Combination Matrix (9x9 = 81 tests)

|  | Sequential | Supervisor | Router | Ensemble | Blackboard | Consensus | Debate | Handoff | Parallel |
|---|-----------|-----------|--------|----------|------------|-----------|--------|---------|----------|
| **Sequential** | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
| **Supervisor** | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 |
| **Router** | 19 | 20 | 21 | 22 | 23 | 24 | 25 | 26 | 27 |
| **Ensemble** | 28 | 29 | 30 | 31 | 32 | 33 | 34 | 35 | 36 |
| **Blackboard** | 37 | 38 | 39 | 40 | 41 | 42 | 43 | 44 | 45 |
| **Consensus** | 46 | 47 | 48 | 49 | 50 | 51 | 52 | 53 | 54 |
| **Debate** | 55 | 56 | 57 | 58 | 59 | 60 | 61 | 62 | 63 |
| **Handoff** | 64 | 65 | 66 | 67 | 68 | 69 | 70 | 71 | 72 |
| **Parallel** | 73 | 74 | 75 | 76 | 77 | 78 | 79 | 80 | 81 |

**Example Combinations**:
- Test 1: Sequential → Sequential
- Test 2: Sequential → Supervisor-Worker
- Test 11: Supervisor-Worker → Supervisor-Worker (nested delegation)
- Test 31: Ensemble → Ensemble (nested multi-perspective)
- Test 81: Parallel → Parallel (nested concurrency)

### Test Implementation

```python
import itertools
import pytest

ALL_PATTERNS = [
    "sequential", "supervisor_worker", "router", "ensemble",
    "blackboard", "consensus", "debate", "handoff", "parallel"
]

class TestPipelineCombinations:
    """Test all 9x9 = 81 pattern combinations."""

    @pytest.mark.parametrize("outer_pattern,inner_pattern",
        itertools.product(ALL_PATTERNS, ALL_PATTERNS))
    def test_pattern_combination(self, outer_pattern, inner_pattern, mock_agents):
        """Test outer_pattern contains inner_pattern as agent."""
        # Create inner pipeline
        inner = self._create_pattern(inner_pattern, mock_agents[:2])
        inner_agent = inner.to_agent(name=f"{inner_pattern}_inner")

        # Create outer pipeline containing inner
        outer_agents = [inner_agent] + mock_agents[2:4]
        outer = self._create_pattern(outer_pattern, outer_agents)

        # Execute
        result = outer.run(data="test", task="test task")

        # Validate
        assert result is not None, f"{outer_pattern} → {inner_pattern} failed"
        assert "error" not in result or result["error"] is None

        # Verify inner pipeline was executed
        assert inner_agent.agent_id in str(result)

    def _create_pattern(self, pattern_name, agents):
        """Factory for creating patterns by name."""
        if pattern_name == "sequential":
            return Pipeline.sequential(agents)
        elif pattern_name == "supervisor_worker":
            return Pipeline.supervisor_worker(supervisor=agents[0], workers=agents[1:])
        elif pattern_name == "router":
            return Pipeline.router(agents)
        elif pattern_name == "ensemble":
            return Pipeline.ensemble(agents=agents[:-1], synthesizer=agents[-1])
        elif pattern_name == "blackboard":
            return Pipeline.blackboard(specialists=agents[:-1], controller=agents[-1])
        elif pattern_name == "consensus":
            return Pipeline.consensus(agents)
        elif pattern_name == "debate":
            return Pipeline.debate(agents)
        elif pattern_name == "handoff":
            return Pipeline.handoff(agents)
        elif pattern_name == "parallel":
            return Pipeline.parallel(agents)
        else:
            raise ValueError(f"Unknown pattern: {pattern_name}")
```

---

## Category 3: Error Handling (7 tests)

**Purpose**: Validate pipeline handles agent failures gracefully with configurable error modes.

**Priority**: P0 - CRITICAL (production robustness)

### Test Details

| Test # | Test Name | Scenario | Error Mode | Expected Behavior |
|--------|-----------|----------|------------|-------------------|
| 3.1 | `test_agent_failure_graceful` | Agent raises exception | graceful | Continue execution, return error info |
| 3.2 | `test_agent_failure_fail_fast` | Agent raises exception | fail-fast | Raise exception, stop execution |
| 3.3 | `test_timeout_handling` | Agent times out | graceful | Return timeout error, continue |
| 3.4 | `test_cascading_failures` | Multiple agents fail | graceful | Return all errors, partial results |
| 3.5 | `test_partial_results` | Some agents succeed | graceful | Return successful results |
| 3.6 | `test_retry_logic` | Agent fails then succeeds | retry | Retry with backoff, return success |
| 3.7 | `test_circuit_breaker` | Agent fails repeatedly | circuit-breaker | Stop calling agent, return cached error |

### Test Implementation

```python
class TestErrorHandling:
    """Test pipeline error handling strategies."""

    def test_agent_failure_graceful(self, mock_agents):
        """Test 1: Graceful degradation on agent failure."""
        failing_agent = MockFailingAgent()
        pipeline = Pipeline.sequential([mock_agents[0], failing_agent, mock_agents[1]])
        pipeline.error_handling = "graceful"

        result = pipeline.run(data="test")

        assert result is not None
        assert "intermediate_results" in result
        # Second result should contain error
        assert "error" in result["intermediate_results"][1]
        # Third agent still executed
        assert result["intermediate_results"][2]["status"] != "failed"

    def test_agent_failure_fail_fast(self, mock_agents):
        """Test 2: Fail-fast mode stops on first error."""
        failing_agent = MockFailingAgent()
        pipeline = Pipeline.sequential([mock_agents[0], failing_agent, mock_agents[1]])
        pipeline.error_handling = "fail-fast"

        with pytest.raises(Exception):
            pipeline.run(data="test")

    def test_timeout_handling(self, mock_agents):
        """Test 3: Agent timeout handling."""
        slow_agent = MockSlowAgent(timeout=5.0)
        pipeline = Pipeline.sequential([mock_agents[0], slow_agent])
        pipeline.timeout = 1.0  # 1 second timeout

        result = pipeline.run(data="test")

        assert "error" in result["intermediate_results"][1]
        assert "timeout" in result["intermediate_results"][1]["error"].lower()

    def test_cascading_failures(self, mock_agents):
        """Test 4: Multiple agents fail, pipeline recovers."""
        failing_1 = MockFailingAgent()
        failing_2 = MockFailingAgent()
        pipeline = Pipeline.sequential([failing_1, mock_agents[0], failing_2])
        pipeline.error_handling = "graceful"

        result = pipeline.run(data="test")

        # Both failures recorded
        assert "error" in result["intermediate_results"][0]
        assert "error" in result["intermediate_results"][2]
        # Middle agent succeeded
        assert result["intermediate_results"][1]["status"] != "failed"

    def test_partial_results(self, mock_agents):
        """Test 5: Return partial results when some agents fail."""
        failing_agent = MockFailingAgent()
        pipeline = Pipeline.parallel([mock_agents[0], failing_agent, mock_agents[1]])

        result = pipeline.run(data="test")

        assert "results" in result
        # 2 successful, 1 failed
        successful = [r for r in result["results"] if "error" not in r]
        assert len(successful) == 2

    def test_retry_logic(self, mock_agents):
        """Test 6: Retry failed agents with exponential backoff."""
        flaky_agent = MockFlakyAgent(fail_count=2)  # Fails twice, then succeeds
        pipeline = Pipeline.sequential([flaky_agent])
        pipeline.retry_config = {"max_retries": 3, "backoff": "exponential"}

        result = pipeline.run(data="test")

        # Should succeed after retries
        assert "error" not in result
        assert result["retry_count"] == 2

    def test_circuit_breaker(self, mock_agents):
        """Test 7: Circuit breaker prevents cascading failures."""
        failing_agent = MockFailingAgent()
        pipeline = Pipeline.sequential([failing_agent])
        pipeline.circuit_breaker = {"threshold": 3, "timeout": 60}

        # Fail 3 times to open circuit
        for i in range(3):
            result = pipeline.run(data="test")
            assert "error" in result

        # 4th call should use circuit breaker (cached error)
        start = time.time()
        result = pipeline.run(data="test")
        duration = time.time() - start

        assert duration < 0.01  # Circuit breaker is fast (<10ms)
        assert "circuit_breaker" in result
```

---

## Category 4: State Management (5 tests)

**Purpose**: Validate pipeline state isolation and concurrent execution safety.

**Priority**: P0 - CRITICAL (prevent state leaks)

### Test Details

| Test # | Test Name | Scenario | Expected Behavior |
|--------|-----------|----------|-------------------|
| 4.1 | `test_stateful_pipelines` | Pipeline maintains state across runs | State preserved between runs |
| 4.2 | `test_shared_memory_isolation` | Multiple pipelines | No accidental state sharing |
| 4.3 | `test_concurrent_executions` | Same pipeline, multiple threads | No race conditions |
| 4.4 | `test_state_reset` | Reset pipeline state | State cleared correctly |
| 4.5 | `test_persistent_state` | State survives `.to_agent()` | State preserved in agent wrapper |

### Test Implementation

```python
class TestStateManagement:
    """Test pipeline state management and isolation."""

    def test_stateful_pipelines(self, mock_agents):
        """Test 1: Pipeline maintains state across runs."""
        pipeline = Pipeline.sequential([mock_agents[0], mock_agents[1]])
        pipeline.state = {"counter": 0}

        # Run 1
        result1 = pipeline.run(data="test1")
        pipeline.state["counter"] += 1

        # Run 2
        result2 = pipeline.run(data="test2")

        # State preserved
        assert pipeline.state["counter"] == 1

    def test_shared_memory_isolation(self, mock_agents):
        """Test 2: Pipelines don't share state accidentally."""
        pipeline1 = Pipeline.sequential([mock_agents[0]])
        pipeline2 = Pipeline.sequential([mock_agents[1]])

        pipeline1.state = {"id": "pipeline1"}
        pipeline2.state = {"id": "pipeline2"}

        # Modify pipeline1 state
        pipeline1.state["data"] = "modified"

        # pipeline2 should not see modification
        assert "data" not in pipeline2.state
        assert pipeline2.state["id"] == "pipeline2"

    def test_concurrent_executions(self, mock_agents):
        """Test 3: Concurrent execution safety."""
        import threading

        pipeline = Pipeline.sequential([mock_agents[0]])
        results = []

        def run_pipeline(data):
            result = pipeline.run(data=data)
            results.append(result)

        # Run 10 concurrent executions
        threads = [threading.Thread(target=run_pipeline, args=(f"test{i}",))
                  for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All executions succeeded
        assert len(results) == 10
        assert all("error" not in r or r["error"] is None for r in results)

    def test_state_reset(self, mock_agents):
        """Test 4: Pipeline state reset."""
        pipeline = Pipeline.sequential([mock_agents[0]])
        pipeline.state = {"counter": 5, "data": "important"}

        # Reset state
        pipeline.reset_state()

        # State cleared
        assert pipeline.state == {} or pipeline.state is None

    def test_persistent_state(self, mock_agents):
        """Test 5: State persists when pipeline converted to agent."""
        pipeline = Pipeline.sequential([mock_agents[0]])
        pipeline.state = {"id": "pipeline123"}

        # Convert to agent
        agent = pipeline.to_agent()

        # State should be accessible
        assert hasattr(agent, "pipeline")
        assert agent.pipeline.state["id"] == "pipeline123"
```

---

## Category 5: Performance (5 tests)

**Purpose**: Validate pipeline performance at scale (agents, nesting, concurrency).

**Priority**: P1 - HIGH (production scalability)

### Test Details

| Test # | Test Name | Scenario | Performance Target |
|--------|-----------|----------|-------------------|
| 5.1 | `test_large_agent_counts` | 100+ agents in pipeline | <5 seconds execution |
| 5.2 | `test_deep_nesting_performance` | 10 levels of nesting | <1 second overhead |
| 5.3 | `test_parallel_scalability` | 50 concurrent agents | <3 seconds with parallelism |
| 5.4 | `test_memory_usage` | Large pipeline | <512MB memory |
| 5.5 | `test_a2a_matching_speed` | A2A matching 100 agents | <50ms per match |

### Test Implementation

```python
import psutil
import time

class TestPerformance:
    """Test pipeline performance at scale."""

    def test_large_agent_counts(self, mock_agents):
        """Test 1: 100+ agents in pipeline."""
        agents = [MockFastAgent(id=f"agent{i}") for i in range(100)]
        pipeline = Pipeline.sequential(agents)

        start = time.time()
        result = pipeline.run(data="test")
        duration = time.time() - start

        assert result is not None
        assert duration < 5.0  # <5 seconds

    def test_deep_nesting_performance(self, mock_agents):
        """Test 2: 10 levels of nesting performance."""
        pipeline = Pipeline.sequential([MockFastAgent()])
        for i in range(9):
            pipeline = Pipeline.sequential([pipeline.to_agent()])

        start = time.time()
        result = pipeline.run(data="test")
        duration = time.time() - start

        assert result is not None
        assert duration < 1.0  # <1 second overhead

    def test_parallel_scalability(self, mock_agents):
        """Test 3: 50 concurrent agents."""
        agents = [MockFastAgent(id=f"agent{i}") for i in range(50)]
        pipeline = Pipeline.parallel(agents)

        start = time.time()
        result = pipeline.run(data="test")
        duration = time.time() - start

        assert result is not None
        assert len(result["results"]) == 50
        # Should be much faster than sequential (50 * 0.1s = 5s)
        assert duration < 3.0  # <3 seconds with parallelism

    def test_memory_usage(self, mock_agents):
        """Test 4: Memory usage with large pipeline."""
        import gc

        # Baseline memory
        gc.collect()
        baseline = psutil.Process().memory_info().rss / 1024 / 1024  # MB

        # Create large pipeline
        agents = [MockFastAgent(id=f"agent{i}") for i in range(100)]
        pipeline = Pipeline.sequential(agents)
        result = pipeline.run(data="test")

        # Check memory usage
        current = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        memory_increase = current - baseline

        assert memory_increase < 512  # <512MB increase

    def test_a2a_matching_speed(self, mock_agents):
        """Test 5: A2A matching performance."""
        agents = [MockAgentWithA2A(id=f"agent{i}") for i in range(100)]
        pipeline = Pipeline.router(agents, routing_strategy="semantic")

        start = time.time()
        result = pipeline.run(task="Test task for routing")
        duration = time.time() - start

        assert result is not None
        # A2A matching should be fast (<50ms for 100 agents)
        assert duration < 0.05  # <50ms
```

---

## Category 6: A2A Integration (4 tests)

**Purpose**: Validate A2A capability matching works correctly with fallback.

**Priority**: P0 - CRITICAL (core feature)

### Test Details

| Test # | Test Name | Scenario | Expected Behavior |
|--------|-----------|----------|-------------------|
| 6.1 | `test_a2a_unavailable_fallback` | A2A module not available | Fallback to round-robin |
| 6.2 | `test_a2a_matching_accuracy` | Correct agent selected | Best match chosen |
| 6.3 | `test_a2a_zero_score` | No matching agent | Fallback to first agent |
| 6.4 | `test_a2a_conflicting_capabilities` | Multiple high scores | Deterministic selection |

### Test Implementation

```python
class TestA2AIntegration:
    """Test A2A capability matching integration."""

    def test_a2a_unavailable_fallback(self, mock_agents, monkeypatch):
        """Test 1: Graceful fallback when A2A unavailable."""
        # Mock A2A_AVAILABLE = False
        monkeypatch.setattr("kaizen.orchestration.patterns.meta_controller.A2A_AVAILABLE", False)

        pipeline = Pipeline.router(mock_agents, routing_strategy="semantic")
        result = pipeline.run(task="Test task")

        # Should use fallback (first agent), not crash
        assert result is not None
        assert "error" not in result

    def test_a2a_matching_accuracy(self, mock_agents):
        """Test 2: A2A selects correct agent based on capabilities."""
        code_agent = MockAgentWithA2A(
            id="code_expert",
            capabilities=["python", "code_generation"]
        )
        data_agent = MockAgentWithA2A(
            id="data_expert",
            capabilities=["data_analysis", "statistics"]
        )

        pipeline = Pipeline.router([code_agent, data_agent], routing_strategy="semantic")

        # Code task should select code_agent
        result = pipeline.run(task="Write a Python function to sort a list")
        assert "code_expert" in str(result)

    def test_a2a_zero_score(self, mock_agents):
        """Test 3: No matching agent (all scores = 0)."""
        agent1 = MockAgentWithA2A(id="agent1", capabilities=["capability_A"])
        agent2 = MockAgentWithA2A(id="agent2", capabilities=["capability_B"])

        pipeline = Pipeline.router([agent1, agent2], routing_strategy="semantic")

        # Task requires capability_C (no match)
        result = pipeline.run(task="Perform task requiring capability_C")

        # Should fall back to first agent
        assert result is not None
        assert "agent1" in str(result)

    def test_a2a_conflicting_capabilities(self, mock_agents):
        """Test 4: Multiple agents with high scores."""
        agent1 = MockAgentWithA2A(id="agent1", capabilities=["python", "coding"])
        agent2 = MockAgentWithA2A(id="agent2", capabilities=["python", "programming"])

        pipeline = Pipeline.router([agent1, agent2], routing_strategy="semantic")

        # Both agents match "python" equally
        result1 = pipeline.run(task="Write Python code")
        result2 = pipeline.run(task="Write Python code")

        # Selection should be deterministic
        assert result1 == result2
```

---

## Category 7: MCP Integration (3 tests)

**Purpose**: Validate pipelines work with MCP protocol.

**Priority**: P1 - HIGH (MCP is key integration)

### Test Details

| Test # | Test Name | Scenario | Expected Behavior |
|--------|-----------|----------|-------------------|
| 7.1 | `test_pipeline_as_mcp_tool` | Expose pipeline as MCP tool | Callable via MCP |
| 7.2 | `test_mcp_agents_in_pipeline` | Pipeline contains MCP agents | MCP calls succeed |
| 7.3 | `test_mcp_resource_access` | Pipeline accesses MCP resources | Resources accessible |

### Test Implementation

```python
class TestMCPIntegration:
    """Test MCP integration with pipelines."""

    def test_pipeline_as_mcp_tool(self, mock_agents):
        """Test 1: Pipeline exposed as MCP tool."""
        from kaizen.integrations.mcp import expose_as_mcp_tool

        pipeline = Pipeline.sequential(mock_agents)
        mcp_tool = expose_as_mcp_tool(pipeline, name="data_processor")

        # Call pipeline via MCP
        result = mcp_tool.call(data="test")

        assert result is not None
        assert "final_output" in result

    def test_mcp_agents_in_pipeline(self, mock_agents):
        """Test 2: Pipeline contains MCP-based agents."""
        from kaizen.integrations.mcp import MCPAgent

        mcp_agent = MCPAgent(server_url="http://localhost:8000", tool_name="analyzer")
        pipeline = Pipeline.sequential([mock_agents[0], mcp_agent])

        result = pipeline.run(data="test")

        # MCP agent should execute successfully
        assert result is not None

    def test_mcp_resource_access(self, mock_agents):
        """Test 3: Pipeline accesses MCP resources."""
        from kaizen.integrations.mcp import MCPResourceAgent

        resource_agent = MCPResourceAgent(resource_uri="mcp://server/resource/123")
        pipeline = Pipeline.sequential([resource_agent])

        result = pipeline.run(query="Get resource data")

        assert result is not None
        assert "resource_data" in result
```

---

## Category 8: Special Cases (5 tests)

**Purpose**: Validate edge cases that don't fit other categories.

**Priority**: P0 - CRITICAL (prevent crashes)

### Test Details

| Test # | Test Name | Scenario | Expected Behavior |
|--------|-----------|----------|-------------------|
| 8.1 | `test_empty_agent_list` | No agents provided | Raise ValueError |
| 8.2 | `test_single_agent_pipeline` | One agent only | Works correctly |
| 8.3 | `test_circular_dependencies` | Pipeline contains itself | Raise ValueError |
| 8.4 | `test_duplicate_agent_ids` | Same agent ID twice | Raise ValueError |
| 8.5 | `test_none_inputs_outputs` | None values | Handle gracefully |

### Test Implementation

```python
class TestSpecialCases:
    """Test special edge cases."""

    def test_empty_agent_list(self):
        """Test 1: Empty agent list raises error."""
        with pytest.raises(ValueError, match="agents cannot be empty"):
            Pipeline.sequential([])

    def test_single_agent_pipeline(self, mock_agents):
        """Test 2: Single agent pipeline works."""
        pipeline = Pipeline.sequential([mock_agents[0]])
        result = pipeline.run(data="test")

        assert result is not None
        assert len(result["intermediate_results"]) == 1

    def test_circular_dependencies(self, mock_agents):
        """Test 3: Detect circular dependencies."""
        pipeline = Pipeline.sequential([mock_agents[0]])

        # Try to add pipeline to itself
        with pytest.raises(ValueError, match="circular dependency"):
            pipeline_agent = pipeline.to_agent()
            Pipeline.sequential([pipeline_agent, pipeline])

    def test_duplicate_agent_ids(self, mock_agents):
        """Test 4: Duplicate agent IDs raise error."""
        agent1 = mock_agents[0]
        agent2 = mock_agents[1]
        agent2.agent_id = agent1.agent_id  # Duplicate ID

        with pytest.raises(ValueError, match="duplicate agent ID"):
            Pipeline.sequential([agent1, agent2])

    def test_none_inputs_outputs(self, mock_agents):
        """Test 5: None inputs/outputs handled gracefully."""
        pipeline = Pipeline.sequential([mock_agents[0]])

        # None input
        result = pipeline.run(data=None)
        assert result is not None  # Should not crash

        # Agent returns None
        none_agent = MockNoneReturningAgent()
        pipeline2 = Pipeline.sequential([none_agent])
        result2 = pipeline2.run(data="test")
        assert result2 is not None
```

---

## Category 9: Serialization (4 tests)

**Purpose**: Validate pipeline serialization to/from JSON.

**Priority**: P2 - NICE TO HAVE (future feature)

### Test Details

| Test # | Test Name | Scenario | Expected Behavior |
|--------|-----------|----------|-------------------|
| 9.1 | `test_pipeline_to_json` | Serialize pipeline | Valid JSON output |
| 9.2 | `test_pipeline_from_json` | Deserialize pipeline | Reconstructed correctly |
| 9.3 | `test_nested_pipeline_serialization` | Nested pipelines | Correct structure |
| 9.4 | `test_a2a_card_serialization` | A2A cards in JSON | Capabilities preserved |

### Test Implementation

```python
import json

class TestSerialization:
    """Test pipeline serialization."""

    def test_pipeline_to_json(self, mock_agents):
        """Test 1: Serialize pipeline to JSON."""
        pipeline = Pipeline.sequential(mock_agents)

        json_str = pipeline.to_json()
        data = json.loads(json_str)

        assert "type" in data
        assert data["type"] == "SequentialPipeline"
        assert "agents" in data
        assert len(data["agents"]) == len(mock_agents)

    def test_pipeline_from_json(self, mock_agents):
        """Test 2: Deserialize pipeline from JSON."""
        pipeline = Pipeline.sequential(mock_agents)
        json_str = pipeline.to_json()

        # Deserialize
        pipeline2 = Pipeline.from_json(json_str)

        # Should be equivalent
        assert type(pipeline2) == type(pipeline)
        assert len(pipeline2.agents) == len(pipeline.agents)

    def test_nested_pipeline_serialization(self, mock_agents):
        """Test 3: Nested pipeline serialization."""
        inner = Pipeline.sequential(mock_agents[:2])
        outer = Pipeline.sequential([inner.to_agent(), mock_agents[2]])

        json_str = outer.to_json()
        data = json.loads(json_str)

        # Nested structure preserved
        assert "agents" in data
        assert any("SequentialPipeline" in str(agent) for agent in data["agents"])

    def test_a2a_card_serialization(self, mock_agents):
        """Test 4: A2A cards serialized correctly."""
        agent_with_a2a = MockAgentWithA2A(capabilities=["python", "coding"])
        pipeline = Pipeline.router([agent_with_a2a])

        json_str = pipeline.to_json()
        data = json.loads(json_str)

        # A2A capabilities preserved
        assert "agents" in data
        agent_data = data["agents"][0]
        assert "capabilities" in agent_data
        assert "python" in agent_data["capabilities"]
```

---

## Category 10: Observability (4 tests)

**Purpose**: Validate pipeline execution tracing and metrics.

**Priority**: P1 - HIGH (production debugging)

### Test Details

| Test # | Test Name | Scenario | Expected Behavior |
|--------|-----------|----------|-------------------|
| 10.1 | `test_execution_tracing` | Trace pipeline execution | Complete trace captured |
| 10.2 | `test_metrics_collection` | Collect execution metrics | Timing, counts captured |
| 10.3 | `test_logging_output` | Log pipeline events | Logs at correct levels |
| 10.4 | `test_error_reporting` | Error details captured | Full context available |

### Test Implementation

```python
import logging

class TestObservability:
    """Test pipeline observability."""

    def test_execution_tracing(self, mock_agents):
        """Test 1: Trace pipeline execution."""
        from kaizen.observability import enable_tracing

        enable_tracing()
        pipeline = Pipeline.sequential(mock_agents)

        result = pipeline.run(data="test")

        # Get trace
        trace = pipeline.get_trace()

        assert trace is not None
        assert len(trace["spans"]) == len(mock_agents)
        assert all("duration" in span for span in trace["spans"])

    def test_metrics_collection(self, mock_agents):
        """Test 2: Metrics collection."""
        from kaizen.observability import MetricsCollector

        collector = MetricsCollector()
        pipeline = Pipeline.sequential(mock_agents)
        pipeline.metrics_collector = collector

        result = pipeline.run(data="test")

        metrics = collector.get_metrics()
        assert "total_duration" in metrics
        assert "agent_count" in metrics
        assert metrics["agent_count"] == len(mock_agents)

    def test_logging_output(self, mock_agents, caplog):
        """Test 3: Logging output."""
        with caplog.at_level(logging.INFO):
            pipeline = Pipeline.sequential(mock_agents)
            result = pipeline.run(data="test")

        # Check log messages
        assert any("Executing pipeline" in record.message for record in caplog.records)
        assert any("Pipeline complete" in record.message for record in caplog.records)

    def test_error_reporting(self, mock_agents):
        """Test 4: Error details captured."""
        failing_agent = MockFailingAgent()
        pipeline = Pipeline.sequential([failing_agent])
        pipeline.error_handling = "graceful"

        result = pipeline.run(data="test")

        # Error details should include full context
        error_info = result["intermediate_results"][0]
        assert "error" in error_info
        assert "traceback" in error_info
        assert "agent_id" in error_info
```

---

## Test Execution Strategy

### Test Organization

**File**: `tests/core/pipelines/test_pipeline_as_agent_edge_cases.py`

**Structure**:
- 10 test classes (one per category)
- 127 test methods total
- Parametrized tests for combinations (81 from 1 method)
- Shared fixtures in `conftest.py`

### Test Fixtures

```python
# tests/core/pipelines/conftest.py

import pytest
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import Signature

@pytest.fixture
def mock_agents():
    """Create 10 mock agents for testing."""
    agents = []
    for i in range(10):
        agent = MockAgent(
            id=f"agent{i}",
            config=BaseAgentConfig(llm_provider="mock", model="test")
        )
        agents.append(agent)
    return agents

@pytest.fixture
def mock_a2a_agents():
    """Create mock agents with A2A capabilities."""
    # Implementation
    pass

class MockAgent(BaseAgent):
    """Mock agent for testing."""
    def run(self, **inputs):
        return {"result": f"processed by {self.agent_id}", "input": inputs}

class MockFailingAgent(BaseAgent):
    """Mock agent that always fails."""
    def run(self, **inputs):
        raise Exception("Intentional failure for testing")

# ... more fixtures
```

### Test Execution

**Run all edge case tests**:
```bash
pytest tests/core/pipelines/test_pipeline_as_agent_edge_cases.py -v
```

**Run specific category**:
```bash
pytest tests/core/pipelines/test_pipeline_as_agent_edge_cases.py::TestNestingDepth -v
```

**Run performance tests only**:
```bash
pytest tests/core/pipelines/test_pipeline_as_agent_edge_cases.py::TestPerformance -v
```

**Run with coverage**:
```bash
pytest tests/core/pipelines/test_pipeline_as_agent_edge_cases.py --cov=kaizen.orchestration.pipeline --cov-report=html
```

---

## Success Criteria

- [ ] All 127+ tests passing (127/127)
- [ ] 100% code coverage for new pipeline code
- [ ] All tests complete in <5 minutes total
- [ ] No flaky tests (100% reproducible)
- [ ] No regressions in existing tests (507+ pass)

---

## Appendix: Test Priority Matrix

### P0 - CRITICAL (Must Pass Before Phase 4)
- Category 1: Nesting Depth (5 tests)
- Category 2: Pipeline Combinations (81 tests)
- Category 3: Error Handling (7 tests)
- Category 4: State Management (5 tests)
- Category 6: A2A Integration (4 tests)
- Category 8: Special Cases (5 tests)
- **Total P0**: 107 tests

### P1 - HIGH (Must Pass Before Production)
- Category 5: Performance (5 tests)
- Category 7: MCP Integration (3 tests)
- Category 10: Observability (4 tests)
- **Total P1**: 12 tests

### P2 - NICE TO HAVE (Future Enhancement)
- Category 9: Serialization (4 tests)
- **Total P2**: 4 tests

---

**Last Updated**: 2025-10-27

**Status**: PLANNED (Ready for implementation in TODO-174, Day 4-5)
