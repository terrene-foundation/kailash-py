====================================
Nexus -- Multi-Channel Platform
====================================

**Version: 1.4.1** | ``pip install kailash-nexus`` | ``from nexus import Nexus``

Nexus is the multi-channel platform built on the Kailash Core SDK. Write a workflow
or handler once, and deploy it simultaneously as a REST API, CLI tool, and MCP server
with zero extra configuration.

Quick Start
===========

Handler Pattern (Recommended)
-----------------------------

The simplest way to create a multi-channel endpoint:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from nexus import Nexus

   app = Nexus()

   @app.handler("greet", description="Greeting handler")
   async def greet(name: str, greeting: str = "Hello") -> dict:
       """Direct async function as multi-channel workflow."""
       return {"message": f"{greeting}, {name}!"}

   app.start()
   # Available via:
   #   API:  POST /greet  {"name": "Alice"}
   #   CLI:  kailash greet --name Alice
   #   MCP:  Tool "greet" with {"name": "Alice"}

**Why use handlers?**

- Bypasses PythonCodeNode sandbox restrictions (no import blocking)
- Simpler syntax for straightforward workflows
- Automatic parameter derivation from function signatures
- Multi-channel deployment from a single function definition

Workflow Registration
---------------------

Register existing Core SDK workflows for multi-channel deployment:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from nexus import Nexus
   from kailash.workflow.builder import WorkflowBuilder

   app = Nexus()

   # Build a workflow
   workflow = WorkflowBuilder()
   workflow.add_node("PythonCodeNode", "process", {
       "code": "result = {'output': input_data.upper()}"
   })

   # Register it (two arguments: name + built workflow)
   app.register("process", workflow.build())
   app.start()

Core Concepts
=============

Unified Sessions
----------------

Nexus maintains session state across all channels:

.. code-block:: python

   app = Nexus()

   # Session state persists whether accessed via API, CLI, or MCP
   session = app.create_session()

Native Middleware API
---------------------

Starlette-compatible middleware for request/response processing:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from nexus import Nexus

   app = Nexus()

   # Add middleware directly
   app.add_middleware(my_middleware_class)

   # Include a router
   app.include_router(my_router)

   # Add a plugin
   app.add_plugin(my_plugin)

Preset System
-------------

One-line middleware stacks for common deployment patterns:

.. code-block:: python

   from nexus import Nexus

   # Available presets: none, lightweight, standard, saas, enterprise
   app = Nexus(preset="saas")

.. list-table::
   :widths: 20 80
   :header-rows: 1

   * - Preset
     - Description
   * - ``none``
     - No middleware
   * - ``lightweight``
     - Basic logging and error handling
   * - ``standard``
     - Logging, error handling, request validation
   * - ``saas``
     - Full SaaS stack with auth, rate limiting, tenant isolation
   * - ``enterprise``
     - Everything in saas plus compliance, audit, and governance

Authentication and Authorization
================================

NexusAuthPlugin
---------------

JWT-based authentication with RBAC, SSO, rate limiting, and tenant isolation:

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
           "admin": ["read", "write", "delete"],
           "user": ["read"],
       },
       tenant=TenantConfig(admin_role="admin"),
   )

   app.add_plugin(auth)

**SSO Providers:**

- GitHub
- Google
- Azure AD

**Security defaults:**

- ``cors_allow_credentials=False``
- JWT secrets must be >= 32 characters for HS\* algorithms
- RBAC error messages are sanitized (no information leakage)

Rate Limiting
-------------

.. code-block:: python

   from nexus.auth.plugin import NexusAuthPlugin

   auth = NexusAuthPlugin(
       rate_limit={
           "default": "100/minute",
           "api": "1000/hour",
       }
   )

Tenant Isolation
----------------

.. code-block:: python

   from nexus.auth.plugin import NexusAuthPlugin, TenantConfig

   auth = NexusAuthPlugin(
       tenant=TenantConfig(
           admin_role="tenant_admin",
       ),
   )

CARE Trust Integration
======================

Nexus can enforce trust at the API gateway level, ensuring all incoming
requests carry proper trust context through to workflow execution:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from nexus import Nexus

   app = Nexus(preset="enterprise")

   @app.handler("secure_op", description="Trust-enforced operation")
   async def secure_op(data: str) -> dict:
       # Trust context is propagated from the API gateway
       return {"result": f"Processed: {data}"}

See :doc:`../core/trust` for the complete CARE trust documentation.

Key Features Summary
====================

- **Multi-channel deployment**: API + CLI + MCP from one codebase
- **Handler pattern**: ``@app.handler()`` for direct function registration
- **Unified sessions**: State maintained across all channels
- **Native middleware**: Starlette-compatible middleware API
- **Preset system**: One-line middleware stacks
- **NexusAuthPlugin**: JWT, RBAC, SSO, rate limiting, tenant isolation, audit
- **Plugin protocol**: Extensible architecture
- **CARE trust**: Gateway-level trust enforcement

Relationship to Core SDK
=========================

Nexus is built ON the Core SDK. Every registered workflow or handler ultimately
executes through ``runtime.execute(workflow.build())``. Nexus adds the multi-channel
deployment layer on top.

See Also
========

- :doc:`../core/workflows` -- WorkflowBuilder patterns
- :doc:`../core/runtime` -- Runtime configuration
- :doc:`../core/trust` -- CARE trust framework
- :doc:`kaizen` -- AI agents that can be deployed via Nexus
- :doc:`dataflow` -- Database operations accessible through Nexus
