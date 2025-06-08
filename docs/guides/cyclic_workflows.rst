=================
Cyclic Workflows
=================

.. versionadded:: 0.2.0
   The Universal Hybrid Cyclic Graph Architecture brings high-performance iterative processing
   to Kailash with automatic convergence detection and comprehensive developer tools.

This guide covers everything you need to know about building and optimizing cyclic workflows
in Kailash SDK v0.2.0.

.. contents:: Table of Contents
   :local:
   :depth: 3

Overview
========

Cyclic workflows enable iterative processing patterns where data flows through nodes multiple
times until a convergence condition is met. This is essential for:

- **Optimization algorithms** (gradient descent, genetic algorithms)
- **Iterative refinement** (data cleaning, quality improvement)
- **Retry logic** (API calls, error recovery)
- **Feedback loops** (reinforcement learning, control systems)
- **Convergence algorithms** (numerical methods, simulations)

**Key Features:**

- ✅ **High Performance**: 30,000+ iterations per second
- ✅ **Automatic Convergence**: Built-in trend detection
- ✅ **Developer Tools**: Analyzer, Debugger, Profiler
- ✅ **Type Safety**: Validated configurations
- ✅ **State Management**: Automatic between iterations

Quick Start
===========

Using CycleBuilder (Recommended)
---------------------------------

The new CycleBuilder API provides the simplest way to create cyclic workflows:

.. code-block:: python

   from kailash.workflow import CycleBuilder
   from kailash.nodes import PythonCodeNode

   # Create builder
   builder = CycleBuilder("gradient_descent")

   # Define optimization logic
   optimizer_code = '''
   # Access previous state with automatic defaults
   try:
       x = cycle_state["x"]
       y = cycle_state["y"]
   except:
       x = 5.0
       y = 5.0

   # Gradient of f(x,y) = x^2 + y^2
   grad_x = 2 * x
   grad_y = 2 * y

   # Update with gradient descent
   learning_rate = 0.1
   new_x = x - learning_rate * grad_x
   new_y = y - learning_rate * grad_y

   # Calculate loss
   loss = new_x**2 + new_y**2

   # Check convergence
   converged = loss < 0.001

   result = {
       "x": new_x,
       "y": new_y,
       "loss": loss,
       "converged": converged
   }
   '''

   # Add cycle node
   builder.add_cycle_node(
       "optimizer",
       PythonCodeNode(name="optimizer", code=optimizer_code),
       convergence_check="converged == True",
       max_iterations=100
   )

   # Build and run
   workflow = builder.build()
   results = workflow.run()

   print(f"Minimum found at: ({results['optimizer']['x']:.4f}, {results['optimizer']['y']:.4f})")

Using Traditional API
---------------------

You can also create cycles using the traditional Workflow API:

.. code-block:: python

   from kailash import Workflow
   from kailash.nodes.base_cycle_aware import CycleAwareNode

   class OptimizerNode(CycleAwareNode):
       def run(self, context, **kwargs):
           # Get iteration and state
           iteration = self.get_iteration(context)
           prev_state = self.get_previous_state(context)

           # Optimization logic
           x = prev_state.get("x", 5.0)
           gradient = 2 * x
           new_x = x - 0.1 * gradient

           # Save state
           self.set_cycle_state({"x": new_x})

           # Check convergence
           converged = abs(new_x) < 0.001

           return {"x": new_x, "converged": converged}

   # Create workflow
   workflow = Workflow("optimization")
   workflow.add_node("optimizer", OptimizerNode())

   # Create cycle
   workflow.connect("optimizer", "optimizer",
                    cycle=True,
                    max_iterations=100,
                    convergence_check="converged == True")

   results = workflow.run()

Core Concepts
=============

Cycle Components
----------------

1. **Cycle Edge**: Connection marked with ``cycle=True``
2. **Convergence Check**: Expression to determine when to stop
3. **Max Iterations**: Safety limit to prevent infinite loops
4. **State Management**: Data persistence between iterations
5. **Parameter Mapping**: How outputs map to next iteration's inputs

State Management
----------------

Cyclic workflows automatically manage state between iterations:

