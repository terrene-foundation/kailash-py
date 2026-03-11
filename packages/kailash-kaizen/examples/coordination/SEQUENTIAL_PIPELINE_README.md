# Sequential Pipeline Pattern

**Multi-agent coordination pattern for linear agent chaining with context preservation**

## Overview

The Sequential Pipeline Pattern enables you to chain multiple agents in linear order where each agent processes the output of the previous agent. This pattern is ideal for multi-stage workflows like ETL pipelines, content generation, and data processing.

### Key Features

- **Linear Execution**: Agents execute in strict sequential order
- **Context Preservation**: Each stage receives previous output + original context
- **Stage Tracking**: All intermediate results stored in shared memory
- **Error Handling**: Failed stages don't block pipeline (partial results)
- **Zero-Config**: Works out-of-the-box with sensible defaults
- **Progressive Configuration**: 4 levels from zero-config to full control
- **Extensibility**: Easy to add custom stage types via inheritance

### When to Use

✅ **Use Sequential Pipeline when**:
- You need multi-stage processing (ETL, data pipelines)
- Each stage builds on the previous stage's output
- Context must be preserved across all stages
- Stages must execute in strict order
- You need stage-by-stage result tracking

❌ **Don't use Sequential Pipeline when**:
- Stages can run in parallel (use SupervisorWorker)
- No dependency between stages (use Concurrent)
- Dynamic routing needed (use Handoff)
- Multiple perspectives on same task (use Consensus)

### Pattern Type

**Coordination Style**: Sequential Processing
**Agent Count**: 2+ (unlimited stages)
**Execution Model**: Synchronous, linear
**Memory Model**: Shared memory with stage tracking

---

## Architecture

### Component Diagram

```
Input → [Stage 1] → [Stage 2] → [Stage 3] → ... → [Stage N] → Final Output
        Extract      Transform     Load            Process

                    ↓ Context preserved across all stages ↓

                    [Shared Memory Pool]
                    - Stage results
                    - Pipeline metadata
                    - Execution tracking
```

### Core Components

#### 1. PipelineStageAgent

Agent that processes one stage of the pipeline.

```python
class PipelineStageAgent(BaseAgent):
    """
    Pipeline stage agent that processes input from previous stage.

    Features:
    - Extends BaseAgent
    - Uses StageProcessingSignature
    - Writes results to shared memory
    - Supports custom stage logic
    """
```

**Responsibilities**:
- Process stage input
- Generate stage output
- Write results to shared memory
- Track stage metadata

#### 2. StageProcessingSignature

Defines input/output structure for each stage.

```python
class StageProcessingSignature(Signature):
    stage_input: str = InputField(desc="Input from previous stage")
    stage_name: str = InputField(desc="Name of current stage")
    context: str = InputField(desc="Additional context", default="")
    stage_output: str = OutputField(desc="Output for next stage")
    stage_metadata: str = OutputField(desc="Stage metadata (JSON)", default="{}")
    stage_status: str = OutputField(desc="Stage status", default="success")
```

**Fields**:
- `stage_input`: Output from previous stage (or initial input for first stage)
- `stage_name`: Identifier for current stage
- `context`: Original context passed to all stages
- `stage_output`: Result to pass to next stage
- `stage_metadata`: Additional information about stage execution (JSON)
- `stage_status`: "success", "partial", or "failed"

#### 3. SequentialPipelinePattern

Container for pipeline stages and execution logic.

```python
@dataclass
class SequentialPipelinePattern(BaseMultiAgentPattern):
    stages: List[PipelineStageAgent] = field(default_factory=list)
    shared_memory: SharedMemoryPool = field(default_factory=SharedMemoryPool)

    def execute_pipeline(self, initial_input: str, context: str = "") -> Dict[str, Any]
    def add_stage(self, agent: PipelineStageAgent) -> None
    def get_stage_results(self, pipeline_id: str) -> List[Dict[str, Any]]
```

**Methods**:
- `execute_pipeline()`: Run full pipeline
- `add_stage()`: Add agent to pipeline
- `get_stage_results()`: Retrieve all intermediate results

#### 4. Factory Function

Zero-config pattern creation.

```python
def create_sequential_pipeline(
    llm_provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    shared_memory: Optional[SharedMemoryPool] = None,
    stage_configs: Optional[List[Dict[str, Any]]] = None,
    stages: Optional[List[PipelineStageAgent]] = None
) -> SequentialPipelinePattern
```

---

## Quick Start

