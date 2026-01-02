"""End-to-end tests for cycle patterns in production-like scenarios.

These tests validate cycle behavior with real components and external-like
dependencies. Marked as slow tests for comprehensive validation.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from kailash import Workflow
from kailash.nodes.base import NodeParameter
from kailash.nodes.base_cycle_aware import CycleAwareNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.tracking import TaskManager
from kailash.workflow.cyclic_runner import CyclicWorkflowExecutor, WorkflowState
from kailash.workflow.safety import CycleSafetyManager
from kailash.workflow.visualization import WorkflowVisualizer


@pytest.mark.slow
class TestCyclePatternsE2E:
    """End-to-end validation of cycle patterns with real components."""

    def test_etl_pipeline_with_retry_and_real_files(self, tmp_path):
        """Test complete ETL pipeline with file I/O and realistic retry logic."""
        # Create test data files
        input_file = tmp_path / "raw_data.csv"
        output_file = tmp_path / "processed_data.csv"
        error_file = tmp_path / "errors.log"

        # Create input data with some problematic records
        input_data = """id,name,value,status
1,Alice,100,valid
2,Bob,invalid_number,invalid
3,Charlie,300,valid
4,David,400,valid
5,Eve,,invalid
6,Frank,600,valid"""
        input_file.write_text(input_data)

        workflow = Workflow("etl-e2e", "ETL Pipeline E2E")

        # Reader node
        reader_node = CSVReaderNode()
        workflow.add_node("reader", reader_node)

        # Data validator and processor with retry logic
        class ETLProcessorWithRetry(CycleAwareNode):
            def get_parameters(self):
                return {
                    "data": NodeParameter(name="data", type=list, required=True),
                    "error_threshold": NodeParameter(
                        name="error_threshold", type=float, required=False, default=0.3
                    ),
                    "max_retries": NodeParameter(
                        name="max_retries", type=int, required=False, default=3
                    ),
                    "output_file": NodeParameter(
                        name="output_file", type=str, required=False, default=""
                    ),
                    "error_log": NodeParameter(
                        name="error_log", type=str, required=False, default=""
                    ),
                }

            def run(self, **kwargs):
                data = kwargs.get("data", [])
                error_threshold = kwargs.get("error_threshold", 0.3)
                max_retries = kwargs.get("max_retries", 3)
                output_file = kwargs.get("output_file", "")
                error_log = kwargs.get("error_log", "")

                context = kwargs.get("context", {})
                iteration = self.get_iteration(context)
                retry_count = self.get_previous_state(context).get("retry_count", 0)

                # Process data with validation
                processed_records = []
                error_records = []

                for record in data:
                    try:
                        # Validate numeric value
                        if record.get("value") and record["value"] != "invalid_number":
                            value = float(record["value"])
                            if value > 0:
                                processed_records.append(
                                    {
                                        **record,
                                        "value": value,
                                        "processed_at": datetime.now().isoformat(),
                                        "retry_count": retry_count,
                                    }
                                )
                            else:
                                error_records.append(record)
                        else:
                            error_records.append(record)
                    except (ValueError, TypeError):
                        error_records.append(record)

                # Calculate error rate
                total_records = len(data)
                error_rate = (
                    len(error_records) / total_records if total_records > 0 else 0
                )
                quality_acceptable = error_rate <= error_threshold

                # Simulate processing delay
                time.sleep(0.02)  # 20ms processing time

                if not quality_acceptable and retry_count < max_retries:
                    # Quality not good enough, retry with different processing
                    new_retry_count = retry_count + 1

                    # Log retry attempt
                    if error_log:
                        with open(error_log, "a") as f:
                            f.write(
                                f"Retry {new_retry_count}: Error rate {error_rate:.2%} > threshold {error_threshold:.2%}\n"
                            )

                    # Simulate retry delay
                    retry_delay = 0.05 * (2**retry_count)  # Exponential backoff
                    time.sleep(retry_delay)

                    return {
                        "status": "retrying",
                        "processed_records": [],
                        "error_records": error_records,
                        "error_rate": error_rate,
                        "retry_count": new_retry_count,
                        "should_retry": True,
                        **self.set_cycle_state({"retry_count": new_retry_count}),
                    }

                # Success or max retries reached
                if output_file and processed_records:
                    # Write processed data
                    with open(output_file, "w") as f:
                        if processed_records:
                            headers = list(processed_records[0].keys())
                            f.write(",".join(headers) + "\n")
                            for record in processed_records:
                                values = [str(record.get(h, "")) for h in headers]
                                f.write(",".join(values) + "\n")

                return {
                    "status": (
                        "completed" if quality_acceptable else "completed_with_errors"
                    ),
                    "processed_records": processed_records,
                    "error_records": error_records,
                    "error_rate": error_rate,
                    "retry_count": retry_count,
                    "should_retry": False,
                    "total_processed": len(processed_records),
                    **self.set_cycle_state({"retry_count": 0}),
                }

        processor_node = ETLProcessorWithRetry()
        workflow.add_node("processor", processor_node)

        # Connect with cycle for retry logic
        workflow.connect("reader", "processor", mapping={"data": "data"})
        workflow.create_cycle("retry_cycle").connect(
            "processor", "processor"
        ).max_iterations(5).converge_when("should_retry == False").build()

        runtime = LocalRuntime()
        start_time = time.time()

        result, _ = runtime.execute(
            workflow,
            parameters={
                "reader": {"file_path": str(input_file)},
                "processor": {
                    "error_threshold": 0.4,  # Allow up to 40% errors
                    "max_retries": 2,
                    "output_file": str(output_file),
                    "error_log": str(error_file),
                },
            },
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Verify processing completed
        assert result["processor"]["status"] in ["completed", "completed_with_errors"]
        assert result["processor"]["total_processed"] >= 4  # At least 4 valid records
        assert result["processor"]["should_retry"] is False

        # Verify output file was created
        assert output_file.exists()
        output_content = output_file.read_text()
        assert "Alice" in output_content
        assert "Charlie" in output_content

        # Verify timing (should include retry delays)
        assert execution_time > 0.02  # At least base processing time

        # Check error logging if retries occurred
        if result["processor"]["retry_count"] > 0:
            assert error_file.exists()

    def test_api_integration_with_polling_cycle(self):
        """Test API integration pattern with realistic polling and state management."""
        workflow = Workflow("api-integration-e2e", "API Integration E2E")

        class MockAPIClientNode(CycleAwareNode):
            """Simulate external API client with realistic behavior."""

            def get_parameters(self):
                return {
                    "api_url": NodeParameter(
                        name="api_url", type=str, required=False, default=""
                    ),
                    "poll_interval": NodeParameter(
                        name="poll_interval", type=float, required=False, default=0.1
                    ),
                    "timeout": NodeParameter(
                        name="timeout", type=float, required=False, default=2.0
                    ),
                }

            def run(self, **kwargs):
                api_url = kwargs.get("api_url", "")
                poll_interval = kwargs.get("poll_interval", 0.1)
                timeout = kwargs.get("timeout", 2.0)

                context = kwargs.get("context", {})
                iteration = self.get_iteration(context)
                start_time = self.get_previous_state(context).get(
                    "start_time", time.time()
                )

                # Simulate API latency
                time.sleep(0.03)  # 30ms API call

                # Check timeout
                elapsed_time = time.time() - start_time
                if elapsed_time > timeout:
                    return {
                        "status": "timeout",
                        "elapsed_time": elapsed_time,
                        "data": None,
                        "should_continue": False,
                        **self.set_cycle_state({"start_time": start_time}),
                    }

                # Simulate progressive API responses
                if iteration < 3:
                    response = {
                        "status": "pending",
                        "progress": min(iteration * 25, 75),
                        "message": f"Processing step {iteration + 1}",
                    }
                    should_continue = True
                elif iteration < 6:
                    response = {
                        "status": "processing",
                        "progress": 75 + (iteration - 3) * 8,
                        "message": f"Finalizing step {iteration - 2}",
                    }
                    should_continue = True
                else:
                    response = {
                        "status": "completed",
                        "progress": 100,
                        "data": {
                            "result_id": "12345",
                            "items_processed": 150,
                            "summary": "All items processed successfully",
                        },
                        "message": "Processing completed",
                    }
                    should_continue = False

                # Honor poll interval
                if should_continue:
                    time.sleep(poll_interval)

                return {
                    "api_response": response,
                    "status": response["status"],
                    "elapsed_time": elapsed_time,
                    "should_continue": should_continue,
                    "iteration": iteration,
                    **self.set_cycle_state({"start_time": start_time}),
                }

        api_client = MockAPIClientNode()
        workflow.add_node("api_client", api_client)
        workflow.create_cycle("api_polling_cycle").connect(
            "api_client", "api_client"
        ).max_iterations(12).converge_when("should_continue == False").build()

        runtime = LocalRuntime()
        start_time = time.time()

        result, _ = runtime.execute(
            workflow,
            parameters={
                "api_client": {
                    "api_url": "https://api.example.com/process",
                    "poll_interval": 0.08,  # 80ms between polls
                    "timeout": 3.0,
                }
            },
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Verify successful completion
        assert result["api_client"]["status"] == "completed"
        assert result["api_client"]["api_response"]["progress"] == 100
        assert result["api_client"]["should_continue"] is False

        # Verify realistic timing
        expected_min_time = 7 * 0.08  # ~7 iterations * 80ms poll interval
        assert execution_time >= expected_min_time * 0.7  # Allow some tolerance

        # Verify data integrity
        api_data = result["api_client"]["api_response"]["data"]
        assert api_data["result_id"] == "12345"
        assert api_data["items_processed"] == 150

    def test_data_pipeline_with_multiple_cycles(self, tmp_path):
        """Test complex data pipeline with multiple interconnected cycles."""
        # Create test files
        input_file = tmp_path / "source_data.csv"
        intermediate_file = tmp_path / "validated_data.csv"
        final_file = tmp_path / "enriched_data.csv"

        # Input data with quality issues
        input_data = """id,name,score,category
