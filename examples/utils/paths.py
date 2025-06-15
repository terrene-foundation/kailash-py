"""
Path utilities for examples to handle data and output directories correctly.

This module provides helper functions to get proper paths that work with
the SDK's security restrictions.
"""

import os
import tempfile
from pathlib import Path


def get_data_dir():
    """
    Get the data directory path.

    Returns absolute path to the centralized /data directory if accessible,
    otherwise returns a temporary directory.
    """
    # Try to use the centralized data directory
    project_root = Path(
        __file__
    ).parent.parent.parent  # Go up from utils to examples to project root
    data_dir = project_root / "data" / "inputs"

    # Check if we can access it (when running from project root)
    if data_dir.exists() and os.access(data_dir, os.R_OK):
        return data_dir

    # Otherwise use temp directory
    temp_dir = Path(tempfile.gettempdir()) / "kailash_examples" / "data"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # Copy essential data files if needed
    _ensure_data_files(temp_dir)

    return temp_dir


def get_output_dir():
    """
    Get the output directory path.

    Returns absolute path to the centralized /data/outputs directory if accessible,
    otherwise returns a temporary directory.
    """
    # Output should be in centralized data/outputs
    project_root = Path(__file__).parent.parent.parent  # Go up to project root
    output_dir = project_root / "data" / "outputs" / "csv"

    # Create directory if it doesn't exist and we have write access
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        if os.access(output_dir, os.W_OK):
            return output_dir
    except (OSError, PermissionError):
        pass

    # Otherwise use temp directory
    temp_dir = Path(tempfile.gettempdir()) / "kailash_examples" / "data" / "outputs"
    temp_dir.mkdir(parents=True, exist_ok=True)

    return temp_dir


def _ensure_data_files(temp_data_dir):
    """
    Ensure essential data files exist in the temporary directory.

    This creates minimal sample data files if they don't exist.
    """
    # Create sample customers.csv if needed
    customers_file = temp_data_dir / "customers.csv"
    if not customers_file.exists():
        import pandas as pd

        customers_data = pd.DataFrame(
            {
                "customer_id": range(1, 6),
                "name": [
                    "Alice Smith",
                    "Bob Johnson",
                    "Carol Williams",
                    "David Brown",
                    "Eve Davis",
                ],
                "age": [25, 30, 35, 40, 45],
                "city": ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"],
                "total_purchases": [1500, 2300, 1800, 3200, 2100],
            }
        )
        customers_data.to_csv(customers_file, index=False)

    # Create sample customer_value.csv if needed
    customer_value_file = temp_data_dir / "customer_value.csv"
    if not customer_value_file.exists():

        value_data = pd.DataFrame(
            {
                "Customer": ["A001", "A002", "A003", "A004", "A005"],
                "Total Claim Amount": [1234.56, 2345.67, 3456.78, 4567.89, 5678.90],
                "Customer Lifetime Value": [5000, 7500, 10000, 12500, 15000],
                "Coverage Type": ["Basic", "Premium", "Basic", "Premium", "Premium"],
            }
        )
        value_data.to_csv(customer_value_file, index=False)

    # Create sample transactions.json if needed
    transactions_file = temp_data_dir / "transactions.json"
    if not transactions_file.exists():
        import json

        transactions = {
            "transactions": [
                {"id": 1, "customer_id": 1, "amount": 150.00, "date": "2024-01-15"},
                {"id": 2, "customer_id": 2, "amount": 230.00, "date": "2024-01-16"},
                {"id": 3, "customer_id": 3, "amount": 180.00, "date": "2024-01-17"},
                {"id": 4, "customer_id": 4, "amount": 320.00, "date": "2024-01-18"},
                {"id": 5, "customer_id": 5, "amount": 210.00, "date": "2024-01-19"},
            ]
        }

        with open(transactions_file, "w") as f:
            json.dump(transactions, f, indent=2)

    # Create sample_reviews.csv if needed
    reviews_file = temp_data_dir / "sample_reviews.csv"
    if not reviews_file.exists():

        reviews_data = pd.DataFrame(
            {
                "review_id": range(1, 6),
                "product": ["Widget A", "Widget B", "Widget A", "Widget C", "Widget B"],
                "rating": [5, 4, 3, 5, 2],
                "review_text": [
                    "Excellent product! Highly recommended.",
                    "Good quality, but a bit pricey.",
                    "Average product, nothing special.",
                    "Amazing! Exceeded my expectations.",
                    "Disappointed. Poor quality.",
                ],
            }
        )
        reviews_data.to_csv(reviews_file, index=False)


def ensure_example_directories():
    """
    Ensure all required directories exist for examples.

    Returns tuple of (data_dir, output_dir) paths.
    """
    data_dir = get_data_dir()
    output_dir = get_output_dir()

    return data_dir, output_dir
