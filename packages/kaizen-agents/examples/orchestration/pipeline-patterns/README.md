# Pipeline Patterns - Composable Multi-Agent Workflows

Production-ready examples demonstrating Kaizen's Pipeline infrastructure for building composable, multi-step workflows that integrate seamlessly with multi-agent patterns.

## Overview

**Kaizen Pipeline Infrastructure** (v0.5.0+) provides:
- Base `Pipeline` class for multi-step workflows
- `.to_agent()` method for converting pipelines to BaseAgent
- Full composability: pipelines as agents, nested pipelines, multi-agent integration

## Examples

### 1. Basic Pipeline (`1_basic_pipeline.py`)

**What it demonstrates:**
- Creating custom Pipeline with multi-step processing
- Converting Pipeline to BaseAgent with `.to_agent()`
- Using pipeline-agent in other contexts

**Pattern:** Pipeline → Agent conversion for composability

**Run:**
```bash
python examples/orchestration/pipeline-patterns/1_basic_pipeline.py
```

**Output:**
```
✅ Step 1/4: Cleaned data
✅ Step 2/4: Transformed data
✅ Step 3/4: Enriched data
✅ Step 4/4: Validated data

✅ Created agent: data_processor
   Can be used in:
   - SupervisorWorkerPattern (as a worker)
   - Other pipelines (nested composition)
   - Workflows (Core SDK integration)
```

**Key Takeaway:** Any Pipeline can become a BaseAgent, enabling use in multi-agent patterns.

---

### 2. Pipeline in Multi-Agent Pattern (`2_pipeline_in_multi_agent.py`)

**What it demonstrates:**
- Creating specialized pipelines (DocumentProcessingPipeline, DataAnalysisPipeline)
- Converting pipelines to agents
- Mixing pipeline-agents with regular agents
- Using in SupervisorWorkerPattern coordination

**Pattern:** Pipeline composability in multi-agent coordination

**Run:**
```bash
python examples/orchestration/pipeline-patterns/2_pipeline_in_multi_agent.py
```

**Output:**
```
Workers:
  1. document_processor (Pipeline → Agent)
  2. data_analyzer (Pipeline → Agent)
  3. simple_qa (Regular Agent)

✅ Successfully demonstrated:
   - Pipelines converted to BaseAgent
   - Pipelines mixed with regular agents
   - All agents executed successfully
   - Ready for SupervisorWorkerPattern integration
```

**Key Takeaway:** Pipelines and regular agents are interchangeable in multi-agent patterns.

---

### 3. Nested Pipelines (`3_nested_pipelines.py`)

**What it demonstrates:**
- Creating reusable sub-pipelines
- Composing master pipeline from sub-pipelines
- Using sub-pipelines independently or nested
- Converting any pipeline (master or sub) to agent

**Pattern:** Nested composition for modular workflow design

**Run:**
```bash
python examples/orchestration/pipeline-patterns/3_nested_pipelines.py
```

**Output:**
```
🔹 Master Pipeline: Starting execution
  └─ Step 1/3: Running DataCleaningPipeline...
     ✅ Cleaning complete
  └─ Step 2/3: Running DataTransformationPipeline...
     ✅ Transformation complete
  └─ Step 3/3: Running DataAnalysisPipeline...
     ✅ Analysis complete

✅ Nested Pipeline Composition Benefits:
   1. Modularity: Sub-pipelines are reusable components
   2. Composability: Build complex workflows from simple parts
   3. Flexibility: Use pipelines independently or nested
   4. Agent Conversion: Any pipeline → BaseAgent via .to_agent()
   5. Multi-Agent Ready: Use as workers in coordination patterns
```

**Key Takeaway:** Build complex workflows by composing simple, reusable pipeline components.

---

## Core API

### Pipeline Base Class

```python
from kaizen.orchestration.pipeline import Pipeline

class MyPipeline(Pipeline):
    def run(self, **inputs) -> Dict[str, Any]:
        # Multi-step workflow logic
        step1 = self.process_step1(inputs)
        step2 = self.process_step2(step1)
        return {"result": step2}

# Use directly
pipeline = MyPipeline()
result = pipeline.run(data="...")

# Convert to agent
agent = pipeline.to_agent(name="my_pipeline")
```

### SequentialPipeline (Convenience)

