# Edge Computing Guide

*Global edge distribution with compliance-aware routing and intelligent service discovery*

## Overview

The Edge Computing module provides comprehensive capabilities for deploying workflows across global edge locations with automatic compliance routing, intelligent service discovery, and performance optimization. This guide covers edge location management, compliance-aware routing, distributed agent networks, and container orchestration.

## Prerequisites

- Completed [Durable Gateway Guide](29-durable-gateway-guide.md)
- Understanding of distributed systems concepts
- Familiarity with compliance requirements (GDPR, CCPA, HIPAA)

## Core Edge Computing Features

### EdgeDiscovery

Intelligent edge location discovery with multiple selection strategies.

```python
from kailash.edge.discovery import EdgeDiscovery, EdgeDiscoveryRequest, EdgeSelectionStrategy
from kailash.edge.location import EdgeRegion, DataClassification
from kailash.edge.compliance import ComplianceZone

# Initialize edge discovery
edge_discovery = EdgeDiscovery()

# Configure discovery request
discovery_request = EdgeDiscoveryRequest(
    # Geographic requirements
    preferred_regions=[EdgeRegion.US_EAST, EdgeRegion.EU_WEST],
    max_latency_ms=100,
    # Note: geographic_coordinates parameter not available in EdgeDiscoveryRequest

    # Resource requirements
    min_cpu_cores=4,
    min_memory_gb=8,
    min_storage_gb=100,
    requires_gpu=False,

    # Compliance requirements
    # Note: data_classification parameter not available in EdgeDiscoveryRequest
    compliance_zones=[ComplianceZone.GDPR, ComplianceZone.CCPA],
    data_residency_country="US",

    # Performance requirements
    bandwidth_requirements=1.0,  # Gbps
    max_cost_per_hour=0.50,
    min_uptime_percentage=99.9
)

# Discover optimal edge locations
discovery_result = await edge_discovery.discover_locations(
    request=discovery_request,
    strategy=EdgeSelectionStrategy.BALANCED,
    max_results=5
)

print(f"Found {len(discovery_result.locations)} suitable edge locations:")
for location in discovery_result.locations:
    print(f"- {location.name} in {location.region.value}")
    print(f"  Latency: {location.metrics.latency_ms}ms")
    print(f"  Score: {location.score.total_score:.2f}")
    print(f"  Cost: ${location.metrics.cost_per_hour:.3f}/hour")
```

### Edge Location Management

Comprehensive edge location configuration and monitoring.

```python
from kailash.edge.location import EdgeLocation, EdgeCapabilities, EdgeMetrics
from kailash.edge.discovery import EdgeScore

# Register a new edge location
edge_location = EdgeLocation(
    id="edge-nyc-01",
    name="New York Edge 1",
    region=EdgeRegion.US_EAST_1,

    # Geographic positioning
    geographic_coordinates={
        "latitude": 40.7128,
        "longitude": -74.0060
    },

    # Capabilities
    capabilities=EdgeCapabilities(
        cpu_cores=16,
        memory_gb=64,
        storage_gb=1000,
        gpu_available=True,
        gpu_count=2,
        network_bandwidth_gbps=10,
        supports_containers=True,
        supports_serverless=True,
        cdn_available=True,
        cache_size_gb=500
    ),

    # Real-time metrics
    metrics=EdgeMetrics(
        latency_ms=45,
        availability_percent=99.95,
        cpu_utilization=0.35,
        memory_utilization=0.42,
        storage_utilization=0.28,
        network_utilization=0.15,
        cost_per_hour=0.45,
        current_workloads=8,
        max_workloads=50
    ),

    # Compliance and regulations
    compliance_zones=[ComplianceZone.GDPR, ComplianceZone.CCPA],
    data_residency_countries=["US"],

    # Health status
    is_healthy=True,
    last_health_check=datetime.now(),
    health_check_interval_seconds=30
)

# Register the location
await edge_discovery.register_location(edge_location)

# Monitor edge location health
health_status = await edge_discovery.check_location_health(edge_location.id)
print(f"Location health: {health_status.status}")
print(f"Response time: {health_status.response_time_ms}ms")
print(f"Available resources: {health_status.available_resources}")
```

### Edge Selection Strategies

Multiple intelligent strategies for optimal edge selection.

