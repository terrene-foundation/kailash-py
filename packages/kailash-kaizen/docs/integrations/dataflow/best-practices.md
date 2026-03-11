# Kaizen-DataFlow Integration Best Practices

Production-ready patterns and recommendations for building robust AI-database applications.

## Architecture Patterns

### Optional Dependency Pattern

Always check DataFlow availability before importing integration components.

**✅ Recommended:**

```python
from kaizen.integrations.dataflow import DATAFLOW_AVAILABLE

if DATAFLOW_AVAILABLE:
    from kaizen.integrations.dataflow import DataFlowAwareAgent
    # Use DataFlow integration
else:
    # Fallback to base Kaizen functionality
    from kaizen.core.base_agent import BaseAgent as DataFlowAwareAgent
    # Continue with limited functionality
```

**❌ Avoid:**

```python
# Don't assume DataFlow is installed
from kaizen.integrations.dataflow import DataFlowAwareAgent  # May fail!
```

### Lazy Initialization Pattern

Delay database connection initialization until first use.

**✅ Recommended:**

```python
from kaizen.integrations.dataflow import DataFlowConnection

# Delay connection until needed
connection = DataFlowConnection(db=db, lazy_init=True)

# First use triggers initialization
tables = connection.list_tables()  # Initializes here
```

**Benefits:**
- Faster application startup
- Avoid unnecessary connections
- Better resource utilization

### Connection Pooling Pattern

Share connection pool across multiple agents.

**✅ Recommended:**

```python
# Single connection pool
connection = DataFlowConnection(db=db, pool_size=10)

# Multiple agents share pool
nl_agent = NLToSQLAgent(config=config, db=db)
transform_agent = DataTransformAgent(config=config, db=db)
quality_agent = DataQualityAgent(config=config, db=db)

# All agents use same pool efficiently
```

**❌ Avoid:**

```python
# Don't create separate connections for each agent
nl_connection = DataFlowConnection(db=db1, pool_size=5)
transform_connection = DataFlowConnection(db=db2, pool_size=5)
# Creates unnecessary connections
```

## Error Handling

### Database Error Handling

Handle database errors gracefully with fallbacks.

**✅ Recommended:**

```python
from kaizen.integrations.dataflow import NLToSQLAgent

def safe_query(agent, query_text, fallback_data=None):
    """Execute query with error handling."""
    try:
        result = agent.query(query_text)

        # Check for errors in result
        if 'error' in result:
            print(f"Query error: {result['error']}")
            return fallback_data or []

        return result.get('results', [])

    except DatabaseError as e:
        # Log database-specific errors
        print(f"Database error: {e}")
        return fallback_data or []

    except Exception as e:
        # Catch unexpected errors
        print(f"Unexpected error: {e}")
        return fallback_data or []

# Usage
results = safe_query(
    agent,
    "Show me all users",
    fallback_data=[{"id": 0, "name": "Unknown"}]
)
```

### Batch Operation Error Handling

Configure batch operations for resilience.

**✅ Recommended:**

```python
from kaizen.integrations.dataflow import BatchOptimizer, BatchConfig

# Configure resilient batching
config = BatchConfig(
    batch_size=1000,
    max_retries=3,           # Retry failed batches
    timeout_seconds=30,      # Per-batch timeout
    continue_on_error=True   # Don't stop on failures
)

optimizer = BatchOptimizer(config)

# Execute with error tracking
result = optimizer.batch_insert(data, insert_fn)

# Check for errors
if result['errors']:
    print(f"Errors in {len(result['errors'])} batches")
    for error in result['errors']:
        print(f"  Batch {error['batch_index']}: {error['error']}")

# Continue with successful records
print(f"Successfully inserted {result['successful']} records")
```

### Validation Before Operations

Validate data and configuration before executing operations.

**✅ Recommended:**

```python
def validate_training_data(agent, table_name):
    """Validate training data before model training."""

    # Check table exists
    tables = agent.list_tables()
    if table_name not in tables:
        raise ValueError(f"Table '{table_name}' not found")

    # Check data quality
    quality_result = agent.analyze_quality(
        table=table_name,
        quality_dimensions=["completeness", "validity"]
    )

    # Enforce minimum quality
    if quality_result.get('overall_score', 0) < 0.7:
        raise ValueError(
            f"Data quality too low: {quality_result['overall_score']}"
        )

    return True

# Usage
if validate_training_data(quality_agent, "TrainingData"):
    result = trainer.train_from_database(table="TrainingData")
```