### Basic Usage (Zero-Config)

```python
from kaizen.agents.coordination import create_sequential_pipeline
from kaizen.agents.coordination.sequential_pipeline import PipelineStageAgent
from kaizen.core.base_agent import BaseAgentConfig

# 1. Create pattern
pipeline = create_sequential_pipeline()

# 2. Add stages
pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "extract"))
pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "transform"))
pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "load"))

# 3. Execute pipeline
result = pipeline.execute_pipeline(
    initial_input="Process this data",
    context="ETL workflow for customer data"
)

# 4. Get results
print(f"Final Output: {result['final_output']}")
print(f"Stages Executed: {result['stage_count']}")

# 5. Get stage-by-stage results
stage_results = pipeline.get_stage_results(result['pipeline_id'])
for stage in stage_results:
    print(f"{stage['stage_name']}: {stage['stage_status']}")
```

### With Custom Configuration

```python
# Create pipeline with specific model
pipeline = create_sequential_pipeline(
    model="gpt-4",
    temperature=0.7,
    max_tokens=1500
)

# Add stages
pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "analyze"))
pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "process"))
pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "summarize"))

# Execute
result = pipeline.execute_pipeline(
    initial_input="Analyze quarterly sales data: Q1=$100k, Q2=$150k, Q3=$125k, Q4=$175k",
    context="Financial analysis pipeline"
)
```

---

## Usage Examples

### Example 13: Basic Usage
- **File**: `13_sequential_pipeline_basic.py`
- **Focus**: Zero-config pattern creation, basic workflow
- **Time**: 5 minutes
- **Learning**: Pattern creation, stage addition, execution, result retrieval

### Example 14: Configuration
- **File**: `14_sequential_pipeline_configuration.py`
- **Focus**: Progressive configuration options
- **Time**: 5 minutes
- **Learning**: Custom models, stage-specific configs, environment variables, pre-built stages

### Example 15: Advanced Features
- **File**: `15_sequential_pipeline_advanced.py`
- **Focus**: Complex workflows, error handling, metadata tracking
- **Time**: 10 minutes
- **Learning**: Multi-stage workflows, partial failures, performance optimization, edge cases

### Example 16: Real-World ETL
- **File**: `16_sequential_pipeline_etl_real_world.py`
- **Focus**: Production ETL pipeline for customer transaction processing
- **Time**: 15 minutes
- **Learning**: ETL implementation, data quality, batch processing, reporting

---

## API Reference

### Factory Function

#### `create_sequential_pipeline()`

Create Sequential Pipeline Pattern with zero-config or progressive configuration.

**Parameters**:
- `llm_provider` (str, optional): LLM provider (default: "openai" or KAIZEN_LLM_PROVIDER)
- `model` (str, optional): Model name (default: "gpt-3.5-turbo" or KAIZEN_MODEL)
- `temperature` (float, optional): Temperature 0.0-1.0 (default: 0.7 or KAIZEN_TEMPERATURE)
- `max_tokens` (int, optional): Max tokens (default: 1000 or KAIZEN_MAX_TOKENS)
- `shared_memory` (SharedMemoryPool, optional): Shared memory instance (default: creates new)
- `stage_configs` (List[Dict], optional): Per-stage configurations (default: uses basic params)
- `stages` (List[PipelineStageAgent], optional): Pre-built stages (default: empty list)

**Returns**: `SequentialPipelinePattern` instance

**Raises**:
- `ValueError`: If stage_configs length doesn't match stages
- `TypeError`: If stages contains non-PipelineStageAgent items

**Example**:
```python
# Zero-config
pipeline = create_sequential_pipeline()

# Basic config
pipeline = create_sequential_pipeline(model="gpt-4", temperature=0.7)

# Stage-specific configs
pipeline = create_sequential_pipeline(
    stage_configs=[
        {'model': 'gpt-3.5-turbo', 'temperature': 0.3},
        {'model': 'gpt-4', 'temperature': 0.8},
        {'model': 'gpt-3.5-turbo', 'temperature': 0.2}
    ]
)

# Pre-built stages
pipeline = create_sequential_pipeline(
    stages=[extract_agent, transform_agent, load_agent]
)
```

---

### SequentialPipelinePattern Class

#### `execute_pipeline(initial_input: str, context: str = "") -> Dict[str, Any]`

Execute the full pipeline from first stage to last.

**Parameters**:
- `initial_input` (str): Initial input for first stage
- `context` (str, optional): Context passed to all stages (default: "")

