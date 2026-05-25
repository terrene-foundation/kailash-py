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
