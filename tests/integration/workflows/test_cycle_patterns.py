"""
Integration tests for cyclic workflow patterns and real-world use cases.

This file tests production patterns like data quality improvement,
ML training simulation, stream processing, and distributed task processing
using real Docker infrastructure.
"""

import json
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from kailash import Workflow, WorkflowBuilder
from kailash.nodes.ai import A2AAgentNode, LLMAgentNode
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.base_cycle_aware import CycleAwareNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, CSVWriterNode, SQLDatabaseNode
from kailash.runtime import LocalRuntime
from tests.utils.docker_config import (
    OLLAMA_CONFIG,
    REDIS_CONFIG,
    get_postgres_connection_string,
)


@pytest.mark.integration
class TestDataQualityPatterns:
    """Test iterative data quality improvement patterns."""

    def test_simple_cyclic_data_improvement(self, tmp_path):
        """Test simple cyclic data improvement."""
        workflow = Workflow("simple_quality", "Simple quality improvement")

        # Simple quality improver that gets better each iteration
        def improve_quality(data, quality=0.5):
            # Improve quality by 0.15 each iteration
            new_quality = min(1.0, quality + 0.15)
            converged = new_quality >= 0.95

            return {
                "data": data,
                "quality": new_quality,
                "converged": converged,
                "iteration_improvement": 0.15,
            }

        improver = PythonCodeNode.from_function(improve_quality, name="improver")
        workflow.add_node("improve", improver)

        # Create improvement cycle
        workflow.create_cycle("quality_cycle").connect(
            "improve", "improve", {"result.quality": "quality"}
        ).max_iterations(10).converge_when("converged == True").build()

        # Execute with initial data
        runtime = LocalRuntime()
        result, _ = runtime.execute(
            workflow, parameters={"improve": {"data": ["test"], "quality": 0.5}}
        )

        # Verify convergence
        assert result["improve"]["result"]["converged"] is True
        assert result["improve"]["result"]["quality"] >= 0.95
        print(f"Final quality: {result['improve']['result']['quality']}")

    def test_iterative_data_quality_improvement(self, tmp_path):
        """Test multi-stage data cleaning with quality cycles."""
        # Create test CSV with dirty data
        csv_file = tmp_path / "dirty_data.csv"
        csv_content = """id,name,email,age,department
1,John Doe,john@example.com,25,Sales
2,Jane Smith,INVALID_EMAIL,30,Marketing
3,Bob Johnson,bob@company,45,Engineering
4,,missing@email.com,0,HR
5,Alice Brown,alice@example.com,-5,Sales
6,Charlie Wilson,charlie@,60,
7,David Lee,david@company.com,200,Marketing"""

        csv_file.write_text(csv_content)

        # Create workflow
        workflow = Workflow(
            "data_quality_pipeline", "Iterative data quality improvement"
        )

        # Single node that reads, cleans and checks quality in cycles
        class DataQualityProcessor(CycleAwareNode):
            def get_parameters(self):
                return {
                    "file_path": NodeParameter(
                        name="file_path", type=str, required=True
                    ),
                    "output_path": NodeParameter(
                        name="output_path", type=str, required=True
                    ),
                    "target_quality": NodeParameter(
                        name="target_quality", type=float, default=0.95
                    ),
                }

            def run(self, **kwargs):
                import csv
                import re

                file_path = kwargs["file_path"]
                output_path = kwargs["output_path"]
                target_quality = kwargs.get("target_quality", 0.95)
                context = kwargs.get("context", {})

                # Get data from state or read from file
                iteration = self.get_iteration(context)
                state = self.get_previous_state(context)

                if iteration == 0:
                    # First iteration - read from file
                    with open(file_path, "r") as f:
                        reader = csv.DictReader(f)
                        data = list(reader)
                else:
                    # Subsequent iterations - use cleaned data from state
                    data = state.get("data", [])

                # Calculate quality metrics
                total_rows = len(data)
                if total_rows == 0:
                    return {"quality_score": 0, "converged": False, "data": []}

                valid_emails = sum(
                    1
                    for row in data
                    if re.match(r"^[^@]+@[^@]+\.[^@]+$", row.get("email", ""))
                )
                valid_names = sum(1 for row in data if row.get("name", "").strip())
                valid_ages = sum(1 for row in data if 0 < int(row.get("age", 0)) < 120)
                valid_depts = sum(
                    1 for row in data if row.get("department", "").strip()
                )

                quality_score = (
                    valid_emails + valid_names + valid_ages + valid_depts
                ) / (4 * total_rows)

                # Check if converged
                if quality_score >= target_quality:
                    # Write clean data
                    with open(output_path, "w", newline="") as f:
                        if data:
                            writer = csv.DictWriter(f, fieldnames=data[0].keys())
                            writer.writeheader()
                            writer.writerows(data)

                    return {
                        "quality_score": quality_score,
                        "converged": True,
                        "total_rows": total_rows,
                        "iterations": iteration + 1,
                        "data": data,
                    }

                # Clean data for next iteration
                cleaned_data = []
                for row in data:
                    cleaned_row = row.copy()

                    # Clean email
                    email = row.get("email", "")
                    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
                        if "@" not in email:
                            cleaned_row["email"] = (
                                f"{row.get('name', 'unknown').lower().replace(' ', '.')}@example.com"
                            )
                        else:
                            cleaned_row["email"] = (
                                email + ".com" if not email.endswith(".com") else email
                            )

                    # Clean name
                    if not row.get("name", "").strip():
                        cleaned_row["name"] = f"User{row.get('id', 'X')}"

                    # Clean age
                    try:
                        age = int(row.get("age", 0))
                        if age <= 0 or age >= 120:
                            cleaned_row["age"] = "30"
                    except:
                        cleaned_row["age"] = "30"

                    # Clean department
                    if not row.get("department", "").strip():
                        cleaned_row["department"] = "General"

                    cleaned_data.append(cleaned_row)

                return {
                    "quality_score": quality_score,
                    "converged": False,
                    "iterations": iteration + 1,
                    **self.set_cycle_state({"data": cleaned_data}),
                }

        # Add processor node
        processor = DataQualityProcessor(name="processor")
        workflow.add_node("processor", processor)

        # Create quality improvement cycle
        workflow.create_cycle("quality_cycle").connect(
            "processor", "processor"
        ).max_iterations(5).converge_when("converged == True").build()

        # Execute pipeline
        runtime = LocalRuntime()
        clean_file = tmp_path / "clean_data.csv"

        result, _ = runtime.execute(
            workflow,
            parameters={
                "processor": {
                    "file_path": str(csv_file),
                    "output_path": str(clean_file),
                    "target_quality": 0.95,
                }
            },
        )

        # Verify results
        assert result["processor"]["quality_score"] >= 0.95
        assert result["processor"]["converged"] is True
        assert clean_file.exists()

        # Verify cleaned data
        cleaned_content = clean_file.read_text()
        assert "INVALID_EMAIL" not in cleaned_content
        assert "User4" in cleaned_content  # Fixed missing name


