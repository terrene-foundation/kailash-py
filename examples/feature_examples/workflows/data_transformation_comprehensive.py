#!/usr/bin/env python3
"""
Comprehensive Data Transformation Example

This example demonstrates various data transformation capabilities:
1. Data cleaning and validation
2. Feature engineering
3. Data aggregation
4. Custom transformations with Python nodes
5. Data quality checks

Shows how to build robust data transformation pipelines.
"""

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from examples.utils.data_paths import get_central_data_dir
from examples.utils.paths import get_data_dir, get_output_dir

# Add the parent directory to the path to import kailash
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import CSVWriterNode, JSONWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow
from kailash.workflow.visualization import WorkflowVisualizer


def create_data_cleaner():
    """Create a node that cleans and validates data."""

    def clean_data(data: list) -> dict[str, Any]:
        """Clean and validate customer data."""
        df = pd.DataFrame(data)
        initial_count = len(df)

        # Remove duplicates
        df = df.drop_duplicates(subset=["customer_id"])
        duplicates_removed = initial_count - len(df)

        # Handle missing values
        numeric_columns = ["age", "income", "purchase_count"]
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                df[col].fillna(df[col].median(), inplace=True)

        # Validate age
        if "age" in df.columns:
            invalid_age = df[(df["age"] < 0) | (df["age"] > 120)]
            df = df[(df["age"] >= 0) & (df["age"] <= 120)]
            invalid_age_count = len(invalid_age)
        else:
            invalid_age_count = 0

        # Standardize text columns
        text_columns = ["email", "name"]
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].str.strip().str.lower()

        # Create validation report
        report = {
            "initial_count": initial_count,
            "final_count": len(df),
            "duplicates_removed": duplicates_removed,
            "invalid_age_removed": invalid_age_count,
            "missing_values_filled": df.isnull().sum().to_dict(),
        }

        return {"result": {"data": df.to_dict(orient="records"), "cleaning_report": report}}

    input_schema = {
        "data": NodeParameter(
            name="data", type=list, required=True, description="Raw customer data"
        )
    }

    output_schema = {
        "result": NodeParameter(
            name="result", type=dict, required=True, description="Cleaned data and report"
        )
    }

    return PythonCodeNode.from_function(
        func=clean_data,
        name="data_cleaner",
        description="Clean and validate customer data",
        input_schema=input_schema,
        output_schema=output_schema,
    )


def create_feature_engineer():
    """Create a node that engineers new features."""

    def engineer_features(data: list) -> dict[str, Any]:
        """Create new features from existing data."""
        df = pd.DataFrame(data)

        # Calculate customer lifetime value (simplified)
        if all(col in df.columns for col in ["purchase_count", "avg_purchase_value"]):
            # Convert to numeric first
            purchase_count = pd.to_numeric(df["purchase_count"], errors="coerce")
            avg_value = pd.to_numeric(df["avg_purchase_value"], errors="coerce")
            df["estimated_clv"] = purchase_count * avg_value

        # Age groups
        if "age" in df.columns:
            # Convert to numeric first
            age_numeric = pd.to_numeric(df["age"], errors="coerce")
            df["age_group"] = pd.cut(
                age_numeric,
                bins=[0, 25, 35, 50, 65, 100],
                labels=["18-25", "26-35", "36-50", "51-65", "65+"],
            )

        # Income categories
        if "income" in df.columns:
            # Convert to numeric first
            income_numeric = pd.to_numeric(df["income"], errors="coerce")
            df["income_category"] = pd.cut(
                income_numeric,
                bins=[0, 30000, 60000, 100000, float("inf")],
                labels=["Low", "Medium", "High", "Very High"],
            )

        # Customer value segments
        if "estimated_clv" in df.columns:
            # Convert to numeric first
            clv_numeric = pd.to_numeric(df["estimated_clv"], errors="coerce")
            df["value_segment"] = pd.qcut(
                clv_numeric,
                q=[0, 0.25, 0.75, 1.0],
                labels=["Low Value", "Medium Value", "High Value"],
            )

        # Email domain
        if "email" in df.columns:
            df["email_domain"] = df["email"].str.split("@").str[1]

        # Activity status based on last purchase
        if "days_since_last_purchase" in df.columns:
            # Convert to numeric first
            days_numeric = pd.to_numeric(
                df["days_since_last_purchase"], errors="coerce"
            )
            df["activity_status"] = days_numeric.apply(
                lambda x: (
                    "Active"
                    if pd.notna(x) and x < 30
                    else "Inactive" if pd.notna(x) and x < 90 else "Churned"
                )
            )

        # Feature summary
        new_features = [col for col in df.columns if col not in data[0].keys()]

        return {
            "result": {
                "data": df.to_dict(orient="records"),
                "new_features": new_features,
                "feature_count": len(new_features),
            }
        }

    input_schema = {
        "data": NodeParameter(
            name="data", type=list, required=True, description="Cleaned customer data"
        )
    }

    output_schema = {
        "result": NodeParameter(
            name="result",
            type=dict,
            required=True,
            description="Data with engineered features",
        )
    }

    return PythonCodeNode.from_function(
        func=engineer_features,
        name="feature_engineer",
        description="Engineer new features from existing data",
        input_schema=input_schema,
        output_schema=output_schema,
    )


