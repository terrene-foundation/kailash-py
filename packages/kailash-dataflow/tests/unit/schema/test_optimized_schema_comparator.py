"""
Unit tests for OptimizedSchemaComparator performance optimization.

This module tests the schema comparison optimization system that provides:
- Early termination on first difference
- Incremental comparison for changed portions only
- Memory efficient processing of large schemas
"""

import time
import unittest
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union
from unittest.mock import MagicMock, Mock, patch

import pytest


@dataclass
class ModelSchema:
    """Mock model schema for testing."""

    tables: Dict[str, Dict[str, Any]]
    schema_id: str


@dataclass
class DatabaseSchema:
    """Mock database schema for testing."""

    tables: Dict[str, Dict[str, Any]]
    schema_id: str


class TestOptimizedSchemaComparator(unittest.TestCase):
    """Test suite for OptimizedSchemaComparator class."""

    def setUp(self):
        """Set up test fixtures."""
        # Import the real class
        from dataflow.performance.migration_optimizer import OptimizedSchemaComparator

        self.comparator = OptimizedSchemaComparator(max_schema_size=1000)

    def test_comparator_initialization(self):
        """Test OptimizedSchemaComparator initializes correctly."""
        self.assertIsNotNone(self.comparator)
        self.assertEqual(self.comparator.max_schema_size, 1000)
        self.assertIsInstance(self.comparator._fingerprint_cache, dict)

    def test_compare_schemas_optimized_identical_schemas(self):
        """Test optimized comparison with identical schemas (early termination)."""
        # Setup identical schemas
        model_schema = ModelSchema(
            tables={
                "users": {
                    "columns": {
                        "id": {
                            "type": "INTEGER",
                            "nullable": False,
                            "primary_key": True,
                        },
                        "name": {"type": "VARCHAR(255)", "nullable": False},
                    }
                }
            },
            schema_id="model_schema_1",
        )

        db_schema = DatabaseSchema(
            tables={
                "users": {
                    "columns": {
                        "id": {
                            "type": "INTEGER",
                            "nullable": False,
                            "primary_key": True,
                        },
                        "name": {"type": "VARCHAR(255)", "nullable": False},
                    }
                }
            },
            schema_id="db_schema_1",
        )

        # Execute
        start_time = time.time()
        result = self.comparator.compare_schemas_optimized(model_schema, db_schema)
        execution_time_ms = (time.time() - start_time) * 1000

        # Import the correct ComparisonResult type
        from dataflow.performance.migration_optimizer import ComparisonResult

        # Verify early termination and performance
        self.assertIsInstance(result, ComparisonResult)
        self.assertFalse(result.schemas_differ)
        self.assertTrue(result.early_termination)
        self.assertTrue(result.fingerprint_match)
        self.assertLess(result.comparison_time_ms, 100)  # Should be very fast
        self.assertEqual(len(result.differences), 0)

    def test_compare_schemas_optimized_different_schemas(self):
        """Test optimized comparison with different schemas."""
        # Setup different schemas
        model_schema = ModelSchema(
            tables={
                "users": {
                    "columns": {
                        "id": {
                            "type": "INTEGER",
                            "nullable": False,
                            "primary_key": True,
                        },
                        "name": {"type": "VARCHAR(255)", "nullable": False},
                        "email": {
                            "type": "VARCHAR(255)",
                            "nullable": False,
                        },  # Extra column
                    }
                }
            },
            schema_id="model_schema_2",
        )

        db_schema = DatabaseSchema(
            tables={
                "users": {
                    "columns": {
                        "id": {
                            "type": "INTEGER",
                            "nullable": False,
                            "primary_key": True,
                        },
                        "name": {"type": "VARCHAR(255)", "nullable": False},
                    }
                }
            },
            schema_id="db_schema_2",
        )

        # Execute
        result = self.comparator.compare_schemas_optimized(model_schema, db_schema)

        # Verify differences detected
        from dataflow.performance.migration_optimizer import ComparisonResult

        self.assertIsInstance(result, ComparisonResult)
        self.assertTrue(result.schemas_differ)
        self.assertFalse(result.early_termination)
        self.assertFalse(result.fingerprint_match)
        self.assertGreater(len(result.differences), 0)
        self.assertLess(result.comparison_time_ms, 1000)  # Should still be fast

    def test_compare_schemas_optimized_missing_table(self):
        """Test comparison when model has tables not in database."""
        # Setup schemas with missing table
        model_schema = ModelSchema(
            tables={
                "users": {"columns": {"id": {"type": "INTEGER", "nullable": False}}},
                "orders": {"columns": {"id": {"type": "INTEGER", "nullable": False}}},
            },
            schema_id="model_schema_3",
        )

        db_schema = DatabaseSchema(
            tables={
                "users": {"columns": {"id": {"type": "INTEGER", "nullable": False}}}
            },
            schema_id="db_schema_3",
        )

        # Execute
        result = self.comparator.compare_schemas_optimized(model_schema, db_schema)

        # Verify missing table detected
        self.assertTrue(result.schemas_differ)
        self.assertGreater(len(result.differences), 0)

        # Check for missing table difference
        missing_table_diffs = [
            d for d in result.differences if d.get("type") == "missing_table"
        ]
        self.assertGreater(len(missing_table_diffs), 0)
        self.assertEqual(missing_table_diffs[0]["table"], "orders")

    def test_generate_schema_fingerprint_consistency(self):
        """Test schema fingerprint generation is consistent."""
        schema = ModelSchema(
            tables={
                "users": {
                    "columns": {
                        "id": {"type": "INTEGER", "nullable": False},
                        "name": {"type": "VARCHAR(255)", "nullable": True},
                    }
                }
            },
            schema_id="test_schema",
        )

        # Generate fingerprint multiple times
        fingerprint1 = self.comparator.generate_schema_fingerprint(schema)
        fingerprint2 = self.comparator.generate_schema_fingerprint(schema)
        fingerprint3 = self.comparator.generate_schema_fingerprint(schema)

        # Verify consistency
        self.assertEqual(fingerprint1, fingerprint2)
        self.assertEqual(fingerprint2, fingerprint3)
        self.assertIsInstance(fingerprint1, str)
        self.assertGreater(len(fingerprint1), 0)

    def test_generate_schema_fingerprint_different_schemas(self):
        """Test that different schemas produce different fingerprints."""
        schema1 = ModelSchema(
            tables={
                "users": {
                    "columns": {
                        "id": {"type": "INTEGER", "nullable": False},
                        "name": {"type": "VARCHAR(255)", "nullable": True},
                    }
                }
            },
            schema_id="schema1",
        )

        schema2 = ModelSchema(
            tables={
                "users": {
                    "columns": {
                        "id": {"type": "INTEGER", "nullable": False},
                        "name": {
                            "type": "VARCHAR(255)",
                            "nullable": False,
                        },  # Different nullable
                    }
                }
            },
            schema_id="schema2",
        )

        fingerprint1 = self.comparator.generate_schema_fingerprint(schema1)
        fingerprint2 = self.comparator.generate_schema_fingerprint(schema2)

        # Verify different fingerprints
        self.assertNotEqual(fingerprint1, fingerprint2)

    def test_fingerprint_caching(self):
        """Test that fingerprints are cached properly."""
        schema = ModelSchema(
            tables={
                "users": {"columns": {"id": {"type": "INTEGER", "nullable": False}}}
            },
            schema_id="cache_test_schema",
        )

        # Clear cache first
        self.comparator._fingerprint_cache.clear()

        # Generate fingerprint - should cache it
        fingerprint1 = self.comparator.generate_schema_fingerprint(schema)

        # Verify cache contains entry
        self.assertIn("cache_test_schema", self.comparator._fingerprint_cache)
        self.assertEqual(
            self.comparator._fingerprint_cache["cache_test_schema"], fingerprint1
        )

        # Generate again - should use cache
        fingerprint2 = self.comparator.generate_schema_fingerprint(schema)
        self.assertEqual(fingerprint1, fingerprint2)

    def test_incremental_schema_comparison_no_changes(self):
        """Test incremental comparison when no changes exist."""
        prev_fingerprint = "stable_fingerprint_123"
        current_schema = ModelSchema(
            tables={
                "users": {"columns": {"id": {"type": "INTEGER", "nullable": False}}}
            },
            schema_id="incremental_test",
        )

        # Mock fingerprint generation to return same fingerprint
        with patch.object(
            self.comparator, "generate_schema_fingerprint"
        ) as mock_fingerprint:
            mock_fingerprint.return_value = prev_fingerprint

            # Execute
            result = self.comparator.incremental_schema_comparison(
                prev_fingerprint, current_schema
            )

            # Import the correct IncrementalResult type
            from dataflow.performance.migration_optimizer import IncrementalResult

            # Verify no changes detected
            self.assertIsInstance(result, IncrementalResult)
            self.assertFalse(result.has_changes)
            self.assertEqual(len(result.changed_tables), 0)
            self.assertLess(result.processing_time_ms, 100)

    def test_incremental_schema_comparison_with_changes(self):
        """Test incremental comparison when changes exist."""
        prev_fingerprint = "old_fingerprint_456"
        current_schema = ModelSchema(
            tables={
                "users": {"columns": {"id": {"type": "INTEGER", "nullable": False}}},
                "orders": {"columns": {"id": {"type": "INTEGER", "nullable": False}}},
            },
            schema_id="incremental_changes_test",
        )

        # Mock fingerprint generation to return different fingerprint
        with patch.object(
            self.comparator, "generate_schema_fingerprint"
        ) as mock_fingerprint:
            mock_fingerprint.return_value = "new_fingerprint_789"

            # Execute
            result = self.comparator.incremental_schema_comparison(
                prev_fingerprint, current_schema
            )

            # Verify changes detected
            self.assertTrue(result.has_changes)
            self.assertGreater(len(result.changed_tables), 0)
            self.assertLess(result.processing_time_ms, 200)

    def test_large_schema_performance(self):
        """Test performance with large schemas."""
        # Generate large schema
        large_schema = ModelSchema(
            tables={
                f"table_{i}": {
                    "columns": {
                        f"column_{j}": {"type": "VARCHAR(255)", "nullable": j % 2 == 0}
                        for j in range(20)  # 20 columns per table
                    }
                }
                for i in range(50)  # 50 tables
            },
            schema_id="large_schema_test",
        )

        # Create similar large schema with slight differences
        large_db_schema = DatabaseSchema(
            tables={
                f"table_{i}": {
                    "columns": {
                        f"column_{j}": {"type": "VARCHAR(255)", "nullable": j % 2 == 0}
                        for j in range(19)  # 19 columns per table (1 less)
                    }
                }
                for i in range(50)  # 50 tables
            },
            schema_id="large_db_schema_test",
        )

        # Execute and measure performance
        start_time = time.time()
        result = self.comparator.compare_schemas_optimized(
            large_schema, large_db_schema
        )
        execution_time_ms = (time.time() - start_time) * 1000

        # Verify performance is reasonable for large schema
        self.assertLess(execution_time_ms, 5000)  # Should complete within 5 seconds
        self.assertTrue(result.schemas_differ)  # Should detect differences
        self.assertGreater(len(result.differences), 0)

    def test_memory_efficiency_with_deep_nesting(self):
        """Test memory efficiency with deeply nested schema structures."""
        # Create schema with deep nesting
        nested_schema = ModelSchema(
            tables={
                "complex_table": {
                    "columns": {
                        f"nested_col_{i}": {
                            "type": "JSON",
                            "nullable": True,
                            "nested_structure": {
                                "level_1": {
                                    f"field_{j}": {
                                        "type": "VARCHAR(100)",
                                        "nested_level": 2,
                                    }
                                    for j in range(10)
                                }
                            },
                        }
                        for i in range(25)
                    }
                }
            },
            schema_id="nested_schema_test",
        )

        # Generate fingerprint (should handle nesting gracefully)
        fingerprint = self.comparator.generate_schema_fingerprint(nested_schema)

        # Verify fingerprint generation completes
        self.assertIsInstance(fingerprint, str)
        self.assertGreater(len(fingerprint), 0)

    def test_error_handling_in_comparison(self):
        """Test error handling during schema comparison."""
        # Create malformed schema that might cause errors
        malformed_schema = ModelSchema(
            tables={"bad_table": None},  # Malformed table definition
            schema_id="malformed_test",
        )

        normal_schema = DatabaseSchema(
            tables={
                "users": {"columns": {"id": {"type": "INTEGER", "nullable": False}}}
            },
            schema_id="normal_test",
        )

        # Execute - should handle errors gracefully
        result = self.comparator.compare_schemas_optimized(
            malformed_schema, normal_schema
        )

        # Verify error handling
        self.assertIsNotNone(result)
        # Should either succeed with graceful handling or mark as different due to error
        self.assertIsInstance(result.comparison_time_ms, (int, float))

    def test_concurrent_fingerprint_generation(self):
        """Test fingerprint generation under concurrent access."""
        import concurrent.futures
        import threading

        schema = ModelSchema(
            tables={
                "users": {"columns": {"id": {"type": "INTEGER", "nullable": False}}}
            },
            schema_id="concurrent_test",
        )

        def generate_fingerprint():
            return self.comparator.generate_schema_fingerprint(schema)

        # Execute concurrent fingerprint generation
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(generate_fingerprint) for _ in range(10)]
            results = [
                future.result() for future in concurrent.futures.as_completed(futures)
            ]

        # Verify all results are consistent
        first_result = results[0]
        for result in results[1:]:
            self.assertEqual(result, first_result)

    def test_schema_comparison_boundary_conditions(self):
        """Test schema comparison with boundary conditions."""
        # Empty schema
        empty_schema = ModelSchema(tables={}, schema_id="empty")

        # Single table schema
        single_schema = DatabaseSchema(
            tables={
                "only_table": {
                    "columns": {"id": {"type": "INTEGER", "nullable": False}}
                }
            },
            schema_id="single",
        )

        # Compare empty with single
        result = self.comparator.compare_schemas_optimized(empty_schema, single_schema)

        # Verify boundary condition handling
        self.assertTrue(result.schemas_differ)
        self.assertGreater(len(result.differences), 0)

        # Check for expected difference type
        extra_table_diffs = [
            d for d in result.differences if d.get("type") == "extra_table"
        ]
        self.assertGreater(len(extra_table_diffs), 0)

    def test_fingerprint_collision_resistance(self):
        """Test that fingerprint generation is collision-resistant."""
        # Create very similar schemas that should have different fingerprints
        schema1 = ModelSchema(
            tables={
                "users": {
                    "columns": {"name": {"type": "VARCHAR(254)", "nullable": False}}
                }
            },
            schema_id="collision_test_1",
        )

        schema2 = ModelSchema(
            tables={
                "users": {
                    "columns": {"name": {"type": "VARCHAR(255)", "nullable": False}}
                }
            },
            schema_id="collision_test_2",
        )

        fingerprint1 = self.comparator.generate_schema_fingerprint(schema1)
        fingerprint2 = self.comparator.generate_schema_fingerprint(schema2)

        # Verify different schemas produce different fingerprints
        self.assertNotEqual(fingerprint1, fingerprint2)

        # Verify fingerprints have reasonable length (collision resistance)
        self.assertGreaterEqual(
            len(fingerprint1), 16
        )  # At least 16 chars for reasonable collision resistance
        self.assertGreaterEqual(len(fingerprint2), 16)


if __name__ == "__main__":
    unittest.main()
