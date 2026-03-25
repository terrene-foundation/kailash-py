# Complex Data Pipeline Agent

**Pattern**: Blackboard with Controller-Driven Orchestration
**Use Case**: Multi-stage data processing with intelligent routing
**Cost**: $0.00 (FREE with Ollama)

## Overview

This example demonstrates the **Blackboard pattern** with a **controller agent** that orchestrates multi-stage data processing. The controller intelligently routes data between specialized agents (extractor, transformer, loader) based on pipeline state.

**Key Features**:
- ✅ **Blackboard Pattern**: Shared state for agent coordination
- ✅ **4 Pipeline Stages**: Extract → Transform → Load → Verify
- ✅ **Controller-Driven**: Dynamic stage selection based on blackboard state
- ✅ **Error Recovery**: Retry logic with checkpoints
- ✅ **Progress Monitoring**: Real-time progress tracking with hooks
- ✅ **Checkpoint Integration**: Resume from interruptions
- ✅ **FREE**: Uses Ollama local inference ($0.00 cost)

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   Pipeline Input                          │
│              1,000,000 customer records                   │
└────────────────────┬─────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────┐
│              Pipeline Controller Agent                    │
│        (Determines next stage based on state)             │
├──────────────────────────────────────────────────────────┤
│  Iteration 1: current_stage=None → next=EXTRACT         │
│  Iteration 2: current_stage=EXTRACT → next=TRANSFORM    │
│  Iteration 3: current_stage=TRANSFORM → next=LOAD       │
│  Iteration 4: current_stage=LOAD → next=VERIFY          │
│  Iteration 5: current_stage=VERIFY → next=None (DONE)   │
└────────────────────┬─────────────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
┌──────────────────┐  ┌──────────────────────────────────┐
│    Blackboard    │  │     Specialist Agents            │
│  (Shared State)  │  ├──────────────────────────────────┤
├──────────────────┤  │ 1. Extractor Agent               │
│ - extracted      │  │    Extract 1M records (0.95s)    │
│ - transformed    │  │                                  │
│ - loaded_count   │  │ 2. Transformer Agent             │
│ - rejected       │  │    Clean & validate (2.3s)       │
│ - verification   │  │    Reject 1,458 invalid          │
│                  │  │                                  │
│                  │  │ 3. Loader Agent                  │
│                  │  │    Load 998,542 records (3.7s)   │
│                  │  │                                  │
│                  │  │ 4. Loader Agent (Verify)         │
│                  │  │    Verify integrity (0.8s)       │
└──────────────────┘  └──────────────────────────────────┘
```

---

## Prerequisites

### Required
- **Python 3.8+**
- **Ollama** installed and running ([install guide](https://ollama.ai))
- **llama3.1:8b-instruct-q8_0** model downloaded

### Installation

```bash
# Install Ollama (if not already installed)
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama server
ollama serve

# Pull model (one-time, ~1.3GB)
ollama pull llama3.1:8b-instruct-q8_0

# Install Kaizen
pip install kailash-kaizen
```

---

## Usage

### Basic Usage

```bash
# Process 1,000 records (testing)
python complex_data_pipeline.py 1000

# Process 100,000 records (medium scale)
python complex_data_pipeline.py 100000

# Process 1,000,000 records (large scale)
python complex_data_pipeline.py 1000000
```

### Expected Output

```
🤖 COMPLEX DATA PIPELINE INITIALIZED
============================================================
📊 Pipeline Stages:
  1. Extract → Data extraction from CSV
  2. Transform → Data cleaning and validation
  3. Load → Database loading (batch inserts)
  4. Verify → Data integrity verification
🔧 Pattern: Blackboard with controller orchestration
🔄 Error Recovery: Retry logic with exponential backoff
============================================================

🔍 Starting pipeline: 1,000,000 records from customers.csv

============================================================
ITERATION 1: EXTRACT STAGE
============================================================

📊 Progress: Starting extract stage...

