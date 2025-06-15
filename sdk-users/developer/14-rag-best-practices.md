# RAG Best Practices

## Overview

Essential best practices for implementing production-ready RAG systems with Kailash SDK's advanced chunking and retrieval nodes.

## Quick Reference

### ✅ DO: Choose Strategy Based on Content

| Content Type | Strategy | Key Parameters |
|--------------|----------|----------------|
| Technical docs | Statistical | `variance_threshold=0.6` |
| Research papers | Statistical | `variance_threshold=0.7` |
| Narrative text | Semantic | `similarity_threshold=0.75` |
| News articles | Semantic | `similarity_threshold=0.8` |
| Legal docs | Statistical | `max_sentences=10` |

### ✅ DO: Use Recommended Defaults

```python
# Semantic chunking (general content)
semantic_chunker = SemanticChunkerNode(
    chunk_size=1000,           # Good balance for most LLMs
    similarity_threshold=0.75,  # Balanced topic coherence
    chunk_overlap=100,         # 10% overlap for context
    window_size=3              # Adequate context window
)

# Statistical chunking (structured content)
statistical_chunker = StatisticalChunkerNode(
    chunk_size=1000,
    variance_threshold=0.5,     # Moderate sensitivity
    min_sentences_per_chunk=3,  # Minimum coherent unit
    max_sentences_per_chunk=15, # Prevent overly large chunks
)

# Hybrid retrieval (production standard)
hybrid_retriever = HybridRetrieverNode(
    fusion_strategy="rrf",      # Gold standard
    top_k=5,                   # Standard for most apps
    rrf_k=60                   # Balanced fusion
)
```

### ✅ DO: Test Both Strategies

```python
def choose_best_strategy(document: str, test_queries: List[str]):
    """Always compare strategies with your specific content."""

    semantic = SemanticChunkerNode(chunk_size=1000)
    statistical = StatisticalChunkerNode(chunk_size=1000)

    sem_result = semantic.run(text=document)
    stat_result = statistical.run(text=document)

    # Evaluate with your queries
    sem_quality = evaluate_chunks(sem_result["chunks"], test_queries)
    stat_quality = evaluate_chunks(stat_result["chunks"], test_queries)

    return "semantic" if sem_quality > stat_quality else "statistical"
```

## Common Mistakes

### ❌ DON'T: Use Fixed-Size Chunking

```python
# ❌ WRONG: Breaks sentences, loses context
chunks = [text[i:i+1000] for i in range(0, len(text), 1000)]

# ✅ RIGHT: Intelligent chunking
chunker = SemanticChunkerNode(chunk_size=1000)
result = chunker.run(text=text)
chunks = result["chunks"]
```

### ❌ DON'T: Ignore Content Type

```python
# ❌ WRONG: Same strategy for everything
universal_chunker = SemanticChunkerNode()

# ✅ RIGHT: Content-aware strategy
if content_type == "technical":
    chunker = StatisticalChunkerNode(variance_threshold=0.6)
else:
    chunker = SemanticChunkerNode(similarity_threshold=0.75)
```

### ❌ DON'T: Skip Quality Checks

```python
# ❌ WRONG: No validation
chunks = chunker.run(text=text)["chunks"]
# Use chunks without checking quality

# ✅ RIGHT: Quality validation
chunks = chunker.run(text=text)["chunks"]

# Validate chunk quality
if not chunks:
    raise ValueError("No chunks generated")

avg_size = sum(len(c["content"]) for c in chunks) / len(chunks)
if avg_size < 100:
    print("Warning: Very small chunks detected")
```

## Performance Optimization

### Caching

```python
# Cache expensive operations
@functools.lru_cache(maxsize=1000)
def get_cached_chunks(text_hash: str, strategy: str):
    """Cache chunking results."""
    if strategy == "semantic":
        chunker = SemanticChunkerNode()
    else:
        chunker = StatisticalChunkerNode()
    return chunker.run(text=text)
```

### Batch Processing

```python
# Process documents in batches
def batch_process(documents: List[Dict], batch_size: int = 50):
    """Efficient batch processing."""
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        # Process batch together
        batch_texts = [doc["content"] for doc in batch]
        # Use batch embedding generation
        embeddings = embedder.run(operation="embed_batch", input_texts=batch_texts)
```

