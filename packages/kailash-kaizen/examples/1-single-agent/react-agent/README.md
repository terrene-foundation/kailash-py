# ReAct Agent with MCP Tool Integration

## Overview
Demonstrates the ReAct (Reasoning and Acting) pattern with MCP (Model Context Protocol) tool integration. This agent can reason about problems, decide which tools to use, execute actions, and reflect on results in an iterative cycle.

## Use Case
- Complex problem-solving requiring multiple steps
- Research tasks needing external data sources
- Automated workflows with decision-making
- Interactive debugging and analysis

## Agent Specification

### Core Functionality
- **Input**: Complex queries requiring multi-step reasoning
- **Processing**: ReAct loop with tool selection and execution
- **Output**: Comprehensive solutions with reasoning traces
- **Memory**: Short-term working memory for reasoning steps

### ReAct Pattern Implementation
```python
class ReActSignature(dspy.Signature):
    """Reason about problems and act using available tools."""
    query: str = dspy.InputField(desc="Complex query requiring reasoning and action")
    available_tools: list = dspy.InputField(desc="List of available MCP tools")
    previous_actions: str = dspy.InputField(desc="Previous actions taken", default="")

    thought: str = dspy.OutputField(desc="Current reasoning about the problem")
    action: str = dspy.OutputField(desc="Tool to use: 'tool_name' or 'finish'")
    action_input: str = dspy.OutputField(desc="Input parameters for the tool")
    observation: str = dspy.OutputField(desc="Result of the action")
    final_answer: str = dspy.OutputField(desc="Final answer when action is 'finish'")
```

### MCP Tool Configuration
```yaml
mcp_servers:
  web_search:
    endpoint: "http://localhost:8000/mcp/web"
    capabilities: ["search", "summarize"]

  database:
    endpoint: "http://localhost:8001/mcp/db"
    capabilities: ["query", "schema"]

  file_system:
    endpoint: "http://localhost:8002/mcp/fs"
    capabilities: ["read", "write", "list"]
```

## Expected Execution Flow

### Phase 1: Initialization (0-100ms)
```
[00:00:000] ReAct Agent initialized with MCP tool discovery
[00:00:025] MCP server connections established:
             - web_search: ✅ (3 tools available)
             - database: ✅ (5 tools available)
             - file_system: ✅ (4 tools available)
[00:00:050] Tool registry populated with 12 available tools
[00:00:075] ReAct workflow built and validated
[00:00:095] Agent ready for reasoning loops
```

### Phase 2: Initial Reasoning (100-800ms)
```
[00:00:100] Query received: "Find the latest stock price for AAPL and compare it to its 52-week high"
[00:00:120] ReAct Cycle 1 - Reasoning Phase:
[00:00:150] THOUGHT: "I need to find current AAPL stock price and its 52-week high.
                      I should use web search to get real-time financial data."
[00:00:200] ACTION: "web_search"
[00:00:210] ACTION_INPUT: "AAPL current stock price real-time"
[00:00:250] Tool execution initiated: web_search.search()
[00:00:750] OBSERVATION: "AAPL trading at $174.50 (as of market close)"
```

### Phase 3: Iterative Action Loop (800-3200ms)
```
[00:00:800] ReAct Cycle 2 - Additional Information Phase:
[00:00:820] THOUGHT: "I have current price ($174.50) but need 52-week high.
                      Let me search for AAPL's 52-week trading range."
[00:00:850] ACTION: "web_search"
[00:00:860] ACTION_INPUT: "AAPL 52-week high low trading range 2024"
[00:00:900] Tool execution: web_search.search()
[00:01:400] OBSERVATION: "AAPL 52-week range: $164.08 - $199.62"

[00:01:450] ReAct Cycle 3 - Analysis Phase:
[00:01:470] THOUGHT: "Now I have both pieces: current price $174.50 and
                      52-week high $199.62. I can calculate the comparison."
[00:01:500] ACTION: "finish"
[00:01:510] FINAL_ANSWER: "AAPL is currently trading at $174.50, which is
                           $25.12 (12.6%) below its 52-week high of $199.62."
[00:01:530] ReAct loop completed successfully
```

