# Phase 4: Enterprise-App Trust Services Implementation Plan

## Executive Summary

This document details the design and implementation of five core trust services required in the Enterprise-App platform to fully realize the CARE/EATP trust framework. These services bridge the Kailash SDK's trust primitives to platform-level orchestration and user-facing capabilities.

**Complexity Score**: Enterprise (32/40)
- Technical: 9/10 (cryptographic operations, distributed systems)
- Business: 8/10 (compliance-critical, multi-tenant)
- Operational: 8/10 (high availability, audit requirements)
- Integration: 7/10 (SDK integration, SSO providers)

---

## 1. Genesis Ceremony Service

### Purpose

Orchestrate the creation of genesis records when users authenticate via SSO. The Genesis Ceremony is the foundational trust establishment that creates the root of all subsequent delegation chains.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    GENESIS CEREMONY SERVICE ARCHITECTURE                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌──────────────┐      ┌──────────────┐      ┌──────────────┐         │
│   │   SSO        │      │   Genesis    │      │   SDK        │         │
│   │   Provider   │─────▶│   Ceremony   │─────▶│   Trust      │         │
│   │   (Okta/AD)  │      │   Service    │      │   Module     │         │
│   └──────────────┘      └──────────────┘      └──────────────┘         │
│          │                     │                     │                  │
│          │                     ▼                     │                  │
│          │              ┌──────────────┐             │                  │
│          │              │   Genesis    │             │                  │
│          └─────────────▶│   Event      │◀────────────┘                  │
│                         │   Store      │                                │
│                         └──────────────┘                                │
│                                │                                        │
│                                ▼                                        │
│                         ┌──────────────┐                                │
│                         │   Trust      │                                │
│                         │   Event      │                                │
│                         │   Stream     │                                │
│                         └──────────────┘                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Service Interface

```python
# services/trust/genesis_ceremony_service.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

from kaizen.trust import (
    HumanOrigin,
    PseudoAgent,
    PseudoAgentFactory,
    TrustOperations,
    GenesisRecord,
    OrganizationalAuthority,
)


class CeremonyStatus(str, Enum):
    """Status of a genesis ceremony."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REVOKED = "revoked"


@dataclass
class CeremonyConfig:
    """Configuration for genesis ceremony behavior."""
    require_mfa: bool = True
    require_email_verification: bool = True
    auto_grant_base_capabilities: bool = True
    default_constraint_template: Optional[str] = None
    max_concurrent_ceremonies: int = 100
    ceremony_timeout_seconds: int = 300


@dataclass
class CeremonyResult:
    """Result of a genesis ceremony."""
    ceremony_id: str
    status: CeremonyStatus
    human_origin: Optional[HumanOrigin]
    pseudo_agent: Optional[PseudoAgent]
    genesis_record: Optional[GenesisRecord]
    created_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class GenesisCeremonyService:
    """
    Orchestrates the creation of genesis records from SSO authentication.

    The Genesis Ceremony establishes the root of trust for a human user,
    creating their PseudoAgent representation and initial capability attestations.
    """

    def __init__(
        self,
        trust_operations: TrustOperations,
        pseudo_agent_factory: PseudoAgentFactory,
        authority_registry: 'OrganizationalAuthorityRegistry',
        event_publisher: 'TrustEventPublisher',
        config: Optional[CeremonyConfig] = None,
    ):
        self._trust_ops = trust_operations
        self._factory = pseudo_agent_factory
        self._authority_registry = authority_registry
        self._event_publisher = event_publisher
        self._config = config or CeremonyConfig()
        self._active_ceremonies: Dict[str, CeremonyResult] = {}

    async def initiate_ceremony(
        self,
        sso_token: str,
        org_id: str,
        additional_claims: Optional[Dict[str, Any]] = None,
    ) -> CeremonyResult:
        """
        Initiate a genesis ceremony from SSO authentication.

        Args:
            sso_token: JWT token from SSO provider
            org_id: Organization identifier for authority lookup
            additional_claims: Additional claims to include in genesis

        Returns:
            CeremonyResult with pending status
        """
        ceremony_id = self._generate_ceremony_id()

        result = CeremonyResult(
            ceremony_id=ceremony_id,
            status=CeremonyStatus.PENDING,
            human_origin=None,
            pseudo_agent=None,
            genesis_record=None,
            created_at=datetime.utcnow(),
            completed_at=None,
        )

        self._active_ceremonies[ceremony_id] = result

        # Publish ceremony initiated event
        await self._event_publisher.publish_ceremony_initiated(ceremony_id, org_id)

        return result

    async def execute_ceremony(
        self,
        ceremony_id: str,
        sso_token: str,
        org_id: str,
        initial_capabilities: Optional[List[str]] = None,
        initial_constraints: Optional[Dict[str, Any]] = None,
    ) -> CeremonyResult:
        """
        Execute the full genesis ceremony.

        This is the core ceremony logic:
        1. Validate SSO token
        2. Extract human identity
        3. Create PseudoAgent
        4. Establish trust with organization authority
        5. Grant initial capabilities
        6. Publish genesis event
        """
        result = self._active_ceremonies.get(ceremony_id)
        if not result:
            raise ValueError(f"Ceremony not found: {ceremony_id}")

        result.status = CeremonyStatus.IN_PROGRESS

        try:
            # Step 1: Create PseudoAgent from SSO token
            pseudo_agent = await self._factory.from_jwt(sso_token)
            result.human_origin = pseudo_agent.human_origin
            result.pseudo_agent = pseudo_agent

            # Step 2: Lookup organizational authority
            authority = await self._authority_registry.get_authority(org_id)
            if not authority:
                raise ValueError(f"Organization authority not found: {org_id}")

            # Step 3: Create genesis record
            genesis_record = await self._create_genesis_record(
                pseudo_agent=pseudo_agent,
                authority=authority,
                capabilities=initial_capabilities or [],
                constraints=initial_constraints or {},
            )
            result.genesis_record = genesis_record

            # Step 4: Store genesis ceremony record
            await self._store_ceremony_record(result)

            # Step 5: Mark complete and publish event
            result.status = CeremonyStatus.COMPLETED
            result.completed_at = datetime.utcnow()

            await self._event_publisher.publish_genesis_completed(
                ceremony_id=ceremony_id,
                human_id=pseudo_agent.human_origin.human_id,
                org_id=org_id,
            )

            return result

        except Exception as e:
            result.status = CeremonyStatus.FAILED
            result.error_message = str(e)
            await self._event_publisher.publish_ceremony_failed(ceremony_id, str(e))
            raise

    async def revoke_genesis(
        self,
        human_id: str,
        reason: str,
        revoked_by: str,
    ) -> Dict[str, Any]:
        """
        Revoke a genesis record, triggering cascade revocation.

        This is called when:
        - User account is disabled
        - User leaves organization
        - Security incident requires access revocation
        """
        # Delegate to cascade revocation engine
        revocation_result = await self._trust_ops.revoke_by_human(
            human_id=human_id,
            reason=reason,
        )

        # Publish revocation event
        await self._event_publisher.publish_genesis_revoked(
            human_id=human_id,
            reason=reason,
            revoked_by=revoked_by,
            agents_revoked=revocation_result,
        )

        return {
            "human_id": human_id,
            "agents_revoked": len(revocation_result),
            "revocation_time": datetime.utcnow().isoformat(),
        }

    async def get_ceremony_status(self, ceremony_id: str) -> Optional[CeremonyResult]:
        """Get the current status of a ceremony."""
        return self._active_ceremonies.get(ceremony_id)

    async def list_active_ceremonies(
        self,
        org_id: Optional[str] = None,
    ) -> List[CeremonyResult]:
        """List all active (non-completed) ceremonies."""
        ceremonies = [
            c for c in self._active_ceremonies.values()
            if c.status in (CeremonyStatus.PENDING, CeremonyStatus.IN_PROGRESS)
        ]
        return ceremonies

    async def _create_genesis_record(
        self,
        pseudo_agent: PseudoAgent,
        authority: OrganizationalAuthority,
        capabilities: List[str],
        constraints: Dict[str, Any],
    ) -> GenesisRecord:
        """Create the genesis record linking human to organization."""
        # Use SDK trust operations to establish trust
        chain = await self._trust_ops.establish(
            agent_id=pseudo_agent.agent_id,
            authority_id=authority.authority_id,
            capabilities=[
                {"capability": cap, "capability_type": "ACCESS"}
                for cap in capabilities
            ],
            constraints=constraints,
        )
        return chain.genesis

    async def _store_ceremony_record(self, result: CeremonyResult) -> None:
        """Persist ceremony record for audit purposes."""
        # Implementation: store to database
        pass

    def _generate_ceremony_id(self) -> str:
        """Generate unique ceremony identifier."""
        import uuid
        return f"ceremony-{uuid.uuid4().hex[:12]}"
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/trust/genesis/initiate` | Start genesis ceremony |
| POST | `/api/v1/trust/genesis/{ceremony_id}/execute` | Execute ceremony |
| GET | `/api/v1/trust/genesis/{ceremony_id}` | Get ceremony status |
| POST | `/api/v1/trust/genesis/{human_id}/revoke` | Revoke genesis |
| GET | `/api/v1/trust/genesis` | List ceremonies (admin) |