.. code-block:: python

   # In PythonCodeNode
   try:
       # Access previous iteration's state
       prev_value = cycle_state["value"]
       history = cycle_state["history"]
   except:
       # First iteration - initialize
       prev_value = 0
       history = []

   # Update state
   new_value = prev_value + 1
   history.append(new_value)

   # Return new state
   result = {
       "value": new_value,
       "history": history,
       "converged": new_value >= 10
   }

Convergence Detection
---------------------

Multiple ways to detect convergence:

.. code-block:: python

   # 1. Simple boolean check
   convergence_check="converged == True"

   # 2. Threshold check
   convergence_check="error < 0.001"

   # 3. Complex expression
   convergence_check="(loss < 0.01) and (gradient_norm < 1e-6)"

   # 4. Automatic trend detection (CycleAwareNode)
   trend = self.detect_convergence_trend(context, "loss")
   converged = trend["converging"] and trend["stable"]

Advanced Patterns
=================

Multi-Node Cycles
-----------------

Create cycles with multiple nodes:

.. code-block:: python

   from kailash.workflow import CycleBuilder

   builder = CycleBuilder("multi_stage_optimization")

   # Stage 1: Calculate gradient
   gradient_code = '''
   try:
       x = cycle_state["x"]
   except:
       x = parameters.get("initial_x", 10.0)

   gradient = 2 * x  # f'(x) for f(x) = x^2
   result = {"x": x, "gradient": gradient}
   '''

   # Stage 2: Update parameters
   update_code = '''
   x = x  # From previous node
   gradient = gradient  # From previous node
   learning_rate = 0.1

   new_x = x - learning_rate * gradient
   loss = new_x ** 2

   converged = abs(gradient) < 0.001
   result = {"x": new_x, "loss": loss, "converged": converged}
   '''

   # Add nodes
   builder.add_node("gradient", PythonCodeNode(name="gradient", code=gradient_code))
   builder.add_node("update", PythonCodeNode(name="update", code=update_code))

   # Connect in cycle
   builder.connect("gradient", "update")
   builder.close_cycle("update", "gradient",
                      mapping={"x": "x"},  # Map x to next iteration
                      convergence_check="converged == True")

   workflow = builder.build()

Nested Cycles
-------------

Create workflows with nested iteration patterns:

.. code-block:: python

   from kailash.workflow import CycleBuilder

   # Outer optimization loop
   outer_builder = CycleBuilder("outer_optimization")

   # Inner refinement loop
   inner_builder = CycleBuilder("inner_refinement")

   # Inner loop logic
   refine_code = '''
   try:
       quality = cycle_state["quality"]
       data = cycle_state["data"]
   except:
       quality = 0.0
       data = input_data

   # Refine data
   refined = [x * 1.01 for x in data]
   quality = min(quality + 0.1, 1.0)

   result = {
       "data": refined,
       "quality": quality,
       "converged": quality >= 0.9
   }
   '''

   inner_builder.add_cycle_node(
       "refiner",
       PythonCodeNode(name="refiner", code=refine_code),
       convergence_check="converged == True",
       max_iterations=10
   )

   # Build inner workflow
   inner_workflow = inner_builder.build()

   # Add to outer workflow
   outer_builder.add_node("inner_loop", WorkflowNode(workflow=inner_workflow))

   # Outer loop continues until overall convergence
   outer_builder.add_cycle_node("evaluate", EvaluatorNode())
   outer_builder.connect("inner_loop", "evaluate")
   outer_builder.close_cycle("evaluate", "inner_loop",
                            convergence_check="score > 0.95")

Parallel Cycles
---------------

Run multiple cycles in parallel:

.. code-block:: python

   from kailash import Workflow
   from kailash.runtime import ParallelRuntime

   workflow = Workflow("parallel_optimization")

   # Add parallel optimizers
   for i in range(4):
       optimizer = create_optimizer_node(f"opt_{i}")
       workflow.add_node(f"optimizer_{i}", optimizer)
       workflow.connect(f"optimizer_{i}", f"optimizer_{i}",
                        cycle=True,
                        convergence_check="converged == True")

   # Merge results
   workflow.add_node("merge", MergeNode())
   for i in range(4):
       workflow.add_edge(f"optimizer_{i}", "merge")

   # Run with parallel runtime
   runtime = ParallelRuntime(max_workers=4)
   results = runtime.execute(workflow)