**Returns**: Dictionary containing:
```python
{
    'pipeline_id': str,           # Unique pipeline execution ID
    'stage_count': int,           # Number of stages executed
    'final_output': str,          # Output from final stage
    'status': str                 # 'completed', 'partial', or 'empty'
}
```

**Behavior**:
- If pipeline is empty: Returns passthrough (initial_input = final_output)
- For each stage: Passes previous output as input + original context
- Stores all stage results in shared memory
- Continues execution even if a stage fails (partial results)

**Example**:
```python
result = pipeline.execute_pipeline(
    initial_input="Customer data to process",
    context="ETL workflow with validation"
)

print(f"Pipeline ID: {result['pipeline_id']}")
print(f"Stages: {result['stage_count']}")
print(f"Output: {result['final_output']}")
print(f"Status: {result['status']}")
```

---

#### `add_stage(agent: PipelineStageAgent) -> None`

Add a stage agent to the pipeline.

**Parameters**:
- `agent` (PipelineStageAgent): Stage agent to add

**Behavior**:
- Appends agent to stages list
- Stages execute in order they are added
- Can add unlimited stages

**Example**:
```python
pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "extract"))
pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "transform"))
pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "load"))

print(f"Total stages: {len(pipeline.stages)}")  # Output: 3
```

---

#### `get_stage_results(pipeline_id: str) -> List[Dict[str, Any]]`

Retrieve all stage results for a pipeline execution.

**Parameters**:
- `pipeline_id` (str): Unique pipeline execution ID from execute_pipeline()

**Returns**: List of dictionaries, each containing:
```python
{
    'pipeline_id': str,
    'stage_index': int,
    'stage_name': str,
    'stage_input': str,
    'stage_output': str,
    'stage_metadata': str,      # JSON string
    'stage_status': str,        # 'success', 'partial', 'failed'
    'timestamp': str
}
```

**Example**:
```python
result = pipeline.execute_pipeline("Data to process")
stage_results = pipeline.get_stage_results(result['pipeline_id'])

for stage in stage_results:
    print(f"Stage {stage['stage_index']}: {stage['stage_name']}")
    print(f"  Status: {stage['stage_status']}")
    print(f"  Input: {stage['stage_input'][:50]}...")
    print(f"  Output: {stage['stage_output'][:50]}...")
```

---

#### `validate_pattern() -> bool`

Validate pattern initialization (inherited from BaseMultiAgentPattern).

**Returns**: `True` if all agents initialized correctly, `False` otherwise

**Example**:
```python
if pipeline.validate_pattern():
    print("✓ Pattern validated")
else:
    print("✗ Pattern validation failed")
```

---

#### `get_agents() -> List[BaseAgent]`

Get all stage agents.

**Returns**: List of PipelineStageAgent instances

**Example**:
```python
agents = pipeline.get_agents()
print(f"Total agents: {len(agents)}")
```

---

#### `get_agent_ids() -> List[str]`

Get all stage agent IDs.

**Returns**: List of agent ID strings

**Example**:
```python
agent_ids = pipeline.get_agent_ids()
print(f"Agent IDs: {agent_ids}")  # ['extract', 'transform', 'load']
```

---

#### `clear_shared_memory() -> None`

Clear shared memory (inherited from BaseMultiAgentPattern).

**Example**:
```python
pipeline.clear_shared_memory()
print("✓ Memory cleared, ready for next execution")
```

---

### PipelineStageAgent Class

#### `__init__(config: BaseAgentConfig, agent_id: str, shared_memory: Optional[SharedMemoryPool] = None)`

Initialize pipeline stage agent.

**Parameters**:
- `config` (BaseAgentConfig): Agent configuration
- `agent_id` (str): Unique identifier for this stage
- `shared_memory` (SharedMemoryPool, optional): Shared memory instance

**Example**:
```python
agent = PipelineStageAgent(
    config=BaseAgentConfig(model="gpt-4", temperature=0.7),
    agent_id="transform_stage"
)
```

---

#### `process_stage(stage_input: str, stage_name: str, context: str = "") -> Dict[str, Any]`

Process stage with given input.

**Parameters**:
- `stage_input` (str): Input from previous stage
- `stage_name` (str): Name of this stage
- `context` (str, optional): Pipeline context

**Returns**: Dictionary containing:
```python
{
    'stage_output': str,
    'stage_metadata': str,  # JSON
    'stage_status': str     # 'success', 'partial', 'failed'
}
```

