# Posture-Aware Execution System Design

## Executive Summary

This document designs a comprehensive posture-aware execution system that adjusts verification depth, approval requirements, and monitoring based on the agent's current trust posture. The system integrates with Enterprise-App work units and provides SDK APIs for posture-aware development.

**Key Features**:

1. Posture-based verification depth (QUICK/STANDARD/FULL)
2. Posture-based approval workflows
3. Automatic posture downgrade on failures (circuit breaker pattern)
4. Posture metrics dashboards
5. Work unit integration with posture constraints

---

## 1. Posture-to-Execution Mapping

### 1.1 Verification Depth by Posture

| Posture                   | Verification Level | Latency Target | What's Checked                          |
| ------------------------- | ------------------ | -------------- | --------------------------------------- |
| Pseudo (BLOCKED)          | N/A                | N/A            | All actions routed to human             |
| Supervised                | FULL               | ~50ms          | Signatures + Capabilities + Constraints |
| Shared Planning           | STANDARD           | ~5ms           | Capabilities + Constraints              |
| Continuous Insight        | STANDARD           | ~5ms           | Capabilities + Constraints              |
| Delegated (FULL_AUTONOMY) | QUICK              | ~1ms           | Hash + Expiration only                  |

### 1.2 Approval Requirements

```python
@dataclass
class PostureApprovalConfig:
    posture: TrustPosture
    requires_pre_approval: bool
    approval_timeout_seconds: int
    auto_approve_on_timeout: bool
    required_approvers: int
    escalation_chain: List[str]

POSTURE_APPROVAL_CONFIGS = {
    TrustPosture.BLOCKED: PostureApprovalConfig(
        posture=TrustPosture.BLOCKED,
        requires_pre_approval=True,
        approval_timeout_seconds=0,  # Never auto-approve
        auto_approve_on_timeout=False,
        required_approvers=1,
        escalation_chain=[]
    ),
    TrustPosture.HUMAN_DECIDES: PostureApprovalConfig(
        posture=TrustPosture.HUMAN_DECIDES,
        requires_pre_approval=True,
        approval_timeout_seconds=300,  # 5 minutes
        auto_approve_on_timeout=False,
        required_approvers=1,
        escalation_chain=["fallback_approver"]
    ),
    TrustPosture.SUPERVISED: PostureApprovalConfig(
        posture=TrustPosture.SUPERVISED,
        requires_pre_approval=False,  # Log but don't block
        approval_timeout_seconds=0,
        auto_approve_on_timeout=True,
        required_approvers=0,
        escalation_chain=[]
    ),
    TrustPosture.FULL_AUTONOMY: PostureApprovalConfig(
        posture=TrustPosture.FULL_AUTONOMY,
        requires_pre_approval=False,
        approval_timeout_seconds=0,
        auto_approve_on_timeout=True,
        required_approvers=0,
        escalation_chain=[]
    )
}
```

### 1.3 Monitoring Levels

| Posture            | Log Level | Alert Threshold     | Report Interval | Anomaly Detection |
| ------------------ | --------- | ------------------- | --------------- | ----------------- |
| BLOCKED            | ERROR     | N/A                 | N/A             | N/A               |
| HUMAN_DECIDES      | WARNING   | Every action        | Real-time       | Enabled           |
| SUPERVISED         | INFO      | Failures only       | 5 minutes       | Enabled           |
| Shared Planning    | INFO      | Plan deviations     | 15 minutes      | Enabled           |
| Continuous Insight | DEBUG     | Anomaly score > 0.7 | 1 hour          | Enabled           |
| FULL_AUTONOMY      | DEBUG     | Exceptions only     | 24 hours        | Optional          |

---

## 2. Posture-Based Circuit Breakers

### 2.1 Concept

Automatic posture downgrade when repeated failures indicate the agent may be operating beyond its competence.

```
FULL_AUTONOMY ──3 failures in 1h──► SUPERVISED ──2 more failures──► HUMAN_DECIDES
      ▲                                   │
      │                                   │
      └──── 50 successes + 24h ───────────┘
```

### 2.2 Implementation

