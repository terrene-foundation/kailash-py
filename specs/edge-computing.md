# Edge Computing

Edge computing infrastructure for global distribution of compute and data. Provides edge location management, discovery and selection, compliance routing for data sovereignty, consistency models for distributed operations, coordination (Raft, leader election, global ordering, partition detection), migration, monitoring, prediction, and resource management.

Source of truth: `src/kailash/edge/`

## Public Exports (`src/kailash/edge/__init__.py`)

```python
from .compliance import ComplianceRouter
from .discovery import EdgeDiscovery, EdgeSelectionStrategy
from .location import EdgeLocation

__all__ = [
    "EdgeLocation",
    "EdgeDiscovery",
    "EdgeSelectionStrategy",
    "ComplianceRouter",
]
```

Only four symbols are in the top-level `kailash.edge` namespace. Subpackages (`coordination`, `migration`, `monitoring`, `prediction`, `resource`) expose their own symbols via their own `__init__.py` files.

## Location (`src/kailash/edge/location.py`)

### `EdgeRegion` (Enum)

String-valued enum of geographic regions:

| Enum Member      | Value              |
| ---------------- | ------------------ |
| `US_EAST`        | `"us-east"`        |
| `US_WEST`        | `"us-west"`        |
| `US_CENTRAL`     | `"us-central"`     |
| `CANADA`         | `"canada"`         |
| `EU_WEST`        | `"eu-west"`        |
| `EU_CENTRAL`     | `"eu-central"`     |
| `EU_NORTH`       | `"eu-north"`       |
| `UK`             | `"uk"`             |
| `ASIA_SOUTHEAST` | `"asia-southeast"` |
| `ASIA_EAST`      | `"asia-east"`      |
| `ASIA_SOUTH`     | `"asia-south"`     |
| `JAPAN`          | `"japan"`          |
| `AUSTRALIA`      | `"australia"`      |
| `SOUTH_AMERICA`  | `"south-america"`  |
| `AFRICA`         | `"africa"`         |
| `MIDDLE_EAST`    | `"middle-east"`    |

### `EdgeStatus` (Enum)

Operational status values:

- `ACTIVE = "active"`
- `DEGRADED = "degraded"`
- `MAINTENANCE = "maintenance"`
- `OFFLINE = "offline"`
- `DRAINING = "draining"` — stopping new workloads

### `ComplianceZone` (Enum)

Data sovereignty / regulatory zones:

| Enum Member  | Value          | Purpose                |
| ------------ | -------------- | ---------------------- |
| `GDPR`       | `"gdpr"`       | EU/EEA personal data   |
| `CCPA`       | `"ccpa"`       | California residents   |
| `PIPEDA`     | `"pipeda"`     | Canadian personal data |
| `LGPD`       | `"lgpd"`       | Brazil                 |
| `HIPAA`      | `"hipaa"`      | US healthcare          |
| `SOX`        | `"sox"`        | US financial           |
| `PCI_DSS`    | `"pci_dss"`    | Payment cards          |
| `FEDRAMP`    | `"fedramp"`    | US government          |
| `ITAR`       | `"itar"`       | US export control      |
| `PUBLIC`     | `"public"`     | No restrictions        |
| `RESTRICTED` | `"restricted"` | Custom restrictions    |

### `GeographicCoordinates`

```python
@dataclass
class GeographicCoordinates:
    latitude: float
    longitude: float

    def distance_to(self, other: "GeographicCoordinates") -> float:
        """Distance in kilometers using the Haversine formula. Earth radius 6371 km."""
```

### `EdgeCapabilities`

```python
@dataclass
class EdgeCapabilities:
    # Compute
    cpu_cores: int
    memory_gb: float
    storage_gb: float
    gpu_available: bool = False
    gpu_type: Optional[str] = None

    # Network
    bandwidth_gbps: float = 1.0
    supports_ipv6: bool = True
    cdn_enabled: bool = True

    # Service
    database_support: Optional[List[str]] = None
    ai_models_available: Optional[List[str]] = None
    container_runtime: str = "docker"

    # Compliance / security
    encryption_at_rest: bool = True
    encryption_in_transit: bool = True
    audit_logging: bool = True

    def __post_init__(self):
        if self.database_support is None:
            self.database_support = ["postgresql", "redis"]
        if self.ai_models_available is None:
            self.ai_models_available = []
```

Defaults applied in `__post_init__`: `database_support` becomes `["postgresql", "redis"]` when left as `None`; `ai_models_available` becomes `[]`.

### `EdgeMetrics`

```python
@dataclass
class EdgeMetrics:
    # Performance
    cpu_utilization: float = 0.0          # 0.0 to 1.0
    memory_utilization: float = 0.0
    storage_utilization: float = 0.0

    # Network
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    throughput_rps: int = 0

    # Reliability
    uptime_percentage: float = 100.0
    error_rate: float = 0.0               # 0.0 to 1.0
    success_rate: float = 1.0             # 0.0 to 1.0

    # Cost
    compute_cost_per_hour: float = 0.0
    network_cost_per_gb: float = 0.0
    storage_cost_per_gb_month: float = 0.0

    collected_at: Optional[datetime] = None

    def __post_init__(self):
        if self.collected_at is None:
            self.collected_at = datetime.now(UTC)
```

### `EdgeLocation`

Represents a single global edge computing location. Holds capabilities, metrics, status, and workload state.

```python
class EdgeLocation:
    def __init__(
        self,
        location_id: str,
        name: str,
        region: EdgeRegion,
        coordinates: GeographicCoordinates,
        capabilities: EdgeCapabilities,
        compliance_zones: Optional[List[ComplianceZone]] = None,
        provider: str = "kailash",
        endpoint_url: Optional[str] = None,
        **metadata,
    ):
        ...
```

**Constructor parameters** (exactly as in source):

- `location_id: str` — unique ID
- `name: str` — human-readable name
- `region: EdgeRegion`
- `coordinates: GeographicCoordinates`
- `capabilities: EdgeCapabilities`
- `compliance_zones: Optional[List[ComplianceZone]] = None` — defaults to `[ComplianceZone.PUBLIC]` when `None` is passed
- `provider: str = "kailash"`
- `endpoint_url: Optional[str] = None` — defaults to `f"https://{location_id}.edge.kailash.ai"` when `None` is passed
- `**metadata` — arbitrary extra metadata captured into `self.metadata` as a dict

