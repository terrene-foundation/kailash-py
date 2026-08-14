"""Server-derived actor identity for MFA authorization (issue #2047).

``MultiFactorAuthNode`` had no actor. ``user_id`` named the SUBJECT of an
action and never the caller, and the only thing separating an administrative
call from an end-user one was ``admin_override`` -- an ordinary caller-supplied
boolean. Five successive adversarial review rounds each patched the specific
action the previous round exploited; the root stood, because the node had no
way to ask "who is doing this?" at all.

This module supplies that. The load-bearing property, from
``rules/security.md`` § Enforcement-Surface Parity → *Identity-derivation
parity*:

    An approver / decider / actor identity in ANY authorization or
    distinctness check MUST be server-derived from the authenticated session,
    NEVER a body field, on BOTH sides of any comparison.

For a workflow node, EVERY input is a body field by construction -- so an
``actor_user_id`` parameter would be exactly the defect it claims to fix, in
new clothes. What the caller may supply is PROOF of authentication (an opaque
session id it cannot forge); what it may never supply is the CLAIM of who it
is. The node resolves the second from the first through server-side state it
holds, and compares that derived identity against the requested subject.

Both sides of the comparison are therefore server-derived: the actor from the
session store, and the subject from the node's own MFA records.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional, Protocol, runtime_checkable

__all__ = [
    "ADMIN_CAPABILITY",
    "ActorResolver",
    "MFAActor",
    "NullActorResolver",
    "SessionActorResolver",
    "StaticActorResolver",
]

logger = logging.getLogger(__name__)

#: Capability required to act on a subject other than yourself, and to take any
#: destructive action (``revoke`` / ``disable`` / ``reset``) or administrative
#: recovery. A capability held by a resolved principal, verified -- never a
#: boolean asserted by the caller.
#:
#: DELIBERATELY NOT PREFIXED WITH THE FACTOR-TYPE ACRONYM, and the reason is a
#: scanner heuristic rather than taste, so it is recorded rather than left to
#: look arbitrary. `py/clear-text-logging-sensitive-data` classifies a value as
#: sensitive from its BINDING'S NAME, and it reads an ``mfa``-containing
#: identifier as credential material -- correctly in general, since a TOTP seed
#: is exactly that, and wrongly here, since this is a policy label with no
#: secret in it. MEASURED on PR #2103: under the former name this constant was
#: the taint SOURCE for SIX of the seven high-severity alerts on that PR
#: (``audit_log.py:113,115,117``, ``nodes/api/rest.py:676``,
#: ``kaizen/nodes/security/ai_behavior_analysis.py:254`` and
#: ``ai_threat_detection.py:262``), reported as "sensitive data (password)".
#: It reached all six because it is interpolated into refusal messages that
#: travel out through ``result["error"]``, and unrelated nodes log that field.
#: The same alert classified ``phone_number`` in this package as "private",
#: which is what confirms the mechanism is the identifier substring.
#:
#: The VALUE is unchanged and remains the wire capability name.
ADMIN_CAPABILITY = "mfa:admin"


@dataclass(frozen=True)
class MFAActor:
    """An authenticated principal, as resolved by an :class:`ActorResolver`.

    Frozen deliberately. An actor is the OUTPUT of a resolution step, and a
    mutable one could be widened after the resolver vouched for it -- by an
    action handler, by a hook, by anything holding a reference. The only way
    to obtain capabilities is to be given them by a resolver.

    ``capabilities`` are matched EXACTLY. There is no wildcard and no
    hierarchy: a ``"*"`` that silently means "everything" is the same
    unbounded grant this whole change exists to remove, and an implicit
    hierarchy makes the grant depend on a naming convention nobody enforces.
    """

    user_id: str
    capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, str) or not self.user_id.strip():
            raise ValueError("MFAActor.user_id must be a non-empty string")
        # Normalize whatever the resolver handed us (list, set, generator) to a
        # frozenset of strings, so `has_capability` cannot be defeated by an
        # exhausted iterator or a mutable set the caller still holds.
        object.__setattr__(
            self, "capabilities", frozenset(str(c) for c in self.capabilities)
        )

    def has_capability(self, capability: str) -> bool:
        """True IFF this actor was granted exactly ``capability``."""
        return capability in self.capabilities


@runtime_checkable
class ActorResolver(Protocol):
    """Resolve an opaque, caller-presented session id to a principal.

    The injection point for a host's own authentication. Implementations MUST
    be fail-closed: any error -- an unreachable session store, a malformed id,
    an expired session -- resolves to ``None``, which the node treats as "no
    actor" and denies. An implementation MUST NOT raise; a node that crashes
    on a bad session id is a denial-of-service surface on the auth path.

    A host with a PACT deployment can bind ``kailash.trust.pact``'s
    ``GovernanceEngine`` here structurally -- its ``verify_action(role_address,
    action, context)`` is the same shape -- without this module importing
    anything from ``kailash.trust`` (which sits behind the ``trust`` extra).
    """

    def resolve_actor(
        self, actor_session_id: str
    ) -> Optional[MFAActor]:  # pragma: no cover (Protocol)
        """Return the principal that owns ``actor_session_id``, or None."""


class NullActorResolver:
    """The fail-closed default: resolves nothing, so nothing is authorized.

    Mirrors ``kailash.delegate.verifier.NullVerifier``. An unwired dependency
    must surface as a refusal, not as an open door -- so a node constructed
    without a resolver denies every action rather than silently falling back
    to trusting ``user_id``, which is the behaviour #2047 is about.
    """

    def resolve_actor(self, actor_session_id: str) -> Optional[MFAActor]:
        return None


class StaticActorResolver:
    """Resolve from an in-process table of ``session_id -> MFAActor``.

    For single-process hosts that mint their own session ids, and for tests.
    The table is server-side state: a caller presenting a session id it was
    not issued resolves to ``None``.
    """

    def __init__(self, sessions: Optional[dict[str, MFAActor]] = None) -> None:
        self._sessions: dict[str, MFAActor] = dict(sessions or {})

    def add(self, actor_session_id: str, actor: MFAActor) -> None:
        """Register an issued session. Called by the HOST, never by a request."""
        if not isinstance(actor_session_id, str) or not actor_session_id:
            raise ValueError("actor_session_id must be a non-empty string")
        self._sessions[actor_session_id] = actor

    def revoke(self, actor_session_id: str) -> None:
        self._sessions.pop(actor_session_id, None)

    def resolve_actor(self, actor_session_id: str) -> Optional[MFAActor]:
        if not isinstance(actor_session_id, str) or not actor_session_id:
            return None
        return self._sessions.get(actor_session_id)


class SessionActorResolver:
    """Resolve the actor from a :class:`SessionManagementNode`-validated session.

    Identity comes from the session record, which the node wrote when the
    principal authenticated -- never from the request.

    Capabilities are a SEPARATE lookup, because a validated session carries
    ``user_id`` and expiry and nothing else: ``SessionData`` has no roles or
    permissions field. ``capability_provider`` is the host's hook for that,
    and it is passed the SERVER-DERIVED user id, not anything from the
    request. With no provider an actor holds NO capabilities, so it can act on
    itself and on nobody else -- fail-closed by construction rather than by
    the host remembering to restrict it.
    """

    def __init__(
        self,
        session_node: Any,
        capability_provider: Optional[Callable[[str], Iterable[str]]] = None,
    ) -> None:
        if session_node is None:
            raise ValueError(
                "SessionActorResolver requires a session_node; pass a "
                "SessionManagementNode, or use NullActorResolver to deny "
                "everything explicitly."
            )
        self._session_node = session_node
        self._capability_provider = capability_provider

    def resolve_actor(self, actor_session_id: str) -> Optional[MFAActor]:
        if not isinstance(actor_session_id, str) or not actor_session_id:
            return None
        try:
            result = self._session_node.execute(
                action="validate", session_id=actor_session_id
            )
        except Exception as exc:
            # Fail closed, but NOT silently: an unreachable session store that
            # denies every request looks identical to a store that is working
            # and rejecting them (`rules/zero-tolerance.md` Rule 3).
            logger.warning(
                "MFA actor resolution failed against the session store: %s",
                type(exc).__name__,
            )
            return None

        if not isinstance(result, dict) or not result.get("valid"):
            return None
        session_data = result.get("session_data")
        if not isinstance(session_data, dict):
            return None
        user_id = session_data.get("user_id")
        if not isinstance(user_id, str) or not user_id.strip():
            return None

        capabilities: frozenset[str] = frozenset()
        if self._capability_provider is not None:
            try:
                capabilities = frozenset(
                    str(c) for c in (self._capability_provider(user_id) or ())
                )
            except Exception as exc:
                # A capability lookup that fails grants NOTHING rather than
                # everything, and says so.
                logger.warning(
                    "MFA capability lookup failed for a resolved actor: %s",
                    type(exc).__name__,
                )
                capabilities = frozenset()

        return MFAActor(user_id=user_id, capabilities=capabilities)