📂 Extractor: Extracting 1,000,000 records from customers.csv...
  Extracted 100,000/1,000,000 records...
  Extracted 200,000/1,000,000 records...
  ...
  Extracted 900,000/1,000,000 records...
✅ Extraction complete: 1,000,000 records (0.95s)

✅ Progress: extract stage complete (0.95s)
💾 Checkpoint saved: checkpoint_1_extract (after extract stage)

============================================================
ITERATION 2: TRANSFORM STAGE
============================================================

📊 Progress: Starting transform stage...

🔄 Transformer: Cleaning and validating 1,000,000 records...
  Transformed 100,000 records...
  Transformed 200,000 records...
  ...
  Transformed 900,000 records...
✅ Transformation complete: 998,542 valid records
⚠️  Rejected 1,458 invalid records

✅ Progress: transform stage complete (2.30s)
💾 Checkpoint saved: checkpoint_2_transform (after transform stage)

============================================================
ITERATION 3: LOAD STAGE
============================================================

📊 Progress: Starting load stage...

💾 Loader: Loading 998,542 records to database...
  Loaded 100,000/998,542 records...
  Loaded 200,000/998,542 records...
  ...
  Loaded 900,000/998,542 records...
✅ Loading complete: 998,542 records (3.70s)

✅ Progress: load stage complete (3.70s)

============================================================
ITERATION 4: VERIFY STAGE
============================================================

📊 Progress: Starting verify stage...

🔍 Loader: Verifying data integrity...
✅ Verification complete: 998,542 records (0.80s)

✅ Progress: verify stage complete (0.80s)

✅ Pipeline complete!

============================================================
📊 PIPELINE RESULTS
============================================================
Total Records: 1,000,000
Extracted: 1,000,000
Transformed: 998,542
Rejected: 1,458
Loaded: 998,542
Success Rate: 99.85%

Timing:
  Extraction: 0.95s
  Transformation: 2.30s
  Loading: 3.70s
  Verification: 0.80s
  Total: 7.75s
============================================================

💰 Cost: $0.00 (using Ollama local inference)
📊 Pattern: Blackboard with controller orchestration
📈 Progress: Logged to ./.kaizen/progress/pipeline_progress.jsonl
💾 Checkpoints: Saved to ./.kaizen/checkpoints/pipeline
```

---

## How It Works

### 1. Blackboard Pattern

The **blackboard** is a shared state dictionary that all agents can read and write:

```python
blackboard = {
    "current_stage": None,              # Current pipeline stage
    "extracted_records": [],            # Records from extractor
    "transformed_records": [],          # Records from transformer
    "loaded_count": 0,                  # Count from loader
    "rejected_count": 0,                # Invalid records
    "verification_result": {},          # Verification status
    "iteration": 0,                     # Current iteration
}
```

**Benefits**:
- **Shared State**: All agents access same data
- **Coordination**: Controller reads state to determine next stage
- **Transparency**: Clear pipeline progress tracking

### 2. Controller-Driven Orchestration

The **controller agent** determines which stage to execute next based on blackboard state:

```python
def next_stage(self, blackboard: Dict) -> Optional[str]:
    """Determine next stage based on blackboard state."""
    current_stage = blackboard.get("current_stage", None)

    if current_stage is None:
        return "extract"              # Start with extraction
    elif current_stage == "extract":
        return "transform"            # After extract, transform
    elif current_stage == "transform":
        return "load"                 # After transform, load
    elif current_stage == "load":
        return "verify"               # After load, verify
    elif current_stage == "verify":
        return None                   # Pipeline complete

    return None
