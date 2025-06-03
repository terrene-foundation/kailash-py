"""
Comprehensive demonstration of agentic AI nodes with both mock and real implementations.

This example shows:
1. All available agentic AI nodes (LLMAgentNode, EmbeddingGeneratorNode, MCP nodes)
2. Mock provider for testing/development
3. Real Ollama integration for production use
4. Complete feature coverage including tool calling, RAG, and MCP
5. Provider architecture for extensibility

Prerequisites:
- For mock provider: None (always available)
- For Ollama provider:
  - Install Ollama from https://ollama.ai
  - Pull a model: `ollama pull llama3.1:8b-instruct-q8_0`
  - Start Ollama service
"""

import os
import sys
import time

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from kailash.nodes.ai import EmbeddingGeneratorNode, LLMAgentNode
from kailash.nodes.mcp import MCPClient, MCPResource, MCPServer


def check_ollama_availability():
    """Check if Ollama is available and list models."""
    try:
        import ollama

        models = ollama.list()
        print("🎉 Ollama is available!")
        print(f"   Found {len(models['models'])} models:")
        for model in models["models"][:3]:  # Show first 3 models
            print(f"   - {model['model']}")
        return True
    except Exception as e:
        print("⚠️  Ollama not available:", str(e))
        print("   To use Ollama:")
        print("   1. Install from https://ollama.ai")
        print("   2. Run: ollama pull llama3.1:8b-instruct-q8_0")
        print("   3. Ensure Ollama is running")
        return False


def demonstrate_llm_agent_mock():
    """Demonstrate LLMAgentNode with mock provider (no dependencies)."""
    print("\n1️⃣  LLMAgentNode with Mock Provider")
    print("=" * 50)

    agent = LLMAgentNode()

    # Basic Q&A
    print("\n📝 Basic Q&A:")
    result = agent.run(
        provider="mock",
        model="mock-gpt-4",
        messages=[
            {"role": "user", "content": "What are the benefits of microservices?"}
        ],
        generation_config={"temperature": 0.7, "max_tokens": 200},
    )

    if result["success"]:
        print(f"Response: {result['response']['content'][:150]}...")
        print(f"Tokens: {result['usage']['total_tokens']}")

    # With conversation memory
    print("\n💭 With Conversation Memory:")
    result = agent.run(
        provider="mock",
        model="mock-gpt-4",
        messages=[
            {"role": "user", "content": "Remember, I'm working on a Python project"}
        ],
        conversation_id="project-discussion",
        memory_config={"type": "buffer", "max_tokens": 2000},
    )

    if result["success"]:
        print(f"Response: {result['response']['content'][:100]}...")
        print(f"Conversation ID: {result['conversation_id']}")

    # With tool calling
    print("\n🔧 With Tool Calling:")
    result = agent.run(
        provider="mock",
        model="mock-gpt-4",
        messages=[{"role": "user", "content": "Create a report about user engagement"}],
        tools=[
            {
                "name": "create_report",
                "description": "Generate a data report",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "report_type": {"type": "string"},
                        "format": {"type": "string", "enum": ["pdf", "html", "json"]},
                    },
                },
            }
        ],
        generation_config={"temperature": 0},
    )

    if result["success"]:
        print(f"Response: {result['response']['content'][:100]}...")
        print(f"Tool calls: {len(result['response'].get('tool_calls', []))}")


def demonstrate_llm_agent_ollama():
    """Demonstrate LLMAgentNode with real Ollama provider."""
    print("\n2️⃣  LLMAgentNode with Ollama Provider (Real LLM)")
    print("=" * 50)

    if not check_ollama_availability():
        print("   Skipping Ollama demonstration...")
        return

    agent = LLMAgentNode()

    # Basic comparison: Mock vs Real
    print("\n🔄 Comparing Mock vs Real Responses:")

    test_prompt = "Explain the concept of recursion in programming in one sentence."

    # Mock response
    print("\n📦 Mock Provider Response:")
    mock_result = agent.run(
        provider="mock",
        model="mock-model",
        messages=[{"role": "user", "content": test_prompt}],
    )
    if mock_result["success"]:
        print(f"   {mock_result['response']['content']}")

    # Real Ollama response
    print("\n🚀 Ollama Provider Response:")
    start_time = time.time()
    ollama_result = agent.run(
        provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        messages=[{"role": "user", "content": test_prompt}],
        generation_config={
            "temperature": 0.7,
            "top_p": 0.9,
            "tfs_z": 1.0,
            "max_tokens": 100,
        },
    )
    duration = time.time() - start_time

    if ollama_result["success"]:
        print(f"   {ollama_result['response']['content']}")
        print("\n   📊 Performance Metrics:")
        print(f"      - Duration: {duration:.2f}s")
        print(f"      - Model: {ollama_result['response']['model']}")
        print(f"      - Tokens: {ollama_result['usage']['total_tokens']}")
        if "metadata" in ollama_result["response"]:
            meta = ollama_result["response"]["metadata"]
            if "eval_duration_ms" in meta:
                print(f"      - Eval speed: {meta['eval_duration_ms']:.0f}ms")

    # Advanced: With system prompt and context
    print("\n🧠 Advanced: Context-Aware Response:")
    result = agent.run(
        provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        system_prompt="You are an expert Python developer. Be concise and practical.",
        messages=[
            {
                "role": "user",
                "content": "What's the best way to handle errors in Python?",
            }
        ],
        generation_config={"temperature": 0.5, "max_tokens": 200},
    )

    if result["success"]:
        print(f"Response: {result['response']['content'][:1500]}...")


