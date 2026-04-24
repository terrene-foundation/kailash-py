---
name: decide-framework
description: "Choose between Core SDK, DataFlow, Nexus, and Kaizen frameworks for your Kailash project. Use when asking 'which framework', 'should I use Core SDK or DataFlow', 'Nexus vs Core', 'framework selection', or 'what's the difference between frameworks'."
---

# Framework Selection Guide

Quick decision tree to choose the right Kailash framework: Core SDK, DataFlow, Nexus, or Kaizen.

> **Skill Metadata**
> Category: `cross-cutting` (decision-support)
> Priority: `CRITICAL`
> SDK Version: `0.9.25+`
> Related Skills: [`dataflow-quickstart`](../../02-dataflow/dataflow-quickstart.md), [`nexus-quickstart`](../../03-nexus/nexus-quickstart.md), [`kaizen-baseagent-template`](../../04-kaizen/kaizen-baseagent-template.md)
> Related Subagents: `framework-advisor` (complex architecture), `dataflow-specialist`, `nexus-specialist`, `kaizen-specialist`

## Quick Decision Matrix

| Your Primary Need                        | Choose                | Why                                            |
| ---------------------------------------- | --------------------- | ---------------------------------------------- |
| **Custom workflows, integrations**       | **Core SDK**          | Fine-grained control, 140+ nodes               |
| **Database operations**                  | **DataFlow**          | Zero-config, 11 auto-generated nodes per model |
| **Multi-channel platform** (API+CLI+MCP) | **Nexus**             | Zero-config multi-channel deployment           |
| **AI agents, multi-agent systems**       | **Kaizen**            | Signature-based programming, BaseAgent         |
| **Database + Multi-channel**             | **DataFlow + Nexus**  | Combine frameworks                             |
| **AI + Workflows**                       | **Core SDK + Kaizen** | Custom workflows with AI                       |
| **Complete AI platform**                 | **All 4**             | Full-stack enterprise solution                 |

## Framework Comparison

### Core SDK (`pip install kailash`)

**Foundational building blocks for workflow automation**

**When to Choose:**

- ✅ Building custom workflows and automation
- ✅ Need fine-grained control over execution
- ✅ Integrating with existing systems
- ✅ Creating domain-specific solutions
- ✅ Single-purpose workflows

**Key Components:**

- WorkflowBuilder with 140+ nodes
- LocalRuntime, ParallelRuntime, AsyncLocalRuntime
- String-based node API
- MCP integration built-in

**Example:**

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "reader", {"file_path": "data.csv"})
workflow.add_node("PythonCodeNode", "process", {"code": "result = len(data)"})
workflow.add_connection("reader", "data", "process", "data")

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### DataFlow (`pip install kailash-dataflow`)

**Zero-config database framework built ON Core SDK**

**When to Choose:**

- ✅ Database operations are primary concern
- ✅ Need automatic CRUD node generation
- ✅ Want enterprise database features (pooling, transactions)
- ✅ Building data-intensive applications
- ✅ PostgreSQL or SQLite database

**Key Features:**

- `@db.model` decorator generates 11 nodes per model
- MongoDB-style query syntax
- Multi-tenancy, audit trails, compliance
- Auto-migration system
- **NOT an ORM** - workflow-based

**Example:**

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

db = DataFlow("postgresql://localhost/db")

@db.model
class User:
    name: str
    email: str

# Automatically generates: UserCreateNode, UserReadNode, UserUpdateNode,
# UserDeleteNode, UserListNode, UserBulkCreateNode, etc.

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "email": "alice@example.com"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Nexus (`pip install kailash-nexus`)

**Multi-channel platform built ON Core SDK**

**When to Choose:**

- ✅ Need API + CLI + MCP access simultaneously
- ✅ Want zero-configuration platform deployment
- ✅ Building AI agent integrations (MCP)
- ✅ Require unified session management
- ✅ Enterprise platform deployment

**Key Features:**

- True zero-config: `Nexus()` with no parameters
- Automatic workflow registration
- Unified sessions across all channels
- Progressive enterprise enhancement

**Example:**

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus()  # Zero configuration!

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "process", {
    "code": "result = {'message': 'Hello!'}"
})

app.register("my_workflow", workflow.build())
app.start()  # Now accessible via API, CLI, and MCP!
```

### Kaizen (`pip install kailash-kaizen`)

**AI agent framework built ON Core SDK**

**When to Choose:**

- ✅ Building AI agents with LLMs
- ✅ Multi-agent coordination needed
- ✅ Signature-based programming preferred
- ✅ Multi-modal processing (vision/audio/text)
- ✅ A2A protocol for semantic capability matching

**Key Features:**

- BaseAgent architecture with lazy initialization
- Signature-based I/O (InputField/OutputField)
- SharedMemoryPool for multi-agent coordination
- Automatic A2A capability card generation

**Example:**

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

class QASignature(Signature):
    question: str = InputField(description="User question")
    answer: str = OutputField(description="Answer")

@dataclass
class QAConfig:
    llm_provider: str = os.environ.get("LLM_PROVIDER", "openai")
    model: str = os.environ.get("LLM_MODEL", "")

class QAAgent(BaseAgent):
    def __init__(self, config: QAConfig):
        super().__init__(config=config, signature=QASignature())

    def ask(self, question: str) -> dict:
        return self.run(question=question)

agent = QAAgent(QAConfig())
result = agent.ask("What is machine learning?")
```

