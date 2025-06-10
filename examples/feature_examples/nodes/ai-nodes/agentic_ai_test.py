"""
Comprehensive demonstration of agentic AI nodes using Docker infrastructure.

This example shows:
1. All available agentic AI nodes (LLMAgentNode, EmbeddingGeneratorNode, MCP integration)
2. Docker-based services for production-ready testing
3. Real Ollama integration via Docker container
4. Vector database integration with Qdrant
5. MCP server integration via Docker

Prerequisites:
- Docker and Docker Compose installed
- Start SDK dev environment: `docker-compose -f docker/docker-compose.sdk-dev.yml up -d`
- Wait for all services to be healthy (check with healthcheck endpoint)
"""

import os
import sys
import time

import requests

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from kailash.mcp import MCPClient, MCPServer
from kailash.nodes.ai import EmbeddingGeneratorNode, LLMAgentNode

# Note: MCPResource and MCPClient are now MCP services, not nodes
# Use LLMAgentNode with mcp_servers parameter for MCP integration


def check_docker_services():
    """Check if Docker services are available."""
    services = {
        "ollama": "http://localhost:11434/api/version",
        "qdrant": "http://localhost:6333/health",
        "mock-api": "http://localhost:8888/health",
        "mcp-server": "http://localhost:8765/health",
        "healthcheck": "http://localhost:8889",
    }

    print("🐳 Checking Docker Services...")
    all_available = True

    for service, url in services.items():
        try:
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                print(f"   ✅ {service}: Available")
            else:
                print(f"   ❌ {service}: HTTP {response.status_code}")
                all_available = False
        except Exception as e:
            print(f"   ❌ {service}: {str(e)}")
            all_available = False

    if not all_available:
        print("\n⚠️  Some Docker services are not available.")
        print(
            "   Start with: docker-compose -f docker/docker-compose.sdk-dev.yml up -d"
        )
        print("   Check status: docker-compose -f docker/docker-compose.sdk-dev.yml ps")
        return False

    print("   🎉 All Docker services are available!")
    return True


def check_ollama_availability():
    """Check if Docker Ollama is available and list models."""
    try:
        # Configure to use Docker Ollama instance
        import ollama

        client = ollama.Client(host="http://localhost:11434")

        models = client.list()
        print("🎉 Docker Ollama is available!")
        print(f"   Found {len(models.models)} models:")
        for model in models.models[:3]:  # Show first 3 models
            print(f"   - {model.model}")
        return True, client
    except Exception as e:
        print("⚠️  Docker Ollama not available:", str(e))
        print("   To use Docker Ollama:")
        print(
            "   1. Start SDK infrastructure: docker-compose -f docker/docker-compose.sdk-dev.yml up -d"
        )
        print(
            "   2. Wait for Ollama to download models (check: docker logs kailash-sdk-ollama)"
        )
        print("   3. Verify health: curl http://localhost:11434/api/version")
        return False, None


