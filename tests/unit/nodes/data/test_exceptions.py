"""Unit tests for kailash.nodes.data.exceptions (DPI-B1 / issue #697).

Tier 1 unit tests covering ``PoolExhaustedError`` construction, attribute
exposure, and message contents. The integration assertion that the error
fires from ``_get_adapter`` lives in
``tests/regression/test_issue_697_pool_leak.py`` (DPI-B5).
"""

from __future__ import annotations

import pytest

from kailash.nodes.data.exceptions import PoolExhaustedError
from kailash.sdk_exceptions import NodeExecutionError


def test_pool_exhausted_error_inherits_node_execution_error():
    """PoolExhaustedError is catchable as NodeExecutionError (parent class)."""
    err = PoolExhaustedError(current=100, cap=100, pool_key="abc|pg|h:5432|10|20")
    assert isinstance(err, NodeExecutionError)


def test_pool_exhausted_error_attributes_accessible():
    """current / cap / pool_key are exposed as attributes for log correlation."""
    err = PoolExhaustedError(current=42, cap=50, pool_key="loop|pg|h:p|10|20")
    assert err.current == 42
    assert err.cap == 50
    assert err.pool_key == "loop|pg|h:p|10|20"


def test_pool_exhausted_error_message_includes_count_cap_and_override_hint():
    """str(err) names current count, cap, and the override entry point."""
    err = PoolExhaustedError(current=100, cap=100, pool_key="k")
    msg = str(err)
    assert "100" in msg  # current AND cap surface in the message
    assert "set_pool_defaults" in msg
    assert "max_pool_count_per_process" in msg
    assert "k" in msg  # pool_key included for forensic correlation


def test_pool_exhausted_error_validates_current_non_negative_int():
    """Negative or non-int current raises ValueError at construction."""
    with pytest.raises(ValueError, match="current"):
        PoolExhaustedError(current=-1, cap=100, pool_key="k")
    with pytest.raises(ValueError, match="current"):
        PoolExhaustedError(current="100", cap=100, pool_key="k")  # type: ignore[arg-type]


def test_pool_exhausted_error_validates_cap_positive_int():
    """Zero / negative / non-int cap raises ValueError at construction."""
    with pytest.raises(ValueError, match="cap"):
        PoolExhaustedError(current=100, cap=0, pool_key="k")
    with pytest.raises(ValueError, match="cap"):
        PoolExhaustedError(current=100, cap=-5, pool_key="k")
    with pytest.raises(ValueError, match="cap"):
        PoolExhaustedError(current=100, cap="100", pool_key="k")  # type: ignore[arg-type]


def test_pool_exhausted_error_validates_pool_key_is_string():
    """Non-string pool_key raises ValueError."""
    with pytest.raises(ValueError, match="pool_key"):
        PoolExhaustedError(current=100, cap=100, pool_key=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="pool_key"):
        PoolExhaustedError(current=100, cap=100, pool_key=42)  # type: ignore[arg-type]


def test_pool_exhausted_error_chains_via_raise_from():
    """Underlying RuntimeError / TimeoutError surfaces via __cause__."""
    cause = TimeoutError("per-pool lock timed out after 5.0s")
    try:
        raise PoolExhaustedError(current=10, cap=10, pool_key="k") from cause
    except PoolExhaustedError as err:
        assert err.__cause__ is cause


def test_pool_exhausted_error_exported_in_all():
    """PoolExhaustedError appears in the module's __all__ public surface."""
    from kailash.nodes.data import exceptions

    assert "PoolExhaustedError" in exceptions.__all__