```python
@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 3
    failure_window_seconds: int = 3600  # 1 hour
    recovery_threshold: int = 50
    recovery_window_seconds: int = 86400  # 24 hours
    cooldown_seconds: int = 300  # 5 min before downgrade takes effect

class PostureCircuitBreaker:
    def __init__(self, config: CircuitBreakerConfig):
        self._config = config
        self._failure_counts: Dict[str, List[datetime]] = {}
        self._success_counts: Dict[str, List[datetime]] = {}
        self._current_postures: Dict[str, TrustPosture] = {}
        self._cooldown_until: Dict[str, datetime] = {}

    async def record_outcome(
        self,
        agent_id: str,
        success: bool,
        current_posture: TrustPosture
    ) -> Optional[TrustPosture]:
        """
        Record action outcome and return new posture if changed.
        """
        now = datetime.now(timezone.utc)

        if success:
            self._record_success(agent_id, now)
            return self._check_upgrade(agent_id, current_posture)
        else:
            self._record_failure(agent_id, now)
            return self._check_downgrade(agent_id, current_posture)

    def _check_downgrade(
        self,
        agent_id: str,
        current_posture: TrustPosture
    ) -> Optional[TrustPosture]:
        """Check if failures warrant posture downgrade"""
        failures = self._get_recent_failures(agent_id)

        if len(failures) >= self._config.failure_threshold:
            new_posture = self._downgrade_posture(current_posture)
            if new_posture != current_posture:
                logger.warning(
                    f"Circuit breaker triggered for {agent_id}: "
                    f"{current_posture.value} -> {new_posture.value}"
                )
                return new_posture

        return None

    def _downgrade_posture(self, posture: TrustPosture) -> TrustPosture:
        """Get next lower posture"""
        downgrade_map = {
            TrustPosture.FULL_AUTONOMY: TrustPosture.SUPERVISED,
            TrustPosture.SUPERVISED: TrustPosture.HUMAN_DECIDES,
            TrustPosture.HUMAN_DECIDES: TrustPosture.BLOCKED,
            TrustPosture.BLOCKED: TrustPosture.BLOCKED
        }
        return downgrade_map[posture]
```

### 2.3 Integration with TrustedAgent

```python
class TrustedAgent:
    def __init__(self, ..., circuit_breaker: PostureCircuitBreaker = None):
        self._circuit_breaker = circuit_breaker or PostureCircuitBreaker()
        self._current_posture: Optional[TrustPosture] = None

    async def execute_async(self, inputs, action, ...):
        # Get current posture
        posture = await self._get_current_posture()

        # Apply posture-based verification
        verification = await self._verify_with_posture(action, posture)

        # Execute action
        success = False
        try:
            result = await self._agent.execute_async(inputs=inputs, **kwargs)
            success = True
            return result
        except Exception as e:
            success = False
            raise
        finally:
            # Record outcome for circuit breaker
            new_posture = await self._circuit_breaker.record_outcome(
                self.agent_id,
                success,
                posture
            )
            if new_posture:
                await self._apply_posture_change(new_posture)
```

### 2.4 Circuit Breaker Hardening (Second-Pass Review)

The original circuit breaker design was identified as weaponizable for denial-of-service. The following hardening measures address this:

#### 2.4.1 Failure Categorization

Not all failures should count toward circuit breaker threshold:

```python
class FailureCategory(Enum):
    SECURITY = "security"          # Counts: trust violations, auth failures
    LOGIC = "logic"                # Counts: constraint violations, invalid actions
    EXTERNAL_SERVICE = "external"  # Does NOT count: third-party API failures
    NETWORK = "network"            # Does NOT count: connectivity issues
    RESOURCE = "resource"          # Does NOT count: OOM, disk full

class SmartCircuitBreaker(PostureCircuitBreaker):
    def _should_count_failure(self, failure: AgentFailure) -> bool:
        """Only count security and logic failures, not external issues."""
        return failure.category in (FailureCategory.SECURITY, FailureCategory.LOGIC)
```

#### 2.4.2 Admin Override

```python
async def admin_force_close(
    self, agent_id: str, admin_id: str, reason: str, duration_seconds: int = 3600
) -> None:
    """Emergency override: force circuit to CLOSED state.

    Requires: Admin with 'circuit_breaker_override' capability verified at FULL level.
    Logged to: Tamper-evident audit trail.
    Duration: Auto-reverts after specified duration.
    """
    await self._verify_admin_authority(admin_id)
    self._state[agent_id] = CircuitState.CLOSED
    self._override_expiry[agent_id] = now() + timedelta(seconds=duration_seconds)
    await self.audit.record("circuit_breaker_override", admin_id=admin_id,
                           agent_id=agent_id, reason=reason, duration=duration_seconds)
```