def demonstrate_embedding_generator():
    """Demonstrate EmbeddingGeneratorNode for vector operations."""
    print("\n3️⃣  EmbeddingGeneratorNode Node")
    print("=" * 50)

    embedder = EmbeddingGeneratorNode()

    # Check if Ollama embeddings are available via LLM providers
    ollama_available = False
    embedding_model = "text-embedding-ada-002"  # Default mock model
    provider = "mock"
    available_embeddings = []

    try:
        from kailash.nodes.ai.ai_providers import get_provider

        ollama_provider = get_provider("ollama")

        if ollama_provider.is_available():
            # Check for embedding models via direct Ollama API
            import ollama

            models = ollama.list()
            # Check for embedding models
            embedding_models = [
                "avr/sfr-embedding-mistral",
                "snowflake-arctic-embed2",
                "nomic-embed-text",
                "all-minilm",
            ]
            for model in models["models"]:
                model_name = model.get("model", model.get("name", ""))
                if any(em in model_name for em in embedding_models):
                    available_embeddings.append(model_name)

            if available_embeddings:
                ollama_available = True
                embedding_model = available_embeddings[0]  # Use first available
                provider = "ollama"
                print(f"✅ Found Ollama embedding models: {available_embeddings}")
                print(f"   Using: {embedding_model}")
                print("   Provider available via LLM providers architecture")
            else:
                print("⚠️  No Ollama embedding models found. To use:")
                print("   ollama pull avr/sfr-embedding-mistral")
                print("   ollama pull snowflake-arctic-embed2")
                print("   ollama pull nomic-embed-text")
    except ImportError:
        print("⚠️  LLM providers not available, checking direct Ollama...")
        try:
            import ollama

            models = ollama.list()
            # Check for embedding models
            embedding_models = ["avr/sfr-embedding-mistral", "snowflake-arctic-embed2"]
            for model in models["models"]:
                model_name = model.get("model", model.get("name", ""))
                if any(em in model_name for em in embedding_models):
                    available_embeddings.append(model_name)

            if available_embeddings:
                ollama_available = True
                embedding_model = available_embeddings[0]
                provider = "ollama"
                print(f"✅ Found Ollama embedding models: {available_embeddings}")
                print(f"   Using: {embedding_model}")
        except Exception:
            print("⚠️  Ollama not available, using mock embeddings")

    # Single text embedding
    print("\n📊 Single Text Embedding:")
    result = embedder.run(
        operation="embed_text",
        input_text="Machine learning is transforming industries",
        provider=provider,
        model=embedding_model,
    )

    if result["success"]:
        print(f"✅ Embedding dimension: {result['dimensions']}")
        print(f"   First 5 values: {result['embedding'][:5]}")
        if provider == "ollama":
            print(f"   Provider: Ollama ({embedding_model})")
            print(f"   Processing time: {result.get('processing_time_ms', 'N/A')}ms")
    else:
        print(f"❌ Error: {result.get('error', 'Unknown error')}")

    # Batch embeddings
    print("\n📊 Batch Embeddings:")
    texts = [
        "Python is a versatile programming language",
        "Data science requires statistical knowledge",
        "Machine learning models learn from data",
    ]

    result = embedder.run(
        operation="embed_batch",
        input_texts=texts,
        provider=provider,
        model=embedding_model,
        batch_size=2,
        cache_hits=True,
    )

    if result["success"]:
        print(f"✅ Generated {result['total_embeddings']} embeddings")
        print(f"   Cache hits: {result.get('cache_hits', 0)}/{result['total_texts']}")
        print(f"   Processing time: {result.get('processing_time_ms', 'N/A')}ms")
        if provider == "ollama":
            print(
                f"   Average tokens per text: {result['usage']['average_tokens_per_text']:.1f}"
            )

    # Similarity calculation
    print("\n🔍 Similarity Calculation:")
    similar_texts = ["AI is the future", "Artificial intelligence will shape tomorrow"]
    result = embedder.run(
        operation="calculate_similarity",
        input_texts=similar_texts,
        provider=provider,
        model=embedding_model,
        similarity_metric="cosine",
    )

    if result["success"]:
        print(f"✅ Similarity score: {result['similarity']:.3f}")
        print(f"   Metric: {result['metric']}")
        print(f"   Interpretation: {result['interpretation']}")
        if "texts" in result:
            print(f"   Text 1: '{result['texts'][0][:50]}...'")
            print(f"   Text 2: '{result['texts'][1][:50]}...'")

    # Demonstrate Ollama provider via LLM providers architecture
    if ollama_available:
        print("\n🔧 Using Ollama via LLM Providers Architecture:")
        try:
            from kailash.nodes.ai.ai_providers import get_provider

            ollama_provider = get_provider("ollama")
            print(f"   ✅ Ollama provider: {type(ollama_provider).__name__}")
            print(f"   Available: {ollama_provider.is_available()}")
            print(f"   Model: {embedding_model}")
        except ImportError:
            print("   ⚠️  Using direct Ollama integration")

    # Demonstrate with different Ollama models if available
    if ollama_available and len(available_embeddings) > 1:
        print("\n🔄 Comparing Embedding Models:")
        for model in available_embeddings[:2]:  # Compare first 2 models
            result = embedder.run(
                operation="embed_text",
                input_text="Neural networks and deep learning",
                provider="ollama",
                model=model,
            )
            if result["success"]:
                dim = result["dimensions"]
                print(f"   {model}: {dim} dimensions")
                print(
                    f"     Processing time: {result.get('processing_time_ms', 'N/A')}ms"
                )

    # Real-world example: Semantic search
    print("\n🔎 Real-World Example: Semantic Search")
    documents = [
        "The Python programming language is known for its simplicity and readability",
        "Machine learning algorithms can predict future outcomes based on historical data",
        "Data visualization helps understand complex patterns in large datasets",
        "Neural networks are inspired by biological neurons and form the basis of deep learning",
        "Python is widely used in data science and AI due to its extensive libraries",
    ]

    query = "What programming language is best for AI and machine learning?"

    # Embed documents and query
    doc_result = embedder.run(
        operation="embed_batch",
        input_texts=documents,
        provider=provider,
        model=embedding_model,
    )

    query_result = embedder.run(
        operation="embed_text",
        input_text=query,
        provider=provider,
        model=embedding_model,
    )

    if doc_result["success"] and query_result["success"]:
        # Calculate similarities
        try:
            from numpy import dot
            from numpy.linalg import norm
        except ImportError:
            # Fallback implementation if numpy not available
            def dot(a, b):
                return sum(x * y for x, y in zip(a, b))

            def norm(a):
                return sum(x * x for x in a) ** 0.5

        query_embedding = query_result["embedding"]
        similarities = []

        for i, doc_info in enumerate(doc_result["embeddings"]):
            doc_embedding = doc_info["embedding"]
            # Cosine similarity
            similarity = dot(query_embedding, doc_embedding) / (
                norm(query_embedding) * norm(doc_embedding)
            )
            similarities.append((i, similarity, documents[i]))

        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)

        print(f"   Query: '{query}'")
        print("   Top 3 most relevant documents:")
        for i, (idx, score, doc) in enumerate(similarities[:3], 1):
            print(f"   {i}. (Score: {score:.3f}) {doc[:60]}...")

    # With dimensionality reduction (mock only)
    if provider == "mock":
        print("\n📉 With Dimensionality Reduction (Mock Only):")
        result = embedder.run(
            operation="embed_text",
            input_text="Complex high-dimensional data",
            provider="mock",
            reduce_dimensions=True,
            target_dimensions=2,
            reduction_method="pca",
        )

        if result["success"] and "reduced_embeddings" in result:
            print(f"Reduced to {len(result['reduced_embeddings'][0])} dimensions")
            print(f"Values: {result['reduced_embeddings'][0]}")


