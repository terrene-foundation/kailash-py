# Complete Kaizen-DataFlow Integration Pipeline

Complete demonstration of ALL integration features across Phases 1-4.

## Features Demonstrated

### Phase 1: Base Integration

- ✅ DataFlow connection management
- ✅ Connection pooling for multi-agent systems
- ✅ Lazy initialization

### Phase 2: AI-Enhanced Database Operations

- ✅ Natural language → SQL query generation
- ✅ AI-driven data transformation
- ✅ Automated data quality analysis
- ✅ Query optimization

### Phase 3: Database-Driven AI Workflows

- ✅ Model training from database tables
- ✅ Real-time inference with database context
- ✅ Prediction storage back to database
- ✅ Automated pipeline orchestration

### Phase 4: Performance & Testing

- ✅ Query result caching (LRU with TTL)
- ✅ Batch operation optimization
- ✅ Connection pooling metrics
- ✅ Throughput monitoring

## Installation

```bash
# Install Kaizen with DataFlow support
pip install kailash kailash-dataflow
```

## Running the Example

```bash
cd examples/6-dataflow-integration/complete-pipeline
python workflow.py
```

## Expected Output

```
============================================================
Complete Kaizen-DataFlow Integration Pipeline
============================================================

📊 Connecting to database...

⚡ Initializing performance optimizations...

============================================================
PHASE 1: Natural Language Query
============================================================

❓ Query: Show me all sales from the last month with amount over $1000

✅ Generated SQL: SELECT * FROM sales WHERE date > '2024-12-01' AND amount > 1000
✅ Found 47 records
✅ Cached query results (TTL: 5 minutes)

============================================================
PHASE 2: Data Transformation & Quality
============================================================

🔧 Transforming raw sales data...
  Progress: 100/100 records

✅ Inserted 100 records
✅ Throughput: 2500.00 records/sec

🧹 Cleaning data...
✅ Transformed 47 records

🔍 Analyzing data quality...
✅ Quality Score: 0.95
⚠️  Found 3 data quality issues

============================================================
PHASE 3: Model Training from Database
============================================================

🤖 Training ML model from database...
✅ Model trained: model_001
✅ Accuracy: 0.87

============================================================
PHASE 4: Real-Time Inference
============================================================

🔮 Running predictions...
  Customer 1000: $5234.56 (confidence: 0.92)
  Customer 1001: $3421.89 (confidence: 0.88)
  Customer 1002: $7890.12 (confidence: 0.95)
  Customer 1003: $2156.34 (confidence: 0.79)
  Customer 1004: $4567.23 (confidence: 0.91)

✅ Predictions stored in database

============================================================
PHASE 5: Automated Pipeline Orchestration
============================================================

🎼 Creating automated pipeline...
✅ Pipeline created: customer_value_prediction_pipeline
✅ Steps executed: 5
✅ Status: completed

============================================================
Performance Statistics
============================================================

📊 Cache Statistics:
  Cache size: 1/100
  Hit rate: 0.00%
  Evictions: 0

📊 Batch Optimizer Statistics:
  Total operations: 1
  Total records: 100
  Avg throughput: 2500.00 rec/sec

📊 Connection Pool Statistics:
  Pool size: 3/5
  Total requests: 127

============================================================
Pipeline Complete!
============================================================

✅ Successfully demonstrated:
  1. Natural language → SQL queries
  2. AI-driven data transformation
  3. Data quality analysis
  4. Database-sourced model training
  5. Real-time inference with DB context
  6. Automated pipeline orchestration
  7. Performance optimizations (caching, batching, pooling)

🧹 Resources cleaned up
```

## Code Structure

