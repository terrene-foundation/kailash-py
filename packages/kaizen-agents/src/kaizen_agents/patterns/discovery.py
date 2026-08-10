"""Agent discovery extensions for Enterprise-App integration.

Provides user-filtered agent discovery and skill metadata for UI integration.
"""

from __future__ import annotations

import inspect
import logging
import math
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from datetime import time as _time
from typing import Any, Final

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
    #: ADVISORY constraint LABELS the checker imposed, carried through verbatim.
    #:
    #: This is the `effective_constraints` label list that
    #: `kailash.trust.chain.VerificationResult` actually emits (`List[str]`,
    #: chain.py:854) — values like `"read_only"`, `"audit_required"`. They have
    #: NO cap semantics, so they are NOT expressible as `AccessConstraints`, and
    #: this field exists so the payload is not silently LOSSY about them.
    #:
    #: ADVISORY IS THE SDK'S OWN CLASSIFICATION, NOT OURS. The producing field,
    #: `DelegationRecord.constraint_subset`, is documented as read by NO
    #: allow/deny gate and DELIBERATELY EXCLUDED from the enforced envelope
    #: (`_derive_enforced_envelope`, advisory per #1896). The tightening is
    #: still ENFORCED, just not here: the same labels are bound into SIGNED
    #: derived capabilities at delegation time (`_build_signed_derived_caps`)
    #: and `verify()` re-derives the enforced constraint set from those signed
    #: sources, so a store-writer editing only the raw field cannot strip it.
    #:
    #: Consumers MAY surface these to a user or an auditor. Consumers MUST NOT
    #: treat an empty list as "no restrictions in force" — the real enforcement
    #: lives in the signed derived capabilities, not in this list.
    #:
    #: Appended LAST, after `denied`, so positional construction of every
    #: pre-existing field is unchanged.
    advisory_constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "permission_level": self.permission_level,
            "constraints": self.constraints.to_dict(),
            "granted_by": self.granted_by,
            "granted_at": self.granted_at,
            "expires_at": self.expires_at,
            "denied": self.denied,
            "advisory_constraints": list(self.advisory_constraints),
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


#: (user, label-set) pairs already announced by `normalize_access_constraints`.
#:
#: The advisory-label WARN is de-duplicated, not once-per-call:
#: `_check_user_access` runs per user PER AGENT inside `find_agents_for_user`,
#: so a per-call warning would emit O(users x agents) identical lines on a
#: discovery hot path — and a log line that floods is a log line that gets
#: filtered, which is how a loud signal becomes a silent one.
#:
#: KEYED ON `(user_id, sorted labels)`, AND THE USER HALF IS THE FIX, NOT AN
#: EMBELLISHMENT. Keyed on the label tuple ALONE, the warning announced the
#: FIRST user to hit a label set and was silent for every DISTINCT user after
#: — and the record carried no `user_id` either, so the one line that did fire
#: named a set of labels without naming anyone they applied to. An operator
#: reading it could not tell whether one user or ten thousand were affected,
#: which is the question the line exists to answer.
#:
#: The de-duplication that motivated the memo is preserved exactly: the
#: O(agents) factor is the flood (ONE user's single `find_agents_for_user` call
#: re-checks every registered agent), and that factor is still collapsed to one
#: line. Only the O(users) factor — which is a genuinely new fact each time,
#: because it is a different subject — is now allowed through.
#:
#: The label half stays SORTED so a NEW label combination still announces
#: itself instead of being masked by the first one ever seen.
#:
#: BOUNDED BY EVICTION, NOT BY REFUSING TO RECORD — and that distinction is
#: the whole reason this is an `OrderedDict` and not a `set`. The earlier form
#: stopped ADDING at the cap and warned unconditionally afterwards. Adding the
#: user dimension moved key cardinality from |label sets| (single digits in
#: practice) to |users| x |label sets|, so any deployment with more than
#: `_ADVISORY_LABELS_WARNED_CAP` distinct pairs SATURATES the memo permanently
#: — and past that point every un-memoized user warns on EVERY call. Since
#: `_check_user_access` runs per user PER AGENT, one `find_agents_for_user`
#: sweep then emits one WARN per registered agent, each also running
#: `scrub_credentials()` per label. That is verbatim the flood the memo exists
#: to prevent: `len(...) < CAP` gated the RECORDING and never the EMITTING.
#:
#: Evicting the least-recently-seen pair instead keeps the bound (memory is
#: still hard-capped) while preserving the de-duplication that motivated the
#: memo: a key is ALWAYS recorded, so the O(agents) factor inside a single
#: sweep still collapses to one line no matter how saturated the memo is. The
#: residual is recency-scoped rather than unbounded — a pair seen again after
#: `_ADVISORY_LABELS_WARNED_CAP` OTHER pairs have intervened announces a
#: second time. That is a rate limit, not a flood, and it degrades toward
#: MORE signal rather than less, which is the safe direction.
_ADVISORY_LABELS_WARNED: OrderedDict[tuple[str | None, tuple[str, ...]], None] = (
    OrderedDict()
)
_ADVISORY_LABELS_WARNED_CAP: Final[int] = 256