### SDK Integration Points

- `PseudoAgentFactory.from_jwt()` - Token validation and PseudoAgent creation
- `TrustOperations.establish()` - Genesis record creation
- `TrustOperations.revoke_by_human()` - Cascade revocation trigger
- `HumanOrigin` - Human identity representation

---

## 2. Cascade Revocation Engine

### Purpose

Compute the impact of revocation operations and execute them efficiently across the entire delegation tree, ensuring no orphaned delegations remain active.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CASCADE REVOCATION ENGINE                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │                      IMPACT ANALYZER                             │  │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │  │
│   │  │ Depth-First  │  │ Breadth-First│  │ Impact       │          │  │
│   │  │ Traversal    │  │ Traversal    │  │ Calculator   │          │  │
│   │  └──────────────┘  └──────────────┘  └──────────────┘          │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                              │                                          │
│                              ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │                    EXECUTION ENGINE                              │  │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │  │
│   │  │ Parallel     │  │ Transaction  │  │ Rollback     │          │  │
│   │  │ Executor     │  │ Manager      │  │ Handler      │          │  │
│   │  └──────────────┘  └──────────────┘  └──────────────┘          │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                              │                                          │
│                              ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────┐  │
│   │                    EVENT PUBLISHER                               │  │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │  │
│   │  │ Agent        │  │ Real-time    │  │ Audit        │          │  │
│   │  │ Notifier     │  │ Stream       │  │ Logger       │          │  │
│   │  └──────────────┘  └──────────────┘  └──────────────┘          │  │
│   └─────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Service Interface

