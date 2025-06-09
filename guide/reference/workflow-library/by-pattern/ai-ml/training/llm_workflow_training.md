# LLM Workflow Training - Common Mistakes and Corrections

This document shows common mistakes when building LLM workflows with Kailash SDK, followed by correct implementations.

## CORRECT: Using LLMAgentNode

```python
# CORRECT: Use LLMAgentNode for LLM interactions
from kailash.nodes.ai import LLMAgentNode

llm_node = LLMAgentNode(
    name="assistant",
    model="gpt-4",
    system_prompt="You are a helpful AI assistant"
)

# Runtime parameters
parameters = {
    "assistant": {
        "prompt": "Analyze this text: {{input_text}}",
        "temperature": 0.7,
        "max_tokens": 500
    }
}
```

## WRONG: Using PythonCodeNode for LLM Calls

```python
# WRONG: Don't implement OpenAI calls manually
llm_node = PythonCodeNode(
    name="llm_call",
    code="""
import openai
openai.api_key = "sk-..."
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "You are helpful"},
        {"role": "user", "content": input_text}
    ]
)
result = {"response": response.choices[0].message.content}
"""
)

# Problems:
# 1. Hardcoded API keys (security risk)
# 2. No error handling
# 3. No retry logic
# 4. No cost tracking
```

## CORRECT: Using EmbeddingGeneratorNode

```python
# CORRECT: Use EmbeddingGeneratorNode for embeddings
from kailash.nodes.ai import EmbeddingGeneratorNode

embedder = EmbeddingGeneratorNode(
    name="text_embedder",
    model="text-embedding-3-small",
    dimensions=1536
)

parameters = {
    "text_embedder": {
        "texts": ["Document 1 content", "Document 2 content"],
        "batch_size": 100
    }
}
```

## WRONG: Manual Embedding Generation

```python
# WRONG: Don't call embedding APIs manually
embedder = PythonCodeNode(
    name="embedder",
    code="""
import openai
embeddings = []
for text in texts:
    response = openai.Embedding.create(
        model="text-embedding-ada-002",
        input=text
    )
    embeddings.append(response['data'][0]['embedding'])
result = {"embeddings": embeddings}
"""
)
```

## CORRECT: Document Chunking with ChunkerNode

```python
# CORRECT: Use ChunkerNode for intelligent chunking
from kailash.nodes.transform import ChunkerNode

chunker = ChunkerNode(name="doc_chunker")

parameters = {
    "doc_chunker": {
        "chunk_size": 500,
        "chunk_overlap": 50,
        "chunking_strategy": "semantic",  # or "fixed", "sentence"
        "preserve_structure": True,
        "metadata_fields": ["title", "section", "page"]
    }
}
```

## WRONG: Manual Chunking Logic

```python
# WRONG: Don't implement chunking manually
chunker = PythonCodeNode(
    name="chunker",
    code="""
chunks = []
for doc in documents:
    text = doc['content']
    # Simple fixed-size chunking
    for i in range(0, len(text), 500):
        chunk = {
            'text': text[i:i+500],
            'doc_id': doc['id'],
            'position': i
        }
        chunks.append(chunk)
result = {"chunks": chunks}
"""
)

# Problems:
# 1. No overlap handling
# 2. Breaks words/sentences
# 3. No semantic awareness
# 4. Missing metadata
```

## CORRECT: RAG with RelevanceScorerNode

```python
# CORRECT: Use RelevanceScorerNode for similarity search
from kailash.nodes.data import RelevanceScorerNode

scorer = RelevanceScorerNode(name="relevance_scorer")

parameters = {
    "relevance_scorer": {
        "similarity_method": "cosine",  # or "bm25", "tfidf"
        "top_k": 5,
        "score_threshold": 0.7,
        "rerank": True
    }
}
```

## WRONG: Manual Similarity Calculation

```python
# WRONG: Don't implement similarity search manually
scorer = PythonCodeNode(
    name="scorer",
    code="""
import numpy as np

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

scores = []
for chunk, chunk_emb in zip(chunks, chunk_embeddings):
    score = cosine_similarity(query_embedding, chunk_emb)
    scores.append((chunk, score))

scores.sort(key=lambda x: x[1], reverse=True)
result = {"relevant_chunks": [s[0] for s in scores[:5]]}
"""
)
```

## CORRECT: Multi-Agent Coordination

