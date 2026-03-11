"""
Complete Kaizen-DataFlow Integration Showcase

Demonstrates ALL integration features in one comprehensive example:
1. Natural language queries → SQL generation
2. AI-driven data transformation and cleaning
3. Database-sourced model training
4. Real-time inference with database context
5. Automated pipeline orchestration
6. Performance optimization (connection pooling, caching, batching)

This example shows a complete ML workflow from raw data to predictions
with all Phase 1-4 features integrated.

Requirements:
    pip install kailash[dataflow]
    # or
    pip install kailash kailash-dataflow
"""

from dataclasses import dataclass

# Check DataFlow availability
from kaizen.integrations.dataflow import DATAFLOW_AVAILABLE

if not DATAFLOW_AVAILABLE:
    print("❌ DataFlow not installed.")
    print("Install with: pip install kailash[dataflow]")
    exit(1)

# Import DataFlow
from dataflow import DataFlow

# Import integration components
from kaizen.integrations.dataflow import (  # Phase 1: Base integration; Phase 2: AI-enhanced operations; Phase 3: DB-driven AI workflows; Phase 4: Performance optimizations
    BatchConfig,
    BatchOptimizer,
    DataFlowConnection,
    DataQualityAgent,
    DataTransformAgent,
    DBTrainingPipeline,
    InferencePipeline,
    NLToSQLAgent,
    PipelineOrchestrator,
    QueryCache,
)


@dataclass
class PipelineConfig:
    """Configuration for ML pipeline."""

    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.3
    max_tokens: int = 1000