Developer Tools
===============

CycleAnalyzer
-------------

Analyze cycle execution and performance:

.. code-block:: python

   from kailash.workflow import CycleAnalyzer

   analyzer = CycleAnalyzer(workflow)

   # Run workflow
   results = workflow.run()

   # Analyze execution
   report = analyzer.analyze_execution(results)

   print(f"Total iterations: {report['iterations']}")
   print(f"Convergence rate: {report['convergence_rate']:.2%}")
   print(f"Performance: {report['iterations_per_second']:.0f} iter/sec")

   # Detailed analysis
   print("\nIteration breakdown:")
   for node_id, stats in report['node_stats'].items():
       print(f"  {node_id}:")
       print(f"    Average time: {stats['avg_time']:.4f}s")
       print(f"    Total time: {stats['total_time']:.2f}s")

   # Generate report
   analyzer.generate_report("analysis_report.json")

   # Visualize convergence
   analyzer.plot_convergence("convergence.png")

CycleDebugger
-------------

Debug cyclic workflows with breakpoints and tracing:

.. code-block:: python

   from kailash.workflow import CycleDebugger

   debugger = CycleDebugger(workflow)

   # Enable debugging
   debugger.enable_debugging()

   # Set breakpoints
   debugger.set_breakpoint("optimizer", iteration=5)
   debugger.set_breakpoint("optimizer", iteration=10)

   # Conditional breakpoint
   debugger.set_conditional_breakpoint(
       "optimizer",
       condition=lambda state: state.get("loss", float('inf')) < 0.1
   )

   # Watch expressions
   debugger.add_watch("loss")
   debugger.add_watch("gradient")

   # Run with debugging
   results = workflow.run()

   # Get debug information
   debug_info = debugger.get_debug_info()

   # Print breakpoint hits
   print("Breakpoint hits:")
   for bp in debug_info['breakpoint_hits']:
       print(f"  Iteration {bp['iteration']}: {bp['state']}")

   # Get execution trace
   trace = debugger.get_execution_trace()
   for step in trace[-10:]:  # Last 10 iterations
       print(f"Iter {step['iteration']}: loss={step['state'].get('loss', 'N/A')}")

CycleProfiler
-------------

Profile performance and identify bottlenecks:

.. code-block:: python

   from kailash.workflow import CycleProfiler

   profiler = CycleProfiler(workflow)

   # Profile execution
   results = workflow.run()
   profile = profiler.profile_execution(results)

   print(f"Performance Summary:")
   print(f"  Total iterations: {profile['total_iterations']}")
   print(f"  Total time: {profile['total_time']:.2f}s")
   print(f"  Avg iteration time: {profile['avg_iteration_time']:.4f}s")
   print(f"  Iterations/second: {profile['iterations_per_second']:.0f}")

   print(f"\nResource Usage:")
   print(f"  Peak memory: {profile['peak_memory_mb']:.1f} MB")
   print(f"  Avg CPU usage: {profile['avg_cpu_percent']:.1f}%")

   print(f"\nBottlenecks:")
   print(f"  Slowest node: {profile['bottleneck_node']}")
   print(f"  Time in bottleneck: {profile['bottleneck_time_percent']:.1f}%")

   # Get optimization suggestions
   suggestions = profiler.get_optimization_suggestions()
   print("\nOptimization suggestions:")
   for suggestion in suggestions:
       print(f"  - {suggestion}")

   # Generate detailed report
   profiler.generate_performance_report("performance_report.html")

Best Practices
==============

1. Always Set Max Iterations
----------------------------

Prevent infinite loops with reasonable limits:

.. code-block:: python

   # Good
   workflow.connect("node", "node",
                    cycle=True,
                    max_iterations=1000,  # Reasonable limit
                    convergence_check="converged == True")

   # Better - with early termination
   workflow.connect("node", "node",
                    cycle=True,
                    max_iterations=1000,
                    convergence_check="converged == True",
                    early_termination="no_improvement_count > 10")

