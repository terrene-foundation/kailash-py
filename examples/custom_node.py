#!/usr/bin/env python3
"""
Custom Node Example

This example demonstrates how to create custom nodes by:
1. Extending the base Node class
2. Implementing required methods
3. Adding custom configuration
4. Handling different data types
5. Implementing validation logic
6. Adding custom error handling
7. Creating reusable node templates

Shows best practices for extending the Kailash SDK.
"""

import sys
import json
import pandas as pd
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

# Add the parent directory to the path to import kailash
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kailash.nodes.base import Node, NodeParameter, NodeMetadata
from kailash.sdk_exceptions import NodeValidationError, NodeExecutionError, NodeConfigurationError
from kailash.workflow.graph import Workflow
from kailash.runtime.local import LocalRuntime


class SentimentAnalyzerNode(Node):
    """
    Custom node that performs sentiment analysis on text data.
    
    This example shows how to create a custom AI/ML node that:
    - Validates input data
    - Processes text using an ML model
    - Outputs structured results
    - Handles errors gracefully
    """
    
    def __init__(self, **kwargs):
        """Initialize the sentiment analyzer node."""
        # Create metadata for this node
        metadata = NodeMetadata(
            id="sentiment_analyzer",
            name="Sentiment Analyzer",
            description="Analyzes sentiment of text data",
            version="1.0.0",
            tags={"nlp", "sentiment", "analysis"}
        )
        
        # Initialize with parent class
        super().__init__(metadata=metadata, **kwargs)
        
        # Initialize model (mock for example)
        self.model = None
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="List of text data to analyze"
            ),
            "model": NodeParameter(
                name="model",
                type=str,
                required=False,
                default="vader",
                description="Model to use for sentiment analysis"
            ),
            "batch_size": NodeParameter(
                name="batch_size",
                type=int,
                required=False,
                default=100,
                description="Batch size for processing"
            ),
            "include_scores": NodeParameter(
                name="include_scores",
                type=bool,
                required=False,
                default=True,
                description="Whether to include detailed scores"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute sentiment analysis."""
        data = kwargs["data"]
        model = kwargs.get("model", "vader")
        batch_size = kwargs.get("batch_size", 100)
        include_scores = kwargs.get("include_scores", True)
        
        # Convert to DataFrame if needed
        if isinstance(data, list) and data and isinstance(data[0], dict):
            df = pd.DataFrame(data)
        else:
            df = pd.DataFrame({"text": data})
        
        # Ensure we have a text column
        if "text" not in df.columns:
            raise NodeExecutionError("Input data must have a 'text' column or be a list of strings")
        
        # Process in batches
        results = []
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i + batch_size]
            batch_results = self._analyze_batch(batch["text"].tolist())
            results.extend(batch_results)
        
        # Add results to dataframe
        df["sentiment"] = [r["sentiment"] for r in results]
        if include_scores:
            df["sentiment_score"] = [r["score"] for r in results]
            df["confidence"] = [r["confidence"] for r in results]
        
        return {"data": df.to_dict(orient='records')}
    
    def _analyze_batch(self, texts: List[str]) -> List[Dict]:
        """Analyze a batch of texts (mock implementation)."""
        # In a real implementation, this would call an actual ML model
        import random
        
        results = []
        for text in texts:
            # Mock sentiment analysis
            score = random.uniform(-1, 1)
            sentiment = "positive" if score > 0.1 else "negative" if score < -0.1 else "neutral"
            confidence = abs(score)
            
            results.append({
                "text": text,
                "sentiment": sentiment,
                "score": score,
                "confidence": confidence
            })
        
        return results


class DataValidatorNode(Node):
    """
    Custom node for comprehensive data validation.
    
    Shows how to create a node that:
    - Performs complex validation rules
    - Generates detailed validation reports
    - Supports custom validation functions
    - Handles multiple data formats
    """
    
    def __init__(self, **kwargs):
        """Initialize the data validator node."""
        metadata = NodeMetadata(
            id="data_validator",
            name="Data Validator",
            description="Validates data against configurable rules",
            version="1.0.0",
            tags={"validation", "quality", "data"}
        )
        super().__init__(metadata=metadata, **kwargs)
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Data to validate"
            ),
            "rules": NodeParameter(
                name="rules",
                type=list,
                required=True,
                description="Validation rules to apply"
            ),
            "fail_on_error": NodeParameter(
                name="fail_on_error",
                type=bool,
                required=False,
                default=True,
                description="Whether to fail on validation errors"
            ),
            "generate_report": NodeParameter(
                name="generate_report",
                type=bool,
                required=False,
                default=True,
                description="Whether to generate validation report"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute data validation."""
        data = kwargs["data"]
        rules = kwargs["rules"]
        fail_on_error = kwargs.get("fail_on_error", True)
        generate_report = kwargs.get("generate_report", True)
        
        # Convert to DataFrame for easier validation
        df = pd.DataFrame(data)
        
        # Initialize validation report
        report = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "statistics": {
                "total_records": len(df),
                "valid_records": len(df),
                "invalid_records": 0
            }
        }
        
        # Run validation rules
        for rule in rules:
            self._apply_rule(df, rule, report)
        
        # Calculate statistics
        report["statistics"]["invalid_records"] = len(report["errors"])
        report["statistics"]["valid_records"] = report["statistics"]["total_records"] - report["statistics"]["invalid_records"]
        
        # Handle validation results
        if not report["valid"] and fail_on_error:
            raise NodeValidationError(f"Data validation failed: {report['errors']}")
        
        # Return data with validation report
        if generate_report:
            return {
                "data": df.to_dict(orient='records'),
                "validation_report": report
            }
        else:
            return {"data": df.to_dict(orient='records')}
    
    def _apply_rule(self, df: pd.DataFrame, rule: Dict, report: Dict):
        """Apply a single validation rule."""
        rule_type = rule.get("type")
        
        if rule_type == "required":
            self._check_required(df, rule, report)
        elif rule_type == "type":
            self._check_type(df, rule, report)
        elif rule_type == "range":
            self._check_range(df, rule, report)
        elif rule_type == "pattern":
            self._check_pattern(df, rule, report)
    
    def _check_required(self, df: pd.DataFrame, rule: Dict, report: Dict):
        """Check if required fields are present."""
        required_columns = rule.get("columns", [])
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            report["valid"] = False
            report["errors"].append(f"Missing required columns: {missing}")
    
    def _check_type(self, df: pd.DataFrame, rule: Dict, report: Dict):
        """Check data types."""
        for column, expected_type in rule.get("columns", {}).items():
            if column in df.columns:
                actual_type = str(df[column].dtype)
                if not self._compatible_types(actual_type, expected_type):
                    report["warnings"].append(
                        f"Column '{column}' has type '{actual_type}', expected '{expected_type}'"
                    )
    
    def _check_range(self, df: pd.DataFrame, rule: Dict, report: Dict):
        """Check numeric ranges."""
        for column, range_spec in rule.get("columns", {}).items():
            if column in df.columns:
                min_val = range_spec.get("min")
                max_val = range_spec.get("max")
                
                if min_val is not None:
                    violations = df[df[column] < min_val]
                    if not violations.empty:
                        report["errors"].append(
                            f"Column '{column}' has {len(violations)} values below minimum {min_val}"
                        )
                
                if max_val is not None:
                    violations = df[df[column] > max_val]
                    if not violations.empty:
                        report["errors"].append(
                            f"Column '{column}' has {len(violations)} values above maximum {max_val}"
                        )
    
    def _check_pattern(self, df: pd.DataFrame, rule: Dict, report: Dict):
        """Check regex patterns."""
        import re
        
        for column, pattern in rule.get("columns", {}).items():
            if column in df.columns:
                regex = re.compile(pattern)
                invalid = df[~df[column].astype(str).str.match(regex)]
                if not invalid.empty:
                    report["errors"].append(
                        f"Column '{column}' has {len(invalid)} values not matching pattern '{pattern}'"
                    )
    
    def _compatible_types(self, actual: str, expected: str) -> bool:
        """Check if types are compatible."""
        type_map = {
            "integer": ["int32", "int64", "Int32", "Int64"],
            "float": ["float32", "float64", "Float32", "Float64"],
            "string": ["object", "string"],
            "datetime": ["datetime64", "datetime64[ns]"]
        }
        
        if expected in type_map:
            return actual in type_map[expected]
        return actual == expected