def demonstrate_mcp_ecosystem():
    """Demonstrate MCP (Model Context Protocol) ecosystem."""
    print("\n4️⃣  MCP Ecosystem (Context Sharing)")
    print("=" * 50)

    # MCPResource - Managing shared resources
    print("\n📦 MCPResource - Creating Shared Context:")
    resource_node = MCPResource()

    # Create a business context resource
    resource_result = resource_node.run(
        operation="create",
        uri="data://business-metrics-2024",
        content={
            "revenue": {"q1": 1.2e6, "q2": 1.5e6, "q3": 1.8e6},
            "customers": {"total": 5000, "active": 4200, "churn_rate": 0.05},
            "products": ["SaaS Platform", "API Service", "Consulting"],
            "market_position": "Growing startup in B2B SaaS",
        },
        metadata={
            "created_by": "data_team",
            "version": "1.0",
            "last_updated": "2024-10-01",
        },
    )

    if resource_result["success"]:
        if "resource" in resource_result:
            print(f"✅ Created resource: {resource_result['resource']['uri']}")
            if "type" in resource_result["resource"]:
                print(f"   Type: {resource_result['resource']['type']}")
            if "id" in resource_result["resource"]:
                print(f"   ID: {resource_result['resource']['id']}")
        else:
            print("✅ Resource created successfully")

    # MCPClient - Connecting to MCP servers
    print("\n🔌 MCPClient - Retrieving Shared Context:")
    client = MCPClient()

    # List available resources
    list_result = client.run(
        server_config={"name": "mock-server", "transport": "stdio"},
        operation="list_resources",
    )

    if list_result["success"]:
        print(f"Available resources: {len(list_result.get('resources', []))}")
        for res in list_result.get("resources", [])[:3]:
            print(f"  - {res['uri']}: {res['name']}")

    # MCPServer - Configuration for hosting
    print("\n🖥️  MCPServer - Hosting Resources:")
    server = MCPServer()

    server_result = server.run(
        server_config={
            "name": "company-data-server",
            "transport": "stdio",
            "resources": [
                {
                    "uri": "data://metrics/current",
                    "name": "Current Business Metrics",
                    "description": "Real-time business KPIs",
                }
            ],
            "capabilities": {"tools": True, "resources": True, "prompts": False},
        }
    )

    if server_result.get("success"):
        if "server" in server_result and isinstance(server_result["server"], dict):
            server_info = server_result["server"]
            print(f"✅ Server configured: {server_info.get('name', 'Unknown')}")
            print(f"   Transport: {server_info.get('transport', 'Unknown')}")
            if "resources" in server_result:
                print(f"   Resources: {server_result['resources'].get('count', 0)}")
            if "capabilities" in server_info:
                caps = server_info["capabilities"]
                print(f"   Capabilities: {', '.join(k for k, v in caps.items() if v)}")
        else:
            print("✅ Server configured successfully")
            print("   Mock server ready")


