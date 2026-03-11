"""
Shared fixtures and configuration for performance benchmarks.
"""

import pytest


def pytest_configure(config):
    """Configure pytest for benchmarks."""
    config.addinivalue_line(
        "markers", "benchmark: mark test as a performance benchmark"
    )


def pytest_benchmark_update_json(config, benchmarks, output_json):
    """
    Add custom metadata to benchmark JSON output.

    This hook is called by pytest-benchmark to allow customization
    of the JSON output.
    """
    output_json["environment_info"] = {
        "test_mode": "in_memory",
        "mocking_policy": "NO_MOCKING",
        "isolation": "InMemoryStores",
    }


def pytest_benchmark_generate_json(config, benchmarks, include_data):
    """
    Generate custom benchmark report data.

    This hook allows adding custom data to the benchmark report.
    """
    # Add performance targets to each benchmark group
    targets = {
        "establish": {"p95_ms": 100, "description": "Agent establishment"},
        "delegate": {"p95_ms": 50, "description": "Trust delegation"},
        "verify": {
            "quick_p95_ms": 5,
            "standard_p95_ms": 50,
            "full_p95_ms": 100,
            "description": "Trust verification",
        },
        "audit": {"p95_ms": 20, "description": "Audit recording"},
        "cache": {
            "hit_mean_ms": 1,
            "hit_rate_target": 0.85,
            "description": "Cache performance",
        },
    }

    return {"performance_targets": targets}
