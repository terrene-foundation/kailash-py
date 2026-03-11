# Universal Tool Integration Testing Pattern

**Reference**: ADR-016 - Universal Tool Integration for All 25 Agents

## Overview

Every agent modified for tool support requires **3 tests minimum**:
1. **Tool Discovery Test** (Tier 1: Unit, mocked LLM)
2. **Tool Execution Test** (Tier 2: Integration, real LLM, real tools)
3. **Backward Compatibility Test** (Tier 1: Unit, mocked LLM)

Total: **75 tests** (25 agents × 3 tests)

## Test File Structure

**Location**: `tests/unit/agents/test_{agent_name}_tool_integration.py`

**Example**: `tests/unit/agents/test_simple_qa_tool_integration.py`

```python
"""
Test SimpleQAAgent tool integration.

3-tier testing strategy:
- Tier 1 (Unit): Mocked LLM, real tool registry
- Tier 2 (Integration): Real Ollama LLM, real tools, real file system
- Tier 3 (E2E): Real OpenAI LLM, real tools (high-value agents only)

Related:
- ADR-016: Universal Tool Integration
- ADR-012: BaseAgent Tool Integration
"""

import pytest
import asyncio
from pathlib import Path
from typing import Dict, Any

from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import SimpleQAConfig
from kaizen.tools.registry import ToolRegistry

from kaizen.tools.types import DangerLevel, ToolCategory

class TestSimpleQAToolDiscovery:
    """Test tool discovery capabilities (Tier 1: Unit)."""

    def test_has_tool_support_with_registry(self):
        """Verify agent reports tool support when registry provided."""

        # 12 builtin tools enabled via MCP

        agent = SimpleQAAgent(
            llm_provider="mock",
            model="mock-model",
            tools="all"  # Enable 12 builtin tools via MCP
        )

        assert agent.has_tool_support()

    def test_has_no_tool_support_without_registry(self):
        """Verify agent reports no tool support when registry not provided."""
        agent = SimpleQAAgent(
            llm_provider="mock",
            model="mock-model"
            # NO tool_registry
        )

        assert not agent.has_tool_support()

    def test_discover_all_tools(self):
        """Verify agent can discover all builtin tools."""

        # 12 builtin tools enabled via MCP

        agent = SimpleQAAgent(
            llm_provider="mock",
            model="mock-model",
            tools="all"  # Enable 12 builtin tools via MCP
        )

        # Discover all tools
        tools = asyncio.run(agent.discover_tools())

        assert len(tools) == 12  # 12 builtin tools
        tool_names = {t.name for t in tools}
        assert "read_file" in tool_names
        assert "http_get" in tool_names
        assert "fetch_url" in tool_names

    def test_discover_tools_by_category(self):
        """Verify agent can filter tools by category."""

        # 12 builtin tools enabled via MCP

        agent = SimpleQAAgent(
            llm_provider="mock",
            model="mock-model",
            tools="all"  # Enable 12 builtin tools via MCP
        )

        # Discover file tools only
        file_tools = asyncio.run(
            agent.discover_tools(category=ToolCategory.SYSTEM)
        )

        assert all(t.category == ToolCategory.SYSTEM for t in file_tools)
        assert len(file_tools) == 5  # 5 file tools

    def test_discover_safe_tools_only(self):
        """Verify agent can filter tools by danger level."""

        # 12 builtin tools enabled via MCP

        agent = SimpleQAAgent(
            llm_provider="mock",
            model="mock-model",
            tools="all"  # Enable 12 builtin tools via MCP
        )

        # Discover safe tools only
        safe_tools = asyncio.run(agent.discover_tools(safe_only=True))

        assert all(t.danger_level == DangerLevel.SAFE for t in safe_tools)
        assert len(safe_tools) == 2  # list_directory, file_exists

    def test_discover_tools_by_keyword(self):
        """Verify agent can search tools by keyword."""

        # 12 builtin tools enabled via MCP

        agent = SimpleQAAgent(
            llm_provider="mock",
            model="mock-model",
            tools="all"  # Enable 12 builtin tools via MCP
        )

        # Search for "http" tools
        http_tools = asyncio.run(agent.discover_tools(keyword="http"))

        assert len(http_tools) == 4  # http_get, http_post, http_put, http_delete
        assert all("http" in t.name.lower() for t in http_tools)

class TestSimpleQAToolExecution:
    """Test tool execution in agent workflow (Tier 2: Integration)."""

    @pytest.mark.tier2
    def test_tool_execution_in_workflow(self, tmp_path):
        """
        Verify agent executes tools during workflow (real LLM).

        This test uses real Ollama LLM and real file system operations.
        Requires: Ollama running locally with llama2 model.
        """
        # Setup: Create test file for tool operations
        test_file = tmp_path / "test_data.txt"
        test_file.write_text("Machine learning is a subset of AI.")

        # Setup: Create tool registry

        # 12 builtin tools enabled via MCP

        # Create agent with tools
        agent = SimpleQAAgent(
            llm_provider="ollama",  # Real LLM (free, local)
            model="llama2",
            temperature=0.1,
            tools="all"  # Enable 12 builtin tools via MCP
        )

        # Execute workflow that requires file reading
        # Note: Real LLM may or may not decide to use tools
        # This test validates the integration, not LLM behavior
        result = agent.ask(
            f"Read the file at {test_file} and tell me what it says about AI"
        )

        # Verify: Result should be successful
        assert result is not None
        assert "answer" in result

        # Note: We cannot assert that tool was called (LLM decision)
        # but we verify the capability exists and doesn't error

    @pytest.mark.tier2
    def test_tool_execution_with_approval(self, tmp_path):
        """Verify tool approval workflow for dangerous operations."""
        from kaizen.core.autonomy.control import ControlProtocol
        from kaizen.core.autonomy.control.transports import MemoryTransport

        # Setup: Create control protocol for approval
        transport = MemoryTransport()
        protocol = ControlProtocol(transport)

        # Pre-approve all tool executions for test
        async def auto_approve(*args, **kwargs):
            return True

        protocol.request_approval = auto_approve

        # Setup: Create registry and agent

        # 12 builtin tools enabled via MCP

        test_file = tmp_path / "dangerous.txt"

        agent = SimpleQAAgent(
            llm_provider="ollama",
            model="llama2",
            tools="all"  # Enable 12 builtin tools via MCP
            control_protocol=protocol
        )

        # Execute workflow that might trigger dangerous tool
        result = agent.ask(
            f"Delete the file at {test_file} if it exists"
        )

        # Verify: Workflow completes without errors
        assert result is not None

class TestSimpleQABackwardCompatibility:
    """Test backward compatibility without tools (Tier 1: Unit)."""

    def test_agent_works_without_tool_registry(self):
        """Verify agent works without tool_registry parameter."""
        agent = SimpleQAAgent(
            llm_provider="mock",
            model="mock-model"
            # NO tool_registry parameter
        )

        # Verify: Agent initializes successfully
        assert agent is not None
        assert not agent.has_tool_support()

    def test_agent_ask_method_without_tools(self):
        """Verify agent's main method works without tool support."""
        agent = SimpleQAAgent(
            llm_provider="mock",
            model="mock-model"
        )

        # Execute main method
        result = agent.ask("What is machine learning?")

        # Verify: Result is successful (mocked LLM)
        assert result is not None
        assert "answer" in result

    def test_existing_tests_still_pass(self):
        """
        Verify existing SimpleQAAgent tests still pass.

        This validates 100% backward compatibility.
        Run existing test suite: pytest tests/unit/agents/test_simple_qa.py
        """
        # This is a meta-test - actual validation happens via existing tests
        # We just verify the agent can be constructed the old way
        agent = SimpleQAAgent(
            llm_provider="openai",
            model="gpt-4",
            temperature=0.7,
            max_tokens=300
        )

        assert agent is not None
        assert agent.config.llm_provider == "openai"
        assert agent.config.model == "gpt-4"
        assert agent.config.temperature == 0.7

# ============================================================================
# Tier 3 Tests (E2E with Real OpenAI) - OPTIONAL, HIGH-VALUE AGENTS ONLY
# ============================================================================

class TestSimpleQAToolIntegrationE2E:
    """
    End-to-end tool integration with real OpenAI (Tier 3).

    WARNING: These tests cost money (OpenAI API usage).
    Only run for high-value agents: ReActAgent, RAGResearchAgent, CodeGenerationAgent.

    Mark with: @pytest.mark.tier3
    Skip by default: pytest -m "not tier3"
    """

    @pytest.mark.tier3
    @pytest.mark.skip(reason="SimpleQAAgent not high-value for Tier 3")
    def test_real_tool_execution_openai(self, tmp_path):
        """
        Verify complete tool workflow with real OpenAI LLM.

        Cost: ~$0.01-0.03 per test
        """
        # Similar to Tier 2 test but with OpenAI
        test_file = tmp_path / "production_data.txt"
        test_file.write_text("Production data content")


        # 12 builtin tools enabled via MCP

        agent = SimpleQAAgent(
            llm_provider="openai",
            model="gpt-4",
            temperature=0.1,
            tools="all"  # Enable 12 builtin tools via MCP
        )

        result = agent.ask(
            f"Read {test_file} and summarize the content"
        )

        assert result is not None
        assert "answer" in result
```