## Performance Optimization

### Query Optimization

Optimize queries for specific access patterns.

**✅ Recommended for Read-Heavy:**

```python
from kaizen.integrations.dataflow import QueryCache

# Enable caching
cache = QueryCache(max_size=100, ttl_seconds=300)

def cached_query(agent, table, filter):
    """Query with automatic caching."""
    key = QueryCache.create_key(table, filter)

    # Check cache
    cached = cache.get(key)
    if cached:
        return cached

    # Execute query
    result = agent.query(f"Select * from {table} where ...")

    # Cache result
    cache.set(key, result)
    return result
```

**✅ Recommended for Write-Heavy:**

```python
from kaizen.integrations.dataflow import BatchOptimizer, BatchConfig

# Configure large batches
config = BatchConfig(batch_size=5000)
optimizer = BatchOptimizer(config)

# Batch writes for efficiency
result = optimizer.batch_insert(large_dataset, insert_fn)
```

### Resource Management

Properly manage resources to avoid leaks.

**✅ Recommended:**

```python
def run_pipeline(db, config):
    """Run pipeline with proper resource cleanup."""

    # Create resources
    connection = DataFlowConnection(db=db, pool_size=10)
    cache = QueryCache(max_size=100)
    optimizer = BatchOptimizer()

    try:
        # Execute pipeline
        agents = create_agents(config, db)
        results = execute_workflow(agents)
        return results

    finally:
        # Always cleanup
        connection.close()
        cache.clear()
        optimizer.reset_stats()
```

**❌ Avoid:**

```python
# Don't forget cleanup
connection = DataFlowConnection(db=db)
# ... operations ...
# Connection never closed - resource leak!
```

## Data Quality

### Pre-Transformation Validation

Validate data before transformation.

**✅ Recommended:**

```python
from kaizen.integrations.dataflow import DataQualityAgent

def validate_before_transform(agent, data):
    """Validate data quality before transformation."""

    # Analyze quality
    quality_result = agent.analyze_quality(
        table="RawData",
        quality_dimensions=["completeness", "validity", "consistency"]
    )

    # Check each dimension
    issues = quality_result.get('issues', [])

    critical_issues = [
        issue for issue in issues
        if issue.get('severity') == 'critical'
    ]

    if critical_issues:
        raise ValueError(
            f"Critical quality issues: {len(critical_issues)}"
        )

    # Warn on medium issues
    medium_issues = [
        issue for issue in issues
        if issue.get('severity') == 'medium'
    ]

    if medium_issues:
        print(f"Warning: {len(medium_issues)} medium quality issues")

    return quality_result

# Usage
quality = validate_before_transform(quality_agent, raw_data)
if quality.get('overall_score', 0) > 0.7:
    result = transform_agent.transform_data(...)
```

### Post-Transformation Verification

Verify transformation results.

**✅ Recommended:**

```python
def verify_transformation(source_count, target_count, threshold=0.95):
    """Verify transformation completed successfully."""

    # Check record count
    success_rate = target_count / source_count if source_count > 0 else 0

    if success_rate < threshold:
        raise ValueError(
            f"Transformation success rate too low: {success_rate:.2%}"
        )

    print(f"Transformation success: {success_rate:.2%}")
    return True

# Usage
source_count = len(raw_data)
result = transform_agent.transform_data(...)
target_count = result['inserted_count']

verify_transformation(source_count, target_count)
```

## Model Training & Inference

### Training Data Validation

Validate training data before model training.

**✅ Recommended:**

```python
from kaizen.integrations.dataflow import DBTrainingPipeline

def validate_training_requirements(agent, table):
    """Validate training data meets requirements."""

    # Check minimum record count
    nl_agent = NLToSQLAgent(config=config, db=agent.db)
    result = nl_agent.query(f"Count records in {table}")

    record_count = result.get('count', 0)
    if record_count < 100:
        raise ValueError(
            f"Insufficient training data: {record_count} records "
            "(minimum: 100)"
        )

    # Check feature completeness
    quality = quality_agent.analyze_quality(
        table=table,
        quality_dimensions=["completeness"]
    )

    if quality.get('completeness_score', 0) < 0.9:
        raise ValueError(
            f"Training data incomplete: "
            f"{quality.get('completeness_score', 0):.2%}"
        )

    return True

# Usage
if validate_training_requirements(trainer, "TrainingData"):
    result = trainer.train_from_database(table="TrainingData")
```

### Inference Result Validation