2. Use Meaningful Convergence Checks
------------------------------------

Make convergence conditions clear and testable:

.. code-block:: python

   # Good - Clear and specific
   convergence_check="(loss < 0.001) and (gradient_norm < 1e-6)"

   # Bad - Unclear
   convergence_check="done == True"

   # Better - With tolerance
   convergence_check=f"abs(loss - previous_loss) < {tolerance}"

3. Track Convergence History
----------------------------

Use CycleAwareNode's built-in tracking:

.. code-block:: python

   class OptimizationNode(CycleAwareNode):
       def run(self, context, **kwargs):
           # Track values
           self.accumulate_values(context, "loss", current_loss)
           self.accumulate_values(context, "gradient", gradient_norm)

           # Detect trends
           loss_trend = self.detect_convergence_trend(context, "loss")

           # Log progress
           if iteration % 10 == 0:
               self.log_cycle_info(context,
                   f"Iteration {iteration}: loss={current_loss:.6f}")

           # Use trend for convergence
           converged = (
               loss_trend["converging"] and
               loss_trend["stable"] and
               current_loss < threshold
           )

4. Handle First Iteration
-------------------------

Always provide defaults for the first iteration:

.. code-block:: python

   # In PythonCodeNode
   try:
       # Try to get previous state
       x = cycle_state["x"]
       velocity = cycle_state["velocity"]
   except:
       # First iteration - initialize
       x = parameters.get("initial_x", 0.0)
       velocity = 0.0

   # In CycleAwareNode
   prev_state = self.get_previous_state(context)
   x = prev_state.get("x", initial_x)  # With default

5. Use Checkpoints for Long Runs
---------------------------------

Save intermediate results for long-running cycles:

.. code-block:: python

   from kailash.workflow import CycleConfig

   config = CycleConfig(
       max_iterations=10000,
       convergence_check="loss < 1e-8",
       save_checkpoints=True,
       checkpoint_interval=100,
       checkpoint_dir="./checkpoints"
   )

   workflow.connect("optimizer", "optimizer",
                    cycle=True,
                    **config.to_dict())

Performance Optimization
========================

1. Minimize State Size
----------------------

Keep cycle state compact:

.. code-block:: python

   # Good - Only essential state
   result = {
       "x": new_x,
       "loss": loss,
       "converged": converged
   }

   # Bad - Storing unnecessary history
   result = {
       "x": new_x,
       "loss": loss,
       "all_iterations": all_iterations,  # Avoid storing full history
       "converged": converged
   }

2. Use NumPy for Numerical Operations
-------------------------------------

Leverage vectorized operations:

.. code-block:: python

   import numpy as np

   # Good - Vectorized
   gradient = 2 * np.array(x)
   new_x = x - learning_rate * gradient

   # Less efficient - Loop
   gradient = []
   for xi in x:
       gradient.append(2 * xi)

3. Profile and Optimize Bottlenecks
-----------------------------------

Use the profiler to identify slow operations:

.. code-block:: python

   profiler = CycleProfiler(workflow)
   profile = profiler.profile_execution(results)

   # Focus optimization on bottlenecks
   if profile['bottleneck_node'] == 'processor':
       # Optimize the processor node
       # - Use caching
       # - Vectorize operations
       # - Reduce I/O

Common Patterns
===============

Gradient Descent
----------------

.. code-block:: python

   gradient_descent_code = '''
   import numpy as np

   try:
       theta = np.array(cycle_state["theta"])
       loss_history = cycle_state["loss_history"]
   except:
       theta = np.random.randn(n_features)
       loss_history = []

   # Compute gradient
   predictions = X @ theta
   errors = predictions - y
   gradient = (2/m) * X.T @ errors

   # Update parameters
   theta = theta - learning_rate * gradient

   # Compute loss
   loss = np.mean(errors ** 2)
   loss_history.append(loss)

   # Check convergence
   converged = len(loss_history) > 1 and abs(loss_history[-1] - loss_history[-2]) < 1e-6

   result = {
       "theta": theta.tolist(),
       "loss": loss,
       "loss_history": loss_history,
       "converged": converged
   }
   '''

Retry with Backoff
------------------

