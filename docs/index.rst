.. Kailash Python SDK documentation master file

Kailash SDK Documentation
=========================

.. image:: https://img.shields.io/badge/python-3.11+-blue.svg
   :target: https://www.python.org/downloads/
   :alt: Python Version

.. image:: https://img.shields.io/badge/version-0.12.5-green.svg
   :alt: SDK Version

.. image:: https://img.shields.io/badge/trust-CARE%20%2F%20EATP-blueviolet.svg
   :alt: CARE Trust Framework

Enterprise AI Agent Platform with Cryptographic Trust

The **Kailash SDK** is the enterprise-grade platform for building production AI agent
workflows with cryptographic trust chains, multi-channel deployment, and zero-config
database operations. From a single workflow to orchestrated multi-agent systems, Kailash
provides the foundation for verifiable, auditable AI applications.

**Current Release: v0.12.5** (Core SDK) | DataFlow v0.12.4 | Nexus v1.4.2 | Kaizen v1.2.5

Quick Links
-----------

**Getting Started**
   New to Kailash? Start with :doc:`installation` and your :doc:`first workflow <quickstart>`.

**Core SDK**
   Build workflows with :doc:`WorkflowBuilder <core/workflows>`, execute with
   :doc:`LocalRuntime or AsyncLocalRuntime <core/runtime>`, and secure with
   :doc:`CARE trust chains <core/trust>`.

**Frameworks**
   - **Kaizen** (v1.2.5): :doc:`AI agents <frameworks/kaizen>` with signatures, multi-agent coordination, and CARE trust
   - **Nexus** (v1.4.2): :doc:`Multi-channel platform <frameworks/nexus>` -- API + CLI + MCP from one codebase
   - **DataFlow** (v0.12.4): :doc:`Zero-config database <frameworks/dataflow>` with 11 auto-generated nodes per model

**Enterprise**
   :doc:`Security <enterprise/security>`, :doc:`compliance <enterprise/compliance>`,
   :doc:`monitoring <enterprise/monitoring>`, and :doc:`deployment <enterprise/deployment>`.

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   installation
   quickstart
   getting_started

.. toctree::
   :maxdepth: 2
   :caption: Core SDK

   core/workflows
   core/nodes
   core/runtime
   core/trust
   core/mcp

.. toctree::
   :maxdepth: 2
   :caption: Frameworks

   frameworks/kaizen
   frameworks/nexus
   frameworks/dataflow

.. toctree::
   :maxdepth: 2
   :caption: Enterprise

   enterprise/index
   enterprise/security
   enterprise/compliance
   enterprise/monitoring
   enterprise/deployment
   enterprise/edge_computing

.. toctree::
   :maxdepth: 2
   :caption: Examples & Patterns

   examples/index

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/index

.. toctree::
   :maxdepth: 1
   :caption: Development

   contributing
   testing
   best_practices
   license

Architecture Overview
---------------------

The Kailash SDK provides a layered architecture:

.. code-block:: text

   +----------------------------------------------+
   |           Frameworks (Choose One+)            |
   |  Kaizen (AI Agents)  |  Nexus (Multi-Channel) |
   |  DataFlow (Database)  |  MCP (Integration)    |
   +----------------------------------------------+
   |              Core SDK Foundation              |
   |  WorkflowBuilder | Runtime | Nodes | Trust    |
   +----------------------------------------------+
   |    User Infrastructure (not part of SDK)       |
   |  Docker | Kubernetes | Cloud | Monitoring     |
   +----------------------------------------------+

**Critical relationships:**

- **DataFlow, Nexus, and Kaizen are built ON the Core SDK** -- they do not replace it
- **All frameworks share the same workflow execution**: ``runtime.execute(workflow.build())``
- **CARE trust** is woven through every layer for cryptographic accountability

What Makes Kailash Different
----------------------------

**Cryptographic Trust (CARE/EATP)**
   Every agent action traces back to a human authorization through verifiable delegation
   chains. No other Python AI framework provides built-in cryptographic trust at the
   runtime level. See :doc:`core/trust`.

**Multi-Channel from One Codebase**
   Write a workflow once. Deploy it as a REST API, CLI tool, and MCP server simultaneously
   with Nexus. See :doc:`frameworks/nexus`.

**Zero-Config Database Operations**
   Declare a model with ``@db.model`` and get 11 production-ready database nodes
   automatically -- CRUD, bulk operations, counting, and upserting. See
   :doc:`frameworks/dataflow`.

**Signature-Based AI Agents**
   Define agent behavior with signatures, not prompts. Agents automatically optimize,
   fall back to alternative models, and coordinate in multi-agent teams. See
   :doc:`frameworks/kaizen`.

Indices and Tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