```python
# Latency-optimized selection
latency_locations = await edge_discovery.discover_locations(
    request=discovery_request,
    strategy=EdgeSelectionStrategy.LATENCY_OPTIMAL,
    max_results=3
)

# Cost-optimized selection
cost_locations = await edge_discovery.discover_locations(
    request=discovery_request,
    strategy=EdgeSelectionStrategy.COST_OPTIMAL,
    max_results=3
)

# Performance-optimized selection
performance_locations = await edge_discovery.discover_locations(
    request=discovery_request,
    strategy=EdgeSelectionStrategy.PERFORMANCE_OPTIMAL,
    max_results=3
)

# Load-balanced selection across regions
load_balanced_locations = await edge_discovery.discover_locations(
    request=discovery_request,
    strategy=EdgeSelectionStrategy.LOAD_BALANCED,
    max_results=5
)

# Compliance-first selection
compliance_locations = await edge_discovery.discover_locations(
    request=discovery_request,
    strategy=EdgeSelectionStrategy.COMPLIANCE_FIRST,
    max_results=3
)

# Custom weighted selection
custom_weights = {
    "latency": 0.4,
    "cost": 0.3,
    "availability": 0.2,
    "compliance": 0.1
}

custom_locations = await edge_discovery.discover_locations(
    request=discovery_request,
    strategy=EdgeSelectionStrategy.CUSTOM,
    selection_weights=custom_weights,
    max_results=3
)
```

## Compliance-Aware Routing

Automatic compliance routing based on data classification and regulatory requirements.

### ComplianceRouter

```python
from kailash.edge.compliance import ComplianceRouter, DataClassification, ComplianceZone

# Initialize compliance router
compliance_router = ComplianceRouter()

# Define data processing request
data_request = {
    "data_type": DataClassification.PHI,  # Protected Health Information
    "user_location": {"country": "US", "state": "CA"},
    "processing_type": "analytics",
    "data_sensitivity": "high",
    "retention_days": 2555,  # 7 years for healthcare
    "audit_required": True
}

# Get compliance-aware routing decision
routing_decision = await compliance_router.route_request(data_request)

print(f"Routing decision: {routing_decision.approved}")
print(f"Target zones: {routing_decision.approved_zones}")
print(f"Restrictions: {routing_decision.restrictions}")
print(f"Audit requirements: {routing_decision.audit_requirements}")

if routing_decision.approved:
    # Deploy to compliant edge locations
    compliant_locations = await edge_discovery.discover_locations(
        request=EdgeDiscoveryRequest(
            compliance_zones=routing_decision.approved_zones,
            data_classification=data_request["data_type"],
            data_residency_country="US"
        ),
        strategy=EdgeSelectionStrategy.COMPLIANCE_FIRST
    )

    print(f"Deploying to {len(compliant_locations.locations)} compliant locations")
```

### Multi-Zone Compliance Handling

```python
# Handle multi-jurisdictional data
multi_zone_request = {
    "data_type": DataClassification.PII,
    "user_locations": [
        {"country": "US", "state": "CA"},  # CCPA
        {"country": "DE"},                  # GDPR
        {"country": "CA"}                   # PIPEDA
    ],
    "processing_type": "machine_learning",
    "cross_border_transfer": True
}

# Get multi-zone routing strategy
multi_zone_routing = await compliance_router.route_multi_zone_request(multi_zone_request)

for zone, decision in multi_zone_routing.zone_decisions.items():
    print(f"{zone}: {decision.approved}")
    if decision.approved:
        print(f"  Allowed operations: {decision.allowed_operations}")
        print(f"  Data retention: {decision.max_retention_days} days")
        print(f"  Transfer restrictions: {decision.transfer_restrictions}")

# Deploy with zone-specific compliance
for zone, decision in multi_zone_routing.zone_decisions.items():
    if decision.approved:
        zone_locations = await edge_discovery.discover_locations(
            request=EdgeDiscoveryRequest(
                compliance_zones=[zone],
                data_classification=multi_zone_request["data_type"]
            ),
            strategy=EdgeSelectionStrategy.COMPLIANCE_FIRST
        )

        # Deploy zone-specific workflows
        await deploy_compliant_workflow(zone_locations.locations, decision)
```

## MCP Service Discovery

Intelligent MCP server discovery with health monitoring and load balancing.

### ServiceRegistry