**There is no `status` parameter on `__init__`.** The constructor hard-codes `self.status = EdgeStatus.ACTIVE` in its body. Status is mutated later by `health_check()`, `update_metrics()`, or by assigning `location.status = ...` directly (e.g., `from_dict()` restores status after construction).

**Runtime state initialized in `__init__`:**

- `self.status = EdgeStatus.ACTIVE`
- `self.metrics = EdgeMetrics()`
- `self.connected_users: Set[str] = set()`
- `self.active_workloads: Dict[str, Any] = {}`
- `self.health_check_failures = 0`
- `self.last_health_check = datetime.now(UTC)`
- `self.cost_optimizer_enabled = True`
- `self._cost_history: List[Dict] = []`

**Property: `is_healthy` — exact logic from source**

```python
@property
def is_healthy(self) -> bool:
    if self.status == EdgeStatus.OFFLINE:
        return False
    if self.health_check_failures > 3:
        return False
    if (
        self.metrics.cpu_utilization > 0.95
        or self.metrics.memory_utilization > 0.95
        or self.metrics.error_rate > 0.1
    ):
        return False
    return True
```

Returns `False` if and only if any of the following hold:

- `status == EdgeStatus.OFFLINE`
- `health_check_failures > 3`
- `metrics.cpu_utilization > 0.95`
- `metrics.memory_utilization > 0.95`
- `metrics.error_rate > 0.1`

Otherwise returns `True`. `is_healthy` does NOT inspect uptime, success rate, or latency. It does not enforce an allowlist of statuses — it only blocks OFFLINE. `ACTIVE`, `DEGRADED`, `MAINTENANCE`, and `DRAINING` are all considered healthy on the status dimension as long as the other thresholds pass.

**Property: `is_available_for_workload`**

```python
@property
def is_available_for_workload(self) -> bool:
    return (
        self.is_healthy
        and self.status in [EdgeStatus.ACTIVE, EdgeStatus.DEGRADED]
        and self.metrics.cpu_utilization < 0.8
    )
```

Available for new workloads iff:

- `is_healthy` is True, AND
- status is one of `{ACTIVE, DEGRADED}` (MAINTENANCE and DRAINING are excluded here even though they can be "healthy"), AND
- `cpu_utilization < 0.8`

**Method: `calculate_latency_to(user_coordinates)`**

```python
def calculate_latency_to(self, user_coordinates: GeographicCoordinates) -> float:
    distance_km = self.coordinates.distance_to(user_coordinates)
    base_latency = 2.0              # Processing overhead
    network_latency = distance_km * 0.01  # ~1ms per 100km
    provider_overhead = 1.0         # CDN/routing overhead
    estimated_latency = base_latency + network_latency + provider_overhead
    if self.status == EdgeStatus.DEGRADED:
        estimated_latency *= 1.5
    return estimated_latency
```

- Base latency: `2.0 ms`
- Network latency: `distance_km * 0.01 ms` (~1ms per 100km)
- Provider/CDN overhead: `1.0 ms`
- DEGRADED status multiplier: `1.5x` applied to the sum

Returned value is in milliseconds.

**Method: `calculate_cost_for_workload(cpu_hours=1.0, memory_gb_hours=1.0, storage_gb=0.0, network_gb=0.0)`**

```python
def calculate_cost_for_workload(
    self,
    cpu_hours: float = 1.0,
    memory_gb_hours: float = 1.0,
    storage_gb: float = 0.0,
    network_gb: float = 0.0,
) -> float:
    compute_cost = (
        cpu_hours * self.capabilities.cpu_cores * self.metrics.compute_cost_per_hour
    )
    storage_cost = storage_gb * self.metrics.storage_cost_per_gb_month / (24 * 30)
    network_cost = network_gb * self.metrics.network_cost_per_gb
    total_cost = compute_cost + storage_cost + network_cost

    region_multipliers = {
        EdgeRegion.US_EAST: 1.0,
        EdgeRegion.US_WEST: 1.1,
        EdgeRegion.EU_WEST: 1.2,
        EdgeRegion.ASIA_EAST: 1.3,
        EdgeRegion.JAPAN: 1.4,
    }
    multiplier = region_multipliers.get(self.region, 1.0)
    return total_cost * multiplier
```

`memory_gb_hours` is accepted but not used in the current formula. Compute cost uses `capabilities.cpu_cores`. Regional cost multipliers are only defined for US_EAST, US_WEST, EU_WEST, ASIA_EAST, and JAPAN; all other regions default to `1.0` via `.get(self.region, 1.0)`.

**Method: `supports_compliance(required_zones)`**

Returns `True` iff every `ComplianceZone` in `required_zones` appears in `self.compliance_zones`. Implemented as `all(zone in self.compliance_zones for zone in required_zones)`.

**Method: `supports_capabilities(required_capabilities: Dict[str, Any])`**

Validates a dict of capability requirements. Recognised keys and their semantics:

- `"cpu_cores"`: requires `self.capabilities.cpu_cores >= requirement`
- `"memory_gb"`: requires `self.capabilities.memory_gb >= requirement`
- `"gpu_required"` with truthy value: requires `self.capabilities.gpu_available is True`
- `"database_support"`: list of required DB names; each must appear in `self.capabilities.database_support`
- `"ai_models"`: list of required model names; each must appear in `self.capabilities.ai_models_available`

Unknown keys are silently ignored (the `for/elif` chain has no fallback branch).

**Async method: `health_check(timeout: float = 5.0) -> bool`**

Performs an HTTP GET to `f"{self.endpoint_url.rstrip('/')}/health"` using `aiohttp`. On HTTP 200, parses the JSON body and updates any of `cpu_utilization`, `memory_utilization`, `error_rate`, `uptime_percentage` found in the body, refreshes `metrics.collected_at`, resets `health_check_failures = 0`, updates `last_health_check`, returns `True`.

On non-200 responses: increments `health_check_failures`, updates `last_health_check`, and if `health_check_failures > 3` sets `self.status = EdgeStatus.DEGRADED`. Returns `False`.

On `ImportError` (aiohttp not installed): logs DEBUG, sets `collected_at`, resets `health_check_failures = 0`, updates `last_health_check`, returns `True` as a fallback.

