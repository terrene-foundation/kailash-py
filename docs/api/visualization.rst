=============
Visualization
=============

This section covers the real-time monitoring, dashboard, and performance visualization
capabilities in the Kailash SDK.

.. contents:: Table of Contents
   :local:
   :depth: 2

Overview
========

The visualization system provides comprehensive real-time monitoring and performance
analysis for workflow execution:

- **Real-time Dashboards**: Live monitoring with streaming metrics
- **Performance Reports**: Multi-format comprehensive reports
- **Interactive Charts**: Chart.js integration for web dashboards
- **API Access**: REST and WebSocket endpoints for custom integrations
- **Resource Monitoring**: CPU, memory, and I/O tracking
- **Bottleneck Analysis**: Automatic performance issue detection

Real-time Dashboard
===================

The core component for live workflow monitoring with background metrics collection.

.. autoclass:: kailash.visualization.dashboard.RealTimeDashboard
   :members:
   :undoc-members:
   :show-inheritance:

Dashboard Configuration
=======================

Configuration options for customizing dashboard behavior and appearance.

.. autoclass:: kailash.visualization.dashboard.DashboardConfig
   :members:
   :undoc-members:
   :show-inheritance:

Live Metrics
============

Data models for real-time performance metrics.

.. autoclass:: kailash.visualization.dashboard.LiveMetrics
   :members:
   :undoc-members:
   :show-inheritance:

Performance Reporter
====================

Generate comprehensive performance reports in multiple formats.

.. autoclass:: kailash.visualization.reports.WorkflowPerformanceReporter
   :members:
   :undoc-members:
   :show-inheritance:

Report Formats
==============

Supported output formats for performance reports.

.. autoclass:: kailash.visualization.reports.ReportFormat
   :members:
   :undoc-members:
   :show-inheritance:

Performance Insights
====================

Structured performance analysis and recommendations.

.. autoclass:: kailash.visualization.reports.PerformanceInsight
   :members:
   :undoc-members:
   :show-inheritance:

Dashboard API
=============

REST API interface for accessing metrics programmatically.

.. autoclass:: kailash.visualization.api.SimpleDashboardAPI
   :members:
   :undoc-members:
   :show-inheritance:

WebSocket Server
================

FastAPI-based server for real-time metrics streaming.

.. note::
   This component requires FastAPI to be installed. Install with: ``pip install fastapi uvicorn``

.. autoclass:: kailash.visualization.api.DashboardAPIServer
   :members:
   :undoc-members:
   :show-inheritance:

Performance Visualizer
======================

Static performance analysis and chart generation.

.. autoclass:: kailash.visualization.performance.PerformanceVisualizer
   :members:
   :undoc-members:
   :show-inheritance:

Usage Examples
==============

Basic Real-time Monitoring
--------------------------

.. code-block:: python

   from kailash.visualization.dashboard import RealTimeDashboard, DashboardConfig
   from kailash.tracking import TaskManager
   from kailash.runtime.local import LocalRuntime

   # Setup components
   task_manager = TaskManager()
   config = DashboardConfig(
       update_interval=1.0,
       max_history_points=100,
       auto_refresh=True,
       theme="light"
   )

   # Create dashboard
   dashboard = RealTimeDashboard(task_manager, config)

   # Start monitoring
   dashboard.start_monitoring()

   # Execute workflow with monitoring
   runtime = LocalRuntime()
   results, run_id = runtime.execute(workflow, task_manager)

   # Generate live dashboard
   dashboard.generate_live_report("dashboard.html", include_charts=True)
   dashboard.stop_monitoring()

Performance Report Generation
-----------------------------

.. code-block:: python

   from kailash.visualization.reports import WorkflowPerformanceReporter, ReportFormat

   # Create reporter
   reporter = WorkflowPerformanceReporter(task_manager)

   # Generate comprehensive HTML report
   report_path = reporter.generate_report(
       run_id,
       output_path="performance_report.html",
       format=ReportFormat.HTML,
       compare_runs=[previous_run_id]
   )

   # Generate Markdown report
   md_report = reporter.generate_report(
       run_id,
       format=ReportFormat.MARKDOWN
   )

