"""
Auto-Discovery Routing MCP Pattern - Production Implementation

Demonstrates automatic service discovery and intelligent routing across multiple
MCP servers using Kailash SDK's production-ready ServiceRegistry and ServiceMesh.

This example shows:
1. Service discovery using ServiceRegistry
2. Automatic routing based on capabilities
3. Load balancing with ServiceMesh
4. Health checking and failover
5. Performance-based routing decisions

Uses kailash.mcp_server (NOT deprecated kaizen.mcp).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# Kailash SDK MCP - Production infrastructure
try:
    from kailash.mcp_server import (
        MCPClient,
        ServerInfo,
        ServiceMesh,
        ServiceRegistry,
        discover_mcp_servers,
    )

    KAILASH_MCP_AVAILABLE = True
except ImportError:
    KAILASH_MCP_AVAILABLE = False
    print(
        "Warning: kailash.mcp_server not available. Install with: pip install kailash"
    )

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==============================================================================
# SIGNATURES
# ==============================================================================


class ServiceDiscoverySignature(Signature):
    """Discover and catalog available MCP services."""

    discovery_scope: str = InputField(
        description="Discovery scope and search parameters"
    )
    capability_requirements: str = InputField(
        description="Required service capabilities"
    )

    discovered_services: str = OutputField(description="Catalog of discovered services")
    capability_mapping: str = OutputField(description="Service capabilities mapping")
    discovery_insights: str = OutputField(description="Discovery insights")


class IntelligentRoutingSignature(Signature):
    """Route requests to optimal MCP services."""

    service_request: str = InputField(description="Service request with requirements")
    available_services: str = InputField(description="Available services and status")
    routing_criteria: str = InputField(description="Routing optimization criteria")

    routing_decision: str = OutputField(description="Optimal service routing decision")
    routing_rationale: str = OutputField(description="Routing decision explanation")
    fallback_options: str = OutputField(description="Alternative routing options")


# ==============================================================================
# CONFIGURATION
# ==============================================================================


@dataclass
class AutoDiscoveryAgentConfig(BaseAgentConfig):
    """Configuration for auto-discovery routing agent."""

    # Service discovery settings
    discovery_interval_seconds: int = 60
    enable_auto_refresh: bool = True
    discovery_timeout: float = 30.0

    # Routing settings
    routing_strategy: str = (
        "capability_match"  # capability_match, load_balance, performance
    )
    max_failover_attempts: int = 3
    health_check_interval: int = 30

    # Performance settings
    enable_performance_tracking: bool = True
    performance_window_minutes: int = 15
    prefer_low_latency: bool = True

    # Service mesh settings
    enable_service_mesh: bool = True
    load_balancing_strategy: str = "round_robin"  # round_robin, least_loaded, random

    # Initial server configurations
    initial_servers: List[Dict[str, Any]] = field(default_factory=list)


# ==============================================================================
# AUTO-DISCOVERY ROUTING AGENT
# ==============================================================================


class AutoDiscoveryRoutingAgent(BaseAgent):
    """
    Agent that automatically discovers MCP services and routes requests
    intelligently based on capabilities, performance, and load.

    Uses Kailash SDK's ServiceRegistry and ServiceMesh for production-ready
    service discovery and load balancing.
    """

    def __init__(self, config: AutoDiscoveryAgentConfig):
        """Initialize auto-discovery routing agent."""
        super().__init__(config=config, signature=ServiceDiscoverySignature())

        if not KAILASH_MCP_AVAILABLE:
            raise ImportError(
                "kailash.mcp_server required for auto-discovery routing. "
                "Install with: pip install kailash"
            )

        self.config: AutoDiscoveryAgentConfig = config

        # Service infrastructure
        self.registry: Optional[ServiceRegistry] = None
        self.service_mesh: Optional[ServiceMesh] = None
        self.mcp_client: Optional[MCPClient] = None

        # Performance tracking
        self.service_performance: Dict[str, Dict[str, Any]] = {}
        self.routing_history: List[Dict[str, Any]] = []

        # Discovery state
        self.last_discovery_time: Optional[datetime] = None
        self.discovered_services: Dict[str, ServerInfo] = {}

        logger.info(
            f"AutoDiscoveryRoutingAgent initialized with "
            f"strategy={config.routing_strategy}, "
            f"mesh={config.enable_service_mesh}"
        )

    async def initialize(self):
        """Initialize service discovery infrastructure."""
        logger.info("Initializing service discovery infrastructure...")

        # Create service registry
        self.registry = ServiceRegistry()

        # Create service mesh for load balancing
        if self.config.enable_service_mesh:
            self.service_mesh = ServiceMesh(
                registry=self.registry, strategy=self.config.load_balancing_strategy
            )

        # Create MCP client
        self.mcp_client = MCPClient(
            retry_strategy="circuit_breaker",
            enable_metrics=True,
            circuit_breaker_config={"failure_threshold": 5, "recovery_timeout": 60},
        )

        # Register initial servers
        if self.config.initial_servers:
            for server_config in self.config.initial_servers:
                await self._register_server(server_config)

        # Perform initial discovery
        await self.discover_services()

        logger.info(
            f"Service discovery initialized: "
            f"{len(self.discovered_services)} services registered"
        )

    async def _register_server(self, server_config: Dict[str, Any]):
        """Register a server in the service registry."""
        server_info = ServerInfo(
            name=server_config["name"],
            transport=server_config["transport"],
            url=server_config.get("url"),
            capabilities=server_config.get("capabilities", []),
            metadata=server_config.get("metadata", {}),
        )

        await self.registry.register_server(server_info)

        # Initialize performance tracking
        self.service_performance[server_config["name"]] = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "average_latency": 0.0,
            "last_health_check": None,
        }

    async def discover_services(self) -> Dict[str, ServerInfo]:
        """
        Discover available MCP services using service registry and network discovery.

        Returns:
            Dictionary of discovered services by name
        """
        logger.info("Starting service discovery...")

        # Discover via network (if available)
        try:
            network_services = await discover_mcp_servers()
            logger.info(f"Discovered {len(network_services)} services via network")

            # Register newly discovered services
            for service in network_services:
                if service.name not in self.discovered_services:
                    await self.registry.register_server(service)
                    self.discovered_services[service.name] = service
        except Exception as e:
            logger.warning(f"Network discovery failed: {e}")

        # Get all registered services
        all_services = await self.registry.discover_servers()

        # Update discovered services
        for service in all_services:
            self.discovered_services[service.name] = service

        # Update discovery timestamp
        self.last_discovery_time = datetime.now()

        # Store in memory
        if self.shared_memory:
            self.write_to_memory(
                content={
                    "event": "service_discovery",
                    "timestamp": self.last_discovery_time.isoformat(),
                    "services_found": len(self.discovered_services),
                    "services": [s.name for s in self.discovered_services.values()],
                },
                tags=["discovery", "service_registry"],
                importance=0.7,
            )

        logger.info(
            f"Service discovery complete: {len(self.discovered_services)} services available"
        )

        return self.discovered_services

    async def route_request(
        self,
        request_type: str,
        tool_name: str,
        arguments: Dict[str, Any],
        required_capabilities: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Intelligently route a request to the optimal MCP service.

        Args:
            request_type: Type of request (e.g., "search", "compute", "analyze")
            tool_name: Name of the tool to invoke
            arguments: Tool arguments
            required_capabilities: Required service capabilities

        Returns:
            Tool invocation result with routing metadata
        """
        logger.info(f"Routing request: type={request_type}, tool={tool_name}")

        # Find suitable services
        suitable_services = await self._find_suitable_services(
            request_type=request_type, required_capabilities=required_capabilities or []
        )

        if not suitable_services:
            logger.error(f"No suitable services found for request type: {request_type}")
            return {
                "success": False,
                "error": "No suitable services available",
                "request_type": request_type,
            }

        # Select best service based on routing strategy
        selected_service = await self._select_best_service(
            suitable_services=suitable_services, strategy=self.config.routing_strategy
        )

        logger.info(
            f"Selected service: {selected_service.name} (strategy={self.config.routing_strategy})"
        )

        # Invoke tool with failover
        result = await self._invoke_with_failover(
            service=selected_service,
            tool_name=tool_name,
            arguments=arguments,
            fallback_services=suitable_services[1:],  # Remaining services as fallbacks
        )

        # Track routing decision
        self._track_routing(
            service=selected_service,
            request_type=request_type,
            tool_name=tool_name,
            success=result.get("success", False),
            latency=result.get("latency", 0.0),
        )

        # Add routing metadata
        result["routing_metadata"] = {
            "selected_service": selected_service.name,
            "routing_strategy": self.config.routing_strategy,
            "alternatives_available": len(suitable_services) - 1,
            "discovery_age_seconds": (
                (datetime.now() - self.last_discovery_time).total_seconds()
                if self.last_discovery_time
                else None
            ),
        }

        return result

    async def _find_suitable_services(
        self, request_type: str, required_capabilities: List[str]
    ) -> List[ServerInfo]:
        """Find services that match the request requirements."""
        suitable = []

        for service in self.discovered_services.values():
            # Check if service has required capabilities
            service_capabilities = set(service.capabilities or [])

            # Match request type
            if request_type and request_type not in service_capabilities:
                continue

            # Match required capabilities
            if required_capabilities:
                if not all(
                    cap in service_capabilities for cap in required_capabilities
                ):
                    continue

            # Check health
            perf = self.service_performance.get(service.name, {})
            if perf.get("failed_requests", 0) > 10:
                logger.warning(
                    f"Service {service.name} has high failure rate, skipping"
                )
                continue

            suitable.append(service)

        return suitable

    async def _select_best_service(
        self, suitable_services: List[ServerInfo], strategy: str
    ) -> ServerInfo:
        """Select the best service based on routing strategy."""
        if not suitable_services:
            raise ValueError("No suitable services available")

        if strategy == "capability_match":
            # Return first matching service
            return suitable_services[0]

        elif strategy == "load_balance":
            # Use service mesh for load balancing
            if self.service_mesh:
                return await self.service_mesh.select_server(
                    capability=(
                        suitable_services[0].capabilities[0]
                        if suitable_services[0].capabilities
                        else None
                    )
                )
            return suitable_services[0]

        elif strategy == "performance":
            # Select service with best performance
            best_service = suitable_services[0]
            best_latency = float("inf")

            for service in suitable_services:
                perf = self.service_performance.get(service.name, {})
                latency = perf.get("average_latency", float("inf"))

                if latency < best_latency:
                    best_latency = latency
                    best_service = service

            return best_service

        else:
            return suitable_services[0]

    async def _invoke_with_failover(
        self,
        service: ServerInfo,
        tool_name: str,
        arguments: Dict[str, Any],
        fallback_services: List[ServerInfo],
    ) -> Dict[str, Any]:
        """Invoke tool with automatic failover to backup services."""
        import time

        # Try primary service
        start_time = time.time()
        try:
            server_config = {
                "name": service.name,
                "transport": service.transport,
                "url": service.url,
            }

            result = await self.mcp_client.call_tool(
                server_config,
                tool_name,
                arguments,
                timeout=self.config.discovery_timeout,
            )

            latency = time.time() - start_time

            return {
                "success": True,
                "result": result,
                "latency": latency,
                "service_used": service.name,
                "failover_attempts": 0,
            }

        except Exception as e:
            logger.warning(f"Service {service.name} failed: {e}")

            # Try fallback services
            for i, fallback in enumerate(
                fallback_services[: self.config.max_failover_attempts]
            ):
                try:
                    fallback_config = {
                        "name": fallback.name,
                        "transport": fallback.transport,
                        "url": fallback.url,
                    }

                    result = await self.mcp_client.call_tool(
                        fallback_config,
                        tool_name,
                        arguments,
                        timeout=self.config.discovery_timeout,
                    )

                    latency = time.time() - start_time

                    logger.info(f"Failover to {fallback.name} succeeded")

                    return {
                        "success": True,
                        "result": result,
                        "latency": latency,
                        "service_used": fallback.name,
                        "failover_attempts": i + 1,
                        "primary_service_failed": service.name,
                    }

                except Exception as fallback_error:
                    logger.warning(
                        f"Failover service {fallback.name} failed: {fallback_error}"
                    )
                    continue

            # All services failed
            return {
                "success": False,
                "error": f"All services failed. Primary: {str(e)}",
                "service_attempted": service.name,
                "failover_attempts": len(fallback_services),
            }

    def _track_routing(
        self,
        service: ServerInfo,
        request_type: str,
        tool_name: str,
        success: bool,
        latency: float,
    ):
        """Track routing decision for performance analysis."""
        # Update service performance
        perf = self.service_performance.get(
            service.name,
            {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "average_latency": 0.0,
            },
        )

        perf["total_requests"] += 1
        if success:
            perf["successful_requests"] += 1
        else:
            perf["failed_requests"] += 1

        # Update average latency
        total = perf["total_requests"]
        perf["average_latency"] = (
            perf["average_latency"] * (total - 1) + latency
        ) / total

        self.service_performance[service.name] = perf

        # Track routing history
        routing_event = {
            "timestamp": datetime.now().isoformat(),
            "service": service.name,
            "request_type": request_type,
            "tool": tool_name,
            "success": success,
            "latency": latency,
        }

        self.routing_history.append(routing_event)

        # Store in memory
        if self.shared_memory:
            self.write_to_memory(
                content=routing_event,
                tags=["routing", "performance", service.name],
                importance=0.6,
            )

    async def get_service_health(self) -> Dict[str, Any]:
        """Get health status of all registered services."""
        health_status = {}

        for service_name, perf in self.service_performance.items():
            total = perf["total_requests"]
            success_rate = perf["successful_requests"] / total if total > 0 else 0.0

            health_status[service_name] = {
                "healthy": success_rate > 0.8 and perf["failed_requests"] < 10,
                "success_rate": success_rate,
                "total_requests": total,
                "average_latency": perf["average_latency"],
            }

        return health_status

    async def refresh_discovery(self):
        """Refresh service discovery (called periodically)."""
        logger.info("Refreshing service discovery...")
        await self.discover_services()

    def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report."""
        return {
            "services": self.service_performance,
            "total_routing_decisions": len(self.routing_history),
            "discovery_age_seconds": (
                (datetime.now() - self.last_discovery_time).total_seconds()
                if self.last_discovery_time
                else None
            ),
        }


# ==============================================================================
# EXAMPLE USAGE
# ==============================================================================


async def main():
    """Example usage of auto-discovery routing agent."""
    print("=== Auto-Discovery Routing Agent Example ===\n")

    # Configure agent with multiple servers
    config = AutoDiscoveryAgentConfig(
        llm_provider="mock",
        model="test-model",
        routing_strategy="performance",
        enable_service_mesh=True,
        initial_servers=[
            {
                "name": "search-server-1",
                "transport": "http",
                "url": "http://localhost:8080",
                "capabilities": ["search", "web_search"],
            },
            {
                "name": "search-server-2",
                "transport": "http",
                "url": "http://localhost:8081",
                "capabilities": ["search", "web_search"],
            },
            {
                "name": "compute-server",
                "transport": "stdio",
                "capabilities": ["compute", "calculate"],
            },
        ],
    )

    # Create agent with shared memory
    memory = SharedMemoryPool()
    agent = AutoDiscoveryRoutingAgent(config)
    agent.shared_memory = memory

    # Initialize service discovery
    await agent.initialize()

    print(f"✅ Discovered {len(agent.discovered_services)} services")
    for name, service in agent.discovered_services.items():
        print(f"   - {name}: {service.capabilities}")

    # Route requests
    print("\n=== Routing Requests ===\n")

    # Request 1: Search request (will route to search servers)
    result1 = await agent.route_request(
        request_type="search",
        tool_name="web_search",
        arguments={"query": "AI research"},
        required_capabilities=["search"],
    )

    print(
        f"Request 1: service={result1.get('routing_metadata', {}).get('selected_service')}"
    )

    # Request 2: Compute request (will route to compute server)
    result2 = await agent.route_request(
        request_type="compute",
        tool_name="calculate",
        arguments={"expression": "2 + 2"},
        required_capabilities=["compute"],
    )

    print(
        f"Request 2: service={result2.get('routing_metadata', {}).get('selected_service')}"
    )

    # Get service health
    print("\n=== Service Health ===\n")
    health = await agent.get_service_health()
    for service_name, status in health.items():
        print(
            f"{service_name}: {'✅ Healthy' if status['healthy'] else '❌ Unhealthy'}"
        )
        print(f"  Success rate: {status['success_rate']:.1%}")
        print(f"  Avg latency: {status['average_latency']:.3f}s")

    # Performance report
    print("\n=== Performance Report ===\n")
    report = agent.get_performance_report()
    print(f"Total routing decisions: {report['total_routing_decisions']}")
    print(f"Discovery age: {report['discovery_age_seconds']:.1f}s")

    print("\n✅ Auto-discovery routing example complete")


if __name__ == "__main__":
    asyncio.run(main())