On any other exception: increments `health_check_failures`, updates `last_health_check`, and if `> 3` sets status to `DEGRADED`. Returns `False`.

**Async method: `update_metrics(new_metrics: EdgeMetrics)`**

Replaces `self.metrics = new_metrics`, then applies automatic status transitions based on the new values:

```python
if self.metrics.error_rate > 0.2:
    self.status = EdgeStatus.DEGRADED
elif self.metrics.uptime_percentage < 95.0:
    self.status = EdgeStatus.DEGRADED
elif self.metrics.cpu_utilization > 0.98:
    self.status = EdgeStatus.DEGRADED
else:
    if self.status == EdgeStatus.DEGRADED:
        self.status = EdgeStatus.ACTIVE
```

Exact DEGRADED thresholds:

- `error_rate > 0.2`
- `uptime_percentage < 95.0`
- `cpu_utilization > 0.98`

Recovery from DEGRADED back to ACTIVE only happens in the `else` branch when none of the three thresholds are exceeded.

**Method: `add_workload(workload_id, workload_config: Dict[str, Any])`**

Records a workload in `self.active_workloads[workload_id]` with keys `config`, `started_at=datetime.now(UTC)`, `status="running"`.

**Method: `remove_workload(workload_id)`**

Removes the workload from `self.active_workloads` if present.

**Method: `get_load_factor() -> float`**

Weighted combination (clamped to 1.0):

```python
cpu_weight = 0.4
memory_weight = 0.3
workload_weight = 0.3
max_workloads = self.capabilities.cpu_cores * 4   # Assume 4 workloads per core
workload_factor = len(self.active_workloads) / max_workloads
load_factor = (
    self.metrics.cpu_utilization * cpu_weight
    + self.metrics.memory_utilization * memory_weight
    + min(workload_factor, 1.0) * workload_weight
)
return min(load_factor, 1.0)
```

**Method: `to_dict() -> Dict[str, Any]`**

Serializes to a dictionary with keys: `location_id`, `name`, `region`, `coordinates`, `capabilities` (sub-dict of cpu_cores/memory_gb/storage_gb/gpu_available/gpu_type/bandwidth_gbps/database_support/ai_models_available), `compliance_zones`, `status`, `provider`, `endpoint_url`, `metrics` (sub-dict), `is_healthy`, `is_available`, `load_factor`, `active_workloads` (count), `metadata`.

**Classmethod: `from_dict(data: Dict[str, Any]) -> "EdgeLocation"`**

Reconstructs an `EdgeLocation` from a dict. Sets `status` post-construction if present in the input dict. Passes metadata through as `**data.get("metadata", {})`.

### Predefined locations

`PREDEFINED_LOCATIONS: Dict[str, EdgeLocation]` contains three pre-built instances:

- `"us-east-1"` — US East (Virginia), coordinates `(39.0458, -77.5081)`, 16 cpu cores, 64 GB memory, 1000 GB storage, GPU `"NVIDIA A100"`, bandwidth 10 Gbps, database `["postgresql", "mongodb", "redis"]`, AI models `["llama3.2", "gpt-4", "claude-3"]`, compliance zones `[PUBLIC, HIPAA, SOX]`
- `"eu-west-1"` — EU West (Ireland), coordinates `(53.3498, -6.2603)`, 12 cpu cores, 48 GB memory, 800 GB storage, GPU `"NVIDIA V100"`, bandwidth 5 Gbps, database `["postgresql", "redis"]`, AI models `["llama3.2", "claude-3"]`, compliance zones `[GDPR, PUBLIC]`
- `"asia-east-1"` — Asia East (Tokyo), region is `EdgeRegion.JAPAN`, coordinates `(35.6762, 139.6503)`, 8 cpu cores, 32 GB memory, 500 GB storage, no GPU, bandwidth 3 Gbps, database `["postgresql", "redis"]`, AI models `["llama3.2"]`, compliance zones `[PUBLIC]`

Helper functions:

- `get_predefined_location(location_id: str) -> Optional[EdgeLocation]`
- `list_predefined_locations() -> List[EdgeLocation]`

## Discovery (`src/kailash/edge/discovery.py`)

### `EdgeSelectionStrategy` (Enum)

```python
class EdgeSelectionStrategy(Enum):
    LATENCY_OPTIMAL = "latency_optimal"
    COST_OPTIMAL = "cost_optimal"
    BALANCED = "balanced"
    CAPACITY_OPTIMAL = "capacity_optimal"
    COMPLIANCE_FIRST = "compliance_first"
    LOAD_BALANCED = "load_balanced"
    PERFORMANCE_OPTIMAL = "performance_optimal"
```

### `HealthCheckResult` (Enum)

`HEALTHY`, `DEGRADED`, `UNHEALTHY`, `UNREACHABLE`.

### `EdgeDiscoveryRequest`

```python
@dataclass
class EdgeDiscoveryRequest:
    # Geographic
    user_coordinates: Optional[GeographicCoordinates] = None
    preferred_regions: Optional[List[EdgeRegion]] = None
    excluded_regions: Optional[List[EdgeRegion]] = None

    # Resource
    min_cpu_cores: int = 1
    min_memory_gb: float = 1.0
    min_storage_gb: float = 10.0
    gpu_required: bool = False
    bandwidth_requirements: float = 1.0  # Gbps

    # Service
    database_support: Optional[List[str]] = None
    ai_models_required: Optional[List[str]] = None

    # Compliance
    compliance_zones: Optional[List[ComplianceZone]] = None
    data_residency_required: bool = False

    # Performance
    max_latency_ms: float = 100.0
    min_uptime_percentage: float = 99.0
    max_error_rate: float = 0.01

    # Selection
    selection_strategy: EdgeSelectionStrategy = EdgeSelectionStrategy.BALANCED
    max_results: int = 5

    # Cost
    max_cost_per_hour: Optional[float] = None
```

`__post_init__` replaces every `None` list field with an empty list, and sets `compliance_zones` to `[ComplianceZone.PUBLIC]` when `None`.

### `EdgeScore`

```python
@dataclass
class EdgeScore:
    location: EdgeLocation
    total_score: float
    latency_score: float = 0.0
    cost_score: float = 0.0
    capacity_score: float = 0.0
    performance_score: float = 0.0
    compliance_score: float = 0.0
    estimated_latency_ms: float = 0.0
    estimated_cost_per_hour: float = 0.0
    available_capacity_percentage: float = 0.0
    selection_reasons: Optional[List[str]] = None
    warnings: Optional[List[str]] = None
```

