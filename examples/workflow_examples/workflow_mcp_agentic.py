"""Complete MCP and Agentic AI workflow demonstrating end-to-end agent coordination."""

import os
import sys

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from kailash.nodes.ai import EmbeddingGenerator, LLMAgent
from kailash.nodes.mcp import MCPClient, MCPResource, MCPServer
from kailash.workflow import WorkflowBuilder


def main():
    """Demonstrate complete MCP and agentic AI workflow with agent coordination."""
    print("🤖 MCP + Agentic AI Complete Workflow")
    print("=" * 50)

    # Create workflow builder
    builder = WorkflowBuilder("mcp_agentic_complete")

    # 1. Setup MCP Server with Workflow Resources
    print("\n🖥️  Step 1: Setting up MCP Server")

    # Define resources to expose via MCP
    workflow_resources = [
        {
            "uri": "workflow://data/customer_segments.csv",
            "name": "Customer Segments",
            "content": "segment,count,revenue,avg_ltv\nPower Users,3084,1470000,476.23\nRegular Users,7710,857500,111.27\nOccasional Users,4626,122500,26.49",
            "mimeType": "text/csv",
        },
        {
            "uri": "workflow://config/analysis_params.json",
            "name": "Analysis Parameters",
            "content": {
                "analysis_type": "customer_segmentation",
                "time_period": "Q4_2024",
                "metrics": ["revenue", "engagement", "retention"],
                "thresholds": {
                    "high_value": 1000,
                    "engagement_min": 0.3,
                    "retention_target": 0.85,
                },
            },
            "mimeType": "application/json",
        },
    ]

    # Define tools for MCP server
    workflow_tools = [
        {
            "name": "segment_customers",
            "description": "Segment customers based on behavior and value",
            "parameters": {
                "type": "object",
                "properties": {
                    "criteria": {
                        "type": "string",
                        "description": "Segmentation criteria",
                    },
                    "output_format": {"type": "string", "enum": ["csv", "json"]},
                },
                "required": ["criteria"],
            },
        },
        {
            "name": "calculate_metrics",
            "description": "Calculate customer metrics and KPIs",
            "parameters": {
                "type": "object",
                "properties": {
                    "metrics": {
                        "type": "array",
                        "description": "List of metrics to calculate",
                    },
                    "segment": {
                        "type": "string",
                        "description": "Customer segment to analyze",
                    },
                },
                "required": ["metrics"],
            },
        },
    ]

    # Create MCP server
    mcp_server = MCPServer()
    server_result = mcp_server.run(
        server_config={"name": "kailash-workflow-server", "transport": "stdio"},
        resources=workflow_resources,
        tools=workflow_tools,
        auto_start=True,
    )

    print(f"✅ MCP Server configured: {server_result['success']}")
    if server_result["success"]:
        server_info = server_result["server"]
        print(f"   Server: {server_info['name']}")
        print(f"   Resources: {server_result['resources']['count']}")
        print(f"   Tools: {server_result['tools']['count']}")
        print(f"   Status: {server_info['status']}")

    # 2. Create Knowledge Base with Embeddings
    print("\n📚 Step 2: Building Knowledge Base with Embeddings")

    # Create knowledge documents
    knowledge_docs = [
        "Customer segmentation best practices: Focus on behavioral patterns, transaction frequency, and lifetime value to create meaningful segments.",
        "Power users typically generate 60% of revenue with 20% of user base. They prefer premium features and direct communication channels.",
        "Regular users respond well to promotional campaigns and feature education. Email marketing shows 3x better performance than push notifications.",
        "Occasional users need re-engagement campaigns. Personalized offers and simplified onboarding improve conversion rates by 25%.",
        "Retention strategies: Implement progressive profiling, loyalty programs, and predictive churn models for different segments.",
        "Data privacy compliance: Always anonymize personal data in analytics, implement proper consent management, and maintain audit trails.",
    ]

    # Generate embeddings for knowledge base
    embedder = EmbeddingGenerator()
    kb_embeddings = embedder.run(
        operation="embed_batch",
        provider="openai",
        model="text-embedding-3-large",
        input_texts=knowledge_docs,
        batch_size=6,
        cache_enabled=True,
        normalize=True,
    )

    print(f"✅ Knowledge base embeddings: {kb_embeddings['success']}")
    if kb_embeddings["success"]:
        print(f"   Documents embedded: {kb_embeddings['total_embeddings']}")
        print(f"   Processing time: {kb_embeddings['processing_time_ms']:.2f}ms")
        print(f"   Cache efficiency: {kb_embeddings['cache_hit_rate']:.2%}")

    # Store knowledge base as MCP resource
    kb_resource = MCPResource()
    kb_result = kb_resource.run(
        operation="create",
        uri="knowledge://base/customer_analytics.json",
        content={
            "documents": knowledge_docs,
            "embeddings": [
                emb["embedding"] for emb in kb_embeddings.get("embeddings", [])
            ],
            "metadata": {
                "created_at": "2025-06-01T12:00:00Z",
                "embedding_model": "text-embedding-3-large",
                "dimensions": 3072,
                "total_docs": len(knowledge_docs),
            },
        },
        metadata={
            "name": "Customer Analytics Knowledge Base",
            "description": "Embedded knowledge base for AI agent context",
            "tags": ["knowledge", "embeddings", "customer_analytics"],
        },
    )

    print(f"✅ Knowledge base resource: {kb_result['success']}")

    # 3. Setup Agent Coordination System
    print("\n🤝 Step 3: Setting up Agent Coordination")

    # Configure MCP client for agent communication
    mcp_client = MCPClient()
    server_config = {"name": "kailash-workflow-server", "transport": "stdio"}

    # Data Analysis Agent
    analysis_agent = LLMAgent()

    # Strategy Agent
    strategy_agent = LLMAgent()

    # Recommendation Agent
    recommendation_agent = LLMAgent()

    # 4. Execute Multi-Agent Workflow
    print("\n🔄 Step 4: Executing Multi-Agent Workflow")

    # Agent 1: Data Analysis
    print("   🔍 Agent 1: Data Analysis")

    analysis_result = analysis_agent.run(
        provider="anthropic",
        model="claude-3-sonnet",
        messages=[
            {
                "role": "user",
                "content": "Analyze the customer segmentation data and identify key patterns and insights.",
            }
        ],
        system_prompt="""You are a data analyst expert. Analyze customer data to identify:
        1. Segment performance metrics
        2. Revenue distribution patterns
        3. Customer value indicators
        4. Key business insights

        Provide specific, data-driven observations.""",
        mcp_servers=[server_config],
        mcp_context=["workflow://data/customer_segments.csv"],
        conversation_id="data_analysis_session",
        generation_config={"temperature": 0.3, "max_tokens": 800},
    )

    print(f"   ✅ Analysis complete: {analysis_result['success']}")
    if analysis_result["success"]:
        analysis_insights = analysis_result["response"]["content"]
        print(f"      Insights length: {len(analysis_insights)} characters")

    # Agent 2: Strategy Development (uses analysis results)
    print("   📈 Agent 2: Strategy Development")

    # Embed the analysis insights for context
    analysis_embedding = embedder.run(
        operation="embed_text",
        provider="openai",
        model="text-embedding-3-large",
        input_text=(
            analysis_insights
            if analysis_result["success"]
            else "Customer analysis pending"
        ),
        cache_enabled=True,
    )

    # Find relevant knowledge base entries
    relevant_knowledge = []
    if analysis_embedding["success"] and kb_embeddings["success"]:
        for i, kb_emb in enumerate(kb_embeddings["embeddings"]):
            similarity = embedder.run(
                operation="calculate_similarity",
                embedding_1=analysis_embedding["embedding"],
                embedding_2=kb_emb["embedding"],
                similarity_metric="cosine",
            )
            if similarity["success"] and similarity["similarity"] > 0.7:
                relevant_knowledge.append(
                    {
                        "content": knowledge_docs[i],
                        "similarity": similarity["similarity"],
                    }
                )

    # Sort by relevance
    relevant_knowledge.sort(key=lambda x: x["similarity"], reverse=True)
    context_docs = [doc["content"] for doc in relevant_knowledge[:3]]

    strategy_result = strategy_agent.run(
        provider="openai",
        model="gpt-4",
        messages=[
            {
                "role": "user",
                "content": f"Based on this data analysis, develop a comprehensive customer engagement strategy:\n\n{analysis_insights[:500]}...",
            }
        ],
        system_prompt="""You are a business strategy consultant. Based on data analysis results, create:
        1. Strategic objectives for each customer segment
        2. Engagement tactics and channel preferences
        3. Revenue optimization opportunities
        4. Implementation priorities

        Use the knowledge base context to inform your recommendations.""",
        rag_config={"enabled": True, "top_k": 3, "similarity_threshold": 0.7},
        mcp_context=["knowledge://base/customer_analytics.json"],
        conversation_id="strategy_session",
        generation_config={"temperature": 0.7, "max_tokens": 1000},
    )

    print(f"   ✅ Strategy developed: {strategy_result['success']}")
    if strategy_result["success"]:
        strategy_content = strategy_result["response"]["content"]
        print(f"      Strategy length: {len(strategy_content)} characters")
        print(
            f"      Context used: {strategy_result['context']['rag_documents_retrieved']} docs"
        )

    # Agent 3: Recommendations and Implementation (uses both previous results)
    print("   💡 Agent 3: Implementation Recommendations")

    tools = [
        {
            "name": "create_campaign_plan",
            "description": "Create detailed campaign implementation plan",
            "parameters": {
                "type": "object",
                "properties": {
                    "segment": {"type": "string"},
                    "timeline": {"type": "string"},
                    "budget": {"type": "number"},
                },
                "required": ["segment", "timeline"],
            },
        },
        {
            "name": "estimate_roi",
            "description": "Estimate return on investment for strategy",
            "parameters": {
                "type": "object",
                "properties": {
                    "investment": {"type": "number"},
                    "timeframe": {"type": "string"},
                },
                "required": ["investment"],
            },
        },
    ]

    combined_context = f"""
    ANALYSIS RESULTS:
    {analysis_insights[:800] if analysis_result['success'] else 'Analysis pending'}

    STRATEGY RECOMMENDATIONS:
    {strategy_content[:800] if strategy_result['success'] else 'Strategy pending'}
    """

    recommendation_result = recommendation_agent.run(
        provider="anthropic",
        model="claude-3-haiku",
        messages=[
            {
                "role": "user",
                "content": f"Create specific, actionable implementation recommendations based on this analysis and strategy:\n\n{combined_context}",
            }
        ],
        system_prompt="""You are an implementation specialist. Create:
        1. Specific action items with timelines
        2. Resource requirements and budget estimates
        3. Success metrics and KPIs
        4. Risk mitigation strategies
        5. Quick wins vs long-term initiatives

        Use tools to create detailed plans and ROI estimates.""",
        tools=tools,
        mcp_servers=[server_config],
        conversation_id="implementation_session",
        generation_config={"temperature": 0.8, "max_tokens": 1200},
    )

    print(f"   ✅ Recommendations created: {recommendation_result['success']}")
    if recommendation_result["success"]:
        recommendations = recommendation_result["response"]["content"]
        print(f"      Recommendations: {len(recommendations)} characters")
        print(
            f"      Tools used: {len(recommendation_result['response'].get('tool_calls', []))}"
        )

    # 5. Consolidate Results and Create Final Report
    print("\n📋 Step 5: Consolidating Multi-Agent Results")

    # Create final consolidated report
    final_report = {
        "workflow_id": "mcp_agentic_complete",
        "timestamp": "2025-06-01T12:00:00Z",
        "agents_involved": 3,
        "analysis": {
            "agent": "Data Analysis Agent",
            "model": "claude-3-sonnet",
            "insights": analysis_insights if analysis_result["success"] else "Failed",
            "tokens_used": analysis_result.get("usage", {}).get("total_tokens", 0),
        },
        "strategy": {
            "agent": "Strategy Agent",
            "model": "gpt-4",
            "recommendations": (
                strategy_content if strategy_result["success"] else "Failed"
            ),
            "context_sources": strategy_result.get("context", {}).get(
                "rag_documents_retrieved", 0
            ),
            "tokens_used": strategy_result.get("usage", {}).get("total_tokens", 0),
        },
        "implementation": {
            "agent": "Implementation Agent",
            "model": "claude-3-haiku",
            "action_plan": (
                recommendations if recommendation_result["success"] else "Failed"
            ),
            "tool_calls": len(
                recommendation_result.get("response", {}).get("tool_calls", [])
            ),
            "tokens_used": recommendation_result.get("usage", {}).get(
                "total_tokens", 0
            ),
        },
        "mcp_integration": {
            "server_resources": server_result.get("resources", {}).get("count", 0),
            "server_tools": server_result.get("tools", {}).get("count", 0),
            "knowledge_base_docs": len(knowledge_docs),
            "embeddings_generated": kb_embeddings.get("total_embeddings", 0),
        },
        "performance": {
            "total_llm_cost": sum(
                [
                    result.get("usage", {}).get("estimated_cost_usd", 0)
                    for result in [
                        analysis_result,
                        strategy_result,
                        recommendation_result,
                    ]
                    if result.get("success")
                ]
            ),
            "embedding_cost": kb_embeddings.get("usage", {}).get(
                "estimated_cost_usd", 0
            ),
            "cache_efficiency": kb_embeddings.get("cache_hit_rate", 0),
            "total_tokens": sum(
                [
                    result.get("usage", {}).get("total_tokens", 0)
                    for result in [
                        analysis_result,
                        strategy_result,
                        recommendation_result,
                    ]
                    if result.get("success")
                ]
            ),
        },
    }

    # Save report as MCP resource
    report_resource = MCPResource()
    report_result = report_resource.run(
        operation="create",
        uri="workflow://reports/mcp_agentic_complete.json",
        content=final_report,
        metadata={
            "name": "MCP Agentic Workflow Report",
            "description": "Complete multi-agent workflow execution results",
            "tags": ["workflow", "multi-agent", "mcp", "report"],
        },
    )

    print(f"✅ Final report created: {report_result['success']}")

    # 6. Workflow Summary and Metrics
    print("\n🎯 Workflow Summary")
    print("=" * 50)

    success_count = sum(
        [
            1
            for result in [analysis_result, strategy_result, recommendation_result]
            if result.get("success")
        ]
    )

    print("✅ Multi-Agent Coordination Results:")
    print(f"   Successful agents: {success_count}/3")
    print(f"   Data Analysis Agent: {'✅' if analysis_result.get('success') else '❌'}")
    print(f"   Strategy Agent: {'✅' if strategy_result.get('success') else '❌'}")
    print(
        f"   Implementation Agent: {'✅' if recommendation_result.get('success') else '❌'}"
    )

    print("\n📊 MCP Integration Results:")
    print(f"   Server configured: {'✅' if server_result.get('success') else '❌'}")
    print(f"   Resources exposed: {server_result.get('resources', {}).get('count', 0)}")
    print(f"   Tools available: {server_result.get('tools', {}).get('count', 0)}")
    print(f"   Knowledge base: {len(knowledge_docs)} documents")
    print(f"   Embeddings: {kb_embeddings.get('total_embeddings', 0)} vectors")

    print("\n💰 Performance Metrics:")
    print(
        f"   Total Cost: ${final_report['performance']['total_llm_cost'] + final_report['performance']['embedding_cost']:.6f}"
    )
    print(f"   Total Tokens: {final_report['performance']['total_tokens']:,}")
    print(f"   Cache Efficiency: {final_report['performance']['cache_efficiency']:.2%}")
    print(f"   Processing Success: {success_count/3:.2%}")

    print("\n🚀 MCP + Agentic AI workflow completed successfully!")
    print("   ✅ Multi-agent coordination")
    print("   ✅ Context sharing via MCP")
    print("   ✅ Knowledge base integration")
    print("   ✅ Tool calling and RAG")
    print("   ✅ Persistent conversations")
    print("   ✅ Performance optimization")


if __name__ == "__main__":
    main()
