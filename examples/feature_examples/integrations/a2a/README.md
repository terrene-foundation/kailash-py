# A2A (Agent-to-Agent) Enhanced Examples

This directory contains examples demonstrating the enhanced A2A communication system with advanced features including semantic memory, hybrid search, and streaming analytics.

## 🚀 Enhanced Features

### 1. Rich Agent Cards
- **Detailed capability descriptions** with proficiency levels
- **Collaboration and communication styles**
- **Performance metrics** and success tracking
- **Hierarchical capability organization** by domain

### 2. Semantic Memory Integration
- **Embeddings-based storage** for agent capabilities
- **Vector similarity search** for intelligent matching
- **Contextual agent profiles** with rich metadata
- **Automatic fallback** to hash-based embeddings

### 3. Hybrid Search System
- **Multi-dimensional scoring** (semantic + keyword + context + performance)
- **Fuzzy matching** with synonym expansion
- **Contextual scoring** based on task history
- **Adaptive weights** that learn from feedback

### 4. Streaming Analytics
- **Real-time metrics collection** with custom alerts
- **Performance dashboards** with aggregated insights
- **Event streaming** for system monitoring
- **A2A-specific monitoring** with coordinator integration

### 5. Enhanced Task Lifecycle
- **State machine management** (CREATED → ASSIGNED → IN_PROGRESS → COMPLETED)
- **Multi-stage insight extraction** with quality scoring
- **Iterative improvement** based on feedback
- **Task validation** and requirement checking

## 📁 Example Files

### Core Examples

1. **`a2a_comprehensive_example.py`** - Complete demonstration of all A2A enhancements
   - Rich agent card registration
   - Semantic memory setup and usage
   - Hybrid search for agent matching
   - Streaming analytics and monitoring
   - Enhanced task execution with insights
   - Adaptive search learning
   - Performance dashboard

2. **`a2a_workflow_example.py`** - Workflow integration example
   - A2A nodes in WorkflowBuilder
   - Connected workflow execution
   - Streaming analytics integration
   - Monitoring and metrics collection

## 🔧 Usage Patterns

### Basic Agent Registration with Rich Cards

```python
from kailash.nodes.ai import A2AAgentNode, A2ACoordinatorNode

# Create agent with detailed capabilities
agent = A2AAgentNode(
    name="python_expert",
    agent_type="coding",
    description="Expert Python developer with web framework expertise",
    capabilities=[
        {
            "name": "web_development",
            "domain": "programming",
            "level": "expert",
            "description": "Django, FastAPI, Flask development"
        }
    ],
    tags=["python", "web", "backend"],
    collaboration_style="mentor",
    communication_style="technical"
)

# Register with coordinator
coordinator = A2ACoordinatorNode(name="coordinator")
await coordinator.register_agent(agent)
```

### Semantic Memory for Agent Matching

```python
from kailash.nodes.ai import SemanticMemoryStoreNode, HybridSearchNode

# Store agent capabilities
semantic_store = SemanticMemoryStoreNode(name="agent_store")
await semantic_store.run(
    content="Python web development with Django and FastAPI expertise",
    metadata={"agent_id": "python_expert"},
    collection="agent_capabilities"
)

# Intelligent agent matching
hybrid_search = HybridSearchNode(name="matcher")
results = await hybrid_search.run(
    requirements=["python web development", "API design"],
    agents=[agent.to_dict() for agent in registered_agents],
    limit=3
)
```

### Streaming Analytics and Monitoring

```python
from kailash.nodes.ai import StreamingAnalyticsNode, A2AMonitoringNode

# Setup analytics with custom alerts
analytics = StreamingAnalyticsNode(name="analytics")
await analytics.run(
    action="start_monitoring",
    alert_rules=[
        {
            "name": "low_performance",
            "metric_name": "task_success_rate",
            "threshold": 0.8,
            "condition": "less_than",
            "severity": "medium"
        }
    ]
)

# A2A-specific monitoring
monitor = A2AMonitoringNode(name="a2a_monitor")
await monitor.run(
    coordinator_node=coordinator,
    streaming_node=analytics,
    monitoring_interval=5
)
```

### Enhanced Task Execution

```python
# Execute task with enhanced insights
task_result = await coordinator.run(
    action="execute_task",
    task={
        "name": "web_app_development",
        "description": "Build scalable web application",
        "requirements": ["Python", "Database", "API design"],
        "priority": "high",
        "expected_quality": 0.85
    },
    assigned_agent_id="python_expert",
    enable_insight_extraction=True,
    insight_extraction_stages=[
        "analysis",
        "design",
        "implementation",
        "review",
        "final_insights"
    ]
)
```

## 🎯 Key Benefits

1. **Intelligent Agent Matching**: Semantic similarity ensures optimal agent selection
2. **Quality Insights**: Multi-stage extraction provides comprehensive task analysis
3. **Performance Monitoring**: Real-time metrics enable proactive system management
4. **Adaptive Learning**: System improves based on historical feedback
5. **Rich Context**: Detailed agent profiles enable better collaboration
6. **Scalable Architecture**: Components designed for production deployment

## 📊 Monitoring and Analytics

The enhanced A2A system provides comprehensive monitoring:

- **Agent Performance**: Success rates, quality scores, utilization metrics
- **Task Lifecycle**: State transitions, completion times, insight quality
- **System Health**: Resource usage, error rates, alert management
- **Search Effectiveness**: Matching accuracy, confidence scores, learning progress

## 🔧 Configuration Options

### Search Weights
- `semantic_weight`: Importance of semantic similarity (default: 0.3)
- `keyword_weight`: Importance of keyword matching (default: 0.3)
- `context_weight`: Importance of contextual scoring (default: 0.2)
- `performance_weight`: Importance of performance metrics (default: 0.2)

### Analytics Settings
- `retention_hours`: Metric retention period (default: 24)
- `buffer_size`: Event buffer size (default: 1000)
- `update_interval`: Dashboard update frequency (default: 5s)

### Monitoring Configuration
- `monitoring_interval`: Metrics collection interval (default: 10s)
- `enable_auto_alerts`: Automatic alert generation (default: True)
- `alert_thresholds`: Custom performance thresholds

## 🚀 Getting Started

1. **Install Dependencies**: Ensure you have the latest Kailash SDK
2. **Run Examples**: Start with `a2a_comprehensive_example.py`
3. **Customize**: Modify agent capabilities and search weights for your use case
4. **Monitor**: Use the streaming analytics to track performance
5. **Iterate**: Leverage adaptive search to improve matching over time

## 💡 Advanced Usage

For production deployments, consider:

- **Persistent Storage**: Replace in-memory stores with databases
- **Distributed Deployment**: Scale components across multiple instances
- **External Monitoring**: Integrate with monitoring systems like Prometheus
- **Custom Embeddings**: Use domain-specific embedding models
- **Advanced Analytics**: Implement custom metrics and dashboards

## 📚 Related Documentation

- [A2A Core Documentation](../../../../sdk-users/cheatsheet/024-a2a-communication.md)
- [Semantic Memory Guide](../../../../sdk-users/cheatsheet/026-semantic-memory.md)
- [Hybrid Search Documentation](../../../../sdk-users/cheatsheet/027-hybrid-search.md)
- [Streaming Analytics Guide](../../../../sdk-users/cheatsheet/028-streaming-analytics.md)
