.. _examples-patterns:


Workflow Patterns
=================

This section demonstrates common workflow patterns and best practices.

Parallel Processing Pattern
---------------------------

.. code-block:: python

   from kailash.workflow import Workflow
   from kailash.runtime.parallel import ParallelRuntime

   # Create workflow with parallel branches
   workflow = Workflow("parallel_pattern", name="Parallel Processing")

   # Add nodes that can run in parallel
   # ... (node setup)

   # Execute with parallel runtime
   runtime = ParallelRuntime(max_workers=4)
   results, run_id = runtime.execute(workflow)

Error Handling Pattern
----------------------

.. code-block:: python

   from kailash.workflow import Workflow
   from kailash.nodes.logic import SwitchNode

   # Create workflow with error handling
   workflow = Workflow("error_handling", name="Error Handling Pattern")

   # Add switch for error routing
   error_router = SwitchNode()
   workflow.add_node("error_handler", error_router)

   # ... (error handling logic)

State Management Pattern
------------------------

.. code-block:: python

   from kailash.workflow import Workflow
   from kailash.workflow.state import WorkflowStateWrapper

   # Create workflow with state management
   workflow = Workflow("stateful_pattern", name="Stateful Workflow")

   # Initialize state
   state = {"counter": 0, "results": []}
   state_wrapper = workflow.create_state_wrapper(state)

   # ... (stateful operations)

Cyclic Workflow Patterns
------------------------

Cyclic workflows enable iterative processing, optimization, and retry patterns.

Retry Pattern with Backoff
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from kailash import Workflow
   from kailash.nodes.base_cycle_aware import CycleAwareNode
   import time

   class RetryNode(CycleAwareNode):
       def run(self, context, **kwargs):
           iteration = self.get_iteration(context)
           max_retries = kwargs.get("max_retries", 3)

           try:
               # Attempt operation
               result = self.perform_operation(kwargs["data"])
               return {"success": True, "result": result}
           except Exception as e:
               if iteration < max_retries:
                   # Exponential backoff
                   delay = 2 ** iteration
                   time.sleep(delay)
                   self.log_cycle_info(context, f"Retry {iteration + 1} after {delay}s")
                   return {"success": False, "retry": True}
               else:
                   return {"success": False, "error": str(e)}

   # Create workflow with retry cycle
   workflow = Workflow("retry_pattern")
   workflow.add_node("retry", RetryNode())
   workflow.create_cycle("retry_cycle") \
           .connect("retry", "retry") \
           .max_iterations(5) \
           .converge_when("success == True") \
           .build()

Iterative Optimization Pattern
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from kailash.nodes.base_cycle_aware import CycleAwareNode

   class GradientDescentNode(CycleAwareNode):
       def run(self, context, **kwargs):
           iteration = self.get_iteration(context)
           prev_state = self.get_previous_state(context)

           # Get current parameters
           params = prev_state.get("params", kwargs.get("initial_params"))
           loss = self.calculate_loss(params)

           # Track loss history
           self.accumulate_values(context, "loss", loss)
           trend = self.detect_convergence_trend(context, "loss")

           # Update parameters
           learning_rate = 0.01 * (0.95 ** iteration)  # Decay
           gradient = self.calculate_gradient(params)
           new_params = params - learning_rate * gradient

           # Save state
           self.set_cycle_state({"params": new_params, "loss": loss})

           # Check convergence
           converged = (
               trend["converging"] and trend["stability"] > 0.99 or
               loss < 0.001 or
               iteration >= 1000
           )

           return {
               "params": new_params,
               "loss": loss,
               "converged": converged,
               "iteration": iteration
           }

   # Create optimization workflow
   workflow = Workflow("optimization")
   workflow.add_node("optimizer", GradientDescentNode())
   workflow.create_cycle("optimization_cycle") \
           .connect("optimizer", "optimizer") \
           .max_iterations(1000) \
           .converge_when("converged == True") \
           .build()

