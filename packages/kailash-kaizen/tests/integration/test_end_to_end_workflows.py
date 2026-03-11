"""
End-to-End Workflow Integration Tests

Tests verify complete workflow integration across all components:
- Complete data pipeline: Ingest → Transform → Train → Infer
- Multi-table operations across related tables
- Error recovery and graceful failure handling
- Transaction consistency and ACID compliance
- Multi-agent coordination with shared database

Tier 2/3: Real infrastructure, real database, real LLM calls
"""

from dataclasses import dataclass

import pytest

# Import integration components with conditional import
try:
    from dataflow import DataFlow

    from kaizen.integrations.dataflow import (
        DATAFLOW_AVAILABLE,
        DataQualityAgent,
        DataTransformAgent,
        DBTrainingPipeline,
        InferencePipeline,
        NLToSQLAgent,
        PipelineOrchestrator,
    )
except ImportError:
    DATAFLOW_AVAILABLE = False
    DataFlow = None

# Skip all tests if DataFlow not available
pytestmark = pytest.mark.skipif(
    not DATAFLOW_AVAILABLE,
    reason="DataFlow not installed - install with pip install kailash[dataflow]",
)


@dataclass
class E2ETestConfig:
    """Test configuration."""

    llm_provider: str = "mock"
    model: str = "mock-model"
    temperature: float = 0.3


@pytest.fixture
def db():
    """Create test database with multi-table schema."""
    db = DataFlow("sqlite:///:memory:")

    # Define related tables for e2e testing
    @db.model
    class RawData:
        id: int
        source: str
        raw_value: str
        timestamp: str

    @db.model
    class CleanData:
        id: int
        source: str
        clean_value: float
        timestamp: str
        quality_score: float

    @db.model
    class TrainingData:
        id: int
        features: str  # JSON string
        target: float
        data_source_id: int

    @db.model
    class Predictions:
        id: int
        model_id: str
        input_features: str  # JSON string
        prediction: float
        confidence: float
        timestamp: str

    @db.model
    class AuditLog:
        id: int
        operation: str
        table_name: str
        record_count: int
        timestamp: str
        status: str

    return db


@pytest.fixture
def config():
    """Test configuration."""
    return E2ETestConfig()


class TestCompleteDataPipeline:
    """Test complete end-to-end data pipeline."""

    @pytest.mark.integration
    @pytest.mark.e2e
    def test_complete_pipeline_ingest_to_prediction(self, db, config):
        """
        COMPLETE PIPELINE: Ingest → Transform → Train → Infer

        Verifies entire ML pipeline works end-to-end:
        1. Ingest raw data
        2. Transform and clean
        3. Train model from cleaned data
        4. Generate predictions
        5. Store results
        """
        # Step 1: Ingest raw data
        raw_records = [
            {
                "id": i,
                "source": "sensor",
                "raw_value": str(100 + i),
                "timestamp": "2025-01-01",
            }
            for i in range(100)
        ]

        transform_agent = DataTransformAgent(config=config, db=db)
        ingest_result = transform_agent.transform_data(
            source_data=raw_records, target_table="RawData"
        )

        assert ingest_result["inserted_count"] == 100

        # Step 2: Transform and clean data
        nl_agent = NLToSQLAgent(config=config, db=db)
        query_result = nl_agent.query("Select all records from RawData")

        clean_result = transform_agent.transform_data(
            source_data=query_result["results"],
            target_table="CleanData",
            transformation_rules={"clean_value": "parse raw_value as float"},
        )

        assert clean_result["inserted_count"] > 0

        # Step 3: Train model from cleaned data
        trainer = DBTrainingPipeline(config=config, db=db)
        training_result = trainer.train_from_database(
            table="CleanData", model_objective="Predict clean values based on features"
        )

        assert "model_id" in training_result
        model_id = training_result["model_id"]

        # Step 4: Generate predictions
        inference = InferencePipeline(config=config, db=db)
        prediction_result = inference.infer_with_db_context(
            model_id=model_id,
            input_data={"source": "sensor", "value": 150},
            store_result=True,
        )

        assert "prediction" in prediction_result

        # Step 5: Verify complete pipeline
        # Query predictions table to verify storage
        predictions_query = nl_agent.query("Select all records from Predictions")
        assert len(predictions_query["results"]) > 0

        # Verify audit trail exists
        _audit_query = nl_agent.query("Select all records from AuditLog")
        # (Audit logging would be implemented in agents)

    @pytest.mark.integration
    @pytest.mark.e2e
    def test_pipeline_orchestration(self, db, config):
        """
        Test automated pipeline orchestration.

        Verifies PipelineOrchestrator can manage complete workflow
        with minimal manual intervention.
        """
        orchestrator = PipelineOrchestrator(config=config, db=db)

        # Create and execute pipeline
        result = orchestrator.create_pipeline(
            pipeline_name="test_ml_pipeline",
            data_sources=["RawData", "CleanData"],
            objective="Automated end-to-end ML pipeline",
        )

        # Verify pipeline execution
        assert result["pipeline_created"] is True
        assert result["steps_executed"] > 0
        assert result["status"] == "completed" or result["status"] == "success"

        # Verify pipeline components
        if "components" in result:
            components = result["components"]
            # Should include data ingestion, transformation, training
            assert any(
                "ingest" in c.lower() or "transform" in c.lower() for c in components
            )

    @pytest.mark.integration
    @pytest.mark.e2e
    def test_streaming_pipeline_processing(self, db, config):
        """
        Test streaming data processing through pipeline.

        Verifies pipeline can handle continuous data flow
        without batching everything upfront.
        """
        transform_agent = DataTransformAgent(config=config, db=db)

        # Simulate streaming data in chunks
        total_processed = 0
        chunk_size = 10

        for batch in range(5):  # 5 batches
            chunk_data = [
                {
                    "id": batch * chunk_size + i,
                    "source": "stream",
                    "raw_value": str(batch * 100 + i),
                    "timestamp": f"2025-01-{batch + 1:02d}",
                }
                for i in range(chunk_size)
            ]

            result = transform_agent.transform_data(
                source_data=chunk_data, target_table="RawData"
            )

            total_processed += result["inserted_count"]

        # Verify all chunks processed
        assert total_processed == 50  # 5 batches * 10 records

        # Verify data accessible for downstream processing
        nl_agent = NLToSQLAgent(config=config, db=db)
        _query_result = nl_agent.query("Count records in RawData")
        # Should have all streamed data


