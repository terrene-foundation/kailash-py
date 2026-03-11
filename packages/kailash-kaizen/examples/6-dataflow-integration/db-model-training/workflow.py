"""
Database-Driven Model Training Example

Demonstrates end-to-end ML training using database as data source.

Workflow:
1. Connect to database via DataFlow
2. Define data schema as models
3. Train AI model from database table
4. AI analyzes schema and recommends features
5. Store model metadata in database
6. Run real-time inference with database context
7. Track all predictions in database

Key Features:
- Database-first ML pipeline
- AI-powered feature engineering
- Automated model versioning
- Context-enriched inference
- Full audit trail
"""

from dataclasses import dataclass
from typing import Optional

try:
    from dataflow import DataFlow

    DATAFLOW_AVAILABLE = True
except ImportError:
    DATAFLOW_AVAILABLE = False
    print("⚠️  DataFlow not available. Install with: pip install kailash[dataflow]")

from kaizen.integrations.dataflow.db_driven_ai import (
    DBTrainingPipeline,
    InferencePipeline,
    PipelineOrchestrator,
)


@dataclass
class TrainingConfig:
    """Configuration for database-driven training."""

    llm_provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.3
    max_tokens: int = 2000


def setup_database() -> Optional["DataFlow"]:
    """
    Setup database with sample customer data.

    Returns:
        DataFlow instance or None if not available
    """
    if not DATAFLOW_AVAILABLE:
        print("DataFlow not available - skipping database setup")
        return None

    # Use in-memory SQLite for demo
    db = DataFlow("sqlite:///:memory:")

    # Define customer schema
    @db.model
    class Customer:
        """Customer data for churn prediction."""

        id: int
        age: int
        income: float
        purchases: int
        churn_risk: str  # "low", "medium", "high"

    # Note: In production, you would also define:
    # - model_metadata table for versioning
    # - inference_results table for audit trail
    # - pipeline_metrics table for monitoring

    print("✅ Database schema created")
    return db


def insert_sample_data(db: "DataFlow") -> int:
    """
    Insert sample customer data for training.

    Args:
        db: DataFlow database instance

    Returns:
        Number of records inserted
    """
    if not db:
        return 0

    # Sample customer data
    customers = [
        {"age": 25, "income": 50000, "purchases": 5, "churn_risk": "low"},
        {"age": 45, "income": 80000, "purchases": 12, "churn_risk": "high"},
        {"age": 35, "income": 65000, "purchases": 8, "churn_risk": "medium"},
        {"age": 55, "income": 95000, "purchases": 20, "churn_risk": "low"},
        {"age": 30, "income": 55000, "purchases": 6, "churn_risk": "medium"},
        {"age": 28, "income": 48000, "purchases": 3, "churn_risk": "low"},
        {"age": 50, "income": 110000, "purchases": 25, "churn_risk": "low"},
        {"age": 40, "income": 70000, "purchases": 10, "churn_risk": "medium"},
        {"age": 60, "income": 120000, "purchases": 30, "churn_risk": "low"},
        {"age": 22, "income": 35000, "purchases": 2, "churn_risk": "high"},
    ]

    # Insert via workflow (using DataFlow's auto-generated nodes)
    from kailash.runtime.local import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    workflow = WorkflowBuilder()

    for i, customer in enumerate(customers):
        workflow.add_node("CustomerCreateNode", f"create_{i}", customer)

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    print(f"✅ Inserted {len(customers)} customer records")
    return len(customers)


def train_model(db: "DataFlow", config: TrainingConfig) -> dict:
    """
    Train churn prediction model from database.

    Args:
        db: DataFlow database instance
        config: Training configuration

    Returns:
        Training result with model_id, accuracy, features
    """
    if not db:
        return {"error": "Database not available"}

    print("\n" + "=" * 60)
    print("TRAINING PHASE")
    print("=" * 60)

    # Create training pipeline
    trainer = DBTrainingPipeline(config=config, db=db)

    print("\n📊 Training model from database...")
    print("   Table: Customer")
    print("   Objective: Predict customer churn risk")

    # Train model - AI analyzes schema and data
    result = trainer.train_from_database(
        table="Customer",
        model_objective="Predict customer churn risk based on age, income, and purchase behavior",
        validation_split=0.2,
    )

    print("\n✅ Model Training Complete!")
    print(f"   Model ID: {result['model_id']}")
    print(f"   Accuracy: {result.get('accuracy', 'N/A')}")
    print(f"   Features: {', '.join(result['features'])}")
    print(f"   Target: {result['metadata'].get('target', 'N/A')}")

    return result


