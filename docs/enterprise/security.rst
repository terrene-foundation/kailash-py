.. _enterprise_security:

Enterprise Security
===================

Enterprise security in the Kailash SDK is built on two foundations: the CARE trust
framework for cryptographic accountability and the NexusAuthPlugin for application-level
security.

CARE Trust Foundation
---------------------

All security features trace back to the CARE (Context, Action, Reasoning,
Evidence) framework. Every agent action is traceable to human
authorization through verifiable delegation chains.

See :doc:`../core/trust` for the complete CARE trust documentation.

NexusAuthPlugin
---------------

The ``NexusAuthPlugin`` provides a complete security stack:

- **JWT Authentication**: Token-based auth with configurable algorithms
- **RBAC**: Role-based access control with permission matrices
- **SSO**: Single sign-on via GitHub, Google, Azure AD
- **Rate Limiting**: Per-user and per-endpoint rate limits
- **Tenant Isolation**: Multi-tenant data isolation
- **Audit Logging**: Comprehensive operation logging

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from nexus import Nexus
   from nexus.auth.plugin import NexusAuthPlugin, JWTConfig, TenantConfig

   app = Nexus()

   auth = NexusAuthPlugin(
       jwt=JWTConfig(
           secret=os.environ["JWT_SECRET"],  # Must be >= 32 chars for HS*
       ),
       rbac={
           "admin": ["read", "write", "delete", "manage"],
           "editor": ["read", "write"],
           "viewer": ["read"],
       },
       tenant=TenantConfig(admin_role="admin"),
   )

   app.add_plugin(auth)

Security Defaults
-----------------

The SDK enforces secure defaults:

- ``cors_allow_credentials=False`` -- credentials require explicit opt-in
- JWT secrets must be >= 32 characters for HS\* algorithms
- RBAC error messages are sanitized to prevent information leakage
- Connection validation prevents parameter injection through workflow connections

Trust Verification Modes
------------------------

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Mode
     - Behavior
   * - ``disabled``
     - No trust checks (default, backward compatible)
   * - ``permissive``
     - Log trust events without blocking
   * - ``enforcing``
     - Block operations that fail trust verification

See Also
--------

- :doc:`../core/trust` -- CARE trust framework
- :doc:`../frameworks/nexus` -- NexusAuthPlugin configuration
- :doc:`compliance` -- Compliance and governance