def demonstrate_integrated_workflow():
    """Demonstrate an integrated workflow using multiple nodes."""
    print("\n5️⃣  Integrated Workflow Example")
    print("=" * 50)
    print("Scenario: AI-powered data analysis with context and embeddings")

    # Step 1: Create context resource
    print("\n📝 Step 1: Create Business Context")
    resource_node = MCPResource()
    resource_node.run(
        operation="create",
        resource_type="context",
        resource_id="q4-analysis",
        content={
            "objective": "Analyze Q4 performance and predict Q1 trends",
            "key_metrics": ["revenue", "customer_acquisition", "churn"],
            "constraints": ["Budget: $50k", "Timeline: 2 weeks"],
        },
    )

    # Step 2: Generate embeddings for relevant documents
    print("\n📊 Step 2: Generate Document Embeddings")
    embedder = EmbeddingGeneratorNode()
    documents = [
        "Q4 revenue exceeded targets by 15% due to holiday sales",
        "Customer acquisition cost decreased by 20% with new marketing strategy",
        "Churn rate remains stable at 5% monthly",
    ]

    embedder.run(
        operation="embed_batch",
        input_texts=documents,
        provider="mock",
        model="text-embedding-ada-002",
        store_in_mcp=True,
        mcp_resource_id="q4-analysis-embeddings",
    )

    # Step 3: Use LLMAgentNode with context and embeddings
    print("\n🤖 Step 3: Generate Analysis with Context")
    agent = LLMAgentNode()

    # Choose provider based on availability
    provider = "mock"
    model = "mock-gpt-4"

    # Try Ollama if available
    try:
        from kailash.nodes.ai.ai_providers import get_provider

        ollama = get_provider("ollama")
        if ollama.is_available():
            provider = "ollama"
            model = "llama3.1:8b-instruct-q8_0"
            print("   Using Ollama for real analysis...")
    except Exception:
        print("   Using mock provider for demonstration...")

    analysis_result = agent.run(
        provider=provider,
        model=model,
        system_prompt="You are a business analyst. Use the provided context to give insights.",
        messages=[
            {
                "role": "user",
                "content": "Based on Q4 performance, what should be our Q1 strategy?",
            }
        ],
        mcp_context=["mcp://q4-analysis", "mcp://q4-analysis-embeddings"],
        rag_config={"enabled": True, "top_k": 3, "similarity_threshold": 0.7},
        generation_config={"temperature": 0.7, "max_tokens": 300},
    )

    if analysis_result["success"]:
        print("\n📈 Analysis Result:")
        print(f"{analysis_result['response']['content'][:400]}...")
        print("\n📊 Context Used:")
        print(f"   - MCP resources: {analysis_result['context']['mcp_resources_used']}")
        print(
            f"   - RAG documents: {analysis_result['context']['rag_documents_retrieved']}"
        )


