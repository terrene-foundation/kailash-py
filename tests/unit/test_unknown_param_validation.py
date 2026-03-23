"""Unit tests for unknown parameter detection in Node.validate_inputs().

Tests verify that:
1. Passing an unknown param logs a WARNING
2. Passing an unknown param with _strict_unknown_params = True raises NodeValidationError
3. Known params still work fine (no false positives)
4. _SPECIAL_PARAMS (like "context") do not trigger the warning
5. Private params (starting with "_") do not trigger the warning
6. The warning message suggests similar valid param names

Tier 1: Unit tests - fast (<1s), isolated, no external dependencies.

Fixes GitHub issue #45: DataFlow UpdateNode silently ignores unknown parameters.
"""

import logging
from typing import Any

import pytest

from kailash.nodes.base import Node, NodeParameter
from kailash.sdk_exceptions import NodeValidationError


# ---------------------------------------------------------------------------
# Test node fixtures
# ---------------------------------------------------------------------------


class SimpleNode(Node):
    """A simple node with well-known parameters for testing."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "name": NodeParameter(
                name="name", type=str, required=True, description="The name"
            ),
            "count": NodeParameter(
                name="count",
                type=int,
                required=False,
                default=1,
                description="How many",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        return {"result": kwargs.get("name", "") * kwargs.get("count", 1)}


class StrictNode(Node):
    """A node with _strict_unknown_params = True."""

    _strict_unknown_params = True

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "value": NodeParameter(
                name="value", type=str, required=True, description="A value"
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        return {"echo": kwargs.get("value")}


class NodeWithAlias(Node):
    """A node whose parameter uses auto_map_from and workflow_alias."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "input_data": NodeParameter(
                name="input_data",
                type=str,
                required=True,
                description="Data input",
                auto_map_from=["data", "payload"],
                workflow_alias="input",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        return {"out": kwargs.get("input_data")}