def _warn_advisory_constraints_once(labels: list[str], user_id: str | None) -> None:
    """Announce an advisory label set the FIRST time THIS USER is seen with it."""
    key = (user_id, tuple(sorted(labels)))
    if key in _ADVISORY_LABELS_WARNED:
        # Refresh recency: a pair still in active use must not be evicted by
        # unrelated traffic and then re-announce itself.
        _ADVISORY_LABELS_WARNED.move_to_end(key)
        return
    _ADVISORY_LABELS_WARNED[key] = None
    while len(_ADVISORY_LABELS_WARNED) > _ADVISORY_LABELS_WARNED_CAP:
        _ADVISORY_LABELS_WARNED.popitem(last=False)
    logger.warning(
        "discovery.advisory_constraints_not_enforced_here",
        extra={
            # The SUBJECT the labels were imposed on. Raw, matching the two
            # sibling ERROR lines in `_check_user_access`
            # (`constraints_unrepresentable_failed_closed`,
            # `permission_check_failed_closed`) which both write `user_id`
            # unscrubbed: a per-surface disagreement about whether this field
            # is sensitive is exactly the split-masking `observability.md`
            # Rule 6.3 blocks. `None` when the caller did not supply one —
            # `normalize_access_constraints` is public and reachable without a
            # user, and the memo key holds `None` as its own distinct subject.
            "user_id": user_id,
            # Labels originate in a CALLER-SUPPLIED checker, so they are
            # scrubbed on the same grounds as every other caller-derived value
            # written to a log in this module.
            "labels": [scrub_credentials(label) for label in sorted(labels)],
            "advisory": (
                "constraint labels are reporting-only and are NOT enforced as "
                "AccessConstraints; the SDK enforces the same labels via "
                "SIGNED derived capabilities re-derived by verify()"
            ),
        },
    )