`__post_init__` replaces `None` for `selection_reasons` and `warnings` with `[]`.

### `EdgeDiscovery`

```python
class EdgeDiscovery:
    def __init__(
        self,
        locations: Optional[List[EdgeLocation]] = None,
        health_check_interval_seconds: int = 60,
        cost_model_enabled: bool = True,
        performance_tracking_enabled: bool = True,
    ):
        ...
```

**State initialized:**

- `self.locations: Dict[str, EdgeLocation] = {}` (keyed by `location_id`)
- `self.health_check_interval = health_check_interval_seconds`
- `self.cost_model_enabled`, `self.performance_tracking_enabled` — flags
- `self._performance_history: Dict[str, List[Dict]] = {}`
- `self._cost_history: Dict[str, List[Dict]] = {}`
- `self._health_check_task: Optional[asyncio.Task] = None`
- `self._health_results: Dict[str, HealthCheckResult] = {}`
- `self._last_health_check: Dict[str, datetime] = {}`
- `self.scoring_weights` — dict keyed by `EdgeSelectionStrategy`, each value is a sub-dict with `latency`, `cost`, `capacity`, `performance` weights. Defined strategies: `LATENCY_OPTIMAL`, `COST_OPTIMAL`, `BALANCED`, `CAPACITY_OPTIMAL`, `PERFORMANCE_OPTIMAL`. Other strategies fall through to `BALANCED` weights via `.get(strategy, self.scoring_weights[BALANCED])`.

Exact scoring weight dictionary:

```python
{
    LATENCY_OPTIMAL:     {"latency": 0.7, "cost": 0.1, "capacity": 0.1, "performance": 0.1},
    COST_OPTIMAL:        {"latency": 0.1, "cost": 0.7, "capacity": 0.1, "performance": 0.1},
    BALANCED:            {"latency": 0.3, "cost": 0.3, "capacity": 0.2, "performance": 0.2},
    CAPACITY_OPTIMAL:    {"latency": 0.2, "cost": 0.1, "capacity": 0.5, "performance": 0.2},
    PERFORMANCE_OPTIMAL: {"latency": 0.2, "cost": 0.1, "capacity": 0.2, "performance": 0.5},
}
```

Each provided `EdgeLocation` is added via `add_location`, which also records its `_health_results[location_id] = HealthCheckResult.HEALTHY` and `_last_health_check[location_id] = datetime.now(UTC)`.

**Key methods:**

- `add_location(location)` — registers the location and marks it healthy.
- `async register_edge(edge_config: Dict[str, Any])` — builds an `EdgeLocation` from a flat config dict. Recognises `id`, `region` (short string mapped to `EdgeRegion` via an internal dict), `capacity` (used to derive cpu_cores as `capacity // 100`, memory_gb as `capacity // 50`, storage_gb as `capacity * 2`), `compliance_zones` (list of zone value strings), `endpoint` (defaults to `f"http://{location_id}.edge.local:8080"`), `healthy` (bool, default True), `latency_ms` (defaults to 10), `current_load` (default 0 — used to compute `cpu_utilization` as `current_load / capacity`), `name` (defaults to `f"Edge {region_str.title()}"`). Returns the built `EdgeLocation`.
- `remove_location(location_id)`
- `get_location(location_id) -> Optional[EdgeLocation]`
- `list_locations(regions=None, compliance_zones=None, healthy_only=True) -> List[EdgeLocation]` — filters by region membership, any-match compliance zone, and HEALTHY check result.
- `async discover_optimal_edges(request: EdgeDiscoveryRequest) -> List[EdgeScore]` — runs `_get_candidate_locations`, scores each via `_score_location`, sorts descending by `total_score`, truncates to `request.max_results`.
- `async _get_candidate_locations(request)` — filters locations by `is_healthy`, `is_available_for_workload`, exclusion regions, capability requirements, compliance zones, performance thresholds (`uptime_percentage < min_uptime_percentage` or `error_rate > max_error_rate`), optional `max_latency_ms` check (if `user_coordinates` provided), and optional `max_cost_per_hour`.
- `async _score_location(location, request)` — computes per-dimension scores and weighted total, populates `EdgeScore`, calls `_add_selection_reasoning`.
- `_calculate_latency_score` — piecewise linear: `≤10ms → 1.0`, `10–50ms → 0.9 – (x-10)*0.01`, `50–100ms → 0.5 – (x-50)*0.008`, `>100ms → max(0, 0.1 – (x-100)*0.001)`. Returns `0.8` when `user_coordinates` is None.
- `_calculate_cost_score` — piecewise linear: `≤$0.01/hr → 1.0`, `0.01–0.05 → 0.9 – (x-0.01)*20`, `0.05–0.10 → 0.5 – (x-0.05)*10`, `>0.10 → max(0, 0.1 – (x-0.10)*1)`.
- `_calculate_capacity_score` — piecewise on load factor: `≤0.5 → 1.0 – load*0.5`, `0.5–0.8 → 0.75 – (load-0.5)*1.67`, `>0.8 → max(0, 0.25 – (load-0.8)*1.25)`.
- `_calculate_performance_score` — `uptime_score * 0.4 + error_score * 0.3 + success_score * 0.3`, clamped to `[0, 1]`. `error_score = max(0, 1.0 - error_rate * 10)`.
- `_calculate_compliance_score` — `1.0 + min(0.2, bonus)` on full match (bonus 0.05 per extra zone), or partial `overlap / len(required)` on mismatch.
- `async start_health_monitoring()` / `async stop_health_monitoring()` — lifecycle for `_health_check_loop`.
- `async _health_check_loop()` — runs `_perform_health_checks` then sleeps `health_check_interval` seconds.
- `async _check_location_health(location_id, location)` — calls `location.health_check()`, sets `HEALTHY` / `DEGRADED` (if `health_check_failures ≤ 5`) / `UNHEALTHY` (if `> 5`) / `UNREACHABLE` on exception.
- `get_health_status() -> Dict[str, Any]` — returns totals and per-location status.
- `async find_nearest_edge(user_coordinates, max_results=1)` — convenience wrapper using `LATENCY_OPTIMAL`.
- `async find_cheapest_edge(requirements=None, max_results=1)` — convenience wrapper using `COST_OPTIMAL`.
- `start_discovery` / `stop_discovery` — no-op / cancels background health task.
- `get_all_edges() -> List[EdgeLocation]`, `get_edge(edge_name) -> Optional[EdgeLocation]`
- `async select_edge(strategy=None, compliance_zones=None)` — returns first matching edge (simplified selector).
- Python magic methods: `__len__`, `__contains__`, `__iter__`.

