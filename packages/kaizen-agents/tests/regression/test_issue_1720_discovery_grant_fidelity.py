# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Three residual findings on `UserFilteredAgentDiscovery`'s GRANT path.

The sibling suites pin the DENIAL shapes. This one pins what happens when the
checker says YES — the direction where a defect widens access rather than
removing it, and where a fix that "hardens" without reading the field's own
contract removes availability for nothing.

**F3 — the advisory-label grant is not an over-grant (ADJUDICATION PIN).**
When the checker returns `valid=True` with `effective_constraints=["read_only"]`,
`_check_user_access` returns `permission_level="execute"` with default
(UNLIMITED) `AccessConstraints`. That reads as an over-grant. It is not, and
the tests below pin the two facts the refutation rests on so the verdict is
re-derived — not re-assumed — the day either fact moves:

1. The checker is asked `verify(action="execute")` and its answer surface is
   `VerificationResult.valid: bool`. That type declares NO permission-level
   field (`src/kailash/trust/chain.py:841-856`), so there is no narrower
   verdict for this payload to under-report; `"execute"` echoes the action the
   checker approved.
2. The label path returns EXACTLY the label-free valid grant plus the
   disclosure. Same `permission_level`, same `constraints`, with the labels
   carried verbatim in `advisory_constraints` — strictly more information,
   never wider.

Denying instead was tried and reverted, and the reason is on the field itself:
`DelegationRecord.constraint_subset` is documented at `chain.py:350-363` as
read by NO allow/deny gate, with the tightening enforced one layer down by
SIGNED derived capabilities that `verify()` re-derives. Denying there removed
every constraint-labelled agent from every user's list and added no safety.

**F5 — the advisory WARN was silent for every user after the first.** The memo
was keyed on the label tuple alone and the record carried no `user_id`, so one
line fired for the first affected user, named no subject, and nothing fired for
any distinct user after.

**F6 — a `Mapping` that disagrees with itself granted UNLIMITED.** `__len__() >
0` got past the presence check; `items()` yielding nothing skipped every
per-key validation; the untouched `AccessConstraints()` fell out of the bottom
— which on that type is the most permissive value it can hold.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Mapping, Sequence
from types import MappingProxyType
from typing import Any

import pytest

from kailash.trust.chain import VerificationResult
from kaizen_agents.patterns import discovery as _discovery
from kaizen_agents.patterns.discovery import (
    DENIED_PERMISSION_LEVEL,
    UserFilteredAgentDiscovery,
    normalize_access_constraints,
)
from kaizen_agents.patterns.registry import AgentRegistry

pytestmark = pytest.mark.regression

WARN_EVENT = "discovery.advisory_constraints_not_enforced_here"


class _Meta:
    """Minimal stand-in for AgentMetadata; only `agent_id` is read."""

    def __init__(self, agent_id: str = "agent-1") -> None:
        self.agent_id = agent_id


class _RealTrustOperationsShaped:
    """Mirrors `TrustOperations.verify` EXACTLY and returns the REAL type.

    Records the kwargs it was called with, because one of the refutation's two
    legs is a claim about the QUESTION this module asks.
    """

    def __init__(self, result: VerificationResult) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    async def verify(self, agent_id, action, resource=None, level=None, context=None):
        self.calls.append(
            {
                "agent_id": agent_id,
                "action": action,
                "resource": resource,
                "level": level,
                "context": context,
            }
        )
        return self._result


class _LyingMapping(Mapping):
    """A real `Mapping` whose `__len__` and `items()` disagree.

    Not exotic: any mapping caching a stale count, or wrapping a view that was
    filtered after the count was taken, has this shape. `items()` is the ABC
    mixin's, driven by `__iter__` + `__getitem__`, so the disagreement is
    produced the same way a genuine bug would produce it.
    """

    def __init__(self, pairs: dict[str, Any], declared_len: int) -> None:
        self._pairs = pairs
        self._declared_len = declared_len

    def __getitem__(self, key: str) -> Any:
        return self._pairs[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._pairs)

    def __len__(self) -> int:
        return self._declared_len


