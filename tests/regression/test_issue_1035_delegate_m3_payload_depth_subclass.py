# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: M3 payload-depth-recursion bypass via custom Mapping/Sequence.

Closes the C6-1 DoS bypass identified in #1035 M3: the prior
``_check_payload_depth`` enumerated only concrete ``dict`` / ``list`` /
``tuple`` via ``isinstance``. A custom ``Mapping``-derived or
``Sequence``-derived container (``UserDict``, ``UserList``,
``collections.abc.Mapping`` subclasses) skipped the depth recursion
entirely. An attacker could craft a payload with a deeply-nested
custom container, bypass the C6-1 boundary, and trigger O(depth)
recursion in ``canonical_json_dumps`` downstream.

The fix switches the gate to ``collections.abc.Mapping`` and
``collections.abc.Sequence`` (excluding ``str``/``bytes``/``bytearray``).
These tests pin the closed bypass surface and guard against regression
to concrete-only ``isinstance`` checks.
"""

from __future__ import annotations

import collections
from collections.abc import Mapping
from typing import Any, Iterator

import pytest

from kailash.delegate.dispatch import (
    _MAX_PAYLOAD_DEPTH,
    DispatchValidationError,
    _check_payload_depth,
)

# ---------------------------------------------------------------------------
# Test fixtures — exotic container shapes the prior check missed
# ---------------------------------------------------------------------------


class DeepUserDict(collections.UserDict):
    """UserDict subclass — Mapping-derived but NOT a concrete dict."""


class DeepUserList(collections.UserList):
    """UserList subclass — Sequence-derived but NOT a concrete list."""


class ConcreteMapping(Mapping):
    """Hand-rolled Mapping that satisfies the ABC contract without
    inheriting from dict. Exercises the abstract-Mapping branch
    independent of UserDict's dict-backed ``data`` attribute.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)


def _nest(builder: Any, depth: int) -> Any:
    """Build a payload nested ``depth`` levels via the given factory.

    ``builder`` is a callable returning the container shape for each level
    (e.g. ``DeepUserDict``). The leaf is ``"leaf"``. Dispatches on the
    container's protocol surface: ``append`` for Sequence-like, ``_data``
    attribute for ConcreteMapping, ``__setitem__`` for Mapping-like.
    """
    payload: Any = "leaf"
    for _ in range(depth):
        wrapped = builder()
        if hasattr(wrapped, "append"):  # UserList / list-like Sequence
            wrapped.append(payload)
        elif hasattr(wrapped, "_data"):  # ConcreteMapping (private dict)
            wrapped._data["k"] = payload
        else:  # UserDict / dict-like Mapping
            wrapped["k"] = payload
        payload = wrapped
    return payload


# ---------------------------------------------------------------------------
# Regression tests — the bypass surfaces
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_user_dict_subclass_triggers_depth_check() -> None:
    """UserDict-derived payload exceeding the limit MUST be refused.

    Pre-fix: ``isinstance(obj, dict)`` returned False for UserDict,
    silently skipping the recursion; payload propagated to
    canonical_json_dumps with full attack depth.
    """
    payload = _nest(DeepUserDict, _MAX_PAYLOAD_DEPTH + 5)
    with pytest.raises(DispatchValidationError, match="maximum nesting depth"):
        _check_payload_depth(payload)


@pytest.mark.regression
def test_user_list_subclass_triggers_depth_check() -> None:
    """UserList-derived payload exceeding the limit MUST be refused."""
    payload = _nest(DeepUserList, _MAX_PAYLOAD_DEPTH + 5)
    with pytest.raises(DispatchValidationError, match="maximum nesting depth"):
        _check_payload_depth(payload)


@pytest.mark.regression
def test_abstract_mapping_subclass_triggers_depth_check() -> None:
    """ABC-derived Mapping (no dict inheritance) MUST be refused.

    Exercises the abstract-Mapping branch independent of UserDict's
    dict-backed ``data`` attribute — a pure ``Mapping`` subclass that
    implements ``__getitem__``/``__iter__``/``__len__`` without ever
    inheriting from dict.
    """
    payload = _nest(lambda: ConcreteMapping({}), _MAX_PAYLOAD_DEPTH + 5)
    with pytest.raises(DispatchValidationError, match="maximum nesting depth"):
        _check_payload_depth(payload)


# ---------------------------------------------------------------------------
# Control case — the original concrete-dict path MUST still raise
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_concrete_dict_still_triggers_depth_check() -> None:
    """Regression guard: switching to abstract Mapping/Sequence MUST NOT
    break the original concrete-dict path. A plain ``dict`` of the same
    shape MUST raise identically.
    """
    payload = _nest(dict, _MAX_PAYLOAD_DEPTH + 5)
    with pytest.raises(DispatchValidationError, match="maximum nesting depth"):
        _check_payload_depth(payload)


@pytest.mark.regression
def test_concrete_list_still_triggers_depth_check() -> None:
    """Regression guard: plain ``list`` of nested lists MUST still raise."""
    payload: Any = "leaf"
    for _ in range(_MAX_PAYLOAD_DEPTH + 5):
        payload = [payload]
    with pytest.raises(DispatchValidationError, match="maximum nesting depth"):
        _check_payload_depth(payload)


# ---------------------------------------------------------------------------
# Negative cases — within-limit payloads MUST pass for every container kind
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_within_limit_user_dict_passes() -> None:
    """Payloads below the limit MUST traverse without raising — proves
    the depth check counts UserDict levels (not just dict levels) and
    matches the budget exactly.
    """
    payload = _nest(DeepUserDict, _MAX_PAYLOAD_DEPTH - 1)
    _check_payload_depth(payload)  # MUST NOT raise


