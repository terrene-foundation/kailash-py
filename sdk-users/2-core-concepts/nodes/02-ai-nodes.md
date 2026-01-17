# AI & ML Nodes

**Module**: `kailash.nodes.ai`
**Last Updated**: 2025-01-06

This document covers all AI and machine learning nodes, including LLM agents, embeddings, A2A communication, self-organizing agents, and intelligent orchestration.

## Table of Contents
- [Core AI Nodes](#core-ai-nodes)
- [A2A Communication Nodes](#a2a-communication-nodes)
- [Self-Organizing Agent Nodes](#self-organizing-agent-nodes)
- [Intelligent Orchestration Nodes](#intelligent-orchestration-nodes)
- [Unified AI Provider Architecture](#unified-ai-provider-architecture)

## Core AI Nodes

### LLMAgentNode
- **Module**: `kailash.nodes.ai.llm_agent`
- **Purpose**: Interact with Large Language Models with unified provider architecture
- **Parameters**:
  - `provider`: Provider name (openai, anthropic, ollama, mock)
  - `model`: LLM model to use
  - `prompt` or `messages`: Input prompt or conversation messages
  - `temperature`: Sampling temperature
  - `max_tokens`: Maximum response tokens
  - `operation`: Operation type (qa, conversation, tool_calling)
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  workflow.add_node("LLMAgentNode", "agent", {
      "provider": "openai",
      "model": "gpt-4",
      "prompt": "Explain quantum computing",
      "temperature": 0.7,
      "max_tokens": 1000
  })

  results, run_id = runtime.execute(workflow.build())
  result = results["agent"]

  ```

### EmbeddingGeneratorNode
- **Module**: `kailash.nodes.ai.embedding_generator`
- **Purpose**: Generate text embeddings using various models with caching
- **Parameters**:
  - `provider`: Provider name (openai, ollama, cohere, huggingface, mock)
  - `model`: Embedding model to use
  - `input_text` or `input_texts`: Text to embed (single or batch)
  - `operation`: Operation type (embed_text, embed_batch, calculate_similarity)
  - `batch_size`: Batch size for processing
  - `cache_enabled`: Enable caching of embeddings
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  workflow.add_node("EmbeddingGeneratorNode", "embedder", {
      "provider": "openai",
      "model": "text-embedding-3-large",
      "input_text": "This is a sample document",
      "operation": "embed_text"
  })

  results, run_id = runtime.execute(workflow.build())
  result = results["embedder"]

  ```

### IterativeLLMAgentNode
- **Module**: `kailash.nodes.ai.iterative_llm_agent`
- **Purpose**: Advanced LLM agent with iterative refinement and real MCP tool execution
- **Key Features**:
  - **Real MCP Tool Execution**: Execute actual MCP tools instead of mock responses (v0.6.5+)
  - **6-Phase Process**: Discovery → Planning → Execution → Reflection → Convergence → Synthesis
  - **Test-Driven Convergence**: Only stops when deliverables actually work
  - **Adaptive Discovery**: Progressive tool discovery based on task complexity
  - **Intelligent Execution**: Context-aware tool selection and execution
- **Parameters**:
  - `provider`: LLM provider (openai, anthropic, ollama, mock)
  - `model`: LLM model to use
  - `messages`: Input conversation messages
  - `max_iterations`: Maximum number of refinement iterations
  - `mcp_servers`: List of MCP server configurations
  - Real MCP tool execution is always enabled with graceful fallback
  - `discovery_mode`: Discovery strategy (progressive, exhaustive, focused)
  - `convergence_criteria`: Criteria for determining completion
  - `auto_discover_tools`: Enable automatic tool discovery
  - `auto_execute_tools`: Enable automatic tool execution
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  # Basic iterative refinement
  workflow.add_node("IterativeLLMAgentNode", "iterative_agent", {
      "provider": "openai",
      "model": "gpt-4",
      "messages": [{"role": "user", "content": "Analyze the sales data and create a comprehensive report"}],
      "max_iterations": 5,
      "discovery_mode": "progressive",
      "convergence_criteria": {
          "goal_satisfaction": {"threshold": 0.9},
          "quality_threshold": 0.8
      }
  })

  results, run_id = runtime.execute(workflow.build())
  result = results["iterative_agent"]

  # With real MCP tool execution
  mcp_workflow = WorkflowBuilder()
  mcp_workflow.add_node("IterativeLLMAgentNode", "mcp_agent", {
      "provider": "openai",
      "model": "gpt-4",
      "messages": [{"role": "user", "content": "Get weather data and analyze trends"}],
      "mcp_servers": [{
          "name": "weather-server",
          "transport": "stdio",
          "command": "python",
          "args": ["-m", "weather_mcp_server"]
      }],
      # Real MCP tool execution is always enabled
      "auto_discover_tools": True,
      "auto_execute_tools": True,
      "max_iterations": 3
  })

  mcp_results, mcp_run_id = runtime.execute(mcp_workflow.build())
  result = mcp_results["mcp_agent"]

  # Output includes detailed iteration history
  print(f"Completed in {len(result['iterations'])} iterations")
  print(f"Tools used: {result['context']['tools_executed']}")
  print(f"Convergence reason: {result['convergence_summary']['reason']}")

  ```

**Simplified API**: IterativeLLMAgentNode now always uses real MCP execution with graceful fallback when MCP tools are unavailable.

## Ollama Integration Patterns

### Working with Local LLMs

Ollama provides excellent local LLM capabilities. Starting from v0.6.2, the LLMAgentNode has improved Ollama support with async compatibility and custom backend configuration:

#### Using LLMAgentNode with Ollama (v0.6.2+)

```python
# Basic usage with improved async support
ollama_workflow = WorkflowBuilder()
ollama_workflow.add_node("LLMAgentNode", "ollama_agent", {
    "provider": "ollama",
    "model": "llama3.2:3b",
    "prompt": "Explain quantum computing",
    "generation_config": {
        "temperature": 0.7,
        "max_tokens": 500
    }
})

results, run_id = await runtime.execute_async(ollama_workflow.build())
result = results["ollama_agent"]

# Custom backend configuration for remote Ollama instances
remote_workflow = WorkflowBuilder()
remote_workflow.add_node("LLMAgentNode", "remote_agent", {
    "provider": "ollama",
    "model": "llama3.2:3b",
    "prompt": "Write a haiku",
    "backend_config": {
        "host": "gpu-server.local",
        "port": 11434
    }
})

remote_results, remote_run_id = await runtime.execute_async(remote_workflow.build())
result = remote_results["remote_agent"]

# Or use base_url directly
workflow.add_node("LLMAgentNode", "node", {
    "provider": "ollama",
    "model": "llama3.2:3b",
    "prompt": "Analyze this data",
    "backend_config": {
        "base_url": "http://ollama.company.com:11434"
    }
})
results, run_id = await runtime.execute_async(workflow.build())
result = results["node"]
```

#### Alternative: Direct API Calls with PythonCodeNode

For specific use cases or when you need more control, you can also use **direct API calls wrapped in PythonCodeNode**:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.code import PythonCodeNode

def ollama_generate(prompt="Hello world", model="llama3.2:1b"):
    """Reliable Ollama LLM generation using direct API."""
    import requests
    import json

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 200
                }
            },
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "response": data.get("response", ""),
                "model": data.get("model", ""),
                "duration": data.get("total_duration", 0) / 1e9
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# Create workflow with Ollama generation
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "llm", PythonCodeNode.from_function(ollama_generate).config)

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "llm": {"prompt": "Write a haiku about programming", "model": "llama3.2:1b"}
})
result = results

# Access result
if result["llm"]["result"]["success"]:
    print(result["llm"]["result"]["response"])
```

### Ollama Embeddings

Generate embeddings using the nomic-embed-text model:

```python
def ollama_embeddings(texts=None):
    """Generate embeddings using Ollama."""
    import requests

    if not texts:
        texts = ["Hello world"]

    embeddings = []
    errors = []

    for text in texts:
        try:
            response = requests.post(
                "http://localhost:11434/api/embeddings",
                json={
                    "model": "nomic-embed-text:latest",
                    "prompt": text
                },
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                # ✅ CRITICAL: Extract embedding correctly
                embeddings.append(data.get("embedding", []))
            else:
                errors.append(f"Failed for '{text}': HTTP {response.status_code}")
        except Exception as e:
            errors.append(f"Failed for '{text}': {str(e)}")

    return {
        "success": len(errors) == 0,
        "embeddings": embeddings,
        "embedding_dims": len(embeddings[0]) if embeddings else 0,
        "errors": errors
    }

# Usage in workflow
workflow.add_node("PythonCodeNode", "embed", PythonCodeNode.from_function(ollama_embeddings).config)

results, run_id = runtime.execute(workflow.build(), parameters={
    "embed": {"texts": ["Python is great", "AI is fascinating"]}
})
result = results

# Extract embeddings
if result["embed"]["result"]["success"]:
    embeddings = result["embed"]["result"]["embeddings"]
    print(f"Generated {len(embeddings)} embeddings of {result['embed']['result']['embedding_dims']} dimensions")
```

### Ollama in Data Processing Pipelines

Complete example with sentiment analysis:

```python
def analyze_sentiment_ollama(reviews):
    """Analyze sentiment using Ollama LLM."""
    import requests
    import json
    import re

    results = []

    for review in reviews:
        prompt = f"""Analyze sentiment and respond with ONLY JSON:
{{"sentiment": "positive" or "negative" or "neutral", "confidence": 0.0-1.0}}

Review: {review['text']}

JSON:"""

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2:1b",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 50}
                },
                timeout=20
            )

            if response.status_code == 200:
                llm_response = response.json()["response"].strip()

                # Extract JSON from response
                json_match = re.search(r'\{[^}]+\}', llm_response)
                if json_match:
                    sentiment_data = json.loads(json_match.group())
                else:
                    # Fallback parsing
                    if "positive" in llm_response.lower():
                        sentiment_data = {"sentiment": "positive", "confidence": 0.7}
                    elif "negative" in llm_response.lower():
                        sentiment_data = {"sentiment": "negative", "confidence": 0.7}
                    else:
                        sentiment_data = {"sentiment": "neutral", "confidence": 0.5}

                results.append({
                    "id": review["id"],
                    "text": review["text"],
                    "sentiment": sentiment_data.get("sentiment", "unknown"),
                    "confidence": sentiment_data.get("confidence", 0.0)
                })
            else:
                results.append({
                    "id": review["id"],
                    "text": review["text"],
                    "sentiment": "error",
                    "confidence": 0.0
                })
        except Exception as e:
            results.append({
                "id": review["id"],
                "text": review["text"],
                "sentiment": "error",
                "confidence": 0.0,
                "error": str(e)
            })

    return {
        "analyzed_reviews": results,
        "success": all(r["sentiment"] != "error" for r in results)
    }

# Complete pipeline
workflow = WorkflowBuilder()

# Data generator
def generate_reviews():
    return {
        "reviews": [
            {"id": 1, "text": "This product is amazing!"},
            {"id": 2, "text": "Terrible quality, very disappointed."},
            {"id": 3, "text": "It's okay, nothing special."}
        ]
    }

# Sentiment analyzer - use the function in workflow

workflow.add_node("PythonCodeNode", "data", PythonCodeNode.from_function(generate_reviews).config)
workflow.add_node("PythonCodeNode", "analyze", PythonCodeNode.from_function(analyze_sentiment_ollama).config)
workflow.add_connection("data", "result", "analyze", "reviews")

result, _ = runtime.execute(workflow.build())
print(f"Analyzed {len(result['analyze']['result']['analyzed_reviews'])} reviews")
```

### Ollama in Cyclic Workflows

Ollama works excellently in cycles for iterative improvement:

```python
def iterative_text_improver(text="", iteration=0, target_length=50):
    """Iteratively improve text using Ollama."""
    import requests

    if iteration == 0:
        prompt = f"Write a short story. Make it exactly {target_length} words."
    else:
        current_length = len(text.split())
        if abs(current_length - target_length) <= 5:
            return {
                "text": text,
                "iteration": iteration,
                "word_count": current_length,
                "converged": True
            }

        if current_length < target_length:
            prompt = f"Expand this story to {target_length} words: {text}"
        else:
            prompt = f"Shorten this story to {target_length} words: {text}"

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2:1b",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 200}
            },
            timeout=30
        )

        if response.status_code == 200:
            new_text = response.json()["response"].strip()
            word_count = len(new_text.split())

            return {
                "text": new_text,
                "iteration": iteration + 1,
                "word_count": word_count,
                "converged": abs(word_count - target_length) <= 5
            }
    except Exception as e:
        return {
            "text": text,
            "iteration": iteration,
            "word_count": len(text.split()) if text else 0,
            "converged": True,  # Stop on error
            "error": str(e)
        }

# Cyclic workflow
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "write", PythonCodeNode.from_function(iterative_text_improver).config)

# Build workflow FIRST, then create improvement cycle
built_workflow = workflow.build()
cycle_builder = built_workflow.create_cycle("writing_cycle")
# CRITICAL: Use "result." prefix for PythonCodeNode outputs
cycle_builder.connect("write", "write", mapping={
    "result.text": "text",
    "result.iteration": "iteration",
    "result.target_length": "target_length"
}).max_iterations(5).converge_when("converged == True").build()

results, run_id = runtime.execute(built_workflow, parameters={
    "write": {"text": "", "iteration": 0, "target_length": 50}
})
result = results

print(f"Generated story in {result['write']['result']['iteration']} iterations")
print(f"Final word count: {result['write']['result']['word_count']}")
```

### Ollama Configuration

**Docker Integration**: Ollama runs on port 11434 by default. Ensure Docker services are available:

```python
# Test Ollama connectivity
import requests

def test_ollama():
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            print(f"✅ Ollama available with {len(models)} models")
            return True
    except Exception as e:
        print(f"❌ Ollama not available: {e}")
        return False
```

**Recommended Models**:
- **LLM**: `llama3.2:1b` (fast, good for development)
- **Embeddings**: `nomic-embed-text:latest` (768 dimensions)

### ChatAgent & RetrievalAgent
- **ChatAgent Module**: `kailash.nodes.ai.agents`
- **RetrievalAgent Module**: `kailash.nodes.ai.agents`
- **Purpose**: Specialized agents for conversation and document retrieval
- **Features**: Built on unified provider architecture with enhanced capabilities

## A2A Communication Nodes

### SharedMemoryPoolNode
- **Module**: `kailash.nodes.ai.a2a`
- **Purpose**: Central memory pool for agent-to-agent communication
- **Parameters**:
  - `action`: Memory operation (read, write, subscribe, query)
  - `agent_id`: ID of the agent performing action
  - `content`: Content to write (for write action)
  - `attention_filter`: Filter criteria for reading memories
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  workflow.add_node("SharedMemoryPoolNode", "memory_pool", {})
  runtime = LocalRuntime()
  results, run_id = runtime.execute(workflow.build(), parameters={
      "memory_pool": {
          "action": "write",
          "agent_id": "researcher_001",
          "content": "Key finding about correlation",
          "tags": ["research", "correlation"],
          "importance": 0.8
      }
  })
  result = results["memory_pool"]

  ```

### A2AAgentNode
- **Module**: `kailash.nodes.ai.a2a`
- **Purpose**: Enhanced LLM agent with A2A communication capabilities
- **Parameters**: Extends LLMAgentNode parameters plus:
  - `agent_id`: Unique agent identifier
  - `agent_role`: Agent's role (researcher, analyst, etc.)
  - `memory_pool`: Reference to SharedMemoryPoolNode
  - `attention_filter`: Criteria for filtering relevant information
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  workflow.add_node("A2AAgentNode", "agent", {})
  runtime = LocalRuntime()
  results, run_id = runtime.execute(workflow.build(), parameters={
      "agent": {
          "agent_id": "researcher_001",
          "provider": "openai",
          "model": "gpt-4",
          "messages": [{"role": "user", "content": "Analyze data"}],
          "memory_pool": "memory_pool_ref",
          "attention_filter": {"tags": ["data", "analysis"]}
      }
  })
  result = results["agent"]

  ```

### A2ACoordinatorNode
- **Module**: `kailash.nodes.ai.a2a`
- **Purpose**: Coordinates communication and task delegation between agents
- **Parameters**:
  - `action`: Coordination action (register, delegate, broadcast, consensus)
  - `agent_info`: Agent information for registration
  - `task`: Task to delegate or coordinate
  - `coordination_strategy`: Strategy (best_match, round_robin, auction)
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  workflow.add_node("A2ACoordinatorNode", "coordinator", {})
  runtime = LocalRuntime()
  results, run_id = runtime.execute(workflow.build(), parameters={
      "coordinator": {
          "action": "delegate",
          "task": {"type": "research", "description": "Analyze trends"},
          "available_agents": [{"id": "agent1", "skills": ["research"]}],
          "coordination_strategy": "best_match"
      }
  })
  result = results["coordinator"]

  ```

## Self-Organizing Agent Nodes

### AgentPoolManagerNode
- **Module**: `kailash.nodes.ai.self_organizing`
- **Purpose**: Manages pool of self-organizing agents with capability tracking
- **Parameters**:
  - `action`: Pool operation (register, find_by_capability, update_status)
  - `agent_id`: ID of the agent
  - `capabilities`: List of agent capabilities
  - `required_capabilities`: Capabilities required for search
- **Features**:
  - Agent registry with capability indexing
  - Performance tracking and load balancing
  - Dynamic agent discovery and matching
  - Real-time availability monitoring
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  workflow.add_node("AgentPoolManagerNode", "pool_manager", {})
  runtime = LocalRuntime()
  results, run_id = runtime.execute(workflow.build(), parameters={
      "pool_manager": {
          "action": "register",
          "agent_id": "research_agent_001",
          "capabilities": ["data_analysis", "research"],
          "metadata": {"experience_level": "senior"}
      }
  })
  result = results["pool_manager"]

  ```

### ProblemAnalyzerNode
- **Module**: `kailash.nodes.ai.self_organizing`
- **Purpose**: Analyzes problems to determine required capabilities and complexity
- **Parameters**:
  - `problem_description`: Description of problem to solve
  - `context`: Additional context about the problem
  - `decomposition_strategy`: Strategy for decomposing problem
- **Features**:
  - Problem complexity assessment
  - Capability requirement analysis
  - Multi-level problem decomposition
  - Resource estimation and planning
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  workflow.add_node("ProblemAnalyzerNode", "analyzer", {})
  runtime = LocalRuntime()
  results, run_id = runtime.execute(workflow.build(), parameters={
      "analyzer": {
          "problem_description": "Predict customer churn",
          "context": {"domain": "business", "urgency": "high"}
      }
  })
  result = results["analyzer"]

  ```

### TeamFormationNode
- **Module**: `kailash.nodes.ai.self_organizing`
- **Purpose**: Forms optimal teams based on problem requirements
- **Parameters**:
  - `problem_analysis`: Analysis from ProblemAnalyzerNode
  - `available_agents`: List of available agents
  - `formation_strategy`: Team formation strategy
  - `constraints`: Constraints for team formation
- **Formation Strategies**:
  - `capability_matching`: Match agents to required skills
  - `swarm_based`: Self-organizing exploration teams
  - `market_based`: Auction-based agent allocation
  - `hierarchical`: Structured teams with clear roles
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  workflow.add_node("TeamFormationNode", "formation_engine", {})
  runtime = LocalRuntime()
  results, run_id = runtime.execute(workflow.build(), parameters={
      "formation_engine": {
          "problem_analysis": "analysis_ref",
          "available_agents": "agents_ref",
          "formation_strategy": "capability_matching"
      }
  })
  result = results["formation_engine"]

  ```

### SelfOrganizingAgentNode
- **Module**: `kailash.nodes.ai.self_organizing`
- **Purpose**: Agent that can autonomously join teams and collaborate
- **Parameters**: Extends A2AAgentNode parameters plus:
  - `capabilities`: Agent's capabilities
  - `team_context`: Current team information
  - `collaboration_mode`: Mode (cooperative, competitive, mixed)
  - `autonomy_level`: Level of autonomous decision making
- **Features**:
  - Autonomous team joining and role adaptation
  - Dynamic capability learning and evolution
  - Context-aware collaboration patterns
  - Performance-based specialization
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  workflow.add_node("SelfOrganizingAgentNode", "agent", {})
  runtime = LocalRuntime()
  results, run_id = runtime.execute(workflow.build(), parameters={
      "agent": {
          "agent_id": "adaptive_agent_001",
          "capabilities": ["data_analysis", "machine_learning"],
          "team_context": {"team_id": "research_team_1"},
          "task": "Perform clustering analysis"
      }
  })
  result = results["agent"]

  ```

### SolutionEvaluatorNode
- **Module**: `kailash.nodes.ai.self_organizing`
- **Purpose**: Evaluates solutions and determines if iteration is needed
- **Parameters**:
  - `solution`: Solution to evaluate
  - `problem_requirements`: Original problem requirements
  - `team_performance`: Team performance metrics
  - `evaluation_criteria`: Custom evaluation criteria
- **Features**:
  - Multi-criteria solution assessment
  - Quality threshold monitoring
  - Iterative improvement detection
  - Team performance correlation analysis
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  workflow.add_node("SolutionEvaluatorNode", "evaluator", {})
  runtime = LocalRuntime()
  results, run_id = runtime.execute(workflow.build(), parameters={
      "evaluator": {
          "solution": {"approach": "ML model", "confidence": 0.85},
          "problem_requirements": {"quality_threshold": 0.8},
          "team_performance": {"collaboration_score": 0.9}
      }
  })
  result = results["evaluator"]

  ```

## Intelligent Orchestration Nodes

### IntelligentCacheNode
- **Module**: `kailash.nodes.ai.intelligent_agent_orchestrator`
- **Purpose**: Intelligent caching system to prevent repeated external calls
- **Features**:
  - Semantic similarity detection for cache hits
  - TTL-based expiration with smart refresh policies
  - Cost-aware caching prioritizing expensive operations
  - Cross-agent information sharing
- **Parameters**:
  - `action`: Cache operation (cache, get, invalidate, stats, cleanup)
  - `cache_key`: Unique key for cached item
  - `data`: Data to cache
  - `metadata`: Metadata including source, cost, semantic tags
  - `ttl`: Time to live in seconds
  - `similarity_threshold`: Threshold for semantic matching
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  workflow.add_node("IntelligentCacheNode", "cache", {})
  runtime = LocalRuntime()
  results, run_id = runtime.execute(workflow.build(), parameters={
      "cache": {
          "action": "cache",
          "cache_key": "weather_api_nyc",
          "data": {"temperature": 72, "humidity": 65},
          "metadata": {
              "source": "weather_mcp_server",
              "cost": 0.05,
              "semantic_tags": ["weather", "temperature", "nyc"]
          },
          "ttl": 3600
      }
  })
  result = results["cache"]

  ```

### MCPAgentNode
- **Module**: `kailash.nodes.ai.intelligent_agent_orchestrator`
- **Purpose**: Self-organizing agent enhanced with MCP integration
- **Features**:
  - Access external tools through MCP servers
  - Integration with intelligent caching
  - Tool capability sharing with team members
  - Adaptive tool usage based on team needs
- **Parameters**: Extends SelfOrganizingAgentNode parameters plus:
  - `mcp_servers`: List of MCP server configurations
  - `cache_node_id`: ID of cache node for preventing repeated calls
  - `tool_preferences`: Agent's preferences for tool usage
  - `cost_awareness`: How cost-conscious the agent is (0-1)
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  workflow.add_node("MCPAgentNode", "agent", {})
  runtime = LocalRuntime()
  results, run_id = runtime.execute(workflow.build(), parameters={
      "agent": {
          "agent_id": "mcp_agent_001",
          "capabilities": ["data_analysis", "api_integration"],
          "mcp_servers": [{
              "name": "weather_server",
              "command": "python",
              "args": ["-m", "weather_mcp"]
          }],
          "task": "Get weather for NYC and analyze trends"
      }
  })
  result = results["agent"]

  ```

### QueryAnalysisNode
- **Module**: `kailash.nodes.ai.intelligent_agent_orchestrator`
- **Purpose**: Analyzes queries to determine optimal solving approach
- **Features**:
  - Pattern recognition for query types
  - Complexity assessment and capability requirements
  - Team composition suggestions
  - MCP tool requirement analysis
- **Parameters**:
  - `query`: The query to analyze
  - `context`: Additional context about the query
  - `available_agents`: List of available agents
  - `mcp_servers`: Available MCP servers
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  workflow.add_node("QueryAnalysisNode", "analyzer", {})
  runtime = LocalRuntime()
  results, run_id = runtime.execute(workflow.build(), parameters={
      "analyzer": {
          "query": "Research renewable energy trends and create strategic plan",
          "context": {"domain": "strategic_planning", "urgency": "high"},
          "mcp_servers": [{"name": "research_server", "type": "web_research"}]
      }
  })
  result = results["analyzer"]

  ```

### OrchestrationManagerNode
- **Module**: `kailash.nodes.ai.intelligent_agent_orchestrator`
- **Purpose**: Central coordinator for entire self-organizing workflow
- **Features**:
  - Multi-phase execution (analysis → formation → collaboration → evaluation)
  - Agent pool management with specializations
  - Iterative solution refinement
  - Performance monitoring and optimization
- **Parameters**:
  - `query`: Main query or problem to solve
  - `context`: Additional context for the query
  - `agent_pool_size`: Number of agents in the pool
  - `mcp_servers`: MCP server configurations
  - `max_iterations`: Maximum number of solution iterations
  - `quality_threshold`: Quality threshold for solution acceptance
  - `time_limit_minutes`: Maximum time limit for solution
  - `enable_caching`: Enable intelligent caching
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  workflow.add_node("OrchestrationManagerNode", "orchestrator", {})
  runtime = LocalRuntime()
  results, run_id = runtime.execute(workflow.build(), parameters={
      "orchestrator": {
          "query": "Analyze market trends and develop strategy",
          "agent_pool_size": 15,
          "mcp_servers": [{"name": "market_server", "type": "market_data"}],
          "max_iterations": 3,
          "quality_threshold": 0.85
      }
  })
  result = results["orchestrator"]

  ```

### ConvergenceDetectorNode
- **Module**: `kailash.nodes.ai.intelligent_agent_orchestrator`
- **Purpose**: Determines when solutions are satisfactory and iteration should terminate
- **Features**:
  - Multiple convergence signals (quality, improvement rate, consensus)
  - Diminishing returns detection
  - Resource efficiency monitoring
  - Recommendation generation
- **Parameters**:
  - `solution_history`: History of solution iterations
  - `quality_threshold`: Minimum quality threshold
  - `improvement_threshold`: Minimum improvement to continue
  - `max_iterations`: Maximum allowed iterations
  - `current_iteration`: Current iteration number
  - `time_limit_seconds`: Maximum time allowed
- **Example**:
  ```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

  workflow.add_node("ConvergenceDetectorNode", "detector", {})
  runtime = LocalRuntime()
  results, run_id = runtime.execute(workflow.build(), parameters={
      "detector": {
          "solution_history": "solution_iterations_ref",
          "quality_threshold": 0.8,
          "improvement_threshold": 0.02,
          "current_iteration": 3
      }
  })
  result = results["detector"]

  ```

## Troubleshooting Ollama Integration (v0.6.2+)

### Common Issues and Solutions

1. **Async Compatibility Issues**
   - **Problem**: `RuntimeError: cannot be used in 'async with' expression`
   - **Solution**: Update to v0.6.2+ which uses `aiohttp` for proper async support

2. **Connection Errors**
   - **Problem**: Cannot connect to Ollama service
   - **Solution**:
     ```python
     # Check environment variables
     export OLLAMA_BASE_URL=http://localhost:11434
     # Or use backend_config
     backend_config={"base_url": "http://localhost:11434"}
     ```

3. **Type Errors in Responses**
   - **Problem**: `TypeError: unhashable type: 'dict'`
   - **Solution**: v0.6.2+ includes defensive type checking for all LLM responses

4. **Timeout Issues**
   - **Problem**: Requests timing out on large models
   - **Solution**: Configure appropriate timeouts
     ```python
     generation_config={
         "max_tokens": 200,  # Reduce for faster responses
         "temperature": 0.7
     }
     ```

5. **Model Not Found**
   - **Problem**: Model not available locally
   - **Solution**: Pull the model first
     ```bash
     ollama pull llama3.2:3b
     ollama pull nomic-embed-text:latest
     ```

## Unified AI Provider Architecture

The SDK features a unified provider architecture supporting multiple AI providers:

**Supported Providers**:
- **OpenAI**: GPT models and text-embedding series
- **Azure**: Unified Azure provider (auto-detects Azure OpenAI vs AI Foundry)
- **Anthropic**: Claude models (chat only)
- **Google**: Gemini models with vision, embeddings, and tool calling
- **Ollama**: Local LLMs with both chat and embeddings
- **Docker**: Docker Model Runner for local inference
- **Cohere**: Embedding models
- **HuggingFace**: Sentence transformers and local models
- **Mock**: Testing provider with consistent outputs

**Auto-Detection Priority**: OpenAI → Azure → Anthropic → Google → Ollama → Docker

**Example**:
```python
from kailash.nodes.ai.ai_providers import get_available_providers, get_provider
providers = get_available_providers()
# Returns: {"ollama": {"available": True, "chat": True, "embeddings": True}, ...}

# Get specific provider
azure_provider = get_provider("azure")
print(azure_provider.get_detected_backend())  # "azure_openai" or "azure_ai_foundry"
```

### Unified Azure Provider (v0.9.0)

The `azure` provider intelligently auto-detects between Azure OpenAI Service and Azure AI Foundry based on endpoint patterns.

**Configuration**:
```bash
export AZURE_ENDPOINT="https://myresource.openai.azure.com"
export AZURE_API_KEY="your-api-key"
export AZURE_DEPLOYMENT="gpt-4o"  # Optional: default deployment
# Optional override: AZURE_BACKEND=openai|foundry
```

**Backend Detection**:
| Endpoint Pattern | Detected Backend |
|------------------|------------------|
| `*.openai.azure.com` | Azure OpenAI Service |
| `*.inference.ai.azure.com` | Azure AI Foundry |
| `*.services.ai.azure.com` | Azure AI Foundry |
| Unknown patterns | Azure OpenAI (default) |

**Backend-Specific Features**:
| Feature | Azure OpenAI | AI Foundry |
|---------|--------------|------------|
| Audio input | ✅ | ❌ |
| Reasoning models (o1/o3/GPT-5) | ✅ | ❌ |
| Llama/Mistral models | ❌ | ✅ |
| Structured output (json_schema) | ✅ | ✅ |

**Usage**:
```python
from kailash.nodes.ai import get_provider

provider = get_provider("azure")

# Auto-detect backend
print(provider.get_detected_backend())  # "azure_openai" or "azure_ai_foundry"
print(provider.get_capabilities())  # Feature dictionary

# Chat with automatic parameter handling
response = provider.chat(
    messages=[{"role": "user", "content": "Hello"}],
    model="gpt-4o"
)

# Reasoning models - temperature auto-filtered
response = provider.chat(
    messages=[{"role": "user", "content": "Think step by step"}],
    model="o1-preview",  # Temperature/top_p automatically removed
    generation_config={"temperature": 0.7}  # Ignored
)
```

## See Also
- [Base Classes](01-base-nodes.md) - Core node abstractions
- [Data Nodes](03-data-nodes.md) - Data processing and I/O
- [API Reference](../api/04-nodes-ai.yaml) - Detailed API documentation