**Example**:
```python
result = agent.process_stage(
    stage_input="Raw data",
    stage_name="extract",
    context="Data processing workflow"
)

print(f"Output: {result['stage_output']}")
print(f"Status: {result['stage_status']}")
```

---

## Configuration

### Configuration Levels

#### Level 1: Zero-Config (Fastest)

```python
pipeline = create_sequential_pipeline()
```

Uses:
- Provider: "openai" (or KAIZEN_LLM_PROVIDER)
- Model: "gpt-3.5-turbo" (or KAIZEN_MODEL)
- Temperature: 0.7 (or KAIZEN_TEMPERATURE)
- Max tokens: 1000 (or KAIZEN_MAX_TOKENS)

---

#### Level 2: Basic Parameters

```python
pipeline = create_sequential_pipeline(
    model="gpt-4",
    temperature=0.7,
    max_tokens=1500
)
```

Override specific parameters while keeping others as defaults.

---

#### Level 3: Stage-Specific Configs

```python
pipeline = create_sequential_pipeline(
    stage_configs=[
        {'model': 'gpt-3.5-turbo', 'temperature': 0.3, 'max_tokens': 500},
        {'model': 'gpt-4', 'temperature': 0.8, 'max_tokens': 1500},
        {'model': 'gpt-3.5-turbo', 'temperature': 0.2, 'max_tokens': 300}
    ]
)
```

Different configuration for each stage based on complexity.

---

#### Level 4: Pre-Built Stages

```python
# Create custom stages
extract = PipelineStageAgent(
    config=BaseAgentConfig(model="gpt-3.5-turbo", temperature=0.5),
    agent_id="extract"
)

transform = PipelineStageAgent(
    config=BaseAgentConfig(model="gpt-4", temperature=0.8),
    agent_id="transform"
)

# Create pipeline with pre-built stages
pipeline = create_sequential_pipeline(stages=[extract, transform])
```

Full control over stage creation and configuration.

---

### Environment Variables

If not overridden, configuration uses these environment variables:

- `KAIZEN_LLM_PROVIDER` - LLM provider (default: "openai")
- `KAIZEN_MODEL` - Model name (default: "gpt-3.5-turbo")
- `KAIZEN_TEMPERATURE` - Temperature (default: 0.7)
- `KAIZEN_MAX_TOKENS` - Max tokens (default: 1000)

**Example**:
```bash
export KAIZEN_MODEL=gpt-4
export KAIZEN_TEMPERATURE=0.8
```

```python
pipeline = create_sequential_pipeline()  # Uses env vars
```

---

## Best Practices

### Stage Configuration

#### 1. Match Model to Stage Complexity

```python
# ✅ GOOD: Fast model for simple stages, powerful for complex
stage_configs=[
    {'model': 'gpt-3.5-turbo', 'temperature': 0.3},  # Extract (simple)
    {'model': 'gpt-4', 'temperature': 0.8},          # Transform (complex)
    {'model': 'gpt-3.5-turbo', 'temperature': 0.2}   # Load (simple)
]

# ❌ BAD: Same powerful model for all stages (costly)
stage_configs=[
    {'model': 'gpt-4', 'temperature': 0.7},
    {'model': 'gpt-4', 'temperature': 0.7},
    {'model': 'gpt-4', 'temperature': 0.7}
]
```

---

#### 2. Use Appropriate Temperature

```python
# ✅ GOOD: Temperature matches task
pipeline = create_sequential_pipeline(
    stage_configs=[
        {'temperature': 0.1},  # Extraction (deterministic)
        {'temperature': 0.8},  # Creative transformation
        {'temperature': 0.1}   # Formatting (deterministic)
    ]
)

# ❌ BAD: High temp for deterministic tasks
pipeline = create_sequential_pipeline(
    stage_configs=[
        {'temperature': 0.9},  # Extraction should be deterministic!
        {'temperature': 0.9},
        {'temperature': 0.9}
    ]
)
```

---

#### 3. Optimize Token Usage

```python
# ✅ GOOD: Token limit matches output size
stage_configs=[
    {'max_tokens': 500},   # Extract (short output)
    {'max_tokens': 1500},  # Transform (detailed output)
    {'max_tokens': 300}    # Format (concise output)
]

# ❌ BAD: Excessive tokens for all stages
stage_configs=[
    {'max_tokens': 2000},  # Wasteful for simple extraction
    {'max_tokens': 2000},
    {'max_tokens': 2000}
]
```

---

### Pipeline Design

#### 1. Keep Stages Focused

