"""Advanced agentic AI workflow with LLMAgent and EmbeddingGenerator integration."""

import os
import sys

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from kailash.nodes.ai import EmbeddingGenerator, LLMAgent
from kailash.nodes.mcp import MCPResource
from kailash.workflow import WorkflowBuilder


def main():
    """Demonstrate advanced agentic AI workflows with LLM agents and embeddings."""
    print("🤖 Advanced Agentic AI Integration Example")
    print("=" * 55)

    # Create a workflow builder
    builder = WorkflowBuilder("agentic_ai_demo")

    # 1. Setup MCP Resources for AI Context
    print("\n📦 Step 1: Setting up MCP Resources for AI Context")

    # Create knowledge base resources
    knowledge_resource = MCPResource()
    kb_result = knowledge_resource.run(
        operation="create",
        uri="knowledge://base/customer_insights.md",
        content="""# Customer Insights Knowledge Base

## Customer Behavior Patterns
- Peak engagement hours: 9-11 AM, 2-4 PM
- Preferred communication channels: Email (60%), SMS (25%), Push (15%)
- Average session duration: 4.2 minutes
- Conversion rates vary by product category

## Product Categories
1. **Premium Products**: Higher margin, longer sales cycle
2. **Standard Products**: Volume drivers, quick decisions
3. **Budget Products**: Price-sensitive, promotion-driven

## Customer Segments
- **Power Users**: 20% of users, 60% of revenue
- **Regular Users**: 50% of users, 35% of revenue
- **Occasional Users**: 30% of users, 5% of revenue

## Best Practices
- Personalization increases conversion by 15%
- Multi-touch campaigns perform 3x better
- Mobile-first design is critical for Gen Z
""",
        metadata={
            "name": "Customer Insights Knowledge Base",
            "description": "Comprehensive customer behavior and business insights",
            "mimeType": "text/markdown",
            "tags": ["knowledge_base", "customer_insights", "best_practices"],
            "category": "business_intelligence",
        },
    )

    print(f"✅ Knowledge base created: {kb_result['success']}")

    # Create policy document
    policy_resource = MCPResource()
    policy_result = policy_resource.run(
        operation="create",
        uri="compliance://policies/data_handling.json",
        content={
            "policy_name": "Customer Data Handling Policy",
            "version": "2.1",
            "effective_date": "2024-01-01",
            "requirements": {
                "data_retention": "24 months maximum",
                "encryption": "AES-256 required for PII",
                "access_control": "Role-based with audit logging",
                "anonymization": "Required for analytics datasets",
            },
            "approved_uses": [
                "Customer service optimization",
                "Product recommendation engines",
                "Marketing campaign personalization",
                "Business analytics and reporting",
            ],
            "restricted_uses": [
                "Third-party data sharing without consent",
                "Profiling for discriminatory purposes",
                "Retention beyond business necessity",
            ],
        },
        metadata={
            "name": "Data Handling Policy",
            "description": "Compliance requirements for customer data",
            "mimeType": "application/json",
            "tags": ["compliance", "data_policy", "privacy"],
        },
    )

    print(f"✅ Policy document created: {policy_result['success']}")

    # 2. Generate Embeddings for Knowledge Base
    print("\n🔗 Step 2: Generating Embeddings for Semantic Search")

    embedder = EmbeddingGenerator()

    # Embed knowledge base sections
    kb_sections = [
        "Customer behavior patterns and engagement metrics",
        "Product categories and performance characteristics",
        "Customer segmentation and revenue distribution",
        "Marketing best practices and conversion optimization",
        "Data handling policies and compliance requirements",
    ]

    embeddings_result = embedder.run(
        operation="embed_batch",
        provider="openai",
        model="text-embedding-3-large",
        input_texts=kb_sections,
        batch_size=5,
        cache_enabled=True,
        normalize=True,
    )

    print(f"✅ Embeddings generated: {embeddings_result['success']}")
    if embeddings_result["success"]:
        print(f"   Total embeddings: {embeddings_result['total_embeddings']}")
        print(f"   Cache hit rate: {embeddings_result['cache_hit_rate']:.2%}")
        print(f"   Processing time: {embeddings_result['processing_time_ms']:.2f}ms")
        print(
            f"   Estimated cost: ${embeddings_result['usage']['estimated_cost_usd']:.6f}"
        )

    # 3. Basic Q&A Agent with MCP Context
    print("\n💬 Step 3: Basic Q&A Agent with MCP Context")

    llm_agent = LLMAgent()
    qa_result = llm_agent.run(
        provider="anthropic",
        model="claude-3-sonnet",
        messages=[
            {
                "role": "user",
                "content": "What are the key customer behavior patterns I should know about?",
            }
        ],
        system_prompt="You are a customer insights analyst. Use the provided knowledge base to give accurate, actionable insights.",
        mcp_context=["knowledge://base/customer_insights.md"],
        generation_config={"temperature": 0.7, "max_tokens": 500},
    )

    print(f"✅ Q&A response generated: {qa_result['success']}")
    if qa_result["success"]:
        response = qa_result["response"]
        print(f"   Model: {response['model']}")
        print(f"   Content: {response['content'][:200]}...")
        print(
            f"   Context used: {qa_result['context']['mcp_resources_used']} MCP resources"
        )
        print(f"   Tokens: {qa_result['usage']['total_tokens']}")

    # 4. Tool-Calling Agent for Report Generation
    print("\n🔧 Step 4: Tool-Calling Agent for Report Generation")

    # Define tools for the agent
    analysis_tools = [
        {
            "name": "analyze_customer_segment",
            "description": "Analyze specific customer segment performance",
            "parameters": {
                "type": "object",
                "properties": {
                    "segment": {
                        "type": "string",
                        "description": "Customer segment to analyze",
                    },
                    "metrics": {"type": "array", "description": "Metrics to include"},
                },
                "required": ["segment"],
            },
        },
        {
            "name": "generate_recommendations",
            "description": "Generate actionable business recommendations",
            "parameters": {
                "type": "object",
                "properties": {
                    "focus_area": {
                        "type": "string",
                        "description": "Business area to focus on",
                    },
                    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["focus_area"],
            },
        },
        {
            "name": "create_data_export",
            "description": "Create a data export for further analysis",
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": ["csv", "json", "excel"]},
                    "filters": {
                        "type": "object",
                        "description": "Data filters to apply",
                    },
                },
                "required": ["format"],
            },
        },
    ]

    tool_agent_result = llm_agent.run(
        provider="openai",
        model="gpt-4",
        messages=[
            {
                "role": "user",
                "content": "I need a comprehensive analysis of our power users segment and recommendations for improving their engagement.",
            }
        ],
        system_prompt="You are a business analyst with access to customer data tools. Use tools to gather insights and create actionable recommendations.",
        tools=analysis_tools,
        mcp_context=["knowledge://base/customer_insights.md"],
        conversation_id="power_user_analysis_session",
        memory_config={"type": "buffer", "max_tokens": 2000},
    )

    print(f"✅ Tool-calling agent executed: {tool_agent_result['success']}")
    if tool_agent_result["success"]:
        response = tool_agent_result["response"]
        print(f"   Response: {response['content'][:200]}...")
        print(f"   Tools available: {tool_agent_result['context']['tools_available']}")
        print(f"   Tool calls made: {len(response.get('tool_calls', []))}")
        print(f"   Conversation ID: {tool_agent_result['conversation_id']}")

    # 5. RAG Agent with Semantic Search
    print("\n🔍 Step 5: RAG Agent with Semantic Search")

    # First, find relevant information using similarity search
    query_embedding = embedder.run(
        operation="embed_text",
        provider="openai",
        model="text-embedding-3-large",
        input_text="What are the compliance requirements for customer data analytics?",
        cache_enabled=True,
    )

    if query_embedding["success"]:
        # Compare with knowledge base embeddings
        similarities = []
        for i, kb_section in enumerate(kb_sections):
            if i < len(embeddings_result.get("embeddings", [])):
                kb_embedding = embeddings_result["embeddings"][i]["embedding"]
                similarity = embedder.run(
                    operation="calculate_similarity",
                    embedding_1=query_embedding["embedding"],
                    embedding_2=kb_embedding,
                    similarity_metric="cosine",
                )
                if similarity["success"]:
                    similarities.append(
                        {"section": kb_section, "similarity": similarity["similarity"]}
                    )

        # Sort by similarity
        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        print(f"   Most relevant sections found: {len(similarities)}")
        for sim in similarities[:3]:
            print(f"   - {sim['section'][:50]}... (score: {sim['similarity']:.3f})")

    # RAG agent with retrieved context
    rag_result = llm_agent.run(
        provider="anthropic",
        model="claude-3-haiku",
        messages=[
            {
                "role": "user",
                "content": "What compliance requirements should I consider when setting up customer analytics dashboards?",
            }
        ],
        system_prompt="You are a compliance expert. Provide specific, actionable guidance based on the retrieved policy documents.",
        rag_config={"enabled": True, "top_k": 3, "similarity_threshold": 0.7},
        mcp_context=[
            "compliance://policies/data_handling.json",
            "knowledge://base/customer_insights.md",
        ],
    )

    print(f"✅ RAG agent response: {rag_result['success']}")
    if rag_result["success"]:
        response = rag_result["response"]
        print(f"   Content: {response['content'][:250]}...")
        print(f"   RAG documents: {rag_result['context']['rag_documents_retrieved']}")
        print(
            f"   Total context: {rag_result['context']['mcp_resources_used']} MCP resources"
        )

    # 6. Multi-turn Conversation with Memory
    print("\n💭 Step 6: Multi-turn Conversation with Memory")

    conversation_id = "customer_strategy_session"

    # First turn
    turn1 = llm_agent.run(
        provider="openai",
        model="gpt-4-turbo",
        messages=[
            {
                "role": "user",
                "content": "I'm planning a new customer retention campaign. What should I consider?",
            }
        ],
        system_prompt="You are a marketing strategist. Build on previous conversations and provide contextual advice.",
        conversation_id=conversation_id,
        memory_config={"type": "buffer", "max_tokens": 3000, "persistence": True},
        mcp_context=["knowledge://base/customer_insights.md"],
    )

    # Second turn - builds on first
    turn2 = llm_agent.run(
        provider="openai",
        model="gpt-4-turbo",
        messages=[
            {
                "role": "user",
                "content": "Focus specifically on power users. What retention strategies work best for them?",
            }
        ],
        conversation_id=conversation_id,
        memory_config={"type": "buffer", "max_tokens": 3000, "persistence": True},
        mcp_context=["knowledge://base/customer_insights.md"],
    )

    print(
        f"✅ Multi-turn conversation: Turn 1 - {turn1['success']}, Turn 2 - {turn2['success']}"
    )
    if turn2["success"]:
        print(f"   Conversation ID: {turn2['conversation_id']}")
        print(f"   Memory tokens: {turn2['context']['memory_tokens']}")
        print(f"   Response: {turn2['response']['content'][:200]}...")

    # 7. Advanced Agent with Multiple Capabilities
    print("\n🎯 Step 7: Advanced Multi-Modal Agent")

    advanced_result = llm_agent.run(
        provider="anthropic",
        model="claude-3-sonnet",
        messages=[
            {
                "role": "user",
                "content": "Create a complete customer engagement strategy document with data analysis, compliance considerations, and implementation timeline.",
            }
        ],
        system_prompt="""You are a senior business consultant with expertise in:
        - Customer analytics and segmentation
        - Marketing strategy and campaign optimization
        - Data privacy and compliance requirements
        - Implementation planning and project management

        Provide comprehensive, actionable recommendations with specific steps and timelines.""",
        tools=analysis_tools,
        mcp_context=[
            "knowledge://base/customer_insights.md",
            "compliance://policies/data_handling.json",
        ],
        rag_config={"enabled": True, "top_k": 5, "similarity_threshold": 0.6},
        conversation_id="strategy_development",
        generation_config={"temperature": 0.8, "max_tokens": 1500},
        streaming=False,
    )

    print(f"✅ Advanced agent strategy: {advanced_result['success']}")
    if advanced_result["success"]:
        response = advanced_result["response"]
        print(f"   Strategy document length: {len(response['content'])} characters")
        print(f"   Provider: {advanced_result['metadata']['provider']}")
        print(f"   Model: {advanced_result['metadata']['model']}")
        print(f"   Tools available: {advanced_result['context']['tools_available']}")
        print(
            f"   Context sources: MCP={advanced_result['context']['mcp_resources_used']}, RAG={advanced_result['context']['rag_documents_retrieved']}"
        )
        print(f"   Total cost: ${advanced_result['usage']['estimated_cost_usd']:.6f}")

    # 8. Summary and Performance Metrics
    print("\n📊 Integration Summary & Performance")
    print("=" * 55)

    # Calculate total costs and performance
    total_llm_cost = sum(
        [
            result.get("usage", {}).get("estimated_cost_usd", 0)
            for result in [
                qa_result,
                tool_agent_result,
                rag_result,
                turn1,
                turn2,
                advanced_result,
            ]
            if result.get("success")
        ]
    )

    total_embedding_cost = embeddings_result.get("usage", {}).get(
        "estimated_cost_usd", 0
    )

    print("✅ Agentic AI Components Demonstrated:")
    print("   🤖 LLMAgent: Q&A, tool-calling, RAG, memory, multi-modal")
    print("   🔗 EmbeddingGenerator: Batch processing, caching, similarity")
    print("   📦 MCP Integration: Context sharing, resource management")
    print("   💭 Conversation Memory: Persistent multi-turn dialogs")
    print("   🔧 Tool Calling: Dynamic function execution")
    print("   🔍 RAG: Semantic search and retrieval")

    print("\n💰 Performance Metrics:")
    print(f"   LLM API Cost: ${total_llm_cost:.6f}")
    print(f"   Embedding Cost: ${total_embedding_cost:.6f}")
    print(f"   Total Cost: ${total_llm_cost + total_embedding_cost:.6f}")
    print(f"   Cache Hit Rate: {embeddings_result.get('cache_hit_rate', 0):.2%}")
    print(
        f"   Conversations: {len(set([turn1.get('conversation_id'), turn2.get('conversation_id'), advanced_result.get('conversation_id')]))}"
    )

    print("\n🚀 Agentic AI integration is fully operational!")
    print("   Ready for production AI agent workflows")


if __name__ == "__main__":
    main()