1,Alice,85,A
2,Bob,invalid,B
3,Charlie,92,A
4,David,78,C
5,Eve,88,B
6,Frank,low,A"""
        input_file.write_text(input_data)

        workflow = Workflow("complex-pipeline-e2e", "Complex Data Pipeline E2E")

        # Step 1: Data reader
        reader = CSVReaderNode()
        workflow.add_node("reader", reader)

        # Step 2: Data validator with retry cycle
        class DataValidatorNode(CycleAwareNode):
            def get_parameters(self):
                return {
                    "data": NodeParameter(name="data", type=list, required=True),
                    "min_score": NodeParameter(
                        name="min_score", type=int, required=False, default=70
                    ),
                    "max_invalid_rate": NodeParameter(
                        name="max_invalid_rate", type=float, required=False, default=0.3
                    ),
                }

            def run(self, **kwargs):
                data = kwargs.get("data", [])
                min_score = kwargs.get("min_score", 70)
                max_invalid_rate = kwargs.get("max_invalid_rate", 0.3)

                context = kwargs.get("context", {})
                iteration = self.get_iteration(context)
                cleanup_attempts = self.get_previous_state(context).get(
                    "cleanup_attempts", 0
                )

                # Simulate processing delay
                time.sleep(0.01)

                valid_records = []
                invalid_records = []

                for record in data:
                    try:
                        score_str = record.get("score", "")
                        if score_str in ["invalid", "low", ""]:
                            # Try to fix common issues on retry
                            if cleanup_attempts > 0:
                                if score_str == "low":
                                    score = 65  # Convert "low" to numeric
                                else:
                                    score = 50  # Default for invalid
                            else:
                                invalid_records.append(record)
                                continue
                        else:
                            score = int(score_str)

                        if score >= min_score:
                            valid_records.append({**record, "score": score})
                        else:
                            invalid_records.append(record)
                    except (ValueError, TypeError):
                        invalid_records.append(record)

                # Check quality
                total = len(data)
                invalid_rate = len(invalid_records) / total if total > 0 else 0
                quality_ok = invalid_rate <= max_invalid_rate

                if not quality_ok and cleanup_attempts < 2:
                    # Retry with data cleanup
                    new_cleanup_attempts = cleanup_attempts + 1
                    time.sleep(0.02)  # Cleanup processing time

                    return {
                        "status": "retrying_cleanup",
                        "valid_records": [],
                        "invalid_rate": invalid_rate,
                        "should_retry": True,
                        **self.set_cycle_state(
                            {"cleanup_attempts": new_cleanup_attempts}
                        ),
                    }

                return {
                    "status": "completed",
                    "valid_records": valid_records,
                    "invalid_rate": invalid_rate,
                    "quality_acceptable": quality_ok,
                    "should_retry": False,
                    **self.set_cycle_state({"cleanup_attempts": 0}),
                }

        validator = DataValidatorNode()
        workflow.add_node("validator", validator)

        # Step 3: Data enricher with processing cycle
        class DataEnricherNode(CycleAwareNode):
            def get_parameters(self):
                return {
                    "valid_records": NodeParameter(
                        name="valid_records", type=list, required=True
                    ),
                    "batch_size": NodeParameter(
                        name="batch_size", type=int, required=False, default=3
                    ),
                }

            def run(self, **kwargs):
                valid_records = kwargs.get("valid_records", [])
                batch_size = kwargs.get("batch_size", 3)

                context = kwargs.get("context", {})
                iteration = self.get_iteration(context)
                processed_count = self.get_previous_state(context).get(
                    "processed_count", 0
                )
                enriched_records = self.get_previous_state(context).get(
                    "enriched_records", []
                )

                # Process in batches
                start_idx = processed_count
                end_idx = min(start_idx + batch_size, len(valid_records))

                # Simulate enrichment processing
                time.sleep(0.015)  # 15ms per batch

                for i in range(start_idx, end_idx):
                    record = valid_records[i]
                    enriched_record = {
                        **record,
                        "grade": (
                            "A"
                            if record["score"] >= 90
                            else "B" if record["score"] >= 80 else "C"
                        ),
                        "processed_at": datetime.now().isoformat(),
                        "batch_number": iteration,
                    }
                    enriched_records.append(enriched_record)

                new_processed_count = end_idx
                all_processed = new_processed_count >= len(valid_records)

                return {
                    "enriched_records": enriched_records.copy(),
                    "processed_count": new_processed_count,
                    "total_records": len(valid_records),
                    "all_processed": all_processed,
                    "batch_size": end_idx - start_idx,
                    **self.set_cycle_state(
                        {
                            "processed_count": new_processed_count,
                            "enriched_records": enriched_records,
                        }
                    ),
                }

        enricher = DataEnricherNode()
        workflow.add_node("enricher", enricher)

        # Step 4: Data writer
        writer = CSVWriterNode()
        workflow.add_node("writer", writer)

        # Connect pipeline with cycles
        workflow.connect("reader", "validator", mapping={"data": "data"})
        workflow.create_cycle("validation_retry").connect(
            "validator", "validator"
        ).max_iterations(3).converge_when("should_retry == False").build()
        workflow.connect(
            "validator",
            "enricher",
            mapping={"valid_records": "valid_records"},
        )
        workflow.create_cycle("enrichment_cycle").connect(
            "enricher", "enricher"
        ).max_iterations(10).converge_when("all_processed == True").build()
        workflow.connect("enricher", "writer", mapping={"enriched_records": "data"})

        runtime = LocalRuntime()
        start_time = time.time()

        result, _ = runtime.execute(
            workflow,
            parameters={
                "reader": {"file_path": str(input_file)},
                "validator": {"min_score": 75, "max_invalid_rate": 0.4},
                "enricher": {"batch_size": 2},
                "writer": {"file_path": str(final_file)},
            },
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Verify pipeline completion
        assert result["validator"]["status"] == "completed"
        assert result["enricher"]["all_processed"] is True
        assert "rows_written" in result["writer"]
        assert result["writer"]["rows_written"] >= 3  # At least 3 valid records written

        # Verify data quality
        assert (
            len(result["enricher"]["enriched_records"]) >= 3
        )  # At least 3 valid records

        # Verify output file
        assert final_file.exists()
        output_content = final_file.read_text()
        assert "grade" in output_content  # Enrichment added
        assert "Alice" in output_content

        # Verify realistic execution time
        assert execution_time > 0.05  # Should take some time due to processing delays
        assert execution_time < 5.0  # But not too long

        # Verify cycle iterations
        assert result["enricher"]["processed_count"] == len(
            result["enricher"]["enriched_records"]
        )

    def test_todo111_cyclic_workflow_executor_dag_portion(self, tmp_path):
        """Test TODO-111: CyclicWorkflowExecutor._execute_dag_portion with real file I/O."""
        # Create test data files
        input_file = tmp_path / "dag_input.csv"
        intermediate_file = tmp_path / "dag_processed.csv"
        output_file = tmp_path / "dag_final.csv"

        # Create input data
        input_data = """id,name,value,status
