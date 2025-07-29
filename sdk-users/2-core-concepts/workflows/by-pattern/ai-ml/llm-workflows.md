# LLM Workflow Patterns

**Complete guide to Large Language Model integration** - From simple text generation to complex RAG systems using native Kailash nodes.

## 📋 Pattern Overview

LLM workflows enable:
- **Document Q&A**: RAG-based question answering with embedding search
- **Text Generation**: Content creation with proper AI nodes
- **Multi-Agent Systems**: Coordinated AI reasoning chains
- **Content Processing**: Document chunking, embedding, and retrieval
- **Production Deployment**: Scalable AI workflows with MCP integration

## 🚀 Quick Start Examples

### 30-Second Document Q&A (RAG Pattern)
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.ai import LLMAgentNode, EmbeddingGeneratorNode
from kailash.nodes.data import DocumentSourceNode, QuerySourceNode, RelevanceScorerNode
from kailash.nodes.transform import HierarchicalChunkerNode
from kailash.runtime.local import LocalRuntime

# Document Q&A workflow using proper Kailash nodes
workflow = WorkflowBuilder()

# Document and query sources
doc_source = DocumentSourceNode(id="docs")
query_source = QuerySourceNode(id="query")
workflow.add_node("docs", doc_source)
workflow.add_node("query", query_source)

# Intelligent document chunking
chunker = HierarchicalChunkerNode(id="chunker")
workflow.add_node("chunker", chunker)
workflow.add_connection("docs", "chunker", "documents", "documents")

# Generate embeddings for search
embedder = EmbeddingGeneratorNode(
    id="embedder",
    model="text-embedding-3-small"
)
workflow.add_node("embedder", embedder)
workflow.add_connection("chunker", "embedder", "chunks", "texts")

# Find relevant content
scorer = RelevanceScorerNode(id="scorer")
workflow.add_node("scorer", scorer)
workflow.add_connection("chunker", "scorer", "chunks", "chunks")
workflow.add_connection("embedder", "scorer", "embeddings", "embeddings")

# Generate answers with LLM
llm = LLMAgentNode(
    id="answer_gen",
    model="gpt-3.5-turbo",
    system_prompt="Answer based on provided context only."
)
workflow.add_node("answer_gen", llm)
workflow.add_connection("scorer", "answer_gen", "relevant_chunks", "context")
workflow.add_connection("query", "answer_gen", "query", "question")

# Execute the workflow
runtime = LocalRuntime()
result, run_id = runtime.execute(workflow, parameters={
    "query": {"query": "What are the main types of machine learning?"},
    "chunker": {"chunk_size": 500, "chunk_overlap": 50},
    "scorer": {"top_k": 3, "similarity_method": "cosine"}
})

```

## 🔬 Advanced LLM Patterns

### Local LLM Integration with Ollama (v0.6.2+)

Run powerful LLMs locally with enhanced Ollama support:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.ai import LLMAgentNode
from kailash.runtime.local import LocalRuntime

# Local LLM workflow with Ollama
workflow = WorkflowBuilder()

# Basic Ollama usage with async support
ollama_node = LLMAgentNode(
    id="local_llm",
    provider="ollama",
    model="llama3.2:3b"
)
workflow.add_node("llm", ollama_node)

# Execute with improved error handling
runtime = LocalRuntime()
result, run_id = await runtime.execute_async(workflow, parameters={
    "llm": {
        "prompt": "Explain the benefits of edge computing",
        "generation_config": {
            "temperature": 0.7,
            "max_tokens": 300
        }
    }
})

# Remote Ollama server configuration
remote_ollama = LLMAgentNode(
    id="remote_llm",
    provider="ollama",
    model="mixtral:8x7b"
)
workflow.add_node("remote_llm", remote_ollama)

# Execute with custom backend
result, run_id = await runtime.execute_async(workflow, parameters={
    "remote_llm": {
        "prompt": "Analyze this technical architecture",
        "backend_config": {
            "host": "gpu-cluster.internal",
            "port": 11434
        },
        "generation_config": {
            "temperature": 0.3,
            "max_tokens": 1000
        }
    }
})
```

