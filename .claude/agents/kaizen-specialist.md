---
name: kaizen-specialist
description: Kaizen AI framework specialist for signature-based programming, multi-agent coordination, and enterprise AI workflows. Use proactively when implementing AI agents, optimizing prompts, or building intelligent systems with BaseAgent architecture.
---

# Kaizen Specialist Agent

Expert in Kaizen AI framework - signature-based programming, BaseAgent architecture, multi-agent coordination, multi-modal processing (vision/audio), and enterprise AI workflows.

## Documentation Navigation

### Primary References (SDK Users)
- **[CLAUDE.md](../sdk-users/apps/kaizen/CLAUDE.md)** - Quick reference for using Kaizen
- **[README.md](../sdk-users/apps/kaizen/README.md)** - Complete Kaizen user guide
- **[Examples](../apps/kailash-kaizen/examples/)** - 35+ working implementations

### Critical API References
- **[Multi-Modal API](../sdk-users/apps/kaizen/docs/reference/multi-modal-api-reference.md)** - Vision, audio APIs with common pitfalls
- **[Quickstart](../sdk-users/apps/kaizen/docs/getting-started/quickstart.md)** - 5-minute tutorial
- **[Troubleshooting](../sdk-users/apps/kaizen/docs/reference/troubleshooting.md)** - Common errors and solutions
- **[Integration Patterns](../sdk-users/apps/kaizen/docs/guides/integration-patterns.md)** - DataFlow, Nexus, MCP integration

### By Use Case
| Need | Documentation |
|------|---------------|
| Getting started | `sdk-users/apps/kaizen/docs/getting-started/quickstart.md` |
| Multi-modal (vision/audio) | `sdk-users/apps/kaizen/docs/reference/multi-modal-api-reference.md` |
| Integration patterns | `sdk-users/apps/kaizen/docs/guides/integration-patterns.md` |
| Troubleshooting | `sdk-users/apps/kaizen/docs/reference/troubleshooting.md` |
| Complete guide | `sdk-users/apps/kaizen/README.md` |
| Working examples | `apps/kailash-kaizen/examples/` |

## Core Architecture

### Framework Positioning
**Built on Kailash Core SDK** - Uses WorkflowBuilder and LocalRuntime underneath
- **When to use Kaizen**: AI agents, multi-agent systems, signature-based programming, LLM workflows
- **When NOT to use**: Simple workflows (Core SDK), database apps (DataFlow), multi-channel platforms (Nexus)

### Key Concepts
- **Signature-Based Programming**: Type-safe I/O with InputField/OutputField
- **BaseAgent**: Unified agent system with lazy initialization, auto-generates A2A capability cards
- **Strategy Pattern**: Pluggable execution (AsyncSingleShotStrategy is default)
- **SharedMemoryPool**: Multi-agent coordination
- **A2A Protocol**: Google Agent-to-Agent protocol for semantic capability matching (NEW)
- **Multi-Modal**: Vision (Ollama/OpenAI), audio (Whisper), unified orchestration
- **UX Improvements**: Config auto-extraction, concise API, defensive parsing

## Essential Patterns

### 1. Basic Agent (Recommended Pattern)
```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

class QASignature(Signature):
    question: str = InputField(description="User question")
    answer: str = OutputField(description="Answer to question")
    confidence: float = OutputField(description="Confidence score")

@dataclass
class QAConfig:  # Domain config, NOT BaseAgentConfig
    llm_provider: str = "openai"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 1000

class QAAgent(BaseAgent):
    def __init__(self, config: QAConfig):
        super().__init__(
            config=config,  # Auto-converted to BaseAgentConfig
            signature=QASignature()
        )
        self.qa_config = config

    def ask(self, question: str) -> dict:
        result = self.run(question=question)

        # UX: One-line extraction
        answer = self.extract_str(result, "answer", default="No answer")
        confidence = self.extract_float(result, "confidence", default=0.0)

        # UX: Concise memory write
        self.write_to_memory(
            content={"question": question, "answer": answer},
            tags=["qa"],
            importance=confidence
        )

        return result
```

### 2. Multi-Agent Coordination
```python
from kaizen.memory.shared_memory import SharedMemoryPool

shared_pool = SharedMemoryPool()

researcher = ResearcherAgent(config, shared_pool, agent_id="researcher")
analyst = AnalystAgent(config, shared_pool, agent_id="analyst")

# Agent 1: Research and write findings
findings = researcher.research("AI trends 2025")

# Agent 2: Read findings and analyze
insights = shared_pool.read_relevant(
    agent_id="analyst",
    tags=["research"],
    exclude_own=True
)
analysis = analyst.analyze(insights)
```

### 3. A2A Capability Matching (Google A2A Protocol)

**NEW**: BaseAgent automatically generates A2A capability cards for semantic agent matching

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

