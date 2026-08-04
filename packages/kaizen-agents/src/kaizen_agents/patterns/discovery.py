"""Agent discovery extensions for Enterprise-App integration.

Provides user-filtered agent discovery and skill metadata for UI integration.
"""

from __future__ import annotations

import inspect
import logging
import math
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from datetime import time as _time
from typing import Any

from kaizen.llm.reasoning import ReasoningDegradedError
from kaizen.utils.credential_scrub import scrub_credentials

from .registry import AgentRegistry
from .runtime import AgentMetadata, AgentStatus


def _accepts_user_kwargs(checker: Any | None) -> bool:
    """Does ``checker.verify`` take ``user_id``/``organization_id`` directly?

    Returns True for the duck-typed shape consumers actually wired (and that
    every existing test uses), False for the ``context=``-taking shape
    ``TrustOperations`` declares. Defaults to True when the signature cannot be
    read, because that is the historical call shape — an unreadable signature
    should not silently switch a working integration onto the other form.
    """
    if checker is None:
        return True
    verify = getattr(checker, "verify", None)
    if verify is None:
        return True
    try:
        params = inspect.signature(verify).parameters
    except (TypeError, ValueError):  # builtins / C-implemented callables
        return True
    if any(p.kind is p.VAR_KEYWORD for p in params.values()):
        return True
    return "user_id" in params


logger = logging.getLogger(__name__)


#: `permission_level` on a DENIED `AccessMetadata`.
#:
#: Exported so consumers compare against a named constant rather than a magic
#: string. The dataclass DEFAULT is ``"execute"``, so a bare ``AccessMetadata()``
#: returned from a denial path reads as an execute-level grant to anything that
#: inspects the payload without also carrying the boolean — see
#: `AccessMetadata.deny`.
DENIED_PERMISSION_LEVEL = "none"


@dataclass
class AccessConstraints:
    """Constraints on agent access for a user.

    TWO ENCODING HAZARDS, both load-bearing for consumers:

    1. ``None`` MEANS UNLIMITED, NOT "NONE". Every field defaults to None and
       `to_dict()` serializes None as `null`, so a bare `AccessConstraints()`
       is the MOST PERMISSIVE value this type can hold — uncapped invocations,
       tokens, spend, and tools. Any code path that cannot determine the real
       caps MUST NOT hand back a default instance; see `deny()`.

    2. A ZEROED CAP IS FALSY. `deny()` encodes denial as `0` / `0.0` / `[]`,
       all of which are falsy in Python. A consumer writing::

           if constraints.max_daily_invocations:      # WRONG
               enforce(constraints.max_daily_invocations)

       reads a DENIAL (`0`) exactly as it reads an ABSENT cap (`None`) — as
       "no limit set" — and enforces nothing. The two states are opposites.
       Consumers MUST discriminate on `is None`::

           if constraints.max_daily_invocations is not None:   # RIGHT
               enforce(constraints.max_daily_invocations)

       The same hazard applies to `max_tokens_per_session` (0),
       `max_cost_per_session_usd` (0.0) and `allowed_tools` (`[]`) — an empty
       allow-list means "no tool is permitted", never "no restriction".
    """

    max_daily_invocations: int | None = None
    max_tokens_per_session: int | None = None
    max_cost_per_session_usd: float | None = None
    allowed_tools: list[str] | None = None
    blocked_tools: list[str] | None = None
    time_window_start: str | None = None  # ISO time (e.g., "09:00:00")
    time_window_end: str | None = None  # ISO time (e.g., "17:00:00")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "max_daily_invocations": self.max_daily_invocations,
            "max_tokens_per_session": self.max_tokens_per_session,
            "max_cost_per_session_usd": self.max_cost_per_session_usd,
            "allowed_tools": self.allowed_tools,
            "blocked_tools": self.blocked_tools,
            "time_window_start": self.time_window_start,
            "time_window_end": self.time_window_end,
        }

    @classmethod
    def deny(cls) -> AccessConstraints:
        """The ZERO-capability constraint set, for a denial payload.

        Every field of a default `AccessConstraints()` is None, which
        `to_dict()` serializes as `null` — and `null` is this type's encoding
        for UNLIMITED, not for "none". A denial carrying default constraints
        therefore serializes as uncapped invocations, tokens, spend, and tools:
        strictly the most permissive value the type can hold.

        Zero caps and an EMPTY `allowed_tools` say the opposite, in the same
        vocabulary.

        EVERY field is now set, including `blocked_tools` and the time window.
        An earlier revision left those three as None with the rationale that
        they are "*additional* restrictions layered on a grant, and inventing
        values for them would imply a grant exists to restrict". That reasoning
        described the AUTHOR's intent and not the TYPE's encoding: None on this
        type does not mean "not applicable", it means UNLIMITED (see the class
        docstring). A consumer that enforces a blocklist read `blocked_tools:
        null` as "nothing is blocked", and a consumer that enforces a schedule
        read `time_window_*: null` as "permitted at any hour" — so the denial
        payload was still maximally permissive on exactly the two axes those
        consumers enforce. Three fields short of a denial is not a denial.

        `blocked_tools=["*"]` blocks every tool, and a ZERO-WIDTH window
        (start == end == midnight) permits no instant, each stated in the
        vocabulary its own consumer already reads. Note the falsy-zero hazard
        documented on the class: these values are only correctly enforced by a
        consumer that discriminates on `is None`.
        """
        return cls(
            max_daily_invocations=0,
            max_tokens_per_session=0,
            max_cost_per_session_usd=0.0,
            allowed_tools=[],
            blocked_tools=["*"],
            time_window_start="00:00:00",
            time_window_end="00:00:00",
        )


