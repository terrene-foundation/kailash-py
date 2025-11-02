# Kaizen Examples

**Working code examples for real-world Kaizen usage**

This section provides practical, tested examples demonstrating Kaizen's signature-based AI programming in real-world scenarios. All examples include complete working code and step-by-step explanations.

## 📁 Example Categories

### [Basic Agent Examples](basic-agent/)
**Simple, foundational patterns** - Perfect for learning core concepts

- **Text Analysis Agent** - Summary, sentiment, and topic extraction
- **Q&A Agent** - Question answering with context
- **Content Generator** - Creative writing and content creation
- **Data Processor** - Structured data analysis
- **Translation Agent** - Multi-language translation with confidence

**Complexity:** ⭐⭐ Beginner
**Time:** 10-15 minutes per example

### [Signature Workflows](signature-workflows/)
**Advanced declarative patterns** - Complex signature-based workflows

- **Multi-Stage Document Processing** - Extract, analyze, classify, audit
- **Research Pipeline** - Research, analyze, synthesize, report
- **Content Workflow** - Plan, create, review, optimize
- **Decision Support** - Gather, analyze, recommend, validate
- **Quality Assurance** - Check, validate, score, improve

**Complexity:** ⭐⭐⭐ Intermediate
**Time:** 20-30 minutes per example

### [Enterprise Setup](enterprise-setup/)
**Production-ready configurations** - Enterprise features and deployment

- **Enterprise Configuration** - Memory, audit, compliance, security
- **Multi-Tenant Deployment** - Isolated environments and resource management
- **Audit Trail Implementation** - Comprehensive logging and compliance
- **Performance Monitoring** - Metrics, alerting, and optimization
- **High Availability Setup** - Redundancy and failover patterns

**Complexity:** ⭐⭐⭐⭐ Advanced
**Time:** 30-45 minutes per example

### [MCP Tools Integration](mcp-tools/)
**External tool connections** - Model Context Protocol integration

- **Tool Exposure** - Convert agents to external MCP tools
- **Tool Discovery** - Find and integrate external tools
- **Server Deployment** - Deploy MCP servers for agents
- **Client Integration** - Use external MCP tools in workflows
- **Registry Management** - Tool catalog and lifecycle management

**Complexity:** ⭐⭐⭐ Intermediate to Advanced
**Time:** 25-35 minutes per example

## 🚀 Quick Start Examples

### 5-Minute Example: Text Analyzer

```python
import kaizen
from kailash.runtime.local import LocalRuntime

# Initialize framework
framework = kaizen.Kaizen(signature_programming_enabled=True)

# Create signature-based agent
analyzer = framework.create_agent(
    "text_analyzer",
    signature="text -> summary, sentiment, key_topics"
)

# Execute with sample text
runtime = LocalRuntime()
workflow = analyzer.to_workflow()

results, run_id = runtime.execute(
    workflow.build(),
    parameters={
        "text": "Your text to analyze here..."
    }
)

print(f"Summary: {results['summary']}")
print(f"Sentiment: {results['sentiment']}")
print(f"Topics: {results['key_topics']}")
```

### 10-Minute Example: Enterprise Agent

```python
# Enterprise configuration
enterprise_config = kaizen.KaizenConfig(
    memory_enabled=True,
    audit_trail_enabled=True,
    security_level="high"
)

framework = kaizen.Kaizen(config=enterprise_config)

# Create memory system
memory = framework.create_memory_system(tier="enterprise")

# Enterprise agent with audit trails
agent = framework.create_agent(
    "enterprise_processor",
    config={
        "model": "gpt-4",
        "memory_system": memory,
        "audit_enabled": True
    },
    signature="document -> analysis, compliance_status, audit_trail"
)
```

### 15-Minute Example: Multi-Agent Team

```python
# Create coordinated agent team
research_team = framework.create_agent_team(
    "research_team",
    pattern="collaborative",
    roles=["researcher", "analyst", "reviewer"],
    coordination="consensus"
)

# Execute team coordination
workflow = research_team.create_coordination_workflow()
results = framework.execute_coordination_workflow(
    "collaborative",
    workflow,
    {"topic": "AI market analysis"}
)
```

---

**Ready to explore examples?** Start with **[Basic Agent Examples](basic-agent/)** to learn foundational patterns, or jump to **[Enterprise Setup](enterprise-setup/)** for production-ready configurations.