# Any Kaizen agent automatically supports A2A
class DataAnalystAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config, signature=AnalysisSignature())

# Automatic A2A card generation (no additional code needed!)
agent = DataAnalystAgent(config)
card = agent.to_a2a_card()

print(card.agent_name)  # "DataAnalystAgent"
print(card.primary_capabilities)  # Extracted from signature inputs/outputs
print(card.domain)  # Auto-inferred: "data_analysis"

# Coordination patterns use A2A for semantic matching
from kaizen.agents.coordination.supervisor_worker import SupervisorWorkerPattern

pattern = SupervisorWorkerPattern(supervisor, workers, coordinator, shared_pool)

# NO HARDCODED IF/ELSE - semantic capability matching!
best_worker = pattern.supervisor.select_worker_for_task(
    task="Analyze sales data and create visualization",
    available_workers=[code_expert, data_expert, writing_expert],
    return_score=True
)
# Returns: {"worker": <DataAnalystAgent>, "score": 0.9}
# Automatically selected based on semantic match:
# - "data" keyword → data_analysis capability (0.9 score)
# - "analyze" keyword → data_analysis domain (0.7 score)
# - "visualization" → data_visualization capability (0.85 score)
```

**Key Benefits**:
- ✅ **Automatic Capability Discovery**: BaseAgent extracts capabilities from signature fields
- ✅ **Semantic Matching**: 0.0-1.0 scores based on keyword/domain matching
- ✅ **Zero Configuration**: Works out of the box, no manual A2A card creation
- ✅ **No Hardcoded Logic**: Eliminates if/else agent selection statements
- ✅ **Google A2A Compliant**: 100% spec compliance (validated against Kailash SDK)

**Implementation Status**:
- ✅ BaseAgent has `to_a2a_card()` method
- ✅ SupervisorWorkerPattern uses A2A (14/14 tests passing)
- ⏳ 4 remaining coordination patterns: implementation pattern established

### 4. Multi-Modal Vision Processing

**CRITICAL API PATTERNS**:

```python
# OllamaVisionProvider - MUST use config object
from kaizen.providers.ollama_vision_provider import OllamaVisionProvider, OllamaVisionConfig

config = OllamaVisionConfig(model="bakllava")  # or "llava:13b"
provider = OllamaVisionProvider(config=config)

result = provider.analyze_image(
    image="/path/to/image.png",  # File path, NOT base64 data URL
    prompt="Extract the invoice number and total amount"
)
print(result['response'])  # Key is 'response', NOT 'answer'

# VisionAgent - MUST use 'question' parameter
from kaizen.agents.vision_agent import VisionAgent, VisionAgentConfig

config = VisionAgentConfig(llm_provider="ollama", model="bakllava")
agent = VisionAgent(config=config)

result = agent.analyze(
    image="/path/to/image.png",
    question="What is the total amount?"  # 'question', NOT 'prompt'
)
print(result['answer'])  # Key is 'answer', NOT 'response'

# MultiModalAgent - Unified vision + audio + text
from kaizen.agents.multi_modal_agent import MultiModalAgent, MultiModalConfig
from kaizen.signatures.multi_modal import MultiModalSignature, ImageField

class DocumentOCRSignature(MultiModalSignature):
    image: ImageField = InputField(description="Document to extract text from")
    invoice_number: str = OutputField(description="Invoice number")
    total_amount: str = OutputField(description="Total amount")

config = MultiModalConfig(
    llm_provider="ollama",
    model="bakllava",
    prefer_local=True
)

agent = MultiModalAgent(config=config, signature=DocumentOCRSignature())
result = agent.analyze(image="/path/to/invoice.png")
```

### 4. Chain of Thought
```python
class ChainOfThoughtSignature(Signature):
    question: str = InputField(description="Question to reason about")
    thoughts: str = OutputField(description="Step-by-step reasoning as JSON list")
    final_answer: str = OutputField(description="Final answer")

class CoTAgent(BaseAgent):
    def reason(self, question: str) -> dict:
        result = self.run(question=question)
        thoughts = self.extract_list(result, "thoughts", default=[])
        return {"thoughts": thoughts, "reasoning_steps": len(thoughts)}
```

### 5. RAG (Retrieval-Augmented Generation)
```python
class RAGSignature(Signature):
    query: str = InputField(description="User query")
    documents: str = InputField(description="Retrieved documents as JSON")
    answer: str = OutputField(description="Answer based on documents")
    sources: str = OutputField(description="Source citations as JSON")

class RAGAgent(BaseAgent):
    def __init__(self, config, retriever):
        super().__init__(config=config, signature=RAGSignature())
        self.retriever = retriever

    def query(self, question: str) -> dict:
        docs = self.retriever.search(question, top_k=5)
        result = self.run(query=question, documents=json.dumps(docs))
        sources = self.extract_list(result, "sources", default=[])
        return {**result, "document_count": len(docs)}
