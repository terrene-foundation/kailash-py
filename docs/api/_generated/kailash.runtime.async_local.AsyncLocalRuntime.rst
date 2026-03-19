kailash.runtime.async\_local.AsyncLocalRuntime
==============================================

.. currentmodule:: kailash.runtime.async_local

.. autoclass:: AsyncLocalRuntime

   
   .. automethod:: __init__

   
   .. rubric:: Methods

   .. autosummary::
   
      ~AsyncLocalRuntime.__init__
      ~AsyncLocalRuntime.add_non_retriable_exception
      ~AsyncLocalRuntime.add_retriable_exception
      ~AsyncLocalRuntime.can_execute_workflow
      ~AsyncLocalRuntime.cleanup
      ~AsyncLocalRuntime.clear_analytics_data
      ~AsyncLocalRuntime.close
      ~AsyncLocalRuntime.execute
      ~AsyncLocalRuntime.execute_async
      ~AsyncLocalRuntime.execute_node_with_enterprise_features
      ~AsyncLocalRuntime.execute_node_with_enterprise_features_sync
      ~AsyncLocalRuntime.execute_workflow_async
      ~AsyncLocalRuntime.generate_compatibility_report
      ~AsyncLocalRuntime.get_compatibility_report_markdown
      ~AsyncLocalRuntime.get_execution_analytics
      ~AsyncLocalRuntime.get_execution_metrics
      ~AsyncLocalRuntime.get_execution_path_debug_info
      ~AsyncLocalRuntime.get_execution_plan_cached
      ~AsyncLocalRuntime.get_health_diagnostics
      ~AsyncLocalRuntime.get_health_status
      ~AsyncLocalRuntime.get_performance_report
      ~AsyncLocalRuntime.get_query_registry
      ~AsyncLocalRuntime.get_resource_metrics
      ~AsyncLocalRuntime.get_retry_analytics
      ~AsyncLocalRuntime.get_retry_configuration
      ~AsyncLocalRuntime.get_retry_metrics_summary
      ~AsyncLocalRuntime.get_retry_policy_engine
      ~AsyncLocalRuntime.get_runtime_metrics
      ~AsyncLocalRuntime.get_shared_connection_pool
      ~AsyncLocalRuntime.get_signal_channel
      ~AsyncLocalRuntime.get_strategy_effectiveness
      ~AsyncLocalRuntime.get_validation_metrics
      ~AsyncLocalRuntime.optimize_runtime_performance
      ~AsyncLocalRuntime.query
      ~AsyncLocalRuntime.record_execution_performance
      ~AsyncLocalRuntime.register_retry_strategy
      ~AsyncLocalRuntime.register_retry_strategy_for_exception
      ~AsyncLocalRuntime.reset_retry_metrics
      ~AsyncLocalRuntime.reset_validation_metrics
      ~AsyncLocalRuntime.set_automatic_mode_switching
      ~AsyncLocalRuntime.set_compatibility_reporting
      ~AsyncLocalRuntime.set_performance_monitoring
      ~AsyncLocalRuntime.shutdown_gracefully
      ~AsyncLocalRuntime.signal
      ~AsyncLocalRuntime.start_persistent_mode
      ~AsyncLocalRuntime.validate_workflow
   
   

   
   
   .. rubric:: Attributes

   .. autosummary::
   
      ~AsyncLocalRuntime.connection_pool_manager
      ~AsyncLocalRuntime.enterprise_monitoring
      ~AsyncLocalRuntime.execution_semaphore
      ~AsyncLocalRuntime.shutdown_coordinator
   
   