def demonstrate_provider_architecture():
    """Demonstrate the unified provider architecture and extensibility."""
    print("\n6️⃣  Unified Provider Architecture")
    print("=" * 50)

    try:
        # Try the new unified provider first
        from kailash.nodes.ai.ai_providers import get_available_providers, get_provider

        print("📋 Available Providers (Unified Architecture):")
        all_providers = get_available_providers()

        for name, info in all_providers.items():
            status = "✅" if info["available"] else "❌"
            capabilities = []
            if info.get("chat"):
                capabilities.append("LLM")
            if info.get("embeddings"):
                capabilities.append("Embeddings")

            print(f"   {status} {name} - Supports: {', '.join(capabilities)}")

            # Show why unavailable
            if not info["available"] and name != "mock":
                if name == "openai":
                    print("      → Set OPENAI_API_KEY environment variable")
                elif name == "anthropic":
                    print("      → Set ANTHROPIC_API_KEY environment variable")
                elif name == "ollama":
                    print("      → Install and start Ollama service")
                elif name == "cohere":
                    print("      → Set COHERE_API_KEY environment variable")
                elif name == "huggingface":
                    print("      → Set HUGGINGFACE_API_KEY or install transformers")

        # Demonstrate unified provider usage
        print("\n🔄 Using Unified Providers:")
        mock_provider = get_provider("mock")
        print(f"   Mock provider capabilities: {mock_provider.get_capabilities()}")

        # Show OpenAI if available
        try:
            openai_provider = get_provider("openai")
            if openai_provider.is_available():
                print("   OpenAI provider supports both LLM and embeddings")
        except Exception:
            pass

    except ImportError:
        # Fallback to legacy providers
        print("⚠️  Using legacy provider architecture...")
        from kailash.nodes.ai.ai_providers import PROVIDERS, get_provider

        print("\n📋 Available LLM Providers (Legacy):")
        for provider_name in PROVIDERS:
            try:
                provider = get_provider(provider_name)
                available = provider.is_available()
                status = "✅" if available else "❌"
                print(f"   {status} {provider_name}")
            except Exception as e:
                print(f"   ❌ {provider_name}: {e}")

    print("\n💡 Provider Architecture Benefits:")
    print("   1. Single unified interface for both LLM and embeddings")
    print("   2. Reduced code duplication for providers like OpenAI and Ollama")
    print("   3. Easy to add new providers with multiple capabilities")
    print("   4. Backward compatible with existing code")


def main():
    """Run all demonstrations."""
    print("🚀 Kailash Agentic AI Nodes - Comprehensive Demo")
    print("=" * 50)
    print("This demo showcases all AI capabilities with both mock and real providers\n")

    # Check Python version
    import sys

    if sys.version_info < (3, 8):
        print("⚠️  Warning: Python 3.8+ recommended for best compatibility")

    # Run all demonstrations
    demonstrate_llm_agent_mock()
    demonstrate_llm_agent_ollama()
    demonstrate_embedding_generator()
    demonstrate_mcp_ecosystem()
    demonstrate_integrated_workflow()
    demonstrate_provider_architecture()

    print("\n\n✨ Summary")
    print("=" * 50)
    print("You've seen demonstrations of:")
    print("✅ LLMAgentNode - With mock and real (Ollama) providers")
    print("✅ EmbeddingGeneratorNode - Vector embeddings and similarity")
    print("✅ MCP Ecosystem - Context sharing across AI components")
    print("✅ Integrated Workflows - Combining multiple nodes")
    print("✅ Provider Architecture - Extensible LLM support")
    print("\n🎯 Next Steps:")
    print("1. Install Ollama for real LLM responses")
    print("2. Set up API keys for OpenAI/Anthropic providers")
    print("3. Explore tool calling and function execution")
    print("4. Build production workflows with persistent memory")
    print("5. Implement custom providers for your LLMs")


if __name__ == "__main__":
    main()