```python
# services/trust/cascade_revocation_engine.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Any
from enum import Enum
import asyncio

from kaizen.trust import TrustOperations, DelegationRecord


class RevocationStrategy(str, Enum):
    """Strategy for executing cascade revocation."""
    PARALLEL = "parallel"        # Revoke all levels in parallel
    LEVEL_ORDER = "level_order"  # Revoke level by level (safer)
    DEPTH_FIRST = "depth_first"  # Revoke deepest first


@dataclass
class ImpactAnalysis:
    """Analysis of revocation impact before execution."""
    root_entity_id: str
    root_entity_type: str  # "human" or "agent"
    total_agents_affected: int
    delegation_depth: int
    agents_by_level: Dict[int, List[str]]
    active_tasks_affected: int
    estimated_execution_time_ms: float
    warnings: List[str] = field(default_factory=list)


@dataclass
class RevocationProgress:
    """Real-time progress of revocation execution."""
    revocation_id: str
    total_agents: int
    revoked_count: int
    failed_count: int
    current_level: int
    percentage_complete: float
    elapsed_time_ms: float
    current_agent: Optional[str] = None


@dataclass
class RevocationResult:
    """Final result of cascade revocation."""
    revocation_id: str
    root_entity_id: str
    reason: str
    initiated_by: str
    initiated_at: datetime
    completed_at: datetime
    total_revoked: int
    failed_revocations: List[Dict[str, str]]
    execution_time_ms: float
    strategy_used: RevocationStrategy


class CascadeRevocationEngine:
    """
    Compute and execute cascade revocation across delegation trees.

    Key features:
    - Impact analysis before execution
    - Parallel execution with configurable strategies
    - Real-time progress streaming
    - Transaction safety with rollback support
    - Audit logging of all revocations
    """

    def __init__(
        self,
        trust_operations: TrustOperations,
        event_publisher: 'TrustEventPublisher',
        max_parallel_revocations: int = 50,
        default_strategy: RevocationStrategy = RevocationStrategy.LEVEL_ORDER,
    ):
        self._trust_ops = trust_operations
        self._event_publisher = event_publisher
        self._max_parallel = max_parallel_revocations
        self._default_strategy = default_strategy
        self._active_revocations: Dict[str, RevocationProgress] = {}

    async def analyze_impact(
        self,
        entity_id: str,
        entity_type: str = "agent",
    ) -> ImpactAnalysis:
        """
        Analyze the impact of revoking an entity before execution.

        Args:
            entity_id: ID of entity to revoke (human_id or agent_id)
            entity_type: "human" or "agent"

        Returns:
            ImpactAnalysis with full impact assessment
        """
        if entity_type == "human":
            delegations = await self._find_all_delegations_from_human(entity_id)
        else:
            delegations = await self._find_all_delegations_from_agent(entity_id)

        # Build delegation tree
        agents_by_level: Dict[int, List[str]] = {}
        max_depth = 0

        for delegation in delegations:
            depth = delegation.delegation_depth
            if depth not in agents_by_level:
                agents_by_level[depth] = []
            agents_by_level[depth].append(delegation.delegatee_id)
            max_depth = max(max_depth, depth)

        # Count active tasks
        active_tasks = await self._count_active_tasks(
            [d.delegatee_id for d in delegations]
        )

        # Estimate execution time
        total_agents = sum(len(agents) for agents in agents_by_level.values())
        estimated_time = self._estimate_execution_time(total_agents, max_depth)

        # Generate warnings
        warnings = []
        if total_agents > 100:
            warnings.append(f"Large cascade: {total_agents} agents will be revoked")
        if active_tasks > 0:
            warnings.append(f"{active_tasks} active tasks will be interrupted")

        return ImpactAnalysis(
            root_entity_id=entity_id,
            root_entity_type=entity_type,
            total_agents_affected=total_agents,
            delegation_depth=max_depth,
            agents_by_level=agents_by_level,
            active_tasks_affected=active_tasks,
            estimated_execution_time_ms=estimated_time,
            warnings=warnings,
        )

    async def execute_revocation(
        self,
        entity_id: str,
        entity_type: str,
        reason: str,
        initiated_by: str,
        strategy: Optional[RevocationStrategy] = None,
        notify_agents: bool = True,
    ) -> RevocationResult:
        """
        Execute cascade revocation.

        Args:
            entity_id: ID of entity to revoke
            entity_type: "human" or "agent"
            reason: Reason for revocation
            initiated_by: ID of user initiating revocation
            strategy: Revocation strategy (default: LEVEL_ORDER)
            notify_agents: Whether to notify affected agents

        Returns:
            RevocationResult with execution details
        """
        revocation_id = self._generate_revocation_id()
        strategy = strategy or self._default_strategy
        initiated_at = datetime.utcnow()

        # Get impact analysis
        impact = await self.analyze_impact(entity_id, entity_type)

        # Initialize progress tracking
        progress = RevocationProgress(
            revocation_id=revocation_id,
            total_agents=impact.total_agents_affected,
            revoked_count=0,
            failed_count=0,
            current_level=0,
            percentage_complete=0.0,
            elapsed_time_ms=0.0,
        )
        self._active_revocations[revocation_id] = progress

        # Publish revocation started event
        await self._event_publisher.publish_revocation_started(
            revocation_id=revocation_id,
            entity_id=entity_id,
            impact=impact,
        )

        failed_revocations = []

        try:
            if strategy == RevocationStrategy.PARALLEL:
                failed_revocations = await self._execute_parallel(
                    impact, reason, progress
                )
            elif strategy == RevocationStrategy.LEVEL_ORDER:
                failed_revocations = await self._execute_level_order(
                    impact, reason, progress
                )
            else:
                failed_revocations = await self._execute_depth_first(
                    impact, reason, progress
                )

            if notify_agents:
                await self._notify_affected_agents(impact, reason)

        except Exception as e:
            failed_revocations.append({
                "error": str(e),
                "phase": "execution",
            })

        completed_at = datetime.utcnow()
        execution_time = (completed_at - initiated_at).total_seconds() * 1000

        result = RevocationResult(
            revocation_id=revocation_id,
            root_entity_id=entity_id,
            reason=reason,
            initiated_by=initiated_by,
            initiated_at=initiated_at,
            completed_at=completed_at,
            total_revoked=progress.revoked_count,
            failed_revocations=failed_revocations,
            execution_time_ms=execution_time,
            strategy_used=strategy,
        )

        # Publish completion event
        await self._event_publisher.publish_revocation_completed(result)

        # Cleanup
        del self._active_revocations[revocation_id]

        return result

    async def get_progress(
        self,
        revocation_id: str,
    ) -> Optional[RevocationProgress]:
        """Get real-time progress of an active revocation."""
        return self._active_revocations.get(revocation_id)

    async def _execute_parallel(
        self,
        impact: ImpactAnalysis,
        reason: str,
        progress: RevocationProgress,
    ) -> List[Dict[str, str]]:
        """Execute all revocations in parallel (fast but aggressive)."""
        all_agents = []
        for agents in impact.agents_by_level.values():
            all_agents.extend(agents)

        semaphore = asyncio.Semaphore(self._max_parallel)
        failed = []

        async def revoke_one(agent_id: str):
            async with semaphore:
                try:
                    await self._trust_ops.revoke(agent_id, reason, cascade=False)
                    progress.revoked_count += 1
                except Exception as e:
                    failed.append({"agent_id": agent_id, "error": str(e)})
                    progress.failed_count += 1

                progress.percentage_complete = (
                    (progress.revoked_count + progress.failed_count) /
                    progress.total_agents * 100
                )

        await asyncio.gather(*[revoke_one(a) for a in all_agents])
        return failed

    async def _execute_level_order(
        self,
        impact: ImpactAnalysis,
        reason: str,
        progress: RevocationProgress,
    ) -> List[Dict[str, str]]:
        """Execute revocations level by level (safe, predictable)."""
        failed = []

        for level in sorted(impact.agents_by_level.keys()):
            progress.current_level = level
            agents = impact.agents_by_level[level]

            # Revoke entire level in parallel
            semaphore = asyncio.Semaphore(self._max_parallel)

            async def revoke_one(agent_id: str):
                async with semaphore:
                    try:
                        await self._trust_ops.revoke(agent_id, reason, cascade=False)
                        progress.revoked_count += 1
                    except Exception as e:
                        failed.append({"agent_id": agent_id, "error": str(e)})
                        progress.failed_count += 1

                    progress.percentage_complete = (
                        (progress.revoked_count + progress.failed_count) /
                        progress.total_agents * 100
                    )

                    # Publish progress update
                    await self._event_publisher.publish_revocation_progress(progress)

            await asyncio.gather(*[revoke_one(a) for a in agents])

        return failed

    async def _execute_depth_first(
        self,
        impact: ImpactAnalysis,
        reason: str,
        progress: RevocationProgress,
    ) -> List[Dict[str, str]]:
        """Execute revocations depth-first (revoke leaves first)."""
        failed = []

        # Process deepest level first
        for level in sorted(impact.agents_by_level.keys(), reverse=True):
            progress.current_level = level
            agents = impact.agents_by_level[level]

            for agent_id in agents:
                progress.current_agent = agent_id
                try:
                    await self._trust_ops.revoke(agent_id, reason, cascade=False)
                    progress.revoked_count += 1
                except Exception as e:
                    failed.append({"agent_id": agent_id, "error": str(e)})
                    progress.failed_count += 1

                progress.percentage_complete = (
                    (progress.revoked_count + progress.failed_count) /
                    progress.total_agents * 100
                )

        return failed

    async def _find_all_delegations_from_human(
        self,
        human_id: str,
    ) -> List[DelegationRecord]:
        """Find all delegations originating from a human."""
        # Use SDK's find by human origin
        return await self._trust_ops.find_delegations_by_human_origin(human_id)

    async def _find_all_delegations_from_agent(
        self,
        agent_id: str,
    ) -> List[DelegationRecord]:
        """Find all delegations from an agent (recursive)."""
        return await self._trust_ops.find_delegations_from(agent_id, recursive=True)

    async def _count_active_tasks(self, agent_ids: List[str]) -> int:
        """Count active tasks across agents."""
        # Implementation: query task registry
        return 0

    async def _notify_affected_agents(
        self,
        impact: ImpactAnalysis,
        reason: str,
    ) -> None:
        """Send notifications to affected agents."""
        # Implementation: use notification service
        pass

    def _estimate_execution_time(self, total_agents: int, depth: int) -> float:
        """Estimate execution time in milliseconds."""
        # ~10ms per agent with parallel execution
        base_time = total_agents * 10
        # Add overhead for depth
        overhead = depth * 50
        return base_time + overhead

    def _generate_revocation_id(self) -> str:
        """Generate unique revocation ID."""
        import uuid
        return f"revoke-{uuid.uuid4().hex[:12]}"
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/trust/revocation/analyze` | Analyze impact before revocation |
| POST | `/api/v1/trust/revocation/execute` | Execute cascade revocation |
| GET | `/api/v1/trust/revocation/{id}/progress` | Get revocation progress (SSE) |
| GET | `/api/v1/trust/revocation/{id}` | Get revocation result |
| GET | `/api/v1/trust/revocation/history` | List past revocations |

