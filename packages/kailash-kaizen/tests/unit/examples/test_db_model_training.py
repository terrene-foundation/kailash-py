"""
Unit tests for database-driven model training example.

Tests the db-model-training workflow using mock providers.
"""

from dataclasses import dataclass

import pytest

# Check if DataFlow is available
try:
    import dataflow

    DATAFLOW_AVAILABLE = True
except ImportError:
    DATAFLOW_AVAILABLE = False


@dataclass
class MockConfig:
    """Mock configuration for testing."""

    llm_provider: str = "mock"
    model: str = "mock-model"
    temperature: float = 0.3
    max_tokens: int = 2000


class TestDBModelTraining:
    """Test database-driven model training example."""

    def test_workflow_components_available(self, load_example):
        """Test that all workflow components can be imported."""
        example = load_example("examples/6-dataflow-integration/db-model-training")

        # Verify key components
        assert "TrainingConfig" in example.config_classes
        assert hasattr(example.module, "setup_database")
        assert hasattr(example.module, "insert_sample_data")
        assert hasattr(example.module, "train_model")
        assert hasattr(example.module, "run_inference")
        assert hasattr(example.module, "create_automated_pipeline")

    def test_training_config_creation(self, load_example):
        """Test training configuration creation."""
        example = load_example("examples/6-dataflow-integration/db-model-training")
        TrainingConfig = example.config_classes["TrainingConfig"]

        config = TrainingConfig(
            llm_provider="openai", model="gpt-4o-mini", temperature=0.3
        )

        assert config.llm_provider == "openai"
        assert config.model == "gpt-4o-mini"
        assert config.temperature == 0.3
        assert config.max_tokens == 2000

    @pytest.mark.skipif(not DATAFLOW_AVAILABLE, reason="DataFlow not installed")
    def test_database_setup(self, load_example):
        """Test database setup function."""
        example = load_example("examples/6-dataflow-integration/db-model-training")
        setup_database = example.module.setup_database

        # Setup database
        db = setup_database()

        # Verify database created
        assert db is not None

        # Verify schema discovery works
        schema = db.discover_schema(use_real_inspection=False)
        assert schema is not None

    @pytest.mark.skipif(not DATAFLOW_AVAILABLE, reason="DataFlow not installed")
    def test_training_pipeline_creation(self, load_example):
        """Test creating training pipeline."""
        from kaizen.integrations.dataflow.db_driven_ai import DBTrainingPipeline

        example = load_example("examples/6-dataflow-integration/db-model-training")
        example.config_classes["TrainingConfig"]
        setup_database = example.module.setup_database

        config = MockConfig()
        db = setup_database()

        # Create training pipeline
        trainer = DBTrainingPipeline(config=config, db=db)

        assert trainer is not None
        assert trainer.db_connection is not None
        assert hasattr(trainer, "train_from_database")

    @pytest.mark.skipif(not DATAFLOW_AVAILABLE, reason="DataFlow not installed")
    def test_inference_pipeline_creation(self, load_example):
        """Test creating inference pipeline."""
        from kaizen.integrations.dataflow.db_driven_ai import InferencePipeline

        example = load_example("examples/6-dataflow-integration/db-model-training")
        example.config_classes["TrainingConfig"]
        setup_database = example.module.setup_database

        config = MockConfig()
        db = setup_database()

        # Create inference pipeline
        pipeline = InferencePipeline(config=config, db=db)

        assert pipeline is not None
        assert pipeline.db_connection is not None
        assert hasattr(pipeline, "infer_with_db_context")

    @pytest.mark.skipif(not DATAFLOW_AVAILABLE, reason="DataFlow not installed")
    def test_pipeline_orchestrator_creation(self, load_example):
        """Test creating pipeline orchestrator."""
        from kaizen.integrations.dataflow.db_driven_ai import PipelineOrchestrator

        example = load_example("examples/6-dataflow-integration/db-model-training")
        example.config_classes["TrainingConfig"]
        setup_database = example.module.setup_database

        config = MockConfig()
        db = setup_database()

        # Create orchestrator
        orchestrator = PipelineOrchestrator(config=config, db=db)

        assert orchestrator is not None
        assert orchestrator.db_connection is not None
        assert hasattr(orchestrator, "create_pipeline")

    def test_sample_data_structure(self):
        """Test sample data has correct structure."""
        # Sample customer data from workflow
        sample_customer = {
            "age": 25,
            "income": 50000,
            "purchases": 5,
            "churn_risk": "low",
        }

        # Verify structure
        assert "age" in sample_customer
        assert "income" in sample_customer
        assert "purchases" in sample_customer
        assert "churn_risk" in sample_customer
        assert sample_customer["churn_risk"] in ["low", "medium", "high"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