### Memory Management

```python
# Monitor memory usage
def process_with_memory_limit(documents: List[Dict], max_memory_mb: int = 1000):
    """Process with memory monitoring."""
    import psutil

    processed = []
    for doc in documents:
        # Check memory before processing
        memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
        if memory_mb > max_memory_mb:
            # Clear caches or process in smaller batches
            gc.collect()

        result = chunker.run(text=doc["content"])
        processed.extend(result["chunks"])

    return processed
```

## Error Handling

### Graceful Degradation

```python
class RobustRAGPipeline:
    def safe_chunking(self, text: str, strategy: str = "semantic"):
        """Chunking with fallback strategies."""
        try:
            if strategy == "semantic":
                chunker = SemanticChunkerNode()
            else:
                chunker = StatisticalChunkerNode()

            result = chunker.run(text=text)
            return result["chunks"], None

        except Exception as e:
            # Fallback to simple sentence splitting
            sentences = [s.strip() + '.' for s in text.split('.') if s.strip()]
            chunks = []
            current_chunk = ""

            for sentence in sentences:
                if len(current_chunk) + len(sentence) > 1000:
                    if current_chunk:
                        chunks.append({
                            "chunk_id": f"fallback_{len(chunks)}",
                            "content": current_chunk.strip(),
                            "chunking_method": "fallback"
                        })
                    current_chunk = sentence
                else:
                    current_chunk += " " + sentence if current_chunk else sentence

            if current_chunk:
                chunks.append({
                    "chunk_id": f"fallback_{len(chunks)}",
                    "content": current_chunk.strip(),
                    "chunking_method": "fallback"
                })

            return chunks, str(e)
```

### Edge Case Handling

```python
def robust_processing(documents: List[Dict]):
    """Handle edge cases gracefully."""
    results = []
    errors = []

    for doc in documents:
        try:
            content = doc.get("content", "").strip()

            # Skip empty documents
            if not content:
                errors.append(f"Empty content in {doc.get('id', 'unknown')}")
                continue

            # Skip very short documents
            if len(content) < 50:
                errors.append(f"Document {doc.get('id')} too short")
                continue

            result = chunker.run(text=content)
            chunks = result["chunks"]

            # Verify chunks were created
            if not chunks:
                errors.append(f"No chunks for {doc.get('id')}")
                continue

            results.extend(chunks)

        except Exception as e:
            errors.append(f"Error processing {doc.get('id', 'unknown')}: {e}")

    return results, errors
```

## Quality Assurance

### Automated Quality Checks

```python
def quality_check(chunks: List[Dict]) -> Dict[str, Any]:
    """Comprehensive quality validation."""
    if not chunks:
        return {"status": "failed", "reason": "No chunks generated"}

    # Size analysis
    sizes = [len(chunk["content"]) for chunk in chunks]
    avg_size = sum(sizes) / len(sizes)
    size_variance = sum((s - avg_size) ** 2 for s in sizes) / len(sizes)

    issues = []

    # Check size consistency
    if size_variance > avg_size:
        issues.append(f"High size variance: {size_variance:.0f}")

    # Check for empty chunks
    empty_chunks = [c for c in chunks if len(c["content"]) < 10]
    if empty_chunks:
        issues.append(f"{len(empty_chunks)} empty/tiny chunks")

    # Check for overly large chunks
    large_chunks = [c for c in chunks if len(c["content"]) > 5000]
    if large_chunks:
        issues.append(f"{len(large_chunks)} overly large chunks")

    return {
        "status": "passed" if not issues else "warning",
        "chunk_count": len(chunks),
        "avg_size": avg_size,
        "issues": issues
    }
```

### Retrieval Quality Testing

```python
def test_retrieval_quality(chunks: List[Dict], test_queries: List[str]) -> float:
    """Test how well chunks work for retrieval."""
    scores = []

    for query in test_queries:
        query_words = set(query.lower().split())
        chunk_scores = []

        for chunk in chunks:
            chunk_words = set(chunk["content"].lower().split())
            overlap = len(query_words & chunk_words)
            relevance = overlap / len(query_words) if query_words else 0
            chunk_scores.append(relevance)

        # Best score for this query
        best_score = max(chunk_scores) if chunk_scores else 0
        scores.append(best_score)

    return sum(scores) / len(scores) if scores else 0
```

