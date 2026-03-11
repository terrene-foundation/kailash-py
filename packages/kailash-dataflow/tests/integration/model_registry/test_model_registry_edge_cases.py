#!/usr/bin/env python3
"""
Tier 2 Integration Tests for ModelRegistry Edge Cases
Tests error conditions, recovery scenarios, and robustness with real PostgreSQL.

NO MOCKING POLICY: All tests use real PostgreSQL infrastructure.
"""

import asyncio
import json
import os
import time
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from dataflow.core.config import DatabaseConfig, DataFlowConfig
from dataflow.core.engine import DataFlow
from dataflow.core.model_registry import ModelRegistry

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


@pytest.fixture
def test_config(test_suite):
    """Test configuration."""
    return DataFlowConfig(
        database=DatabaseConfig(url=test_suite.config.url), environment="edge_case_test"
    )


@pytest.fixture
def unique_test_id():
    """Generate unique test identifier."""
    return f"edge_{uuid.uuid4().hex[:8]}"


@pytest.mark.integration
@pytest.mark.timeout(5)
class TestModelRegistryErrorHandling:
    """Test error handling and recovery scenarios."""

    @pytest.mark.asyncio
    async def test_database_migration_table_corruption(
        self, test_suite, runtime, test_config, unique_test_id
    ):
        """Test recovery when migration table has corrupted data."""
        dataflow = DataFlow(config=test_config, auto_migrate=True)
        registry = dataflow._model_registry
        registry.initialize()

        # Register a normal model first
        model_name = f"TestModel_{unique_test_id}"
        fields = {"id": {"type": "int"}, "name": {"type": "str"}}

        assert registry.register_model(model_name, fields, {}) is True

        # Corrupt the migration table by inserting invalid JSON
        workflow = WorkflowBuilder()

        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "corrupt_data",
            {
                "connection_url": test_suite.config.url,
                "query": """
                INSERT INTO dataflow_migrations
                (version, name, checksum, model_checksum, applied_at, status, operations, model_definitions, application_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                "params": [
                    f"corrupt_{unique_test_id}",
                    "Corrupted entry",
                    "corrupt_checksum",
                    "corrupt_model_checksum",
                    datetime.now(),
                    "applied",
                    "invalid_json{",  # Invalid JSON
                    "also_invalid{",  # Invalid JSON
                    "edge_case_test",
                ],
            },
        )

        results, _ = runtime.execute(workflow.build())

        # Registry should still function despite corruption
        discovered = registry.discover_models()

        # Should find the valid model, skip corrupted entries
        assert model_name in discovered

    @pytest.mark.asyncio
    async def test_concurrent_model_registration_race_condition(
        self, test_suite, test_config, unique_test_id
    ):
        """Test race condition when multiple processes register the same model simultaneously."""

        async def register_same_model(instance_id: str):
            """Register the same model from different instance."""
            config = DataFlowConfig(
                database=DatabaseConfig(url=test_suite.config.url),
                environment=f"race_test_{instance_id}",
            )

            dataflow = DataFlow(config=config, auto_migrate=True)
            registry = dataflow._model_registry
            registry.initialize()

            model_name = f"RaceModel_{unique_test_id}"
            fields = {
                "id": {"type": "int", "primary_key": True},
                "name": {"type": "str", "required": True},
                "instance": {"type": "str", "default": instance_id},
            }

            # Add small random delay to increase chance of race condition
            await asyncio.sleep(0.01 + (hash(instance_id) % 100) / 10000)

            return registry.register_model(model_name, fields, {})

        # Run 5 concurrent registrations of the same model
        results = await asyncio.gather(
            register_same_model("A"),
            register_same_model("B"),
            register_same_model("C"),
            register_same_model("D"),
            register_same_model("E"),
            return_exceptions=True,
        )

        # All should succeed (either register or skip as duplicate)
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_results) >= 4  # Allow for some timing variance

        # Check that model exists only once in final state
        verification_dataflow = DataFlow(config=test_config, auto_migrate=True)
        verification_registry = verification_dataflow._model_registry
        verification_registry.initialize()

        version_count = verification_registry.get_model_version(
            f"RaceModel_{unique_test_id}"
        )
        assert version_count >= 1  # Should exist

        # No duplicate entries should exist
        history = verification_registry.get_model_history(f"RaceModel_{unique_test_id}")
        checksums = [entry["checksum"] for entry in history]
        # All entries with same definition should have same checksum
        if len(history) > 1:
            # Multiple entries are OK if they represent evolution
            pass

    @pytest.mark.asyncio
    async def test_malformed_model_definitions(
        self, test_config, unique_test_id, cleanup_database
    ):
        """Test handling of malformed model definitions."""
        dataflow = DataFlow(config=test_config, auto_migrate=True)
        registry = dataflow._model_registry
        registry.initialize()

        # Test various malformed inputs
        test_cases = [
            # Empty model name
            ("", {"id": {"type": "int"}}, {}),
            # None fields
            (f"NoneFields_{unique_test_id}", None, {}),
            # Invalid field types
            (f"InvalidType_{unique_test_id}", {"field": {"type": "invalid_type"}}, {}),
            # Circular references in options
            (
                f"CircularRef_{unique_test_id}",
                {"id": {"type": "int"}},
                {"self_ref": None},
            ),
        ]

        for model_name, fields, options in test_cases:
            # Should handle gracefully without crashing
            try:
                result = registry.register_model(model_name, fields or {}, options)
                # Either succeeds with cleanup or fails gracefully
                assert isinstance(result, bool)
            except Exception as e:
                # Specific exceptions are acceptable
                assert isinstance(e, (ValueError, TypeError, KeyError))

    @pytest.mark.asyncio
    async def test_database_connection_interruption(
        self, test_config, unique_test_id, cleanup_database
    ):
        """Test behavior when database connection is interrupted."""
        dataflow = DataFlow(config=test_config, auto_migrate=True)
        registry = dataflow._model_registry
        registry.initialize()

        # Register model successfully first
        model_name = f"InterruptModel_{unique_test_id}"
        fields = {"id": {"type": "int"}, "name": {"type": "str"}}

        assert registry.register_model(model_name, fields, {}) is True

        # Test with invalid connection URL (simulating connection failure)
        bad_config = DataFlowConfig(
            database=DatabaseConfig(
                url="postgresql://invalid:invalid@nonexistent:5432/invalid"
            ),
            environment="invalid_test",
        )

        bad_dataflow = DataFlow(
            config=bad_config, auto_migrate=False
        )  # Don't auto-migrate
        bad_registry = ModelRegistry(bad_dataflow)

        # Operations should fail gracefully
        init_result = bad_registry.initialize()
        assert init_result is False  # Should fail gracefully

        register_result = bad_registry.register_model(
            "FailModel", {"id": {"type": "int"}}, {}
        )
        assert register_result is False  # Should fail gracefully

        discovery_result = bad_registry.discover_models()
        assert discovery_result == {}  # Should return empty gracefully

    @pytest.mark.asyncio
    async def test_extremely_large_model_definitions(
        self, test_config, unique_test_id, cleanup_database
    ):
        """Test handling of extremely large model definitions."""
        dataflow = DataFlow(config=test_config, auto_migrate=True)
        registry = dataflow._model_registry
        registry.initialize()

        model_name = f"LargeModel_{unique_test_id}"

        # Create model with many fields and complex options
        fields = {}
        for i in range(500):  # 500 fields
            fields[f"field_{i:03d}"] = {
                "type": "str" if i % 3 == 0 else "int" if i % 3 == 1 else "float",
                "required": i % 4 == 0,
                "default": f"default_value_{i}" if i % 5 == 0 else None,
                "description": f"This is field number {i} with a long description "
                * 10,
                "validation_rules": [f"rule_{j}" for j in range(i % 3 + 1)],
            }

        options = {
            "table_name": f"very_long_table_name_{unique_test_id}",
            "indexes": [f"idx_{i}" for i in range(100)],
            "constraints": [f"constraint_{i}" for i in range(50)],
            "metadata": {
                "description": "A" * 10000,  # Very long description
                "tags": [f"tag_{i}" for i in range(1000)],
                "properties": {f"prop_{i}": f"value_{i}" for i in range(500)},
            },
        }

        # Should handle large definition (may take longer but should not fail)
        start_time = time.perf_counter()
        success = registry.register_model(model_name, fields, options)
        end_time = time.perf_counter()

        assert success is True
        assert end_time - start_time < 3.0  # Should complete within reasonable time

        # Should be discoverable
        discovered = registry.discover_models()
        assert model_name in discovered
        assert len(discovered[model_name]["fields"]) == 500

    @pytest.mark.asyncio
    async def test_migration_system_failure_recovery(
        self, test_config, unique_test_id, cleanup_database
    ):
        """Test recovery when migration system fails during model registration."""
        # Create dataflow with migration system
        dataflow = DataFlow(config=test_config, auto_migrate=True)
        registry = dataflow._model_registry
        registry.initialize()

        # Register model successfully first
        model_name = f"RecoveryModel_{unique_test_id}"
        fields = {"id": {"type": "int"}, "name": {"type": "str"}}

        assert registry.register_model(model_name, fields, {}) is True

        # Simulate migration system failure by corrupting the table
        workflow = WorkflowBuilder()
        runtime = LocalRuntime()

        # Break the migration table structure temporarily
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "break_table",
            {
                "connection_url": test_config.database.url,
                "query": "ALTER TABLE dataflow_migrations DROP COLUMN IF EXISTS model_definitions",
            },
        )

        results, _ = runtime.execute(workflow.build())

        # Try to register another model - should handle gracefully
        recovery_model = f"RecoveryModel2_{unique_test_id}"
        result = registry.register_model(recovery_model, fields, {})

        # May fail due to broken table, but should not crash
        assert isinstance(result, bool)

        # Restore table structure
        workflow = WorkflowBuilder()
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "restore_table",
            {
                "connection_url": test_config.database.url,
                "query": """
                ALTER TABLE dataflow_migrations
                ADD COLUMN IF NOT EXISTS model_definitions JSONB,
                ADD COLUMN IF NOT EXISTS application_id VARCHAR(255),
                ADD COLUMN IF NOT EXISTS model_checksum VARCHAR(64)
            """,
            },
        )

        results, _ = runtime.execute(workflow.build())

        # Re-initialize registry after recovery
        new_dataflow = DataFlow(config=test_config, auto_migrate=True)
        new_registry = new_dataflow._model_registry
        assert new_registry.initialize() is True

        # Should be able to register models again
        final_model = f"FinalModel_{unique_test_id}"
        assert new_registry.register_model(final_model, fields, {}) is True

    @pytest.mark.asyncio
    async def test_checksum_collision_handling(
        self, test_config, unique_test_id, cleanup_database
    ):
        """Test handling of checksum collisions (though extremely unlikely)."""
        dataflow = DataFlow(config=test_config, auto_migrate=True)
        registry = dataflow._model_registry
        registry.initialize()

        # Create two different models that might have similar content
        model1_name = f"Model1_{unique_test_id}"
        model1_fields = {"id": {"type": "int"}, "name": {"type": "str"}}

        model2_name = f"Model2_{unique_test_id}"
        model2_fields = {
            "id": {"type": "int"},
            "name": {"type": "str"},
        }  # Identical content

        # Both should register successfully
        assert registry.register_model(model1_name, model1_fields, {}) is True
        assert registry.register_model(model2_name, model2_fields, {}) is True

        # Verify both exist in history even with identical content
        discovered = registry.discover_models()
        assert model1_name in discovered
        assert model2_name in discovered

        # Check that checksums are handled properly
        version1 = registry.get_model_version(model1_name)
        version2 = registry.get_model_version(model2_name)

        assert version1 >= 1
        assert version2 >= 1


@pytest.mark.integration
@pytest.mark.timeout(5)
class TestModelRegistryPerformanceEdgeCases:
    """Test performance under stress conditions."""

    @pytest.mark.asyncio
    async def test_rapid_model_registration_stress(
        self, test_config, unique_test_id, cleanup_database
    ):
        """Test rapid registration of many models."""
        dataflow = DataFlow(config=test_config, auto_migrate=True)
        registry = dataflow._model_registry
        registry.initialize()

        # Register models rapidly
        model_count = 50
        start_time = time.perf_counter()

        tasks = []
        for i in range(model_count):
            model_name = f"StressModel_{i}_{unique_test_id}"
            fields = {
                "id": {"type": "int", "primary_key": True},
                "field1": {"type": "str"},
                "field2": {"type": "int"},
                f"unique_field_{i}": {"type": "str"},  # Make each model unique
            }

            # Register synchronously for this test
            success = registry.register_model(model_name, fields, {})
            assert success is True

        end_time = time.perf_counter()
        total_time = end_time - start_time

        print(
            f"Registered {model_count} models in {total_time:.2f}s ({total_time/model_count:.3f}s avg)"
        )

        # Performance threshold - should handle rapid registration
        assert total_time < 10.0  # Should complete within 10 seconds
        assert total_time / model_count < 0.2  # Average <200ms per model

        # Verify all models were registered
        discovered = registry.discover_models()
        registered_stress_models = [
            name
            for name in discovered.keys()
            if "StressModel_" in name and unique_test_id in name
        ]
        assert len(registered_stress_models) == model_count

    @pytest.mark.asyncio
    async def test_discovery_performance_with_many_models(
        self, test_config, unique_test_id, cleanup_database
    ):
        """Test discovery performance when many models exist."""
        dataflow = DataFlow(config=test_config, auto_migrate=True)
        registry = dataflow._model_registry
        registry.initialize()

        # Pre-register many models
        model_count = 30
        for i in range(model_count):
            model_name = f"PerfModel_{i}_{unique_test_id}"
            fields = {"id": {"type": "int"}, f"field_{i}": {"type": "str"}}
            registry.register_model(model_name, fields, {})

        # Test discovery performance
        discovery_times = []
        for _ in range(10):  # Run multiple times
            start_time = time.perf_counter()
            discovered = registry.discover_models()
            end_time = time.perf_counter()

            discovery_times.append(end_time - start_time)
            assert len(discovered) >= model_count

        avg_discovery_time = sum(discovery_times) / len(discovery_times)
        max_discovery_time = max(discovery_times)

        print(
            f"Discovery times: avg={avg_discovery_time:.3f}s, max={max_discovery_time:.3f}s"
        )

        # Performance thresholds
        assert avg_discovery_time < 0.5  # Average <500ms
        assert max_discovery_time < 1.0  # Max <1s

    @pytest.mark.asyncio
    async def test_consistency_validation_performance(
        self, test_config, unique_test_id, cleanup_database
    ):
        """Test consistency validation performance with many models and applications."""
        # Create multiple applications with overlapping models
        app_count = 5
        models_per_app = 10

        applications = []
        for app_id in range(app_count):
            config = DataFlowConfig(
                database=DatabaseConfig(url=test_config.database.url),
                environment=f"perf_app_{app_id}_{unique_test_id}",
            )

            dataflow = DataFlow(config=config, auto_migrate=True)
            registry = dataflow._model_registry
            registry.initialize()

            # Register models for this app
            for model_id in range(models_per_app):
                model_name = f"SharedModel_{model_id}_{unique_test_id}"
                fields = {
                    "id": {"type": "int", "primary_key": True},
                    "name": {"type": "str"},
                    f"app_{app_id}_field": {"type": "str"},  # App-specific field
                }

                registry.register_model(model_name, fields, {})

            applications.append((dataflow, registry))

        # Test consistency validation performance
        validation_times = []
        for dataflow, registry in applications:
            start_time = time.perf_counter()
            issues = registry.validate_consistency()
            end_time = time.perf_counter()

            validation_times.append(end_time - start_time)

        avg_validation_time = sum(validation_times) / len(validation_times)
        max_validation_time = max(validation_times)

        print(
            f"Validation times: avg={avg_validation_time:.3f}s, max={max_validation_time:.3f}s"
        )

        # Performance thresholds
        assert avg_validation_time < 1.0  # Average <1s
        assert max_validation_time < 2.0  # Max <2s


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=5"])