---

## 3. Trust Health Dashboard Service

### Purpose

Aggregate trust health metrics across the organization, providing real-time visibility into trust chain integrity, delegation patterns, and potential security concerns.

### Service Interface

```python
# services/trust/trust_health_service.py

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum


class HealthStatus(str, Enum):
    """Overall trust health status."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class TrustMetrics:
    """Core trust metrics."""
    total_active_agents: int
    total_active_delegations: int
    total_genesis_records: int
    active_humans: int
    average_delegation_depth: float
    max_delegation_depth: int
    delegations_per_human: float
    verification_success_rate: float
    verification_avg_latency_ms: float
    revocations_last_24h: int


@dataclass
class SLAMetrics:
    """Verification SLA compliance metrics."""
    quick_verification_p50_ms: float
    quick_verification_p99_ms: float
    quick_sla_compliance: float  # < 1ms target
    standard_verification_p50_ms: float
    standard_verification_p99_ms: float
    standard_sla_compliance: float  # < 5ms target
    full_verification_p50_ms: float
    full_verification_p99_ms: float
    full_sla_compliance: float  # < 50ms target


@dataclass
class SecurityAlerts:
    """Security-related alerts."""
    unusual_delegation_patterns: List[Dict[str, Any]]
    expired_delegations_active: int
    constraint_violations_24h: int
    failed_verifications_24h: int
    suspicious_genesis_attempts: int


@dataclass
class TrustHealthReport:
    """Complete trust health report."""
    generated_at: datetime
    org_id: str
    overall_status: HealthStatus
    metrics: TrustMetrics
    sla_metrics: SLAMetrics
    security_alerts: SecurityAlerts
    recommendations: List[str]


class TrustHealthDashboardService:
    """
    Aggregates and analyzes trust health metrics across the organization.

    Provides:
    - Real-time health status
    - SLA compliance monitoring
    - Security anomaly detection
    - Trend analysis
    - Actionable recommendations
    """

    def __init__(
        self,
        trust_store: 'TrustStore',
        audit_store: 'AuditStore',
        metrics_collector: 'MetricsCollector',
        alert_threshold_config: Optional[Dict[str, Any]] = None,
    ):
        self._trust_store = trust_store
        self._audit_store = audit_store
        self._metrics = metrics_collector
        self._thresholds = alert_threshold_config or self._default_thresholds()

    async def get_health_report(
        self,
        org_id: str,
        include_recommendations: bool = True,
    ) -> TrustHealthReport:
        """Generate comprehensive trust health report."""
        metrics = await self._collect_trust_metrics(org_id)
        sla_metrics = await self._collect_sla_metrics(org_id)
        security_alerts = await self._detect_security_anomalies(org_id)

        overall_status = self._calculate_overall_status(
            metrics, sla_metrics, security_alerts
        )

        recommendations = []
        if include_recommendations:
            recommendations = self._generate_recommendations(
                metrics, sla_metrics, security_alerts
            )

        return TrustHealthReport(
            generated_at=datetime.utcnow(),
            org_id=org_id,
            overall_status=overall_status,
            metrics=metrics,
            sla_metrics=sla_metrics,
            security_alerts=security_alerts,
            recommendations=recommendations,
        )

    async def get_real_time_metrics(
        self,
        org_id: str,
    ) -> Dict[str, Any]:
        """Get real-time metrics for dashboard streaming."""
        return {
            "active_agents": await self._count_active_agents(org_id),
            "verifications_per_second": await self._get_verification_rate(org_id),
            "current_sla_compliance": await self._get_current_sla_compliance(org_id),
            "active_revocations": await self._get_active_revocations(org_id),
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def get_trend_analysis(
        self,
        org_id: str,
        metric_name: str,
        time_range: timedelta = timedelta(days=7),
        granularity: str = "hour",
    ) -> List[Dict[str, Any]]:
        """Get trend data for a specific metric."""
        # Implementation: query time-series data
        pass

    async def _collect_trust_metrics(self, org_id: str) -> TrustMetrics:
        """Collect core trust metrics."""
        # Implementation: aggregate from trust store
        pass

    async def _collect_sla_metrics(self, org_id: str) -> SLAMetrics:
        """Collect verification SLA metrics."""
        # Implementation: query metrics collector
        pass

    async def _detect_security_anomalies(self, org_id: str) -> SecurityAlerts:
        """Detect security anomalies in trust patterns."""
        # Implementation: anomaly detection logic
        pass

    def _calculate_overall_status(
        self,
        metrics: TrustMetrics,
        sla_metrics: SLAMetrics,
        security_alerts: SecurityAlerts,
    ) -> HealthStatus:
        """Calculate overall health status."""
        # Critical conditions
        if security_alerts.constraint_violations_24h > self._thresholds["critical_violations"]:
            return HealthStatus.CRITICAL
        if sla_metrics.standard_sla_compliance < self._thresholds["critical_sla"]:
            return HealthStatus.CRITICAL

        # Warning conditions
        if security_alerts.unusual_delegation_patterns:
            return HealthStatus.WARNING
        if sla_metrics.standard_sla_compliance < self._thresholds["warning_sla"]:
            return HealthStatus.WARNING

        return HealthStatus.HEALTHY

    def _generate_recommendations(
        self,
        metrics: TrustMetrics,
        sla_metrics: SLAMetrics,
        security_alerts: SecurityAlerts,
    ) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []

        if metrics.average_delegation_depth > 5:
            recommendations.append(
                "Consider flattening delegation chains - average depth is high"
            )

        if sla_metrics.quick_sla_compliance < 0.95:
            recommendations.append(
                "Enable trust chain caching to improve QUICK verification SLA"
            )

        if security_alerts.expired_delegations_active > 0:
            recommendations.append(
                f"Clean up {security_alerts.expired_delegations_active} expired delegations"
            )

        return recommendations

    def _default_thresholds(self) -> Dict[str, Any]:
        """Default alert thresholds."""
        return {
            "critical_violations": 10,
            "critical_sla": 0.90,
            "warning_sla": 0.95,
            "max_delegation_depth": 10,
        }
```