Validate inference results before storing.

**✅ Recommended:**

```python
from kaizen.integrations.dataflow import InferencePipeline

def validate_prediction(prediction_result, confidence_threshold=0.7):
    """Validate prediction before storing."""

    # Check prediction exists
    if 'prediction' not in prediction_result:
        raise ValueError("Missing prediction in result")

    # Check confidence threshold
    confidence = prediction_result.get('confidence', 0)
    if confidence < confidence_threshold:
        print(f"Low confidence: {confidence:.2%}")
        # Could return None or use fallback

    # Validate prediction range (domain-specific)
    prediction = prediction_result['prediction']
    if not (0 <= prediction <= 1000000):
        raise ValueError(f"Prediction out of range: {prediction}")

    return True

# Usage
prediction = inference.infer_with_db_context(...)
if validate_prediction(prediction, confidence_threshold=0.75):
    # Store prediction
    inference.infer_with_db_context(..., store_result=True)
```

## Pipeline Orchestration

### Modular Pipeline Design

Design pipelines with modular, reusable components.

**✅ Recommended:**

```python
from kaizen.integrations.dataflow import PipelineOrchestrator

class MLPipeline:
    """Modular ML pipeline with reusable stages."""

    def __init__(self, config, db):
        self.config = config
        self.db = db

        # Initialize agents
        self.nl_agent = NLToSQLAgent(config=config, db=db)
        self.transform_agent = DataTransformAgent(config=config, db=db)
        self.quality_agent = DataQualityAgent(config=config, db=db)
        self.trainer = DBTrainingPipeline(config=config, db=db)
        self.inference = InferencePipeline(config=config, db=db)

    def ingest(self, raw_data):
        """Ingest stage."""
        return self.transform_agent.transform_data(
            source_data=raw_data,
            target_table="RawData"
        )

    def clean(self, table="RawData"):
        """Cleaning stage."""
        # Get raw data
        result = self.nl_agent.query(f"Select all from {table}")

        # Transform
        return self.transform_agent.transform_data(
            source_data=result['results'],
            target_table="CleanData"
        )

    def validate_quality(self, table="CleanData"):
        """Quality validation stage."""
        return self.quality_agent.analyze_quality(
            table=table,
            quality_dimensions=["completeness", "validity", "consistency"]
        )

    def train(self, table="TrainingData"):
        """Training stage."""
        return self.trainer.train_from_database(
            table=table,
            model_objective="Predict target variable"
        )

    def predict(self, model_id, input_data):
        """Inference stage."""
        return self.inference.infer_with_db_context(
            model_id=model_id,
            input_data=input_data,
            store_result=True
        )

    def run_complete_pipeline(self, raw_data):
        """Execute complete pipeline."""
        # Ingest
        ingest_result = self.ingest(raw_data)
        print(f"✅ Ingested {ingest_result['inserted_count']} records")

        # Clean
        clean_result = self.clean()
        print(f"✅ Cleaned {clean_result['inserted_count']} records")

        # Validate
        quality_result = self.validate_quality()
        print(f"✅ Quality score: {quality_result.get('overall_score', 0):.2f}")

        # Train
        training_result = self.train()
        model_id = training_result['model_id']
        print(f"✅ Trained model: {model_id}")

        # Predict (example)
        prediction = self.predict(model_id, {"feature": 1.0})
        print(f"✅ Prediction: {prediction['prediction']}")

        return {
            'ingest': ingest_result,
            'clean': clean_result,
            'quality': quality_result,
            'training': training_result,
            'prediction': prediction
        }

# Usage
pipeline = MLPipeline(config, db)
results = pipeline.run_complete_pipeline(raw_data)
```

### Error Recovery in Pipelines

Implement error recovery for resilient pipelines.

**✅ Recommended:**