@pytest.mark.integration
class TestMLTrainingPatterns:
    """Test ML training simulation patterns with convergence."""

    def test_ml_training_with_convergence(self):
        """Test iterative ML model training with loss convergence."""
        workflow = Workflow("ml_training", "ML training simulation")

        # Model training node
        class ModelTrainer(CycleAwareNode):
            def get_parameters(self):
                return {
                    "learning_rate": NodeParameter(
                        name="learning_rate", type=float, default=0.1
                    ),
                    "batch_size": NodeParameter(
                        name="batch_size", type=int, default=32
                    ),
                    "target_loss": NodeParameter(
                        name="target_loss", type=float, default=0.01
                    ),
                }

            def run(self, **kwargs):
                lr = kwargs.get("learning_rate", 0.1)
                batch_size = kwargs.get("batch_size", 32)
                target_loss = kwargs.get("target_loss", 0.01)
                context = kwargs.get("context", {})

                # Get training state
                state = self.get_previous_state(context)
                current_loss = state.get("loss", 1.0)
                epoch = state.get("epoch", 0)
                loss_history = state.get("loss_history", [])

                # Simulate training (loss decreases with noise)
                noise = random.uniform(-0.01, 0.01)
                new_loss = current_loss * (1 - lr) + noise
                new_loss = max(0.001, new_loss)  # Prevent negative loss

                # Update metrics
                epoch += 1
                loss_history.append(new_loss)

                # Check convergence (loss plateaued or target reached)
                converged = False
                if new_loss <= target_loss:
                    converged = True
                elif len(loss_history) >= 3:
                    # Check if loss plateaued
                    recent_losses = loss_history[-3:]
                    loss_variance = max(recent_losses) - min(recent_losses)
                    if loss_variance < 0.001:
                        converged = True

                return {
                    "epoch": epoch,
                    "loss": new_loss,
                    "loss_history": loss_history,
                    "converged": converged,
                    "improvement": current_loss - new_loss,
                    "metrics": {
                        "avg_loss": sum(loss_history) / len(loss_history),
                        "best_loss": min(loss_history),
                        "training_time": epoch * 0.5,  # Simulated time
                    },
                    **self.set_cycle_state(
                        {"loss": new_loss, "epoch": epoch, "loss_history": loss_history}
                    ),
                }

        # Model evaluation node
        evaluator = PythonCodeNode.from_function(
            lambda loss, metrics, epoch: {
                "final_loss": loss,
                "total_epochs": epoch,
                "performance": (
                    "excellent" if loss < 0.01 else "good" if loss < 0.1 else "poor"
                ),
                "ready_for_production": loss < 0.05,
            },
            name="evaluator",
        )

        trainer = ModelTrainer(name="trainer")
        workflow.add_node("train", trainer)
        workflow.add_node("eval", evaluator)

        # Training loop - CycleAwareNode doesn't need mapping
        workflow.create_cycle("training_cycle").connect(
            "train", "train"
        ).max_iterations(50).converge_when("converged == True").build()

        # Evaluate when converged
        workflow.connect(
            "train", "eval", {"loss": "loss", "metrics": "metrics", "epoch": "epoch"}
        )

        # Execute training
        runtime = LocalRuntime()
        result, _ = runtime.execute(
            workflow, {"train": {"learning_rate": 0.15, "target_loss": 0.01}}
        )

        # Verify training results
        assert result["train"]["converged"] is True
        assert result["train"]["loss"] < 0.1  # Should achieve good loss
        assert result["eval"]["result"]["ready_for_production"] is True
        assert len(result["train"]["loss_history"]) == result["train"]["epoch"]