## Production Monitoring

### Health Checks

```python
class RAGHealthMonitor:
    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.health_history = []

    def health_check(self) -> Dict[str, Any]:
        """Run comprehensive health check."""
        status = {"timestamp": datetime.now().isoformat(), "issues": []}

        # Test chunking
        try:
            test_text = "Test sentence one. Test sentence two."
            chunks = self.pipeline.chunker.run(text=test_text)["chunks"]
            if not chunks:
                status["issues"].append("Chunking returned no results")
        except Exception as e:
            status["issues"].append(f"Chunking failed: {e}")

        # Test retrieval
        try:
            test_results = [{"id": "test", "content": "test", "similarity_score": 0.8}]
            retrieval = self.pipeline.hybrid_retriever.run(
                query="test", dense_results=test_results, sparse_results=test_results
            )
            if not retrieval["hybrid_results"]:
                status["issues"].append("Retrieval returned no results")
        except Exception as e:
            status["issues"].append(f"Retrieval failed: {e}")

        status["overall"] = "healthy" if not status["issues"] else "degraded"
        self.health_history.append(status)

        return status
```

### Performance Metrics

```python
class PerformanceTracker:
    def __init__(self):
        self.metrics = {"chunking_time": [], "retrieval_time": [], "quality_scores": []}

    def track_operation(self, operation: str, duration: float, quality: float = None):
        """Track operation performance."""
        self.metrics[f"{operation}_time"].append(duration)
        if quality is not None:
            self.metrics["quality_scores"].append(quality)

    def get_summary(self) -> Dict[str, float]:
        """Get performance summary."""
        return {
            "avg_chunking_time": sum(self.metrics["chunking_time"]) / len(self.metrics["chunking_time"]),
            "avg_retrieval_time": sum(self.metrics["retrieval_time"]) / len(self.metrics["retrieval_time"]),
            "avg_quality": sum(self.metrics["quality_scores"]) / len(self.metrics["quality_scores"]),
        }
```

## Configuration Management

### Environment-Specific Configs

```python
# config/production.yaml
chunking:
  semantic:
    chunk_size: 1200
    similarity_threshold: 0.8
    chunk_overlap: 120
  statistical:
    chunk_size: 1000
    variance_threshold: 0.6

retrieval:
  fusion_strategy: "rrf"
  top_k: 5
  dense_weight: 0.6

# config/development.yaml
chunking:
  semantic:
    chunk_size: 500  # Smaller for faster testing
    similarity_threshold: 0.7
    chunk_overlap: 50
```

### Config Loading

```python
import yaml
from pathlib import Path

def load_rag_config(environment: str = "production") -> Dict:
    """Load environment-specific configuration."""
    config_path = Path(f"config/{environment}.yaml")

    if not config_path.exists():
        # Fallback to defaults
        return {
            "chunking": {"semantic": {"chunk_size": 1000}},
            "retrieval": {"fusion_strategy": "rrf"}
        }

    with open(config_path) as f:
        return yaml.safe_load(f)

# Usage
config = load_rag_config("production")
chunker = SemanticChunkerNode(**config["chunking"]["semantic"])
```

## Deployment Checklist

### Before Production

- [ ] **Strategy Selection**: Tested both semantic and statistical on your content
- [ ] **Parameter Tuning**: Optimized for your specific documents and queries
- [ ] **Quality Validation**: Implemented automated quality checks
- [ ] **Error Handling**: Graceful degradation and fallback strategies
- [ ] **Performance Testing**: Verified latency and throughput requirements
- [ ] **Health Monitoring**: Automated health checks and alerting
- [ ] **Configuration Management**: Environment-specific configs
- [ ] **Documentation**: Clear runbooks and troubleshooting guides

### During Production

- [ ] **Monitor Performance**: Track chunking and retrieval latency
- [ ] **Quality Metrics**: Monitor chunk quality and retrieval effectiveness
- [ ] **Error Rates**: Track and alert on error patterns
- [ ] **Resource Usage**: Monitor memory and CPU consumption
- [ ] **User Feedback**: Collect and analyze search quality feedback

This guide provides the essential patterns for production-ready RAG systems. Start with the basics and gradually adopt advanced patterns as your system scales.