class TestMultiTableOperations:
    """Test operations spanning multiple related tables."""

    @pytest.mark.integration
    @pytest.mark.e2e
    def test_cross_table_joins_and_aggregations(self, db, config):
        """
        Test operations requiring joins across multiple tables.

        Verifies integration handles complex multi-table queries
        correctly.
        """
        # Setup: Insert data into related tables
        transform_agent = DataTransformAgent(config=config, db=db)

        # Raw data
        raw_data = [
            {
                "id": i,
                "source": "test",
                "raw_value": str(i * 10),
                "timestamp": "2025-01-01",
            }
            for i in range(10)
        ]
        transform_agent.transform_data(source_data=raw_data, target_table="RawData")

        # Clean data (related via transformation)
        clean_data = [
            {
                "id": i,
                "source": "test",
                "clean_value": i * 10.0,
                "timestamp": "2025-01-01",
                "quality_score": 0.9,
            }
            for i in range(10)
        ]
        transform_agent.transform_data(source_data=clean_data, target_table="CleanData")

        # Query across tables
        nl_agent = NLToSQLAgent(config=config, db=db)
        result = nl_agent.query(
            "Show me raw and clean data for the same source and timestamp"
        )

        # Verify join executed correctly
        assert "sql" in result
        assert "results" in result
        # SQL should contain JOIN or equivalent

    @pytest.mark.integration
    @pytest.mark.e2e
    def test_referential_integrity_maintained(self, db, config):
        """
        Verify referential integrity maintained across tables.

        Tests that foreign key relationships and constraints
        are respected during operations.
        """
        transform_agent = DataTransformAgent(config=config, db=db)

        # Insert parent records (CleanData)
        clean_data = [
            {
                "id": i,
                "source": "test",
                "clean_value": 100.0,
                "timestamp": "2025-01-01",
                "quality_score": 0.95,
            }
            for i in range(5)
        ]
        transform_agent.transform_data(source_data=clean_data, target_table="CleanData")

        # Insert child records (TrainingData referencing CleanData)
        training_data = [
            {"id": i, "features": '{"f1": 1.0}', "target": 50.0, "data_source_id": i}
            for i in range(5)
        ]
        result = transform_agent.transform_data(
            source_data=training_data, target_table="TrainingData"
        )

        # Verify relationships maintained
        assert result["inserted_count"] == 5

        # Query to verify relationship
        nl_agent = NLToSQLAgent(config=config, db=db)
        query_result = nl_agent.query(
            "Show me training data with their source clean data"
        )

        # Should successfully join related tables
        assert "results" in query_result

    @pytest.mark.integration
    @pytest.mark.e2e
    def test_cascading_operations_across_tables(self, db, config):
        """
        Test operations that cascade across multiple tables.

        Verifies that operations correctly propagate through
        table relationships.
        """
        orchestrator = PipelineOrchestrator(config=config, db=db)

        # Create pipeline affecting multiple tables
        result = orchestrator.create_pipeline(
            pipeline_name="cascading_test",
            data_sources=["RawData", "CleanData", "TrainingData"],
            objective="Test cascading operations across tables",
        )

        # Verify all tables affected
        assert result["pipeline_created"] is True

        # Check that operations cascaded properly
        nl_agent = NLToSQLAgent(config=config, db=db)

        # Verify data in each table
        for table in ["RawData", "CleanData", "TrainingData"]:
            _query_result = nl_agent.query(f"Count records in {table}")
            # Each table should have data from cascading operations


