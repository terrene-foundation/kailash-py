# MCP Integration Tests with Real LLM Providers

## Overview

These integration tests validate that **real LLM providers** (OpenAI and Ollama) can successfully interact with the MCP (Model Context Protocol) infrastructure. Unlike unit tests that use mock providers, these tests verify:

1. **Real LLM Capabilities**:
   - Can the LLM parse MCP tool schemas?
   - Can the LLM generate proper tool arguments from natural language?
   - Can the LLM process tool invocation results?
   - Does the end-to-end MCP workflow actually work?

2. **Real MCP Protocol**:
   - NO MOCKING at the MCP protocol level
   - Uses real `MCPConnection`, `MCPRegistry`, `MCPServerConfig`
   - Uses real JSON-RPC 2.0 communication
   - Tests actual server lifecycle and tool discovery

3. **Production Readiness**:
   - Validates enterprise-ready MCP integration
   - Tests error handling with real providers
   - Measures real performance metrics
   - Verifies memory integration

## Test Files

### 1. `test_mcp_agent_as_client_real_llm.py`

**Purpose**: Tests agents consuming external MCP tools using real LLM providers.

**Test Coverage** (12 tests):

#### OpenAI Tests (gpt-4o-mini)
- ✅ Task analysis with real LLM
- ✅ MCP tool schema parsing
- ✅ Argument generation from natural language
- ✅ End-to-end MCP workflow
- ✅ Memory integration
- ✅ Invalid tool request error handling
- ✅ Connection failure handling
- ✅ Task analysis latency
- ✅ Multiple LLM calls throughput

#### Ollama Tests (llama3.1:8b-instruct-q8_0)
- ✅ Task analysis with Ollama
- ✅ Tool invocation with Ollama

#### Comparative Tests
- ✅ Provider consistency validation

### 2. `test_mcp_agent_as_server_real_llm.py`

**Purpose**: Tests agents exposing themselves as MCP servers using real LLM providers.

**Test Coverage** (14 tests):

#### OpenAI Tests (gpt-4o-mini)
- ✅ Question answering tool
- ✅ Text analysis tool
- ✅ Tool discovery
- ✅ JSON-RPC error handling
- ✅ Server lifecycle (start/stop)
- ✅ Memory integration
- ✅ Concurrent requests
- ✅ Invalid arguments handling
- ✅ Server not running error
- ✅ Question latency
- ✅ Throughput multiple questions

#### Ollama Tests (llama3.1:8b-instruct-q8_0)
- ✅ Question answering tool
- ✅ Text analysis tool

#### Comparative Tests
- ✅ Provider consistency for Q&A

## Environment Setup

### OpenAI Tests

**Required Environment Variable**:
```bash
export OPENAI_API_KEY="sk-..."
```

**Supported Models**:
- `gpt-4o-mini` (default for tests - better availability)
- `gpt-5-nano` (if available)
- `gpt-4` (for advanced tests)

**Notes**:
- Tests use low temperature (0.1) for deterministic behavior
- Tests use short max_tokens (500) to minimize cost
- Tests skip automatically if `OPENAI_API_KEY` is not set

### Ollama Tests

