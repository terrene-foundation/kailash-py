=============================
CARE Trust Framework
=============================

The CARE (Context, Action, Reasoning, Evidence) framework and its
companion EATP (Enterprise Agent Trust Protocol) provide verifiable trust chains
for AI agent workflows. This is the defining capability of the Kailash SDK --
no other Python AI framework provides built-in cryptographic trust at the runtime
level. The Core SDK provides the foundational ``RuntimeTrustContext`` for immutable
trust context propagation, delegation chain tracking, and trust verification modes.
Full cryptographic features -- hash chains, RFC 3161 timestamps, the knowledge
ledger, and posture-based constraint dimensions -- require the Kaizen framework
integration (v1.2.0+).

Why Trust Matters
=================

When Agent A delegates to Agent B which delegates to Agent C, every action C takes
must be traceable back to the human who authorized it. Without this:

- There is no way to audit what an agent did or why
- Delegation chains become opaque
- Compliance requirements (SOC2, HIPAA, GDPR) cannot be met
- Enterprise deployments lack accountability

The CARE framework solves this with:

- **Human origin tracking**: Every workflow records which human authorized it
- **Delegation chain propagation**: Agent-to-agent delegation paths are preserved
- **Constraint enforcement**: Constraints from delegation chains can only be tightened, never loosened
- **Trust verification**: Pluggable backends can allow or deny operations
- **Audit trail**: EATP-compliant event log for compliance and forensics
- **RFC 3161 timestamping**: Cryptographic timestamps for non-repudiation

Core Concepts
=============

Trust Verification Modes
------------------------

The trust system has three modes, allowing incremental adoption:

.. list-table::
   :widths: 20 40 40
   :header-rows: 1

   * - Mode
     - Behavior
     - Use Case
   * - ``disabled``
     - No trust checks. Default behavior.
     - Development, backward compatibility
   * - ``permissive``
     - Logs trust events, does not block.
     - Staging, gradual rollout
   * - ``enforcing``
     - Blocks untrusted operations.
     - Production, compliance-critical

RuntimeTrustContext
-------------------

The context object that carries trust information through workflow execution:

.. code-block:: python

   from kailash.runtime.trust import (
       RuntimeTrustContext,
       TrustVerificationMode,
   )

   ctx = RuntimeTrustContext(
       trace_id="trace-abc-123",
       delegation_chain=["human-alice", "agent-coordinator", "agent-worker"],
       verification_mode=TrustVerificationMode.ENFORCING,
   )

Fields:

- **trace_id**: Unique identifier linking all events in one execution
- **delegation_chain**: Ordered list from human origin through agent delegations
- **verification_mode**: How strictly to enforce trust

TrustVerifier
-------------

The verifier that checks trust context against policies:

.. code-block:: python

   from kailash.runtime.trust import TrustVerifier, TrustVerifierConfig

   verifier = TrustVerifier(
       config=TrustVerifierConfig(mode="enforcing"),
   )

Usage Patterns
==============

No-Trust Mode (Default)
-----------------------

Existing code works unchanged. Trust is disabled by default:

.. code-block:: python

   from kailash.runtime import LocalRuntime

   with LocalRuntime() as runtime:
       results, run_id = runtime.execute(workflow.build())
       # No trust context, no verification, no audit -- same as before

Permissive Mode (Log Only)
---------------------------

Log trust events without blocking. Ideal for staging and gradual rollout:

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
       trace_id="trace-staging-001",
       delegation_chain=["human-bob", "agent-analyzer"],
       verification_mode=TrustVerificationMode.PERMISSIVE,
   )

   verifier = TrustVerifier(
       config=TrustVerifierConfig(mode="permissive"),
   )

   with LocalRuntime(
       trust_context=ctx,
       trust_verifier=verifier,
       trust_verification_mode="permissive",
   ) as runtime:
       results, run_id = runtime.execute(workflow.build())
       # Trust context propagated; denied operations logged but allowed