```python
# CORRECT: Chain multiple LLM agents with specific roles
workflow = Workflow(name="multi_agent_system")

# Research agent
researcher = LLMAgentNode(
    name="researcher",
    model="gpt-4",
    system_prompt="You are a research assistant. Find relevant information."
)
workflow.add_node(researcher)

# Analysis agent  
analyst = LLMAgentNode(
    name="analyst",
    model="gpt-4",
    system_prompt="You are a data analyst. Analyze the research findings."
)
workflow.add_node(analyst)

# Writer agent
writer = LLMAgentNode(
    name="writer",
    model="gpt-3.5-turbo",
    system_prompt="You are a technical writer. Create clear documentation."
)
workflow.add_node(writer)

# Connect agents
workflow.connect(researcher.id, analyst.id, mapping={"response": "research"})
workflow.connect(analyst.id, writer.id, mapping={"response": "analysis"})
```

## WRONG: Single Monolithic LLM Call

```python
# WRONG: Don't try to do everything in one LLM call
do_everything = PythonCodeNode(
    name="do_all",
    code="""
prompt = f'''
Research this topic: {topic}
Then analyze the findings.
Then write a report.
Format it nicely.
Include citations.
Make it professional.
'''
response = call_llm(prompt)
result = {"report": response}
"""
)

# Problems:
# 1. Too much for one prompt
# 2. No specialization
# 3. Hard to debug/improve
# 4. Poor output quality
```

## CORRECT: Structured Output with JSON Mode

```python
# CORRECT: Use LLMAgentNode with structured outputs
json_extractor = LLMAgentNode(
    name="json_extractor",
    model="gpt-4-turbo",
    system_prompt="Extract structured data as JSON"
)

parameters = {
    "json_extractor": {
        "prompt": "Extract key information as JSON with fields: name, date, amount, category",
        "response_format": {"type": "json_object"},
        "temperature": 0.1  # Low temperature for consistency
    }
}
```

## Complete RAG Pipeline Example

```python
# CORRECT: Complete RAG pipeline with proper nodes
from kailash import Workflow
from kailash.nodes.data import DocumentSourceNode, QuerySourceNode, RelevanceScorerNode
from kailash.nodes.transform import ChunkerNode
from kailash.nodes.ai import EmbeddingGeneratorNode, LLMAgentNode
from kailash.runtime import AsyncLocalRuntime

async def create_rag_pipeline():
    workflow = Workflow(name="rag_system")
    
    # Document processing
    docs = DocumentSourceNode(name="documents")
    workflow.add_node(docs)
    
    chunker = ChunkerNode(name="chunker")
    workflow.add_node(chunker)
    workflow.connect(docs.id, chunker.id, mapping={"documents": "documents"})
    
    # Embeddings
    doc_embedder = EmbeddingGeneratorNode(name="doc_embedder")
    workflow.add_node(doc_embedder)
    workflow.connect(chunker.id, doc_embedder.id, mapping={"chunks": "texts"})
    
    # Query processing
    query = QuerySourceNode(name="query")
    workflow.add_node(query)
    
    query_embedder = EmbeddingGeneratorNode(name="query_embedder")
    workflow.add_node(query_embedder)
    workflow.connect(query.id, query_embedder.id, mapping={"query": "texts"})
    
    # Relevance scoring
    scorer = RelevanceScorerNode(name="scorer")
    workflow.add_node(scorer)
    workflow.connect(chunker.id, scorer.id, mapping={"chunks": "chunks"})
    workflow.connect(query_embedder.id, scorer.id, mapping={"embeddings": "query_embedding"})
    workflow.connect(doc_embedder.id, scorer.id, mapping={"embeddings": "chunk_embeddings"})
    
    # Answer generation
    answerer = LLMAgentNode(
        name="answerer",
        model="gpt-4",
        system_prompt="Answer based on context. Cite sources."
    )
    workflow.add_node(answerer)
    workflow.connect(scorer.id, answerer.id, mapping={"relevant_chunks": "context"})
    workflow.connect(query.id, answerer.id, mapping={"query": "question"})
    
    # Execute
    runtime = AsyncLocalRuntime()
    result = await runtime.execute(workflow, parameters={
        "chunker": {"chunk_size": 500, "overlap": 50},
        "scorer": {"top_k": 5, "similarity_method": "cosine"},
        "answerer": {
            "prompt": "Question: {{question}}\n\nContext: {{context}}\n\nAnswer:",
            "temperature": 0.7
        }
    })
    
    return result
```

## Key Principles for LLM Workflows

1. **Use Specialized AI Nodes**: LLMAgentNode, EmbeddingGeneratorNode, etc.
2. **Avoid Manual API Calls**: Nodes handle auth, retry, errors
3. **Chain Agents**: Break complex tasks into specialized agents
4. **Structured Outputs**: Use response_format for JSON
5. **Proper Chunking**: Use ChunkerNode with semantic strategies
6. **Relevance Scoring**: Use RelevanceScorerNode for retrieval
7. **Async Execution**: Use AsyncLocalRuntime for LLM workflows