async def _check(checker, user_id: str = "user-1", agent_id: str = "agent-1"):
    discovery = UserFilteredAgentDiscovery(AgentRegistry(), permission_checker=checker)
    return await discovery._check_user_access(user_id, "org-1", _Meta(agent_id))


@pytest.fixture(autouse=True)
def _clear_advisory_warn_memo():
    """The memo is module-global and BOUNDED; leaking it across tests would
    make a warn-count assertion depend on test order."""
    _discovery._ADVISORY_LABELS_WARNED.clear()
    yield
    _discovery._ADVISORY_LABELS_WARNED.clear()


class TestF3TheRefutationsPremises:
    """The two facts the F3 verdict rests on, pinned against the REAL SDK.

    Both are DISCRIMINATING: each reads the live type / the live call, so a
    change in either returns the other answer instead of letting a stale
    adjudication stand.
    """

    def test_verification_result_declares_no_permission_level_field(self) -> None:
        """LEG 1. There is no narrower verdict being under-reported.

        If the SDK ever adds a level/permission field to its verification
        result, `permission_level="execute"` stops being a restatement of the
        checker's answer and becomes an independent claim — at which point the
        F3 adjudication MUST be re-derived rather than inherited.
        """
        names = {f.name for f in dataclasses.fields(VerificationResult)}

        assert "valid" in names, (
            "VerificationResult no longer exposes `valid`; the whole grant "
            "path reads a field that has moved"
        )
        level_like = {
            n
            for n in names
            if "permission" in n or n in {"permission_level", "access_level", "grant"}
        }
        assert level_like == set(), (
            f"VerificationResult now carries {sorted(level_like)} — the checker "
            "CAN express a permission level, so reporting a flat 'execute' may "
            "now under-report a narrower verdict. Re-adjudicate F3."
        )

    @pytest.mark.asyncio
    async def test_the_checker_is_asked_for_the_execute_action(self) -> None:
        """LEG 1, other half. `permission_level` echoes the APPROVED action."""
        checker = _RealTrustOperationsShaped(
            VerificationResult(valid=True, effective_constraints=["read_only"])
        )
        granted, access = await _check(checker)

        assert checker.calls, "the checker was never called"
        assert checker.calls[0]["action"] == "execute", (
            f"the module asked for {checker.calls[0]['action']!r} but reports "
            f"{access.permission_level!r}; the reported level is only a "
            "restatement of the verdict while the two agree"
        )
        assert granted is True
        assert access.permission_level == "execute"


class TestF3AdvisoryGrantIsNotWiderThanTheLabelFreeGrant:
    """LEG 2. The label path = the label-free grant PLUS a disclosure."""

    @pytest.mark.asyncio
    async def test_label_grant_differs_from_label_free_grant_only_by_disclosure(
        self,
    ) -> None:
        labelled = _RealTrustOperationsShaped(
            VerificationResult(
                valid=True, effective_constraints=["read_only", "audit_required"]
            )
        )
        unlabelled = _RealTrustOperationsShaped(VerificationResult(valid=True))

        labelled_granted, labelled_access = await _check(labelled)
        plain_granted, plain_access = await _check(unlabelled)

        assert labelled_granted is True and plain_granted is True

        labelled_dict = labelled_access.to_dict()
        plain_dict = plain_access.to_dict()

        assert labelled_dict.pop("advisory_constraints") == [
            "read_only",
            "audit_required",
        ], (
            "the labels were NOT carried out to the payload. The grant is only "
            "defensible because it DISCLOSES what the checker imposed; drop "
            "the disclosure and it becomes a silent unqualified execute-grant"
        )
        assert plain_dict.pop("advisory_constraints") == []
        assert labelled_dict == plain_dict, (
            "the advisory-label grant diverged from the label-free grant on "
            f"{sorted(k for k in labelled_dict if labelled_dict[k] != plain_dict[k])}. "
            "F3 was refuted on the grounds that the label path is never WIDER "
            "than the grant nobody disputes — if it now differs at all, that "
            "refutation no longer holds"
        )

    @pytest.mark.asyncio
    async def test_labels_are_carried_verbatim_and_not_parsed(self) -> None:
        """No invented grammar: a `key=value`-looking label stays a label."""
        checker = _RealTrustOperationsShaped(
            VerificationResult(valid=True, effective_constraints=["max_tokens=42"])
        )
        granted, access = await _check(checker)

        assert granted is True
        assert access.advisory_constraints == ["max_tokens=42"]
        assert access.constraints.max_tokens_per_session is None, (
            "a label was PARSED into a cap. The producing type emits no such "
            "grammar, so every label failing the invented parse would fall "
            "back to unlimited"
        )


