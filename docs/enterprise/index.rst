.. _enterprise:

Enterprise Features
===================

The Kailash SDK provides comprehensive enterprise-grade features for production
deployments, built on the CARE (Context, Action, Reasoning, Evidence) trust
framework.

.. toctree::
   :maxdepth: 2

   security
   compliance
   monitoring
   deployment
   edge_computing

Overview
--------

**CARE Trust Foundation**
   All enterprise features are built on the CARE trust framework, providing
   cryptographic accountability from human authorization through agent execution.
   See :doc:`../core/trust`.

**Enterprise Security**
   JWT authentication, RBAC, SSO providers, rate limiting, tenant isolation,
   and audit logging through the NexusAuthPlugin. See :doc:`security`.

**Compliance & Governance**
   EATP-compliant audit trails with RFC 3161 timestamping, trust postures,
   and constraint enforcement for SOC2, HIPAA, and GDPR. See :doc:`compliance`.

**Monitoring & Analytics**
   Real-time performance monitoring, workflow execution tracking, and
   enterprise-grade observability. See :doc:`monitoring`.

**Production Deployment**
   Docker, Kubernetes, and cloud deployment patterns with async runtime
   optimization. See :doc:`deployment`.

**Edge Computing**
   Distributed coordination, state management, and enterprise reliability
   across edge locations. See :doc:`edge_computing`.

CARE Trust Integration
----------------------

Every enterprise feature integrates with the CARE trust framework:

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

   # Enterprise workflows carry trust context
   ctx = RuntimeTrustContext(
       trace_id="enterprise-trace-001",
       delegation_chain=["human-admin", "agent-orchestrator"],
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

   # All workflow operations are now trust-verified and audited

Getting Started
--------------

1. **Trust**: Start with :doc:`../core/trust` for the CARE framework foundation
2. **Security**: Set up :doc:`security` with NexusAuthPlugin
3. **Compliance**: Configure :doc:`compliance` audit trails
4. **Monitoring**: Deploy :doc:`monitoring` for observability
5. **Deployment**: Follow :doc:`deployment` patterns for production