Enforcing Mode (Block Untrusted)
--------------------------------

Block workflows that fail trust verification. For production use:

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
   from kailash.workflow.builder import WorkflowBuilder

   ctx = RuntimeTrustContext(
       trace_id="trace-prod-001",
       delegation_chain=["human-alice", "agent-orchestrator"],
       verification_mode=TrustVerificationMode.ENFORCING,
   )

   verifier = TrustVerifier(
       config=TrustVerifierConfig(mode="enforcing"),
   )

   workflow = WorkflowBuilder()
   workflow.add_node("PythonCodeNode", "secure_task", {
       "code": "result = {'status': 'executed with enforced trust'}"
   })

   with LocalRuntime(
       trust_context=ctx,
       trust_verifier=verifier,
       trust_verification_mode="enforcing",
   ) as runtime:
       try:
           results, run_id = runtime.execute(workflow.build())
       except Exception as e:
           print(f"Trust verification denied execution: {e}")

Trust Postures
==============

The CARE framework defines trust postures that control how strictly an agent
operates. Postures form a hierarchy -- delegation can only tighten constraints,
never loosen them.

Posture Levels
--------------

From most permissive to most restrictive:

1. **open**: Minimal constraints, maximum flexibility
2. **cautious**: Standard operating constraints
3. **restricted**: Elevated security, limited operations
4. **locked**: Maximum restriction, minimal operations

Posture Transitions
-------------------

Agents can transition between postures based on context, but the CARE framework
enforces that a delegating agent cannot grant more trust than it holds:

.. code-block:: text

   Human (open) -> Agent A (cautious) -> Agent B (restricted)
   # Agent B CANNOT be "open" -- constraints only tighten

Constraint Dimensions
---------------------

Trust constraints operate across multiple dimensions:

- **Temporal**: Time-bounded permissions (e.g., "valid for 1 hour")
- **Scope**: Limited to specific operations or data domains
- **Resource**: Budget, API call, or compute limits
- **Network**: Allowed external service connections

.. note::

   The posture system, constraint dimensions, and knowledge ledger are implemented
   in the Kaizen framework (v1.2.0+). The Core SDK provides the foundational
   ``RuntimeTrustContext`` for constraint propagation. To use postures, constraint
   dimensions, and the knowledge ledger, install ``kailash-kaizen``.

Knowledge Ledger
================

The CARE framework maintains a cryptographic knowledge ledger that records:

- Every delegation event
- Every constraint propagation
- Every trust verification decision
- RFC 3161 timestamps for non-repudiation

This ledger provides a complete, tamper-evident audit trail suitable for
enterprise compliance requirements (SOC2, HIPAA, GDPR).

Framework Integration
=====================

Kaizen Integration
------------------

The Kaizen AI agent framework integrates with CARE natively:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kaizen.api import Agent

   model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")

   # Kaizen agents automatically participate in trust chains
   agent = Agent(
       model=model,
       execution_mode="autonomous",
   )

See :doc:`../frameworks/kaizen` for Kaizen-specific trust features.

DataFlow Integration
--------------------

DataFlow operations can carry trust context for audited database operations.
See :doc:`../frameworks/dataflow`.

Nexus Integration
-----------------

Nexus multi-channel deployments can enforce trust at the API gateway level.
See :doc:`../frameworks/nexus`.

Best Practices
==============

1. **Start with permissive mode** in staging, move to enforcing in production
2. **Always include a human origin** in the delegation chain
3. **Use trace IDs** to correlate events across distributed systems
4. **Never loosen constraints** in delegation -- the framework enforces constraint
   tightening (numeric min, set intersection, boolean AND) via the ``with_constraints()``
   method on ``RuntimeTrustContext``
5. **Review audit logs** regularly for compliance
6. **Use RFC 3161 timestamps** for legal non-repudiation requirements
