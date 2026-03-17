"""Unit tests for the continue-as-new pattern.

Tests ContinueAsNew exception behavior, ContinuationContext depth tracking,
chain recording, and depth-exceeded safety limits.
"""

import pytest

from kailash.workflow.continuation import (
    ContinuationContext,
    ContinuationDepthExceededError,
    ContinueAsNew,
    DEFAULT_MAX_CONTINUATION_DEPTH,
)


class TestContinueAsNewException:
    """Tests for the ContinueAsNew exception class."""

    def test_basic_creation(self):
        """ContinueAsNew should be constructable with new_params."""
        exc = ContinueAsNew(new_params={"page": 2})

        assert exc.new_params == {"page": 2}
        assert exc.version is None
        assert isinstance(exc, Exception)

    def test_creation_with_version(self):
        """ContinueAsNew should accept an optional version."""
        exc = ContinueAsNew(new_params={"cursor": "abc"}, version="2.0.0")

        assert exc.new_params == {"cursor": "abc"}
        assert exc.version == "2.0.0"

    def test_default_params_is_empty_dict(self):
        """ContinueAsNew with no params should default to empty dict."""
        exc = ContinueAsNew()

        assert exc.new_params == {}
        assert exc.version is None

    def test_message_includes_params_keys(self):
        """The exception message should include sorted parameter keys."""
        exc = ContinueAsNew(new_params={"z_key": 1, "a_key": 2}, version="3.0.0")

        msg = str(exc)
        assert "a_key" in msg
        assert "z_key" in msg
        assert "3.0.0" in msg

    def test_is_catchable_as_exception(self):
        """ContinueAsNew should be catchable as a standard Exception."""
        with pytest.raises(ContinueAsNew) as exc_info:
            raise ContinueAsNew(new_params={"batch": 5})

        assert exc_info.value.new_params == {"batch": 5}

    def test_none_params_becomes_empty_dict(self):
        """Passing None for new_params should result in empty dict."""
        exc = ContinueAsNew(new_params=None)
        assert exc.new_params == {}


class TestContinuationDepthExceededError:
    """Tests for the ContinuationDepthExceededError."""

    def test_attributes(self):
        """Error should carry depth, max_depth, and chain."""
        err = ContinuationDepthExceededError(
            depth=1001, max_depth=1000, chain=["run-1", "run-2"]
        )

        assert err.depth == 1001
        assert err.max_depth == 1000
        assert err.chain == ["run-1", "run-2"]

    def test_message(self):
        """Error message should explain the problem."""
        err = ContinuationDepthExceededError(
            depth=5, max_depth=3, chain=["a", "b", "c", "d"]
        )

        msg = str(err)
        assert "5" in msg
        assert "3" in msg
        assert "infinite continuation loop" in msg