### Phase 4: Response Assembly (3200-3300ms)
```
[00:03:200] Reasoning trace compiled:
             - 3 ReAct cycles executed
             - 2 tool invocations successful
             - 1 final answer generated
[00:03:250] Response structure validated
[00:03:280] Execution metrics calculated
[00:03:295] Complete reasoning trace prepared for return
```

## Technical Requirements

### Dependencies
```python
# Core Kailash SDK
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.llm_agent import LLMAgentNode
from kailash.integrations.mcp import MCPClient

# ReAct implementation
import dspy
from typing import List, Dict, Any, Optional
import asyncio
import json
```

### MCP Integration Requirements
```python
mcp_config = {
    "servers": [
        {
            "name": "web_search",
            "endpoint": "http://localhost:8000/mcp",
            "tools": ["search", "summarize", "get_content"]
        },
        {
            "name": "database",
            "endpoint": "http://localhost:8001/mcp",
            "tools": ["query", "schema", "insert", "update", "delete"]
        },
        {
            "name": "file_system",
            "endpoint": "http://localhost:8002/mcp",
            "tools": ["read_file", "write_file", "list_dir", "file_info"]
        }
    ],
    "timeout": 30,
    "retry_attempts": 3,
    "concurrent_tool_limit": 5
}
```

## Success Criteria

### Functional Requirements
- ✅ Completes multi-step reasoning problems in <10 cycles
- ✅ Successfully integrates with 3+ MCP servers
- ✅ Handles tool failures gracefully with retry logic
- ✅ Maintains coherent reasoning trace throughout execution

### ReAct Loop Requirements
- ✅ Clear separation between reasoning and action phases
- ✅ Appropriate tool selection based on problem context
- ✅ Effective use of observations to guide next actions
- ✅ Knows when to stop and provide final answer

### Tool Integration Requirements
- ✅ Dynamic tool discovery from MCP servers
- ✅ Proper parameter passing to tool functions
- ✅ Error handling for tool timeouts and failures
- ✅ Concurrent tool execution where applicable

## Enterprise Considerations

### MCP Server Management
- Service discovery and health monitoring
- Load balancing across multiple tool instances
- Authentication and authorization for tool access
- Resource quotas and rate limiting per tenant

### Security
- Input sanitization for tool parameters
- Output validation from external tools
- Sandboxed execution environment for tools
- Audit logging for all tool interactions

### Monitoring
- ReAct loop performance metrics
- Tool usage patterns and success rates
- Reasoning quality assessment
- Cost tracking for external API calls

## Error Scenarios

### Tool Unavailability
```python
# Expected behavior when MCP server is down
{
  "thought": "Web search tool is unavailable. I'll use my knowledge to provide best answer.",
  "action": "finish",
  "final_answer": "I cannot access real-time data currently. AAPL typically trades between $160-200.",
  "error_context": "web_search tool unavailable",
  "confidence": 0.3
}
```

### Infinite Loop Detection
```python
# Response when agent gets stuck in reasoning loop
{
  "thought": "I've been unable to make progress after 10 cycles.",
  "action": "finish",
  "final_answer": "I encountered difficulty solving this problem with available tools.",
  "loop_detection": "Max cycles reached (10/10)",
  "partial_results": ["current_price_search_attempted", "range_data_incomplete"]
}
```

### Tool Parameter Errors
```python
# Handling malformed tool inputs
{
  "thought": "My previous tool call failed due to invalid parameters. Let me reformulate.",
  "action": "web_search",
  "action_input": "AAPL stock price",  # Simplified input
  "previous_error": "Invalid JSON in action_input",
  "retry_attempt": 2
}
```

## ReAct Pattern Variations

### Standard ReAct Loop
```
Thought → Action → Observation → Thought → Action → ... → Final Answer
```

### Parallel ReAct (Multiple Tools)
```
Thought → [Action1, Action2] → [Obs1, Obs2] → Synthesis → Final Answer
```

### Hierarchical ReAct (Sub-problems)
```
Thought → Sub-problem1 [ReAct Loop] → Sub-problem2 [ReAct Loop] → Synthesis
```

### Self-Correcting ReAct
```
Thought → Action → Observation → Validation → [Retry if invalid] → Final Answer
```
