:orphan:

.. _guides-workflows:


Workflow Management
===================

This guide covers workflow creation, management, and best practices.

Creating Workflows
------------------

.. code-block:: python

   from kailash.workflow import Workflow

   # Create a new workflow
   workflow = Workflow(
       workflow_id="data_processing",
       name="Data Processing Pipeline",
       description="Processes customer data"
   )

Workflow Patterns
-----------------

See the :doc:`../examples/patterns` for common workflow patterns.

State Management
----------------

See the :doc:`../best_practices` for state management techniques.

Cyclic Workflows
----------------

Kailash supports cyclic workflows for iterative processing, optimization, and retry patterns.

Creating Cyclic Workflows
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from kailash import Workflow
   from kailash.nodes.base_cycle_aware import CycleAwareNode

   # Use CycleAwareNode for cycle-specific features
   class OptimizerNode(CycleAwareNode):
       def run(self, context, **kwargs):
           iteration = self.get_iteration(context)
           prev_state = self.get_previous_state(context)

           # Perform optimization step
           current_value = prev_state.get("value", 0) + 0.1
           converged = current_value >= 0.95

           # Save state for next iteration
           self.set_cycle_state({"value": current_value})

           return {
               "value": current_value,
               "converged": converged,
               "iteration": iteration
           }

   # Build cyclic workflow
   workflow = Workflow("optimization")
   workflow.add_node("optimizer", OptimizerNode())

   # Connect node to itself
   workflow.connect("optimizer", "optimizer",
                    cycle=True,
                    max_iterations=100,
                    convergence_check="converged == True")

Common Cyclic Patterns
~~~~~~~~~~~~~~~~~~~~~~

**1. Retry with Exponential Backoff:**

.. code-block:: python

   class RetryNode(CycleAwareNode):
       def run(self, context, **kwargs):
           iteration = self.get_iteration(context)
           max_retries = kwargs.get("max_retries", 3)

           try:
               # Attempt operation
               result = perform_operation()
               return {"success": True, "result": result}
           except Exception as e:
               if iteration < max_retries:
                   # Exponential backoff
                   delay = 2 ** iteration
                   time.sleep(delay)
                   return {"success": False, "retry": True}
               else:
                   return {"success": False, "error": str(e)}

**2. Data Quality Improvement:**

.. code-block:: python

   class QualityNode(CycleAwareNode):
       def run(self, context, **kwargs):
           data = kwargs["data"]

           # Track quality metrics over iterations
           quality = calculate_quality(data)
           history = self.accumulate_values(context, "quality", quality)

           # Detect convergence trend
           trend = self.detect_convergence_trend(context, "quality")

           # Improve data
           improved_data = improve_quality(data)

           return {
               "data": improved_data,
               "quality": quality,
               "converged": quality > 0.95 or trend["converging"]
           }

**3. Stream Processing Windows:**

.. code-block:: python

   class WindowProcessor(CycleAwareNode):
       def run(self, context, **kwargs):
           stream = kwargs["stream"]
           window_size = kwargs.get("window_size", 100)
           iteration = self.get_iteration(context)

           # Process window
           start = iteration * window_size
           end = start + window_size
           window = stream[start:end]

           # Process and check for more data
           result = process_window(window)
           more_data = end < len(stream)

           return {
               "result": result,
               "more_data": more_data,
               "window_number": iteration
           }

Best Practices for Cycles
~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Always Set Convergence Conditions**: Use either ``convergence_check`` or return a convergence flag
2. **Set Reasonable Max Iterations**: Prevent infinite loops with ``max_iterations``
3. **Use State Management**: Leverage ``get_previous_state()`` and ``set_cycle_state()``
4. **Track Metrics**: Use ``accumulate_values()`` to build history
5. **Log Progress**: Use ``log_cycle_info()`` for debugging
6. **Handle Edge Cases**: Consider what happens on first/last iteration

Performance Considerations
~~~~~~~~~~~~~~~~~~~~~~~~~~

- Cycles add minimal overhead (~0.03ms per iteration)
- State is efficiently managed with automatic cleanup
- Use ``ParallelCyclicRuntime`` for parallel cycle execution
- History windows are configurable to manage memory

State Management
----------------

See the :doc:`../best_practices` for state management techniques.
