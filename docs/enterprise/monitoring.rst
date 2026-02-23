.. _enterprise_monitoring:

Enterprise Monitoring
======================

Production-grade monitoring and observability for Kailash workflows.

Workflow Monitoring
-------------------

Every workflow execution returns a ``run_id`` for tracking:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime import LocalRuntime

   workflow = WorkflowBuilder()
   workflow.add_node("PythonCodeNode", "process", {
       "code": "result = {'status': 'complete'}"
   })

   runtime = LocalRuntime(debug=True)
   results, run_id = runtime.execute(workflow.build())

   # run_id can be used for distributed tracing and audit correlation
   print(f"Workflow completed: {run_id}")

Validation Metrics
------------------

Monitor connection validation health in production:

.. code-block:: python

   runtime = LocalRuntime(connection_validation="strict")
   results, run_id = runtime.execute(workflow.build())

   metrics = runtime.get_validation_metrics()
   print(f"Validation metrics: {metrics}")

   runtime.reset_validation_metrics()

Trust Audit Trail
-----------------

When CARE trust is enabled, all trust events are logged:

- Delegation chain propagation events
- Trust verification decisions (allow/deny)
- Constraint enforcement actions
- RFC 3161 timestamps for each event

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
       trace_id="monitoring-trace-001",
       delegation_chain=["human-operator", "agent-monitor"],
       verification_mode=TrustVerificationMode.PERMISSIVE,
   )

   verifier = TrustVerifier(
       config=TrustVerifierConfig(mode="permissive"),
   )

   runtime = LocalRuntime(
       trust_context=ctx,
       trust_verifier=verifier,
       trust_verification_mode="permissive",
   )

   # Trust events are logged for monitoring
   results, run_id = runtime.execute(workflow.build())

Performance Notes
-----------------

- Resource limit checks are opt-in via ``enable_resource_limits=True`` (default: False)
- Topological sort and cycle edge classification are cached per workflow
- networkx is removed from hot-path execution

See Also
--------

- :doc:`../core/trust` -- CARE trust framework for audit trails
- :doc:`../core/runtime` -- Runtime configuration and validation metrics
- :doc:`deployment` -- Production deployment patterns