def normalize_access_constraints(
    raw: Any,
    *,
    user_id: str | None = None,
) -> tuple[AccessConstraints | None, list[str], str | None]:
    """Turn a checker's constraint payload into `AccessConstraints`.

    `user_id` is the SUBJECT the payload was produced for. It is used for
    exactly one thing and is not otherwise consulted: it is half the key of the
    advisory-label WARN memo, so the warning announces once PER USER per label
    set rather than once per label set globally (which announced the first
    affected user and went silent for every distinct user after). Keyword-only
    and defaulted so the pre-existing single-argument call shape still works;
    omitted, the memo treats "no user" as its own distinct subject.

    Returns `(constraints, advisory_labels, None)` on success, or
    `(None, [], reason)` when the payload is PRESENT but cannot be
    represented — in which case the caller MUST fail closed. It never returns a
    default `AccessConstraints()` for a payload it could not READ, because on
    this type a default instance is UNLIMITED (see the class docstring) — i.e.
    the most permissive possible answer to a question we just failed to answer.

    THREE SHAPES, and the third is why this function exists:

    * **MAPPING** — `{"max_tokens": 42}`. Real cap semantics; all SEVEN fields
      are mapped. `Mapping`, not `dict`: a checker returning a `MappingProxy`,
      a `ChainMap`, or any `collections.abc.Mapping` implementation was
      previously rejected by an `isinstance(raw, dict)` test and its caps
      silently dropped.

    * **ABSENT / EMPTY** — no constraints imposed; an unrestricted grant.

    * **NON-EMPTY SEQUENCE OF LABELS** — `["read_only", "audit_required"]`.
      This is what the DOCUMENTED checker actually emits. It GRANTS, with
      default (uncapped) `AccessConstraints` and the labels carried forward in
      `advisory_labels`.

      IT DENIED, AND THAT WAS AN OVER-CORRECTION THIS DOCSTRING ONCE ARGUED
      FOR. The prior revision reasoned: the labels are a restriction the
      checker DID impose and this type CANNOT express, so the only honest
      dispositions are deny or grant caps we cannot justify — and it chose
      deny. The first half is still true. The conclusion was wrong, because it
      treated "we cannot express this" as "this is unenforced", and for THIS
      field the SDK says otherwise.

      `DelegationRecord.constraint_subset` — the field these labels come from
      — is documented at `src/kailash/trust/chain.py:350-363` as reporting-only
      in its RAW form: surfaced in `VerificationResult.effective_constraints`,
      read by NO allow/deny gate, and DELIBERATELY EXCLUDED from the enforced
      envelope (`_derive_enforced_envelope`, advisory per #1896). The same
      paragraph states the tightening is NOT a no-op: the labels are bound into
      SIGNED derived capabilities at delegation time
      (`_build_signed_derived_caps`) and `verify()` RE-DERIVES the enforced
      constraint set from those signed sources, so a store-writer editing only
      the raw field cannot strip it.

      So the control is ALREADY correctly enforced, one layer down, by
      signature. Denying here adds NO safety and removes availability: because
      `find_agents_for_user` filters on `has_access`, an agent established with
      the SDK's own documented `constraints=["read_only"]` vanished from every
      user's list with NO error — indistinguishable from an outage. The only
      operator lever was `permission_checker=None`, which this module itself
      calls a "SILENT NO-OP default on a security control": the remedy offered
      to a denied operator was to switch the control OFF.

      The labels are still not silently dropped. They ride out in
      `advisory_labels` -> `AccessMetadata.advisory_constraints` -> `to_dict()`,
      so a consumer SEES what was imposed, and a once-per-distinct-set WARN
      names them.

      STILL NO INVENTED GRAMMAR. The labels carry no number, no field name and
      no `key=value` form; splitting on `=` or pattern-matching `max_tokens_42`
      would fabricate a grammar the producing type does not emit, and every
      label failing the invented parse would fall back to UNLIMITED. Nothing
      here parses a label — they are copied verbatim.

    Anything else present — a bare string, an int, an arbitrary object, a
    mapping carrying an unrecognized key or an unusable value type — is
    genuinely UNREADABLE and still denies. An unrecognized key is deliberately
    NOT ignored: a checker sending `{"max_requests_per_hour": 5}` capped an
    axis, and silently dropping it grants unlimited on exactly that axis,
    which is the defect class this function closes. Only the advisory
    LABEL-LIST case flips to grant; the seven-field validation is untouched.
    """
    if not _constraint_payload_present(raw):
        return AccessConstraints(), [], None

    if isinstance(raw, Mapping):
        constraints = AccessConstraints()
        assigned: dict[str, Any] = {}
        # MATERIALIZE ONCE. Every decision below reads THIS snapshot, never
        # `raw` again — which is what makes the check sound rather than merely
        # plausible.
        #
        # An earlier revision compared `len(raw)` against a count taken while
        # iterating. That was a SECOND, INDEPENDENT `__len__` call (the first
        # is in `_constraint_payload_present`), and comparing read #2 against
        # an iteration says nothing about read #1 — which is the read that
        # decided we are in this branch at all. A `Mapping` whose `__len__` is
        # not idempotent (returns 1, then 0) walked straight through it:
        # presence saw 1 and entered, the guard compared 0 against 0, agreed
        # with itself, and fell out of the bottom returning the untouched
        # `AccessConstraints()` — UNLIMITED (class docstring). The guard
        # written to stop exactly that outcome was defeated by the same CLASS
        # of object, lying on a different axis.
        #
        # One `list(raw.items())` removes the axis entirely: after this line
        # there is no live object left to disagree with, so no re-derivation is
        # possible by construction rather than by comparison.
        #
        # An EMPTY snapshot is then UNREADABLE, not empty: presence already
        # asserted this payload holds pairs (a genuinely empty one returns the
        # unrestricted grant at the top of the function and never reaches
        # here), so yielding none contradicts that assertion and there is no
        # honest answer to "what did the checker cap?". Costs a well-behaved
        # mapping NOTHING — `dict`, `MappingProxy`, `ChainMap` all materialize
        # exactly what they reported.
        pairs = list(raw.items())
        if not pairs:
            return (
                None,
                [],
                (
                    "constraint mapping reported a non-empty payload but "
                    "yielded no entries; its len() and items() disagree and "
                    "the payload cannot be read"
                ),
            )
        for key, value in pairs:
            if not isinstance(key, str):
                return None, [], f"constraint key {key!r} is not a string"
            field_name = _CONSTRAINT_KEY_ALIASES.get(key)
            if field_name is None:
                return (
                    None,
                    [],
                    (
                        f"unrecognized constraint key {key!r} (recognized: "
                        f"{', '.join(sorted(_CONSTRAINT_KEY_ALIASES))})"
                    ),
                )
            if value is None:
                continue
            coerced, ok = _CONSTRAINT_COERCERS[field_name](value)
            if not ok:
                return (
                    None,
                    [],
                    (
                        f"constraint {key!r} carries an unusable value "
                        f"({type(value).__name__})"
                    ),
                )
            # Alias collision. `max_tokens` and `max_tokens_per_session` land
            # on the SAME field, so a payload carrying both with DIFFERENT
            # values has two answers and dict order picks one; that silent
            # coin-flip between two caps is itself a fail-closed case.
            if field_name in assigned and assigned[field_name] != coerced:
                return (
                    None,
                    [],
                    (
                        f"conflicting values for {field_name!r} "
                        f"({assigned[field_name]!r} vs {coerced!r})"
                    ),
                )
            assigned[field_name] = coerced
            setattr(constraints, field_name, coerced)
        return constraints, [], None

    if isinstance(raw, (Sequence, AbstractSet)) and not isinstance(
        raw, (str, bytes, bytearray)
    ):
        # EVERY element must be a real label. A non-`str` element means this is
        # not the documented label-list shape at all, and we are back to a
        # payload we cannot read — which still denies. Checked BEFORE the grant
        # so a `[{"max_tokens": 42}]` or `[None]` cannot ride the advisory path
        # into an uncapped grant.
        # MATERIALIZE ONCE, for the reason spelled out in the mapping branch,
        # and this branch needed it MORE: the pre-existing code walked `raw`
        # THREE separate times — `all(...)`, the `offenders` comprehension, and
        # the label comprehension. A one-shot `__iter__` (an iterator, a
        # generator-backed view, a cursor) is exhausted by the first walk, so
        # the element check ran over the real elements and the labels were
        # built from an EMPTY second walk. `all(...)` over nothing is
        # vacuously True, so the payload passed validation and granted with
        # `labels == []`: UNLIMITED, and with no disclosure either, because
        # the label list it would have disclosed is the empty one.
        #
        # Counting `len(raw)` against the walk did not close it, for the same
        # reason it did not close the mapping branch — a container lying on
        # `__len__` as well answers `0 == 0` and agrees with itself.
        items = list(raw)
        if not items:
            return (
                None,
                [],
                (
                    "constraint label list reported a non-empty payload but "
                    "yielded no elements; its len() and iteration disagree "
                    "and the payload cannot be read"
                ),
            )
        if not all(isinstance(item, str) for item in items):
            offenders = ", ".join(
                sorted(
                    {type(item).__name__ for item in items if not isinstance(item, str)}
                )
            )
            return (
                None,
                [],
                (
                    "constraint label list carries non-string elements "
                    f"({offenders}) and cannot be read as labels"
                ),
            )
        labels = [str(item) for item in items]
        _warn_advisory_constraints_once(labels, user_id)
        # GRANT with DEFAULT constraints. `AccessConstraints()` is the UNLIMITED
        # value of this type (class docstring), and that is the correct answer
        # here rather than an accident: the checker imposed no numeric cap on
        # any of the seven axes this type models. It imposed advisory labels,
        # which are returned separately and enforced by the SDK's signed
        # derived capabilities.
        return AccessConstraints(), labels, None

    return (
        None,
        [],
        (
            f"constraint payload of type {type(raw).__name__} cannot be read as "
            "constraints"
        ),
    )