def main():
    """Execute complete integration pipeline."""

    print("=" * 60)
    print("Complete Kaizen-DataFlow Integration Pipeline")
    print("=" * 60)

    # Setup: Connect to database
    print("\n📊 Connecting to database...")
    db = DataFlow("sqlite:///ecommerce.db")

    # Define database models
    @db.model
    class RawSales:
        id: int
        date: str
        amount: str  # Dirty data (string instead of float)
        customer_id: str  # Dirty data (string instead of int)
        product_name: str

    @db.model
    class CleanSales:
        id: int
        date: str
        amount: float  # Clean data
        customer_id: int  # Clean data
        product_name: str

    @db.model
    class TrainingData:
        id: int
        customer_lifetime_value: float
        purchase_frequency: float
        avg_order_value: float
        is_high_value_customer: int  # Target variable (0 or 1)

    @db.model
    class Predictions:
        id: int
        model_id: str
        customer_id: int
        predicted_lifetime_value: float
        confidence: float
        timestamp: str

    # Phase 4: Setup performance optimizations
    print("\n⚡ Initializing performance optimizations...")
    query_cache = QueryCache(max_size=100, ttl_seconds=300)
    batch_optimizer = BatchOptimizer(BatchConfig(batch_size=1000, max_retries=3))
    connection = DataFlowConnection(db=db, pool_size=5)

    # Configuration
    config = PipelineConfig()

    print("\n" + "=" * 60)
    print("PHASE 1: Natural Language Query")
    print("=" * 60)

    # Step 1: Natural language query
    nl_agent = NLToSQLAgent(config=config, db=db)

    query = "Show me all sales from the last month with amount over $1000"
    print(f"\n❓ Query: {query}")

    result = nl_agent.query(query)

    print(f"✅ Generated SQL: {result.get('sql', 'N/A')}")
    print(f"✅ Found {len(result.get('results', []))} records")

    # Cache the query for future use
    cache_key = QueryCache.create_key("sales", {"month": "last", "amount_gt": 1000})
    query_cache.set(cache_key, result)
    print("✅ Cached query results (TTL: 5 minutes)")

    print("\n" + "=" * 60)
    print("PHASE 2: Data Transformation & Quality")
    print("=" * 60)

    # Step 2: Data transformation
    transform_agent = DataTransformAgent(config=config, db=db)

    print("\n🔧 Transforming raw sales data...")

    # Simulate raw data
    raw_data = [
        {
            "id": i,
            "date": "2025-01-15",
            "amount": f"${100 + i * 10}",  # Dirty: string with $
            "customer_id": str(1000 + i % 10),  # Dirty: string
            "product_name": f"Product_{i % 5}",
        }
        for i in range(100)
    ]

    # Use batch optimizer for efficient insertion
    def insert_batch(batch):
        return transform_agent.transform_data(
            source_data=batch,
            target_table="RawSales",
        )

    batch_result = batch_optimizer.batch_insert(
        data=raw_data,
        insert_fn=insert_batch,
        progress_callback=lambda current, total: print(
            f"  Progress: {current}/{total} records"
        ),
    )

    print(f"\n✅ Inserted {batch_result['successful']} records")
    print(f"✅ Throughput: {batch_result['throughput']:.2f} records/sec")

    # Transform to clean format
    print("\n🧹 Cleaning data...")
    transform_result = transform_agent.transform_data(
        source_data=result.get("results", []),
        target_table="CleanSales",
        transformation_rules={
            "amount": "parse as float, remove $",
            "customer_id": "parse as integer",
        },
    )

    print(f"✅ Transformed {transform_result['inserted_count']} records")

    # Step 3: Data quality analysis
    quality_agent = DataQualityAgent(config=config, db=db)

    print("\n🔍 Analyzing data quality...")
    quality_result = quality_agent.analyze_quality(
        table="CleanSales",
        quality_dimensions=["completeness", "validity", "consistency"],
    )

    print(f"✅ Quality Score: {quality_result.get('overall_score', 'N/A')}")
    if "issues" in quality_result:
        print(f"⚠️  Found {len(quality_result['issues'])} data quality issues")

    print("\n" + "=" * 60)
    print("PHASE 3: Model Training from Database")
    print("=" * 60)

    # Step 4: Train model from database
    trainer = DBTrainingPipeline(config=config, db=db)

    print("\n🤖 Training ML model from database...")
    training_result = trainer.train_from_database(
        table="TrainingData",
        model_objective="Predict high-value customers based on purchase history",
    )

    model_id = training_result.get("model_id", "model_001")
    print(f"✅ Model trained: {model_id}")
    print(f"✅ Accuracy: {training_result.get('accuracy', 'N/A')}")

    print("\n" + "=" * 60)
    print("PHASE 4: Real-Time Inference")
    print("=" * 60)

    # Step 5: Real-time inference
    inference = InferencePipeline(config=config, db=db)

    print("\n🔮 Running predictions...")

    # Make predictions for multiple customers
    customer_ids = [1000, 1001, 1002, 1003, 1004]

    for customer_id in customer_ids:
        prediction_result = inference.infer_with_db_context(
            model_id=model_id,
            input_data={"customer_id": customer_id},
            store_result=True,
        )

        print(
            f"  Customer {customer_id}: "
            f"${prediction_result.get('prediction', 0):.2f} "
            f"(confidence: {prediction_result.get('confidence', 0):.2f})"
        )

    print("\n✅ Predictions stored in database")

    print("\n" + "=" * 60)
    print("PHASE 5: Automated Pipeline Orchestration")
    print("=" * 60)

    # Step 6: Pipeline orchestration
    orchestrator = PipelineOrchestrator(config=config, db=db)

    print("\n🎼 Creating automated pipeline...")
    pipeline_result = orchestrator.create_pipeline(
        pipeline_name="customer_value_prediction_pipeline",
        data_sources=["RawSales", "CleanSales", "TrainingData"],
        objective="Automated end-to-end customer value prediction",
    )

    print(f"✅ Pipeline created: {pipeline_result.get('pipeline_name', 'N/A')}")
    print(f"✅ Steps executed: {pipeline_result.get('steps_executed', 0)}")
    print(f"✅ Status: {pipeline_result.get('status', 'unknown')}")

    print("\n" + "=" * 60)
    print("Performance Statistics")
    print("=" * 60)

    # Display performance metrics
    print("\n📊 Cache Statistics:")
    cache_stats = query_cache.get_stats()
    print(f"  Cache size: {cache_stats['size']}/{cache_stats['max_size']}")
    print(f"  Hit rate: {cache_stats['hit_rate']:.2f}%")
    print(f"  Evictions: {cache_stats['evictions']}")

    print("\n📊 Batch Optimizer Statistics:")
    batch_stats = batch_optimizer.get_stats()
    print(f"  Total operations: {batch_stats['total_operations']}")
    print(f"  Total records: {batch_stats['total_records']}")
    print(f"  Avg throughput: {batch_stats['avg_throughput']:.2f} rec/sec")

    print("\n📊 Connection Pool Statistics:")
    pool_stats = connection.get_pool_stats()
    print(
        f"  Pool size: {pool_stats.get('connections', 0)}/{pool_stats.get('max_size', 0)}"
    )
    print(f"  Total requests: {pool_stats.get('total_requests', 0)}")

    print("\n" + "=" * 60)
    print("Pipeline Complete!")
    print("=" * 60)

    print("\n✅ Successfully demonstrated:")
    print("  1. Natural language → SQL queries")
    print("  2. AI-driven data transformation")
    print("  3. Data quality analysis")
    print("  4. Database-sourced model training")
    print("  5. Real-time inference with DB context")
    print("  6. Automated pipeline orchestration")
    print("  7. Performance optimizations (caching, batching, pooling)")

    # Cleanup
    connection.close()
    print("\n🧹 Resources cleaned up")


if __name__ == "__main__":
    main()
