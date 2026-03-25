============
Installation
============

This guide covers all installation methods for the Kailash SDK and its frameworks.

System Requirements
===================

- **Python**: 3.11 or higher
- **Operating System**: macOS, Linux, Windows
- **Memory**: 4 GB RAM minimum, 8 GB recommended
- **Disk Space**: 500 MB for SDK and dependencies

.. note::

   Python 3.11+ is required. Earlier Python versions are not supported.

Quick Install
=============

Core SDK
--------

.. code-block:: bash

   pip install kailash

Frameworks
----------

Install frameworks separately based on your needs:

.. code-block:: bash

   # AI agents with signatures and multi-agent coordination
   pip install kailash-kaizen

   # Multi-channel platform (API + CLI + MCP)
   pip install kailash-nexus

   # Zero-config database operations
   pip install kailash-dataflow

Or install everything:

.. code-block:: bash

   pip install kailash kailash-kaizen kailash-nexus kailash-dataflow

Install from Source
===================

For development or to get the latest features:

.. code-block:: bash

   git clone https://github.com/terrene-foundation/kailash-py.git
   cd kailash-py
   uv sync

.. note::

   We use `uv <https://github.com/astral-sh/uv>`_ as the package manager.
   Install it with: ``curl -LsSf https://astral.sh/uv/install.sh | sh``

Environment Setup
=================

The Kailash SDK reads all API keys and model names from environment variables.
Create a ``.env`` file in your project root:

.. code-block:: bash

   # .env file -- NEVER commit this to git
   OPENAI_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...
   GOOGLE_API_KEY=AIza...

   # Model configuration -- NEVER hardcode model names
   DEFAULT_LLM_MODEL=gpt-4o
   OPENAI_PROD_MODEL=gpt-4o

Load the ``.env`` file in your Python code:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()  # MUST be before any os.environ access

   model = os.environ.get("DEFAULT_LLM_MODEL")

.. warning::

   Never hardcode API keys or model names. The SDK enforces this through
   pre-commit hooks. All keys and model names must come from ``.env``.

Virtual Environment (Recommended)
---------------------------------

.. code-block:: bash

   # Create virtual environment
   python -m venv .venv

   # Activate on Linux/macOS
   source .venv/bin/activate

   # Activate on Windows
   .venv\Scripts\activate

   # Install SDK
   pip install kailash

Verify Installation
===================

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.workflow.builder import WorkflowBuilder
   from kailash.runtime import LocalRuntime

   # Build a simple workflow
   workflow = WorkflowBuilder()
   workflow.add_node("PythonCodeNode", "test", {
       "code": "result = {'status': 'Kailash SDK installed successfully!'}"
   })

   # Execute
   with LocalRuntime() as runtime:
       results, run_id = runtime.execute(workflow.build())
       print(results["test"]["result"]["status"])

Docker Installation
===================

For containerized deployments, use ``AsyncLocalRuntime``:

.. code-block:: dockerfile

   FROM python:3.11-slim

   RUN pip install kailash kailash-nexus

   COPY . /app
   WORKDIR /app

   # Use AsyncLocalRuntime for Docker/FastAPI
   CMD ["python", "main.py"]

Example ``main.py`` for Docker:

.. code-block:: python

   import os
   from dotenv import load_dotenv
   load_dotenv()

   from kailash.runtime import AsyncLocalRuntime
   from kailash.workflow.builder import WorkflowBuilder

   async def main():
       workflow = WorkflowBuilder()
       workflow.add_node("PythonCodeNode", "process", {
           "code": "result = {'status': 'running in Docker'}"
       })

       runtime = AsyncLocalRuntime()
       try:
           results, run_id = await runtime.execute_workflow_async(
               workflow.build(), inputs={}
           )
           print(results)
       finally:
           runtime.close()

   if __name__ == "__main__":
       import asyncio
       asyncio.run(main())

Development Setup
=================

For contributing to the SDK:

.. code-block:: bash

   # Clone the repository
   git clone https://github.com/terrene-foundation/kailash-py.git
   cd kailash-py

   # Install with uv
   uv sync

   # Run tests
   pytest tests/unit/ --timeout=1       # Fast unit tests
   pytest tests/integration/ --timeout=5  # Integration tests

Next Steps
==========

- :doc:`quickstart` -- Build your first workflow in 5 minutes
- :doc:`getting_started` -- Comprehensive guide to core concepts
- :doc:`core/workflows` -- Deep dive into WorkflowBuilder
- :doc:`core/trust` -- Learn about CARE cryptographic trust
