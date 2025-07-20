"""Base edge-aware node with location awareness and compliance routing."""

import asyncio
from typing import Any, Dict, List, Optional

from kailash.edge.compliance import ComplianceRouter, DataClassification
from kailash.edge.discovery import EdgeDiscovery, EdgeSelectionStrategy
from kailash.edge.location import EdgeLocation
from kailash.nodes.base_async import AsyncNode


class EdgeNode(AsyncNode):
    """Base node with edge computing awareness.

    Extends AsyncNode with:
    - Edge location awareness
    - Automatic edge selection
    - Compliance-aware routing
    - Migration capabilities
    """

    def __init__(self, **config):
        """Initialize edge-aware node.

        Args:
            edge_strategy: Edge selection strategy (latency|cost|balanced|compliance)
            preferred_locations: List of preferred edge location names
            compliance_zones: List of required compliance zones (gdpr, ccpa, etc.)
            enable_migration: Whether to enable edge migration capabilities
            **config: Additional node configuration
        """
        self.edge_strategy = EdgeSelectionStrategy(
            config.pop("edge_strategy", "balanced")
        )
        self.preferred_locations = config.pop("preferred_locations", [])
        self.compliance_zones = config.pop("compliance_zones", [])
        self.enable_migration = config.pop("enable_migration", True)

        # Check for injected infrastructure (from WorkflowBuilder)
        edge_infrastructure = config.pop("_edge_infrastructure", None)

        if edge_infrastructure:
            # Use shared infrastructure from WorkflowBuilder
            self.edge_discovery = edge_infrastructure.get_discovery()
            self.compliance_router = edge_infrastructure.get_compliance_router()
            self._shared_infrastructure = edge_infrastructure
        else:
            # Standalone mode - create own infrastructure (backward compatibility)
            self.edge_discovery = EdgeDiscovery()
            self.compliance_router = ComplianceRouter()
            self._shared_infrastructure = None

        self.current_edge: Optional[EdgeLocation] = None

        super().__init__(**config)

    async def initialize(self):
        """Initialize edge infrastructure."""
        # No need to call super().initialize() as AsyncNode doesn't have it

        # Start edge discovery only if not using shared infrastructure
        if not self._shared_infrastructure:
            await self.edge_discovery.start_discovery()

        # Select initial edge
        self.current_edge = await self._select_edge()

        if not self.current_edge:
            raise RuntimeError("No suitable edge location found")

    async def _select_edge(
        self, data: Optional[Dict[str, Any]] = None
    ) -> Optional[EdgeLocation]:
        """Select optimal edge location based on strategy and constraints.

        Args:
            data: Optional data for compliance classification

        Returns:
            Selected edge location or None
        """
        # Get all available edges
        edges = self.edge_discovery.get_all_edges()

        # Filter by preferred locations if specified
        if self.preferred_locations:
            edges = [e for e in edges if e.name in self.preferred_locations]

        # Filter by compliance if data provided
        if data and self.compliance_zones:
            data_class = self.compliance_router.classify_data(data)
            edges = [
                e
                for e in edges
                if self.compliance_router.is_compliant_location(
                    e, data_class, self.compliance_zones
                )
            ]

        # Apply edge selection strategy
        if not edges:
            return None

        # If we've already filtered edges, select from the filtered list
        # based on the strategy
        if self.edge_strategy == EdgeSelectionStrategy.LATENCY_OPTIMAL:
            # Select edge with lowest latency
            return min(edges, key=lambda e: e.metrics.latency_p50_ms)
        elif self.edge_strategy == EdgeSelectionStrategy.COST_OPTIMAL:
            # Select edge with lowest cost
            return min(edges, key=lambda e: e.metrics.compute_cost_per_hour)
        elif self.edge_strategy == EdgeSelectionStrategy.COMPLIANCE_FIRST:
            # Already filtered for compliance, pick first
            return edges[0]
        elif self.edge_strategy == EdgeSelectionStrategy.CAPACITY_OPTIMAL:
            # Select edge with most capacity
            return max(
                edges,
                key=lambda e: e.capabilities.cpu_cores
                * (1 - e.metrics.cpu_utilization),
            )
        else:  # BALANCED or others
            # Simple balanced selection - pick edge with best combined score
            return min(
                edges,
                key=lambda e: e.metrics.latency_p50_ms
                * e.metrics.compute_cost_per_hour,
            )

    async def migrate_to_edge(
        self, target_edge: EdgeLocation, state_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Migrate this node to a different edge location.

        Args:
            target_edge: Target edge location
            state_data: Optional state to migrate

        Returns:
            Success status
        """
        if not self.enable_migration:
            return False

        try:
            # Prepare for migration
            await self._prepare_migration(target_edge, state_data)

            # Perform migration
            old_edge = self.current_edge
            self.current_edge = target_edge

            # Cleanup old edge
            if old_edge:
                await self._cleanup_edge(old_edge)

            return True

        except Exception as e:
            self.logger.error(f"Migration failed: {e}")
            return False

    async def _prepare_migration(
        self, target_edge: EdgeLocation, state_data: Optional[Dict[str, Any]]
    ):
        """Prepare for edge migration."""
        # Override in subclasses for specific preparation
        pass

    async def _cleanup_edge(self, edge: EdgeLocation):
        """Cleanup after migrating away from an edge."""
        # Override in subclasses for specific cleanup
        pass

    async def get_edge_metrics(self) -> Dict[str, Any]:
        """Get current edge performance metrics."""
        if not self.current_edge:
            return {}

        return {
            "edge_name": self.current_edge.name,
            "edge_region": self.current_edge.region,
            "latency_ms": self.current_edge.metrics.latency_p50_ms,
            "cpu_usage": self.current_edge.metrics.cpu_utilization,
            "memory_usage": self.current_edge.metrics.memory_utilization,
            "request_count": self.current_edge.metrics.throughput_rps,
            "error_rate": self.current_edge.metrics.error_rate,
        }

    def is_compliant_for_data(
        self, data: Dict[str, Any], required_zones: Optional[List[str]] = None
    ) -> bool:
        """Check if current edge is compliant for given data.

        Args:
            data: Data to check compliance for
            required_zones: Override compliance zones

        Returns:
            Compliance status
        """
        if not self.current_edge:
            return False

        zones = required_zones or self.compliance_zones
        if not zones:
            return True

        data_class = self.compliance_router.classify_data(data)
        return self.compliance_router.is_compliant_location(
            self.current_edge, data_class, zones
        )

    async def ensure_compliance(
        self, data: Dict[str, Any], required_zones: Optional[List[str]] = None
    ) -> bool:
        """Ensure node is at compliant edge for data.

        Migrates to compliant edge if necessary.

        Args:
            data: Data requiring compliance
            required_zones: Override compliance zones

        Returns:
            Success status
        """
        zones = required_zones or self.compliance_zones

        # Check current compliance
        if self.is_compliant_for_data(data, zones):
            return True

        # Find compliant edge
        compliant_edge = await self._select_edge(data)
        if not compliant_edge:
            return False

        # Migrate to compliant edge
        return await self.migrate_to_edge(compliant_edge)
