# Kailash Studio Integration: Complete Guide for Visual & Code Users

**Last Updated**: 2025-10-05
**Kaizen Version**: 0.1.0
**Studio Integration Status**: See Gap Analysis Below

---

## 📋 Overview

This guide serves **two distinct audiences**:

### 👥 Part 1: Visual-Only Users (Studio UI/UX)

**Persona**: Business users, data scientists, product managers who use **only** Studio's visual workflow builder

**Goal**: Access all 14 Kaizen agents through drag-and-drop UI without writing any code

**Prerequisites**: None - purely visual/UI-based

**Current Status**: 🚧 **Studio Implementation Needed** (see Gap Analysis)

---

### 💻 Part 2: SDK Developers (Code-First)

**Persona**: Software engineers creating custom agents and registering them for Studio discovery

**Goal**: Build custom agents that are fully discoverable and configurable in Studio's visual builder

**Prerequisites**: Python development, familiarity with Kaizen framework

**Current Status**: ✅ **Fully Documented** (see Developer Guide below)

---

## 🎯 Navigation

- **[Part 1: Visual-Only Users](#part-1-visual-only-users-studio-uiux)** → Studio UI/UX requirements
- **[Part 2: SDK Developers](#part-2-sdk-developers-creating-custom-agents)** → Code-based agent creation
- **[Gap Analysis](#-studio-implementation-gap-analysis)** → What Studio needs to implement

---

# Part 1: Visual-Only Users (Studio UI/UX)

## 🎨 User Journey: Visual Workflow Builder

### Persona: Sarah - Product Manager

- **Background**: Non-technical, familiar with no-code tools
- **Goal**: Build AI workflows without writing code
- **Tools**: Only Kailash Studio (web UI)

### Sarah's Workflow Requirements

1. **Discover** - Browse 14 Kaizen agents in Studio palette
2. **Configure** - Set parameters through form UI (no code)
3. **Compose** - Drag-and-drop agents, connect visually
4. **Execute** - Run workflow and see results in UI
5. **Iterate** - Modify configuration, re-run, refine

---

## 🏗️ Required Studio Features for Visual-Only Users

### Feature 1: Agent Discovery & Palette

**What Sarah Needs**:

- **Node Palette** showing all 14 Kaizen agents
- **Visual Categories** (Specialized, Multi-Modal)
- **Search/Filter** by name, tags, description
- **Agent Preview Cards** with:
  - Icon (database, user-check, shield, etc.)
  - Name (BatchProcessingAgent, HumanApprovalAgent, etc.)
  - Brief description
  - Tags (batch, concurrent, human-in-loop, etc.)
  - Version (1.0.0)

**Implementation Details**:

```
Kailash Studio UI Mockup:

┌─────────────────────────────────────┐
│ 🔍 Search agents...                 │
├─────────────────────────────────────┤
│ 📂 Specialized Agents (11)          │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ 💬 SimpleQAAgent                │ │
│ │ Question answering with         │ │
│ │ confidence scoring              │ │
│ │ Tags: qa, simple                │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ 🗄️ BatchProcessingAgent         │ │
│ │ Concurrent batch processing     │ │
│ │ with high throughput            │ │
│ │ Tags: batch, concurrent         │ │
│ └─────────────────────────────────┘ │
│                                     │
│ 📂 Multi-Modal Agents (3)           │
│ ...                                 │
└─────────────────────────────────────┘
```

**Studio Implementation Checklist**:

- [ ] Read `KAIZEN_AGENTS` dict from `kaizen.agents.nodes`
- [ ] Display agents in left sidebar palette
- [ ] Show icon, name, description, version, tags
- [ ] Implement search/filter by name and tags
- [ ] Group by category (Specialized, Multi-Modal)
- [ ] Drag-and-drop to canvas

---

### Feature 2: Agent Configuration UI (Form-Based)

**What Sarah Needs**:

- **Property Panel** when agent selected
- **Form Fields** for all agent parameters
- **No code required** - all configuration through UI
- **Defaults pre-filled** from agent config
- **Validation** with helpful error messages
- **Environment variable hints** (KAIZEN_LLM_PROVIDER, etc.)

**Example: BatchProcessingAgent Configuration**:

```
Kailash Studio UI Mockup:

┌─────────────────────────────────────┐
│ Properties: BatchProcessingAgent    │
├─────────────────────────────────────┤
│                                     │
│ LLM Configuration                   │
│ ┌─────────────────────────────────┐ │
│ │ Provider: [openai ▼]            │ │
│ │ (Default: KAIZEN_LLM_PROVIDER)  │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ Model: [gpt-3.5-turbo ▼]       │ │
│ │ (Default: KAIZEN_MODEL)         │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ Temperature: [0.1   ]           │ │
│ │ (Range: 0.0-1.0)                │ │
│ └─────────────────────────────────┘ │
│                                     │
│ Batch Configuration                 │
│ ┌─────────────────────────────────┐ │
│ │ Max Concurrent: [10   ]         │ │
│ │ (Default: 10, Max: 100)         │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ Timeout (sec): [30   ]          │ │
│ └─────────────────────────────────┘ │
│                                     │
│ [Apply] [Reset]                     │
└─────────────────────────────────────┘
```

**How Studio Generates Forms**:

1. **Read Agent Signature** (from `BatchProcessingSignature`):

   ```python
   prompt: str = InputField(desc="Data item to process")
   result: str = OutputField(desc="Processed result")
   ```

   → Studio knows: INPUT = "prompt" (string), OUTPUT = "result" (string)

2. **Read Agent Config** (from `BatchProcessingConfig`):

   ```python
   llm_provider: str = "openai"
   model: str = "gpt-3.5-turbo"
   temperature: float = 0.1
   max_concurrent: int = 10
   ```

   → Studio generates form fields with defaults

3. **Read Environment Variable Hints**:
   ```python
   llm_provider: str = field(default_factory=lambda: os.getenv("KAIZEN_LLM_PROVIDER", "openai"))
   ```
   → Studio shows: "(Default: KAIZEN_LLM_PROVIDER)"

**Studio Implementation Checklist**:

- [ ] Parse agent `Signature` for input/output fields
- [ ] Parse agent `Config` dataclass for parameters
- [ ] Generate form UI from config schema
- [ ] Show default values from config
- [ ] Show environment variable hints
- [ ] Validate input (type checking, ranges)
- [ ] Apply configuration to agent instance

---

### Feature 3: Visual Workflow Composition

**What Sarah Needs**:

- **Drag-and-drop canvas** for building workflows
- **Visual connections** between agent outputs and inputs
- **Auto-suggest connections** based on signature compatibility
- **Workflow validation** (missing connections, type mismatches)
- **Save/load workflows** (JSON format)

**Example Workflow: Batch Document Analysis**:

```
Kailash Studio UI Mockup:

Canvas View:
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  ┌──────────────────┐                                  │
│  │ 📥 Input Data    │                                  │
│  │ (CSV/JSON)       │                                  │
│  └────────┬─────────┘                                  │
│           │                                             │
│           │ batch                                       │
│           ▼                                             │
│  ┌──────────────────────────────────┐                  │
│  │ 🗄️ BatchProcessingAgent          │                  │
│  │ Max Concurrent: 20                │                  │
│  │ Provider: openai                  │                  │
│  └────────┬─────────────────────────┘                  │
│           │                                             │
│           │ results                                     │
│           ▼                                             │
│  ┌──────────────────┐                                  │
│  │ 📊 Results       │                                  │
│  │ (Table View)     │                                  │
│  └──────────────────┘                                  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Studio Implementation Checklist**:

- [ ] Drag-and-drop agents from palette to canvas
- [ ] Visual connectors (output → input)
- [ ] Signature-based connection validation
- [ ] Workflow execution order determination
- [ ] Save workflow as JSON (WorkflowBuilder serialization)
- [ ] Load workflow from JSON

---

### Feature 4: Workflow Execution & Monitoring

**What Sarah Needs**:

- **Execute button** to run workflow
- **Real-time progress** (which agent is running)
- **Streaming logs** (agent outputs, errors)
- **Result visualization** (tables, charts, JSON viewer)
- **Error handling UI** (retry, debug, modify)

**Example: Batch Processing Execution**:

```
Kailash Studio UI Mockup:

Execution View:
┌─────────────────────────────────────────────────────────┐
│ 🏃 Running: BatchProcessingAgent                        │
│ Progress: 45/100 items processed (45%)                  │
│                                                         │
│ [████████████░░░░░░░░░░░░░░] 45%                      │
│                                                         │
│ Logs:                                                   │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ [12:34:01] Started batch processing                 │ │
│ │ [12:34:05] Processed item 1-10 (success)            │ │
│ │ [12:34:08] Processed item 11-20 (success)           │ │
│ │ [12:34:11] Processed item 21-30 (success)           │ │
│ │ [12:34:14] Processed item 31-40 (success)           │ │
│ │ [12:34:17] Processing item 41-50...                 │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ Results Preview:                                        │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ Item 1: ✅ Success - "Processed result..."          │ │
│ │ Item 2: ✅ Success - "Processed result..."          │ │
│ │ Item 3: ✅ Success - "Processed result..."          │ │
│ │ ...                                                 │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ [⏸️ Pause] [⏹️ Stop] [📥 Download Results]            │
└─────────────────────────────────────────────────────────┘
```

**Studio Implementation Checklist**:

- [ ] Serialize workflow to WorkflowBuilder code
- [ ] Execute via LocalRuntime or CloudRuntime
- [ ] Stream execution logs to UI (WebSocket)
- [ ] Show progress bars for batch processing
- [ ] Display results in UI (table, JSON, visualization)
- [ ] Handle errors gracefully (show error messages, allow retry)
- [ ] Export results (CSV, JSON download)

---

### Feature 5: Pre-Built Workflow Templates

**What Sarah Needs**:

- **Template Gallery** with common use cases
- **One-click clone** to customize
- **Guided walkthroughs** (tutorial mode)
- **Category organization** (Batch Processing, RAG, Chat, etc.)

**Example Templates**:

```
Kailash Studio UI Mockup:

Template Gallery:
┌─────────────────────────────────────────────────────────┐
│ 🎨 Workflow Templates                                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ 📂 Batch Processing                                     │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 🗄️ Bulk Document Analysis                          │ │
│ │ Process 1000s of documents concurrently             │ │
│ │ Agents: BatchProcessingAgent                        │ │
│ │ [Clone Template]                                    │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ 📂 Human-in-Loop Workflows                              │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ ✅ Content Moderation Pipeline                      │ │
│ │ Generate content → Human approval → Publish         │ │
│ │ Agents: CodeGenerationAgent, HumanApprovalAgent     │ │
│ │ [Clone Template]                                    │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ 📂 High Availability                                    │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 🛡️ Multi-Model Fallback Q&A                        │ │
│ │ GPT-4 → GPT-3.5 → Local fallback                   │ │
│ │ Agents: ResilientAgent                              │ │
│ │ [Clone Template]                                    │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ 📂 Interactive Chat                                     │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 💬 Streaming Chatbot                                │ │
│ │ Real-time token-by-token streaming                  │ │
│ │ Agents: StreamingChatAgent, MemoryAgent             │ │
│ │ [Clone Template]                                    │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ 📂 Quality Improvement                                  │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 🔄 Self-Improving Content Generator                 │ │
│ │ Generate → Critique → Refine (iterative)            │ │
│ │ Agents: SelfReflectionAgent                         │ │
│ │ [Clone Template]                                    │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Studio Implementation Checklist**:

- [ ] Pre-build 10-15 common workflow templates
- [ ] Store templates as JSON (WorkflowBuilder format)
- [ ] Template gallery UI (categorized, searchable)
- [ ] One-click clone to user's workspace
- [ ] Template descriptions and use cases
- [ ] Tutorial mode (step-by-step walkthrough)

---

## 🔧 Studio Implementation Gap Analysis

### ⚠️ CRITICAL: What Studio Needs to Build

This section documents the **complete gap** between current Kaizen capabilities and what Studio needs to provide a visual-only user experience.

---

### Gap 1: Agent Discovery & Registration

**Current State**:

- ✅ 14 Kaizen agents registered in `KAIZEN_AGENTS` dict
- ✅ Each agent has metadata (name, description, version, tags, icon, color)
- ✅ Agents discoverable via `NodeRegistry.list_nodes()`

**Studio Needs to Build**:

- [ ] **Python SDK Integration**: Import `kaizen.agents.nodes.KAIZEN_AGENTS`
- [ ] **Parse Metadata**: Extract name, description, version, tags, icon, color
- [ ] **Node Palette UI**: Visual browser for all agents
- [ ] **Search/Filter**: By name, tags, category
- [ ] **Drag-and-Drop**: From palette to canvas

**Kaizen Provides** (ready to use):

```python
from kaizen.agents.nodes import KAIZEN_AGENTS, list_agents

# Studio can call this
agents = list_agents()
# Returns dict with all metadata

for agent_name, agent_info in agents.items():
    print(f"Icon: {agent_info['icon']}")
    print(f"Color: {agent_info['color']}")
    print(f"Description: {agent_info['description']}")
    print(f"Tags: {agent_info['tags']}")
```

**Implementation Difficulty**: 🟡 Medium (requires Python SDK integration)

---

### Gap 2: Configuration Form Generation

**Current State**:

- ✅ Each agent has `Signature` (InputField/OutputField)
- ✅ Each agent has `Config` dataclass with defaults
- ✅ Environment variable hints in config

**Studio Needs to Build**:

- [ ] **Signature Parser**: Extract InputField/OutputField from agent.signature
- [ ] **Config Parser**: Extract dataclass fields from agent config
- [ ] **Form Generator**: Auto-generate UI forms from schema
- [ ] **Default Values**: Pre-fill from config defaults
- [ ] **Validation**: Type checking, ranges, required fields
- [ ] **Environment Variable UI**: Show KAIZEN\_\* hints

**Kaizen Provides** (ready to inspect):

```python
from kaizen.agents import BatchProcessingAgent

agent_class = BatchProcessingAgent

# Studio can inspect
signature = agent_class.__init__.__annotations__
# Returns: {'llm_provider': Optional[str], 'model': Optional[str], ...}

# Studio can get defaults
import inspect
init_sig = inspect.signature(agent_class.__init__)
for param_name, param in init_sig.parameters.items():
    print(f"{param_name}: default={param.default}")
```

**Implementation Difficulty**: 🔴 Hard (requires Python introspection + form generation)

**Suggested Approach**:

1. Use Python `inspect` module to read agent `__init__` parameters
2. Use `dataclasses.fields()` to read config schema
3. Generate JSON schema from dataclass → Studio renders form
4. Alternative: Kaizen could provide `.to_json_schema()` method

---

### Gap 3: Workflow Serialization & Execution

**Current State**:

- ✅ Kailash `WorkflowBuilder` supports string-based node addition
- ✅ Agents registered and callable via `add_node("AgentName", "id", {...})`
- ✅ `LocalRuntime` executes workflows

**Studio Needs to Build**:

- [ ] **Visual → Code**: Serialize canvas to WorkflowBuilder code
- [ ] **Connection Mapping**: Map visual connections to workflow inputs/outputs
- [ ] **Execution Engine**: Run workflow via LocalRuntime or CloudRuntime
- [ ] **Result Handling**: Parse and display workflow results
- [ ] **Error Handling**: Show errors from failed agents

**Kaizen Provides** (ready to use):

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Studio generates this from visual workflow
workflow = WorkflowBuilder()
workflow.add_node("BatchProcessingAgent", "batch", {
    "llm_provider": "openai",
    "model": "gpt-3.5-turbo",
    "max_concurrent": 20
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
# Studio displays results
```

**Implementation Difficulty**: 🟡 Medium (requires workflow graph → code translation)

---

### Gap 4: Real-Time Execution Monitoring

**Current State**:

- ✅ Agents execute and return results
- ❌ No built-in streaming progress API (yet)

**Studio Needs to Build**:

- [ ] **Progress API**: Stream execution progress to UI
- [ ] **Log Streaming**: Real-time agent logs via WebSocket
- [ ] **Result Streaming**: Progressive result display
- [ ] **Batch Progress**: Show % complete for batch processing
- [ ] **Error Streaming**: Real-time error messages

**Kaizen Could Provide** (future enhancement):

```python
# Potential API for Studio
from kaizen.agents import BatchProcessingAgent

agent = BatchProcessingAgent()

# Stream progress
async for progress in agent.process_batch_stream(batch):
    print(f"Progress: {progress['percent']}%")
    # Studio updates progress bar
```

**Implementation Difficulty**: 🔴 Hard (requires new streaming API in Kaizen)

**Current Workaround**: Studio polls for status or waits for completion

---

### Gap 5: Pre-Built Workflow Templates

**Current State**:

- ✅ 49 example workflows in `/examples/`
- ❌ Not in Studio-consumable format (Python code, not JSON)

**Studio Needs to Build**:

- [ ] **Template Library**: Convert examples to JSON workflows
- [ ] **Template Gallery UI**: Browse, search, preview
- [ ] **Clone Functionality**: Copy template to user workspace
- [ ] **Template Metadata**: Use cases, descriptions, tags

**Kaizen Could Provide** (manual conversion):

```bash
# Convert Python examples to JSON
examples/1-single-agent/batch-processing/workflow.py
→ templates/batch-processing.json

examples/1-single-agent/human-approval/workflow.py
→ templates/human-approval.json

etc.
```

**Implementation Difficulty**: 🟢 Easy (manual conversion of 10-15 key examples)

**Deliverable**: `studio/templates/` directory with JSON workflows

---

## 📊 Gap Summary Table

| Feature                | Kaizen Status | Studio Needs           | Difficulty | Priority |
| ---------------------- | ------------- | ---------------------- | ---------- | -------- |
| Agent Discovery        | ✅ Ready      | Parse KAIZEN_AGENTS    | 🟡 Medium  | P0       |
| Configuration Forms    | ✅ Ready      | Form generator         | 🔴 Hard    | P0       |
| Workflow Serialization | ✅ Ready      | Visual → Code          | 🟡 Medium  | P0       |
| Execution Engine       | ✅ Ready      | Runtime integration    | 🟡 Medium  | P0       |
| Real-Time Monitoring   | ❌ Missing    | Progress streaming API | 🔴 Hard    | P1       |
| Template Library       | 🟡 Partial    | Convert to JSON        | 🟢 Easy    | P1       |
| Result Visualization   | ✅ Ready      | UI components          | 🟡 Medium  | P1       |
| Error Handling UI      | ✅ Ready      | Error display          | 🟢 Easy    | P0       |

**Legend**:

- ✅ Ready - Kaizen provides this
- 🟡 Partial - Kaizen provides some support
- ❌ Missing - Not yet implemented in Kaizen
- P0 - Critical for MVP
- P1 - Important for full experience

---

## 🚀 Recommended Implementation Phases for Studio

### Phase 1: MVP (Visual Discovery + Basic Execution)

**Timeline**: 2-4 weeks

**Deliverables**:

1. ✅ Agent palette (all 14 agents visible)
2. ✅ Basic configuration forms (manual forms, not auto-generated)
3. ✅ Drag-and-drop to canvas
4. ✅ Execute workflow (simple, no streaming)
5. ✅ Display results (JSON viewer)

**Milestone**: Sarah can build and run a BatchProcessingAgent workflow through UI

---

### Phase 2: Enhanced UX (Auto-Forms + Templates)

**Timeline**: 3-5 weeks

**Deliverables**:

1. ✅ Auto-generated configuration forms (from agent schema)
2. ✅ Template gallery (10-15 pre-built workflows)
3. ✅ Visual connections (output → input mapping)
4. ✅ Workflow validation (missing connections, type errors)
5. ✅ Save/load workflows (JSON persistence)

**Milestone**: Sarah can build complex multi-agent workflows from templates

---

### Phase 3: Production-Ready (Monitoring + Optimization)

**Timeline**: 4-6 weeks

**Deliverables**:

1. ✅ Real-time execution monitoring (progress bars, logs)
2. ✅ Result visualization (tables, charts)
3. ✅ Error handling UI (retry, debug)
4. ✅ Performance optimization (lazy loading, caching)
5. ✅ Export workflows (share, version control)

**Milestone**: Sarah can deploy production workflows with full observability

---

## 🎯 Success Metrics for Visual-Only Users

### User Can...

- [ ] **Discover** all 14 Kaizen agents without code
- [ ] **Configure** any agent through form UI (no code)
- [ ] **Build** multi-agent workflows (drag-and-drop)
- [ ] **Execute** workflows and see results
- [ ] **Clone** pre-built templates
- [ ] **Monitor** execution in real-time
- [ ] **Debug** errors through UI
- [ ] **Export** results (CSV, JSON)
- [ ] **Share** workflows with team
- [ ] **Iterate** rapidly (modify, re-run)

### Conversion Metrics

- **Time to First Workflow**: < 5 minutes (from sign-up to execution)
- **Template Usage**: 70%+ users start from template
- **Workflow Completion**: 80%+ workflows execute successfully
- **User Retention**: 60%+ return after first session

---

# Part 2: SDK Developers (Creating Custom Agents)

## 🎯 Quick Start: The Minimal Agent

Here's the **absolute minimum** required for a Studio-compatible agent:

```python
from kailash.nodes.base import NodeMetadata, register_node
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField


class MySignature(Signature):
    """Define inputs and outputs for your agent."""
    input: str = InputField(desc="User input")
    output: str = OutputField(desc="Agent output")


@register_node()  # ✅ Step 1: Register decorator
class MyCustomAgent(BaseAgent):
    """Your custom agent implementation."""

    # ✅ Step 2: Add metadata for Studio
    metadata = NodeMetadata(
        name="MyCustomAgent",
        description="Brief description for Studio UI",
        version="1.0.0",
        tags={"ai", "kaizen", "custom"}
    )

    def __init__(self, **kwargs):
        """Accept any kwargs for Studio compatibility."""
        super().__init__(
            signature=MySignature(),
            **kwargs
        )

    def process(self, input: str) -> dict:
        """Your agent logic here."""
        result = self.run(input=input)
        return result
```

**That's it!** This agent is now discoverable in Studio.

---

## 📖 Complete Example: Production-Ready Agent

Let's walk through creating a **complete, production-ready agent** with all best practices.

### Example: SentimentAnalysisAgent

```python
"""
SentimentAnalysisAgent - Production-Ready Sentiment Analysis

Zero-config usage:
    from kaizen.agents import SentimentAnalysisAgent

    agent = SentimentAnalysisAgent()
    result = agent.analyze("This product is amazing!")
    print(result['sentiment'])  # "positive"

Progressive configuration:
    agent = SentimentAnalysisAgent(
        llm_provider="openai",
        model="gpt-4",
        temperature=0.1,
        include_confidence=True
    )

Environment variable support:
    KAIZEN_LLM_PROVIDER=openai
    KAIZEN_MODEL=gpt-3.5-turbo
    KAIZEN_TEMPERATURE=0.1
"""

import os
from dataclasses import dataclass, field, replace
from typing import Dict, Any, Optional

from kailash.nodes.base import NodeMetadata, register_node
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField


# Step 1: Define Signature (type-safe I/O)
class SentimentSignature(Signature):
    """Signature for sentiment analysis."""

    text: str = InputField(desc="Text to analyze")

    sentiment: str = OutputField(desc="Sentiment: positive, negative, or neutral")
    confidence: float = OutputField(desc="Confidence score (0.0-1.0)")
    explanation: str = OutputField(desc="Brief explanation of sentiment")


# Step 2: Define Config (zero-config with progressive overrides)
@dataclass
class SentimentConfig:
    """
    Configuration for Sentiment Analysis Agent.

    All parameters have sensible defaults and can be overridden via:
    1. Constructor arguments (highest priority)
    2. Environment variables (KAIZEN_*)
    3. Default values (lowest priority)
    """
    # LLM configuration
    llm_provider: str = field(
        default_factory=lambda: os.getenv("KAIZEN_LLM_PROVIDER", "openai")
    )
    model: str = field(
        default_factory=lambda: os.getenv("KAIZEN_MODEL", "gpt-3.5-turbo")
    )
    temperature: float = field(
        default_factory=lambda: float(os.getenv("KAIZEN_TEMPERATURE", "0.1"))
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("KAIZEN_MAX_TOKENS", "200"))
    )

    # Agent-specific configuration
    include_confidence: bool = True
    include_explanation: bool = True

    # Technical configuration
    timeout: int = 30
    retry_attempts: int = 3
    provider_config: Dict[str, Any] = field(default_factory=dict)


# Step 3: Implement Agent
@register_node()  # ✅ CRITICAL: Makes agent discoverable to Studio
class SentimentAnalysisAgent(BaseAgent):
    """
    Production-ready Sentiment Analysis Agent.

    Features:
    - Zero-config with sensible defaults
    - Analyzes text for positive, negative, or neutral sentiment
    - Returns confidence score and explanation
    - Built-in error handling and logging via BaseAgent

    Inherits from BaseAgent:
    - Signature-based sentiment analysis pattern
    - Single-shot execution via AsyncSingleShotStrategy (default)
    - Error handling (ErrorHandlingMixin)
    - Performance tracking (PerformanceMixin)
    - Structured logging (LoggingMixin)

    Use Cases:
    - Customer feedback analysis
    - Social media monitoring
    - Product review analysis
    - Support ticket prioritization

    Usage:
        # Zero-config
        agent = SentimentAnalysisAgent()
        result = agent.analyze("Great product!")
        print(f"Sentiment: {result['sentiment']}")
        print(f"Confidence: {result['confidence']}")

        # Custom configuration
        agent = SentimentAnalysisAgent(
            llm_provider="openai",
            model="gpt-4",
            include_confidence=True
        )
    """

    # ✅ CRITICAL: Metadata for Studio discovery
    metadata = NodeMetadata(
        name="SentimentAnalysisAgent",
        description="Analyze text sentiment with confidence scoring",
        version="1.0.0",
        tags={"ai", "kaizen", "sentiment", "analysis", "nlp"}
    )

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        include_confidence: Optional[bool] = None,
        include_explanation: Optional[bool] = None,
        timeout: Optional[int] = None,
        retry_attempts: Optional[int] = None,
        provider_config: Optional[Dict[str, Any]] = None,
        config: Optional[SentimentConfig] = None
    ):
        """
        Initialize Sentiment Analysis Agent with zero-config defaults.

        Args:
            llm_provider: Override default LLM provider
            model: Override default model
            temperature: Override default temperature (0.0-1.0)
            max_tokens: Override default max tokens
            include_confidence: Include confidence score in output
            include_explanation: Include explanation in output
            timeout: Override default timeout
            retry_attempts: Override default retry attempts
            provider_config: Additional provider-specific configuration
            config: Full config object (overrides individual params)
        """
        # Build config with overrides
        if config is None:
            config = SentimentConfig()

            if llm_provider is not None:
                config = replace(config, llm_provider=llm_provider)
            if model is not None:
                config = replace(config, model=model)
            if temperature is not None:
                config = replace(config, temperature=temperature)
            if max_tokens is not None:
                config = replace(config, max_tokens=max_tokens)
            if include_confidence is not None:
                config = replace(config, include_confidence=include_confidence)
            if include_explanation is not None:
                config = replace(config, include_explanation=include_explanation)
            if timeout is not None:
                config = replace(config, timeout=timeout)
            if retry_attempts is not None:
                config = replace(config, retry_attempts=retry_attempts)
            if provider_config is not None:
                config = replace(config, provider_config=provider_config)

        # Merge timeout into provider_config
        if config.timeout and (
            not config.provider_config or 'timeout' not in config.provider_config
        ):
            provider_cfg = config.provider_config.copy() if config.provider_config else {}
            provider_cfg['timeout'] = config.timeout
            config = replace(config, provider_config=provider_cfg)

        # Initialize BaseAgent (auto-converts config to BaseAgentConfig)
        super().__init__(
            config=config,
            signature=SentimentSignature()
        )

        self.sentiment_config = config

    def analyze(self, text: str) -> Dict[str, Any]:
        """
        Analyze sentiment of text.

        Args:
            text: Text to analyze

        Returns:
            Dict with sentiment, confidence, and explanation

        Example:
            >>> agent = SentimentAnalysisAgent()
            >>> result = agent.analyze("This is amazing!")
            >>> print(result['sentiment'])  # "positive"
            >>> print(result['confidence'])  # 0.95
        """
        result = self.run(text=text)

        # Filter output based on config
        if not self.sentiment_config.include_confidence:
            result.pop('confidence', None)
        if not self.sentiment_config.include_explanation:
            result.pop('explanation', None)

        return result

    async def analyze_async(self, text: str) -> Dict[str, Any]:
        """Async version of analyze."""
        result = await self.run_async(text=text)

        if not self.sentiment_config.include_confidence:
            result.pop('confidence', None)
        if not self.sentiment_config.include_explanation:
            result.pop('explanation', None)

        return result
```

---

## 🔧 Step-by-Step Implementation Guide

### Step 1: Decorate with `@register_node()`

**Purpose**: Makes your agent discoverable to Kailash NodeRegistry and Studio.

```python
from kailash.nodes.base import register_node

@register_node()  # ← THIS IS CRITICAL
class MyAgent(BaseAgent):
    pass
```

**What it does**:

- Registers agent in global NodeRegistry
- Enables Studio discovery
- Allows `WorkflowBuilder.add_node("MyAgent", ...)` usage

**Common mistake**: Forgetting this decorator → Agent won't appear in Studio

---

### Step 2: Add `NodeMetadata`

**Purpose**: Provides metadata for Studio's visual interface.

```python
from kailash.nodes.base import NodeMetadata

class MyAgent(BaseAgent):
    metadata = NodeMetadata(
        name="MyAgent",               # Agent class name
        description="Brief summary",  # Shown in Studio palette
        version="1.0.0",              # Semantic versioning
        tags={"ai", "kaizen"}         # For filtering/search
    )
```

**Metadata fields**:

- `name` (str): Agent class name (must match class)
- `description` (str): Brief summary for Studio UI (1-2 sentences)
- `version` (str): Semantic version (e.g., "1.0.0")
- `tags` (set): Tags for categorization (always include `"ai"` and `"kaizen"`)

**Example tags by category**:

```python
# Specialized agents
tags={"ai", "kaizen", "qa", "question-answering"}

# Batch processing
tags={"ai", "kaizen", "batch", "concurrent", "high-throughput"}

# Multi-modal
tags={"ai", "kaizen", "vision", "multi-modal", "ocr"}

# Workflow patterns
tags={"ai", "kaizen", "workflow", "orchestration"}
```

---

### Step 3: Follow Configuration Pattern

**Best Practice**: Use domain-specific config with `replace()` for zero-config UX.

```python
from dataclasses import dataclass, field, replace
import os

@dataclass
class MyAgentConfig:
    """
    Zero-config with progressive overrides.

    Priority:
    1. Constructor args (highest)
    2. Environment variables (KAIZEN_*)
    3. Defaults (lowest)
    """
    llm_provider: str = field(
        default_factory=lambda: os.getenv("KAIZEN_LLM_PROVIDER", "openai")
    )
    model: str = field(
        default_factory=lambda: os.getenv("KAIZEN_MODEL", "gpt-3.5-turbo")
    )
    # ... other fields ...


class MyAgent(BaseAgent):
    def __init__(self, llm_provider=None, model=None, config=None):
        # Build config with overrides
        if config is None:
            config = MyAgentConfig()

            if llm_provider is not None:
                config = replace(config, llm_provider=llm_provider)
            if model is not None:
                config = replace(config, model=model)

        # BaseAgent auto-converts to BaseAgentConfig
        super().__init__(config=config, signature=MySignature())
```

**Why this pattern?**

- ✅ Zero-config: Users can do `MyAgent()` with no args
- ✅ Progressive: Advanced users can override specific params
- ✅ Environment variables: Support 12-factor app pattern
- ✅ Type-safe: Dataclass provides validation

---

### Step 4: Register in `nodes.py`

**Location**: `src/kaizen/agents/nodes.py`

**Add import**:

```python
# In nodes.py
from kaizen.agents.specialized.my_agent import MyAgent
```

**Add to KAIZEN_AGENTS dict**:

```python
KAIZEN_AGENTS = {
    # ... existing agents ...

    "MyAgent": {
        "class": MyAgent,
        "category": "AI Agents",
        "description": "Brief summary for Studio",
        "version": "1.0.0",
        "tags": ["ai", "kaizen", "custom"],
        "icon": "zap",           # Lucide icon name
        "color": "#8B5CF6"       # Hex color for Studio UI
    }
}
```

**Add to `__all__` list**:

```python
__all__ = [
    # ... existing agents ...
    "MyAgent",
    "KAIZEN_AGENTS"
]
```

**Icon options** (Lucide icons):

- `message-circle` - Chat/Q&A
- `brain` - Memory/Learning
- `git-branch` - Reasoning/Chain-of-thought
- `search` - RAG/Retrieval
- `code` - Code generation
- `zap` - ReAct/Tool use
- `database` - Batch processing
- `user-check` - Human approval
- `shield` - Resilience/Fallback
- `message-square` - Streaming
- `rotate-cw` - Reflection/Iteration
- `eye` - Vision
- `mic` - Audio/Transcription
- `layers` - Multi-modal

**Color palette** (Studio theme):

```python
"#4F46E5"  # Indigo - Q&A
"#7C3AED"  # Purple - Memory
"#DC2626"  # Red - Reasoning
"#059669"  # Green - RAG
"#F59E0B"  # Amber - Code
"#8B5CF6"  # Violet - ReAct
"#10B981"  # Emerald - Batch
"#6366F1"  # Indigo - Approval
"#EF4444"  # Red - Resilience
"#3B82F6"  # Blue - Streaming
"#A855F7"  # Purple - Reflection
"#0891B2"  # Cyan - Vision
"#EA580C"  # Orange - Audio
"#06B6D4"  # Cyan - Multi-modal
```

---

## ✅ Validation Checklist

Before submitting your custom agent, verify:

### ✅ Registration

- [ ] Agent decorated with `@register_node()`
- [ ] `metadata` class attribute defined
- [ ] Imported in `src/kaizen/agents/nodes.py`
- [ ] Added to `KAIZEN_AGENTS` dict with metadata
- [ ] Added to `__all__` export list

### ✅ Configuration

- [ ] Domain-specific config class (e.g., `MyAgentConfig`)
- [ ] Environment variable support (`KAIZEN_*`)
- [ ] Zero-config works: `MyAgent()` with no args
- [ ] Progressive config works: Override specific params
- [ ] `replace()` pattern for immutable config updates

### ✅ Documentation

- [ ] Class docstring with:
  - [ ] Brief summary
  - [ ] Features list
  - [ ] Use cases
  - [ ] Usage examples
- [ ] Method docstrings with args/returns
- [ ] Module-level docstring with examples

### ✅ Testing

- [ ] Agent appears in `NodeRegistry.list_nodes()`
- [ ] Agent metadata validates (name, description, version, tags)
- [ ] Import path works: `from kaizen.agents import MyAgent`
- [ ] Zero-config instantiation works: `MyAgent()`
- [ ] Run with test input to verify basic functionality

---

## 🧪 Testing Your Agent

### Test 1: Registry Discovery

```python
from kailash.nodes.base import NodeRegistry

registry = NodeRegistry()
all_nodes = registry.list_nodes()

# Check your agent is registered
assert "MyAgent" in all_nodes

# Validate metadata
agent_class = all_nodes["MyAgent"]
assert hasattr(agent_class, 'metadata')
assert agent_class.metadata.name == "MyAgent"
assert agent_class.metadata.version
assert agent_class.metadata.tags
assert 'kaizen' in agent_class.metadata.tags
```

### Test 2: Import Path

```python
# Test direct import
from kaizen.agents import MyAgent

# Test instantiation
agent = MyAgent()
assert agent is not None
```

### Test 3: KAIZEN_AGENTS Dict

```python
from kaizen.agents.nodes import KAIZEN_AGENTS

# Check agent in dict
assert "MyAgent" in KAIZEN_AGENTS

# Validate dict structure
agent_info = KAIZEN_AGENTS["MyAgent"]
required_keys = ['class', 'category', 'description', 'version', 'tags', 'icon', 'color']
for key in required_keys:
    assert key in agent_info
```

### Test 4: Functional Test

```python
# Test zero-config
agent = MyAgent()
result = agent.process("test input")
assert result is not None

# Test with config override
agent = MyAgent(llm_provider="mock", model="test-model")
result = agent.process("test input")
assert result is not None
```

---

## 🎯 Complete Template

Use this as a starting point for new agents:

```python
"""
<AgentName> - Production-Ready <Brief Description>

Zero-config usage:
    from kaizen.agents import <AgentName>

    agent = <AgentName>()
    result = agent.<method>("<input>")

Progressive configuration:
    agent = <AgentName>(
        llm_provider="openai",
        model="gpt-4",
        <custom_param>=<value>
    )

Environment variable support:
    KAIZEN_LLM_PROVIDER=openai
    KAIZEN_MODEL=gpt-3.5-turbo
"""

import os
from dataclasses import dataclass, field, replace
from typing import Dict, Any, Optional

from kailash.nodes.base import NodeMetadata, register_node
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField


class <AgentName>Signature(Signature):
    """Signature for <agent purpose>."""

    input_field: str = InputField(desc="<description>")
    output_field: str = OutputField(desc="<description>")


@dataclass
class <AgentName>Config:
    """Configuration for <AgentName>."""

    llm_provider: str = field(default_factory=lambda: os.getenv("KAIZEN_LLM_PROVIDER", "openai"))
    model: str = field(default_factory=lambda: os.getenv("KAIZEN_MODEL", "gpt-3.5-turbo"))
    temperature: float = field(default_factory=lambda: float(os.getenv("KAIZEN_TEMPERATURE", "0.7")))

    # Agent-specific config
    custom_param: str = "default_value"

    # Technical config
    timeout: int = 30
    retry_attempts: int = 3
    provider_config: Dict[str, Any] = field(default_factory=dict)


@register_node()
class <AgentName>(BaseAgent):
    """
    Production-ready <AgentName>.

    Features:
    - <Feature 1>
    - <Feature 2>

    Use Cases:
    - <Use case 1>
    - <Use case 2>

    Usage:
        agent = <AgentName>()
        result = agent.<method>("<input>")
    """

    metadata = NodeMetadata(
        name="<AgentName>",
        description="<Brief description for Studio>",
        version="1.0.0",
        tags={"ai", "kaizen", "<category>"}
    )

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        custom_param: Optional[str] = None,
        timeout: Optional[int] = None,
        retry_attempts: Optional[int] = None,
        provider_config: Optional[Dict[str, Any]] = None,
        config: Optional[<AgentName>Config] = None
    ):
        if config is None:
            config = <AgentName>Config()

            if llm_provider is not None:
                config = replace(config, llm_provider=llm_provider)
            if model is not None:
                config = replace(config, model=model)
            if temperature is not None:
                config = replace(config, temperature=temperature)
            if custom_param is not None:
                config = replace(config, custom_param=custom_param)
            if timeout is not None:
                config = replace(config, timeout=timeout)
            if retry_attempts is not None:
                config = replace(config, retry_attempts=retry_attempts)
            if provider_config is not None:
                config = replace(config, provider_config=provider_config)

        if config.timeout and (not config.provider_config or 'timeout' not in config.provider_config):
            provider_cfg = config.provider_config.copy() if config.provider_config else {}
            provider_cfg['timeout'] = config.timeout
            config = replace(config, provider_config=provider_cfg)

        super().__init__(config=config, signature=<AgentName>Signature())
        self.agent_config = config

    def <method>(self, input_field: str) -> Dict[str, Any]:
        """
        <Method description>.

        Args:
            input_field: <description>

        Returns:
            Dict with <outputs>

        Example:
            >>> agent = <AgentName>()
            >>> result = agent.<method>("<input>")
        """
        result = self.run(input_field=input_field)
        return result
```

---

## 📚 Additional Resources

### Documentation

- **BaseAgent API**: `/docs/reference/base-agent-api-reference.md`
- **Signature Programming**: `/docs/reference/signature-programming-guide.md`
- **Configuration Patterns**: `/docs/developer-experience/configuration-patterns.md`
- **Testing Guide**: `/docs/development/testing.md`

### Examples

- **Production Agents**: `/src/kaizen/agents/specialized/`
  - See `batch_processing.py`, `human_approval.py`, `resilient.py` for complete examples
- **Example Workflows**: `/examples/1-single-agent/`
  - See how agents are used in real workflows

### Get Help

- **GitHub Issues**: [kailash-python-sdk/issues](https://github.com/terrene-foundation/kailash-py/issues)
- **Discord**: [Kailash Community](https://discord.gg/kailash)

---

## 🎉 Summary

Creating Studio-compatible agents requires just 4 steps:

1. ✅ **Decorate**: `@register_node()`
2. ✅ **Metadata**: Add `NodeMetadata` class attribute
3. ✅ **Config**: Use domain-specific config with `replace()` pattern
4. ✅ **Register**: Import in `nodes.py` and add to `KAIZEN_AGENTS`

Follow the template above and you'll have a production-ready, Studio-discoverable agent in minutes!

---

**Last Updated**: 2025-10-05
**Kaizen Version**: 0.1.0
**Status**: Production-ready
