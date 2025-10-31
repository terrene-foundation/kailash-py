# Your First Agent - Deep Dive

**Master agent creation, configuration, and execution patterns**

Building on the quickstart, this guide provides a comprehensive walkthrough of creating, configuring, and executing Kaizen agents with signature-based programming.

## 🎯 What You'll Master

By the end of this guide, you'll understand:

- Complete agent configuration options
- Advanced signature patterns and syntax
- Error handling and debugging techniques
- Integration with Core SDK workflows
- Enterprise configuration basics
- Performance optimization tips

## 🏗️ Agent Architecture Overview

Understanding how Kaizen agents work:

```
┌─────────────────────────────────────────────────────────┐
│                    Your Agent                           │
│                                                         │
│  ┌─────────────────┐  ┌─────────────────────────────┐    │
│  │    Signature    │  │      Configuration         │    │
│  │ "text -> result"│  │ model, temperature, etc.   │    │
│  └─────────────────┘  └─────────────────────────────┘    │
│                              │                         │
│  ┌───────────────────────────┼─────────────────────────┐ │
│  │           Kaizen Framework                          │ │
│  │  Signature Parser │ Optimizer │ Error Handler      │ │
│  └───────────────────────────┼─────────────────────────┘ │
│                              │                         │
│  ┌───────────────────────────┼─────────────────────────┐ │
│  │         Kailash Core SDK                            │ │
│  │    WorkflowBuilder │ LocalRuntime │ Nodes          │ │
│  └───────────────────────────┼─────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## 🧠 Understanding Signatures

### Signature Syntax

Signatures define the interface between inputs and outputs:

```python
# Basic patterns
"input -> output"                    # Single input, single output
"input1, input2 -> output"          # Multiple inputs
"input -> output1, output2"         # Multiple outputs
"input1, input2 -> output1, output2"  # Complex mapping

# Real examples
"text -> summary"                    # Text summarization
"question, context -> answer"        # Question answering
"data -> insights, confidence"       # Analysis with confidence
"document -> extract, classify, audit"  # Multi-stage processing
```

### Advanced Signature Patterns

**Typed Signatures:**
```python
# With type hints
"text: str -> summary: str, sentiment: str"
"data: dict -> analysis: dict, score: float"
"image: bytes -> description: str, objects: list"
```

**Optional Outputs:**
```python
# Some outputs may be empty
"text -> summary, sentiment, warnings?"
"data -> result, error_message?, metadata?"
```

**Nested Structures:**
```python
# Complex data structures
"document -> {title, summary, metadata: {author, date, tags}}"
"analysis -> {insights: [str], confidence: float, sources: [str]}"
```

## 🤖 Agent Creation Patterns

### Basic Agent Creation

```python
import kaizen

# Initialize framework
framework = kaizen.Kaizen(signature_programming_enabled=True)

# Create basic agent
agent = framework.create_agent(
    agent_id="text_processor",
    signature="text -> summary"
)
```

### Configured Agent Creation

```python
# Agent with specific configuration
agent = framework.create_agent(
    agent_id="advanced_processor",
    config={
        "model": "gpt-4",
        "temperature": 0.7,
        "max_tokens": 1000,
        "timeout": 30
    },
    signature="text -> summary, sentiment, key_topics"
)
```

### Specialized Agent Creation

```python
# Create specialized agent with role-based behavior
specialist = framework.create_specialized_agent(
    name="research_specialist",
    role="Analyze research papers and extract key insights",
    config={
        "model": "gpt-4",
        "expertise": "academic_research",
        "capabilities": ["analysis", "summarization", "citation"]
    }
)
```

## ⚙️ Configuration Options

### Model Configuration

```python
# OpenAI models
config = {
    "model": "gpt-4",           # or "gpt-3.5-turbo"
    "temperature": 0.7,         # 0.0 = deterministic, 1.0 = creative
    "max_tokens": 1000,         # Maximum response length
    "top_p": 0.9,              # Nucleus sampling
    "frequency_penalty": 0.0,   # Avoid repetition
    "presence_penalty": 0.0     # Encourage new topics
}

# Anthropic Claude
config = {
    "model": "claude-3-sonnet-20240229",
    "temperature": 0.7,
    "max_tokens": 1000
}