.. code-block:: python

   retry_code = '''
   try:
       attempt = cycle_state["attempt"]
       backoff = cycle_state["backoff"]
   except:
       attempt = 0
       backoff = 1

   attempt += 1

   try:
       # Attempt operation
       response = make_api_call(data)
       result = {
           "response": response,
           "success": True,
           "attempts": attempt
       }
   except Exception as e:
       # Exponential backoff
       import time
       time.sleep(backoff)

       result = {
           "error": str(e),
           "success": False,
           "attempt": attempt,
           "backoff": min(backoff * 2, 60),  # Cap at 60 seconds
           "attempts": attempt
       }
   '''

Iterative Refinement
--------------------

.. code-block:: python

   refinement_code = '''
   try:
       data = cycle_state["data"]
       quality_score = cycle_state["quality_score"]
   except:
       data = input_data
       quality_score = calculate_quality(data)

   # Apply refinement
   refined_data = apply_refinement_step(data)
   new_quality = calculate_quality(refined_data)

   # Check if improvement is significant
   improvement = new_quality - quality_score
   converged = improvement < min_improvement_threshold

   result = {
       "data": refined_data,
       "quality_score": new_quality,
       "improvement": improvement,
       "converged": converged
   }
   '''

Troubleshooting
===============

Common Issues
-------------

1. **Infinite Loops**

   .. code-block:: python

      # Problem: No convergence check
      workflow.connect("node", "node", cycle=True)

      # Solution: Add convergence check
      workflow.connect("node", "node",
                       cycle=True,
                       convergence_check="converged == True",
                       max_iterations=1000)

2. **State Not Persisting**

   .. code-block:: python

      # Problem: Not including state in result
      result = {"converged": converged}

      # Solution: Include all state
      result = {
          "value": new_value,
          "history": history,
          "converged": converged
      }

3. **Slow Performance**

   .. code-block:: python

      # Use profiler to identify bottlenecks
      profiler = CycleProfiler(workflow)
      profile = profiler.profile_execution(results)

      # Common solutions:
      # - Reduce state size
      # - Use vectorized operations
      # - Cache expensive computations

4. **Convergence Not Detected**

   .. code-block:: python

      # Use debugger to inspect state
      debugger = CycleDebugger(workflow)
      debugger.enable_debugging()
      debugger.add_watch("loss")
      debugger.add_watch("converged")

      # Check convergence criteria
      # - Is threshold too strict?
      # - Is check expression correct?
      # - Are values in expected range?

Migration Guide
===============

Migrating from Traditional Loops
---------------------------------

Convert traditional Python loops to cyclic workflows:

**Before:**

.. code-block:: python

   # Traditional loop
   x = 10.0
   for i in range(100):
       gradient = 2 * x
       x = x - 0.1 * gradient
       if abs(x) < 0.001:
           break

**After:**

.. code-block:: python

   # Cyclic workflow
   from kailash.workflow import CycleBuilder

   builder = CycleBuilder("optimization")

   optimizer_code = '''
   try:
       x = cycle_state["x"]
   except:
       x = 10.0

   gradient = 2 * x
   new_x = x - 0.1 * gradient
   converged = abs(new_x) < 0.001

   result = {"x": new_x, "converged": converged}
   '''

   builder.add_cycle_node(
       "optimizer",
       PythonCodeNode(name="optimizer", code=optimizer_code),
       convergence_check="converged == True",
       max_iterations=100
   )

   workflow = builder.build()
   results = workflow.run()

Using Migration Tools
---------------------

.. code-block:: python

   from kailash.workflow.migration import WorkflowMigrator

   # Analyze existing workflow
   migrator = WorkflowMigrator()
   analysis = migrator.analyze_workflow(old_workflow)

   # Generate migration code
   migration_code = migrator.generate_migration_code(old_workflow)
   print(migration_code)

   # Auto-migrate
   new_workflow = migrator.migrate_workflow(old_workflow)

See Also
========

- :doc:`/api/workflow` - Complete API reference
- :doc:`/examples/index` - Example workflows
- :doc:`/guides/performance` - Performance optimization
- :doc:`/guides/best_practices` - General best practices