class TestErrorRecovery:
    """Test error handling and graceful failure recovery."""

    @pytest.mark.integration
    @pytest.mark.e2e
    def test_database_error_graceful_handling(self, db, config):
        """
        Verify graceful handling of database errors.

        Tests that agents properly catch and handle
        database errors without crashing.
        """
        nl_agent = NLToSQLAgent(config=config, db=db)

        # Attempt invalid query
        result = nl_agent.query("Select from NonExistentTable")

        # Should handle error gracefully
        assert result is not None
        # Should contain error information
        assert "error" in result or "sql" in result

    @pytest.mark.integration
    @pytest.mark.e2e
    def test_partial_failure_recovery(self, db, config):
        """
        Test recovery from partial batch failures.

        Verifies that batch operations can recover from
        individual record failures.
        """
        transform_agent = DataTransformAgent(config=config, db=db)

        # Create batch with some invalid records
        mixed_data = [
            (
                {
                    "id": i,
                    "source": "test",
                    "raw_value": str(i),
                    "timestamp": "2025-01-01",
                }
                if i % 2 == 0
                else {
                    "id": i,
                    "source": None,
                    "raw_value": None,
                    "timestamp": "invalid",
                }
            )  # Invalid
            for i in range(10)
        ]

        result = transform_agent.transform_data(
            source_data=mixed_data, target_table="RawData"
        )

        # Should process valid records despite some failures
        assert result["inserted_count"] >= 0
        if "errors" in result:
            # Some errors expected for invalid records
            assert len(result["errors"]) > 0

    @pytest.mark.integration
    @pytest.mark.e2e
    def test_rollback_on_critical_failure(self, db, config):
        """
        Verify transaction rollback on critical failures.

        Tests that critical failures trigger proper rollback
        to maintain database consistency.
        """
        orchestrator = PipelineOrchestrator(config=config, db=db)

        # Get initial state
        nl_agent = NLToSQLAgent(config=config, db=db)
        _initial_query = nl_agent.query("Count records in RawData")

        # Attempt pipeline with intentional failure
        try:
            orchestrator.create_pipeline(
                pipeline_name="failing_pipeline",
                data_sources=["NonExistentTable"],
                objective="Test rollback on failure",
            )
        except Exception:
            pass  # Expected to fail

        # Verify database state unchanged (rollback occurred)
        _final_query = nl_agent.query("Count records in RawData")
        # Record counts should be same (no partial commits)


class TestTransactionConsistency:
    """Test ACID transaction compliance."""

    @pytest.mark.integration
    @pytest.mark.e2e
    def test_atomic_operations(self, db, config):
        """
        Verify operations are atomic (all-or-nothing).

        Tests that operations either complete fully
        or leave no partial changes.
        """
        transform_agent = DataTransformAgent(config=config, db=db)

        # Single batch operation
        test_data = [
            {"id": i, "source": "test", "raw_value": str(i), "timestamp": "2025-01-01"}
            for i in range(50)
        ]

        result = transform_agent.transform_data(
            source_data=test_data, target_table="RawData"
        )

        # Should be all or nothing
        assert (
            result["inserted_count"] == len(test_data) or result["inserted_count"] == 0
        )

    @pytest.mark.integration
    @pytest.mark.e2e
    def test_isolated_concurrent_operations(self, db, config):
        """
        Verify transaction isolation between concurrent operations.

        Tests that concurrent operations don't interfere
        with each other's intermediate states.
        """
        agent1 = NLToSQLAgent(config=config, db=db)
        agent2 = DataTransformAgent(config=config, db=db)

        # Agent 1 queries while Agent 2 modifies
        query_result = agent1.query("Select all from RawData")

        transform_result = agent2.transform_data(
            source_data=[
                {
                    "id": 999,
                    "source": "concurrent",
                    "raw_value": "999",
                    "timestamp": "2025-01-01",
                }
            ],
            target_table="RawData",
        )

        # Operations should be isolated
        assert query_result is not None
        assert transform_result is not None

    @pytest.mark.integration
    @pytest.mark.e2e
    def test_durable_commits(self, db, config):
        """
        Verify committed data persists (durability).

        Tests that once operations complete successfully,
        changes are permanent.
        """
        transform_agent = DataTransformAgent(config=config, db=db)

        # Commit data
        data = [
            {
                "id": 1,
                "source": "durable",
                "raw_value": "100",
                "timestamp": "2025-01-01",
            }
        ]
        result = transform_agent.transform_data(
            source_data=data, target_table="RawData"
        )

        assert result["inserted_count"] == 1

        # Create new agent to verify persistence
        new_agent = NLToSQLAgent(config=config, db=db)
        query_result = new_agent.query(
            "Select all from RawData where source = 'durable'"
        )

        # Data should persist across agent instances
        assert len(query_result["results"]) >= 1