# Azure OpenAI
config = {
    "model": "gpt-4",
    "azure_endpoint": "https://your-resource.openai.azure.com/",
    "api_version": "2023-05-15"
}
```

### Agent Behavior Configuration

```python
config = {
    # Core model settings
    "model": "gpt-4",
    "temperature": 0.3,

    # Behavioral settings
    "role": "expert_analyst",
    "expertise": "financial_analysis",
    "behavior_traits": ["thorough", "analytical", "conservative"],

    # Performance settings
    "timeout": 45,
    "retry_count": 3,
    "cache_enabled": True,

    # Output formatting
    "output_format": "structured",
    "include_confidence": True,
    "include_reasoning": False
}

agent = framework.create_agent(
    "financial_analyst",
    config=config,
    signature="financial_data -> analysis, risk_assessment, recommendations"
)
```

### Enterprise Configuration

```python
# Enterprise agent with audit trails
enterprise_config = {
    "model": "gpt-4",
    "audit_enabled": True,
    "compliance_level": "enterprise",
    "security_level": "high",
    "tenant_id": "dept_finance",
    "user_context": {
        "user_id": "analyst_001",
        "permissions": ["read", "analyze"],
        "clearance_level": "confidential"
    }
}

enterprise_agent = framework.create_agent(
    "secure_analyst",
    config=enterprise_config,
    signature="sensitive_data -> analysis, compliance_status, audit_trail"
)
```

## 🏃‍♂️ Execution Patterns

### Basic Execution

```python
from kailash.runtime.local import LocalRuntime

# Initialize runtime
runtime = LocalRuntime()

# Convert agent to workflow
workflow = agent.to_workflow()

# Execute
results, run_id = runtime.execute(
    workflow.build(),
    parameters={"text": "Your input text here"}
)

print(f"Results: {results}")
print(f"Execution ID: {run_id}")
```

### Batch Execution

```python
# Process multiple inputs
inputs = [
    {"text": "First document to analyze"},
    {"text": "Second document to analyze"},
    {"text": "Third document to analyze"}
]

results_list = []
for input_data in inputs:
    results, run_id = runtime.execute(
        workflow.build(),
        parameters=input_data
    )
    results_list.append({
        "input": input_data,
        "output": results,
        "run_id": run_id
    })

print(f"Processed {len(results_list)} documents")
```

### Parameterized Execution

```python
# Execute with runtime parameters
results, run_id = runtime.execute(
    workflow.build(),
    parameters={
        "text": "Document to analyze",
        "analysis_depth": "detailed",
        "include_citations": True,
        "output_format": "json"
    }
)
```

### Streaming Execution (Enterprise)

```python
# For long-running processes
def process_callback(partial_results):
    print(f"Partial results: {partial_results}")

results, run_id = runtime.execute(
    workflow.build(),
    parameters={"text": "Long document..."},
    streaming=True,
    callback=process_callback
)
```

## 🔧 Error Handling

### Basic Error Handling

```python
try:
    results, run_id = runtime.execute(
        workflow.build(),
        parameters={"text": "Input text"}
    )
    print("✅ Execution successful")

except kaizen.SignatureError as e:
    print(f"❌ Signature error: {e}")
    print("Check your signature syntax")

except kaizen.ConfigurationError as e:
    print(f"❌ Configuration error: {e}")
    print("Check your agent configuration")

except kaizen.ExecutionError as e:
    print(f"❌ Execution error: {e}")
    print("Check your runtime and parameters")

except Exception as e:
    print(f"❌ Unexpected error: {e}")
```

### Advanced Error Handling

```python
def robust_execution(agent, input_data, max_retries=3):
    """Execute agent with retry logic and fallback."""

    for attempt in range(max_retries):
        try:
            # Attempt execution
            workflow = agent.to_workflow()
            results, run_id = runtime.execute(
                workflow.build(),
                parameters=input_data,
                timeout=30
            )

            # Validate results
            if validate_results(results):
                return results, run_id
            else:
                raise ValueError("Invalid results format")

        except TimeoutError:
            print(f"Attempt {attempt + 1}: Timeout, retrying...")
            if attempt == max_retries - 1:
                return {"error": "Execution timeout"}, None

        except Exception as e:
            print(f"Attempt {attempt + 1}: Error {e}")
            if attempt == max_retries - 1:
                return {"error": str(e)}, None

    return {"error": "Max retries exceeded"}, None

def validate_results(results):
    """Validate result structure matches signature."""
    required_keys = ["summary", "sentiment"]
    return all(key in results for key in required_keys)