def create_data_aggregator():
    """Create a node that aggregates data by groups."""

    def aggregate_data(data: list, group_by: list, metrics: dict) -> dict[str, Any]:
        """Aggregate data by specified groups and metrics."""
        df = pd.DataFrame(data)

        # Perform aggregation
        aggregated = df.groupby(group_by).agg(metrics)

        # Flatten column names
        aggregated.columns = [
            "_".join(col).strip() for col in aggregated.columns.values
        ]
        aggregated = aggregated.reset_index()

        # Calculate summary statistics
        summary_stats = {}
        for col in aggregated.columns:
            if aggregated[col].dtype in ["float64", "int64"]:
                summary_stats[col] = {
                    "mean": float(aggregated[col].mean()),
                    "std": float(aggregated[col].std()),
                    "min": float(aggregated[col].min()),
                    "max": float(aggregated[col].max()),
                }

        return {
            "result": {
                "data": aggregated.to_dict(orient="records"),
                "row_count": len(aggregated),
                "group_count": len(aggregated),
                "summary_stats": summary_stats,
            }
        }

    input_schema = {
        "data": NodeParameter(
            name="data", type=list, required=True, description="Data to aggregate"
        ),
        "group_by": NodeParameter(
            name="group_by", type=list, required=True, description="Columns to group by"
        ),
        "metrics": NodeParameter(
            name="metrics", type=dict, required=True, description="Aggregation metrics"
        ),
    }

    output_schema = {
        "result": NodeParameter(
            name="result", type=dict, required=True, description="Aggregated data and stats"
        )
    }

    return PythonCodeNode.from_function(
        func=aggregate_data,
        name="data_aggregator",
        description="Aggregate data by groups",
        input_schema=input_schema,
        output_schema=output_schema,
    )