class CustomAggregatorNode(Node):
    """
    Custom node that performs configurable data aggregation.
    
    This example shows how to create a node that:
    - Accepts flexible configuration
    - Performs various aggregation operations
    - Handles multiple data types
    - Provides detailed output
    """
    
    def __init__(self, **kwargs):
        """Initialize the aggregator node."""
        metadata = NodeMetadata(
            id="custom_aggregator",
            name="Custom Aggregator",
            description="Performs configurable data aggregation",
            version="1.0.0",
            tags={"aggregation", "statistics", "transform"}
        )
        super().__init__(metadata=metadata, **kwargs)
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Data to aggregate"
            ),
            "group_by": NodeParameter(
                name="group_by",
                type=list,
                required=False,
                default=[],
                description="Columns to group by"
            ),
            "aggregations": NodeParameter(
                name="aggregations",
                type=dict,
                required=True,
                description="Aggregation operations to perform"
            )
        }
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute aggregation."""
        data = kwargs["data"]
        group_by = kwargs.get("group_by", [])
        aggregations = kwargs["aggregations"]
        
        # Convert to DataFrame
        df = pd.DataFrame(data)
        
        # Perform aggregation
        if group_by:
            # Group and aggregate
            grouped = df.groupby(group_by)
            result = grouped.agg(aggregations)
            
            # Flatten column names
            result.columns = ['_'.join(col).strip() for col in result.columns.values]
            result = result.reset_index()
        else:
            # Aggregate without grouping
            result = pd.DataFrame([df.agg(aggregations)])
            
        return {
            "data": result.to_dict(orient='records'),
            "row_count": len(result),
            "aggregation_summary": {
                "grouped_by": group_by,
                "operations": list(aggregations.keys())
            }
        }


def create_custom_workflow():
    """Create a workflow using custom nodes."""
    
    print("Creating workflow with custom nodes...")
    
    # Create workflow
    workflow = Workflow(
        name="custom_node_workflow",
        description="Demonstrates custom node usage"
    )
    
    # Create instances of custom nodes
    validator = DataValidatorNode()
    sentiment_analyzer = SentimentAnalyzerNode()
    aggregator = CustomAggregatorNode()
    
    # Add nodes to workflow with configurations
    workflow.add_node(
        node_id="validator",
        node_or_type=validator,
        config={
            "rules": [
                {
                    "type": "required",
                    "columns": ["review_id", "text", "rating"]
                },
                {
                    "type": "range",
                    "columns": {
                        "rating": {"min": 1, "max": 5}
                    }
                },
                {
                    "type": "pattern",
                    "columns": {
                        "review_id": "^REV[0-9]{6}$"
                    }
                }
            ],
            "fail_on_error": False,
            "generate_report": True
        }
    )
    
    workflow.add_node(
        node_id="sentiment",
        node_or_type=sentiment_analyzer,
        config={
            "model": "vader",
            "batch_size": 50,
            "include_scores": True
        }
    )
    
    workflow.add_node(
        node_id="aggregator",
        node_or_type=aggregator,
        config={
            "group_by": ["sentiment"],
            "aggregations": {
                "rating": ["mean", "count"],
                "confidence": "mean"
            }
        }
    )
    
    # Connect nodes
    workflow.connect("validator", "sentiment", {"data": "data"})
    workflow.connect("sentiment", "aggregator", {"data": "data"})
    
    return workflow


def main():
    """Execute custom node example."""
    
    print("=== Kailash Custom Node Example ===\n")
    
    # Create sample data
    sample_reviews = [
        {
            "review_id": "REV000001",
            "text": "Great product, highly recommend!",
            "rating": 5
        },
        {
            "review_id": "REV000002",
            "text": "Terrible experience, would not buy again.",
            "rating": 1
        },
        {
            "review_id": "REV000003",
            "text": "It's okay, nothing special but does the job.",
            "rating": 3
        },
        {
            "review_id": "REV000004",
            "text": "Excellent quality and fast shipping!",
            "rating": 5
        },
        {
            "review_id": "REV000005",
            "text": "Product broke after one week.",
            "rating": 1
        }
    ]
    
    # Direct node execution example
    print("Example 1: Direct node execution")
    print("-" * 40)
    
    validator = DataValidatorNode()
    try:
        result = validator.execute(
            data=sample_reviews,
            rules=[
                {"type": "required", "columns": ["review_id", "text", "rating"]},
                {"type": "range", "columns": {"rating": {"min": 1, "max": 5}}}
            ],
            generate_report=True
        )
        
        print(f"Validation passed: {result['validation_report']['valid']}")
        print(f"Errors: {result['validation_report']['errors']}")
        print(f"Warnings: {result['validation_report']['warnings']}")
        print()
    except Exception as e:
        print(f"Validation error: {e}")
    
    # Workflow execution example
    print("\nExample 2: Workflow execution")
    print("-" * 40)
    
    workflow = create_custom_workflow()
    
    # Validate workflow
    print("Validating workflow...")
    try:
        workflow.validate()
        print("✓ Workflow validation successful!")
    except Exception as e:
        print(f"✗ Workflow validation failed: {e}")
        return 1
    
    # Run workflow
    print("\nExecuting workflow...")
    runner = LocalRuntime(debug=True)
    
    try:
        # Create a CSV reader to provide input data
        from kailash.nodes.data.readers import CSVReader
        from kailash.nodes.data.writers import CSVWriter
        
        # Save sample data to CSV
        sample_file = Path("data/sample_reviews.csv")
        sample_file.parent.mkdir(exist_ok=True)
        pd.DataFrame(sample_reviews).to_csv(sample_file, index=False)
        
        # Create reader node
        reader = CSVReader(file_path=str(sample_file), headers=True)
        writer = CSVWriter(file_path="data/sentiment_summary.csv")
        
        # Add to workflow
        workflow.add_node(node_id="reader", node_or_type=reader)
        workflow.add_node(node_id="writer", node_or_type=writer)
        
        # Connect reader to validator and aggregator to writer
        workflow.connect("reader", "validator", {"data": "data"})
        workflow.connect("aggregator", "writer", {"data": "data"})
        
        # Execute workflow
        results, run_id = runner.execute(workflow)
        
        print(f"\n✓ Workflow completed successfully!")
        print(f"  Run ID: {run_id}")
        print(f"  Nodes executed: {len(results)}")
        
        # Show results
        print("\nWorkflow outputs:")
        for node_id, output in results.items():
            print(f"\n{node_id}:")
            if isinstance(output, dict):
                if "data" in output and isinstance(output["data"], list):
                    print(f"  Records processed: {len(output['data'])}")
                    if output["data"]:
                        print(f"  Sample: {output['data'][0]}")
                for key, value in output.items():
                    if key != "data":
                        print(f"  {key}: {value}")
        
    except Exception as e:
        print(f"\n✗ Workflow execution failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())