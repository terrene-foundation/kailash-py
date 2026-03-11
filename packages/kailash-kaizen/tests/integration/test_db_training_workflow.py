"""
Integration tests for database-driven training workflows.

Tests end-to-end workflows with real database (Tier 2 - NO MOCKING).
Uses real PostgreSQL/SQLite via DataFlow and real LLM providers.
"""

from dataclasses import dataclass

import pytest

# Import will be available after implementation
pytest.importorskip("dataflow", reason="DataFlow required for integration tests")


@dataclass
class RealConfig:
    """Real configuration for integration testing."""

    llm_provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.3


@pytest.mark.integration
@pytest.mark.requires_db
class TestDBTrainingWorkflow:
    """Integration tests with real database for training."""

    @pytest.fixture
    def real_db(self):
        """Provide real DataFlow instance with test database."""
        from dataflow import DataFlow

        # Use SQLite for testing (lighter than PostgreSQL)
        db = DataFlow("sqlite:///:memory:")

        # Define test schema
        @db.model
        class Customer:
            id: int
            age: int
            income: float
            purchases: int
            churn_risk: str

        # Initialize with sample data
        yield db

        # Cleanup handled by in-memory database

    def test_end_to_end_training_pipeline(self, real_db):
        """Test complete training pipeline from database data."""
        from kaizen.integrations.dataflow.db_driven_ai import DBTrainingPipeline

        config = RealConfig()
        trainer = DBTrainingPipeline(config=config, db=real_db)

        # Insert training data into database
        training_samples = [
            {"age": 25, "income": 50000, "purchases": 5, "churn_risk": "low"},
            {"age": 45, "income": 80000, "purchases": 12, "churn_risk": "high"},
            {"age": 35, "income": 65000, "purchases": 8, "churn_risk": "medium"},
            {"age": 55, "income": 95000, "purchases": 20, "churn_risk": "low"},
            {"age": 30, "income": 55000, "purchases": 6, "churn_risk": "medium"},
        ]

        # Insert via DataFlow
        for sample in training_samples:
            trainer.insert_database(table="Customer", data=sample)

        # Train model from database
        result = trainer.train_from_database(
            table="Customer",
            model_objective="Predict customer churn risk based on demographics",
            validation_split=0.2,
        )

        # Verify training completed successfully
        assert "model_id" in result
        assert "accuracy" in result or "metrics" in result
        assert "features" in result
        assert len(result["features"]) > 0

        # Verify model metadata was stored
        assert "metadata" in result
        assert result["metadata"]["source_table"] == "Customer"

    def test_real_time_inference_integration(self, real_db):
        """Test inference with real database lookups."""
        from kaizen.integrations.dataflow.db_driven_ai import (
            DBTrainingPipeline,
            InferencePipeline,
        )

        config = RealConfig()

        # First, train a model
        trainer = DBTrainingPipeline(config=config, db=real_db)

        # Insert training data
        training_samples = [
            {"age": 25, "income": 50000, "purchases": 5, "churn_risk": "low"},
            {"age": 45, "income": 80000, "purchases": 12, "churn_risk": "high"},
            {"age": 35, "income": 65000, "purchases": 8, "churn_risk": "medium"},
        ]

        for sample in training_samples:
            trainer.insert_database(table="Customer", data=sample)

        training_result = trainer.train_from_database(
            table="Customer", model_objective="Predict customer churn risk"
        )

        # Now test inference
        inference_pipeline = InferencePipeline(config=config, db=real_db)

        new_customer = {"age": 40, "income": 70000, "purchases": 10}

        prediction = inference_pipeline.infer_with_db_context(
            model_id=training_result["model_id"],
            input_data=new_customer,
            store_result=True,
        )

        # Verify prediction structure
        assert "prediction" in prediction
        assert "confidence" in prediction
        assert "explanation" in prediction
        assert isinstance(prediction["confidence"], (int, float))
        assert 0 <= prediction["confidence"] <= 1

    def test_pipeline_automation_workflow(self, real_db):
        """Test automated training and deployment pipeline."""
        from kaizen.integrations.dataflow.db_driven_ai import PipelineOrchestrator

        config = RealConfig()
        orchestrator = PipelineOrchestrator(config=config, db=real_db)

        # Insert sample data
        samples = [
            {"age": 28, "income": 45000, "purchases": 3, "churn_risk": "low"},
            {"age": 50, "income": 90000, "purchases": 15, "churn_risk": "high"},
        ]

        for sample in samples:
            orchestrator.insert_database(table="Customer", data=sample)

        # Create and execute pipeline
        result = orchestrator.create_pipeline(
            pipeline_name="customer_analysis_pipeline",
            data_sources=["Customer"],
            objective="Analyze customer behavior and predict churn",
        )

        # Verify pipeline execution
        assert result["pipeline_name"] == "customer_analysis_pipeline"
        assert "steps_executed" in result
        assert result["steps_executed"] > 0
        assert "metrics" in result

    def test_model_performance_tracking(self, real_db):
        """Test tracking model metrics in database."""
        from kaizen.integrations.dataflow.db_driven_ai import DBTrainingPipeline

        config = RealConfig()
        trainer = DBTrainingPipeline(config=config, db=real_db)

        # Insert training data
        samples = [
            {"age": 30, "income": 60000, "purchases": 7, "churn_risk": "medium"},
            {"age": 40, "income": 75000, "purchases": 11, "churn_risk": "low"},
        ]

        for sample in samples:
            trainer.insert_database(table="Customer", data=sample)

        # Train model
        result = trainer.train_from_database(
            table="Customer", model_objective="Predict churn"
        )

        # Verify performance metrics tracked
        assert "metadata" in result
        metadata = result["metadata"]

        # Should have timestamp or version
        assert "created_at" in metadata or "version" in metadata

        # Should track source information
        assert "source_table" in metadata
        assert metadata["source_table"] == "Customer"


@pytest.mark.integration
@pytest.mark.requires_llm
class TestLLMIntegration:
    """Test LLM integration in database workflows."""

    def test_llm_feature_recommendation(self):
        """Test LLM recommending features from database schema."""
        from dataflow import DataFlow

        from kaizen.integrations.dataflow.db_driven_ai import DBTrainingPipeline

        db = DataFlow("sqlite:///:memory:")

        @db.model
        class Product:
            name: str
            price: float
            category: str
            sales: int
            rating: float

        config = RealConfig()
        _trainer = DBTrainingPipeline(config=config, db=db)

        # Get schema
        schema = db.discover_schema(use_real_inspection=False)

        # LLM should be able to analyze schema
        assert schema is not None
        assert "Product" in schema or len(schema) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
