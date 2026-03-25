=======
Runtime
=======

Runtimes execute workflows. The Kailash SDK provides two runtimes that share
the same API and return the same ``(results, run_id)`` tuple.

Runtime Selection
=================

.. list-table::
   :widths: 30 35 35
   :header-rows: 1

   * - Runtime
     - Use Case
     - Import
   * - ``LocalRuntime``
     - CLI, scripts, synchronous code
     - ``from kailash.runtime import LocalRuntime``
   * - ``AsyncLocalRuntime``
     - Docker, FastAPI, async code
     - ``from kailash.runtime import AsyncLocalRuntime``
   * - ``get_runtime()``
     - Auto-detect context
     - ``from kailash.runtime import get_runtime``

LocalRuntime
============

Synchronous runtime for CLI scripts and non-async contexts:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime import LocalRuntime

   workflow = WorkflowBuilder()
   workflow.add_node("PythonCodeNode", "hello", {
       "code": "result = {'msg': 'Hello!'}"
   })

   with LocalRuntime() as runtime:
       results, run_id = runtime.execute(workflow.build())

AsyncLocalRuntime
=================

Async-optimized runtime for Docker and FastAPI deployments:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime import AsyncLocalRuntime

   workflow = WorkflowBuilder()
   workflow.add_node("PythonCodeNode", "hello", {
       "code": "result = {'msg': 'Hello async!'}"
   })

   runtime = AsyncLocalRuntime()
   try:
       results, run_id = await runtime.execute_workflow_async(
           workflow.build(), inputs={}
       )
   finally:
       runtime.close()

``AsyncLocalRuntime`` extends ``LocalRuntime`` with:

- **WorkflowAnalyzer**: Determines optimal execution strategy
- **ExecutionContext**: Async context with integrated resource access
- **Level-based parallelism**: Independent nodes execute concurrently
- **Thread pool**: Sync nodes run without blocking the async loop
- **Semaphore control**: Limits concurrent executions

.. code-block:: python

   runtime = AsyncLocalRuntime(
       max_concurrent_nodes=10  # AsyncLocalRuntime-specific
   )

Architecture
============

Both runtimes inherit from ``BaseRuntime`` and share three mixins:

BaseRuntime Foundation
----------------------

29 configuration parameters including:

- ``debug``: Enable debug logging
- ``enable_cycles``: Allow cyclic workflow execution
- ``conditional_execution``: Branch skipping mode
- ``connection_validation``: Validation strictness (strict/warn/off)
- ``enable_resource_limits``: Opt-in resource limit checks (default: False)

Shared Mixins
-------------

**CycleExecutionMixin**
   Delegates cycle execution to ``CyclicWorkflowExecutor`` with validation
   and error wrapping.

**ValidationMixin** (5 methods)
   - ``validate_workflow()``: Structure, connections, parameter mappings
   - ``_validate_connection_contracts()``: Connection parameter contracts
   - ``_validate_conditional_execution_prerequisites()``: Conditional setup
   - ``_validate_switch_results()``: Switch node results
   - ``_validate_conditional_execution_results()``: Conditional results

**ConditionalExecutionMixin**
   Pattern detection, cycle detection, node skipping, hierarchical execution,
   and conditional workflow orchestration with ``SwitchNode`` support.

LocalRuntime-Specific
---------------------

- Enhanced error messages via ``_generate_enhanced_validation_error()``
- Connection context building via ``_build_connection_context()``
- Public validation API: ``get_validation_metrics()``, ``reset_validation_metrics()``
- Uses ``WorkflowParameterInjector`` for enterprise parameter handling

Configuration
=============

Full Configuration Example
--------------------------

.. code-block:: python

   runtime = LocalRuntime(
       # Debugging
       debug=True,

       # Cycle support
       enable_cycles=True,

       # Conditional execution
       conditional_execution="skip_branches",

       # Connection validation (strict / warn / off)
       connection_validation="strict",

       # Resource limits (opt-in, default False)
       enable_resource_limits=False,
   )

Validation Metrics
------------------

.. code-block:: python

   with LocalRuntime(connection_validation="strict") as runtime:
       results, run_id = runtime.execute(workflow.build())

       # Inspect validation results
       metrics = runtime.get_validation_metrics()
       print(metrics)

   # Reset for next run
   runtime.reset_validation_metrics()

Trust Integration
=================

Attach a CARE trust context to any runtime for cryptographic accountability:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.runtime import LocalRuntime
   from kailash.runtime.trust import (
       RuntimeTrustContext,
       TrustVerificationMode,
       TrustVerifier,
       TrustVerifierConfig,
   )

   ctx = RuntimeTrustContext(
       trace_id="trace-001",
       delegation_chain=["human-alice", "agent-orchestrator"],
       verification_mode=TrustVerificationMode.ENFORCING,
   )

   verifier = TrustVerifier(
       config=TrustVerifierConfig(mode="enforcing"),
   )

   with LocalRuntime(
       trust_context=ctx,
       trust_verifier=verifier,
       trust_verification_mode="enforcing",
   ) as runtime:
       results, run_id = runtime.execute(workflow.build())

See :doc:`trust` for the complete CARE trust documentation.

Performance Notes
=================

- **Resource limit checks** are opt-in via ``enable_resource_limits=True``
  (default: ``False``) to avoid unnecessary overhead
- **Topological sort** and **cycle edge classification** are cached per workflow;
  invalidated on ``add_node()`` / ``connect()``
- **networkx** is removed from the hot-path execution in ``local.py`` and
  ``async_local.py``; still used in ``graph.py`` for core DAG operations
- **Regression tests** in ``tests/unit/runtime/test_phase0{a,b,c}_optimizations.py``
  (53 tests) guard performance optimizations

Best Practices
==============

1. **Use LocalRuntime for scripts**, AsyncLocalRuntime for Docker/FastAPI
2. **Enable strict validation** in production: ``connection_validation="strict"``
3. **Attach trust context** for auditable, accountable workflows
4. **Both runtimes return** ``(results, run_id)`` -- identical API
5. **Use** ``get_runtime()`` **for auto-detection** when context is uncertain