def _require_identity_or_raise(
    user_id: str | None,
    organization_id: str | None,
    *,
    surface: str,
    omission_remedy: str,
) -> tuple[str, str]:
    """THE fail-closed caller-identity predicate. One implementation, N surfaces.

    Every public surface of `UserFilteredAgentDiscovery` that takes a caller
    identity routes here. That is not tidiness: the identity check landed
    piecemeal, one surface per review round, and each round the sibling that
    did not get it kept the exact defect the round had just closed. A predicate
    the surfaces SHARE cannot drift; three that "must agree" always do
    (`rules/security.md` § Credential Decode Helpers states the general form,
    § Enforcement-Surface Parity the specific one).

    Two refusals, and both are refusals of MALFORMED INPUT rather than of a
    caller:

    * MISSING / PARTIAL — one or both halves are `None`. A half-identity
      previously WIDENED to "every registered agent", so a caller who supplied
      LESS received MORE, which is the inverse of what an authorization
      parameter means. Refusing is the only disposition an attacker cannot
      reach by choosing what to omit.
    * BLANK — a supplied half is empty or whitespace-only. Refused rather than
      forwarded because a blank id is not a scope the permission checker can
      evaluate, and checkers differ on what they do with one: a LAX checker
      reads an empty organization as "unscoped" and GRANTS. `security.md`
      § Input Validation puts that check at the boundary, and the § Redactor
      Contract length floor is the same shape — refuse with a typed error
      naming the offending field rather than hand a degenerate value to the
      authority and hope.

    `is not None`, NOT truthiness, and the identity test is load-bearing:
    `_FalsyOrgId("org-1")` — present, non-empty, `__bool__` False — is SUPPLIED
    and gets mediated, which is precisely the case a truthiness guard got
    wrong. The BLANK check that follows is not truthiness coming back through
    the side door; it asks a different question of a different thing (does a
    supplied STRING carry characters), and it is `isinstance`-gated so a
    non-`str` id type is never asked.

    `omission_remedy` is the one sentence that legitimately differs per
    surface, because the surfaces genuinely differ: the skill-metadata methods
    default both parameters and therefore HAVE a documented unfiltered form to
    point the caller at, while `find_agents_for_user` declares both as required
    `str` and has none. Parameterising the remedy is what lets the CHECK stay
    identical while the ADVICE stays accurate.

    Returns the NARROWED `(user_id, organization_id)` pair rather than a bool
    so the callee signatures (`_check_user_access` declares `str`, not
    `str | None`) are satisfied by control flow instead of by a correlation the
    type system cannot see.
    """
    supplied = {
        "user_id": user_id is not None,
        "organization_id": organization_id is not None,
    }
    if not all(supplied.values()):
        missing = [name for name, present in supplied.items() if not present]
        given = [name for name, present in supplied.items() if present]
        raise ValueError(
            f"{surface}() received a {'PARTIAL' if given else 'MISSING'} caller "
            "identity: "
            + (
                f"{', '.join(given)} supplied, {', '.join(missing)} missing. "
                if given
                else f"{' and '.join(missing)} are both absent. "
            )
            + "Both are required to filter by permission; supplying one alone "
            "previously returned every registered agent unfiltered. " + omission_remedy
        )

    blank = [
        name
        for name, value in (
            ("user_id", user_id),
            ("organization_id", organization_id),
        )
        if isinstance(value, str) and not value.strip()
    ]
    if blank:
        raise ValueError(
            f"{surface}() received a BLANK caller identity: "
            f"{', '.join(blank)} is empty or whitespace-only. An empty "
            "identity is not a permission scope; it previously bypassed "
            "filtering and returned every registered agent. " + omission_remedy
        )

    # Narrowed by the `is not None` guard above.
    return user_id, organization_id  # type: ignore[return-value]


