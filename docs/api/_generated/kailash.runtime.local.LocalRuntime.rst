kailash.runtime.local.LocalRuntime
==================================

.. currentmodule:: kailash.runtime.local

.. autoclass:: LocalRuntime

   
   .. automethod:: __init__

   
   .. rubric:: Methods

   .. autosummary::
   
      ~LocalRuntime.__init__
      ~LocalRuntime.add_non_retriable_exception
      ~LocalRuntime.add_retriable_exception
      ~LocalRuntime.can_execute_workflow
      ~LocalRuntime.cleanup
      ~LocalRuntime.clear_analytics_data
      ~LocalRuntime.close
      ~LocalRuntime.execute
      ~LocalRuntime.execute_async
      ~LocalRuntime.execute_node_with_enterprise_features
      ~LocalRuntime.execute_node_with_enterprise_features_sync
      ~LocalRuntime.generate_compatibility_report
      ~LocalRuntime.get_compatibility_report_markdown
      ~LocalRuntime.get_execution_analytics
      ~LocalRuntime.get_execution_metrics
      ~LocalRuntime.get_execution_path_debug_info
      ~LocalRuntime.get_execution_plan_cached
      ~LocalRuntime.get_health_diagnostics
      ~LocalRuntime.get_health_status
      ~LocalRuntime.get_performance_report
      ~LocalRuntime.get_query_registry
      ~LocalRuntime.get_resource_metrics
      ~LocalRuntime.get_retry_analytics
      ~LocalRuntime.get_retry_configuration
      ~LocalRuntime.get_retry_metrics_summary
      ~LocalRuntime.get_retry_policy_engine
      ~LocalRuntime.get_runtime_metrics
      ~LocalRuntime.get_shared_connection_pool
      ~LocalRuntime.get_signal_channel
      ~LocalRuntime.get_strategy_effectiveness
      ~LocalRuntime.get_validation_metrics
      ~LocalRuntime.optimize_runtime_performance
      ~LocalRuntime.query
      ~LocalRuntime.record_execution_performance
      ~LocalRuntime.register_retry_strategy
      ~LocalRuntime.register_retry_strategy_for_exception
      ~LocalRuntime.reset_retry_metrics
      ~LocalRuntime.reset_validation_metrics
      ~LocalRuntime.set_automatic_mode_switching
      ~LocalRuntime.set_compatibility_reporting
      ~LocalRuntime.set_performance_monitoring
      ~LocalRuntime.shutdown_gracefully
      ~LocalRuntime.signal
      ~LocalRuntime.start_persistent_mode
      ~LocalRuntime.validate_workflow
   
   

   
   
   .. rubric:: Attributes

   .. autosummary::
   
      ~LocalRuntime.connection_pool_manager
      ~LocalRuntime.enterprise_monitoring
      ~LocalRuntime.shutdown_coordinator
   
   