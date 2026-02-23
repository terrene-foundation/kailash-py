.. _enterprise_deployment:

Production Deployment
======================

Deployment patterns for Kailash SDK applications in production environments.

Runtime Selection
-----------------

Choose the right runtime for your deployment target:

.. list-table::
   :widths: 30 35 35
   :header-rows: 1

   * - Environment
     - Runtime
     - Why
   * - Docker / FastAPI
     - ``AsyncLocalRuntime``
     - Async-optimized, no thread blocking
   * - CLI / Scripts
     - ``LocalRuntime``
     - Synchronous, simple execution
   * - Auto-detect
     - ``get_runtime()``
     - Picks based on context

Docker Deployment
-----------------

.. code-block:: dockerfile

   FROM python:3.11-slim

   WORKDIR /app

   # Install dependencies
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt

   # Copy application
   COPY . .

   # Use AsyncLocalRuntime in Docker
   CMD ["python", "main.py"]

Example ``main.py``:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.runtime import AsyncLocalRuntime
   from kailash.workflow.builder import WorkflowBuilder

   async def main():
       workflow = WorkflowBuilder()
       workflow.add_node("PythonCodeNode", "process", {
           "code": "result = {'status': 'running in production'}"
       })

       runtime = AsyncLocalRuntime(
           connection_validation="strict",
       )
       results, run_id = await runtime.execute_workflow_async(
           workflow.build(), inputs={}
       )

   if __name__ == "__main__":
       import asyncio
       asyncio.run(main())

Nexus Deployment
----------------

Deploy multi-channel services with Nexus:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from nexus import Nexus
   from nexus.auth.plugin import NexusAuthPlugin, JWTConfig

   app = Nexus(preset="enterprise")

   auth = NexusAuthPlugin(
       jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
       rbac={
           "admin": ["read", "write", "delete"],
           "user": ["read"],
       },
   )
   app.add_plugin(auth)

   @app.handler("health", description="Health check")
   async def health() -> dict:
       return {"status": "healthy"}

   app.start()

Environment Variables
---------------------

Production deployments must use ``.env`` or environment variables for all
configuration:

.. code-block:: bash

   # Required
   DEFAULT_LLM_MODEL=gpt-4o
   OPENAI_API_KEY=sk-...

   # Security
   JWT_SECRET=your-secret-at-least-32-characters-long

   # Database
   DATABASE_URL=postgresql://user:pass@host:5432/db

   # Optional
   KAILASH_LOG_LEVEL=INFO

Trust in Production
-------------------

For production deployments, use enforcing mode:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.runtime import AsyncLocalRuntime
   from kailash.runtime.trust import (
       RuntimeTrustContext,
       TrustVerificationMode,
       TrustVerifier,
       TrustVerifierConfig,
   )

   ctx = RuntimeTrustContext(
       trace_id="prod-trace-001",
       delegation_chain=["human-deployer", "service-agent"],
       verification_mode=TrustVerificationMode.ENFORCING,
   )

   verifier = TrustVerifier(
       config=TrustVerifierConfig(mode="enforcing"),
   )

   runtime = AsyncLocalRuntime(
       trust_context=ctx,
       trust_verifier=verifier,
       trust_verification_mode="enforcing",
       connection_validation="strict",
   )

See Also
--------

- :doc:`../core/runtime` -- Runtime architecture and configuration
- :doc:`../core/trust` -- CARE trust for production accountability
- :doc:`../frameworks/nexus` -- Multi-channel deployment
- :doc:`monitoring` -- Production monitoring