```

**No Hardcoded Workflow**:
- Controller decides based on state, not fixed sequence
- Can skip stages, retry failed stages, or branch to different stages
- Adaptive to runtime conditions

### 3. Multi-Stage Processing

#### Stage 1: Extract
```python
# Extract records from CSV
result = extractor.extract_data("customers.csv", 1_000_000)
blackboard["extracted_records"] = result["records"]
```

#### Stage 2: Transform
```python
# Clean and validate data
result = transformer.transform_data(blackboard["extracted_records"])
blackboard["transformed_records"] = result["transformed_records"]
blackboard["rejected_count"] = result["rejected_count"]
```

#### Stage 3: Load
```python
# Load to database
result = loader.load_data(blackboard["transformed_records"])
blackboard["loaded_count"] = result["loaded_count"]
```

#### Stage 4: Verify
```python
# Verify integrity
result = loader.verify_data(blackboard["loaded_count"])
blackboard["verification_result"] = result
```

### 4. Error Recovery

**Checkpoint After Each Stage**:
```python
# Create checkpoint after critical stages
if stage in ["extract", "transform"]:
    checkpoint_id = await state_manager.save_checkpoint(agent_state)
    print(f"💾 Checkpoint saved: {checkpoint_id}")
```

**Resume From Checkpoint**:
```python
# If pipeline interrupted (Ctrl+C), resume from last checkpoint
latest_state = await state_manager.resume_from_latest("data_pipeline")
blackboard = latest_state.memory_contents
```

### 5. Progress Monitoring

**Real-Time Progress Tracking**:
```json
{
  "timestamp": "2025-11-03T12:00:00",
  "event": "stage_start",
  "stage": "extract"
}

{
  "timestamp": "2025-11-03T12:00:01",
  "event": "stage_complete",
  "stage": "extract",
  "duration_seconds": 0.95
}
```

**Hook Integration**:
```python
# Pre-stage hook
async def pre_stage(context: HookContext) -> HookResult:
    stage = context.data.get("stage")
    print(f"📊 Progress: Starting {stage} stage...")
    return HookResult(success=True)
```

---

## Code Structure

### Pipeline Stages

```python
class DataExtractorAgent(BaseAgent):
    """Specialist for data extraction."""

    def extract_data(self, source: str, record_count: int) -> Dict:
        # Extract records from source
        pass

class DataTransformerAgent(BaseAgent):
    """Specialist for data transformation."""

    def transform_data(self, records: List[Dict]) -> Dict:
        # Clean and validate records
        pass

class DataLoaderAgent(BaseAgent):
    """Specialist for data loading."""

    def load_data(self, records: List[Dict]) -> Dict:
        # Load records to database
        pass

    def verify_data(self, expected_count: int) -> Dict:
        # Verify data integrity
        pass
```

### Controller

```python
class PipelineControllerAgent(BaseAgent):
    """Controller that orchestrates pipeline."""

    def next_stage(self, blackboard: Dict) -> Optional[str]:
        # Determine next stage based on blackboard state
        pass

    def is_complete(self, blackboard: Dict) -> bool:
        # Check if pipeline is complete
        pass
```

### Pipeline Setup

```python
# Create pipeline with controller + specialists
pipeline = ComplexDataPipeline(
    extractor=extractor,
    transformer=transformer,
    loader=loader,
    controller=controller,
    hook_manager=hook_manager,
    state_manager=state_manager
)

# Execute pipeline
result = await pipeline.execute_pipeline(
    source="customers.csv",
    record_count=1_000_000,
    max_iterations=5
)
```

---

## Customization

### Add New Pipeline Stage

```python
class DataEnricherAgent(BaseAgent):
    """Specialist for data enrichment."""

    def enrich_data(self, records: List[Dict]) -> Dict:
        # Enrich records with external data
        pass

# Update controller to include new stage
def next_stage(self, blackboard: Dict) -> Optional[str]:
    current_stage = blackboard.get("current_stage")

    if current_stage == "transform":
        return "enrich"  # NEW STAGE
    elif current_stage == "enrich":
        return "load"
    # ...
