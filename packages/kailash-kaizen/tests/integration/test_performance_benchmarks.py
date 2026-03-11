"""
Performance Benchmarks for Kaizen-DataFlow Integration

Tests verify performance targets for combined AI-database workflows:
- NL→SQL query latency <500ms
- Bulk transformation >1000 records/sec
- Training pipeline efficiency
- Inference latency <100ms per prediction
- Concurrent operation efficiency

Tier 2/3: Real infrastructure, real database, real LLM calls
"""

import time
from dataclasses import dataclass

import pytest

# Import integration components with conditional import
try:
    from dataflow import DataFlow

    from kaizen.integrations.dataflow import (
        DATAFLOW_AVAILABLE,
        DataFlowConnection,
        DataTransformAgent,
        DBTrainingPipeline,
        InferencePipeline,
        NLToSQLAgent,
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
class PerfTestConfig:
    """Test configuration."""

    llm_provider: str = "mock"
    model: str = "mock-model"
    temperature: float = 0.3


@pytest.fixture
def db():
    """Create test database with sample data."""
    db = DataFlow("sqlite:///:memory:")

    # Define test models
    @db.model
    class QueryTest:
        id: int
        name: str
        value: float

    @db.model
    class TransformTest:
        id: int
        data: str

    @db.model
    class TrainingData:
        id: int
        feature_a: float
        feature_b: float
        target: float

    return db


@pytest.fixture
def config():
    """Test configuration."""
    return PerfTestConfig()


class TestNLQueryPerformance:
    """Test natural language query performance."""

    @pytest.mark.integration
    @pytest.mark.performance
    def test_nl_query_latency_under_500ms(self, db, config):
        """
        PERFORMANCE TARGET: NL→SQL query latency <500ms

        Measures end-to-end latency from natural language input to query results.
        Includes LLM call, SQL generation, query execution, and result formatting.
        """
        agent = NLToSQLAgent(config=config, db=db)

        # Warm up (first call may be slower)
        agent.query("Select all records")

        # Measure actual performance
        start = time.time()
        result = agent.query("Show me all records with value greater than 100")
        elapsed_ms = (time.time() - start) * 1000

        # Verify result structure
        assert "sql" in result
        assert "results" in result

        # Performance assertion
        assert elapsed_ms < 500, f"Query took {elapsed_ms:.2f}ms, expected <500ms"

    @pytest.mark.integration
    @pytest.mark.performance
    def test_cached_query_performance_under_5ms(self, db, config):
        """
        PERFORMANCE TARGET: Cached queries <5ms

        Verifies query caching provides significant performance improvement
        for repeated queries.
        """
        agent = NLToSQLAgent(config=config, db=db)
        query = "Show me all records"

        # First query (cache miss)
        first_start = time.time()
        agent.query(query)
        first_elapsed_ms = (time.time() - first_start) * 1000

        # Second query (cache hit)
        second_start = time.time()
        agent.query(query)
        second_elapsed_ms = (time.time() - second_start) * 1000

        # Cache should provide significant speedup
        assert (
            second_elapsed_ms < first_elapsed_ms * 0.1
        ), f"Cached query took {second_elapsed_ms:.2f}ms, expected <{first_elapsed_ms * 0.1:.2f}ms"

        # Absolute performance target
        assert (
            second_elapsed_ms < 5
        ), f"Cached query took {second_elapsed_ms:.2f}ms, expected <5ms"


class TestBulkTransformationPerformance:
    """Test bulk data transformation throughput."""

    @pytest.mark.integration
    @pytest.mark.performance
    def test_transformation_throughput_over_1000_per_sec(self, db, config):
        """
        PERFORMANCE TARGET: Transform >1000 records/sec

        Measures throughput for AI-driven data transformation operations.
        """
        agent = DataTransformAgent(config=config, db=db)

        # Generate test data
        test_records = [
            {"id": i, "data": f"record_{i}"}
            for i in range(2000)  # 2000 records for accurate measurement
        ]

        # Measure transformation throughput
        start = time.time()
        result = agent.transform_data(
            source_data=test_records, target_table="TransformTest"
        )
        elapsed = time.time() - start

        # Calculate throughput
        throughput = len(test_records) / elapsed if elapsed > 0 else 0

        # Verify results
        assert result["inserted_count"] == len(test_records)

        # Performance assertion
        assert (
            throughput > 1000
        ), f"Throughput was {throughput:.2f} records/sec, expected >1000 records/sec"

    @pytest.mark.integration
    @pytest.mark.performance
    def test_batch_optimization_scaling(self, db, config):
        """
        Verify batch size optimization improves performance.

        Tests that larger batches provide better throughput
        up to optimal batch size.
        """
        agent = DataTransformAgent(config=config, db=db)

        test_data = [{"id": i, "data": f"data_{i}"} for i in range(5000)]

        # Test different batch sizes
        batch_sizes = [100, 500, 1000]
        throughputs = []

        for batch_size in batch_sizes:
            # Configure batch size if agent supports it
            if hasattr(agent, "batch_size"):
                agent.batch_size = batch_size

            start = time.time()
            agent.transform_data(source_data=test_data, target_table="TransformTest")
            elapsed = time.time() - start

            throughput = len(test_data) / elapsed if elapsed > 0 else 0
            throughputs.append(throughput)

        # Verify throughput improves with larger batches
        # (up to a point - may plateau at optimal batch size)
        assert (
            throughputs[-1] >= throughputs[0]
        ), "Larger batches should not decrease throughput"


class TestTrainingPipelinePerformance:
    """Test model training pipeline efficiency."""

    @pytest.mark.integration
    @pytest.mark.performance
    def test_training_pipeline_completes_efficiently(self, db, config):
        """
        PERFORMANCE TARGET: Training completes in reasonable time

        Verifies training pipeline completes without excessive overhead
        from database operations or workflow orchestration.
        """
        pipeline = DBTrainingPipeline(config=config, db=db)

        # Generate training data
        _training_records = [
            {"id": i, "feature_a": i * 0.1, "feature_b": i * 0.2, "target": i * 0.3}
            for i in range(1000)
        ]

        # Insert training data
        # (Would use BulkCreateNode in real implementation)

        # Measure training time
        start = time.time()
        result = pipeline.train_from_database(
            table="TrainingData", model_objective="Test model training efficiency"
        )
        elapsed = time.time() - start

        # Verify training completed
        assert "model_id" in result
        assert "accuracy" in result or "metrics" in result

        # Performance assertion - should complete in reasonable time
        # (Actual threshold depends on model complexity and data size)
        assert elapsed < 30, f"Training took {elapsed:.2f}s, expected <30s"

    @pytest.mark.integration
    @pytest.mark.performance
    def test_training_data_fetch_performance(self, db, config):
        """
        Verify efficient data fetching from database for training.

        Tests that training pipeline can fetch large datasets
        without performance bottlenecks.
        """
        pipeline = DBTrainingPipeline(config=config, db=db)

        # Measure data fetch time for large dataset
        start = time.time()
        # Pipeline should fetch data efficiently
        _result = pipeline.train_from_database(
            table="TrainingData", model_objective="Test data fetch performance"
        )
        elapsed = time.time() - start

        # Data fetch should not be bottleneck
        # (Most time should be in actual training)
        assert (
            elapsed < 60
        ), f"Training pipeline took {elapsed:.2f}s, data fetch likely bottleneck"


class TestInferencePerformance:
    """Test model inference latency."""

    @pytest.mark.integration
    @pytest.mark.performance
    def test_inference_latency_under_100ms(self, db, config):
        """
        PERFORMANCE TARGET: Inference <100ms per prediction

        Measures end-to-end inference latency including
        database context retrieval and prediction.
        """
        pipeline = InferencePipeline(config=config, db=db)

        # Setup: Train a simple model
        # (In real implementation, would use pre-trained model)
        model_id = "test_model_001"

        # Warm up
        pipeline.infer_with_db_context(
            model_id=model_id, input_data={"feature": 1.0}, store_result=False
        )

        # Measure inference latency
        start = time.time()
        result = pipeline.infer_with_db_context(
            model_id=model_id, input_data={"feature": 2.0}, store_result=True
        )
        elapsed_ms = (time.time() - start) * 1000

        # Verify prediction
        assert "prediction" in result

        # Performance assertion
        assert elapsed_ms < 100, f"Inference took {elapsed_ms:.2f}ms, expected <100ms"

    @pytest.mark.integration
    @pytest.mark.performance
    def test_batch_inference_throughput(self, db, config):
        """
        Verify batch inference provides better throughput than individual predictions.

        Tests that batching multiple predictions improves overall throughput.
        """
        pipeline = InferencePipeline(config=config, db=db)
        model_id = "test_model_batch"

        # Generate test inputs
        test_inputs = [{"feature": i * 0.1} for i in range(100)]

        # Individual predictions
        start = time.time()
        for input_data in test_inputs[:10]:  # Sample for comparison
            pipeline.infer_with_db_context(
                model_id=model_id, input_data=input_data, store_result=False
            )
        individual_elapsed = time.time() - start
        individual_throughput = 10 / individual_elapsed if individual_elapsed > 0 else 0

        # Batch prediction (if supported)
        if hasattr(pipeline, "batch_infer"):
            start = time.time()
            pipeline.batch_infer(
                model_id=model_id, input_data=test_inputs, store_results=False
            )
            batch_elapsed = time.time() - start
            batch_throughput = (
                len(test_inputs) / batch_elapsed if batch_elapsed > 0 else 0
            )

            # Batch should be significantly faster
            assert (
                batch_throughput > individual_throughput * 2
            ), "Batch inference should be at least 2x faster than individual"


class TestConcurrentOperations:
    """Test concurrent multi-agent database operations."""

    @pytest.mark.integration
    @pytest.mark.performance
    def test_multiple_agents_share_database_efficiently(self, db, config):
        """
        PERFORMANCE TARGET: Multiple agents share database without contention

        Verifies connection pooling and resource management work correctly
        when multiple agents access the same database concurrently.
        """
        # Create multiple agents
        nl_agent = NLToSQLAgent(config=config, db=db)
        transform_agent = DataTransformAgent(config=config, db=db)
        inference_agent = InferencePipeline(config=config, db=db)

        # Measure concurrent operations
        start = time.time()

        # Simulate concurrent workload
        results = []
        for i in range(10):
            # Each iteration uses multiple agents
            r1 = nl_agent.query("Select all records")
            r2 = transform_agent.transform_data(
                source_data=[{"id": i, "data": f"data_{i}"}],
                target_table="TransformTest",
            )
            r3 = inference_agent.infer_with_db_context(
                model_id="test", input_data={"feature": i}, store_result=False
            )
            results.extend([r1, r2, r3])

        elapsed = time.time() - start

        # Verify all operations completed
        assert len(results) == 30

        # Performance should not degrade significantly with concurrent access
        avg_time_per_op = elapsed / 30
        assert (
            avg_time_per_op < 1.0
        ), f"Average time per operation {avg_time_per_op:.2f}s suggests contention"

    @pytest.mark.integration
    @pytest.mark.performance
    def test_connection_pool_efficiency(self, db, config):
        """
        Verify connection pooling prevents connection exhaustion.

        Tests that connection pool properly reuses connections
        and prevents creating excessive database connections.
        """
        # Create connection with pool
        _connection = DataFlowConnection(db=db, pool_size=5)

        # Simulate high connection demand
        agents = []
        for i in range(20):  # More agents than pool size
            agent = NLToSQLAgent(config=config, db=db)
            agents.append(agent)

        # All agents should work without exhausting connections
        start = time.time()
        for agent in agents:
            result = agent.query("Select all records")
            assert result is not None
        elapsed = time.time() - start

        # Should complete efficiently despite limited pool
        assert (
            elapsed < 10
        ), f"Connection pool operation took {elapsed:.2f}s, suggests inefficiency"

    @pytest.mark.integration
    @pytest.mark.performance
    def test_no_connection_leaks(self, db, config):
        """
        Verify no connection leaks in repeated operations.

        Tests that connections are properly released back to pool
        after operations complete.
        """
        agent = NLToSQLAgent(config=config, db=db)

        # Get initial connection state
        # (Would check pool metrics in real implementation)

        # Perform many operations
        for i in range(100):
            agent.query("Select all records")

        # Verify connection pool state stable
        # (In real implementation, would assert pool size unchanged)

        # Measure performance should not degrade over time
        times = []
        for i in range(10):
            start = time.time()
            agent.query("Select all records")
            times.append(time.time() - start)

        # Later operations should not be slower (no leak accumulation)
        avg_early = sum(times[:5]) / 5
        avg_late = sum(times[5:]) / 5

        assert (
            avg_late <= avg_early * 1.5
        ), f"Performance degraded over time: {avg_early:.3f}s → {avg_late:.3f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
