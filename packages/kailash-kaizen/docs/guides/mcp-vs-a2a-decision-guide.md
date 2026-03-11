# MCP vs A2A Decision Guide

**Author**: Kaizen Framework Team
**Date**: 2025-10-22
**Purpose**: Define when to use MCP (Model Context Protocol) vs A2A (Agent-to-Agent) protocol

---

## Executive Summary

**Critical Distinction**:
- **MCP**: AI model ↔ External tools/services (client-server)
- **A2A**: AI agent ↔ AI agent (peer-to-peer)

**Key Insight**: MCP is for **tool calling**. A2A is for **agent collaboration**. These are fundamentally different communication patterns.

---

## Protocol Overview

### MCP (Model Context Protocol)

**What**: Anthropic's standard for exposing tools, resources, and prompts to AI models

**Architecture**:
```
┌─────────────┐         MCP          ┌─────────────┐
│             │  ─────────────────►  │             │
│  AI Model   │   Tool Calls         │ MCP Server  │
│  (Claude)   │  ◄─────────────────  │  (Tools)    │
│             │   Tool Results       │             │
└─────────────┘                      └─────────────┘
```

**Characteristics**:
- **Client-Server Model**: Model requests, server responds
- **Tool-Based**: Functions with parameters and return values
- **One-Way Execution**: Model calls tool, tool executes, returns result
- **No Autonomy**: Tools are passive, called by model
- **JSON-RPC Protocol**: Standardized request/response format

**Standard**: Anthropic MCP specification

### A2A (Agent-to-Agent Protocol)

**What**: Google's standard for agent capability discovery and collaboration

**Architecture**:
```
┌─────────────┐         A2A          ┌─────────────┐
│             │  ─────────────────►  │             │
│  Agent A    │   Capability Card    │  Agent B    │
│  (Peer)     │  ◄─────────────────  │  (Peer)     │
│             │   Task Delegation    │             │
└─────────────┘                      └─────────────┘
```

**Characteristics**:
- **Peer-to-Peer**: Agents are equals, collaborate
- **Capability-Based**: Agents advertise what they can do
- **Two-Way Communication**: Bidirectional message passing
- **Autonomous**: Agents decide how to handle tasks
- **Semantic Matching**: Best agent selected for task

**Standard**: Google Agent-to-Agent protocol specification

---

## When to Use MCP

### ✅ Use MCP For:

1. **Exposing Agent as Tool to External AI Models**
   ```python
   # Kaizen agent exposed via MCP to Claude Code
   from kaizen.integrations.mcp import expose_agent_as_mcp_server

   agent = RAGResearchAgent(config)
   server = expose_agent_as_mcp_server(
       agent=agent,
       tool_name="research_assistant",
       description="Research agent for comprehensive topic analysis"
   )

   # Now Claude Code can call: research_assistant(topic="...")
   ```

2. **Agent Consuming External Tools/Services**
   ```python
   # Kaizen agent uses MCP to call external tools
   from kaizen.core.base_agent import BaseAgent
   # Tools auto-configured via MCP


   registry.register_mcp_server({
       "name": "github",
       "command": "npx",
       "args": ["-y", "@modelcontextprotocol/server-github"]
   })

   agent = BaseAgent(
       config=config,
       tools="all"  # Enable 12 builtin tools via MCP
   )
   ```

3. **Tool-Like Behavior**
   - Single function execution
   - Deterministic input/output
   - No multi-agent coordination needed
   - Stateless execution

4. **Integration with Non-Kaizen Systems**
   - Claude Desktop
   - Continue IDE
   - Other MCP clients
   - Generic AI assistants

### ❌ Don't Use MCP For:

- ❌ Multi-agent coordination (use A2A)
- ❌ Agent-to-agent delegation (use A2A)
- ❌ Complex workflows requiring multiple agents (use A2A)
- ❌ Semantic capability matching (use A2A)

---

## When to Use A2A

### ✅ Use A2A For:

1. **Multi-Agent Coordination**
   ```python
   # Supervisor coordinating workers via A2A
   from kaizen.agents.coordination import SupervisorWorkerPattern

   supervisor = SupervisorAgent(config)
   workers = [
       CodeExpertAgent(config),
       DataExpertAgent(config),
       WritingExpertAgent(config)
   ]

   # A2A semantic matching
   pattern = SupervisorWorkerPattern(supervisor, workers)
   result = pattern.execute_task("Analyze sales data and create report")
   # A2A: Supervisor → capability cards → selects DataExpert
   ```

2. **Semantic Capability Discovery**
   ```python
   # Agent discovers best peer via A2A capability cards
   best_agent = supervisor.select_worker_for_task(
       task="Generate Python code for data processing",
       available_workers=workers,
       return_score=True
   )
   # Returns: {"worker": CodeExpertAgent, "score": 0.95}
   # A2A capability matching: task semantics → agent capabilities
   ```

3. **Agent Delegation Patterns**
   ```python
   # Debate pattern: agents collaborate via A2A
   from kaizen.agents.coordination import DebatePattern

   pattern = DebatePattern(
       leader=debate_leader,
       participants=[agent1, agent2, agent3],
       judge=debate_judge
   )

   # A2A: Leader orchestrates, participants exchange arguments
   consensus = pattern.reach_consensus("Best architecture for microservices")
   ```

4. **Peer-to-Peer Communication**
   - Agents are equals (no client-server hierarchy)
   - Bidirectional message passing
   - Collaborative problem solving
   - Distributed reasoning

5. **Complex Multi-Agent Workflows**
   ```python
   # Consensus pattern: iterative voting via A2A
   from kaizen.agents.coordination import ConsensusPattern

   pattern = ConsensusPattern(
       leader=consensus_leader,
       voters=[voter1, voter2, voter3],
       tally=consensus_tally
   )

   # A2A: Iterative rounds until agreement
   decision = pattern.vote_until_consensus("Which database to use?")
   ```

### ❌ Don't Use A2A For:

- ❌ Calling external tools (use MCP)
- ❌ Exposing agent to non-agent systems (use MCP)
- ❌ Simple function calls (use MCP)
- ❌ Integration with Claude Desktop (use MCP)

---

## Comparison Matrix

| Dimension | MCP | A2A |
|-----------|-----|-----|
| **Relationship** | Client → Server | Peer ↔ Peer |
| **Direction** | One-way (call→result) | Two-way (bidirectional) |
| **Discovery** | Tool registry | Capability cards |
| **Selection** | Manual/LLM chooses tool name | Semantic matching (automatic) |
| **Autonomy** | Tool is passive | Agent is autonomous |
| **State** | Stateless | Stateful (agents maintain context) |
| **Protocol** | JSON-RPC | Capability-based messaging |
| **Use Case** | Tool calling | Agent collaboration |
| **Standard** | Anthropic MCP | Google A2A |
| **Examples** | file_read, http_get, bash_command | SupervisorWorker, Debate, Consensus |

---

## Hybrid Usage Patterns

### Pattern 1: Agent Uses Both

**Scenario**: Agent coordinates with peers (A2A) AND calls tools (MCP)

```python
class HybridAgent(BaseAgent):
    """Agent using both MCP (for tools) and A2A (for peers)."""

    def __init__(self, config):
        # MCP: Tool registry for external tools
        self.tool_
        self.tool_registry.register_mcp_server(github_server)

        super().__init__(
            config=config,
            tools="all"  # Enable tools via MCP
        )

        # A2A: Capability card for peer discovery
        self.a2a_card = self.to_a2a_card()

    async def collaborate(self, peers: List[BaseAgent], task: str):
        """Collaborate with peers via A2A."""
        # A2A: Semantic matching
        best_peer = self._select_best_peer(task, peers)

        # A2A: Delegate task
        peer_result = await best_peer.handle_task(task)

        # MCP: Use tools to process result
        tool_result = await self.execute_tool(
            "write_file",
            {"path": "output.txt", "content": peer_result}
        )

        return tool_result
```

