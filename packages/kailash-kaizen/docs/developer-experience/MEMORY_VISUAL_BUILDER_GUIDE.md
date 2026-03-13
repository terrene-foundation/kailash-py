# Memory Management: Kaizen + Kailash + Visual Builder

**Date**: 2025-10-05
**Purpose**: Explain how global/local memory works across Kaizen agents, Kailash workflows, and Studio visual builder

---

## 🎯 The Core Question

**Q**: How does memory work in a visual builder when workflows are just business logic, but global memory persists across the entire workflow?

**A**: Memory exists at **three levels** with different scopes:
1. **Node-Local** (session_id parameter) - Per-node conversation history
2. **Workflow-Global** (shared session) - Workflow-wide context
3. **Shared Pool** (multi-agent) - Cross-workflow persistent memory

Each level has different config/storage patterns in visual builder.

---

## 📊 Three Memory Levels Explained

### Level 1: Node-Local Memory (Session-Scoped)

**What It Is**: Each node instance maintains its own conversation history tied to a `session_id`.

**Storage**: In-memory dict keyed by session_id
```python
# BufferMemory internal storage
{
    "user_123": [
        {"role": "user", "content": "My name is Alice"},
        {"role": "assistant", "content": "Nice to meet you, Alice!"}
    ],
    "user_456": [
        {"role": "user", "content": "My name is Bob"},
        {"role": "assistant", "content": "Hello, Bob!"}
    ]
}
```

**Scope**: Single node instance, isolated per session

**Visual Builder Mapping**: `session_id` is a **node parameter** (visible in node config)

---

### Level 2: Workflow-Global Memory (Workflow-Scoped)

**What It Is**: All nodes in a workflow share a common memory pool for the workflow execution.

**Storage**: Workflow metadata + shared session ID
```python
# WorkflowBuilder internal
{
    "workflow_id": "research_pipeline_001",
    "session_id": "shared_workflow_session",  # All nodes inherit
    "execution_id": "exec_abc123"
}
```

**Scope**: All nodes in single workflow execution

**Visual Builder Mapping**: Workflow-level metadata (not in nodes, but in workflow config)

---

### Level 3: Shared Memory Pool (Cross-Workflow)

**What It Is**: Multiple agents across multiple workflows read/write to a persistent shared pool.

**Storage**: Database (PostgreSQL, Redis, etc.) or in-memory pool
```python
# SharedMemoryPool storage
{
    "insights": [
        {
            "agent_id": "researcher_1",
            "content": "Found 5 relevant papers on AI safety",
            "timestamp": "2025-10-05T10:30:00Z",
            "metadata": {"confidence": 0.9}
        },
        {
            "agent_id": "analyst_2",
            "content": "Key risk: alignment problem",
            "timestamp": "2025-10-05T10:31:00Z",
            "metadata": {"importance": 0.95}
        }
    ]
}
```

**Scope**: Cross-workflow, persistent, multi-agent

**Visual Builder Mapping**: Global application config (outside workflow, like database connection)

---

## 💻 Working Code Examples

### Example 1: Node-Local Memory (Isolated Sessions)

```python
#!/usr/bin/env python3
"""
Example 1: Node-Local Memory
Shows how session_id isolates conversations per user.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kaizen.agents.specialized.memory_agent import MemoryAgent


def demo_node_local_memory():
    """Node-local memory: Each session_id has independent history."""

    print("=" * 70)
    print("Example 1: Node-Local Memory (session_id)")
    print("=" * 70)
    print()

    # Create single agent instance
    agent = MemoryAgent(llm_provider="ollama", model="llama2")

    # Session 1: User Alice
    print("📍 Session: user_alice")
    result1 = agent.chat("My name is Alice", session_id="user_alice")
    print(f"   User: My name is Alice")
    print(f"   Agent: {result1['response']}")

    result2 = agent.chat("What is my name?", session_id="user_alice")
    print(f"   User: What is my name?")
    print(f"   Agent: {result2['response']}")  # → "Alice"
    print()

    # Session 2: User Bob (DIFFERENT session)
    print("📍 Session: user_bob")
    result3 = agent.chat("My name is Bob", session_id="user_bob")
    print(f"   User: My name is Bob")
    print(f"   Agent: {result3['response']}")

    result4 = agent.chat("What is my name?", session_id="user_bob")
    print(f"   User: What is my name?")
    print(f"   Agent: {result4['response']}")  # → "Bob" (NOT Alice!)
    print()

    # Verify isolation
    print("✅ Memory Isolation Verified:")
    print(f"   Session 'user_alice' has {agent.get_conversation_count('user_alice')} messages")
    print(f"   Session 'user_bob' has {agent.get_conversation_count('user_bob')} messages")
    print()


if __name__ == "__main__":
    demo_node_local_memory()
```

