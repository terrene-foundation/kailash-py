"""
Comprehensive Self-Organizing Agent Orchestration Demo

This example demonstrates a complete self-organizing agent workflow architecture that:

1. **Agent Pool Self-Organization**: Agents autonomously form teams based on query requirements
2. **MCP Integration**: Agents use Model Context Protocol to access external tools and resources  
3. **Information Reuse**: Intelligent caching prevents repeated external calls and enables cross-agent sharing
4. **Automatic Evaluation**: Solutions are continuously evaluated with convergence detection
5. **Workflow Orchestration**: Central orchestrator coordinates the entire process seamlessly

Key Features Demonstrated:
- Intelligent query analysis and team formation
- MCP tool integration with smart caching
- Multi-iteration solution refinement
- Automatic termination when solutions are satisfactory
- Performance metrics and cost optimization

Real-World Applications:
- Research and analysis projects
- Business intelligence and strategy
- Complex problem-solving workflows
- Multi-source data integration
- Collaborative decision making
"""

import json
import os
import sys
import time
from typing import Dict, List

# Add the src directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from kailash import Workflow
from kailash.nodes.ai.intelligent_agent_orchestrator import (
    ConvergenceDetectorNode,
    IntelligentCacheNode,
    MCPAgentNode,
    OrchestrationManagerNode,
    QueryAnalysisNode,
)
from kailash.runtime import LocalRuntime


def demo_intelligent_cache():
    """
    Demonstrate intelligent caching capabilities.
    
    This function showcases the IntelligentCacheNode's ability to:
    1. Cache expensive API results with metadata
    2. Perform direct cache lookups by key
    3. Find similar cached items using semantic search
    4. Track cache statistics and cost savings
    
    The demo simulates caching results from weather and financial APIs,
    then shows how agents can retrieve this information without making
    redundant external calls.
    
    Key features demonstrated:
        - TTL-based cache expiration
        - Semantic similarity matching
        - Cost tracking for ROI analysis
        - Cross-agent cache sharing
    """
    print("🧠 Intelligent Cache Demo")
    print("=" * 40)
    
    cache = IntelligentCacheNode()
    
    # Cache some expensive API results
    print("\n1. Caching expensive API results...")
    
    # Weather API result
    cache.run(
        action="cache",
        cache_key="weather_nyc_20241215",
        data={
            "temperature": 45,
            "humidity": 68,
            "conditions": "partly_cloudy",
            "wind_speed": 12,
            "forecast": ["sunny", "rainy", "cloudy"]
        },
        metadata={
            "source": "weather_mcp_server",
            "cost": 0.15,
            "query_abstraction": "weather_location_date",
            "semantic_tags": ["weather", "nyc", "temperature", "forecast"]
        },
        ttl=3600
    )
    
    # Financial data result
    cache.run(
        action="cache",
        cache_key="stock_aapl_20241215",
        data={
            "symbol": "AAPL",
            "price": 198.50,
            "change": 2.34,
            "volume": 45678901,
            "market_cap": "3.1T"
        },
        metadata={
            "source": "financial_mcp_server", 
            "cost": 0.25,
            "query_abstraction": "stock_price_symbol",
            "semantic_tags": ["finance", "stock", "aapl", "price"]
        },
        ttl=1800
    )
    
    print("✅ Cached weather and financial data")
    
    # Demonstrate cache hits
    print("\n2. Testing cache retrieval...")
    
    # Direct cache hit
    weather_hit = cache.run(
        action="get",
        cache_key="weather_nyc_20241215"
    )
    print(f"   Direct hit: {weather_hit['hit']} (weather data)")
    
    # Semantic cache hit
    semantic_hit = cache.run(
        action="get",
        query="temperature forecast new york",
        similarity_threshold=0.6
    )
    print(f"   Semantic hit: {semantic_hit['hit']} (similarity: {semantic_hit.get('similarity_score', 'N/A')})")
    
    # Cache miss
    miss = cache.run(
        action="get",
        cache_key="nonexistent_key"
    )
    print(f"   Cache miss: {miss['hit']} (as expected)")
    
    # Show cache statistics
    stats = cache.run(action="stats")
    if stats["success"]:
        print(f"\n📊 Cache Statistics:")
        print(f"   Total entries: {stats['stats']['total_entries']}")
        print(f"   Hit rate: {stats['stats']['hit_rate']:.2%}")
        print(f"   Cost saved: ${stats['stats']['estimated_cost_saved']:.2f}")