@dataclass
class AccessMetadata:
    """Access metadata for a user's access to an agent."""

    permission_level: str = "execute"  # execute, view, admin
    constraints: AccessConstraints = field(default_factory=AccessConstraints)
    granted_by: str | None = None  # User/role that granted access
    granted_at: str | None = None  # ISO timestamp
    expires_at: str | None = None  # ISO timestamp
    # Explicit denial marker. Appended LAST so positional construction of the
    # pre-existing fields is unchanged. Defaults False because the default
    # instance is the GRANT shape — inverting the public default would silently
    # re-key every caller that builds one directly.
    denied: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "permission_level": self.permission_level,
            "constraints": self.constraints.to_dict(),
            "granted_by": self.granted_by,
            "granted_at": self.granted_at,
            "expires_at": self.expires_at,
            "denied": self.denied,
        }

    @classmethod
    def deny(cls) -> AccessMetadata:
        """The denial payload — explicitly denied on every axis it exposes.

        ONE constructor for every denial branch in `_check_user_access`. Three
        sites each hand-building `AccessMetadata()` is how one of them stays
        permissive after a later edit, and it is how this payload came to be
        indistinguishable from a maximally permissive grant in the first place:
        the type's defaults are the GRANT defaults, so `AccessMetadata()` on a
        denial path serialized as execute-level access with unlimited
        constraints.

        A consumer that reads only the boolean is unaffected. A consumer that
        reads the payload — a direct caller of the public `_check_user_access`
        2-tuple, an audit sink, a serializer — now sees `denied: true`,
        `permission_level: "none"`, and zeroed caps instead of a grant.

        Still well-formed and never None: `find_agents_for_user` unpacks the
        pair unconditionally and callers may call `.to_dict()` on the result. A
        fail-closed decision that crashes the caller is not fail-closed.
        """
        return cls(
            permission_level=DENIED_PERMISSION_LEVEL,
            constraints=AccessConstraints.deny(),
            denied=True,
        )


#: Accepted keys in a MAPPING-shaped constraint payload → `AccessConstraints`
#: field name. ALL SEVEN fields are reachable. `max_tokens` is the historical
#: alias for `max_tokens_per_session`: it is the only key the pre-normalizer
#: code read besides `max_daily_invocations`, so consumer-wired duck-typed
#: checkers emit it and dropping it would break them.
_CONSTRAINT_KEY_ALIASES: dict[str, str] = {
    "max_daily_invocations": "max_daily_invocations",
    "max_tokens": "max_tokens_per_session",
    "max_tokens_per_session": "max_tokens_per_session",
    "max_cost_per_session_usd": "max_cost_per_session_usd",
    "allowed_tools": "allowed_tools",
    "blocked_tools": "blocked_tools",
    "time_window_start": "time_window_start",
    "time_window_end": "time_window_end",
}


def _coerce_int_cap(value: Any) -> tuple[Any, bool]:
    """An invocation/token cap. `bool` is EXCLUDED though it is an `int`
    subclass — `max_tokens: True` is a mis-typed payload, not a cap of 1."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None, False
    return value, True


def _coerce_float_cap(value: Any) -> tuple[Any, bool]:
    """A spend cap. NaN/Inf are REJECTED: `NaN` silently passes every `>`
    comparison a budget check makes (`trust-plane-security.md` MUST-NOT-5), so
    accepting one here would reinstate the unlimited grant in numeric form."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, False
    if not math.isfinite(value) or value < 0:
        return None, False
    return float(value), True


def _coerce_tool_list(value: Any) -> tuple[Any, bool]:
    """An allow/block list. Must be a real sequence of strings; a bare `str`
    is rejected because iterating one yields CHARACTERS, silently producing a
    per-character tool list."""
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(
        value, (Sequence, AbstractSet)
    ):
        return None, False
    items = list(value)
    if not all(isinstance(item, str) for item in items):
        return None, False
    return items, True


def _coerce_time(value: Any) -> tuple[Any, bool]:
    """An ISO time bound. Parsed, not merely type-checked: an unparseable
    bound is read by a scheduling consumer as no bound at all."""
    if not isinstance(value, str):
        return None, False
    try:
        _time.fromisoformat(value)
    except ValueError:
        return None, False
    return value, True