---

## 4. Constraint Envelope Compiler

### Purpose

Compile user-friendly UI constraint configurations into SDK-compatible `ConstraintEnvelope` objects, providing validation and preview capabilities.

### Service Interface

```python
# services/trust/constraint_compiler.py

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Dict, List, Optional, Any, Union
from enum import Enum

from kaizen.trust import ConstraintEnvelope, Constraint, ConstraintType


@dataclass
class UIConstraintConfig:
    """User-friendly constraint configuration from UI."""
    cost_limit: Optional[float] = None
    cost_currency: str = "USD"
    time_window_start: Optional[str] = None  # "HH:MM"
    time_window_end: Optional[str] = None    # "HH:MM"
    time_window_timezone: str = "UTC"
    allowed_days: Optional[List[str]] = None  # ["monday", "tuesday", ...]
    resource_patterns: Optional[List[str]] = None
    rate_limit_requests: Optional[int] = None
    rate_limit_period: str = "hour"  # "minute", "hour", "day"
    geo_restrictions: Optional[List[str]] = None  # ISO country codes
    expires_at: Optional[datetime] = None
    custom_constraints: Optional[Dict[str, Any]] = None


@dataclass
class CompilationResult:
    """Result of constraint compilation."""
    success: bool
    envelope: Optional[ConstraintEnvelope]
    validation_errors: List[str]
    warnings: List[str]
    preview: Dict[str, Any]  # Human-readable preview


class ConstraintTemplateType(str, Enum):
    """Pre-defined constraint templates."""
    MINIMAL = "minimal"
    STANDARD_OFFICE = "standard_office"
    STRICT_COMPLIANCE = "strict_compliance"
    HIGH_VALUE_TRANSACTION = "high_value_transaction"
    READ_ONLY = "read_only"
    CUSTOM = "custom"


class ConstraintEnvelopeCompiler:
    """
    Compiles UI constraint configurations to SDK ConstraintEnvelope format.

    Provides:
    - UI-to-SDK constraint translation
    - Constraint validation
    - Template application
    - Tightening verification
    - Human-readable preview
    """

    def __init__(
        self,
        template_repository: 'ConstraintTemplateRepository',
    ):
        self._templates = template_repository

    def compile(
        self,
        config: UIConstraintConfig,
        parent_envelope: Optional[ConstraintEnvelope] = None,
    ) -> CompilationResult:
        """
        Compile UI configuration to SDK ConstraintEnvelope.

        Args:
            config: UI constraint configuration
            parent_envelope: Parent constraints for tightening validation

        Returns:
            CompilationResult with envelope and any errors/warnings
        """
        errors = []
        warnings = []
        constraints = []

        # Compile cost constraint
        if config.cost_limit is not None:
            cost_result = self._compile_cost_constraint(
                config.cost_limit,
                config.cost_currency,
                parent_envelope,
            )
            if cost_result.get("error"):
                errors.append(cost_result["error"])
            else:
                constraints.append(cost_result["constraint"])
                if cost_result.get("warning"):
                    warnings.append(cost_result["warning"])

        # Compile time window constraint
        if config.time_window_start and config.time_window_end:
            time_result = self._compile_time_constraint(
                config.time_window_start,
                config.time_window_end,
                config.time_window_timezone,
                config.allowed_days,
                parent_envelope,
            )
            if time_result.get("error"):
                errors.append(time_result["error"])
            else:
                constraints.append(time_result["constraint"])
                if time_result.get("warning"):
                    warnings.append(time_result["warning"])

        # Compile resource scope constraint
        if config.resource_patterns:
            resource_result = self._compile_resource_constraint(
                config.resource_patterns,
                parent_envelope,
            )
            if resource_result.get("error"):
                errors.append(resource_result["error"])
            else:
                constraints.append(resource_result["constraint"])

        # Compile rate limit constraint
        if config.rate_limit_requests is not None:
            rate_result = self._compile_rate_constraint(
                config.rate_limit_requests,
                config.rate_limit_period,
                parent_envelope,
            )
            if rate_result.get("error"):
                errors.append(rate_result["error"])
            else:
                constraints.append(rate_result["constraint"])

        # Compile geo restriction constraint
        if config.geo_restrictions:
            geo_result = self._compile_geo_constraint(
                config.geo_restrictions,
                parent_envelope,
            )
            if geo_result.get("error"):
                errors.append(geo_result["error"])
            else:
                constraints.append(geo_result["constraint"])

        # Compile custom constraints
        if config.custom_constraints:
            for name, value in config.custom_constraints.items():
                constraints.append(Constraint(
                    constraint_type=ConstraintType.CUSTOM,
                    name=name,
                    value=value,
                ))

        # Build envelope
        envelope = None
        if not errors:
            envelope = ConstraintEnvelope(
                constraints=constraints,
                expires_at=config.expires_at,
            )

        # Generate preview
        preview = self._generate_preview(config, constraints)

        return CompilationResult(
            success=len(errors) == 0,
            envelope=envelope,
            validation_errors=errors,
            warnings=warnings,
            preview=preview,
        )

    def apply_template(
        self,
        template_type: ConstraintTemplateType,
        overrides: Optional[UIConstraintConfig] = None,
    ) -> UIConstraintConfig:
        """Apply a constraint template with optional overrides."""
        template = self._templates.get_template(template_type)

        if overrides:
            # Merge overrides into template
            return self._merge_configs(template, overrides)

        return template

    def validate_tightening(
        self,
        child_config: UIConstraintConfig,
        parent_envelope: ConstraintEnvelope,
    ) -> List[str]:
        """Validate that child constraints are tighter than parent."""
        errors = []

        # Check cost limit
        parent_cost = self._get_parent_cost_limit(parent_envelope)
        if child_config.cost_limit and parent_cost:
            if child_config.cost_limit > parent_cost:
                errors.append(
                    f"Cost limit {child_config.cost_limit} exceeds parent limit {parent_cost}"
                )

        # Check time window
        parent_window = self._get_parent_time_window(parent_envelope)
        if parent_window and child_config.time_window_start:
            if not self._is_time_window_subset(
                child_config.time_window_start,
                child_config.time_window_end,
                parent_window,
            ):
                errors.append("Time window must be within parent time window")

        # Check resource patterns
        parent_resources = self._get_parent_resources(parent_envelope)
        if parent_resources and child_config.resource_patterns:
            for pattern in child_config.resource_patterns:
                if not self._is_resource_subset(pattern, parent_resources):
                    errors.append(f"Resource pattern '{pattern}' not within parent scope")

        return errors

    def _compile_cost_constraint(
        self,
        limit: float,
        currency: str,
        parent: Optional[ConstraintEnvelope],
    ) -> Dict[str, Any]:
        """Compile cost limit constraint."""
        # Validate against parent
        if parent:
            parent_limit = self._get_parent_cost_limit(parent)
            if parent_limit and limit > parent_limit:
                return {"error": f"Cost limit {limit} exceeds parent {parent_limit}"}

        constraint = Constraint(
            constraint_type=ConstraintType.COST,
            name="cost_limit",
            value={"limit": limit, "currency": currency},
        )
        return {"constraint": constraint}

    def _compile_time_constraint(
        self,
        start: str,
        end: str,
        timezone: str,
        allowed_days: Optional[List[str]],
        parent: Optional[ConstraintEnvelope],
    ) -> Dict[str, Any]:
        """Compile time window constraint."""
        constraint = Constraint(
            constraint_type=ConstraintType.TIME,
            name="time_window",
            value={
                "start": start,
                "end": end,
                "timezone": timezone,
                "allowed_days": allowed_days or [
                    "monday", "tuesday", "wednesday", "thursday", "friday"
                ],
            },
        )
        return {"constraint": constraint}

    def _compile_resource_constraint(
        self,
        patterns: List[str],
        parent: Optional[ConstraintEnvelope],
    ) -> Dict[str, Any]:
        """Compile resource scope constraint."""
        constraint = Constraint(
            constraint_type=ConstraintType.RESOURCE,
            name="resource_scope",
            value={"patterns": patterns},
        )
        return {"constraint": constraint}

    def _compile_rate_constraint(
        self,
        requests: int,
        period: str,
        parent: Optional[ConstraintEnvelope],
    ) -> Dict[str, Any]:
        """Compile rate limit constraint."""
        constraint = Constraint(
            constraint_type=ConstraintType.RATE,
            name="rate_limit",
            value={"requests": requests, "period": period},
        )
        return {"constraint": constraint}

    def _compile_geo_constraint(
        self,
        countries: List[str],
        parent: Optional[ConstraintEnvelope],
    ) -> Dict[str, Any]:
        """Compile geographic restriction constraint."""
        constraint = Constraint(
            constraint_type=ConstraintType.GEO,
            name="geo_restrictions",
            value={"allowed_countries": countries},
        )
        return {"constraint": constraint}

    def _generate_preview(
        self,
        config: UIConstraintConfig,
        constraints: List[Constraint],
    ) -> Dict[str, Any]:
        """Generate human-readable preview of constraints."""
        preview = {"summary": [], "details": {}}

        if config.cost_limit:
            preview["summary"].append(f"Cost limit: {config.cost_limit} {config.cost_currency}")
            preview["details"]["cost"] = {
                "limit": config.cost_limit,
                "currency": config.cost_currency,
            }

        if config.time_window_start:
            preview["summary"].append(
                f"Active: {config.time_window_start}-{config.time_window_end} {config.time_window_timezone}"
            )

        if config.resource_patterns:
            preview["summary"].append(f"Resources: {len(config.resource_patterns)} patterns")
            preview["details"]["resources"] = config.resource_patterns

        if config.rate_limit_requests:
            preview["summary"].append(
                f"Rate limit: {config.rate_limit_requests}/{config.rate_limit_period}"
            )

        if config.geo_restrictions:
            preview["summary"].append(f"Geo: {', '.join(config.geo_restrictions)}")

        return preview
```

