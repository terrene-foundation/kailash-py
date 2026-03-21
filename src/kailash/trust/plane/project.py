# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""TrustPlane project with EATP trust tracking.

A TrustProject wraps EATP operations for any collaborative workflow:
- Genesis Record establishes the project root of trust
- Decision records are Audit Anchors with Reasoning Traces
- Milestones are FULL-verification checkpoints
- All state persists to a trust-plane directory as JSON

Usage:
    project = await TrustProject.create(
        trust_dir="workspaces/care-thesis/trust-plane",
        project_name="CARE Thesis Rewrite",
        author="Dr. Jack Hong",
        constraints=["publication_claims_rules", "honest_limitations_required"],
    )

    await project.record_decision(DecisionRecord(
        decision_type=DecisionType.SCOPE,
        decision="CARE must be pure philosophy, no EATP/CO details",
        rationale="Mixing framework with application confounds debate",
        alternatives=["Keep integrated", "Split into 3 papers"],
        confidence=0.9,
    ))
"""

import asyncio
import fnmatch
import hashlib
import hmac as hmac_mod
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kailash.trust.operations import CapabilityRequest, TrustKeyManager, TrustOperations
from kailash.trust.authority import AuthorityPermission, OrganizationalAuthority
from kailash.trust.chain import (
    ActionResult,
    AuthorityType,
    CapabilityType,
    VerificationResult,
)
from kailash.trust.signing.crypto import generate_keypair
from kailash.trust.enforce.shadow import ShadowEnforcer
from kailash.trust.enforce.strict import HeldBehavior, StrictEnforcer, Verdict
from kailash.trust.posture.postures import (
    PostureStateMachine,
    PostureTransitionRequest,
    TrustPosture,
)
from kailash.trust.reasoning.traces import ConfidentialityLevel, ReasoningTrace
from kailash.trust.chain_store.filesystem import FilesystemStore

from kailash.trust.plane.exceptions import (
    BudgetExhaustedError,
    ConstraintViolationError,
    TrustPlaneError,
)
from kailash.trust.plane.models import (
    ConstraintEnvelope,
    DecisionRecord,
    EscalationRecord,
    ExecutionRecord,
    InterventionRecord,
    MilestoneRecord,
    ProjectManifest,
    _decision_type_value,
)
from kailash.trust._locking import (
    atomic_write as _atomic_write,
    file_lock as _file_lock,
    safe_read_json as _safe_read_json,
)
from kailash.trust.plane.session import AuditSession
from kailash.trust.plane.store import TrustPlaneStore
from kailash.trust.plane.store.filesystem import FileSystemTrustPlaneStore

logger = logging.getLogger(__name__)

__all__ = [
    "TrustProject",
]


class _AuthorityRegistry:
    """Minimal authority registry for trust projects."""

    def __init__(self) -> None:
        self._authorities: dict[str, OrganizationalAuthority] = {}

    async def initialize(self) -> None:
        pass

    def register(self, authority: OrganizationalAuthority) -> None:
        self._authorities[authority.id] = authority

    async def get_authority(
        self, authority_id: str, include_inactive: bool = False
    ) -> OrganizationalAuthority:
        authority = self._authorities.get(authority_id)
        if authority is None:
            raise KeyError(f"Authority not found: {authority_id}")
        return authority

    async def update_authority(self, authority: OrganizationalAuthority) -> None:
        self._authorities[authority.id] = authority


def set_private_file_permissions(path: Path) -> None:
    """Restrict file access to the owning user only.

    On POSIX: chmod 0o600 (owner read/write only).
    On Windows: attempts to set a DACL via pywin32 restricting access
    to the current user's SID. Falls back to a warning if pywin32
    is not installed.
    """
    import sys as _sys

    if _sys.platform == "win32":
        try:
            import win32security  # type: ignore[import-untyped]
            import win32api  # type: ignore[import-untyped]
            import ntsecuritycon as con  # type: ignore[import-untyped]

            username = win32api.GetUserName()
            user_sid = win32security.LookupAccountName(None, username)[0]
            dacl = win32security.ACL()
            dacl.AddAccessAllowedAce(
                win32security.ACL_REVISION,
                con.FILE_GENERIC_READ | con.FILE_GENERIC_WRITE,
                user_sid,
            )
            sd = win32security.GetFileSecurity(
                str(path), win32security.DACL_SECURITY_INFORMATION
            )
            sd.SetSecurityDescriptorDacl(True, dacl, False)
            win32security.SetFileSecurity(
                str(path), win32security.DACL_SECURITY_INFORMATION, sd
            )
        except ImportError:
            logger.warning(
                "Private file %s is not access-controlled on this platform. "
                "Install pywin32 for key protection: pip install trust-plane[windows]",
                path,
            )
    else:
        os.chmod(path, 0o600)


def _save_keys(keys_dir: Path, private_key: str, public_key: str) -> None:
    """Persist keypair to disk with restricted permissions.

    Uses os.open() with mode 0o600 to create the private key file
    atomically with correct permissions — no world-readable window.
    On Windows, applies ACL-based protection via set_private_file_permissions().
    """
    keys_dir.mkdir(parents=True, exist_ok=True)

    priv_path = keys_dir / "private.key"
    pub_path = keys_dir / "public.key"

    # Create private key with restricted permissions from the start.
    # O_NOFOLLOW prevents writing through a symlink (attacker could redirect
    # the key write to an attacker-controlled location).
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(priv_path), flags, 0o600)
    try:
        os.write(fd, private_key.encode())
    finally:
        os.close(fd)

    # Apply platform-aware permissions (Windows ACL on win32)
    set_private_file_permissions(priv_path)

    # Public key also uses O_NOFOLLOW to prevent symlink redirection.
    # Mode 0o644 — public key is not secret but should not be world-writable.
    pub_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        pub_flags |= os.O_NOFOLLOW
    pub_fd = os.open(str(pub_path), pub_flags, 0o644)
    try:
        os.write(pub_fd, public_key.encode())
    finally:
        os.close(pub_fd)


def _safe_read_text(path: Path) -> str:
    """Read a text file with O_NOFOLLOW to prevent symlink attacks."""
    import errno as _errno

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(path), flags)
    except OSError as e:
        if e.errno == _errno.ELOOP:
            raise OSError(f"Refusing to read symlink (possible attack): {path}") from e
        raise
    try:
        f = os.fdopen(fd, "r")
    except Exception:
        os.close(fd)  # fdopen failed — close fd to prevent leak
        raise
    with f:
        return f.read()


def _safe_hash_file(path: Path) -> str:
    """SHA-256 hash of a file's contents with O_NOFOLLOW symlink protection."""
    import errno as _errno

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(path), flags)
    except OSError as e:
        if e.errno == _errno.ELOOP:
            raise OSError(f"Refusing to hash symlink (possible attack): {path}") from e
        raise
    try:
        f = os.fdopen(fd, "rb")
    except Exception:
        os.close(fd)
        raise
    h = hashlib.sha256()
    with f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_keys(keys_dir: Path) -> tuple[str, str]:
    """Load persisted keypair from disk.

    Uses O_NOFOLLOW to prevent symlink-based key substitution.

    Returns:
        (private_key, public_key)

    Raises:
        FileNotFoundError: If keys haven't been persisted
    """
    priv_path = keys_dir / "private.key"
    pub_path = keys_dir / "public.key"

    try:
        private = _safe_read_text(priv_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"Keys not found at {keys_dir}")
    try:
        public = _safe_read_text(pub_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"Keys not found at {keys_dir}")

    return private, public