### Multi-Agent Reasoning Chain
```python
from kailash.nodes.ai import IterativeLLMAgentNode

# Multi-agent reasoning using specialized LLM nodes
workflow = WorkflowBuilder()

# Research agent with MCP tool access
researcher = IterativeLLMAgentNode(
    id="researcher",
    model="gpt-4",
    system_prompt="You are a research specialist. Use available tools to gather comprehensive information."
)
workflow.add_node("researcher", researcher)

# Analysis agent
analyzer = LLMAgentNode(
    id="analyzer",
    model="gpt-4",
    system_prompt="You are an analytical expert. Apply frameworks to understand patterns."
)
workflow.add_node("analyzer", analyzer)

# Synthesis agent
synthesizer = LLMAgentNode(
    id="synthesizer",
    model="gpt-4",
    system_prompt="You are a synthesis expert. Combine insights into actionable conclusions."
)
workflow.add_node("synthesizer", synthesizer)

# Chain the reasoning steps
workflow.add_connection("researcher", "analyzer", "final_response", "research_context")
workflow.add_connection("analyzer", "synthesizer", "response", "analysis_context")

# Execute with MCP integration for real tool access
runtime = LocalRuntime()
result, run_id = runtime.execute(workflow, parameters={
    "researcher": {
        "messages": [{"role": "user", "content": "Research remote work productivity trends"}],
        "mcp_servers": [{
            "name": "ai-registry",
            "command": "python",
            "args": ["scripts/start-ai-registry-server.py"]
        }],
        "auto_discover_tools": True,
        "max_iterations": 3
    },
    "analyzer": {
        "messages": [{"role": "user", "content": "Analyze the research findings"}],
        "temperature": 0.3
    },
    "synthesizer": {
        "messages": [{"role": "user", "content": "Synthesize insights into recommendations"}],
        "temperature": 0.5
    }
})

```