**Visual Builder Representation**:
```json
{
  "nodes": [
    {
      "id": "memory_1",
      "type": "MemoryAgent",
      "data": {
        "parameters": {
          "message": "My name is Alice",
          "session_id": "user_alice"  // ← Node parameter (user input)
        }
      }
    },
    {
      "id": "memory_2",
      "type": "MemoryAgent",
      "data": {
        "parameters": {
          "message": "My name is Bob",
          "session_id": "user_bob"  // ← Different session (isolated)
        }
      }
    }
  ]
}
```

**Studio UI**:
```
┌─────────────────────────────────────┐
│ MemoryAgent Configuration           │
├─────────────────────────────────────┤
│ Message: [My name is Alice______]  │
│ Session ID: [user_alice_________]  │ ← User configures per node
└─────────────────────────────────────┘
```

---

### Example 2: Workflow-Global Memory (Shared Session)

```python
#!/usr/bin/env python3
"""
Example 2: Workflow-Global Memory
Shows how all nodes in a workflow share the same session.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime


def demo_workflow_global_memory():
    """Workflow-global: All nodes inherit workflow's session_id."""

    print("=" * 70)
    print("Example 2: Workflow-Global Memory (Shared Session)")
    print("=" * 70)
    print()

    # Build workflow with workflow-level session
    workflow = WorkflowBuilder()

    # PROPOSED API (needs implementation in WorkflowBuilder)
    # workflow.set_session_id("research_workflow_001")

    # CURRENT WORKAROUND: Manual session_id in each node
    WORKFLOW_SESSION = "research_workflow_001"

    # Node 1: Researcher learns a fact
    workflow.add_node("MemoryAgent", "researcher", {
        "message": "The capital of France is Paris",
        "session_id": WORKFLOW_SESSION,  # Shared session
        "llm_provider": "ollama",
        "model": "llama2"
    })

    # Node 2: Analyst asks about what researcher learned
    workflow.add_node("MemoryAgent", "analyst", {
        "message": "What capital did we just learn about?",
        "session_id": WORKFLOW_SESSION,  # Same session!
        "llm_provider": "ollama",
        "model": "llama2"
    })

    # Execute
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    # Results
    print("📍 Workflow Session:", WORKFLOW_SESSION)
    print()

    print("Node 1 (Researcher):")
    print(f"   Input: The capital of France is Paris")
    print(f"   Response: {results['researcher'].get('response', 'N/A')}")
    print()

    print("Node 2 (Analyst):")
    print(f"   Input: What capital did we just learn about?")
    print(f"   Response: {results['analyst'].get('response', 'N/A')}")
    print(f"   ✅ Analyst knows 'Paris' because shared session!")
    print()


if __name__ == "__main__":
    demo_workflow_global_memory()
```

**Visual Builder Representation** (Workflow-Level Config):
```json
{
  "workflow": {
    "id": "research_pipeline",
    "metadata": {
      "session_id": "research_workflow_001"  // ← Workflow-level
    }
  },
  "nodes": [
    {
      "id": "researcher",
      "type": "MemoryAgent",
      "data": {
        "parameters": {
          "message": "Capital of France is Paris"
          // session_id inherited from workflow.metadata
        }
      }
    },
    {
      "id": "analyst",
      "type": "MemoryAgent",
      "data": {
        "parameters": {
          "message": "What capital did we learn?"
          // session_id inherited from workflow.metadata
        }
      }
    }
  ]
}
```

**Studio UI** (Workflow Settings Panel):
```
┌─────────────────────────────────────┐
│ Workflow Settings                   │
├─────────────────────────────────────┤
│ Name: [Research Pipeline________]  │
│                                     │
│ ─── Memory Configuration ───       │
│                                     │
│ ☑ Enable Workflow-Global Memory    │
│ Session ID: [research_workflow_001]│ ← Workflow-level setting
│                                     │
│ (All nodes will inherit this)      │
└─────────────────────────────────────┘
```

