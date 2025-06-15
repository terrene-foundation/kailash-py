# Advanced Document Processing and Compression Guide

**Last Updated**: 2025-01-06  
**Difficulty**: Intermediate to Advanced  
**Prerequisites**: [Basic Node Usage](01-getting-started.md), [Data Nodes](../nodes/03-data-nodes.md)

This guide covers the advanced document processing and compression capabilities newly added to the Kailash SDK, including the DocumentProcessorNode and ContextualCompressorNode.

## Table of Contents
- [Overview](#overview)
- [DocumentProcessorNode](#documentprocessornode)
- [ContextualCompressorNode](#contextualcompressornode)
- [Integration Patterns](#integration-patterns)
- [Performance Optimization](#performance-optimization)
- [Production Considerations](#production-considerations)
- [Troubleshooting](#troubleshooting)

## Overview

The advanced document processing and compression nodes provide enterprise-grade capabilities for:

- **Multi-format document processing** with automatic format detection
- **Intelligent content compression** for LLM context optimization
- **Metadata extraction** for document management systems
- **Structure preservation** for advanced document analysis
- **Token budget management** for cost-effective AI applications

### Key Benefits

1. **Universal Document Support**: Handle PDF, DOCX, Markdown, HTML, RTF, and text files
2. **Intelligent Compression**: Achieve 50-70% token reduction while preserving relevance
3. **Production Ready**: Comprehensive error handling and fallback strategies
4. **Metadata Rich**: Extract titles, authors, structure, and statistical information
5. **RAG Optimized**: Perfect for Retrieval-Augmented Generation pipelines

## DocumentProcessorNode

### Core Capabilities

The DocumentProcessorNode provides unified document processing across multiple formats:

```python
from kailash.nodes.data.readers import DocumentProcessorNode

processor = DocumentProcessorNode(
    extract_metadata=True,
    preserve_structure=True,
    encoding="utf-8"
)
```

### Format-Specific Processing

#### PDF Documents
```python
result = processor.run(file_path="research_paper.pdf")
# Extracts:
# - Full text content
# - Page numbers and structure
# - Document metadata (title, author, creation date)
# - Page count and PDF version
```

#### Microsoft Word Documents
```python
result = processor.run(file_path="business_report.docx")
# Extracts:
# - Text content with formatting preserved
# - Document properties (title, author, word count)
# - Paragraph and section structure
# - Creation and modification dates
```

#### Markdown Documents
```python
result = processor.run(file_path="documentation.md")
# Extracts:
# - Full markdown content
# - Heading structure (levels, titles, positions)
# - Word and character counts
# - Line numbers for each heading
```

#### HTML Documents
```python
result = processor.run(file_path="webpage.html")
# Extracts:
# - Clean text without HTML tags
# - Heading structure (h1-h6)
# - Document title from <title> tag
# - Removes scripts and styles automatically
```

### Advanced Usage Patterns

#### Batch Document Processing
```python
import os
from pathlib import Path

def process_document_directory(directory_path: str):
    """Process all documents in a directory."""
    processor = DocumentProcessorNode()
    results = []
    
    for file_path in Path(directory_path).rglob("*"):
        if file_path.is_file() and file_path.suffix in ['.pdf', '.docx', '.md', '.html', '.txt']:
            try:
                result = processor.run(file_path=str(file_path))
                results.append({
                    "file_path": str(file_path),
                    "success": True,
                    "content_length": len(result["content"]),
                    "metadata": result["metadata"]
                })
            except Exception as e:
                results.append({
                    "file_path": str(file_path),
                    "success": False,
                    "error": str(e)
                })
    
    return results
```

#### Metadata-Driven Workflows
```python
def categorize_documents_by_metadata(file_paths: list):
    """Categorize documents based on extracted metadata."""
    processor = DocumentProcessorNode(extract_metadata=True)
    categories = {
        "technical": [],
        "business": [],
        "academic": [],
        "other": []
    }
    
    for file_path in file_paths:
        result = processor.run(file_path=file_path)
        metadata = result["metadata"]
        
        # Categorize based on content characteristics
        word_count = metadata.get("word_count", 0)
        has_technical_structure = len(result.get("sections", [])) > 5
        
        if word_count > 5000 and has_technical_structure:
            categories["technical"].append(file_path)
        elif "business" in result["content"].lower():
            categories["business"].append(file_path)
        elif word_count > 10000:
            categories["academic"].append(file_path)
        else:
            categories["other"].append(file_path)
    
    return categories
```

## ContextualCompressorNode

### Core Compression Strategies

The ContextualCompressorNode provides intelligent content compression for optimal context utilization:

```python
from kailash.nodes.transform.processors import ContextualCompressorNode

compressor = ContextualCompressorNode(
    compression_target=2000,
    relevance_threshold=0.75,
    compression_strategy="extractive_summarization"
)
```

### Compression Strategies Explained

#### Extractive Summarization
```python
# Best for: General content, mixed document types
compressor = ContextualCompressorNode(
    compression_strategy="extractive_summarization",
    relevance_threshold=0.7
)

result = compressor.run(
    query="machine learning applications",
    retrieved_docs=documents
)
# Extracts most relevant sentences while preserving original wording
```

#### Abstractive Synthesis
```python
# Best for: Creating structured summaries
compressor = ContextualCompressorNode(
    compression_strategy="abstractive_synthesis",
    compression_ratio=0.5
)

result = compressor.run(
    query="financial market analysis",
    retrieved_docs=financial_reports
)
# Creates structured summary with key points
```

#### Hierarchical Organization
```python
# Best for: Complex topics requiring structure
compressor = ContextualCompressorNode(
    compression_strategy="hierarchical_organization",
    compression_target=3000
)

result = compressor.run(
    query="software architecture patterns",
    retrieved_docs=technical_docs
)
# Organizes content by importance levels
```

### Advanced Compression Techniques

#### Token Budget Management
```python
def compress_for_llm_context(documents: list, query: str, max_tokens: int):
    """Compress documents to fit within LLM context window."""
    compressor = ContextualCompressorNode(
        compression_target=max_tokens,
        relevance_threshold=0.8,  # Higher threshold for quality
        compression_strategy="extractive_summarization"
    )
    
    result = compressor.run(
        query=query,
        retrieved_docs=documents
    )
    
    # Validate compression success
    if result["compression_success"]:
        metadata = result["compression_metadata"]
        print(f"Compressed {metadata['original_document_count']} documents")
        print(f"Achieved {metadata['compression_ratio']:.2%} compression")
        print(f"Average relevance: {metadata['avg_relevance_score']:.3f}")
        
        return result["compressed_context"]
    else:
        raise Exception(f"Compression failed: {result.get('error', 'Unknown error')}")
```

#### Quality-Driven Compression
```python
def adaptive_compression(documents: list, query: str, quality_threshold: float = 0.8):
    """Adaptive compression that prioritizes quality over compression ratio."""
    
    # Start with conservative compression
    compressor = ContextualCompressorNode(
        relevance_threshold=quality_threshold,
        compression_strategy="extractive_summarization"
    )
    
    # Try different compression targets until quality is maintained
    for target_tokens in [4000, 3000, 2000, 1500]:
        result = compressor.run(
            query=query,
            retrieved_docs=documents,
            compression_target=target_tokens
        )
        
        if result["compression_success"]:
            avg_relevance = result["compression_metadata"]["avg_relevance_score"]
            if avg_relevance >= quality_threshold:
                return result["compressed_context"]
    
    # Fallback to minimal compression
    return compressor.run(
        query=query,
        retrieved_docs=documents,
        compression_target=5000
    )["compressed_context"]
```

## Integration Patterns

### Complete Document-to-Answer Pipeline

```python
from kailash.nodes.data.readers import DocumentProcessorNode
from kailash.nodes.transform.processors import ContextualCompressorNode
from kailash.nodes.ai.llm_agent import LLMAgentNode

def document_qa_pipeline(file_path: str, question: str):
    """Complete pipeline from document to answer."""
    
    # Step 1: Process document
    processor = DocumentProcessorNode(
        extract_metadata=True,
        preserve_structure=True
    )
    doc_result = processor.run(file_path=file_path)
    
    if "error" in doc_result:
        return {"error": f"Document processing failed: {doc_result['error']}"}
    
    # Step 2: Create retrieved documents structure
    retrieved_docs = [{
        "content": doc_result["content"],
        "similarity_score": 0.9,  # High since it's the source document
        "metadata": doc_result["metadata"]
    }]
    
    # Step 3: Compress for LLM context
    compressor = ContextualCompressorNode(
        compression_target=2000,
        relevance_threshold=0.6,  # Lower threshold for single document
        compression_strategy="extractive_summarization"
    )
    
    compression_result = compressor.run(
        query=question,
        retrieved_docs=retrieved_docs
    )
    
    if not compression_result["compression_success"]:
        return {"error": f"Compression failed: {compression_result.get('error')}"}
    
    # Step 4: Generate answer using LLM
    llm = LLMAgentNode(
        provider="openai",
        model="gpt-4",
        temperature=0.1
    )
    
    prompt = f"""Based on the following document content, answer the question:

Question: {question}

Document Content:
{compression_result['compressed_context']}

Please provide a comprehensive answer based only on the information in the document."""
    
    answer_result = llm.run(messages=[{"role": "user", "content": prompt}])
    
    return {
        "answer": answer_result.get("content", ""),
        "source_metadata": doc_result["metadata"],
        "compression_stats": compression_result["compression_metadata"]
    }
```

### Batch Document Analysis

```python
def analyze_document_collection(document_paths: list, analysis_query: str):
    """Analyze a collection of documents for specific information."""
    
    processor = DocumentProcessorNode()
    compressor = ContextualCompressorNode(
        compression_target=1000,  # Smaller chunks for batch processing
        compression_strategy="hierarchical_organization"
    )
    
    analysis_results = []
    
    for doc_path in document_paths:
        # Process document
        doc_result = processor.run(file_path=doc_path)
        
        if "error" in doc_result:
            analysis_results.append({
                "document": doc_path,
                "error": doc_result["error"]
            })
            continue
        
        # Compress for analysis
        retrieved_docs = [{
            "content": doc_result["content"],
            "similarity_score": 0.9,
            "metadata": doc_result["metadata"]
        }]
        
        compression_result = compressor.run(
            query=analysis_query,
            retrieved_docs=retrieved_docs
        )
        
        analysis_results.append({
            "document": doc_path,
            "compressed_content": compression_result.get("compressed_context", ""),
            "metadata": doc_result["metadata"],
            "compression_success": compression_result["compression_success"]
        })
    
    return analysis_results
```

## Performance Optimization

### Memory Management

```python
def process_large_document_safely(file_path: str, chunk_size: int = 10000):
    """Process large documents with memory management."""
    
    processor = DocumentProcessorNode(
        extract_metadata=True,
        preserve_structure=False  # Reduces memory for large docs
    )
    
    result = processor.run(file_path=file_path)
    
    # For very large documents, process in chunks
    if len(result["content"]) > chunk_size:
        content_chunks = [
            result["content"][i:i+chunk_size] 
            for i in range(0, len(result["content"]), chunk_size)
        ]
        
        # Process each chunk separately if needed
        return {
            "chunks": content_chunks,
            "metadata": result["metadata"],
            "total_length": len(result["content"])
        }
    
    return result
```

### Caching Strategies

```python
import hashlib
import json
from pathlib import Path

class DocumentCache:
    """Simple file-based cache for processed documents."""
    
    def __init__(self, cache_dir: str = ".document_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
    
    def _get_cache_key(self, file_path: str, options: dict) -> str:
        """Generate cache key from file path and processing options."""
        file_stat = Path(file_path).stat()
        cache_input = {
            "file_path": file_path,
            "file_size": file_stat.st_size,
            "file_mtime": file_stat.st_mtime,
            "options": options
        }
        return hashlib.md5(json.dumps(cache_input, sort_keys=True).encode()).hexdigest()
    
    def get(self, file_path: str, options: dict):
        """Get cached result if available."""
        cache_key = self._get_cache_key(file_path, options)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if cache_file.exists():
            with open(cache_file, 'r') as f:
                return json.load(f)
        return None
    
    def set(self, file_path: str, options: dict, result: dict):
        """Cache processing result."""
        cache_key = self._get_cache_key(file_path, options)
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        with open(cache_file, 'w') as f:
            json.dump(result, f)

# Usage with caching
cache = DocumentCache()

def cached_document_processing(file_path: str, **options):
    """Process document with caching."""
    
    # Check cache first
    cached_result = cache.get(file_path, options)
    if cached_result:
        return cached_result
    
    # Process document
    processor = DocumentProcessorNode(**options)
    result = processor.run(file_path=file_path)
    
    # Cache result
    cache.set(file_path, options, result)
    return result
```

## Production Considerations

### Error Handling and Resilience

```python
def robust_document_processing(file_path: str, max_retries: int = 3):
    """Robust document processing with retries and fallbacks."""
    
    for attempt in range(max_retries):
        try:
            # Try with full feature set
            processor = DocumentProcessorNode(
                extract_metadata=True,
                preserve_structure=True
            )
            
            result = processor.run(file_path=file_path)
            
            if "error" not in result:
                return result
            
            # If error, log and retry with simpler settings
            print(f"Attempt {attempt + 1} failed: {result['error']}")
            
            if attempt < max_retries - 1:
                # Retry with simpler settings
                processor = DocumentProcessorNode(
                    extract_metadata=False,
                    preserve_structure=False
                )
                
        except Exception as e:
            print(f"Exception on attempt {attempt + 1}: {str(e)}")
            
            if attempt == max_retries - 1:
                # Final fallback: treat as plain text
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    return {
                        "content": content,
                        "metadata": {"file_path": file_path, "fallback_mode": True},
                        "sections": [],
                        "document_format": "text"
                    }
                except Exception as final_error:
                    return {"error": f"All processing attempts failed: {str(final_error)}"}
    
    return {"error": "Maximum retries exceeded"}
```

### Monitoring and Logging

```python
import logging
import time
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def monitored_processing(file_path: str) -> Dict[str, Any]:
    """Document processing with comprehensive monitoring."""
    
    start_time = time.time()
    
    try:
        # Log processing start
        logger.info(f"Starting document processing: {file_path}")
        
        processor = DocumentProcessorNode()
        result = processor.run(file_path=file_path)
        
        # Calculate processing metrics
        processing_time = time.time() - start_time
        content_length = len(result.get("content", ""))
        
        # Log success metrics
        logger.info(f"Processing completed: {file_path}")
        logger.info(f"Processing time: {processing_time:.2f}s")
        logger.info(f"Content length: {content_length} characters")
        logger.info(f"Document format: {result.get('document_format', 'unknown')}")
        
        # Add monitoring metadata
        result["processing_metrics"] = {
            "processing_time_seconds": processing_time,
            "content_length": content_length,
            "success": True
        }
        
        return result
        
    except Exception as e:
        processing_time = time.time() - start_time
        
        # Log error
        logger.error(f"Processing failed: {file_path}")
        logger.error(f"Error: {str(e)}")
        logger.error(f"Processing time before failure: {processing_time:.2f}s")
        
        return {
            "error": str(e),
            "processing_metrics": {
                "processing_time_seconds": processing_time,
                "success": False
            }
        }
```

## Troubleshooting

### Common Issues and Solutions

#### Document Format Detection Problems
```python
# Problem: Format not detected correctly
# Solution: Manual format specification
processor = DocumentProcessorNode()

# Override format detection
file_path = "document.unknown"
if file_path.endswith('.unknown'):
    # Force treat as text
    result = processor._process_text(file_path, "utf-8", extract_metadata=True)
else:
    result = processor.run(file_path=file_path)
```

#### Memory Issues with Large Documents
```python
# Problem: Out of memory with large documents
# Solution: Chunk processing or disable structure preservation
processor = DocumentProcessorNode(
    preserve_structure=False,  # Reduces memory usage
    extract_metadata=False     # Reduces processing overhead
)
```

#### Compression Quality Issues
```python
# Problem: Compression removes important content
# Solution: Adjust relevance threshold and strategy
compressor = ContextualCompressorNode(
    relevance_threshold=0.5,   # Lower threshold includes more content
    compression_strategy="hierarchical_organization",  # Preserves structure
    compression_target=4000    # Higher target for more content
)
```

#### Encoding Issues
```python
# Problem: Text encoding errors
# Solution: Try multiple encodings
def try_multiple_encodings(file_path: str):
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
    
    for encoding in encodings:
        try:
            processor = DocumentProcessorNode(encoding=encoding)
            result = processor.run(file_path=file_path)
            if "error" not in result:
                return result
        except Exception:
            continue
    
    return {"error": "Could not decode with any supported encoding"}
```

### Performance Troubleshooting

#### Slow Processing Diagnosis
```python
import time

def diagnose_slow_processing(file_path: str):
    """Diagnose performance issues in document processing."""
    
    start_time = time.time()
    
    # Test basic file operations
    try:
        with open(file_path, 'rb') as f:
            file_size = len(f.read())
        file_read_time = time.time() - start_time
        print(f"File read time: {file_read_time:.2f}s for {file_size} bytes")
    except Exception as e:
        print(f"File read failed: {e}")
        return
    
    # Test document processing
    start_time = time.time()
    processor = DocumentProcessorNode(
        extract_metadata=False,  # Minimal processing
        preserve_structure=False
    )
    
    result = processor.run(file_path=file_path)
    processing_time = time.time() - start_time
    
    print(f"Document processing time: {processing_time:.2f}s")
    print(f"Processing rate: {file_size / processing_time:.0f} bytes/second")
    
    if processing_time > 10:  # Slow processing
        print("⚠️  Slow processing detected. Consider:")
        print("  - Disabling metadata extraction")
        print("  - Disabling structure preservation")
        print("  - Processing in smaller chunks")
        print("  - Using simpler document formats")
```

### Best Practices Summary

1. **Always handle errors gracefully** with fallback strategies
2. **Use caching** for frequently processed documents
3. **Monitor performance** in production environments
4. **Choose appropriate compression strategies** based on content type
5. **Test with representative document samples** before production
6. **Consider memory constraints** when processing large documents
7. **Use appropriate relevance thresholds** for your use case
8. **Validate compression quality** meets your requirements

This completes the advanced document processing and compression guide. These nodes provide powerful capabilities for enterprise document workflows and RAG systems.