def run_inference(
    db: "DataFlow", config: TrainingConfig, model_id: str, test_customers: list[dict]
) -> list[dict]:
    """
    Run inference on test customers.

    Args:
        db: DataFlow database instance
        config: Training configuration
        model_id: Trained model ID
        test_customers: List of customer data for predictions

    Returns:
        List of prediction results
    """
    if not db:
        return []

    print("\n" + "=" * 60)
    print("INFERENCE PHASE")
    print("=" * 60)

    # Create inference pipeline
    pipeline = InferencePipeline(config=config, db=db)

    predictions = []

    for i, customer in enumerate(test_customers, 1):
        print(f"\n🔮 Prediction #{i}")
        print(
            f"   Input: Age={customer['age']}, Income=${customer['income']:,}, "
            f"Purchases={customer['purchases']}"
        )

        # Run inference with database context
        prediction = pipeline.infer_with_db_context(
            model_id=model_id,
            input_data=customer,
            store_result=True,  # Store in database for audit trail
        )

        print(f"   → Prediction: {prediction['prediction']}")
        print(f"   → Confidence: {prediction['confidence']:.2%}")
        print(f"   → Explanation: {prediction['explanation']}")

        predictions.append(prediction)

    return predictions


def create_automated_pipeline(db: "DataFlow", config: TrainingConfig) -> dict:
    """
    Create and execute automated ML pipeline.

    Args:
        db: DataFlow database instance
        config: Training configuration

    Returns:
        Pipeline execution results
    """
    if not db:
        return {"error": "Database not available"}

    print("\n" + "=" * 60)
    print("AUTOMATED PIPELINE")
    print("=" * 60)

    # Create pipeline orchestrator
    orchestrator = PipelineOrchestrator(config=config, db=db)

    print("\n🚀 Creating automated pipeline...")
    print("   Name: customer_churn_pipeline")
    print("   Data Sources: Customer")
    print("   Objective: End-to-end churn prediction")

    # Create and execute pipeline
    result = orchestrator.create_pipeline(
        pipeline_name="customer_churn_pipeline",
        data_sources=["Customer"],
        objective="Analyze customer behavior and predict churn risk with full automation",
    )

    print("\n✅ Pipeline Execution Complete!")
    print(f"   Pipeline: {result['pipeline_name']}")
    print(f"   Steps Executed: {result['steps_executed']}")
    print(f"   Metrics: {result['metrics']}")

    return result


def main():
    """Run complete database-driven ML workflow."""
    print("=" * 60)
    print("DATABASE-DRIVEN MODEL TRAINING")
    print("=" * 60)

    # Setup
    config = TrainingConfig()
    db = setup_database()

    if not db:
        print("\n❌ Cannot proceed without DataFlow")
        print("   Install: pip install kailash[dataflow]")
        return

    # Insert sample data
    insert_sample_data(db)

    # Train model
    training_result = train_model(db, config)

    # Run inference on new customers
    test_customers = [
        {"age": 32, "income": 62000, "purchases": 7},
        {"age": 48, "income": 85000, "purchases": 15},
        {"age": 26, "income": 42000, "purchases": 4},
    ]

    predictions = run_inference(db, config, training_result["model_id"], test_customers)

    # Create automated pipeline
    pipeline_result = create_automated_pipeline(db, config)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"✅ Model trained: {training_result['model_id']}")
    print(f"✅ Predictions made: {len(predictions)}")
    print(f"✅ Pipeline executed: {pipeline_result['pipeline_name']}")
    print("\n🎉 Database-driven ML workflow complete!")


if __name__ == "__main__":
    main()
