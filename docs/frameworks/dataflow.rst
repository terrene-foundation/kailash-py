====================================
DataFlow -- Database Framework
====================================

**Version: 0.12.1** | ``pip install kailash-dataflow`` | ``from dataflow import DataFlow``

DataFlow is the zero-config database framework built on the Kailash Core SDK.
Declare a model with ``@db.model`` and get 11 production-ready database nodes
automatically -- no ORM, no boilerplate.

.. important::

   DataFlow is NOT an ORM. It generates workflow nodes for database operations.
   The underlying execution is ``runtime.execute(workflow.build())``.

Quick Start
===========

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

This single ``@db.model`` decorator generates 11 nodes:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Node
     - Description
   * - CREATE
     - Create a single record
   * - READ
     - Read a single record by ID
   * - UPDATE
     - Update a record (filter + fields)
   * - DELETE
     - Delete a record
   * - LIST
     - List records with optional filters
   * - UPSERT
     - Create or update based on conflict
   * - COUNT
     - Count matching records
   * - BULK_CREATE
     - Create multiple records at once
   * - BULK_UPDATE
     - Update multiple records at once
   * - BULK_DELETE
     - Delete multiple records at once
   * - BULK_UPSERT
     - Create or update multiple records

Critical Gotchas
================

These rules are non-negotiable. Violating them causes runtime errors:

1. **Primary key MUST be named** ``id``

   .. code-block:: python

      # CORRECT
      @db.model
      class User:
          id: int        # Must be named 'id'
          name: str

      # WRONG -- will fail
      # @db.model
      # class User:
      #     user_id: int  # Wrong name!
      #     name: str

2. **NEVER manually set** ``created_at`` **/** ``updated_at``

   These timestamps are auto-managed by DataFlow. Setting them manually
   causes conflicts.

3. **CreateNode uses FLAT parameters**

   .. code-block:: python

      from kailash.workflow.builder import WorkflowBuilder

      workflow = WorkflowBuilder()

      # CORRECT -- flat parameters
      workflow.add_node("CreateUser", "create", {
          "name": "Alice",
          "email": "alice@example.com"
      })

      # WRONG -- nested data
      # workflow.add_node("CreateUser", "create", {
      #     "data": {"name": "Alice", "email": "alice@example.com"}
      # })

4. **UpdateNode uses** ``filter`` **+** ``fields``

   .. code-block:: python

      workflow.add_node("UpdateUser", "update", {
          "filter": {"id": 1},
          "fields": {"name": "New Name"}
      })

5. **soft_delete only affects DELETE, NOT queries**

   If you enable soft delete, records are marked as deleted but still appear
   in LIST and READ queries unless you filter them explicitly.

6. **Use** ``$null`` **/** ``$exists`` **for NULL checking**

   .. code-block:: python

      workflow.add_node("ListUser", "list_no_email", {
          "filter": {"email": "$null"}
      })

Database Support
================

DataFlow supports multiple database backends:

- **PostgreSQL**: Full support including pgvector for vector search
- **SQLite**: Full support including in-memory databases
- **MySQL**: Standard CRUD operations

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from dataflow import DataFlow

   # PostgreSQL
   db = DataFlow(os.environ.get("DATABASE_URL", "postgresql://user:pass@localhost/mydb"))

   # SQLite (file)
   db = DataFlow("sqlite:///app.db")

   # SQLite (in-memory, for testing)
   db = DataFlow("sqlite:///:memory:")

Async Transactions
==================

Transaction nodes are ``AsyncNode`` subclasses that use ``async_run()``:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from dataflow import DataFlow

   db = DataFlow("sqlite:///app.db")

   # Transaction operations are async
   async with db.transaction() as tx:
       await tx.create(User, name="Alice", email="alice@example.com")
       await tx.create(User, name="Bob", email="bob@example.com")

Multi-Tenancy
=============

DataFlow provides auto-wired multi-tenancy through ``QueryInterceptor``,
which injects tenant filtering at 8 SQL execution points automatically:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from dataflow import DataFlow

   db = DataFlow(
       os.environ.get("DATABASE_URL"),
       tenant_id="tenant_001"
   )

   # All queries are automatically filtered by tenant_id
   # No need to add tenant_id to every query manually

Multi-Instance Isolation
========================

DataFlow supports multi-instance deployments with string IDs preserved
and deferred schema operations for both PostgreSQL and SQLite.

CARE Trust Integration
======================

DataFlow operations can carry trust context for audited database operations,
ensuring every data modification is traceable back to its human authorization.

See :doc:`../core/trust` for the complete CARE trust documentation.

Key Features Summary
====================

- **Zero-config**: ``@db.model`` generates 11 nodes automatically
- **Not an ORM**: Generates workflow nodes, not object-relational mappings
- **Async transactions**: Full async support
- **Auto-wired multi-tenancy**: QueryInterceptor at 8 SQL execution points
- **Multi-instance isolation**: String IDs preserved, deferred schema ops
- **PostgreSQL + SQLite**: Full support for both
- **CARE trust**: Audited database operations

Relationship to Core SDK
=========================

DataFlow is built ON the Core SDK. Every generated node executes through
``runtime.execute(workflow.build())``. You can always drop down to the
Core SDK for custom database workflows.

See Also
========

- :doc:`../core/workflows` -- WorkflowBuilder patterns
- :doc:`../core/runtime` -- Runtime configuration
- :doc:`../core/trust` -- CARE trust for audited operations
- :doc:`nexus` -- Deploy DataFlow operations as APIs
- :doc:`kaizen` -- AI agents that use DataFlow for data access