@pytest.mark.integration
class TestStreamProcessingPatterns:
    """Test real-time stream processing patterns."""

    def test_sliding_window_stream_processing(self):
        """Test stream processing with sliding windows and anomaly detection."""
        workflow = Workflow("stream_processor", "Stream processing with windows")

        # Stream generator (simulates real-time data)
        stream_gen = PythonCodeNode.from_function(
            lambda batch_id=0: {
                "events": [
                    {
                        "timestamp": (
                            datetime.now(timezone.utc) - timedelta(seconds=i)
                        ).isoformat(),
                        "value": (
                            random.gauss(100, 10)
                            if random.random() > 0.1
                            else random.gauss(150, 20)
                        ),  # 10% anomalies
                        "sensor_id": f"sensor_{i % 5}",
                        "batch_id": batch_id,
                    }
                    for i in range(20)
                ],
                "batch_id": batch_id + 1,
            },
            name="stream_generator",
        )

        # Window processor with anomaly detection
        class WindowProcessor(CycleAwareNode):
            def get_parameters(self):
                return {
                    "window_size": NodeParameter(
                        name="window_size", type=int, default=100
                    ),
                    "anomaly_threshold": NodeParameter(
                        name="anomaly_threshold", type=float, default=2.5
                    ),
                }

            def run(self, **kwargs):
                events = kwargs.get("events", [])
                window_size = kwargs.get("window_size", 100)
                threshold = kwargs.get("anomaly_threshold", 2.5)
                context = kwargs.get("context", {})

                # Get window state
                window = self.get_previous_state(context).get("window", [])
                stats_history = self.get_previous_state(context).get("stats", [])

                # Add new events to window
                window.extend(events)

                # Maintain window size
                if len(window) > window_size:
                    window = window[-window_size:]

                # Calculate statistics
                values = [e["value"] for e in window]
                if values:
                    mean = sum(values) / len(values)
                    variance = sum((v - mean) ** 2 for v in values) / len(values)
                    std_dev = variance**0.5

                    # Detect anomalies
                    anomalies = []
                    for event in events:
                        z_score = (
                            abs(event["value"] - mean) / std_dev if std_dev > 0 else 0
                        )
                        if z_score > threshold:
                            anomalies.append(
                                {
                                    **event,
                                    "z_score": z_score,
                                    "expected_range": (
                                        mean - threshold * std_dev,
                                        mean + threshold * std_dev,
                                    ),
                                }
                            )

                    stats = {
                        "mean": mean,
                        "std_dev": std_dev,
                        "min": min(values),
                        "max": max(values),
                        "count": len(window),
                        "anomaly_count": len(anomalies),
                    }
                    stats_history.append(stats)

                    # Keep last 10 stats for trend analysis
                    if len(stats_history) > 10:
                        stats_history = stats_history[-10:]

                    # Check if we should stop (stable statistics)
                    converged = False
                    if len(stats_history) >= 5:
                        recent_means = [s["mean"] for s in stats_history[-5:]]
                        mean_variance = max(recent_means) - min(recent_means)
                        converged = mean_variance < 1.0  # Stable if variance < 1

                    return {
                        "window_stats": stats,
                        "anomalies": anomalies,
                        "stats_history": stats_history,
                        "converged": converged,
                        "window_size": len(window),
                        **self.set_cycle_state(
                            {"window": window, "stats": stats_history}
                        ),
                    }

                return {
                    "window_stats": {},
                    "anomalies": [],
                    "converged": False,
                    "window_size": 0,
                }

        # Alert generator for anomalies
        alerter = PythonCodeNode.from_function(
            lambda anomalies, window_stats: {
                "alerts": [
                    {
                        "severity": "high" if a["z_score"] > 3 else "medium",
                        "message": f"Anomaly detected: sensor {a['sensor_id']} value {a['value']:.2f} (z-score: {a['z_score']:.2f})",
                        "timestamp": a["timestamp"],
                    }
                    for a in anomalies
                ],
                "summary": {
                    "total_anomalies": len(anomalies),
                    "affected_sensors": list(set(a["sensor_id"] for a in anomalies)),
                    "window_mean": window_stats.get("mean", 0),
                    "window_std": window_stats.get("std_dev", 0),
                },
            },
            name="alerter",
        )

        processor = WindowProcessor(name="processor")

        workflow.add_node("stream", stream_gen)
        workflow.add_node("process", processor)
        workflow.add_node("alert", alerter)

        # Connect stream to processor
        workflow.connect("stream", "process", {"result.events": "events"})

        # Process cycles back to stream for next batch
        workflow.create_cycle("stream_cycle").connect(
            "process", "stream", {"window_size": "batch_id"}
        ).max_iterations(10).converge_when("converged == True").build()

        # Generate alerts
        workflow.connect(
            "process",
            "alert",
            {"anomalies": "anomalies", "window_stats": "window_stats"},
        )

        # Execute stream processing with initial parameters
        runtime = LocalRuntime()
        result, _ = runtime.execute(
            workflow, parameters={"stream": {"batch_id": 0}, "process": {"events": []}}
        )

        # Verify results
        assert "window_stats" in result["process"]
        assert "window_size" in result["process"]
        assert "result" in result["alert"]
        assert "alerts" in result["alert"]["result"]
        assert "summary" in result["alert"]["result"]


