## Project Structure

The project follows this current structure:

```
kailash_python_sdk/           # Project root directory
├── src/                      # Source directory
│   └── kailash/              # Package directory (what gets imported)
│       ├── __init__.py       # Package initialization
│       ├── manifest.py       # Core manifest and registry
│       ├── sdk_exceptions.py # Custom exceptions
│       ├── nodes/            # Node definitions
│       │   ├── __init__.py
│       │   ├── base.py       # Base node class
│       │   ├── base_async.py # Async base node
│       │   ├── data/         # Data connector nodes
│       │   │   ├── __init__.py
│       │   │   ├── readers.py # Data source nodes
│       │   │   ├── writers.py # Data sink nodes
│       │   │   ├── sql.py     # SQL database nodes
│       │   │   ├── streaming.py # Streaming data nodes
│       │   │   └── vector_db.py # Vector database nodes
│       │   ├── transform/    # Transformation nodes
│       │   │   ├── __init__.py
│       │   │   └── processors.py # Data transformation nodes
│       │   ├── logic/        # Business logic nodes
│       │   │   ├── __init__.py
│       │   │   ├── operations.py # Logical operation nodes
│       │   │   └── async_operations.py # Async operations
│       │   ├── ai/           # AI & ML nodes
│       │   │   ├── __init__.py
│       │   │   ├── models.py  # ML model nodes
│       │   │   └── agents.py  # AI agent nodes
│       │   ├── api/          # API integration nodes
│       │   │   ├── __init__.py
│       │   │   ├── http.py    # HTTP client nodes
│       │   │   ├── rest.py    # REST API nodes
│       │   │   ├── graphql.py # GraphQL nodes
│       │   │   ├── auth.py    # Authentication nodes
│       │   │   └── rate_limiting.py # Rate limiting
│       │   └── code/         # Code execution nodes
│       │       ├── __init__.py
│       │       └── python.py  # Python code execution
│       ├── workflow/         # Workflow management
│       │   ├── __init__.py
│       │   ├── builder.py    # Workflow builder
│       │   ├── graph.py      # Workflow graph definition
│       │   ├── runner.py     # Workflow execution
│       │   ├── state.py      # State management
│       │   ├── visualization.py # Visualization utilities
│       │   ├── visualization_backup.py # Backup visualization
│       │   └── mock_registry.py # Mock registry for testing
│       ├── runtime/          # Execution environment
│       │   ├── __init__.py
│       │   ├── local.py      # Local execution engine
│       │   ├── async_local.py # Async local execution
│       │   ├── parallel.py   # Parallel execution
│       │   ├── docker.py     # Docker runtime
│       │   ├── runner.py     # Runtime runner
│       │   └── testing.py    # Testing utilities
│       ├── tracking/         # Task tracking system
│       │   ├── __init__.py
│       │   ├── models.py     # Task data models
│       │   ├── manager.py    # Task manager
│       │   └── storage/      # Storage backends
│       │       ├── __init__.py
│       │       ├── base.py   # Base storage interface
│       │       ├── filesystem.py # File system storage
│       │       └── database.py # Database storage
│       ├── utils/            # Helper utilities
│       │   ├── __init__.py
│       │   ├── export.py     # Export utilities
│       │   └── templates.py  # Node templates
│       └── cli/              # Command-line interface
│           ├── __init__.py
│           └── commands.py   # CLI commands
├── tests/                    # Test directory (mirrors src structure)
│   ├── __init__.py
│   ├── conftest.py          # PyTest configuration
│   ├── sample_data/         # Test data files
│   ├── test_nodes/          # Node tests
│   │   ├── test_base.py
│   │   ├── test_data.py
│   │   ├── test_api.py
│   │   ├── test_ai.py
│   │   ├── test_code.py
│   │   ├── test_logic.py
│   │   ├── test_transform.py
│   │   └── test_async_operations.py
│   ├── test_workflow/       # Workflow tests
│   │   ├── test_graph.py
│   │   ├── test_state_management.py
│   │   ├── test_visualization.py
│   │   └── test_hmi_state_management.py
│   ├── test_runtime/        # Runtime tests
│   │   ├── test_local.py
│   │   ├── test_docker.py
│   │   ├── test_simple_runtime.py
│   │   └── test_testing.py
│   ├── test_tracking/       # Tracking tests
│   │   ├── test_manager.py
│   │   ├── test_models.py
│   │   └── test_storage.py
│   ├── test_utils/          # Utility tests
│   │   ├── test_export.py
│   │   └── test_templates.py
│   ├── test_cli/            # CLI tests
│   │   └── test_commands.py
│   ├── test_schema/         # Schema validation tests
│   ├── test_validation/     # Type validation tests
│   ├── integration/         # Integration tests
│   │   ├── test_workflow_execution.py
│   │   ├── test_node_communication.py
│   │   ├── test_error_propagation.py
│   │   ├── test_performance.py
│   │   ├── test_storage_integration.py
│   │   ├── test_export_integration.py
│   │   ├── test_visualization_integration.py
│   │   ├── test_task_tracking_integration.py
│   │   ├── test_code_node_integration.py
│   │   ├── test_complex_workflows.py
│   │   └── test_cli_integration.py
│   └── test_ci_setup.py     # CI/CD setup tests
├── docs/                    # Public Documentation
│   ├── api/                 # Sphinx API documentation ✅ COMPLETE
│   │   ├── conf.py          # Sphinx configuration
│   │   ├── index.rst        # Main documentation entry point
│   │   ├── getting_started.rst # Getting started guide
│   │   ├── installation.rst # Installation instructions
│   │   ├── quickstart.rst   # 5-minute quickstart
│   │   ├── best_practices.rst # Best practices guide ✅ NEW
│   │   ├── troubleshooting.rst # Troubleshooting guide ✅ NEW
│   │   ├── performance.rst  # Performance optimization ✅ NEW
│   │   ├── requirements.txt # Documentation dependencies
│   │   ├── Makefile         # Build automation
│   │   ├── _static/         # Custom CSS/JS files
│   │   ├── _templates/      # Custom templates
│   │   └── api/             # API reference files
│   │       ├── nodes.rst    # Node types documentation
│   │       ├── workflow.rst # Workflow management
│   │       ├── runtime.rst  # Runtime engines
│   │       ├── tracking.rst # Task tracking
│   │       ├── utils.rst    # Utilities and helpers
│   │       └── cli.rst      # CLI commands
│   ├── build_docs.py        # Build script for GitHub Pages
│   └── README.md            # Documentation development guide
├── guide/                   # Internal Development Documentation (not in PyPI)
│   ├── README.md            # Guide overview
│   ├── prd/                 # Product Requirements Documents
│   │   ├── 0001-kailash_python_sdk_prd.md
│   │   └── 0000-project_structure.md (this file)
│   ├── adr/                 # Architecture Decision Records
│   │   ├── README.md        # ADR summary
│   │   ├── 0000-template.md # ADR template
│   │   ├── 0003-base-node-interface.md
│   │   ├── 0004-workflow-representation.md
│   │   ├── 0005-local-execution-strategy.md
│   │   ├── 0006-task-tracking-architecture.md
│   │   ├── 0007-export-format.md
│   │   ├── 0008-docker-runtime-architecture.md
│   │   ├── 0009-src-layout-for-package.md
│   │   ├── 0010-python-code-node.md
│   │   ├── 0011-workflow-execution-improvements.md
│   │   ├── 0012-workflow-conditional-routing.md
│   │   ├── 0013-simplify-conditional-logic-nodes.md
│   │   ├── 0014-async-node-execution.md
│   │   ├── 0015-api-integration-architecture.md
│   │   └── 0016-immutable-state-management.md
│   ├── features/            # Feature documentation
│   │   ├── api_integration.md
│   │   ├── python_code_node.md
│   │   └── workflow_pattern.md
│   ├── development/         # Development workflows and processes
│   │   └── pre-commit-hooks.md
│   ├── mistakes/            # Common mistakes and lessons learned
│   │   └── 000-master.md
│   └── todos/               # Development task tracking
│       ├── 000-master.md    # Master todo list
│       └── [session-specific todos]
├── examples/                # Example usage and demonstrations
│   ├── node_examples/       # Individual node usage examples
│   │   ├── node_basic_connection.py
│   │   ├── node_custom_creation.py
│   │   ├── node_docker_test.py
│   │   ├── node_python_code.py
│   │   └── node_output_schema.py
│   ├── workflow_examples/   # Workflow patterns and use cases
│   │   ├── workflow_basic.py
│   │   ├── workflow_complex.py
│   │   ├── workflow_comprehensive.py
│   │   ├── workflow_conditional.py
│   │   ├── workflow_parallel.py
│   │   ├── workflow_error_handling.py
│   │   └── workflow_task_tracking.py
│   ├── integration_examples/ # API and system integrations
│   │   ├── integration_api_comprehensive.py
│   │   ├── integration_api_simple.py
│   │   └── integration_sharepoint_graph.py
│   ├── visualization_examples/ # Visualization and reporting
│   │   ├── viz_workflow_graphs.py
│   │   ├── viz_mermaid.py
│   │   └── viz_examples_overview.py
│   ├── data/                # Sample data files
│   │   ├── customers.csv
│   │   ├── transactions.json
│   │   └── input.csv
│   ├── outputs/             # Generated output files
│   │   └── visualizations/  # Mermaid markdown files
│   ├── migrations/          # Migration experiments
│   ├── _utils/              # Testing utilities
│   │   └── test_all_examples.py # Example validation entrypoint
│   └── README.md            # Examples documentation
├── data/                    # Root-level data for testing
│   ├── customers.csv        # Sample datasets
│   ├── transactions.json
│   ├── outputs/             # Processing outputs
│   └── task_storage/        # Task tracking storage
├── output/                  # Generated output files
├── pyproject.toml           # Package build configuration
├── setup.py                 # Package setup script
├── setup.cfg                # Setup configuration
├── pytest.ini              # PyTest configuration
├── uv.lock                  # UV lockfile
├── README.md                # Project README
├── CONTRIBUTING.md          # Contribution guidelines
├── LICENSE                  # License file
└── Claude.md                # Development guidelines (this file)
```