API-based Monitoring
--------------------

.. code-block:: python

   from kailash.visualization.api import SimpleDashboardAPI

   # Create API interface
   api = SimpleDashboardAPI(task_manager)
   api.start_monitoring()

   # Get current metrics
   metrics = api.get_current_metrics()
   print(f"Active tasks: {metrics['active_tasks']}")

   # Get historical data
   history = api.get_metrics_history(minutes=30)

   # Stop monitoring
   api.stop_monitoring()

WebSocket Streaming Server
--------------------------

.. code-block:: python

   from kailash.visualization.api import DashboardAPIServer
   import asyncio

   # Create server
   server = DashboardAPIServer(task_manager, port=8000)

   # Start server (runs async)
   async def run_server():
       await server.start()

   # In your client (JavaScript):
   # const ws = new WebSocket('ws://localhost:8000/api/v1/metrics/stream');
   # ws.onmessage = (event) => {
   #     const metrics = JSON.parse(event.data);
   #     // Update dashboard with real-time metrics
   # };

Real-time Callbacks
-------------------

.. code-block:: python

   # Add custom callbacks for real-time events
   def on_metrics_update(metrics):
       print(f"CPU: {metrics.total_cpu_usage:.1f}%, Memory: {metrics.total_memory_usage:.1f}MB")

   def on_status_change(event_type, count):
       if event_type == "task_completed":
           print(f"✅ {count} task(s) completed")
       elif event_type == "task_failed":
           print(f"❌ {count} task(s) failed")

   dashboard.add_metrics_callback(on_metrics_update)
   dashboard.add_status_callback(on_status_change)

Dashboard Features
==================

The real-time dashboard provides:

**Live Metrics**
   - Active, completed, and failed task counts
   - Real-time CPU and memory usage
   - Throughput metrics (tasks per minute)
   - I/O statistics and data transfer rates

**Interactive Charts**
   - Timeline charts with Chart.js integration
   - Resource usage graphs over time
   - Task status progression visualization
   - Performance comparison charts

**Responsive Design**
   - Mobile-friendly layout
   - Auto-refresh capabilities
   - Dark/light theme support
   - Customizable update intervals

**Export Options**
   - HTML dashboards with embedded JavaScript
   - JSON metrics logs for external analysis
   - Markdown reports for documentation
   - PNG/SVG chart exports (with matplotlib)

Architecture
============

The visualization system follows a modular architecture:

.. mermaid::

   graph TB
       subgraph "Real-time Layer"
           A[RealTimeDashboard]
           B[LiveMetrics]
           C[DashboardConfig]
       end

       subgraph "Reporting Layer"
           D[WorkflowPerformanceReporter]
           E[PerformanceInsight]
           F[ReportFormat]
       end

       subgraph "API Layer"
           G[SimpleDashboardAPI]
           H[DashboardAPIServer]
           I[WebSocket Streaming]
       end

       subgraph "Static Analysis"
           J[PerformanceVisualizer]
           K[Chart Generation]
           L[Metrics Analysis]
       end

       A --> B
       A --> C
       A --> G

       D --> E
       D --> F

       G --> H
       H --> I

       J --> K
       J --> L

       A --> D
       G --> J

Best Practices
==============

**Real-time Monitoring**
   - Use appropriate update intervals (1-5 seconds for active monitoring)
   - Limit history points to prevent memory issues (100-500 points)
   - Stop monitoring when done to free resources
   - Use callbacks for custom event handling

**Performance Reports**
   - Generate reports after workflow completion
   - Compare multiple runs to identify trends
   - Include relevant run metadata and context
   - Use appropriate output formats for your use case

**API Integration**
   - Use WebSocket streaming for real-time dashboards
   - Implement proper error handling and reconnection
   - Rate limit API calls to prevent performance impact
   - Cache metrics data for better performance

**Resource Management**
   - Monitor system resources during metrics collection
   - Use background threads to avoid blocking workflow execution
   - Implement proper cleanup and resource disposal
   - Consider storage requirements for long-running monitoring