def demo_query_analysis():
    """Demonstrate query analysis capabilities."""
    print("\n🔍 Query Analysis Demo")
    print("=" * 40)
    
    analyzer = QueryAnalysisNode()
    
    # Complex multi-domain query
    complex_query = """
    Research the latest trends in renewable energy technology, analyze the market opportunity 
    for our company, create a 5-year strategic plan including financial projections, 
    and identify potential partnerships. Consider regulatory changes and competitive landscape.
    """
    
    print(f"\nAnalyzing complex query: {complex_query[:100]}...")
    
    analysis = analyzer.run(
        query=complex_query,
        context={
            "domain": "strategic_planning",
            "urgency": "high",
            "deadline": "2024-12-31",
            "budget": 50000
        },
        mcp_servers=[
            {"name": "research_server", "type": "web_research"},
            {"name": "financial_server", "type": "financial_data"},
            {"name": "market_server", "type": "market_analysis"}
        ]
    )
    
    if analysis["success"]:
        result = analysis["analysis"]
        print(f"\n📋 Analysis Results:")
        print(f"   Complexity Score: {result['complexity_score']:.2f}")
        print(f"   Required Capabilities: {len(result['required_capabilities'])} capabilities")
        print(f"     - {', '.join(result['required_capabilities'][:5])}")
        print(f"   MCP Tools Needed: {result['mcp_requirements']['mcp_needed']}")
        print(f"   Suggested Team Size: {result['team_suggestion']['suggested_size']}")
        print(f"   Strategy: {result['strategy']['approach']}")
        print(f"   Estimated Time: {result['estimates']['estimated_time_minutes']} minutes")
        print(f"   Max Iterations: {result['estimates']['max_iterations']}")


def demo_mcp_agent():
    """Demonstrate MCP-enhanced agent capabilities."""
    print("\n🤖 MCP Agent Demo")
    print("=" * 40)
    
    # Create cache for agent to use
    cache = IntelligentCacheNode()
    
    # Pre-populate cache with some data
    cache.run(
        action="cache",
        cache_key="market_research_renewables",
        data={
            "market_size": "$1.1T by 2030",
            "growth_rate": "8.4% CAGR",
            "key_segments": ["solar", "wind", "hydro", "geothermal"],
            "leading_companies": ["Tesla", "First Solar", "Vestas", "Orsted"]
        },
        metadata={
            "source": "market_research_mcp",
            "cost": 2.50,
            "semantic_tags": ["renewable", "energy", "market", "research"]
        }
    )
    
    # Create MCP-enhanced agent
    agent = MCPAgentNode()
    
    result = agent.run(
        agent_id="research_agent_001",
        capabilities=["market_research", "data_analysis", "strategic_planning"],
        mcp_servers=[
            {
                "name": "market_research_server",
                "command": "python",
                "args": ["-m", "market_research_mcp"]
            },
            {
                "name": "financial_server", 
                "command": "python",
                "args": ["-m", "financial_mcp"]
            }
        ],
        task="Analyze the renewable energy market and identify strategic opportunities",
        team_context={
            "team_id": "strategy_team_alpha",
            "team_goal": "Develop renewable energy strategy",
            "other_members": ["analyst_002", "financial_expert_003"]
        },
        collaboration_mode="cooperative",
        provider="mock",
        model="mock-model"
    )
    
    print(f"\n🔬 Agent Execution Result:")
    if result.get("success"):
        print(f"   Agent: {result['self_organization']['agent_id']}")
        print(f"   Capabilities: {', '.join(result['self_organization']['capabilities'])}")
        print(f"   Task completed: ✅")
        print(f"   MCP tools available: {len(result.get('mcp_tool_results', []))}")
        if "content" in result:
            print(f"   Response preview: {result['content'][:100]}...")
    else:
        print(f"   ❌ Execution failed: {result.get('error', 'Unknown error')}")