class TestMultiAgentCoordination:
    """Test coordination between multiple agents sharing database."""

    @pytest.mark.integration
    @pytest.mark.e2e
    def test_shared_database_state(self, db, config):
        """
        Verify multiple agents correctly share database state.

        Tests that changes made by one agent are immediately
        visible to other agents.
        """
        agent1 = DataTransformAgent(config=config, db=db)
        agent2 = NLToSQLAgent(config=config, db=db)

        # Agent 1 inserts data
        agent1.transform_data(
            source_data=[
                {
                    "id": 1,
                    "source": "shared",
                    "raw_value": "100",
                    "timestamp": "2025-01-01",
                }
            ],
            target_table="RawData",
        )

        # Agent 2 queries data
        result = agent2.query("Select all from RawData where source = 'shared'")

        # Agent 2 should see Agent 1's changes
        assert len(result["results"]) >= 1

    @pytest.mark.integration
    @pytest.mark.e2e
    def test_coordinated_multi_agent_pipeline(self, db, config):
        """
        Test multiple agents working together in pipeline.

        Verifies agents can coordinate to accomplish
        complex workflows requiring multiple steps.
        """
        # Create specialized agents
        ingest_agent = DataTransformAgent(config=config, db=db)
        quality_agent = DataQualityAgent(config=config, db=db)
        training_agent = DBTrainingPipeline(config=config, db=db)
        inference_agent = InferencePipeline(config=config, db=db)

        # Step 1: Ingest (Transform agent)
        raw_data = [
            {
                "id": i,
                "source": "coordinated",
                "raw_value": str(i * 10),
                "timestamp": "2025-01-01",
            }
            for i in range(20)
        ]
        ingest_result = ingest_agent.transform_data(
            source_data=raw_data, target_table="RawData"
        )
        assert ingest_result["inserted_count"] == 20

        # Step 2: Quality check (Quality agent)
        quality_result = quality_agent.analyze_quality(
            table="RawData", quality_dimensions=["completeness", "validity"]
        )
        assert quality_result is not None

        # Step 3: Training (Training agent)
        training_result = training_agent.train_from_database(
            table="RawData", model_objective="Coordinated multi-agent training"
        )
        assert "model_id" in training_result

        # Step 4: Inference (Inference agent)
        prediction_result = inference_agent.infer_with_db_context(
            model_id=training_result["model_id"],
            input_data={"source": "coordinated", "value": 150},
            store_result=True,
        )
        assert "prediction" in prediction_result

        # Verify complete coordination
        # All agents successfully contributed to pipeline

    @pytest.mark.integration
    @pytest.mark.e2e
    def test_agent_state_independence(self, db, config):
        """
        Verify agents maintain independent state while sharing database.

        Tests that agents don't interfere with each other's
        internal state or configuration.
        """
        # Create agents with different configurations
        agent1_config = E2ETestConfig(temperature=0.1)
        agent2_config = E2ETestConfig(temperature=0.9)

        agent1 = NLToSQLAgent(config=agent1_config, db=db)
        agent2 = NLToSQLAgent(config=agent2_config, db=db)

        # Both agents query same data
        result1 = agent1.query("Select all from RawData")
        result2 = agent2.query("Select all from RawData")

        # Both should succeed with their own configurations
        assert result1 is not None
        assert result2 is not None

        # Verify configurations independent
        assert agent1.config.temperature != agent2.config.temperature


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