**Key**: MCP for tool interaction, A2A for agent collaboration

### Pattern 2: Agent Exposed via MCP, Coordinates via A2A

**Scenario**: Agent is MCP server for external systems, uses A2A internally

```python
# Internal: Agent coordinates workers via A2A
supervisor = SupervisorAgent(config)
workers = [agent1, agent2, agent3]
pattern = SupervisorWorkerPattern(supervisor, workers)

# External: Expose supervisor via MCP
from kaizen.integrations.mcp import MCPServer

server = MCPServer()
server.register_tool(
    name="delegate_task",
    description="Delegate task to specialized agents",
    handler=lambda task: pattern.execute_task(task)
)

# Claude Code calls: delegate_task(task="...")
# Internally: Supervisor uses A2A to coordinate workers
```

**Key**: MCP is external interface, A2A is internal coordination

### Pattern 3: Autonomous Agent with MCP Tools

**Scenario**: Autonomous agent (MultiCycleStrategy) calling MCP tools

```python
from kaizen.strategies.multi_cycle import MultiCycleStrategy

class AutonomousMCPAgent(BaseAgent):
    """Autonomous agent calling MCP tools in loops."""

    def __init__(self, config):
        strategy = MultiCycleStrategy(
            max_cycles=10,
            convergence_check=self._check_convergence
        )

        super().__init__(
            config=config,
            strategy=strategy,  # Autonomous execution
            tools="all"  # Enable tools via MCP
        )

    def _check_convergence(self, result: Dict[str, Any]) -> bool:
        """Stop when no more tools needed."""
        tool_calls = result.get("tool_calls", [])
        return len(tool_calls) == 0

    async def solve(self, task: str):
        """
        Autonomous loop calling MCP tools.

        Cycle 1: Reason → call read_file (MCP)
        Cycle 2: Observe result → call write_file (MCP)
        Cycle 3: Verify → no tools → converged
        """
        return await self.run(task=task)
```

**Key**: Autonomous execution pattern, MCP for tool calls

---

## Architecture Decision Tree

```
┌─────────────────────────────────────┐
│  Do you need to call external       │
│  tools/services?                    │
└─────────────────────────────────────┘
         │
         ├─ YES ──► Use MCP
         │          - Register MCP servers
         │          - Call tools via tool_registry
         │
         └─ NO
              │
              ▼
         ┌─────────────────────────────────────┐
         │  Do you need to coordinate with     │
         │  other agents?                      │
         └─────────────────────────────────────┘
                  │
                  ├─ YES ──► Use A2A
                  │          - Create capability cards
                  │          - Semantic matching
                  │          - Peer-to-peer delegation
                  │
                  └─ NO ──► Single agent, no protocol needed
```

---

## Implementation Guidelines

### MCP Implementation

**1. Agent as MCP Server**

```python
# Expose agent as MCP tool
from kaizen.integrations.mcp import KaizenMCPServer

agent = RAGResearchAgent(config)

server = KaizenMCPServer()
server.register_agent_as_tool(
    agent=agent,
    tool_name="research",
    description="Research topics comprehensively",
    parameters={
        "topic": {"type": "string", "description": "Research topic"},
        "depth": {"type": "string", "enum": ["shallow", "deep"]}
    }
)

# Start MCP server
await server.start(transport="stdio")
```

**2. Agent Consuming MCP Tools**

```python
# Agent uses MCP tools
# Tools auto-configured via MCP

# Register MCP server
registry.register_mcp_server({
    "name": "github",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"],
    "env": {"GITHUB_TOKEN": os.getenv("GITHUB_TOKEN")}
})

# Agent with MCP tools
agent = BaseAgent(
    config=config,
    tools="all"  # Enable 12 builtin tools via MCP
)

# Call MCP tool
result = await agent.execute_tool(
    "github_create_issue",
    {"repo": "kaizen", "title": "Bug", "body": "..."}
)
```

### A2A Implementation

**1. Agent Capability Card**