Data Quality Improvement Pattern
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   class DataQualityNode(CycleAwareNode):
       def run(self, context, **kwargs):
           data = kwargs["data"]
           iteration = self.get_iteration(context)

           # Calculate quality metrics
           completeness = self.calculate_completeness(data)
           accuracy = self.calculate_accuracy(data)
           quality_score = (completeness + accuracy) / 2

           # Track improvement
           self.accumulate_values(context, "quality", quality_score)
           trend = self.detect_convergence_trend(context, "quality")

           # Apply improvements
           if completeness < 0.95:
               data = self.fill_missing_values(data)
           if accuracy < 0.95:
               data = self.fix_outliers(data)

           # Log progress
           self.log_cycle_info(context,
               f"Iteration {iteration}: Quality={quality_score:.2%}")

           # Check if we've plateaued
           converged = (
               quality_score > 0.95 or
               trend["plateau_detected"] or
               iteration >= 10
           )

           return {
               "data": data,
               "quality_score": quality_score,
               "converged": converged
           }

Stream Processing Pattern
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   class StreamProcessorNode(CycleAwareNode):
       def run(self, context, **kwargs):
           stream = kwargs["stream"]
           batch_size = kwargs.get("batch_size", 100)
           iteration = self.get_iteration(context)

           # Calculate batch indices
           start = iteration * batch_size
           end = min(start + batch_size, len(stream))

           # Process batch
           batch = stream[start:end]
           results = self.process_batch(batch)

           # Accumulate results
           all_results = self.get_previous_state(context).get("results", [])
           all_results.extend(results)
           self.set_cycle_state({"results": all_results})

           # Check if more data exists
           more_data = end < len(stream)

           return {
               "batch_results": results,
               "total_processed": end,
               "more_data": more_data,
               "all_results": all_results if not more_data else None
           }

   # Create stream processing workflow
   workflow = Workflow("stream_processor")
   workflow.add_node("processor", StreamProcessorNode())
   workflow.create_cycle("stream_cycle") \
           .connect("processor", "processor") \
           .converge_when("more_data == False") \
           .build()

Multi-Node Cycle Pattern
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Create a cycle with multiple nodes
   workflow = Workflow("multi_node_cycle")

   # Add nodes for different stages
   workflow.add_node("collector", DataCollectorNode())
   workflow.add_node("processor", ProcessorNode())
   workflow.add_node("validator", ValidatorNode())
   workflow.add_node("decider", DecisionNode())

   # Connect in a cycle: collector → processor → validator → decider → collector
   workflow.connect("collector", "processor")
   workflow.connect("processor", "validator")
   workflow.connect("validator", "decider")
   workflow.create_cycle("processing_cycle") \
           .connect("decider", "collector") \
           .max_iterations(50) \
           .converge_when("should_continue == False") \
           .build()

Best Practices for Cyclic Workflows
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Always Set Convergence Conditions**: Prevent infinite loops
2. **Use State Management**: Leverage CycleAwareNode helpers
3. **Track Metrics**: Monitor convergence with accumulate_values()
4. **Handle Edge Cases**: Consider first/last iteration behavior
5. **Set Reasonable Limits**: Use max_iterations as a safety net
6. **Log Progress**: Use log_cycle_info() for debugging
7. **Optimize Performance**: Cycles add ~0.03ms overhead per iteration