```python
from kailash.mcp_server.discovery import ServiceRegistry, FileBasedDiscovery, NetworkDiscovery
from kailash.mcp_server.discovery import HealthChecker, ServiceMesh, LoadBalancer

# Initialize service registry with multiple backends
file_backend = FileBasedDiscovery(
    registry_path="/etc/mcp/servers.json"
)

network_backend = NetworkDiscovery(
    broadcast_port=8765,
    multicast_group="239.255.0.1",
    scan_interval_seconds=30,
    discovery_timeout_seconds=5
)

service_registry = ServiceRegistry(backends=[file_backend, network_backend])

# Configure health checking
health_checker = HealthChecker(
    check_interval_seconds=30,
    timeout_seconds=10,
    max_failures=3,
    recovery_check_interval_seconds=60
)

# Initialize service mesh with load balancing
load_balancer = LoadBalancer(
    strategy="round_robin",  # "least_connections", "weighted", "latency_based"
    health_check_enabled=True,
    fail_fast=True
)

service_mesh = ServiceMesh(
    registry=service_registry,
    health_checker=health_checker,
    load_balancer=load_balancer
)

# Start service discovery
await service_mesh.start()

# Discover MCP servers by capability
servers = await service_mesh.discover_servers(
    capabilities=["file_operations", "data_analysis"],
    min_version="1.0.0",
    health_status="healthy",
    max_latency_ms=100
)

print(f"Found {len(servers)} suitable MCP servers:")
for server in servers:
    print(f"- {server.name} at {server.transport.uri}")
    print(f"  Capabilities: {server.capabilities}")
    print(f"  Health: {server.health_status}")
    print(f"  Latency: {server.metrics.avg_latency_ms}ms")
```

### Advanced Service Discovery

```python
# Register a new MCP server
server_info = {
    "name": "edge-analytics-server",
    "version": "2.1.0",
    "transport": {
        "type": "http",
        "uri": "http://edge-nyc-01:8080",
        "authentication": "bearer_token"
    },
    "capabilities": [
        "data_analysis",
        "machine_learning",
        "real_time_processing"
    ],
    "metadata": {
        "region": "us-east-1",
        "compliance": ["GDPR", "CCPA"],
        "max_concurrent_requests": 100,
        "supported_data_types": ["json", "csv", "parquet"]
    }
}

await service_registry.register_server(server_info)

# Query servers with complex filters
analytics_servers = await service_mesh.query_servers({
    "capabilities": {"contains": "data_analysis"},
    "metadata.region": {"in": ["us-east-1", "us-west-2"]},
    "metadata.compliance": {"contains": "GDPR"},
    "health_status": "healthy",
    "version": {">=": "2.0.0"}
})

# Get server with intelligent load balancing
selected_server = await service_mesh.select_server(
    filters={"capabilities": {"contains": "machine_learning"}},
    strategy="latency_based",
    exclude_overloaded=True
)

print(f"Selected server: {selected_server.name}")
print(f"Current load: {selected_server.metrics.current_requests}")
print(f"Average latency: {selected_server.metrics.avg_latency_ms}ms")
```

## Distributed Agent Networks

Self-organizing multi-agent systems with intelligent coordination.

### Multi-Agent Architecture

```python
from kailash.nodes.ai.intelligent_agent_orchestrator import IntelligentCacheNode, MCPAgentNode
from kailash.nodes.ai.intelligent_agent_orchestrator import OrchestrationManagerNode, ConvergenceDetectorNode

# Initialize distributed agent network
coordinator_agent = MCPAgentNode(
    name="coordinator_agent",
    role="coordinator",
    capabilities=["task_delegation", "result_aggregation", "coordination"],
    mcp_server_uri="http://coordinator:8080",
    max_delegated_tasks=10
)

analyst_agents = [
    MCPAgentNode(
        name=f"analyst_agent_{i}",
        role="analyst",
        capabilities=["data_analysis", "pattern_recognition", "reporting"],
        mcp_server_uri=f"http://analyst-{i}:8080",
        specialization="financial" if i % 2 == 0 else "operational"
    )
    for i in range(4)
]

processor_agents = [
    MCPAgentNode(
        name=f"processor_agent_{i}",
        role="processor",
        capabilities=["data_transformation", "feature_engineering", "validation"],
        mcp_server_uri=f"http://processor-{i}:8080",
        processing_capacity=1000
    )
    for i in range(6)
]

# Initialize intelligent caching
intelligent_cache = IntelligentCacheNode(
    name="intelligent_cache",
    cache_size_mb=1024,
    ttl_seconds=3600,
    cost_threshold=0.10,  # Cache if cost > $0.10
    similarity_threshold=0.95  # Cache similar requests
)

# Initialize orchestration manager
orchestration_manager = OrchestrationManagerNode(
    name="orchestration_manager",
    agents=[coordinator_agent] + analyst_agents + processor_agents,
    load_balancing_strategy="capability_based",
    fault_tolerance_enabled=True,
    auto_scaling_enabled=True
)

# Initialize convergence detector
convergence_detector = ConvergenceDetectorNode(
    name="convergence_detector",
    convergence_threshold=0.98,
    max_iterations=10,
    consensus_algorithm="weighted_average",
    quality_metrics=["accuracy", "confidence", "completeness"]
)

# Deploy agents across edge locations
agent_deployment = await deploy_agents_to_edge(
    agents=analyst_agents + processor_agents,
    edge_locations=compliant_locations.locations,
    deployment_strategy="capability_matched",
    resource_requirements={"cpu_cores": 2, "memory_gb": 4}
)

print(f"Deployed {len(agent_deployment.successful)} agents successfully")
```

