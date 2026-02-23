============================
MCP Server Integration
============================

The Kailash SDK includes built-in support for the Model Context Protocol (MCP),
enabling AI agents to discover and use tools, resources, and prompts exposed by
Kailash workflows.

Overview
========

MCP provides a standard protocol for AI applications to interact with external
capabilities. The Kailash SDK can act as both an MCP server (exposing workflows
as tools) and integrate with MCP clients (consuming external tools).

MCP Server
==========

Expose workflows as MCP tools that any MCP-compatible client can call:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from nexus import Nexus

   app = Nexus()

   @app.handler("analyze_data", description="Analyze a dataset")
   async def analyze_data(data: str, analysis_type: str = "summary") -> dict:
       """Analyze data and return insights."""
       return {
           "analysis": f"Performed {analysis_type} analysis on data",
           "result": "Analysis complete"
       }

   app.start()
   # This handler is now available as:
   #   - REST API: POST /analyze_data
   #   - CLI: kailash analyze_data --data "..." --analysis_type summary
   #   - MCP tool: "analyze_data" with parameters

The Nexus framework automatically registers handlers as MCP tools with proper
schema generation from function signatures.

MCP Client Integration
======================

Kaizen agents can discover and use MCP resources:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kaizen.api import Agent

   model = os.environ.get("DEFAULT_LLM_MODEL", "gpt-4o")

   agent = Agent(model=model)

   # Discover MCP resources
   resources = await agent.discover_mcp_resources()

   # Read a specific resource
   data = await agent.read_mcp_resource("resource://my-data")

   # Discover available prompts
   prompts = await agent.discover_mcp_prompts()

   # Get a specific prompt
   prompt = await agent.get_mcp_prompt("analysis-prompt")

Transports
==========

The MCP implementation supports multiple transport protocols:

- **stdio**: Standard input/output for local process communication
- **SSE**: Server-Sent Events for HTTP streaming
- **HTTP**: Standard HTTP for request/response patterns

Security
========

MCP integration respects the CARE trust framework. When trust is enabled,
MCP tool calls carry the trust context through the delegation chain:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.runtime import LocalRuntime
   from kailash.runtime.trust import (
       RuntimeTrustContext,
       TrustVerificationMode,
   )

   ctx = RuntimeTrustContext(
       trace_id="trace-mcp-001",
       delegation_chain=["human-operator", "agent-coordinator"],
       verification_mode=TrustVerificationMode.ENFORCING,
   )

   runtime = LocalRuntime(
       trust_context=ctx,
       trust_verification_mode="enforcing",
   )

   # MCP tool calls executed through this runtime carry the trust context

See :doc:`trust` for the complete CARE trust documentation.

See Also
========

- :doc:`../frameworks/nexus` -- Multi-channel deployment including MCP
- :doc:`../frameworks/kaizen` -- AI agents with MCP session methods
- :doc:`trust` -- CARE trust framework for secure MCP operations