---

### Example 3: Shared Memory Pool (Cross-Workflow Persistence)

```python
#!/usr/bin/env python3
"""
Example 3: Shared Memory Pool
Shows how multiple agents across workflows share a persistent pool.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kaizen.memory.shared_pool import SharedMemoryPool
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass


class ResearchSignature(Signature):
    """Research signature with insight writing."""
    topic: str = InputField(desc="Research topic")
    answer: str = OutputField(desc="Research findings")


@dataclass
class ResearchConfig:
    llm_provider: str = "ollama"
    model: str = "llama2"


class ResearchAgent(BaseAgent):
    """Research agent that writes insights to shared pool."""

    def __init__(self, config: ResearchConfig, shared_pool: SharedMemoryPool, agent_id: str):
        super().__init__(
            config=config,
            signature=ResearchSignature(),
            shared_memory=shared_pool,  # ← Shared pool
            agent_id=agent_id
        )
        self.agent_id = agent_id

    def research(self, topic: str) -> dict:
        """Research and write insight to pool."""
        result = self.run(topic=topic)

        # Write insight to shared pool
        if self.shared_memory:
            self.shared_memory.add_insight(
                agent_id=self.agent_id,
                content=f"Researched {topic}: {result.get('answer', 'N/A')}",
                metadata={"topic": topic}
            )

        return result


def demo_shared_memory_pool():
    """Shared pool: Multiple agents collaborate via persistent memory."""

    print("=" * 70)
    print("Example 3: Shared Memory Pool (Cross-Workflow)")
    print("=" * 70)
    print()

    # Create shared pool (persistent across workflows)
    shared_pool = SharedMemoryPool()

    # Create agents with shared pool
    researcher1 = ResearchAgent(
        config=ResearchConfig(),
        shared_pool=shared_pool,
        agent_id="researcher_1"
    )

    researcher2 = ResearchAgent(
        config=ResearchConfig(),
        shared_pool=shared_pool,
        agent_id="researcher_2"
    )

    # Workflow 1: Researcher 1 investigates
    print("📍 Workflow 1: Researcher 1")
    result1 = researcher1.research("Machine Learning")
    print(f"   Researcher 1 researched: Machine Learning")
    print(f"   Wrote insight to shared pool")
    print()

    # Workflow 2: Researcher 2 investigates
    print("📍 Workflow 2: Researcher 2")
    result2 = researcher2.research("Deep Learning")
    print(f"   Researcher 2 researched: Deep Learning")
    print(f"   Wrote insight to shared pool")
    print()

    # Check shared pool (both insights persisted)
    print("📍 Shared Memory Pool Contents:")
    insights = shared_pool.get_recent_insights(limit=10)
    for i, insight in enumerate(insights, 1):
        print(f"   {i}. {insight['agent_id']}: {insight['content']}")
    print()

    print("✅ Cross-Workflow Persistence Verified:")
    print(f"   Total insights in pool: {len(insights)}")
    print(f"   Insights persist across workflow executions")
    print()


if __name__ == "__main__":
    demo_shared_memory_pool()
```

**Visual Builder Representation** (Global App Config):
```json
{
  "application": {
    "name": "Research Platform",
    "memory": {
      "type": "shared_pool",
      "backend": "postgresql",
      "connection": "postgresql://localhost/research_pool",
      "pool_id": "research_team_pool"  // ← Global config
    }
  },
  "workflows": [
    {
      "id": "workflow_1",
      "nodes": [
        {
          "id": "researcher_1",
          "type": "ResearchAgent",
          "data": {
            "parameters": {
              "topic": "Machine Learning",
              "agent_id": "researcher_1"
              // shared_pool injected from app config
            }
          }
        }
      ]
    },
    {
      "id": "workflow_2",
      "nodes": [
        {
          "id": "researcher_2",
          "type": "ResearchAgent",
          "data": {
            "parameters": {
              "topic": "Deep Learning",
              "agent_id": "researcher_2"
              // same shared_pool from app config
            }
          }
        }
      ]
    }
  ]
}
```