class NodeWithPrimary(Node):
    """A node with a primary auto-map parameter."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "primary_input": NodeParameter(
                name="primary_input",
                type=str,
                required=True,
                description="Primary",
                auto_map_primary=True,
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        return {"out": kwargs.get("primary_input")}


# ---------------------------------------------------------------------------
# Tests: known parameters work correctly (no false positives)
# ---------------------------------------------------------------------------


class TestKnownParamsNoWarning:
    """Verify that valid/known parameters do NOT trigger unknown-param warnings."""

    def test_known_params_no_warning(self, caplog):
        """Passing only declared params should produce no warning."""
        node = SimpleNode(id="test")
        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            result = node.validate_inputs(name="hello", count=3)

        assert result["name"] == "hello"
        assert result["count"] == 3
        assert "unknown" not in caplog.text.lower()

    def test_known_params_subset_no_warning(self, caplog):
        """Passing a subset of declared params (optional omitted) triggers no warning."""
        node = SimpleNode(id="test")
        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            result = node.validate_inputs(name="hello")

        assert result["name"] == "hello"
        assert "unknown" not in caplog.text.lower()

    def test_alias_params_no_warning(self, caplog):
        """Params consumed via workflow_alias should not trigger unknown-param warning."""
        node = NodeWithAlias(id="test")
        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            result = node.validate_inputs(input="test_data")

        assert result["input_data"] == "test_data"
        assert "unknown" not in caplog.text.lower()

    def test_auto_map_from_params_no_warning(self, caplog):
        """Params consumed via auto_map_from should not trigger unknown-param warning."""
        node = NodeWithAlias(id="test")
        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            result = node.validate_inputs(data="test_data")

        assert result["input_data"] == "test_data"
        assert "unknown" not in caplog.text.lower()

    def test_primary_auto_map_no_warning(self, caplog):
        """Params consumed via auto_map_primary should not trigger unknown-param warning."""
        node = NodeWithPrimary(id="test")
        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            result = node.validate_inputs(some_arbitrary_input="primary_value")

        assert result["primary_input"] == "primary_value"
        assert "unknown" not in caplog.text.lower()


# ---------------------------------------------------------------------------
# Tests: _SPECIAL_PARAMS do not trigger warning
# ---------------------------------------------------------------------------


class TestSpecialParamsExcluded:
    """Verify that _SPECIAL_PARAMS (e.g., 'context') do not trigger warnings."""

    def test_context_param_no_warning(self, caplog):
        """The 'context' special param should never trigger unknown-param warning."""
        node = SimpleNode(id="test")
        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            result = node.validate_inputs(name="hello", context={"run_id": "abc"})

        assert result["name"] == "hello"
        assert result["context"] == {"run_id": "abc"}
        assert "unknown" not in caplog.text.lower()


# ---------------------------------------------------------------------------
# Tests: private params (starting with "_") do not trigger warning
# ---------------------------------------------------------------------------


class TestPrivateParamsExcluded:
    """Verify that private params (starting with '_') do not trigger warnings."""

    def test_private_param_no_warning(self, caplog):
        """Params starting with '_' should be silently ignored."""
        node = SimpleNode(id="test")
        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            result = node.validate_inputs(name="hello", _internal_flag=True)

        assert result["name"] == "hello"
        assert "unknown" not in caplog.text.lower()

    def test_multiple_private_params_no_warning(self, caplog):
        """Multiple private params should all be silently ignored."""
        node = SimpleNode(id="test")
        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            result = node.validate_inputs(
                name="hello", _flag1=True, _flag2="x", _flag3=42
            )

        assert result["name"] == "hello"
        assert "unknown" not in caplog.text.lower()


# ---------------------------------------------------------------------------
# Tests: unknown params trigger WARNING
# ---------------------------------------------------------------------------


class TestUnknownParamWarning:
    """Verify that unknown params produce a WARNING log message."""

    def test_single_unknown_param_warns(self, caplog):
        """A single unknown param should log a warning."""
        node = SimpleNode(id="test")
        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            result = node.validate_inputs(name="hello", bogus_param="oops")

        # The known param should still resolve
        assert result["name"] == "hello"
        # A warning should have been logged mentioning the unknown param
        assert "bogus_param" in caplog.text
        assert "unknown" in caplog.text.lower()

    def test_multiple_unknown_params_warns(self, caplog):
        """Multiple unknown params should all appear in the warning."""
        node = SimpleNode(id="test")
        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            node.validate_inputs(name="hello", foo="bar", baz=42)

        assert "foo" in caplog.text
        assert "baz" in caplog.text

    def test_unknown_param_suggests_similar(self, caplog):
        """When an unknown param is similar to a valid one, suggest the valid name."""
        node = SimpleNode(id="test")
        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            # "nme" is close to "name", "cont" is close to "count"
            node.validate_inputs(name="hello", cont=5)

        # The suggestion should mention the similar valid param "count"
        assert "count" in caplog.text

    def test_unknown_param_does_not_affect_result(self, caplog):
        """Unknown params should not appear in the validated output."""
        node = SimpleNode(id="test")
        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            result = node.validate_inputs(name="hello", bogus="nope")

        assert "bogus" not in result

    def test_unknown_param_with_cache_enabled(self, caplog):
        """Unknown param detection must also work when the cache path is taken."""
        node = SimpleNode(id="test")
        node._cache_enabled = True

        # First call populates cache
        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            node.validate_inputs(name="hello", bogus="first")
        assert "bogus" in caplog.text

        caplog.clear()

        # Second call hits cache -- unknown detection must still fire
        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            node.validate_inputs(name="hello", bogus="second")
        assert "bogus" in caplog.text


# ---------------------------------------------------------------------------
# Tests: _strict_unknown_params = True raises NodeValidationError
# ---------------------------------------------------------------------------


class TestStrictUnknownParams:
    """When _strict_unknown_params = True, unknown params raise an error."""

    def test_strict_mode_raises_on_unknown(self):
        """Unknown params should raise NodeValidationError in strict mode."""
        node = StrictNode(id="test")
        with pytest.raises(NodeValidationError, match="Unknown parameter"):
            node.validate_inputs(value="ok", extra="bad")

    def test_strict_mode_allows_known_params(self):
        """Known params should still work in strict mode."""
        node = StrictNode(id="test")
        result = node.validate_inputs(value="good")
        assert result["value"] == "good"

    def test_strict_mode_allows_special_params(self):
        """Special params should not trigger error in strict mode."""
        node = StrictNode(id="test")
        result = node.validate_inputs(value="ok", context={"run_id": "x"})
        assert result["value"] == "ok"
        assert result["context"] == {"run_id": "x"}

    def test_strict_mode_allows_private_params(self):
        """Private params should not trigger error in strict mode."""
        node = StrictNode(id="test")
        result = node.validate_inputs(value="ok", _internal=True)
        assert result["value"] == "ok"

    def test_strict_mode_error_includes_suggestions(self):
        """The error message in strict mode should suggest similar valid params."""
        node = StrictNode(id="test")
        with pytest.raises(NodeValidationError, match="value") as exc_info:
            # "valu" is close to "value"
            node.validate_inputs(value="ok", valu="typo")
        # The error should mention the suggestion
        assert "value" in str(exc_info.value)

    def test_strict_mode_error_lists_all_unknown(self):
        """All unknown params should be listed in the error."""
        node = StrictNode(id="test")
        with pytest.raises(NodeValidationError) as exc_info:
            node.validate_inputs(value="ok", alpha="a", beta="b")
        error_msg = str(exc_info.value)
        assert "alpha" in error_msg
        assert "beta" in error_msg


# ---------------------------------------------------------------------------
# Tests: cache + alias path regression
# ---------------------------------------------------------------------------


class TestCacheAliasPath:
    """Regression tests for cache hit path with workflow_alias parameters.

    Verifies that on a cache hit the alias key is still recognised as valid
    (no spurious unknown-param warning) and that a genuinely unknown key still
    produces exactly one warning.
    """

    def test_alias_key_no_warning_on_cache_miss(self, caplog):
        """First call (cache miss) with alias key must not warn."""
        node = NodeWithAlias(id="test")
        node._cache_enabled = True

        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            result = node.validate_inputs(input="hello")

        assert result["input_data"] == "hello"
        assert "unknown" not in caplog.text.lower()

    def test_alias_key_no_warning_on_cache_hit(self, caplog):
        """Second call (cache hit) with alias key must not warn."""
        node = NodeWithAlias(id="test")
        node._cache_enabled = True

        # Populate cache
        node.validate_inputs(input="first")
        caplog.clear()

        # Cache hit — alias key must still be recognised
        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            result = node.validate_inputs(input="second")

        assert result["input_data"] == "second"
        assert "unknown" not in caplog.text.lower()

    def test_unknown_key_warns_on_cache_hit(self, caplog):
        """On a cache hit, an unknown key (not alias) must still trigger a warning."""
        node = NodeWithAlias(id="test")
        node._cache_enabled = True

        # Populate cache with alias key only
        node.validate_inputs(input="first")
        caplog.clear()

        # Cache hit + extra unknown key
        with caplog.at_level(logging.WARNING, logger="kailash.nodes.base"):
            node.validate_inputs(input="second", bogus_key="oops")

        assert "bogus_key" in caplog.text
        assert "unknown" in caplog.text.lower()
