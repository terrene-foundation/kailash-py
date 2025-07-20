"""Edge infrastructure management for WorkflowBuilder.

This module provides a singleton EdgeInfrastructure class that manages
shared edge computing resources across workflows, including EdgeDiscovery
and ComplianceRouter instances.
"""

import asyncio
import logging
import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from kailash.edge.compliance import ComplianceRouter
from kailash.edge.discovery import EdgeDiscovery
from kailash.edge.location import EdgeLocation
from kailash.utils.resource_manager import AsyncResourcePool

logger = logging.getLogger(__name__)


class EdgeInfrastructure:
    """Singleton class managing shared edge infrastructure for workflows.

    This class provides centralized management of edge computing resources
    including discovery service, compliance routing, and connection pooling.
    It follows the singleton pattern to ensure resource sharing across
    multiple workflows and edge nodes.
    """

    _instance: Optional["EdgeInfrastructure"] = None
    _lock = threading.Lock()

    def __new__(cls, config: Optional[Dict[str, Any]] = None):
        """Create or return the singleton instance.

        Args:
            config: Edge infrastructure configuration

        Returns:
            The singleton EdgeInfrastructure instance
        """
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the edge infrastructure.

        Args:
            config: Edge infrastructure configuration
        """
        # Only initialize once
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            logger.info("Initializing EdgeInfrastructure singleton")

            # Merge with defaults
            self._config = self._merge_with_defaults(config or {})

            # Lazy-initialized components
            self._discovery: Optional[EdgeDiscovery] = None
            self._compliance_router: Optional[ComplianceRouter] = None
            self._connection_pools: Dict[str, AsyncResourcePool] = {}

            # Metrics tracking
            self._metrics = {
                "edge_nodes_registered": 0,
                "active_connections": 0,
                "total_requests": 0,
                "latency_by_location": defaultdict(
                    lambda: {"count": 0, "total": 0, "avg": 0}
                ),
            }

            # Node registry
            self._edge_nodes: Dict[str, Dict[str, Any]] = {}

            # Infrastructure state
            self._start_time = time.time()
            self._initialized = True

    def _merge_with_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge user config with default values.

        Args:
            config: User-provided configuration

        Returns:
            Merged configuration
        """
        defaults = {
            "discovery": {
                "locations": [],
                "refresh_interval": 300,
                "selection_strategy": "balanced",
            },
            "compliance": {
                "strict_mode": True,
                "default_classification": "public",
                "audit_logging": True,
            },
            "performance": {
                "connection_pool_size": 10,
                "health_check_interval": 60,
                "request_timeout": 30,
            },
        }

        # Deep merge
        merged = defaults.copy()
        for key, value in config.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key].update(value)
            else:
                merged[key] = value

        return merged

    def get_discovery(self) -> EdgeDiscovery:
        """Get or create the EdgeDiscovery instance.

        Returns:
            The shared EdgeDiscovery instance
        """
        if self._discovery is None:
            with self._lock:
                if self._discovery is None:
                    logger.debug("Creating EdgeDiscovery instance")

                    # Load predefined locations from config
                    locations = []
                    for location_id in self._config["discovery"]["locations"]:
                        # Import here to avoid circular dependency
                        from kailash.edge.location import get_predefined_location

                        location = get_predefined_location(location_id)
                        if location:
                            locations.append(location)

                    self._discovery = EdgeDiscovery(locations=locations)

        return self._discovery

    def get_compliance_router(self) -> ComplianceRouter:
        """Get or create the ComplianceRouter instance.

        Returns:
            The shared ComplianceRouter instance
        """
        if self._compliance_router is None:
            with self._lock:
                if self._compliance_router is None:
                    logger.debug("Creating ComplianceRouter instance")
                    self._compliance_router = ComplianceRouter()

        return self._compliance_router

    def get_connection_pool(self, location_id: str) -> AsyncResourcePool:
        """Get or create a connection pool for an edge location.

        Args:
            location_id: Edge location identifier

        Returns:
            Connection pool for the location
        """
        if location_id not in self._connection_pools:
            with self._lock:
                if location_id not in self._connection_pools:
                    logger.debug(f"Creating connection pool for {location_id}")

                    async def create_connection():
                        # Placeholder for actual edge connection creation
                        # In real implementation, this would create connections
                        # to the edge location's services
                        return {"location": location_id, "connected": True}

                    async def cleanup_connection(conn):
                        # Placeholder for connection cleanup
                        logger.debug(f"Cleaning up connection to {location_id}")

                    pool = AsyncResourcePool(
                        factory=create_connection,
                        max_size=self._config["performance"]["connection_pool_size"],
                        timeout=self._config["performance"]["request_timeout"],
                        cleanup=cleanup_connection,
                    )

                    self._connection_pools[location_id] = pool

        return self._connection_pools[location_id]

    def is_edge_node(self, node_type: str) -> bool:
        """Check if a node type is an edge node.

        Args:
            node_type: The node type to check

        Returns:
            True if the node is an edge node
        """
        # Check exact matches and subclasses
        edge_prefixes = ["Edge", "edge"]
        edge_suffixes = [
            "EdgeNode",
            "EdgeDataNode",
            "EdgeStateMachine",
            "EdgeCacheNode",
        ]
        edge_keywords = ["Edge", "edge"]

        # Exact match
        if node_type in edge_suffixes:
            return True

        # Check if it starts with Edge/edge
        for prefix in edge_prefixes:
            if node_type.startswith(prefix):
                return True

        # Check if it ends with EdgeNode (for custom edge nodes)
        if node_type.endswith("EdgeNode"):
            return True

        # Check if it contains Edge keywords (for variations like MyEdgeDataNode)
        for keyword in edge_keywords:
            if keyword in node_type:
                return True

        return False

    def register_edge_node(self, node_id: str, node_info: Dict[str, Any]):
        """Register an edge node with the infrastructure.

        Args:
            node_id: Unique node identifier
            node_info: Node information including type and config
        """
        with self._lock:
            self._edge_nodes[node_id] = {**node_info, "registered_at": time.time()}
            self._metrics["edge_nodes_registered"] = len(self._edge_nodes)
            logger.debug(f"Registered edge node: {node_id}")

    def add_location(self, location: EdgeLocation):
        """Add an edge location to the discovery service.

        Args:
            location: EdgeLocation to add
        """
        discovery = self.get_discovery()
        discovery.add_location(location)
        logger.info(f"Added edge location: {location.location_id}")

    def get_all_locations(self) -> List[EdgeLocation]:
        """Get all registered edge locations.

        Returns:
            List of EdgeLocation instances
        """
        discovery = self.get_discovery()
        return discovery.get_all_edges()

    async def select_edge(self, criteria: Dict[str, Any]) -> Optional[EdgeLocation]:
        """Select an edge location based on criteria.

        Args:
            criteria: Selection criteria

        Returns:
            Selected EdgeLocation or None
        """
        discovery = self.get_discovery()
        return await discovery.select_edge(criteria)

    def record_request(self, location_id: str, latency_ms: float):
        """Record a request for metrics tracking.

        Args:
            location_id: Edge location that handled the request
            latency_ms: Request latency in milliseconds
        """
        with self._lock:
            self._metrics["total_requests"] += 1

            location_metrics = self._metrics["latency_by_location"][location_id]
            location_metrics["count"] += 1
            location_metrics["total"] += latency_ms
            location_metrics["avg"] = (
                location_metrics["total"] / location_metrics["count"]
            )

    def get_metrics(self) -> Dict[str, Any]:
        """Get infrastructure metrics.

        Returns:
            Dictionary of metrics
        """
        with self._lock:
            return {
                **self._metrics,
                "uptime_seconds": time.time() - self._start_time,
                "connection_pools": len(self._connection_pools),
            }

    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of the infrastructure.

        Returns:
            Health status dictionary
        """
        with self._lock:
            discovery_initialized = self._discovery is not None
            compliance_initialized = self._compliance_router is not None

            health = {
                "status": "healthy",
                "uptime_seconds": time.time() - self._start_time,
                "discovery": {
                    "initialized": discovery_initialized,
                    "location_count": (
                        len(self.get_all_locations()) if discovery_initialized else 0
                    ),
                },
                "compliance": {
                    "initialized": compliance_initialized,
                    "strict_mode": self._config["compliance"]["strict_mode"],
                },
                "metrics": {
                    "edge_nodes": self._metrics["edge_nodes_registered"],
                    "total_requests": self._metrics["total_requests"],
                },
            }

            return health

    async def cleanup(self):
        """Clean up all resources asynchronously."""
        logger.info("Cleaning up EdgeInfrastructure resources")

        # Clean up connection pools
        cleanup_tasks = []
        for location_id, pool in self._connection_pools.items():
            cleanup_tasks.append(pool.cleanup_all())

        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

        with self._lock:
            self._connection_pools.clear()
            self._discovery = None
            self._compliance_router = None
            self._edge_nodes.clear()

        logger.info("EdgeInfrastructure cleanup complete")
