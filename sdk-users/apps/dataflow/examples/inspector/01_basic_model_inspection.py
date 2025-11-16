"""
Basic Model Inspection Example

This example demonstrates how to use Inspector to examine DataFlow models.

Run this example:
    python sdk-users/apps/dataflow/examples/inspector/01_basic_model_inspection.py
"""

from typing import Optional

from dataflow import DataFlow
from dataflow.platform.inspector import Inspector


def main():
    print("=" * 60)
    print("Inspector Example 1: Basic Model Inspection")
    print("=" * 60)
    print()

    # Create in-memory DataFlow instance
    db = DataFlow(":memory:")

    # Define models
    @db.model
    class User:
        id: str
        name: str
        email: str
        age: Optional[int] = None

    @db.model
    class Order:
        id: str
        user_id: str  # Foreign key (detected by _id suffix)
        total: float
        status: str

    # Create Inspector
    inspector = Inspector(db)

    # 1. Inspect User model
    print("1. User Model Inspection")
    print("-" * 60)
    user_model = inspector.model("User")
    print(user_model.show())
    print()

    # 2. Inspect Order model
    print("2. Order Model Inspection")
    print("-" * 60)
    order_model = inspector.model("Order")
    print(order_model.show())
    print()

    # 3. Get validation rules
    print("3. Order Validation Rules")
    print("-" * 60)
    validation_rules = inspector.model_validation_rules("Order")
    print(validation_rules.show())
    print()

    # 4. Compare model schemas
    print("4. Schema Comparison (User vs Order)")
    print("-" * 60)
    schema_diff = inspector.model_schema_diff("User", "Order")
    print(schema_diff.show())
    print()

    print("=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