```python
from kaizen.orchestration.pipeline import SequentialPipeline
from kaizen.agents import SimpleQAAgent, CodeGenerationAgent

# Create from existing agents
pipeline = SequentialPipeline(
    agents=[
        SimpleQAAgent(config),
        CodeGenerationAgent(config)
    ]
)

# Execute (each output → next input)
result = pipeline.run(task="...")

# Convert to agent
agent = pipeline.to_agent(name="code_pipeline")
```

### Integration with Multi-Agent Patterns

```python
from kaizen.orchestration.patterns import SupervisorWorkerPattern
from kaizen.orchestration.pipeline import Pipeline

# Create custom pipeline
class DocumentPipeline(Pipeline):
    def run(self, **inputs):
        # Multi-step processing
        return {"processed": True}

# Convert to agent
doc_agent = DocumentPipeline().to_agent(name="doc_processor")

# Use in multi-agent pattern
pattern = SupervisorWorkerPattern(
    supervisor=supervisor,
    workers=[
        doc_agent,      # Pipeline as worker
        qa_agent,       # Regular agent
        research_agent  # Regular agent
    ],
    coordinator=coordinator,
    shared_pool=shared_pool
)
```

## Benefits

### Composability
- ✅ Pipelines can be nested within other pipelines
- ✅ Pipelines can be used as workers in multi-agent patterns
- ✅ Reuse workflow logic across different contexts

### Flexibility
- ✅ Mix and match: Combine pipelines with regular agents
- ✅ Progressive enhancement: Start simple, add complexity as needed
- ✅ Type safety: Inherits BaseAgent's signature-based I/O

### Production Ready
- ✅ All BaseAgent features: memory, hooks, observability, permissions
- ✅ Full compatibility with multi-agent patterns
- ✅ Testable: Unit test pipelines independently, then compose

## Migration from Old Patterns

**Old** (agents.coordination):
```python
# DEPRECATED (v0.4.x and earlier)
from kaizen.agents.coordination.sequential_pipeline import SequentialPattern

pattern = SequentialPattern(agents=[...])
# Limited to sequential patterns, no composability
```

**New** (orchestration.patterns + orchestration.pipeline):
```python
# CURRENT (v0.5.0+)
from kaizen.orchestration.patterns import SequentialPipelinePattern
from kaizen.orchestration.pipeline import SequentialPipeline, Pipeline

# Option 1: Use pattern for coordination
pattern = SequentialPipelinePattern(agents=[...])

# Option 2: Use pipeline for composability
pipeline = SequentialPipeline(agents=[...])
agent = pipeline.to_agent()  # Now composable!

# Option 3: Custom pipeline with full control
class CustomPipeline(Pipeline):
    def run(self, **inputs):
        # Custom multi-step logic
        pass
```

**Backward Compatibility:** Old imports (`kaizen.agents.coordination.*`) still work with deprecation warnings. Will be removed in v0.6.0.

## Documentation

**Implementation:**
- Source: `src/kaizen/orchestration/pipeline.py`
- Tests: `tests/unit/orchestration/test_pipeline.py`

**Guides:**
- Kaizen Specialist: `.claude/agents/frameworks/kaizen-specialist.md`
- Multi-Agent Coordination: `sdk-users/apps/kaizen/docs/guides/multi-agent-coordination.md`
- API Reference: `sdk-users/apps/kaizen/docs/reference/api-reference.md`

## Running Examples

### Prerequisites

**Core functionality** (Pipeline execution):
```bash
# Works with base Kaizen installation
pip install kailash-kaizen
```

**Full functionality** (including .to_agent()):
```bash
# Requires optional observability dependencies
pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc
```

### Execute Examples

```bash
# Basic pipeline
python examples/orchestration/pipeline-patterns/1_basic_pipeline.py

# Pipeline in multi-agent
python examples/orchestration/pipeline-patterns/2_pipeline_in_multi_agent.py

# Nested pipelines
python examples/orchestration/pipeline-patterns/3_nested_pipelines.py
```

**Note:** Examples demonstrate Pipeline execution (always works) and .to_agent() conversion (requires optional dependencies)

## Next Steps

1. **Extend with Agents:** Replace mock processing with real AI agents
2. **Add Observability:** Enable tracing/metrics for production monitoring
3. **Multi-Agent Integration:** Use in SupervisorWorkerPattern with real supervisor
4. **Custom Pipelines:** Build domain-specific pipelines for your use case

---

**Version:** Kaizen v0.5.0+
**Pattern:** Pipeline Infrastructure for Composable Workflows
**Status:** Production Ready