#### 2.4.3 Recovery Jitter

```python
def _get_recovery_timeout(self, agent_id: str) -> float:
    """Add jitter to recovery timeout to prevent coordinated attacks."""
    base_timeout = self.config.recovery_timeout
    jitter = random.uniform(0.5, 1.5)  # 50-150% of base
    return base_timeout * jitter
```

#### 2.4.4 Gradual Degradation

Instead of binary OPEN/CLOSED, use graduated states:

| State        | Behavior                                     | Trigger                                   |
| ------------ | -------------------------------------------- | ----------------------------------------- |
| CLOSED       | Normal operation                             | Default                                   |
| DEGRADED_25  | 25% of operations require extra verification | 3+ security failures in window            |
| DEGRADED_50  | 50% random sampling for FULL verification    | 5+ security failures                      |
| DEGRADED_100 | All operations require FULL verification     | 8+ security failures                      |
| OPEN         | All operations blocked, human required       | 10+ security failures OR critical failure |

This prevents an attacker from causing a sudden jump from fully operational to fully blocked.

---

## 3. Posture Metrics Dashboards

### 3.1 Metrics Schema

```python
@dataclass
class PostureMetrics:
    agent_id: str
    posture: TrustPosture
    timestamp: datetime

    # Action counts
    actions_total: int
    actions_success: int
    actions_failed: int
    actions_denied: int

    # Timing
    avg_verification_latency_ms: float
    p99_verification_latency_ms: float

    # Approvals (for HUMAN_DECIDES)
    approvals_requested: int
    approvals_granted: int
    approvals_denied: int
    avg_approval_time_seconds: float

    # Circuit breaker
    circuit_breaker_trips: int
    posture_downgrades: int
    posture_upgrades: int
    time_in_posture_seconds: int

    # Anomalies
    anomaly_score: float
    anomaly_alerts: int

class PostureMetricsCollector:
    def __init__(self, metrics_backend: MetricsBackend):
        self._backend = metrics_backend

    async def record_action(
        self,
        agent_id: str,
        posture: TrustPosture,
        action: str,
        result: ActionResult,
        verification_latency_ms: float
    ):
        await self._backend.increment(
            f"posture_actions_total",
            labels={"agent_id": agent_id, "posture": posture.value}
        )
        await self._backend.increment(
            f"posture_actions_{result.value}",
            labels={"agent_id": agent_id, "posture": posture.value}
        )
        await self._backend.histogram(
            "posture_verification_latency_ms",
            verification_latency_ms,
            labels={"agent_id": agent_id, "posture": posture.value}
        )
```

### 3.2 Dashboard Views

**Per-Posture View**:

```
┌─────────────────────────────────────────────────────────────────┐
│                   TRUST POSTURE DASHBOARD                        │
├─────────────────────────────────────────────────────────────────┤
│  Posture: SUPERVISED              Agent: invoice-processor       │
│  Time in Posture: 7d 4h 23m       Posture Health: ████████░░ 82% │
├─────────────────────────────────────────────────────────────────┤
│  ACTIONS (Last 24h)               VERIFICATION LATENCY          │
│  ───────────────────              ─────────────────────         │
│  Total:    1,247                  Avg:  4.2ms                   │
│  Success:  1,201 (96.3%)          P50:  3.1ms                   │
│  Failed:      34 (2.7%)           P99: 12.4ms                   │
│  Denied:      12 (1.0%)                                         │
├─────────────────────────────────────────────────────────────────┤
│  CIRCUIT BREAKER                  POSTURE HISTORY               │
│  ─────────────────                ───────────────               │
│  Status: CLOSED                   [Timeline graph]              │
│  Failures: 2/3                    FULL_AUTO → SUPERVISED (7d)   │
│  Successes: 47/50                                               │
├─────────────────────────────────────────────────────────────────┤
│  RECENT ANOMALIES                 UPGRADE PROGRESS              │
│  ────────────────                 ────────────────              │
│  None in last 24h                 47/50 successes needed        │
│                                   23h until eligible            │
└─────────────────────────────────────────────────────────────────┘
```

**Organization Overview**:

```
┌─────────────────────────────────────────────────────────────────┐
│            ORGANIZATION POSTURE DISTRIBUTION                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  BLOCKED          ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 3 (2%)│
│  HUMAN_DECIDES    ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 12 (8%)│
│  SUPERVISED       ██████████████████████░░░░░░░░░░░░░░░░ 54 (36%)│
│  SHARED_PLANNING  ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░ 21 (14%)│
│  CONTINUOUS       █████████████████████████████░░░░░░░░░ 42 (28%)│
│  FULL_AUTONOMY    ██████████████████░░░░░░░░░░░░░░░░░░░░ 18 (12%)│
│                                                                  │
│  Total Agents: 150                                               │
├─────────────────────────────────────────────────────────────────┤
│  POSTURE CHANGES (Last 7 Days)                                   │
│  ────────────────────────────                                    │
│  ↑ Upgrades:   23                                                │
│  ↓ Downgrades: 7 (3 via circuit breaker)                        │
│  → Unchanged:  120                                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Integration with Enterprise-App Work Units

### 4.1 Work Unit Posture Configuration

```python
@dataclass
class WorkUnitPostureConfig:
    """Posture configuration for a work unit"""

    work_unit_id: str

    # Posture settings
    initial_posture: TrustPosture
    minimum_posture: TrustPosture  # Can't go below this
    maximum_posture: TrustPosture  # Can't exceed this

    # Circuit breaker overrides
    enable_circuit_breaker: bool = True
    failure_threshold_override: Optional[int] = None

    # Approval overrides
    approval_required_for_actions: List[str] = field(default_factory=list)
    skip_approval_for_actions: List[str] = field(default_factory=list)

    # Monitoring
    alert_on_posture_change: bool = True
    require_explanation_for_demotion: bool = True

class WorkUnitPostureManager:
    """Manages posture for Enterprise-App work units"""

    async def configure_work_unit(
        self,
        work_unit_id: str,
        config: WorkUnitPostureConfig
    ):
        """Apply posture configuration to work unit"""
        await self._store.save_config(work_unit_id, config)

    async def get_effective_posture(
        self,
        work_unit_id: str,
        agent_id: str
    ) -> TrustPosture:
        """Get effective posture considering work unit constraints"""
        config = await self._store.get_config(work_unit_id)
        agent_posture = await self._trust_ops.get_agent_posture(agent_id)

        # Apply work unit constraints
        effective = max(
            config.minimum_posture,
            min(agent_posture, config.maximum_posture)
        )

        return effective
```

### 4.2 Work Unit Execution Flow

```
┌───────────────────────────────────────────────────────────────────┐
│                    WORK UNIT EXECUTION FLOW                        │
│                                                                    │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐│
│  │ Work Unit   │───►│ Posture     │───►│ Execution               ││
│  │ Submitted   │    │ Resolution  │    │ Engine                  ││
│  └─────────────┘    └─────────────┘    └───────────┬─────────────┘│
│                                                     │              │
│                                                     ▼              │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    POSTURE-BASED ROUTING                     │  │
│  │                                                              │  │
│  │  BLOCKED/PSEUDO    HUMAN_DECIDES    SUPERVISED    FULL_AUTO │  │
│  │        │                │               │             │      │  │
│  │        ▼                ▼               ▼             ▼      │  │
│  │  ┌─────────┐      ┌─────────┐     ┌─────────┐   ┌─────────┐ │  │
│  │  │ Route   │      │ Queue   │     │ Execute │   │ Execute │ │  │
│  │  │ to      │      │ for     │     │ + Log   │   │ Freely  │ │  │
│  │  │ Human   │      │ Approval│     │         │   │         │ │  │
│  │  └─────────┘      └────┬────┘     └─────────┘   └─────────┘ │  │
│  │                        │                                     │  │
│  │                        ▼                                     │  │
│  │                  ┌─────────┐                                 │  │
│  │                  │ Human   │                                 │  │
│  │                  │ Approval│                                 │  │
│  │                  │ Workflow│                                 │  │
│  │                  └────┬────┘                                 │  │
│  │                       │                                      │  │
│  │              ┌────────┴────────┐                            │  │
│  │              ▼                 ▼                            │  │
│  │         ┌─────────┐      ┌─────────┐                        │  │
│  │         │ Approved│      │ Denied  │                        │  │
│  │         │ Execute │      │ Reject  │                        │  │
│  │         └─────────┘      └─────────┘                        │  │
│  │                                                              │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                    │
└───────────────────────────────────────────────────────────────────┘
```

### 4.3 API Integration

```python
# Enterprise-App Work Unit API
@router.post("/api/v1/work-units/{work_unit_id}/execute")
async def execute_work_unit(
    work_unit_id: str,
    request: ExecuteRequest,
    trust_context: TrustContext = Depends(get_trust_context)
):
    # Get work unit posture config
    posture_config = await posture_manager.get_config(work_unit_id)

    # Resolve effective posture
    effective_posture = await posture_manager.get_effective_posture(
        work_unit_id=work_unit_id,
        agent_id=request.agent_id
    )

    # Route based on posture
    if effective_posture == TrustPosture.BLOCKED:
        return await route_to_human(work_unit_id, request)

    if effective_posture == TrustPosture.HUMAN_DECIDES:
        approval = await request_approval(work_unit_id, request)
        if not approval.granted:
            return ExecuteResponse(status="denied", reason=approval.reason)

    # Execute with posture-aware verification
    result = await execution_engine.execute(
        work_unit_id=work_unit_id,
        request=request,
        posture=effective_posture,
        trust_context=trust_context
    )

    return result
