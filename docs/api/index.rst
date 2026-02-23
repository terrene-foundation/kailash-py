=============
API Reference
=============

Auto-generated API documentation from the Kailash SDK source code.

.. toctree::
   :maxdepth: 2

   workflow
   runtime
   nodes
   workflow_api
   middleware
   access_control
   tracking
   monitoring
   visualization
   utils
   cli

Core SDK
========

Workflow
--------

.. autosummary::
   :toctree: _generated

   kailash.workflow.builder.WorkflowBuilder

Runtime
-------

.. autosummary::
   :toctree: _generated

   kailash.runtime.local.LocalRuntime
   kailash.runtime.async_local.AsyncLocalRuntime
   kailash.runtime.base.BaseRuntime

Trust
-----

.. autosummary::
   :toctree: _generated

   kailash.runtime.trust

Nodes
-----

See :doc:`nodes` for the complete node reference covering 140+ node types
organized by category (AI, API, Code, Data, Database, Logic, Monitoring,
Transaction, Transform).

Frameworks
==========

Kaizen (v1.2.1)
----------------

.. code-block:: python

   from kaizen.api import Agent
   from kaizen.core.base_agent import BaseAgent
   from kaizen.core.registry import AgentRegistry

See :doc:`../frameworks/kaizen` for framework documentation.

Nexus (v1.4.1)
---------------

.. code-block:: python

   from nexus import Nexus
   from nexus.auth.plugin import NexusAuthPlugin, JWTConfig, TenantConfig

See :doc:`../frameworks/nexus` for framework documentation.

DataFlow (v0.12.1)
------------------

.. code-block:: python

   from dataflow import DataFlow

See :doc:`../frameworks/dataflow` for framework documentation.

Import Quick Reference
======================

.. code-block:: python

   # Core SDK
   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime import LocalRuntime, AsyncLocalRuntime, get_runtime
   from kailash.runtime.trust import (
       RuntimeTrustContext,
       TrustVerificationMode,
       TrustVerifier,
       TrustVerifierConfig,
   )
   from kailash.nodes.base import BaseNode, AsyncNode, NodeParameter

   # Kaizen (AI Agents)
   from kaizen.api import Agent
   from kaizen.core.base_agent import BaseAgent
   from kaizen.core.registry import AgentRegistry

   # Nexus (Multi-Channel)
   from nexus import Nexus
   from nexus.auth.plugin import NexusAuthPlugin, JWTConfig, TenantConfig

   # DataFlow (Database)
   from dataflow import DataFlow