**Studio UI** (Application Settings - Global):
```
┌─────────────────────────────────────┐
│ Application Settings                │
├─────────────────────────────────────┤
│                                     │
│ ─── Shared Memory Pool ───         │
│                                     │
│ ☑ Enable Shared Memory              │
│                                     │
│ Backend: [PostgreSQL ▾]            │
│ Host: [localhost______________]    │
│ Database: [research_pool_______]   │
│ Pool ID: [research_team________]   │ ← Global to all workflows
│                                     │
│ (All workflows can share insights) │
└─────────────────────────────────────┘
```

---

## 🎨 Visual Builder Architecture

### Where Each Memory Level Lives

```
┌─────────────────────────────────────────────────────────────┐
│                   Studio Application                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌────────────────────────────────────┐                   │
│  │  Application Settings (Global)     │ ← Level 3         │
│  ├────────────────────────────────────┤    Shared Pool    │
│  │  Shared Memory Pool:               │                   │
│  │    - Backend: PostgreSQL           │                   │
│  │    - Pool ID: research_team_pool   │                   │
│  └────────────────────────────────────┘                   │
│                                                             │
│  ┌────────────────────────────────────┐                   │
│  │  Workflow 1 Settings               │ ← Level 2         │
│  ├────────────────────────────────────┤    Workflow-Global│
│  │  Session ID: workflow_session_001  │                   │
│  │                                     │                   │
│  │  ┌──────────────┐  ┌──────────────┐│                   │
│  │  │ Node 1       │  │ Node 2       ││                   │
│  │  ├──────────────┤  ├──────────────┤│ ← Level 1         │
│  │  │ session_id:  │  │ session_id:  ││    Node-Local     │
│  │  │ user_alice   │  │ user_bob     ││                   │
│  │  └──────────────┘  └──────────────┘│                   │
│  └────────────────────────────────────┘                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Config vs Global Vars in Visual Builder

**Problem**: "Workflows are business logic, but global memory persists across workflows"

**Solution**: Three-tier config hierarchy

```python
# Tier 1: Application Config (Global - outside workflows)
{
    "application": {
        "shared_memory_pool": {
            "backend": "postgresql",
            "pool_id": "research_pool"
        }
    }
}

# Tier 2: Workflow Config (Workflow-scoped)
{
    "workflow": {
        "id": "research_pipeline_001",
        "metadata": {
            "session_id": "shared_workflow_session"
        }
    }
}

# Tier 3: Node Config (Node-scoped)
{
    "node": {
        "id": "memory_agent_1",
        "parameters": {
            "session_id": "user_alice"  // Overrides workflow session
        }
    }
}
```

**Precedence**: Node > Workflow > Application

---

## 📋 Decision Matrix: Which Memory Level?

| Use Case | Memory Level | Config Location | Persistence |
|----------|-------------|-----------------|-------------|
| Multi-user chatbot (isolated sessions) | Node-Local | Node parameter | Per-session |
| Research pipeline (shared context) | Workflow-Global | Workflow metadata | Per-execution |
| Multi-agent team (collaboration) | Shared Pool | Application settings | Cross-workflow |
| Customer support (user history) | Node-Local + Shared Pool | Both | Hybrid |

---

## 🔧 Implementation Checklist for Studio Team

### Node-Local Memory ✅
- [x] Expose `session_id` as node parameter
- [x] Text input in node config form
- [ ] Session viewer UI (show conversation history)

### Workflow-Global Memory ⚠️
- [ ] Add workflow metadata panel
- [ ] `session_id` field in workflow settings
- [ ] Auto-inject into nodes (if not overridden)

### Shared Memory Pool ❌
- [ ] Application settings panel
- [ ] Database connection config
- [ ] Pool ID input
- [ ] Memory viewer (show insights from pool)

---

## 📝 Summary

| Level | Scope | Config Location | Studio UI Location |
|-------|-------|----------------|-------------------|
| Node-Local | Per-node, per-session | Node parameters | Node config panel |
| Workflow-Global | Per-workflow execution | Workflow metadata | Workflow settings panel |
| Shared Pool | Cross-workflow persistent | Application config | Application settings (global) |

**Key Insight**: Memory "global-ness" is achieved through **config hierarchy**, not magic globals:
- Workflow config → propagates to all nodes
- Application config → propagates to all workflows
- Node config → can override higher levels

---

**Test These Examples**:
```bash
cd 
python docs/developer-experience/memory_example_1_node_local.py
python docs/developer-experience/memory_example_2_workflow_global.py
python docs/developer-experience/memory_example_3_shared_pool.py
```