def demo_convergence_detection():
    """Demonstrate convergence detection logic."""
    print("\n🎯 Convergence Detection Demo")
    print("=" * 40)
    
    detector = ConvergenceDetectorNode()
    
    # Simulate solution history with improving scores
    solution_history = [
        {
            "iteration": 1,
            "evaluation": {"overall_score": 0.65},
            "team_agreement": 0.75,
            "duration": 120
        },
        {
            "iteration": 2, 
            "evaluation": {"overall_score": 0.78},
            "team_agreement": 0.83,
            "duration": 95
        },
        {
            "iteration": 3,
            "evaluation": {"overall_score": 0.84},
            "team_agreement": 0.89,
            "duration": 110
        }
    ]
    
    print("\nTesting convergence with improving solution...")
    
    convergence = detector.run(
        solution_history=solution_history,
        quality_threshold=0.8,
        improvement_threshold=0.02,
        max_iterations=5,
        current_iteration=3
    )
    
    if convergence["success"]:
        print(f"\n📈 Convergence Analysis:")
        print(f"   Should continue: {convergence['should_continue']}")
        print(f"   Reason: {convergence['reason']}")
        print(f"   Confidence: {convergence['confidence']:.2%}")
        print(f"   Latest score: {convergence['latest_score']:.3f}")
        print(f"   Improvement trend: {convergence['improvement_trend']['trend']}")
        
        if convergence["recommendations"]:
            print(f"   Recommendations:")
            for rec in convergence["recommendations"]:
                print(f"     - {rec}")


def demo_full_orchestration():
    """Demonstrate complete orchestration workflow."""
    print("\n🎼 Full Orchestration Demo")
    print("=" * 50)
    
    # Create orchestration manager
    orchestrator = OrchestrationManagerNode()
    
    # Define a complex business problem
    business_query = """
    Our technology startup needs to pivot our business model due to changing market conditions.
    Research emerging technology trends, analyze our current capabilities, identify new market 
    opportunities, and develop a comprehensive pivot strategy with financial projections and 
    implementation timeline. Focus on AI/ML applications in healthcare and fintech sectors.
    """
    
    print(f"\n🚀 Executing Full Orchestration...")
    print(f"Query: {business_query[:100]}...")
    
    # Mock MCP servers for the demo
    mcp_servers = [
        {
            "name": "tech_trends_server",
            "command": "python", 
            "args": ["-m", "tech_trends_mcp"],
            "description": "Technology trend analysis and forecasting"
        },
        {
            "name": "market_analysis_server",
            "command": "python",
            "args": ["-m", "market_analysis_mcp"], 
            "description": "Market size and opportunity analysis"
        },
        {
            "name": "financial_modeling_server",
            "command": "python",
            "args": ["-m", "financial_modeling_mcp"],
            "description": "Financial projections and modeling"
        }
    ]
    
    start_time = time.time()
    
    # Execute orchestration
    result = orchestrator.run(
        query=business_query,
        context={
            "domain": "business_strategy",
            "company_stage": "startup",
            "urgency": "high",
            "budget": 25000,
            "timeline": "Q1 2025"
        },
        agent_pool_size=12,
        mcp_servers=mcp_servers,
        max_iterations=3,
        quality_threshold=0.85,
        time_limit_minutes=30,
        enable_caching=True
    )
    
    execution_time = time.time() - start_time
    
    print(f"\n📊 Orchestration Results:")
    if result.get("success"):
        print(f"   ✅ Execution completed successfully")
        print(f"   Session ID: {result['session_id']}")
        print(f"   Quality Score: {result['quality_score']:.3f}")
        print(f"   Iterations: {result['iterations_completed']}")
        print(f"   Total Time: {result['total_time_seconds']:.1f}s")
        
        # Performance metrics
        if "performance_metrics" in result:
            metrics = result["performance_metrics"]
            print(f"\n📈 Performance Metrics:")
            print(f"   Cache Hit Rate: {metrics['cache_hit_rate']:.2%}")
            print(f"   External Calls Saved: ${metrics['external_calls_saved']:.2f}")
            print(f"   Agent Utilization: {metrics['agent_utilization']:.2%}")
        
        # Solution summary
        if "final_solution" in result:
            solution = result["final_solution"]
            print(f"\n💡 Solution Summary:")
            print(f"   Team Size: {solution.get('team_size', 'N/A')}")
            print(f"   Confidence: {solution.get('confidence', 0):.2%}")
            print(f"   Information Sources: {len(solution.get('information_gathering', []))}")
            print(f"   Analysis Components: {len(solution.get('analysis_processing', []))}")
            print(f"   Synthesis Results: {len(solution.get('synthesis', []))}")
            
        # Infrastructure used
        if "metadata" in result:
            infrastructure = result["metadata"].get("infrastructure_used", [])
            print(f"\n🏗️ Infrastructure Used: {', '.join(infrastructure)}")
            
    else:
        print(f"   ❌ Execution failed: {result.get('error', 'Unknown error')}")
        
    print(f"\n⏱️ Demo execution time: {execution_time:.1f}s")


