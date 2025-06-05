========
Tracking
========

This section covers the task tracking and monitoring system in the Kailash SDK.

.. contents:: Table of Contents
   :local:
   :depth: 2

Overview
========

The tracking system provides comprehensive monitoring and analytics for workflow
execution:

- **Task Tracking**: Monitor individual node executions
- **Run Management**: Track complete workflow runs
- **Metrics Collection**: Gather performance and resource metrics
- **Storage Backends**: Persist tracking data
- **Analytics**: Analyze execution patterns and performance

TaskManager
===========

The central component for tracking workflow execution.

.. autoclass:: kailash.tracking.manager.TaskManager
   :members:
   :undoc-members:
   :show-inheritance:

**Basic Usage:**

.. code-block:: python

   from kailash.tracking import TaskManager
   from kailash import Workflow
   from kailash.workflow.runner import WorkflowRunner

   # Create task manager
   task_manager = TaskManager()

   # Use with workflow runner
   workflow = Workflow("my_workflow")
   runner = WorkflowRunner(workflow, task_manager)

   # Execute and track
   results = runner.run()

   # Access tracking data
   run_id = results["run_id"]
   run_info = task_manager.get_run(run_id)
   print(f"Execution took: {run_info.duration}s")

Tracking Models
===============

WorkflowRun
-----------

Represents a complete workflow execution.

.. autoclass:: kailash.tracking.models.WorkflowRun
   :members:
   :undoc-members:
   :show-inheritance:

**Attributes:**

- ``run_id``: Unique identifier for the run
- ``workflow_id``: Identifier of the executed workflow
- ``status``: Current status (pending, running, completed, failed)
- ``start_time``: Execution start timestamp
- ``end_time``: Execution end timestamp
- ``duration``: Total execution time
- ``metadata``: Additional run metadata

**Example Usage:**

.. code-block:: python

   # Get run information
   run = task_manager.get_run(run_id)

   print(f"Run ID: {run.run_id}")
   print(f"Status: {run.status}")
   print(f"Duration: {run.duration}s")
   print(f"Nodes executed: {len(run.tasks)}")

Task
----

Represents individual node execution within a workflow run.

.. autoclass:: kailash.tracking.models.Task
   :members:
   :undoc-members:
   :show-inheritance:

**Attributes:**

- ``task_id``: Unique task identifier
- ``run_id``: Parent workflow run ID
- ``node_id``: ID of the executed node
- ``status``: Task status (pending, running, completed, failed, skipped)
- ``start_time``: Task start timestamp
- ``end_time``: Task end timestamp
- ``duration``: Task execution time
- ``error``: Error information if failed
- ``metrics``: Performance metrics

**Example Usage:**

.. code-block:: python

   # Get task details
   tasks = task_manager.get_tasks(run_id)

   for task in tasks:
       print(f"Node: {task.node_id}")
       print(f"Status: {task.status}")
       print(f"Duration: {task.duration}s")
       if task.error:
           print(f"Error: {task.error}")

TaskMetrics
-----------

Performance and resource metrics for task execution.

.. autoclass:: kailash.tracking.models.TaskMetrics
   :members:
   :undoc-members:
   :show-inheritance:

**Collected Metrics:**

- **CPU Usage**: Processor utilization percentage
- **Memory Usage**: RAM consumption in bytes
- **Disk I/O**: Read/write operations and bytes
- **Network I/O**: Sent/received bytes
- **Custom Metrics**: Application-specific measurements

**Example Usage:**

.. code-block:: python

   # Access task metrics
   task = task_manager.get_task(task_id)
   metrics = task.metrics

   print(f"CPU Usage: {metrics.cpu_percent}%")
   print(f"Memory: {metrics.memory_bytes / 1024 / 1024:.2f} MB")
   print(f"Disk Read: {metrics.disk_read_bytes / 1024 / 1024:.2f} MB")
   print(f"Network Sent: {metrics.network_sent_bytes / 1024:.2f} KB")

Storage Backends
================

FileSystemStorage
-----------------

Default storage backend using the local filesystem.

.. autoclass:: kailash.tracking.storage.filesystem.FileSystemStorage
   :members:
   :undoc-members:
   :show-inheritance:

**Configuration:**

.. code-block:: python

   from kailash.tracking.storage import FileSystemStorage

   storage = FileSystemStorage(
       base_path="/path/to/tracking/data",
       format="json",  # or "yaml"
       compress=True,  # Gzip compression
       retention_days=30  # Auto-cleanup old data
   )

   task_manager = TaskManager(storage=storage)

**Directory Structure:**

.. code-block:: text

   tracking_data/
   ├── runs/
   │   ├── 2024-01-01/
   │   │   ├── run_123.json
   │   │   └── run_456.json
   │   └── 2024-01-02/
   │       └── run_789.json
   ├── tasks/
   │   └── run_123/
   │       ├── task_001.json
   │       └── task_002.json
   └── metrics/
       └── daily_summary.json

DatabaseStorage
---------------

Database backend for scalable storage.

.. autoclass:: kailash.tracking.storage.database.DatabaseStorage
   :members:
   :undoc-members:
   :show-inheritance:

**Supported Databases:**

- PostgreSQL
- MySQL
- SQLite
- MongoDB

**Configuration:**

.. code-block:: python

   from kailash.tracking.storage import DatabaseStorage

   # PostgreSQL
   storage = DatabaseStorage(
       connection_string="postgresql://user:pass@localhost/tracking",
       pool_size=10,
       echo=False  # SQL logging
   )

   # MongoDB
   storage = DatabaseStorage(
       connection_string="mongodb://localhost:27017/",
       database="kailash_tracking",
       collection_prefix="tracking_"
   )

Custom Storage Backend
----------------------

Implement custom storage by extending the base class:

.. code-block:: python

   from kailash.tracking.storage.base import BaseStorage
   import redis

   class RedisStorage(BaseStorage):
       """Redis-based tracking storage."""

       def __init__(self, redis_url: str):
           self.client = redis.from_url(redis_url)

       def save_run(self, run: WorkflowRun) -> None:
           key = f"run:{run.run_id}"
           self.client.setex(
               key,
               86400,  # 24 hour TTL
               run.json()
           )

       def get_run(self, run_id: str) -> WorkflowRun:
           key = f"run:{run_id}"
           data = self.client.get(key)
           if data:
               return WorkflowRun.parse_raw(data)
           return None

       def save_task(self, task: Task) -> None:
           key = f"task:{task.task_id}"
           self.client.setex(key, 86400, task.json())

       def get_tasks(self, run_id: str) -> List[Task]:
           # Implementation for retrieving tasks
           pass

Tracking Configuration
======================

Environment Variables
---------------------

Configure tracking behavior:

.. code-block:: bash

   # Storage location
   export KAILASH_TRACKING_PATH=/var/kailash/tracking

   # Storage backend
   export KAILASH_TRACKING_BACKEND=filesystem

   # Database connection (if using database backend)
   export KAILASH_TRACKING_DB=postgresql://localhost/tracking

   # Metrics collection
   export KAILASH_COLLECT_METRICS=true
   export KAILASH_METRICS_INTERVAL=1.0  # seconds

   # Retention policy
   export KAILASH_TRACKING_RETENTION_DAYS=30

Configuration File
------------------

.. code-block:: yaml

   # ~/.kailash/tracking.yaml
   tracking:
     enabled: true
     backend: filesystem
     storage:
       path: ~/.kailash/tracking
       format: json
       compress: true

     metrics:
       enabled: true
       interval: 1.0
       include:
         - cpu
         - memory
         - disk_io
         - network_io

     retention:
       days: 30
       max_runs: 10000

Programmatic Configuration
--------------------------

.. code-block:: python

   from kailash.tracking import TaskManager, TrackingConfig

   config = TrackingConfig(
       enabled=True,
       collect_metrics=True,
       metric_interval=0.5,
       storage_backend="database",
       storage_config={
           "connection_string": "postgresql://localhost/tracking",
           "pool_size": 20
       }
   )

   task_manager = TaskManager(config=config)

Analytics and Reporting
=======================

Run Analytics
-------------

Analyze workflow execution patterns:

.. code-block:: python

   from kailash.tracking.analytics import RunAnalyzer

   analyzer = RunAnalyzer(task_manager)

   # Get run statistics
   stats = analyzer.get_run_stats(
       start_date="2024-01-01",
       end_date="2024-01-31"
   )

   print(f"Total runs: {stats['total_runs']}")
   print(f"Success rate: {stats['success_rate']:.2%}")
   print(f"Average duration: {stats['avg_duration']:.2f}s")
   print(f"Failed runs: {stats['failed_runs']}")

Performance Analysis
--------------------

Identify performance bottlenecks:

.. code-block:: python

   # Analyze node performance
   node_stats = analyzer.get_node_performance(workflow_id)

   for node_id, stats in node_stats.items():
       print(f"\nNode: {node_id}")
       print(f"  Executions: {stats['count']}")
       print(f"  Avg Duration: {stats['avg_duration']:.2f}s")
       print(f"  Max Duration: {stats['max_duration']:.2f}s")
       print(f"  Failure Rate: {stats['failure_rate']:.2%}")

Resource Usage Analysis
-----------------------

Monitor resource consumption:

.. code-block:: python

   # Get resource usage trends
   resource_trends = analyzer.get_resource_trends(
       run_id=run_id,
       metric="memory",
       interval="1min"
   )

   # Plot memory usage
   import matplotlib.pyplot as plt

   plt.plot(resource_trends['timestamps'], resource_trends['values'])
   plt.xlabel('Time')
   plt.ylabel('Memory (MB)')
   plt.title('Memory Usage Over Time')
   plt.show()

Custom Reports
--------------

Generate custom reports:

.. code-block:: python

   from kailash.tracking.reporting import ReportGenerator

   generator = ReportGenerator(task_manager)

   # Generate HTML report
   report = generator.generate_html_report(
       run_id=run_id,
       include_metrics=True,
       include_timeline=True,
       include_errors=True
   )

   with open("execution_report.html", "w") as f:
       f.write(report)

   # Generate CSV summary
   generator.export_run_summary(
       output_path="run_summary.csv",
       start_date="2024-01-01",
       end_date="2024-01-31"
   )

Real-time Monitoring
====================

Live Tracking
-------------

Monitor workflows in real-time:

.. code-block:: python

   from kailash.tracking import LiveMonitor

   monitor = LiveMonitor(task_manager)

   # Start monitoring
   monitor.start()

   # Execute workflow
   results = workflow.run()

   # Get live statistics
   live_stats = monitor.get_stats()
   print(f"Active tasks: {live_stats['active_tasks']}")
   print(f"Completed tasks: {live_stats['completed_tasks']}")
   print(f"Failed tasks: {live_stats['failed_tasks']}")

Event Streaming
---------------

Stream tracking events:

.. code-block:: python

   from kailash.tracking import EventStream

   stream = EventStream(task_manager)

   # Subscribe to events
   @stream.on("task.started")
   def on_task_start(event):
       print(f"Task started: {event['node_id']}")

   @stream.on("task.completed")
   def on_task_complete(event):
       print(f"Task completed: {event['node_id']} in {event['duration']}s")

   @stream.on("run.failed")
   def on_run_failed(event):
       print(f"Run failed: {event['error']}")
       # Send alert
       send_failure_alert(event)

   # Start streaming
   stream.start()

Webhooks
--------

Send tracking events to external systems:

.. code-block:: python

   from kailash.tracking import WebhookHandler

   webhook = WebhookHandler(
       url="https://api.example.com/webhooks/kailash",
       events=["run.completed", "run.failed"],
       headers={"Authorization": "Bearer token"}
   )

   task_manager.add_handler(webhook)

Performance Metrics Collection
==============================

The SDK includes comprehensive performance metrics collection that automatically tracks
resource usage during workflow execution.

MetricsCollector
----------------

Collects real-time performance metrics during node execution.

.. autoclass:: kailash.tracking.metrics_collector.MetricsCollector
   :members:
   :undoc-members:
   :show-inheritance:

**Usage Example:**