#: Remedy sentence for the two surfaces that DO have a documented unfiltered
#: form (both identity parameters are defaulted, so omitting them is a
#: pre-existing supported call shape kept reachable-but-loud).
_REMEDY_UNFILTERED_AVAILABLE: Final[str] = (
    "Pass a real identity for both, or omit both arguments to explicitly "
    "request the unfiltered listing."
)

#: Remedy sentence for `find_agents_for_user`, which declares both parameters
#: as required `str` with no default. An all-`None` call was never a supported
#: shape there, so there is no unfiltered form to offer and none is invented:
#: offering one would ADD a wide path under cover of a fail-closed fix.
_REMEDY_NO_UNFILTERED_FORM: Final[str] = (
    "Both are required on this surface, which has no unfiltered form; use "
    "list_skill_metadata() with no arguments if an unmediated listing is "
    "genuinely intended."
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

        #: Skill-metadata surfaces that have already warned about being called
        #: without a caller identity. Per INSTANCE and per SURFACE so the wide
        #: path is announced once for each distinct unmediated call site,
        #: rather than once per request (spam) or once per process (a second
        #: mis-wired surface would be silenced by the first).
        self._warned_unfiltered_surfaces: set[str] = set()

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
            ValueError: The caller identity is PARTIAL (exactly one half
                supplied), MISSING (neither) or BLANK (a supplied half is
                empty/whitespace-only). Fail CLOSED — see
                `_require_identity_or_raise`. Unlike the two skill-metadata
                surfaces this method has NO unfiltered form to fall back to:
                both parameters are declared required `str` with no default, so
                an identity-less call was never a supported shape here and
                inventing one now would ADD a wide path under cover of a
                fail-closed fix.
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
        # FIRST, before any registry work. This surface is the one that returns
        # the RICHER payload (`AgentWithAccess` carries `AccessMetadata` — the
        # permission level and the whole constraint envelope), and it is also
        # the MEDIATED PATH `list_skill_metadata` delegates to. The guard
        # therefore belongs in this CALLEE rather than only in the callers
        # above it: placed here it closes the class, placed there it would
        # close two instances of it.
        #
        # The refusal precedes the registry lookup because a degenerate
        # identity is not a scope any lookup can be performed under — both
        # branches below (`find_agents_by_capability` and `list_agents`) are
        # covered by the single guard rather than one each.
        user_id, organization_id = _require_identity_or_raise(
            user_id,
            organization_id,
            surface="find_agents_for_user",
            omission_remedy=_REMEDY_NO_UNFILTERED_FORM,
        )

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
                constraints, advisory_labels, unrepresentable = (
                    normalize_access_constraints(raw, user_id=user_id)
                )
                # `constraints is None` IS PART OF THE GUARD, not a type-checker
                # appeasement. `normalize_access_constraints` documents its
                # failure shape as `(None, [], reason)`, so today the two
                # conditions coincide and this second test never fires on its
                # own. It is here because of what happens if they EVER come
                # apart: a future edit returning `(None, labels, None)` — a
                # helper that forgets to set a reason, a branch added below the
                # return — would hand `None` to `AccessMetadata(constraints=)`,
                # whose consumers then read `.max_daily_invocations` off None
                # (an AttributeError turning an authorization decision into a
                # crash) or, worse, treat the absent object as "no caps" — which
                # on this type is UNLIMITED, the exact failure the whole
                # function exists to prevent, re-entering through the ONE hole
                # the reason-string guard does not cover.
                #
                # Testing the value we are about to USE, rather than a sibling
                # field that currently correlates with it, is what makes that
                # unreachable rather than merely unlikely. It also lets the
                # declared `AccessConstraints` (non-optional) parameter type
                # stay honest instead of being widened to accept None, which
                # would push the same question onto every consumer.
                if unrepresentable is not None or constraints is None:
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
                            #
                            # The fallback is NOT decoration: it is the message
                            # for the `constraints is None` half of the guard,
                            # which by construction has no reason string. A
                            # denial whose log line said only `None` would be
                            # indistinguishable from a checker denial — and this
                            # branch means the normalizer broke its own
                            # documented contract, which is the single most
                            # important thing this line could say.
                            "reason": scrub_credentials(
                                unrepresentable
                                if unrepresentable is not None
                                else (
                                    "normalize_access_constraints returned no "
                                    "constraints and no reason; treating as "
                                    "unreadable"
                                )
                            ),
                        },
                    )
                    return False, AccessMetadata.deny()

                # `permission_level="execute"` RESTATES THE CHECKER'S VERDICT;
                # it does not widen it. Adjudicated, because the grant looks
                # like an over-grant when `advisory_labels` carries something
                # like `"read_only"` and this line still says "execute".
                #
                # The checker was asked ONE question — `verify(agent_id,
                # action="execute", ...)` forty lines above — and its answer
                # surface is `VerificationResult.valid: bool`
                # (`src/kailash/trust/chain.py:841-856`). That type declares NO
                # permission-level field, so there is no narrower verdict being
                # under-reported here: `valid=True` for `action="execute"` IS
                # the verdict, and this echoes the action it approved.
                #
                # The labels are NOT that verdict. They arrive in
                # `effective_constraints`, whose producing field
                # (`DelegationRecord.constraint_subset`) is documented at
                # `chain.py:350-363` as read by NO allow/deny gate and
                # DELIBERATELY EXCLUDED from the enforced envelope. Reading
                # `"read_only"` as a demotion of the verdict would be this
                # module deciding an allow/deny question the SDK states this
                # field does not answer — and would require parsing the label,
                # which `normalize_access_constraints` refuses to do for the
                # documented reason that the producing type emits no grammar to
                # parse.
                #
                # So this payload is the label-free valid grant PLUS a
                # disclosure: identical `permission_level`, identical
                # `constraints`, with `advisory_constraints` naming what the
                # checker imposed. Strictly more information, never wider —
                # which is the property
                # `tests/regression/test_issue_1720_discovery_grant_fidelity.py`
                # pins, so a future edit that lets the label path out-grant the
                # label-free path fails loudly.
                return True, AccessMetadata(
                    permission_level="execute",
                    constraints=constraints,
                    advisory_constraints=advisory_labels,
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

    def _resolve_identity_scope(
        self,
        user_id: str | None,
        organization_id: str | None,
        *,
        surface: str,
        protection_off: str,
    ) -> tuple[str, str] | None:
        """Decide whether a skill-metadata call is identity-scoped.

        THE OPTIONAL-IDENTITY WRAPPER around `_require_identity_or_raise`. This
        method owns exactly ONE thing the shared predicate does not: the
        NEITHER-supplied case, which on these two surfaces means "the caller
        explicitly asked for the unfiltered listing" and is a documented
        pre-existing shape. Everything else — the PARTIAL refusal, the BLANK
        refusal, the narrowing — is delegated, because it must be IDENTICAL at
        every identity-taking surface in this class and the ONLY way to
        guarantee that is to have one implementation
        (`rules/security.md` § Enforcement-Surface Parity).

        The earlier form of this method carried those checks INLINE, which is
        how `find_agents_for_user` — the third identity-taking surface, and the
        one this class's own docstring advertises — went two review rounds
        without them: there was nothing for it to call.

        Returns the NARROWED `(user_id, organization_id)` pair when the call is
        MEDIATED, or None for the unfiltered legacy path.

        Returning the pair rather than a bool is deliberate: `_check_user_access`
        and `find_agents_for_user` both declare `user_id: str` (not optional),
        so a bool return would leave every call site passing `str | None` into a
        `str` parameter and relying on a correlation the type system cannot see
        — precisely the "sibling field that currently correlates" shape the
        constraints guard above was fixed for. Handing back the narrowed values
        makes the guarantee the guard actually provides the same thing the
        callee's signature demands.

        THREE CASES, and only the third is decided here:

        * BOTH supplied -> mediated (the shared predicate narrows and returns).
        * EXACTLY ONE supplied, or a supplied half BLANK -> `ValueError` from
          the shared predicate. FAIL CLOSED.
        * NEITHER supplied -> unfiltered, but LOUD (once per instance per
          surface). THIS case is what makes these two surfaces different from
          `find_agents_for_user`, and it is the only reason this wrapper exists.

        The NEITHER branch is tested FIRST and with `is None`, NOT truthiness,
        and that ordering is load-bearing: under the old truthiness guard
        `organization_id=""` (or any org id whose `__bool__` is False, or whose
        `__len__` is 0 — an id type wrapping an empty tenant scope) was NOT
        "supplied", so it fell to the unfiltered branch and disclosed every
        agent's `input_schema` and `capabilities` with no check and no warning.
        Under identity it IS supplied, so it reaches the shared predicate,
        which refuses it as malformed rather than widening.
        """
        # NEITHER-supplied is decided here and nowhere else: it is the only
        # disposition that differs between this wrapper and the required-identity
        # surface. Everything below the branch is delegated so the two cannot
        # diverge. Written as an explicit `is None` conjunction rather than an
        # `all(...)` over a dict so the narrowing falls out of control flow.
        if user_id is not None or organization_id is not None:
            return _require_identity_or_raise(
                user_id,
                organization_id,
                surface=surface,
                omission_remedy=_REMEDY_UNFILTERED_AVAILABLE,
            )

        # Unfiltered path. Kept reachable because it predates this change and
        # is the documented single-tenant / internal-catalogue usage, so
        # fail-closed here would break existing callers — the same
        # backward-compat constraint `__init__` faces, resolved the same way
        # (`rules/security.md` § "Secure-Default For A New Security Feature":
        # loud WARN when on-by-default is not available). What changes is that
        # the wide path is no longer SILENT (`rules/zero-tolerance.md` Rule 3).
        #
        # Once per instance per surface, matching `__init__`'s one-time
        # warning: a per-call warning on a discovery hot path is log spam, and
        # spam is how a loud signal becomes a filtered-out one
        # (`rules/observability.md` MUST NOT § log-spam in hot loops).
        if surface not in self._warned_unfiltered_surfaces:
            self._warned_unfiltered_surfaces.add(surface)
            logger.warning(
                f"discovery.{surface}.unfiltered",
                extra={
                    "protection_off": protection_off,
                    "wiring": (
                        f"pass user_id= and organization_id= to {surface}() to "
                        "filter by caller permission"
                    ),
                },
            )
        return None

    async def get_skill_metadata(
        self,
        agent_id: str,
        user_id: str | None = None,
        organization_id: str | None = None,
    ) -> AgentSkillMetadata | None:
        """
        Get skill metadata for an agent.

        When `user_id` AND `organization_id` are supplied the lookup is
        MEDIATED through `_check_user_access`, and a denied caller receives
        `None` — deliberately indistinguishable from "no such agent", so a
        denial does not confirm the agent exists.

        This surface previously took no identity at all and performed NO
        permission check, while returning the agent's signature-derived
        `input_schema`, its capabilities and its suggested prompts — the same
        disclosure class as the gated-`inputSchema` MCP leak closed under this
        issue. The identity parameters are optional rather than required
        because out-of-package callers already invoke the one-argument form;
        the unscoped call is preserved and made loud instead
        (see `_resolve_identity_scope`).

        Args:
            agent_id: Agent identifier
            user_id: Caller's user ID. Required together with
                `organization_id`; supplying exactly one raises `ValueError`.
            organization_id: Caller's organization ID.

        Returns:
            AgentSkillMetadata, or None if the agent is absent OR the caller
            is not permitted to see it.

        Raises:
            ValueError: If exactly one of `user_id` / `organization_id` is
                supplied (fail closed on a partial identity).
        """
        scope = self._resolve_identity_scope(
            user_id,
            organization_id,
            surface="get_skill_metadata",
            protection_off=(
                "per-caller permission filtering — the agent's input_schema, "
                "capabilities and suggested prompts are returned to any caller"
            ),
        )

        agent_metadata = await self._registry.get_agent(agent_id)
        # `is None`, not truthiness — swept alongside the identity guard above
        # under `rules/security.md` § Enforcement-Surface Parity rather than
        # left as the one remaining instance of the class in this file.
        # `_registry` is INJECTED, so `get_agent` may return any duck-typed
        # metadata object; one defining `__len__`/`__bool__` (a metadata type
        # that proxies its capability collection, say) would read as absent
        # while being a live record. That direction fails CLOSED — the caller
        # gets None — so it is a correctness bug rather than a disclosure one,
        # which is precisely why it would have sat here unnoticed.
        if agent_metadata is None:
            return None

        if scope is not None:
            scoped_user_id, scoped_org_id = scope
            has_access, _ = await self._check_user_access(
                scoped_user_id, scoped_org_id, agent_metadata
            )
            if not has_access:
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
            user_id: Caller's user ID. Required together with
                `organization_id`; supplying exactly one raises `ValueError`.
            organization_id: Caller's organization ID.

        Returns:
            List of AgentSkillMetadata

        Raises:
            ValueError: If exactly one of `user_id` / `organization_id` is
                supplied (fail closed on a partial identity).
        """
        scope = self._resolve_identity_scope(
            user_id,
            organization_id,
            surface="list_skill_metadata",
            protection_off=(
                "per-caller permission filtering — every registered agent's "
                "input_schema and capabilities are returned to any caller"
            ),
        )

        if scope is not None:
            scoped_user_id, scoped_org_id = scope
            agents = await self.find_agents_for_user(scoped_user_id, scoped_org_id)
            return [
                AgentSkillMetadata.from_agent(a.metadata.agent, a.agent_id)
                for a in agents
            ]

        unfiltered = await self._registry.list_agents()
        return [AgentSkillMetadata.from_agent(a.agent, a.agent_id) for a in unfiltered]


__all__ = [
    "DENIED_PERMISSION_LEVEL",
    "AccessConstraints",
    "AccessMetadata",
    "AgentWithAccess",
    "AgentSkillMetadata",
    "UserFilteredAgentDiscovery",
]