def demo_workflow_integration():
    """Demonstrate integration with Kailash workflow system."""
    print("\n🔄 Workflow Integration Demo")
    print("=" * 45)
    
    # Create a complete workflow using the orchestration components
    workflow = Workflow(
        workflow_id="intelligent_orchestration_demo",
        name="Self-Organizing Agent Workflow",
        description="Complete self-organizing agent workflow with MCP integration"
    )
    
    # Add orchestration components
    workflow.add_node(
        "cache",
        IntelligentCacheNode(),
        config={"default_ttl": 3600}
    )
    
    workflow.add_node(
        "query_analyzer", 
        QueryAnalysisNode()
    )
    
    workflow.add_node(
        "orchestrator",
        OrchestrationManagerNode()
    )
    
    workflow.add_node(
        "convergence_detector",
        ConvergenceDetectorNode()
    )
    
    # Connect the workflow
    workflow.connect("query_analyzer", "orchestrator")
    workflow.connect("orchestrator", "convergence_detector")
    
    print(f"✅ Created workflow with {len(workflow.nodes)} nodes")
    print(f"   Nodes: {', '.join(workflow.nodes.keys())}")
    
    # Test workflow execution
    runtime = LocalRuntime()
    
    test_query = "Analyze customer churn patterns and recommend retention strategies"
    
    print(f"\n🧪 Testing workflow with query: {test_query}")
    
    try:
        # Execute just the query analyzer for demo
        query_result, _ = runtime.execute(
            workflow,
            parameters={
                "query_analyzer": {
                    "query": test_query,
                    "context": {"domain": "customer_analytics"}
                }
            }
        )
        
        if query_result.get("query_analyzer", {}).get("success"):
            analysis = query_result["query_analyzer"]["analysis"]
            print(f"   ✅ Query analysis completed")
            print(f"   Complexity: {analysis['complexity_score']:.2f}")
            print(f"   Required capabilities: {len(analysis['required_capabilities'])}")
        else:
            print(f"   ❌ Query analysis failed")
            
    except Exception as e:
        print(f"   ⚠️ Workflow execution error: {e}")


def main():
    """Run all demonstration components."""
    print("🎯 Intelligent Agent Orchestration - Complete Demo")
    print("=" * 60)
    
    print("\nThis demo showcases a comprehensive self-organizing agent architecture with:")
    print("  • Intelligent caching to prevent repeated external calls")
    print("  • MCP integration for external tool access") 
    print("  • Automatic team formation and collaboration")
    print("  • Solution evaluation and convergence detection")
    print("  • Complete workflow orchestration")
    
    try:
        # Run individual component demos
        demo_intelligent_cache()
        demo_query_analysis()
        demo_mcp_agent()
        demo_convergence_detection()
        
        # Run integration demos
        demo_workflow_integration()
        demo_full_orchestration()
        
        print("\n" + "=" * 60)
        print("🎉 All demos completed successfully!")
        print("\n🔗 Key Architecture Benefits:")
        print("  ✅ Autonomous agent self-organization")
        print("  ✅ Intelligent information reuse and caching")
        print("  ✅ Seamless MCP tool integration")
        print("  ✅ Automatic solution evaluation and termination")
        print("  ✅ Scalable workflow orchestration")
        print("  ✅ Cost optimization through smart caching")
        print("  ✅ Multi-iteration solution refinement")
        
        print("\n📚 Real-World Applications:")
        print("  • Business intelligence and strategic planning")
        print("  • Research and analysis projects")
        print("  • Multi-source data integration")
        print("  • Complex decision-making workflows")
        print("  • Collaborative problem solving")
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        raise


if __name__ == "__main__":
    main()