.. code-block:: python

   from kailash.tracking.metrics_collector import MetricsCollector

   # Automatic collection in runtime
   collector = MetricsCollector()
   with collector.collect(node_id="process_data") as metrics:
       # Your node execution code
       result = process_data(input_data)

   # Access collected metrics
   performance = metrics.result()
   print(f"Duration: {performance.duration}s")
   print(f"CPU Usage: {performance.cpu_percent}%")
   print(f"Memory: {performance.memory_mb}MB")

PerformanceMetrics
------------------

Comprehensive performance data collected during execution.

.. autoclass:: kailash.tracking.metrics_collector.PerformanceMetrics
   :members:
   :undoc-members:
   :show-inheritance:

**Collected Metrics:**

- **Timing**: Start time, end time, duration
- **CPU**: Usage percentage, user/system time
- **Memory**: Current usage, peak usage, delta
- **I/O**: Read/write bytes, operation counts
- **Network**: Bytes sent/received (for API nodes)

Performance Visualization
=========================

Visualize and analyze performance metrics from workflow runs.

PerformanceVisualizer
---------------------

Creates various performance visualizations from collected metrics.

.. autoclass:: kailash.visualization.performance.PerformanceVisualizer
   :members:
   :undoc-members:
   :show-inheritance:

**Visualization Types:**

1. **Execution Timeline** - Gantt chart showing node execution order and duration
2. **Resource Usage** - Line charts of CPU and memory over time
3. **Performance Comparison** - Radar charts comparing multiple runs
4. **I/O Analysis** - Bar charts of read/write operations
5. **Performance Heatmap** - Visual bottleneck identification
6. **Markdown Reports** - Comprehensive performance analysis

**Example Usage:**

.. code-block:: python

   from kailash.visualization.performance import PerformanceVisualizer
   from kailash.tracking import TaskManager

   # Create visualizer
   task_manager = TaskManager()
   perf_viz = PerformanceVisualizer(task_manager)

   # Generate performance report
   outputs = perf_viz.create_run_performance_summary(
       run_id="abc-123",
       output_dir="performance_report"
   )

   # Compare multiple runs
   perf_viz.compare_runs(
       run_ids=["run-1", "run-2", "run-3"],
       output_path="comparison.png"
   )

**Dashboard Creation:**

.. code-block:: python

   from kailash.workflow.visualization import WorkflowVisualizer

   # Create performance dashboard
   workflow_viz = WorkflowVisualizer(workflow)
   dashboard = workflow_viz.create_performance_dashboard(
       run_id=run_id,
       task_manager=task_manager,
       output_dir="dashboard"
   )

   # Dashboard includes:
   # - dashboard.html (interactive overview)
   # - Timeline charts
   # - Resource usage graphs
   # - Performance heatmaps
   # - Detailed metrics tables

Best Practices
==============

1. **Enable Tracking in Production**

.. code-block:: python

   # Always use tracking in production
   task_manager = TaskManager(
       storage=DatabaseStorage(connection_string),
       config=TrackingConfig(
           enabled=True,
           collect_metrics=True
       )
   )

2. **Set Appropriate Retention**

.. code-block:: python

   # Balance storage vs history
   storage = FileSystemStorage(
       retention_days=90,  # 3 months
       archive_old_data=True,  # Compress old data
       archive_path="/archive/tracking"
   )

3. **Monitor Key Metrics**

.. code-block:: python

   # Focus on important metrics
   key_metrics = analyzer.get_key_metrics(run_id)

   if key_metrics['memory_peak'] > threshold:
       alert("High memory usage detected")

   if key_metrics['duration'] > sla_duration:
       alert("SLA breach: execution too slow")

4. **Use Appropriate Storage**

- **Development**: FileSystemStorage with JSON
- **Production**: DatabaseStorage with PostgreSQL/MongoDB
- **High Volume**: Time-series database or data warehouse

5. **Implement Cleanup**

.. code-block:: python

   # Regular cleanup job
   from kailash.tracking.maintenance import cleanup_old_data

   # Run daily
   cleanup_old_data(
       task_manager,
       older_than_days=90,
       keep_failed_runs=True
   )

See Also
========

- :doc:`workflow` - Workflow execution
- :doc:`runtime` - Runtime engines
- Monitoring guide
- :doc:`../guides/performance` - Performance optimization
- Tracking examples
