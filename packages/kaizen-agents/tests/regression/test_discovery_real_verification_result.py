# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Constraint extraction, pinned against the REAL `VerificationResult`.

WHY THIS FILE EXISTS, and why it is not a second copy of the sibling suite.

`test_discovery_falsy_checker_and_denial_shape.py` already claims to have
closed "the granted user silently received UNLIMITED constraints". It did not,
and it could not have, because every fixture in it supplies a **dict**::

    effective_constraints={"max_tokens": 42, "max_daily_invocations": 7}

The documented checker type cannot emit that shape. Empirically, against the
real class rather than against a reading of it::

    >>> from kailash.trust.chain import VerificationResult
    >>> VerificationResult(valid=True).effective_constraints
    []
    >>> hasattr(VerificationResult(valid=True), "constraints")
    False

`effective_constraints` is declared `List[str]` (chain.py:854) and populated by
`TrustOperations.verify` from `chain.get_effective_constraints(...)`
(operations/__init__.py:1244), which set-unions constraint LABELS and returns
`List[str]` (chain.py:1028-1043). So the guard the sibling suite exercised —
`isinstance(raw, dict)` — was **False for the documented type**, the extraction
block never ran, and the granted user received `AccessConstraints()`: every
field None, which that type encodes as UNLIMITED. Verbatim the failure the
sibling suite's own docstring says it closed, one type-check over.

A fixture shaped to the CODE can only ever confirm the code. Every fixture here
is shaped to what a PRODUCTION path emits: the tests below import
`kailash.trust.chain.VerificationResult` and construct the real thing, so if
the SDK's shape ever moves, `test_real_type_shape_is_what_this_suite_assumes`
fails loudly instead of this suite quietly re-confirming a stale belief.

WHAT THE LABEL GRAMMAR TURNED OUT TO BE. The labels are OPAQUE — `"read_only"`,
`"audit_required"` — with no number, no field name and no `key=value` form.
`DelegationRecord.constraint_subset` documents them as "constraint labels ...
read by NO allow/deny gate" (chain.py:350-352), and the in-SDK consumer folds
them as `{c: True for c in ...}` (runtime/trust/verifier.py:398) — each label is
a BOOLEAN FLAG, not a cap. There is therefore no grammar to parse into
`AccessConstraints`, and inventing one would mean every label that failed the
invented parse fell back to unlimited.

THE DISPOSITION IS NOT "FAIL CLOSED ON THEIR PRESENCE" — this paragraph said so
while the tests below already said otherwise, and the tests are right. Denying
on a label list was tried and REVERTED: the same `chain.py:350-363` paragraph
that calls the raw field advisory also states the tightening IS enforced, by
SIGNED derived capabilities that `verify()` re-derives — so denying here added
no safety and removed every constraint-labelled agent from every user's
discovery list. The disposition is GRANT, with the labels carried verbatim into
`AccessMetadata.advisory_constraints` so nothing is silently dropped. The grant
is pinned as never-wider-than-the-label-free-grant in
`test_issue_1720_discovery_grant_fidelity.py`.
"""

from __future__ import annotations

import math
from types import MappingProxyType

import pytest

from kailash.trust.chain import VerificationResult
from kaizen_agents.patterns.discovery import (
    DENIED_PERMISSION_LEVEL,
    AccessConstraints,
    UserFilteredAgentDiscovery,
    normalize_access_constraints,
)
from kaizen_agents.patterns.registry import AgentRegistry

pytestmark = pytest.mark.regression


class _Meta:
    """Minimal stand-in for AgentMetadata; only `agent_id` is read."""

    agent_id = "agent-1"


class _RealTrustOperationsShaped:
    """Mirrors `TrustOperations.verify` EXACTLY and returns the REAL type.

    The signature carries no `user_id` and no `**kwargs`, so
    `_accepts_user_kwargs` resolves it to the `context=` call shape — the same
    branch the documented checker takes in production.
    """

    def __init__(self, result: VerificationResult) -> None:
        self._result = result

    async def verify(self, agent_id, action, resource=None, level=None, context=None):
        return self._result


class _DuckTyped:
    """The shape consumers actually wired: kwargs in, `constraints` out."""

    def __init__(self, valid: bool, constraints=None) -> None:
        self._valid = valid
        self._constraints = constraints

    async def verify(self, agent_id, action, user_id, organization_id):
        return type("R", (), {"valid": self._valid, "constraints": self._constraints})()


async def _check(checker):
    discovery = UserFilteredAgentDiscovery(AgentRegistry(), permission_checker=checker)
    return await discovery._check_user_access("user-1", "org-1", _Meta())


class TestRealVerificationResultGroundTruth:
    """The fixture's own premises, asserted against the real class."""

    def test_real_type_shape_is_what_this_suite_assumes(self) -> None:
        """If the SDK moves, fail HERE rather than silently elsewhere.

        Every other test in this file is only meaningful while these three
        facts hold. Pinning them makes the suite self-invalidating instead of
        quietly re-confirming a stale reading of the type.
        """
        result = VerificationResult(valid=True)

        assert isinstance(result.effective_constraints, list), (
            "effective_constraints is no longer a list; this suite's premise "
            "that the documented checker emits a LABEL SEQUENCE is stale"
        )
        assert result.effective_constraints == [], (
            "effective_constraints no longer defaults to empty; the "
            "unconstrained-grant path below is testing something else"
        )
        assert not hasattr(result, "constraints"), (
            "VerificationResult grew a `constraints` attribute; the "
            "sequential two-name read in _check_user_access must be re-checked"
        )

    def test_real_labels_are_opaque_strings(self) -> None:
        """No cap semantics to parse — the premise of the fail-closed call."""
        result = VerificationResult(
            valid=True, effective_constraints=["read_only", "audit_required"]
        )
        assert all(isinstance(item, str) for item in result.effective_constraints)
        assert not any("=" in item for item in result.effective_constraints), (
            "a label grew a key=value shape; a parser may now be justified "
            "where inventing one previously was not"
        )