def create_quality_checker():
    """Create a node that checks data quality."""

    def check_quality(data: list) -> dict[str, Any]:
        """Check data quality and generate report."""
        df = pd.DataFrame(data)

        # Quality metrics
        total_rows = len(df)

        # Completeness - check for missing values
        missing_counts = df.isnull().sum()
        completeness = {}
        for col in df.columns:
            completeness[col] = 1 - (missing_counts[col] / total_rows)

        overall_completeness = np.mean(list(completeness.values()))

        # Uniqueness - check for duplicates
        duplicate_count = df.duplicated().sum()
        uniqueness_rate = 1 - (duplicate_count / total_rows)

        # Consistency checks
        consistency_issues = []

        # Check age consistency
        if "age" in df.columns:
            invalid_age = len(df[(df["age"] < 0) | (df["age"] > 120)])
            if invalid_age > 0:
                consistency_issues.append(f"{invalid_age} invalid age values")

        # Check income consistency
        if "income" in df.columns:
            negative_income = len(df[df["income"] < 0])
            if negative_income > 0:
                consistency_issues.append(f"{negative_income} negative income values")

        # Data type validation
        type_issues = []
        numeric_columns = ["age", "income", "purchase_count"]
        for col in numeric_columns:
            if col in df.columns:
                non_numeric = (
                    df[col].apply(lambda x: not isinstance(x, (int, float))).sum()
                )
                if non_numeric > 0:
                    type_issues.append(f"{col}: {non_numeric} non-numeric values")

        # Generate quality report
        quality_report = {
            "total_rows": total_rows,
            "overall_completeness": float(overall_completeness),
            "column_completeness": {k: float(v) for k, v in completeness.items()},
            "uniqueness_rate": float(uniqueness_rate),
            "duplicate_count": int(duplicate_count),
            "consistency_issues": consistency_issues,
            "type_issues": type_issues,
            "quality_score": float(overall_completeness * uniqueness_rate),
        }

        return {
            "result": {
                "data": df.to_dict(orient="records"),
                "quality_report": quality_report,
                "is_high_quality": quality_report["quality_score"] > 0.9,
            }
        }

    input_schema = {
        "data": NodeParameter(
            name="data", type=list, required=True, description="Data to check quality"
        )
    }

    output_schema = {
        "result": NodeParameter(
            name="result", type=dict, required=True, description="Data and quality report"
        )
    }

    return PythonCodeNode.from_function(
        func=check_quality,
        name="quality_checker",
        description="Check data quality",
        input_schema=input_schema,
        output_schema=output_schema,
    )


def create_transformation_pipeline():
    """Create a complete data transformation pipeline."""

    print("Building data transformation pipeline...")

    # Create workflow
    workflow = Workflow(
        workflow_id="data_transformation_pipeline",
        name="data_transformation_pipeline",
        description="Complete data transformation workflow",
    )

    # Create nodes
    reader = CSVReaderNode(
        file_path=str(get_data_dir() / "raw_customers.csv"), headers=True
    )

    cleaner = create_data_cleaner()
    feature_engineer = create_feature_engineer()
    aggregator = create_data_aggregator()
    quality_checker = create_quality_checker()

    # Writers for different outputs
    cleaned_writer = CSVWriterNode(
        file_path=str(get_output_dir() / "cleaned_customers.csv")
    )

    features_writer = CSVWriterNode(
        file_path=str(get_output_dir() / "customers_with_features.csv")
    )

    aggregated_writer = CSVWriterNode(
        file_path=str(get_output_dir() / "customer_segments.csv")
    )

    quality_report_writer = JSONWriterNode(
        file_path=str(get_output_dir() / "quality_report.json")
    )

    # Add nodes to workflow
    workflow.add_node(node_id="reader", node_or_type=reader)
    workflow.add_node(node_id="cleaner", node_or_type=cleaner)
    workflow.add_node(node_id="feature_engineer", node_or_type=feature_engineer)
    workflow.add_node(
        node_id="aggregator",
        node_or_type=aggregator,
        config={
            "group_by": ["age_group", "income_category"],
            "metrics": {
                "purchase_count": ["mean", "sum"],
                "estimated_clv": ["mean", "max"],
            },
        },
    )
    workflow.add_node(node_id="quality_checker", node_or_type=quality_checker)
    workflow.add_node(node_id="cleaned_writer", node_or_type=cleaned_writer)
    workflow.add_node(node_id="features_writer", node_or_type=features_writer)
    workflow.add_node(node_id="aggregated_writer", node_or_type=aggregated_writer)
    workflow.add_node(
        node_id="quality_report_writer", node_or_type=quality_report_writer
    )

    # Connect nodes with proper parameter mapping
    workflow.connect("reader", "cleaner", {"data": "data"})
    workflow.connect("cleaner", "feature_engineer", {"result": "data"})
    workflow.connect("feature_engineer", "aggregator", {"result": "data"})
    workflow.connect("feature_engineer", "quality_checker", {"result": "data"})

    # Output connections
    workflow.connect("cleaner", "cleaned_writer", {"result": "data"})
    workflow.connect("feature_engineer", "features_writer", {"result": "data"})
    workflow.connect("aggregator", "aggregated_writer", {"result": "data"})
    workflow.connect(
        "quality_checker", "quality_report_writer", {"result": "data"}
    )

    return workflow