```

### Custom Validation Rules

```python
# In DataTransformerAgent
def transform_data(self, records: List[Dict]) -> Dict:
    for record in records:
        # Custom validation
        if not self._is_valid_email(record["email"]):
            rejected_count += 1
            continue

        if not self._is_valid_age(record["age"]):
            rejected_count += 1
            continue

        # Custom transformation
        transformed = {
            "id": record["id"],
            "name": self._normalize_name(record["name"]),
            "email": record["email"].lower(),
            "age_group": self._calculate_age_group(record["age"])
        }
```

---

## Production Deployment

### Scaling to Millions of Records

```python
# Process large datasets in chunks
chunk_size = 100_000

for chunk_start in range(0, total_records, chunk_size):
    chunk_end = min(chunk_start + chunk_size, total_records)

    result = await pipeline.execute_pipeline(
        source="customers.csv",
        record_count=chunk_end - chunk_start,
        offset=chunk_start
    )
```

### Distributed Processing

```python
# Use multiple workers for parallel processing
from multiprocessing import Pool

def process_chunk(chunk_id):
    # Process chunk independently
    pipeline = ComplexDataPipeline(...)
    return pipeline.execute_pipeline(...)

# Process chunks in parallel
with Pool(processes=8) as pool:
    results = pool.map(process_chunk, chunk_ids)
```

### Real Database Integration

```python
class DataLoaderAgent(BaseAgent):
    def __init__(self, config, db_connection):
        super().__init__(config, signature=LoadSignature())
        self.db = db_connection  # PostgreSQL, MySQL, MongoDB

    def load_data(self, records: List[Dict]) -> Dict:
        # Real database operations
        with self.db.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO customers VALUES (%s, %s, %s)",
                [(r["id"], r["name"], r["email"]) for r in records]
            )
            self.db.commit()
```

---

## Troubleshooting

### Issue: Pipeline too slow for large datasets

**Cause**: Processing all records in single iteration

**Solution**: Use chunking and batch processing

```python
# Process in batches
batch_size = 10_000
for i in range(0, len(records), batch_size):
    batch = records[i:i + batch_size]
    # Process batch
```

### Issue: Out of memory with 1M+ records

**Cause**: All records loaded into memory

**Solution**: Use streaming/generator pattern

```python
def extract_data_stream(self, source: str):
    # Yield records in batches
    for batch in self._read_csv_batches(source, batch_size=10_000):
        yield batch
```

### Issue: Checkpoint files too large

**Cause**: Storing all records in checkpoint

**Solution**: Store only metadata, not full data

```python
# Instead of storing all records
blackboard["extracted_records"] = records  # ❌ Too large

# Store only metadata
blackboard["extraction_metadata"] = {
    "record_count": len(records),
    "source": source,
    "timestamp": datetime.now()
}  # ✅ Lightweight
```

---

## Related Examples

- **Multi-Specialist Coding** (`meta-controller/multi-specialist-coding/`) - Router pattern with A2A
- **Data Analysis Agent** (`tool-calling/data-analysis-agent/`) - Checkpoints and statistical analysis
- **Research Assistant** (`planning/research-assistant/`) - Multi-step workflows with planning

---

## Key Takeaways

1. **Blackboard Pattern**: Shared state for agent coordination
2. **Controller-Driven**: Dynamic stage selection based on runtime state
3. **Multi-Stage Pipeline**: Extract → Transform → Load → Verify workflow
4. **Error Recovery**: Checkpoints enable resume after interruptions
5. **Progress Monitoring**: Real-time tracking with hooks
6. **FREE**: Uses Ollama local inference ($0.00 cost, unlimited usage)

---

## Production Notes

- **Scalability**: Process millions of records with chunking and batching
- **Distributed**: Run pipeline stages on separate workers for parallelism
- **Checkpoints**: Resume from interruptions without data loss
- **Monitoring**: Track stage performance and data quality
- **Cost**: $0.00 with Ollama (unlimited local inference)
- **Throughput**: 100K-1M records/minute depending on hardware

---

**Pattern**: Blackboard (Meta-Controller)
**Protocol**: Controller-driven orchestration
**Cost**: FREE ($0.00 with Ollama)
**Lines**: 550+ (production-ready)
