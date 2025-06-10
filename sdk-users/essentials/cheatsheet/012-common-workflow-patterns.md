# Common Workflow Patterns

## ETL Pipeline
```python
workflow = Workflow("etl-001", name="etl_pipeline")

# Extract
workflow.add_node("extract", CSVReaderNode(), file_path="raw_data.csv")

# Transform
workflow.add_node("transform", DataTransformerNode(),
    operations=[
        {"type": "filter", "condition": "valid == True"},
        {"type": "map", "expression": "upper(name)"},
        {"type": "sort", "key": "timestamp"}
    ]
)

# Load
workflow.add_node("load", CSVWriterNode(), file_path="processed_data.csv")

# Connect pipeline
workflow.connect("extract", "transform")
workflow.connect("transform", "load")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)
```

## Hierarchical RAG Pipeline
```python
from kailash.nodes.data.sources import DocumentSourceNode, QuerySourceNode
from kailash.nodes.data.retrieval import RelevanceScorerNode
from kailash.nodes.transform.chunkers import HierarchicalChunkerNode
from kailash.nodes.transform.formatters import (
    ChunkTextExtractorNode, QueryTextWrapperNode, ContextFormatterNode
)

workflow = Workflow("rag-001", name="hierarchical_rag")

# Data sources
workflow.add_node("doc_source", DocumentSourceNode())
workflow.add_node("query_source", QuerySourceNode())

# Document processing
workflow.add_node("chunker", HierarchicalChunkerNode(),
    chunk_size=1000, chunk_overlap=200)
workflow.add_node("chunk_text_extractor", ChunkTextExtractorNode())
workflow.add_node("query_wrapper", QueryTextWrapperNode())

# Embeddings
workflow.add_node("chunk_embedder", EmbeddingGeneratorNode(),
    provider="ollama", model="nomic-embed-text", operation="embed_batch")
workflow.add_node("query_embedder", EmbeddingGeneratorNode(),
    provider="ollama", model="nomic-embed-text", operation="embed_batch")

# Retrieval and generation
workflow.add_node("scorer", RelevanceScorerNode(),
    similarity_method="cosine", top_k=5)
workflow.add_node("formatter", ContextFormatterNode())
workflow.add_node("llm", LLMAgentNode(),
    provider="ollama", model="llama3.2", temperature=0.7)

# Connect RAG pipeline
workflow.connect("doc_source", "chunker")
workflow.connect("chunker", "chunk_text_extractor")
workflow.connect("chunk_text_extractor", "chunk_embedder")
workflow.connect("query_source", "query_wrapper")
workflow.connect("query_wrapper", "query_embedder")
workflow.connect("chunker", "scorer", {"chunks": "chunks"})
workflow.connect("query_embedder", "scorer", {"embeddings": "query_embedding"})
workflow.connect("chunk_embedder", "scorer", {"embeddings": "chunk_embeddings"})
workflow.connect("scorer", "formatter")
workflow.connect("query_source", "formatter", {"query": "query"})
workflow.connect("formatter", "llm")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow)
```

## Self-Organizing Agent Workflow
```python
workflow = Workflow("agents-001", name="self_organizing_research")

# Shared infrastructure
workflow.add_node("memory", SharedMemoryPoolNode(),
    memory_size_limit=1000, attention_window=50)
workflow.add_node("cache", IntelligentCacheNode(),
    ttl=3600, similarity_threshold=0.8)

# Problem analysis and team formation
workflow.add_node("analyzer", ProblemAnalyzerNode())
workflow.add_node("team_former", TeamFormationNode(),
    formation_strategy="capability_matching")

# Agent pool
workflow.add_node("pool", AgentPoolManagerNode(),
    max_active_agents=20, agent_timeout=120)

# Orchestration
workflow.add_node("orchestrator", OrchestrationManagerNode(),
    max_iterations=10, quality_threshold=0.85)

# Connect components
workflow.connect("orchestrator", "analyzer")
workflow.connect("analyzer", "team_former")
workflow.connect("team_former", "pool")

# Execute with complex problem
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "orchestrator": {
        "query": "Analyze market trends for fintech growth strategy",
        "agent_pool_size": 12,
        "context": {"domain": "fintech", "depth": "comprehensive"}
    }
})
```

## API Gateway for Multiple Workflows
```python
from kailash.api.gateway import WorkflowAPIGateway
from kailash.api.mcp_integration import MCPIntegration

# Create gateway
gateway = WorkflowAPIGateway(
    title="Enterprise Platform",
    description="Unified API for all workflows"
)

# Register workflows
gateway.register_workflow("sales", sales_workflow)
gateway.register_workflow("analytics", analytics_workflow)

# Add MCP tools
mcp = MCPIntegration("ai_tools")
mcp.add_tool("analyze", analyze_function)
gateway.register_mcp_server("ai", mcp)

# Run gateway
gateway.run(port=8000)

# Access endpoints:
# POST /sales/execute
# POST /analytics/execute
# GET /workflows
# GET /health
```