def main():
    """Execute data transformation examples."""

    print("=== Kailash Comprehensive Data Transformation Example ===\n")

    # Create sample data
    data_dir = get_data_dir()
    data_dir.mkdir(exist_ok=True)
    output_dir = get_output_dir()
    output_dir.mkdir(exist_ok=True)

    # Generate sample customer data
    sample_file = data_dir / "raw_customers.csv"
    if not sample_file.exists():
        print("Creating sample customer data...")
        np.random.seed(42)

        sample_data = pd.DataFrame(
            {
                "customer_id": [f"CUST{i:04d}" for i in range(100)],
                "name": [f"Customer {i}" for i in range(100)],
                "email": [f"customer{i}@example.com" for i in range(100)],
                "age": np.random.randint(18, 80, 100),
                "income": np.random.normal(60000, 25000, 100),
                "purchase_count": np.random.poisson(5, 100),
                "avg_purchase_value": np.random.uniform(50, 500, 100),
                "days_since_last_purchase": np.random.randint(1, 365, 100),
            }
        )

        # Add some missing values and duplicates for testing
        sample_data.loc[10:15, "income"] = np.nan
        sample_data.loc[90:95, "customer_id"] = "CUST0001"  # Duplicates
        sample_data.loc[5, "age"] = -5  # Invalid age
        sample_data.loc[95, "age"] = 150  # Invalid age

        sample_data.to_csv(sample_file, index=False)
        print(f"Created {sample_file}")

    try:
        # Create and run the transformation pipeline
        pipeline = create_transformation_pipeline()

        # Validate pipeline
        print("\nValidating transformation pipeline...")
        pipeline.validate()
        print("✓ Pipeline validation successful!")

        # Visualize pipeline
        print("\nCreating pipeline visualization...")
        try:
            visualizer = WorkflowVisualizer()
            visualizer.visualize(
                pipeline, output_path=str(output_dir / "transformation_pipeline.png")
            )
            print(
                f"✓ Visualization saved to {output_dir / 'transformation_pipeline.png'}"
            )
        except Exception as e:
            print(f"Warning: Could not create visualization: {e}")

        # Run pipeline
        print("\nExecuting transformation pipeline...")
        runner = LocalRuntime()
        results, run_id = runner.execute(pipeline)

        print("\n✓ Transformation pipeline completed!")
        print(f"  Run ID: {run_id}")
        print(f"  Nodes executed: {len(results)}")

        # Show transformation results
        print("\nTransformation Results:")
        for node_id, output in results.items():
            print(f"\n{node_id}:")
            if isinstance(output, dict):
                for key, value in output.items():
                    if key == "result" and isinstance(value, dict):
                        for result_key, result_value in value.items():
                            if result_key == "data" and isinstance(result_value, list):
                                print(f"  {result_key}: {len(result_value)} records")
                            elif result_key == "cleaning_report":
                                print("  Cleaning Report:")
                                print(
                                    f"    Duplicates removed: {result_value.get('duplicates_removed', 0)}"
                                )
                                print(
                                    f"    Invalid ages removed: {result_value.get('invalid_age_removed', 0)}"
                                )
                            elif result_key == "quality_report":
                                print("  Quality Report:")
                                print(
                                    f"    Overall completeness: {result_value.get('overall_completeness', 0):.2%}"
                                )
                                print(
                                    f"    Uniqueness rate: {result_value.get('uniqueness_rate', 0):.2%}"
                                )
                                print(f"    Quality score: {result_value.get('quality_score', 0):.2%}")
                            elif result_key == "new_features":
                                print(f"  New features created: {result_value}")
                            else:
                                print(f"  {result_key}: {result_value}")
                    else:
                        print(f"  {key}: {value}")

        print(f"\n✓ All outputs written to {output_dir}/")

    except Exception as e:
        print(f"\n✗ Transformation failed: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())