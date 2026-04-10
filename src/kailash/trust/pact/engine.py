# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""GovernanceEngine -- the single entry point for PACT governance decisions.

All governance state access and mutations go through this class. It composes
compilation, envelopes, clearance, access enforcement, and audit into a
thread-safe facade. Verticals (astra, arbor) use GovernanceEngine as their
primary interface.

Design principles:
1. Thread-safe: All public methods acquire self._lock.
2. Fail-closed: verify_action() catches ALL exceptions and returns BLOCKED.
3. Audit by default: Every mutation and decision emits EATP audit anchors
   when audit_chain is configured.
4. NaN-safe: Relies on M7 guards in envelopes.py and schema.py.
5. Frozen returns: All returned objects are frozen dataclasses.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from kailash.trust.pact.access import (
    AccessDecision,
    KnowledgeSharePolicy,
    PactBridge,
    can_access,
)
from kailash.trust.pact.addressing import Address
from kailash.trust.pact.audit import (
    PactAuditAction,
    TieredAuditDispatcher,
    create_pact_audit_details,
)
from kailash.trust.pact.clearance import (
    RoleClearance,
    VettingStatus,
    effective_clearance,
    validate_transition,
)
from kailash.trust.pact.compilation import (
    CompiledOrg,
    OrgNode,
    VacancyDesignation,
    compile_org,
)
from kailash.trust.pact.config import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    TrustPostureLevel,
    VerificationLevel,
)
from kailash.trust.pact.context import GovernanceContext
from kailash.trust.pact.envelopes import (
    EffectiveEnvelopeSnapshot,
    MonotonicTighteningError,
    RoleEnvelope,
    TaskEnvelope,
    check_passthrough_envelope,
    compute_effective_envelope,
    compute_effective_envelope_with_version,
    intersect_envelopes,
)
from kailash.trust.pact.exceptions import PactError
from kailash.trust.pact.knowledge import (
    FilterDecision,
    KnowledgeFilter,
    KnowledgeItem,
    KnowledgeQuery,
)
from kailash.trust.pact.observation import Observation, ObservationSink
from kailash.trust.pact.store import (
    AccessPolicyStore,
    ClearanceStore,
    EnvelopeStore,
    MemoryAccessPolicyStore,
    MemoryClearanceStore,
    MemoryEnvelopeStore,
    MemoryOrgStore,
    OrgStore,
)
from kailash.trust.pact.suspension import (
    PlanSuspension,
    ResumeCondition,
    SuspensionTrigger,
    resume_condition_for_trigger,
)
from kailash.trust.pact.verdict import GovernanceVerdict

logger = logging.getLogger(__name__)

__all__ = ["BridgeApproval", "GovernanceEngine"]

# ---------------------------------------------------------------------------
# Bridge approval -- LCA must approve cross-functional bridges (Section 4.4)
# ---------------------------------------------------------------------------

_MAX_BRIDGE_APPROVALS: int = 10_000
"""Maximum number of bridge approvals stored in memory (bounded collection)."""

_BRIDGE_APPROVAL_TTL: timedelta = timedelta(hours=24)
"""Default time-to-live for bridge approvals."""

_MAX_ENVELOPE_CACHE_ENTRIES: int = 10_000
"""Maximum number of cached effective envelope entries (bounded collection)."""


@dataclass
class _CachedEnvelope:
    """Internal cache entry for a computed effective envelope.

    Stores the computed ConstraintEnvelopeConfig along with monotonic
    creation time for optional TTL-based expiry.

    Not exported -- internal implementation detail.
    """

    envelope: ConstraintEnvelopeConfig | None
    created_at_mono: float  # time.monotonic() timestamp
    task_id: str | None  # None for role-only, set for task-scoped


