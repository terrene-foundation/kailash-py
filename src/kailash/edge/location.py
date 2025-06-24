"""Edge location management for global compute distribution."""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union

logger = logging.getLogger(__name__)


class EdgeRegion(Enum):
    """Standard geographic regions for edge deployment."""

    # North America
    US_EAST = "us-east"
    US_WEST = "us-west"
    US_CENTRAL = "us-central"
    CANADA = "canada"

    # Europe
    EU_WEST = "eu-west"
    EU_CENTRAL = "eu-central"
    EU_NORTH = "eu-north"
    UK = "uk"

    # Asia Pacific
    ASIA_SOUTHEAST = "asia-southeast"
    ASIA_EAST = "asia-east"
    ASIA_SOUTH = "asia-south"
    JAPAN = "japan"
    AUSTRALIA = "australia"

    # Other regions
    SOUTH_AMERICA = "south-america"
    AFRICA = "africa"
    MIDDLE_EAST = "middle-east"


class EdgeStatus(Enum):
    """Edge location operational status."""

    ACTIVE = "active"
    DEGRADED = "degraded"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"
    DRAINING = "draining"  # Stopping new workloads


class ComplianceZone(Enum):
    """Data compliance and sovereignty zones."""

    # Data sovereignty regions
    GDPR = "gdpr"  # EU/EEA
    CCPA = "ccpa"  # California
    PIPEDA = "pipeda"  # Canada
    LGPD = "lgpd"  # Brazil

    # Industry compliance
    HIPAA = "hipaa"  # Healthcare (US)
    SOX = "sox"  # Financial (US)
    PCI_DSS = "pci_dss"  # Payment cards

    # Government/security
    FEDRAMP = "fedramp"  # US Government
    ITAR = "itar"  # Export control (US)

    # General zones
    PUBLIC = "public"  # No restrictions
    RESTRICTED = "restricted"  # Custom restrictions


@dataclass
class GeographicCoordinates:
    """Geographic coordinates for edge location."""

    latitude: float
    longitude: float

    def distance_to(self, other: "GeographicCoordinates") -> float:
        """Calculate distance to another location in kilometers using Haversine formula."""
        import math

        # Convert to radians
        lat1, lon1 = math.radians(self.latitude), math.radians(self.longitude)
        lat2, lon2 = math.radians(other.latitude), math.radians(other.longitude)

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))

        # Earth radius in kilometers
        earth_radius = 6371
        return earth_radius * c


@dataclass
class EdgeCapabilities:
    """Resource capabilities available at an edge location."""

    # Compute resources
    cpu_cores: int
    memory_gb: float
    storage_gb: float
    gpu_available: bool = False
    gpu_type: Optional[str] = None

    # Network capabilities
    bandwidth_gbps: float = 1.0
    supports_ipv6: bool = True
    cdn_enabled: bool = True

    # Service capabilities
    database_support: List[str] = None  # ["postgresql", "mongodb", "redis"]
    ai_models_available: List[str] = None  # ["llama", "gpt", "claude"]
    container_runtime: str = "docker"

    # Compliance and security
    encryption_at_rest: bool = True
    encryption_in_transit: bool = True
    audit_logging: bool = True

    def __post_init__(self):
        if self.database_support is None:
            self.database_support = ["postgresql", "redis"]
        if self.ai_models_available is None:
            self.ai_models_available = []


@dataclass
class EdgeMetrics:
    """Real-time metrics for edge location performance."""

    # Performance metrics
    cpu_utilization: float = 0.0  # 0.0 to 1.0
    memory_utilization: float = 0.0
    storage_utilization: float = 0.0

    # Network metrics
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    throughput_rps: int = 0

    # Reliability metrics
    uptime_percentage: float = 100.0
    error_rate: float = 0.0  # 0.0 to 1.0
    success_rate: float = 1.0  # 0.0 to 1.0

    # Cost metrics
    compute_cost_per_hour: float = 0.0
    network_cost_per_gb: float = 0.0
    storage_cost_per_gb_month: float = 0.0

    # Timestamp
    collected_at: datetime = None

    def __post_init__(self):
        if self.collected_at is None:
            self.collected_at = datetime.now(UTC)