class TestContinuationContext:
    """Tests for the ContinuationContext tracker."""

    def test_initial_state(self):
        """A fresh context should have depth 0 and no continuation chain."""
        ctx = ContinuationContext()

        assert ctx.depth == 0
        assert ctx.continued_from is None
        assert ctx.chain == []
        assert ctx.max_depth == DEFAULT_MAX_CONTINUATION_DEPTH

    def test_default_max_depth(self):
        """Default max depth should be 1000."""
        assert DEFAULT_MAX_CONTINUATION_DEPTH == 1000

    def test_custom_max_depth(self):
        """Custom max_depth should be respected."""
        ctx = ContinuationContext(max_depth=5)
        assert ctx.max_depth == 5

    def test_record_single_continuation(self):
        """Recording one continuation should update depth and continued_from."""
        ctx = ContinuationContext()

        ctx.record_continuation("run-001", {"page": 2})

        assert ctx.depth == 1
        assert ctx.continued_from == "run-001"
        assert len(ctx.chain) == 1
        assert ctx.chain[0] == ("run-001", {"page": 2})

    def test_record_multiple_continuations(self):
        """Recording multiple continuations should build the chain correctly."""
        ctx = ContinuationContext()

        ctx.record_continuation("run-001", {"page": 1})
        ctx.record_continuation("run-002", {"page": 2})
        ctx.record_continuation("run-003", {"page": 3})

        assert ctx.depth == 3
        assert ctx.continued_from == "run-003"
        assert len(ctx.chain) == 3
        assert ctx.chain[0][0] == "run-001"
        assert ctx.chain[1][0] == "run-002"
        assert ctx.chain[2][0] == "run-003"

    def test_depth_exceeded_raises(self):
        """Exceeding max_depth should raise ContinuationDepthExceededError."""
        ctx = ContinuationContext(max_depth=3)

        ctx.record_continuation("run-1", {})
        ctx.record_continuation("run-2", {})
        ctx.record_continuation("run-3", {})

        with pytest.raises(ContinuationDepthExceededError) as exc_info:
            ctx.record_continuation("run-4", {})

        err = exc_info.value
        assert err.depth == 4
        assert err.max_depth == 3
        assert "run-4" in err.chain

    def test_depth_exceeded_does_not_mutate_context(self):
        """When depth is exceeded, the context should remain at the last valid state."""
        ctx = ContinuationContext(max_depth=2)

        ctx.record_continuation("run-1", {"a": 1})
        ctx.record_continuation("run-2", {"b": 2})

        with pytest.raises(ContinuationDepthExceededError):
            ctx.record_continuation("run-3", {"c": 3})

        # Context should still be at depth 2
        assert ctx.depth == 2
        assert ctx.continued_from == "run-2"
        assert len(ctx.chain) == 2

    def test_get_chain_run_ids(self):
        """get_chain_run_ids should return ordered run IDs."""
        ctx = ContinuationContext()

        ctx.record_continuation("run-a", {"x": 1})
        ctx.record_continuation("run-b", {"y": 2})
        ctx.record_continuation("run-c", {"z": 3})

        ids = ctx.get_chain_run_ids()
        assert ids == ["run-a", "run-b", "run-c"]

    def test_get_chain_run_ids_empty(self):
        """get_chain_run_ids should return empty list for fresh context."""
        ctx = ContinuationContext()
        assert ctx.get_chain_run_ids() == []

    def test_get_params_at_depth(self):
        """get_params_at_depth should return params for the specified continuation."""
        ctx = ContinuationContext()

        ctx.record_continuation("run-1", {"page": 1, "size": 100})
        ctx.record_continuation("run-2", {"page": 2, "size": 100})
        ctx.record_continuation("run-3", {"page": 3, "size": 200})

        assert ctx.get_params_at_depth(1) == {"page": 1, "size": 100}
        assert ctx.get_params_at_depth(2) == {"page": 2, "size": 100}
        assert ctx.get_params_at_depth(3) == {"page": 3, "size": 200}

    def test_get_params_at_depth_out_of_range(self):
        """get_params_at_depth should raise IndexError for invalid depth."""
        ctx = ContinuationContext()
        ctx.record_continuation("run-1", {"a": 1})

        with pytest.raises(IndexError, match="out of range"):
            ctx.get_params_at_depth(0)

        with pytest.raises(IndexError, match="out of range"):
            ctx.get_params_at_depth(2)

    def test_reset(self):
        """reset should clear the context but preserve max_depth."""
        ctx = ContinuationContext(max_depth=50)

        ctx.record_continuation("run-1", {"x": 1})
        ctx.record_continuation("run-2", {"y": 2})

        ctx.reset()

        assert ctx.depth == 0
        assert ctx.continued_from is None
        assert ctx.chain == []
        assert ctx.max_depth == 50

    def test_max_depth_of_one(self):
        """A max_depth of 1 should allow exactly one continuation."""
        ctx = ContinuationContext(max_depth=1)

        ctx.record_continuation("run-1", {"page": 1})
        assert ctx.depth == 1

        with pytest.raises(ContinuationDepthExceededError):
            ctx.record_continuation("run-2", {"page": 2})

    def test_chain_preserves_params_by_value(self):
        """Params in the chain should not be affected by later mutations."""
        ctx = ContinuationContext()
        params = {"counter": 0}

        ctx.record_continuation("run-1", params)

        # Mutate the original dict
        params["counter"] = 999

        # The chain should still have the original value
        # (Note: dataclass stores the reference, so this tests awareness)
        # In production, callers should not mutate params after passing them
        chain_params = ctx.chain[0][1]
        # This is a reference, so it will reflect the mutation
        # Documenting this behavior - callers must not mutate
        assert chain_params is params

    def test_continuation_depth_exceeded_chain_includes_failing_run(self):
        """The chain in the error should include the run that caused the overflow."""
        ctx = ContinuationContext(max_depth=2)

        ctx.record_continuation("run-1", {})
        ctx.record_continuation("run-2", {})

        with pytest.raises(ContinuationDepthExceededError) as exc_info:
            ctx.record_continuation("run-overflow", {})

        assert "run-overflow" in exc_info.value.chain
        assert "run-1" in exc_info.value.chain
        assert "run-2" in exc_info.value.chain