class TestF3NoneConstraintsCannotReachTheGrant:
    """The one hole the reason-string guard did not cover.

    `_check_user_access` gated the grant on `unrepresentable is not None` and
    then passed `constraints` — declared `AccessConstraints | None` — into a
    parameter typed non-optional. Today the normalizer's documented failure
    shape `(None, [], reason)` makes the two conditions coincide. If they ever
    come apart, `None` reaches `AccessMetadata(constraints=)`, and consumers
    either crash reading `.max_daily_invocations` off it or read the absent
    object as "no caps" — UNLIMITED, F3's failure re-entering through the type
    system rather than the logic.
    """

    @pytest.mark.asyncio
    async def test_no_constraints_and_no_reason_denies(self, monkeypatch) -> None:
        """Injected because the real normalizer cannot produce this today.

        That is the point: the guard exists for the edit that makes it
        producible, so the test drives the shape directly rather than waiting
        for that edit to ship undefended.
        """
        monkeypatch.setattr(
            _discovery,
            "normalize_access_constraints",
            lambda raw, *, user_id=None: (None, [], None),
        )
        checker = _RealTrustOperationsShaped(
            VerificationResult(valid=True, effective_constraints=["read_only"])
        )

        granted, access = await _check(checker)

        assert granted is False, (
            "a None constraints payload with no reason reached the GRANT; "
            "None is not an AccessConstraints, and every consumer reading caps "
            "off it either crashes or reads UNLIMITED"
        )
        assert access.denied is True
        assert access.permission_level == DENIED_PERMISSION_LEVEL

    @pytest.mark.asyncio
    async def test_that_denial_is_still_diagnosable(self, monkeypatch, caplog) -> None:
        """A denial whose log line said only `None` is indistinguishable from
        a checker denial — and this branch means the normalizer broke its own
        contract, the most important thing the line could say."""
        monkeypatch.setattr(
            _discovery,
            "normalize_access_constraints",
            lambda raw, *, user_id=None: (None, [], None),
        )

        with caplog.at_level("ERROR", logger=_discovery.logger.name):
            await _check(
                _RealTrustOperationsShaped(
                    VerificationResult(valid=True, effective_constraints=["read_only"])
                )
            )

        failed_closed = [
            r
            for r in caplog.records
            if r.getMessage() == "discovery.constraints_unrepresentable_failed_closed"
        ]
        assert failed_closed, "the fail-closed denial was silent"
        assert "no reason" in getattr(failed_closed[0], "reason", "")


