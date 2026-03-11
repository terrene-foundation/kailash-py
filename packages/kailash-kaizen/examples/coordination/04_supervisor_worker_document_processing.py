"""
Example 4: Supervisor-Worker Pattern - Real-World Document Processing

This example demonstrates a real-world use case: parallel document processing
pipeline using the SupervisorWorkerPattern. The supervisor coordinates multiple
workers to process documents efficiently.

Use Case:
A company receives 100 customer feedback documents daily that need:
1. Sentiment analysis
2. Key topic extraction
3. Action item identification
4. Priority scoring

Learning Objectives:
- Real-world parallel processing
- Document pipeline orchestration
- Result aggregation and reporting
- Performance optimization with workers

Estimated time: 15 minutes
"""

import time
from datetime import datetime
from typing import Any, Dict, List

from kaizen.agents.coordination import create_supervisor_worker_pattern

# Simulated document dataset
SAMPLE_DOCUMENTS = [
    {
        "id": "DOC-001",
        "source": "email",
        "content": "The new product feature is amazing! It solved our workflow problem perfectly. Thank you!",
        "received": "2025-10-01 09:15",
    },
    {
        "id": "DOC-002",
        "source": "support_ticket",
        "content": "Having issues with the login process. It keeps timing out after 30 seconds. Very frustrating.",
        "received": "2025-10-01 09:22",
    },
    {
        "id": "DOC-003",
        "source": "survey",
        "content": "The customer service team was helpful, but the response time could be improved. Waited 2 hours.",
        "received": "2025-10-01 09:45",
    },
    {
        "id": "DOC-004",
        "source": "email",
        "content": "URGENT: Production database is experiencing high latency. Multiple customers affected.",
        "received": "2025-10-01 10:03",
    },
    {
        "id": "DOC-005",
        "source": "review",
        "content": "Good product overall. Documentation could be more detailed. Integration was smooth.",
        "received": "2025-10-01 10:15",
    },
    {
        "id": "DOC-006",
        "source": "support_ticket",
        "content": "Unable to export reports. Getting error 500. Need this fixed ASAP for quarterly review.",
        "received": "2025-10-01 10:28",
    },
    {
        "id": "DOC-007",
        "source": "email",
        "content": "Love the new dashboard! Metrics are clear and actionable. Great work by the team.",
        "received": "2025-10-01 10:45",
    },
    {
        "id": "DOC-008",
        "source": "survey",
        "content": "Performance has degraded since last update. Page load times increased significantly.",
        "received": "2025-10-01 11:02",
    },
]


def create_document_batch(start_idx: int, batch_size: int) -> List[Dict[str, Any]]:
    """Create a batch of documents for processing."""
    # Cycle through sample documents
    batch = []
    for i in range(batch_size):
        doc_idx = (start_idx + i) % len(SAMPLE_DOCUMENTS)
        doc = SAMPLE_DOCUMENTS[doc_idx].copy()
        doc["id"] = f"DOC-{start_idx + i + 1:03d}"  # Unique ID
        batch.append(doc)
    return batch