_CONSTRAINT_COERCERS = {
    "max_daily_invocations": _coerce_int_cap,
    "max_tokens_per_session": _coerce_int_cap,
    "max_cost_per_session_usd": _coerce_float_cap,
    "allowed_tools": _coerce_tool_list,
    "blocked_tools": _coerce_tool_list,
    "time_window_start": _coerce_time,
    "time_window_end": _coerce_time,
}


def _constraint_payload_present(raw: Any) -> bool:
    """Is there a constraint payload to read at all?

    ABSENT (None, or any EMPTY collection) is distinct from UNREADABLE. An
    absent payload means the checker imposed no constraints — which is exactly
    what `VerificationResult.effective_constraints` defaults to
    (`field(default_factory=list)`), so the overwhelmingly common valid
    verification carries an EMPTY list. Treating that as unreadable would deny
    every user of the documented checker.
    """
    if raw is None:
        return False
    if isinstance(raw, (str, bytes, bytearray)):
        return len(raw) > 0
    if isinstance(raw, (Mapping, Sequence, AbstractSet)):
        return len(raw) > 0
    return True


def normalize_access_constraints(
    raw: Any,
) -> tuple[AccessConstraints | None, str | None]:
    """Turn a checker's constraint payload into `AccessConstraints`.

    Returns `(constraints, None)` on success, or `(None, reason)` when the
    payload is PRESENT but cannot be represented — in which case the caller
    MUST fail closed. It never returns a default `AccessConstraints()` for a
    payload it could not read, because on this type a default instance is
    UNLIMITED (see the class docstring) — i.e. the most permissive possible
    answer to a question we just failed to answer.

    THREE SHAPES, and the third is why this function exists:

    * **MAPPING** — `{"max_tokens": 42}`. Real cap semantics; all SEVEN fields
      are mapped. `Mapping`, not `dict`: a checker returning a `MappingProxy`,
      a `ChainMap`, or any `collections.abc.Mapping` implementation was
      previously rejected by an `isinstance(raw, dict)` test and its caps
      silently dropped.

    * **ABSENT / EMPTY** — no constraints imposed; an unrestricted grant.

    * **NON-EMPTY SEQUENCE OF LABELS** — `["read_only", "audit_required"]`.
      This is what the DOCUMENTED checker actually emits, and it is
      UNREPRESENTABLE here, so it fails closed.

      Establishing that grammar was the whole point, so it is recorded rather
      than assumed: `kailash.trust.chain.VerificationResult` declares
      `effective_constraints: List[str]` (chain.py:854), populated by
      `TrustOperations.verify` from `chain.get_effective_constraints(...)`
      (operations/__init__.py:1244), which set-unions `cap.constraints` with
      `delegation.constraint_subset` and returns `List[str]`
      (chain.py:1028-1043). `DelegationRecord.constraint_subset` is documented
      as "constraint LABELS ... read by NO allow/deny gate" (chain.py:350-352),
      and the in-SDK consumer at `runtime/trust/verifier.py:398` folds them as
      `{c: True for c in ...}` — each label is a BOOLEAN FLAG. Observed values
      are `"read_only"`, `"audit_required"`.

      So the labels carry NO cap semantics: there is no number, no field name,
      and no `key=value` form to parse. Inventing one (splitting on `=`,
      pattern-matching `max_tokens_42`) would be fabricating a grammar the
      producing type does not emit, and every label that failed the invented
      parse would fall back to unlimited. A label set is a restriction the
      checker DID impose and this type CANNOT express — the only honest
      dispositions are deny, or grant caps we cannot justify. It denies.

    Anything else present — a bare string, an int, an arbitrary object, a
    mapping carrying an unrecognized key or an unusable value type — is
    likewise unrepresentable and denies. An unrecognized key is deliberately
    NOT ignored: a checker sending `{"max_requests_per_hour": 5}` capped an
    axis, and silently dropping it grants unlimited on exactly that axis,
    which is the defect class this function closes.
    """
    if not _constraint_payload_present(raw):
        return AccessConstraints(), None

    if isinstance(raw, Mapping):
        constraints = AccessConstraints()
        assigned: dict[str, Any] = {}
        for key, value in raw.items():
            if not isinstance(key, str):
                return None, f"constraint key {key!r} is not a string"
            field_name = _CONSTRAINT_KEY_ALIASES.get(key)
            if field_name is None:
                return None, (
                    f"unrecognized constraint key {key!r} (recognized: "
                    f"{', '.join(sorted(_CONSTRAINT_KEY_ALIASES))})"
                )
            if value is None:
                continue
            coerced, ok = _CONSTRAINT_COERCERS[field_name](value)
            if not ok:
                return None, (
                    f"constraint {key!r} carries an unusable value "
                    f"({type(value).__name__})"
                )
            # Alias collision. `max_tokens` and `max_tokens_per_session` land
            # on the SAME field, so a payload carrying both with DIFFERENT
            # values has two answers and dict order picks one; that silent
            # coin-flip between two caps is itself a fail-closed case.
            if field_name in assigned and assigned[field_name] != coerced:
                return None, (
                    f"conflicting values for {field_name!r} "
                    f"({assigned[field_name]!r} vs {coerced!r})"
                )
            assigned[field_name] = coerced
            setattr(constraints, field_name, coerced)
        return constraints, None

    if isinstance(raw, (Sequence, AbstractSet)) and not isinstance(
        raw, (str, bytes, bytearray)
    ):
        labels = ", ".join(sorted(repr(item) for item in raw))
        return None, (
            "constraint labels carry no cap semantics and cannot be enforced "
            f"as AccessConstraints: [{labels}]"
        )

    return None, (
        f"constraint payload of type {type(raw).__name__} cannot be read as "
        "constraints"
    )