```python
# Generate A2A capability card
class MyAgent(BaseAgent):
    def to_a2a_card(self) -> Dict[str, Any]:
        """Generate Google A2A capability card."""
        return {
            "agent_id": self.agent_id,
            "name": "MyAgent",
            "description": "Specialized agent for data analysis",
            "capabilities": [
                {
                    "name": "analyze_data",
                    "description": "Analyze datasets and generate insights",
                    "input_schema": {...},
                    "output_schema": {...}
                }
            ],
            "protocols": ["A2A/1.0"],
            "metadata": {
                "version": "1.0.0",
                "specialization": "data_analysis"
            }
        }
```

**2. Multi-Agent Coordination**

```python
# Supervisor-Worker with A2A
from kaizen.agents.coordination import SupervisorWorkerPattern

supervisor = SupervisorAgent(config)
workers = [
    DataAgent(config),
    CodeAgent(config),
    WritingAgent(config)
]

pattern = SupervisorWorkerPattern(supervisor, workers)

# A2A semantic matching
result = pattern.execute_task(
    "Analyze sales.csv and create visualization"
)

# Behind the scenes:
# 1. Supervisor gets task
# 2. Requests capability cards from workers (A2A)
# 3. Semantic matching: sales.csv → data analysis → DataAgent
# 4. Delegates to DataAgent (A2A)
# 5. DataAgent executes and returns
```

---

## Common Mistakes

### ❌ Mistake 1: Using MCP for Agent Coordination

```python
# WRONG: MCP is not for agent-to-agent coordination

registry.register_tool("call_data_agent", handler=data_agent.run)
registry.register_tool("call_code_agent", handler=code_agent.run)

supervisor.execute_tool("call_data_agent", {"task": "analyze"})
```

**Why Wrong**: Agents are peers, not tools. Use A2A for coordination.

**Correct**:
```python
pattern = SupervisorWorkerPattern(supervisor, [data_agent, code_agent])
result = pattern.execute_task("analyze data")  # A2A coordination
```

### ❌ Mistake 2: Using A2A for External Tools

```python
# WRONG: A2A is not for calling external services
github_agent = GitHubAgent(config)  # Wrapping GitHub API as agent
pattern = SupervisorWorkerPattern(supervisor, [github_agent])
```

**Why Wrong**: GitHub is a tool, not an agent. Use MCP.

**Correct**:
```python

registry.register_mcp_server(github_mcp_server)
agent.execute_tool("github_create_issue", params)  # MCP
```

### ❌ Mistake 3: Exposing Agent via A2A to External Systems

```python
# WRONG: A2A is for agent-to-agent, not external systems
# Trying to expose agent to Claude Desktop via A2A
```

**Why Wrong**: Claude Desktop expects MCP, not A2A.

**Correct**:
```python
# Expose via MCP for external systems
server = KaizenMCPServer()
server.register_agent_as_tool(agent)
```

---

## Summary

**Golden Rules**:

1. ✅ **MCP = Tool Calling** - Use for external tools, services, functions
2. ✅ **A2A = Agent Collaboration** - Use for multi-agent coordination
3. ✅ **MCP = Client-Server** - Hierarchical, one-way execution
4. ✅ **A2A = Peer-to-Peer** - Equal agents, bidirectional communication
5. ✅ **Agents can use BOTH** - MCP for tools, A2A for peers

**Decision Checklist**:
- [ ] Calling external tools/services? → MCP
- [ ] Exposing agent to external systems? → MCP
- [ ] Coordinating with other agents? → A2A
- [ ] Semantic capability discovery? → A2A
- [ ] Multi-agent workflow? → A2A
- [ ] Simple function execution? → MCP

**References**:
- MCP Specification: https://modelcontextprotocol.io/
- Google A2A Protocol: Internal Kaizen implementation
- BaseAgent A2A: `src/kaizen/core/base_agent.py:to_a2a_card()`
- MCP Integration: `src/kaizen/integrations/mcp/`

---

**Last Updated**: 2025-10-22
**Version**: 1.0.0