```python
# ✅ GOOD: Single responsibility per stage
pipeline.add_stage(PipelineStageAgent(config, "extract"))      # Just extract
pipeline.add_stage(PipelineStageAgent(config, "validate"))     # Just validate
pipeline.add_stage(PipelineStageAgent(config, "transform"))    # Just transform

# ❌ BAD: One stage doing everything
pipeline.add_stage(PipelineStageAgent(config, "do_everything"))
```

---

#### 2. Order Stages Logically

```python
# ✅ GOOD: Logical progression
pipeline.add_stage(extract)    # 1. Get data
pipeline.add_stage(validate)   # 2. Check quality
pipeline.add_stage(transform)  # 3. Process
pipeline.add_stage(load)       # 4. Store

# ❌ BAD: Illogical order
pipeline.add_stage(load)       # Can't load before extracting!
pipeline.add_stage(extract)
pipeline.add_stage(transform)
```

---

#### 3. Use Descriptive Stage Names

```python
# ✅ GOOD: Clear stage names
pipeline.add_stage(PipelineStageAgent(config, "extract_customer_data"))
pipeline.add_stage(PipelineStageAgent(config, "validate_email_format"))
pipeline.add_stage(PipelineStageAgent(config, "transform_to_json"))

# ❌ BAD: Vague names
pipeline.add_stage(PipelineStageAgent(config, "stage1"))
pipeline.add_stage(PipelineStageAgent(config, "stage2"))
pipeline.add_stage(PipelineStageAgent(config, "stage3"))
```

---

### Error Handling

#### 1. Check Pipeline Status

```python
result = pipeline.execute_pipeline(data)

if result['status'] == 'completed':
    print("✓ All stages successful")
elif result['status'] == 'partial':
    print("⚠️  Some stages failed")
    # Check stage results for details
    stage_results = pipeline.get_stage_results(result['pipeline_id'])
    for stage in stage_results:
        if stage['stage_status'] != 'success':
            print(f"Failed stage: {stage['stage_name']}")
```

---

#### 2. Validate Before Processing

```python
# ✅ GOOD: Validate pattern before execution
if pipeline.validate_pattern():
    result = pipeline.execute_pipeline(data)
else:
    print("✗ Pattern validation failed")

# ❌ BAD: Execute without validation
result = pipeline.execute_pipeline(data)  # May fail unexpectedly
```

---

#### 3. Handle Empty Pipelines

```python
# ✅ GOOD: Check stage count
if len(pipeline.stages) == 0:
    print("⚠️  Pipeline is empty")
else:
    result = pipeline.execute_pipeline(data)

# Pipeline handles this gracefully (passthrough), but checking is better
```

---

### Performance Optimization

#### 1. Reuse Pipeline Instances

```python
# ✅ GOOD: Reuse pipeline, clear memory between runs
pipeline = create_sequential_pipeline()
pipeline.add_stage(extract)
pipeline.add_stage(transform)
pipeline.add_stage(load)

for data in datasets:
    result = pipeline.execute_pipeline(data)
    # Process result
    pipeline.clear_shared_memory()  # Clean up

# ❌ BAD: Create new pipeline each time
for data in datasets:
    pipeline = create_sequential_pipeline()
    pipeline.add_stage(extract)
    pipeline.add_stage(transform)
    pipeline.add_stage(load)
    result = pipeline.execute_pipeline(data)
```

---

#### 2. Batch Processing

```python
# ✅ GOOD: Process multiple items with same pipeline
results = []
for item in batch:
    result = pipeline.execute_pipeline(item)
    results.append(result)
    pipeline.clear_shared_memory()

# Consider: Could you batch at a higher level?
```

---

## Use Cases

### 1. ETL Pipelines

**Scenario**: Extract, transform, and load customer transaction data

```python
pipeline = create_sequential_pipeline(
    stage_configs=[
        {'model': 'gpt-3.5-turbo', 'temperature': 0.3},  # Extract
        {'model': 'gpt-3.5-turbo', 'temperature': 0.1},  # Validate
        {'model': 'gpt-4', 'temperature': 0.5},          # Transform
        {'model': 'gpt-3.5-turbo', 'temperature': 0.3},  # Enrich
        {'model': 'gpt-3.5-turbo', 'temperature': 0.1}   # Load
    ]
)

pipeline.add_stage(PipelineStageAgent(config, "extract"))
pipeline.add_stage(PipelineStageAgent(config, "validate"))
pipeline.add_stage(PipelineStageAgent(config, "transform"))
pipeline.add_stage(PipelineStageAgent(config, "enrich"))
pipeline.add_stage(PipelineStageAgent(config, "load"))

result = pipeline.execute_pipeline(
    initial_input=raw_transaction_data,
    context="ETL for customer transactions - ensure data quality"
)
```