@dataclass
class AgentWithAccess:
    """Agent metadata combined with access information.

    Returned by find_agents_for_user() to include both agent
    details and the user's access permissions.

    Example:
        >>> agent_with_access = await registry.find_agents_for_user(
        ...     user_id="user-123",
        ...     organization_id="org-456",
        ... )
        >>> print(agent_with_access.metadata.agent_id)
        >>> print(agent_with_access.access.permission_level)
    """

    metadata: AgentMetadata
    access: AccessMetadata

    @property
    def agent_id(self) -> str:
        """Get agent ID."""
        return self.metadata.agent_id

    @property
    def agent(self):
        """Get agent instance."""
        return self.metadata.agent

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.metadata.agent_id,
            "name": getattr(
                self.metadata.agent, "name", self.metadata.agent.__class__.__name__
            ),
            "status": self.metadata.status.value,
            "capabilities": self._extract_capabilities(),
            "_access": self.access.to_dict(),
        }

    def _extract_capabilities(self) -> list[str]:
        """Extract capabilities from A2A card."""
        if not self.metadata.a2a_card:
            return []

        capabilities = []
        if isinstance(self.metadata.a2a_card, dict):
            if "capability" in self.metadata.a2a_card:
                capabilities.append(self.metadata.a2a_card["capability"])
            if "capabilities" in self.metadata.a2a_card:
                caps = self.metadata.a2a_card["capabilities"]
                if isinstance(caps, list):
                    capabilities.extend(caps)
                elif isinstance(caps, str):
                    capabilities.append(caps)

        return capabilities


