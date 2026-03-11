# Kaizen Developer Workflow Guide

**The Definitive Guide to Production-Ready AI Agents**

**Version**: 1.0.0
**Created**: 2025-10-22
**Audience**: Developers new to Kaizen
**Reading Time**: 30-45 minutes

---

## Welcome to Kaizen

Kaizen is a production-ready AI agent framework that makes building sophisticated AI applications **simple, reliable, and powerful**. Whether you're building a simple Q&A chatbot or a fully autonomous coding assistant, Kaizen provides battle-tested patterns and sensible defaults that just work.

**What makes Kaizen different?** While other frameworks force you to build everything from scratch, Kaizen gives you:

- ✅ **Production-ready patterns** proven in real-world systems (Claude Code, Codex, Google A2A)
- ✅ **Simple configuration** with powerful defaults (90% use cases need <10 lines)
- ✅ **Autonomous execution** with objective convergence (no hallucinated "I'm done" signals)
- ✅ **Multi-agent coordination** with semantic capability matching (no hardcoded if/else)
- ✅ **Universal tool integration** supporting 12 builtin tools + MCP ecosystem

---

## Table of Contents

**Part 1: Understanding Kaizen**

1. [Why Kaizen Exists](#why-kaizen-exists)
2. [Kaizen Philosophy](#kaizen-philosophy)
3. [State-of-the-Art Patterns](#state-of-the-art-patterns)

**Part 2: Quick Start Journey** 4. [Your First Agent (5 minutes)](#your-first-agent) 5. [Adding Tools (10 minutes)](#adding-tools) 6. [Multi-Agent Coordination (15 minutes)](#multi-agent-coordination) 7. [Autonomous Agents (20 minutes)](#autonomous-agents)

**Part 3: Architecture Decisions** 8. [When to Use MCP vs A2A](#when-to-use-mcp-vs-a2a) 9. [Choosing the Right Agent Type](#choosing-the-right-agent-type) 10. [Tool Integration Strategy](#tool-integration-strategy)

**Part 4: Production Deployment** 11. [Testing Strategy](#testing-strategy) 12. [Monitoring & Observability](#monitoring-and-observability) 13. [Performance Optimization](#performance-optimization)

---

# Part 1: Understanding Kaizen

## Why Kaizen Exists

### The Problem: AI Agent Development is Too Complex

Building production-ready AI agents is **hard**. Developers face fragmented tools, unclear patterns, and no proven architectures:

**Pain Point 1: Complexity Overload**

```python
# Other frameworks: Configure everything manually
agent = GenericAgent(
    llm_provider=provider,
    model=model,
    temperature=temp,
    max_tokens=tokens,
    system_prompt=prompt,
    tools=tools,
    memory=memory,
    strategy=strategy,
    error_handler=handler,
    retry_policy=policy,
    # ... 20 more parameters
)
```

**Result**: 100+ lines of boilerplate before you can even test your agent.

**Pain Point 2: Coordination is Manual**

```python
# Other frameworks: Hardcoded agent selection
def select_worker(task):
    if "code" in task.lower():
        return code_agent
    elif "data" in task.lower():
        return data_agent
    elif "writing" in task.lower():
        return writing_agent
    else:
        return default_agent  # 😱 What about edge cases?
```

**Result**: Brittle if/else logic that breaks with new task types.

**Pain Point 3: Tools are Fragmented**

```python
# Other frameworks: Manual tool integration
def read_file(path):
    with open(path) as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w') as f:
        f.write(content)

# Register each tool manually
agent.register_tool("read", read_file)
agent.register_tool("write", write_file)
# ... repeat for 50+ tools
```

**Result**: Hours spent on tool plumbing instead of business logic.

**Pain Point 4: Autonomous Agents are Black Boxes**

```python
# Other frameworks: Subjective convergence (unreliable)
if agent.confidence > 0.9:  # 😱 LLM can hallucinate confidence!
    return "done"
```

**Result**: Agents stop early or loop forever with no clear signal.

**Pain Point 5: No Production Patterns**

```python
# Other frameworks: Build everything from scratch
# - How do I handle long-running sessions?
# - What about context overflow?
# - How do I persist state?
# - How do I handle tool failures?
```

**Result**: Reinventing the wheel for every production concern.

### The Solution: Kaizen Philosophy

Kaizen solves these pain points with **5 core principles**:

**Principle 1: Simple Configuration, Powerful Defaults**

```python
# Kaizen: 3 lines to get started
from kaizen.agents import SimpleQAAgent

agent = SimpleQAAgent()  # Uses sensible defaults
result = agent.ask("What is quantum computing?")
```

**Result**: Start testing in seconds, configure when needed.

**Principle 2: Semantic Coordination (No Hardcoding)**

```python
# Kaizen: Automatic semantic matching via Google A2A
pattern = SupervisorWorkerPattern(supervisor, workers)

# Automatically selects best worker based on task semantics
best_worker = pattern.supervisor.select_worker_for_task(
    task="Analyze sales data and create visualization",
    available_workers=[code_expert, data_expert, writing_expert]
)
# Returns: data_expert (score: 0.92) ✅ Semantic match!
```

**Result**: No if/else logic, semantic understanding drives selection.

**Principle 3: Universal Tool Integration**

```python
# Kaizen: 12 builtin tools + MCP ecosystem

# 12 builtin tools enabled via MCP

# Instant access to:
# - File operations (read, write, delete, list)
# - HTTP operations (get, post, put, delete)
# - Bash execution
# - Web access (fetch_url, extract_links)
```

**Result**: Production-ready tools in one line.

**Principle 4: Objective Convergence (Reliable)**

```python
# Kaizen: Objective detection via tool_calls field
def _check_convergence(self, response):
    tool_calls = response.get("tool_calls", [])
    return not tool_calls  # Empty = done ✅ No hallucination!
```

**Result**: Deterministic stopping condition, 100% reliable.

**Principle 5: Battle-Tested Patterns**

```python
# Kaizen: Proven architectures built-in
from kaizen.agents.autonomous import ClaudeCodeAgent

# Claude Code's 30+ hour autonomous coding pattern
agent = ClaudeCodeAgent(config)
result = await agent.execute_autonomously("Refactor auth module")
```

**Result**: Production patterns from day one.

### The Value: What You Get with Kaizen

**For Developers**:

- ⚡ **10x faster development** - Simple config, powerful defaults
- 🎯 **90% less boilerplate** - Focus on business logic, not plumbing
- 🔒 **Production-ready patterns** - Battle-tested architectures
- 🤖 **Autonomous execution** - Multi-hour sessions with reliable convergence
- 🔗 **Seamless coordination** - Google A2A semantic matching

**For Teams**:

- 📊 **Consistent patterns** - Everyone uses the same proven architecture
- 🧪 **Comprehensive testing** - 3-tier strategy with NO MOCKING
- 📚 **Complete documentation** - Guides, tutorials, examples
- 🚀 **Easy onboarding** - New developers productive in hours

**For Organizations**:

- 💰 **Lower development costs** - Reuse patterns, avoid mistakes
- ⚡ **Faster time-to-market** - Production-ready from day one
- 🔐 **Enterprise-grade** - Audit trails, error handling, monitoring
- 📈 **Scalable architecture** - Multi-agent coordination built-in

---

## Kaizen Philosophy

Kaizen is built on 5 foundational principles that guide every design decision:

### Principle 1: Signature-Based Programming

**What it is**: Type-safe, declarative I/O definitions inspired by DSPy but improved.

**Why it matters**: Traditional prompt engineering is brittle and hard to maintain. Signatures make agent I/O **type-safe, composable, and self-documenting**.

**Example**:

```python
from kaizen.signatures import Signature, InputField, OutputField

class QASignature(Signature):
    """Question answering with confidence scoring."""

    # Inputs (what the agent receives)
    question: str = InputField(
        description="User's question to answer"
    )
    context: str = InputField(
        description="Additional context (optional)",
        default=""
    )

    # Outputs (what the agent produces)
    answer: str = OutputField(
        description="Clear, concise answer to the question"
    )
    confidence: float = OutputField(
        description="Confidence score (0.0-1.0)"
    )
    sources: list = OutputField(
        description="List of sources consulted",
        default=[]
    )
```

**Benefits**:

- ✅ **Type Safety**: Catch errors at development time
- ✅ **Self-Documenting**: Descriptions explain expected I/O
- ✅ **Composable**: Reuse signatures across agents
- ✅ **LLM-Friendly**: Auto-generates clear prompts

**Comparison with DSPy**:

```python
# DSPy: Separate signature and module
class QASignature(dspy.Signature):
    question = dspy.InputField()
    answer = dspy.OutputField()

class QAModule(dspy.Module):
    def __init__(self):
        self.generate = dspy.ChainOfThought(QASignature)

    def forward(self, question):
        return self.generate(question=question)

# Kaizen: Unified agent with signature
class QAAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config, signature=QASignature())

    def ask(self, question: str):
        return self.run(question=question)
```

**Why Kaizen is better**:

- ✅ Less boilerplate (no separate Module class)
- ✅ Better ergonomics (natural method names like `ask()`)
- ✅ Integrated with BaseAgent (memory, tools, strategies)

### Principle 2: Workflow Foundation (Kailash SDK)

**What it is**: Kaizen is built **on top of** Kailash Core SDK, the workflow automation framework.

**Why it matters**: Most AI frameworks are built from scratch, missing proven patterns from workflow orchestration. Kaizen inherits **10+ years of workflow best practices**.

**Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│                    Kaizen Framework                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  BaseAgent  │  │ Multi-Modal │  │  Multi-     │        │
│  │ Architecture│  │  Processing │  │  Agent      │        │
│  └─────────────┘  └─────────────┘  └─────────────┘        │
│                           │                                 │
│  ┌─────────────────────────────────────────────────────┐  │
│  │          Kailash Core SDK                           │  │
│  │  WorkflowBuilder │ LocalRuntime │ 140+ Nodes       │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**What you get from Kailash**:

- ✅ **Robust execution engine** (LocalRuntime, AsyncLocalRuntime)
- ✅ **140+ built-in nodes** for common operations
- ✅ **Error handling** with retry policies
- ✅ **State management** with checkpoints
- ✅ **Performance monitoring** built-in

**Example - Agent as Workflow**:

```python
# Every Kaizen agent can be converted to a workflow
agent = SimpleQAAgent(config)

# Convert to workflow for integration
workflow = agent.to_workflow()

# Now you can:
# 1. Combine with other workflows
# 2. Deploy via Nexus (API + CLI + MCP)
# 3. Integrate with DataFlow (database operations)
# 4. Add custom nodes
combined_workflow = WorkflowBuilder()
combined_workflow.add_subworkflow("qa", workflow)
combined_workflow.add_node("SaveToDatabase", "save", {...})
```

**Benefits**:

- ✅ **Enterprise integration** - Agents work with existing workflows
- ✅ **Production-ready** - Inherits battle-tested infrastructure
- ✅ **Flexible deployment** - API, CLI, MCP, or embedded

### Principle 3: Battle-Tested Patterns

**What it is**: Kaizen implements proven architectures from production systems (Claude Code, Codex, Google A2A).

**Why it matters**: Don't reinvent the wheel. Use patterns that have proven successful in **millions of production interactions**.

**Pattern 1: Claude Code Autonomous Architecture**

Implements the `while(tool_calls_exist)` pattern from Claude Code:

```python
from kaizen.agents.autonomous import ClaudeCodeAgent, ClaudeCodeConfig

config = ClaudeCodeConfig(
    max_cycles=100,           # 30+ hour sessions
    context_threshold=0.92,   # 92% compression trigger
    enable_diffs=True,        # Show changes before applying
    enable_reminders=True     # Combat model drift
)

agent = ClaudeCodeAgent(config, signature, registry)

# Autonomous coding session (1-30+ hours)
result = await agent.execute_autonomously(
    "Refactor authentication module to use dependency injection. "
    "Add comprehensive tests. Ensure all existing tests pass."
)
```

**Features**:

- ✅ 15-tool ecosystem (file, search, execution, web)
- ✅ Diff-first workflow (transparency)
- ✅ System reminders (every 10 cycles to combat drift)
- ✅ Context management (auto-compress at 92%)
- ✅ CLAUDE.md project memory

**Pattern 2: Codex PR Generation Architecture**

Implements Codex's container-based one-shot PR workflow:

```python
from kaizen.agents.autonomous import CodexAgent, CodexConfig

config = CodexConfig(
    timeout_minutes=30,         # 1-30 minute tasks
    container_image="python:3.11",
    enable_internet=False,      # Security isolation
    test_command="pytest tests/",
    agents_md_path="AGENTS.md"
)

agent = CodexAgent(config, signature, registry)

# Autonomous PR generation (5-30 minutes)
result = await agent.execute_autonomously(
    "Fix bug #123: User authentication timeout after 30 minutes. "
    "Add tests to prevent regression."
)

print(result['commit_message'])  # Professional commit message
print(result['pr_description'])  # Complete PR description
```

**Features**:

- ✅ Container-based execution (isolated environment)
- ✅ Test-driven iteration (run → parse → fix → repeat)
- ✅ Professional PR generation
- ✅ Logging and evidence system
- ✅ AGENTS.md configuration

**Pattern 3: Google A2A Multi-Agent Coordination**

Implements Google's Agent-to-Agent (A2A) protocol for semantic coordination:

```python
from kaizen.agents.coordination.supervisor_worker import SupervisorWorkerPattern

# Create workers with capability cards (auto-generated)
code_expert = CodeGenerationAgent(config)
data_expert = RAGResearchAgent(config)
writing_expert = SimpleQAAgent(config)

# Supervisor uses A2A for semantic matching
pattern = SupervisorWorkerPattern(
    supervisor=supervisor,
    workers=[code_expert, data_expert, writing_expert]
)

# Automatic semantic selection (NO hardcoded if/else!)
result = pattern.execute_task(
    "Analyze this codebase, identify performance bottlenecks, "
    "and suggest optimizations with code examples."
)

# Behind the scenes:
# 1. Supervisor analyzes task semantics
# 2. Compares with worker capabilities (via A2A cards)
# 3. Selects data_expert (0.85) and code_expert (0.92)
# 4. Coordinates execution and merges results
```

**Features**:

- ✅ Automatic capability discovery (no registration)
- ✅ Semantic task matching (no if/else logic)
- ✅ Score-based selection (confidence in matching)
- ✅ Multi-worker coordination
- ✅ Result aggregation

### Principle 4: Production-Ready Defaults

**What it is**: Every Kaizen agent comes with production-grade features enabled by default.

**Why it matters**: Don't waste time implementing error handling, logging, and monitoring. **It just works**.

**Default Feature 1: Error Handling**

```python
agent = SimpleQAAgent(config)

# Automatic error handling:
# - LLM API failures → Retry with exponential backoff
# - Invalid responses → Fallback to default
# - Tool execution errors → Logged and recovered
# - Context overflow → Auto-compression
```

**Default Feature 2: Audit Trails**

```python
result = agent.ask("What is AI?")

# Automatically tracked:
# - Input/output pairs
# - Token usage
# - Execution time
# - Tool calls
# - Errors and retries
```

**Default Feature 3: Memory Management**

```python
# Enable memory with one parameter
config = QAConfig(max_turns=10)  # Buffer last 10 turns

agent = SimpleQAAgent(config)

# Automatic conversation history:
result1 = agent.ask("My name is Alice", session_id="user123")
result2 = agent.ask("What's my name?", session_id="user123")
# Returns: "Your name is Alice" ✅ Remembers context
```

**Default Feature 4: Performance Monitoring**

```python
# Built-in metrics (no setup required):
# - Latency (p50, p95, p99)
# - Token usage
# - Cost estimation
# - Cache hit rates
# - Error rates

# Access metrics:
metrics = agent.get_metrics()
print(f"Average latency: {metrics['latency_p50']}ms")
print(f"Total cost: ${metrics['total_cost']:.2f}")
```

### Principle 5: Progressive Complexity

**What it is**: Start simple, add complexity only when needed.

**Why it matters**: Don't overwhelm new users with options. **90% of use cases need <10 lines of code**.

**Level 1: Zero Configuration (Simple Start)**

```python
from kaizen.agents import SimpleQAAgent

agent = SimpleQAAgent()  # Uses all defaults
result = agent.ask("What is quantum computing?")
print(result['answer'])
```

**Level 2: Basic Configuration (Custom Model)**

```python
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

config = QAConfig(
    llm_provider="anthropic",
    model="claude-3-opus-20240229"
)

agent = SimpleQAAgent(config)
result = agent.ask("Explain quantum entanglement")
```

**Level 3: Tool Integration (Autonomous Execution)**

```python
# Tools auto-configured via MCP

# 12 builtin tools enabled via MCP

agent = SimpleQAAgent(config, tools="all"  # Enable 12 builtin tools via MCP
result = agent.ask("Read data.txt and summarize it")
# Agent autonomously: reads file → processes → returns summary
```

**Level 4: Multi-Agent Coordination (Complex Tasks)**

```python
from kaizen.agents.coordination.supervisor_worker import SupervisorWorkerPattern

supervisor = SupervisorAgent(config)
workers = [CodeAgent(config), DataAgent(config), QAAgent(config)]

pattern = SupervisorWorkerPattern(supervisor, workers)
result = pattern.execute_task(
    "Analyze codebase, identify issues, generate report"
)
```

**Level 5: Autonomous Agents (Production Systems)**

```python
from kaizen.agents.autonomous import ClaudeCodeAgent, ClaudeCodeConfig

config = ClaudeCodeConfig(max_cycles=100, enable_diffs=True)
agent = ClaudeCodeAgent(config, signature, registry)

result = await agent.execute_autonomously(
    "Refactor entire authentication system. Add OAuth2. Update docs."
)
```

**The Pattern**: Each level builds on the previous, adding one concept at a time.

---

## State-of-the-Art Patterns

Kaizen implements 5 cutting-edge patterns that set it apart from other frameworks:

### Pattern 1: Objective Convergence (ADR-013)

**Problem**: How do you know when an AI agent is done?

**Traditional Approach (Subjective)**:

```python
# ❌ UNRELIABLE: Agent can hallucinate confidence
if agent_response.confidence > 0.9:
    return "done"

# ❌ UNRELIABLE: Agent can hallucinate "finish" action
if agent_response.action == "finish":
    return "done"
```

**Kaizen Approach (Objective)**:

```python
# ✅ RELIABLE: Check tool_calls field (objective, JSON-structured)
def _check_convergence(self, response: Dict[str, Any]) -> bool:
    """
    Objective convergence via tool_calls field.

    Returns:
        True if converged (empty tool_calls)
        False if not converged (has tool_calls)
    """
    tool_calls = response.get("tool_calls", [])

    if not isinstance(tool_calls, list):
        return True  # Invalid format → stop

    if tool_calls:
        return False  # Has tools to call → continue

    return True  # No tools needed → converged ✅
```

**Why this matters**:

| Method               | Type          | Accuracy | Risk             |
| -------------------- | ------------- | -------- | ---------------- |
| confidence score     | Subjective    | 85-90%   | ⚠️ Hallucination |
| action field         | Subjective    | 85-95%   | ⚠️ Hallucination |
| **tool_calls field** | **Objective** | **100%** | ✅ **No risk**   |

**Real-World Example**:

```python
from kaizen.agents.specialized import ReActAgent

agent = ReActAgent(config, tools="all"  # Enable 12 builtin tools via MCP

# Cycle 1:
response_1 = agent.run(task="Read data.txt and summarize")
# {
#     "thought": "Need to read file first",
#     "tool_calls": [{"name": "read_file", "params": {"path": "data.txt"}}]
# }
# → NOT converged (has tool_calls) → Continue

# Cycle 2:
response_2 = agent.run(task="...", observation="File content: ...")
# {
#     "thought": "File read successfully, now summarize",
#     "answer": "Summary: ...",
#     "tool_calls": []  # ← Empty!
# }
# → CONVERGED (no tool_calls) → Stop ✅
```

**Benefits**:

- ✅ **100% reliable** - No hallucination risk
- ✅ **Deterministic** - Same stopping condition every time
- ✅ **Transparent** - Clear signal when done
- ✅ **Debuggable** - Easy to trace execution flow

### Pattern 2: Autonomous Execution (Multi-Cycle Agent Loop)

**Problem**: How do you build agents that can work for hours without human intervention?

**Traditional Approach (Single-Shot)**:

```python
# ❌ LIMITED: One request, one response, done
response = agent.run(prompt="Build a REST API")
# Returns immediately with plan, but doesn't execute
```

**Kaizen Approach (Autonomous Loop)**:

```python
# ✅ POWERFUL: Multi-cycle execution with convergence
from kaizen.agents.autonomous import BaseAutonomousAgent

agent = BaseAutonomousAgent(config, signature, registry)

result = await agent.execute_autonomously(
    "Build a REST API with authentication, rate limiting, and tests"
)

# Behind the scenes (autonomous loop):
# Cycle 1: Plan → tool_calls = [read_file("requirements.txt")]
# Cycle 2: Read requirements → tool_calls = [write_file("api.py", code)]
# Cycle 3: Write code → tool_calls = [bash_command("pytest tests/")]
# Cycle 4: Run tests (failures) → tool_calls = [edit_file("api.py", fixes)]
# Cycle 5: Fix code → tool_calls = [bash_command("pytest tests/")]
# Cycle 6: Tests pass → tool_calls = []
# → Converged ✅
```

**The Loop Pattern**:

```python
async def _autonomous_loop(self, task: str) -> Dict[str, Any]:
    """
    Autonomous execution following while(tool_calls_exist) pattern.

    Pattern:
        while tool_calls_exist:
            gather_context()  # Read files, search code
            take_action()     # Edit files, run commands
            verify()          # Check results, run tests
            iterate()         # Update plan, continue
    """
    for cycle_num in range(max_cycles):
        # Execute cycle
        cycle_result = self.strategy.execute(self, inputs)

        # Save checkpoint (every N cycles)
        if cycle_num % checkpoint_frequency == 0:
            self._save_checkpoint(cycle_result, cycle_num)

        # Check convergence (objective)
        if self._check_convergence(cycle_result):
            return cycle_result  # Done ✅

        # Update inputs for next cycle
        inputs["observation"] = cycle_result.get("observation", "")

    return final_result
```

**Real-World Example (ClaudeCodeAgent)**:

```python
from kaizen.agents.autonomous import ClaudeCodeAgent, ClaudeCodeConfig

config = ClaudeCodeConfig(
    max_cycles=100,           # 30+ hour sessions
    enable_diffs=True,        # Show changes before applying
    enable_reminders=True,    # Combat drift every 10 cycles
    context_threshold=0.92    # Auto-compress at 92%
)

agent = ClaudeCodeAgent(config, signature, registry)

# 30+ hour autonomous coding session
result = await agent.execute_autonomously(
    "Migrate authentication from JWT to OAuth2. "
    "Add social login (Google, GitHub). "
    "Update all tests. "
    "Update documentation."
)

print(f"Completed in {result['cycles_used']} cycles")
# Typical: 50-80 cycles over 4-8 hours
```

**Benefits**:

- ✅ **Long-running tasks** - Hours or days of autonomous work
- ✅ **Iterative refinement** - Test → Fix → Repeat
- ✅ **State persistence** - Checkpoints for recovery
- ✅ **Context management** - Auto-compression at 92%
- ✅ **Transparent execution** - Full action log

### Pattern 3: Semantic Coordination (Google A2A Protocol)

**Problem**: How do you coordinate multiple agents without hardcoded logic?

**Traditional Approach (Hardcoded If/Else)**:

```python
# ❌ BRITTLE: Manual task routing
def select_worker(task: str) -> Agent:
    if "code" in task.lower():
        return code_agent
    elif "data" in task.lower():
        return data_agent
    elif "writing" in task.lower():
        return writing_agent
    else:
        return default_agent  # 😱 What about edge cases?

# Problems:
# - Breaks with synonyms ("programming" != "code")
# - Can't handle multi-skill tasks
# - No confidence scoring
# - Hard to maintain as agents grow
```

**Kaizen Approach (Semantic Matching via A2A)**:

```python
# ✅ ROBUST: Automatic semantic task-to-capability matching
from kaizen.agents.coordination.supervisor_worker import SupervisorWorkerPattern

# Workers auto-generate capability cards
code_expert = CodeGenerationAgent(config)
# Capability card (auto-generated):
# {
#     "name": "code_expert",
#     "capabilities": ["code generation", "programming", "software development"],
#     "skills": ["python", "typescript", "refactoring", "testing"],
#     "description": "Expert in generating production-ready code with tests"
# }

data_expert = RAGResearchAgent(config)
# Capability card:
# {
#     "name": "data_expert",
#     "capabilities": ["data analysis", "research", "information retrieval"],
#     "skills": ["statistics", "visualization", "pandas", "sql"],
#     "description": "Expert in analyzing data and generating insights"
# }

# Supervisor coordinates via semantic matching
pattern = SupervisorWorkerPattern(
    supervisor=supervisor,
    workers=[code_expert, data_expert]
)

# Automatic semantic selection
result = pattern.execute_task(
    "Analyze sales data from Q4 and create visualization dashboard"
)

# Behind the scenes:
# 1. Supervisor extracts task semantics: ["analyze", "sales data", "visualization"]
# 2. Compares with worker capabilities using A2A protocol
# 3. Scores each worker:
#    - code_expert: 0.45 (has visualization capability)
#    - data_expert: 0.92 (strong match for analysis + visualization)
# 4. Selects data_expert (highest score)
# 5. Delegates task and monitors execution
```

**The A2A Card Format**:

```python
# Auto-generated from agent signature and config
capability_card = {
    "agent_id": "data_expert_001",
    "agent_type": "RAGResearchAgent",
    "capabilities": [
        "data analysis",
        "statistical analysis",
        "data visualization",
        "research",
        "information retrieval"
    ],
    "skills": [
        "python", "pandas", "numpy", "matplotlib",
        "seaborn", "sql", "statistics"
    ],
    "input_schema": {
        "task": "string",
        "data_source": "string (optional)"
    },
    "output_schema": {
        "analysis": "string",
        "visualizations": "list",
        "insights": "list"
    },
    "description": "Expert in analyzing datasets and generating insights",
    "version": "1.0.0"
}
```

**Real-World Example**:

```python
# Create diverse team
workers = [
    CodeGenerationAgent(config),      # Code expert
    RAGResearchAgent(config),         # Research expert
    SimpleQAAgent(config),            # Q&A expert
    VisionAgent(config),              # Image analysis expert
    TranscriptionAgent(config)        # Audio transcription expert
]

supervisor = SupervisorAgent(config)
pattern = SupervisorWorkerPattern(supervisor, workers)

# Complex multi-skill task
result = pattern.execute_task(
    "Analyze the code in main.py, research best practices for "
    "the identified patterns, generate refactored code with tests, "
    "and create a markdown report explaining the changes."
)

# Automatic coordination:
# 1. CodeAgent: Analyzes main.py → extracts patterns
# 2. ResearchAgent: Researches best practices → finds recommendations
# 3. CodeAgent: Generates refactored code → applies best practices
# 4. QAAgent: Creates markdown report → explains changes
# All orchestrated automatically via semantic matching ✅
```

**Benefits**:

- ✅ **No hardcoded logic** - Semantic understanding drives selection
- ✅ **Handles synonyms** - "code" = "programming" = "development"
- ✅ **Multi-skill tasks** - Can select multiple workers
- ✅ **Confidence scoring** - Knows match quality
- ✅ **Scales easily** - Add workers without changing supervisor

### Pattern 4: Universal Tool Integration (Builtin + MCP)

**Problem**: How do you give agents access to tools without reinventing the wheel?

**Traditional Approach (Manual Tool Creation)**:

```python
# ❌ TEDIOUS: Define every tool manually
def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()

def write_file(path: str, content: str) -> None:
    with open(path, 'w') as f:
        f.write(content)

# ... repeat for 50+ tools

# Register each tool
agent.register_tool("read_file", read_file, schema={...})
agent.register_tool("write_file", write_file, schema={...})
# ... repeat 50 times
```

**Kaizen Approach (Universal Registry + MCP)**:

```python
# ✅ INSTANT: 12 builtin tools in one line
# Tools auto-configured via MCP

# 12 builtin tools enabled via MCP

# Available immediately:
# File Operations (5 tools):
#   - read_file, write_file, delete_file, list_directory, file_exists
# HTTP Operations (4 tools):
#   - http_get, http_post, http_put, http_delete
# Bash Execution (1 tool):
#   - bash_command
# Web Access (2 tools):
#   - fetch_url, extract_links

# Use with any agent
agent = ReActAgent(config, tools="all"  # Enable 12 builtin tools via MCP

# Agent can now autonomously use all 12 tools
result = agent.run(
    task="Read requirements.txt, fetch latest packages from PyPI, "
         "and write updated versions to requirements_new.txt"
)
```

**MCP Integration (Model Context Protocol)**:

```python
# ✅ EXTENSIBLE: Add MCP servers for unlimited tools
from kaizen.core.base_agent import BaseAgent

agent = BaseAgent(
    config=config,
    signature=signature,
    tools="all"  # Enable 12 builtin tools via MCP
    mcp_servers=[
        "github",      # GitHub API tools
        "slack",       # Slack messaging tools
        "filesystem",  # Enhanced file operations
        "browser"      # Web automation tools
    ]
)

# Agent now has access to:
# - 12 builtin tools
# - 50+ GitHub tools (issues, PRs, repos, etc.)
# - 20+ Slack tools (messages, channels, etc.)
# - 30+ filesystem tools (advanced operations)
# - 40+ browser tools (web automation)
# Total: 150+ tools with minimal configuration ✅
```

**Tool Discovery & Approval**:

```python
# Discover available tools
tools = await agent.discover_tools()
print(f"Total tools: {len(tools)}")

# Discover by category
file_tools = await agent.discover_tools(category="file")
web_tools = await agent.discover_tools(category="web")

# Tool execution with approval workflow
# SAFE tools: Auto-execute
result = await agent.execute_tool("read_file", {"path": "data.txt"})

# DANGEROUS tools: Request approval
result = await agent.execute_tool(
    "bash_command",
    {"command": "rm -rf /tmp/cache"}
)
# Prompts user: "Allow agent to execute 'rm -rf /tmp/cache'? [y/n]"
```

**Benefits**:

- ✅ **Instant productivity** - 12 tools in one line
- ✅ **Extensible** - Add MCP servers for specialized tools
- ✅ **Safe** - Approval workflows for dangerous operations
- ✅ **Discoverable** - Agents can explore available tools
- ✅ **Standard protocol** - Works with any MCP-compatible server

### Pattern 5: Multi-Modal Processing (Vision + Audio)

**Problem**: How do you build agents that process images, audio, and text together?

**Traditional Approach (Separate Agents)**:

```python
# ❌ FRAGMENTED: Different agents for each modality
text_agent = TextAgent(config)
vision_agent = VisionAgent(config)
audio_agent = AudioAgent(config)

# Manual coordination required
text_result = text_agent.process(text)
vision_result = vision_agent.process(image)
audio_result = audio_agent.process(audio)

# Manual merging
combined_result = merge_results([text_result, vision_result, audio_result])
```

**Kaizen Approach (Unified Multi-Modal)**:

```python
# ✅ UNIFIED: Single agent handles multiple modalities
from kaizen.agents import VisionAgent, TranscriptionAgent, MultiModalAgent
from kaizen.agents.vision import VisionAgentConfig

# Vision processing (Ollama - free, local)
vision_config = VisionAgentConfig(
    llm_provider="ollama",
    model="bakllava"  # or "llava"
)
vision_agent = VisionAgent(config=vision_config)

# Image analysis
result = vision_agent.analyze(
    image="/path/to/receipt.jpg",
    question="What is the total amount on this receipt?"
)
print(result['answer'])  # "The total amount is $47.82"

# Audio transcription (Whisper)
audio_agent = TranscriptionAgent(config)

# Audio to text
result = audio_agent.transcribe(
    audio="/path/to/meeting.mp3"
)
print(result['transcript'])  # Full meeting transcript

# Multi-modal orchestration
multimodal_agent = MultiModalAgent(
    vision_agent=vision_agent,
    audio_agent=audio_agent,
    qa_agent=qa_agent
)

# Process mixed media
result = multimodal_agent.process(
    image="/path/to/chart.png",
    audio="/path/to/explanation.mp3",
    question="Combine the chart data with the audio explanation "
             "and provide a comprehensive summary"
)
```

**Real-World Example (Document Extraction)**:

```python
from kaizen.agents import VisionAgent
# Tools auto-configured via MCP

# Create vision agent with tools

# 12 builtin tools enabled via MCP

vision_agent = VisionAgent(
    config=VisionAgentConfig(llm_provider="ollama", model="bakllava"),
    tools="all"  # Enable 12 builtin tools via MCP
)

# Autonomous document extraction
result = vision_agent.analyze(
    image="/path/to/invoice.pdf",  # PDF → auto-converted to image
    question="Extract all line items, quantities, prices, and total. "
             "Save to invoice_data.json in structured format."
)

# Agent autonomously:
# 1. Analyzes image with vision model
# 2. Extracts structured data
# 3. Uses write_file tool to save JSON
# 4. Returns confirmation
```

**Multi-Modal Providers**:

| Modality | Providers      | Models               | Cost          |
| -------- | -------------- | -------------------- | ------------- |
| Vision   | Ollama (local) | llava, bakllava      | Free ✅       |
| Vision   | OpenAI         | gpt-4-vision-preview | $0.01/image   |
| Audio    | OpenAI         | whisper-1            | $0.006/minute |

**Benefits**:

- ✅ **Unified API** - Same patterns for all modalities
- ✅ **Local options** - Ollama for free vision processing
- ✅ **Cloud options** - OpenAI for higher accuracy
- ✅ **Tool integration** - Vision + audio agents can use tools
- ✅ **Orchestration** - Multi-modal workflows simplified

---

# Part 2: Quick Start Journey

This part walks you through building AI agents from zero to production, step by step. Each section builds on the previous, adding one concept at a time.

## Your First Agent (5 minutes)

Let's build your first Kaizen agent in 5 minutes.

### Level 1: Zero Configuration

The simplest possible agent - 3 lines of code:

```python
from kaizen.agents import SimpleQAAgent

agent = SimpleQAAgent()  # Uses all defaults
result = agent.ask("What is quantum computing?")
print(result['answer'])
```

**What you get**:

- ✅ Ready-to-use agent with sensible defaults
- ✅ Uses OpenAI GPT-3.5-turbo (from OPENAI_API_KEY in .env)
- ✅ Automatic error handling and retry logic
- ✅ Built-in audit trails and logging

**Cost**: ~$0.002 per query (~500 queries per $1)

### Level 2: Custom Model

Want to use a different model? Add configuration:

```python
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

config = QAConfig(
    llm_provider="anthropic",
    model="claude-3-opus-20240229",
    temperature=0.7
)

agent = SimpleQAAgent(config)
result = agent.ask("Explain quantum entanglement in simple terms")
print(result['answer'])
```

**What changed**:

- ✅ Now using Claude instead of GPT
- ✅ Custom temperature for creativity control
- ✅ Same simple API, different backend

**Cost**: ~$0.015 per query (Opus is more expensive but higher quality)

### Level 3: Add Memory

Enable conversation history with one parameter:

```python
config = QAConfig(
    llm_provider="openai",
    model="gpt-4",
    max_turns=10  # Enable BufferMemory (keep last 10 turns)
)

agent = SimpleQAAgent(config)

# Conversation with memory
result1 = agent.ask("My name is Alice", session_id="user123")
print(result1['answer'])  # "Nice to meet you, Alice!"

result2 = agent.ask("What's my name?", session_id="user123")
print(result2['answer'])  # "Your name is Alice" ✅ Remembers!
```

**What you get**:

- ✅ Automatic conversation history tracking
- ✅ Session-based isolation (different users don't mix)
- ✅ BufferMemory keeps last N turns (configurable)
- ✅ Old conversations auto-pruned

### Level 4: Chain of Thought

Want step-by-step reasoning? Use ChainOfThoughtAgent:

```python
from kaizen.agents import ChainOfThoughtAgent
from kaizen.agents.specialized.cot import CoTConfig

config = CoTConfig(
    llm_provider="openai",
    model="gpt-4",
    max_thinking_steps=5
)

agent = ChainOfThoughtAgent(config)

result = agent.reason("If Alice has 3 apples and Bob has twice as many, how many total?")

print(result['reasoning_steps'])
# [
#     "Alice has 3 apples",
#     "Bob has twice as many as Alice: 2 * 3 = 6 apples",
#     "Total apples: 3 + 6 = 9 apples"
# ]

print(result['answer'])  # "9 apples"
```

**What you get**:

- ✅ Transparent reasoning process
- ✅ Step-by-step breakdown
- ✅ Higher accuracy for complex questions
- ✅ Debuggable logic

**Summary**: In 5 minutes, you've learned:

- ✅ Zero-config agent (3 lines)
- ✅ Custom model configuration
- ✅ Conversation memory
- ✅ Chain of thought reasoning

**Next**: Add autonomous tool calling →

---

## Adding Tools (10 minutes)

Now let's give your agent the ability to **take actions** - reading files, calling APIs, running commands.

### The Power of Tools

**Without tools**, agents can only think:

```python
agent = SimpleQAAgent()
result = agent.ask("Read data.txt and summarize it")
print(result['answer'])
# "I cannot read files. Please provide the contents."
```

**With tools**, agents can act:

```python
# Tools auto-configured via MCP

# 12 builtin tools enabled via MCP

agent = SimpleQAAgent(config, tools="all"  # Enable 12 builtin tools via MCP
result = agent.ask("Read data.txt and summarize it")
print(result['answer'])
# "Summary: The file contains sales data for Q4 2024..."
# (Agent autonomously: read_file → analyze → summarize)
```

### The 12 Builtin Tools

```python
# Tools auto-configured via MCP

# 12 builtin tools enabled via MCP

# File Operations (5 tools)
# - read_file: Read file contents
# - write_file: Write or create file
# - delete_file: Delete file
# - list_directory: List directory contents
# - file_exists: Check if file exists

# HTTP Operations (4 tools)
# - http_get: GET request
# - http_post: POST request
# - http_put: PUT request
# - http_delete: DELETE request

# Bash Execution (1 tool)
# - bash_command: Execute shell command

# Web Access (2 tools)
# - fetch_url: Fetch webpage content
# - extract_links: Extract links from webpage
```

### Autonomous Execution with ReAct

**ReAct** = Reasoning + Acting in cycles:

```python
from kaizen.agents import ReActAgent
from kaizen.agents.specialized.react import ReActConfig

config = ReActConfig(
    llm_provider="openai",
    model="gpt-4",
    max_cycles=10
)

agent = ReActAgent(config, tools="all"  # Enable 12 builtin tools via MCP

result = agent.run(
    task="Read requirements.txt, check which packages are outdated, "
         "and write a report to outdated_packages.txt"
)

# Behind the scenes (autonomous loop):
# Cycle 1:
#   Thought: "Need to read requirements.txt first"
#   Action: read_file("requirements.txt")
#   Observation: "Flask==2.0.0\nrequests==2.25.0\n..."
#
# Cycle 2:
#   Thought: "Need to check latest versions for each package"
#   Action: http_get("https://pypi.org/pypi/Flask/json")
#   Observation: "Latest version: 3.0.0"
#
# Cycle 3:
#   Thought: "Flask is outdated (2.0.0 → 3.0.0), check requests"
#   Action: http_get("https://pypi.org/pypi/requests/json")
#   Observation: "Latest version: 2.31.0"
#
# Cycle 4:
#   Thought: "Both packages are outdated, generate report"
#   Action: write_file("outdated_packages.txt", report_content)
#   Observation: "File written successfully"
#
# Cycle 5:
#   Thought: "Task complete"
#   tool_calls: []  # ← Converged!
```

### Tool Approval Workflows

Tools have danger levels:

```python
from kaizen.tools import ToolDangerLevel

# SAFE: Auto-execute (no approval)
registry.register_tool(
    name="read_file",
    function=read_file_impl,
    danger_level=ToolDangerLevel.SAFE
)

# MODERATE: Ask once per session
registry.register_tool(
    name="http_post",
    function=http_post_impl,
    danger_level=ToolDangerLevel.MODERATE
)

# DANGEROUS: Ask every time
registry.register_tool(
    name="delete_file",
    function=delete_file_impl,
    danger_level=ToolDangerLevel.DANGEROUS
)

# CRITICAL: Requires explicit confirmation
registry.register_tool(
    name="bash_command",
    function=bash_impl,
    danger_level=ToolDangerLevel.CRITICAL
)
```

**Execution Flow**:

```python
# SAFE tools: Execute immediately
result = await agent.execute_tool("read_file", {"path": "data.txt"})

# DANGEROUS tools: Request approval
result = await agent.execute_tool("bash_command", {"command": "rm -rf /tmp/cache"})
# → Prompts: "Allow agent to execute 'rm -rf /tmp/cache'? [y/n]"
# → If approved: Executes and remembers approval for session
# → If denied: Returns error to agent
```

### Tool Discovery

Agents can discover available tools:

```python
# Discover all tools
tools = await agent.discover_tools()
print(f"Total tools: {len(tools)}")  # 12

# Discover by category
file_tools = await agent.discover_tools(category="file")
web_tools = await agent.discover_tools(category="web")

# Example tool metadata
print(file_tools[0])
# {
#     "name": "read_file",
#     "description": "Read contents of a file",
#     "category": "file",
#     "danger_level": "SAFE",
#     "parameters": {
#         "path": {"type": "string", "required": True}
#     }
# }
```

### Complete Example: Research Assistant

```python
from kaizen.agents import ReActAgent
from kaizen.agents.specialized.react import ReActConfig
# Tools auto-configured via MCP

# Setup

# 12 builtin tools enabled via MCP

config = ReActConfig(
    llm_provider="openai",
    model="gpt-4",
    max_cycles=20
)

agent = ReActAgent(config, tools="all"  # Enable 12 builtin tools via MCP

# Autonomous research task
result = agent.run(
    task="Research the top 3 Python web frameworks in 2024. "
         "For each framework, find the latest version and main features. "
         "Save a comparison table to python_frameworks_2024.md"
)

# Agent autonomously:
# 1. Searches web for "top python web frameworks 2024"
# 2. Extracts framework names (Flask, Django, FastAPI)
# 3. Fetches latest versions from PyPI for each
# 4. Fetches documentation to extract features
# 5. Generates markdown table
# 6. Writes to python_frameworks_2024.md
# 7. Converges (no more tools needed)

print(result['summary'])
# "Successfully researched 3 frameworks and created comparison table in python_frameworks_2024.md"
```

**Summary**: In 10 minutes, you've learned:

- ✅ Tool registry and builtin tools (12 total)
- ✅ Autonomous execution with ReAct
- ✅ Tool approval workflows (4 danger levels)
- ✅ Tool discovery API
- ✅ Building a research assistant

**Next**: Multi-agent coordination →

---

## Multi-Agent Coordination (15 minutes)

Now let's build systems where **multiple specialized agents work together** to solve complex tasks.

### The Problem: One Agent Can't Do Everything

```python
# ❌ Single agent trying to do everything
general_agent = SimpleQAAgent(config)

result = general_agent.ask(
    "Analyze the codebase in src/, identify performance bottlenecks, "
    "generate optimized code with tests, and create a technical report."
)
# Result: Mediocre at everything, expert at nothing
```

### The Solution: Specialized Agents + Semantic Coordination

```python
# ✅ Specialized agents, each expert in their domain
from kaizen.agents import CodeGenerationAgent, RAGResearchAgent, SimpleQAAgent
from kaizen.agents.coordination.supervisor_worker import SupervisorWorkerPattern

# Create specialists
code_expert = CodeGenerationAgent(config)  # Expert: code generation
data_expert = RAGResearchAgent(config)     # Expert: research and analysis
writer_expert = SimpleQAAgent(config)       # Expert: documentation

# Create coordination pattern
supervisor = SupervisorAgent(config)
pattern = SupervisorWorkerPattern(
    supervisor=supervisor,
    workers=[code_expert, data_expert, writer_expert]
)

# Automatic semantic task routing (NO hardcoded if/else!)
result = pattern.execute_task(
    "Analyze the codebase, identify performance bottlenecks, "
    "generate optimized code, and create a technical report."
)

# Behind the scenes:
# 1. data_expert: Analyzes codebase → finds bottlenecks
# 2. code_expert: Generates optimized code → applies best practices
# 3. writer_expert: Creates technical report → explains changes
# All orchestrated automatically via Google A2A protocol ✅
```

### Google A2A Protocol (Agent-to-Agent)

**What is A2A?** Google's standard for semantic agent coordination.

**Key Concept**: Agents advertise capabilities, supervisor matches tasks semantically.

**Capability Cards** (Auto-Generated):

```python
# Code expert's capability card (auto-generated from signature)
{
    "agent_id": "code_expert_001",
    "agent_type": "CodeGenerationAgent",
    "capabilities": [
        "code generation",
        "programming",
        "software development",
        "refactoring",
        "testing"
    ],
    "skills": [
        "python", "typescript", "javascript",
        "testing", "debugging", "optimization"
    ],
    "input_schema": {
        "task": "string",
        "language": "string (optional)"
    },
    "output_schema": {
        "code": "string",
        "tests": "string",
        "explanation": "string"
    },
    "description": "Expert in generating production-ready code with tests"
}
```

**Semantic Matching**:

```python
# Task: "Optimize database queries in user_service.py"

# Supervisor analyzes task semantics:
task_semantics = ["optimize", "database", "queries", "code"]

# Compares with worker capabilities:
# code_expert: ["code", "programming", "optimization"] → score: 0.92 ✅
# data_expert: ["analysis", "research", "database"] → score: 0.75
# writer_expert: ["writing", "documentation"] → score: 0.15

# Selects: code_expert (highest score)
```

### No More Hardcoded If/Else!

**Traditional Approach** (❌ Brittle):

```python
def select_worker(task: str):
    if "code" in task.lower():
        return code_agent
    elif "data" in task.lower():
        return data_agent
    elif "writing" in task.lower():
        return writing_agent
    else:
        return default_agent  # 😱 What about "programming", "analysis", etc?
```

**Kaizen A2A Approach** (✅ Robust):

```python
# Automatic semantic matching (handles synonyms, multi-skill tasks)
best_worker = pattern.supervisor.select_worker_for_task(
    task="Write Python code to analyze sales data and create visualization",
    available_workers=[code_expert, data_expert, writer_expert],
    return_score=True
)

# Returns:
# {
#     "worker": <DataAnalystAgent>,  # Best match!
#     "score": 0.89,  # High confidence
#     "reasoning": "Task requires data analysis + visualization skills"
# }
```

**Benefits**:

- ✅ Handles synonyms ("code" = "programming" = "development")
- ✅ Multi-skill tasks (selects multiple workers if needed)
- ✅ Confidence scoring (know match quality)
- ✅ Scales with new agents (no supervisor changes needed)

### Complete Example: Software Development Team

```python
from kaizen.agents import (
    CodeGenerationAgent,
    RAGResearchAgent,
    SimpleQAAgent,
    ReActAgent
)
from kaizen.agents.coordination.supervisor_worker import SupervisorWorkerPattern

# Create specialized team
backend_dev = CodeGenerationAgent(
    config,
    name="BackendDeveloper",
    skills=["python", "fastapi", "databases"]
)

frontend_dev = CodeGenerationAgent(
    config,
    name="FrontendDeveloper",
    skills=["react", "typescript", "tailwind"]
)

qa_engineer = ReActAgent(
    config,
    name="QAEngineer",
    tools="all"  # Enable tools via MCP
)

tech_writer = SimpleQAAgent(
    config,
    name="TechnicalWriter"
)

research_analyst = RAGResearchAgent(
    config,
    name="ResearchAnalyst"
)

# Create supervisor
supervisor = SupervisorAgent(config, name="ProjectManager")

# Coordination pattern
team = SupervisorWorkerPattern(
    supervisor=supervisor,
    workers=[backend_dev, frontend_dev, qa_engineer, tech_writer, research_analyst]
)

# Complex multi-stage task
result = team.execute_task(
    "Build a REST API for user authentication with JWT tokens. "
    "Include rate limiting, password hashing, and email verification. "
    "Add comprehensive tests. Create a React login form. "
    "Document the API in markdown with examples."
)

# Automatic orchestration:
# 1. research_analyst: Researches JWT best practices
# 2. backend_dev: Builds FastAPI endpoints with auth logic
# 3. qa_engineer: Writes and runs tests (pytest)
# 4. frontend_dev: Creates React login form
# 5. tech_writer: Documents API with examples
# 6. supervisor: Coordinates execution and merges results
```

### Other Coordination Patterns

**1. Consensus Pattern** (Democratic Decision Making):

```python
from kaizen.agents.coordination.consensus_pattern import ConsensusPattern

# Multiple agents vote on best solution
pattern = ConsensusPattern(
    agents=[agent1, agent2, agent3],
    voting_strategy="majority"  # or "unanimous", "weighted"
)

result = pattern.reach_consensus(
    "What is the best approach to implement user authentication?"
)
# Each agent proposes solution → votes on all proposals → selects winner
```

**2. Debate Pattern** (Adversarial Refinement):

```python
from kaizen.agents.coordination.debate_pattern import DebatePattern

# Agents debate to refine solution
pattern = DebatePattern(
    proponent=proponent_agent,
    opponent=opponent_agent,
    judge=judge_agent,
    max_rounds=3
)

result = pattern.debate(
    "Should we use microservices or monolithic architecture?"
)
# Proponent argues for → Opponent argues against → Judge evaluates → Repeat
```

**3. Sequential Pattern** (Pipeline):

```python
from kaizen.agents.coordination.sequential_pattern import SequentialPattern

# Agents process task in sequence (pipeline)
pattern = SequentialPattern(agents=[agent1, agent2, agent3])

result = pattern.execute(task)
# agent1 output → agent2 input → agent2 output → agent3 input → final result
```

**Summary**: In 15 minutes, you've learned:

- ✅ Multi-agent coordination with Google A2A
- ✅ Semantic task matching (no hardcoded logic)
- ✅ Capability cards and confidence scoring
- ✅ SupervisorWorkerPattern for complex tasks
- ✅ Other patterns (Consensus, Debate, Sequential)

**Next**: Autonomous agents for long-running tasks →

---

## Autonomous Agents (20 minutes)

Now let's build agents that can work for **hours** without human intervention.

### The Three Autonomous Patterns

Kaizen provides 3 production-ready autonomous patterns:

| Pattern                 | Use Case          | Duration     | Cycles | Example               |
| ----------------------- | ----------------- | ------------ | ------ | --------------------- |
| **BaseAutonomousAgent** | General purpose   | 1-4 hours    | 20     | Research, analysis    |
| **ClaudeCodeAgent**     | Autonomous coding | 4-30+ hours  | 100    | Refactoring, features |
| **CodexAgent**          | PR generation     | 5-30 minutes | 30     | Bug fixes, one-shot   |

### Pattern 1: BaseAutonomousAgent (General Purpose)

**Use Case**: Research, analysis, general autonomous tasks

```python
from kaizen.agents.autonomous import BaseAutonomousAgent, AutonomousConfig

config = AutonomousConfig(
    llm_provider="openai",
    model="gpt-4",
    max_cycles=20,  # 1-4 hour sessions
    checkpoint_frequency=5  # Save every 5 cycles
)

agent = BaseAutonomousAgent(config, signature, registry)

# Autonomous execution
result = await agent.execute_autonomously(
    "Research the top 10 machine learning papers from 2024. "
    "For each paper, extract: title, authors, key contribution, and impact. "
    "Create a comprehensive markdown report with citations."
)

# Behind the scenes (autonomous loop):
# Cycle 1: Plan → search for ML papers 2024
# Cycle 2: Find top papers → extract metadata
# Cycle 3-12: For each paper, read abstract → extract key points
# Cycle 13: Analyze impact metrics
# Cycle 14: Generate markdown report
# Cycle 15: Verify completeness
# Cycle 16: tool_calls = [] → Converged ✅

print(result['summary'])
# "Successfully researched 10 papers and created comprehensive report in ml_papers_2024.md"
```

**Key Features**:

- ✅ Autonomous loop (`while(tool_calls_exist)`)
- ✅ Checkpoint saving (recovery from failures)
- ✅ Objective convergence (tool_calls field)
- ✅ Planning system (TODO-based)
- ✅ State persistence (JSONL format)

### Pattern 2: ClaudeCodeAgent (30+ Hour Sessions)

**Use Case**: Large refactoring, feature implementation, multi-file changes

**Architecture**: Based on Claude Code's proven autonomous coding pattern.

```python
from kaizen.agents.autonomous import ClaudeCodeAgent, ClaudeCodeConfig

config = ClaudeCodeConfig(
    llm_provider="openai",
    model="gpt-4",
    max_cycles=100,  # 30+ hour sessions supported
    enable_diffs=True,  # Show changes before applying
    enable_reminders=True,  # Combat drift every 10 cycles
    context_threshold=0.92,  # Auto-compress at 92%
    reminder_frequency=10  # System reminder every 10 cycles
)

agent = ClaudeCodeAgent(config, signature, registry)

# Autonomous coding session (4-30 hours)
result = await agent.execute_autonomously(
    "Migrate authentication system from JWT to OAuth2. "
    "Add social login (Google, GitHub, Apple). "
    "Update all tests to use new auth system. "
    "Update documentation with migration guide."
)

# Behind the scenes (100 cycles over 8 hours):
# Cycles 1-5: Explore codebase, read current auth implementation
# Cycles 6-15: Plan migration strategy, identify affected files
# Cycles 16-40: Implement OAuth2 core (providers, tokens, refresh)
# Cycles 41-55: Add social login integrations
# Cycles 56-75: Update tests (read → modify → verify)
# Cycles 76-85: Update documentation
# Cycles 86-95: Final verification, run all tests
# Cycle 96: tool_calls = [] → Converged ✅

print(f"Completed in {result['cycles_used']} cycles")  # 96 cycles
print(f"Files modified: {len(result['modified_files'])}")  # 42 files
print(f"Total time: {result['duration_hours']:.1f} hours")  # 8.3 hours
```

**Key Features**:

- ✅ **15-tool ecosystem**:
  - File: read, write, edit, delete, list
  - Search: glob, grep
  - Execution: bash
  - Web: fetch_url, web_search
  - Workflow: todo_write, task_spawn
- ✅ **Diff-first workflow** (transparency before changes)
- ✅ **System reminders** (every 10 cycles to combat drift)
- ✅ **Context management** (auto-compress at 92%)
- ✅ **CLAUDE.md memory** (project knowledge persistence)

**System Reminders** (Combat Model Drift):

```python
# Every 10 cycles, inject reminder:
"""
SYSTEM REMINDER (Cycle 30):
- Original task: Migrate auth to OAuth2
- Progress: OAuth2 core implemented (40% complete)
- Next: Add social login integrations
- Modified files: 18 files
- Tests passing: 245/312
- Checkpoint saved at: cycle_30_checkpoint.jsonl
"""
```

### Pattern 3: CodexAgent (PR Generation)

**Use Case**: Bug fixes, small features, automated PR generation

**Architecture**: Based on Codex's container-based one-shot workflow.

```python
from kaizen.agents.autonomous import CodexAgent, CodexConfig

config = CodexConfig(
    llm_provider="openai",
    model="gpt-4",
    timeout_minutes=30,  # 5-30 minute tasks
    container_image="python:3.11",
    enable_internet=False,  # Security: No internet after setup
    test_command="pytest tests/",
    agents_md_path="AGENTS.md"  # Configuration file
)

agent = CodexAgent(config, signature, registry)

# Autonomous PR generation (5-30 minutes)
result = await agent.execute_autonomously(
    "Fix bug #123: User authentication timeout after 30 minutes. "
    "Root cause: JWT token expiry not handled correctly. "
    "Add tests to prevent regression."
)

# Behind the scenes (30 cycles over 12 minutes):
# Cycle 1: Read AGENTS.md config
# Cycle 2: Read bug report and related code
# Cycle 3-5: Identify root cause (JWT expiry logic)
# Cycle 6-8: Implement fix (handle expiry, refresh token)
# Cycle 9: Run tests → 2 failures
# Cycle 10-12: Fix test failures
# Cycle 13: Run tests → All pass ✅
# Cycle 14: Generate commit message
# Cycle 15: Generate PR description
# Cycle 16: tool_calls = [] → Converged ✅

# Professional outputs
print(result['commit_message'])
# """
# fix: Handle JWT token expiry correctly (fixes #123)
#
# - Added token refresh logic on 401 responses
# - Updated auth middleware to check expiry before requests
# - Added comprehensive tests for token expiry scenarios
#
# Closes #123
# """

print(result['pr_description'])
# """
# ## Summary
# Fixes bug #123 where users were logged out after 30 minutes due to
# JWT token expiry not being handled correctly.
#
# ## Changes
# - Added automatic token refresh logic
# - Updated auth middleware to proactively check token expiry
# - Added 5 new tests covering expiry edge cases
#
# ## Testing
# - [x] All existing tests pass (312/312)
# - [x] New tests added and passing (5/5)
# - [x] Manual testing with 30-minute timeout
#
# ## Checklist
# - [x] Code follows style guide
# - [x] Tests added and passing
# - [x] Documentation updated
# - [x] No breaking changes
# """
```

**Key Features**:

- ✅ **Container-based execution** (isolated environment)
- ✅ **Test-driven iteration** (run → parse → fix → repeat)
- ✅ **Professional PR generation** (commit + description)
- ✅ **Logging system** (evidence trail)
- ✅ **AGENTS.md configuration** (project-specific settings)

### Choosing the Right Pattern

| Question          | BaseAutonomous     | ClaudeCode      | Codex           |
| ----------------- | ------------------ | --------------- | --------------- |
| Duration?         | 1-4 hours          | 4-30+ hours     | 5-30 min        |
| Task type?        | Research, analysis | Large refactors | Bug fixes       |
| Files changed?    | <10 files          | 10-100 files    | 1-5 files       |
| Isolation needed? | No                 | No              | Yes (container) |
| PR generation?    | No                 | Manual          | Automatic       |
| Cost?             | $2-10              | $20-100         | $1-5            |

### Complete Example: Autonomous Research to PR

```python
from kaizen.agents.autonomous import BaseAutonomousAgent, CodexAgent
from kaizen.agents.autonomous import AutonomousConfig, CodexConfig

# Step 1: Research best practices (BaseAutonomousAgent)
research_config = AutonomousConfig(max_cycles=20)
research_agent = BaseAutonomousAgent(research_config, signature, registry)

research_result = await research_agent.execute_autonomously(
    "Research best practices for implementing rate limiting in FastAPI. "
    "Find 3-5 proven approaches with pros/cons. "
    "Save findings to rate_limiting_research.md"
)

# Step 2: Implement based on research (CodexAgent)
codex_config = CodexConfig(timeout_minutes=30)
codex_agent = CodexAgent(codex_config, signature, registry)

pr_result = await codex_agent.execute_autonomously(
    "Implement rate limiting in our FastAPI app based on findings in "
    "rate_limiting_research.md. Use the recommended approach (token bucket). "
    "Add tests and documentation. Generate PR."
)

print(pr_result['pr_url'])  # Auto-generated PR ready for review!
```

**Summary**: In 20 minutes, you've learned:

- ✅ 3 autonomous patterns (BaseAutonomous, ClaudeCode, Codex)
- ✅ Multi-hour autonomous execution (100 cycles)
- ✅ Diff-first transparency workflow
- ✅ System reminders for drift prevention
- ✅ Automatic PR generation
- ✅ Choosing the right pattern for your use case

---

# Part 3: Architecture Decisions

This part helps you make informed architectural decisions when building with Kaizen.

## When to Use MCP vs A2A

Both Model Context Protocol (MCP) and Agent-to-Agent (A2A) Protocol enable agent coordination, but they serve different purposes.

### MCP (Model Context Protocol)

**What it is**: Standard protocol for connecting AI agents to external tools and data sources.

**Use Case**: Tool integration and data access

**Architecture**:

```
┌─────────────┐
│   Agent     │
│             │
└──────┬──────┘
       │
       │ MCP Protocol
       │
┌──────▼──────────────────────────┐
│   MCP Servers (Tool Providers)  │
├─────────────────────────────────┤
│ • GitHub Server (50+ tools)     │
│ • Slack Server (20+ tools)      │
│ • Filesystem Server (30+ tools) │
│ • Browser Server (40+ tools)    │
└─────────────────────────────────┘
```

**Example**:

```python
from kaizen.agents import SimpleQAAgent

# Agent with MCP integration (external tools)
agent = SimpleQAAgent(
    config,
    mcp_servers=["github", "slack", "filesystem"]
)

# Agent now has access to 100+ external tools
result = agent.ask(
    "Create a GitHub issue for the bug, notify the team in Slack, "
    "and save the bug report to bugs/report_123.md"
)

# Behind the scenes:
# 1. Uses GitHub MCP server → create_issue()
# 2. Uses Slack MCP server → post_message()
# 3. Uses Filesystem MCP server → write_file()
```

**When to use MCP**:

- ✅ Need access to external tools (GitHub, Slack, databases)
- ✅ Want to use community-built MCP servers
- ✅ Single agent needs many specialized tools
- ✅ Tools are provided by third-party services

### A2A (Agent-to-Agent Protocol)

**What it is**: Google's protocol for semantic coordination between AI agents.

**Use Case**: Multi-agent coordination and task routing

**Architecture**:

```
┌─────────────────┐
│   Supervisor    │
│     Agent       │
└────────┬────────┘
         │
         │ A2A Protocol (Capability Cards)
         │
┌────────┴───────────────────────────────┐
│                                        │
┌───▼───────┐  ┌────▼──────┐  ┌────▼───────┐
│ Code      │  │ Data      │  │ Writing    │
│ Expert    │  │ Expert    │  │ Expert     │
└───────────┘  └───────────┘  └────────────┘
```

**Example**:

```python
from kaizen.agents.coordination.supervisor_worker import SupervisorWorkerPattern

# Multiple specialized agents coordinated via A2A
code_expert = CodeGenerationAgent(config)
data_expert = RAGResearchAgent(config)
writer_expert = SimpleQAAgent(config)

pattern = SupervisorWorkerPattern(
    supervisor=supervisor,
    workers=[code_expert, data_expert, writer_expert]
)

# Semantic task routing (no hardcoded logic)
result = pattern.execute_task(
    "Analyze sales data, generate insights, create visualization code, "
    "and write an executive summary report"
)

# Behind the scenes (A2A semantic matching):
# 1. data_expert: Analyzes sales data → generates insights
# 2. code_expert: Creates visualization code → applies best practices
# 3. writer_expert: Writes executive summary → explains findings
```

**When to use A2A**:

- ✅ Need multi-agent coordination
- ✅ Want semantic task routing (no if/else)
- ✅ Complex tasks requiring multiple specialists
- ✅ Agents are different AI models/configurations

### Comparison Table

| Feature        | MCP                        | A2A                            |
| -------------- | -------------------------- | ------------------------------ |
| **Purpose**    | Tool integration           | Agent coordination             |
| **Connects**   | Agent → External Tools     | Agent → Other Agents           |
| **Routing**    | Direct tool calls          | Semantic matching              |
| **Protocol**   | MCP standard               | Google A2A                     |
| **Example**    | GitHub, Slack, Filesystem  | Supervisor → Workers           |
| **Use Case**   | Single agent, many tools   | Multiple agents, complex tasks |
| **Complexity** | Low (just add mcp_servers) | Medium (define workers)        |

### Can you use both?

**Yes!** Combine MCP and A2A for maximum flexibility:

```python
from kaizen.agents import CodeGenerationAgent, RAGResearchAgent
from kaizen.agents.coordination.supervisor_worker import SupervisorWorkerPattern

# Each worker has MCP tool access
code_expert = CodeGenerationAgent(
    config,
    mcp_servers=["github"]  # Can create PRs, issues
)

data_expert = RAGResearchAgent(
    config,
    mcp_servers=["filesystem", "postgres"]  # Can read files, query DB
)

# A2A coordination between MCP-enabled agents
pattern = SupervisorWorkerPattern(
    supervisor=supervisor,
    workers=[code_expert, data_expert]
)

result = pattern.execute_task(
    "Query the database for performance issues, analyze the code, "
    "create an optimized version, and submit a GitHub PR"
)

# Combines both protocols:
# 1. A2A: Supervisor routes "query database" → data_expert
# 2. MCP: data_expert uses postgres MCP server → run query
# 3. A2A: Supervisor routes "optimize code" → code_expert
# 4. MCP: code_expert uses github MCP server → create PR
```

**Decision Matrix**:

| Scenario                        | Use MCP | Use A2A | Use Both |
| ------------------------------- | ------- | ------- | -------- |
| Single agent + external tools   | ✅      | ❌      | ❌       |
| Multi-agent + no external tools | ❌      | ✅      | ❌       |
| Multi-agent + external tools    | ❌      | ❌      | ✅       |
| Simple tasks                    | ✅      | ❌      | ❌       |
| Complex multi-stage tasks       | ❌      | ✅      | ✅       |

---

## Choosing the Right Agent Type

Kaizen provides multiple agent types, each optimized for specific use cases.

### Decision Tree

```
Start: What kind of task?
│
├─ Simple Q&A? → SimpleQAAgent
│
├─ Need reasoning steps? → ChainOfThoughtAgent
│
├─ Need tool calling? → ReActAgent
│
├─ Generate code? → CodeGenerationAgent
│
├─ Research/Analysis? → RAGResearchAgent
│
├─ Process images? → VisionAgent
│
├─ Transcribe audio? → TranscriptionAgent
│
├─ Long-running (1-4 hours)? → BaseAutonomousAgent
│
├─ Coding (4-30 hours)? → ClaudeCodeAgent
│
├─ Bug fix + PR (5-30 min)? → CodexAgent
│
└─ Multiple agents needed? → SupervisorWorkerPattern
```

### Agent Comparison Matrix

| Agent Type              | Use Case        | Duration | Tools?   | Autonomous?   | Cost   |
| ----------------------- | --------------- | -------- | -------- | ------------- | ------ |
| **SimpleQAAgent**       | Basic Q&A       | 1-5s     | Optional | No            | $      |
| **ChainOfThoughtAgent** | Reasoning       | 5-15s    | Optional | No            | $$     |
| **ReActAgent**          | Tool calling    | 30s-5min | Required | Yes (limited) | $$$    |
| **CodeGenerationAgent** | Code generation | 10s-2min | Optional | No            | $$$    |
| **RAGResearchAgent**    | Research        | 1-10min  | Optional | No            | $$$    |
| **VisionAgent**         | Image analysis  | 5-30s    | Optional | No            | $$$    |
| **TranscriptionAgent**  | Audio → text    | 10s-2min | No       | No            | $$     |
| **BaseAutonomousAgent** | General tasks   | 1-4hrs   | Required | Yes           | $$$$$  |
| **ClaudeCodeAgent**     | Large refactors | 4-30hrs  | Required | Yes           | $$$$$$ |
| **CodexAgent**          | Bug fixes + PR  | 5-30min  | Required | Yes           | $$$$   |

### Selection Guide

**Start here**:

1. **Need simple answer?** → SimpleQAAgent
2. **Need reasoning?** → ChainOfThoughtAgent
3. **Need actions?** → ReActAgent
4. **Generate code?** → CodeGenerationAgent
5. **Research documents?** → RAGResearchAgent
6. **Process images?** → VisionAgent
7. **Long autonomous task?** → BaseAutonomousAgent
8. **Large refactor?** → ClaudeCodeAgent
9. **Bug fix + PR?** → CodexAgent
10. **Multiple agents?** → SupervisorWorkerPattern

**Rule of thumb**:

- Tasks < 5 minutes → Single-shot agents (SimpleQA, CoT, CodeGen)
- Tasks 5-30 minutes → ReAct or Codex
- Tasks 1-4 hours → BaseAutonomous
- Tasks 4-30 hours → ClaudeCode
- Multi-stage tasks → SupervisorWorker

---

## Tool Integration Strategy

Kaizen provides multiple approaches to tool integration. Choose based on your needs.

### Three Levels of Tool Integration

#### Level 1: No Tools (Pure LLM)

**When to use**: Simple Q&A, reasoning tasks, no external actions needed

**Example**:

```python
from kaizen.agents import SimpleQAAgent

agent = SimpleQAAgent()  # No tool_registry
result = agent.ask("Explain quantum computing")
# Pure LLM response, no actions
```

**Pros**:

- ✅ Simplest setup
- ✅ Fastest execution
- ✅ Cheapest cost

**Cons**:

- ❌ No file access
- ❌ No API calls
- ❌ No bash execution

#### Level 2: Builtin Tools (12 Tools)

**When to use**: 90% of use cases - file ops, HTTP, bash, web access

**Example**:

```python
# Tools auto-configured via MCP

# 12 builtin tools enabled via MCP

agent = ReActAgent(config, tools="all"  # Enable 12 builtin tools via MCP
result = agent.run("Read config.yaml and validate schema")
# Agent can now read files, make HTTP calls, etc.
```

**Available tools**:

- File operations (5): read_file, write_file, delete_file, list_directory, file_exists
- HTTP operations (4): http_get, http_post, http_put, http_delete
- Bash execution (1): bash_command
- Web access (2): fetch_url, extract_links

**Pros**:

- ✅ One-line setup
- ✅ Production-ready
- ✅ Covers most needs

**Cons**:

- ❌ Limited to 12 tools
- ❌ No specialized tools (GitHub, Slack, etc.)

#### Level 3: MCP Servers (Unlimited Tools)

**When to use**: Need specialized tools (GitHub, Slack, databases, etc.)

**Example**:

```python
from kaizen.agents import ReActAgent

agent = ReActAgent(
    config,
    tools="all"  # Enable 12 builtin tools via MCP
    mcp_servers=["github", "slack", "postgres"]  # + MCP tools
)

result = agent.run(
    "Query user table for inactive users, create GitHub issues for each, "
    "and notify team in Slack"
)

# Agent has access to:
# - 12 builtin tools
# - 50+ GitHub tools
# - 20+ Slack tools
# - 30+ PostgreSQL tools
# Total: 110+ tools
```

**Pros**:

- ✅ Unlimited tool ecosystem
- ✅ Community-built servers
- ✅ Specialized capabilities

**Cons**:

- ❌ Requires MCP server installation
- ❌ More complex setup
- ❌ Potential version conflicts

### Tool Selection Decision Tree

```
Start: What do you need?
│
├─ No external actions? → Level 1 (No tools)
│
├─ File/HTTP/Bash/Web? → Level 2 (Builtin tools)
│
├─ GitHub/Slack/DB? → Level 3 (MCP servers)
│
└─ Custom domain logic? → Custom tools
```

### Best Practices

**1. Start Simple, Add Complexity**

```python
# Start: No tools
agent = SimpleQAAgent()

# Add: Builtin tools (if needed)
agent = ReActAgent(config, tools="all"  # Enable 12 builtin tools via MCP

# Add: MCP servers (if needed)
agent = ReActAgent(config, tools="all"  # Enable 12 builtin tools via MCP
```

**2. Minimize Tool Surface Area**

```python
# ❌ BAD: Give all agents all tools
all_tools_agent = ReActAgent(config, tools="all"  # Enable tools via MCP

# ✅ GOOD: Give each agent only needed tools
file_agent = ReActAgent(config, tools="all"  # Enable tools via MCP
api_agent = ReActAgent(config, tools="all"  # Enable tools via MCP
```

**3. Use Danger Levels Appropriately**

```python
# SAFE: Auto-execute
registry.register_tool("read_file", read_fn, danger_level=ToolDangerLevel.SAFE)

# MODERATE: Ask once per session
registry.register_tool("http_post", post_fn, danger_level=ToolDangerLevel.MODERATE)

# DANGEROUS: Ask every time
registry.register_tool("delete_file", delete_fn, danger_level=ToolDangerLevel.DANGEROUS)

# CRITICAL: Explicit confirmation required
registry.register_tool("bash_command", bash_fn, danger_level=ToolDangerLevel.CRITICAL)
```

---

# Part 4: Production Deployment

This part covers testing, monitoring, and deploying Kaizen agents to production.

## Testing Strategy

Kaizen uses a **3-tier testing strategy** with a **NO MOCKING policy** for Tiers 2-3.

### The 3-Tier Philosophy

**Why 3 tiers?** Different test goals require different approaches:

- **Tier 1 (Unit)**: Fast feedback during development
- **Tier 2 (Integration)**: Validate real behavior with free/local infrastructure
- **Tier 3 (End-to-End)**: Production validation with paid services

### Tier 1: Unit Tests (Mocked LLM)

**Purpose**: Fast feedback for logic validation

**Characteristics**:

- ✅ Mock LLM providers
- ✅ Fast execution (<1s per test)
- ✅ Run on every code change
- ✅ No external dependencies

**Example**:

```python
import pytest
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

def test_qa_agent_initialization():
    """Test agent initialization."""
    config = QAConfig(
        llm_provider="mock",  # Use mock provider
        model="gpt-4"
    )
    agent = SimpleQAAgent(config)
    assert agent is not None
    assert agent.signature is not None

def test_qa_agent_ask_method():
    """Test ask method with mock LLM."""
    config = QAConfig(llm_provider="mock")
    agent = SimpleQAAgent(config)

    result = agent.ask("What is 2+2?")

    # Validate structure (not content, since mocked)
    assert "answer" in result
    assert isinstance(result["answer"], str)
```

**Run Tier 1 tests**:

```bash
pytest tests/unit/ -v
```

### Tier 2: Integration Tests (Real Ollama)

**Purpose**: Validate real LLM behavior with free/local infrastructure

**Characteristics**:

- ✅ Real Ollama inference (local, free)
- ✅ NO MOCKING (real infrastructure only)
- ✅ Moderate speed (~5-10s per test)
- ✅ Run before commits

**Setup**:

```bash
# Install Ollama
curl https://ollama.ai/install.sh | sh

# Pull models
ollama pull llama2
ollama pull bakllava  # For vision tests
```

**Example**:

```python
import pytest
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

@pytest.mark.integration
def test_qa_agent_real_inference():
    """Test real Ollama inference."""
    config = QAConfig(
        llm_provider="ollama",
        model="llama2"
    )
    agent = SimpleQAAgent(config)

    # Real inference
    result = agent.ask("What is the capital of France?")

    # Validate real answer
    assert "answer" in result
    answer = result["answer"].lower()
    assert "paris" in answer  # Real LLM should know this
```

**Run Tier 2 tests**:

```bash
# Requires Ollama running locally
pytest tests/integration/ -v -m integration
```

### Tier 3: End-to-End Tests (Real OpenAI)

**Purpose**: Production validation with paid services

**Characteristics**:

- ✅ Real OpenAI/Anthropic APIs (paid)
- ✅ NO MOCKING (production infrastructure)
- ✅ Slow (~10-30s per test)
- ✅ Run before releases

**Setup**:

```bash
# Add API keys to .env
echo "OPENAI_API_KEY=sk-..." >> .env
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env
```

**Example**:

```python
import pytest
from kaizen.agents import SimpleQAAgent, VisionAgent
from kaizen.agents.specialized.simple_qa import QAConfig
from kaizen.agents.vision import VisionAgentConfig

@pytest.mark.e2e
def test_qa_agent_openai_gpt4():
    """Test real OpenAI GPT-4 inference."""
    config = QAConfig(
        llm_provider="openai",
        model="gpt-4"
    )
    agent = SimpleQAAgent(config)

    result = agent.ask("Explain quantum entanglement in one sentence.")

    assert "answer" in result
    answer = result["answer"]
    assert len(answer) > 20  # Should be substantive
    assert any(word in answer.lower() for word in ["quantum", "particles", "correlated"])

@pytest.mark.e2e
@pytest.mark.vision
def test_vision_agent_gpt4v():
    """Test real GPT-4V vision inference."""
    config = VisionAgentConfig(
        llm_provider="openai",
        model="gpt-4-vision-preview"
    )
    agent = VisionAgent(config=config)

    result = agent.analyze(
        image="tests/fixtures/sample_receipt.jpg",
        question="What is the total amount on this receipt?"
    )

    assert "answer" in result
    # Validate extracted amount matches expected
```

**Run Tier 3 tests**:

```bash
# Requires API keys in .env
pytest tests/integration/ -v -m e2e

# Or run specific vision tests
pytest tests/integration/ -v -m "e2e and vision"
```

### Test Organization

```
tests/
├── unit/                   # Tier 1: Mocked tests
│   ├── agents/                # Agent logic tests
│   ├── core/                  # Core functionality tests
│   ├── signatures/            # Signature tests
│   └── tools/                 # Tool tests
│
├── integration/            # Tiers 2-3: Real infrastructure
│   ├── test_ollama_validation.py      # Tier 2: Ollama
│   ├── test_multi_modal_integration.py # Tier 3: OpenAI
│   └── test_coordination_integration.py # Tier 3: Multi-agent
│
└── fixtures/               # Test data
    ├── images/                # Sample images
    ├── audio/                 # Sample audio
    └── documents/             # Sample documents
```

### Testing Best Practices

**1. Test Naming Convention**

```python
# Unit tests
def test_[component]_[scenario]():
    """Test [component] [scenario]."""

# Integration tests
@pytest.mark.integration
def test_[component]_[scenario]_real_inference():
    """Test [component] [scenario] with real Ollama."""

# E2E tests
@pytest.mark.e2e
def test_[component]_[scenario]_production():
    """Test [component] [scenario] with production APIs."""
```

**2. Use Fixtures for Reusable Setup**

```python
# tests/conftest.py
import pytest
from kaizen.agents.specialized.simple_qa import QAConfig

@pytest.fixture
def qa_config_mock():
    """Mock QA config for unit tests."""
    return QAConfig(llm_provider="mock")

@pytest.fixture
def qa_config_ollama():
    """Ollama QA config for integration tests."""
    return QAConfig(llm_provider="ollama", model="llama2")

@pytest.fixture
def qa_config_openai():
    """OpenAI QA config for E2E tests."""
    return QAConfig(llm_provider="openai", model="gpt-4")
```

**3. Test Markers for Selective Execution**

```python
# pytest.ini or pyproject.toml
[tool.pytest.ini_options]
markers = [
    "unit: Unit tests with mocked dependencies",
    "integration: Integration tests with real Ollama",
    "e2e: End-to-end tests with production APIs",
    "vision: Vision-related tests",
    "audio: Audio-related tests",
    "slow: Slow tests (>10s)"
]

# Run specific categories
# Fast feedback: pytest -m unit
# Pre-commit: pytest -m "unit or integration"
# Pre-release: pytest
```

### Cost Control for Tier 3

**Budget Management**:

```python
# Set test budget
MAX_E2E_TESTS_PER_RUN = 20  # Limit E2E tests
MAX_COST_PER_TEST = 0.10    # $0.10 per test

# Use pytest markers to limit scope
@pytest.mark.e2e
@pytest.mark.limit(count=5)  # Only run 5 most critical tests
def test_critical_production_feature():
    pass
```

**Prefer Tier 2 (Ollama) when possible**:

```python
# ✅ GOOD: Test with Ollama first
@pytest.mark.integration
def test_agent_behavior_ollama():
    """Test agent with free Ollama."""
    config = QAConfig(llm_provider="ollama", model="llama2")
    agent = SimpleQAAgent(config)
    # Test behavior...

# Only test with OpenAI if Ollama-specific issue
@pytest.mark.e2e
@pytest.mark.skip(reason="Ollama test sufficient for this scenario")
def test_agent_behavior_openai():
    """Test agent with paid OpenAI."""
    pass
```

---

## Monitoring & Observability

### Built-in Monitoring

Every Kaizen agent has built-in monitoring via transparency system:

```python
from kaizen.agents import SimpleQAAgent

agent = SimpleQAAgent(config)

# After execution
result = agent.ask("What is AI?")

# Built-in metrics
print(agent.metrics)
# {
#     "total_calls": 1,
#     "total_tokens": 245,
#     "total_cost": 0.00245,
#     "avg_latency_ms": 1250,
#     "error_rate": 0.0
# }
```

### Custom Monitoring

**1. Structured Logging**

```python
import logging
from kaizen.agents import SimpleQAAgent

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

agent = SimpleQAAgent(config)

# Logs automatically include:
# - Agent type
# - Execution time
# - Token usage
# - Errors
```

**2. Performance Tracking**

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.utils.performance import PerformanceTracker

class MonitoredAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config, signature=signature)
        self.perf_tracker = PerformanceTracker()

    def ask(self, question: str):
        with self.perf_tracker.track("ask"):
            result = self.run(question=question)

        # Log metrics
        metrics = self.perf_tracker.get_metrics()
        logger.info(f"Performance: {metrics}")

        return result
```

**3. Integration with External Tools**

**Prometheus**:

```python
from prometheus_client import Counter, Histogram
from kaizen.agents import SimpleQAAgent

# Define metrics
agent_requests = Counter('agent_requests_total', 'Total agent requests')
agent_latency = Histogram('agent_latency_seconds', 'Agent latency')
agent_errors = Counter('agent_errors_total', 'Total agent errors')

class MetricsAgent(SimpleQAAgent):
    def ask(self, question: str):
        agent_requests.inc()

        with agent_latency.time():
            try:
                result = super().ask(question)
            except Exception as e:
                agent_errors.inc()
                raise

        return result
```

**DataDog**:

```python
from datadog import statsd
from kaizen.agents import SimpleQAAgent

class DataDogAgent(SimpleQAAgent):
    def ask(self, question: str):
        with statsd.timed('agent.ask.duration'):
            result = super().ask(question)

        # Track metrics
        statsd.increment('agent.ask.count')
        statsd.gauge('agent.tokens', result.get('token_count', 0))

        return result
```

### Health Checks

```python
from kaizen.agents import SimpleQAAgent
from fastapi import FastAPI

app = FastAPI()
agent = SimpleQAAgent(config)

@app.get("/health")
def health_check():
    """Agent health check endpoint."""
    try:
        # Quick inference test
        result = agent.ask("Test")
        return {"status": "healthy", "agent": "operational"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.get("/metrics")
def metrics():
    """Expose agent metrics."""
    return {
        "total_requests": agent.metrics["total_calls"],
        "avg_latency_ms": agent.metrics["avg_latency_ms"],
        "error_rate": agent.metrics["error_rate"],
        "uptime_seconds": agent.metrics["uptime"]
    }
```

---

## Performance Optimization

### 1. Model Selection

**Cost vs Quality Tradeoff**:

| Model           | Cost/1M tokens | Speed  | Quality   | Use Case                  |
| --------------- | -------------- | ------ | --------- | ------------------------- |
| GPT-3.5-turbo   | $0.50          | Fast   | Good      | Development, simple tasks |
| GPT-4           | $30.00         | Slow   | Excellent | Production, complex tasks |
| Claude 3 Sonnet | $3.00          | Fast   | Very Good | Production, balanced      |
| Claude 3 Opus   | $15.00         | Medium | Excellent | Critical tasks            |
| Ollama (llama2) | Free           | Fast   | Good      | Development, testing      |

**Pattern**: Start with GPT-3.5, upgrade to GPT-4/Claude for production:

```python
import os

# Development: Use cheap model
if os.getenv("ENVIRONMENT") == "development":
    config = QAConfig(llm_provider="ollama", model="llama2")
# Production: Use quality model
else:
    config = QAConfig(llm_provider="openai", model="gpt-4")

agent = SimpleQAAgent(config)
```

### 2. Prompt Optimization

**Use Signatures for Efficiency**:

```python
# ❌ BAD: Verbose manual prompt
prompt = """
You are a helpful AI assistant. Please answer the following question accurately and concisely.
Provide your confidence level and cite sources if applicable.

Question: {question}

Please format your response as:
Answer: [your answer]
Confidence: [0.0-1.0]
Sources: [list of sources]
"""

# ✅ GOOD: Signature-based (auto-optimized)
class QASignature(Signature):
    question: str = InputField(desc="User question")
    answer: str = OutputField(desc="Concise answer")
    confidence: float = OutputField(desc="Confidence (0.0-1.0)")
    sources: list = OutputField(desc="Sources", default=[])
```

### 3. Caching

**Response Caching**:

```python
from functools import lru_cache
from kaizen.agents import SimpleQAAgent

class CachedAgent(SimpleQAAgent):
    @lru_cache(maxsize=1000)
    def ask(self, question: str):
        """Cached ask method."""
        return super().ask(question)

# Identical questions use cache
agent = CachedAgent(config)
result1 = agent.ask("What is AI?")  # LLM call
result2 = agent.ask("What is AI?")  # Cache hit (free)
```

**Workflow Caching**:

```python
from kailash.workflow.builder import WorkflowBuilder

# Convert agent to workflow
agent = SimpleQAAgent(config)
workflow = agent.to_workflow()

# Cache compiled workflow
cached_workflow = workflow.build()  # Compile once

# Reuse across requests
runtime = LocalRuntime()
result1 = runtime.execute(cached_workflow)  # Fast
result2 = runtime.execute(cached_workflow)  # Fast (reuses compiled)
```

### 4. Batch Processing

**Process Multiple Requests Together**:

```python
from kaizen.agents import SimpleQAAgent

agent = SimpleQAAgent(config)

# ❌ BAD: Sequential processing
for question in questions:
    result = agent.ask(question)  # 100 LLM calls

# ✅ GOOD: Batch processing
batch_prompt = "\n".join([f"Q{i}: {q}" for i, q in enumerate(questions)])
batch_result = agent.ask(f"Answer all questions:\n{batch_prompt}")
```

### 5. Async Execution

**Use Async for Parallel Requests**:

```python
import asyncio
from kaizen.agents import SimpleQAAgent

agent = SimpleQAAgent(config)

# Sequential (slow)
def process_sequential(questions):
    return [agent.ask(q) for q in questions]  # 10s per question = 100s total

# Parallel (fast)
async def process_parallel(questions):
    tasks = [agent.ask_async(q) for q in questions]
    return await asyncio.gather(*tasks)  # 10s total (parallel)

# 10x speedup
questions = ["Q1", "Q2", "Q3", ..., "Q10"]
results = asyncio.run(process_parallel(questions))  # 10s (not 100s)
```

---

## Deployment Patterns

### 1. FastAPI Deployment

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from kaizen.agents import SimpleQAAgent
from kaizen.agents.specialized.simple_qa import QAConfig

# Initialize agent
config = QAConfig(
    llm_provider="openai",
    model="gpt-4"
)
agent = SimpleQAAgent(config)

# FastAPI app
app = FastAPI(title="Kaizen AI Agent API")

class QuestionRequest(BaseModel):
    question: str
    session_id: str = None

class QuestionResponse(BaseModel):
    answer: str
    confidence: float = None

@app.post("/ask", response_model=QuestionResponse)
async def ask_question(request: QuestionRequest):
    """Ask agent a question."""
    try:
        result = agent.ask(
            request.question,
            session_id=request.session_id
        )
        return QuestionResponse(
            answer=result["answer"],
            confidence=result.get("confidence")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "healthy"}

# Run: uvicorn app:app --host 0.0.0.0 --port 8000
```

### 2. Docker Deployment

**Dockerfile**:

```dockerfile
FROM python:3.11-slim

# Install dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Environment
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Expose port
EXPOSE 8000

# Run
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**docker-compose.yml**:

```yaml
version: "3.8"

services:
  kaizen-agent:
    build: .
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - ENVIRONMENT=production
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped
```

**Deploy**:

```bash
# Build and run
docker-compose up -d

# Scale horizontally
docker-compose up -d --scale kaizen-agent=3
```

### 3. Kubernetes Deployment

**deployment.yaml**:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kaizen-agent
spec:
  replicas: 3
  selector:
    matchLabels:
      app: kaizen-agent
  template:
    metadata:
      labels:
        app: kaizen-agent
    spec:
      containers:
        - name: kaizen-agent
          image: your-registry/kaizen-agent:latest
          ports:
            - containerPort: 8000
          env:
            - name: OPENAI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: api-keys
                  key: openai
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: api-keys
                  key: anthropic
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: kaizen-agent-service
spec:
  selector:
    app: kaizen-agent
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8000
  type: LoadBalancer
```

**Deploy**:

```bash
# Create secrets
kubectl create secret generic api-keys \
  --from-literal=openai=$OPENAI_API_KEY \
  --from-literal=anthropic=$ANTHROPIC_API_KEY

# Deploy
kubectl apply -f deployment.yaml

# Check status
kubectl get pods
kubectl logs -f deployment/kaizen-agent
```

### 4. Nexus Multi-Channel Deployment

**Best for**: Deploying as API + CLI + MCP simultaneously

```python
from nexus import Nexus
from kaizen.agents import SimpleQAAgent

# Create Nexus platform
nexus = Nexus(
    title="AI Q&A Platform",
    enable_api=True,    # FastAPI server
    enable_cli=True,    # CLI interface
    enable_mcp=True     # MCP server for AI assistants
)

# Deploy Kaizen agent
agent = SimpleQAAgent(QAConfig())
agent_workflow = agent.to_workflow()
nexus.register("qa_agent", agent_workflow.build())

# Run (exposes all channels)
nexus.run(port=8000)

# Available on all channels:
# 1. API: POST http://localhost:8000/workflows/qa_agent
# 2. CLI: nexus run qa_agent --question "What is AI?"
# 3. MCP: qa_agent tool for Claude Desktop, Cline, etc.
```

---

## Summary

You've completed the Kaizen Developer Workflow Guide! Here's what you've learned:

### Part 1: Understanding Kaizen

- Why Kaizen exists (problems it solves)
- 5 core principles (signatures, workflows, patterns, defaults, progressive complexity)
- 5 state-of-the-art patterns (convergence, autonomy, A2A, tools, multi-modal)

### Part 2: Quick Start Journey

- Your first agent (5 minutes)
- Adding tools (10 minutes)
- Multi-agent coordination (15 minutes)
- Autonomous agents (20 minutes)

### Part 3: Architecture Decisions

- When to use MCP vs A2A
- Choosing the right agent type (10 agents)
- Tool integration strategy (3 levels)

### Part 4: Production Deployment

- 3-tier testing strategy (NO MOCKING in Tiers 2-3)
- Monitoring & observability (built-in + custom)
- Performance optimization (5 techniques)
- Deployment patterns (FastAPI, Docker, Kubernetes, Nexus)

## Next Steps

1. **Try Examples**: Browse `examples/` directory for 35+ working implementations
2. **Read API Docs**: Dive into `docs/reference/api-reference.md` for complete API
3. **Join Community**: Share your agents and learn from others
4. **Build**: Start with SimpleQAAgent, progressively add complexity

## Resources

- **Documentation**: [docs/](../README.md)
- **Examples**: [examples/](../../examples/)
- **API Reference**: [docs/reference/api-reference.md](../reference/api-reference.md)
- **Troubleshooting**: [docs/reference/troubleshooting.md](../reference/troubleshooting.md)

---

**Happy Building!** 🚀

_This guide was created for Kaizen v0.2.0, built on Kailash Core SDK v0.9.25_