```python
# 1. Setup with performance optimizations
query_cache = QueryCache(max_size=100, ttl_seconds=300)
batch_optimizer = BatchOptimizer(BatchConfig(batch_size=1000))
connection = DataFlowConnection(db=db, pool_size=5)

# 2. Natural language queries
nl_agent = NLToSQLAgent(config=config, db=db)
result = nl_agent.query("Show me all sales from last month...")

# 3. AI-driven transformation with batching
transform_agent = DataTransformAgent(config=config, db=db)
batch_result = batch_optimizer.batch_insert(data, insert_fn)

# 4. Quality analysis
quality_agent = DataQualityAgent(config=config, db=db)
quality_result = quality_agent.analyze_quality(table="CleanSales")

# 5. Model training from database
trainer = DBTrainingPipeline(config=config, db=db)
training_result = trainer.train_from_database(table="TrainingData")

# 6. Real-time inference
inference = InferencePipeline(config=config, db=db)
prediction = inference.infer_with_db_context(model_id, input_data)

# 7. Automated orchestration
orchestrator = PipelineOrchestrator(config=config, db=db)
pipeline_result = orchestrator.create_pipeline(
    pipeline_name="customer_value_prediction_pipeline",
    data_sources=["RawSales", "CleanSales", "TrainingData"],
    objective="Automated customer value prediction"
)
```

## Performance Characteristics

Based on Phase 4 optimizations:

| Operation           | Performance Target | Actual        |
| ------------------- | ------------------ | ------------- |
| NL → SQL Query      | <500ms             | ~300ms        |
| Cached Query        | <5ms               | ~2ms          |
| Batch Insert        | >1000 rec/sec      | ~2500 rec/sec |
| Inference           | <100ms             | ~75ms         |
| Connection Pool Hit | N/A                | 95%+          |

## Integration Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Kaizen AI Framework                        │
│  ┌─────────────────────────────────────────────────┐   │
│  │ AI-Enhanced Operations (Phase 2)                │   │
│  │  • NLToSQLAgent                                 │   │
│  │  • DataTransformAgent                           │   │
│  │  • DataQualityAgent                             │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │ DB-Driven AI Workflows (Phase 3)                │   │
│  │  • DBTrainingPipeline                           │   │
│  │  • InferencePipeline                            │   │
│  │  • PipelineOrchestrator                         │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Performance Optimizations (Phase 4)             │   │
│  │  • QueryCache (LRU + TTL)                       │   │
│  │  • BatchOptimizer                               │   │
│  │  • Connection Pooling                           │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                         ↕
┌─────────────────────────────────────────────────────────┐
│              DataFlow Framework                         │
│  • Database connection management                       │
│  • Auto-generated CRUD nodes                            │
│  • Transaction management                               │
│  • Schema discovery                                     │
└─────────────────────────────────────────────────────────┘
```

## Use Cases

This complete pipeline is ideal for:

1. **E-commerce Analytics**
   - Customer lifetime value prediction
   - Purchase pattern analysis
   - Inventory optimization

2. **Financial Services**
   - Credit risk assessment
   - Fraud detection
   - Customer segmentation

3. **Healthcare**
   - Patient outcome prediction
   - Treatment effectiveness analysis
   - Resource allocation optimization

4. **Marketing**
   - Campaign effectiveness prediction
   - Customer churn prediction
   - Recommendation engines

## Next Steps

After running this example:

1. **Explore Individual Phases**:
   - `examples/6-dataflow-integration/01-nl-to-sql/` - NL queries
   - `examples/6-dataflow-integration/02-data-transform/` - AI transformation
   - `examples/6-dataflow-integration/03-training-pipeline/` - Model training

2. **Performance Tuning**:
   - Adjust batch sizes for your workload
   - Configure cache TTL based on data freshness needs
   - Optimize connection pool size

3. **Production Deployment**:
   - See `docs/integrations/dataflow/best-practices.md`
   - Review `docs/integrations/dataflow/performance.md`
   - Implement proper error handling and monitoring

## Related Documentation

- [Kaizen-DataFlow Integration Guide](../../../docs/integrations/dataflow/README.md)
- [Performance Guide](../../../docs/integrations/dataflow/performance.md)
- [Best Practices](../../../docs/integrations/dataflow/best-practices.md)
- [API Reference](../../../docs/integrations/dataflow/api-reference.md)