@dataclass
class AgentSkillMetadata:
    """Metadata for agent as skill in Enterprise-App UI.

    Provides all information needed to display an agent/skill
    in the Enterprise-App platform UI.

    Example:
        >>> skill = AgentSkillMetadata.from_agent(agent)
        >>> print(f"{skill.name}: {skill.description}")
    """

    id: str
    name: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    suggested_prompts: list[str] = field(default_factory=list)
    input_schema: dict[str, Any] | None = None
    output_types: list[str] = field(default_factory=list)
    avg_execution_time_seconds: float = 0.0
    avg_cost_cents: float = 0.0
    tags: list[str] = field(default_factory=list)
    icon: str | None = None
    category: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "suggested_prompts": self.suggested_prompts,
            "input_schema": self.input_schema,
            "output_types": self.output_types,
            "avg_execution_time_seconds": self.avg_execution_time_seconds,
            "avg_cost_cents": self.avg_cost_cents,
            "tags": self.tags,
            "icon": self.icon,
            "category": self.category,
        }

    @classmethod
    def from_agent(
        cls,
        agent: Any,
        agent_id: str | None = None,
        suggested_prompts: list[str] | None = None,
        avg_execution_time: float = 0.0,
        avg_cost_cents: float = 0.0,
    ) -> AgentSkillMetadata:
        """
        Create skill metadata from an agent instance.

        Args:
            agent: The agent instance
            agent_id: Optional agent ID (uses agent.agent_id if available)
            suggested_prompts: Optional example prompts
            avg_execution_time: Average execution time in seconds
            avg_cost_cents: Average cost in cents

        Returns:
            AgentSkillMetadata instance
        """
        # Extract basic info
        aid = agent_id or getattr(agent, "agent_id", None) or f"agent-{id(agent)}"
        name = getattr(agent, "name", None) or agent.__class__.__name__

        # Extract description from docstring or attribute
        description = (
            getattr(agent, "description", None)
            or getattr(agent, "__doc__", None)
            or f"{name} agent"
        )
        if description:
            description = description.strip().split("\n")[0]

        # Extract capabilities from A2A card
        capabilities = []
        a2a_card = getattr(agent, "_a2a_card", None)
        if a2a_card and isinstance(a2a_card, dict):
            if "capabilities" in a2a_card:
                caps = a2a_card["capabilities"]
                if isinstance(caps, list):
                    capabilities.extend(caps)
                elif isinstance(caps, str):
                    capabilities.append(caps)

        # Extract input schema from signature
        input_schema = None
        signature = getattr(agent, "_signature", None) or getattr(
            agent, "signature", None
        )
        if signature:
            input_schema = cls._extract_input_schema(signature)

        # Extract output types
        output_types = cls._extract_output_types(signature) if signature else []

        return cls(
            id=aid,
            name=name,
            description=description,
            capabilities=capabilities,
            suggested_prompts=suggested_prompts or [],
            input_schema=input_schema,
            output_types=output_types,
            avg_execution_time_seconds=avg_execution_time,
            avg_cost_cents=avg_cost_cents,
        )

    @classmethod
    def from_specialist_definition(
        cls,
        definition: Any,
        specialist_name: str,
    ) -> AgentSkillMetadata:
        """
        Create skill metadata from a SpecialistDefinition.

        Args:
            definition: SpecialistDefinition instance
            specialist_name: Name of the specialist

        Returns:
            AgentSkillMetadata instance
        """
        return cls(
            id=specialist_name,
            name=specialist_name.replace("-", " ").replace("_", " ").title(),
            description=getattr(
                definition, "description", f"{specialist_name} specialist"
            ),
            capabilities=getattr(definition, "available_tools", []),
            suggested_prompts=getattr(definition, "suggested_prompts", []),
            input_schema=None,
            output_types=["text"],
            avg_execution_time_seconds=getattr(definition, "avg_execution_time", 0.0),
            avg_cost_cents=getattr(definition, "avg_cost_cents", 0.0),
            tags=getattr(definition, "tags", []),
            category=getattr(definition, "category", None),
        )

    @staticmethod
    def _extract_input_schema(signature: Any) -> dict[str, Any] | None:
        """Extract JSON schema from signature input fields."""
        schema = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        try:
            for name, field_value in signature.__class__.__dict__.items():
                if hasattr(field_value, "__class__"):
                    field_class = field_value.__class__.__name__
                    if field_class == "InputField":
                        desc = getattr(field_value, "desc", "") or getattr(
                            field_value, "description", ""
                        )
                        schema["properties"][name] = {
                            "type": "string",
                            "description": desc,
                        }
                        # Check if required (no default)
                        if (
                            not hasattr(field_value, "default")
                            or field_value.default is None
                        ):
                            schema["required"].append(name)

            if not schema["properties"]:
                return None

            return schema
        except Exception as exc:
            # Introspecting an arbitrary signature object is best-effort — a
            # malformed/foreign signature yields "no schema", not a failure.
            # It is NOT silent: the fallback is logged so a systematically
            # unreadable signature is triageable (`rules/zero-tolerance.md`
            # Rule 3, `rules/observability.md` MUST Rule 3).
            logger.warning(
                "discovery.input_schema_extraction_failed",
                extra={
                    "error": scrub_credentials(str(exc)),
                    "signature": type(signature).__name__,
                },
            )
            return None

    @staticmethod
    def _extract_output_types(signature: Any) -> list[str]:
        """Extract output types from signature."""
        output_types = []

        try:
            for name, field_value in signature.__class__.__dict__.items():
                if hasattr(field_value, "__class__"):
                    field_class = field_value.__class__.__name__
                    if field_class == "OutputField":
                        output_types.append(name)

            return output_types if output_types else ["text"]
        except Exception as exc:
            # Sibling of `_extract_input_schema` above — same best-effort
            # introspection, same documented fallback, same WARN so the
            # fallback is never taken silently.
            logger.warning(
                "discovery.output_types_extraction_failed",
                extra={
                    "error": scrub_credentials(str(exc)),
                    "signature": type(signature).__name__,
                },
            )
            return ["text"]


