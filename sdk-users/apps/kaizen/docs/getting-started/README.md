# Getting Started with Kaizen

**Your journey to signature-based AI programming and enterprise agents**

Welcome to Kaizen! This section will guide you from installation to your first working AI agent using Kaizen's powerful signature-based programming approach.

## 🎯 What You'll Learn

By the end of this getting started section, you'll be able to:

- Install and configure Kaizen for your development environment
- Create your first signature-based AI agent in under 5 minutes
- Understand the core concepts of declarative AI programming
- Execute agents using the Kailash Core SDK runtime
- Configure enterprise features for production usage

## 📖 Learning Path

### 1. [Installation Guide](installation.md)
**Time: 2-3 minutes**

Set up your development environment with Kaizen and all required dependencies. Covers:
- Python environment setup
- Kaizen installation options
- Required dependencies and optional features
- Verification that everything works

### 2. [Quickstart Tutorial](quickstart.md)
**Time: 5-10 minutes**

Create and execute your first Kaizen agent with minimal setup. You'll learn:
- Basic framework initialization
- Creating a simple signature-based agent
- Executing agents with Core SDK runtime
- Understanding the results

### 3. [First Agent Deep Dive](first-agent.md)
**Time: 15-20 minutes**

Detailed walkthrough of agent creation, configuration, and execution. Covers:
- Agent configuration options
- Signature syntax and patterns
- Integration with Core SDK workflows
- Error handling and debugging
- Enterprise configuration basics

## 🚀 Quick Preview

Here's what you'll be able to do after completing this section:

```python
import kaizen

# Initialize Kaizen framework
framework = kaizen.Kaizen(signature_programming_enabled=True)

# Create a signature-based agent
agent = framework.create_agent(
    "text_analyzer",
    signature="text -> summary, sentiment, key_topics"
)

# Execute with Core SDK runtime
from kailash.runtime.local import LocalRuntime
runtime = LocalRuntime()

# Convert to workflow and execute
workflow = agent.to_workflow()
results, run_id = runtime.execute(workflow.build())

# Access structured results
print(f"Summary: {results['summary']}")
print(f"Sentiment: {results['sentiment']}")
print(f"Key Topics: {results['key_topics']}")
```

## 🎯 Prerequisites

### Required Knowledge
- **Python programming**: Basic familiarity with Python (variables, functions, imports)
- **Command line**: Comfort with terminal/command prompt for installation
- **Optional**: Basic understanding of AI/LLM concepts (helpful but not required)

### System Requirements
- **Python**: 3.8 or higher
- **Operating System**: Windows, macOS, or Linux
- **Memory**: 4GB RAM minimum (8GB recommended for enterprise features)
- **Disk Space**: 2GB for full installation with dependencies

### Development Environment
- **Text Editor/IDE**: VS Code, PyCharm, or your preferred Python editor
- **Terminal Access**: Command prompt, PowerShell, Terminal, or IDE terminal
- **Internet Connection**: Required for model access and package installation

## 🏗️ Framework Architecture Preview

Understanding how Kaizen fits into the larger ecosystem:

```
Your Application
       ↓
   Kaizen Framework (Signature-based AI)
       ↓
   Kailash Core SDK (WorkflowBuilder + LocalRuntime)
       ↓
   AI Models & Infrastructure
```

**Key Concepts You'll Learn:**
- **Signatures**: Declarative input/output definitions (`"text -> summary"`)
- **Agents**: AI components that implement signatures
- **Workflows**: Core SDK execution patterns
- **Runtime**: Execution engine that runs your workflows

## 🎯 Learning Objectives

### After Installation
- [ ] Kaizen installed and verified working
- [ ] Development environment configured
- [ ] Core dependencies available

### After Quickstart
- [ ] Created first signature-based agent
- [ ] Executed agent using Core SDK runtime
- [ ] Understand basic signature syntax
- [ ] Know how to access results

### After First Agent Deep Dive
- [ ] Understand agent configuration options
- [ ] Know signature patterns and syntax
- [ ] Can debug common issues
- [ ] Ready for enterprise features

## 🚨 Common Gotchas

**Before you start, be aware of these common issues:**

1. **Python Version**: Kaizen requires Python 3.8+. Check with `python --version`
2. **Virtual Environments**: Recommended to avoid dependency conflicts
3. **API Keys**: Some models require API keys (covered in installation)
4. **Core SDK Pattern**: Always use `runtime.execute(workflow.build())`, never `workflow.execute(runtime)`

## 🔗 What's Next?

After completing the getting started section:

1. **[Core Guides](../guides/)** - Deep dive into signature programming and enterprise features
2. **[Examples](../examples/)** - Working code examples for real-world use cases
3. **[Advanced Usage](../advanced/)** - Custom nodes, performance tuning, enterprise deployment

## 🛠️ Support

If you encounter issues during setup:
- Check the [Troubleshooting Guide](../reference/troubleshooting.md)
- Review [Common Issues](installation.md#troubleshooting) in the installation guide
- Visit the [GitHub repository](https://github.com/terrene-foundation/kailash-py) for latest updates

---

**Ready to begin?** Start with the **[Installation Guide](installation.md)** to set up your development environment.