**Benefits**:
- Structured data flow
- Quality validation
- Stage-by-stage tracking
- Error isolation per stage

---

### 2. Content Generation Pipeline

**Scenario**: Research → Outline → Draft → Edit → Publish

```python
pipeline = create_sequential_pipeline(model="gpt-4")

pipeline.add_stage(PipelineStageAgent(config, "research"))
pipeline.add_stage(PipelineStageAgent(config, "outline"))
pipeline.add_stage(PipelineStageAgent(config, "draft"))
pipeline.add_stage(PipelineStageAgent(config, "edit"))
pipeline.add_stage(PipelineStageAgent(config, "finalize"))

result = pipeline.execute_pipeline(
    initial_input="Write article about AI safety in autonomous vehicles",
    context="Target: Technical blog, 1000 words, include examples"
)

final_article = result['final_output']
```

**Benefits**:
- Iterative refinement
- Context preservation (requirements stay consistent)
- Each stage builds on previous work
- Quality improves through pipeline

---

### 3. Document Processing

**Scenario**: OCR → Parse → Classify → Extract → Validate

```python
pipeline = create_sequential_pipeline()

pipeline.add_stage(PipelineStageAgent(config, "ocr_text"))
pipeline.add_stage(PipelineStageAgent(config, "parse_structure"))
pipeline.add_stage(PipelineStageAgent(config, "classify_document"))
pipeline.add_stage(PipelineStageAgent(config, "extract_fields"))
pipeline.add_stage(PipelineStageAgent(config, "validate_data"))

result = pipeline.execute_pipeline(
    initial_input=scanned_document,
    context="Legal document processing - extract key fields"
)
```

**Benefits**:
- Handles complex document workflows
- Each stage specialized
- Progressive data extraction
- Validation at end of pipeline

---

### 4. Data Analysis Workflow

**Scenario**: Collect → Clean → Analyze → Aggregate → Summarize

```python
pipeline = create_sequential_pipeline(model="gpt-4")

pipeline.add_stage(PipelineStageAgent(config, "collect_data"))
pipeline.add_stage(PipelineStageAgent(config, "clean_outliers"))
pipeline.add_stage(PipelineStageAgent(config, "analyze_trends"))
pipeline.add_stage(PipelineStageAgent(config, "aggregate_stats"))
pipeline.add_stage(PipelineStageAgent(config, "summarize_insights"))

result = pipeline.execute_pipeline(
    initial_input="Q1 sales: $100k, Q2: $150k, Q3: $125k, Q4: $175k",
    context="Annual sales analysis - identify trends and opportunities"
)
```

**Benefits**:
- Systematic analysis
- Data quality ensured early
- Progressive insight generation
- Final summary for stakeholders

---

### 5. Customer Onboarding Flow

**Scenario**: Intake → Verify → Enrich → Setup → Welcome

```python
pipeline = create_sequential_pipeline()

pipeline.add_stage(PipelineStageAgent(config, "intake_info"))
pipeline.add_stage(PipelineStageAgent(config, "verify_identity"))
pipeline.add_stage(PipelineStageAgent(config, "enrich_profile"))
pipeline.add_stage(PipelineStageAgent(config, "setup_account"))
pipeline.add_stage(PipelineStageAgent(config, "generate_welcome"))

result = pipeline.execute_pipeline(
    initial_input=customer_application,
    context="New customer onboarding - ensure complete setup"
)
```

**Benefits**:
- Structured onboarding
- Verification before setup
- Profile enrichment
- Personalized welcome message

---

## Advanced Topics

### Custom Stage Implementations

Create specialized stage agents by extending PipelineStageAgent:

```python
class DataValidationStage(PipelineStageAgent):
    """Stage that validates data quality."""

    def process_stage(self, stage_input: str, stage_name: str, context: str = "") -> Dict[str, Any]:
        # Custom validation logic
        is_valid = self._validate_data(stage_input)

        if is_valid:
            return {
                'stage_output': stage_input,  # Pass through
                'stage_metadata': json.dumps({'validation': 'passed'}),
                'stage_status': 'success'
            }
        else:
            return {
                'stage_output': stage_input,  # Still pass through
                'stage_metadata': json.dumps({'validation': 'failed', 'errors': [...]}),
                'stage_status': 'partial'  # Flag as partial
            }

    def _validate_data(self, data: str) -> bool:
        # Implement validation logic
        return True

# Use custom stage
pipeline = create_sequential_pipeline()
pipeline.add_stage(PipelineStageAgent(config, "extract"))
pipeline.add_stage(DataValidationStage(config, "validate"))
pipeline.add_stage(PipelineStageAgent(config, "transform"))
```