## Test Templates by Agent Type

### For Iterative Agents (ReAct, ChainOfThought, RAG)

**Special Considerations**:
- Tool execution happens in MultiCycleStrategy loops
- Test convergence detection with `tool_calls` field
- Verify tool results feed back to next cycle

```python
class TestReActToolExecution:
    @pytest.mark.tier2
    def test_tool_execution_in_react_cycle(self, tmp_path):
        """Verify ReAct executes tools in reasoning cycles."""
        # Setup
        test_file = tmp_path / "data.txt"
        test_file.write_text("42")


        # 12 builtin tools enabled via MCP

        agent = ReActAgent(
            llm_provider="ollama",
            model="llama2",
            tools="all"  # Enable 12 builtin tools via MCP
        )

        # Execute task requiring tool use
        result = agent.solve_task(
            f"Read the number from {test_file} and multiply it by 2"
        )

        # Verify: Result exists and cycles completed
        assert result is not None
        assert "thought" in result
        assert "action" in result
        assert result.get("cycles_used", 0) > 0
```

### For Multi-Modal Agents (Vision, Transcription, MultiModal)

**Special Considerations**:
- Tools for file access (image files, audio files)
- Tools for preprocessing (format conversion, compression)
- Tools for post-processing (OCR, metadata extraction)

