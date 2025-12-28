.. _enterprise_compliance:

Compliance & Governance
========================

Enterprise compliance frameworks for regulatory requirements, data governance, and policy enforcement.

.. note::
   This section is under development. Core compliance features are available through the security framework.

Key Features
------------

- GDPR compliance automation
- Data governance and lineage
- Regulatory reporting
- Policy enforcement
- Audit trail management
- Data residency controls

Quick Example
-------------

.. code-block:: python

   from kailash.workflow.builder import WorkflowBuilder

   workflow = WorkflowBuilder()

   # GDPR compliance
   workflow.add_node("GDPRComplianceNode", "gdpr", {
       "auto_anonymize": True,
       "retention_policy": "7_years",
       "consent_tracking": True
   })

See the security documentation for available compliance features.
