"""Performance and load tests for the Kailash SDK."""

import time
import json
import psutil
import threading
from pathlib import Path
from typing import Dict, List, Any
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from datetime import datetime

import pytest
import pandas as pd
import numpy as np

from kailash.runtime.local import LocalRuntime
from kailash.runtime.runner import WorkflowRunner
from kailash.workflow import Workflow, WorkflowBuilder
from kailash.nodes.base import NodeStatus, DataFormat, InputType, OutputType
from kailash.tracking.manager import TaskTracker
from kailash.tracking.storage.database import DatabaseStorage


class TestPerformance:
    """Test performance and scalability of the SDK."""
    
    def test_large_workflow_construction(self, temp_data_dir: Path):
        """Test building and executing large workflows."""
        builder = WorkflowBuilder()
        
        # Create a large workflow with many nodes
        node_count = 100
        nodes = []
        
        start_time = time.time()
        
        # Create input node
        input_node = builder.add_node(
            "DataGenerator",
            "input",
            inputs={"size": InputType(value=1000)},
            outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
        )
        nodes.append(input_node)
        
        # Create processing chain
        for i in range(node_count - 2):
            processor = builder.add_node(
                f"Processor{i}",
                f"processor_{i}",
                inputs={"data": InputType(format=DataFormat.DATAFRAME)},
                outputs={"processed": OutputType(format=DataFormat.DATAFRAME)}
            )
            
            # Connect to previous node
            if i == 0:
                builder.add_connection(input_node, "data", processor, "data")
            else:
                builder.add_connection(nodes[-1], "processed", processor, "data")
            
            nodes.append(processor)
        
        # Create output node
        output_node = builder.add_node(
            "DataWriter",
            "output",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "path": InputType(value=str(temp_data_dir / "output.csv"))
            },
            outputs={"result": OutputType(format=DataFormat.TEXT)}
        )
        builder.add_connection(nodes[-1], "processed", output_node, "data")
        
        workflow = builder.build("large_workflow")
        construction_time = time.time() - start_time
        
        # Verify workflow
        assert len(workflow.graph.nodes()) == node_count
        assert construction_time < 5.0  # Should be fast
        
        # Execute workflow
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        execution_start = time.time()
        result = runner.run(workflow)
        execution_time = time.time() - execution_start
        
        assert result.status == NodeStatus.COMPLETED
        print(f"Large workflow ({node_count} nodes) - Construction: {construction_time:.3f}s, Execution: {execution_time:.3f}s")
    
    def test_parallel_workflow_execution(self, temp_data_dir: Path):
        """Test parallel execution of multiple workflows."""
        # Create test workflow
        def create_test_workflow(index: int) -> WorkflowGraph:
            builder = WorkflowBuilder()
            
            reader = builder.add_node(
                "DataGenerator",
                f"reader_{index}",
                inputs={"size": InputType(value=1000)},
                outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
            )
            
            processor = builder.add_node(
                "DataProcessor",
                f"processor_{index}",
                inputs={"data": InputType(format=DataFormat.DATAFRAME)},
                outputs={"processed": OutputType(format=DataFormat.DATAFRAME)}
            )
            
            writer = builder.add_node(
                "DataWriter",
                f"writer_{index}",
                inputs={
                    "data": InputType(format=DataFormat.DATAFRAME),
                    "path": InputType(value=str(temp_data_dir / f"output_{index}.csv"))
                },
                outputs={"result": OutputType(format=DataFormat.TEXT)}
            )
            
            builder.add_connection(reader, "data", processor, "data")
            builder.add_connection(processor, "processed", writer, "data")
            
            return builder.build(f"parallel_workflow_{index}")
        
        # Create multiple workflows
        workflow_count = 10
        workflows = [create_test_workflow(i) for i in range(workflow_count)]
        
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Execute workflows in parallel
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(runner.run, wf) for wf in workflows]
            results = [f.result() for f in futures]
        
        parallel_time = time.time() - start_time
        
        # Execute workflows sequentially for comparison
        start_time = time.time()
        sequential_results = []
        for workflow in workflows:
            result = runner.run(workflow)
            sequential_results.append(result)
        
        sequential_time = time.time() - start_time
        
        # Verify results
        assert all(r.status == NodeStatus.COMPLETED for r in results)
        assert all(r.status == NodeStatus.COMPLETED for r in sequential_results)
        
        speedup = sequential_time / parallel_time
        print(f"Parallel execution speedup: {speedup:.2f}x (Sequential: {sequential_time:.3f}s, Parallel: {parallel_time:.3f}s)")
        assert speedup > 1.5  # Should have significant speedup
    
    def test_large_data_processing(self, temp_data_dir: Path):
        """Test processing large datasets through workflows."""
        # Create large dataset
        rows = 1_000_000
        data = pd.DataFrame({
            'id': range(rows),
            'value': np.random.rand(rows),
            'category': np.random.choice(['A', 'B', 'C', 'D'], rows)
        })
        
        large_file = temp_data_dir / "large_data.csv"
        data.to_csv(large_file, index=False)
        
        # Create workflow for processing large data
        builder = WorkflowBuilder()
        
        reader = builder.add_node(
            "CSVFileReader",
            "reader",
            inputs={"path": InputType(value=str(large_file))},
            outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        filter_node = builder.add_node(
            "DataFilter",
            "filter",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "condition": InputType(value="value > 0.5")
            },
            outputs={"filtered": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        aggregator = builder.add_node(
            "DataAggregator",
            "aggregator",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "group_by": InputType(value=["category"]),
                "agg_func": InputType(value="mean")
            },
            outputs={"aggregated": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        writer = builder.add_node(
            "CSVFileWriter",
            "writer",
            inputs={
                "data": InputType(format=DataFormat.DATAFRAME),
                "path": InputType(value=str(temp_data_dir / "aggregated_results.csv"))
            },
            outputs={"result": OutputType(format=DataFormat.TEXT)}
        )
        
        builder.add_connection(reader, "data", filter_node, "data")
        builder.add_connection(filter_node, "filtered", aggregator, "data")
        builder.add_connection(aggregator, "aggregated", writer, "data")
        
        workflow = builder.build("large_data_workflow")
        
        # Execute workflow and measure performance
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        # Monitor system resources
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        start_time = time.time()
        result = runner.run(workflow)
        execution_time = time.time() - start_time
        
        peak_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_used = peak_memory - initial_memory
        
        assert result.status == NodeStatus.COMPLETED
        print(f"Large data processing - Rows: {rows:,}, Time: {execution_time:.3f}s, Memory: {memory_used:.1f}MB")
        
        # Verify results
        results_df = pd.read_csv(temp_data_dir / "aggregated_results.csv")
        assert len(results_df) == 4  # 4 categories
    
    def test_concurrent_node_execution(self, temp_data_dir: Path):
        """Test concurrent execution of independent nodes."""
        builder = WorkflowBuilder()
        
        # Create workflow with parallel branches
        input_node = builder.add_node(
            "DataGenerator",
            "input",
            inputs={"size": InputType(value=10000)},
            outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        # Create 5 parallel processing branches
        parallel_nodes = []
        for i in range(5):
            processor = builder.add_node(
                f"Processor{i}",
                f"parallel_processor_{i}",
                inputs={
                    "data": InputType(format=DataFormat.DATAFRAME),
                    "operation": InputType(value=f"operation_{i}")
                },
                outputs={f"result_{i}": OutputType(format=DataFormat.DATAFRAME)}
            )
            builder.add_connection(input_node, "data", processor, "data")
            parallel_nodes.append(processor)
        
        # Create combiner node
        combiner = builder.add_node(
            "DataCombiner",
            "combiner",
            inputs={
                f"input_{i}": InputType(format=DataFormat.DATAFRAME)
                for i in range(5)
            },
            outputs={"combined": OutputType(format=DataFormat.DATAFRAME)}
        )
        
        for i, node in enumerate(parallel_nodes):
            builder.add_connection(node, f"result_{i}", combiner, f"input_{i}")
        
        workflow = builder.build("concurrent_nodes_workflow")
        
        # Execute with concurrent runtime
        runtime = LocalRuntime(max_workers=5)
        runner = WorkflowRunner(runtime=runtime)
        
        start_time = time.time()
        result = runner.run(workflow)
        concurrent_time = time.time() - start_time
        
        # Execute with single-threaded runtime for comparison
        single_runtime = LocalRuntime(max_workers=1)
        single_runner = WorkflowRunner(runtime=single_runtime)
        
        start_time = time.time()
        single_result = runner.run(workflow)
        single_time = time.time() - start_time
        
        assert result.status == NodeStatus.COMPLETED
        assert single_result.status == NodeStatus.COMPLETED
        
        speedup = single_time / concurrent_time
        print(f"Concurrent node execution speedup: {speedup:.2f}x")
    
    def test_memory_efficiency(self, temp_data_dir: Path):
        """Test memory efficiency with large workflows."""
        import gc
        
        # Create workflow that processes data in stages
        builder = WorkflowBuilder()
        
        # Create chain of memory-intensive operations
        nodes = []
        for i in range(10):
            if i == 0:
                node = builder.add_node(
                    "DataGenerator",
                    f"generator_{i}",
                    inputs={"size": InputType(value=100000)},
                    outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
                )
            else:
                node = builder.add_node(
                    "MemoryIntensiveProcessor",
                    f"processor_{i}",
                    inputs={"data": InputType(format=DataFormat.DATAFRAME)},
                    outputs={"processed": OutputType(format=DataFormat.DATAFRAME)}
                )
                prev_output = "data" if i == 1 else "processed"
                builder.add_connection(nodes[-1], prev_output, node, "data")
            
            nodes.append(node)
        
        workflow = builder.build("memory_test_workflow")
        
        # Monitor memory usage during execution
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        process = psutil.Process()
        memory_snapshots = []
        
        def monitor_memory():
            while getattr(monitor_memory, 'running', True):
                memory_mb = process.memory_info().rss / 1024 / 1024
                memory_snapshots.append(memory_mb)
                time.sleep(0.1)
        
        # Start memory monitoring
        monitor_thread = threading.Thread(target=monitor_memory)
        monitor_memory.running = True
        monitor_thread.start()
        
        # Execute workflow
        gc.collect()
        initial_memory = process.memory_info().rss / 1024 / 1024
        
        result = runner.run(workflow)
        
        # Stop monitoring
        monitor_memory.running = False
        monitor_thread.join()
        
        # Analyze memory usage
        peak_memory = max(memory_snapshots)
        final_memory = process.memory_info().rss / 1024 / 1024
        memory_delta = peak_memory - initial_memory
        
        assert result.status == NodeStatus.COMPLETED
        print(f"Memory usage - Initial: {initial_memory:.1f}MB, Peak: {peak_memory:.1f}MB, Final: {final_memory:.1f}MB")
        
        # Memory should be released after workflow completes
        gc.collect()
        time.sleep(0.5)
        post_gc_memory = process.memory_info().rss / 1024 / 1024
        assert post_gc_memory < peak_memory * 0.8  # Most memory should be freed
    
    def test_task_tracking_performance(self, temp_data_dir: Path):
        """Test performance of task tracking system."""
        # Test with database storage
        db_path = temp_data_dir / "tasks.db"
        storage = DatabaseStorage(f"sqlite:///{db_path}")
        tracker = TaskTracker(storage=storage)
        
        # Create many tasks
        task_count = 1000
        
        start_time = time.time()
        
        tasks = []
        for i in range(task_count):
            task = tracker.create_task(
                f"Task {i}",
                f"Performance test task {i}",
                metadata={
                    "index": i,
                    "category": f"cat_{i % 10}",
                    "priority": i % 3
                }
            )
            
            # Simulate task lifecycle
            task.update_status(TaskStatus.IN_PROGRESS)
            task.update_progress(50)
            task.update_status(TaskStatus.COMPLETED)
            
            tasks.append(task)
        
        creation_time = time.time() - start_time
        
        # Test retrieval performance
        start_time = time.time()
        all_tasks = tracker.get_tasks()
        retrieval_time = time.time() - start_time
        
        # Test search performance
        start_time = time.time()
        completed_tasks = tracker.search_tasks(status=TaskStatus.COMPLETED)
        search_time = time.time() - start_time
        
        # Test complex query
        start_time = time.time()
        filtered_tasks = tracker.search_tasks(
            status=TaskStatus.COMPLETED,
            metadata_filter={"category": "cat_5", "priority": 2}
        )
        complex_search_time = time.time() - start_time
        
        print(f"Task tracking performance ({task_count} tasks):")
        print(f"  Creation: {creation_time:.3f}s ({task_count/creation_time:.0f} tasks/s)")
        print(f"  Retrieval: {retrieval_time:.3f}s")
        print(f"  Simple search: {search_time:.3f}s")
        print(f"  Complex search: {complex_search_time:.3f}s")
        
        assert len(all_tasks) == task_count
        assert len(completed_tasks) == task_count
    
    def test_workflow_scalability(self, temp_data_dir: Path):
        """Test workflow scalability with increasing complexity."""
        runtime = LocalRuntime()
        runner = WorkflowRunner(runtime=runtime)
        
        results = []
        
        # Test with increasing workflow sizes
        for size in [10, 50, 100, 500]:
            builder = WorkflowBuilder()
            
            # Create workflow with 'size' nodes
            prev_node = None
            for i in range(size):
                if i == 0:
                    node = builder.add_node(
                        "DataGenerator",
                        f"node_{i}",
                        inputs={"size": InputType(value=100)},
                        outputs={"data": OutputType(format=DataFormat.JSON)}
                    )
                else:
                    node = builder.add_node(
                        "DataProcessor",
                        f"node_{i}",
                        inputs={"data": InputType(format=DataFormat.JSON)},
                        outputs={"processed": OutputType(format=DataFormat.JSON)}
                    )
                    output_key = "data" if i == 1 else "processed"
                    builder.add_connection(prev_node, output_key, node, "data")
                
                prev_node = node
            
            workflow = builder.build(f"scalability_test_{size}")
            
            # Measure execution time
            start_time = time.time()
            result = runner.run(workflow)
            execution_time = time.time() - start_time
            
            assert result.status == NodeStatus.COMPLETED
            
            results.append({
                "size": size,
                "execution_time": execution_time,
                "time_per_node": execution_time / size
            })
        
        # Analyze scalability
        print("\nWorkflow Scalability Results:")
        print("Size\tTime(s)\tTime/Node(s)")
        for r in results:
            print(f"{r['size']}\t{r['execution_time']:.3f}\t{r['time_per_node']:.4f}")
        
        # Check that time per node doesn't increase significantly
        times_per_node = [r['time_per_node'] for r in results]
        assert max(times_per_node) < min(times_per_node) * 2  # Should scale reasonably
    
    def test_concurrent_workflow_modifications(self, temp_data_dir: Path):
        """Test concurrent modifications to workflows."""
        import threading
        from queue import Queue
        
        results = Queue()
        errors = Queue()
        
        def modify_workflow(thread_id: int):
            try:
                builder = WorkflowBuilder()
                
                # Each thread creates its own workflow
                for i in range(20):
                    node = builder.add_node(
                        f"Node_{thread_id}_{i}",
                        f"node_{thread_id}_{i}",
                        inputs={"data": InputType(value=f"thread_{thread_id}")},
                        outputs={"result": OutputType(format=DataFormat.JSON)}
                    )
                    
                    if i > 0:
                        prev_node = f"node_{thread_id}_{i-1}"
                        builder.add_connection(prev_node, "result", node, "data")
                
                workflow = builder.build(f"concurrent_workflow_{thread_id}")
                results.put((thread_id, len(workflow.graph.nodes())))
                
            except Exception as e:
                errors.put((thread_id, str(e)))
        
        # Create workflows concurrently
        threads = []
        thread_count = 10
        
        start_time = time.time()
        
        for i in range(thread_count):
            thread = threading.Thread(target=modify_workflow, args=(i,))
            thread.start()
            threads.append(thread)
        
        for thread in threads:
            thread.join()
        
        concurrent_time = time.time() - start_time
        
        # Check results
        assert errors.empty(), f"Errors occurred: {list(errors.queue)}"
        
        created_workflows = []
        while not results.empty():
            thread_id, node_count = results.get()
            created_workflows.append((thread_id, node_count))
            assert node_count == 20
        
        assert len(created_workflows) == thread_count
        print(f"Concurrent workflow creation - {thread_count} workflows in {concurrent_time:.3f}s")
    
    def test_stress_test_complete_system(self, temp_data_dir: Path):
        """Comprehensive stress test of the entire system."""
        # Configuration for stress test
        workflow_count = 5
        nodes_per_workflow = 20
        data_size = 10000
        concurrent_executions = 3
        
        # Create complex workflows
        workflows = []
        
        for w in range(workflow_count):
            builder = WorkflowBuilder()
            
            # Create interconnected nodes
            nodes = []
            for n in range(nodes_per_workflow):
                if n == 0:
                    node = builder.add_node(
                        "DataGenerator",
                        f"gen_{w}_{n}",
                        inputs={"size": InputType(value=data_size)},
                        outputs={"data": OutputType(format=DataFormat.DATAFRAME)}
                    )
                elif n < nodes_per_workflow - 1:
                    node = builder.add_node(
                        "DataProcessor",
                        f"proc_{w}_{n}",
                        inputs={"data": InputType(format=DataFormat.DATAFRAME)},
                        outputs={"processed": OutputType(format=DataFormat.DATAFRAME)}
                    )
                else:
                    node = builder.add_node(
                        "DataWriter",
                        f"writer_{w}_{n}",
                        inputs={
                            "data": InputType(format=DataFormat.DATAFRAME),
                            "path": InputType(value=str(temp_data_dir / f"stress_output_{w}.csv"))
                        },
                        outputs={"result": OutputType(format=DataFormat.TEXT)}
                    )
                
                nodes.append(node)
                
                if n > 0:
                    prev_output = "data" if n == 1 else "processed"
                    builder.add_connection(nodes[n-1], prev_output, node, "data")
            
            workflows.append(builder.build(f"stress_workflow_{w}"))
        
        # Setup tracking
        storage = DatabaseStorage(f"sqlite:///{temp_data_dir}/stress_test.db")
        tracker = TaskTracker(storage=storage)
        
        # Setup runtime
        runtime = LocalRuntime(max_workers=10)
        runner = WorkflowRunner(runtime=runtime)
        
        # Monitor system resources
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024
        initial_cpu = process.cpu_percent()
        
        # Execute workflows concurrently
        start_time = time.time()
        
        with ProcessPoolExecutor(max_workers=concurrent_executions) as executor:
            futures = []
            for i in range(concurrent_executions):
                for workflow in workflows:
                    future = executor.submit(runner.run, workflow, tracker)
                    futures.append(future)
            
            results = [f.result() for f in futures]
        
        total_time = time.time() - start_time
        
        # Collect final metrics
        final_memory = process.memory_info().rss / 1024 / 1024
        peak_cpu = process.cpu_percent()
        
        # Verify results
        successful_runs = sum(1 for r in results if r.status == NodeStatus.COMPLETED)
        total_runs = len(results)
        
        # Get task statistics
        all_tasks = tracker.get_tasks()
        completed_tasks = tracker.search_tasks(status=TaskStatus.COMPLETED)
        
        print(f"\nStress Test Results:")
        print(f"Workflows: {workflow_count}, Nodes/workflow: {nodes_per_workflow}")
        print(f"Concurrent executions: {concurrent_executions}")
        print(f"Total runs: {total_runs}, Successful: {successful_runs}")
        print(f"Total time: {total_time:.3f}s")
        print(f"Memory - Initial: {initial_memory:.1f}MB, Final: {final_memory:.1f}MB")
        print(f"CPU usage peak: {peak_cpu:.1f}%")
        print(f"Total tasks tracked: {len(all_tasks)}")
        print(f"Completed tasks: {len(completed_tasks)}")
        
        assert successful_runs == total_runs
        assert len(completed_tasks) > 0