class TestDocumentedCheckerAdvisoryLabelsGrantAndAreCarried:
    """The documented checker's OWN label list must not remove availability.

    THIS CLASS PREVIOUSLY ASSERTED THE OPPOSITE, AND THAT ASSERTION PINNED AN
    OVER-CORRECTION. It required `granted is False` for a
    `VerificationResult(valid=True, effective_constraints=[...])` — the exact
    shape `TrustOperations.verify` emits for the SDK's own documented
    `CapabilityRequest(constraints=["read_only"])`. Because
    `find_agents_for_user` filters on `has_access`, that agent then vanished
    from every user's list with NO error, indistinguishable from an outage,
    and the only operator lever was `permission_checker=None` — i.e. switching
    the security control off.

    The deny was argued from "the checker imposed a restriction we cannot
    express", which is true, and "therefore the restriction is unenforced",
    which is FALSE for this field. `src/kailash/trust/chain.py:350-363` states
    `constraint_subset` is reporting-only in its RAW form AND that the same
    labels are bound into SIGNED derived capabilities that `verify()`
    re-derives the enforced constraint set from — so the tightening IS
    enforced, one layer down, by signature. Denying here added no safety and
    removed availability.

    The teeth that remain: the labels must be CARRIED, not silently dropped.
    """

    @pytest.mark.asyncio
    async def test_label_constraints_grant_rather_than_vanish_the_agent(
        self,
    ) -> None:
        checker = _RealTrustOperationsShaped(
            VerificationResult(
                valid=True, effective_constraints=["read_only", "audit_required"]
            )
        )
        granted, access = await _check(checker)

        assert granted is True, (
            "the SDK's OWN documented checker returned valid=True with its "
            "OWN documented label list, and discovery denied — the agent "
            "disappears from every user's list with no error. The labels are "
            "advisory by SDK design (chain.py:350-363) and the real tightening "
            "is enforced via signed derived capabilities."
        )
        assert access.denied is False
        assert access.permission_level == "execute"

    @pytest.mark.asyncio
    async def test_labels_are_carried_forward_not_silently_dropped(self) -> None:
        """Granting must not make the payload LOSSY about what was imposed."""
        checker = _RealTrustOperationsShaped(
            VerificationResult(
                valid=True, effective_constraints=["read_only", "audit_required"]
            )
        )
        _, access = await _check(checker)

        assert sorted(access.advisory_constraints) == [
            "audit_required",
            "read_only",
        ], (
            "the checker imposed labels and the grant does not carry them; a "
            "consumer or auditor cannot see what was imposed"
        )
        assert sorted(access.to_dict()["advisory_constraints"]) == [
            "audit_required",
            "read_only",
        ], "advisory_constraints must survive serialization, not just the object"

    @pytest.mark.asyncio
    async def test_advisory_labels_are_announced_once_not_per_call(
        self, caplog
    ) -> None:
        """A grant on an unenforceable-here control must not be silent.

        Once per DISTINCT label set, not per call: `_check_user_access` runs
        per user PER AGENT, so a per-call WARN floods a discovery hot path.
        """
        import kaizen_agents.patterns.discovery as _disc

        _disc._ADVISORY_LABELS_WARNED.clear()
        checker = _RealTrustOperationsShaped(
            VerificationResult(valid=True, effective_constraints=["read_only"])
        )
        with caplog.at_level("WARNING"):
            await _check(checker)
            await _check(checker)
            await _check(checker)

        warns = [
            r
            for r in caplog.records
            if r.message == "discovery.advisory_constraints_not_enforced_here"
        ]
        assert len(warns) == 1, (
            f"expected exactly ONE advisory WARN across three calls, got "
            f"{len(warns)} — a per-call warning on a discovery hot path is "
            "log spam, and spam gets filtered, which makes the loud signal silent"
        )
        assert warns[0].labels == ["read_only"]

    @pytest.mark.asyncio
    async def test_a_new_label_set_still_announces_itself(self) -> None:
        """CONTROL for the once-only guard: it must not mask a NEW label set."""
        import kaizen_agents.patterns.discovery as _disc

        _disc._ADVISORY_LABELS_WARNED.clear()
        seen = []
        for labels in (["read_only"], ["audit_required"], ["read_only"]):
            _, _, _ = normalize_access_constraints(labels)
            seen.append(len(_disc._ADVISORY_LABELS_WARNED))
        assert seen == [1, 2, 2], (
            "a NEW label combination must announce itself; only a REPEAT is "
            f"suppressed. Recorded-set sizes were {seen}"
        )

    @pytest.mark.asyncio
    async def test_denial_payload_still_carries_no_unlimited_axis(self) -> None:
        """A genuine DENIAL must still be a denial on EVERY axis.

        The denial path is now reached by a payload that is genuinely
        UNREADABLE (an unrecognized key), not by an advisory label list.
        """
        checker = _DuckTyped(valid=True, constraints={"max_requests_per_hour": 5})
        granted, access = await _check(checker)

        assert granted is False
        unlimited = [
            name
            for name, value in access.constraints.to_dict().items()
            if value is None
        ]
        assert unlimited == [], (
            f"denial payload is UNLIMITED on {unlimited}: None serializes as "
            "null and this type reads null as 'no cap', so a consumer "
            "enforcing those axes reads the denial as unrestricted"
        )
        assert access.permission_level == DENIED_PERMISSION_LEVEL

    @pytest.mark.asyncio
    async def test_unconstrained_verification_still_grants(self) -> None:
        """CONTROL. A fix that denied everything would pass the teeth above.

        The real type defaults `effective_constraints` to `[]`, which is the
        overwhelmingly common valid verification. Denying on an EMPTY payload
        would take the documented checker from 'grants everything' to 'denies
        everything' — the opposite failure, equally wrong.
        """
        checker = _RealTrustOperationsShaped(VerificationResult(valid=True))
        granted, access = await _check(checker)

        assert granted is True, (
            "an unconstrained valid verification was denied; the fail-closed "
            "branch is firing on ABSENT constraints, not unreadable ones"
        )
        assert access.denied is False
        assert access.permission_level == "execute"
        assert access.constraints.max_daily_invocations is None

    @pytest.mark.asyncio
    async def test_invalid_verification_denies(self) -> None:
        """CONTROL. The pre-existing deny path is untouched."""
        checker = _RealTrustOperationsShaped(
            VerificationResult(valid=False, reason="revoked")
        )
        granted, access = await _check(checker)
        assert granted is False
        assert access.denied is True