```

## 🔍 Debugging and Monitoring

### Debug Mode

```python
# Enable debug mode
framework = kaizen.Kaizen(
    debug=True,
    signature_programming_enabled=True
)

# Create agent with debug info
agent = framework.create_agent(
    "debug_agent",
    config={
        "model": "gpt-3.5-turbo",
        "debug": True,
        "log_level": "DEBUG"
    },
    signature="text -> summary"
)

# Execution shows detailed logs
results, run_id = runtime.execute(
    workflow.build(),
    parameters={"text": "Test input"}
)
```

### Performance Monitoring

```python
import time

def monitor_execution(agent, input_data):
    """Monitor execution performance."""

    start_time = time.time()

    # Execute
    workflow = agent.to_workflow()
    results, run_id = runtime.execute(
        workflow.build(),
        parameters=input_data
    )

    end_time = time.time()
    execution_time = end_time - start_time

    # Log performance metrics
    print(f"Execution completed in {execution_time:.2f}s")
    print(f"Run ID: {run_id}")
    print(f"Input size: {len(str(input_data))} chars")
    print(f"Output size: {len(str(results))} chars")

    return results, {
        "run_id": run_id,
        "execution_time": execution_time,
        "input_size": len(str(input_data)),
        "output_size": len(str(results))
    }
```

### Audit Trail Access

```python
# For enterprise agents with audit trails
if hasattr(agent, 'audit_trail'):
    audit_entries = agent.audit_trail.get_entries()
    for entry in audit_entries:
        print(f"Action: {entry['action']}")
        print(f"Timestamp: {entry['timestamp']}")
        print(f"User: {entry.get('user_id', 'system')}")
        print(f"Result: {entry['success']}")
        print("---")
```

## 🔗 Integration Patterns

### Core SDK Workflow Integration

```python
from kailash.workflow.builder import WorkflowBuilder

# Create a larger workflow with Kaizen agent
workflow = WorkflowBuilder()

# Add data processing node
workflow.add_node("CSVReaderNode", "reader", {
    "file_path": "data.csv"
})

# Add Kaizen agent as a node
kaizen_agent = framework.create_agent(
    "analyzer",
    signature="data -> insights"
)

# Convert agent to workflow node
agent_node = kaizen_agent.to_workflow_node()
workflow.add_node_instance(agent_node)

# Connect nodes
workflow.add_edge("reader", "analyzer")

# Execute complete workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### DataFlow Integration

```python
# Integration with DataFlow models
from kailash_dataflow import db

@db.model
class AnalysisResult:
    text: str
    summary: str
    sentiment: str
    confidence: float

# Create agent that outputs to DataFlow model
analyzer = framework.create_agent(
    "dataflow_analyzer",
    signature="text -> summary, sentiment, confidence"
)

# Execute and save to database
results, run_id = runtime.execute(
    workflow.build(),
    parameters={"text": "Document text"}
)

# Save to DataFlow model
analysis = AnalysisResult(
    text=results["text"],
    summary=results["summary"],
    sentiment=results["sentiment"],
    confidence=results["confidence"]
)
analysis.save()
```

### Multi-Agent Coordination

```python
# Create multiple specialized agents
summarizer = framework.create_agent(
    "summarizer",
    signature="text -> summary"
)

sentiment_analyzer = framework.create_agent(
    "sentiment_analyzer",
    signature="text -> sentiment, confidence"
)

topic_extractor = framework.create_agent(
    "topic_extractor",
    signature="text -> topics, categories"
)

# Coordinate execution
def analyze_document(text):
    """Coordinate multiple agents for document analysis."""

    # Run agents in parallel or sequence
    summary_workflow = summarizer.to_workflow()
    sentiment_workflow = sentiment_analyzer.to_workflow()
    topics_workflow = topic_extractor.to_workflow()

    # Execute all
    summary_results, _ = runtime.execute(
        summary_workflow.build(),
        parameters={"text": text}
    )

    sentiment_results, _ = runtime.execute(
        sentiment_workflow.build(),
        parameters={"text": text}
    )

    topics_results, _ = runtime.execute(
        topics_workflow.build(),
        parameters={"text": text}
    )

    # Combine results
    return {
        "summary": summary_results["summary"],
        "sentiment": sentiment_results["sentiment"],
        "confidence": sentiment_results["confidence"],
        "topics": topics_results["topics"],
        "categories": topics_results["categories"]
    }
```

## 🚀 Complete Example

Here's a comprehensive example bringing everything together:

```python
import kaizen
from kailash.runtime.local import LocalRuntime
import time

def create_advanced_analyzer():
    """Create a sophisticated document analyzer."""

    # Initialize framework with enterprise features
    framework = kaizen.Kaizen(
        signature_programming_enabled=True,
        enterprise_features=True,
        debug=True
    )

    # Create specialized analyzer
    config = {
        "model": "gpt-4",
        "temperature": 0.3,
        "max_tokens": 1500,
        "expertise": "document_analysis",
        "behavior_traits": ["thorough", "analytical", "precise"],
        "audit_enabled": True,
        "include_confidence": True
    }

    agent = framework.create_agent(
        agent_id="document_analyzer",
        config=config,
        signature="""
        document_text -> {
            summary: str,
            sentiment: str,
            key_topics: [str],
            insights: [str],
            confidence: float,
            metadata: {
                word_count: int,
                readability: str,
                language: str
            }
        }
        """
    )

    return agent

def analyze_document_robustly(agent, document_text):
    """Robust document analysis with error handling."""

    runtime = LocalRuntime()

    try:
        start_time = time.time()

        # Convert to workflow
        workflow = agent.to_workflow()

        # Execute with monitoring
        print("🔄 Analyzing document...")
        results, run_id = runtime.execute(
            workflow.build(),
            parameters={"document_text": document_text}
        )

        execution_time = time.time() - start_time

        # Validate results
        if not results or "summary" not in results:
            raise ValueError("Invalid analysis results")

        # Display results
        print(f"✅ Analysis completed in {execution_time:.2f}s")
        print(f"📄 Document: {len(document_text)} characters")
        print(f"📝 Summary: {results['summary']}")
        print(f"😊 Sentiment: {results['sentiment']}")
        print(f"🔑 Topics: {', '.join(results['key_topics'])}")
        print(f"💡 Insights: {len(results['insights'])} insights found")
        print(f"📊 Confidence: {results['confidence']:.2f}")

        return results, run_id

    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        return None, None

# Example usage
if __name__ == "__main__":
    # Create analyzer
    analyzer = create_advanced_analyzer()

    # Sample document
    document = """
    The future of artificial intelligence in enterprise applications
    looks incredibly promising. Companies are increasingly adopting
    AI solutions for customer service, data analysis, and process
    automation. However, challenges remain in areas such as data
    privacy, algorithmic bias, and the need for skilled personnel.

    Recent surveys indicate that 78% of enterprises plan to increase
    their AI investments in the next two years. The key drivers include
    improved efficiency, better decision-making capabilities, and
    competitive advantages in the marketplace.
    """

    # Analyze document
    results, run_id = analyze_document_robustly(analyzer, document)

    if results:
        print(f"\n🎉 Analysis successful! (Run ID: {run_id})")
    else:
        print("\n❌ Analysis failed!")
```

## 🎯 Next Steps

### Immediate Practice
1. **Experiment with different signatures** - Try various input/output patterns
2. **Test different models** - Compare GPT-3.5-turbo vs GPT-4 performance
3. **Add error handling** - Make your agents production-ready

### Advanced Features
1. **[Enterprise Features](../guides/enterprise-features.md)** - Memory systems, audit trails
2. **[Multi-Agent Workflows](../guides/multi-agent-workflows.md)** - Coordinate multiple agents
3. **[Signature Programming Guide](../guides/signature-programming.md)** - Master declarative patterns

### Integration Exploration
1. **[Core SDK Integration](../../2-core-concepts/)** - Deep workflow integration
2. **[DataFlow Usage](../dataflow/)** - Database-first development patterns
3. **[MCP Integration](../guides/mcp-integration.md)** - External tool connections

## 📚 Key Takeaways

✅ **Agent Configuration** - Complete control over model behavior and capabilities
✅ **Signature Patterns** - Flexible input/output definitions for any use case
✅ **Error Handling** - Robust execution with retry logic and validation
✅ **Performance Monitoring** - Track execution metrics and optimize performance
✅ **Integration Patterns** - Seamless integration with Core SDK and other frameworks
✅ **Enterprise Features** - Audit trails, security, and compliance capabilities

You now have the foundation to build sophisticated AI agents with Kaizen's signature-based programming approach!

---

**Ready for advanced topics?** Explore **[Enterprise Features](../guides/enterprise-features.md)** or dive into **[Multi-Agent Workflows](../guides/multi-agent-workflows.md)**.