```python
class ResilientPipeline:
    """Pipeline with error recovery."""

    def run_with_recovery(self, raw_data, checkpoint_dir="./checkpoints"):
        """Execute pipeline with checkpointing."""
        results = {}

        # Stage 1: Ingest (checkpoint)
        try:
            results['ingest'] = self.ingest(raw_data)
            self.save_checkpoint('ingest', results['ingest'], checkpoint_dir)
        except Exception as e:
            print(f"Ingest failed: {e}")
            # Try to recover from checkpoint
            results['ingest'] = self.load_checkpoint('ingest', checkpoint_dir)

        # Stage 2: Clean (checkpoint)
        try:
            results['clean'] = self.clean()
            self.save_checkpoint('clean', results['clean'], checkpoint_dir)
        except Exception as e:
            print(f"Clean failed: {e}")
            results['clean'] = self.load_checkpoint('clean', checkpoint_dir)

        # Continue with other stages...

        return results

    def save_checkpoint(self, stage, data, checkpoint_dir):
        """Save pipeline checkpoint."""
        import json
        import os
        os.makedirs(checkpoint_dir, exist_ok=True)
        with open(f"{checkpoint_dir}/{stage}.json", 'w') as f:
            json.dump(data, f)

    def load_checkpoint(self, stage, checkpoint_dir):
        """Load pipeline checkpoint."""
        import json
        with open(f"{checkpoint_dir}/{stage}.json", 'r') as f:
            return json.load(f)
```

## Testing

### Unit Testing with Mocks

Test agents with mock database.

**✅ Recommended:**

```python
import pytest
from unittest.mock import Mock

def test_nl_agent_with_mock():
    """Test NL agent with mock database."""

    # Mock DataFlow
    mock_db = Mock()
    mock_db.list_tables.return_value = ["users", "orders"]

    # Create agent
    config = TestConfig()
    agent = NLToSQLAgent(config=config, db=mock_db)

    # Test query
    result = agent.query("Show me all users")

    # Verify
    assert 'sql' in result
    assert 'results' in result
```

### Integration Testing

Test with real database.

**✅ Recommended:**

```python
import pytest

@pytest.fixture
def test_db():
    """Create test database."""
    from dataflow import DataFlow

    db = DataFlow("sqlite:///:memory:")

    @db.model
    class TestUser:
        id: int
        name: str

    return db

def test_integration_with_real_db(test_db):
    """Test integration with real database."""

    config = TestConfig()
    agent = NLToSQLAgent(config=config, db=test_db)

    # Execute real query
    result = agent.query("Select all from TestUser")

    # Verify results
    assert result is not None
    assert 'results' in result
```

## Common Pitfalls

### ❌ Not Checking DataFlow Availability

```python
# Wrong: Assumes DataFlow is installed
from kaizen.integrations.dataflow import DataFlowAwareAgent
```

**✅ Correct:**

```python
from kaizen.integrations.dataflow import DATAFLOW_AVAILABLE

if DATAFLOW_AVAILABLE:
    from kaizen.integrations.dataflow import DataFlowAwareAgent
```

### ❌ Creating Too Many Connections

```python
# Wrong: New connection for each operation
for data in large_dataset:
    connection = DataFlowConnection(db=db)
    # ... operation ...
```

**✅ Correct:**

```python
# Right: Reuse connection pool
connection = DataFlowConnection(db=db, pool_size=10)
for data in large_dataset:
    # ... use shared connection ...
```

### ❌ Ignoring Batch Errors

```python
# Wrong: Ignore errors
result = optimizer.batch_insert(data, insert_fn)
# Continue without checking errors
```

**✅ Correct:**

```python
# Right: Handle errors
result = optimizer.batch_insert(data, insert_fn)
if result['errors']:
    print(f"Errors: {len(result['errors'])}")
    # Handle or retry failed batches
```

### ❌ No Resource Cleanup

```python
# Wrong: No cleanup
connection = DataFlowConnection(db=db)
cache = QueryCache()
# Resources never cleaned up
```

**✅ Correct:**

```python
# Right: Proper cleanup
connection = DataFlowConnection(db=db)
cache = QueryCache()
try:
    # ... operations ...
finally:
    connection.close()
    cache.clear()
```

## Production Checklist

Before deploying to production:

- [ ] DataFlow availability check implemented
- [ ] Error handling for all database operations
- [ ] Connection pooling configured (pool_size: 10-20)
- [ ] Query caching enabled for read-heavy operations
- [ ] Batch operations for bulk data (batch_size: 1000-5000)
- [ ] Resource cleanup in finally blocks
- [ ] Data quality validation before transformations
- [ ] Model validation before training
- [ ] Prediction validation before storing
- [ ] Performance monitoring enabled
- [ ] Integration tests with real database
- [ ] Error recovery for critical pipelines
- [ ] Logging for operations and errors
- [ ] Configuration externalized (not hardcoded)

## Related Documentation

- [Performance Guide](performance.md) - Optimization strategies
- [API Reference](api-reference.md) - Complete API documentation
- [Complete Pipeline Example](../../examples/6-dataflow-integration/complete-pipeline/) - Working implementation