@pytest.mark.regression
def test_within_limit_abstract_mapping_passes() -> None:
    """Pure ABC-Mapping payload at depth-1 below limit MUST pass."""
    payload = _nest(lambda: ConcreteMapping({}), _MAX_PAYLOAD_DEPTH - 1)
    _check_payload_depth(payload)  # MUST NOT raise


@pytest.mark.regression
def test_str_is_not_walked_as_sequence() -> None:
    """A long string nested inside a dict MUST NOT trigger the depth
    check via the Sequence branch. Strings are Sequences but iterating
    them yields characters; treating each character as a nesting level
    would false-positive every payload carrying a long string.
    """
    payload = {"big": "x" * 10_000}
    _check_payload_depth(payload)  # MUST NOT raise


@pytest.mark.regression
def test_bytes_is_not_walked_as_sequence() -> None:
    """Bytes objects MUST be excluded from Sequence-branch recursion
    for the same reason as strings."""
    payload = {"big": b"x" * 10_000}
    _check_payload_depth(payload)  # MUST NOT raise


# ---------------------------------------------------------------------------
# Set-ABC bypass surface — R1 followup
#
# A frozenset / set / MappingView is a ``collections.abc.Set`` but NOT a
# ``Sequence``; the prior Mapping + Sequence gate skipped Set recursion
# entirely. An attacker could craft a payload of
# ``frozenset({frozenset({frozenset({...})})})`` (frozensets are hashable
# so they can nest), reach canonical_json_dumps with arbitrary depth, and
# reopen the C6-1 DoS class. These tests pin the extended Set-ABC branch.
# ---------------------------------------------------------------------------


def _nest_frozenset(depth: int) -> Any:
    """Build a payload nested ``depth`` frozensets deep.

    Each level wraps the prior payload in a single-element frozenset.
    Frozensets are hashable so frozenset-of-frozenset nesting is the
    canonical Set-ABC stress vector. The leaf is the literal string
    ``"leaf"`` (hashable).
    """
    payload: Any = "leaf"
    for _ in range(depth):
        payload = frozenset({payload})
    return payload


@pytest.mark.regression
def test_frozenset_of_sequences_triggers_depth_check() -> None:
    """Frozenset wrapping a deeply-nested tuple-chain MUST trigger the depth check.

    Pre-fix: ``isinstance(obj, Set)`` was not checked, so the frozenset
    layer was skipped entirely. The depth count then started from the
    inner Sequence and the payload silently passed the gate even though
    the full (frozenset + Sequence chain) exceeded the limit.

    Dicts cannot be frozenset elements (unhashable), so this test uses
    a nested tuple chain — tuples are hashable Sequences that the depth
    check walks via the Sequence branch. The test thus exercises the
    composition: Set branch (frozenset) → Sequence branch (tuple chain).
    """
    inner: Any = "leaf"
    for _ in range(_MAX_PAYLOAD_DEPTH + 5):
        inner = (inner,)
    payload = frozenset({inner})
    with pytest.raises(DispatchValidationError, match="maximum nesting depth"):
        _check_payload_depth(payload)


@pytest.mark.regression
def test_nested_frozensets_trigger_depth_check() -> None:
    """Frozenset-of-frozenset-of-... payload MUST be refused.

    Pure Set-ABC chain — no Mapping or Sequence anywhere in the structure.
    Pre-fix the recursion never entered any layer; depth gate never fired.
    """
    payload = _nest_frozenset(_MAX_PAYLOAD_DEPTH + 5)
    with pytest.raises(DispatchValidationError, match="maximum nesting depth"):
        _check_payload_depth(payload)


@pytest.mark.regression
def test_plain_set_iterables_walked() -> None:
    """``set`` (MutableSet) wrapping nested dicts MUST be walked.

    Plain ``set`` is ``collections.abc.MutableSet`` which is a subclass
    of ``collections.abc.Set``; the extended check MUST handle both
    immutable (frozenset) and mutable (set) variants identically. The
    set elements must be hashable, so we wrap a tuple instead of a dict
    at the leaf level (tuples are hashable; dicts are not).
    """
    inner: Any = "leaf"
    for _ in range(_MAX_PAYLOAD_DEPTH + 5):
        inner = (inner,)  # tuple = hashable Sequence, walked via Sequence branch
    payload = {inner}  # outer set wrapping a deeply-nested tuple
    with pytest.raises(DispatchValidationError, match="maximum nesting depth"):
        _check_payload_depth(payload)


@pytest.mark.regression
def test_within_limit_frozenset_passes() -> None:
    """Frozenset chain below the limit MUST pass — proves the extended
    Set-ABC branch counts levels (it doesn't false-positive every Set)."""
    payload = _nest_frozenset(_MAX_PAYLOAD_DEPTH - 1)
    _check_payload_depth(payload)  # MUST NOT raise


@pytest.mark.regression
def test_memoryview_is_not_walked_recursively() -> None:
    """``memoryview`` is a ``Sequence`` whose iteration yields ints.

    A memoryview over bytes is a Sequence per the ABC, but its elements
    are int (non-Container) so recursion immediately terminates at the
    first iteration step regardless of buffer length. This is the same
    structural property that protects the str/bytes/bytearray exclusion:
    the Sequence branch only deepens when an element is itself a
    Container the gate walks again. A 64-byte memoryview does NOT
    overflow the budget — confirms the gate's depth semantics correctly
    distinguish "container of containers" from "container of leaves".
    """
    payload = {"buf": memoryview(b"\x00" * 64)}
    _check_payload_depth(payload)  # MUST NOT raise
