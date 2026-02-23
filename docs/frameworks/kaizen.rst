==============================
Kaizen -- AI Agent Framework
==============================

**Version: 1.2.1** | ``pip install kailash-kaizen`` | ``from kaizen.api import Agent``

Kaizen is the production-ready AI agent framework built on the Kailash Core SDK.
It provides signature-based programming, multi-agent coordination, automatic
optimization, and CARE/EATP trust integration.

Quick Start
===========

Two-Line Agent
--------------

.. code-block:: python

   import asyncio
   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kaizen.api import Agent

   async def main():
       model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")
       agent = Agent(model=model)
       result = await agent.run("What are the key benefits of cryptographic trust?")
       print(result)

   asyncio.run(main())

Autonomous Agent with Memory
-----------------------------

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

       result = await agent.run("Research edge computing trends and summarize findings")
       print(result)

   asyncio.run(main())

.. warning::

   Never hardcode model names. Always read from ``.env`` via ``os.environ``.

Core Concepts
=============

Unified Agent API
-----------------

Since v1.0.0, Kaizen provides a progressive configuration API from two-line
quickstart to expert mode:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kaizen.api import Agent

   model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")

   # Quickstart -- minimal configuration
   simple = Agent(model=model)

   # Standard -- with memory and execution mode
   standard = Agent(
       model=model,
       execution_mode="autonomous",
       memory="session",
   )

   # Expert -- full configuration
   expert = Agent(
       model=model,
       execution_mode="autonomous",
       memory="session",
       tool_access="constrained",
   )

Signature-Based Programming
----------------------------

Define agent behavior with signatures instead of raw prompts. Signatures are
declarative descriptions of inputs and outputs that enable automatic optimization:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kaizen.api import Agent

   model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")

   agent = Agent(model=model)

   # Signature-based task definition
   result = await agent.run(
       "Given {context}, answer {question}",
       context="Annual revenue was $50M with 15% YoY growth",
       question="What is the growth trajectory?"
   )

.. note::

   The ``await`` keyword requires an async context. Run these examples inside
   ``asyncio.run()`` or an async framework like FastAPI.

BaseAgent Architecture
----------------------

For advanced use cases, extend ``BaseAgent`` directly:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kaizen.core.base_agent import BaseAgent

   model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")

   class AnalysisAgent(BaseAgent):
       """Custom agent for data analysis tasks."""

       async def process(self, input_data):
           # Custom processing logic
           return await self.run(f"Analyze: {input_data}")

Multi-Agent Coordination
========================

OrchestrationRuntime
--------------------

Use ``OrchestrationRuntime`` for multi-agent coordination (``AgentTeam`` is deprecated):

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kaizen.api import Agent
   from kaizen.core.registry import AgentRegistry

   model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")

   # Create specialized agents
   researcher = Agent(model=model, execution_mode="autonomous")
   analyst = Agent(model=model, execution_mode="autonomous")

   # Register in AgentRegistry for scale
   registry = AgentRegistry()
   registry.register(researcher)
   registry.register(analyst)

FallbackRouter Safety
---------------------

The ``FallbackRouter`` provides safe model fallback with callbacks:

- ``on_fallback`` callback fires before each fallback (raise ``FallbackRejectedError`` to block)
- WARNING-level logging on every fallback event
- Model capability validation before attempting fallback

CARE/EATP Trust
===============

Since v1.2.0, Kaizen includes the CARE trust framework with:

- **Cryptographic trust chains**: Every agent action traces to human authorization
- **Posture system**: Trust postures (open, cautious, restricted, locked) that only tighten through delegation
- **Constraint dimensions**: Temporal, scope, resource, and network constraints
- **Knowledge ledger**: Tamper-evident audit log
- **RFC 3161 timestamping**: Cryptographic timestamps for non-repudiation

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kaizen.api import Agent

   model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")

   # Agents automatically participate in CARE trust chains
   # when the runtime has a trust context attached
   agent = Agent(
       model=model,
       execution_mode="autonomous",
   )

See :doc:`../core/trust` for the complete CARE trust documentation.

MCP Session Methods
===================

Kaizen agents can discover and use MCP resources:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kaizen.api import Agent

   model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")
   agent = Agent(model=model)

   # Discover available MCP resources
   resources = await agent.discover_mcp_resources()

   # Read a specific MCP resource
   data = await agent.read_mcp_resource("resource://my-data")

   # Discover available MCP prompts
   prompts = await agent.discover_mcp_prompts()

   # Get a specific MCP prompt
   prompt = await agent.get_mcp_prompt("analysis-prompt")

.. note::

   The ``await`` keyword requires an async context. Run these examples inside
   ``asyncio.run()`` or an async framework like FastAPI.

Key Features Summary
====================

- **Unified Agent API** with progressive configuration (v1.0.0+)
- **Signature-based programming** for declarative agent behavior
- **BaseAgent architecture** for extensibility
- **Multi-agent coordination** via OrchestrationRuntime
- **FallbackRouter** with safety callbacks and capability validation
- **CARE/EATP trust** with cryptographic delegation chains (v1.2.0+)
- **MCP integration** with resource and prompt discovery
- **Automatic optimization** of agent behavior
- **Error handling** with comprehensive audit trails

Relationship to Core SDK
========================

Kaizen is built ON the Core SDK. Under the hood, agents use
``runtime.execute(workflow.build())`` for execution. You can always drop down
to the Core SDK for fine-grained control.

See Also
========

- :doc:`../core/trust` -- CARE trust framework
- :doc:`../core/runtime` -- Runtime configuration
- :doc:`nexus` -- Multi-channel deployment for agent workflows
- :doc:`dataflow` -- Database operations for agent data
