"""Edge discovery and selection system for optimal edge placement."""

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .location import ComplianceZone, EdgeLocation, EdgeRegion, GeographicCoordinates

logger = logging.getLogger(__name__)


class EdgeSelectionStrategy(Enum):
    """Strategies for selecting optimal edge locations."""

    LATENCY_OPTIMAL = "latency_optimal"  # Minimize latency
    COST_OPTIMAL = "cost_optimal"  # Minimize cost
    BALANCED = "balanced"  # Balance latency and cost
    CAPACITY_OPTIMAL = "capacity_optimal"  # Maximize available capacity
    COMPLIANCE_FIRST = "compliance_first"  # Prioritize compliance requirements
    LOAD_BALANCED = "load_balanced"  # Distribute load evenly
    PERFORMANCE_OPTIMAL = "performance_optimal"  # Maximize performance metrics


class HealthCheckResult(Enum):
    """Health check result status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNREACHABLE = "unreachable"


@dataclass
class EdgeDiscoveryRequest:
    """Request for discovering optimal edge locations."""

    # Geographic preferences
    user_coordinates: Optional[GeographicCoordinates] = None
    preferred_regions: List[EdgeRegion] = None
    excluded_regions: List[EdgeRegion] = None

    # Resource requirements
    min_cpu_cores: int = 1
    min_memory_gb: float = 1.0
    min_storage_gb: float = 10.0
    gpu_required: bool = False
    bandwidth_requirements: float = 1.0  # Gbps

    # Service requirements
    database_support: List[str] = None
    ai_models_required: List[str] = None

    # Compliance requirements
    compliance_zones: List[ComplianceZone] = None
    data_residency_required: bool = False

    # Performance requirements
    max_latency_ms: float = 100.0
    min_uptime_percentage: float = 99.0
    max_error_rate: float = 0.01

    # Selection preferences
    selection_strategy: EdgeSelectionStrategy = EdgeSelectionStrategy.BALANCED
    max_results: int = 5

    # Cost constraints
    max_cost_per_hour: Optional[float] = None

    def __post_init__(self):
        if self.preferred_regions is None:
            self.preferred_regions = []
        if self.excluded_regions is None:
            self.excluded_regions = []
        if self.database_support is None:
            self.database_support = []
        if self.ai_models_required is None:
            self.ai_models_required = []
        if self.compliance_zones is None:
            self.compliance_zones = [ComplianceZone.PUBLIC]


@dataclass
class EdgeScore:
    """Scoring result for an edge location."""

    location: EdgeLocation
    total_score: float

    # Individual scoring components
    latency_score: float = 0.0
    cost_score: float = 0.0
    capacity_score: float = 0.0
    performance_score: float = 0.0
    compliance_score: float = 0.0

    # Calculated metrics
    estimated_latency_ms: float = 0.0
    estimated_cost_per_hour: float = 0.0
    available_capacity_percentage: float = 0.0

    # Reasoning
    selection_reasons: List[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.selection_reasons is None:
            self.selection_reasons = []
        if self.warnings is None:
            self.warnings = []


class EdgeDiscovery:
    """Edge discovery service for finding optimal edge locations.

    Provides intelligent edge selection based on latency, cost, compliance,
    and performance requirements.
    """

    def __init__(
        self,
        locations: List[EdgeLocation] = None,
        health_check_interval_seconds: int = 60,
        cost_model_enabled: bool = True,
        performance_tracking_enabled: bool = True,
    ):
        """Initialize edge discovery service.

        Args:
            locations: Available edge locations
            health_check_interval_seconds: How often to health check locations
            cost_model_enabled: Enable cost optimization features
            performance_tracking_enabled: Track performance metrics
        """
        self.locations: Dict[str, EdgeLocation] = {}
        self.health_check_interval = health_check_interval_seconds
        self.cost_model_enabled = cost_model_enabled
        self.performance_tracking_enabled = performance_tracking_enabled

        # Performance tracking
        self._performance_history: Dict[str, List[Dict]] = {}
        self._cost_history: Dict[str, List[Dict]] = {}

        # Health monitoring
        self._health_check_task: Optional[asyncio.Task] = None
        self._health_results: Dict[str, HealthCheckResult] = {}
        self._last_health_check: Dict[str, datetime] = {}

        # Add provided locations
        if locations:
            for location in locations:
                self.add_location(location)

        # Selection algorithm weights (can be tuned)
        self.scoring_weights = {
            EdgeSelectionStrategy.LATENCY_OPTIMAL: {
                "latency": 0.7,
                "cost": 0.1,
                "capacity": 0.1,
                "performance": 0.1,
            },
            EdgeSelectionStrategy.COST_OPTIMAL: {
                "latency": 0.1,
                "cost": 0.7,
                "capacity": 0.1,
                "performance": 0.1,
            },
            EdgeSelectionStrategy.BALANCED: {
                "latency": 0.3,
                "cost": 0.3,
                "capacity": 0.2,
                "performance": 0.2,
            },
            EdgeSelectionStrategy.CAPACITY_OPTIMAL: {
                "latency": 0.2,
                "cost": 0.1,
                "capacity": 0.5,
                "performance": 0.2,
            },
            EdgeSelectionStrategy.PERFORMANCE_OPTIMAL: {
                "latency": 0.2,
                "cost": 0.1,
                "capacity": 0.2,
                "performance": 0.5,
            },
        }

        logger.info(f"Initialized EdgeDiscovery with {len(self.locations)} locations")

    def add_location(self, location: EdgeLocation):
        """Add an edge location to the discovery pool."""
        self.locations[location.location_id] = location
        self._health_results[location.location_id] = HealthCheckResult.HEALTHY
        self._last_health_check[location.location_id] = datetime.now(UTC)
        logger.info(f"Added edge location: {location.name}")

    async def register_edge(self, edge_config: Dict[str, Any]):
        """Register an edge location from configuration dictionary.

        Args:
            edge_config: Dictionary containing edge location configuration
        """
        from .location import (
            ComplianceZone,
            EdgeCapabilities,
            EdgeLocation,
            EdgeRegion,
            GeographicCoordinates,
        )

        # Extract basic info
        location_id = edge_config["id"]
        region_str = edge_config.get("region", "us-east")

        # Map region string to enum
        region_map = {
            "us-east-1": EdgeRegion.US_EAST,
            "us-west-1": EdgeRegion.US_WEST,
            "eu-west-1": EdgeRegion.EU_WEST,
            "eu-central-1": EdgeRegion.EU_CENTRAL,
            "asia-southeast-1": EdgeRegion.ASIA_SOUTHEAST,
        }
        region = region_map.get(region_str, EdgeRegion.US_EAST)

        # Default coordinates based on region
        coord_map = {
            EdgeRegion.US_EAST: GeographicCoordinates(39.0458, -76.6413),  # Virginia
            EdgeRegion.US_WEST: GeographicCoordinates(37.7749, -122.4194),  # California
            EdgeRegion.EU_WEST: GeographicCoordinates(53.3498, -6.2603),  # Ireland
            EdgeRegion.EU_CENTRAL: GeographicCoordinates(50.1109, 8.6821),  # Frankfurt
            EdgeRegion.ASIA_SOUTHEAST: GeographicCoordinates(
                1.3521, 103.8198
            ),  # Singapore
        }
        coordinates = coord_map.get(region, GeographicCoordinates(39.0458, -76.6413))

        # Create capabilities
        capabilities = EdgeCapabilities(
            cpu_cores=edge_config.get("capacity", 1000) // 100,  # Rough mapping
            memory_gb=edge_config.get("capacity", 1000) // 50,
            storage_gb=edge_config.get("capacity", 1000) * 2,
            bandwidth_gbps=10.0,
            database_support=["postgresql", "redis"],
            ai_models_available=["llama", "claude"],
        )

        # Create edge location
        location = EdgeLocation(
            location_id=location_id,
            name=f"Edge {region_str.title()}",
            region=region,
            coordinates=coordinates,
            capabilities=capabilities,
            endpoint_url=edge_config.get(
                "endpoint", f"http://{location_id}.edge.local:8080"
            ),
        )

        # Set health status
        from .location import EdgeStatus

        if edge_config.get("healthy", True):
            location.status = EdgeStatus.ACTIVE
            self._health_results[location_id] = HealthCheckResult.HEALTHY
        else:
            location.status = EdgeStatus.OFFLINE
            self._health_results[location_id] = HealthCheckResult.UNHEALTHY

        # Update metrics
        location.metrics.latency_p50_ms = edge_config.get("latency_ms", 10)
        location.metrics.cpu_utilization = edge_config.get(
            "current_load", 0
        ) / edge_config.get("capacity", 1000)

        # Add to locations
        self.locations[location_id] = location
        self._last_health_check[location_id] = datetime.now(UTC)

        logger.info(f"Registered edge location: {location_id} in {region_str}")

        return location

    def remove_location(self, location_id: str):
        """Remove an edge location from the discovery pool."""
        if location_id in self.locations:
            location = self.locations[location_id]
            del self.locations[location_id]
            del self._health_results[location_id]
            del self._last_health_check[location_id]
            logger.info(f"Removed edge location: {location.name}")

    def get_location(self, location_id: str) -> Optional[EdgeLocation]:
        """Get edge location by ID."""
        return self.locations.get(location_id)

    def list_locations(
        self,
        regions: List[EdgeRegion] = None,
        compliance_zones: List[ComplianceZone] = None,
        healthy_only: bool = True,
    ) -> List[EdgeLocation]:
        """List edge locations with optional filtering."""
        locations = list(self.locations.values())

        # Filter by region
        if regions:
            locations = [loc for loc in locations if loc.region in regions]

        # Filter by compliance
        if compliance_zones:
            locations = [
                loc
                for loc in locations
                if any(zone in loc.compliance_zones for zone in compliance_zones)
            ]

        # Filter by health
        if healthy_only:
            locations = [
                loc
                for loc in locations
                if self._health_results.get(loc.location_id)
                == HealthCheckResult.HEALTHY
            ]

        return locations

    async def discover_optimal_edges(
        self, request: EdgeDiscoveryRequest
    ) -> List[EdgeScore]:
        """Discover optimal edge locations based on requirements.

        Args:
            request: Discovery request with requirements and preferences

        Returns:
            List of scored edge locations sorted by total score (best first)
        """
        logger.info(
            f"Discovering optimal edges with strategy: {request.selection_strategy.value}"
        )

        # Get candidate locations
        candidates = await self._get_candidate_locations(request)

        if not candidates:
            logger.warning("No candidate locations found matching requirements")
            return []

        # Score each candidate
        scored_locations = []
        for location in candidates:
            score = await self._score_location(location, request)
            if score:
                scored_locations.append(score)

        # Sort by total score (highest first)
        scored_locations.sort(key=lambda x: x.total_score, reverse=True)

        # Apply result limit
        results = scored_locations[: request.max_results]

        logger.info(f"Found {len(results)} optimal edge locations")
        return results

    async def _get_candidate_locations(
        self, request: EdgeDiscoveryRequest
    ) -> List[EdgeLocation]:
        """Get candidate locations that meet basic requirements."""
        candidates = []

        for location in self.locations.values():
            # Skip unhealthy locations
            if not location.is_healthy:
                continue

            # Skip if not available for workloads
            if not location.is_available_for_workload:
                continue

            # Check region preferences
            if request.excluded_regions and location.region in request.excluded_regions:
                continue

            # Check resource requirements
            if not location.supports_capabilities(
                {
                    "cpu_cores": request.min_cpu_cores,
                    "memory_gb": request.min_memory_gb,
                    "gpu_required": request.gpu_required,
                    "database_support": request.database_support,
                    "ai_models": request.ai_models_required,
                }
            ):
                continue

            # Check compliance requirements
            if not location.supports_compliance(request.compliance_zones):
                continue

            # Check performance requirements
            if (
                location.metrics.uptime_percentage < request.min_uptime_percentage
                or location.metrics.error_rate > request.max_error_rate
            ):
                continue

            # Check latency requirements if user coordinates provided
            if request.user_coordinates:
                estimated_latency = location.calculate_latency_to(
                    request.user_coordinates
                )
                if estimated_latency > request.max_latency_ms:
                    continue

            # Check cost constraints
            if request.max_cost_per_hour:
                estimated_cost = location.calculate_cost_for_workload()
                if estimated_cost > request.max_cost_per_hour:
                    continue

            candidates.append(location)

        return candidates

    async def _score_location(
        self, location: EdgeLocation, request: EdgeDiscoveryRequest
    ) -> Optional[EdgeScore]:
        """Score a location based on request requirements."""
        try:
            # Calculate individual scores
            latency_score = self._calculate_latency_score(location, request)
            cost_score = self._calculate_cost_score(location, request)
            capacity_score = self._calculate_capacity_score(location, request)
            performance_score = self._calculate_performance_score(location, request)
            compliance_score = self._calculate_compliance_score(location, request)

            # Get weights for scoring strategy
            weights = self.scoring_weights.get(
                request.selection_strategy,
                self.scoring_weights[EdgeSelectionStrategy.BALANCED],
            )

            # Calculate weighted total score
            total_score = (
                latency_score * weights.get("latency", 0.25)
                + cost_score * weights.get("cost", 0.25)
                + capacity_score * weights.get("capacity", 0.25)
                + performance_score * weights.get("performance", 0.25)
            )

            # Create score object
            score = EdgeScore(
                location=location,
                total_score=total_score,
                latency_score=latency_score,
                cost_score=cost_score,
                capacity_score=capacity_score,
                performance_score=performance_score,
                compliance_score=compliance_score,
                estimated_latency_ms=(
                    location.calculate_latency_to(request.user_coordinates)
                    if request.user_coordinates
                    else 0.0
                ),
                estimated_cost_per_hour=location.calculate_cost_for_workload(),
                available_capacity_percentage=(1.0 - location.get_load_factor()) * 100,
            )

            # Add selection reasoning
            self._add_selection_reasoning(score, request)

            return score

        except Exception as e:
            logger.error(f"Error scoring location {location.location_id}: {e}")
            return None

    def _calculate_latency_score(
        self, location: EdgeLocation, request: EdgeDiscoveryRequest
    ) -> float:
        """Calculate latency score (0.0 to 1.0, higher is better)."""
        if not request.user_coordinates:
            return 0.8  # Neutral score if no user location

        estimated_latency = location.calculate_latency_to(request.user_coordinates)

        # Score based on latency: 0ms = 1.0, 100ms = 0.5, 200ms+ = 0.0
        if estimated_latency <= 10:
            return 1.0
        elif estimated_latency <= 50:
            return 0.9 - (estimated_latency - 10) * 0.01  # Linear decay
        elif estimated_latency <= 100:
            return 0.5 - (estimated_latency - 50) * 0.008
        else:
            return max(0.0, 0.1 - (estimated_latency - 100) * 0.001)

    def _calculate_cost_score(
        self, location: EdgeLocation, request: EdgeDiscoveryRequest
    ) -> float:
        """Calculate cost score (0.0 to 1.0, higher is better - lower cost)."""
        estimated_cost = location.calculate_cost_for_workload()

        # Cost scoring: $0.01/hour = 1.0, $0.10/hour = 0.5, $0.20/hour+ = 0.0
        if estimated_cost <= 0.01:
            return 1.0
        elif estimated_cost <= 0.05:
            return 0.9 - (estimated_cost - 0.01) * 20  # Linear decay
        elif estimated_cost <= 0.10:
            return 0.5 - (estimated_cost - 0.05) * 10
        else:
            return max(0.0, 0.1 - (estimated_cost - 0.10) * 1)

    def _calculate_capacity_score(
        self, location: EdgeLocation, request: EdgeDiscoveryRequest
    ) -> float:
        """Calculate capacity score (0.0 to 1.0, higher is better)."""
        load_factor = location.get_load_factor()

        # Capacity score: 0% load = 1.0, 50% load = 0.75, 90% load = 0.25
        if load_factor <= 0.5:
            return 1.0 - load_factor * 0.5  # Slow decay up to 50%
        elif load_factor <= 0.8:
            return 0.75 - (load_factor - 0.5) * 1.67  # Faster decay
        else:
            return max(0.0, 0.25 - (load_factor - 0.8) * 1.25)  # Steep decay

    def _calculate_performance_score(
        self, location: EdgeLocation, request: EdgeDiscoveryRequest
    ) -> float:
        """Calculate performance score (0.0 to 1.0, higher is better)."""
        metrics = location.metrics

        # Combine multiple performance factors
        uptime_score = metrics.uptime_percentage / 100.0
        error_score = max(0.0, 1.0 - metrics.error_rate * 10)  # Error rate penalty
        success_score = metrics.success_rate

        # Weighted combination
        performance_score = uptime_score * 0.4 + error_score * 0.3 + success_score * 0.3

        return max(0.0, min(1.0, performance_score))

    def _calculate_compliance_score(
        self, location: EdgeLocation, request: EdgeDiscoveryRequest
    ) -> float:
        """Calculate compliance score (0.0 to 1.0, higher is better)."""
        required_zones = set(request.compliance_zones)
        available_zones = set(location.compliance_zones)

        # Perfect match gets full score
        if required_zones.issubset(available_zones):
            # Bonus for additional compliance zones
            bonus = min(0.2, len(available_zones - required_zones) * 0.05)
            return 1.0 + bonus
        else:
            # Partial compliance scoring
            overlap = len(required_zones.intersection(available_zones))
            return overlap / len(required_zones) if required_zones else 1.0

    def _add_selection_reasoning(self, score: EdgeScore, request: EdgeDiscoveryRequest):
        """Add human-readable reasoning for edge selection."""
        reasons = []
        warnings = []

        # Latency reasoning
        if score.estimated_latency_ms <= 10:
            reasons.append(f"Excellent latency: {score.estimated_latency_ms:.1f}ms")
        elif score.estimated_latency_ms <= 50:
            reasons.append(f"Good latency: {score.estimated_latency_ms:.1f}ms")
        elif score.estimated_latency_ms > 100:
            warnings.append(f"High latency: {score.estimated_latency_ms:.1f}ms")

        # Cost reasoning
        if score.estimated_cost_per_hour <= 0.02:
            reasons.append(f"Low cost: ${score.estimated_cost_per_hour:.3f}/hour")
        elif score.estimated_cost_per_hour > 0.10:
            warnings.append(f"High cost: ${score.estimated_cost_per_hour:.3f}/hour")

        # Capacity reasoning
        if score.available_capacity_percentage > 70:
            reasons.append(
                f"High capacity: {score.available_capacity_percentage:.0f}% available"
            )
        elif score.available_capacity_percentage < 30:
            warnings.append(
                f"Limited capacity: {score.available_capacity_percentage:.0f}% available"
            )

        # Performance reasoning
        if score.location.metrics.uptime_percentage > 99.5:
            reasons.append(
                f"Excellent uptime: {score.location.metrics.uptime_percentage:.1f}%"
            )
        elif score.location.metrics.uptime_percentage < 99.0:
            warnings.append(
                f"Lower uptime: {score.location.metrics.uptime_percentage:.1f}%"
            )

        # Compliance reasoning
        compliance_match = set(request.compliance_zones).issubset(
            set(score.location.compliance_zones)
        )
        if compliance_match:
            reasons.append("Full compliance requirements met")
        else:
            warnings.append("Partial compliance match only")

        score.selection_reasons = reasons
        score.warnings = warnings

    async def start_health_monitoring(self):
        """Start continuous health monitoring of edge locations."""
        if self._health_check_task:
            return  # Already running

        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("Started edge health monitoring")

    async def stop_health_monitoring(self):
        """Stop health monitoring."""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
            logger.info("Stopped edge health monitoring")

    async def _health_check_loop(self):
        """Continuous health checking loop."""
        while True:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
                await asyncio.sleep(5)  # Brief pause on error

    async def _perform_health_checks(self):
        """Perform health checks on all locations."""
        health_check_tasks = []

        for location_id, location in self.locations.items():
            task = asyncio.create_task(
                self._check_location_health(location_id, location)
            )
            health_check_tasks.append(task)

        if health_check_tasks:
            await asyncio.gather(*health_check_tasks, return_exceptions=True)

    async def _check_location_health(self, location_id: str, location: EdgeLocation):
        """Check health of a specific location."""
        try:
            is_healthy = await location.health_check()

            if is_healthy:
                self._health_results[location_id] = HealthCheckResult.HEALTHY
            else:
                # Determine degraded vs unhealthy based on failure count
                if location.health_check_failures > 5:
                    self._health_results[location_id] = HealthCheckResult.UNHEALTHY
                else:
                    self._health_results[location_id] = HealthCheckResult.DEGRADED

            self._last_health_check[location_id] = datetime.now(UTC)

        except Exception as e:
            logger.error(f"Health check failed for {location.name}: {e}")
            self._health_results[location_id] = HealthCheckResult.UNREACHABLE

    def get_health_status(self) -> Dict[str, Any]:
        """Get overall health status of edge infrastructure."""
        total_locations = len(self.locations)
        healthy_count = sum(
            1
            for result in self._health_results.values()
            if result == HealthCheckResult.HEALTHY
        )

        return {
            "total_locations": total_locations,
            "healthy_locations": healthy_count,
            "health_percentage": (
                (healthy_count / total_locations * 100) if total_locations > 0 else 0
            ),
            "locations": {
                location_id: {
                    "name": location.name,
                    "region": location.region.value,
                    "status": location.status.value,
                    "health": self._health_results.get(
                        location_id, HealthCheckResult.UNREACHABLE
                    ).value,
                    "last_check": self._last_health_check.get(
                        location_id, datetime.now(UTC)
                    ).isoformat(),
                    "load_factor": location.get_load_factor(),
                    "active_workloads": len(location.active_workloads),
                }
                for location_id, location in self.locations.items()
            },
        }

    async def find_nearest_edge(
        self, user_coordinates: GeographicCoordinates, max_results: int = 1
    ) -> List[EdgeScore]:
        """Find nearest edge location(s) to user coordinates."""
        request = EdgeDiscoveryRequest(
            user_coordinates=user_coordinates,
            selection_strategy=EdgeSelectionStrategy.LATENCY_OPTIMAL,
            max_results=max_results,
        )

        return await self.discover_optimal_edges(request)

    async def find_cheapest_edge(
        self, requirements: Dict[str, Any] = None, max_results: int = 1
    ) -> List[EdgeScore]:
        """Find cheapest edge location(s) meeting requirements."""
        request = EdgeDiscoveryRequest(
            selection_strategy=EdgeSelectionStrategy.COST_OPTIMAL,
            max_results=max_results,
            **(requirements or {}),
        )

        return await self.discover_optimal_edges(request)

    def __len__(self) -> int:
        return len(self.locations)

    def __contains__(self, location_id: str) -> bool:
        return location_id in self.locations

    def __iter__(self):
        return iter(self.locations.values())