---

### Stage Metadata Tracking

Track additional information in stage metadata:

```python
# In custom stage
metadata = {
    'execution_time_ms': 150,
    'tokens_used': 450,
    'confidence_score': 0.95,
    'data_quality': 'high',
    'processing_notes': 'All fields validated'
}

return {
    'stage_output': result,
    'stage_metadata': json.dumps(metadata),
    'stage_status': 'success'
}

# Retrieve and analyze
stage_results = pipeline.get_stage_results(pipeline_id)
for stage in stage_results:
    metadata = json.loads(stage['stage_metadata'])
    print(f"{stage['stage_name']}: {metadata}")
```

---

### Conditional Stage Execution

Implement conditional logic by checking previous stage results:

```python
class ConditionalStage(PipelineStageAgent):
    def process_stage(self, stage_input: str, stage_name: str, context: str = "") -> Dict[str, Any]:
        # Check if we should process
        if "skip_processing" in stage_input:
            return {
                'stage_output': stage_input,
                'stage_metadata': json.dumps({'skipped': True}),
                'stage_status': 'success'
            }

        # Normal processing
        result = self.run(stage_input=stage_input, stage_name=stage_name, context=context)
        # ... return result
```

---

### Pipeline Branching (Advanced)

Create branching logic by examining stage results:

```python
# Execute main pipeline
result = pipeline.execute_pipeline(data)

# Check results and branch
stage_results = pipeline.get_stage_results(result['pipeline_id'])
validation_stage = next(s for s in stage_results if s['stage_name'] == 'validate')

if validation_stage['stage_status'] == 'success':
    # Continue with normal pipeline
    load_pipeline = create_sequential_pipeline(stages=[load_stage])
    load_result = load_pipeline.execute_pipeline(result['final_output'])
else:
    # Route to error handling pipeline
    error_pipeline = create_sequential_pipeline(stages=[error_stage])
    error_result = error_pipeline.execute_pipeline(result['final_output'])
```

---

## Troubleshooting

### Issue: Empty final output

**Symptom**: `result['final_output']` is empty or unexpected

**Causes**:
1. Last stage returned empty output
2. Stage failed silently
3. Output field not populated

**Solution**:
```python
# Check stage results
stage_results = pipeline.get_stage_results(result['pipeline_id'])
for stage in stage_results:
    print(f"{stage['stage_name']}: output_length={len(stage['stage_output'])}")

# Look for empty outputs or failed stages
```

---

### Issue: Pipeline execution hangs

**Symptom**: `execute_pipeline()` doesn't return

**Causes**:
1. LLM API timeout
2. Very large input/output
3. Infinite loop in custom stage

**Solution**:
```python
# 1. Check stage configs for reasonable token limits
stage_configs=[
    {'max_tokens': 500},   # Reasonable limit
    {'max_tokens': 1500},
    {'max_tokens': 300}
]

# 2. Monitor execution
import time
start = time.time()
result = pipeline.execute_pipeline(data)
print(f"Execution time: {time.time() - start}s")

# 3. Add timeout to LLM calls (in custom stages)
```

---

### Issue: Partial pipeline failures

**Symptom**: `result['status'] == 'partial'`

**Causes**:
1. Stage returned status='partial' or status='failed'
2. Exception in stage processing
3. Invalid stage output

**Solution**:
```python
# Identify failed stage
stage_results = pipeline.get_stage_results(result['pipeline_id'])
for stage in stage_results:
    if stage['stage_status'] != 'success':
        print(f"Failed stage: {stage['stage_name']}")
        print(f"Input: {stage['stage_input']}")
        print(f"Output: {stage['stage_output']}")
        print(f"Status: {stage['stage_status']}")

# Fix the specific stage or add error handling
```

---

### Issue: Context not preserved

**Symptom**: Later stages don't seem to use original context

**Causes**:
1. Context not passed to execute_pipeline()
2. Stages not using context parameter
3. Context overwritten in stage logic