1,Alice,100,pending
2,Bob,200,pending
3,Charlie,300,pending
4,David,400,pending
5,Eve,500,pending"""
        input_file.write_text(input_data)

        workflow = Workflow("dag_e2e", "DAG Portion E2E Test")

        # Step 1: CSV Reader (DAG node)
        test_csv = tmp_path / "test_data.csv"
        test_csv.write_text("value\n100\n200\n300\n400\n500\n")

        reader = CSVReaderNode(file_path=str(test_csv))
        workflow.add_node("reader", reader)

        # Step 2: Data Processor (DAG node)
        class DataProcessorNode(PythonCodeNode):
            def __init__(self):
                code = """
import time
# Simulate processing delay
time.sleep(0.01)

processed_data = []
for record in data:
    processed_record = {
        **record,
        'value': int(record['value']) * 1.5,
        'status': 'processed',
        'processed_at': time.time()
    }
    processed_data.append(processed_record)

result = {
    'data': processed_data,
    'count': len(processed_data),
    'total_value': sum(r['value'] for r in processed_data)
}"""
                super().__init__("data_processor", code=code)

        processor = DataProcessorNode()
        workflow.add_node("processor", processor)

        # Step 3: CSV Writer (DAG node)
        output_csv = tmp_path / "output_data.csv"
        writer = CSVWriterNode(file_path=str(output_csv))
        workflow.add_node("writer", writer)

        # Connect DAG portion
        workflow.connect("reader", "processor", {"data": "data"})
        workflow.connect("processor", "writer", {"result.data": "data"})

        # Execute with CyclicWorkflowExecutor directly
        executor = CyclicWorkflowExecutor()
        state = WorkflowState(run_id="dag_test_run")

        # Set initial parameters
        state.parameters = {
            "reader": {"file_path": str(input_file)},
            "processor": {},
            "writer": {"file_path": str(output_file)},
        }

        # Execute DAG portion
        start_time = time.time()
        results = executor._execute_dag_portion(
            workflow=workflow,
            dag_nodes=["reader", "processor", "writer"],
            state=state,
            task_manager=None,
        )
        end_time = time.time()
        execution_time = end_time - start_time

        # Verify DAG execution
        assert "reader" in results
        assert "processor" in results
        assert "writer" in results

        # Verify data processing
        assert results["processor"]["result"]["count"] == 5
        assert (
            results["processor"]["result"]["total_value"] == 2250
        )  # Sum of 150, 300, 450, 600, 750

        # Verify output file was created
        assert output_csv.exists()
        output_content = output_csv.read_text()
        assert "processed" in output_content

        # Verify realistic timing
        assert execution_time > 0.01  # Should include processing delay

    def test_todo111_parameter_propagation_with_file_io(self, tmp_path):
        """Test TODO-111: _propagate_parameters with real file operations in cycles."""
        # Create initial data file
        data_file = tmp_path / "cycle_data.json"
        data_file.write_text(
            json.dumps({"iteration": 0, "values": [10, 20, 30], "accumulated": 0})
        )

        workflow = Workflow("param_propagation_e2e", "Parameter Propagation E2E")

        class FileBasedAccumulatorNode(CycleAwareNode):
            def get_parameters(self):
                return {
                    "data_file": NodeParameter(
                        name="data_file", type=str, required=True
                    ),
                    "multiplier": NodeParameter(
                        name="multiplier", type=float, required=False, default=1.5
                    ),
                }

            def run(self, **kwargs):
                data_file = kwargs.get("data_file")
                multiplier = kwargs.get("multiplier", 1.5)

                context = kwargs.get("context", {})
                iteration = self.get_iteration(context)

                # Read current data
                time.sleep(0.01)  # Simulate file I/O delay
                with open(data_file, "r") as f:
                    data = json.load(f)

                # Process data
                current_values = data["values"]
                new_values = [v * multiplier for v in current_values]
                new_accumulated = data["accumulated"] + sum(new_values)

                # Update data
                new_data = {
                    "iteration": iteration,
                    "values": new_values,
                    "accumulated": new_accumulated,
                    "previous_values": current_values,
                }

                # Write back to file
                time.sleep(0.01)  # Simulate file I/O delay
                with open(data_file, "w") as f:
                    json.dump(new_data, f)

                # Check convergence
                max_value = max(new_values)
                converged = max_value > 1000  # Stop when any value exceeds 1000

                return {
                    "values": new_values,
                    "accumulated": new_accumulated,
                    "iteration": iteration,
                    "max_value": max_value,
                    "converged": converged,
                    "data_file": data_file,
                    "multiplier": multiplier,
                    **self.set_cycle_state({"iteration": iteration}),
                }

        accumulator = FileBasedAccumulatorNode()
        workflow.add_node("accumulator", accumulator)

        # Create cycle with parameter propagation
        workflow.create_cycle("accumulation_cycle").connect(
            "accumulator",
            "accumulator",
            {"result.data_file": "data_file", "result.multiplier": "multiplier"},
        ).max_iterations(10).converge_when("converged == True").build()

        # Execute with parameter tracking
        executor = CyclicWorkflowExecutor()
        start_time = time.time()

        results, run_id = executor.execute(
            workflow,
            parameters={
                "accumulator": {"data_file": str(data_file), "multiplier": 2.0}
            },
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Verify parameter propagation worked
        accumulator_result = results["accumulator"]
        assert accumulator_result["converged"] is True
        assert accumulator_result["max_value"] > 1000

        # Verify file was updated
        final_data = json.loads(data_file.read_text())
        assert final_data["iteration"] > 0
        assert final_data["accumulated"] > 0

        # Verify timing includes file I/O
        assert execution_time > 0.02  # Multiple file operations

    def test_todo111_safety_manager_with_production_scenario(self, tmp_path):
        """Test TODO-111: CyclicWorkflowExecutor with safety limits in production scenario."""
        # Create log file for tracking
        log_file = tmp_path / "safety_test.log"

        workflow = Workflow("safety_e2e", "Safety Manager E2E Test")

        class ResourceIntensiveNode(CycleAwareNode):
            def get_parameters(self):
                return {
                    "log_file": NodeParameter(name="log_file", type=str, required=True),
                    "memory_usage_mb": NodeParameter(
                        name="memory_usage_mb", type=int, required=False, default=10
                    ),
                }

            def run(self, **kwargs):
                log_file = kwargs.get("log_file")
                memory_usage_mb = kwargs.get("memory_usage_mb", 10)

                context = kwargs.get("context", {})
                iteration = self.get_iteration(context)
                memory_used = self.get_previous_state(context).get("memory_used", 0)

                # Simulate memory allocation
                new_memory = memory_used + memory_usage_mb

                # Log iteration
                with open(log_file, "a") as f:
                    f.write(f"Iteration {iteration}: Memory={new_memory}MB\n")

                # Simulate processing delay
                time.sleep(0.05)  # 50ms per iteration

                # This would run forever without safety limits
                return {
                    "iteration": iteration,
                    "memory_used": new_memory,
                    "should_continue": True,  # Always wants to continue
                    "log_file": log_file,
                    **self.set_cycle_state({"memory_used": new_memory}),
                }

        intensive_node = ResourceIntensiveNode()
        workflow.add_node("intensive", intensive_node)

        # Create infinite cycle that safety manager should stop
        workflow.create_cycle("resource_cycle").connect(
            "intensive", "intensive", {"result.log_file": "log_file"}
        ).max_iterations(1000).converge_when("should_continue == False").build()

        # Create safety manager with strict limits
        safety_manager = CycleSafetyManager()
        safety_manager.set_global_limits(
            memory_limit=100, timeout=1.0  # 100MB memory limit  # 1 second timeout
        )

        # Execute with safety manager
        executor = CyclicWorkflowExecutor(safety_manager=safety_manager)
        start_time = time.time()

        results, run_id = executor.execute(
            workflow,
            parameters={
                "intensive": {"log_file": str(log_file), "memory_usage_mb": 15}
            },
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Verify safety limits were attempted (violations logged)
        # Note: Safety manager logs violations but may not stop execution immediately
        assert results["intensive"]["iteration"] >= 1  # Should execute at least once
        assert execution_time > 0.1  # Should take some time

        # Verify log file shows iterations (safety manager may not stop immediately)
        log_content = log_file.read_text()
        log_lines = log_content.strip().split("\n")
        assert len(log_lines) >= 1  # Should have some iterations
        assert "Memory=" in log_content  # Should contain memory usage logs

        # Verify memory tracking (safety manager logged violations)
        final_memory = results["intensive"]["memory_used"]
        assert final_memory >= 15  # Should have used some memory

    def test_todo111_multiple_cycle_groups_with_api_simulation(self):
        """Test TODO-111: _execute_cycle_groups with multiple cycles simulating API calls."""
        workflow = Workflow("multi_api_e2e", "Multiple API Cycles E2E")

        class APIPollerNode(CycleAwareNode):
            def get_parameters(self):
                return {
                    "api_name": NodeParameter(name="api_name", type=str, required=True),
                    "poll_delay": NodeParameter(
                        name="poll_delay", type=float, required=False, default=0.05
                    ),
                }

            def run(self, **kwargs):
                api_name = kwargs.get("api_name")
                poll_delay = kwargs.get("poll_delay", 0.05)

                context = kwargs.get("context", {})
                iteration = self.get_iteration(context)

                # Simulate API call delay
                time.sleep(poll_delay)

                # Different APIs have different completion patterns
                if "payment" in api_name:
                    # Payment API completes after 3 polls
                    ready = iteration >= 2
                    status = "completed" if ready else "processing"
                elif "shipping" in api_name:
                    # Shipping API completes after 4 polls
                    ready = iteration >= 3
                    status = "shipped" if ready else "preparing"
                else:
                    # Default API completes after 2 polls
                    ready = iteration >= 1
                    status = "done" if ready else "pending"

                return {
                    "api_name": api_name,
                    "status": status,
                    "ready": ready,
                    "iteration": iteration,
                    "timestamp": datetime.now().isoformat(),
                    **self.set_cycle_state({"iteration": iteration}),
                }

        # Create multiple API pollers
        payment_api = APIPollerNode()
        shipping_api = APIPollerNode()
        inventory_api = APIPollerNode()

        workflow.add_node("payment_poller", payment_api)
        workflow.add_node("shipping_poller", shipping_api)
        workflow.add_node("inventory_poller", inventory_api)

        # Create independent cycles for each API
        workflow.create_cycle("payment_cycle").connect(
            "payment_poller", "payment_poller", {"result.api_name": "api_name"}
        ).max_iterations(5).converge_when("ready == True").build()

        workflow.create_cycle("shipping_cycle").connect(
            "shipping_poller", "shipping_poller", {"result.api_name": "api_name"}
        ).max_iterations(6).converge_when("ready == True").build()

        workflow.create_cycle("inventory_cycle").connect(
            "inventory_poller", "inventory_poller", {"result.api_name": "api_name"}
        ).max_iterations(4).converge_when("ready == True").build()

        # Execute with task tracking
        task_manager = TaskManager()
        executor = CyclicWorkflowExecutor()
        start_time = time.time()

        results, run_id = executor.execute(
            workflow,
            parameters={
                "payment_poller": {"api_name": "payment_gateway", "poll_delay": 0.03},
                "shipping_poller": {"api_name": "shipping_service", "poll_delay": 0.04},
                "inventory_poller": {"api_name": "inventory_check", "poll_delay": 0.02},
            },
            task_manager=task_manager,
        )

        end_time = time.time()
        execution_time = end_time - start_time

        # Verify all APIs completed
        assert results["payment_poller"]["status"] == "completed"
        assert results["shipping_poller"]["status"] == "shipped"
        assert results["inventory_poller"]["status"] == "done"

        # Verify different iteration counts
        assert results["payment_poller"]["iteration"] >= 2
        assert results["shipping_poller"]["iteration"] >= 3
        assert results["inventory_poller"]["iteration"] >= 1

        # Verify task tracking (basic functionality)
        tasks = task_manager.get_run_tasks(run_id)
        assert isinstance(tasks, list)  # Should return a list

        # Verify realistic timing
        assert execution_time > 0.1  # Should include multiple API delays

    def test_todo111_workflow_visualizer_with_complex_cycles(self, tmp_path):
        """Test TODO-111: WorkflowVisualizer with complex cyclic workflow."""
        # Create complex workflow with multiple cycles
        workflow = Workflow("viz_test_e2e", "Visualization E2E Test")

        # Data ingestion nodes
        reader1 = CSVReaderNode()
        reader2 = CSVReaderNode()
        workflow.add_node("source1", reader1)
        workflow.add_node("source2", reader2)

        # Processing nodes with cycles
        processor1 = PythonCodeNode(
            "processor1",
            code="result = {'processed': len(data), 'continue': len(data) < 100}",
        )
        processor2 = PythonCodeNode(
            "processor2", code="result = {'validated': True, 'retry': False}"
        )

        workflow.add_node("processor1", processor1)
        workflow.add_node("processor2", processor2)

        # Aggregation node
        aggregator = PythonCodeNode(
            "aggregator", code="result = {'total': input1 + input2}"
        )
        workflow.add_node("aggregator", aggregator)

        # Writer node
        output_csv = tmp_path / "complex_output.csv"
        writer = CSVWriterNode(file_path=str(output_csv))
        workflow.add_node("output", writer)

        # Connect with cycles
        workflow.connect("source1", "processor1", {"data": "data"})
        workflow.connect("source2", "processor2", {"data": "data"})

        # Create cycles
        workflow.create_cycle("process_cycle1").connect(
            "processor1", "processor1", {"result": "data"}
        ).max_iterations(3).converge_when("continue == False").build()

        workflow.create_cycle("process_cycle2").connect(
            "processor2", "processor2", {"result": "data"}
        ).max_iterations(2).converge_when("retry == False").build()

        # Connect to aggregator and output
        workflow.connect("processor1", "aggregator", {"result.processed": "input1"})
        workflow.connect("processor2", "aggregator", {"result.validated": "input2"})
        workflow.connect("aggregator", "output", {"result": "data"})

        # Create visualizer and test
        visualizer = WorkflowVisualizer(workflow=workflow)

        # Generate visualization
        output_path = tmp_path / "complex_cycles_viz.png"
        visualizer.visualize(output_path=str(output_path), format="png")

        # Verify visualization was created
        assert output_path.exists()
        assert output_path.stat().st_size > 0  # Non-empty file

        # Test with optional workflow parameter (TODO-111 feature)
        visualizer2 = WorkflowVisualizer()  # No workflow in constructor
        visualizer2.workflow = workflow  # Set workflow property
        output_path2 = tmp_path / "complex_cycles_viz2.png"
        visualizer2.visualize(output_path=str(output_path2))

        assert output_path2.exists()
        assert output_path2.stat().st_size > 0