### Task Orchestration and Delegation

```python
# Define complex analysis task
analysis_task = {
    "task_id": "financial_analysis_2024_q1",
    "task_type": "financial_analysis",
    "data_sources": [
        {"type": "database", "connection": "prod_finance_db"},
        {"type": "api", "endpoint": "market_data_api"},
        {"type": "files", "path": "/data/quarterly_reports/"}
    ],
    "analysis_requirements": {
        "metrics": ["revenue", "profit_margin", "growth_rate"],
        "timeframe": "2024-Q1",
        "comparisons": ["yoy", "qoq"],
        "forecasting": {"periods": 4, "confidence_interval": 0.95}
    },
    "output_format": "comprehensive_report",
    "deadline": "2024-04-15T23:59:59Z"
}

# Orchestrate task execution
execution_result = await orchestration_manager.execute_task(
    task=analysis_task,
    execution_strategy="parallel_processing",
    fault_tolerance=True,
    progress_reporting=True
)

# Monitor task progress
async for progress_update in execution_result.progress_stream:
    print(f"Progress: {progress_update.completion_percentage:.1f}%")
    print(f"Active agents: {progress_update.active_agents}")
    print(f"Completed subtasks: {progress_update.completed_subtasks}")

    if progress_update.issues:
        print(f"Issues detected: {progress_update.issues}")

# Check for convergence
convergence_result = await convergence_detector.check_convergence(
    results=[agent.last_result for agent in execution_result.participating_agents],
    quality_threshold=0.95
)

if convergence_result.converged:
    print(f"Task converged after {convergence_result.iterations} iterations")
    print(f"Final confidence: {convergence_result.confidence:.3f}")
    print(f"Quality score: {convergence_result.quality_score:.3f}")
else:
    print("Task requires additional iterations or manual review")
    print(f"Convergence gap: {convergence_result.convergence_gap:.3f}")
```

## Container Orchestration

Docker-based distributed workflow execution across edge locations.

### DockerRuntime

```python
from kailash.runtime.docker import DockerRuntime

# Initialize Docker runtime for edge deployment
docker_runtime = DockerRuntime(
    name="edge_docker_runtime",

    # Container configuration
    base_image="python:3.11-slim",
    working_directory="/app",
    environment_variables={
        "PYTHONPATH": "/app",
        "LOG_LEVEL": "INFO",
        "EDGE_LOCATION": "us-east-1"
    },

    # Resource constraints
    cpu_limit=2.0,
    memory_limit="4g",
    storage_limit="10g",

    # Network configuration
    network_mode="bridge",
    port_mappings={"8080": "8080", "9090": "9090"},

    # Volume mounts
    volume_mounts={
        "/app/data": "/edge/data",
        "/app/models": "/edge/models",
        "/app/config": "/edge/config"
    },

    # Edge-specific configuration
    edge_optimized=True,
    auto_scaling=True,
    health_check_enabled=True
)

# Deploy workflow to multiple edge locations
edge_deployment = await docker_runtime.deploy_to_edge_locations(
    workflow_definition={
        "name": "distributed_analytics_workflow",
        "nodes": [
            {
                "name": "data_ingestion",
                "type": "DataIngestionNode",
                "config": {"batch_size": 1000, "format": "parquet"}
            },
            {
                "name": "feature_engineering",
                "type": "FeatureEngineeringNode",
                "config": {"features": ["numerical", "categorical", "temporal"]}
            },
            {
                "name": "model_inference",
                "type": "ModelInferenceNode",
                "config": {"model_path": "/edge/models/analytics_model.pkl"}
            },
            {
                "name": "result_aggregation",
                "type": "ResultAggregationNode",
                "config": {"aggregation_method": "weighted_average"}
            }
        ],
        "connections": [
            {"from": "data_ingestion", "to": "feature_engineering"},
            {"from": "feature_engineering", "to": "model_inference"},
            {"from": "model_inference", "to": "result_aggregation"}
        ]
    },

    target_locations=compliant_locations.locations,
    deployment_strategy="resource_optimized",
    failover_enabled=True,
    monitoring_enabled=True
)

print(f"Deployed to {len(edge_deployment.successful_deployments)} edge locations")

# Monitor deployment health
for deployment in edge_deployment.successful_deployments:
    health = await docker_runtime.check_deployment_health(deployment.deployment_id)
    print(f"{deployment.location.name}: {health.status}")
    print(f"  Containers: {health.running_containers}/{health.total_containers}")
    print(f"  CPU usage: {health.cpu_usage:.1f}%")
    print(f"  Memory usage: {health.memory_usage:.1f}%")
```