**Solution**:
```python
# 1. Always pass context
result = pipeline.execute_pipeline(
    initial_input=data,
    context="Important requirements here"  # Don't forget!
)

# 2. In custom stages, use context
def process_stage(self, stage_input: str, stage_name: str, context: str = ""):
    # Use context in processing
    prompt = f"Given context: {context}\nProcess: {stage_input}"
    # ...
```

---

### Issue: Stage results not found

**Symptom**: `get_stage_results()` returns empty list

**Causes**:
1. Wrong pipeline_id
2. Shared memory cleared
3. No stages executed

**Solution**:
```python
# 1. Save pipeline_id immediately
result = pipeline.execute_pipeline(data)
pipeline_id = result['pipeline_id']  # Save this!

# 2. Get results before clearing memory
stage_results = pipeline.get_stage_results(pipeline_id)
# Now safe to clear:
pipeline.clear_shared_memory()

# 3. Check if stages executed
print(f"Stages executed: {result['stage_count']}")
```

---

### Debug Mode

Enable detailed logging for troubleshooting:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Run pipeline
result = pipeline.execute_pipeline(data)

# Detailed stage inspection
stage_results = pipeline.get_stage_results(result['pipeline_id'])
for idx, stage in enumerate(stage_results, 1):
    print(f"\n{'='*70}")
    print(f"STAGE {idx}: {stage['stage_name']}")
    print(f"{'='*70}")
    print(f"Status: {stage['stage_status']}")
    print(f"Input length: {len(stage['stage_input'])}")
    print(f"Output length: {len(stage['stage_output'])}")
    print(f"Input preview: {stage['stage_input'][:100]}...")
    print(f"Output preview: {stage['stage_output'][:100]}...")
    print(f"Metadata: {stage['stage_metadata']}")
```

---

## Pattern Comparison

### Sequential Pipeline vs SupervisorWorker

| Feature | Sequential Pipeline | SupervisorWorker |
|---------|---------------------|------------------|
| Execution | Sequential (A → B → C) | Parallel (A, B, C simultaneously) |
| Task Type | Same task, multiple stages | Different tasks, different workers |
| Context | Preserved across stages | Shared across workers |
| Use Case | ETL, content generation | Research aggregation, parallel processing |
| When to Use | Output of A feeds into B | Tasks independent, results aggregated |

**Example**:
```python
# Sequential: Each stage builds on previous
pipeline.add_stage(extract)      # Output → Transform input
pipeline.add_stage(transform)    # Output → Load input
pipeline.add_stage(load)

# SupervisorWorker: All tasks independent
supervisor.add_worker(researcher1)   # Independent research
supervisor.add_worker(researcher2)   # Independent research
supervisor.add_worker(researcher3)   # Independent research
# Results aggregated at end
```

---

### Sequential Pipeline vs Handoff

| Feature | Sequential Pipeline | Handoff |
|---------|---------------------|---------|
| Routing | Predetermined order | Dynamic based on complexity |
| Stages | Fixed sequence | Conditional escalation |
| Use Case | Known workflow | Tier-based support |
| When to Use | Workflow steps known | Expertise discovery needed |

**Example**:
```python
# Sequential: Always runs all stages
pipeline: extract → transform → load  (always this order)

# Handoff: Dynamic routing based on complexity
handoff: tier1 → (if complex) tier2 → (if very complex) tier3
```

---

## Summary

The Sequential Pipeline Pattern provides:

✅ **Linear agent chaining** with context preservation
✅ **Stage-by-stage processing** for multi-step workflows
✅ **Zero-config** with progressive configuration options
✅ **Error resilience** with partial failure handling
✅ **Result tracking** for all intermediate stages
✅ **Production-ready** for ETL, content generation, and data processing

### Quick Reference

```python
# Create
pipeline = create_sequential_pipeline()

# Add stages
pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "stage1"))
pipeline.add_stage(PipelineStageAgent(BaseAgentConfig(), "stage2"))

# Execute
result = pipeline.execute_pipeline(data, context="...")

# Get results
stage_results = pipeline.get_stage_results(result['pipeline_id'])

# Clean up
pipeline.clear_shared_memory()
```

### Next Steps

- Try **Example 13**: Basic usage
- Try **Example 14**: Configuration options
- Try **Example 15**: Advanced features
- Try **Example 16**: Real-world ETL pipeline

---

**Version**: 1.0
**Last Updated**: 2025-10-04
**Pattern Type**: Multi-Agent Coordination
**Production Ready**: ✅ YES
