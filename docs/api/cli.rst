===
CLI
===

This section covers the Kailash SDK command-line interface.

.. contents:: Table of Contents
   :local:
   :depth: 2

Overview
========

The Kailash CLI provides command-line tools for:

- Running workflows
- Managing nodes
- Debugging and testing
- Performance analysis
- Workflow visualization

Installation
============

The CLI is automatically installed with the SDK:

.. code-block:: bash

   pip install kailash

Verify installation:

.. code-block:: bash

   kailash --version
   kailash --help

Basic Usage
===========

Run a Workflow
--------------

.. code-block:: bash

   # Run a workflow file
   kailash run workflow.py

   # Run with arguments
   kailash run workflow.py --input data.csv --output results.csv

   # Run with environment file
   kailash run workflow.py --env-file .env

   # Run with specific runtime
   kailash run workflow.py --runtime docker

Workflow File Format
--------------------

Workflows can be defined in Python files:

.. code-block:: python

   # workflow.py
   from kailash import Workflow

   def create_workflow():
       workflow = Workflow("my_workflow")

       workflow.add_node("CSVReaderNode", "input", config={
           "file_path": "${INPUT_FILE:-data.csv}"
       })

       workflow.add_node("DataFilter", "filter", config={
           "column": "status",
           "value": "active"
       })

       workflow.add_node("CSVWriterNode", "output", config={
           "file_path": "${OUTPUT_FILE:-output.csv}"
       })

       workflow.connect_sequential(["input", "filter", "output"])

       return workflow

   # Required for CLI
   if __name__ == "__main__":
       workflow = create_workflow()
       workflow.run()

CLI Commands
============

kailash run
-----------

Execute workflows from the command line.

**Synopsis:**

.. code-block:: bash

   kailash run [OPTIONS] WORKFLOW_FILE

**Options:**

.. code-block:: text

   --runtime TEXT          Runtime to use (local, async, parallel, docker)
   --config FILE          Configuration file (YAML/JSON)
   --env-file FILE        Environment variables file
   --param KEY=VALUE      Set workflow parameters
   --input FILE           Input data file
   --output FILE          Output data file
   --tracking/--no-tracking  Enable/disable tracking (default: enabled)
   --profile              Enable profiling
   --debug                Debug mode with verbose output
   --dry-run              Validate without executing
   --timeout INTEGER      Execution timeout in seconds
   --workers INTEGER      Number of parallel workers
   --help                 Show help message

**Examples:**

.. code-block:: bash

   # Basic execution
   kailash run my_workflow.py

   # With parameters
   kailash run etl_pipeline.py \
     --param source=customers.csv \
     --param target=processed.csv \
     --runtime parallel \
     --workers 4

   # Docker execution
   kailash run secure_workflow.py \
     --runtime docker \
     --config docker-config.yaml

   # Profiling
   kailash run complex_workflow.py \
     --profile \
     --output profile_report.html

kailash list
------------

List available nodes and workflows.

**Synopsis:**

.. code-block:: bash

   kailash list [OPTIONS] [nodes|workflows|runs]

**Options:**

.. code-block:: text

   --category TEXT     Filter by category
   --search TEXT       Search term
   --format TEXT       Output format (table, json, yaml)
   --verbose          Show detailed information

**Examples:**

.. code-block:: bash

   # List all nodes
   kailash list nodes

   # List data nodes
   kailash list nodes --category data

   # Search for CSV nodes
   kailash list nodes --search csv

   # List workflow runs
   kailash list runs --limit 10

kailash info
------------

Get detailed information about nodes or workflows.

**Synopsis:**

.. code-block:: bash

   kailash info [OPTIONS] [node|workflow|run] NAME_OR_ID

**Examples:**

.. code-block:: bash

   # Node information
   kailash info node CSVReaderNode

   # Workflow information
   kailash info workflow my_workflow.py

   # Run information
   kailash info run 123e4567-e89b-12d3-a456-426614174000

kailash validate
----------------

Validate workflow definitions.

**Synopsis:**

.. code-block:: bash

   kailash validate [OPTIONS] WORKFLOW_FILE

**Options:**

.. code-block:: text

   --strict            Strict validation mode
   --schema FILE       Custom schema file
   --format            Check export format compatibility

**Examples:**