### Edge Workflow Coordination

```python
# Coordinate distributed workflow execution
coordination_config = {
    "coordination_strategy": "consensus_based",
    "data_partitioning": "geographic",
    "result_aggregation": "federated_averaging",
    "fault_tolerance": {
        "max_failures": 2,
        "auto_recovery": True,
        "backup_locations": True
    },
    "performance_optimization": {
        "load_balancing": True,
        "adaptive_batching": True,
        "compression_enabled": True
    }
}

# Execute coordinated workflow
coordination_result = await docker_runtime.execute_coordinated_workflow(
    workflow_id="distributed_analytics_workflow",
    coordination_config=coordination_config,
    input_data={
        "data_sources": ["regional_data_east", "regional_data_west"],
        "model_parameters": {"learning_rate": 0.001, "batch_size": 64},
        "validation_split": 0.2
    }
)

# Monitor coordination progress
async for coordination_update in coordination_result.progress_stream:
    print(f"Coordination phase: {coordination_update.current_phase}")
    print(f"Active locations: {coordination_update.active_locations}")
    print(f"Data processed: {coordination_update.data_processed_gb:.2f} GB")
    print(f"Intermediate results: {coordination_update.intermediate_results}")

# Aggregate final results
final_result = await coordination_result.get_aggregated_result()
print(f"Final accuracy: {final_result.metrics.accuracy:.3f}")
print(f"Total processing time: {final_result.execution_time_seconds:.1f}s")
print(f"Edge locations used: {final_result.participating_locations}")
```

## Production Edge Patterns

### Global Edge Deployment

```python
# Complete global edge deployment example
async def deploy_global_edge_analytics():
    """Deploy analytics workflow across global edge locations."""

    # Step 1: Discover global edge locations
    global_discovery = EdgeDiscoveryRequest(
        preferred_regions=[
            EdgeRegion.US_EAST_1, EdgeRegion.US_WEST_2,
            EdgeRegion.EU_WEST_1, EdgeRegion.EU_CENTRAL_1,
            EdgeRegion.ASIA_PACIFIC_1, EdgeRegion.ASIA_PACIFIC_2
        ],
        min_cpu_cores=8,
        min_memory_gb=16,
        requires_gpu=True,
        compliance_zones=[ComplianceZone.GDPR, ComplianceZone.CCPA],
        min_uptime_percentage=99.9
    )

    global_locations = await edge_discovery.discover_locations(
        request=global_discovery,
        strategy=EdgeSelectionStrategy.BALANCED,
        max_results=10
    )

    # Step 2: Setup compliance routing
    compliance_routing = await compliance_router.create_global_routing_plan(
        locations=global_locations.locations,
        data_types=[DataClassification.PII, DataClassification.COMMERCIAL],
        cross_region_transfers=True
    )

    # Step 3: Deploy MCP service mesh
    global_service_mesh = await deploy_global_service_mesh(
        locations=global_locations.locations,
        mesh_config={
            "service_discovery": True,
            "load_balancing": True,
            "fault_tolerance": True,
            "cross_region_communication": True
        }
    )

    # Step 4: Deploy distributed agents
    global_agent_network = await deploy_global_agent_network(
        locations=global_locations.locations,
        agent_types=["coordinator", "analyst", "processor"],
        redundancy_factor=2
    )

    # Step 5: Deploy analytics workflow
    global_workflow_deployment = await docker_runtime.deploy_global_workflow(
        workflow_definition=analytics_workflow_definition,
        locations=global_locations.locations,
        compliance_routing=compliance_routing,
        service_mesh=global_service_mesh,
        agent_network=global_agent_network
    )

    return {
        "deployment_id": global_workflow_deployment.deployment_id,
        "active_locations": len(global_workflow_deployment.active_locations),
        "compliance_zones": compliance_routing.covered_zones,
        "estimated_cost_per_hour": global_workflow_deployment.cost_estimate
    }

# Execute global deployment
global_deployment = await deploy_global_edge_analytics()
print(f"Global deployment completed: {global_deployment['deployment_id']}")
```