class TrustProject:
    """An EATP-tracked project.

    Manages the full lifecycle: initialization (Genesis Record),
    decision recording (Audit Anchors + Reasoning Traces),
    milestone tracking, and trust chain verification.

    All state is persisted to the trust directory as JSON files:
        trust-plane/
            manifest.json       # Project identity and EATP references
            genesis.json        # The Genesis Record
            keys/               # Persisted signing keys (private.key is 600)
            chains/             # EATP FilesystemStore (persistent trust chains)
            decisions/          # Numbered decision records
            milestones/         # Milestone checkpoints
            anchors/            # Raw EATP Audit Anchors
    """

    def __init__(
        self,
        trust_dir: Path,
        manifest: ProjectManifest,
        ops: TrustOperations,
        store: FilesystemStore,
        agent_id: str,
        last_anchor_id: str | None = None,
        tp_store: TrustPlaneStore | None = None,
    ) -> None:
        self._dir = trust_dir
        self._manifest = manifest
        self._ops = ops
        self._store = store
        self._agent_id = agent_id
        if tp_store is not None:
            self._tp_store: TrustPlaneStore = tp_store
        else:
            fs_store = FileSystemTrustPlaneStore(trust_dir)
            fs_store.initialize()
            self._tp_store = fs_store
        self._lock_path = trust_dir / ".lock"
        self._last_anchor_id = last_anchor_id
        # In-process async lock to prevent chain fork when multiple
        # coroutines call record_decision/record_execution concurrently.
        # Complements the cross-process fcntl.flock in _file_lock.
        self._async_lock = asyncio.Lock()
        # Enforcement mode: "strict" (default) or "shadow"
        enforcement_mode = self._manifest.metadata.get("enforcement_mode", "strict")
        self._shadow_enforcer = ShadowEnforcer()
        self._strict_enforcer = StrictEnforcer(on_held=HeldBehavior.RAISE)
        self._enforcement_mode = enforcement_mode
        self._enforcer = (
            self._shadow_enforcer
            if enforcement_mode == "shadow"
            else self._strict_enforcer
        )
        self._session: AuditSession | None = None
        self._posture_machine = PostureStateMachine(
            default_posture=TrustPosture.SUPERVISED,
        )
        # Restore persisted posture from manifest
        posture_name = self._manifest.metadata.get("trust_posture")
        if posture_name:
            try:
                self._posture_machine.set_posture(
                    self._agent_id, TrustPosture(posture_name)
                )
            except (ValueError, Exception):
                pass  # Invalid posture name — use default

    @classmethod
    async def create(
        cls,
        trust_dir: str | Path,
        project_name: str,
        author: str,
        constraints: list[str] | None = None,
        constraint_envelope: ConstraintEnvelope | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "TrustProject":
        """Create a new project with EATP Genesis Record.

        This is the equivalent of EATP ESTABLISH — it creates the root
        of trust for the entire project.

        Args:
            trust_dir: Directory for trust plane files
            project_name: Human-readable project name
            author: Author name (the human authority)
            constraints: Legacy project constraints (list of strings)
            constraint_envelope: Structured constraints across all 5 EATP dimensions
            metadata: Additional project metadata

        Returns:
            Initialized TrustProject with Genesis Record
        """
        trust_path = Path(trust_dir)
        for subdir in ["decisions", "milestones", "anchors", "keys", "chains"]:
            (trust_path / subdir).mkdir(parents=True, exist_ok=True)

        # Create TrustPlane store for record persistence
        tp_store = FileSystemTrustPlaneStore(trust_path)
        tp_store.initialize()

        constraints = constraints or []
        metadata = metadata or {}

        # Build constraint envelope if not provided
        if constraint_envelope is None and constraints:
            constraint_envelope = ConstraintEnvelope.from_legacy(constraints, author)
        elif constraint_envelope is not None:
            constraint_envelope.signed_by = constraint_envelope.signed_by or author

        # Generate project ID from name + timestamp + nonce
        now = datetime.now(timezone.utc)
        nonce = secrets.token_hex(4)
        project_id = f"proj-{hashlib.sha256(f'{project_name}:{now.isoformat()}:{nonce}'.encode()).hexdigest()[:12]}"

        # Create EATP infrastructure with persistent FilesystemStore
        store = FilesystemStore(str(trust_path / "chains"))
        await store.initialize()

        key_mgr = TrustKeyManager()
        private_key, public_key = generate_keypair()
        key_id = f"key-{project_id}"
        key_mgr.register_key(key_id, private_key)

        # Persist keys for cross-session identity
        _save_keys(trust_path / "keys", private_key, public_key)

        # F4: Remove private key from local scope after registration and save
        del private_key

        authority_id = f"author-{project_id}"
        registry = _AuthorityRegistry()
        registry.register(
            OrganizationalAuthority(
                id=authority_id,
                name=author,
                authority_type=AuthorityType.HUMAN,
                public_key=public_key,
                signing_key_id=key_id,
                permissions=[
                    AuthorityPermission.CREATE_AGENTS,
                    AuthorityPermission.DELEGATE_TRUST,
                    AuthorityPermission.GRANT_CAPABILITIES,
                ],
                metadata={
                    "project": project_name,
                    "author": author,
                    "created_at": now.isoformat(),
                },
            )
        )

        ops = TrustOperations(
            authority_registry=registry,
            key_manager=key_mgr,
            trust_store=store,
        )

        # ESTABLISH — create the trust agent's chain
        agent_id = f"trust-agent-{project_id}"
        chain = await ops.establish(
            agent_id=agent_id,
            authority_id=authority_id,
            capabilities=[
                CapabilityRequest(
                    capability="draft_content",
                    capability_type=CapabilityType.ACTION,
                    constraints=["audit_required"],
                ),
                CapabilityRequest(
                    capability="record_decision",
                    capability_type=CapabilityType.ACTION,
                    constraints=["audit_required"],
                ),
                CapabilityRequest(
                    capability="cross_reference",
                    capability_type=CapabilityType.ACCESS,
                ),
            ],
            constraints=constraints,
        )

        # Build manifest
        manifest = ProjectManifest(
            project_id=project_id,
            project_name=project_name,
            author=author,
            created_at=now,
            genesis_id=chain.genesis.id,
            chain_hash=chain.hash(),
            authority_public_key=public_key,
            constraints=constraints,
            constraint_envelope=constraint_envelope,
            metadata=metadata,
        )

        project = cls(
            trust_dir=trust_path,
            manifest=manifest,
            ops=ops,
            store=store,
            agent_id=agent_id,
            tp_store=tp_store,
        )

        # Persist genesis and manifest
        project._write_json(
            "genesis.json",
            {
                "genesis_id": chain.genesis.id,
                "authority_id": chain.genesis.authority_id,
                "agent_id": chain.genesis.agent_id,
                "chain_hash": chain.hash(),
                "capabilities": [cap.capability for cap in chain.capabilities],
                "constraints": constraints,
                "created_at": now.isoformat(),
                "public_key": public_key,
            },
        )
        project._tp_store.store_manifest(manifest)

        # Persist constraint envelope separately for easy inspection
        if constraint_envelope is not None:
            project._write_json(
                "constraint-envelope.json", constraint_envelope.to_dict()
            )

        logger.info(
            "Created project '%s' (genesis: %s)",
            project_name,
            chain.genesis.id,
        )
        return project

    @classmethod
    async def load(cls, trust_dir: str | Path) -> "TrustProject":
        """Load an existing project from its trust plane directory.

        Reconstructs the EATP infrastructure using the persisted keys,
        preserving the original signing identity across sessions.

        Args:
            trust_dir: Directory containing trust plane files

        Returns:
            Loaded TrustProject

        Raises:
            FileNotFoundError: If manifest.json doesn't exist
        """
        trust_path = Path(trust_dir)
        manifest_path = trust_path / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"No project found at {trust_path}")

        # Create TrustPlane store for record persistence
        tp_store = FileSystemTrustPlaneStore(trust_path)
        tp_store.initialize()

        manifest = tp_store.get_manifest()

        # Recreate EATP infrastructure with persistent FilesystemStore
        chains_dir = trust_path / "chains"
        chains_dir.mkdir(parents=True, exist_ok=True)
        store = FilesystemStore(str(chains_dir))
        await store.initialize()

        key_mgr = TrustKeyManager()
        key_id = f"key-{manifest.project_id}"

        # Load persisted keys — preserves signing identity across sessions
        keys_dir = trust_path / "keys"
        try:
            private_key, public_key = _load_keys(keys_dir)
        except FileNotFoundError:
            # Backward compat: pre-key-persistence projects get new keys
            logger.warning(
                "No persisted keys found for %s — generating new keypair. "
                "Cross-session signature verification will not work for "
                "actions before this load.",
                manifest.project_id,
            )
            private_key, public_key = generate_keypair()
            _save_keys(keys_dir, private_key, public_key)

        key_mgr.register_key(key_id, private_key)

        # F4: Remove private key from local scope after registration
        del private_key

        authority_id = f"author-{manifest.project_id}"
        registry = _AuthorityRegistry()
        registry.register(
            OrganizationalAuthority(
                id=authority_id,
                name=manifest.author,
                authority_type=AuthorityType.HUMAN,
                public_key=public_key,
                signing_key_id=key_id,
                permissions=[
                    AuthorityPermission.CREATE_AGENTS,
                    AuthorityPermission.DELEGATE_TRUST,
                    AuthorityPermission.GRANT_CAPABILITIES,
                ],
            )
        )

        ops = TrustOperations(
            authority_registry=registry,
            key_manager=key_mgr,
            trust_store=store,
        )

        agent_id = f"trust-agent-{manifest.project_id}"

        # Reconnect to existing chain — do NOT call establish() which
        # would create a NEW genesis record, severing the chain.
        try:
            chain = await store.get_chain(agent_id)
            logger.info(
                "Loaded existing chain for '%s' (genesis: %s)",
                manifest.project_name,
                chain.genesis.id,
            )
        except Exception as e:
            # Chain not in FilesystemStore — either a pre-FilesystemStore
            # project or first load after migration. Re-establish.
            logger.warning(
                "No chain found in store for %s (%s) — re-establishing. "
                "This is expected for projects created before FilesystemStore.",
                agent_id,
                e,
            )
            await ops.establish(
                agent_id=agent_id,
                authority_id=authority_id,
                capabilities=[
                    CapabilityRequest(
                        capability="draft_content",
                        capability_type=CapabilityType.ACTION,
                    ),
                    CapabilityRequest(
                        capability="record_decision",
                        capability_type=CapabilityType.ACTION,
                    ),
                    CapabilityRequest(
                        capability="cross_reference",
                        capability_type=CapabilityType.ACCESS,
                    ),
                ],
                constraints=manifest.constraints,
            )

        # Reconstruct last_anchor_id from existing anchor files
        last_anchor_id = None
        anchors = tp_store.list_anchors()
        if anchors:
            last_anchor_id = anchors[-1].get("anchor_id")

        project = cls(
            trust_dir=trust_path,
            manifest=manifest,
            ops=ops,
            store=store,
            agent_id=agent_id,
            last_anchor_id=last_anchor_id,
            tp_store=tp_store,
        )

        # Restore active session if one exists
        session_path = trust_path / "session.json"
        if session_path.exists():
            session_data = _safe_read_json(session_path)
            session = AuditSession.from_dict(session_data)
            if session.is_active:
                project._session = session
                logger.info("Restored active session %s", session.session_id)

        # Detect abandoned sessions: session.json exists but
        # process died before end_session(). Close with abandoned anchor.
        if project._session and not project._session.is_active:
            logger.warning(
                "Found inactive session %s on disk — cleaning up",
                project._session.session_id,
            )
            session_path.unlink(missing_ok=True)
            project._session = None

        return project

    def check(self, action: str, context: dict[str, Any] | None = None) -> Verdict:
        """Check whether an action is allowed by the constraint envelope.

        Returns AUTO_APPROVED, FLAGGED, HELD, or BLOCKED.
        Does NOT record anything — just checks constraints.

        This is the gating function that the MCP server will expose
        as trust_check.

        Args:
            action: The action to check (e.g., "record_decision", "fabricate")
            context: Optional context for the check

        Returns:
            Verdict enum value
        """
        envelope = self._manifest.constraint_envelope
        if envelope is None:
            return Verdict.AUTO_APPROVED

        # Check blocked actions (case-insensitive)
        dt_value = (context or {}).get("decision_type", action)
        blocked_lower = {a.lower() for a in envelope.operational.blocked_actions}
        if dt_value.lower() in blocked_lower:
            return Verdict.BLOCKED

        # Check blocked paths (normalized + case-insensitive)
        # Two-stage normalization:
        # 1. normalize_resource_path: separator normalization (backslash -> forward slash)
        # 2. posixpath.normpath: resolve '..' and '.' segments (path traversal defense)
        import posixpath

        from kailash.trust.pathutils import normalize_resource_path

        resource = (context or {}).get("resource", "")
        norm_resource = (
            posixpath.normpath(normalize_resource_path(resource)).lower()
            if resource
            else ""
        )
        for blocked in envelope.data_access.blocked_paths:
            norm_blocked = posixpath.normpath(normalize_resource_path(blocked)).lower()
            if norm_resource.startswith(norm_blocked):
                return Verdict.BLOCKED
        # Check blocked patterns (glob matching)
        # Both args normalized to forward slashes per path normalization convention
        for pattern in envelope.data_access.blocked_patterns:
            if fnmatch.fnmatch(
                norm_resource,
                posixpath.normpath(normalize_resource_path(pattern)).lower(),
            ):
                return Verdict.BLOCKED

        # Check financial constraints (budget limits)
        import math as _math

        ctx = context or {}
        action_cost = float(ctx.get("cost", 0.0))
        # Fail-closed on NaN/Inf/negative cost — Pattern 5 (isfinite)
        if not _math.isfinite(action_cost) or action_cost < 0:
            return Verdict.BLOCKED
        if envelope.financial.budget_tracking:
            # Per-action cost limit
            if (
                envelope.financial.max_cost_per_action is not None
                and action_cost > envelope.financial.max_cost_per_action
            ):
                return Verdict.BLOCKED
            # Session cost limit
            if (
                envelope.financial.max_cost_per_session is not None
                and self._session is not None
            ):
                projected = self._session.session_cost + action_cost
                if projected > envelope.financial.max_cost_per_session:
                    return Verdict.BLOCKED

        # Use the enforcer for more nuanced classification
        vr = VerificationResult(valid=True)
        try:
            if self._enforcement_mode == "shadow":
                result = self._shadow_enforcer.check(
                    self._agent_id, action, vr, metadata=context
                )
            else:
                result = self._strict_enforcer.enforce(
                    self._agent_id, action, vr, metadata=context
                )
            return result
        except Exception:
            # Enforcer failure: degrade to HELD — human must review.
            # Fail-to-human is safer than fail-open (AUTO_APPROVED) or
            # fail-closed (BLOCKED). The human can inspect the audit trail
            # and decide whether to proceed.
            logger.warning(
                "StrictEnforcer raised unexpected error for action '%s' — "
                "degrading to HELD for human review.",
                action,
                exc_info=True,
            )
            return Verdict.HELD

    async def record_decision(self, decision: DecisionRecord) -> str:
        """Record a decision with EATP audit trail.

        Checks the constraint envelope BEFORE recording. If the action
        is BLOCKED, raises an error. If HELD, raises for human review.
        FLAGGED actions proceed with a warning logged.

        Creates both:
        1. A human-readable decision record (JSON in decisions/)
        2. An EATP Audit Anchor with Reasoning Trace (JSON in anchors/)

        Args:
            decision: The decision to record

        Returns:
            The decision ID

        Raises:
            ConstraintViolationError: If the action is BLOCKED
        """
        async with self._async_lock:
            return await self._record_decision_locked(decision)

    async def _record_decision_locked(self, decision: DecisionRecord) -> str:
        # Enforce constraints before recording (includes budget check)
        action_cost = getattr(decision, "cost", 0.0) or 0.0
        verdict = self.check(
            "record_decision",
            {
                "decision_type": _decision_type_value(decision.decision_type),
                "content_hash": decision.content_hash(),
                "cost": action_cost,
            },
        )
        if verdict == Verdict.BLOCKED:
            # Determine if blocked by budget or by operational constraint
            envelope = self._manifest.constraint_envelope
            if (
                envelope is not None
                and envelope.financial.budget_tracking
                and self._session is not None
            ):
                projected = self._session.session_cost + action_cost
                if (
                    envelope.financial.max_cost_per_session is not None
                    and projected > envelope.financial.max_cost_per_session
                ):
                    raise BudgetExhaustedError(
                        f"Session budget exceeded: "
                        f"${projected:.2f} > ${envelope.financial.max_cost_per_session:.2f}",
                        session_cost=self._session.session_cost,
                        budget_limit=envelope.financial.max_cost_per_session,
                        action_cost=action_cost,
                    )
                if (
                    envelope.financial.max_cost_per_action is not None
                    and action_cost > envelope.financial.max_cost_per_action
                ):
                    raise BudgetExhaustedError(
                        f"Action cost ${action_cost:.2f} exceeds per-action "
                        f"limit ${envelope.financial.max_cost_per_action:.2f}",
                        session_cost=(
                            self._session.session_cost if self._session else 0.0
                        ),
                        budget_limit=envelope.financial.max_cost_per_action,
                        action_cost=action_cost,
                    )
            raise ConstraintViolationError(
                f"Action blocked by constraint envelope: "
                f"decision type '{_decision_type_value(decision.decision_type)}' "
                f"is in blocked_actions"
            )
        if verdict == Verdict.FLAGGED:
            logger.warning(
                "Decision '%s' is FLAGGED — proceeding with audit trail",
                decision.decision_id,
            )
        # Create EATP Reasoning Trace from the decision
        reasoning = ReasoningTrace(
            decision=decision.decision,
            rationale=decision.rationale,
            confidentiality=ConfidentialityLevel(decision.confidentiality),
            timestamp=decision.timestamp,
            alternatives_considered=decision.alternatives,
            evidence=decision.evidence,
            methodology=_decision_type_value(decision.decision_type),
            confidence=decision.confidence,
        )

        # Create EATP Audit Anchor with parent chain link
        ctx = {
            "decision_type": _decision_type_value(decision.decision_type),
            "verification_grade": decision.review_requirement.value,
            "content_hash": decision.content_hash(),
            "parent_anchor_id": self._last_anchor_id,
        }
        if self._session is not None and self._session.is_active:
            ctx.update(self._session.context_data())
            self._session.record_action("record_decision", cost=action_cost)

        anchor = await self._ops.audit(
            agent_id=self._agent_id,
            action="record_decision",
            resource=f"decision/{decision.decision_id}",
            result=ActionResult.SUCCESS,
            context_data=ctx,
            reasoning_trace=reasoning,
        )
        self._last_anchor_id = anchor.id

        with _file_lock(self._lock_path):
            # Re-read manifest inside lock to get current sequence number
            self._reload_manifest()

            seq = self._manifest.total_decisions
            audit_seq = self._manifest.total_audits

            # Persist the decision record
            self._write_json(
                f"decisions/{seq:04d}-{decision.decision_id}.json",
                {
                    **decision.to_dict(),
                    "content_hash": decision.content_hash(),
                    "eatp_anchor_id": anchor.id,
                    "eatp_chain_hash": anchor.trust_chain_hash,
                },
            )

            # Persist the raw EATP anchor with parent chain link
            # Include reasoning_trace_hash for dual-binding (EATP v2.2)
            self._write_json(
                f"anchors/{audit_seq:04d}-{anchor.id}.json",
                {
                    "anchor_id": anchor.id,
                    "parent_anchor_id": anchor.context.get("parent_anchor_id"),
                    "agent_id": anchor.agent_id,
                    "action": anchor.action,
                    "resource": anchor.resource,
                    "result": anchor.result.value,
                    "trust_chain_hash": anchor.trust_chain_hash,
                    "signature": anchor.signature or "",
                    "timestamp": anchor.timestamp.isoformat(),
                    "context": anchor.context,
                    "reasoning_trace": reasoning.to_dict(),
                    "reasoning_trace_hash": reasoning.content_hash_hex(),
                },
            )

            # Update manifest
            self._manifest.total_decisions += 1
            self._manifest.total_audits += 1
            self._tp_store.store_manifest(self._manifest)

        logger.info(
            "Recorded decision %s (anchor: %s)", decision.decision_id, anchor.id
        )
        return decision.decision_id

    async def record_milestone(
        self,
        version: str,
        description: str,
        file_path: str = "",
    ) -> str:
        """Record a milestone with EATP audit trail.

        Milestones are FULL-verification events. The file (if provided)
        is hashed for tamper detection.

        Args:
            version: Version string (e.g., "v0.1")
            description: What this milestone represents
            file_path: Path to the file (will be hashed)

        Returns:
            The milestone ID
        """
        async with self._async_lock:
            return await self._record_milestone_locked(version, description, file_path)

    async def _record_milestone_locked(
        self, version: str, description: str, file_path: str = ""
    ) -> str:
        file_hash = ""
        if file_path:
            path = Path(file_path)
            if path.exists():
                file_hash = _safe_hash_file(path)

        milestone = MilestoneRecord(
            version=version,
            description=description,
            file_path=file_path,
            file_hash=file_hash,
            decision_count=self._manifest.total_decisions,
        )

        # EATP Audit Anchor for the milestone with parent chain link
        ctx = {
            "version": version,
            "file_hash": file_hash,
            "decisions_since_last": milestone.decision_count,
            "parent_anchor_id": self._last_anchor_id,
        }
        if self._session is not None and self._session.is_active:
            ctx.update(self._session.context_data())
            self._session.record_action("create_milestone")

        anchor = await self._ops.audit(
            agent_id=self._agent_id,
            action="create_milestone",
            resource=f"milestone/{milestone.milestone_id}",
            result=ActionResult.SUCCESS,
            context_data=ctx,
        )
        self._last_anchor_id = anchor.id

        with _file_lock(self._lock_path):
            self._reload_manifest()

            seq = self._manifest.total_milestones
            audit_seq = self._manifest.total_audits
            self._write_json(
                f"milestones/{seq:04d}-{milestone.milestone_id}.json",
                {
                    **milestone.to_dict(),
                    "eatp_anchor_id": anchor.id,
                    "eatp_chain_hash": anchor.trust_chain_hash,
                },
            )

            # Persist the raw EATP anchor (milestones are audit events too)
            self._write_json(
                f"anchors/{audit_seq:04d}-{anchor.id}.json",
                {
                    "anchor_id": anchor.id,
                    "parent_anchor_id": anchor.context.get("parent_anchor_id"),
                    "agent_id": anchor.agent_id,
                    "action": anchor.action,
                    "resource": anchor.resource,
                    "result": anchor.result.value,
                    "trust_chain_hash": anchor.trust_chain_hash,
                    "signature": anchor.signature or "",
                    "timestamp": anchor.timestamp.isoformat(),
                    "context": anchor.context,
                },
            )

            self._manifest.total_milestones += 1
            self._manifest.total_audits += 1
            self._tp_store.store_manifest(self._manifest)

        logger.info("Recorded milestone %s (%s)", version, milestone.milestone_id)
        return milestone.milestone_id

    async def verify(self) -> dict[str, Any]:
        """Verify the project's trust chain integrity.

        Performs three levels of verification:
        1. EATP chain verification (genesis, capabilities, signatures)
        2. Anchor parent chain verification (detect gaps, insertions, reordering)
        3. Decision content hash verification (detect tampered decision records)
        4. Key consistency check

        Returns:
            Verification report dictionary
        """
        async with self._async_lock:
            return await self._verify_locked()

    async def _verify_locked(self) -> dict[str, Any]:
        integrity_issues: list[str] = []
        chain_valid = True

        # 1. EATP chain verification via store
        try:
            chain = await self._store.get_chain(self._agent_id)
            if chain.genesis.id != self._manifest.genesis_id:
                integrity_issues.append(
                    f"genesis mismatch: store has {chain.genesis.id}, "
                    f"manifest has {self._manifest.genesis_id}"
                )
                chain_valid = False
        except Exception as e:
            integrity_issues.append(f"chain not found in store: {e}")
            chain_valid = False

        # 2. Anchor parent chain verification
        anchors_dir = self._dir / "anchors"
        anchor_files = (
            sorted(anchors_dir.glob("*.json")) if anchors_dir.exists() else []
        )

        expected_parent: str | None = None
        for af in anchor_files:
            data = _safe_read_json(af)
            actual_parent = data.get("parent_anchor_id") or data.get("context", {}).get(
                "parent_anchor_id"
            )
            anchor_id = data.get("anchor_id", af.stem)

            if actual_parent != expected_parent:
                integrity_issues.append(
                    f"{af.name}: parent chain broken "
                    f"(expected {expected_parent}, got {actual_parent})"
                )
                chain_valid = False
            expected_parent = anchor_id

        # 3. Decision content hash verification
        decisions_dir = self._dir / "decisions"
        decision_files = (
            sorted(decisions_dir.glob("*.json")) if decisions_dir.exists() else []
        )

        for df in decision_files:
            data = _safe_read_json(df)
            stored_hash = data.get("content_hash", "")
            record = DecisionRecord.from_dict(data)
            computed_hash = record.content_hash()
            if stored_hash and not hmac_mod.compare_digest(stored_hash, computed_hash):
                integrity_issues.append(f"{df.name}: hash mismatch (tampered?)")
                chain_valid = False

        # 4. Key consistency
        keys_dir = self._dir / "keys"
        try:
            _, stored_public = _load_keys(keys_dir)
            if stored_public != self._manifest.authority_public_key:
                integrity_issues.append(
                    "public key mismatch between keys/ and manifest"
                )
                chain_valid = False
        except FileNotFoundError:
            integrity_issues.append("signing keys missing from keys/ directory")
            chain_valid = False

        # Map posture to verification level
        posture = self.posture
        posture_level_map = {
            TrustPosture.PSEUDO_AGENT: "FULL",
            TrustPosture.SUPERVISED: "FULL",
            TrustPosture.SHARED_PLANNING: "STANDARD",
            TrustPosture.CONTINUOUS_INSIGHT: "STANDARD",
            TrustPosture.DELEGATED: "QUICK",
        }
        verification_level = posture_level_map.get(posture, "FULL")

        return {
            "project_id": self._manifest.project_id,
            "project_name": self._manifest.project_name,
            "chain_valid": chain_valid,
            "total_decisions": self._manifest.total_decisions,
            "total_milestones": self._manifest.total_milestones,
            "total_audits": self._manifest.total_audits,
            "total_anchors": len(anchor_files),
            "integrity_issues": integrity_issues,
            "genesis_id": self._manifest.genesis_id,
            "trust_posture": posture.value,
            "verification_level": verification_level,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_decisions(self) -> list[DecisionRecord]:
        """Load all decision records from disk."""
        return self._tp_store.list_decisions()

    def get_milestones(self) -> list[MilestoneRecord]:
        """Load all milestone records from disk."""
        return self._tp_store.list_milestones()

    @property
    def manifest(self) -> ProjectManifest:
        return self._manifest

    @property
    def constraint_envelope(self) -> ConstraintEnvelope | None:
        return self._manifest.constraint_envelope

    @property
    def session(self) -> AuditSession | None:
        return self._session

    async def start_session(
        self, tracked_paths: list[str | Path] | None = None
    ) -> AuditSession:
        """Start a new audit session.

        Creates a session-start anchor and returns the AuditSession.
        All subsequent record_decision/record_milestone calls will
        include the session_id in their anchor context.

        Args:
            tracked_paths: Directories to track for file changes.
                If provided, file hashes are captured at session start
                and end, with a diff included in the session-complete
                anchor.

        Returns:
            The new AuditSession

        Raises:
            RuntimeError: If a session is already active
        """
        async with self._async_lock:
            return await self._start_session_locked(tracked_paths)

    async def _start_session_locked(
        self, tracked_paths: list[str | Path] | None = None
    ) -> AuditSession:
        if self._session is not None and self._session.is_active:
            raise RuntimeError(
                f"Session already active: {self._session.session_id}. "
                "End it before starting a new one."
            )

        paths = [Path(p) for p in (tracked_paths or [])]
        session = AuditSession(tracked_paths=paths)
        self._session = session

        # Create session-start anchor
        anchor = await self._ops.audit(
            agent_id=self._agent_id,
            action="session_start",
            resource=f"session/{session.session_id}",
            result=ActionResult.SUCCESS,
            context_data={
                "session_id": session.session_id,
                "parent_anchor_id": self._last_anchor_id,
            },
        )
        self._last_anchor_id = anchor.id

        with _file_lock(self._lock_path):
            self._reload_manifest()
            audit_seq = self._manifest.total_audits
            self._write_json(
                f"anchors/{audit_seq:04d}-{anchor.id}.json",
                {
                    "anchor_id": anchor.id,
                    "parent_anchor_id": anchor.context.get("parent_anchor_id"),
                    "agent_id": anchor.agent_id,
                    "action": anchor.action,
                    "resource": anchor.resource,
                    "result": anchor.result.value,
                    "trust_chain_hash": anchor.trust_chain_hash,
                    "signature": anchor.signature or "",
                    "timestamp": anchor.timestamp.isoformat(),
                    "context": anchor.context,
                },
            )
            # Persist session state
            self._write_json("session.json", session.to_dict())
            self._manifest.total_audits += 1
            self._tp_store.store_manifest(self._manifest)

        logger.info("Started session %s", session.session_id)
        return session

    async def end_session(self) -> dict:
        """End the current audit session.

        Creates a session-complete anchor with aggregate stats.

        Returns:
            Session summary dict

        Raises:
            RuntimeError: If no session is active
        """
        async with self._async_lock:
            return await self._end_session_locked()

    async def _end_session_locked(self) -> dict:
        if self._session is None or not self._session.is_active:
            raise RuntimeError("No active session to end.")

        self._session.end()
        summary = self._session.summary()

        # Create session-complete anchor
        anchor = await self._ops.audit(
            agent_id=self._agent_id,
            action="session_complete",
            resource=f"session/{self._session.session_id}",
            result=ActionResult.SUCCESS,
            context_data={
                **summary,
                "parent_anchor_id": self._last_anchor_id,
            },
        )
        self._last_anchor_id = anchor.id

        with _file_lock(self._lock_path):
            self._reload_manifest()
            audit_seq = self._manifest.total_audits
            self._write_json(
                f"anchors/{audit_seq:04d}-{anchor.id}.json",
                {
                    "anchor_id": anchor.id,
                    "parent_anchor_id": anchor.context.get("parent_anchor_id"),
                    "agent_id": anchor.agent_id,
                    "action": anchor.action,
                    "resource": anchor.resource,
                    "result": anchor.result.value,
                    "trust_chain_hash": anchor.trust_chain_hash,
                    "signature": anchor.signature or "",
                    "timestamp": anchor.timestamp.isoformat(),
                    "context": anchor.context,
                },
            )
            # Remove session file
            session_path = self._dir / "session.json"
            if session_path.exists():
                session_path.unlink()
            self._manifest.total_audits += 1
            self._tp_store.store_manifest(self._manifest)

        logger.info("Ended session %s", self._session.session_id)
        self._session = None
        return summary

    @property
    def posture(self) -> TrustPosture:
        """Current trust posture."""
        return self._posture_machine.get_posture(self._agent_id)

    @property
    def budget_status(self) -> dict[str, Any]:
        """Current financial budget status for the active session.

        Returns a dict with:
            budget_tracking: Whether budget tracking is enabled.
            session_cost: Total cost accumulated in the current session.
            max_cost_per_session: The session budget limit (None if unlimited).
            max_cost_per_action: The per-action limit (None if unlimited).
            remaining: Budget remaining (None if unlimited or no session).
            utilization: Fraction of budget used (0.0-1.0, None if unlimited).
        """
        envelope = self._manifest.constraint_envelope
        tracking = envelope.financial.budget_tracking if envelope is not None else False
        session_cost = self._session.session_cost if self._session else 0.0
        max_session = (
            envelope.financial.max_cost_per_session if envelope is not None else None
        )
        max_action = (
            envelope.financial.max_cost_per_action if envelope is not None else None
        )
        remaining = (max_session - session_cost) if max_session is not None else None
        utilization = (
            (session_cost / max_session) if max_session and max_session > 0 else None
        )
        return {
            "budget_tracking": tracking,
            "session_cost": session_cost,
            "max_cost_per_session": max_session,
            "max_cost_per_action": max_action,
            "remaining": remaining,
            "utilization": utilization,
        }

    @property
    def enforcement_mode(self) -> str:
        """Current enforcement mode: 'strict' or 'shadow'."""
        return self._enforcement_mode

    async def switch_enforcement(self, mode: str, reason: str) -> str:
        """Switch enforcement mode between strict and shadow.

        Creates an audit anchor recording the switch.

        Args:
            mode: 'strict' or 'shadow'
            reason: Why the switch is being made

        Returns:
            The new enforcement mode
        """
        async with self._async_lock:
            return await self._switch_enforcement_locked(mode, reason)

    async def _switch_enforcement_locked(self, mode: str, reason: str) -> str:
        if mode not in ("strict", "shadow"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'strict' or 'shadow'")
        if mode == self._enforcement_mode:
            return mode

        previous = self._enforcement_mode
        self._enforcement_mode = mode
        self._enforcer = (
            self._shadow_enforcer if mode == "shadow" else self._strict_enforcer
        )

        anchor = await self._ops.audit(
            agent_id=self._agent_id,
            action="enforcement_mode_change",
            resource=f"enforcement/{mode}",
            result=ActionResult.SUCCESS,
            context_data={
                "previous_mode": previous,
                "new_mode": mode,
                "reason": reason,
                "parent_anchor_id": self._last_anchor_id,
            },
        )
        self._last_anchor_id = anchor.id

        with _file_lock(self._lock_path):
            self._reload_manifest()
            audit_seq = self._manifest.total_audits
            self._write_json(
                f"anchors/{audit_seq:04d}-{anchor.id}.json",
                {
                    "anchor_id": anchor.id,
                    "parent_anchor_id": anchor.context.get("parent_anchor_id"),
                    "agent_id": anchor.agent_id,
                    "action": anchor.action,
                    "resource": anchor.resource,
                    "result": anchor.result.value,
                    "trust_chain_hash": anchor.trust_chain_hash,
                    "signature": anchor.signature or "",
                    "timestamp": anchor.timestamp.isoformat(),
                    "context": anchor.context,
                },
            )
            self._manifest.metadata["enforcement_mode"] = mode
            self._manifest.total_audits += 1
            self._tp_store.store_manifest(self._manifest)

        logger.info("Enforcement mode: %s → %s (reason: %s)", previous, mode, reason)
        return mode

    def shadow_report(self) -> str:
        """Get the shadow enforcer's report.

        Returns the human-readable report from EATP's ShadowEnforcer,
        showing what would have been blocked/held.
        """
        return self._shadow_enforcer.report()

    async def transition_posture(
        self, target: TrustPosture, reason: str
    ) -> TrustPosture:
        """Transition to a new trust posture.

        Creates an audit anchor recording the transition.

        Args:
            target: Target posture
            reason: Human-provided reason for the transition

        Returns:
            The new posture

        Raises:
            ValueError: If the transition is not allowed
        """
        async with self._async_lock:
            return await self._transition_posture_locked(target, reason)

    async def _transition_posture_locked(
        self, target: TrustPosture, reason: str
    ) -> TrustPosture:
        previous = self.posture

        request = PostureTransitionRequest(
            agent_id=self._agent_id,
            from_posture=previous,
            to_posture=target,
            reason=reason,
            requester_id=self._manifest.author,
        )
        result = self._posture_machine.transition(request)
        if not result.success:
            raise ValueError(f"Posture transition denied: {result.reason}")

        # Record the transition
        anchor = await self._ops.audit(
            agent_id=self._agent_id,
            action="posture_transition",
            resource=f"posture/{target.value}",
            result=ActionResult.SUCCESS,
            context_data={
                "previous_posture": previous.value,
                "new_posture": target.value,
                "reason": reason,
                "parent_anchor_id": self._last_anchor_id,
            },
        )
        self._last_anchor_id = anchor.id

        with _file_lock(self._lock_path):
            self._reload_manifest()
            audit_seq = self._manifest.total_audits
            self._write_json(
                f"anchors/{audit_seq:04d}-{anchor.id}.json",
                {
                    "anchor_id": anchor.id,
                    "parent_anchor_id": anchor.context.get("parent_anchor_id"),
                    "agent_id": anchor.agent_id,
                    "action": anchor.action,
                    "resource": anchor.resource,
                    "result": anchor.result.value,
                    "trust_chain_hash": anchor.trust_chain_hash,
                    "signature": anchor.signature or "",
                    "timestamp": anchor.timestamp.isoformat(),
                    "context": anchor.context,
                },
            )
            self._manifest.metadata["trust_posture"] = target.value
            self._manifest.total_audits += 1
            self._tp_store.store_manifest(self._manifest)

        logger.info(
            "Posture transition: %s → %s (reason: %s)",
            previous.value,
            target.value,
            reason,
        )
        return target

    async def record_execution(self, record: ExecutionRecord) -> str:
        """Record an autonomous AI execution within the constraint envelope.

        Creates an Audit Anchor with QUICK verification. This is the
        simplest Mirror Thesis record — AI handled this without human
        engagement.

        Args:
            record: The execution record

        Returns:
            The execution ID
        """
        async with self._async_lock:
            return await self._record_execution_locked(record)

    async def _record_execution_locked(self, record: ExecutionRecord) -> str:
        # Populate envelope hash from current envelope
        if not record.envelope_hash and self._manifest.constraint_envelope:
            record.envelope_hash = self._manifest.constraint_envelope.envelope_hash()

        reasoning = ReasoningTrace(
            decision=f"Autonomous execution: {record.action}",
            rationale=f"Action within constraint envelope (ref: {record.constraint_reference})",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=record.timestamp,
            methodology="autonomous_execution",
            confidence=record.confidence,
        )

        ctx: dict[str, Any] = {
            "record_type": "execution",
            "verification_category": record.verification_category.value,
            "envelope_hash": record.envelope_hash,
            "parent_anchor_id": self._last_anchor_id,
        }
        if self._session is not None and self._session.is_active:
            ctx.update(self._session.context_data())
            self._session.record_action("record_execution")

        anchor = await self._ops.audit(
            agent_id=self._agent_id,
            action="record_execution",
            resource=f"execution/{record.execution_id}",
            result=ActionResult.SUCCESS,
            context_data=ctx,
            reasoning_trace=reasoning,
        )
        self._last_anchor_id = anchor.id

        with _file_lock(self._lock_path):
            self._reload_manifest()
            audit_seq = self._manifest.total_audits
            self._write_json(
                f"anchors/{audit_seq:04d}-{anchor.id}.json",
                {
                    "anchor_id": anchor.id,
                    "parent_anchor_id": anchor.context.get("parent_anchor_id"),
                    "agent_id": anchor.agent_id,
                    "action": anchor.action,
                    "resource": anchor.resource,
                    "result": anchor.result.value,
                    "trust_chain_hash": anchor.trust_chain_hash,
                    "signature": anchor.signature or "",
                    "timestamp": anchor.timestamp.isoformat(),
                    "context": anchor.context,
                    "reasoning_trace": reasoning.to_dict(),
                    "reasoning_trace_hash": reasoning.content_hash_hex(),
                    "mirror_record": record.to_dict(),
                },
            )
            self._manifest.total_audits += 1
            self._tp_store.store_manifest(self._manifest)

        logger.info("Recorded execution %s", record.execution_id)
        return record.execution_id

    async def record_escalation(self, record: EscalationRecord) -> str:
        """Record an escalation — AI reached its envelope boundary.

        Creates an Audit Anchor with STANDARD verification. Captures
        what triggered the escalation, which competency was needed,
        and how it was resolved.

        Args:
            record: The escalation record

        Returns:
            The escalation ID
        """
        async with self._async_lock:
            return await self._record_escalation_locked(record)

    async def _record_escalation_locked(self, record: EscalationRecord) -> str:
        if not record.envelope_hash and self._manifest.constraint_envelope:
            record.envelope_hash = self._manifest.constraint_envelope.envelope_hash()

        competency_str = ", ".join(c.value for c in record.competency_categories)
        reasoning = ReasoningTrace(
            decision=f"Escalation: {record.trigger}",
            rationale=record.recommendation or "Human judgment required",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=record.timestamp,
            methodology="boundary_escalation",
            confidence=record.confidence,
            alternatives_considered=(
                [f"Competencies needed: {competency_str}"] if competency_str else []
            ),
        )

        ctx: dict[str, Any] = {
            "record_type": "escalation",
            "verification_category": record.verification_category.value,
            "constraint_dimension": record.constraint_dimension,
            "competency_categories": [c.value for c in record.competency_categories],
            "human_authority": record.human_authority,
            "resolution": record.resolution,
            "envelope_hash": record.envelope_hash,
            "parent_anchor_id": self._last_anchor_id,
        }
        if self._session is not None and self._session.is_active:
            ctx.update(self._session.context_data())
            self._session.record_action("record_escalation")

        anchor = await self._ops.audit(
            agent_id=self._agent_id,
            action="record_escalation",
            resource=f"escalation/{record.escalation_id}",
            result=ActionResult.SUCCESS,
            context_data=ctx,
            reasoning_trace=reasoning,
        )
        self._last_anchor_id = anchor.id

        with _file_lock(self._lock_path):
            self._reload_manifest()
            audit_seq = self._manifest.total_audits
            self._write_json(
                f"anchors/{audit_seq:04d}-{anchor.id}.json",
                {
                    "anchor_id": anchor.id,
                    "parent_anchor_id": anchor.context.get("parent_anchor_id"),
                    "agent_id": anchor.agent_id,
                    "action": anchor.action,
                    "resource": anchor.resource,
                    "result": anchor.result.value,
                    "trust_chain_hash": anchor.trust_chain_hash,
                    "signature": anchor.signature or "",
                    "timestamp": anchor.timestamp.isoformat(),
                    "context": anchor.context,
                    "reasoning_trace": reasoning.to_dict(),
                    "reasoning_trace_hash": reasoning.content_hash_hex(),
                    "mirror_record": record.to_dict(),
                },
            )
            self._manifest.total_audits += 1
            self._tp_store.store_manifest(self._manifest)

        logger.info("Recorded escalation %s", record.escalation_id)
        return record.escalation_id

    async def record_intervention(self, record: InterventionRecord) -> str:
        """Record a human intervention — human engaged without AI escalation.

        Creates an Audit Anchor with FULL verification. This is the most
        revealing Mirror Thesis data — the human noticed something AI missed.

        Args:
            record: The intervention record

        Returns:
            The intervention ID
        """
        async with self._async_lock:
            return await self._record_intervention_locked(record)

    async def _record_intervention_locked(self, record: InterventionRecord) -> str:
        if not record.envelope_hash and self._manifest.constraint_envelope:
            record.envelope_hash = self._manifest.constraint_envelope.envelope_hash()

        competency_str = ", ".join(c.value for c in record.competency_categories)
        reasoning = ReasoningTrace(
            decision=f"Human intervention: {record.observation}",
            rationale=record.action_taken or "Human noticed something AI missed",
            confidentiality=ConfidentialityLevel.PUBLIC,
            timestamp=record.timestamp,
            methodology="proactive_intervention",
            confidence=record.confidence,
            alternatives_considered=(
                [f"Competencies exercised: {competency_str}"] if competency_str else []
            ),
        )

        ctx: dict[str, Any] = {
            "record_type": "intervention",
            "verification_category": record.verification_category.value,
            "competency_categories": [c.value for c in record.competency_categories],
            "human_authority": record.human_authority,
            "envelope_hash": record.envelope_hash,
            "parent_anchor_id": self._last_anchor_id,
        }
        if self._session is not None and self._session.is_active:
            ctx.update(self._session.context_data())
            self._session.record_action("record_intervention")

        anchor = await self._ops.audit(
            agent_id=self._agent_id,
            action="record_intervention",
            resource=f"intervention/{record.intervention_id}",
            result=ActionResult.SUCCESS,
            context_data=ctx,
            reasoning_trace=reasoning,
        )
        self._last_anchor_id = anchor.id

        with _file_lock(self._lock_path):
            self._reload_manifest()
            audit_seq = self._manifest.total_audits
            self._write_json(
                f"anchors/{audit_seq:04d}-{anchor.id}.json",
                {
                    "anchor_id": anchor.id,
                    "parent_anchor_id": anchor.context.get("parent_anchor_id"),
                    "agent_id": anchor.agent_id,
                    "action": anchor.action,
                    "resource": anchor.resource,
                    "result": anchor.result.value,
                    "trust_chain_hash": anchor.trust_chain_hash,
                    "signature": anchor.signature or "",
                    "timestamp": anchor.timestamp.isoformat(),
                    "context": anchor.context,
                    "reasoning_trace": reasoning.to_dict(),
                    "reasoning_trace_hash": reasoning.content_hash_hex(),
                    "mirror_record": record.to_dict(),
                },
            )
            self._manifest.total_audits += 1
            self._tp_store.store_manifest(self._manifest)

        logger.info("Recorded intervention %s", record.intervention_id)
        return record.intervention_id

    def get_mirror_records(
        self,
    ) -> dict[str, list[ExecutionRecord | EscalationRecord | InterventionRecord]]:
        """Load all Mirror Thesis records from anchor files.

        Scans anchors/ for records tagged with record_type
        (execution, escalation, intervention) and returns them
        grouped by type.

        Returns:
            Dict with keys 'executions', 'escalations', 'interventions'
        """
        result: dict[
            str, list[ExecutionRecord | EscalationRecord | InterventionRecord]
        ] = {
            "executions": [],
            "escalations": [],
            "interventions": [],
        }

        anchors_dir = self._dir / "anchors"
        if not anchors_dir.exists():
            return result

        for af in sorted(anchors_dir.glob("*.json")):
            data = _safe_read_json(af)
            mirror = data.get("mirror_record")
            if not mirror:
                continue

            record_type = mirror.get("record_type")
            if record_type == "execution":
                result["executions"].append(ExecutionRecord.from_dict(mirror))
            elif record_type == "escalation":
                result["escalations"].append(EscalationRecord.from_dict(mirror))
            elif record_type == "intervention":
                result["interventions"].append(InterventionRecord.from_dict(mirror))

        return result

    async def abandon_session(self, reason: str = "Process terminated") -> dict:
        """Close an abandoned session with audit trail.

        Creates a session_abandoned anchor. Used when a previous process
        died during an active session.

        Args:
            reason: Why the session is being abandoned

        Returns:
            The abandoned session summary
        """
        async with self._async_lock:
            return await self._abandon_session_locked(reason)

    async def _abandon_session_locked(self, reason: str) -> dict:
        if self._session is None:
            raise RuntimeError("No active session to abandon")

        self._session.end()
        summary = self._session.summary()
        summary["abandoned"] = True
        summary["abandon_reason"] = reason

        parent_id = self._last_anchor_id
        anchor = await self._ops.audit(
            agent_id=self._agent_id,
            action="session_abandoned",
            resource=f"session/{self._session.session_id}",
            result=ActionResult.SUCCESS,
            context_data={
                **summary,
                "parent_anchor_id": parent_id,
            },
        )
        self._last_anchor_id = anchor.id

        with _file_lock(self._lock_path):
            self._reload_manifest()
            audit_seq = self._manifest.total_audits
            self._write_json(
                f"anchors/{audit_seq:04d}-{anchor.id}.json",
                {
                    "anchor_id": anchor.id,
                    "parent_anchor_id": parent_id,
                    "agent_id": anchor.agent_id,
                    "action": anchor.action,
                    "resource": anchor.resource,
                    "result": anchor.result.value,
                    "trust_chain_hash": anchor.trust_chain_hash,
                    "signature": anchor.signature or "",
                    "timestamp": anchor.timestamp.isoformat(),
                    "context": anchor.context,
                },
            )
            session_path = self._dir / "session.json"
            if session_path.exists():
                session_path.unlink()
            self._manifest.total_audits += 1
            self._tp_store.store_manifest(self._manifest)

        logger.warning("Abandoned session %s: %s", self._session.session_id, reason)
        self._session = None
        return summary

    async def repair(self, dry_run: bool = False) -> dict:
        """Attempt to repair trust infrastructure.

        Rebuilds chain consistency from anchor files. Does NOT
        create new keys or alter signing identity.

        All mutations are performed under the project-level file lock
        to prevent concurrent repair/write conflicts.

        Args:
            dry_run: If True, report issues without fixing

        Returns:
            Dict with 'issues_found' and 'issues_fixed' lists
        """
        issues_found: list[str] = []
        issues_fixed: list[str] = []

        with _file_lock(self._lock_path):
            # Check anchor file integrity
            anchors_dir = self._dir / "anchors"
            if anchors_dir.exists():
                anchor_files = sorted(anchors_dir.glob("*.json"))
                prev_id = None
                for af in anchor_files:
                    try:
                        data = _safe_read_json(af)
                    except (json.JSONDecodeError, OSError):
                        issues_found.append(f"Corrupted anchor file: {af.name}")
                        continue

                    parent = data.get("parent_anchor_id")
                    if prev_id is not None and parent != prev_id:
                        issues_found.append(
                            f"Broken parent chain at {af.name}: "
                            f"expected {prev_id}, got {parent}"
                        )
                        if not dry_run:
                            data["parent_anchor_id"] = prev_id
                            _atomic_write(af, data)
                            issues_fixed.append(f"Fixed parent chain in {af.name}")
                    prev_id = data.get("anchor_id")

            # Check for orphaned session file
            session_path = self._dir / "session.json"
            if session_path.exists() and self._session is None:
                issues_found.append("Orphaned session.json (no active session)")
                if not dry_run:
                    session_path.unlink()
                    issues_fixed.append("Removed orphaned session.json")

            # Sync manifest audit count with actual anchor files
            if anchors_dir.exists():
                actual_count = len(list(anchors_dir.glob("*.json")))
                if self._manifest.total_audits != actual_count:
                    issues_found.append(
                        f"Manifest audit count mismatch: "
                        f"manifest={self._manifest.total_audits}, "
                        f"files={actual_count}"
                    )
                    if not dry_run:
                        self._manifest.total_audits = actual_count
                        self._tp_store.store_manifest(self._manifest)
                        issues_fixed.append(
                            f"Updated manifest audit count to {actual_count}"
                        )

            # Post-repair verification: re-verify parent chain after fixes
            if issues_fixed and anchors_dir.exists():
                anchor_files_post = sorted(anchors_dir.glob("*.json"))
                prev_post = None
                for af in anchor_files_post:
                    try:
                        data = _safe_read_json(af)
                        parent = data.get("parent_anchor_id")
                        if prev_post is not None and parent != prev_post:
                            issues_found.append(
                                f"Post-repair: still broken at {af.name}"
                            )
                        prev_post = data.get("anchor_id")
                    except (json.JSONDecodeError, OSError):
                        issues_found.append(f"Post-repair: still corrupted: {af.name}")

        return {
            "issues_found": issues_found,
            "issues_fixed": issues_fixed,
            "dry_run": dry_run,
        }

    def _reload_manifest(self) -> None:
        """Re-read manifest from disk (call inside lock)."""
        from kailash.trust.plane.exceptions import RecordNotFoundError

        try:
            self._manifest = self._tp_store.get_manifest()
        except RecordNotFoundError:
            pass  # Manifest not yet written — keep in-memory version

    def _write_json(self, relative_path: str, data: dict[str, Any]) -> None:
        """Write JSON to the trust plane directory atomically."""
        path = self._dir / relative_path
        _atomic_write(path, data)
