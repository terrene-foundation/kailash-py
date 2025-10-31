.. _enterprise_security:

Enterprise Security
===================

Comprehensive security framework for production deployments including multi-factor authentication, threat detection, compliance, and audit capabilities.

.. note::
   This section is under development. For now, see the core security documentation at :doc:`../security`.

Key Features
------------

- Multi-factor authentication
- Threat detection and response
- RBAC and ABAC authorization
- Compliance frameworks (GDPR, SOC2, HIPAA)
- Comprehensive audit trails
- Security monitoring and alerting

Quick Example
-------------

.. code-block:: python

   from kailash.workflow.builder import WorkflowBuilder

   workflow = WorkflowBuilder()

   # Multi-factor authentication
   workflow.add_node("MultiFactorAuthNode", "auth", {
       "methods": ["password", "totp"],
       "require_all": False
   })

   # Threat detection
   workflow.add_node("ThreatDetectionNode", "security", {
       "enable_ml": True,
       "detection_rules": ["brute_force", "anomaly"]
   })

See :doc:`../security` for detailed security documentation.