### Enterprise RAG System with Advanced Document Processing
```python
from kailash.nodes.data import VectorDBNode, DatabaseReaderNode, DocumentLoaderNode
from kailash.nodes.logic import SwitchNode, MergeNode, LoopNode
from kailash.nodes.transform import FilterNode

# Enterprise-grade RAG system
enterprise_rag = Workflow(
    workflow_id="enterprise_rag_001",
    name="enterprise_document_qa_system",
    description="Production RAG with advanced document processing"
)

# Multi-source document loading
document_loader = DocumentLoaderNode(
    id="doc_loader",
    supported_formats=["pdf", "docx", "txt", "html", "markdown"],
    batch_size=50,
    parallel_processing=True
)
enterprise_rag.add_node("doc_loader", document_loader)

# Intelligent document preprocessing
doc_preprocessor = DataTransformer(
    id="doc_preprocessor",
    transformations=[
        """
# Advanced document preprocessing
import re
from datetime import datetime

processed_docs = []
for doc in data.get("documents", []):
    # Extract metadata
    metadata = {
        "file_name": doc.get("file_name", ""),
        "file_type": doc.get("file_type", ""),
        "file_size": doc.get("file_size", 0),
        "creation_date": doc.get("creation_date", ""),
        "last_modified": doc.get("last_modified", ""),
        "author": doc.get("author", ""),
        "language": doc.get("language", "en"),
        "processing_timestamp": datetime.now().isoformat()
    }

    # Clean and normalize text
    content = doc.get("content", "")

    # Remove excessive whitespace
    content = re.sub(r'\s+', ' ', content)

    # Remove special characters but preserve structure
    content = re.sub(r'[^\w\s\.\,\!\?\;\:\-\(\)\[\]\{\}\"\'\/\\n\\t]', '', content)

    # Normalize line breaks
    content = re.sub(r'\n\s*\n', '\n\n', content)

    # Extract sections and headings
    sections = []
    current_section = {"title": "", "content": "", "level": 0}

    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Detect headings (simple heuristic)
        if (line.isupper() and len(line) < 100) or \
           (line.startswith('#') or re.match(r'^\d+\.', line)):
            # Save previous section
            if current_section["content"]:
                sections.append(dict(current_section))

            # Start new section
            current_section = {
                "title": line,
                "content": "",
                "level": len(re.findall(r'^#+', line)) if line.startswith('#') else 1
            }
        else:
            current_section["content"] += line + " "

    # Add final section
    if current_section["content"]:
        sections.append(dict(current_section))

    # Calculate document statistics
    stats = {
        "total_chars": len(content),
        "total_words": len(content.split()),
        "total_sentences": len(re.findall(r'[.!?]+', content)),
        "total_paragraphs": len([p for p in content.split('\n\n') if p.strip()]),
        "total_sections": len(sections),
        "avg_section_length": sum(len(s["content"]) for s in sections) / len(sections) if sections else 0
    }

    # Quality assessment
    quality_score = 1.0
    quality_issues = []

    if stats["total_words"] < 10:
        quality_score *= 0.3
        quality_issues.append("Very short document")

    if stats["total_words"] > 50000:
        quality_issues.append("Very long document - consider splitting")

    if len(re.findall(r'[^\x00-\x7F]', content)) > stats["total_chars"] * 0.1:
        quality_issues.append("High non-ASCII character ratio")

    processed_doc = {
        "id": doc.get("id", ""),
        "metadata": metadata,
        "content": content,
        "sections": sections,
        "statistics": stats,
        "quality": {
            "score": quality_score,
            "issues": quality_issues
        },
        "processing_status": "completed"
    }

    processed_docs.append(processed_doc)

result = {
    "documents": processed_docs,
    "total_processed": len(processed_docs),
    "processing_summary": {
        "avg_quality_score": sum(d["quality"]["score"] for d in processed_docs) / len(processed_docs) if processed_docs else 0,
        "total_words": sum(d["statistics"]["total_words"] for d in processed_docs),
        "total_sections": sum(d["statistics"]["total_sections"] for d in processed_docs)
    }
}
"""
    ]
)
enterprise_rag.add_node("doc_preprocessor", doc_preprocessor)

# Hierarchical chunking with overlap optimization
advanced_chunker = HierarchicalChunkerNode(
    id="advanced_chunker",
    chunking_strategy="semantic",  # semantic, sentence, paragraph, or fixed
    chunk_size=512,
    chunk_overlap=64,
    preserve_structure=True,
    min_chunk_size=50,
    max_chunk_size=1024
)
enterprise_rag.add_node("advanced_chunker", advanced_chunker)

# Multi-model embedding generation
primary_embedder = EmbeddingGeneratorNode(
    id="primary_embedder",
    model="text-embedding-3-large",
    dimensions=3072,
    batch_size=100
)
enterprise_rag.add_node("primary_embedder", primary_embedder)

# Secondary embedder for comparison/diversity
secondary_embedder = EmbeddingGeneratorNode(
    id="secondary_embedder",
    model="text-embedding-ada-002",
    dimensions=1536,
    batch_size=100
)
enterprise_rag.add_node("secondary_embedder", secondary_embedder)

# Vector database storage
vector_db = VectorDBNode(
    id="vector_store",
    db_type="pinecone",  # pinecone, weaviate, chroma, or faiss
    index_name="enterprise-docs",
    embedding_dimension=3072,
    similarity_metric="cosine"
)
enterprise_rag.add_node("vector_store", vector_db)

# Query processing and intent detection
query_processor = DataTransformer(
    id="query_processor",
    transformations=[
        """
# Advanced query processing and intent detection

query_text = data.get("query", "")
if not query_text:
    result = {"error": "No query provided"}
else:
    # Query analysis
    query_analysis = {
        "original_query": query_text,
        "processed_query": query_text.strip().lower(),
        "query_length": len(query_text),
        "word_count": len(query_text.split()),
        "processing_timestamp": datetime.now().isoformat()
    }

    # Intent detection (simple rule-based)
    intent_patterns = {
        "factual": [r"\bwhat\b", r"\bwho\b", r"\bwhen\b", r"\bwhere\b", r"\bdefine\b"],
        "procedural": [r"\bhow\b", r"\bsteps\b", r"\bprocess\b", r"\bmethod\b"],
        "comparative": [r"\bcompare\b", r"\bdifference\b", r"\bvs\b", r"\bbetter\b"],
        "analytical": [r"\bwhy\b", r"\banalyze\b", r"\bexplain\b", r"\breason\b"],
        "summary": [r"\bsummarize\b", r"\boverview\b", r"\bmain points\b"],
        "recommendation": [r"\brecommend\b", r"\badvice\b", r"\bsuggest\b", r"\bbest\b"]
    }

    detected_intents = []
    intent_confidence = {}

    for intent, patterns in intent_patterns.items():
        matches = sum(1 for pattern in patterns if re.search(pattern, query_text.lower()))
        if matches > 0:
            detected_intents.append(intent)
            intent_confidence[intent] = matches / len(patterns)

    primary_intent = max(intent_confidence.items(), key=lambda x: x[1])[0] if intent_confidence else "general"

    # Query expansion for better retrieval
    expanded_terms = []

    # Add synonyms (simplified)
    synonym_map = {
        "fast": ["quick", "rapid", "speedy"],
        "slow": ["sluggish", "gradual", "delayed"],
        "big": ["large", "huge", "massive"],
        "small": ["tiny", "little", "compact"],
        "good": ["excellent", "great", "beneficial"],
        "bad": ["poor", "terrible", "harmful"]
    }

    query_words = query_text.lower().split()
    for word in query_words:
        if word in synonym_map:
            expanded_terms.extend(synonym_map[word])

    # Generate search parameters based on intent
    search_params = {
        "similarity_threshold": 0.7,
        "top_k": 5,
        "rerank": True,
        "include_metadata": True
    }

    # Adjust parameters based on intent
    if primary_intent == "factual":
        search_params["similarity_threshold"] = 0.8
        search_params["top_k"] = 3
    elif primary_intent == "summary":
        search_params["top_k"] = 10
        search_params["similarity_threshold"] = 0.6
    elif primary_intent == "comparative":
        search_params["top_k"] = 8
        search_params["diversity_penalty"] = 0.2

    result = {
        "query_analysis": query_analysis,
        "primary_intent": primary_intent,
        "detected_intents": detected_intents,
        "intent_confidence": intent_confidence,
        "expanded_terms": expanded_terms,
        "search_params": search_params,
        "processed_query": query_text + " " + " ".join(expanded_terms) if expanded_terms else query_text
    }
"""
    ]
)
enterprise_rag.add_node("query_processor", query_processor)

# Enhanced relevance scoring with multiple signals
enhanced_scorer = DataTransformer(
    id="enhanced_scorer",
    transformations=[
        """
# Multi-signal relevance scoring
from datetime import datetime
import math

chunks = data.get("chunks", [])
query_info = data.get("query_info", {})
primary_intent = query_info.get("primary_intent", "general")

scored_chunks = []
for chunk in chunks:
    base_score = chunk.get("similarity_score", 0.0)

    # Content quality signals
    content = chunk.get("content", "")
    content_quality = 1.0

    # Length penalty/bonus
    content_length = len(content)
    if content_length < 50:
        content_quality *= 0.8  # Too short
    elif content_length > 1000:
        content_quality *= 0.9  # Too long
    else:
        content_quality *= 1.1  # Good length

    # Structure signals
    has_headers = bool(re.search(r'^[A-Z][^.]*:|\n#+\s', content))
    has_lists = bool(re.search(r'\n\s*[-\*\d+\.]\s', content))
    has_formatting = has_headers or has_lists

    if has_formatting:
        content_quality *= 1.1

    # Metadata signals
    metadata = chunk.get("metadata", {})
    doc_quality = metadata.get("quality_score", 1.0)

    # Recency bonus (if timestamp available)
    recency_score = 1.0
    if "last_modified" in metadata:
        try:
            modified_date = datetime.fromisoformat(metadata["last_modified"])
            days_old = (datetime.now() - modified_date).days
            recency_score = max(0.5, 1.0 - (days_old / 365.0))  # Decay over a year
        except:
            pass

    # Intent-based scoring adjustments
    intent_bonus = 1.0
    if primary_intent == "factual" and re.search(r'\b(is|are|definition|means)\b', content.lower()):
        intent_bonus = 1.2
    elif primary_intent == "procedural" and re.search(r'\b(step|steps|first|then|next|finally)\b', content.lower()):
        intent_bonus = 1.2
    elif primary_intent == "comparative" and re.search(r'\b(compare|versus|difference|better|worse)\b', content.lower()):
        intent_bonus = 1.2

    # Calculate final score
    final_score = base_score * content_quality * doc_quality * recency_score * intent_bonus

    scored_chunk = dict(chunk)
    scored_chunk.update({
        "final_score": final_score,
        "scoring_breakdown": {
            "base_similarity": base_score,
            "content_quality": content_quality,
            "document_quality": doc_quality,
            "recency_score": recency_score,
            "intent_bonus": intent_bonus
        }
    })

    scored_chunks.append(scored_chunk)

# Sort by final score and apply diversity
scored_chunks.sort(key=lambda x: x["final_score"], reverse=True)

# Diversity filtering to avoid redundant content
diverse_chunks = []
seen_content_hashes = set()

for chunk in scored_chunks:
    content = chunk.get("content", "")
    # Simple content hash for diversity
    content_hash = hash(content[:100])  # First 100 chars

    if content_hash not in seen_content_hashes:
        diverse_chunks.append(chunk)
        seen_content_hashes.add(content_hash)

        if len(diverse_chunks) >= query_info.get("search_params", {}).get("top_k", 5):
            break

result = {
    "relevant_chunks": diverse_chunks,
    "total_scored": len(scored_chunks),
    "total_returned": len(diverse_chunks),
    "scoring_metadata": {
        "primary_intent": primary_intent,
        "diversity_applied": len(scored_chunks) != len(diverse_chunks),
        "avg_score": sum(c["final_score"] for c in diverse_chunks) / len(diverse_chunks) if diverse_chunks else 0
    }
}
"""
    ]
)
enterprise_rag.add_node("enhanced_scorer", enhanced_scorer)

# Multi-model answer generation with validation
answer_generator = LLMAgentNode(
    id="answer_generator",
    model="gpt-4-turbo",
    system_prompt="""You are an expert assistant providing accurate, well-sourced answers based on provided context.

Guidelines:
1. Answer questions directly and comprehensively
2. Use only information from the provided context
3. Cite specific sections when making claims
4. If information is insufficient, clearly state limitations
5. Structure your response with clear sections for complex queries
6. Provide confidence levels for key statements
7. Include relevant metadata when available""",
    temperature=0.2,
    max_tokens=1000
)
enterprise_rag.add_node("answer_generator", answer_generator)

# Answer validation and quality assessment
answer_validator = DataTransformer(
    id="answer_validator",
    transformations=[
        """
# Validate and assess answer quality

answer = data.get("answer", "")
context_chunks = data.get("context_chunks", [])
query_info = data.get("query_info", {})

validation_result = {
    "answer": answer,
    "validation_timestamp": datetime.now().isoformat(),
    "quality_metrics": {},
    "citations": [],
    "issues": [],
    "recommendations": []
}

# Basic quality metrics
quality_metrics = {
    "length": len(answer),
    "word_count": len(answer.split()),
    "sentence_count": len(re.findall(r'[.!?]+', answer)),
    "paragraph_count": len([p for p in answer.split('\n\n') if p.strip()])
}

# Citation detection
citation_patterns = [
    r'according to.*?section',
    r'as mentioned in.*?document',
    r'based on.*?source',
    r'from.*?chapter',
    r'\[.*?\]',  # Bracket citations
    r'\(.*?\)'   # Parenthetical citations
]

citations_found = []
for pattern in citation_patterns:
    matches = re.findall(pattern, answer.lower())
    citations_found.extend(matches)

quality_metrics["citation_count"] = len(citations_found)
validation_result["citations"] = citations_found

# Content validation against context
context_terms = set()
for chunk in context_chunks:
    content = chunk.get("content", "").lower()
    # Extract key terms (simplified)
    terms = re.findall(r'\b[a-z]{4,}\b', content)
    context_terms.update(terms[:50])  # Limit to avoid memory issues

answer_terms = set(re.findall(r'\b[a-z]{4,}\b', answer.lower()))
term_overlap = len(answer_terms.intersection(context_terms))
term_coverage = term_overlap / len(answer_terms) if answer_terms else 0

quality_metrics["context_alignment"] = term_coverage

# Answer completeness assessment
query_words = query_info.get("query_analysis", {}).get("processed_query", "").split()
query_terms_in_answer = sum(1 for word in query_words if word.lower() in answer.lower())
query_coverage = query_terms_in_answer / len(query_words) if query_words else 0

quality_metrics["query_coverage"] = query_coverage

# Issue detection
if quality_metrics["length"] < 50:
    validation_result["issues"].append("Answer may be too brief")

if quality_metrics["citation_count"] == 0:
    validation_result["issues"].append("No citations found in answer")

if term_coverage < 0.3:
    validation_result["issues"].append("Low alignment with provided context")

if query_coverage < 0.5:
    validation_result["issues"].append("Answer may not fully address the query")

# Overall quality score
quality_score = (
    min(quality_metrics["length"] / 200, 1.0) * 0.2 +  # Length normalized
    min(quality_metrics["citation_count"] / 3, 1.0) * 0.3 +  # Citations
    term_coverage * 0.3 +  # Context alignment
    query_coverage * 0.2   # Query coverage
)

quality_metrics["overall_score"] = quality_score

# Recommendations
if quality_score < 0.6:
    validation_result["recommendations"].append("Consider regenerating answer with more specific prompts")

if quality_metrics["citation_count"] < 2:
    validation_result["recommendations"].append("Add more specific citations to improve credibility")

validation_result["quality_metrics"] = quality_metrics

result = validation_result
"""
    ]
)
enterprise_rag.add_node("answer_validator", answer_validator)

# Connect the enterprise RAG workflow
enterprise_rag.connect("doc_loader", "doc_preprocessor", # mapping removed)
enterprise_rag.connect("doc_preprocessor", "advanced_chunker", # mapping removed)
enterprise_rag.connect("advanced_chunker", "primary_embedder", # mapping removed)
enterprise_rag.connect("advanced_chunker", "secondary_embedder", # mapping removed)
enterprise_rag.connect("primary_embedder", "vector_store", # mapping removed)

# Query processing branch
enterprise_rag.connect("query_processor", "enhanced_scorer", # mapping removed)
enterprise_rag.connect("enhanced_scorer", "answer_generator", # mapping removed)
enterprise_rag.connect("answer_generator", "answer_validator", # mapping removed)

```