class EdgeLocation:
    """Represents a global edge computing location.

    Each edge location provides compute, storage, and network resources
    for low-latency data processing and compliance with regional regulations.
    """

    def __init__(
        self,
        location_id: str,
        name: str,
        region: EdgeRegion,
        coordinates: GeographicCoordinates,
        capabilities: EdgeCapabilities,
        compliance_zones: List[ComplianceZone] = None,
        provider: str = "kailash",
        endpoint_url: str = None,
        **metadata,
    ):
        """Initialize edge location.

        Args:
            location_id: Unique identifier for this location
            name: Human-readable name (e.g., "US-East-Virginia")
            region: Geographic region
            coordinates: Latitude/longitude coordinates
            capabilities: Available compute and network resources
            compliance_zones: Regulatory compliance zones
            provider: Cloud provider or infrastructure name
            endpoint_url: API endpoint for this location
            **metadata: Additional custom metadata
        """
        self.location_id = location_id
        self.name = name
        self.region = region
        self.coordinates = coordinates
        self.capabilities = capabilities
        self.compliance_zones = compliance_zones or [ComplianceZone.PUBLIC]
        self.provider = provider
        self.endpoint_url = endpoint_url or f"https://{location_id}.edge.kailash.ai"
        self.metadata = metadata

        # Runtime state
        self.status = EdgeStatus.ACTIVE
        self.metrics = EdgeMetrics()
        self.connected_users: Set[str] = set()
        self.active_workloads: Dict[str, Any] = {}
        self.health_check_failures = 0
        self.last_health_check = datetime.now(UTC)

        # Cost tracking
        self.cost_optimizer_enabled = True
        self._cost_history: List[Dict] = []

        logger.info(
            f"Initialized edge location {self.name} ({self.location_id}) in {self.region.value}"
        )

    @property
    def is_healthy(self) -> bool:
        """Check if edge location is healthy and available."""
        if self.status == EdgeStatus.OFFLINE:
            return False

        # Check if health checks are failing
        if self.health_check_failures > 3:
            return False

        # Check if metrics indicate problems
        if (
            self.metrics.cpu_utilization > 0.95
            or self.metrics.memory_utilization > 0.95
            or self.metrics.error_rate > 0.1
        ):
            return False

        return True

    @property
    def is_available_for_workload(self) -> bool:
        """Check if location can accept new workloads."""
        return (
            self.is_healthy
            and self.status in [EdgeStatus.ACTIVE, EdgeStatus.DEGRADED]
            and self.metrics.cpu_utilization < 0.8
        )

    def calculate_latency_to(self, user_coordinates: GeographicCoordinates) -> float:
        """Estimate network latency to user location in milliseconds.

        Uses geographic distance as a proxy for network latency.
        Assumes ~1ms per 100km plus base latency.
        """
        distance_km = self.coordinates.distance_to(user_coordinates)

        # Base latency components
        base_latency = 2.0  # Processing overhead
        network_latency = distance_km * 0.01  # ~1ms per 100km
        provider_overhead = 1.0  # CDN/routing overhead

        estimated_latency = base_latency + network_latency + provider_overhead

        # Add current performance degradation
        if self.status == EdgeStatus.DEGRADED:
            estimated_latency *= 1.5

        return estimated_latency

    def calculate_cost_for_workload(
        self,
        cpu_hours: float = 1.0,
        memory_gb_hours: float = 1.0,
        storage_gb: float = 0.0,
        network_gb: float = 0.0,
    ) -> float:
        """Calculate estimated cost for running a workload."""
        compute_cost = (
            cpu_hours * self.capabilities.cpu_cores * self.metrics.compute_cost_per_hour
        )
        storage_cost = (
            storage_gb * self.metrics.storage_cost_per_gb_month / (24 * 30)
        )  # Hourly rate
        network_cost = network_gb * self.metrics.network_cost_per_gb

        total_cost = compute_cost + storage_cost + network_cost

        # Apply regional cost multipliers
        region_multipliers = {
            EdgeRegion.US_EAST: 1.0,
            EdgeRegion.US_WEST: 1.1,
            EdgeRegion.EU_WEST: 1.2,
            EdgeRegion.ASIA_EAST: 1.3,
            EdgeRegion.JAPAN: 1.4,
        }

        multiplier = region_multipliers.get(self.region, 1.0)
        return total_cost * multiplier

    def supports_compliance(self, required_zones: List[ComplianceZone]) -> bool:
        """Check if location supports required compliance zones."""
        return all(zone in self.compliance_zones for zone in required_zones)

    def supports_capabilities(self, required_capabilities: Dict[str, Any]) -> bool:
        """Check if location supports required capabilities."""
        for capability, requirement in required_capabilities.items():
            if capability == "cpu_cores" and self.capabilities.cpu_cores < requirement:
                return False
            elif (
                capability == "memory_gb" and self.capabilities.memory_gb < requirement
            ):
                return False
            elif (
                capability == "gpu_required"
                and requirement
                and not self.capabilities.gpu_available
            ):
                return False
            elif capability == "database_support":
                if not all(
                    db in self.capabilities.database_support for db in requirement
                ):
                    return False
            elif capability == "ai_models":
                if not all(
                    model in self.capabilities.ai_models_available
                    for model in requirement
                ):
                    return False

        return True

    async def health_check(self) -> bool:
        """Perform health check on edge location."""
        try:
            # Simulate health check (in production, would ping actual endpoint)
            await asyncio.sleep(0.1)  # Simulate network call

            # Update metrics (in production, would fetch real metrics)
            self.metrics.collected_at = datetime.now(UTC)

            # Reset failure counter on success
            self.health_check_failures = 0
            self.last_health_check = datetime.now(UTC)

            logger.debug(f"Health check passed for {self.name}")
            return True

        except Exception as e:
            self.health_check_failures += 1
            logger.warning(f"Health check failed for {self.name}: {e}")

            # Mark as degraded if failing repeatedly
            if self.health_check_failures > 3:
                self.status = EdgeStatus.DEGRADED

            return False

    async def update_metrics(self, new_metrics: EdgeMetrics):
        """Update location metrics."""
        self.metrics = new_metrics

        # Automatic status updates based on metrics
        if self.metrics.error_rate > 0.2:
            self.status = EdgeStatus.DEGRADED
        elif self.metrics.uptime_percentage < 95.0:
            self.status = EdgeStatus.DEGRADED
        elif self.metrics.cpu_utilization > 0.98:
            self.status = EdgeStatus.DEGRADED
        else:
            # Recovery to active if metrics improve
            if self.status == EdgeStatus.DEGRADED:
                self.status = EdgeStatus.ACTIVE

    def add_workload(self, workload_id: str, workload_config: Dict[str, Any]):
        """Register a new workload at this location."""
        self.active_workloads[workload_id] = {
            "config": workload_config,
            "started_at": datetime.now(UTC),
            "status": "running",
        }
        logger.info(f"Added workload {workload_id} to {self.name}")

    def remove_workload(self, workload_id: str):
        """Remove workload from this location."""
        if workload_id in self.active_workloads:
            del self.active_workloads[workload_id]
            logger.info(f"Removed workload {workload_id} from {self.name}")

    def get_load_factor(self) -> float:
        """Calculate current load factor (0.0 to 1.0)."""
        # Weighted combination of resource utilization
        cpu_weight = 0.4
        memory_weight = 0.3
        workload_weight = 0.3

        # Workload factor based on active workloads vs capacity
        max_workloads = self.capabilities.cpu_cores * 4  # Assume 4 workloads per core
        workload_factor = len(self.active_workloads) / max_workloads

        load_factor = (
            self.metrics.cpu_utilization * cpu_weight
            + self.metrics.memory_utilization * memory_weight
            + min(workload_factor, 1.0) * workload_weight
        )

        return min(load_factor, 1.0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert edge location to dictionary representation."""
        return {
            "location_id": self.location_id,
            "name": self.name,
            "region": self.region.value,
            "coordinates": {
                "latitude": self.coordinates.latitude,
                "longitude": self.coordinates.longitude,
            },
            "capabilities": {
                "cpu_cores": self.capabilities.cpu_cores,
                "memory_gb": self.capabilities.memory_gb,
                "storage_gb": self.capabilities.storage_gb,
                "gpu_available": self.capabilities.gpu_available,
                "gpu_type": self.capabilities.gpu_type,
                "bandwidth_gbps": self.capabilities.bandwidth_gbps,
                "database_support": self.capabilities.database_support,
                "ai_models_available": self.capabilities.ai_models_available,
            },
            "compliance_zones": [zone.value for zone in self.compliance_zones],
            "status": self.status.value,
            "provider": self.provider,
            "endpoint_url": self.endpoint_url,
            "metrics": {
                "cpu_utilization": self.metrics.cpu_utilization,
                "memory_utilization": self.metrics.memory_utilization,
                "latency_p95_ms": self.metrics.latency_p95_ms,
                "uptime_percentage": self.metrics.uptime_percentage,
                "error_rate": self.metrics.error_rate,
                "collected_at": (
                    self.metrics.collected_at.isoformat()
                    if self.metrics.collected_at
                    else None
                ),
            },
            "is_healthy": self.is_healthy,
            "is_available": self.is_available_for_workload,
            "load_factor": self.get_load_factor(),
            "active_workloads": len(self.active_workloads),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EdgeLocation":
        """Create EdgeLocation from dictionary."""
        coordinates = GeographicCoordinates(
            latitude=data["coordinates"]["latitude"],
            longitude=data["coordinates"]["longitude"],
        )

        capabilities_data = data["capabilities"]
        capabilities = EdgeCapabilities(
            cpu_cores=capabilities_data["cpu_cores"],
            memory_gb=capabilities_data["memory_gb"],
            storage_gb=capabilities_data["storage_gb"],
            gpu_available=capabilities_data.get("gpu_available", False),
            gpu_type=capabilities_data.get("gpu_type"),
            bandwidth_gbps=capabilities_data.get("bandwidth_gbps", 1.0),
            database_support=capabilities_data.get(
                "database_support", ["postgresql", "redis"]
            ),
            ai_models_available=capabilities_data.get("ai_models_available", []),
        )

        compliance_zones = [
            ComplianceZone(zone) for zone in data.get("compliance_zones", ["public"])
        ]

        location = cls(
            location_id=data["location_id"],
            name=data["name"],
            region=EdgeRegion(data["region"]),
            coordinates=coordinates,
            capabilities=capabilities,
            compliance_zones=compliance_zones,
            provider=data.get("provider", "kailash"),
            endpoint_url=data.get("endpoint_url"),
            **data.get("metadata", {}),
        )

        # Restore status if provided
        if "status" in data:
            location.status = EdgeStatus(data["status"])

        return location

    def __str__(self) -> str:
        return f"EdgeLocation({self.name}, {self.region.value}, {self.status.value})"

    def __repr__(self) -> str:
        return (
            f"EdgeLocation(location_id='{self.location_id}', name='{self.name}', "
            f"region={self.region}, status={self.status})"
        )


# Predefined edge locations for common deployments
PREDEFINED_LOCATIONS = {
    "us-east-1": EdgeLocation(
        location_id="us-east-1",
        name="US East (Virginia)",
        region=EdgeRegion.US_EAST,
        coordinates=GeographicCoordinates(39.0458, -77.5081),
        capabilities=EdgeCapabilities(
            cpu_cores=16,
            memory_gb=64,
            storage_gb=1000,
            gpu_available=True,
            gpu_type="NVIDIA A100",
            bandwidth_gbps=10.0,
            database_support=["postgresql", "mongodb", "redis"],
            ai_models_available=["llama3.2", "gpt-4", "claude-3"],
        ),
        compliance_zones=[
            ComplianceZone.PUBLIC,
            ComplianceZone.HIPAA,
            ComplianceZone.SOX,
        ],
    ),
    "eu-west-1": EdgeLocation(
        location_id="eu-west-1",
        name="EU West (Ireland)",
        region=EdgeRegion.EU_WEST,
        coordinates=GeographicCoordinates(53.3498, -6.2603),
        capabilities=EdgeCapabilities(
            cpu_cores=12,
            memory_gb=48,
            storage_gb=800,
            gpu_available=True,
            gpu_type="NVIDIA V100",
            bandwidth_gbps=5.0,
            database_support=["postgresql", "redis"],
            ai_models_available=["llama3.2", "claude-3"],
        ),
        compliance_zones=[ComplianceZone.GDPR, ComplianceZone.PUBLIC],
    ),
    "asia-east-1": EdgeLocation(
        location_id="asia-east-1",
        name="Asia East (Tokyo)",
        region=EdgeRegion.JAPAN,
        coordinates=GeographicCoordinates(35.6762, 139.6503),
        capabilities=EdgeCapabilities(
            cpu_cores=8,
            memory_gb=32,
            storage_gb=500,
            gpu_available=False,
            bandwidth_gbps=3.0,
            database_support=["postgresql", "redis"],
            ai_models_available=["llama3.2"],
        ),
        compliance_zones=[ComplianceZone.PUBLIC],
    ),
}


def get_predefined_location(location_id: str) -> Optional[EdgeLocation]:
    """Get a predefined edge location by ID."""
    return PREDEFINED_LOCATIONS.get(location_id)


def list_predefined_locations() -> List[EdgeLocation]:
    """Get all predefined edge locations."""
    return list(PREDEFINED_LOCATIONS.values())
