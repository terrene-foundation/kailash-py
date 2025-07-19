"""
A2A Workflow Integration Example

This example shows how to integrate A2A enhancements into workflows using WorkflowBuilder.
"""

import asyncio

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


async def main():
    """Demonstrate A2A enhancements in workflow context."""
    print("🔧 A2A Workflow Integration Example")
    print("===================================\n")
    
    # Create workflow with A2A enhancements
    workflow = WorkflowBuilder()
    
    # Step 1: Initialize streaming analytics
    workflow.add_node(
        "StreamingAnalyticsNode", 
        "analytics",
        {
            "action": "start_monitoring",
            "alert_rules": [
                {
                    "name": "task_performance",
                    "metric_name": "task_success_rate",
                    "threshold": 0.8,
                    "condition": "less_than",
                    "severity": "medium"
                }
            ]
        }
    )
    
    # Step 2: Setup A2A coordinator
    workflow.add_node(
        "A2ACoordinatorNode",
        "coordinator", 
        {
            "coordinator_id": "workflow_coordinator",
            "max_concurrent_tasks": 3
        }
    )
    
    # Step 3: Create specialized agents
    workflow.add_node(
        "A2AAgentNode",
        "coding_agent",
        {
            "agent_id": "python_specialist",
            "agent_type": "coding",
            "description": "Python development specialist with web framework expertise",
            "capabilities": [
                {
                    "name": "web_development",
                    "domain": "programming",
                    "level": "expert",
                    "description": "Django, FastAPI, Flask development"
                }
            ],
            "tags": ["python", "web", "api"]
        }
    )
    
    workflow.add_node(
        "A2AAgentNode",
        "data_agent",
        {
            "agent_id": "data_analyst",
            "agent_type": "analytics", 
            "description": "Data analysis and visualization expert",
            "capabilities": [
                {
                    "name": "data_analysis",
                    "domain": "analytics",
                    "level": "expert",
                    "description": "Statistical analysis and machine learning"
                }
            ],
            "tags": ["python", "data", "ml"]
        }
    )
    
    # Step 4: Setup semantic memory for agent matching
    workflow.add_node(
        "SemanticMemoryStoreNode",
        "memory_store",
        {
            "content": [
                "Python web development with Django and FastAPI",
                "Data analysis with pandas and scikit-learn",
                "API design and database integration"
            ],
            "collection": "agent_skills"
        }
    )
    
    # Step 5: Use hybrid search for intelligent agent matching
    workflow.add_node(
        "HybridSearchNode",
        "agent_matcher",
        {
            "requirements": ["python web application", "data processing"],
            "agents": [
                {
                    "agent_id": "python_specialist",
                    "description": "Python web development specialist"
                },
                {
                    "agent_id": "data_analyst", 
                    "description": "Data analysis and ML expert"
                }
            ],
            "limit": 2,
            "semantic_weight": 0.4,
            "keyword_weight": 0.3,
            "context_weight": 0.2,
            "performance_weight": 0.1
        }
    )
    
    # Step 6: Execute task with best matched agent
    workflow.add_node(
        "A2ACoordinatorNode",
        "task_executor",
        {
            "action": "execute_task",
            "task": {
                "name": "web_app_development",
                "description": "Build a web application with data processing capabilities",
                "requirements": ["Python web framework", "Data processing", "API design"],
                "priority": "high"
            },
            "enable_insight_extraction": True
        }
    )
    
    # Step 7: Setup A2A monitoring
    workflow.add_node(
        "A2AMonitoringNode",
        "a2a_monitor",
        {
            "monitoring_interval": 10,
            "enable_auto_alerts": True
        }
    )
    
    # Connect workflow nodes
    workflow.add_connection("analytics", "coordinator")
    workflow.add_connection("coordinator", "coding_agent")
    workflow.add_connection("coordinator", "data_agent")
    workflow.add_connection("memory_store", "agent_matcher")
    workflow.add_connection("agent_matcher", "task_executor")
    workflow.add_connection("task_executor", "a2a_monitor")
    
    # Execute workflow
    print("🚀 Starting A2A workflow...")
    runtime = LocalRuntime()
    
    try:
        results, run_id = runtime.execute(workflow.build())
        
        print(f"✅ Workflow completed successfully!")
        print(f"📊 Run ID: {run_id}")
        
        # Show key results
        if "agent_matcher" in results:
            matches = results["agent_matcher"]
            print(f"🎯 Agent Matching: Found {matches.get('count', 0)} suitable agents")
            
        if "task_executor" in results:
            task_result = results["task_executor"]
            print(f"⚙️ Task Execution: {task_result.get('success', False)}")
            if task_result.get('insights'):
                print(f"💡 Insights Generated: {len(task_result['insights'])}")
                
        if "a2a_monitor" in results:
            monitor_result = results["a2a_monitor"]
            print(f"📈 Monitoring: {monitor_result.get('success', False)}")
        
    except Exception as e:
        print(f"❌ Workflow failed: {e}")
    
    print("\n🎉 A2A Workflow Integration Complete!")


if __name__ == "__main__":
    asyncio.run(main())