## Compliance (`src/kailash/edge/compliance.py`)

### `DataClassification` (Enum)

`PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, `RESTRICTED`, `PII`, `PHI`, `PCI`, `FINANCIAL`, `HEALTHCARE`, `EDUCATIONAL`, `EU_PERSONAL`, `CALIFORNIA_RESIDENT`, `CANADIAN_PERSONAL`. String values match enum names lowercased.

### `ComplianceRule` (Enum)

Geographic: `DATA_RESIDENCY`, `CROSS_BORDER_TRANSFER`.
Encryption: `ENCRYPTION_AT_REST`, `ENCRYPTION_IN_TRANSIT`, `KEY_MANAGEMENT`.
Access: `RBAC_REQUIRED`, `MFA_REQUIRED`, `AUDIT_LOGGING`.
Lifecycle: `RETENTION_PERIOD`, `RIGHT_TO_DELETE`, `DATA_PORTABILITY`.
Industry: `HIPAA_SAFEGUARDS`, `SOX_CONTROLS`, `PCI_DSS_REQUIREMENTS`.

### `ComplianceRequirement`

```python
@dataclass
class ComplianceRequirement:
    rule: ComplianceRule
    description: str
    enforcement_level: str  # "required", "recommended", "optional"
    applicable_data_types: List[DataClassification]
    applicable_regions: Optional[List[EdgeRegion]] = None
    exceptions: Optional[List[str]] = None
```

`__post_init__` replaces `None` list fields with `[]`.

### `ComplianceContext`

```python
@dataclass
class ComplianceContext:
    data_classification: DataClassification
    data_size_gb: float = 0.0
    contains_personal_data: bool = False
    subject_countries: Optional[List[str]] = None    # ISO country codes
    user_location: Optional[GeographicCoordinates] = None
    user_citizenship: Optional[str] = None
    user_residence: Optional[str] = None
    operation_type: str = "read"                      # "read"|"write"|"process"|"store"
    retention_period_days: Optional[int] = None
    sharing_scope: str = "internal"                   # "internal"|"third_party"|"public"
    explicit_compliance_zones: Optional[List[ComplianceZone]] = None
    override_data_residency: bool = False
```

### `ComplianceDecision`

```python
@dataclass
class ComplianceDecision:
    allowed_locations: List[EdgeLocation]
    prohibited_locations: List[EdgeLocation]
    recommended_location: Optional[EdgeLocation]
    compliance_requirements: List[ComplianceRequirement]
    applied_rules: List[str]
    warnings: List[str]
    violations: List[str]
    decision_timestamp: datetime
    decision_confidence: float  # 0.0 to 1.0
```

### `ComplianceRouter`

```python
class ComplianceRouter:
    def __init__(self):
        self.compliance_rules = self._load_default_compliance_rules()
        self.country_to_region_mapping = self._load_country_region_mapping()
        self.audit_log: List[Dict] = []