Alert and Notification Patterns
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from kailash import Workflow
   from kailash.nodes.alerts import DiscordAlertNode
   from kailash.nodes.logic import SwitchNode
   from kailash.nodes.code import PythonCodeNode

   # Error Alert Pattern
   def create_error_alert_workflow():
       workflow = Workflow("error_alerts")

       # Process data (might fail)
       processor = PythonCodeNode.from_function(
           func=process_data_with_errors,
           name="processor"
       )
       workflow.add_node("process", processor)

       # Route based on success/failure
       router = SwitchNode(
           condition_mapping={
               "error": "status == 'error'",
               "success": "status == 'success'"
           }
       )
       workflow.add_node("router", router)

       # Critical error alert
       error_alert = DiscordAlertNode()
       workflow.add_node("error_alert", error_alert)

       # Success notification
       success_alert = DiscordAlertNode()
       workflow.add_node("success_alert", success_alert)

       # Connect the workflow
       workflow.connect("process", "router")
       workflow.connect("router", "error_alert", output_key="error")
       workflow.connect("router", "success_alert", output_key="success")

       return workflow

   # Health Dashboard Pattern
   def create_health_dashboard():
       workflow = Workflow("health_dashboard")

       # System health check
       health_checker = PythonCodeNode.from_function(
           func=check_system_health,
           name="health_checker"
       )
       workflow.add_node("health_check", health_checker)

       # Dashboard alert
       dashboard = DiscordAlertNode()
       workflow.add_node("dashboard", dashboard)

       workflow.connect("health_check", "dashboard")

       return workflow

   # Business KPI Alert Pattern
   def create_kpi_alerts():
       workflow = Workflow("kpi_alerts")

       # Calculate KPIs
       kpi_calculator = PythonCodeNode.from_function(
           func=calculate_business_kpis,
           name="kpi_calculator"
       )
       workflow.add_node("calculate", kpi_calculator)

       # Check thresholds
       threshold_checker = SwitchNode(
           condition_mapping={
               "critical": "revenue < target_revenue * 0.8",
               "warning": "revenue < target_revenue * 0.9",
               "normal": "default"
           }
       )
       workflow.add_node("threshold_check", threshold_checker)

       # Different alert types
       critical_alert = DiscordAlertNode()
       warning_alert = DiscordAlertNode()
       normal_report = DiscordAlertNode()

       workflow.add_node("critical_alert", critical_alert)
       workflow.add_node("warning_alert", warning_alert)
       workflow.add_node("normal_report", normal_report)

       # Connect workflow
       workflow.connect("calculate", "threshold_check")
       workflow.connect("threshold_check", "critical_alert", output_key="critical")
       workflow.connect("threshold_check", "warning_alert", output_key="warning")
       workflow.connect("threshold_check", "normal_report", output_key="normal")

       return workflow

   # Execute with parameters
   def execute_alert_workflows():
       # Error alert execution
       error_workflow = create_error_alert_workflow()
       runtime.execute(error_workflow, parameters={
           "error_alert": {
               "webhook_url": "${DISCORD_WEBHOOK}",
               "title": "🚨 Processing Error",
               "alert_type": "critical",
               "mentions": ["@here"]
           },
           "success_alert": {
               "webhook_url": "${DISCORD_WEBHOOK}",
               "title": "✅ Processing Complete",
               "alert_type": "success"
           }
       })

       # Health dashboard execution
       health_workflow = create_health_dashboard()
       runtime.execute(health_workflow, parameters={
           "dashboard": {
               "webhook_url": "${DISCORD_WEBHOOK}",
               "title": "📊 System Health Dashboard",
               "alert_type": "info",
               "username": "Health Monitor",
               "fields": [
                   {"name": "CPU", "value": "{cpu_usage:.1f}%", "inline": True},
                   {"name": "Memory", "value": "{memory_usage:.1f}%", "inline": True},
                   {"name": "Disk", "value": "{disk_usage:.1f}%", "inline": True}
               ]
           }
       })

**Alert Pattern Benefits:**

- **Real-time Notifications**: Immediate alerts on failures or thresholds
- **Rich Formatting**: Color-coded embeds with structured data
- **Escalation Support**: Different alert types for different severity levels
- **Integration Ready**: Works with existing monitoring and error handling

For more patterns, see the `workflow examples
<https://github.com/terrene-foundation/kailash-py/tree/main/examples/workflow_examples>`_.