```python
class TestVisionAgentToolExecution:
    @pytest.mark.tier2
    def test_vision_agent_with_file_tools(self, tmp_path):
        """Verify VisionAgent uses file tools for image access."""
        # Setup: Copy image to temp location
        test_image = tmp_path / "test_image.png"
        # ... copy actual image file ...


        # 12 builtin tools enabled via MCP

        agent = VisionAgent(
            llm_provider="ollama",
            model="bakllava",
            tools="all"  # Enable 12 builtin tools via MCP
        )

        # Agent might use file_exists tool before processing
        result = agent.analyze(
            image=str(test_image),
            question="What is in this image?"
        )

        assert result is not None
        assert "answer" in result
```

### For Coordination Agents (Supervisor, Worker, Coordinator)

**Special Considerations**:
- Supervisor uses tools for task analysis
- Worker uses tools for task execution
- Coordinator uses tools for monitoring

```python
class TestSupervisorToolExecution:
    @pytest.mark.tier2
    def test_supervisor_uses_analysis_tools(self):
        """Verify SupervisorAgent uses tools for task decomposition."""

        # 12 builtin tools enabled via MCP

        supervisor = SupervisorAgent(
            llm_provider="ollama",
            model="llama2",
            tools="all"  # Enable 12 builtin tools via MCP
        )

        # Supervisor might use HTTP tools to check API health
        # before delegating API-related tasks
        result = supervisor.delegate_tasks(
            "Process user data from API endpoint"
        )

        assert result is not None
        assert "tasks" in result
```

## Test Execution

### Run All Tool Integration Tests

```bash
# All tool integration tests
pytest tests/unit/agents/test_*_tool_integration.py -v

# Tier 1 only (fast, mocked)
pytest tests/unit/agents/test_*_tool_integration.py -v -m "not tier2 and not tier3"

# Tier 2 integration (real Ollama, ~5-10s per test)
pytest tests/unit/agents/test_*_tool_integration.py -v -m tier2

# Tier 3 E2E (real OpenAI, costs money, skip by default)
pytest tests/unit/agents/test_*_tool_integration.py -v -m tier3
```

### Run Tests for Specific Agent

```bash
# All tests for SimpleQAAgent
pytest tests/unit/agents/test_simple_qa_tool_integration.py -v

# Only Tier 1 for SimpleQAAgent
pytest tests/unit/agents/test_simple_qa_tool_integration.py::TestSimpleQAToolDiscovery -v
```

### CI/CD Integration

**GitHub Actions Workflow**:

```yaml
name: Tool Integration Tests

on: [push, pull_request]

jobs:
  tier1-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -e .
      - run: pytest tests/unit/agents/test_*_tool_integration.py -m "not tier2 and not tier3"

  tier2-tests:
    runs-on: ubuntu-latest
    services:
      ollama:
        image: ollama/ollama:latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -e .
      - run: ollama pull llama2
      - run: pytest tests/unit/agents/test_*_tool_integration.py -m tier2

  tier3-tests:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'  # Only on main branch
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -e .
      - run: pytest tests/unit/agents/test_*_tool_integration.py -m tier3
    env:
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

## Test Coverage Requirements

**Per Agent**:
- ✅ Minimum 3 tests (discovery, execution, backward compatibility)
- ✅ At least 1 Tier 2 test (real LLM)
- ✅ 100% coverage for tool parameter passing

**Overall**:
- ✅ 75 tests total (25 agents × 3 tests)
- ✅ 25 Tier 2 tests (1 per agent)
- ✅ 3 Tier 3 tests (high-value agents only: ReAct, RAG, CodeGen)

**Code Coverage Target**: 100% for tool integration code paths

## Common Test Failures

### ❌ Tool Registry Not Initialized

```python
# WRONG: Forget to register builtin tools

# Missing: # 12 builtin tools enabled via MCP

agent = SimpleQAAgent(tools="all"  # Enable 12 builtin tools via MCP
tools = asyncio.run(agent.discover_tools())
assert len(tools) == 12  # FAILS: 0 tools registered
```

```python
# CORRECT: Register builtin tools

# 12 builtin tools enabled via MCP

agent = SimpleQAAgent(tools="all"  # Enable 12 builtin tools via MCP
tools = asyncio.run(agent.discover_tools())
assert len(tools) == 12  # PASSES
```

### ❌ Missing Async Execution

```python
# WRONG: Forget asyncio.run() for async methods
tools = agent.discover_tools()  # Returns coroutine, not list
assert len(tools) == 12  # FAILS: TypeError
```

```python
# CORRECT: Use asyncio.run() for async methods
tools = asyncio.run(agent.discover_tools())  # Returns list
assert len(tools) == 12  # PASSES
```

### ❌ Wrong Tier Marker

```python
# WRONG: Tier 2 test without marker
def test_tool_execution_in_workflow(self, tmp_path):
    # Uses real Ollama LLM but no marker
    agent = SimpleQAAgent(llm_provider="ollama", ...)
```

```python
# CORRECT: Add @pytest.mark.tier2
@pytest.mark.tier2
def test_tool_execution_in_workflow(self, tmp_path):
    # Uses real Ollama LLM with correct marker
    agent = SimpleQAAgent(llm_provider="ollama", ...)
```

## Test Organization

```
tests/
├── unit/
│   └── agents/
│       ├── test_simple_qa_tool_integration.py          # 3 tests
│       ├── test_react_tool_integration.py              # 3 tests
│       ├── test_chain_of_thought_tool_integration.py   # 3 tests
│       ├── test_rag_research_tool_integration.py       # 3 tests
│       ├── test_code_generation_tool_integration.py    # 3 tests
│       ├── test_memory_agent_tool_integration.py       # 3 tests
│       # ... 19 more agents ...
│       └── test_sequential_pipeline_tool_integration.py # 3 tests
├── integration/
│   └── test_tool_integration_e2e.py  # Cross-agent tool workflows
└── conftest.py  # Shared fixtures (tmp_path, registries, etc.)
```

## Validation Checklist

Before merging tool integration tests:

- [ ] Created test file: `tests/unit/agents/test_{agent_name}_tool_integration.py`
- [ ] Implemented 3 test classes: Discovery, Execution, BackwardCompatibility
- [ ] Test 1: Tool discovery with registry (Tier 1)
- [ ] Test 2: Tool execution in workflow (Tier 2, real LLM)
- [ ] Test 3: Backward compatibility without tools (Tier 1)
- [ ] Added `@pytest.mark.tier2` to integration tests
- [ ] Verified tests pass: `pytest tests/unit/agents/test_{agent_name}_tool_integration.py -v`
- [ ] Verified Tier 1 pass: `pytest ... -m "not tier2 and not tier3"`
- [ ] Verified Tier 2 pass: `pytest ... -m tier2` (requires Ollama)
- [ ] No test mocking for Tier 2 (real LLM, real tools, real file system)
- [ ] Tests follow naming convention: `test_{feature}_{scenario}`
- [ ] Docstrings explain what each test validates

## References

- **ADR-016**: Universal Tool Integration for All 25 Agents
- **ADR-012**: BaseAgent Tool Integration
- **ADR-005**: Testing Strategy Alignment (3-tier approach)
- **Examples**: `examples/autonomy/tools/` for usage patterns