def main():
    print("=" * 70)
    print("Real-World Document Processing Pipeline")
    print("Supervisor-Worker Pattern Implementation")
    print("=" * 70)
    print()

    # ==================================================================
    # STEP 1: Configure Pipeline
    # ==================================================================
    print("Step 1: Pipeline Configuration")
    print("-" * 70)

    # Pipeline parameters
    total_documents = 24  # Process 24 documents
    num_workers = 4  # Use 4 workers for parallel processing
    batch_size = 6  # 6 documents per worker batch

    print("Pipeline Parameters:")
    print(f"  - Total documents: {total_documents}")
    print(f"  - Workers: {num_workers}")
    print(f"  - Documents per task: {batch_size}")
    print(f"  - Expected tasks: {total_documents // batch_size}")
    print()

    # ==================================================================
    # STEP 2: Create Processing Pattern
    # ==================================================================
    print("Step 2: Creating document processing pattern...")
    print("-" * 70)

    # Create pattern optimized for document processing
    # - Use GPT-4 for supervisor (better at delegation)
    # - Use GPT-3.5-turbo for workers (faster, cost-effective)
    pattern = create_supervisor_worker_pattern(
        num_workers=num_workers,
        supervisor_config={
            "model": "gpt-4",
            "temperature": 0.2,  # Low temp for consistent delegation
            "max_tokens": 2000,
        },
        worker_config={
            "model": "gpt-3.5-turbo",
            "temperature": 0.5,  # Balanced for analysis
            "max_tokens": 1500,
        },
        coordinator_config={
            "model": "gpt-3.5-turbo",
            "temperature": 0.1,  # Very low for accurate monitoring
        },
    )

    print("✓ Pattern created successfully!")
    print(f"  - Supervisor: {pattern.supervisor.agent_id} (GPT-4)")
    print(f"  - Workers: {len(pattern.workers)} x GPT-3.5-turbo")
    print(f"  - Coordinator: {pattern.coordinator.agent_id}")
    print()

    # ==================================================================
    # STEP 3: Prepare Document Batches
    # ==================================================================
    print("Step 3: Preparing document batches...")
    print("-" * 70)

    # Create document batches
    all_documents = create_document_batch(0, total_documents)

    print(f"✓ Prepared {len(all_documents)} documents")
    print()

    # Preview sample documents
    print("Sample Documents:")
    for doc in all_documents[:3]:
        print(f"  [{doc['id']}] ({doc['source']})")
        print(f"    {doc['content'][:60]}...")
        print()

    # ==================================================================
    # STEP 4: Delegate Processing Tasks
    # ==================================================================
    print("Step 4: Delegating processing tasks to workers...")
    print("-" * 70)

    # Create processing request
    processing_request = f"""
    Process {total_documents} customer feedback documents to extract:
    1. Sentiment (positive/negative/neutral)
    2. Key topics and themes
    3. Action items or issues
    4. Priority level (high/medium/low)

    Each worker should process {batch_size} documents in their batch.
    """

    start_time = time.time()

    # Delegate to workers
    num_tasks = total_documents // batch_size
    tasks = pattern.delegate(processing_request, num_tasks=num_tasks)

    print(f"✓ Delegated {len(tasks)} tasks!")
    print()

    # Show task distribution
    for i, task in enumerate(tasks, 1):
        print(f"Task {i}:")
        print(f"  - Assigned to: {task['assigned_to']}")
        print(f"  - Documents to process: {batch_size}")
        print(f"  - Request ID: {task['request_id']}")
        print()

    # ==================================================================
    # STEP 5: Workers Process Documents in Parallel
    # ==================================================================
    print("Step 5: Workers processing documents...")
    print("-" * 70)

    request_id = tasks[0]["request_id"]

    # Simulate parallel worker execution
    # In production, workers would run concurrently (threads/processes/async)
    print("Worker Execution (simulated parallel):")
    print()

    for worker_idx, worker in enumerate(pattern.workers):
        assigned_tasks = worker.get_assigned_tasks()

        if assigned_tasks:
            print(f"{worker.agent_id}: Processing {len(assigned_tasks)} batch(es)...")

            for task in assigned_tasks:
                # Simulate document processing
                # In real scenario, worker would:
                # 1. Read documents from storage
                # 2. Run sentiment analysis
                # 3. Extract topics
                # 4. Identify action items
                # 5. Calculate priority

                result = worker.execute_task(task)

                if result:
                    print(f"  ✓ Batch completed: {batch_size} documents processed")

            print()

    processing_time = time.time() - start_time
    print(f"✓ All workers finished in {processing_time:.2f}s")
    print()

    # ==================================================================
    # STEP 6: Monitor Pipeline Progress
    # ==================================================================
    print("Step 6: Monitoring pipeline progress...")
    print("-" * 70)

    progress = pattern.monitor_progress()

    print("Pipeline Status:")
    print(f"  - Active workers: {progress.get('active_workers', [])}")
    print(f"  - Total tasks: {num_tasks}")
    print(f"  - Pending: {progress.get('pending_tasks', 0)}")
    print(f"  - Completed: {progress.get('completed_tasks', 0)}")
    print(f"  - Documents processed: {total_documents}")
    print()

    # Calculate throughput
    docs_per_second = total_documents / processing_time if processing_time > 0 else 0
    print("Performance Metrics:")
    print(f"  - Processing time: {processing_time:.2f}s")
    print(f"  - Throughput: {docs_per_second:.1f} docs/sec")
    print(f"  - Avg time per doc: {(processing_time/total_documents)*1000:.0f}ms")
    print()

    # ==================================================================
    # STEP 7: Aggregate and Analyze Results
    # ==================================================================
    print("Step 7: Aggregating results...")
    print("-" * 70)

    final_result = pattern.aggregate_results(request_id)

    print("✓ Results aggregated!")
    print()

    # Extract insights from aggregated results
    print("Processing Summary:")
    print(f"  - Summary: {final_result.get('summary', 'N/A')[:150]}...")
    print()

    # Display individual task results
    task_results = final_result.get("task_results", [])
    if task_results:
        print(f"Individual Batch Results ({len(task_results)} batches):")
        for i, tr in enumerate(task_results[:3], 1):  # Show first 3
            print(f"  Batch {i}:")
            print(f"    - Worker: {tr.get('worker', 'N/A')}")
            print(f"    - Result: {tr.get('result', 'N/A')[:80]}...")
            print()

    # ==================================================================
    # STEP 8: Generate Processing Report
    # ==================================================================
    print("Step 8: Generating processing report...")
    print("-" * 70)

    # Simulated report generation
    # In real scenario, would extract actual sentiment, topics, etc.
    report = {
        "timestamp": datetime.now().isoformat(),
        "pipeline": "customer_feedback_processing",
        "documents_processed": total_documents,
        "processing_time_seconds": round(processing_time, 2),
        "workers_used": num_workers,
        "tasks_completed": len(task_results),
        "throughput_docs_per_sec": round(docs_per_second, 1),
        "status": "completed",
        "insights": {
            "total_batches": num_tasks,
            "avg_batch_size": batch_size,
            "parallel_efficiency": f"{(num_workers / processing_time) * 100:.0f}%",
        },
    }

    print("Processing Report:")
    print(f"  Timestamp: {report['timestamp']}")
    print(f"  Pipeline: {report['pipeline']}")
    print(f"  Status: ✓ {report['status'].upper()}")
    print()
    print(f"  Documents Processed: {report['documents_processed']}")
    print(f"  Processing Time: {report['processing_time_seconds']}s")
    print(f"  Throughput: {report['throughput_docs_per_sec']} docs/sec")
    print()
    print(f"  Workers Used: {report['workers_used']}")
    print(f"  Tasks Completed: {report['tasks_completed']}")
    print(f"  Parallel Efficiency: {report['insights']['parallel_efficiency']}")
    print()

    # ==================================================================
    # STEP 9: Cleanup for Next Run
    # ==================================================================
    print("Step 9: Cleanup for next pipeline run...")
    print("-" * 70)

    # Clear shared memory for next batch
    pattern.clear_shared_memory()

    print("✓ Pipeline reset and ready for next batch")
    print()

    # ==================================================================
    # Summary and Insights
    # ==================================================================
    print("=" * 70)
    print("Document Processing Pipeline Complete!")
    print("=" * 70)
    print()

    print("What you learned:")
    print("  ✓ How to build a real-world document processing pipeline")
    print("  ✓ How to optimize worker configurations for cost/performance")
    print("  ✓ How to process documents in parallel batches")
    print("  ✓ How to monitor pipeline progress in real-time")
    print("  ✓ How to generate processing reports and metrics")
    print("  ✓ How to calculate throughput and efficiency")
    print()

    print("Production Considerations:")
    print("  → Scale workers dynamically based on document volume")
    print("  → Implement persistent queue for document batches")
    print("  → Add retry logic for failed document processing")
    print("  → Store results in database for analytics")
    print("  → Add real-time monitoring dashboard")
    print("  → Implement priority queues for urgent documents")
    print("  → Add document validation and preprocessing")
    print("  → Integrate with document storage (S3, database)")
    print()

    print("Scaling Guidelines:")
    print(f"  → Current: {num_workers} workers → ~{docs_per_second:.0f} docs/sec")
    print(f"  → 8 workers → ~{docs_per_second * 2:.0f} docs/sec (estimated)")
    print(f"  → 16 workers → ~{docs_per_second * 4:.0f} docs/sec (estimated)")
    print()

    print("Next Steps:")
    print("  → Implement actual sentiment analysis (e.g., with transformers)")
    print("  → Add topic modeling (e.g., LDA, BERTopic)")
    print("  → Integrate with document storage system")
    print("  → Add result persistence and reporting")
    print("  → Deploy as production pipeline with monitoring")
    print()


if __name__ == "__main__":
    main()
