"""
Comprehensive A2A Enhancement Example

This example demonstrates all the enhanced A2A features:
- Agent Cards with rich capability descriptions
- Task Lifecycle with state management
- Multi-stage insight extraction
- Semantic memory for intelligent agent matching
- Hybrid search combining multiple scoring methods
- Streaming analytics and performance monitoring
- Adaptive search that learns from feedback
"""

import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List

from kailash.nodes.ai import (
    A2AAgentNode,
    A2ACoordinatorNode,
    A2AMonitoringNode,
    AdaptiveSearchNode,
    HybridSearchNode,
    SemanticAgentMatchingNode,
    SemanticMemorySearchNode,
    SemanticMemoryStoreNode,
    StreamingAnalyticsNode,
)
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


async def main():
    """Main example demonstrating comprehensive A2A features."""
    print("🚀 A2A Comprehensive Enhancement Example")
    print("=========================================\n")
    
    # Initialize runtime
    runtime = LocalRuntime()
    
    # Phase 1: Agent Registration with Rich Agent Cards
    print("📋 Phase 1: Agent Registration with Rich Agent Cards")
    print("-" * 50)
    
    coordinator = A2ACoordinatorNode(name="enhanced_coordinator")
    
    # Create specialized agents with detailed agent cards
    python_expert = A2AAgentNode(
        name="python_expert",
        agent_type="coding",
        description="Expert Python developer with deep knowledge of frameworks and best practices",
        capabilities=[
            {
                "name": "python_development",
                "domain": "programming",
                "level": "expert",
                "description": "Advanced Python programming with frameworks like Django, FastAPI, and async programming"
            },
            {
                "name": "code_review", 
                "domain": "quality_assurance",
                "level": "expert",
                "description": "Comprehensive code review with security and performance analysis"
            },
            {
                "name": "testing",
                "domain": "quality_assurance", 
                "level": "advanced",
                "description": "Unit testing, integration testing, and test automation"
            }
        ],
        tags=["python", "backend", "api", "testing", "senior"],
        collaboration_style="mentor",
        communication_style="technical"
    )
    
    data_scientist = A2AAgentNode(
        name="data_scientist",
        agent_type="analytics",
        description="Data science expert specializing in machine learning and statistical analysis",
        capabilities=[
            {
                "name": "data_analysis",
                "domain": "analytics",
                "level": "expert", 
                "description": "Advanced statistical analysis and data visualization"
            },
            {
                "name": "machine_learning",
                "domain": "ai",
                "level": "expert",
                "description": "ML model development, training, and deployment"
            },
            {
                "name": "python_libraries",
                "domain": "programming",
                "level": "advanced",
                "description": "Pandas, NumPy, Scikit-learn, TensorFlow expertise"
            }
        ],
        tags=["python", "ml", "statistics", "visualization", "research"],
        collaboration_style="researcher",
        communication_style="analytical"
    )
    
    devops_engineer = A2AAgentNode(
        name="devops_engineer",
        agent_type="infrastructure",
        description="DevOps engineer focused on automation, deployment, and monitoring",
        capabilities=[
            {
                "name": "automation",
                "domain": "infrastructure",
                "level": "expert",
                "description": "CI/CD pipelines, infrastructure as code, and deployment automation"
            },
            {
                "name": "monitoring",
                "domain": "operations",
                "level": "expert", 
                "description": "System monitoring, alerting, and performance optimization"
            },
            {
                "name": "containerization",
                "domain": "infrastructure",
                "level": "advanced",
                "description": "Docker, Kubernetes, and container orchestration"
            }
        ],
        tags=["devops", "automation", "monitoring", "docker", "kubernetes"],
        collaboration_style="systematic",
        communication_style="practical"
    )
    
    # Register agents with the coordinator
    agents = [python_expert, data_scientist, devops_engineer]
    for agent in agents:
        await coordinator.register_agent(agent)
    
    print(f"✅ Registered {len(agents)} agents with rich capability profiles")
    
    # Phase 2: Semantic Memory and Intelligent Matching
    print("\n🧠 Phase 2: Semantic Memory and Intelligent Matching")
    print("-" * 55)
    
    # Store agent capabilities in semantic memory
    semantic_store = SemanticMemoryStoreNode(name="capability_store")
    
    # Store each agent's capabilities
    for agent_data in coordinator.registered_agents.values():
        agent_description = f"{agent_data.agent_name}: {agent_data.description}"
        capabilities_text = " ".join([
            f"{cap.name} ({cap.level}): {cap.description}"
            for cap in agent_data.primary_capabilities
        ])
        full_text = f"{agent_description} {capabilities_text}"
        
        await semantic_store.run(
            content=full_text,
            metadata={"agent_id": agent_data.agent_id, "type": "agent_profile"},
            collection="agent_capabilities"
        )
    
    print("✅ Stored agent capabilities in semantic memory")
    
    # Phase 3: Hybrid Search Demonstration
    print("\n🔍 Phase 3: Hybrid Search for Agent Matching")
    print("-" * 45)
    
    # Create hybrid search node
    hybrid_search = HybridSearchNode(name="agent_matcher")
    
    # Search for best agent for a complex task
    requirements = [
        "python web application development",
        "API design and implementation", 
        "database integration",
        "testing and quality assurance"
    ]
    
    # Get all registered agents for search
    agent_list = [agent.to_dict() for agent in coordinator.registered_agents.values()]
    
    search_result = await hybrid_search.run(
        requirements=requirements,
        agents=agent_list,
        limit=3,
        min_threshold=0.2
    )
    
    print(f"📊 Found {search_result['count']} matching agents:")
    for i, result in enumerate(search_result['results'][:2]):
        print(f"  {i+1}. {result['agent_id']} (Score: {result['combined_score']:.3f})")
        print(f"     Semantic: {result['semantic_score']:.3f}, Keyword: {result['keyword_score']:.3f}")
        print(f"     Context: {result['context_score']:.3f}, Performance: {result['performance_score']:.3f}")
    
    # Phase 4: Streaming Analytics Setup
    print("\n📈 Phase 4: Streaming Analytics and Monitoring")
    print("-" * 48)
    
    # Create streaming analytics node
    streaming_analytics = StreamingAnalyticsNode(name="a2a_analytics")
    
    # Start monitoring with custom alert rules
    await streaming_analytics.run(
        action="start_monitoring",
        alert_rules=[
            {
                "name": "low_task_completion",
                "metric_name": "task_completion_rate",
                "threshold": 0.8,
                "condition": "less_than",
                "severity": "medium",
                "message": "Task completion rate below 80%"
            },
            {
                "name": "high_insight_quality",
                "metric_name": "insight_quality",
                "threshold": 0.9,
                "condition": "greater_than", 
                "severity": "low",
                "message": "Excellent insight quality achieved"
            }
        ]
    )
    
    print("✅ Started streaming analytics with custom alert rules")
    
    # Create A2A-specific monitoring
    a2a_monitor = A2AMonitoringNode(name="a2a_monitor")
    
    # Start A2A monitoring
    await a2a_monitor.run(
        coordinator_node=coordinator,
        streaming_node=streaming_analytics,
        monitoring_interval=5,
        enable_auto_alerts=True
    )
    
    print("✅ Started A2A-specific monitoring")
    
    # Phase 5: Enhanced Task Execution with Lifecycle Management
    print("\n⚙️ Phase 5: Enhanced Task Execution")
    print("-" * 40)
    
    # Create a complex task that requires multiple insights
    complex_task = {
        "name": "web_app_architecture",
        "description": "Design and implement a scalable web application with ML integration",
        "requirements": [
            "Python web framework selection",
            "Database design and optimization",
            "ML model integration",
            "API design and documentation",
            "Deployment and monitoring strategy"
        ],
        "priority": "high",
        "expected_quality": 0.85,
        "max_iterations": 3
    }
    
    # Find best agent using hybrid search
    best_agent_id = search_result['results'][0]['agent_id'] if search_result['results'] else 'python_expert'
    
    print(f"🎯 Assigning complex task to best matched agent: {best_agent_id}")
    
    # Record task metrics
    await streaming_analytics.run(
        action="record_metric",
        metric_name="tasks_assigned",
        metric_value=1,
        metric_type="counter"
    )
    
    # Execute task with enhanced insight extraction
    task_result = await coordinator.run(
        action="execute_task",
        task=complex_task,
        assigned_agent_id=best_agent_id,
        enable_insight_extraction=True,
        insight_extraction_stages=[
            "analysis",
            "solution_design", 
            "implementation_plan",
            "quality_review",
            "final_insights"
        ]
    )
    
    print(f"✅ Task executed with {len(task_result.get('insights', []))} insights generated")
    
    # Record completion metrics
    await streaming_analytics.run(
        action="record_metric",
        metric_name="tasks_completed",
        metric_value=1,
        metric_type="counter"
    )
    
    await streaming_analytics.run(
        action="record_metric",
        metric_name="task_completion_rate",
        metric_value=1.0,
        metric_type="gauge"
    )
    
    if 'insights' in task_result:
        avg_quality = sum(insight.get('quality_score', 0.5) for insight in task_result['insights']) / len(task_result['insights'])
        await streaming_analytics.run(
            action="record_metric",
            metric_name="insight_quality",
            metric_value=avg_quality,
            metric_type="gauge"
        )
    
    # Phase 6: Adaptive Search Learning
    print("\n🎓 Phase 6: Adaptive Search Learning")
    print("-" * 38)
    
    # Create adaptive search node
    adaptive_search = AdaptiveSearchNode(name="learning_matcher")
    
    # Simulate feedback from previous searches
    feedback_history = [
        {
            "success": 0.9,
            "component_scores": {
                "semantic": 0.8,
                "keyword": 0.7,
                "context": 0.6,
                "performance": 0.9
            }
        },
        {
            "success": 0.8,
            "component_scores": {
                "semantic": 0.9,
                "keyword": 0.6,
                "context": 0.7,
                "performance": 0.8
            }
        }
    ]
    
    # Perform adaptive search with learning
    adaptive_result = await adaptive_search.run(
        requirements=["machine learning model deployment", "python automation"],
        agents=agent_list,
        feedback_history=feedback_history,
        limit=2
    )
    
    print(f"🧠 Adaptive search completed with learned weights:")
    weights = adaptive_result['adaptive_weights']
    for component, weight in weights.items():
        print(f"  {component}: {weight:.3f}")
    
    # Phase 7: Performance Dashboard
    print("\n📊 Phase 7: Performance Dashboard")
    print("-" * 35)
    
    # Get dashboard data
    dashboard_result = await streaming_analytics.run(action="get_dashboard")
    
    if dashboard_result['success']:
        dashboard = dashboard_result['dashboard']
        real_time = dashboard_result['real_time']
        
        print("📈 System Performance Overview:")
        if 'overview' in dashboard:
            overview = dashboard['overview']
            print(f"  • Total Tasks: {overview.get('total_tasks', 0)}")
            print(f"  • Agent Utilization: {overview.get('average_agent_utilization', 0):.1%}")
            print(f"  • Insight Quality: {overview.get('average_insight_quality', 0):.1%}")
            print(f"  • Active Alerts: {overview.get('active_alerts', 0)}")
        
        print("\n⚡ Real-time Metrics:")
        print(f"  • Tasks/min: {real_time.get('tasks_per_minute', 0)}")
        print(f"  • Avg Quality: {real_time.get('average_insight_quality', 0):.1%}")
        print(f"  • Active Agents: {real_time.get('active_agents', 0)}")
    
    # Phase 8: Cleanup and Summary
    print("\n🏁 Phase 8: Cleanup and Summary")
    print("-" * 33)
    
    # Stop monitoring
    await streaming_analytics.run(action="stop_monitoring")
    await a2a_monitor.stop_monitoring()
    
    # Get final metrics
    final_metrics = await streaming_analytics.run(action="get_metrics")
    
    print("✅ A2A Comprehensive Enhancement Demo Complete!")
    print("\n📋 Features Demonstrated:")
    print("  ✓ Rich Agent Cards with detailed capabilities")
    print("  ✓ Semantic Memory for intelligent content storage")
    print("  ✓ Hybrid Search combining multiple scoring methods")
    print("  ✓ Streaming Analytics with custom alerts")
    print("  ✓ A2A-specific monitoring and metrics")
    print("  ✓ Enhanced Task Lifecycle with state management")
    print("  ✓ Multi-stage insight extraction")
    print("  ✓ Adaptive Search with learning capabilities")
    print("  ✓ Real-time Performance Dashboard")
    
    if final_metrics['success']:
        print(f"\n📊 Final Metrics: {len(final_metrics['metrics'])} metric types collected")
        print(f"🚨 Active Alerts: {len(final_metrics['active_alerts'])}")
    
    print("\n🎉 All A2A enhancements successfully integrated!")


if __name__ == "__main__":
    asyncio.run(main())