```

`ComplianceRouter` takes no constructor arguments. Rules and country mappings are hardcoded.

Default rules loaded in `_load_default_compliance_rules()`:

- **GDPR**: `DATA_RESIDENCY` (required; applicable regions EU_WEST/EU_CENTRAL/EU_NORTH), `RIGHT_TO_DELETE`, `ENCRYPTION_AT_REST`, `AUDIT_LOGGING` — each required, apply to `PII` and `EU_PERSONAL`.
- **CCPA**: `DATA_RESIDENCY` (recommended, region `US_WEST`), `RIGHT_TO_DELETE`, `DATA_PORTABILITY` — apply to `CALIFORNIA_RESIDENT`.
- **HIPAA**: `ENCRYPTION_AT_REST`, `ENCRYPTION_IN_TRANSIT`, `AUDIT_LOGGING`, `MFA_REQUIRED` — all required, apply to `PHI` and `HEALTHCARE`.
- **PCI_DSS**: `ENCRYPTION_AT_REST`, `ENCRYPTION_IN_TRANSIT`, `RBAC_REQUIRED` — all required, apply to `PCI`.
- **SOX**: `AUDIT_LOGGING`, `RETENTION_PERIOD` — required, apply to `FINANCIAL`.
- **PUBLIC**: `ENCRYPTION_IN_TRANSIT` recommended, applies to `PUBLIC` and `INTERNAL`.

Country-to-region mapping covers US/CA (NA), DE/FR/GB/IE/NL/ES/IT (EU variants), SE/NO/FI/DK (EU_NORTH), JP/SG/AU/KR/HK/IN/TH/MY/ID (APAC), BR/MX (SA), ZA (AFRICA), AE/SA (MIDDLE_EAST).

**Key methods:**

- `async route_compliant(context, available_locations) -> ComplianceDecision` — determines applicable zones, gathers requirements for the data classification, evaluates each location, chooses a recommended location, logs the decision to `audit_log` (capped at 1000 entries), returns `ComplianceDecision`.
- `_determine_applicable_zones(context)` — returns `explicit_compliance_zones` if set. Otherwise maps data classification to zones: `PII`/`EU_PERSONAL` with EU subject countries → `GDPR`; `CALIFORNIA_RESIDENT` → `CCPA`; `PHI`/`HEALTHCARE` → `HIPAA`; `PCI` → `PCI_DSS`; `FINANCIAL` → `SOX`. Defaults to `[PUBLIC]` if nothing else matched. The EU country list includes: DE, FR, IT, ES, NL, BE, AT, SE, DK, FI, IE, PT, GR, LU, MT, CY, EE, LV, LT, SI, SK, HR, BG, RO, HU, CZ, PL.
- `_get_compliance_requirements(zones, context)` — intersects each zone's rules with the context's data classification.
- `async _evaluate_location_compliance(location, context, requirements)` — returns dict with `compliant`, `violations`, `warnings`, `applied_rules`. Required-level failures set `compliant=False`; non-required failures become warnings.
- `async _evaluate_compliance_rule(location, context, requirement)` — dispatches by rule type to one of the helpers below. Unimplemented rules return `{"compliant": True, "message": "Rule {rule} not evaluated"}`.
- `async _check_data_residency(location, context, requirement)` — passes if `override_data_residency` is True; else checks `location.region in requirement.applicable_regions`.
- `_check_encryption_at_rest`, `_check_encryption_in_transit`, `_check_audit_logging` — check the corresponding boolean flags on `location.capabilities`.
- `_check_mfa_support`, `_check_rbac_support` — currently always return compliant (source hardcodes `True`; real enforcement expected to be added later).
- `_select_recommended_location(allowed, context, requirements)` — scores each allowed location by `len(compliance_zones) * 10 + max(0, 1000 - distance) + (100 if healthy) + (1 - load_factor) * 50` and returns the highest scorer.
- `_calculate_decision_confidence(allowed_count, prohibited_count, violation_count)` — returns `0.0` if no allowed; `base_confidence - violation_penalty + 0.2` (capped at 1) if `≥3` allowed; `base_confidence - violation_penalty` otherwise. `violation_penalty = min(0.3, violation_count * 0.1)`.
- `async _log_compliance_decision(context, decision)` — appends a dict to `self.audit_log`, truncates to last 1000 entries.
- `classify_data(data: Dict[str, Any]) -> DataClassification` — lowercase JSON substring match on PII keywords (`email`, `ssn`, `social_security`, `phone`, `address`, `name`), then PHI (`medical`, `diagnosis`, `treatment`, `patient`, `health`), then PCI (`credit_card`, `card_number`, `cvv`, `payment`, `billing`), then FINANCIAL (`account_number`, `routing`, `bank`, `financial` — but only if not already matched by PCI). Defaults to `PUBLIC`.
- `get_applicable_regulations(data_classification) -> List[ComplianceZone]` — static mapping.
- `get_audit_log(limit=100) -> List[Dict]`.
- `is_compliant_location(location, data_class, required_zones: List[str]) -> bool` — special-cases GDPR (requires `"gdpr"` in location zones when data is `PII`/`EU_PERSONAL`), otherwise requires all `required_zones` to appear in the location's compliance zones.
- `get_compliance_summary() -> Dict[str, Any]` — aggregates audit log: total decisions, `compliance_rate`, top-5 violations, classification counts, average confidence.

## Consistency (`src/kailash/edge/consistency.py`)

### `ConsistencyLevel` (Enum)

Integer-valued: `ONE=1`, `QUORUM=2`, `ALL=3`, `LOCAL_QUORUM=4`, `EACH_QUORUM=5`.

### `ConsistencyMetrics`

Counter dataclass with zeroed defaults: `writes_total`, `writes_succeeded`, `writes_failed`, `reads_total`, `reads_stale`, `conflicts_detected`, `conflicts_resolved`, `average_replication_lag_ms`, `max_replication_lag_ms`.

### `Version`

```python
@dataclass
class Version:
    number: int
    timestamp: datetime
    edge_id: str
    vector_clock: Dict[str, int] = field(default_factory=dict)

    def is_newer_than(self, other: "Version") -> bool: ...
    def _dominates_vector_clock(self, other: "Version") -> bool: ...
```

`is_newer_than` uses vector clocks if both sides have them (checking strict dominance across all keys), otherwise falls back to timestamp comparison.

### `ConsistencyManager` (Abstract Base)

```python
class ConsistencyManager(ABC):
    def __init__(self):
        self.metrics = ConsistencyMetrics()
        self.logger = logging.getLogger(
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        )

    @abstractmethod
    async def write(self, key: str, value: Any, replicas: List[str],
                    level: ConsistencyLevel = ConsistencyLevel.QUORUM) -> bool: ...

    @abstractmethod
    async def read(self, key: str, replicas: List[str],
                   level: ConsistencyLevel = ConsistencyLevel.QUORUM) -> Optional[Any]: ...
```

### `StrongConsistencyManager(ConsistencyManager)`

Constructor: `__init__(self, write_callback: Callable, read_callback: Callable)`. Additional state: `self.prepared_writes: Dict[str, Set[str]] = {}`.

Implements two-phase commit (2PC). Default level `ConsistencyLevel.ALL` on both write and read. Writes run a Phase 1 (`_prepare_write`) across all replicas, check if the prepared count satisfies `level`, then Phase 2 (`_commit_write`) on prepared replicas. On failure, calls `_abort_transaction`. Reads from all replicas and verifies unanimity; increments `conflicts_detected` on disagreement.

### `EventualConsistencyManager(ConsistencyManager)`

Constructor: `__init__(self, write_callback: Callable, read_callback: Callable)`. Additional state: `self.replication_lag: Dict[str, float] = {}`.

Default level `ConsistencyLevel.ONE` for both. Write path writes to the primary replica (first in the list), spawns an async replication task to the remaining secondaries. Read path tries replicas in order and returns the first non-None result; increments `reads_stale` when the read data is > 5 seconds old (determined by `_is_stale`).

### `CausalConsistencyManager(ConsistencyManager)`

Constructor: `__init__(self, write_callback: Callable, read_callback: Callable)`. Tracks `vector_clocks: Dict[str, Dict[str, int]]`. Implements vector-clock–based causal consistency.

### `BoundedStalenessManager(ConsistencyManager)`

```python
def __init__(
    self,
    write_callback: Callable,
    read_callback: Callable,
    max_staleness_ms: int = 5000,
):
    super().__init__()
    self.write_callback = write_callback
    self.read_callback = read_callback
    self.max_staleness_ms = max_staleness_ms
    self.write_timestamps: Dict[str, float] = {}
```

Writes wrap values in `{"data": value, "write_timestamp": time.time(), "primary_replica": replicas[0]}`. Reads check `staleness_ms = (time.time() - write_timestamp) * 1000` against `max_staleness_ms`; if too stale, tries the primary replica as fallback.

Has a local `_check_consistency_level(successful, total, level)`: `ONE` → ≥1 success, `QUORUM` → > half, `ALL` → equal to total, otherwise QUORUM semantics.

## Coordination (`src/kailash/edge/coordination/`)

### Package exports

```python
from .global_ordering import GlobalOrderingService, HybridLogicalClock
from .leader_election import EdgeLeaderElection
from .partition_detector import PartitionDetector
from .raft import (
    AppendEntriesRequest, AppendEntriesResponse, LogEntry, PersistentState,
    RaftNode, RaftState, RequestVoteRequest, RequestVoteResponse,
)
```

### `RaftNode` (`raft.py`)

```python
class RaftNode:
    def __init__(
        self,
        node_id: str,
        peers: List[str],
        election_timeout_ms: int = 150,
        heartbeat_interval_ms: int = 50,
        rpc_handler: Optional[Callable] = None,
    ):