class TestF5AdvisoryWarnNamesItsSubjectAndFiresPerUser:
    """The warn announced the first affected user and nobody after."""

    @pytest.mark.asyncio
    async def test_a_second_distinct_user_with_the_same_labels_still_warns(
        self, caplog
    ) -> None:
        result = VerificationResult(valid=True, effective_constraints=["read_only"])

        with caplog.at_level("WARNING", logger=_discovery.logger.name):
            await _check(_RealTrustOperationsShaped(result), user_id="user-1")
            await _check(_RealTrustOperationsShaped(result), user_id="user-2")

        warned = [r for r in caplog.records if r.getMessage() == WARN_EVENT]
        subjects = [getattr(r, "user_id", None) for r in warned]

        assert subjects == ["user-1", "user-2"], (
            "the advisory warn was keyed on the label set ALONE, so it fired "
            f"for the first affected user and went silent after. Saw {subjects}"
        )

    @pytest.mark.asyncio
    async def test_the_same_user_across_many_agents_still_warns_once(
        self, caplog
    ) -> None:
        """CONTROL. The anti-flood property the memo exists for is preserved.

        A fix that simply removed the memo would pass the test above and emit
        O(users x agents) identical lines on a discovery hot path — a loud
        signal that gets filtered is a silent one.
        """
        result = VerificationResult(valid=True, effective_constraints=["read_only"])
        checker = _RealTrustOperationsShaped(result)

        with caplog.at_level("WARNING", logger=_discovery.logger.name):
            for agent_id in ("agent-1", "agent-2", "agent-3", "agent-4"):
                await _check(checker, user_id="user-1", agent_id=agent_id)

        warned = [r for r in caplog.records if r.getMessage() == WARN_EVENT]
        assert len(warned) == 1, (
            f"{len(warned)} advisory warns for ONE user across 4 agents; the "
            "per-agent de-duplication that motivated the memo is gone"
        )

    @pytest.mark.asyncio
    async def test_a_new_label_set_for_a_known_user_still_warns(self, caplog) -> None:
        """CONTROL. The label half of the key is still live."""
        with caplog.at_level("WARNING", logger=_discovery.logger.name):
            await _check(
                _RealTrustOperationsShaped(
                    VerificationResult(valid=True, effective_constraints=["read_only"])
                ),
                user_id="user-1",
            )
            await _check(
                _RealTrustOperationsShaped(
                    VerificationResult(
                        valid=True, effective_constraints=["audit_required"]
                    )
                ),
                user_id="user-1",
            )

        warned = [r for r in caplog.records if r.getMessage() == WARN_EVENT]
        assert len(warned) == 2, (
            "a NEW label combination for a known user was masked by the first "
            "set ever seen for that user"
        )


class TestF5MemoSaturationDoesNotReinstateTheFlood:
    """Adding the user dimension made the cap REACHABLE, and reaching it used
    to re-open the flood the memo exists to prevent.

    Key cardinality moved from |label sets| to |users| x |label sets|. The old
    form stopped RECORDING at the cap and warned unconditionally afterwards,
    so a saturated deployment warned on EVERY call — and `_check_user_access`
    runs per user PER AGENT, so one sweep emitted one WARN per registered
    agent, each running `scrub_credentials()` per label. `len(...) < CAP`
    gated the recording and never the emitting.
    """

    def _saturate(self) -> None:
        for i in range(_discovery._ADVISORY_LABELS_WARNED_CAP):
            _discovery._ADVISORY_LABELS_WARNED[(f"filler-{i}", ("x",))] = None

    def test_repeat_calls_after_saturation_do_not_warn_every_time(self, caplog) -> None:
        self._saturate()

        with caplog.at_level("WARNING", logger=_discovery.logger.name):
            for _ in range(5):
                normalize_access_constraints(["read_only"], user_id="new-user")

        warned = [r for r in caplog.records if r.getMessage() == WARN_EVENT]
        assert len(warned) == 1, (
            f"{len(warned)} WARN lines for 5 identical calls once the memo "
            "saturated; the cap gated recording but not emitting, so every "
            "un-memoized user warned on every call"
        )

    def test_a_full_agent_sweep_after_saturation_still_warns_once(self, caplog) -> None:
        """The O(agents) factor is the flood, and it must stay collapsed even
        when the memo is full."""
        self._saturate()

        with caplog.at_level("WARNING", logger=_discovery.logger.name):
            for _ in range(20):
                normalize_access_constraints(["read_only"], user_id="sweeper")

        warned = [r for r in caplog.records if r.getMessage() == WARN_EVENT]
        assert len(warned) == 1, (
            f"one user across 20 agents emitted {len(warned)} WARN lines "
            "post-saturation"
        )

    def test_the_memo_stays_hard_bounded(self) -> None:
        """Eviction, not unbounded growth — the memory bound is the reason the
        cap existed in the first place."""
        for i in range(_discovery._ADVISORY_LABELS_WARNED_CAP * 3):
            normalize_access_constraints(["read_only"], user_id=f"user-{i}")

        assert (
            len(_discovery._ADVISORY_LABELS_WARNED)
            <= _discovery._ADVISORY_LABELS_WARNED_CAP
        )