class TestMappingShapedConstraintsAreRead:
    """`isinstance(raw, dict)` also dropped every non-dict Mapping."""

    @pytest.mark.asyncio
    async def test_mapping_proxy_caps_are_applied(self) -> None:
        checker = _DuckTyped(
            valid=True, constraints=MappingProxyType({"max_tokens": 42})
        )
        granted, access = await _check(checker)

        assert granted is True
        assert access.constraints.max_tokens_per_session == 42, (
            "a MappingProxyType carrying a real cap was dropped — "
            "isinstance(raw, dict) is False for every Mapping that is not "
            "literally a dict, and the user was granted unlimited tokens"
        )

    @pytest.mark.asyncio
    async def test_all_seven_fields_are_mapped(self) -> None:
        """Pre-fix only 2 of 7 were read; the other 5 granted unlimited."""
        payload = {
            "max_daily_invocations": 10,
            "max_tokens_per_session": 2048,
            "max_cost_per_session_usd": 1.5,
            "allowed_tools": ["search"],
            "blocked_tools": ["shell"],
            "time_window_start": "09:00:00",
            "time_window_end": "17:00:00",
        }
        granted, access = await _check(_DuckTyped(valid=True, constraints=payload))

        assert granted is True
        assert access.constraints.to_dict() == payload, (
            "a checker capped an axis and the grant does not carry it; every "
            "unmapped field is None, i.e. UNLIMITED on that axis"
        )

    @pytest.mark.asyncio
    async def test_max_tokens_alias_is_preserved(self) -> None:
        """CONTROL. `max_tokens` is what wired consumers actually emit."""
        granted, access = await _check(
            _DuckTyped(valid=True, constraints={"max_tokens": 7})
        )
        assert granted is True
        assert access.constraints.max_tokens_per_session == 7