```

State: `current_term=0`, `voted_for=None`, `log: List[LogEntry] = []`, `state = RaftState.FOLLOWER`, `commit_index=0`, `last_applied=0`, `next_index`, `match_index`, `leader_id=None`, `last_heartbeat = datetime.now()`, `votes_received=0`.

Supporting classes (dataclasses/enums in the same file):

- `RaftState` (Enum): standard Raft states.
- `LogEntry`, `PersistentState` — data structures.
- `RequestVoteRequest`/`RequestVoteResponse`, `AppendEntriesRequest`/`AppendEntriesResponse` — RPC message dataclasses.

### `EdgeLeaderElection` (`leader_election.py`)

```python
class EdgeLeaderElection:
    def __init__(self, raft_nodes: Dict[str, RaftNode]): ...
```

Orchestrates Raft-based leader election across multiple nodes.

### `PartitionDetector` (`partition_detector.py`)

```python
class PartitionDetector:
    def __init__(
        self,
        node_id: str,
        peers: List[str],
        heartbeat_interval_ms: int = 100,
        failure_threshold_ms: int = 500,
    ):
```

Tracks `last_heartbeats: Dict[str, datetime]`, `peer_connections: Dict[str, Set[str]]`, `my_connections: Set[str]`, `current_partition: Optional[Set[str]]`, `partition_history: List[Dict[str, Any]]`. Detects split-brain via heartbeat loss and cluster connectivity analysis.

### `GlobalOrderingService` / `HybridLogicalClock` (`global_ordering.py`)

```python
class HybridLogicalClock:
    def __init__(self, node_id: str): ...

class GlobalOrderingService:
    def __init__(self, node_id: str): ...
```

Hybrid logical clocks combine physical time with logical counters to provide global ordering across distributed nodes.

## Migration (`src/kailash/edge/migration/`)

### Package exports

```python
from .edge_migrator import (
    EdgeMigrator, MigrationCheckpoint, MigrationPhase,
    MigrationPlan, MigrationProgress, MigrationStrategy,
)
```

### `MigrationStrategy` (Enum)

- `LIVE = "live"` — live migration with minimal downtime
- `STAGED = "staged"` — staged migration with controlled phases
- `BULK = "bulk"` — bulk transfer for large datasets
- `INCREMENTAL = "incremental"` — incremental sync with delta updates
- `EMERGENCY = "emergency"` — fast evacuation for failures

### `MigrationPhase` (Enum)

`PLANNING`, `PRE_SYNC`, `SYNC`, `CUTOVER`, `VALIDATION`, `CLEANUP`, `COMPLETED`, `FAILED`, `ROLLBACK`.

### `MigrationPlan`

```python
@dataclass
class MigrationPlan:
    migration_id: str
    source_edge: str
    target_edge: str
    strategy: MigrationStrategy
    workloads: List[str]
    data_size_estimate: int  # bytes
    priority: int = 5        # 1-10, higher is more urgent
    constraints: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
```

### `MigrationProgress`

```python
@dataclass
class MigrationProgress:
    migration_id: str
    phase: MigrationPhase
    progress_percent: float
    data_transferred: int    # bytes
    workloads_migrated: List[str]
    start_time: datetime
    estimated_completion: Optional[datetime] = None
    errors: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
```

### `MigrationCheckpoint`

```python
@dataclass
class MigrationCheckpoint:
    checkpoint_id: str
    migration_id: str
    phase: MigrationPhase
    timestamp: datetime
    state_snapshot: Dict[str, Any]
    can_rollback: bool = True
```

### `EdgeMigrator`

```python
class EdgeMigrator:
    EDGE_API_BASE = "/api/v1"
    HTTP_TIMEOUT = 30

    def __init__(
        self,
        checkpoint_interval: int = 1,                  # seconds (fast for tests)
        sync_batch_size: int = 1000,                   # records per batch
        bandwidth_limit_mbps: Optional[float] = None,
        enable_compression: bool = True,
        edge_endpoints: Optional[Dict[str, str]] = None,
        http_timeout: int = 30,
    ):
```

Expects edge nodes to expose a REST API at their `endpoint_url` with the following endpoints (enumerated in the class docstring):

- `GET  /api/v1/workloads/<workload>/size` → `{"size_bytes": int}`
- `GET  /api/v1/capacity` → `{"available_capacity": float}`
- `GET  /api/v1/workloads/<workload>/data` → binary data batches (NDJSON)
- `POST /api/v1/workloads/<workload>/data` → upload batch data
- `POST /api/v1/workloads/<workload>/start` → start workload
- `POST /api/v1/workloads/<workload>/stop` → stop workload
- `DELETE /api/v1/workloads/<workload>` → remove workload
- `POST /api/v1/routing` → update traffic routing
- `GET  /api/v1/workloads/<workload>/status` → `{"status": "running"|"stopped"}`
- `GET  /api/v1/workloads/<workload>/checksum` → `{"sha256": str}`
- `POST /api/v1/workloads/<workload>/drain` → drain workload connections
- `POST /api/v1/env/prepare` → prepare environment
- `GET  /api/v1/workloads/<workload>/health` → workload health

State: `active_migrations: Dict[str, MigrationPlan]`, `migration_progress: Dict[str, MigrationProgress]`, and related tracking dicts.

## Monitoring (`src/kailash/edge/monitoring/`)

### Package exports

```python
from .edge_monitor import (
    AlertSeverity, EdgeAlert, EdgeHealth, EdgeMetric,
    EdgeMonitor, HealthStatus, MetricType,
)
```

### `EdgeMonitor`

```python
class EdgeMonitor:
    def __init__(
        self,
        retention_period: int = 24 * 60 * 60,   # 24 hours
        alert_cooldown: int = 300,              # 5 minutes
        health_check_interval: int = 30,        # 30 seconds
        anomaly_detection: bool = True,
    ):