.. code-block:: bash

   # Basic validation
   kailash validate workflow.py

   # Strict validation
   kailash validate workflow.py --strict

   # Validate export format
   kailash validate workflow.yaml --format

kailash export
--------------

Export workflows to different formats.

**Synopsis:**

.. code-block:: bash

   kailash export [OPTIONS] WORKFLOW_FILE OUTPUT_FILE

**Options:**

.. code-block:: text

   --format TEXT       Output format (yaml, json)
   --pretty            Pretty print output
   --validate          Validate before export
   --include-metadata  Include workflow metadata

**Examples:**

.. code-block:: bash

   # Export to YAML
   kailash export workflow.py workflow.yaml

   # Export to JSON with metadata
   kailash export workflow.py workflow.json \
     --format json \
     --include-metadata

kailash visualize
-----------------

Generate workflow visualizations.

**Synopsis:**

.. code-block:: bash

   kailash visualize [OPTIONS] WORKFLOW_FILE OUTPUT_FILE

**Options:**

.. code-block:: text

   --format TEXT       Output format (mermaid, dot, png, html)
   --layout TEXT       Graph layout (TB, LR, BT, RL)
   --theme TEXT        Visual theme
   --include-config    Show node configurations

**Examples:**

.. code-block:: bash

   # Generate Mermaid diagram
   kailash visualize workflow.py diagram.md --format mermaid

   # Generate PNG image
   kailash visualize workflow.py workflow.png --format png

   # Interactive HTML
   kailash visualize workflow.py workflow.html \
     --format html \
     --theme dark

kailash test
------------

Run workflow tests.

**Synopsis:**

.. code-block:: bash

   kailash test [OPTIONS] TEST_FILE_OR_DIR

**Options:**

.. code-block:: text

   --pattern TEXT      Test file pattern
   --coverage          Generate coverage report
   --parallel          Run tests in parallel
   --verbose           Verbose output
   --failfast          Stop on first failure

**Examples:**

.. code-block:: bash

   # Run all tests
   kailash test tests/

   # Run specific test file
   kailash test test_workflow.py

   # With coverage
   kailash test tests/ --coverage

kailash profile
---------------

Profile workflow performance.

**Synopsis:**

.. code-block:: bash

   kailash profile [OPTIONS] WORKFLOW_FILE

**Options:**

.. code-block:: text

   --iterations INT    Number of iterations
   --warmup INT        Warmup iterations
   --output FILE       Output report file
   --format TEXT       Report format (html, json, csv)

**Examples:**

.. code-block:: bash

   # Basic profiling
   kailash profile workflow.py

   # Multiple iterations
   kailash profile workflow.py \
     --iterations 10 \
     --warmup 2 \
     --output profile.html

kailash debug
-------------

Debug workflow execution.

**Synopsis:**

.. code-block:: bash

   kailash debug [OPTIONS] WORKFLOW_FILE

**Options:**

.. code-block:: text

   --breakpoint NODE   Set breakpoint at node
   --step              Step through execution
   --watch EXPR        Watch expression
   --trace             Show execution trace

**Examples:**

.. code-block:: bash

   # Debug with breakpoint
   kailash debug workflow.py --breakpoint process_data

   # Step through execution
   kailash debug workflow.py --step

   # Watch variables
   kailash debug workflow.py --watch "data.shape"

kailash server
--------------

Start the Kailash API server.

**Synopsis:**

.. code-block:: bash

   kailash server [OPTIONS]

**Options:**

.. code-block:: text

   --host TEXT         Host to bind (default: 0.0.0.0)
   --port INT          Port to bind (default: 8000)
   --workers INT       Number of workers
   --reload            Auto-reload on changes

**Examples:**

.. code-block:: bash

   # Start server
   kailash server

   # Development mode
   kailash server --reload --host localhost

   # Production mode
   kailash server --workers 4 --port 80

Configuration
=============

CLI Configuration File
----------------------

Create ``~/.kailash/cli.yaml``:

.. code-block:: yaml

   # Default runtime settings
   runtime:
     type: local
     workers: 4

   # Tracking settings
   tracking:
     enabled: true
     storage: ~/.kailash/tracking

   # Output preferences
   output:
     format: table
     color: auto

   # Aliases
   aliases:
     etl: run --runtime parallel --workers 8
     test-all: test tests/ --coverage --parallel

