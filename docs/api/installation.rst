============
Installation
============

This guide covers all installation methods and configurations for the Kailash Python SDK.

System Requirements
===================

Minimum Requirements
--------------------

- **Python**: 3.8 or higher
- **Operating System**: Windows 10+, macOS 10.14+, Linux (Ubuntu 18.04+, CentOS 7+)
- **Memory**: 4GB RAM minimum, 8GB recommended
- **Disk Space**: 500MB for SDK and dependencies

Python Version Support
----------------------

.. list-table:: Python Version Compatibility
   :widths: 20 20 60
   :header-rows: 1

   * - Python Version
     - Support Status
     - Notes
   * - 3.8
     - ✅ Supported
     - Minimum supported version
   * - 3.9
     - ✅ Supported
     - Recommended for production
   * - 3.10
     - ✅ Supported
     - Latest features available
   * - 3.11
     - ✅ Supported
     - Performance improvements
   * - 3.12
     - 🔄 Testing
     - In testing phase

Installation Methods
====================

1. Install from PyPI (Recommended)
----------------------------------

The simplest way to install:

.. code-block:: bash

   pip install kailash

To upgrade to the latest version:

.. code-block:: bash

   pip install --upgrade kailash

2. Install from Source
----------------------

For development or latest features:

.. code-block:: bash

   # Clone the repository
   git clone https://github.com/terrene-foundation/kailash-py.git
   cd kailash-python-sdk

   # Install in development mode
   pip install -e .

3. Install with Poetry
----------------------

If using Poetry for dependency management:

.. code-block:: bash

   poetry add kailash

4. Install with Conda
---------------------

For Conda environments:

.. code-block:: bash

   conda install -c conda-forge kailash

Optional Dependencies
=====================

The SDK has several optional dependency groups for specific features:

API Testing
-----------

For testing API nodes with mocked responses:

.. code-block:: bash

   pip install kailash[api-testing]

This installs:
- ``responses``: For mocking HTTP responses
- ``requests-mock``: Alternative HTTP mocking

Development Tools
-----------------

For SDK development:

.. code-block:: bash

   pip install kailash[dev]

This installs:
- ``pytest``: Testing framework
- ``pytest-asyncio``: Async test support
- ``pytest-cov``: Coverage reporting
- ``black``: Code formatting
- ``isort``: Import sorting
- ``ruff``: Linting
- ``mypy``: Type checking

Documentation
-------------

For building documentation:

.. code-block:: bash

   pip install kailash[docs]

This installs:
- ``sphinx``: Documentation generator
- ``sphinx-rtd-theme``: Read the Docs theme
- ``sphinx-copybutton``: Copy button for code blocks
- ``sphinxcontrib-mermaid``: Mermaid diagram support

Visualization
-------------

For advanced visualization features:

.. code-block:: bash

   pip install kailash[viz]

This installs:
- ``matplotlib``: Plotting library
- ``seaborn``: Statistical visualization
- ``plotly``: Interactive plots
- ``pygraphviz``: GraphViz integration

All Features
------------

To install all optional dependencies:

.. code-block:: bash

   pip install kailash[all]

Docker Installation
===================

Using Pre-built Image
---------------------

Pull the official Docker image:

.. code-block:: bash

   docker pull terrene-foundation/kailash-py:latest

Run a workflow in Docker:

.. code-block:: bash

   docker run -v $(pwd):/workspace terrene-foundation/kailash-py workflow.py

Building Custom Image
---------------------

Create a Dockerfile for your application:

.. code-block:: dockerfile

   FROM python:3.9-slim

   # Install system dependencies
   RUN apt-get update && apt-get install -y \
       gcc \
       g++ \
       && rm -rf /var/lib/apt/lists/*

   # Install Kailash SDK
   RUN pip install kailash

   # Copy your workflow files
   COPY . /app
   WORKDIR /app

   # Run your workflow
   CMD ["python", "my_workflow.py"]

Build and run:

.. code-block:: bash

   docker build -t my-kailash-app .
   docker run my-kailash-app

Environment Setup
=================

Virtual Environment (Recommended)
---------------------------------

Always use a virtual environment:

.. code-block:: bash

   # Create virtual environment
   python -m venv kailash-env

   # Activate on Linux/macOS
   source kailash-env/bin/activate

   # Activate on Windows
   kailash-env\Scripts\activate

   # Install SDK
   pip install kailash

Using pyenv
-----------

For managing multiple Python versions:

.. code-block:: bash

   # Install Python 3.9
   pyenv install 3.9.15

   # Create virtual environment
   pyenv virtualenv 3.9.15 kailash-env

   # Activate environment
   pyenv activate kailash-env

   # Install SDK
   pip install kailash

Configuration
=============

Environment Variables
---------------------

Configure SDK behavior with environment variables:

.. code-block:: bash

   # Set default runtime
   export KAILASH_RUNTIME=local

   # Configure logging
   export KAILASH_LOG_LEVEL=INFO

   # Set task storage location
   export KAILASH_TASK_STORAGE=/path/to/storage

   # Enable debug mode
   export KAILASH_DEBUG=true

Configuration File
------------------

Create ``~/.kailash/config.yaml``:

.. code-block:: yaml

   # Default runtime configuration
   runtime:
     type: local
     max_workers: 4

   # Logging configuration
   logging:
     level: INFO
     format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

   # Task tracking
   tracking:
     enabled: true
     storage_path: ~/.kailash/tasks

   # Node defaults
   nodes:
     timeout: 300  # seconds
     retry_count: 3

Verification
============

Verify Installation
-------------------

Check the installation:

.. code-block:: python

   import kailash

   # Check version
   print(f"Kailash SDK version: {kailash.__version__}")

   # List available nodes
   from kailash import NodeRegistry

   print("Available nodes:")
   for node_name in NodeRegistry.list_nodes():
       print(f"  - {node_name}")

Run Test Workflow
-----------------

Test with a simple workflow:

.. code-block:: python

   from kailash import Workflow

   # Create test workflow
   workflow = Workflow("test_installation")

   # Add a simple node
   workflow.add_node("PythonCodeNode", "test", config={
       "code": "return {'status': 'Installation successful!'}"
   })

   # Run workflow
   result = workflow.run()
   print(result)

Troubleshooting Installation
============================

Common Issues
-------------

**ImportError: No module named 'kailash'**

- Ensure you've activated your virtual environment
- Verify installation: ``pip list | grep kailash``

**Permission Denied Errors**

- Use ``pip install --user kailash`` for user installation
- Or use a virtual environment (recommended)

**Dependency Conflicts**

- Create a fresh virtual environment
- Use ``pip install --force-reinstall kailash``

**C Extension Build Errors**

- Install build tools:
  - macOS: ``xcode-select --install``
  - Ubuntu: ``sudo apt-get install build-essential``
  - Windows: Install Visual Studio Build Tools

Platform-Specific Issues
------------------------

**macOS**

If using Apple Silicon (M1/M2):

.. code-block:: bash

   # Install Rosetta 2 if needed
   softwareupdate --install-rosetta

   # Use x86_64 Python if compatibility issues
   arch -x86_64 pip install kailash

**Windows**

For long path support:

.. code-block:: powershell

   # Run as Administrator
   New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
     -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force

**Linux**

For system-wide installation:

.. code-block:: bash

   # Install system dependencies
   sudo apt-get update
   sudo apt-get install python3-pip python3-dev

   # Install SDK
   sudo pip3 install kailash

Next Steps
==========

After installation:

1. Read the :doc:`getting_started` guide
2. Explore :doc:`examples/index`
3. Review :doc:`guides/best_practices`
4. Check :doc:`api/index` for detailed reference

For additional help, see :doc:`guides/troubleshooting` or visit our `GitHub Issues <https://github.com/terrene-foundation/kailash-py/issues>`_.