## Framework Combinations

### DataFlow + Nexus (Multi-Channel Database App)

Perfect for database applications needing API, CLI, and MCP access:

```python
from dataflow import DataFlow
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

# Step 1: Create Nexus with auto_discovery=False
app = Nexus(auto_discovery=False)

# Step 2: Create DataFlow (defaults work correctly)
db = DataFlow("postgresql://localhost/db")

@db.model
class User:
    name: str
    email: str

# Step 3: Register workflows
workflow = WorkflowBuilder()
workflow.add_node("UserListNode", "list_users", {})
app.register("list_users", workflow.build())

app.start()
```

### Core SDK + Kaizen (AI-Powered Workflows)

Ideal for custom workflows with AI decision-making:

```python
from kailash.workflow.builder import WorkflowBuilder
from kaizen.core.base_agent import BaseAgent

# Kaizen agent for AI processing
agent = QAAgent(config)

# Core SDK workflow for orchestration
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "ai_process", {
    "code": "import os; from openai import OpenAI; client = OpenAI(); resp = client.chat.completions.create(model=os.environ['LLM_MODEL'], messages=messages); result = {'response': resp.choices[0].message.content}",
    "input_variables": ["messages"]
})
```

## Decision Flowchart

```
START: What's your primary use case?
  │
  ├─ Database-heavy application?
  │    YES → DataFlow
  │    │
  │    └─ Need multi-channel access (API/CLI/MCP)?
  │         YES → DataFlow + Nexus
  │         NO → DataFlow alone
  │
  ├─ Multi-channel platform needed?
  │    YES → Nexus
  │    │
  │    └─ Need database operations?
  │         YES → DataFlow + Nexus
  │         NO → Nexus alone
  │
  ├─ AI agent system?
  │    YES → Kaizen
  │    │
  │    └─ Need custom workflow orchestration?
  │         YES → Kaizen + Core SDK
  │         NO → Kaizen alone
  │
  └─ Custom workflows/integrations?
       YES → Core SDK
```

## When to Escalate to Subagent

Use `framework-advisor` subagent when:

- Complex multi-framework architecture needed
- Evaluating migration paths between frameworks
- Enterprise-scale system design
- Need coordination between multiple specialists

Use framework specialists when you've chosen:

- **DataFlow** → `dataflow-specialist` for implementation
- **Nexus** → `nexus-specialist` for deployment
- **Kaizen** → `kaizen-specialist` for AI patterns

## Within-Framework Layer Selection

After choosing your framework, choose your abstraction layer. See `rules/framework-first.md`.

**Rule of thumb**: Start with the Engine layer. Drop to Primitives only when the Engine can't express your need.

| Framework | Start here (Engine) | Drop to this (Primitives) when...         |
| --------- | ------------------- | ----------------------------------------- |
| DataFlow  | `db.express.*`      | Multi-step workflows, custom transactions |
| Nexus     | `Nexus()`           | Custom protocols, non-standard channels   |
| Kaizen    | `Delegate`          | Custom execution loops, non-TAOD agents   |
| PACT      | `GovernanceEngine`  | Custom envelope patterns                  |

## Documentation References

### Framework Documentation

- **Core SDK Overview**: [`CLAUDE.md` (lines 12-17)](../../../../CLAUDE.md#L12-L17)
- **DataFlow Overview**: [`CLAUDE.md` (lines 19-25)](../../../../CLAUDE.md#L19-L25)
- **Nexus Overview**: [`CLAUDE.md` (lines 27-33)](../../../../CLAUDE.md#L27-L33)
- **Kaizen Overview**: [`CLAUDE.md` (lines 35-41)](../../../../CLAUDE.md#L35-L41)
- **Framework Relationships**: [`CLAUDE.md` (lines 43-46)](../../../../CLAUDE.md#L43-L46)

### Detailed Guides

- **Framework Advisor**: [`.claude/agents/implementation/pattern-expert.md`](../../../../.claude/agents/implementation/pattern-expert.md)

## Quick Tips

- 💡 **Start with Core SDK**: If unsure, start with Core SDK and add frameworks later
- 💡 **Frameworks stack**: DataFlow/Nexus/Kaizen are built ON Core SDK, not replacements
- 💡 **Mix and match**: You can use multiple frameworks in the same project
- 💡 **Zero-config first**: Try DataFlow/Nexus zero-config before adding complexity
- 💡 **Consult specialists**: Use framework-specific subagents for detailed implementation

<!--Trigger Keywords: which framework, should I use Core SDK or DataFlow, Nexus vs Core, framework selection, what's the difference between frameworks, choose framework, Core SDK vs DataFlow, DataFlow vs Nexus, framework comparison, best framework for, framework decision -->