class TestF6AMappingThatDisagreesWithItselfFailsClosed:
    """`len() > 0` + `items()` yielding nothing granted UNLIMITED."""

    def test_zero_yield_mapping_is_unreadable_not_unconstrained(self) -> None:
        constraints, labels, reason = normalize_access_constraints(
            _LyingMapping({}, declared_len=3)
        )

        assert constraints is None, (
            "a mapping claiming 3 entries and yielding none returned "
            f"{constraints!r} — a default AccessConstraints() is UNLIMITED on "
            "all seven axes, so the lying mapping bought the most permissive "
            "value the type can hold while skipping every per-key check"
        )
        assert labels == []
        assert reason is not None and "disagree" in reason

    def test_non_idempotent_len_cannot_walk_through_the_guard(self) -> None:
        """The defeat the COUNT-based guard could not see.

        An earlier fix compared `len(raw)` against a count taken while
        iterating — but that `len()` is a SECOND, INDEPENDENT read; the FIRST
        happens in `_constraint_payload_present` and is what decided this
        branch was entered at all. A `Mapping` whose `__len__` is not
        idempotent answered 1 to the presence check and 0 to the guard, so the
        guard compared 0 against 0, agreed with itself, and fell through to
        the untouched UNLIMITED `AccessConstraints()` — defeated by the same
        CLASS of object it was written to stop, lying on a different axis.

        Materializing once removes the axis rather than measuring it: after
        `list(raw.items())` there is no live object left to disagree with.
        """

        class _NonIdempotentLen(Mapping):
            def __init__(self) -> None:
                self._reads = 0

            def __len__(self) -> int:
                self._reads += 1
                return 1 if self._reads == 1 else 0

            def __iter__(self) -> Iterator[str]:
                return iter(())

            def __getitem__(self, key: str) -> Any:
                raise KeyError(key)

        constraints, _labels, reason = normalize_access_constraints(_NonIdempotentLen())

        assert constraints is None, (
            f"a Mapping lying on a DIFFERENT axis returned {constraints!r} — "
            "every field None, which this type encodes as UNLIMITED"
        )
        assert reason is not None and "disagree" in reason

    def test_one_shot_iteration_does_not_lose_the_labels(self) -> None:
        """The sequence branch walked `raw` THREE times.

        `all(...)`, the `offenders` comprehension, and the label comprehension
        were three separate walks, so a one-shot `__iter__` was exhausted by
        the first: the element check ran over the real elements and the labels
        were built from an EMPTY second walk — an UNLIMITED grant carrying no
        disclosure of what the checker imposed.
        """

        class _OneShotIter(Sequence):
            def __init__(self, items: list[str]) -> None:
                self._items = items
                self._walked = False

            def __getitem__(self, index):  # pragma: no cover - never reached
                raise IndexError(index)

            def __len__(self) -> int:
                return 0 if self._walked else len(self._items)

            def __iter__(self) -> Iterator[str]:
                if self._walked:
                    return iter(())
                self._walked = True
                return iter(self._items)

        constraints, labels, reason = normalize_access_constraints(
            _OneShotIter(["read_only"])
        )

        assert reason is None
        assert labels == ["read_only"], (
            f"the labels were lost to a second walk (got {labels!r}); an "
            "empty label list here grants UNLIMITED and discloses nothing"
        )
        assert constraints is not None

    def test_over_yielding_mapping_applies_every_yielded_cap(self) -> None:
        """A mapping yielding MORE than it declares is NOT a denial case.

        The previous count-based guard denied this. That was over-strict:
        every materialized pair goes through the full seven-field validation,
        so applying all of them is strictly MORE restrictive than dropping
        any. There is no unlimited-grant route here, and denying removed
        availability without adding safety.
        """
        constraints, _labels, reason = normalize_access_constraints(
            _LyingMapping(
                {"max_tokens": 42, "max_daily_invocations": 7}, declared_len=1
            )
        )

        assert reason is None
        assert constraints is not None
        assert constraints.max_tokens_per_session == 42
        assert constraints.max_daily_invocations == 7

    @pytest.mark.asyncio
    async def test_the_lying_mapping_denies_end_to_end(self) -> None:
        """THE TEETH. Through the real `_check_user_access`, not the helper."""

        class _DuckTyped:
            async def verify(self, agent_id, action, user_id, organization_id):
                return type(
                    "R",
                    (),
                    {"valid": True, "constraints": _LyingMapping({}, declared_len=2)},
                )()

        granted, access = await _check(_DuckTyped())

        assert granted is False
        assert access.denied is True
        assert access.permission_level == DENIED_PERMISSION_LEVEL
        unlimited = [n for n, v in access.constraints.to_dict().items() if v is None]
        assert unlimited == [], (
            f"the denial payload is UNLIMITED on {unlimited}; null is this "
            "type's encoding for 'no cap'"
        )

    @pytest.mark.asyncio
    async def test_honest_mappings_are_untouched(self) -> None:
        """CONTROL — the availability half.

        Every real mapping has `len()` == its item count by construction, so
        the counting guard must be invisible to `dict`, `MappingProxyType`,
        and a well-behaved custom Mapping alike. A guard that denied any of
        these would remove availability without adding safety.
        """
        for payload in (
            {"max_tokens": 42},
            MappingProxyType({"max_tokens": 42}),
            _LyingMapping({"max_tokens": 42}, declared_len=1),  # honest: 1 == 1
        ):
            constraints, labels, reason = normalize_access_constraints(payload)
            assert reason is None, f"{type(payload).__name__} was denied: {reason}"
            assert labels == []
            assert constraints is not None
            assert constraints.max_tokens_per_session == 42

    def test_the_label_sequence_branch_has_the_same_floor(self) -> None:
        """ENFORCEMENT-SURFACE PARITY. The sibling payload shape, same defect.

        A sequence whose `__len__` is non-zero but which iterates empty passes
        the per-element check VACUOUSLY (`all(...)` over nothing is True) and
        reaches the label grant with `labels == []` — default
        `AccessConstraints()`, i.e. UNLIMITED, and this time with no disclosure
        either. Closing only the mapping branch would leave a fail-closed
        control that one of the two payload shapes never learned.
        """

        class _LyingSequence(Sequence):
            def __getitem__(self, index):  # pragma: no cover - never reached
                raise IndexError(index)

            def __len__(self) -> int:
                return 2

        constraints, labels, reason = normalize_access_constraints(_LyingSequence())

        assert constraints is None, (
            "a sequence claiming 2 labels and yielding none granted "
            f"{constraints!r} with labels {labels!r} — UNLIMITED on all seven "
            "axes AND with nothing disclosed"
        )
        assert reason is not None and "disagree" in reason

    def test_honest_label_sequences_are_untouched(self) -> None:
        """CONTROL — the availability half of the parity fix."""
        for payload in (["read_only"], ("read_only", "audit_required")):
            constraints, labels, reason = normalize_access_constraints(payload)
            assert reason is None, f"{payload!r} was denied: {reason}"
            assert labels == list(payload)
            assert constraints is not None

    def test_an_explicit_none_value_is_still_a_read_entry(self) -> None:
        """A `None` cap `continue`s the loop; it must not read as unyielded."""
        constraints, _labels, reason = normalize_access_constraints(
            {"max_tokens": None, "max_daily_invocations": 7}
        )

        assert reason is None, (
            "an explicitly-None cap was counted as an unyielded entry; the "
            "counter must advance before the None short-circuit"
        )
        assert constraints is not None
        assert constraints.max_tokens_per_session is None
        assert constraints.max_daily_invocations == 7
