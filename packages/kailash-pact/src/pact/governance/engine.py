# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
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
from datetime import UTC, datetime
from typing import Any

from pact.build.config.schema import (
    ConstraintEnvelopeConfig,
    TrustPostureLevel,
    VerificationLevel,
)
from pact.governance.access import (
    AccessDecision,
    KnowledgeSharePolicy,
    PactBridge,
    can_access,
)
from pact.governance.audit import PactAuditAction, create_pact_audit_details
from pact.governance.clearance import RoleClearance, effective_clearance
from pact.governance.compilation import CompiledOrg, OrgNode, compile_org
from pact.governance.context import GovernanceContext
from pact.governance.envelopes import (
    EffectiveEnvelopeSnapshot,
    RoleEnvelope,
    TaskEnvelope,
    compute_effective_envelope,
    compute_effective_envelope_with_version,
)
from pact.governance.knowledge import KnowledgeItem
from pact.governance.store import (
    AccessPolicyStore,
    ClearanceStore,
    EnvelopeStore,
    MemoryAccessPolicyStore,
    MemoryClearanceStore,
    MemoryEnvelopeStore,
    MemoryOrgStore,
    OrgStore,
)
from pact.governance.verdict import GovernanceVerdict

logger = logging.getLogger(__name__)

__all__ = ["GovernanceEngine"]


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
    ) -> None:
        self._lock = threading.Lock()

        # Initialize stores -- use factory if store_backend specified,
        # otherwise use explicit stores or default to memory
        self._sqlite_audit_log: Any | None = None  # SqliteAuditLog when using sqlite backend

        if (
            store_backend == "sqlite"
            and store_url is not None
            and all(
                s is None for s in (envelope_store, clearance_store, access_policy_store, org_store)
            )
        ):
            from pact.governance.stores.sqlite import (
                SqliteAccessPolicyStore,
                SqliteAuditLog,
                SqliteClearanceStore,
                SqliteEnvelopeStore,
                SqliteOrgStore,
            )

            self._envelope_store: EnvelopeStore = SqliteEnvelopeStore(store_url)
            self._clearance_store: ClearanceStore = SqliteClearanceStore(store_url)
            self._access_policy_store: AccessPolicyStore = SqliteAccessPolicyStore(store_url)
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
                clearance_store if clearance_store is not None else MemoryClearanceStore()
            )
            self._access_policy_store = (
                access_policy_store
                if access_policy_store is not None
                else MemoryAccessPolicyStore()
            )
            self._org_store = org_store if org_store is not None else MemoryOrgStore()
        self._audit_chain = audit_chain

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
    ) -> AccessDecision:
        """Check if a role can access a knowledge item. Thread-safe, fail-closed.

        Delegates to the 5-step access enforcement algorithm using current
        clearances, KSPs, and bridges from the stores.

        Args:
            role_address: The D/T/R address of the requesting role.
            knowledge_item: The knowledge item being accessed.
            posture: The current trust posture level of the role.

        Returns:
            An AccessDecision indicating allow/deny with reason.
        """
        with self._lock:
            try:
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

    def verify_action(
        self,
        role_address: str,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> GovernanceVerdict:
        """The primary decision API. Combines envelope + gradient + access.

        Fail-closed: any error returns BLOCKED verdict.

        Logic:
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
                reason=f"Internal error during action verification -- fail-closed to BLOCKED",
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
        # Step 1: Compute effective envelope with version hash (TOCTOU defense)
        task_id = ctx.get("task_id")
        snapshot = self._compute_envelope_with_version_locked(role_address, task_id=task_id)
        effective = snapshot.envelope
        envelope_version = snapshot.version_hash

        # Step 2+3: Evaluate action against envelope
        level = "auto_approved"
        reason = "No envelope constraints -- action permitted"
        envelope_snapshot: dict[str, Any] | None = None

        if effective is not None:
            envelope_snapshot = effective.model_dump()
            level, reason = self._evaluate_against_envelope(effective, action, ctx)

        # Multi-level VERIFY: walk accountability chain and check each ancestor's
        # effective envelope. Most restrictive verdict wins. This prevents a role
        # from executing an action that is allowed at the leaf but blocked by
        # an ancestor's envelope.
        if level in ("auto_approved", "flagged"):
            ancestor_level, ancestor_reason = self._multi_level_verify(role_address, action, ctx)
            if ancestor_level is not None:
                # Escalate to more restrictive level
                level_order = {"auto_approved": 0, "flagged": 1, "held": 2, "blocked": 3}
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
        blocked_actions = set(envelope.operational.blocked_actions)
        allowed_actions = set(envelope.operational.allowed_actions)

        if action in blocked_actions:
            return (
                "blocked",
                f"Action '{action}' is explicitly blocked by operational constraints",
            )

        # If allowed_actions is explicitly defined (even if empty), the action
        # must be in the list. Empty allowed_actions + envelope exists = nothing allowed.
        # When no envelope exists, the caller gets None (maximally permissive)
        # and _evaluate_against_envelope is never called.
        if action not in allowed_actions:
            return (
                "blocked",
                f"Action '{action}' is not in the allowed actions list: "
                f"{sorted(allowed_actions)}",
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

        # --- All checks passed ---
        return ("auto_approved", f"Action '{action}' is within all constraint dimensions")

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
        """Internal envelope computation. Caller must hold self._lock."""
        # Get all ancestor envelopes for the role
        ancestor_envelopes = self._envelope_store.get_ancestor_envelopes(role_address)

        # Get task envelope if task_id is provided
        task_envelope: TaskEnvelope | None = None
        if task_id is not None:
            task_envelope = self._envelope_store.get_active_task_envelope(role_address, task_id)

        return compute_effective_envelope(
            role_address=role_address,
            role_envelopes=ancestor_envelopes,
            task_envelope=task_envelope,
        )

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
            task_envelope = self._envelope_store.get_active_task_envelope(role_address, task_id)

        return compute_effective_envelope_with_version(
            role_address=role_address,
            role_envelopes=ancestor_envelopes,
            task_envelope=task_envelope,
        )

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
        """Look up a node by its positional address. Thread-safe.

        Args:
            address: A D/T/R positional address string.

        Returns:
            The OrgNode at that address, or None if not found.
        """
        with self._lock:
            return self._compiled_org.nodes.get(address)

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
    # State Mutation API
    # -------------------------------------------------------------------

    def grant_clearance(self, role_address: str, clearance: RoleClearance) -> None:
        """Grant clearance to a role. Thread-safe. Emits audit anchor.

        Args:
            role_address: The D/T/R address of the role.
            clearance: The RoleClearance to grant.
        """
        with self._lock:
            self._clearance_store.grant_clearance(clearance)

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

    def revoke_clearance(self, role_address: str) -> None:
        """Revoke clearance for a role. Thread-safe. Emits audit anchor.

        Args:
            role_address: The D/T/R address whose clearance to revoke.
        """
        with self._lock:
            self._clearance_store.revoke_clearance(role_address)

        self._emit_audit(
            PactAuditAction.CLEARANCE_REVOKED.value,
            create_pact_audit_details(
                PactAuditAction.CLEARANCE_REVOKED,
                role_address=role_address,
                reason="Clearance revoked",
            ),
        )

    def create_bridge(self, bridge: PactBridge) -> None:
        """Create a Cross-Functional Bridge. Thread-safe. Emits audit anchor.

        Args:
            bridge: The PactBridge to create.
        """
        with self._lock:
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
            ),
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

        Args:
            envelope: The RoleEnvelope to set.
        """
        with self._lock:
            self._envelope_store.save_role_envelope(envelope)

        self._emit_audit(
            PactAuditAction.ENVELOPE_CREATED.value,
            create_pact_audit_details(
                PactAuditAction.ENVELOPE_CREATED,
                role_address=envelope.defining_role_address,
                target_address=envelope.target_role_address,
                reason=f"Role envelope '{envelope.id}' set for '{envelope.target_role_address}'",
                envelope_id=envelope.id,
            ),
        )

    def set_task_envelope(self, envelope: TaskEnvelope) -> None:
        """Set a task envelope. Thread-safe. Emits audit anchor.

        Args:
            envelope: The TaskEnvelope to set.
        """
        with self._lock:
            self._envelope_store.save_task_envelope(envelope)

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

    # -------------------------------------------------------------------
    # Audit API
    # -------------------------------------------------------------------

    @property
    def audit_chain(self) -> Any | None:
        """The EATP audit chain, or None if not configured."""
        return self._audit_chain

    def _emit_audit(self, action: str, details: dict[str, Any]) -> None:
        """Emit an audit anchor if audit_chain is configured.

        Thread-safe: AuditChain has its own internal lock. SqliteAuditLog
        has its own write_lock.

        Args:
            action: The audit action name.
            details: Structured details for the audit record.
        """
        # Emit to EATP audit chain if configured
        if self._audit_chain is not None:
            try:
                self._audit_chain.append(
                    agent_id=f"governance-engine:{self._compiled_org.org_id}",
                    action=action,
                    verification_level=VerificationLevel.AUTO_APPROVED,
                    metadata=details,
                )
            except Exception:
                logger.exception(
                    "Failed to emit audit anchor for action=%s -- continuing without audit",
                    action,
                )

        # Also emit to SQLite audit log if configured
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

    def _emit_audit_unlocked(self, action: str, details: dict[str, Any]) -> None:
        """Emit audit anchor from within a locked section.

        Same as _emit_audit but named explicitly to indicate it is safe
        to call while holding self._lock (the audit chain uses its own lock).
        """
        self._emit_audit(action, details)

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
        from pact.governance.addressing import Address

        try:
            addr = Address.parse(role_address)
        except Exception:
            return (None, "")

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
                continue

            # Evaluate the action against this ancestor's envelope
            anc_level, anc_reason = self._evaluate_against_envelope(ancestor_envelope, action, ctx)

            anc_order = level_order.get(anc_level, 0)
            current_order = level_order.get(most_restrictive_level, -1)

            if anc_order > current_order:
                most_restrictive_level = anc_level
                most_restrictive_reason = (
                    f"Ancestor envelope at '{ancestor_str}' restricts: {anc_reason}"
                )

        return (most_restrictive_level, most_restrictive_reason)

    # -------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------

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