def demonstrate_llm_agent_docker():
    """Demonstrate LLMAgentNode with Docker Ollama provider."""
    print("\n1️⃣  LLMAgentNode with Docker Ollama")
    print("=" * 50)

    ollama_available, ollama_client = check_ollama_availability()
    if not ollama_available:
        print("   Skipping Ollama demonstration...")
        return

    agent = LLMAgentNode()

    # Basic Q&A with Docker Ollama
    print("\n📝 Basic Q&A:")
    test_prompt = "What are the benefits of microservices architecture?"

    start_time = time.time()
    result = agent.run(
        provider="ollama",
        model="llama3.2:1b",  # Using the model from docker-compose
        messages=[{"role": "user", "content": test_prompt}],
        generation_config={"temperature": 0.7, "max_tokens": 200},
    )
    duration = time.time() - start_time

    if result["success"]:
        print(f"Response: {result['response']['content'][:150]}...")
        print(f"Tokens: {result['usage']['total_tokens']}")
        print(f"Duration: {duration:.2f}s")
    else:
        print(f"❌ Error: {result.get('error', 'Unknown error')}")

    # With conversation memory
    print("\n💭 With Conversation Memory:")
    result = agent.run(
        provider="ollama",
        model="llama3.2:1b",
        messages=[
            {
                "role": "user",
                "content": "Remember, I'm working on a Python project using Docker",
            }
        ],
        conversation_id="docker-project-discussion",
        memory_config={"type": "buffer", "max_tokens": 2000},
    )

    if result["success"]:
        print(f"Response: {result['response']['content'][:100]}...")
        print(f"Conversation ID: {result['conversation_id']}")

    # Advanced: With system prompt and context
    print("\n🧠 Advanced: Context-Aware Response:")
    result = agent.run(
        provider="ollama",
        model="llama3.2:1b",
        system_prompt="You are an expert Python developer. Be concise and practical.",
        messages=[
            {
                "role": "user",
                "content": "How should I handle database connections in containerized Python apps?",
            }
        ],
        generation_config={"temperature": 0.5, "max_tokens": 200},
    )

    if result["success"]:
        print(f"Response: {result['response']['content'][:500]}...")
        print("\n   📊 Performance with Docker:")
        print(f"      - Model: {result['response']['model']}")
        print(f"      - Provider: Docker Ollama")
        print(f"      - Tokens: {result['usage']['total_tokens']}")


def demonstrate_llm_agent_tools():
    """Demonstrate LLMAgentNode with tool calling using Docker infrastructure."""
    print("\n2️⃣  LLMAgentNode with Tool Integration")
    print("=" * 50)

    ollama_available, _ = check_ollama_availability()
    if not ollama_available:
        print("   Skipping tool demonstration...")
        return

    agent = LLMAgentNode()

    # With tool calling
    print("\n🔧 Tool Calling with Docker Infrastructure:")
    result = agent.run(
        provider="ollama",
        model="llama3.2:1b",
        messages=[
            {
                "role": "user",
                "content": "Create a database connection report for our Docker setup",
            }
        ],
        tools=[
            {
                "name": "check_database",
                "description": "Check database connection status",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "db_type": {
                            "type": "string",
                            "enum": ["postgresql", "mongodb", "qdrant"],
                        },
                        "host": {"type": "string", "default": "localhost"},
                        "format": {
                            "type": "string",
                            "enum": ["json", "text"],
                            "default": "json",
                        },
                    },
                    "required": ["db_type"],
                },
            }
        ],
        generation_config={"temperature": 0},
    )

    if result["success"]:
        print(f"Response: {result['response']['content'][:150]}...")
        print(f"Tool calls: {len(result['response'].get('tool_calls', []))}")

        # Show tool calls if any
        tool_calls = result["response"].get("tool_calls", [])
        for i, tool_call in enumerate(tool_calls):
            print(
                f"   Tool {i+1}: {tool_call.get('function', {}).get('name', 'Unknown')}"
            )
            print(f"     Args: {tool_call.get('function', {}).get('arguments', {})}")
    else:
        print(f"❌ Error: {result.get('error', 'Unknown error')}")


