# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests: _validate_limits helper for issue #912 typed time-limit kwargs.

Issue #912 — per-task soft/hard time limits. Shard 1 lands the
validation helper that every runtime entry point calls before accepting
``soft_time_limit`` / ``time_limit`` kwargs. Shard 2 will wire actual
deadline enforcement; this shard's helper guards the kwarg surface so
caller errors (``time_limit=-1``) raise loudly at the entry point
rather than silently or at the timer thread.

Validation contract:
  * ``None`` for either kwarg is permitted (no limit).
  * Positive floats / ints are permitted.
  * Zero or negative values raise ``ValueError`` with an actionable message.
  * When BOTH kwargs are set, ``soft_time_limit`` MUST be strictly less
    than ``time_limit`` — celery convention. Equal or inverted values
    raise ``ValueError``.
"""

import pytest

from kailash.runtime._time_limits import _validate_limits


@pytest.mark.unit
def test_validate_limits_both_none_is_silent():
    """Default state — no limits configured — does not raise."""
    _validate_limits(soft_time_limit=None, time_limit=None)


@pytest.mark.unit
def test_validate_limits_only_soft_positive_is_silent():
    """Single positive soft limit, no hard limit — accepted."""
    _validate_limits(soft_time_limit=2.0, time_limit=None)


@pytest.mark.unit
def test_validate_limits_only_hard_positive_is_silent():
    """Single positive hard limit, no soft limit — accepted."""
    _validate_limits(soft_time_limit=None, time_limit=5.0)


@pytest.mark.unit
def test_validate_limits_both_positive_with_soft_lt_hard_is_silent():
    """Both set, soft strictly less than hard — accepted."""
    _validate_limits(soft_time_limit=2.0, time_limit=5.0)


@pytest.mark.unit
def test_validate_limits_integer_values_accepted():
    """Integer kwargs are accepted (callers MAY pass ``int`` or ``float``)."""
    _validate_limits(soft_time_limit=2, time_limit=5)


@pytest.mark.unit
@pytest.mark.parametrize("soft", [-1, -0.001, 0, 0.0])
def test_validate_limits_rejects_non_positive_soft(soft):
    """Soft limit ``<= 0`` raises ValueError."""
    with pytest.raises(ValueError):
        _validate_limits(soft_time_limit=soft, time_limit=None)


@pytest.mark.unit
@pytest.mark.parametrize("hard", [-1, -0.001, 0, 0.0])
def test_validate_limits_rejects_non_positive_hard(hard):
    """Hard limit ``<= 0`` raises ValueError."""
    with pytest.raises(ValueError):
        _validate_limits(soft_time_limit=None, time_limit=hard)


@pytest.mark.unit
def test_validate_limits_rejects_soft_equal_to_hard():
    """``soft_time_limit == time_limit`` is invalid (no warning window before kill)."""
    with pytest.raises(ValueError):
        _validate_limits(soft_time_limit=5.0, time_limit=5.0)


@pytest.mark.unit
def test_validate_limits_rejects_soft_greater_than_hard():
    """``soft_time_limit > time_limit`` is invalid (soft would never fire)."""
    with pytest.raises(ValueError):
        _validate_limits(soft_time_limit=10.0, time_limit=5.0)


@pytest.mark.unit
def test_validate_limits_error_message_mentions_parameters():
    """Error message MUST name the offending parameter for actionable feedback."""
    with pytest.raises(ValueError, match="soft_time_limit|time_limit"):
        _validate_limits(soft_time_limit=-1, time_limit=None)