Environment Variables
---------------------

Configure CLI behavior:

.. code-block:: bash

   # Set default runtime
   export KAILASH_RUNTIME=docker

   # Set tracking directory
   export KAILASH_TRACKING_DIR=/var/kailash/tracking

   # Enable debug mode
   export KAILASH_DEBUG=1

   # Disable color output
   export KAILASH_COLOR=0

Extending the CLI
=================

Custom Commands
---------------

Add custom commands using plugins:

.. code-block:: python

   # my_plugin.py
   import click
   from kailash.cli import cli

   @cli.command()
   @click.argument('workflow_file')
   @click.option('--output', '-o', help='Output file')
   def analyze(workflow_file, output):
       """Analyze workflow complexity."""
       from kailash import Workflow

       workflow = Workflow.from_file(workflow_file)

       # Analysis logic
       node_count = len(workflow.nodes)
       edge_count = len(workflow.edges)
       complexity = edge_count / node_count

       result = {
           'nodes': node_count,
           'edges': edge_count,
           'complexity': complexity
       }

       if output:
           with open(output, 'w') as f:
               json.dump(result, f, indent=2)
       else:
           click.echo(json.dumps(result, indent=2))

Register the plugin:

.. code-block:: bash

   # Install plugin
   pip install -e ./my_plugin

   # Use custom command
   kailash analyze workflow.py -o analysis.json

CLI Scripting
-------------

Use the CLI in scripts:

.. code-block:: bash

   #!/bin/bash
   # batch_process.sh

   # Process multiple workflows
   for workflow in workflows/*.py; do
       echo "Processing $workflow..."

       # Run workflow
       kailash run "$workflow" \
         --runtime parallel \
         --workers 4 \
         --output "results/$(basename $workflow .py).csv"

       # Generate report
       kailash visualize "$workflow" \
         "reports/$(basename $workflow .py).html" \
         --format html
   done

   # Aggregate results
   kailash analyze results/ --output summary.json

Python API Integration
----------------------

Use CLI functionality from Python:

.. code-block:: python

   from kailash.cli import runner

   # Run workflow programmatically
   result = runner.run_workflow(
       'workflow.py',
       runtime='parallel',
       params={'input': 'data.csv'},
       tracking=True
   )

   # Validate workflow
   from kailash.cli import validator

   is_valid = validator.validate_workflow('workflow.py', strict=True)

   # Export workflow
   from kailash.cli import exporter

   exporter.export_workflow(
       'workflow.py',
       'workflow.yaml',
       format='yaml',
       include_metadata=True
   )

Best Practices
==============

1. **Use Environment Files**

.. code-block:: bash

   # .env file
   INPUT_FILE=data/customers.csv
   OUTPUT_FILE=output/processed.csv
   API_KEY=secret_key

   # Run with env file
   kailash run workflow.py --env-file .env

2. **Create Shell Aliases**

.. code-block:: bash

   # ~/.bashrc or ~/.zshrc
   alias kr='kailash run'
   alias kv='kailash validate'
   alias kp='kailash profile'

   # Quick workflow run
   kr my_workflow.py

3. **Use Configuration Files**

.. code-block:: yaml

   # workflow.yaml
   runtime:
     type: docker
     image: custom-kailash:latest

   parameters:
     batch_size: 1000
     timeout: 300

   tracking:
     enabled: true
     metrics: all

.. code-block:: bash

   kailash run workflow.py --config workflow.yaml

4. **Implement Workflow Testing**

.. code-block:: python

   # test_workflow.py
   import pytest
   from kailash.cli import tester

   def test_etl_workflow():
       result = tester.test_workflow(
           'etl_workflow.py',
           test_data='test_data.csv',
           expected_output='expected_output.csv'
       )
       assert result.success
       assert result.output_matches_expected

5. **Monitor Long-Running Workflows**

.. code-block:: bash

   # Start workflow in background
   kailash run long_workflow.py --tracking &

   # Monitor progress
   watch kailash info run latest

   # View logs
   kailash logs -f

See Also
========

- :doc:`../getting_started` - Getting started guide
- :doc:`../guides/workflows` - Workflow development
- Debugging workflows
- CLI usage examples