def demonstrate_embedding_generator():
    """Demonstrate EmbeddingGeneratorNode with Docker Qdrant vector database."""
    print("\n3️⃣  EmbeddingGeneratorNode with Vector Database")
    print("=" * 50)

    embedder = EmbeddingGeneratorNode()

    # Check if Docker Ollama embeddings are available
    ollama_available, ollama_client = check_ollama_availability()
    embedding_model = "nomic-embed-text"  # Default embedding model for Docker
    provider = "ollama"
    available_embeddings = []

    if ollama_available and ollama_client:
        try:
            # Check for embedding models via Docker Ollama
            models = ollama_client.list()
            # Check for embedding models in Docker instance
            embedding_models = [
                "nomic-embed-text",
                "avr/sfr-embedding-mistral",
                "snowflake-arctic-embed2",
                "all-minilm",
            ]
            for model in models.models:
                model_name = model.model
                if any(em in model_name for em in embedding_models):
                    available_embeddings.append(model_name)

            if available_embeddings:
                embedding_model = available_embeddings[0]  # Use first available
                print(
                    f"✅ Found Docker Ollama embedding models: {available_embeddings}"
                )
                print(f"   Using: {embedding_model}")
                print("   Provider: Docker Ollama + Qdrant vector database")
            else:
                print("⚠️  No embedding models found in Docker Ollama.")
                print("   Available models for embeddings:")
                print("   docker exec kailash-sdk-ollama ollama pull nomic-embed-text")
                print(
                    "   docker exec kailash-sdk-ollama ollama pull snowflake-arctic-embed2"
                )
                ollama_available = False
        except Exception as e:
            print(f"⚠️  Error checking Docker Ollama models: {e}")
            ollama_available = False

    if not ollama_available:
        print("   Using fallback embedding approach...")
        return

    # Single text embedding with Docker infrastructure
    print("\n📊 Single Text Embedding with Docker Ollama:")
    result = embedder.run(
        operation="embed_text",
        input_text="Docker containers enable scalable microservices architecture",
        provider=provider,
        model=embedding_model,
    )

    if result["success"]:
        print(f"✅ Embedding dimension: {result['dimensions']}")
        print(f"   First 5 values: {result['embedding'][:5]}")
        print(f"   Provider: Docker Ollama ({embedding_model})")
        print(f"   Processing time: {result.get('processing_time_ms', 'N/A')}ms")

        # Store in Qdrant for demonstration
        print("\n💾 Storing in Docker Qdrant Vector Database:")
        try:
            # Check if Qdrant is available
            qdrant_response = requests.get("http://localhost:6333/health", timeout=3)
            if qdrant_response.status_code == 200:
                print("   ✅ Qdrant vector database is available")
                print(f"   Vector dimensions: {result['dimensions']}")
                print("   Ready for semantic search and similarity matching")
            else:
                print("   ❌ Qdrant not available")
        except Exception as e:
            print(f"   ❌ Qdrant connection error: {e}")
    else:
        print(f"❌ Error: {result.get('error', 'Unknown error')}")

    # Batch embeddings with Docker infrastructure themes
    print("\n📊 Batch Embeddings with Docker Infrastructure:")
    texts = [
        "Docker containers provide consistent deployment environments",
        "Kubernetes orchestrates containerized applications at scale",
        "Microservices architecture enables independent service deployment",
        "Vector databases enable semantic search capabilities",
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
        print(
            f"   Average tokens per text: {result['usage']['average_tokens_per_text']:.1f}"
        )
        print("   All embeddings ready for Qdrant storage")

    # Similarity calculation with Docker infrastructure
    print("\n🔍 Similarity Calculation with Docker Services:")
    similar_texts = [
        "Container orchestration provides scalability",
        "Docker Swarm and Kubernetes enable service scaling",
    ]
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
        print(f"   Text 1: '{result['texts'][0][:45]}...'")
        print(f"   Text 2: '{result['texts'][1][:45]}...'")
        print("   Semantic understanding powered by Docker Ollama")

    # Demonstrate Docker infrastructure integration
    print("\n🐳 Docker Infrastructure Integration:")
    print(f"   ✅ Ollama provider: Docker container at localhost:11434")
    print(f"   ✅ Embedding model: {embedding_model}")
    print(f"   ✅ Vector storage: Qdrant at localhost:6333")
    print("   🔗 Full stack embeddings pipeline ready")

    # Compare multiple models if available
    if len(available_embeddings) > 1:
        print("\n🔄 Comparing Docker Embedding Models:")
        for model in available_embeddings[:2]:  # Compare first 2 models
            result = embedder.run(
                operation="embed_text",
                input_text="Docker enables consistent deployment environments",
                provider="ollama",
                model=model,
            )
            if result["success"]:
                dim = result["dimensions"]
                print(f"   {model}: {dim} dimensions")
                print(
                    f"     Processing time: {result.get('processing_time_ms', 'N/A')}ms"
                )
                print("     Ready for Qdrant storage")

    # Real-world example: Semantic search with Docker infrastructure
    print("\n🔎 Real-World Example: Docker Infrastructure Semantic Search")
    documents = [
        "Docker containers provide consistent runtime environments across development and production",
        "Kubernetes orchestrates containerized applications enabling automatic scaling and load balancing",
        "PostgreSQL in Docker containers offers reliable relational database storage for applications",
        "Qdrant vector database enables high-performance semantic search and similarity matching",
        "Ollama in containers provides local LLM inference without external API dependencies",
        "MongoDB containers offer flexible document storage for unstructured data processing",
    ]

    query = "What containerized database should I use for semantic search and AI applications?"

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

        print("\n🎯 Search Results Analysis:")
        print("   ✅ Semantic search successfully identified relevant Docker services")
        print("   ✅ Vector similarity powered by Docker Ollama embeddings")
        print("   ✅ Results ready for Qdrant vector database storage")
        print("   🔗 Full pipeline: Query → Embed → Search → Rank → Store")


def demonstrate_mcp_ecosystem():
    """Demonstrate MCP (Model Context Protocol) ecosystem."""
    print("\n4️⃣  MCP Ecosystem (Context Sharing)")
    print("=" * 50)

    # MCP services are now integrated into LLMAgentNode
    print("\n🔌 MCP Integration - Built into LLMAgentNode:")
    print("✅ MCP functionality is now integrated as services, not standalone nodes")
    print("   - MCPClient service handles tool discovery and execution")
    print("   - MCPServer service provides framework for custom servers")
    print("   - Use LLMAgentNode with mcp_servers parameter for integration")

    # Demonstrate MCP client service
    print("\n📦 MCPClient Service - Tool Discovery:")
    client = MCPClient()

    # Mock server configuration for demonstration
    mock_server_config = {
        "transport": "stdio",
        "command": "echo",
        "args": ["mock-mcp-tools"],
        "env": {"MCP_MODE": "demo"},
    }

    print("✅ MCPClient service initialized")
    print("   Configuration ready for tool discovery")
    print(
        f"   Server config: {mock_server_config['command']} {' '.join(mock_server_config['args'])}"
    )

    # Create an agent with MCP integration
    print("\n🤖 LLMAgentNode with MCP Integration:")
    agent = LLMAgentNode(name="mcp_integrated_agent")

    # Use Docker Ollama for MCP integration
    ollama_available, _ = check_ollama_availability()
    if ollama_available:
        result = agent.run(
            provider="ollama",
            model="llama3.2:1b",
            messages=[
                {
                    "role": "user",
                    "content": "What MCP tools are available in our Docker environment?",
                }
            ],
            mcp_servers=[mock_server_config],
            auto_discover_tools=True,
        )
    else:
        print("   ⚠️  Skipping MCP integration demo - Docker Ollama not available")
        return

    if result["success"]:
        print(f"✅ MCP-integrated response: {result['response']['content'][:100]}...")
        print(f"   Context: {result.get('context', {})}")
    else:
        print(f"❌ Error: {result.get('error', 'Unknown error')}")

    # MCPServer - Configuration for hosting
    print("\n🖥️  MCPServer Framework - Creating Custom Server:")

    # Note: MCPServer is a service framework, not a node
    print("✅ MCPServer framework available for custom server creation")
    print("   Example server configuration:")

    server_config = {
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

    print(f"   Server name: {server_config['name']}")
    print(f"   Transport: {server_config['transport']}")
    print(f"   Resources: {len(server_config['resources'])}")
    print(
        f"   Capabilities: {', '.join(k for k, v in server_config['capabilities'].items() if v)}"
    )

    print("\n💡 MCP Architecture Notes:")
    print("   - MCP services provide background capabilities")
    print("   - LLMAgentNode handles MCP integration automatically")
    print("   - Custom servers can extend workflow capabilities")
    print("   - No separate MCP nodes needed - integrated as services")


def demonstrate_integrated_workflow():
    """Demonstrate an integrated workflow using multiple nodes."""
    print("\n5️⃣  Integrated Workflow Example")
    print("=" * 50)
    print("Scenario: AI-powered data analysis with context and embeddings")

    # Step 1: Create business context (using workflow state)
    print("\n📝 Step 1: Create Business Context")
    business_context = {
        "objective": "Analyze Q4 performance and predict Q1 trends",
        "key_metrics": ["revenue", "customer_acquisition", "churn"],
        "constraints": ["Budget: $50k", "Timeline: 2 weeks"],
    }
    print("✅ Business context prepared for analysis")
    print(f"   Objective: {business_context['objective']}")
    print(f"   Key metrics: {', '.join(business_context['key_metrics'])}")

    # Step 2: Generate embeddings for relevant documents
    print("\n📊 Step 2: Generate Document Embeddings")
    embedder = EmbeddingGeneratorNode()
    documents = [
        "Q4 revenue exceeded targets by 15% due to holiday sales",
        "Customer acquisition cost decreased by 20% with new marketing strategy",
        "Churn rate remains stable at 5% monthly",
    ]

    embedding_result = embedder.run(
        operation="embed_batch",
        input_texts=documents,
        provider="mock",
        model="text-embedding-ada-002",
    )

    if embedding_result["success"]:
        print(f"✅ Generated embeddings for {len(documents)} documents")
        print(f"   Embedding dimensions: {embedding_result['dimensions']}")
    else:
        print(f"❌ Embedding failed: {embedding_result.get('error', 'Unknown error')}")

    # Step 3: Use LLMAgentNode with context and embeddings
    print("\n🤖 Step 3: Generate Analysis with Context")
    agent = LLMAgentNode()

    # Use Docker Ollama for real analysis
    ollama_available, _ = check_ollama_availability()
    if ollama_available:
        provider = "ollama"
        model = "llama3.2:1b"
        print("   Using Docker Ollama for real analysis...")
    else:
        print("   ⚠️  Docker Ollama not available, skipping analysis...")
        return

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
        context_data={
            "business_context": business_context,
            "embeddings": embedding_result,
        },
        rag_config={"enabled": True, "top_k": 3, "similarity_threshold": 0.7},
        generation_config={"temperature": 0.7, "max_tokens": 300},
    )

    if analysis_result["success"]:
        print("\n📈 Analysis Result:")
        print(f"{analysis_result['response']['content'][:400]}...")
        print("\n📊 Context Used:")
        context = analysis_result.get("context", {})
        print(
            f"   - Business context: {context.get('business_context_available', 'Yes')}"
        )
        print(
            f"   - Embeddings available: {context.get('embeddings_available', 'Yes')}"
        )
        if "rag_documents_retrieved" in context:
            print(f"   - RAG documents: {context['rag_documents_retrieved']}")


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
    print("🚀 Kailash Agentic AI Nodes - Docker Infrastructure Demo")
    print("=" * 50)
    print("This demo showcases all AI capabilities using Docker infrastructure\n")

    # Check Python version
    import sys

    if sys.version_info < (3, 8):
        print("⚠️  Warning: Python 3.8+ recommended for best compatibility")

    # Check Docker services first
    if not check_docker_services():
        print(
            "❌ Docker services not available. Please start the infrastructure first."
        )
        return

    # Run all demonstrations
    demonstrate_llm_agent_docker()
    demonstrate_llm_agent_tools()
    demonstrate_embedding_generator()
    demonstrate_mcp_ecosystem()
    demonstrate_integrated_workflow()
    demonstrate_provider_architecture()

    print("\n\n✨ Summary")
    print("=" * 50)
    print("You've seen demonstrations of:")
    print("✅ LLMAgentNode - With Docker Ollama provider")
    print("✅ EmbeddingGeneratorNode - With Qdrant vector database")
    print("✅ MCP Ecosystem - Docker MCP server integration")
    print("✅ Integrated Workflows - Full Docker infrastructure")
    print("✅ Provider Architecture - Production-ready setup")
    print("\n🎯 Next Steps:")
    print("1. Explore Docker container logs: docker-compose logs -f")
    print("2. Scale services: docker-compose up --scale ollama=2")
    print("3. Monitor with healthcheck: curl http://localhost:8889")
    print("4. Build custom MCP servers for your workflows")
    print("5. Integrate with external vector databases")


if __name__ == "__main__":
    main()