class TestUnreadablePayloadsFailClosed:
    """`valid is True` + a payload we cannot read is never a blank grant."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({"max_requests_per_hour": 5}, id="unrecognized-key"),
            pytest.param({"max_tokens": "lots"}, id="unusable-value-type"),
            pytest.param({"max_tokens": True}, id="bool-is-not-a-cap"),
            pytest.param({"max_daily_invocations": -1}, id="negative-cap"),
            pytest.param({"max_cost_per_session_usd": float("nan")}, id="nan-cost"),
            pytest.param({"max_cost_per_session_usd": float("inf")}, id="inf-cost"),
            pytest.param({"allowed_tools": "search"}, id="bare-str-tool-list"),
            pytest.param({"time_window_start": "not-a-time"}, id="unparseable-time"),
            pytest.param(
                {"max_tokens": 1, "max_tokens_per_session": 2}, id="alias-conflict"
            ),
            pytest.param("unlimited", id="bare-string-payload"),
            pytest.param(42, id="scalar-payload"),
            # NOTE: a list/set of STRING labels is deliberately NOT here — it
            # GRANTS (advisory, see TestDocumentedCheckerAdvisoryLabels...).
            # A label list carrying NON-string elements is still unreadable:
            pytest.param([{"max_tokens": 42}], id="label-list-of-dicts"),
            pytest.param([None], id="label-list-of-none"),
            pytest.param(["read_only", 42], id="label-list-mixed-types"),
        ],
    )
    async def test_unreadable_payload_denies(self, payload) -> None:
        granted, access = await _check(_DuckTyped(valid=True, constraints=payload))

        assert granted is False, (
            f"payload {payload!r} could not be represented as caps and access "
            "was granted anyway — with AccessConstraints() the grant is "
            "UNLIMITED on every axis the checker just tried to cap"
        )
        assert access.denied is True

    @pytest.mark.asyncio
    async def test_failure_is_loud(self, caplog) -> None:
        """A total-denial mode that logs nothing is indistinguishable from a
        checker outage; the ERROR line is the only triage signal."""
        with caplog.at_level("ERROR"):
            await _check(_DuckTyped(valid=True, constraints={"nope": 1}))

        assert any(
            record.message == "discovery.constraints_unrepresentable_failed_closed"
            for record in caplog.records
        ), "failed closed silently; no ERROR names the unreadable payload"


class TestNormalizerUnit:
    """Direct tests of the normalizer, independent of the discovery wiring."""

    def test_absent_payload_is_unrestricted_not_unreadable(self) -> None:
        for absent in (None, {}, [], set(), ""):
            constraints, advisory, reason = normalize_access_constraints(absent)
            assert reason is None, f"{absent!r} read as unreadable, not absent"
            assert constraints == AccessConstraints()
            assert advisory == []

    def test_label_sequence_returns_the_labels_and_no_reason(self) -> None:
        """INVERTED. This previously asserted the labels produced a DENY reason.

        That assertion pinned the over-correction: it locked in a denial for
        the one payload shape the documented checker actually emits. The labels
        must now come back as ADVISORY, with default (uncapped) constraints and
        no failure reason.
        """
        constraints, advisory, reason = normalize_access_constraints(
            ["read_only", "audit_required"]
        )
        assert reason is None, (
            "the SDK's own documented label list was reported unreadable; "
            "this is the shape TrustOperations.verify emits routinely"
        )
        assert constraints == AccessConstraints()
        assert sorted(advisory) == ["audit_required", "read_only"], (
            "labels must be returned verbatim — they are the only record of "
            "what the checker imposed"
        )

    def test_labels_are_copied_verbatim_with_no_invented_grammar(self) -> None:
        """No label is PARSED into a cap. Inventing a grammar stays BLOCKED."""
        constraints, advisory, reason = normalize_access_constraints(
            ["max_tokens=42", "max_tokens_99", "read_only"]
        )
        assert reason is None
        assert sorted(advisory) == ["max_tokens=42", "max_tokens_99", "read_only"]
        assert constraints.max_tokens_per_session is None, (
            "a label that LOOKS like a cap was parsed into one; the producing "
            "type emits no key=value grammar and inventing one means every "
            "label that fails the invented parse falls back to UNLIMITED"
        )

    def test_none_valued_key_is_skipped_not_rejected(self) -> None:
        """An explicit null cap means 'no limit on this axis', not garbage."""
        constraints, _advisory, reason = normalize_access_constraints(
            {"max_tokens": None, "max_daily_invocations": 3}
        )
        assert reason is None
        assert constraints.max_tokens_per_session is None
        assert constraints.max_daily_invocations == 3

    def test_matching_alias_values_do_not_conflict(self) -> None:
        """CONTROL. Only DIFFERING values are ambiguous."""
        constraints, _advisory, reason = normalize_access_constraints(
            {"max_tokens": 5, "max_tokens_per_session": 5}
        )
        assert reason is None
        assert constraints.max_tokens_per_session == 5

    def test_int_cost_is_accepted_as_float(self) -> None:
        """CONTROL. `max_cost_per_session_usd: 2` is a legitimate spend cap."""
        constraints, _advisory, reason = normalize_access_constraints(
            {"max_cost_per_session_usd": 2}
        )
        assert reason is None
        assert constraints.max_cost_per_session_usd == 2.0

    def test_mapping_payload_carries_no_advisory_labels(self) -> None:
        """CONTROL. A cap mapping is not a label list; advisory stays empty."""
        _constraints, advisory, reason = normalize_access_constraints({"max_tokens": 5})
        assert reason is None
        assert advisory == []


class TestDenyIsDeniedOnEveryAxis:
    """Finding 4: three fields stayed None, and None means UNRESTRICTED."""

    def test_no_field_is_left_unlimited(self) -> None:
        denied = AccessConstraints.deny().to_dict()
        unlimited = [name for name, value in denied.items() if value is None]
        assert unlimited == [], (
            f"AccessConstraints.deny() is UNLIMITED on {unlimited} — a "
            "consumer enforcing a blocklist or a schedule reads null as "
            "'no restriction', so the denial is permissive on those axes"
        )

    def test_blocklist_blocks_and_window_is_zero_width(self) -> None:
        denied = AccessConstraints.deny()
        assert denied.blocked_tools == ["*"]
        assert (
            denied.time_window_start == denied.time_window_end
        ), "a denial's time window must admit no instant"

    def test_zeroed_caps_are_falsy_and_that_is_the_documented_hazard(self) -> None:
        """Pins the hazard the class docstring warns consumers about.

        This is not an endorsement of the encoding — it asserts that the
        trap the docstring describes is REAL, so the warning cannot silently
        become stale prose about a problem that no longer exists.
        """
        denied = AccessConstraints.deny()
        assert not denied.max_daily_invocations
        assert not denied.max_tokens_per_session
        assert not denied.max_cost_per_session_usd
        assert not denied.allowed_tools
        assert denied.max_daily_invocations is not None, (
            "a consumer MUST be able to discriminate the denial from an "
            "absent cap via `is None`"
        )
        assert math.isfinite(denied.max_cost_per_session_usd)
