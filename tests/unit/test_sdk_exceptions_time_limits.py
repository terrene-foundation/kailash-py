# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests: SoftTimeLimitExceeded / HardTimeLimitExceeded exception types (#912).

Issue #912 — per-task soft/hard time limits. Shard 1 lands the typed
exception classes that downstream shards (Shard 2 wrapper, Shard 3
scheduler, Shard 4 distributed) raise on deadline expiry.

Invariants asserted here:
  1. Both classes subclass ``RuntimeException`` (the canonical runtime
     execution failure parent), NOT ``ResourceLimitExceededError``
     (which would imply a pool/quota exhaustion semantic — wrong domain).
  2. Both names are exported via ``kailash.sdk_exceptions.__all__`` so
     ``from kailash.sdk_exceptions import *`` and Sphinx autodoc surface
     them as part of the documented public API.
  3. ``__cause__`` chaining is preserved when the timing wrapper raises
     these from a lower-level ``WorkflowCancelledError`` — operators
     reading the traceback see the original cancellation cause.
"""

import pytest

from kailash.sdk_exceptions import (
    HardTimeLimitExceeded,
    ResourceLimitExceededError,
    RuntimeException,
    SoftTimeLimitExceeded,
)


@pytest.mark.unit
def test_soft_time_limit_exceeded_subclasses_runtime_exception():
    """SoftTimeLimitExceeded MUST inherit from RuntimeException."""
    assert issubclass(SoftTimeLimitExceeded, RuntimeException)


@pytest.mark.unit
def test_hard_time_limit_exceeded_subclasses_runtime_exception():
    """HardTimeLimitExceeded MUST inherit from RuntimeException."""
    assert issubclass(HardTimeLimitExceeded, RuntimeException)


@pytest.mark.unit
def test_soft_time_limit_exceeded_is_not_resource_limit_error():
    """SoftTimeLimitExceeded is a sibling of ResourceLimitExceededError, not a subclass.

    Time-limit exhaustion is a different domain than resource-pool
    exhaustion. Conflating them via subclass would let
    ``except ResourceLimitExceededError`` catch time-limit cases and
    apply the wrong remediation (scale the pool, not extend the budget).
    """
    assert not issubclass(SoftTimeLimitExceeded, ResourceLimitExceededError)


@pytest.mark.unit
def test_hard_time_limit_exceeded_is_not_resource_limit_error():
    """HardTimeLimitExceeded is a sibling of ResourceLimitExceededError, not a subclass."""
    assert not issubclass(HardTimeLimitExceeded, ResourceLimitExceededError)


@pytest.mark.unit
def test_soft_time_limit_exceeded_preserves_cause_chain():
    """Raising SoftTimeLimitExceeded ``from`` an inner exception preserves __cause__."""
    inner = TimeoutError("workflow exceeded soft deadline")
    try:
        try:
            raise inner
        except TimeoutError as exc:
            raise SoftTimeLimitExceeded("soft limit reached") from exc
    except SoftTimeLimitExceeded as captured:
        assert captured.__cause__ is inner


@pytest.mark.unit
def test_hard_time_limit_exceeded_preserves_cause_chain():
    """Raising HardTimeLimitExceeded ``from`` an inner exception preserves __cause__."""
    inner = TimeoutError("workflow exceeded hard deadline")
    try:
        try:
            raise inner
        except TimeoutError as exc:
            raise HardTimeLimitExceeded("hard limit reached") from exc
    except HardTimeLimitExceeded as captured:
        assert captured.__cause__ is inner


@pytest.mark.unit
def test_soft_time_limit_exceeded_in_all():
    """SoftTimeLimitExceeded MUST be in kailash.sdk_exceptions.__all__."""
    import kailash.sdk_exceptions as mod

    assert hasattr(mod, "__all__"), (
        "kailash.sdk_exceptions MUST define __all__ to declare the public "
        "exception API surface (per orphan-detection.md Rule 6)"
    )
    assert "SoftTimeLimitExceeded" in mod.__all__


@pytest.mark.unit
def test_hard_time_limit_exceeded_in_all():
    """HardTimeLimitExceeded MUST be in kailash.sdk_exceptions.__all__."""
    import kailash.sdk_exceptions as mod

    assert hasattr(mod, "__all__"), (
        "kailash.sdk_exceptions MUST define __all__ to declare the public "
        "exception API surface (per orphan-detection.md Rule 6)"
    )
    assert "HardTimeLimitExceeded" in mod.__all__
