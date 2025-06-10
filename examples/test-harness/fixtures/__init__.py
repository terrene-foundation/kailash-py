"""Test fixtures for Kailash SDK feature tests."""

import json
from pathlib import Path

import pandas as pd


def get_fixture_path() -> Path:
    """Get path to fixtures directory."""
    return Path(__file__).parent


def get_test_csv(name: str) -> pd.DataFrame:
    """Get a standard test CSV file."""
    csv_files = {
        "customers": {
            "columns": ["id", "name", "age", "city", "status"],
            "data": [
                [1, "Alice", 30, "New York", "active"],
                [2, "Bob", 25, "San Francisco", "active"],
                [3, "Charlie", 35, "Chicago", "inactive"],
                [4, "David", 28, "Boston", "active"],
                [5, "Eve", 32, "Seattle", "active"],
            ],
        },
        "transactions": {
            "columns": ["id", "customer_id", "amount", "date", "category"],
            "data": [
                [1, 1, 100.50, "2024-01-01", "electronics"],
                [2, 1, 50.25, "2024-01-02", "groceries"],
                [3, 2, 200.00, "2024-01-01", "clothing"],
                [4, 3, 75.80, "2024-01-03", "electronics"],
                [5, 4, 125.00, "2024-01-02", "furniture"],
            ],
        },
    }

    if name not in csv_files:
        raise ValueError(
            f"Unknown test CSV: {name}. Available: {list(csv_files.keys())}"
        )

    spec = csv_files[name]
    return pd.DataFrame(spec["data"], columns=spec["columns"])


def get_test_json(name: str) -> dict:
    """Get a standard test JSON object."""
    json_objects = {
        "config": {
            "api_key": "test-key-123",
            "timeout": 30,
            "retry_count": 3,
            "features": {"cache": True, "logging": True, "monitoring": False},
        },
        "api_response": {
            "status": 200,
            "data": {
                "items": [
                    {"id": 1, "name": "Item 1", "price": 10.99},
                    {"id": 2, "name": "Item 2", "price": 20.50},
                ],
                "total": 2,
                "page": 1,
            },
        },
    }

    if name not in json_objects:
        raise ValueError(
            f"Unknown test JSON: {name}. Available: {list(json_objects.keys())}"
        )

    return json_objects[name]


def get_test_config(workflow_type: str) -> dict:
    """Get test configuration for different workflow types."""
    configs = {
        "basic_workflow": {
            "runtime": {"type": "local", "debug": True, "timeout": 60},
            "tracking": {"enabled": True, "storage": "memory"},
        },
        "cyclic_workflow": {
            "runtime": {"type": "local", "debug": True, "timeout": 300},
            "cycle": {"max_iterations": 10, "convergence_threshold": 0.01},
        },
    }

    return configs.get(workflow_type, configs["basic_workflow"])