@dataclass(frozen=True)
class BridgeApproval:
    """A pre-approval for a cross-functional bridge by the LCA of source and target.

    Per PACT Section 4.4, before creating a cross-functional bridge, the
    lowest common ancestor (LCA) of the two roles in the D/T/R tree must
    approve the bridge. This dataclass records that approval.

    frozen=True: prevents post-construction mutation (security invariant).

    Attributes:
        source_address: D/T/R address of one side of the bridge.
        target_address: D/T/R address of the other side of the bridge.
        approved_by: D/T/R address of the LCA that approved the bridge.
        approved_at: When the approval was granted.
        expires_at: When the approval expires (default: 24h after approved_at).
    """

    source_address: str
    target_address: str
    approved_by: str
    approved_at: datetime
    expires_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary.

        Returns:
            Dict with all fields. Datetimes are serialized as ISO 8601 strings.
        """
        return {
            "source_address": self.source_address,
            "target_address": self.target_address,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BridgeApproval:
        """Deserialize from a dictionary.

        Args:
            data: Dict with serialized BridgeApproval fields.

        Returns:
            A BridgeApproval instance.
        """
        return cls(
            source_address=data["source_address"],
            target_address=data["target_address"],
            approved_by=data["approved_by"],
            approved_at=datetime.fromisoformat(data["approved_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )


@dataclass(frozen=True)
class _VacancyCheckResult:
    """Internal result of vacancy check (Section 5.5). Not exported."""

    status: str  # "ok", "interim", "blocked"
    message: str | None = None
    interim_envelope: ConstraintEnvelopeConfig | None = None


class GovernanceEngine:
    """Single entry point for PACT governance decisions.

    All public methods are thread-safe via threading.Lock.
    All error paths are fail-closed (return BLOCKED, not exceptions).
    All mutations emit EATP audit anchors when audit_chain is configured.

    Args:
        org: Either an OrgDefinition (will be compiled) or a pre-compiled
            CompiledOrg. The engine detects the type and handles accordingly.
        envelope_store: Store for role and task envelopes. Defaults to
            MemoryEnvelopeStore if None.
        clearance_store: Store for knowledge clearance assignments. Defaults
            to MemoryClearanceStore if None.
        access_policy_store: Store for KSPs and bridges. Defaults to
            MemoryAccessPolicyStore if None.
        org_store: Store for compiled organizations. Defaults to
            MemoryOrgStore if None.
        audit_chain: Optional EATP audit chain for recording governance
            decisions. When None, no audit records are emitted.
    """

    def __init__(
        self,
        org: Any,  # OrgDefinition | CompiledOrg
        *,
        envelope_store: EnvelopeStore | None = None,
        clearance_store: ClearanceStore | None = None,
        access_policy_store: AccessPolicyStore | None = None,
        org_store: OrgStore | None = None,
        audit_chain: Any | None = None,  # AuditChain (lazy import to avoid cycles)
        store_backend: str = "memory",  # "memory" or "sqlite"
        store_url: str | None = None,  # Path for sqlite backend
        eatp_emitter: Any | None = None,  # PactEatpEmitter (Section 5.7)
        knowledge_filter: KnowledgeFilter | None = None,  # Pre-retrieval filter
        envelope_cache_ttl_seconds: float | None = None,  # N2: optional TTL
        audit_dispatcher: TieredAuditDispatcher | None = None,  # PACT-08 tiers
        observation_sink: ObservationSink | None = None,  # N5 monitoring events
        vacancy_deadline_hours: int = 24,  # Section 5.5 configurable deadline
        require_bilateral_consent: bool = False,  # Section 4.4 bilateral consent
    ) -> None:
        self._lock = threading.Lock()

        # N2 Effective Envelope Cache -- bounded dict keyed by
        # (role_address, task_id) -> _CachedEnvelope.
        # Invalidated via prefix-based cascade on mutations.
        self._envelope_cache: OrderedDict[tuple[str, str | None], _CachedEnvelope] = (
            OrderedDict()
        )
        self._envelope_cache_ttl: float | None = envelope_cache_ttl_seconds

        # Initialize stores -- use factory if store_backend specified,
        # otherwise use explicit stores or default to memory
        self._sqlite_audit_log: Any | None = (
            None  # SqliteAuditLog when using sqlite backend
        )

        if (
            store_backend == "sqlite"
            and store_url is not None
            and all(
                s is None
                for s in (
                    envelope_store,
                    clearance_store,
                    access_policy_store,
                    org_store,
                )
            )
        ):
            from kailash.trust.pact.stores.sqlite import (
                SqliteAccessPolicyStore,
                SqliteAuditLog,
                SqliteClearanceStore,
                SqliteEnvelopeStore,
                SqliteOrgStore,
            )

            self._envelope_store: EnvelopeStore = SqliteEnvelopeStore(store_url)
            self._clearance_store: ClearanceStore = SqliteClearanceStore(store_url)
            self._access_policy_store: AccessPolicyStore = SqliteAccessPolicyStore(
                store_url
            )
            self._org_store: OrgStore = SqliteOrgStore(store_url)
            self._sqlite_audit_log = SqliteAuditLog(store_url)
            logger.info("GovernanceEngine using SQLite stores at %s", store_url)
        elif store_backend == "sqlite" and store_url is None:
            raise ValueError("store_backend='sqlite' requires store_url parameter")
        elif store_backend not in ("memory", "sqlite"):
            raise ValueError(
                f"Unsupported store_backend '{store_backend}'. Use 'memory' or 'sqlite'."
            )
        else:
            self._envelope_store = (
                envelope_store if envelope_store is not None else MemoryEnvelopeStore()
            )
            self._clearance_store = (
                clearance_store
                if clearance_store is not None
                else MemoryClearanceStore()
            )
            self._access_policy_store = (
                access_policy_store
                if access_policy_store is not None
                else MemoryAccessPolicyStore()
            )
            self._org_store = org_store if org_store is not None else MemoryOrgStore()
        self._audit_chain = audit_chain

        # Tiered audit dispatcher -- gradient-aligned persistence (PACT-08)
        self._audit_dispatcher = audit_dispatcher

        # EATP record emitter -- optional synchronous emission (Section 5.7)
        self._eatp_emitter = eatp_emitter

        # Pre-retrieval knowledge filter -- evaluated before 5-step access check
        self._knowledge_filter: KnowledgeFilter | None = knowledge_filter

        # Observation sink -- optional structured monitoring events (N5)
        self._observation_sink = observation_sink

        # Vacancy deadline -- configurable (Section 5.5, default 24h)
        if vacancy_deadline_hours <= 0:
            raise ValueError(
                f"vacancy_deadline_hours must be > 0, got {vacancy_deadline_hours}"
            )
        self._vacancy_deadline = timedelta(hours=vacancy_deadline_hours)

        # Vacancy designations -- bounded in-memory store (Section 5.5)
        # Key: vacant_role_address -> VacancyDesignation
        self._vacancy_designations: dict[str, VacancyDesignation] = {}
        self._max_vacancy_designations: int = 10_000

        # Vacancy start times -- tracks when each vacancy began (Section 5.5)
        self._vacancy_start_times: dict[str, datetime] = {}

        # Bridge approvals -- bounded in-memory store (Section 4.4 LCA approval)
        # Key: "source_address|target_address" -> BridgeApproval
        self._bridge_approvals: OrderedDict[str, BridgeApproval] = OrderedDict()

        # Bridge consents -- bilateral consent for bridge creation (Section 4.4)
        self._bridge_consents: OrderedDict[tuple[str, str], datetime] = OrderedDict()
        self._require_bilateral_consent: bool = require_bilateral_consent

        # Compliance role -- alternative bridge approver (Section 4.4)
        self._compliance_role: str | None = None

        # Plan suspensions -- bounded in-memory store (N3 Plan Re-Entry)
        # Key: plan_id -> PlanSuspension
        self._suspensions: dict[str, PlanSuspension] = {}
        self._max_suspensions: int = 10_000

        # Compile if OrgDefinition, or use directly if CompiledOrg
        if isinstance(org, CompiledOrg):
            self._compiled_org = org
            self._org_name: str = org.org_id
        else:
            # Assume OrgDefinition -- compile it and preserve the human-readable name
            self._compiled_org = compile_org(org)
            self._org_name = getattr(org, "name", org.org_id) or org.org_id

        # Save compiled org in the org store
        self._org_store.save_org(self._compiled_org)

        # Initialize vacancy start times for roles that are vacant at compilation
        init_time = datetime.now(UTC)
        for addr, node in self._compiled_org.nodes.items():
            if node.is_vacant:
                self._vacancy_start_times[addr] = init_time

        # Emit GenesisRecord (PACT Section 5.7 normative mapping)
        if self._eatp_emitter is not None:
            try:
                from kailash.trust.chain import AuthorityType, GenesisRecord

                genesis = GenesisRecord(
                    id=f"pact-genesis-{self._compiled_org.org_id}",
                    agent_id=f"pact-engine-{self._compiled_org.org_id}",
                    authority_id=self._compiled_org.org_id,
                    authority_type=AuthorityType.ORGANIZATION,
                    created_at=datetime.now(UTC),
                    signature="UNSIGNED",
                )
                self._eatp_emitter.emit_genesis(genesis)
            except Exception:
                logger.exception(
                    "Failed to emit GenesisRecord for org '%s'",
                    self._compiled_org.org_id,
                )

        logger.info(
            "GovernanceEngine initialized for org '%s' with %d nodes",
            self._compiled_org.org_id,
            len(self._compiled_org.nodes),
        )

    # -------------------------------------------------------------------
    # Decision API
    # -------------------------------------------------------------------

    def check_access(
        self,
        role_address: str,
        knowledge_item: KnowledgeItem,
        posture: TrustPostureLevel,
        *,
        query: KnowledgeQuery | None = None,
    ) -> AccessDecision:
        """Check if a role can access a knowledge item. Thread-safe, fail-closed.

        If a ``KnowledgeFilter`` is configured, it runs as a pre-step BEFORE
        the 5-step access enforcement algorithm. The filter can deny the
        request outright (skip data retrieval entirely) or narrow the query
        scope. Filter errors are fail-closed to DENY.

        Args:
            role_address: The D/T/R address of the requesting role.
            knowledge_item: The knowledge item being accessed.
            posture: The current trust posture level of the role.
            query: Optional pre-retrieval query descriptor. When a filter
                is configured, this describes the scope of the data request.
                If None and a filter is configured, a default query is built
                from the knowledge_item.

        Returns:
            An AccessDecision indicating allow/deny with reason.
        """
        with self._lock:
            try:
                # --- Pre-step: KnowledgeFilter (before 5-step algorithm) ---
                if self._knowledge_filter is not None:
                    filter_decision = self._run_knowledge_filter_locked(
                        role_address, knowledge_item, query
                    )
                    if not filter_decision.allowed:
                        logger.info(
                            "Access denied (pre-filter): role_address=%s, "
                            "item_id=%s, reason=%s",
                            role_address,
                            knowledge_item.item_id,
                            filter_decision.reason,
                        )
                        self._emit_audit_unlocked(
                            "knowledge_filter_denied",
                            {
                                "role_address": role_address,
                                "item_id": knowledge_item.item_id,
                                "reason": filter_decision.reason,
                                "audit_anchor_id": filter_decision.audit_anchor_id,
                                "barrier_enforced": True,
                            },
                        )
                        return AccessDecision(
                            allowed=False,
                            reason=(
                                f"Pre-retrieval filter denied: "
                                f"{filter_decision.reason}"
                            ),
                            step_failed=0,
                            audit_details={
                                "role_address": role_address,
                                "item_id": knowledge_item.item_id,
                                "filter_decision": filter_decision.to_dict(),
                                "step": "pre_filter",
                            },
                        )
                    # Filter allowed (possibly with narrowed scope) -- log and proceed
                    if filter_decision.filtered_scope is not None:
                        logger.debug(
                            "Knowledge filter narrowed scope for role_address=%s",
                            role_address,
                        )
                    self._emit_audit_unlocked(
                        "knowledge_filter_allowed",
                        {
                            "role_address": role_address,
                            "item_id": knowledge_item.item_id,
                            "audit_anchor_id": filter_decision.audit_anchor_id,
                            "narrowed": filter_decision.filtered_scope is not None,
                        },
                    )

                # --- 5-step access enforcement algorithm ---
                # Gather current state from stores
                clearances = self._gather_clearances()
                ksps = self._access_policy_store.list_ksps()
                bridges = self._access_policy_store.list_bridges()

                decision = can_access(
                    role_address=role_address,
                    knowledge_item=knowledge_item,
                    posture=posture,
                    compiled_org=self._compiled_org,
                    clearances=clearances,
                    ksps=ksps,
                    bridges=bridges,
                )

                if not decision.allowed:
                    self._emit_audit_unlocked(
                        "access_denied",
                        {
                            "role_address": role_address,
                            "item_id": knowledge_item.item_id,
                            "reason": decision.reason,
                            "step_failed": decision.step_failed,
                            "barrier_enforced": True,
                        },
                    )

                return decision

            except Exception:
                logger.exception(
                    "check_access failed for role_address=%s, item_id=%s -- fail-closed to DENY",
                    role_address,
                    knowledge_item.item_id,
                )
                return AccessDecision(
                    allowed=False,
                    reason="Internal error during access check -- fail-closed to DENY",
                    step_failed=0,
                    audit_details={
                        "role_address": role_address,
                        "item_id": knowledge_item.item_id,
                        "error": "internal_error",
                    },
                )

    def _run_knowledge_filter_locked(
        self,
        role_address: str,
        knowledge_item: KnowledgeItem,
        query: KnowledgeQuery | None,
    ) -> FilterDecision:
        """Run the pre-retrieval knowledge filter. Caller must hold self._lock.

        Fail-closed: if the filter raises an exception, returns a DENY decision.
        This ensures a buggy filter implementation cannot accidentally grant access.

        Args:
            role_address: The D/T/R address of the requesting role.
            knowledge_item: The knowledge item being accessed.
            query: Optional query descriptor. If None, a default query is
                built from the knowledge_item.

        Returns:
            A FilterDecision from the configured filter, or a DENY decision
            if the filter raised an exception.
        """
        assert self._knowledge_filter is not None  # noqa: S101 -- caller must check

        # Build a default query from the knowledge item if none was provided
        if query is None:
            query = KnowledgeQuery(
                item_ids=frozenset({knowledge_item.item_id}),
                classifications=frozenset({knowledge_item.classification.value}),
                owning_units=frozenset({knowledge_item.owning_unit_address}),
                description=f"Access check for item '{knowledge_item.item_id}'",
            )

        # Compute the effective envelope snapshot for the filter
        snapshot = self._compute_envelope_with_version_locked(role_address)

        try:
            decision = self._knowledge_filter.filter_before_retrieval(
                role_address, query, snapshot
            )
        except Exception:
            logger.exception(
                "KnowledgeFilter.filter_before_retrieval raised for "
                "role_address=%s -- fail-closed to DENY",
                role_address,
            )
            return FilterDecision(
                allowed=False,
                reason="Knowledge filter raised an exception -- fail-closed to DENY",
            )

        # Validate the decision type (defensive -- a bad implementation might
        # return something other than FilterDecision)
        if not isinstance(decision, FilterDecision):
            logger.error(
                "KnowledgeFilter returned non-FilterDecision type %s for "
                "role_address=%s -- fail-closed to DENY",
                type(decision).__name__,
                role_address,
            )
            return FilterDecision(
                allowed=False,
                reason=(
                    "Knowledge filter returned invalid type "
                    f"'{type(decision).__name__}' -- fail-closed to DENY"
                ),
            )

        return decision

    def verify_action(
        self,
        role_address: str,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> GovernanceVerdict:
        """The primary decision API. Combines vacancy + envelope + gradient + access.

        Fail-closed: any error returns BLOCKED verdict.

        Logic:
        0. Vacancy check (Section 5.5): if role or ancestor is vacant without
           a valid acting occupant designation, BLOCK immediately.
        1. Compute effective envelope for role_address.
        2. If envelope exists, evaluate action against envelope dimensions.
        3. Classify result into gradient zones.
        4. If context has "resource", run check_access for knowledge clearance.
        5. Combine envelope verdict + access verdict (most restrictive wins).
        6. Emit audit anchor with full details.
        7. Return GovernanceVerdict.

        Args:
            role_address: The D/T/R address of the role requesting the action.
            action: The action being performed (e.g., "read", "write", "deploy").
            context: Optional context dict with additional info:
                - "cost": float -- the cost of the action for financial checks
                - "resource": KnowledgeItem -- for knowledge access checks

        Returns:
            A GovernanceVerdict with level, reason, and audit details.
        """
        ctx = context or {}
        now = datetime.now(UTC)

        try:
            with self._lock:
                return self._verify_action_locked(role_address, action, ctx, now)
        except Exception:
            logger.exception(
                "verify_action failed for role_address=%s, action=%s -- fail-closed to BLOCKED",
                role_address,
                action,
            )
            verdict = GovernanceVerdict(
                level="blocked",
                reason="Internal error during action verification -- fail-closed to BLOCKED",
                role_address=role_address,
                action=action,
                effective_envelope_snapshot=None,
                audit_details={
                    "error": "internal_error",
                    "role_address": role_address,
                    "action": action,
                },
                access_decision=None,
                timestamp=now,
            )
            # Emit audit even on error (outside lock since audit chain has its own lock)
            self._emit_audit(
                "verify_action",
                {
                    "role_address": role_address,
                    "action": action,
                    "level": "blocked",
                    "error": "internal_error",
                },
            )
            return verdict

    def _verify_action_locked(
        self,
        role_address: str,
        action: str,
        ctx: dict[str, Any],
        now: datetime,
    ) -> GovernanceVerdict:
        """Internal verify_action implementation. Caller must hold self._lock.

        Uses versioned envelope computation for TOCTOU defense. The
        envelope_version hash is included in the GovernanceVerdict so
        callers can detect stale snapshots.

        Returns:
            A GovernanceVerdict with the decision.
        """
        # Step 0: Vacancy check (PACT Section 5.5) -- BEFORE envelope checks.
        # If the role or any ancestor is vacant without a valid acting occupant
        # designation, all actions are blocked (auto-suspended).
        vacancy_result = self._check_vacancy(role_address)
        if vacancy_result.status == "blocked":
            self._emit_audit_unlocked(
                PactAuditAction.VACANCY_SUSPENDED.value,
                {
                    "role_address": role_address,
                    "action": action,
                    "level": "blocked",
                    "reason": vacancy_result.message,
                },
            )
            return GovernanceVerdict(
                level="blocked",
                reason=vacancy_result.message or "Vacancy enforcement -- blocked",
                role_address=role_address,
                action=action,
                effective_envelope_snapshot=None,
                audit_details={
                    "role_address": role_address,
                    "action": action,
                    "level": "blocked",
                    "vacancy_suspended": True,
                },
                access_decision=None,
                timestamp=now,
            )

        # Step 0.5: Plan suspension check (N3 Plan Re-Entry Guarantee).
        # If the context carries a plan_id and that plan is suspended,
        # block the action with a reference to the suspension record.
        plan_id = ctx.get("plan_id")
        if plan_id and plan_id in self._suspensions:
            suspension = self._suspensions[plan_id]
            if not suspension.all_conditions_met():
                self._emit_audit_unlocked(
                    "plan_suspended",
                    {
                        "role_address": role_address,
                        "action": action,
                        "plan_id": plan_id,
                        "suspension_id": suspension.suspension_id,
                        "trigger": suspension.trigger.value,
                        "level": "blocked",
                    },
                )
                return GovernanceVerdict(
                    level="blocked",
                    reason=(
                        f"Plan '{plan_id}' is suspended "
                        f"(trigger: {suspension.trigger.value}). "
                        f"Resume conditions not yet met."
                    ),
                    role_address=role_address,
                    action=action,
                    effective_envelope_snapshot=None,
                    audit_details={
                        "role_address": role_address,
                        "action": action,
                        "plan_id": plan_id,
                        "suspension_id": suspension.suspension_id,
                        "trigger": suspension.trigger.value,
                        "level": "blocked",
                        "plan_suspended": True,
                    },
                    access_decision=None,
                    timestamp=now,
                )

        # Step 1: Compute effective envelope with version hash (TOCTOU defense)
        task_id = ctx.get("task_id")
        snapshot = self._compute_envelope_with_version_locked(
            role_address, task_id=task_id
        )
        effective = snapshot.envelope
        envelope_version = snapshot.version_hash

        # If vacancy check returned "interim", intersect with interim envelope
        if (
            vacancy_result.status == "interim"
            and vacancy_result.interim_envelope is not None
        ):
            if effective is not None:
                effective = intersect_envelopes(
                    effective, vacancy_result.interim_envelope
                )
            else:
                effective = vacancy_result.interim_envelope

        # Step 2+3: Evaluate action against envelope
        level = "auto_approved"
        reason = "No envelope constraints -- action permitted"
        envelope_snapshot: dict[str, Any] | None = None

        if effective is not None:
            envelope_snapshot = effective.model_dump(mode="json")
            level, reason = self._evaluate_against_envelope(effective, action, ctx)

        # Multi-level VERIFY: walk accountability chain and check each ancestor's
        # effective envelope. Most restrictive verdict wins. This prevents a role
        # from executing an action that is allowed at the leaf but blocked by
        # an ancestor's envelope.
        if level in ("auto_approved", "flagged"):
            ancestor_level, ancestor_reason = self._multi_level_verify(
                role_address, action, ctx
            )
            if ancestor_level is not None:
                # Escalate to more restrictive level
                level_order = {
                    "auto_approved": 0,
                    "flagged": 1,
                    "held": 2,
                    "blocked": 3,
                }
                if level_order.get(ancestor_level, 0) > level_order.get(level, 0):
                    level = ancestor_level
                    reason = ancestor_reason

        # Step 4: Knowledge access check if resource is provided
        access_decision: AccessDecision | None = None
        if "resource" in ctx and isinstance(ctx["resource"], KnowledgeItem):
            posture = ctx.get("posture", TrustPostureLevel.SUPERVISED)
            clearances = self._gather_clearances()
            ksps = self._access_policy_store.list_ksps()
            bridges = self._access_policy_store.list_bridges()

            access_decision = can_access(
                role_address=role_address,
                knowledge_item=ctx["resource"],
                posture=posture,
                compiled_org=self._compiled_org,
                clearances=clearances,
                ksps=ksps,
                bridges=bridges,
            )

            # Step 5: Most restrictive wins
            if not access_decision.allowed:
                level = "blocked"
                reason = f"Knowledge access denied: {access_decision.reason}"

        # Build audit details with envelope version (TOCTOU defense)
        audit_details: dict[str, Any] = {
            "role_address": role_address,
            "action": action,
            "level": level,
            "has_envelope": effective is not None,
            "envelope_version": envelope_version,
        }
        if effective is not None:
            audit_details["effective_envelope_snapshot"] = {
                "financial_max_spend": (
                    effective.financial.max_spend_usd if effective.financial else None
                ),
                "confidentiality": effective.confidentiality_clearance.value,
                "allowed_actions_count": (
                    len(effective.operational.allowed_actions)
                    if effective.operational is not None
                    else None
                ),
            }

        verdict = GovernanceVerdict(
            level=level,
            reason=reason,
            role_address=role_address,
            action=action,
            effective_envelope_snapshot=envelope_snapshot,
            audit_details=audit_details,
            access_decision=access_decision,
            timestamp=now,
            envelope_version=envelope_version,
        )

        # Step 6: Emit audit anchor (release lock before audit to avoid deadlock)
        # NOTE: We emit after returning from locked section in the caller.
        # But since we need the verdict first, we emit here inside the lock.
        # The audit chain has its own internal lock, so this is safe.
        self._emit_audit_unlocked(
            "verify_action",
            {
                "role_address": role_address,
                "action": action,
                "level": level,
                "reason": reason,
            },
        )

        # Emit monitoring observation (N5 ObservationSink)
        obs_level = "info"
        if level in ("flagged", "held"):
            obs_level = "warn"
        elif level == "blocked":
            obs_level = "critical"
        self._emit_observation(
            event_type="verdict",
            role_address=role_address,
            level=obs_level,
            payload={
                "action": action,
                "verdict_level": level,
                "reason": reason,
                "has_envelope": effective is not None,
                "envelope_version": envelope_version,
            },
        )

        return verdict

    def _evaluate_against_envelope(
        self,
        envelope: ConstraintEnvelopeConfig,
        action: str,
        ctx: dict[str, Any],
    ) -> tuple[str, str]:
        """Evaluate an action against an effective envelope.

        Returns:
            A tuple of (level, reason).
        """
        # --- Operational: check allowed/blocked actions ---
        # None means unconstrained (maximally permissive) -- skip entirely (GH #390).
        if envelope.operational is not None:
            blocked_actions = set(envelope.operational.blocked_actions)
            allowed_actions = set(envelope.operational.allowed_actions)

            if action in blocked_actions:
                return (
                    "blocked",
                    f"Action '{action}' is explicitly blocked by operational constraints",
                )

            # If allowed_actions is explicitly defined (even if empty), the action
            # must be in the list. Empty allowed_actions + envelope exists = nothing
            # allowed. When no envelope exists, the caller gets None (maximally
            # permissive) and _evaluate_against_envelope is never called.
            if action not in allowed_actions:
                return (
                    "blocked",
                    f"Action '{action}' is not in the allowed actions list: "
                    f"{sorted(allowed_actions)}",
                )

            # --- Operational: check rate limits (max_actions_per_day/hour) ---
            daily_calls = ctx.get("daily_calls")
            if (
                daily_calls is not None
                and envelope.operational.max_actions_per_day is not None
            ):
                daily_calls_int = int(daily_calls)
                if daily_calls_int >= envelope.operational.max_actions_per_day:
                    return (
                        "blocked",
                        f"Daily rate limit exceeded: {daily_calls_int} actions "
                        f"(limit: {envelope.operational.max_actions_per_day}/day)",
                    )
            hourly_calls = ctx.get("hourly_calls")
            if (
                hourly_calls is not None
                and envelope.operational.max_actions_per_hour is not None
            ):
                hourly_calls_int = int(hourly_calls)
                if hourly_calls_int >= envelope.operational.max_actions_per_hour:
                    return (
                        "blocked",
                        f"Hourly rate limit exceeded: {hourly_calls_int} actions "
                        f"(limit: {envelope.operational.max_actions_per_hour}/hour)",
                    )

        # --- Financial: check cost against max_spend_usd ---
        cost = ctx.get("cost")
        if cost is not None and envelope.financial is not None:
            # Validate cost is finite (NaN-safe)
            cost_float = float(cost)
            if not math.isfinite(cost_float):
                return (
                    "blocked",
                    f"Action cost is not finite ({cost_float!r}) -- fail-closed to BLOCKED",
                )
            if cost_float < 0:
                return (
                    "blocked",
                    f"Action cost is negative ({cost_float}) -- fail-closed to BLOCKED",
                )

            max_spend = envelope.financial.max_spend_usd
            if cost_float > max_spend:
                return (
                    "blocked",
                    f"Action cost (${cost_float:.2f}) exceeds financial limit "
                    f"(${max_spend:.2f})",
                )

            # Check flagged threshold (requires_approval_above_usd)
            approval_threshold = envelope.financial.requires_approval_above_usd
            if approval_threshold is not None and cost_float > approval_threshold:
                return (
                    "held",
                    f"Action cost (${cost_float:.2f}) exceeds approval threshold "
                    f"(${approval_threshold:.2f}) -- held for human approval",
                )

            # Check near-boundary flagging (within 20% of max_spend)
            if max_spend > 0 and cost_float > max_spend * 0.8:
                return (
                    "flagged",
                    f"Action cost (${cost_float:.2f}) is within 20% of financial "
                    f"limit (${max_spend:.2f})",
                )

        # --- Temporal: check active hours and blackout periods ---
        if envelope.temporal is not None:
            from datetime import datetime as _dt
            from datetime import timezone as _tz

            _tz_name = envelope.temporal.timezone or "UTC"
            try:
                import zoneinfo as _zi

                _tzinfo = _zi.ZoneInfo(_tz_name)
            except Exception:
                _tzinfo = _tz.utc
            _now = _dt.now(_tzinfo)
            _current_time = _now.strftime("%H:%M")

            # Check blackout periods (supports overnight ranges like 22:00-06:00)
            import re as _re

            _BP_RE = _re.compile(r"^(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})$")
            for bp in envelope.temporal.blackout_periods or []:
                if isinstance(bp, str):
                    _m = _BP_RE.match(bp)
                    if _m:
                        _bp_start, _bp_end = _m.group(1), _m.group(2)
                        if _bp_start <= _bp_end:
                            in_blackout = _bp_start <= _current_time <= _bp_end
                        else:
                            in_blackout = (
                                _current_time >= _bp_start or _current_time <= _bp_end
                            )
                        if in_blackout:
                            return (
                                "blocked",
                                f"Action blocked during blackout period ({bp})",
                            )

            # Check active hours window
            _start = envelope.temporal.active_hours_start
            _end = envelope.temporal.active_hours_end
            if _start is not None and _end is not None:
                if _start <= _end:
                    # Normal range (e.g., 09:00-17:00)
                    if not (_start <= _current_time <= _end):
                        return (
                            "blocked",
                            f"Action outside active hours ({_start}-{_end}, current: {_current_time})",
                        )
                else:
                    # Overnight range (e.g., 22:00-06:00)
                    if _end < _current_time < _start:
                        return (
                            "blocked",
                            f"Action outside active hours ({_start}-{_end}, current: {_current_time})",
                        )

        # --- Data Access: check read/write paths ---
        if envelope.data_access is not None:
            resource_path = ctx.get("resource_path")
            access_type = ctx.get("access_type")  # "read" or "write"
            if resource_path is not None and access_type is not None:
                from kailash.trust.pathutils import normalize_resource_path

                _rp = normalize_resource_path(str(resource_path))
                # Reject path traversal attempts
                if ".." in _rp.split("/"):
                    return (
                        "blocked",
                        f"Path traversal detected in resource_path: {_rp!r}",
                    )

                # Check blocked data types first
                _data_type = ctx.get("data_type")
                if _data_type and envelope.data_access.blocked_data_types:
                    if str(_data_type) in envelope.data_access.blocked_data_types:
                        return (
                            "blocked",
                            f"Data type '{_data_type}' is blocked by data access constraint",
                        )

                # Check allowed read paths
                if access_type == "read" and envelope.data_access.read_paths:
                    if not any(
                        _rp == p or _rp.startswith(p + "/")
                        for p in envelope.data_access.read_paths
                    ):
                        return (
                            "blocked",
                            f"Read access to '{_rp}' not in allowed read paths",
                        )
                # Check allowed write paths
                elif access_type == "write" and envelope.data_access.write_paths:
                    if not any(
                        _rp == p or _rp.startswith(p + "/")
                        for p in envelope.data_access.write_paths
                    ):
                        return (
                            "blocked",
                            f"Write access to '{_rp}' not in allowed write paths",
                        )

        # --- Communication: check channel and external constraints ---
        if envelope.communication is not None:
            channel = ctx.get("channel")
            is_external = ctx.get("is_external")

            # internal_only: block only when is_external is explicitly True.
            # Unspecified (None) defaults to internal — callers that don't
            # declare an action as external should not be blocked.
            if envelope.communication.internal_only and is_external is True:
                return (
                    "blocked",
                    "External communication blocked — agent is internal-only",
                )

            # external_requires_approval: HELD for external actions
            if (
                envelope.communication.external_requires_approval
                and is_external
                and not envelope.communication.internal_only
            ):
                return (
                    "held",
                    "External communication requires human approval",
                )

            # Check allowed channels
            allowed_channels = envelope.communication.allowed_channels
            if channel is not None and allowed_channels:
                if str(channel) not in allowed_channels:
                    return (
                        "blocked",
                        f"Channel '{channel}' not in allowed channels: {sorted(allowed_channels)}",
                    )

        # --- All checks passed ---
        return (
            "auto_approved",
            f"Action '{action}' is within all constraint dimensions",
        )

    def compute_envelope(
        self,
        role_address: str,
        task_id: str | None = None,
    ) -> ConstraintEnvelopeConfig | None:
        """Compute effective envelope for a role. Thread-safe.

        Args:
            role_address: The D/T/R address of the role.
            task_id: Optional task ID for task-specific envelope narrowing.

        Returns:
            The effective ConstraintEnvelopeConfig, or None if no envelopes
            are configured for this role or its ancestors.
        """
        with self._lock:
            return self._compute_envelope_locked(role_address, task_id=task_id)

    def _compute_envelope_locked(
        self,
        role_address: str,
        task_id: str | None = None,
    ) -> ConstraintEnvelopeConfig | None:
        """Internal envelope computation with caching. Caller must hold self._lock.

        N2 cache: checks the envelope cache first. On miss, computes from
        stores and caches the result. TTL-based expiry is checked on read
        when envelope_cache_ttl_seconds is configured.
        """
        cache_key = (role_address, task_id)

        # Check cache
        cached = self._envelope_cache.get(cache_key)
        if cached is not None:
            # TTL check if configured
            if self._envelope_cache_ttl is not None:
                age = time.monotonic() - cached.created_at_mono
                if age > self._envelope_cache_ttl:
                    # Expired -- evict and recompute
                    del self._envelope_cache[cache_key]
                else:
                    return cached.envelope
            else:
                return cached.envelope

        # Cache miss -- compute from stores
        ancestor_envelopes = self._envelope_store.get_ancestor_envelopes(role_address)

        task_envelope: TaskEnvelope | None = None
        if task_id is not None:
            task_envelope = self._envelope_store.get_active_task_envelope(
                role_address, task_id
            )

        result = compute_effective_envelope(
            role_address=role_address,
            role_envelopes=ancestor_envelopes,
            task_envelope=task_envelope,
        )

        # Store in cache (bounded)
        self._envelope_cache[cache_key] = _CachedEnvelope(
            envelope=result,
            created_at_mono=time.monotonic(),
            task_id=task_id,
        )
        # Evict oldest entries when at capacity
        while len(self._envelope_cache) > _MAX_ENVELOPE_CACHE_ENTRIES:
            self._envelope_cache.popitem(last=False)

        return result

    def _compute_envelope_with_version_locked(
        self,
        role_address: str,
        task_id: str | None = None,
    ) -> EffectiveEnvelopeSnapshot:
        """Internal versioned envelope computation. Caller must hold self._lock.

        Returns an EffectiveEnvelopeSnapshot with version_hash for TOCTOU defense.
        """
        ancestor_envelopes = self._envelope_store.get_ancestor_envelopes(role_address)

        task_envelope: TaskEnvelope | None = None
        if task_id is not None:
            task_envelope = self._envelope_store.get_active_task_envelope(
                role_address, task_id
            )

        return compute_effective_envelope_with_version(
            role_address=role_address,
            role_envelopes=ancestor_envelopes,
            task_envelope=task_envelope,
        )

    # -------------------------------------------------------------------
    # N2 Envelope Cache Invalidation
    # -------------------------------------------------------------------

    def _cascade_invalidate(self, address: str) -> int:
        """Evict cached envelopes for address and all descendant addresses.

        Prefix-based eviction: when address X changes, every cache entry
        whose role_address == X or starts with X followed by '-' is evicted.
        This ensures that parent envelope mutations propagate to all
        descendants that inherit from the parent.

        Caller must hold self._lock.

        Args:
            address: The D/T/R address whose envelope (and descendants') should
                be evicted.

        Returns:
            The number of cache entries evicted.
        """
        if not self._envelope_cache:
            return 0

        keys_to_evict: list[tuple[str, str | None]] = []
        prefix = address + "-"
        for cache_key in self._envelope_cache:
            role_addr = cache_key[0]
            if role_addr == address or role_addr.startswith(prefix):
                keys_to_evict.append(cache_key)

        for key in keys_to_evict:
            del self._envelope_cache[key]

        if keys_to_evict:
            logger.debug(
                "envelope_cache.cascade_invalidate: evicted %d entries for address '%s'",
                len(keys_to_evict),
                address,
            )

        return len(keys_to_evict)

    def _invalidate_bridge_endpoints(
        self, source_address: str, target_address: str
    ) -> int:
        """Evict cached envelopes for both bridge endpoints and their descendants.

        Bridge approval or revocation can affect access decisions that depend
        on envelope context, so both endpoints must be invalidated.

        Caller must hold self._lock.

        Args:
            source_address: D/T/R address of one side of the bridge.
            target_address: D/T/R address of the other side of the bridge.

        Returns:
            Total number of cache entries evicted.
        """
        count = self._cascade_invalidate(source_address)
        count += self._cascade_invalidate(target_address)
        return count

    @property
    def _envelope_cache_size(self) -> int:
        """Current number of entries in the envelope cache. Thread-safe."""
        with self._lock:
            return len(self._envelope_cache)

    # -------------------------------------------------------------------
    # Plan Suspension / Resumption (N3 Plan Re-Entry Guarantee)
    # -------------------------------------------------------------------

    def suspend_plan(
        self,
        role_address: str,
        plan_id: str,
        trigger: SuspensionTrigger,
        snapshot: dict[str, Any] | None = None,
    ) -> PlanSuspension:
        """Suspend a plan with explicit resume conditions.

        Creates a PlanSuspension record that blocks all ``verify_action()``
        calls carrying this plan_id until the resume conditions are met
        and ``resume_plan()`` is called.

        Thread-safe, fail-closed. Bounded to ``_max_suspensions`` entries.

        Args:
            role_address: The D/T/R address of the role whose plan is suspended.
            plan_id: Unique identifier for the plan being suspended.
            trigger: Why the plan is being suspended.
            snapshot: Optional frozen state at suspension time.

        Returns:
            The created PlanSuspension record.

        Raises:
            PactError: If the suspension store is full.
        """
        with self._lock:
            if len(self._suspensions) >= self._max_suspensions:
                # Evict oldest to stay within bounds
                oldest_key = next(iter(self._suspensions))
                del self._suspensions[oldest_key]
                logger.warning(
                    "Plan suspension store at capacity (%d), evicted oldest: %s",
                    self._max_suspensions,
                    oldest_key,
                )

            condition = resume_condition_for_trigger(trigger)
            now = datetime.now(UTC)
            suspension = PlanSuspension(
                plan_id=plan_id,
                trigger=trigger,
                suspended_at=now.isoformat(),
                resume_conditions=(condition,),
                snapshot=snapshot or {},
                role_address=role_address,
            )
            self._suspensions[plan_id] = suspension

            self._emit_audit_unlocked(
                "plan_suspended",
                {
                    "role_address": role_address,
                    "plan_id": plan_id,
                    "trigger": trigger.value,
                    "suspension_id": suspension.suspension_id,
                    "suspended_at": suspension.suspended_at,
                },
            )

            logger.info(
                "Plan '%s' suspended for role '%s' (trigger: %s)",
                plan_id,
                role_address,
                trigger.value,
            )

            return suspension

    def resume_plan(self, plan_id: str) -> GovernanceVerdict:
        """Attempt to resume a suspended plan.

        Checks all resume conditions. If ALL are satisfied, removes the
        suspension and returns an auto_approved verdict. Otherwise returns
        a blocked verdict listing which conditions are still unmet.

        Thread-safe, fail-closed.

        Args:
            plan_id: The plan to resume.

        Returns:
            GovernanceVerdict indicating whether resume succeeded.
        """
        now = datetime.now(UTC)
        try:
            with self._lock:
                suspension = self._suspensions.get(plan_id)
                if suspension is None:
                    return GovernanceVerdict(
                        level="blocked",
                        reason=f"No active suspension found for plan '{plan_id}'",
                        role_address="",
                        action="resume_plan",
                        timestamp=now,
                    )

                if not suspension.all_conditions_met():
                    unmet = [
                        c.condition_type
                        for c in suspension.resume_conditions
                        if not c.satisfied
                    ]
                    return GovernanceVerdict(
                        level="blocked",
                        reason=(
                            f"Cannot resume plan '{plan_id}': "
                            f"unmet conditions: {unmet}"
                        ),
                        role_address=suspension.role_address,
                        action="resume_plan",
                        audit_details={
                            "plan_id": plan_id,
                            "unmet_conditions": unmet,
                            "trigger": suspension.trigger.value,
                        },
                        timestamp=now,
                    )

                # All conditions met -- remove suspension
                del self._suspensions[plan_id]

                self._emit_audit_unlocked(
                    "plan_resumed",
                    {
                        "role_address": suspension.role_address,
                        "plan_id": plan_id,
                        "trigger": suspension.trigger.value,
                        "suspension_id": suspension.suspension_id,
                    },
                )

                logger.info(
                    "Plan '%s' resumed for role '%s'",
                    plan_id,
                    suspension.role_address,
                )

                return GovernanceVerdict(
                    level="auto_approved",
                    reason=f"Plan '{plan_id}' resumed -- all conditions met",
                    role_address=suspension.role_address,
                    action="resume_plan",
                    audit_details={
                        "plan_id": plan_id,
                        "trigger": suspension.trigger.value,
                    },
                    timestamp=now,
                )
        except Exception:
            logger.exception(
                "resume_plan failed for plan_id=%s -- fail-closed to BLOCKED",
                plan_id,
            )
            return GovernanceVerdict(
                level="blocked",
                reason="Internal error during plan resume -- fail-closed to BLOCKED",
                role_address="",
                action="resume_plan",
                timestamp=now,
            )

    def update_resume_condition(
        self,
        plan_id: str,
        condition_type: str,
        satisfied: bool,
        details: str = "",
    ) -> PlanSuspension | None:
        """Update the satisfaction status of a resume condition.

        Since PlanSuspension and ResumeCondition are frozen, this creates
        a new PlanSuspension with updated conditions and replaces the old one.

        Thread-safe.

        Args:
            plan_id: The suspended plan to update.
            condition_type: Which condition to update (e.g., "budget_replenished").
            satisfied: Whether the condition is now met.
            details: Optional updated details string.

        Returns:
            The updated PlanSuspension, or None if the plan_id is not found.
        """
        with self._lock:
            suspension = self._suspensions.get(plan_id)
            if suspension is None:
                return None

            # Build new conditions tuple with the updated entry
            new_conditions: list[ResumeCondition] = []
            for cond in suspension.resume_conditions:
                if cond.condition_type == condition_type:
                    new_conditions.append(
                        ResumeCondition(
                            condition_type=cond.condition_type,
                            satisfied=satisfied,
                            details=details or cond.details,
                        )
                    )
                else:
                    new_conditions.append(cond)

            # Create a new frozen suspension with updated conditions
            updated = PlanSuspension(
                plan_id=suspension.plan_id,
                trigger=suspension.trigger,
                suspended_at=suspension.suspended_at,
                resume_conditions=tuple(new_conditions),
                snapshot=suspension.snapshot,
                role_address=suspension.role_address,
                suspension_id=suspension.suspension_id,
            )
            self._suspensions[plan_id] = updated

            self._emit_audit_unlocked(
                "resume_condition_updated",
                {
                    "plan_id": plan_id,
                    "condition_type": condition_type,
                    "satisfied": satisfied,
                    "role_address": suspension.role_address,
                },
            )

            return updated

    def get_suspension(self, plan_id: str) -> PlanSuspension | None:
        """Retrieve the current suspension record for a plan.

        Thread-safe.

        Args:
            plan_id: The plan to look up.

        Returns:
            The PlanSuspension if the plan is suspended, None otherwise.
        """
        with self._lock:
            return self._suspensions.get(plan_id)

    # -------------------------------------------------------------------
    # Query API
    # -------------------------------------------------------------------

    @property
    def org_name(self) -> str:
        """Human-readable organization name.

        When initialized from an OrgDefinition, returns the OrgDefinition.name.
        When initialized from a CompiledOrg, returns the org_id.
        """
        return self._org_name

    def get_org(self) -> CompiledOrg:
        """Return the compiled organization. Thread-safe.

        Returns:
            The CompiledOrg that this engine was initialized with.
        """
        with self._lock:
            return self._compiled_org

    def get_node(self, address: str) -> OrgNode | None:
        """Look up a node by its positional address or config role ID. Thread-safe.

        First attempts an exact address lookup in compiled_org.nodes. If that
        fails, falls back to searching by role_id via get_node_by_role_id().
        This ensures non-head roles (analysts, members) that are not in the
        primary nodes dict by their config ID can still be found.

        Args:
            address: A D/T/R positional address string or a config role ID.

        Returns:
            The OrgNode at that address, or None if not found.
        """
        with self._lock:
            # Exact address lookup first (O(1))
            node = self._compiled_org.nodes.get(address)
            if node is not None:
                return node
            # Fallback: search by config role_id (O(n) over nodes)
            return self._compiled_org.get_node_by_role_id(address)

    def list_roles(self, prefix: str | None = None) -> list[OrgNode]:
        """List all Role nodes in the compiled org. Thread-safe.

        Optionally filters by address prefix (e.g., "D1-R1" returns all
        Role nodes whose address starts with "D1-R1").

        Args:
            prefix: Optional D/T/R address prefix to filter by. When None,
                returns all Role nodes in the organization.

        Returns:
            A list of OrgNode instances whose node_type is ROLE, optionally
            filtered by the given prefix.
        """
        from kailash.trust.pact.addressing import NodeType

        with self._lock:
            results: list[OrgNode] = []
            for addr, node in self._compiled_org.nodes.items():
                if node.node_type != NodeType.ROLE:
                    continue
                if prefix is not None:
                    if addr != prefix and not addr.startswith(prefix + "-"):
                        continue
                results.append(node)
            return results

    def get_context(
        self,
        role_address: str,
        posture: TrustPostureLevel = TrustPostureLevel.SUPERVISED,
    ) -> GovernanceContext:
        """Create a frozen GovernanceContext snapshot for an agent.

        This is the anti-self-modification defense: agents receive a frozen
        snapshot of their governance state, NOT the engine itself. They cannot
        call grant_clearance(), set_role_envelope(), or any mutation method.

        The context includes:
        - The role's effective envelope (computed from role + ancestors)
        - The role's clearance and posture-capped effective clearance level
        - Allowed actions derived from the operational envelope dimension
        - Compartments from the clearance assignment

        Args:
            role_address: The D/T/R positional address of the role.
            posture: The trust posture level for this agent. Defaults to
                SUPERVISED (the safest starting posture).

        Returns:
            A frozen GovernanceContext suitable for agent consumption.
        """
        with self._lock:
            # Compute effective envelope
            effective_env = self._compute_envelope_locked(role_address)

            # Get clearance if it exists
            clearance = self._clearance_store.get_clearance(role_address)

            # Compute effective clearance level (posture-capped)
            eff_clearance_level = None
            if clearance is not None:
                eff_clearance_level = effective_clearance(clearance, posture)

            # Derive allowed_actions from envelope
            allowed_actions: frozenset[str] = frozenset()
            if effective_env is not None:
                allowed_actions = frozenset(effective_env.operational.allowed_actions)

            # Derive compartments from clearance
            compartments: frozenset[str] = frozenset()
            if clearance is not None:
                compartments = clearance.compartments

            return GovernanceContext(
                role_address=role_address,
                posture=posture,
                effective_envelope=effective_env,
                clearance=clearance,
                effective_clearance_level=eff_clearance_level,
                allowed_actions=allowed_actions,
                compartments=compartments,
                org_id=self._compiled_org.org_id,
                created_at=datetime.now(UTC),
            )

    # -------------------------------------------------------------------
    # Address Resolution
    # -------------------------------------------------------------------

    def _resolve_role_address(self, role_address: str) -> str:
        """Resolve a role identifier to its positional D/T/R address.

        Accepts either a positional address (e.g., "D1-R1") or a config
        role ID (e.g., "r-president"). Returns the canonical positional
        address in both cases.

        This method does NOT acquire self._lock -- callers must hold it.

        Args:
            role_address: A D/T/R address or config role ID.

        Returns:
            The canonical positional address string.

        Raises:
            PactError: If the identifier cannot be resolved to any node.
        """
        # Try exact address lookup first (O(1))
        if role_address in self._compiled_org.nodes:
            return role_address

        # Fallback: search by config role_id (O(n) over nodes)
        node = self._compiled_org.get_node_by_role_id(role_address)
        if node is not None:
            return node.address

        raise PactError(
            f"Cannot resolve role address '{role_address}': not found as a "
            f"positional address or config role ID in the compiled organization",
            details={
                "role_address": role_address,
                "available_addresses": sorted(self._compiled_org.nodes.keys()),
            },
        )

    # -------------------------------------------------------------------
    # State Mutation API
    # -------------------------------------------------------------------

    def grant_clearance(self, role_address: str, clearance: RoleClearance) -> None:
        """Grant clearance to a role. Thread-safe. Emits audit anchor.

        Accepts both D/T/R positional addresses (e.g., "D1-R1") and config
        role IDs (e.g., "r-president"). The address is resolved to its
        canonical positional form before any store operations.

        FSM validation is enforced for "living" states (PENDING, ACTIVE,
        SUSPENDED). Terminal states (REVOKED, EXPIRED) and missing records
        allow unconditional overwrite to support re-granting and backup/restore.

        Args:
            role_address: The D/T/R address or config role ID of the role.
            clearance: The RoleClearance to grant.

        Raises:
            PactError: If the address cannot be resolved, or if the
                transition from the existing vetting status to the new one
                is invalid per the FSM.
        """
        _LIVING_STATES = {
            VettingStatus.PENDING,
            VettingStatus.ACTIVE,
            VettingStatus.SUSPENDED,
        }
        with self._lock:
            role_address = self._resolve_role_address(role_address)
            existing = self._clearance_store.get_clearance(role_address)
            if (
                existing is not None
                and existing.vetting_status in _LIVING_STATES
                and existing.vetting_status != clearance.vetting_status
            ):
                validate_transition(existing.vetting_status, clearance.vetting_status)
            self._clearance_store.grant_clearance(clearance)

            # N2: Clearance changes affect access decisions that may be
            # cached alongside envelope context. Invalidate the role's
            # cached envelopes so next computation uses fresh state.
            self._cascade_invalidate(role_address)

        self._emit_audit(
            PactAuditAction.CLEARANCE_GRANTED.value,
            create_pact_audit_details(
                PactAuditAction.CLEARANCE_GRANTED,
                role_address=role_address,
                reason=f"Granted {clearance.max_clearance.value} clearance",
                max_clearance=clearance.max_clearance.value,
                vetting_status=clearance.vetting_status.value,
            ),
        )

        # N5: Emit observation for clearance grant
        self._emit_observation(
            event_type="clearance_change",
            role_address=role_address,
            level="info",
            payload={
                "change": "granted",
                "max_clearance": clearance.max_clearance.value,
                "vetting_status": clearance.vetting_status.value,
                "compartments": sorted(clearance.compartments),
            },
        )

        # Emit CapabilityAttestation via EATP (Section 5.7)
        if self._eatp_emitter is not None:
            try:
                from uuid import uuid4

                from kailash.trust.chain import CapabilityAttestation, CapabilityType

                constraints = [
                    f"vetting:{clearance.vetting_status.value}",
                ]
                for compartment in sorted(clearance.compartments):
                    constraints.append(f"compartment:{compartment}")
                attestation = CapabilityAttestation(
                    id=f"pact-capability-{uuid4().hex[:8]}",
                    capability=f"clearance:{clearance.max_clearance.value}",
                    capability_type=CapabilityType.ACCESS,
                    constraints=constraints,
                    attester_id=role_address,
                    attested_at=datetime.now(UTC),
                    signature="UNSIGNED",
                )
                self._eatp_emitter.emit_capability(attestation)
            except Exception:
                logger.exception(
                    "Failed to emit CapabilityAttestation for grant_clearance"
                )

    def revoke_clearance(self, role_address: str) -> None:
        """Revoke clearance for a role. Thread-safe. Emits audit anchor.

        Accepts both D/T/R positional addresses and config role IDs.
        No-op if the clearance is already REVOKED (prevents audit log pollution).

        Args:
            role_address: The D/T/R address or config role ID whose clearance
                to revoke.

        Raises:
            PactError: If the address cannot be resolved.
        """
        with self._lock:
            role_address = self._resolve_role_address(role_address)
            existing = self._clearance_store.get_clearance(role_address)
            if (
                existing is not None
                and existing.vetting_status == VettingStatus.REVOKED
            ):
                return
            self._clearance_store.revoke_clearance(role_address)

            # N2: Clearance revocation invalidates cached envelopes for the role.
            self._cascade_invalidate(role_address)

        self._emit_audit(
            PactAuditAction.CLEARANCE_REVOKED.value,
            create_pact_audit_details(
                PactAuditAction.CLEARANCE_REVOKED,
                role_address=role_address,
                reason="Clearance revoked",
            ),
        )

        # N5: Emit observation for clearance revocation
        self._emit_observation(
            event_type="clearance_change",
            role_address=role_address,
            level="critical",
            payload={"change": "revoked"},
        )

    def transition_clearance(
        self, role_address: str, new_status: VettingStatus
    ) -> None:
        """Transition an existing clearance's vetting status. Thread-safe.

        Accepts both D/T/R positional addresses and config role IDs.
        Validates the FSM transition and emits an audit anchor. Use this
        for status changes (e.g., ACTIVE -> SUSPENDED for investigation,
        SUSPENDED -> ACTIVE for reinstatement).

        Args:
            role_address: The D/T/R address or config role ID of the role.
            new_status: The target VettingStatus.

        Raises:
            PactError: If the address cannot be resolved, if no clearance
                exists for the role, or if the transition is invalid per
                the FSM.
        """
        from dataclasses import replace

        with self._lock:
            role_address = self._resolve_role_address(role_address)
            existing = self._clearance_store.get_clearance(role_address)
            if existing is None:
                raise PactError(
                    f"Cannot transition clearance: no clearance found for '{role_address}'",
                    details={
                        "role_address": role_address,
                        "new_status": new_status.value,
                    },
                )
            validate_transition(existing.vetting_status, new_status)
            updated = replace(existing, vetting_status=new_status)
            self._clearance_store.grant_clearance(updated)

            # N2: Clearance transition invalidates cached envelopes for the role.
            self._cascade_invalidate(role_address)

        self._emit_audit(
            PactAuditAction.CLEARANCE_TRANSITIONED.value,
            create_pact_audit_details(
                PactAuditAction.CLEARANCE_TRANSITIONED,
                role_address=role_address,
                reason=f"Transitioned from {existing.vetting_status.value} to {new_status.value}",
                from_status=existing.vetting_status.value,
                to_status=new_status.value,
            ),
        )

        # Emit CapabilityAttestation via EATP (Section 5.7)
        if self._eatp_emitter is not None:
            try:
                from uuid import uuid4

                from kailash.trust.chain import CapabilityAttestation, CapabilityType

                constraints = [
                    f"vetting:{new_status.value}",
                    f"transition:{existing.vetting_status.value}->{new_status.value}",
                ]
                for compartment in sorted(existing.compartments):
                    constraints.append(f"compartment:{compartment}")
                attestation = CapabilityAttestation(
                    id=f"pact-capability-{uuid4().hex[:8]}",
                    capability=f"clearance:{existing.max_clearance.value}",
                    capability_type=CapabilityType.ACCESS,
                    constraints=constraints,
                    attester_id=role_address,
                    attested_at=datetime.now(UTC),
                    signature="UNSIGNED",
                )
                self._eatp_emitter.emit_capability(attestation)
            except Exception:
                logger.exception(
                    "Failed to emit CapabilityAttestation for transition_clearance"
                )

    def consent_bridge(self, role_address: str, bridge_id: str) -> None:
        """Register a role's consent to participate in a bridge (Section 4.4).

        When require_bilateral_consent is True, both roles involved in a bridge
        must consent before create_bridge() can proceed.
        Consents expire after 24 hours.
        """
        with self._lock:
            # RED TEAM FIX R2: validate address exists in org
            if role_address not in self._compiled_org.nodes:
                raise PactError(
                    f"Cannot register bridge consent: address '{role_address}' "
                    f"does not exist in the compiled organization",
                    details={"role_address": role_address, "bridge_id": bridge_id},
                )
            # Bounded: evict oldest if at capacity
            while len(self._bridge_consents) >= _MAX_BRIDGE_APPROVALS:
                self._bridge_consents.popitem(last=False)
            self._bridge_consents[(role_address, bridge_id)] = datetime.now(UTC)

        self._emit_audit(
            PactAuditAction.BRIDGE_CONSENT.value,
            create_pact_audit_details(
                PactAuditAction.BRIDGE_CONSENT,
                role_address=role_address,
                reason=f"Bridge consent registered for bridge '{bridge_id}'",
            ),
        )

    def register_compliance_role(self, role_address: str) -> None:
        """Register a role as the designated compliance approver for bridges."""
        with self._lock:
            # RED TEAM FIX R2: validate address exists in org
            if role_address not in self._compiled_org.nodes:
                raise PactError(
                    f"Cannot register compliance role: address '{role_address}' "
                    f"does not exist in the compiled organization",
                    details={"role_address": role_address},
                )
            self._compliance_role = role_address
        self._emit_audit(
            "compliance_role_registered",
            {"role_address": role_address},
        )

    def approve_bridge(
        self,
        source_address: str,
        target_address: str,
        approver_address: str,
    ) -> BridgeApproval:
        """Pre-approve a bridge between two roles. Thread-safe. Emits audit anchor.

        Per PACT Section 4.4, the LCA of the source and target roles must
        approve a bridge before it can be created. This method records that
        approval with a 24-hour TTL.

        The approver_address MUST be the LCA of source_address and
        target_address. If it is not, a PactError is raised (fail-closed).

        Args:
            source_address: D/T/R address of one side of the bridge.
            target_address: D/T/R address of the other side of the bridge.
            approver_address: D/T/R address of the role approving the bridge.
                Must be the LCA of source and target.

        Returns:
            The BridgeApproval record.

        Raises:
            PactError: If the approver is not the LCA of source and target,
                if addresses cannot be parsed, or if no common ancestor exists.
        """
        with self._lock:
            # Parse addresses -- fail-closed on parse errors
            try:
                source_addr = Address.parse(source_address)
                target_addr = Address.parse(target_address)
            except Exception as exc:
                raise PactError(
                    f"Cannot parse bridge addresses: {exc}",
                    details={
                        "source_address": source_address,
                        "target_address": target_address,
                    },
                ) from exc

            # Compute LCA
            lca = Address.lowest_common_ancestor(source_addr, target_addr)
            if lca is None:
                raise PactError(
                    "Cannot approve bridge: addresses have no common ancestor",
                    details={
                        "source_address": source_address,
                        "target_address": target_address,
                    },
                )

            # Verify the approver IS the LCA or the compliance role
            lca_str = str(lca)
            is_lca = approver_address == lca_str
            is_compliance = (
                self._compliance_role is not None
                and approver_address == self._compliance_role
            )
            if not is_lca and not is_compliance:
                raise PactError(
                    f"Bridge approval must come from the LCA ({lca}) "
                    f"or the compliance role ({self._compliance_role}), "
                    f"not {approver_address}",
                    details={
                        "source_address": source_address,
                        "target_address": target_address,
                        "approver_address": approver_address,
                        "required_lca": lca_str,
                        "compliance_role": self._compliance_role,
                    },
                )

            # Vacancy check: vacant roles cannot approve bridges
            approver_node = self._compiled_org.nodes.get(approver_address)
            if approver_node is not None and approver_node.is_vacant:
                raise PactError(
                    f"Bridge approval cannot be given by vacant role '{approver_address}'",
                    details={
                        "approver_address": approver_address,
                        "is_vacant": True,
                        "source_address": source_address,
                        "target_address": target_address,
                    },
                )

            approver_type = "compliance" if is_compliance else "lca"

            now = datetime.now(UTC)
            approval = BridgeApproval(
                source_address=source_address,
                target_address=target_address,
                approved_by=approver_address,
                approved_at=now,
                expires_at=now + _BRIDGE_APPROVAL_TTL,
            )

            # Store with bounded eviction
            approval_key = f"{source_address}|{target_address}"
            self._bridge_approvals[approval_key] = approval
            # Evict oldest when at capacity (bounded collection)
            while len(self._bridge_approvals) > _MAX_BRIDGE_APPROVALS:
                self._bridge_approvals.popitem(last=False)

            # N2: Bridge approval invalidates cached envelopes at both endpoints.
            self._invalidate_bridge_endpoints(source_address, target_address)

        self._emit_audit(
            PactAuditAction.BRIDGE_APPROVED.value,
            create_pact_audit_details(
                PactAuditAction.BRIDGE_APPROVED,
                role_address=approver_address,
                target_address=target_address,
                reason=(
                    f"Bridge between '{source_address}' and '{target_address}' "
                    f"approved by {approver_type} '{approver_address}'"
                ),
                source_address=source_address,
                lca_address=approver_address,
                approver_type=approver_type,
            ),
        )

        # N5: Emit observation for bridge approval
        self._emit_observation(
            event_type="bridge_event",
            role_address=approver_address,
            level="info",
            payload={
                "bridge_action": "approved",
                "source_address": source_address,
                "target_address": target_address,
                "approver_type": approver_type,
            },
        )

        return approval

    def reject_bridge(
        self,
        source_address: str,
        target_address: str,
        rejector_address: str,
    ) -> bool:
        """Reject (remove) a bridge approval. Thread-safe. Emits audit anchor.

        The rejector must be the LCA of the source and target roles or the
        designated compliance role. Vacant roles cannot reject bridges.

        Args:
            source_address: D/T/R address of one side of the bridge.
            target_address: D/T/R address of the other side of the bridge.
            rejector_address: D/T/R address of the role rejecting the bridge.
                Must be the LCA of source and target, or the compliance role.

        Returns:
            True if an approval existed and was removed, False if no approval
            was found for the given source/target pair.

        Raises:
            PactError: If the rejector is not the LCA or compliance role,
                if the rejector is vacant, if addresses cannot be parsed,
                or if no common ancestor exists.
        """
        with self._lock:
            # Parse addresses -- fail-closed on parse errors
            try:
                source_addr = Address.parse(source_address)
                target_addr = Address.parse(target_address)
            except Exception as exc:
                raise PactError(
                    f"Cannot parse bridge addresses: {exc}",
                    details={
                        "source_address": source_address,
                        "target_address": target_address,
                    },
                ) from exc

            # Compute LCA
            lca = Address.lowest_common_ancestor(source_addr, target_addr)
            if lca is None:
                raise PactError(
                    "Cannot reject bridge: addresses have no common ancestor",
                    details={
                        "source_address": source_address,
                        "target_address": target_address,
                    },
                )

            # Verify the rejector IS the LCA or the compliance role
            lca_str = str(lca)
            is_lca = rejector_address == lca_str
            is_compliance = (
                self._compliance_role is not None
                and rejector_address == self._compliance_role
            )
            if not is_lca and not is_compliance:
                raise PactError(
                    f"Bridge rejection must come from the LCA ({lca}) "
                    f"or the compliance role ({self._compliance_role}), "
                    f"not {rejector_address}",
                    details={
                        "source_address": source_address,
                        "target_address": target_address,
                        "rejector_address": rejector_address,
                        "required_lca": lca_str,
                        "compliance_role": self._compliance_role,
                    },
                )

            # Vacancy check: vacant roles cannot reject bridges
            rejector_node = self._compiled_org.nodes.get(rejector_address)
            if rejector_node is not None and rejector_node.is_vacant:
                raise PactError(
                    f"Bridge rejection cannot be given by vacant role '{rejector_address}'",
                    details={
                        "rejector_address": rejector_address,
                        "is_vacant": True,
                        "source_address": source_address,
                        "target_address": target_address,
                    },
                )

            # Remove approval if it exists (check both orderings)
            removed = False
            for key in (
                f"{source_address}|{target_address}",
                f"{target_address}|{source_address}",
            ):
                if key in self._bridge_approvals:
                    del self._bridge_approvals[key]
                    removed = True

            # N2: Bridge rejection invalidates cached envelopes at both endpoints.
            if removed:
                self._invalidate_bridge_endpoints(source_address, target_address)

        rejector_type = "compliance" if is_compliance else "lca"

        self._emit_audit(
            PactAuditAction.BRIDGE_REJECTED.value,
            create_pact_audit_details(
                PactAuditAction.BRIDGE_REJECTED,
                role_address=rejector_address,
                target_address=target_address,
                reason=(
                    f"Bridge between '{source_address}' and '{target_address}' "
                    f"rejected by {rejector_type} '{rejector_address}'"
                ),
                source_address=source_address,
                lca_address=rejector_address,
                rejector_type=rejector_type,
                approval_existed=removed,
            ),
        )

        return removed

    def _check_bridge_approval(
        self,
        source_address: str,
        target_address: str,
    ) -> BridgeApproval | None:
        """Check if a valid (non-expired) bridge approval exists.

        Caller must hold self._lock.

        Checks both orderings (source|target and target|source) since a bridge
        approval for A->B should also satisfy B->A.

        Args:
            source_address: D/T/R address of one side of the bridge.
            target_address: D/T/R address of the other side of the bridge.

        Returns:
            The BridgeApproval if one exists and has not expired, else None.
        """
        now = datetime.now(UTC)
        # Check both orderings
        for key in (
            f"{source_address}|{target_address}",
            f"{target_address}|{source_address}",
        ):
            approval = self._bridge_approvals.get(key)
            if approval is not None:
                if now < approval.expires_at:
                    return approval
                # Expired -- clean up
                del self._bridge_approvals[key]
        return None

    def create_bridge(self, bridge: PactBridge) -> None:
        """Create a Cross-Functional Bridge. Thread-safe. Emits audit anchor.

        Per PACT Section 4.4, the lowest common ancestor (LCA) of the source
        and target roles must have approved the bridge via approve_bridge()
        before it can be created. If no valid (non-expired) approval exists,
        creation is blocked (fail-closed).

        Args:
            bridge: The PactBridge to create.

        Raises:
            PactError: If no valid LCA approval exists, if addresses cannot
                be parsed, or if no common ancestor exists.
        """
        with self._lock:
            # Parse addresses for LCA computation
            try:
                source_addr = Address.parse(bridge.role_a_address)
                target_addr = Address.parse(bridge.role_b_address)
            except Exception as exc:
                raise PactError(
                    f"Cannot parse bridge addresses: {exc}",
                    details={
                        "role_a_address": bridge.role_a_address,
                        "role_b_address": bridge.role_b_address,
                        "bridge_id": bridge.id,
                    },
                ) from exc

            # Compute LCA
            lca = Address.lowest_common_ancestor(source_addr, target_addr)
            if lca is None:
                raise PactError(
                    "Cannot create bridge: addresses have no common ancestor",
                    details={
                        "role_a_address": bridge.role_a_address,
                        "role_b_address": bridge.role_b_address,
                        "bridge_id": bridge.id,
                    },
                )

            # Check for valid approval from the LCA
            approval = self._check_bridge_approval(
                bridge.role_a_address, bridge.role_b_address
            )
            if approval is None:
                raise PactError(
                    f"Bridge requires approval from LCA: {lca}",
                    details={
                        "role_a_address": bridge.role_a_address,
                        "role_b_address": bridge.role_b_address,
                        "bridge_id": bridge.id,
                        "required_lca": str(lca),
                    },
                )

            # Verify the approval came from the actual LCA or compliance role
            lca_str = str(lca)
            is_lca_approval = approval.approved_by == lca_str
            is_compliance_approval = (
                self._compliance_role is not None
                and approval.approved_by == self._compliance_role
            )
            if not is_lca_approval and not is_compliance_approval:
                raise PactError(
                    f"Bridge approval must come from LCA ({lca}) "
                    f"or compliance role ({self._compliance_role}), "
                    f"not {approval.approved_by}",
                    details={
                        "role_a_address": bridge.role_a_address,
                        "role_b_address": bridge.role_b_address,
                        "bridge_id": bridge.id,
                        "approved_by": approval.approved_by,
                        "required_lca": lca_str,
                        "compliance_role": self._compliance_role,
                    },
                )

            # Bilateral consent check (Section 4.4)
            source_address = bridge.role_a_address
            target_address = bridge.role_b_address
            if self._require_bilateral_consent:
                now_check = datetime.now(UTC)
                for role_addr in (source_address, target_address):
                    key = (role_addr, bridge.id)
                    consent_time = self._bridge_consents.get(key)
                    if consent_time is None:
                        raise PactError(
                            f"Bridge bilateral consent missing from '{role_addr}'",
                            details={"role": role_addr},
                        )
                    if now_check - consent_time > _BRIDGE_APPROVAL_TTL:
                        raise PactError(
                            f"Bridge consent from '{role_addr}' has expired",
                            details={"role": role_addr},
                        )

            # Validate bridge scope against endpoint envelopes
            self._validate_bridge_scope_locked(bridge)

            # All checks passed -- persist the bridge
            self._access_policy_store.save_bridge(bridge)

        self._emit_audit(
            PactAuditAction.BRIDGE_ESTABLISHED.value,
            create_pact_audit_details(
                PactAuditAction.BRIDGE_ESTABLISHED,
                role_address=bridge.role_a_address,
                target_address=bridge.role_b_address,
                reason=f"Bridge '{bridge.id}' ({bridge.bridge_type}) established",
                bridge_id=bridge.id,
                bridge_type=bridge.bridge_type,
                lca_approver=approval.approved_by,
            ),
        )

        # Emit bilateral DelegationRecord via EATP (Section 5.7)
        if self._eatp_emitter is not None:
            try:
                from uuid import uuid4

                from kailash.trust.chain import DelegationRecord

                # Bilateral: emit A->B and B->A
                for delegator, delegatee in [
                    (source_address, target_address),
                    (target_address, source_address),
                ]:
                    delegation = DelegationRecord(
                        id=f"pact-deleg-{uuid4().hex[:8]}",
                        delegator_id=delegator,
                        delegatee_id=delegatee,
                        task_id="",
                        capabilities_delegated=[],
                        constraint_subset=[],
                        delegated_at=datetime.now(UTC),
                        signature="UNSIGNED",
                    )
                    self._eatp_emitter.emit_delegation(delegation)
            except Exception:
                logger.exception("Failed to emit DelegationRecord for create_bridge")

        # N5: Emit observation for bridge creation
        self._emit_observation(
            event_type="bridge_event",
            role_address=bridge.role_a_address,
            level="info",
            payload={
                "bridge_action": "created",
                "bridge_id": bridge.id,
                "bridge_type": bridge.bridge_type,
                "role_a_address": bridge.role_a_address,
                "role_b_address": bridge.role_b_address,
                "lca_approver": approval.approved_by,
            },
        )

    def _validate_bridge_scope_locked(self, bridge: PactBridge) -> None:
        """Validate bridge scope against both endpoint envelopes. Caller holds lock."""
        has_classification = (
            hasattr(bridge, "max_classification")
            and bridge.max_classification != ConfidentialityLevel.PUBLIC
        )
        has_ops_scope = (
            hasattr(bridge, "operational_scope") and bridge.operational_scope
        )

        if not has_classification and not has_ops_scope:
            return  # No scope to validate

        source_addr = bridge.role_a_address
        target_addr = bridge.role_b_address

        for role_addr in (source_addr, target_addr):
            if role_addr is None:
                continue
            envelope = self._compute_envelope_locked(role_addr)
            if envelope is None:
                # No envelope for this role -- skip scope validation.
                # Scope checks only apply when an envelope constrains the role.
                continue

            if has_classification:
                from kailash.trust.pact.config import CONFIDENTIALITY_ORDER

                # Only enforce classification when the role has an explicit
                # (non-default) clearance. PUBLIC is the default "no restriction"
                # level -- enforcing against it would block all non-PUBLIC
                # bridges on roles that never configured classification.
                role_clearance = envelope.confidentiality_clearance
                if role_clearance != ConfidentialityLevel.PUBLIC:
                    bridge_order = CONFIDENTIALITY_ORDER.get(
                        bridge.max_classification, 0
                    )
                    role_order = CONFIDENTIALITY_ORDER.get(role_clearance, 0)
                    if bridge_order > role_order:
                        raise PactError(
                            f"Bridge max_classification '{bridge.max_classification.value}' exceeds "
                            f"role '{role_addr}' clearance '{role_clearance.value}'",
                            details={
                                "bridge_classification": bridge.max_classification.value,
                                "role_clearance": role_clearance.value,
                            },
                        )

            if has_ops_scope:
                allowed = set(envelope.operational.allowed_actions)
                requested = set(bridge.operational_scope)
                if allowed and not requested.issubset(allowed):
                    extra = requested - allowed
                    raise PactError(
                        f"Bridge operational_scope {sorted(extra)} not in "
                        f"role '{role_addr}' allowed actions {sorted(allowed)}",
                        details={
                            "role_address": role_addr,
                            "extra_ops": sorted(extra),
                        },
                    )

    def create_ksp(self, ksp: KnowledgeSharePolicy) -> None:
        """Create a Knowledge Share Policy. Thread-safe. Emits audit anchor.

        Args:
            ksp: The KnowledgeSharePolicy to create.
        """
        with self._lock:
            self._access_policy_store.save_ksp(ksp)

        self._emit_audit(
            PactAuditAction.KSP_CREATED.value,
            create_pact_audit_details(
                PactAuditAction.KSP_CREATED,
                role_address=ksp.created_by_role_address,
                reason=f"KSP '{ksp.id}': {ksp.source_unit_address} -> {ksp.target_unit_address}",
                ksp_id=ksp.id,
                source_unit=ksp.source_unit_address,
                target_unit=ksp.target_unit_address,
            ),
        )

    def set_role_envelope(self, envelope: RoleEnvelope) -> None:
        """Set a role envelope. Thread-safe. Emits audit anchor.

        Validates monotonic tightening before persisting: the child envelope
        cannot be wider than the defining role's effective envelope.

        Args:
            envelope: The RoleEnvelope to set.

        Raises:
            MonotonicTighteningError: If the envelope is wider than the
                defining role's effective envelope.
        """
        with self._lock:
            # Check if this is a new or modified envelope
            is_new = (
                self._envelope_store.get_role_envelope(envelope.target_role_address)
                is None
            )

            # Validate monotonic tightening: child cannot be wider than parent
            defining_envelope = self._compute_envelope_locked(
                envelope.defining_role_address
            )
            if defining_envelope is not None:
                RoleEnvelope.validate_tightening(
                    parent_envelope=defining_envelope,
                    child_envelope=envelope.envelope,
                )

            # Detect pass-through envelope
            is_passthrough = False
            if defining_envelope is not None:
                is_passthrough = check_passthrough_envelope(
                    defining_envelope, envelope.envelope
                )
                if is_passthrough:
                    logger.warning(
                        "Pass-through envelope detected: envelope '%s' for "
                        "role '%s' is identical to the defining role's "
                        "effective envelope (no additional tightening). "
                        "Consider whether this delegation adds value.",
                        envelope.id,
                        envelope.target_role_address,
                    )

            self._envelope_store.save_role_envelope(envelope)

            # N2: Cascade-invalidate the target address and all descendants.
            # The target role and any role beneath it in the D/T/R tree may
            # have cached envelopes that depend on this role envelope.
            self._cascade_invalidate(envelope.target_role_address)

        audit_action = (
            PactAuditAction.ENVELOPE_CREATED
            if is_new
            else PactAuditAction.ENVELOPE_MODIFIED
        )
        self._emit_audit(
            audit_action.value,
            create_pact_audit_details(
                audit_action,
                role_address=envelope.defining_role_address,
                target_address=envelope.target_role_address,
                reason=f"Role envelope '{envelope.id}' {'created' if is_new else 'modified'} for '{envelope.target_role_address}'",
                envelope_id=envelope.id,
                is_passthrough=is_passthrough,
            ),
        )

        # Emit DelegationRecord via EATP (Section 5.7)
        if self._eatp_emitter is not None:
            try:
                from uuid import uuid4

                from kailash.trust.chain import DelegationRecord

                delegation = DelegationRecord(
                    id=f"pact-deleg-{uuid4().hex[:8]}",
                    delegator_id=envelope.defining_role_address,
                    delegatee_id=envelope.target_role_address,
                    task_id="",
                    capabilities_delegated=list(
                        envelope.envelope.operational.allowed_actions
                    ),
                    constraint_subset=[],
                    delegated_at=datetime.now(UTC),
                    signature="UNSIGNED",
                )
                self._eatp_emitter.emit_delegation(delegation)
            except Exception:
                logger.exception(
                    "Failed to emit DelegationRecord for set_role_envelope"
                )

        # N5: Emit observation for role envelope change
        self._emit_observation(
            event_type="envelope_change",
            role_address=envelope.target_role_address,
            level="info",
            payload={
                "envelope_id": envelope.id,
                "envelope_type": "role",
                "change": "created" if is_new else "modified",
                "defining_role_address": envelope.defining_role_address,
                "is_passthrough": is_passthrough,
            },
        )

    def set_task_envelope(self, envelope: TaskEnvelope) -> None:
        """Set a task envelope. Thread-safe. Emits audit anchor.

        Validates monotonic tightening before persisting: the task envelope
        cannot be wider than the parent role envelope it narrows. The parent
        is identified by the task envelope's parent_envelope_id.

        Args:
            envelope: The TaskEnvelope to set.

        Raises:
            MonotonicTighteningError: If the task envelope is wider than the
                parent role envelope.
        """
        with self._lock:
            # Validate monotonic tightening: task envelope cannot be wider
            # than the parent role envelope.
            parent_role_env = self._find_role_envelope_by_id_locked(
                envelope.parent_envelope_id
            )
            if parent_role_env is not None:
                RoleEnvelope.validate_tightening(
                    parent_envelope=parent_role_env.envelope,
                    child_envelope=envelope.envelope,
                )
            self._envelope_store.save_task_envelope(envelope)

            # N2: Invalidate any cached envelope entries that match this task_id.
            # Task envelopes narrow the effective envelope for a specific task,
            # so any cached entry with the same task_id must be evicted.
            keys_to_evict = [
                k for k in self._envelope_cache if k[1] == envelope.task_id
            ]
            for k in keys_to_evict:
                del self._envelope_cache[k]

        self._emit_audit(
            PactAuditAction.ENVELOPE_CREATED.value,
            create_pact_audit_details(
                PactAuditAction.ENVELOPE_CREATED,
                reason=(
                    f"Task envelope '{envelope.id}' for task '{envelope.task_id}' "
                    f"(parent: '{envelope.parent_envelope_id}')"
                ),
                envelope_id=envelope.id,
                task_id=envelope.task_id,
                parent_envelope_id=envelope.parent_envelope_id,
            ),
        )

        # Emit DelegationRecord via EATP (Section 5.7)
        if self._eatp_emitter is not None:
            try:
                from uuid import uuid4

                from kailash.trust.chain import DelegationRecord

                delegation = DelegationRecord(
                    id=f"pact-deleg-task-{uuid4().hex[:8]}",
                    delegator_id=envelope.parent_envelope_id,
                    delegatee_id=envelope.task_id,
                    task_id=envelope.task_id,
                    capabilities_delegated=list(
                        envelope.envelope.operational.allowed_actions
                    ),
                    constraint_subset=[],
                    delegated_at=datetime.now(UTC),
                    signature="UNSIGNED",
                )
                self._eatp_emitter.emit_delegation(delegation)
            except Exception:
                logger.exception(
                    "Failed to emit DelegationRecord for set_task_envelope"
                )

        # N5: Emit observation for task envelope creation
        self._emit_observation(
            event_type="envelope_change",
            role_address=envelope.task_id,
            level="info",
            payload={
                "envelope_id": envelope.id,
                "envelope_type": "task",
                "change": "created",
                "task_id": envelope.task_id,
                "parent_envelope_id": envelope.parent_envelope_id,
            },
        )

    # -------------------------------------------------------------------
    # Vacancy Designation API (Section 5.5)
    # -------------------------------------------------------------------

    def designate_acting_occupant(
        self,
        vacant_role: str,
        acting_role: str,
        designated_by: str,
    ) -> VacancyDesignation:
        """Designate an acting occupant for a vacant role. Thread-safe.

        The parent role of a vacant position must designate an acting occupant
        within 24 hours. The designation expires after 24 hours and must be
        renewed if the vacancy persists.

        The acting occupant inherits the vacant role's envelope (constraints)
        but does NOT receive clearance upgrades from the vacant role.

        Args:
            vacant_role: The D/T/R address of the vacant role.
            acting_role: The D/T/R address of the acting occupant.
            designated_by: The D/T/R address of the parent role making
                the designation.

        Returns:
            The VacancyDesignation record.

        Raises:
            PactError: If the vacant role is not actually vacant, if the
                designating role is not found, or if the store is at capacity.
        """
        from kailash.trust.pact.exceptions import PactError

        with self._lock:
            # Validate the vacant role exists and is actually vacant
            node = self._compiled_org.nodes.get(vacant_role)
            if node is None:
                raise PactError(
                    f"Vacant role address '{vacant_role}' not found in org",
                    details={"vacant_role": vacant_role},
                )
            if not node.is_vacant:
                raise PactError(
                    f"Role at '{vacant_role}' is not vacant",
                    details={"vacant_role": vacant_role, "is_vacant": False},
                )

            # Validate the acting role exists
            acting_node = self._compiled_org.nodes.get(acting_role)
            if acting_node is None:
                raise PactError(
                    f"Acting role address '{acting_role}' not found in org",
                    details={"acting_role": acting_role},
                )

            # Validate the designating role exists
            designator_node = self._compiled_org.nodes.get(designated_by)
            if designator_node is None:
                raise PactError(
                    f"Designating role address '{designated_by}' not found in org",
                    details={"designated_by": designated_by},
                )

            # Enforce bounded collection
            if len(self._vacancy_designations) >= self._max_vacancy_designations:
                raise PactError(
                    f"Vacancy designation store at capacity "
                    f"({self._max_vacancy_designations})",
                    details={"capacity": self._max_vacancy_designations},
                )

            now = datetime.now(timezone.utc)
            expires = now + self._vacancy_deadline

            designation = VacancyDesignation(
                vacant_role_address=vacant_role,
                acting_role_address=acting_role,
                designated_by=designated_by,
                designated_at=now.isoformat(),
                expires_at=expires.isoformat(),
            )

            self._vacancy_designations[vacant_role] = designation

        # Emit audit outside lock (audit chain has its own lock)
        self._emit_audit(
            PactAuditAction.VACANCY_DESIGNATED.value,
            create_pact_audit_details(
                PactAuditAction.VACANCY_DESIGNATED,
                role_address=designated_by,
                target_address=vacant_role,
                reason=(
                    f"Acting occupant '{acting_role}' designated for "
                    f"vacant role '{vacant_role}' by '{designated_by}'"
                ),
                acting_role=acting_role,
            ),
        )

        return designation

    def get_vacancy_designation(
        self,
        role_address: str,
    ) -> VacancyDesignation | None:
        """Get the vacancy designation for a role, if one exists. Thread-safe.

        Args:
            role_address: The D/T/R address of the (potentially vacant) role.

        Returns:
            The VacancyDesignation if one exists, or None.
        """
        with self._lock:
            return self._vacancy_designations.get(role_address)

    def _check_vacancy(self, address: str) -> _VacancyCheckResult:
        """Check vacancy status with interim envelope support (Section 5.5).

        Implements PACT Section 5.5 vacancy enforcement with interim envelopes:
        1. If the role at the address is not vacant, return ok.
        2. If the role is vacant and has a valid (non-expired) designation,
           return ok (acting occupant covers it).
        3. If the role is vacant, no designation, but within the vacancy deadline,
           return interim (with a tightened envelope).
        4. If the role is vacant past the vacancy deadline, return blocked.
        5. Also checks all ancestor roles: multiple vacant ancestors produce
           intersected interim envelopes (RED TEAM FIX R1).

        Args:
            address: The D/T/R address to check.

        Returns:
            A _VacancyCheckResult with status, message, and optional interim_envelope.
        """
        from kailash.trust.pact.addressing import Address

        try:
            parsed = Address.parse(address)
        except Exception:
            return _VacancyCheckResult(
                status="blocked",
                message=f"Unable to parse address '{address}' for vacancy check -- fail-closed",
            )

        now = datetime.now(UTC)
        addresses_to_check = [str(a) for a in parsed.accountability_chain]
        worst_result = _VacancyCheckResult(status="ok")

        for check_addr in addresses_to_check:
            node = self._compiled_org.nodes.get(check_addr)
            if node is None:
                continue
            if not node.is_vacant:
                continue

            designation = self._vacancy_designations.get(check_addr)
            if designation is not None and not designation.is_expired():
                continue

            vacancy_start = self._vacancy_start_times.get(check_addr)
            if vacancy_start is None:
                vacancy_start = now
                self._vacancy_start_times[check_addr] = vacancy_start

            elapsed = now - vacancy_start
            if elapsed >= self._vacancy_deadline:
                return _VacancyCheckResult(
                    status="blocked",
                    message=(
                        f"Role at '{check_addr}' is vacant with no acting occupant "
                        f"designation and has exceeded the vacancy deadline "
                        f"({self._vacancy_deadline}) -- all downstream actions "
                        f"are suspended (PACT Section 5.5)"
                    ),
                )

            # Within deadline -- compute interim envelope
            interim_env = self._compute_interim_envelope_locked(address, check_addr)

            # RED TEAM FIX R1: intersect multiple interim envelopes
            if worst_result.status == "ok":
                worst_result = _VacancyCheckResult(
                    status="interim",
                    message=(
                        f"Role at '{check_addr}' is vacant -- operating under "
                        f"interim envelope (deadline in {self._vacancy_deadline - elapsed})"
                    ),
                    interim_envelope=interim_env,
                )
            elif worst_result.status == "interim":
                combined_env = worst_result.interim_envelope
                if combined_env is not None and interim_env is not None:
                    combined_env = intersect_envelopes(combined_env, interim_env)
                elif interim_env is not None:
                    combined_env = interim_env
                worst_result = _VacancyCheckResult(
                    status="interim",
                    message=(
                        f"Multiple vacant ancestors (latest: '{check_addr}') -- "
                        f"operating under intersected interim envelope"
                    ),
                    interim_envelope=combined_env,
                )

        return worst_result

    def _compute_interim_envelope_locked(
        self,
        role_address: str,
        vacant_ancestor_address: str,
    ) -> ConstraintEnvelopeConfig | None:
        """Compute interim envelope during vacancy deadline window. Caller holds lock."""
        own_envelope = self._compute_envelope_locked(role_address)
        parent_envelope = self._compute_envelope_locked(vacant_ancestor_address)
        if own_envelope is None and parent_envelope is None:
            return None
        if own_envelope is None:
            return parent_envelope
        if parent_envelope is None:
            return own_envelope
        return intersect_envelopes(own_envelope, parent_envelope)

    # -------------------------------------------------------------------
    # Audit API
    # -------------------------------------------------------------------

    @property
    def audit_chain(self) -> Any | None:
        """The EATP audit chain, or None if not configured."""
        return self._audit_chain

    @property
    def audit_dispatcher(self) -> TieredAuditDispatcher | None:
        """The tiered audit dispatcher, or None if not configured."""
        return self._audit_dispatcher

    def _emit_audit(
        self,
        action: str,
        details: dict[str, Any],
        *,
        verification_level: VerificationLevel = VerificationLevel.AUTO_APPROVED,
    ) -> None:
        """Emit an audit anchor if audit_chain or audit_dispatcher is configured.

        When a ``TieredAuditDispatcher`` is configured, anchors are routed
        through it (gradient-aligned persistence tiers, PACT-08).  Otherwise
        the legacy direct-append path is used for backward compatibility.

        Thread-safe: AuditChain has its own internal lock. SqliteAuditLog
        has its own write_lock.

        Args:
            action: The audit action name.
            details: Structured details for the audit record.
            verification_level: The PACT verification level for tier routing.
                Defaults to AUTO_APPROVED for backward compatibility.
        """
        agent_id = f"governance-engine:{self._compiled_org.org_id}"

        # Route through tiered dispatcher if configured (PACT-08)
        if self._audit_dispatcher is not None:
            try:
                from kailash.trust.pact.audit import AuditAnchor as PactAuditAnchor

                anchor = PactAuditAnchor(
                    agent_id=agent_id,
                    action=action,
                    verification_level=verification_level,
                    metadata=details,
                )
                anchor.seal()
                self._audit_dispatcher.dispatch(anchor, verification_level)
            except Exception:
                logger.exception(
                    "Failed to dispatch tiered audit for action=%s -- "
                    "falling through to direct emit",
                    action,
                )
                # Fall through to legacy path on dispatcher failure
                self._emit_audit_direct(action, details, verification_level)
            else:
                # Dispatcher handled it; still emit to SQLite audit log if present
                self._emit_sqlite_audit(action, details)
                return

        # Legacy path: direct append to audit chain
        self._emit_audit_direct(action, details, verification_level)
        self._emit_sqlite_audit(action, details)

    def _emit_audit_direct(
        self,
        action: str,
        details: dict[str, Any],
        verification_level: VerificationLevel = VerificationLevel.AUTO_APPROVED,
    ) -> None:
        """Direct-append to the EATP audit chain (legacy path)."""
        if self._audit_chain is not None:
            try:
                self._audit_chain.append(
                    agent_id=f"governance-engine:{self._compiled_org.org_id}",
                    action=action,
                    verification_level=verification_level,
                    metadata=details,
                )
            except Exception:
                logger.exception(
                    "Failed to emit audit anchor for action=%s -- continuing without audit",
                    action,
                )

    def _emit_sqlite_audit(self, action: str, details: dict[str, Any]) -> None:
        """Emit to SQLite audit log if configured."""
        if self._sqlite_audit_log is not None:
            try:
                self._sqlite_audit_log.append(action, details)
            except Exception:
                logger.exception(
                    "Failed to emit SQLite audit entry for action=%s -- continuing",
                    action,
                )

    def verify_audit_integrity(self) -> tuple[bool, str | None]:
        """Walk the audit chain and verify all content_hash and chain_hash values.

        If no SQLite audit log is configured (memory backend), returns
        (True, None) -- vacuously valid because there are no entries to verify.

        Returns:
            A tuple (is_valid, error_message). is_valid is True if the chain
            is intact. error_message describes the first violation found, or
            None if the chain is valid.
        """
        if self._sqlite_audit_log is None:
            return (True, None)
        return self._sqlite_audit_log.verify_integrity()

    def _emit_audit_unlocked(
        self,
        action: str,
        details: dict[str, Any],
        *,
        verification_level: VerificationLevel = VerificationLevel.AUTO_APPROVED,
    ) -> None:
        """Emit audit anchor from within a locked section.

        Same as _emit_audit but named explicitly to indicate it is safe
        to call while holding self._lock (the audit chain uses its own lock).
        """
        self._emit_audit(action, details, verification_level=verification_level)

    def _emit_observation(
        self,
        event_type: str,
        role_address: str,
        level: str = "info",
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Emit an observation if an ObservationSink is configured.

        Non-blocking: exceptions are logged but never re-raised, ensuring
        that monitoring failures cannot disrupt governance decisions.

        Args:
            event_type: "verdict", "envelope_change", "clearance_change",
                or "bridge_event".
            role_address: D/T/R address of the primary role involved.
            level: "info", "warn", or "critical".
            payload: Event-specific structured data.
            correlation_id: Optional cross-event tracing identifier.
        """
        if self._observation_sink is None:
            return
        try:
            obs = Observation(
                event_type=event_type,
                role_address=role_address,
                timestamp=datetime.now(UTC).isoformat(),
                level=level,
                payload=payload or {},
                correlation_id=correlation_id,
            )
            self._observation_sink.emit(obs)
        except Exception:
            logger.exception(
                "ObservationSink.emit() failed for event_type=%s, role_address=%s "
                "-- continuing without observation",
                event_type,
                role_address,
            )

    # -------------------------------------------------------------------
    # Multi-Level Verification
    # -------------------------------------------------------------------

    def _multi_level_verify(
        self,
        role_address: str,
        action: str,
        ctx: dict[str, Any],
    ) -> tuple[str | None, str]:
        """Walk the accountability chain and verify action against each ancestor's envelope.

        For each ancestor role in the accountability chain (from root to the
        target role), compute that ancestor's effective envelope and evaluate
        the action against it. Return the most restrictive verdict found.

        This prevents a scenario where a leaf role is allowed an action
        but an ancestor envelope blocks it -- the ancestor's restriction
        must be respected due to monotonic tightening.

        Args:
            role_address: The D/T/R address of the role requesting the action.
            action: The action being performed.
            ctx: Context dict with optional cost, task_id, etc.

        Returns:
            A tuple (level, reason) of the most restrictive ancestor verdict,
            or (None, "") if no ancestor blocks the action.
        """
        from kailash.trust.pact.addressing import Address

        try:
            addr = Address.parse(role_address)
        except Exception:
            return (
                "blocked",
                f"Unable to parse role address '{role_address}' for ancestor "
                f"verification -- fail-closed",
            )

        most_restrictive_level: str | None = None
        most_restrictive_reason = ""
        level_order = {"auto_approved": 0, "flagged": 1, "held": 2, "blocked": 3}

        # Walk each ancestor role address (excluding the target itself)
        for ancestor_addr in addr.accountability_chain:
            ancestor_str = str(ancestor_addr)
            if ancestor_str == role_address:
                continue  # Skip self -- already evaluated in main path

            # Compute effective envelope for this ancestor
            ancestor_envelope = self._compute_envelope_locked(ancestor_str)
            if ancestor_envelope is None:
                continue  # Ancestor has no envelope -- not a constraint violation

            # Evaluate the action against this ancestor's envelope
            anc_level, anc_reason = self._evaluate_against_envelope(
                ancestor_envelope, action, ctx
            )

            anc_order = level_order.get(anc_level, 0)
            current_order = (
                level_order.get(most_restrictive_level, -1)
                if most_restrictive_level is not None
                else -1
            )

            if anc_order > current_order:
                most_restrictive_level = anc_level
                most_restrictive_reason = (
                    f"Ancestor envelope at '{ancestor_str}' restricts: {anc_reason}"
                )

        return (most_restrictive_level, most_restrictive_reason)

    # -------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------

    def _find_role_envelope_by_id_locked(self, envelope_id: str) -> RoleEnvelope | None:
        """Find a RoleEnvelope by its ID. Caller must hold self._lock.

        Iterates all role addresses in the compiled org and checks if a stored
        RoleEnvelope matches the given ID. This is used for task envelope
        validation where parent_envelope_id is a RoleEnvelope ID, not an address.

        Args:
            envelope_id: The RoleEnvelope.id to search for.

        Returns:
            The matching RoleEnvelope, or None if not found.
        """
        for address in self._compiled_org.nodes:
            role_env = self._envelope_store.get_role_envelope(address)
            if role_env is not None and role_env.id == envelope_id:
                return role_env
        return None

    def _gather_clearances(self) -> dict[str, RoleClearance]:
        """Gather all clearances from the store for the compiled org.

        Iterates all role addresses in the compiled org and collects any
        clearances that exist in the store.

        Returns:
            Dict mapping role address to RoleClearance.
        """
        clearances: dict[str, RoleClearance] = {}
        for address in self._compiled_org.nodes:
            clr = self._clearance_store.get_clearance(address)
            if clr is not None:
                clearances[address] = clr
        return clearances
