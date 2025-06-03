# Kailash Python SDK v0.1.2 Release Notes

## 🎉 Major Release: Complete Hierarchical RAG Implementation

**Release Date:** June 3, 2025
**Version:** 0.1.2
**PyPI Package:** `kailash==0.1.2`

### 🚀 What's New

#### Complete Hierarchical RAG Architecture
This release introduces a production-ready Retrieval-Augmented Generation (RAG) pipeline with 7 specialized nodes:

- **DocumentSourceNode** - Autonomous document provider with sample data
- **QuerySourceNode** - Sample query provider for RAG testing
- **HierarchicalChunkerNode** - Intelligent document chunking with configurable sizes
- **RelevanceScorerNode** - Multi-method similarity scoring (cosine similarity + text-based fallback)
- **ChunkTextExtractorNode** - Text extraction for embedding generation
- **QueryTextWrapperNode** - Query formatting for batch processing
- **ContextFormatterNode** - LLM context preparation

#### Key Features
- ✅ **Autonomous Operation** - No external files required for examples
- ✅ **Multi-Provider AI Integration** - Works with Ollama, OpenAI, Anthropic, Azure
- ✅ **Production Ready** - 29 comprehensive tests with full validation
- ✅ **Embedding-Based Retrieval** - Advanced semantic search capabilities
- ✅ **Flexible Configuration** - Customizable chunk sizes and similarity methods

### 📁 Path Standardization

- Standardized all examples to use `examples/outputs/` consistently
- Fixed 12+ example files that were creating subdirectories or root-level outputs
- Improved developer experience with predictable output locations

### 🔧 Technical Improvements

#### AI Provider Unification
- Unified AI provider interface combining LLM and embedding capabilities
- Single BaseAIProvider, LLMProvider, EmbeddingProvider classes
- Support for Ollama, OpenAI, Anthropic, Cohere, HuggingFace, and Mock providers

#### Code Quality
- Applied Black formatting across all modified files
- Import sorting with isort for consistency
- Pre-commit hook compliance for all changes
- Enhanced documentation with working examples

### 📚 Documentation Updates

- Complete hierarchical RAG section in API documentation
- Working pipeline examples and configuration guides
- Updated implementation status tracker
- Usage patterns and best practices

### 🧪 Testing & Validation

- **29 new tests** covering all RAG components
- All 45 existing examples continue to pass
- Documentation build verification
- Integration testing with multiple AI providers

### 💾 Installation & Upgrade

```bash
# Fresh installation
pip install kailash==0.1.2

# Upgrade from previous version
pip install --upgrade kailash

# With uv (recommended)
uv add kailash==0.1.2
```

### 🎯 Quick Start with Hierarchical RAG

```python
from kailash.workflow import Workflow
from kailash.nodes.data.sources import DocumentSourceNode, QuerySourceNode
from kailash.nodes.data.retrieval import RelevanceScorerNode
from kailash.nodes.transform.chunkers import HierarchicalChunkerNode
from kailash.nodes.ai.embedding_generator import EmbeddingGenerator
from kailash.nodes.ai.llm_agent import LLMAgent

# Create hierarchical RAG workflow
workflow = Workflow("hierarchical_rag", name="Hierarchical RAG Workflow")

# Add RAG components
workflow.add_node("doc_source", DocumentSourceNode())
workflow.add_node("query_source", QuerySourceNode())
workflow.add_node("chunker", HierarchicalChunkerNode())
workflow.add_node("embedder", EmbeddingGenerator(provider="ollama", model="nomic-embed-text"))
workflow.add_node("relevance_scorer", RelevanceScorerNode())
workflow.add_node("llm_agent", LLMAgent(provider="ollama", model="llama3.2"))

# Connect and run
# ... (see full example in documentation)
```

### 🔗 Resources

- **PyPI Package**: https://pypi.org/project/kailash/0.1.2/
- **GitHub Release**: https://github.com/terrene-foundation/kailash-py/releases/tag/v0.1.2
- **Pull Request**: https://github.com/terrene-foundation/kailash-py/pull/81
- **Documentation**: https://terrene-foundation.github.io/kailash_python_sdk/

### 🚨 Breaking Changes

None. This is a purely additive release maintaining full backward compatibility.

### 🐛 Bug Fixes

- Fixed HTTPClientNode parameter handling
- Resolved import statement issues
- Corrected documentation build formatting

### 🙏 Acknowledgments

This release represents a significant milestone in making Kailash Python SDK production-ready for enterprise AI workflows. Special thanks to the development team for their comprehensive testing and documentation efforts.

---

**Full Changelog**: https://github.com/terrene-foundation/kailash-py/blob/main/CHANGELOG.md
