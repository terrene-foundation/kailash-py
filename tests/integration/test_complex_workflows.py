"""Test complex multi-branch workflows with various node types."""

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from kailash.runtime.local import LocalRuntime
from kailash.tracking.manager import TaskManager
from kailash.workflow import WorkflowBuilder

# Skip all tests in this module - many rely on non-existent node types
pytestmark = pytest.mark.skip(
    reason="Tests rely on non-existent node types like APIDataReader, DataMerger, JSONToDataFrame, etc."
)


class TestComplexWorkflows:
    """Test execution of complex workflows with multiple branches and node types."""

    def test_multi_source_multi_sink_workflow(self, temp_data_dir: Path):
        """Test workflow with multiple data sources and sinks."""
        builder = WorkflowBuilder()

        # Create multiple data sources
        csv_data = temp_data_dir / "source1.csv"
        csv_data.write_text("id,value,category\n1,100,A\n2,200,B\n3,300,A\n")

        json_data = temp_data_dir / "source2.json"
        json_data.write_text(
            json.dumps(
                {
                    "metadata": {"version": "1.0"},
                    "records": [
                        {"id": 1, "score": 0.8},
                        {"id": 2, "score": 0.9},
                        {"id": 3, "score": 0.7},
                    ],
                }
            )
        )

        api_data = {"endpoint": "https://api.example.com/data"}

        # Add data source nodes
        csv_reader_id = builder.add_node(
            "CSVReader", "csv_reader", config={"file_path": str(csv_data)}
        )

        json_reader_id = builder.add_node(
            "JSONReader", "json_reader", config={"file_path": str(json_data)}
        )

        builder.add_node(
            "APIDataReader",
            "api_reader",
            config={
                "endpoint": api_data["endpoint"],
                "mock_response": {"data": [{"id": 1, "external_value": 50}]},
            },
        )

        # Add processing nodes
        json_to_df_id = builder.add_node(
            "JSONToDataFrame", "json_to_df", config={"records_path": "records"}
        )

        merger_id = builder.add_node(
            "DataMerger", "merger", config={"on": "id", "how": "inner"}
        )

        aggregator_id = builder.add_node(
            "DataAggregator",
            "aggregator",
            config={"group_by": ["category"], "agg_func": "mean"},
        )

        # Add AI processing
        ai_analyzer_id = builder.add_node(
            "LLMAnalyzer",
            "ai_analyzer",
            config={
                "prompt": "Analyze this aggregated data and provide insights",
                "mock_response": "Category A has higher average values",
            },
        )

        # Add multiple output nodes
        csv_writer_id = builder.add_node(
            "CSVFileWriter",
            "csv_writer",
            config={"path": str(temp_data_dir / "final_aggregated.csv")},
        )

        excel_writer_id = builder.add_node(
            "ExcelFileWriter",
            "excel_writer",
            config={
                "path": str(temp_data_dir / "report.xlsx"),
                "sheet_name": "Aggregated Data",
            },
        )

        report_writer_id = builder.add_node(
            "ReportGenerator",
            "report_generator",
            config={
                "template": "markdown",
                "output_path": str(temp_data_dir / "report.md"),
            },
        )

        # Connect the workflow
        builder.add_connection(json_reader_id, "data", json_to_df_id, "json_data")
        builder.add_connection(csv_reader_id, "data", merger_id, "left")
        builder.add_connection(json_to_df_id, "dataframe", merger_id, "right")
        builder.add_connection(merger_id, "merged_data", aggregator_id, "data")
        builder.add_connection(aggregator_id, "aggregated_data", ai_analyzer_id, "data")
        builder.add_connection(aggregator_id, "aggregated_data", csv_writer_id, "data")
        builder.add_connection(
            aggregator_id, "aggregated_data", excel_writer_id, "data"
        )
        builder.add_connection(
            aggregator_id, "aggregated_data", report_writer_id, "data"
        )
        builder.add_connection(ai_analyzer_id, "analysis", report_writer_id, "analysis")

        workflow = builder.build("multi_source_multi_sink")

        # Execute workflow
        runner = LocalRuntime()
        runner.run(workflow)

        # Verify outputs exist
        assert (temp_data_dir / "final_aggregated.csv").exists()
        assert (temp_data_dir / "report.xlsx").exists()
        assert (temp_data_dir / "report.md").exists()

        # Verify aggregated data
        final_data = pd.read_csv(temp_data_dir / "final_aggregated.csv")
        assert len(final_data) == 2  # Two categories
        assert "category" in final_data.columns
        assert "value" in final_data.columns

    def test_conditional_branching_workflow(self, temp_data_dir: Path):
        """Test workflow with conditional branching logic."""
        builder = WorkflowBuilder()

        # Create test data
        test_data = temp_data_dir / "test_data.csv"
        test_data.write_text(
            "id,value,status\n1,100,active\n2,50,inactive\n3,200,active\n"
        )

        # Add nodes
        reader_id = builder.add_node(
            "CSVReader", "reader", config={"file_path": str(test_data)}
        )

        # Add conditional router
        router_id = builder.add_node(
            "ConditionalRouter",
            "router",
            config={"condition": "sum(df['value']) > 300", "mock_result": True},
        )

        # Add processing branches
        high_value_processor_id = builder.add_node(
            "DataFilter", "high_value_filter", config={"condition": "value > 100"}
        )

        low_value_processor_id = builder.add_node(
            "DataFilter", "low_value_filter", config={"condition": "value <= 100"}
        )

        # Add output nodes for each branch
        high_value_writer_id = builder.add_node(
            "CSVFileWriter",
            "high_value_writer",
            config={"path": str(temp_data_dir / "high_values.csv")},
        )

        low_value_writer_id = builder.add_node(
            "CSVFileWriter",
            "low_value_writer",
            config={"path": str(temp_data_dir / "low_values.csv")},
        )

        # Connect workflow with conditional branching
        builder.add_connection(reader_id, "data", router_id, "data")
        builder.add_connection(
            router_id, "true_output", high_value_processor_id, "data"
        )
        builder.add_connection(
            router_id, "false_output", low_value_processor_id, "data"
        )
        builder.add_connection(
            high_value_processor_id, "filtered_data", high_value_writer_id, "data"
        )
        builder.add_connection(
            low_value_processor_id, "filtered_data", low_value_writer_id, "data"
        )

        workflow = builder.build("conditional_branching")

        # Execute workflow
        runner = LocalRuntime()
        runner.run(workflow)

        # Since mock_result is True, should go to high_value branch
        assert (temp_data_dir / "high_values.csv").exists()
        # Low value branch should still be created but might be empty
        if (temp_data_dir / "low_values.csv").exists():
            low_data = pd.read_csv(temp_data_dir / "low_values.csv")
            assert len(low_data) == 0 or all(low_data["value"] <= 100)

    def test_parallel_processing_workflow(self, temp_data_dir: Path):
        """Test workflow with parallel processing branches."""
        builder = WorkflowBuilder()

        # Create large dataset
        large_data = temp_data_dir / "large_dataset.csv"
        with open(large_data, "w") as f:
            f.write("id,value,category,timestamp\n")
            for i in range(1000):
                f.write(f"{i},{i*10 % 1000},Cat_{i % 5},2024-01-{(i % 30) + 1:02d}\n")

        # Add reader
        reader_id = builder.add_node(
            "CSVReader", "reader", config={"file_path": str(large_data)}
        )

        # Add parallel processing branches
        # Branch 1: Statistical analysis
        stats_calculator_id = builder.add_node(
            "StatisticalAnalyzer",
            "stats_calculator",
            config={"calculations": ["mean", "std", "median", "quartiles"]},
        )

        # Branch 2: Category grouping
        category_grouper_id = builder.add_node(
            "DataAggregator",
            "category_grouper",
            config={"group_by": ["category"], "agg_func": "sum"},
        )

        # Branch 3: Time series analysis
        time_series_analyzer_id = builder.add_node(
            "TimeSeriesAnalyzer",
            "time_series",
            config={
                "date_column": "timestamp",
                "value_column": "value",
                "frequency": "D",
            },
        )

        # Branch 4: Data validation
        validator_id = builder.add_node(
            "DataValidator",
            "validator",
            config={
                "rules": {
                    "value": {"min": 0, "max": 1000},
                    "category": {"pattern": "Cat_[0-4]"},
                }
            },
        )

        # Add output writers for each branch
        stats_writer_id = builder.add_node(
            "JSONFileWriter",
            "stats_writer",
            config={"path": str(temp_data_dir / "statistics.json")},
        )

        category_writer_id = builder.add_node(
            "CSVFileWriter",
            "category_writer",
            config={"path": str(temp_data_dir / "category_summary.csv")},
        )

        timeseries_writer_id = builder.add_node(
            "CSVFileWriter",
            "timeseries_writer",
            config={"path": str(temp_data_dir / "timeseries.csv")},
        )

        validation_writer_id = builder.add_node(
            "JSONFileWriter",
            "validation_writer",
            config={"path": str(temp_data_dir / "validation_report.json")},
        )

        # Connect parallel branches
        builder.add_connection(reader_id, "data", stats_calculator_id, "data")
        builder.add_connection(reader_id, "data", category_grouper_id, "data")
        builder.add_connection(reader_id, "data", time_series_analyzer_id, "data")
        builder.add_connection(reader_id, "data", validator_id, "data")

        builder.add_connection(
            stats_calculator_id, "statistics", stats_writer_id, "data"
        )
        builder.add_connection(
            category_grouper_id, "aggregated_data", category_writer_id, "data"
        )
        builder.add_connection(
            time_series_analyzer_id, "timeseries_data", timeseries_writer_id, "data"
        )
        builder.add_connection(
            validator_id, "validation_report", validation_writer_id, "data"
        )

        workflow = builder.build("parallel_processing")

        # Execute workflow with parallel execution
        runner = LocalRuntime(max_parallel_jobs=4)
        start_time = time.time()
        runner.run(workflow)
        execution_time = time.time() - start_time

        # Verify all outputs were created
        assert (temp_data_dir / "statistics.json").exists()
        assert (temp_data_dir / "category_summary.csv").exists()
        assert (temp_data_dir / "timeseries.csv").exists()
        assert (temp_data_dir / "validation_report.json").exists()

        # Check that execution was actually parallel (should be faster than sequential)
        # This is a rough check, actual timing depends on system
        assert execution_time < 10  # Should complete relatively quickly

    def test_recursive_workflow_pattern(self, temp_data_dir: Path):
        """Test workflow with recursive/iterative processing pattern."""
        builder = WorkflowBuilder()

        # Create initial data
        initial_data = temp_data_dir / "initial.csv"
        initial_data.write_text("id,value,iteration\n1,100,0\n2,200,0\n3,300,0\n")

        # Add nodes for iterative processing
        reader_id = builder.add_node(
            "CSVReader", "reader", config={"file_path": str(initial_data)}
        )

        # Process data (multiply by factor)
        processor_id = builder.add_node(
            "DataTransformer",
            "processor",
            config={
                "operation": "multiply",
                "factor": 0.9,
                "increment_field": "iteration",
            },
        )

        # Check convergence condition
        convergence_checker_id = builder.add_node(
            "ConvergenceChecker",
            "convergence_checker",
            config={
                "condition": "max(df['value']) < 50",
                "max_iterations": 10,
                "mock_converged": False,  # Will be True after some iterations
            },
        )

        # Write intermediate results
        intermediate_writer_id = builder.add_node(
            "CSVFileWriter",
            "intermediate_writer",
            config={
                "path": str(temp_data_dir / "intermediate_{iteration}.csv"),
                "dynamic_path": True,
            },
        )

        # Final writer
        final_writer_id = builder.add_node(
            "CSVFileWriter",
            "final_writer",
            config={"path": str(temp_data_dir / "final_result.csv")},
        )

        # Connect with feedback loop
        builder.add_connection(reader_id, "data", processor_id, "data")
        builder.add_connection(
            processor_id, "transformed_data", convergence_checker_id, "data"
        )
        builder.add_connection(
            convergence_checker_id, "continue_data", intermediate_writer_id, "data"
        )
        builder.add_connection(
            convergence_checker_id, "converged_data", final_writer_id, "data"
        )
        # In real workflow, would have feedback connection: intermediate_writer -> reader

        workflow = builder.build("recursive_pattern")

        # Execute workflow
        runner = LocalRuntime()
        runner.run(workflow)

        # Check that some intermediate files were created
        intermediate_files = list(temp_data_dir.glob("intermediate_*.csv"))
        assert len(intermediate_files) >= 1

        # Check final result exists
        assert (temp_data_dir / "final_result.csv").exists()

    def test_dynamic_workflow_generation(self, temp_data_dir: Path):
        """Test dynamically generated workflow based on configuration."""
        # Configuration for dynamic workflow
        config = {
            "data_sources": [
                {"type": "csv", "path": "source1.csv", "id": "source1"},
                {"type": "json", "path": "source2.json", "id": "source2"},
            ],
            "processors": [
                {"type": "filter", "condition": "value > 100", "id": "filter1"},
                {"type": "aggregate", "group_by": ["category"], "id": "agg1"},
            ],
            "outputs": [
                {"type": "csv", "path": "output.csv", "id": "output1"},
                {"type": "json", "path": "output.json", "id": "output2"},
            ],
        }

        # Create test data
        (temp_data_dir / "source1.csv").write_text(
            "id,value,category\n1,150,A\n2,50,B\n"
        )
        (temp_data_dir / "source2.json").write_text(
            json.dumps({"data": [{"id": 3, "value": 200, "category": "A"}]})
        )

        # Build workflow dynamically
        builder = WorkflowBuilder()

        # Add data sources
        source_ids = {}
        for source in config["data_sources"]:
            if source["type"] == "csv":
                node_id = builder.add_node(
                    "CSVReader",
                    source["id"],
                    config={"file_path": str(temp_data_dir / source["path"])},
                )
            elif source["type"] == "json":
                node_id = builder.add_node(
                    "JSONReader",
                    source["id"],
                    config={"file_path": str(temp_data_dir / source["path"])},
                )
            source_ids[source["id"]] = node_id

        # Add processors
        processor_ids = {}
        for i, processor in enumerate(config["processors"]):
            if processor["type"] == "filter":
                node_id = builder.add_node(
                    "DataFilter",
                    processor["id"],
                    config={"condition": processor["condition"]},
                )
            elif processor["type"] == "aggregate":
                node_id = builder.add_node(
                    "DataAggregator",
                    processor["id"],
                    config={"group_by": processor["group_by"]},
                )
            processor_ids[processor["id"]] = node_id

            # Connect to previous node
            if i == 0:
                # Connect to first source
                builder.add_connection(source_ids["source1"], "data", node_id, "data")
            else:
                # Connect to previous processor
                prev_processor_id = processor_ids[config["processors"][i - 1]["id"]]
                builder.add_connection(
                    prev_processor_id,
                    (
                        "filtered_data"
                        if "filter" in config["processors"][i - 1]["type"]
                        else "aggregated_data"
                    ),
                    node_id,
                    "data",
                )

        # Add outputs
        last_processor_id = processor_ids[config["processors"][-1]["id"]]
        for output in config["outputs"]:
            if output["type"] == "csv":
                node_id = builder.add_node(
                    "CSVFileWriter",
                    output["id"],
                    config={"file_path": str(temp_data_dir / output["path"])},
                )
            elif output["type"] == "json":
                node_id = builder.add_node(
                    "JSONFileWriter",
                    output["id"],
                    config={"file_path": str(temp_data_dir / output["path"])},
                )

            builder.add_connection(
                last_processor_id, "aggregated_data", node_id, "data"
            )

        workflow = builder.build("dynamic_workflow")

        # Execute workflow
        runner = LocalRuntime()
        runner.run(workflow)

        # Verify outputs
        assert (temp_data_dir / "output.csv").exists()
        assert (temp_data_dir / "output.json").exists()

    def test_error_handling_and_retry_workflow(self, temp_data_dir: Path):
        """Test workflow with error handling and retry mechanisms."""
        builder = WorkflowBuilder()

        # Create test data
        test_data = temp_data_dir / "test.csv"
        test_data.write_text("id,value\n1,100\n2,invalid\n3,300\n")

        # Add nodes with potential errors
        reader_id = builder.add_node(
            "CSVReader", "reader", config={"file_path": str(test_data)}
        )

        # Add processor that may fail on invalid data
        processor_id = builder.add_node(
            "DataProcessor",
            "processor",
            config={
                "operation": "numeric_transform",
                "error_handling": "skip",
                "retry_attempts": 3,
            },
        )

        # Add error handler
        error_handler_id = builder.add_node(
            "ErrorHandler",
            "error_handler",
            config={
                "log_path": str(temp_data_dir / "errors.log"),
                "strategy": "continue",
            },
        )

        # Add fallback processor
        fallback_processor_id = builder.add_node(
            "FallbackProcessor", "fallback", config={"default_value": 0}
        )

        # Add final writer
        writer_id = builder.add_node(
            "CSVFileWriter",
            "writer",
            config={"path": str(temp_data_dir / "processed.csv")},
        )

        # Connect with error handling
        builder.add_connection(reader_id, "data", processor_id, "data")
        builder.add_connection(processor_id, "success_data", writer_id, "data")
        builder.add_connection(processor_id, "error_data", error_handler_id, "data")
        builder.add_connection(
            error_handler_id, "handled_data", fallback_processor_id, "data"
        )
        builder.add_connection(
            fallback_processor_id, "processed_data", writer_id, "data"
        )

        workflow = builder.build("error_handling_workflow")

        # Execute workflow with error handling
        runner = LocalRuntime(continue_on_error=True)
        runner.run(workflow)

        # Check that workflow completed despite errors
        assert (temp_data_dir / "processed.csv").exists()
        assert (temp_data_dir / "errors.log").exists()

        # Verify processed data contains handled errors
        processed_data = pd.read_csv(temp_data_dir / "processed.csv")
        assert len(processed_data) >= 2  # At least the valid rows

    def test_workflow_with_external_dependencies(
        self, temp_data_dir: Path, task_manager: TaskManager
    ):
        """Test workflow that depends on external services and resources."""
        builder = WorkflowBuilder()

        # Mock external service configurations
        external_configs = {
            "database": {"connection_string": "mock://db", "table": "test_table"},
            "api": {"endpoint": "https://api.example.com", "auth_token": "mock_token"},
            "storage": {"bucket": "test-bucket", "region": "us-west-2"},
        }

        # Add external data source
        db_reader_id = builder.add_node(
            "DatabaseReader",
            "db_reader",
            config={
                "connection_string": external_configs["database"]["connection_string"],
                "query": "SELECT * FROM test_table",
                "mock_data": pd.DataFrame({"id": [1, 2, 3], "value": [100, 200, 300]}),
            },
        )

        # Add API enrichment
        api_enricher_id = builder.add_node(
            "APIEnricher",
            "api_enricher",
            config={
                "endpoint": external_configs["api"]["endpoint"],
                "auth_token": external_configs["api"]["auth_token"],
                "mock_response": {"enriched": True},
            },
        )

        # Add cloud storage writer
        cloud_writer_id = builder.add_node(
            "CloudStorageWriter",
            "cloud_writer",
            config={
                "bucket": external_configs["storage"]["bucket"],
                "key": "processed/data.parquet",
                "format": "parquet",
                "local_backup": str(temp_data_dir / "backup.parquet"),
            },
        )

        # Add monitoring node
        monitor_id = builder.add_node(
            "PerformanceMonitor",
            "monitor",
            config={
                "metrics": ["latency", "throughput", "errors"],
                "alert_threshold": {"latency": 1000},
            },
        )

        # Connect workflow
        builder.add_connection(db_reader_id, "data", api_enricher_id, "data")
        builder.add_connection(
            api_enricher_id, "enriched_data", cloud_writer_id, "data"
        )
        builder.add_connection(cloud_writer_id, "result", monitor_id, "data")

        workflow = builder.build("external_dependencies_workflow")

        # Execute with dependency management
        runner = LocalRuntime(task_manager=task_manager, dependency_timeout=30)

        result = runner.run(workflow)

        # Check local backup was created
        assert (temp_data_dir / "backup.parquet").exists()

        # Check monitoring data
        monitor_data = result.get_node_output("monitor", "metrics")
        assert monitor_data is not None

    def test_machine_learning_pipeline_workflow(self, temp_data_dir: Path):
        """Test ML pipeline workflow with training, validation, and prediction."""
        builder = WorkflowBuilder()

        # Create training data
        train_data = temp_data_dir / "train.csv"
        X_train = np.random.randn(100, 5)
        y_train = X_train[:, 0] * 2 + X_train[:, 1] * 3 + np.random.randn(100) * 0.1
        train_df = pd.DataFrame(X_train, columns=[f"feature_{i}" for i in range(5)])
        train_df["target"] = y_train
        train_df.to_csv(train_data, index=False)

        # Create test data
        test_data = temp_data_dir / "test.csv"
        X_test = np.random.randn(20, 5)
        test_df = pd.DataFrame(X_test, columns=[f"feature_{i}" for i in range(5)])
        test_df.to_csv(test_data, index=False)

        # Add data loading
        train_loader_id = builder.add_node(
            "CSVReader", "train_loader", config={"file_path": str(train_data)}
        )

        test_loader_id = builder.add_node(
            "CSVReader", "test_loader", config={"file_path": str(test_data)}
        )

        # Add feature preprocessing
        scaler_id = builder.add_node(
            "FeatureScaler",
            "scaler",
            config={
                "method": "standard",
                "feature_columns": [f"feature_{i}" for i in range(5)],
            },
        )

        # Add feature engineering
        feature_engineer_id = builder.add_node(
            "FeatureEngineer",
            "feature_engineer",
            config={
                "operations": [
                    {"type": "polynomial", "degree": 2},
                    {"type": "interaction", "features": ["feature_0", "feature_1"]},
                ]
            },
        )

        # Add model training
        model_trainer_id = builder.add_node(
            "ModelTrainer",
            "trainer",
            config={
                "algorithm": "random_forest",
                "hyperparameters": {"n_estimators": 100, "max_depth": 10},
                "target_column": "target",
            },
        )

        # Add model evaluation
        evaluator_id = builder.add_node(
            "ModelEvaluator", "evaluator", config={"metrics": ["mse", "r2", "mae"]}
        )

        # Add prediction
        predictor_id = builder.add_node(
            "ModelPredictor", "predictor", config={"output_column": "prediction"}
        )

        # Add results writer
        results_writer_id = builder.add_node(
            "CSVFileWriter",
            "results_writer",
            config={"path": str(temp_data_dir / "predictions.csv")},
        )

        # Add model saver
        model_saver_id = builder.add_node(
            "ModelSerializer",
            "model_saver",
            config={"path": str(temp_data_dir / "model.pkl"), "format": "pickle"},
        )

        # Connect ML pipeline
        builder.add_connection(train_loader_id, "data", scaler_id, "data")
        builder.add_connection(scaler_id, "scaled_data", feature_engineer_id, "data")
        builder.add_connection(
            feature_engineer_id, "engineered_data", model_trainer_id, "training_data"
        )
        builder.add_connection(model_trainer_id, "model", evaluator_id, "model")
        builder.add_connection(train_loader_id, "data", evaluator_id, "validation_data")
        builder.add_connection(model_trainer_id, "model", predictor_id, "model")
        builder.add_connection(test_loader_id, "data", predictor_id, "prediction_data")
        builder.add_connection(predictor_id, "predictions", results_writer_id, "data")
        builder.add_connection(model_trainer_id, "model", model_saver_id, "model")

        workflow = builder.build("ml_pipeline_workflow")

        # Execute ML pipeline
        runner = LocalRuntime()
        runner.run(workflow)

        # Verify outputs
        assert (temp_data_dir / "predictions.csv").exists()
        assert (temp_data_dir / "model.pkl").exists()

        # Check predictions
        predictions = pd.read_csv(temp_data_dir / "predictions.csv")
        assert "prediction" in predictions.columns
        assert len(predictions) == 20  # Same as test data

    def test_real_time_streaming_workflow(self, temp_data_dir: Path):
        """Test workflow designed for real-time data streaming."""
        builder = WorkflowBuilder()

        # Simulate streaming data source
        stream_config = {
            "format": "json",
            "batch_size": 10,
            "frequency": 1.0,  # seconds
            "mock_data": [
                {"timestamp": i, "value": np.random.randn()} for i in range(100)
            ],
        }

        # Add streaming source
        stream_reader_id = builder.add_node(
            "StreamingDataSource", "stream_reader", config=stream_config
        )

        # Add windowing processor
        windower_id = builder.add_node(
            "WindowProcessor",
            "windower",
            config={"window_type": "sliding", "window_size": 10, "slide_interval": 5},
        )

        # Add real-time analytics
        analytics_id = builder.add_node(
            "RealTimeAnalytics",
            "analytics",
            config={
                "calculations": ["mean", "std", "trend"],
                "alert_conditions": {
                    "high_value": "mean > 2.0",
                    "high_variance": "std > 1.5",
                },
            },
        )

        # Add alert handler
        alert_handler_id = builder.add_node(
            "AlertHandler",
            "alert_handler",
            config={
                "channels": ["log", "email"],
                "log_path": str(temp_data_dir / "alerts.log"),
            },
        )

        # Add dashboard updater
        dashboard_id = builder.add_node(
            "DashboardUpdater",
            "dashboard",
            config={
                "update_frequency": 1.0,
                "metrics_file": str(temp_data_dir / "dashboard_metrics.json"),
            },
        )

        # Add data archiver
        archiver_id = builder.add_node(
            "DataArchiver",
            "archiver",
            config={
                "archive_path": str(temp_data_dir / "archive"),
                "partition_by": "hour",
                "format": "parquet",
            },
        )

        # Connect streaming pipeline
        builder.add_connection(stream_reader_id, "data", windower_id, "data")
        builder.add_connection(windower_id, "windowed_data", analytics_id, "data")
        builder.add_connection(analytics_id, "metrics", dashboard_id, "data")
        builder.add_connection(analytics_id, "alerts", alert_handler_id, "data")
        builder.add_connection(windower_id, "windowed_data", archiver_id, "data")

        workflow = builder.build("streaming_workflow")

        # Execute streaming workflow (with timeout for test)
        runner = LocalRuntime(streaming_mode=True)

        # Run for a short time in test
        import threading

        def run_with_timeout():
            runner.run(workflow)

        thread = threading.Thread(target=run_with_timeout)
        thread.start()
        time.sleep(3)  # Run for 3 seconds
        runner.stop()
        thread.join()

        # Verify outputs
        assert (temp_data_dir / "dashboard_metrics.json").exists()
        assert (temp_data_dir / "archive").exists()

        # Check metrics
        with open(temp_data_dir / "dashboard_metrics.json") as f:
            metrics = json.load(f)
            assert "mean" in metrics
            assert "std" in metrics