## Best Practices

### 1. Edge Location Selection

```python
# Optimize edge location selection for different use cases
def get_optimal_edge_strategy(use_case: str) -> dict:
    """Get optimal edge selection strategy for specific use cases."""
    strategies = {
        "real_time_processing": {
            "strategy": EdgeSelectionStrategy.LATENCY_OPTIMIZED,
            "max_latency_ms": 50,
            "min_bandwidth_mbps": 1000,
            "priority": "performance"
        },
        "batch_analytics": {
            "strategy": EdgeSelectionStrategy.COST_OPTIMIZED,
            "max_cost_per_hour": 0.25,
            "min_compute_capacity": "high",
            "priority": "cost_efficiency"
        },
        "compliance_critical": {
            "strategy": EdgeSelectionStrategy.COMPLIANCE_FIRST,
            "strict_data_residency": True,
            "audit_logging": True,
            "priority": "compliance"
        },
        "high_availability": {
            "strategy": EdgeSelectionStrategy.LOAD_BALANCED,
            "min_availability_sla": 99.99,
            "redundancy_factor": 3,
            "priority": "availability"
        }
    }

    return strategies.get(use_case, strategies["batch_analytics"])
```

### 2. Compliance Automation

```python
# Automate compliance decisions
async def ensure_compliance_automation():
    """Setup automated compliance handling."""

    # Configure compliance policies
    compliance_policies = {
        DataClassification.PII: {
            "allowed_zones": [ComplianceZone.GDPR, ComplianceZone.CCPA],
            "retention_days": 365,
            "encryption_required": True,
            "audit_trail": True
        },
        DataClassification.PHI: {
            "allowed_zones": [ComplianceZone.HIPAA],
            "retention_days": 2555,  # 7 years
            "encryption_required": True,
            "access_logging": True
        },
        DataClassification.FINANCIAL: {
            "allowed_zones": [ComplianceZone.SOX, ComplianceZone.PCI_DSS],
            "retention_days": 2555,
            "immutable_storage": True,
            "dual_authorization": True
        }
    }

    # Setup automated routing
    await compliance_router.configure_automated_routing(compliance_policies)

    # Enable compliance monitoring
    await compliance_router.enable_continuous_monitoring(
        alert_on_violations=True,
        auto_remediation=True,
        compliance_dashboard=True
    )
```

### 3. Performance Monitoring

```python
# Monitor edge performance across locations
async def monitor_edge_performance():
    """Comprehensive edge performance monitoring."""

    # Collect performance metrics
    performance_metrics = await edge_discovery.collect_global_metrics()

    # Analyze performance trends
    for location in performance_metrics.locations:
        if location.metrics.latency_ms > 100:
            print(f"High latency detected at {location.name}: {location.metrics.latency_ms}ms")

        if location.metrics.cpu_utilization > 0.8:
            print(f"High CPU usage at {location.name}: {location.metrics.cpu_utilization:.1%}")

        if location.metrics.availability_percent < 99.5:
            print(f"Low availability at {location.name}: {location.metrics.availability_percent:.2f}%")

    # Generate optimization recommendations
    optimization_recommendations = await edge_discovery.generate_optimization_recommendations(
        current_metrics=performance_metrics,
        target_sla={"latency_ms": 50, "availability_percent": 99.9}
    )

    return optimization_recommendations
```

## Related Guides

**Prerequisites:**
- [Durable Gateway Guide](29-durable-gateway-guide.md) - Gateway durability
- [Enterprise Security Nodes Guide](28-enterprise-security-nodes-guide.md) - Security features

**Next Steps:**
- [Cyclic Workflows Guide](31-cyclic-workflows-guide.md) - Workflow cycles
- [MCP Node Development Guide](32-mcp-node-development-guide.md) - Custom MCP nodes

---

**Deploy AI workloads globally with intelligent edge computing and compliance automation!**
