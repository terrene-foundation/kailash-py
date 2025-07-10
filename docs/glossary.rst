Glossary
========

.. glossary::
   :sorted:

   Node
      The fundamental building block of a workflow. Each node performs a specific task such as reading data, transforming it, or calling an API.

   Workflow
      A directed graph of connected nodes that defines a complete data processing or automation pipeline.

   Runtime
      The execution engine that processes workflows. Examples include LocalRuntime, AsyncLocalRuntime, and DockerRuntime.

   MCP
      Model Context Protocol - A standard for AI agents to interact with external tools and services.

   Parameter
      Configuration values passed to nodes or workflows at execution time.

   Edge
      A connection between two nodes in a workflow that defines the flow of data.

   Middleware
      Components that add cross-cutting functionality like authentication, monitoring, or API gateway features.

   DataFlow
      A framework built on top of Kailash SDK for zero-configuration database operations.

   Nexus
      A multi-channel orchestration platform that provides unified API, CLI, and MCP interfaces.

   ABAC
      Attribute-Based Access Control - A security model that uses attributes to determine access permissions.

   RBAC
      Role-Based Access Control - A security model that uses roles to determine access permissions.

   Circuit Breaker
      A resilience pattern that prevents cascading failures by monitoring and controlling service calls.

   Bulkhead
      A resilience pattern that isolates resources to prevent failures from spreading.

   Saga Pattern
      A distributed transaction pattern that manages long-running business processes across multiple services.

   2PC
      Two-Phase Commit - A distributed transaction protocol that ensures atomicity across multiple databases.