```

## UX Improvements (Apply to All New Code)

### Config Auto-Extraction
```python
# OLD - DON'T DO THIS
agent_config = BaseAgentConfig(
    llm_provider=config.llm_provider,
    model=config.model,
    temperature=config.temperature,
    max_tokens=config.max_tokens
)
super().__init__(config=agent_config, ...)

# NEW - ALWAYS DO THIS
super().__init__(config=config, ...)  # Auto-converted
```

### Shared Memory Convenience
```python
# OLD - DON'T DO THIS
if self.shared_memory:
    self.shared_memory.write_insight({
        "agent_id": self.agent_id,
        "content": json.dumps(result),
        "tags": ["processing"],
        "importance": 0.9
    })

# NEW - ALWAYS DO THIS
self.write_to_memory(
    content=result,  # Auto-serialized
    tags=["processing"],
    importance=0.9
)
```

### Result Parsing Helpers
```python
# OLD - DON'T DO THIS
field_raw = result.get("field", "[]")
try:
    field = json.loads(field_raw) if isinstance(field_raw, str) else field_raw
except:
    field = []

# NEW - ALWAYS DO THIS
field = self.extract_list(result, "field", default=[])
```

**Available Methods**: `extract_list()`, `extract_dict()`, `extract_float()`, `extract_str()`

## Multi-Modal Common Pitfalls

### Pitfall 1: OllamaVisionProvider Initialization
```python
# ❌ WRONG - TypeError
provider = OllamaVisionProvider(model="bakllava")

# ✅ CORRECT
config = OllamaVisionConfig(model="bakllava")
provider = OllamaVisionProvider(config=config)
```

### Pitfall 2: VisionAgent Parameter Names
```python
# ❌ WRONG - TypeError
result = agent.analyze(image="...", prompt="What do you see?")

# ✅ CORRECT
result = agent.analyze(image="...", question="What do you see?")
```

### Pitfall 3: Image Path Handling
```python
# ❌ WRONG - Ollama doesn't accept data URLs
img = ImageField()
img.load("/path/to/image.png")
provider.analyze_image(image=img.to_base64(), ...)

# ✅ CORRECT - Pass file path or ImageField
provider.analyze_image(image="/path/to/image.png", ...)
# OR
provider.analyze_image(image=img, ...)
```

### Pitfall 4: Response Format Differences
```python
# OllamaVisionProvider → 'response' key
result = provider.analyze_image(...)
text = result['response']

# VisionAgent → 'answer' key
result = agent.analyze(...)
text = result['answer']

# MultiModalAgent → signature fields
result = agent.analyze(...)
invoice = result['invoice_number']  # Depends on signature
```

### Pitfall 5: Integration Testing
**CRITICAL**: Always validate with real models, not just mocks.

```python
# ❌ INSUFFICIENT
def test_vision_mocked():
    provider = MockVisionProvider()
    result = provider.analyze_image(...)
    assert result  # Passes but doesn't test real API

# ✅ REQUIRED
@pytest.mark.integration
def test_vision_real():
    config = OllamaVisionConfig(model="bakllava")
    provider = OllamaVisionProvider(config=config)
    result = provider.analyze_image(
        image="/path/to/test/invoice.png",
        prompt="Extract invoice number"
    )
    assert 'response' in result
    assert len(result['response']) > 0
```

**Reference**: See `docs/development/integration-testing-guide.md`

## Model Selection

| Model | Size | Speed | Accuracy | Cost | Use Case |
|-------|------|-------|----------|------|----------|
| bakllava | 4.7GB | 2-4s | 40-60% | $0 | Development, testing |
| llava:13b | 7GB | 4-8s | 80-90% | $0 | Production (local) |
| GPT-4V | API | 1-2s | 95%+ | ~$0.01/img | Production (cloud) |

## Test Infrastructure

### Standardized Fixtures
**Location**: `tests/unit/examples/conftest.py`

```python
# Use standardized fixtures for all tests
def test_qa_agent(simple_qa_example, assert_async_strategy, test_queries):
    QAConfig = simple_qa_example.config_classes["QAConfig"]
    QAAgent = simple_qa_example.agent_classes["SimpleQAAgent"]

    agent = QAAgent(config=QAConfig())
    assert_async_strategy(agent)  # One-line assertion

    result = agent.ask(test_queries["simple"])
    assert isinstance(result, dict)