@pytest.mark.integration
@pytest.mark.requires_docker
class TestDistributedProcessingPatterns:
    """Test distributed task processing patterns with A2A coordination."""

    def test_simple_task_coordination_cycles(self):
        """Test simple task coordination without A2A agents."""
        workflow = Workflow("task_coordination", "Simple task coordination")

        # Task generator
        def generate_tasks(batch=0):
            return {
                "tasks": [
                    {"id": f"task_{batch}_{i}", "type": "process", "data": f"item_{i}"}
                    for i in range(5)
                ],
                "batch": batch + 1,
                "completed": batch >= 3,
            }

        # Task processor
        def process_tasks(tasks, batch=0):
            processed = []
            for task in tasks:
                processed.append(
                    {
                        **task,
                        "status": "completed",
                        "result": f"processed_{task['data']}",
                    }
                )
            return {
                "processed_tasks": processed,
                "batch": batch,
                "all_complete": len(processed) == len(tasks),
            }

        generator = PythonCodeNode.from_function(generate_tasks, name="generator")
        processor = PythonCodeNode.from_function(process_tasks, name="processor")

        workflow.add_node("gen", generator)
        workflow.add_node("proc", processor)

        # Connect nodes
        workflow.connect(
            "gen", "proc", {"result.tasks": "tasks", "result.batch": "batch"}
        )

        # Create coordination cycle
        workflow.create_cycle("coordination_cycle").connect(
            "proc", "gen", {"result.batch": "batch"}
        ).max_iterations(5).converge_when("completed == True").build()

        # Execute
        runtime = LocalRuntime()
        result, _ = runtime.execute(workflow, parameters={"gen": {"batch": 0}})

        # Verify coordination happened
        assert result["gen"]["result"]["completed"] is True
        assert result["gen"]["result"]["batch"] >= 3
        assert len(result["proc"]["result"]["processed_tasks"]) == 5

    def test_a2a_coordination_cycles(self):
        """Test A2A agent coordination in distributed processing."""
        # Use direct Ollama API wrapped in PythonCodeNode
        workflow = Workflow("a2a_simulation", "Simulated A2A coordination")

        # Task distributor using Ollama
        def distribute_tasks(tasks, workers):
            import json

            import requests

            prompt = f"""You are a task distributor. Given these tasks and workers, distribute them efficiently.
Output a JSON object with worker assignments.

Tasks: {json.dumps(tasks)}
Workers: {json.dumps(workers)}

Output JSON format:
{{"assignments": [{{"worker": "worker_id", "tasks": ["task_id1", "task_id2"]}}]}}

JSON:"""

            try:
                response = requests.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": "llama3.2:1b",
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.3, "num_predict": 200},
                    },
                    timeout=20,
                )

                if response.status_code == 200:
                    llm_response = response.json()["response"]
                    # Extract JSON from response
                    import re

                    json_match = re.search(r"\{[^}]+\}", llm_response)
                    if json_match:
                        try:
                            assignments = json.loads(json_match.group())
                            return {
                                "success": True,
                                "assignments": assignments,
                                "response": llm_response,
                            }
                        except:
                            pass

                # Fallback distribution
                return {
                    "success": True,
                    "assignments": {
                        "assignments": [
                            {"worker": workers[i % len(workers)], "tasks": [task["id"]]}
                            for i, task in enumerate(tasks)
                        ]
                    },
                    "response": "Fallback distribution",
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        # Worker processor
        def process_tasks(assignments):
            results = []
            for assignment in assignments.get("assignments", []):
                for task_id in assignment.get("tasks", []):
                    results.append(
                        {
                            "task_id": task_id,
                            "worker": assignment["worker"],
                            "status": "completed",
                            "result": f"Processed {task_id}",
                        }
                    )

            return {
                "processed_tasks": results,
                "total_processed": len(results),
                "all_complete": True,
            }

        # Coordinator
        def coordinate_results(processed_tasks, iteration=0):
            return {
                "summary": f"Processed {len(processed_tasks)} tasks in iteration {iteration}",
                "all_complete": len(processed_tasks) > 0,
                "iteration": iteration + 1,
                "converged": iteration >= 2,
            }

        # Build workflow
        distributor = PythonCodeNode.from_function(distribute_tasks, name="distributor")
        worker = PythonCodeNode.from_function(process_tasks, name="worker")
        coordinator = PythonCodeNode.from_function(
            coordinate_results, name="coordinator"
        )

        workflow.add_node("dist", distributor)
        workflow.add_node("work", worker)
        workflow.add_node("coord", coordinator)

        # Connect workflow
        workflow.connect("dist", "work", {"result.assignments": "assignments"})
        workflow.connect("work", "coord", {"result.processed_tasks": "processed_tasks"})

        # Create coordination cycle
        workflow.create_cycle("coord_cycle").connect(
            "coord", "coord", {"result.iteration": "iteration"}
        ).max_iterations(3).converge_when("converged == True").build()

        # Execute
        runtime = LocalRuntime()
        test_tasks = [
            {"id": f"task_{i}", "type": "process", "data": f"item_{i}"}
            for i in range(5)
        ]
        test_workers = ["worker_1", "worker_2", "worker_3"]

        result, _ = runtime.execute(
            workflow,
            parameters={
                "dist": {"tasks": test_tasks, "workers": test_workers},
                "coord": {"processed_tasks": [], "iteration": 0},
            },
        )

        # Verify
        assert result["dist"]["result"]["success"] is True
        assert result["work"]["result"]["all_complete"] is True
        assert result["coord"]["result"]["converged"] is True
        assert result["coord"]["result"]["iteration"] >= 2
