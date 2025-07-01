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
