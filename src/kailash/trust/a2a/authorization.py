# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
A2A authorization — routes every decision to PACT, and fails closed.

Authentication (``jsonrpc.py``) establishes WHO is calling. This module decides
WHAT they may do, and it deliberately owns almost no policy: `framework-first`
binds governance / RBAC / policy / access control to PACT, so a hand-rolled
rule set here would be a parallel implementation that drifts from the canonical
one.

Three fail-OPEN behaviours in the surrounding code are load-bearing here, each
MEASURED rather than assumed. This module exists to convert all three into
refusals:

1. **A `None` envelope is maximally permissive.** ``GovernanceEngine`` treats an
   unconfigured envelope as "no constraints — action permitted", by design (it
   is opt-in governance). Measured: with a real role and no envelope,
   ``impersonate_president`` returned ``auto_approved``; with an envelope
   allowing only ``read``, the same call returned ``blocked``. That control is
   what makes the first result readable. So a verdict whose
   ``effective_envelope_snapshot`` is ``None`` is a NON-ANSWER, not an approval.

2. **``AgentRoleMapping.resolve()`` passes unknown ids through.** Measured:
   ``resolve('agent-002-Rogue')`` returns ``'agent-002-Rogue'`` and
   ``resolve('RANDOM')`` returns ``'RANDOM'`` — any identifier containing a
   ``D``, ``T`` or ``R`` is treated as an already-formed role address. This
   module uses ``get_address()`` ONLY, which returns ``None`` for every
   unregistered id.

3. **A missing authorizer would authorize nothing.** An A2A service with no
   governance org configured refuses protected methods rather than allowing
   them — the same shape ``JsonRpcHandler`` uses for a missing token verifier.

Verdict handling is a positive ALLOWLIST: only ``auto_approved`` proceeds.
Enumerating the deny-values instead would silently admit any level PACT gains
later.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Protocol

from kailash.trust.a2a.auth import CallerIdentity
from kailash.trust.a2a.exceptions import AuthorizationError

logger = logging.getLogger(__name__)

__all__ = ["A2AAuthorizer", "GovernanceEngineLike", "RoleMappingLike"]

#: The ONLY verdict level that permits an action. A positive allowlist: a
#: deny-list would admit any future level by default.
_PERMITTED_VERDICT_LEVELS = frozenset({"auto_approved"})


class GovernanceEngineLike(Protocol):
    """Structural type for PACT's governance engine."""

    def verify_action(
        self,
        role_address: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Any: ...

    def check_access(
        self, role_address: str, knowledge_item: Any, posture: Any
    ) -> Any: ...


class RoleMappingLike(Protocol):
    """Structural type for PACT's agent→role-address mapping.

    Only ``get_address`` is declared. ``resolve`` is deliberately absent so this
    module cannot reach the fail-open passthrough described in the module
    docstring.
    """

    def get_address(self, agent_id: str) -> Optional[str]: ...


class A2AAuthorizer:
    """Authorizes A2A method calls against a PACT governance org.

    Every refusal raises :class:`AuthorizationError`. Before this module that
    exception was declared and exported with no raise site anywhere in the
    package — a control that existed only on paper.
    """

    def __init__(
        self,
        governance_engine: GovernanceEngineLike,
        role_mapping: RoleMappingLike,
        posture: Any,
    ):
        """
        Args:
            governance_engine: PACT ``GovernanceEngine``.
            role_mapping: PACT ``AgentRoleMapping``. Agent ids are resolved
                through ``get_address`` only.
            posture: ``TrustPostureLevel`` for access checks.
        """
        self._gov = governance_engine
        self._roles = role_mapping
        self._posture = posture

    # -- internals ---------------------------------------------------------

    def _role_or_deny(self, agent_id: str, role_of: str) -> str:
        """Map an agent id to a D/T/R role address, or refuse.

        ``get_address`` returns ``None`` for an unregistered id; that is a DENY,
        never a passthrough.
        """
        address = self._roles.get_address(agent_id)
        if address is None:
            logger.warning(
                "a2a.authz.unmapped_agent",
                extra={"role_of": role_of, "agent_id_present": bool(agent_id)},
            )
            raise AuthorizationError(
                reason=f"{role_of} is not mapped to a governance role; refusing"
            )
        return address

    def _require_governed_verdict(self, verdict: Any, action: str) -> None:
        """Accept a verdict only if an envelope was actually in effect."""
        if getattr(verdict, "effective_envelope_snapshot", None) is None:
            # The permissive non-answer described in the module docstring.
            raise AuthorizationError(
                reason=f"no governance envelope in effect for '{action}'; refusing "
                "(an unconfigured envelope permits every action, so this is "
                "not an approval)"
            )

        level = getattr(verdict, "level", None)
        if level not in _PERMITTED_VERDICT_LEVELS:
            reason = getattr(verdict, "reason", "") or "no reason given"
            raise AuthorizationError(reason=f"'{action}' not permitted: {reason}")

    # -- public surface ----------------------------------------------------

    def require_action(
        self,
        caller: CallerIdentity,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Authorize ``caller`` to perform ``action``; raise otherwise.

        Returns the caller's resolved role address, so a handler that needs it
        does not resolve twice.
        """
        role = self._role_or_deny(caller.agent_id, "caller")
        verdict = self._gov.verify_action(role, action, context)
        self._require_governed_verdict(verdict, action)
        return role

    def require_audit_access(
        self, caller: CallerIdentity, subject_agent_id: str
    ) -> None:
        """Authorize ``caller`` to read ``subject_agent_id``'s audit trail.

        Modelled as a knowledge-access check whose owning unit is the SUBJECT's
        own role address. That yields the right semantics from PACT's existing
        containment algorithm without hardcoding any of them here: the subject
        is same-unit (allow); a supervisor's address is a prefix of it (allow);
        an unrelated peer matches neither and falls through to the KSP/bridge
        steps, which default to deny.

        A same-agent equality check would have been simpler and wrong — it
        forecloses the compliance-officer and incident-responder cases
        permanently, and can only be undone by editing this file.
        """
        from kailash.trust.pact.knowledge import ConfidentialityLevel, KnowledgeItem

        role = self._role_or_deny(caller.agent_id, "caller")
        owner = self._role_or_deny(subject_agent_id, "audit subject")

        item = KnowledgeItem(
            item_id=f"audit:{subject_agent_id}",
            classification=ConfidentialityLevel.CONFIDENTIAL,
            owning_unit_address=owner,
        )
        decision = self._gov.check_access(role, item, self._posture)
        if not getattr(decision, "allowed", False):
            reason = getattr(decision, "reason", "") or "no access path"
            raise AuthorizationError(reason=f"audit access denied: {reason}")