```

Hardcoded alert thresholds in `self.alert_thresholds`:

```python
{
    MetricType.LATENCY:        {"warning": 0.5,  "error": 1.0,  "critical": 2.0},
    MetricType.ERROR_RATE:     {"warning": 0.05, "error": 0.1,  "critical": 0.2},
    MetricType.RESOURCE_USAGE: {"warning": 0.7,  "error": 0.85, "critical": 0.95},
    MetricType.AVAILABILITY:   {"warning": 0.99, "error": 0.95, "critical": 0.9},
    MetricType.CACHE_HIT_RATE: {"warning": 0.7,  "error": 0.5,  "critical": 0.3},
}
```

State includes `self.metrics: Dict[str, deque]` (max 10,000 entries per key), `health_status`, `node_start_times`, `alerts: List[EdgeAlert]`, `alert_history`, `baseline_metrics`, and background task handles for health checks, cleanup, and analytics.

`MetricType`, `AlertSeverity`, `HealthStatus` are enums; `EdgeMetric`, `EdgeAlert`, `EdgeHealth` are dataclasses.

## Prediction (`src/kailash/edge/prediction/`)

### Package exports

```python
from .predictive_warmer import (
    PredictionStrategy, PredictiveWarmer, UsagePattern, WarmingDecision,
)
```

### `PredictiveWarmer`

```python
class PredictiveWarmer:
    def __init__(
        self,
        history_window: int = 7 * 24 * 60 * 60,  # 7 days in seconds
        prediction_horizon: int = 300,           # 5 minutes ahead
        confidence_threshold: float = 0.7,
        max_prewarmed_nodes: int = 10,
    ):
```

State: `usage_history: deque(maxlen=10000)`, `pattern_cache: Dict[str, List[UsagePattern]]`, `warmed_nodes: Set[str]`, `warming_decisions: List[WarmingDecision]`, `model_trained: bool = False`, and counters `predictions_made`, `successful_predictions`, `false_positives`, `missed_predictions`. Uses stdlib linear regression (no sklearn dependency).

`PredictionStrategy` is an enum; `UsagePattern` and `WarmingDecision` are dataclasses.

## Resource (`src/kailash/edge/resource/`)

### Package exports

```python
from .cloud_integration import CloudInstance, CloudIntegration, CloudMetrics
from .cloud_integration import CloudProvider as CloudProviderType
from .cloud_integration import InstanceSpec, InstanceState
from .cost_optimizer import (
    CloudProvider, CostMetric, CostOptimization,
    CostOptimizer, InstanceType, OptimizationStrategy,
)
from .docker_integration import (
    ContainerMetrics, ContainerSpec, ContainerState,
    DockerIntegration, NetworkMode, RestartPolicyType, ServiceSpec,
)
from .kubernetes_integration import (
    KubernetesIntegration, KubernetesResource, KubernetesResourceType,
    PodScalingSpec, ScalingPolicy,
)
from .platform_integration import (
    PlatformConfig, PlatformIntegration, PlatformType, ResourceAllocation,
)
from .platform_integration import ResourceRequest as PlatformResourceRequest
from .platform_integration import ResourceScope
from .predictive_scaler import (
    PredictionHorizon, PredictiveScaler, ScalingDecision,
    ScalingPrediction, ScalingStrategy,
)
from .resource_analyzer import ResourceAnalyzer, ResourceMetric, ResourceType
from .resource_pools import AllocationResult, ResourcePool, ResourceRequest
```

Note: `CloudProvider` appears twice because `cloud_integration.CloudProvider` is re-exported under the alias `CloudProviderType`, while `cost_optimizer.CloudProvider` is exported under its own name. Likewise, `ResourceRequest` from `platform_integration` is aliased to `PlatformResourceRequest` so it does not collide with `resource_pools.ResourceRequest`.

### `ResourceAnalyzer`

```python
class ResourceAnalyzer:
    def __init__(
        self,
        history_window: int = 3600,                   # 1 hour
        analysis_interval: int = 60,                  # 1 minute
        anomaly_threshold: float = 2.5,               # Standard deviations
        pattern_confidence_threshold: float = 0.7,
    ):
```

State: `metrics: Dict[str, deque]` (maxlen 1000 per key), `patterns: List[ResourcePattern]`, `bottlenecks: List[Bottleneck]`, `anomalies: List[Dict[str, Any]]`.

Supporting types in the same file: `ResourceType` and `BottleneckType` (enums), `ResourceMetric`, `ResourcePattern`, `Bottleneck` (dataclasses).

### Other resource components

Other classes in `src/kailash/edge/resource/` include `ResourcePool` / `ResourceRequest` / `AllocationResult` (resource_pools.py), `PredictiveScaler` (predictive_scaler.py), `CostOptimizer` (cost_optimizer.py), `KubernetesIntegration`, `DockerIntegration`, `CloudIntegration`, `PlatformIntegration`. Each exposes its own enums and dataclasses via `resource/__init__.py`. Callers that need full parameter lists should consult the source files directly — the public surface is stable but the internal state of these classes is large.

## Design Notes

- The `ComplianceRouter` class has no constructor parameters — rules are hardcoded and loaded in `__init__`. Customization is via mutating `self.compliance_rules` after construction.
- `EdgeLocation.is_healthy` and `EdgeLocation.is_available_for_workload` are distinct gates: the first is purely "not clearly broken", the second adds the status allowlist `{ACTIVE, DEGRADED}` and the `cpu_utilization < 0.8` headroom requirement.
- `EdgeLocation.calculate_cost_for_workload` accepts `memory_gb_hours` but does not consume it. If future cost modelling adds memory pricing, the parameter is already wired.
- `update_metrics` only recovers from `DEGRADED` to `ACTIVE` — it does not recover other states.
- Discovery scoring weights are only explicitly defined for 5 strategies (LATENCY_OPTIMAL, COST_OPTIMAL, BALANCED, CAPACITY_OPTIMAL, PERFORMANCE_OPTIMAL). COMPLIANCE_FIRST and LOAD_BALANCED fall through to BALANCED weights via the `.get()` default.
- There is no public `EdgeRegistry` or `EdgeNetworkManager` class; coordination and management are distributed across the subpackages listed above.
