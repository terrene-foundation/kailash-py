==========
Quickstart
==========

Get up and running with the Kailash SDK in 5 minutes. This guide shows a quick
example for each major component.

Core SDK -- Your First Workflow
===============================

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime import LocalRuntime

   # 1. Build a workflow
   workflow = WorkflowBuilder()
   workflow.add_node("PythonCodeNode", "greet", {
       "code": "result = {'message': f'Hello, {name}!'}"
   })

   # 2. Execute it
   with LocalRuntime() as runtime:
       results, run_id = runtime.execute(
           workflow.build(),
           parameters={"greet": {"name": "World"}}
       )

       print(results["greet"]["result"]["message"])
   # Output: Hello, World!

The pattern is always the same: **build a workflow, then execute it with a runtime**.

.. code-block:: python

   # ALWAYS this pattern:
   results, run_id = runtime.execute(workflow.build())

   # NEVER this:
   # workflow.execute(runtime)  -- WRONG

Kaizen -- AI Agent in 3 Lines
=============================

.. code-block:: python

   import asyncio
   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kaizen.api import Agent

   async def main():
       # Read model from .env -- NEVER hardcode model names
       model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")

       agent = Agent(model=model)
       result = await agent.run("Summarize the key benefits of cryptographic trust in AI systems")
       print(result)

   asyncio.run(main())

**With memory and autonomous mode:**

.. code-block:: python

   import asyncio
   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kaizen.api import Agent

   async def main():
       model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")

       agent = Agent(
           model=model,
           execution_mode="autonomous",  # TAOD loop
           memory="session",
           tool_access="constrained",
       )

       result = await agent.run("Research and summarize recent advances in edge computing")
       print(result)

   asyncio.run(main())

Nexus -- Multi-Channel Platform
================================

Deploy a function as API + CLI + MCP simultaneously:

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
   # Now available via:
   #   API:  POST /greet {"name": "Alice"}
   #   CLI:  kailash greet --name Alice
   #   MCP:  Tool call "greet" with {"name": "Alice"}

**Why handlers?**

- Bypasses PythonCodeNode sandbox restrictions
- Simpler syntax for straightforward workflows
- Automatic parameter derivation from function signatures
- Multi-channel deployment from a single function

DataFlow -- Zero-Config Database
=================================

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from dataflow import DataFlow

   db = DataFlow("sqlite:///app.db")

   @db.model
   class User:
       id: int
       name: str
       email: str

   db.create_tables()

   # The @db.model decorator auto-generates 11 nodes:
   # CREATE, READ, UPDATE, DELETE, LIST, UPSERT, COUNT
   # BULK_CREATE, BULK_UPDATE, BULK_DELETE, BULK_UPSERT

.. note::

   DataFlow is NOT an ORM. It auto-generates workflow nodes for database
   operations. The primary key MUST be named ``id``. Never manually set
   ``created_at`` / ``updated_at`` -- they are auto-managed.

CARE Trust -- Context, Action, Reasoning, Evidence
==========================================

Every workflow can carry a cryptographic trust chain from human to agent:

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

   # Create trust context with delegation chain
   ctx = RuntimeTrustContext(
       trace_id="trace-001",
       delegation_chain=["human-alice", "agent-coordinator"],
       verification_mode=TrustVerificationMode.PERMISSIVE,
   )

   verifier = TrustVerifier(
       config=TrustVerifierConfig(mode="permissive"),
   )

   # Execute with trust verification
   workflow = WorkflowBuilder()
   workflow.add_node("PythonCodeNode", "process", {
       "code": "result = {'processed': True}"
   })

   with LocalRuntime(
       trust_context=ctx,
       trust_verifier=verifier,
       trust_verification_mode="permissive",
   ) as runtime:
       results, run_id = runtime.execute(workflow.build())
       # Trust context propagated; denied operations logged but allowed

See :doc:`core/trust` for the complete CARE/EATP trust framework documentation.

Async Runtime for Docker / FastAPI
==================================

When running in Docker or with FastAPI, use ``AsyncLocalRuntime``:

.. code-block:: python

   import asyncio
   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.runtime import AsyncLocalRuntime
   from kailash.workflow.builder import WorkflowBuilder

   workflow = WorkflowBuilder()
   workflow.add_node("PythonCodeNode", "process", {
       "code": "result = {'status': 'async processing complete'}"
   })

   async def main():
       runtime = AsyncLocalRuntime()
       try:
           results, run_id = await runtime.execute_workflow_async(
               workflow.build(), inputs={}
           )
           print(results)
       finally:
           runtime.close()

   asyncio.run(main())

.. note::

   The ``await`` keyword requires an async context. The examples above use
   ``asyncio.run()``. In async frameworks like FastAPI, you can use ``await``
   directly inside route handlers.

Both ``LocalRuntime`` and ``AsyncLocalRuntime`` return the same
``(results, run_id)`` tuple. Choose based on your execution context:

- **CLI / scripts**: ``LocalRuntime``
- **Docker / FastAPI / async**: ``AsyncLocalRuntime``
- **Auto-detect**: ``from kailash.runtime import get_runtime; runtime = get_runtime()``

Next Steps
==========

- :doc:`getting_started` -- Comprehensive walkthrough of core concepts
- :doc:`core/workflows` -- WorkflowBuilder patterns and connections
- :doc:`core/runtime` -- Runtime configuration and execution modes
- :doc:`core/trust` -- CARE trust framework deep dive
- :doc:`frameworks/kaizen` -- AI agent framework
- :doc:`frameworks/nexus` -- Multi-channel platform
- :doc:`frameworks/dataflow` -- Database operations framework
