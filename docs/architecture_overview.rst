Architecture Overview
=====================

The Kailash Python SDK follows a modular, node-based architecture designed for maximum flexibility and extensibility.

Core Components
---------------

**Nodes**
  The fundamental building blocks of workflows. Each node performs a specific task and can be connected to other nodes to create complex processing pipelines.

**Workflows**
  Directed graphs that define the flow of data and execution between nodes. Workflows can be cyclic or acyclic, supporting iterative and sequential processing.

**Runtime**
  The execution engine that processes workflows. Multiple runtime options are available including local, async, parallel, and Docker-based execution.

**Middleware**
  Enterprise features like authentication, monitoring, and API gateway functionality that can be added to workflows and applications.

Architecture Principles
-----------------------

1. **Composability**: Small, focused nodes that can be combined into complex workflows
2. **Extensibility**: Easy to create custom nodes by extending base classes
3. **Flexibility**: Multiple runtime options and execution strategies
4. **Enterprise-Ready**: Built-in support for security, monitoring, and scalability

.. note::
   For detailed architecture decisions, see the :doc:`Architecture Decision Records <adr/README>`.