### Simple Content Processing (when specialized nodes don't exist)
```python
from kailash.nodes.transform import DataTransformer

# Only use DataTransformer for simple transformations
content_processor = DataTransformer(
    id="processor",
    transformations=[
        """
# Simple content enhancement
enhanced_content = {
    "original": data.get("content", ""),
    "word_count": len(data.get("content", "").split()),
    "summary": data.get("content", "")[:200] + "..." if len(data.get("content", "")) > 200 else data.get("content", ""),
    "processed_at": "2024-01-01T00:00:00Z"
}
result = enhanced_content
"""
    ]
)

```

## 📝 Content Generation with LLM Nodes

### Automated Report Generation
```python
from kailash.nodes.data import JSONWriterNode

workflow = WorkflowBuilder()

# Data preparation (use DataTransformer only for data prep)
data_prep = DataTransformer(
    id="data_prep",
    transformations=[
        """
# Prepare data for LLM processing
report_data = {
    "metrics": data.get("metrics", {}),
    "period": "2024-Q1",
    "summary_stats": {
        "total_records": len(data.get("raw_data", [])),
        "key_metrics": data.get("key_metrics", {})
    }
}
result = report_data
"""
    ]
)
workflow.add_node("data_prep", data_prep)

# Use LLM for actual report generation
report_generator = LLMAgentNode(
    id="report_gen",
    model="gpt-4",
    system_prompt="Generate comprehensive business reports based on provided data."
)
workflow.add_node("report_gen", report_generator)
workflow.add_connection("data_prep", "report_gen", "result", "report_data")

# Save the generated report
writer = JSONWriterNode(
    id="writer",
    file_path="reports/generated_report.json"
)
workflow.add_node("writer", writer)
workflow.add_connection("report_gen", "writer", "response", "data")

```

