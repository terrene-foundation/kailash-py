---
name: kailash-installation
description: "Install and setup Kailash SDK with pip, poetry, or virtual environments. Use when asking 'install kailash', 'setup SDK', 'pip install', 'poetry add kailash', 'requirements.txt', 'installation guide', 'setup environment', 'verify installation', 'docker setup', or 'getting started'."
---

# Kailash SDK Installation & Setup

Complete guide for installing the Kailash SDK using pip, poetry, virtual environments, or Docker.

> **Skill Metadata**
> Category: `core-sdk`
> Priority: `HIGH`
> SDK Version: `0.9.25+`

## Quick Reference

- **Basic Install**: `pip install kailash`
- **Poetry**: `poetry add kailash`
- **With All Dependencies**: `pip install kailash[all]`
- **Python Requirement**: 3.8+
- **Verify**: Import `WorkflowBuilder` and `LocalRuntime`

## Core Pattern

```bash
# Install Kailash SDK
pip install kailash

# Verify installation
python -c "from kailash.workflow.builder import WorkflowBuilder; print('✅ Kailash installed successfully!')"
```

## Common Use Cases

- **Quick Start**: Install SDK for new project
- **Development Setup**: Create isolated development environment
- **Docker Deployment**: Setup infrastructure services
- **Team Collaboration**: Add SDK to existing project
- **Dependency Management**: Manage SDK version in requirements

## Step-by-Step Guide

### Option 1: Pip Installation (Simplest)

```bash
# Install latest version
pip install kailash

# Install specific version
pip install kailash==0.9.25

# Install with all optional dependencies
pip install kailash[all]
```

### Option 2: Poetry Installation (Recommended)

```bash
# Add to existing project
poetry add kailash

# Or create new project
poetry new my-kailash-project
cd my-kailash-project
poetry add kailash
poetry shell
```

### Option 3: Virtual Environment

```bash
# Create virtual environment
python -m venv kailash-env
source kailash-env/bin/activate  # Linux/Mac
# kailash-env\Scripts\activate  # Windows

# Install in virtual environment
pip install kailash
```

### Option 4: Requirements.txt

```bash
# Add to requirements.txt
echo "kailash>=0.9.25" >> requirements.txt

# Install from requirements
pip install -r requirements.txt
```

## Key Parameters / Options

| Installation Method | Use Case                             | Command                                     |
| ------------------- | ------------------------------------ | ------------------------------------------- |
| **Basic pip**       | Quick start, simple projects         | `pip install kailash`                       |
| **Poetry**          | Team projects, dependency management | `poetry add kailash`                        |
| **Virtual env**     | Isolated development                 | `python -m venv env && pip install kailash` |
| **Docker**          | Production, infrastructure           | `docker-compose up -d`                      |
| **With extras**     | Full feature set                     | `pip install kailash[all]`                  |

## Common Mistakes

### ❌ Mistake 1: Missing Python Version

```bash
# Wrong - Python 3.7 or earlier
python --version  # Python 3.7.x (unsupported)
pip install kailash  # May fail
```

### ✅ Fix: Use Python 3.8+

```bash
# Correct - Python 3.8 or later
python3.8 --version  # Python 3.8.x or higher
python3.8 -m pip install kailash
```

### ❌ Mistake 2: ImportError After Installation

```bash
# Wrong - Installing in one environment, running in another
pip install kailash  # System Python
python my_script.py  # Different Python interpreter
```

### ✅ Fix: Verify Correct Environment

```bash
# Correct - Same environment for install and run
which python  # Check current Python
pip list | grep kailash  # Verify installation
python my_script.py  # Now works
```

### ❌ Mistake 3: Missing Dependencies

```python
# Wrong - kailash.nodes.ai does not exist
# For LLM integration, use Kaizen agents (pip install kailash-kaizen)
# or PythonCodeNode with direct API calls
```

### ✅ Fix: Install With Dependencies

```bash
# Correct - Install all optional dependencies
pip install kailash[all]
```

## Verification Test

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Test basic functionality
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "test", {
    "code": "result = {'status': 'installed', 'version': '0.9.25'}"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

print("✅ Kailash SDK installed successfully!")
print(f"Test result: {results['test']['result']}")
print(f"Run ID: {run_id}")
```

## Related Patterns

- **For basic imports**: See [`kailash-imports`](#)
- **For first workflow**: See [`workflow-quickstart`](#)
- **For Docker setup**: See [`deploy-docker-quick`](#)
- **For troubleshooting**: See [`error-handling-patterns`](#)

## When to Escalate to Subagent

Use `sdk-navigator` subagent when:

- Installation fails with complex errors
- Need custom installation for enterprise environments
- Integrating with existing infrastructure
- Setting up CI/CD pipelines
- Configuring advanced deployment scenarios

Use `deployment-specialist` subagent when:

- Deploying to production environments
- Setting up Docker/Kubernetes infrastructure
- Configuring multi-environment deployments

## Documentation References

### Primary Sources

### Related Documentation

## Troubleshooting

| Issue                                    | Cause                           | Solution                                                |
| ---------------------------------------- | ------------------------------- | ------------------------------------------------------- |
| `ImportError: No module named 'kailash'` | Wrong Python environment        | Verify: `pip list \| grep kailash`, reinstall if needed |
| `ModuleNotFoundError: pydantic`          | Missing dependencies            | Install with extras: `pip install kailash[all]`         |
| `Python version incompatible`            | Python < 3.8                    | Upgrade to Python 3.8+                                  |
| Docker services not starting             | Port conflicts or Docker issues | Run: `docker-compose down -v && docker-compose up -d`   |

## Quick Tips

- 💡 **Use virtual environments**: Isolate project dependencies to avoid conflicts
- 💡 **Check Python version first**: Ensure Python 3.8+ before installation
- 💡 **Install with [all] for development**: Get all optional dependencies upfront
- 💡 **Verify installation immediately**: Run test workflow to confirm setup
- 💡 **Use poetry for teams**: Better dependency management and reproducibility

## Version Notes

- **v0.9.25+**: AsyncLocalRuntime now default for Docker/async
- **v0.9.20+**: String-based nodes became recommended pattern
- **v0.8.0+**: Python 3.8+ required

## Keywords for Auto-Trigger

<!-- Trigger Keywords: install kailash, setup SDK, pip install, poetry add kailash, requirements.txt, installation guide, setup environment, verify installation, docker setup, getting started, kailash setup, how to install, SDK installation -->