```

---

## 5. SDK APIs for Posture-Aware Execution

### 5.1 Core APIs

```python
class PostureAwareAgent:
    """
    Agent wrapper with built-in posture awareness.

    Example:
        agent = PostureAwareAgent(
            base_agent=my_agent,
            trust_ops=trust_ops,
            initial_posture=TrustPosture.SUPERVISED
        )

        # Execution automatically adjusts to posture
        result = await agent.execute_async(inputs={"query": "..."})

        # Check current posture
        posture = await agent.get_current_posture()

        # Request posture upgrade (requires evidence)
        await agent.request_posture_upgrade(
            target=TrustPosture.FULL_AUTONOMY,
            evidence={"success_count": 100, "days_in_posture": 30}
        )
    """

    def __init__(
        self,
        base_agent: BaseAgent,
        trust_ops: TrustOperations,
        agent_id: str,
        initial_posture: TrustPosture = TrustPosture.SUPERVISED,
        circuit_breaker: Optional[PostureCircuitBreaker] = None,
        metrics_collector: Optional[PostureMetricsCollector] = None
    ):
        self._agent = base_agent
        self._trust_ops = trust_ops
        self._agent_id = agent_id
        self._current_posture = initial_posture
        self._circuit_breaker = circuit_breaker or PostureCircuitBreaker()
        self._metrics = metrics_collector

    async def get_current_posture(self) -> TrustPosture:
        """Get agent's current trust posture."""
        return self._current_posture

    async def get_posture_constraints(self) -> PostureConstraints:
        """Get constraints associated with current posture."""
        return POSTURE_CONSTRAINTS[self._current_posture]

    async def execute_async(
        self,
        inputs: Dict[str, Any],
        action: str = "execute",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute with posture-aware verification and monitoring.
        """
        start_time = datetime.now(timezone.utc)
        posture = self._current_posture

        # 1. Check if action allowed at current posture
        if posture == TrustPosture.BLOCKED:
            raise PostureBlockedError(self._agent_id, action)

        # 2. Get posture-appropriate verification level
        verification_level = self._get_verification_level(posture)

        # 3. Verify trust
        verification = await self._trust_ops.verify(
            agent_id=self._agent_id,
            action=action,
            level=verification_level
        )

        verification_latency = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        if not verification.valid:
            if self._metrics:
                await self._metrics.record_action(
                    self._agent_id, posture, action,
                    ActionResult.DENIED, verification_latency
                )
            raise VerificationFailedError(action, verification.reason)

        # 4. Check approval requirements
        if self._requires_approval(posture, action):
            approval = await self._request_approval(action, inputs)
            if not approval.granted:
                raise ApprovalDeniedError(action, approval.reason)

        # 5. Execute
        success = False
        try:
            result = await self._agent.execute_async(inputs=inputs, **kwargs)
            success = True
            return result
        except Exception as e:
            success = False
            raise
        finally:
            # 6. Record metrics
            if self._metrics:
                await self._metrics.record_action(
                    self._agent_id,
                    posture,
                    action,
                    ActionResult.SUCCESS if success else ActionResult.FAILURE,
                    verification_latency
                )

            # 7. Check circuit breaker
            new_posture = await self._circuit_breaker.record_outcome(
                self._agent_id, success, posture
            )
            if new_posture:
                await self._handle_posture_change(posture, new_posture)

    async def request_posture_upgrade(
        self,
        target: TrustPosture,
        evidence: Dict[str, Any],
        reason: str = ""
    ) -> PostureUpgradeResult:
        """
        Request upgrade to higher posture.

        Args:
            target: Target posture to upgrade to
            evidence: Evidence supporting upgrade (metrics, success counts, etc.)
            reason: Human-readable reason for request

        Returns:
            PostureUpgradeResult with approval status
        """
        # Validate upgrade is allowed
        if target.value <= self._current_posture.value:
            raise InvalidPostureUpgradeError("Target must be higher than current")

        # Submit upgrade request
        request = PostureUpgradeRequest(
            agent_id=self._agent_id,
            current_posture=self._current_posture,
            target_posture=target,
            evidence=evidence,
            reason=reason,
            requested_at=datetime.now(timezone.utc)
        )

        # Evaluate against criteria
        return await self._posture_manager.evaluate_upgrade(request)

    def _get_verification_level(self, posture: TrustPosture) -> VerificationLevel:
        """Map posture to verification level."""
        level_map = {
            TrustPosture.BLOCKED: VerificationLevel.FULL,
            TrustPosture.HUMAN_DECIDES: VerificationLevel.FULL,
            TrustPosture.SUPERVISED: VerificationLevel.STANDARD,
            TrustPosture.FULL_AUTONOMY: VerificationLevel.QUICK
        }
        return level_map.get(posture, VerificationLevel.STANDARD)
```

### 5.2 Decorator APIs

```python
def require_posture(min_posture: TrustPosture):
    """
    Decorator to require minimum posture for method execution.

    Example:
        @require_posture(TrustPosture.SUPERVISED)
        async def sensitive_operation(self, data):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            current = await self.get_current_posture()
            if current.value < min_posture.value:
                raise PostureInsufficientError(
                    required=min_posture,
                    current=current
                )
            return await func(self, *args, **kwargs)
        return wrapper
    return decorator


def posture_fallback(fallback_posture: TrustPosture):
    """
    Decorator to specify fallback posture on verification failure.

    Example:
        @posture_fallback(TrustPosture.HUMAN_DECIDES)
        async def risky_operation(self, data):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            try:
                return await func(self, *args, **kwargs)
            except VerificationFailedError:
                # Fall back to more restrictive posture
                self._current_posture = fallback_posture
                return await func(self, *args, **kwargs)
        return wrapper
    return decorator
```

### 5.3 Context Manager API

```python
@asynccontextmanager
async def posture_context(
    agent: PostureAwareAgent,
    temporary_posture: TrustPosture,
    reason: str
):
    """
    Temporarily operate at a different posture.

    Example:
        async with posture_context(agent, TrustPosture.HUMAN_DECIDES, "sensitive data"):
            await agent.execute_async({"action": "delete_user"})
    """
    original_posture = agent._current_posture

    try:
        # Temporarily set new posture
        agent._current_posture = temporary_posture
        logger.info(
            f"Posture temporarily changed: {original_posture.value} -> "
            f"{temporary_posture.value}. Reason: {reason}"
        )
        yield agent
    finally:
        # Restore original posture
        agent._current_posture = original_posture
        logger.info(f"Posture restored: {original_posture.value}")
```

---

## 6. Implementation Roadmap

### Phase 1: Core Posture Infrastructure (Week 1-2)

- [ ] Implement 5-posture enum in SDK
- [ ] Add posture field to ExecutionContext
- [ ] Implement verification level mapping
- [ ] Add basic posture-aware TrustedAgent

### Phase 2: Circuit Breaker (Week 3-4)

- [ ] Implement PostureCircuitBreaker
- [ ] Add failure tracking
- [ ] Implement automatic downgrade
- [ ] Add upgrade path logic

### Phase 3: Metrics & Monitoring (Week 5-6)

- [ ] Define PostureMetrics schema
- [ ] Implement metrics collection
- [ ] Create dashboard views
- [ ] Add alerting integration

### Phase 4: Work Unit Integration (Week 7-8)

- [ ] Design WorkUnitPostureConfig
- [ ] Implement posture resolution
- [ ] Add API endpoints
- [ ] Document integration patterns

### Phase 5: SDK APIs & Documentation (Week 9-10)

- [ ] Implement PostureAwareAgent
- [ ] Add decorator APIs
- [ ] Create example applications
- [ ] Write comprehensive documentation