## 🎨 Multi-Modal Content Creation

### Content Adaptation Pipeline
```python
# Content generation with LLM
content_generator = LLMAgentNode(
    id="generator",
    model="gpt-3.5-turbo",
    system_prompt="Create engaging content for multiple platforms."
)

# Platform adaptation (simple transformation)
platform_adapter = DataTransformer(
    id="adapter",
    transformations=[
        """
# Adapt content for different platforms
content = data.get("content", "")
adaptations = {}

# Social media (truncate to 280 chars)
if len(content) > 280:
    adaptations["social"] = content[:277] + "..."
else:
    adaptations["social"] = content

# Email (add structure)
adaptations["email"] = f"Subject: Content Update\\n\\n{content}\\n\\nBest regards,\\nAI Team"

# Blog (add metadata)
adaptations["blog"] = {
    "title": "Generated Content",
    "content": content,
    "word_count": len(content.split())
}

result = adaptations
"""
    ]
)

workflow.add_connection("generator", "adapter", "response", "data")

```

## 🔗 LLM Best Practices

### Performance Optimization
- **Use Specialized Nodes**: Prefer `LLMAgentNode`, `EmbeddingGeneratorNode`, `HierarchicalChunkerNode`
- **Temperature Control**: Use 0.1-0.3 for factual content, 0.7-0.9 for creative content
- **Proper Connections**: Map outputs correctly (`{"response": "data"}`, `{"chunks": "texts"}`)
- **MCP Integration**: Use `IterativeLLMAgentNode` for tool access

