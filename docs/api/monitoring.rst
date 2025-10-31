Monitoring & Alerting API
=========================

The monitoring and alerting system provides comprehensive metrics collection,
security violation tracking, and multi-channel alerting for Kailash workflows.

.. automodule:: kailash.monitoring
   :members:
   :undoc-members:
   :show-inheritance:

Metrics Collection
------------------

.. automodule:: kailash.monitoring.metrics
   :members:
   :undoc-members:
   :show-inheritance:

Alert Management
----------------

.. automodule:: kailash.monitoring.alerts
   :members:
   :undoc-members:
   :show-inheritance:

Usage Examples
--------------

Basic Monitoring Setup
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from kailash.monitoring.metrics import get_validation_metrics, get_security_metrics
   from kailash.monitoring.alerts import AlertManager, AlertRule, AlertSeverity
   from kailash.monitoring.alerts import LogNotificationChannel

   # Set up comprehensive monitoring
   validation_metrics = get_validation_metrics()
   security_metrics = get_security_metrics()
   registry = get_metrics_registry()
   alert_manager = AlertManager(registry)

   # Configure alert rules
   alert_manager.add_rule(AlertRule(
       name="high_validation_failures",
       description="Validation failure rate above 10%",
       severity=AlertSeverity.ERROR,
       metric_name="validation_failure",
       condition="> 5",
       threshold=5
   ))

   alert_manager.add_notification_channel(LogNotificationChannel())
   alert_manager.start()

Custom Metrics Collection
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from kailash.monitoring.metrics import MetricsCollector, MetricType

   # Create custom metrics collector
   collector = MetricsCollector()

   # Create and record metrics
   response_time = collector.create_metric(
       "api_response_time",
       MetricType.TIMER,
       "API response time",
       "milliseconds"
   )

   collector.record_timer("api_response_time", 150.5)
   collector.increment("api_requests")
   collector.set_gauge("active_connections", 42)

Security Monitoring
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from kailash.monitoring.metrics import get_security_metrics, MetricSeverity

   security_metrics = get_security_metrics()

   # Record security violations
   security_metrics.record_security_violation(
       violation_type="sql_injection_attempt",
       severity=MetricSeverity.HIGH,
       source="workflow_connection",
       details={"query": "malicious_query"}
   )

   # Check critical violations
   critical_count = security_metrics.get_critical_violations()
   violation_rate = security_metrics.get_violation_rate()

Performance Monitoring
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from kailash.monitoring.metrics import get_performance_metrics

   performance_metrics = get_performance_metrics()

   # Record operation performance
   performance_metrics.record_operation(
       operation="workflow_execution",
       duration_ms=1250.0,
       success=True
   )

   # Update system metrics
   performance_metrics.update_system_metrics(
       memory_mb=512.0,
       cpu_percent=25.5,
       rps=100.0
   )

   # Get performance statistics
   p95_time = performance_metrics.get_p95_response_time()

Connection Validation Monitoring
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from kailash.runtime.local import LocalRuntime
   from kailash.monitoring.metrics import get_validation_metrics

   # Enable connection validation with monitoring
   runtime = LocalRuntime(connection_validation="strict")
   validation_metrics = get_validation_metrics()

   # Execute workflow with monitoring
   results, run_id = runtime.execute(workflow.build())

   # View validation metrics
   success_rate = validation_metrics.get_success_rate()
   cache_hit_rate = validation_metrics.get_cache_hit_rate()

   print(f"Validation success rate: {success_rate:.2%}")
   print(f"Cache hit rate: {cache_hit_rate:.2%}")

Metrics Export
~~~~~~~~~~~~~~

.. code-block:: python

   from kailash.monitoring.metrics import get_metrics_registry

   registry = get_metrics_registry()

   # Export metrics in JSON format
   json_metrics = registry.export_metrics("json")

   # Export metrics in Prometheus format
   prometheus_metrics = registry.export_metrics("prometheus")

   print(json_metrics)