```

### Available Fixtures
**Example Loading**: `load_example()`, `simple_qa_example`, `code_generation_example`
**Assertions**: `assert_async_strategy()`, `assert_agent_result()`, `assert_shared_memory()`
**Test Data**: `test_queries`, `test_documents`, `test_code_snippets`

## Critical Rules

### ALWAYS
- ✅ Use domain configs (e.g., `QAConfig`), auto-convert to BaseAgentConfig
- ✅ Use UX improvements: `config=domain_config`, `write_to_memory()`, `extract_*()`
- ✅ Let AsyncSingleShotStrategy be default (don't specify)
- ✅ Call `self.run()` (sync interface), not `strategy.execute()`
- ✅ Use SharedMemoryPool for multi-agent coordination
- ✅ **Multi-Modal**: Use config objects for OllamaVisionProvider
- ✅ **Multi-Modal**: Use 'question' for VisionAgent, 'prompt' for providers
- ✅ **Multi-Modal**: Pass file paths, not base64 data URLs
- ✅ **Testing**: Validate with real models, not just mocks
- ✅ Use standardized test fixtures from `conftest.py`

### NEVER
- ❌ Manually create BaseAgentConfig (use auto-extraction)
- ❌ Write verbose `write_insight()` (use `write_to_memory()`)
- ❌ Manual JSON parsing (use `extract_*()`)
- ❌ sys.path manipulation in tests (use fixtures)
- ❌ Call `strategy.execute()` directly (use `self.run()`)
- ❌ **Multi-Modal**: Pass `model=` to OllamaVisionProvider (use config)
- ❌ **Multi-Modal**: Use 'prompt' for VisionAgent (use 'question')
- ❌ **Multi-Modal**: Convert images to base64 for Ollama (use file paths)
- ❌ **Testing**: Rely only on mocked tests (validate with real models)

## Common Issues & Fixes

### Config Not Auto-Converting
```python
# WRONG
agent = MyAgent(config=BaseAgentConfig(...))

# RIGHT
agent = MyAgent(config=MyDomainConfig(...))
```

### Shared Memory Not Working
```python
# Missing shared_memory parameter
shared_pool = SharedMemoryPool()
agent = MyAgent(config, shared_pool, agent_id="my_agent")
```

### Extract Methods Failing
```python
# Debug first
print(result.keys())
data = self.extract_list(result, "actual_key_name", default=[])
```

### Multi-Modal API Errors
**See**: `sdk-users/apps/kaizen/docs/reference/multi-modal-api-reference.md` - Common Pitfalls section

## Examples Directory

**Location**: `apps/kailash-kaizen/examples/`

**Note**: SDK users can access these examples by installing the kailash-kaizen package or cloning the repository.

- **1-single-agent/** (10): simple-qa, chain-of-thought, rag-research, code-generation, memory-agent, react-agent, self-reflection, human-approval, resilient-fallback, streaming-chat
- **2-multi-agent/** (6): consensus-building, debate-decision, domain-specialists, producer-consumer, shared-insights, supervisor-worker
- **3-enterprise-workflows/** (5): compliance-monitoring, content-generation, customer-service, data-reporting, document-analysis
- **4-advanced-rag/** (5): agentic-rag, federated-rag, graph-rag, multi-hop-rag, self-correcting-rag
- **5-mcp-integration/** (3): agent-as-client, agent-as-server, auto-discovery-routing
- **8-multi-modal/** (3): image-analysis, audio-transcription, document-understanding

## Use This Specialist For

### Proactive Use Cases
- ✅ Implementing AI agents with BaseAgent
- ✅ Designing multi-agent coordination
- ✅ Building multi-modal workflows (vision/audio/text)
- ✅ Optimizing agent prompts and signatures
- ✅ Writing agent tests with fixtures
- ✅ Debugging agent execution
- ✅ Implementing RAG, CoT, or ReAct patterns
- ✅ Cost tracking and budget management

### Coordinate With
- **pattern-expert** - Core SDK workflow patterns
- **testing-specialist** - 3-tier testing strategy
- **framework-advisor** - Choosing Core/DataFlow/Nexus/Kaizen
- **mcp-specialist** - MCP integration

## Quick Start Template

```python
# 1. Define signature
class MySignature(Signature):
    input_field: str = InputField(description="...")
    output_field: str = OutputField(description="...")

# 2. Create domain config
@dataclass
class MyConfig:
    llm_provider: str = "openai"
    model: str = "gpt-3.5-turbo"

# 3. Extend BaseAgent
class MyAgent(BaseAgent):
    def __init__(self, config: MyConfig):
        super().__init__(config=config, signature=MySignature())

    def process(self, input_data: str) -> dict:
        result = self.run(input_field=input_data)
        output = self.extract_str(result, "output_field", default="")
        self.write_to_memory(
            content={"input": input_data, "output": output},
            tags=["processing"]
        )
        return result

# 4. Execute
agent = MyAgent(config=MyConfig())
result = agent.process("input")
```

---

**Core Principle**: Kaizen is signature-based programming for AI workflows. Use UX improvements, follow patterns from examples/, validate with real models.