class UserFilteredAgentDiscovery:
    """
    Extension for AgentRegistry to provide user-filtered agent discovery.

    Wraps an AgentRegistry and adds user permission filtering.

    Example:
        >>> registry = AgentRegistry()
        >>> discovery = UserFilteredAgentDiscovery(registry)
        >>> agents = await discovery.find_agents_for_user(
        ...     user_id="user-123",
        ...     organization_id="org-456",
        ... )
    """

    def __init__(
        self,
        registry: AgentRegistry,
        permission_checker: Any | None = None,
    ):
        """
        Initialize discovery extension.

        Args:
            registry: The AgentRegistry to wrap
            permission_checker: Optional permission checker (TrustOperations).
                When omitted, permission filtering is OFF and every user is
                granted `execute` on every agent — see the warning below.
        """
        self._registry = registry
        self._permission_checker = permission_checker

        # Introspected ONCE here, not per agent per call: does this checker
        # accept the duck-typed `user_id`/`organization_id` kwargs, or does it
        # take the `context=` mapping that `TrustOperations` declares? See
        # `_check_user_access` for why both shapes must be supported.
        self._checker_takes_user_kwargs = _accepts_user_kwargs(permission_checker)

        # `permission_checker` defaults to None, and with it None
        # `_check_user_access` unconditionally returns
        # `(True, AccessMetadata(permission_level="execute"))` for every user
        # and every agent. That is a SILENT NO-OP default on a security
        # control: the class is named `UserFilteredAgentDiscovery` and its
        # `find_agents_for_user` signature takes `user_id` +
        # `organization_id`, so the un-wired instance LOOKS filtered at every
        # call site while filtering nothing.
        #
        # `rules/security.md` § "Secure-Default For A New Security Feature"
        # requires such a default to fail CLOSED, or — where backward-compat
        # forbids on-by-default — to emit a LOUD one-time WARN naming the OFF
        # protection and its wiring. Fail-closed is NOT available here without
        # a posture decision: `permission_checker` has always defaulted to
        # None and this class's own docstring example constructs it that way,
        # so denying by default would break every existing caller. The WARN is
        # therefore the required remedy, not a softer substitute for one.
        #
        # Deliberately at __init__ (once per instance, one per distinct
        # un-wired wiring) rather than per call — a per-request warning on a
        # discovery hot path would be log spam and would be filtered out,
        # which is how a loud signal becomes a silent one.
        #
        # Distinct from the EXCEPTION path in `_check_user_access`, which now
        # fails CLOSED (a checker that raised has not approved anything). The
        # two are different questions: an un-wired instance never asked, a
        # raising checker was asked and could not answer.
        if permission_checker is None:
            logger.warning(
                "discovery.permission_filtering_disabled",
                extra={
                    "protection_off": (
                        "user permission filtering — every user is granted "
                        "'execute' on every agent returned by "
                        "find_agents_for_user()"
                    ),
                    "wiring": (
                        "pass permission_checker=<TrustOperations> to "
                        "UserFilteredAgentDiscovery(registry, "
                        "permission_checker=...)"
                    ),
                },
            )

    async def find_agents_for_user(
        self,
        user_id: str,
        organization_id: str,
        status_filter: AgentStatus | None = AgentStatus.ACTIVE,
        capability_filter: str | None = None,
    ) -> list[AgentWithAccess]:
        """
        Find agents accessible to a specific user.

        Args:
            user_id: User identifier
            organization_id: Organization identifier
            status_filter: Optional status filter (default: ACTIVE)
            capability_filter: Optional capability filter

        Returns:
            List of AgentWithAccess with access metadata

        Raises:
            ReasoningDegradedError: `capability_filter` ONLY — the LLM
                capability judge degraded for EVERY registered agent (#1981),
                so the registry has no ranking to filter. Deliberately
                PROPAGATED rather than converted to an empty list: `[]` is
                exactly what `find_agents_by_capability` used to return on a
                total judge failure, and every caller read it as "no agent has
                this capability". Swallowing it here would reinstate the bug
                #1981 exists to eliminate, one layer higher up. A WARN is
                emitted first so the degradation is triageable at THIS layer
                too (`rules/observability.md` MUST Rule 3).
        """
        # Get all agents from registry
        if capability_filter:
            try:
                agents = await self._registry.find_agents_by_capability(
                    capability_filter, status_filter
                )
            except ReasoningDegradedError as exc:
                logger.warning(
                    "discovery.find_agents_for_user.degraded",
                    extra={
                        "user_id": user_id,
                        "organization_id": organization_id,
                        "capability_filter": capability_filter,
                        "correlation_id": exc.correlation_id,
                        "helper": exc.helper,
                        "model": exc.model,
                        "error": exc.error,
                    },
                )
                raise
        else:
            agents = await self._registry.list_agents(status_filter=status_filter)

        # Filter by user permissions and add access metadata
        results = []
        for agent_metadata in agents:
            # Check permission
            has_access, access_meta = await self._check_user_access(
                user_id, organization_id, agent_metadata
            )

            if has_access:
                results.append(
                    AgentWithAccess(
                        metadata=agent_metadata,
                        access=access_meta,
                    )
                )

        return results

    async def _check_user_access(
        self,
        user_id: str,
        organization_id: str,
        agent_metadata: AgentMetadata,
    ) -> tuple[bool, AccessMetadata]:
        """
        Check if user has access to agent.

        Args:
            user_id: User identifier
            organization_id: Organization identifier
            agent_metadata: Agent metadata

        Returns:
            Tuple of (has_access, access_metadata)
        """
        # If permission checker is available, use it.
        #
        # `is not None`, matching `__init__`'s guard EXACTLY, and that identity
        # test is load-bearing rather than stylistic. This was `if
        # self._permission_checker:` — a TRUTHINESS test — while `__init__`
        # guards its loud "filtering is disabled" WARN on `permission_checker
        # is None`. Two guards over the same object disagreeing on one class of
        # value: a checker that is falsy but NOT None.
        #
        # Such a checker is ordinary, not exotic — any object defining
        # `__bool__` returning False or `__len__` returning 0: a policy-set /
        # rule-collection wrapper that is momentarily empty, a health-gated
        # checker reporting degraded. It skipped this entire block, fell
        # through to the terminal grant below, and emitted NO warning, because
        # the constructor only warns on `is None`. A checker was installed, and
        # every user was granted `execute` on every agent, silently — the exact
        # combination the WARN exists to make unreachable.
        if self._permission_checker is not None:
            try:
                # CALL SHAPE, and this was 100% broken for the DOCUMENTED
                # checker type. The docstring names `TrustOperations`, whose
                # real signature is
                #     verify(agent_id, action, resource=None, level=...,
                #            context=None)
                # — NO `user_id`, NO `organization_id`, NO `**kwargs`. Passing
                # them raised TypeError on the FIRST agent of every call, which
                # the `except` below caught and turned into a grant. So wiring
                # the documented checker meant EVERY agent was returned to
                # EVERY user, always — not a transient window, the steady
                # state. Verified by `inspect.signature`, not by reading.
                #
                # Nothing caught it because every existing test supplies a
                # bespoke duck-typed checker written to match this call site.
                #
                # Both shapes are supported rather than one being broken: the
                # duck-typed kwargs form (what consumers actually wired, and
                # what the tests use) and the `context=` form TrustOperations
                # declares. Introspected ONCE at __init__, not per agent.
                if self._checker_takes_user_kwargs:
                    result = await self._permission_checker.verify(
                        agent_id=agent_metadata.agent_id,
                        action="execute",
                        user_id=user_id,
                        organization_id=organization_id,
                    )
                else:
                    result = await self._permission_checker.verify(
                        agent_id=agent_metadata.agent_id,
                        action="execute",
                        context={
                            "user_id": user_id,
                            "organization_id": organization_id,
                        },
                    )

                # FAIL CLOSED on a malformed result. `hasattr(result, "valid")`
                # granted access to any object lacking `.valid` — a dict, None,
                # a renamed field — reading the ABSENCE of a deny signal as a
                # grant. `is not True` denies unless the checker affirmatively
                # said yes.
                #
                # Distinct QUESTION from the exception path below, though both
                # now deny: that one is about the checker ERRORING, this is
                # about it ANSWERING in a shape we cannot read. (An earlier
                # revision of this comment said the disposition below was
                # "deliberately unchanged" fail-open — it was already flipped
                # to fail-closed in the same commit that wrote the sentence.)
                # There is no availability trade-off to weigh here either way:
                # an unreadable answer is not an approval.
                if getattr(result, "valid", None) is not True:
                    return False, AccessMetadata.deny()

                # Extract constraints. `TrustOperations.VerificationResult`
                # exposes `effective_constraints`, NOT `constraints`, so the
                # old `hasattr(result, "constraints")` was False for the
                # documented type and every granted user silently received
                # UNLIMITED constraints. Both names are read.
                #
                # Read SEQUENTIALLY, not as a `getattr` default chain. A
                # default argument fires only when the attribute is ABSENT, so
                # `getattr(result, "constraints", getattr(result,
                # "effective_constraints", None))` returned None for a result
                # that DECLARES `constraints` (a None-defaulted dataclass
                # field) while POPULATING `effective_constraints` — the shape
                # any type carrying both names through a rename actually has.
                #
                # PRESENCE, not `isinstance(..., dict)`, is what selects
                # between the two names, and that is the fix rather than a
                # tidy-up. The dict test was still 100% WRONG for the
                # DOCUMENTED type one step further on: the sentence three
                # lines above says `effective_constraints` is what
                # `TrustOperations` populates, and that field is declared
                # `List[str]` (chain.py:854) — never a dict. So `isinstance(
                # raw, dict)` was False, the block fell through, and the
                # granted user received `AccessConstraints()`, every field
                # None, which this type encodes as UNLIMITED. Verbatim the
                # failure the paragraph above claims to have closed, still
                # live, one type-check over.
                #
                # It survived a regression suite written for it because every
                # new fixture supplied a DICT (`effective_constraints={
                # "max_tokens": 42}`) — a shape the documented type cannot
                # emit. The suite was shaped to the code, so it could only ever
                # confirm it. `normalize_access_constraints` is now pinned
                # against a REAL `kailash.trust.chain.VerificationResult`.
                raw = getattr(result, "constraints", None)
                if not _constraint_payload_present(raw):
                    raw = getattr(result, "effective_constraints", None)

                # FAIL CLOSED on a payload we cannot represent. The checker
                # affirmatively said `valid=True` AND affirmatively imposed
                # constraints; if we cannot express them, the choice is between
                # denying and granting UNLIMITED on axes the checker capped.
                # A denial is a recoverable availability event — the same trade
                # the exception branch below makes, for the same reason.
                constraints, unrepresentable = normalize_access_constraints(raw)
                if unrepresentable is not None:
                    logger.error(
                        "discovery.constraints_unrepresentable_failed_closed",
                        extra={
                            "user_id": user_id,
                            "organization_id": organization_id,
                            "agent_id": agent_metadata.agent_id,
                            # The reason names the offending key/label/type, so
                            # this line is the only signal distinguishing "the
                            # checker denied" from "the checker allowed but
                            # spoke a constraint vocabulary we cannot enforce".
                            # It is a LOCAL diagnostic about our own payload
                            # shape, but the labels/keys originate in a
                            # CALLER-SUPPLIED checker, so it is scrubbed on the
                            # same grounds as the exception branch below.
                            "reason": scrub_credentials(unrepresentable),
                        },
                    )
                    return False, AccessMetadata.deny()

                return True, AccessMetadata(
                    permission_level="execute",
                    constraints=constraints,
                )
            except Exception as exc:
                # FAIL CLOSED. A checker that raised has not approved
                # anything; an unanswered authorization question is not a yes.
                #
                # This branch previously fell through to the grant below
                # (fail-OPEN). The flip is deliberate and ratified, and it
                # accepts a real trade rather than overlooking one: a
                # transient checker outage now DENIES every user instead of
                # granting every user. That is the approved disposition — a
                # denial is a recoverable availability event, a wrong grant is
                # an unrecoverable disclosure. The prior fail-open was not a
                # neutral default: combined with the call-shape defect it
                # meant the DOCUMENTED checker type returned every agent to
                # every user as the steady state.
                #
                # The denial stays LOUD (ERROR, with the exception detail),
                # and the severity now matters more, not less: under
                # fail-closed a checker outage is a total discovery outage, so
                # this log line is the only signal distinguishing "nobody has
                # access" from "the checker is down".
                logger.error(
                    "discovery.permission_check_failed_closed",
                    extra={
                        "user_id": user_id,
                        "organization_id": organization_id,
                        "agent_id": agent_metadata.agent_id,
                        # SCRUBBED: `exc` comes from a CALLER-SUPPLIED
                        # permission_checker. If that checker is backed by a
                        # database or a remote service, its exception text is
                        # exactly the DSN/URL-bearing driver output this
                        # branch (#1970/#1974) exists to scrub — written RAW
                        # to ERROR would be the inverse of the sibling fix at
                        # `rich_output.py` (`observability.md` Rule 6.3:
                        # masking one surface and not another is BLOCKED).
                        "error": scrub_credentials(str(exc)),
                    },
                )
                # Well-formed metadata, never None: `find_agents_for_user`
                # unpacks this pair unconditionally, and a direct caller can
                # still call `.to_dict()` on the result. Same denial shape as
                # the malformed-result branch above — ONE constructor, so the
                # two denials are indistinguishable to consumers (the LOG is
                # what tells them apart) and no caller needs a second denial
                # code path.
                return False, AccessMetadata.deny()

        # Default: grant access with default constraints.
        #
        # Reachable ONLY when no permission_checker is wired — every path
        # inside the `if self._permission_checker is not None` block above
        # returns. That is true because the guard is an IDENTITY test: while it
        # was a truthiness test, a falsy-but-not-None checker reached here too,
        # and this line granted it access without any warning having fired.
        # The un-wired default is deliberately NOT changed by the fail-closed
        # flip: it is a separate posture question (an unconfigured discovery
        # instance is a wiring gap, not an authorization outage) and it is
        # already announced by the constructor's WARNING.
        return True, AccessMetadata(
            permission_level="execute",
            constraints=AccessConstraints(),
        )

    async def get_skill_metadata(
        self,
        agent_id: str,
    ) -> AgentSkillMetadata | None:
        """
        Get skill metadata for an agent.

        Args:
            agent_id: Agent identifier

        Returns:
            AgentSkillMetadata or None if agent not found
        """
        agent_metadata = await self._registry.get_agent(agent_id)
        if not agent_metadata:
            return None

        return AgentSkillMetadata.from_agent(
            agent=agent_metadata.agent,
            agent_id=agent_id,
        )

    async def list_skill_metadata(
        self,
        user_id: str | None = None,
        organization_id: str | None = None,
    ) -> list[AgentSkillMetadata]:
        """
        List skill metadata for all accessible agents.

        Args:
            user_id: Optional user ID for filtering
            organization_id: Optional organization ID for filtering

        Returns:
            List of AgentSkillMetadata
        """
        if user_id and organization_id:
            agents = await self.find_agents_for_user(user_id, organization_id)
            return [
                AgentSkillMetadata.from_agent(a.metadata.agent, a.agent_id)
                for a in agents
            ]
        else:
            agents = await self._registry.list_agents()
            return [AgentSkillMetadata.from_agent(a.agent, a.agent_id) for a in agents]


__all__ = [
    "DENIED_PERMISSION_LEVEL",
    "AccessConstraints",
    "AccessMetadata",
    "AgentWithAccess",
    "AgentSkillMetadata",
    "UserFilteredAgentDiscovery",
]
