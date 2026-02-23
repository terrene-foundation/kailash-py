.. _enterprise_compliance:

Compliance & Governance
========================

Enterprise compliance in the Kailash SDK is built on the CARE trust framework,
providing cryptographic audit trails suitable for SOC2, HIPAA, and GDPR compliance.

CARE-Based Compliance
---------------------

The CARE framework provides:

- **EATP-compliant audit trails**: Every workflow execution generates a verifiable event log
- **RFC 3161 timestamping**: Cryptographic timestamps for legal non-repudiation
- **Delegation chain tracking**: Complete provenance from human authorization to agent action
- **Constraint enforcement**: Trust constraints can only be tightened through delegation
- **Knowledge ledger**: Tamper-evident record of all trust events

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

   # Enforcing mode for compliance-critical workflows
   ctx = RuntimeTrustContext(
       trace_id="compliance-audit-001",
       delegation_chain=["human-compliance-officer", "agent-processor"],
       verification_mode=TrustVerificationMode.ENFORCING,
   )

   verifier = TrustVerifier(
       config=TrustVerifierConfig(mode="enforcing"),
   )

   runtime = LocalRuntime(
       trust_context=ctx,
       trust_verifier=verifier,
       trust_verification_mode="enforcing",
   )

   # All operations are now audited with cryptographic timestamps

Trust Postures for Governance
-----------------------------

The posture system enforces governance policies:

- **open**: Development environments
- **cautious**: Standard production operations
- **restricted**: Sensitive data processing
- **locked**: Compliance-critical, minimal operations

Postures only tighten through delegation -- an agent cannot grant more
trust than it holds.

Data Governance
---------------

- **Audit logging** through NexusAuthPlugin
- **Tenant isolation** for data segregation
- **Soft delete** support in DataFlow for data retention compliance

See Also
--------

- :doc:`../core/trust` -- Complete CARE trust documentation
- :doc:`security` -- Enterprise security features
- :doc:`monitoring` -- Audit monitoring and alerting