---

## 5. Posture Progression Engine

### Purpose

Automatically advance agent trust postures based on behavioral metrics, compliance history, and organizational policies.

### Service Interface

```python
# services/trust/posture_progression_engine.py

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum

from kaizen.trust.postures import TrustPosture


class ProgressionDirection(str, Enum):
    """Direction of posture change."""
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    MAINTAIN = "maintain"


@dataclass
class PostureMetrics:
    """Metrics used for posture evaluation."""
    agent_id: str
    current_posture: TrustPosture
    days_at_current_posture: int
    total_executions: int
    successful_executions: int
    failed_executions: int
    constraint_violations: int
    verification_failures: int
    human_overrides: int
    average_response_time_ms: float
    compliance_score: float  # 0.0 to 1.0


@dataclass
class ProgressionRule:
    """Rule for posture progression."""
    rule_id: str
    name: str
    from_posture: TrustPosture
    to_posture: TrustPosture
    direction: ProgressionDirection
    conditions: Dict[str, Any]
    min_days_required: int
    requires_approval: bool


@dataclass
class ProgressionRecommendation:
    """Recommendation for posture change."""
    agent_id: str
    current_posture: TrustPosture
    recommended_posture: TrustPosture
    direction: ProgressionDirection
    confidence_score: float
    triggering_rules: List[str]
    metrics_summary: Dict[str, Any]
    requires_approval: bool
    auto_apply: bool


class PostureProgressionEngine:
    """
    Automatically advances agent trust postures based on behavior and metrics.

    Posture Levels (from restricted to autonomous):
    1. SUPERVISED - Human approval for all actions
    2. GUIDED - Human approval for high-risk actions
    3. COLLABORATIVE - Human oversight, agent initiative
    4. AUTONOMOUS - Full autonomy within constraints

    Provides:
    - Automatic posture advancement based on metrics
    - Posture downgrade on violations
    - Approval workflows for upgrades
    - Audit trail of posture changes
    """

    def __init__(
        self,
        trust_operations: 'TrustOperations',
        metrics_collector: 'MetricsCollector',
        approval_manager: 'ApprovalManager',
        rules_repository: 'PostureRulesRepository',
    ):
        self._trust_ops = trust_operations
        self._metrics = metrics_collector
        self._approvals = approval_manager
        self._rules = rules_repository

    async def evaluate_agent(
        self,
        agent_id: str,
    ) -> ProgressionRecommendation:
        """
        Evaluate an agent for posture progression.

        Returns recommendation for posture change (if any).
        """
        # Collect metrics
        metrics = await self._collect_agent_metrics(agent_id)

        # Get applicable rules
        rules = await self._rules.get_rules_for_posture(metrics.current_posture)

        # Evaluate upgrade rules
        upgrade_rules = [r for r in rules if r.direction == ProgressionDirection.UPGRADE]
        upgrade_match = self._evaluate_rules(metrics, upgrade_rules)

        # Evaluate downgrade rules
        downgrade_rules = [r for r in rules if r.direction == ProgressionDirection.DOWNGRADE]
        downgrade_match = self._evaluate_rules(metrics, downgrade_rules)

        # Downgrade takes priority over upgrade
        if downgrade_match:
            return self._create_recommendation(
                metrics, downgrade_match, ProgressionDirection.DOWNGRADE
            )

        if upgrade_match:
            return self._create_recommendation(
                metrics, upgrade_match, ProgressionDirection.UPGRADE
            )

        return ProgressionRecommendation(
            agent_id=agent_id,
            current_posture=metrics.current_posture,
            recommended_posture=metrics.current_posture,
            direction=ProgressionDirection.MAINTAIN,
            confidence_score=1.0,
            triggering_rules=[],
            metrics_summary=self._summarize_metrics(metrics),
            requires_approval=False,
            auto_apply=False,
        )

    async def apply_progression(
        self,
        recommendation: ProgressionRecommendation,
        approved_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Apply a posture progression recommendation.

        For upgrades requiring approval, approved_by must be provided.
        """
        if recommendation.requires_approval and not approved_by:
            raise ValueError("Upgrade requires approval")

        if recommendation.direction == ProgressionDirection.MAINTAIN:
            return {"applied": False, "reason": "No change recommended"}

        # Apply posture change via SDK
        await self._trust_ops.update_agent_posture(
            agent_id=recommendation.agent_id,
            new_posture=recommendation.recommended_posture,
            reason=f"Auto-progression: {recommendation.triggering_rules}",
            approved_by=approved_by,
        )

        return {
            "applied": True,
            "agent_id": recommendation.agent_id,
            "old_posture": recommendation.current_posture.value,
            "new_posture": recommendation.recommended_posture.value,
            "direction": recommendation.direction.value,
            "approved_by": approved_by,
            "applied_at": datetime.utcnow().isoformat(),
        }

    async def evaluate_all_agents(
        self,
        org_id: str,
    ) -> List[ProgressionRecommendation]:
        """Evaluate all agents in an organization for progression."""
        agents = await self._trust_ops.list_agents(org_id=org_id)
        recommendations = []

        for agent in agents:
            recommendation = await self.evaluate_agent(agent.agent_id)
            if recommendation.direction != ProgressionDirection.MAINTAIN:
                recommendations.append(recommendation)

        return recommendations

    async def schedule_evaluation(
        self,
        agent_id: str,
        schedule: str = "daily",  # "hourly", "daily", "weekly"
    ) -> Dict[str, Any]:
        """Schedule periodic posture evaluation for an agent."""
        # Implementation: create scheduled job
        pass

    async def _collect_agent_metrics(self, agent_id: str) -> PostureMetrics:
        """Collect behavioral metrics for an agent."""
        # Get current posture
        chain = await self._trust_ops.get_trust_chain(agent_id)
        current_posture = chain.posture if chain else TrustPosture.SUPERVISED

        # Get execution metrics
        execution_stats = await self._metrics.get_execution_stats(
            agent_id=agent_id,
            time_range=timedelta(days=30),
        )

        # Get violation history
        violations = await self._metrics.get_violation_count(
            agent_id=agent_id,
            time_range=timedelta(days=30),
        )

        return PostureMetrics(
            agent_id=agent_id,
            current_posture=current_posture,
            days_at_current_posture=execution_stats.get("days_at_posture", 0),
            total_executions=execution_stats.get("total", 0),
            successful_executions=execution_stats.get("successful", 0),
            failed_executions=execution_stats.get("failed", 0),
            constraint_violations=violations.get("constraint", 0),
            verification_failures=violations.get("verification", 0),
            human_overrides=execution_stats.get("overrides", 0),
            average_response_time_ms=execution_stats.get("avg_response_ms", 0),
            compliance_score=self._calculate_compliance_score(execution_stats, violations),
        )

    def _evaluate_rules(
        self,
        metrics: PostureMetrics,
        rules: List[ProgressionRule],
    ) -> Optional[ProgressionRule]:
        """Evaluate rules against metrics, return first matching rule."""
        for rule in rules:
            if self._rule_matches(metrics, rule):
                return rule
        return None

    def _rule_matches(
        self,
        metrics: PostureMetrics,
        rule: ProgressionRule,
    ) -> bool:
        """Check if a rule matches current metrics."""
        conditions = rule.conditions

        # Check minimum days
        if metrics.days_at_current_posture < rule.min_days_required:
            return False

        # Check compliance score
        if "min_compliance_score" in conditions:
            if metrics.compliance_score < conditions["min_compliance_score"]:
                return False

        # Check success rate
        if "min_success_rate" in conditions:
            if metrics.total_executions > 0:
                success_rate = metrics.successful_executions / metrics.total_executions
                if success_rate < conditions["min_success_rate"]:
                    return False

        # Check maximum violations
        if "max_violations" in conditions:
            total_violations = metrics.constraint_violations + metrics.verification_failures
            if total_violations > conditions["max_violations"]:
                return False

        # Check minimum executions
        if "min_executions" in conditions:
            if metrics.total_executions < conditions["min_executions"]:
                return False

        return True

    def _create_recommendation(
        self,
        metrics: PostureMetrics,
        rule: ProgressionRule,
        direction: ProgressionDirection,
    ) -> ProgressionRecommendation:
        """Create a progression recommendation from matching rule."""
        return ProgressionRecommendation(
            agent_id=metrics.agent_id,
            current_posture=metrics.current_posture,
            recommended_posture=rule.to_posture,
            direction=direction,
            confidence_score=self._calculate_confidence(metrics, rule),
            triggering_rules=[rule.rule_id],
            metrics_summary=self._summarize_metrics(metrics),
            requires_approval=rule.requires_approval,
            auto_apply=not rule.requires_approval and direction == ProgressionDirection.DOWNGRADE,
        )

    def _calculate_confidence(
        self,
        metrics: PostureMetrics,
        rule: ProgressionRule,
    ) -> float:
        """Calculate confidence score for recommendation."""
        # Base confidence on how much metrics exceed thresholds
        return min(1.0, metrics.compliance_score * 1.2)

    def _calculate_compliance_score(
        self,
        execution_stats: Dict[str, Any],
        violations: Dict[str, int],
    ) -> float:
        """Calculate overall compliance score."""
        total = execution_stats.get("total", 0)
        if total == 0:
            return 0.5  # Neutral for new agents

        successful = execution_stats.get("successful", 0)
        total_violations = sum(violations.values())

        success_rate = successful / total
        violation_penalty = min(0.5, total_violations * 0.05)

        return max(0.0, success_rate - violation_penalty)

    def _summarize_metrics(self, metrics: PostureMetrics) -> Dict[str, Any]:
        """Summarize metrics for recommendation display."""
        return {
            "compliance_score": f"{metrics.compliance_score:.1%}",
            "days_at_posture": metrics.days_at_current_posture,
            "total_executions": metrics.total_executions,
            "success_rate": f"{metrics.successful_executions / max(1, metrics.total_executions):.1%}",
            "violations": metrics.constraint_violations + metrics.verification_failures,
        }
```