**Required Setup**:
1. Install Ollama: `https://ollama.ai/`
2. Pull model: `ollama pull llama3.1:8b-instruct-q8_0`
3. Start Ollama: `ollama serve` (runs on http://localhost:11434)

**Supported Models**:
- `llama3.1:8b-instruct-q8_0` (default - fast and small)
- Any other Ollama model (configure in test)

**Notes**:
- Tests skip automatically if Ollama is not available
- Tests verify Ollama availability before running
- Completely free and runs locally

## Running the Tests

### Run All MCP Real LLM Tests

```bash
# Run all OpenAI and Ollama tests
pytest tests/integration/test_mcp_agent_as_client_real_llm.py -v
pytest tests/integration/test_mcp_agent_as_server_real_llm.py -v
```

### Run Specific Provider Tests

```bash
# OpenAI tests only
pytest tests/integration/test_mcp_agent_as_client_real_llm.py::TestMCPClientAgentRealOpenAI -v

# Ollama tests only
pytest tests/integration/test_mcp_agent_as_client_real_llm.py::TestMCPClientAgentRealOllama -v
```

### Run Specific Test Cases

```bash
# Test OpenAI task analysis
pytest tests/integration/test_mcp_agent_as_client_real_llm.py::TestMCPClientAgentRealOpenAI::test_openai_task_analysis_with_real_llm -v

# Test server lifecycle
pytest tests/integration/test_mcp_agent_as_server_real_llm.py::TestMCPServerAgentRealOpenAI::test_openai_server_lifecycle -v
```

### Run with Pytest Markers

```bash
# Run all tests requiring LLM
pytest -m requires_llm -v

# Run all MCP tests
pytest -m mcp -v

# Run performance tests
pytest -m performance -v

# Run Ollama-specific tests
pytest -m requires_ollama -v
```

## Test Behavior

### When OpenAI API Key is Available

```bash
$ export OPENAI_API_KEY="sk-..."
$ pytest tests/integration/test_mcp_agent_as_client_real_llm.py::TestMCPClientAgentRealOpenAI -v

PASSED test_openai_task_analysis_with_real_llm
PASSED test_openai_tool_schema_parsing
PASSED test_openai_argument_generation_from_natural_language
...
```

**Expected**: Tests execute with real OpenAI API calls

### When OpenAI API Key is NOT Available

```bash
$ pytest tests/integration/test_mcp_agent_as_client_real_llm.py::TestMCPClientAgentRealOpenAI -v

SKIPPED [OPENAI_API_KEY not set in environment]
SKIPPED [OPENAI_API_KEY not set in environment]
...
```

**Expected**: Tests skip gracefully (no failures)

### When Ollama is Running

```bash
$ ollama serve  # In separate terminal
$ pytest tests/integration/test_mcp_agent_as_client_real_llm.py::TestMCPClientAgentRealOllama -v

PASSED test_ollama_task_analysis_with_real_llm
PASSED test_ollama_tool_invocation
```

**Expected**: Tests execute with real Ollama calls

### When Ollama is NOT Running

```bash
$ pytest tests/integration/test_mcp_agent_as_client_real_llm.py::TestMCPClientAgentRealOllama -v

SKIPPED [Ollama not available at http://localhost:11434]
SKIPPED [Ollama not available at http://localhost:11434]
```

**Expected**: Tests skip gracefully (no failures)

## Test Architecture

### 3-Tier Testing Strategy

These tests are **Tier 2 (Integration)** tests following the NO MOCKING policy:

- **Tier 1 (Unit)**: Agent logic with mock providers (fast, < 1s)
  - Located in: `tests/unit/examples/test_agent_as_client.py`
  - Uses: `llm_provider="mock"`

- **Tier 2 (Integration)**: Real MCP + Real LLM providers (moderate, ~5-10s)
  - Located in: `tests/integration/test_mcp_agent_as_*_real_llm.py` ← **THESE TESTS**
  - Uses: `llm_provider="openai"` or `llm_provider="ollama"`
  - NO MOCKING of MCP protocol

- **Tier 3 (E2E)**: Complete workflows with real infrastructure (slow, > 30s)
  - Would include: Real MCP servers, real databases, real message queues

### Real Infrastructure Used

✅ **Real MCP Components**:
- `MCPConnection` - Real JSON-RPC 2.0 client
- `MCPRegistry` - Real service registry
- `MCPServerConfig` - Real server configuration
- `AutoDiscovery` - Real service discovery

✅ **Real LLM Providers**:
- `RealOpenAIProvider` - Direct OpenAI API calls
- `RealOllamaProvider` - Direct Ollama API calls

✅ **Real Memory**:
- `SharedMemoryPool` - Real shared memory writes/reads

## What These Tests Validate

### 1. LLM Can Parse MCP Tool Schemas

**Test**: `test_openai_tool_schema_parsing`

**Validates**:
- LLM receives tool schema in JSON format
- LLM understands parameter requirements
- LLM generates valid tool invocation request
- Result: LLM successfully prepares tool call

**Evidence of Real LLM Use**: Test fails if LLM can't parse schema

---

### 2. LLM Can Generate Arguments from Natural Language

**Test**: `test_openai_argument_generation_from_natural_language`

**Validates**:
- User provides natural language request: "Calculate sum of 42 and 17"
- LLM identifies appropriate tool: "calculate"
- LLM generates proper arguments: `{"a": 42, "b": 17}`
- Result: Tool receives correctly formatted arguments

**Evidence of Real LLM Use**: Mock provider can't translate natural language to arguments

---

### 3. LLM Can Process Tool Results

**Test**: `test_openai_end_to_end_mcp_workflow`

**Validates**:
- LLM analyzes task
- LLM invokes appropriate tool via MCP
- LLM receives tool result
- LLM synthesizes final answer incorporating result
- Result: Coherent final answer based on tool output

**Evidence of Real LLM Use**: Complete reasoning chain requires real LLM

---

### 4. JSON-RPC 2.0 Works with Real LLM

**Test**: `test_openai_question_answering_tool`

**Validates**:
- Server receives JSON-RPC 2.0 request
- LLM processes request content
- LLM generates response
- Server returns JSON-RPC 2.0 compliant response
- Result: Valid JSON-RPC structure with LLM-generated content

**Evidence of Real LLM Use**: Response content is contextually relevant

---

### 5. Real Performance Metrics

**Test**: `test_openai_task_analysis_latency`

**Validates**:
- Actual API call latency to OpenAI
- Real network overhead
- Real LLM processing time
- Result: Performance baseline for production

**Evidence of Real LLM Use**: Actual timing data (not instant mocks)

## Performance Expectations

### Agent-as-Client (with OpenAI gpt-4o-mini)

- Task analysis: **< 10 seconds**
- Tool schema parsing: **< 5 seconds**
- Tool invocation: **< 10 seconds**
- End-to-end workflow: **< 15 seconds**

### Agent-as-Server (with OpenAI gpt-4o-mini)

- Question answering: **< 10 seconds**
- Text analysis: **< 10 seconds**
- Server lifecycle: **< 2 seconds** (startup/shutdown)
- Concurrent requests: **< 30 seconds** (3 requests)

### With Ollama (llama3.1:8b-instruct-q8_0, local)

- Generally **faster** than OpenAI (no network latency)
- Task analysis: **< 5 seconds**
- Question answering: **< 5 seconds**
- **Completely free** (runs locally)

## Cost Considerations

### OpenAI Costs (Approximate)

Using `gpt-4o-mini` with 500 max_tokens per test:

- **Per test**: ~$0.0001 - $0.0005 (very cheap)
- **Full test suite** (26 tests): ~$0.003 - $0.013
- **100 test runs**: ~$0.30 - $1.30

Tests are designed to minimize costs:
- Use smallest suitable model (gpt-4o-mini)
- Use low max_tokens (500)
- Skip tests if key not available
- Cache results where possible

### Ollama Costs

- **Completely FREE** (runs locally)
- No API costs
- No rate limits
- Instant availability

## Troubleshooting

### Tests Skip with "OPENAI_API_KEY not set"

**Solution**: Set environment variable
```bash
export OPENAI_API_KEY="sk-..."
```

### Tests Skip with "Ollama not available"

**Solution**: Start Ollama
```bash
ollama serve
```

In separate terminal:
```bash
ollama pull llama3.1:8b-instruct-q8_0
```

### Tests Fail with "Connection refused"

**Issue**: MCP test server not available

**Solution**: Tests are designed to skip if servers unavailable, but check:
```python
# In test code - should skip gracefully
if len(agent.connections) == 0:
    pytest.skip("No MCP connections available")
```

### Tests Fail with "Rate limit exceeded"

**Issue**: OpenAI rate limit hit

**Solutions**:
1. Wait and retry
2. Use Ollama instead (no rate limits)
3. Run fewer tests in parallel

### Tests Fail with "Invalid API key"

**Issue**: Wrong or expired OpenAI key

**Solution**: Update environment variable
```bash
export OPENAI_API_KEY="sk-your-valid-key"
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: MCP Real LLM Tests

on: [push, pull_request]

jobs:
  test-openai:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.12
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run OpenAI MCP tests
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          pytest tests/integration/test_mcp_agent_as_client_real_llm.py::TestMCPClientAgentRealOpenAI -v
          pytest tests/integration/test_mcp_agent_as_server_real_llm.py::TestMCPServerAgentRealOpenAI -v

  test-ollama:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Install Ollama
        run: |
          curl https://ollama.ai/install.sh | sh
          ollama serve &
          ollama pull llama3.1:8b-instruct-q8_0
      - name: Run Ollama MCP tests
        run: |
          pytest tests/integration/test_mcp_agent_as_client_real_llm.py::TestMCPClientAgentRealOllama -v
          pytest tests/integration/test_mcp_agent_as_server_real_llm.py::TestMCPServerAgentRealOllama -v
```

## Summary

These integration tests provide **critical validation** that the MCP integration examples work with **real LLM providers**, not just mocks. They answer the user's question:

> "How would you know if the LLM can actually use the MCP tools/resources/prompts if you are using mock provider?"

**Answer**: By running these tests with `OPENAI_API_KEY` or Ollama available, which:
1. Make real API calls to LLM providers
2. Use real MCP protocol (no mocking)
3. Validate actual tool schema parsing
4. Verify real argument generation
5. Test actual workflow execution
6. Measure real performance

**Test Files**:
- `tests/integration/test_mcp_agent_as_client_real_llm.py` (12 tests)
- `tests/integration/test_mcp_agent_as_server_real_llm.py` (14 tests)

**Total Coverage**: 26 integration tests with real LLM providers

**Status**: ✅ All tests properly structured and ready to run
