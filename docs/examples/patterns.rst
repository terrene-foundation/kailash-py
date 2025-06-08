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
   workflow.connect("retry", "retry",
                    cycle=True,
                    max_iterations=5,
                    convergence_check="success == True")

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
   workflow.connect("optimizer", "optimizer",
                    cycle=True,
                    max_iterations=1000,
                    convergence_check="converged == True")

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
   workflow.connect("processor", "processor",
                    cycle=True,
                    convergence_check="more_data == False")

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
   workflow.connect("decider", "collector",
                    cycle=True,  # Only mark the closing edge
                    max_iterations=50,
                    convergence_check="should_continue == False")

Best Practices for Cyclic Workflows
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Always Set Convergence Conditions**: Prevent infinite loops
2. **Use State Management**: Leverage CycleAwareNode helpers
3. **Track Metrics**: Monitor convergence with accumulate_values()
4. **Handle Edge Cases**: Consider first/last iteration behavior
5. **Set Reasonable Limits**: Use max_iterations as a safety net
6. **Log Progress**: Use log_cycle_info() for debugging
7. **Optimize Performance**: Cycles add ~0.03ms overhead per iteration

For more patterns, see the `workflow examples
<https://github.com/terrene-foundation/kailash-py/tree/main/examples/workflow_examples>`_.