---

## Implementation Dependencies

### SDK Components Required

| Service | SDK Dependency | Status |
|---------|----------------|--------|
| Genesis Ceremony | `PseudoAgentFactory`, `TrustOperations.establish()` | Available |
| Cascade Revocation | `TrustOperations.revoke_by_human()`, `TrustOperations.revoke()` | Available |
| Trust Health | `TrustStore`, `AuditStore`, SLA metrics | Available |
| Constraint Compiler | `ConstraintEnvelope`, `Constraint`, `ConstraintValidator` | Available |
| Posture Progression | `TrustOperations.update_agent_posture()` | Needs Enhancement |

### Database Schema Additions

```sql
-- Genesis ceremony records
CREATE TABLE genesis_ceremonies (
    ceremony_id VARCHAR(64) PRIMARY KEY,
    human_id VARCHAR(128) NOT NULL,
    org_id VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    metadata JSONB,
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

-- Revocation history
CREATE TABLE revocation_history (
    revocation_id VARCHAR(64) PRIMARY KEY,
    root_entity_id VARCHAR(128) NOT NULL,
    root_entity_type VARCHAR(32) NOT NULL,
    reason TEXT NOT NULL,
    initiated_by VARCHAR(128) NOT NULL,
    initiated_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    total_revoked INTEGER,
    execution_time_ms FLOAT,
    strategy VARCHAR(32),
    failed_revocations JSONB
);

-- Posture progression history
CREATE TABLE posture_progressions (
    progression_id VARCHAR(64) PRIMARY KEY,
    agent_id VARCHAR(128) NOT NULL,
    old_posture VARCHAR(32) NOT NULL,
    new_posture VARCHAR(32) NOT NULL,
    direction VARCHAR(32) NOT NULL,
    triggering_rules JSONB,
    approved_by VARCHAR(128),
    applied_at TIMESTAMPTZ NOT NULL,
    metrics_snapshot JSONB
);

-- Constraint templates
CREATE TABLE constraint_templates (
    template_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(256) NOT NULL,
    template_type VARCHAR(64) NOT NULL,
    config JSONB NOT NULL,
    created_by VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    is_system BOOLEAN DEFAULT FALSE
);
```

---

## Success Criteria

| Service | Metric | Target |
|---------|--------|--------|
| Genesis Ceremony | Ceremony completion time | < 500ms |
| Genesis Ceremony | SSO integration success rate | > 99.9% |
| Cascade Revocation | 1000 agent revocation time | < 2 seconds |
| Cascade Revocation | Revocation completion rate | 100% |
| Trust Health | Dashboard refresh latency | < 200ms |
| Trust Health | Real-time metrics delay | < 1 second |
| Constraint Compiler | Compilation time | < 50ms |
| Constraint Compiler | Validation accuracy | 100% |
| Posture Progression | Evaluation time per agent | < 100ms |
| Posture Progression | False upgrade rate | < 0.1% |