### Quality Assurance
- **Prompt Engineering**: Use clear system prompts with specific instructions
- **Output Validation**: Check response structure before downstream processing
- **Error Handling**: Handle missing or malformed LLM responses gracefully
- **Context Management**: Use proper chunking for long documents

### Production Deployment
- **Rate Limiting**: Built into `LLMAgentNode` and `EmbeddingGeneratorNode`
- **Error Recovery**: Nodes handle API failures automatically
- **Monitoring**: Track token usage through workflow execution logs
- **Cost Management**: Use appropriate models for different tasks

## ⚠️ Common Mistakes to Avoid

### Don't Use PythonCodeNode for LLM Operations
```python
# WRONG: Manual LLM API calls
llm_node = PythonCodeNode(
    code="response = openai.chat.completions.create(...); result = response"
)

# CORRECT: Use LLMAgentNode
llm_node = LLMAgentNode(
    model="gpt-3.5-turbo",
    system_prompt="Your instructions here"
)

```

### Don't Implement Embedding Generation Manually
```python
# WRONG: Manual embedding calls
embed_node = PythonCodeNode(
    code="embeddings = openai.embeddings.create(...); result = embeddings"
)

# CORRECT: Use EmbeddingGeneratorNode
embed_node = EmbeddingGeneratorNode(
    model="text-embedding-3-small"
)

```

### Don't Implement Document Chunking Manually
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

# WRONG: Manual text splitting
chunk_node = PythonCodeNode(
    code="chunks = text.split('\\n\\n'); result = chunks"
)

# CORRECT: Use HierarchicalChunkerNode
chunk_node = HierarchicalChunkerNode(
    chunk_size=500,
    chunk_overlap=50
)

```

---

*These LLM workflow patterns use the correct Kailash nodes for maximum efficiency and maintainability. Always prefer specialized AI nodes over manual implementations.*
