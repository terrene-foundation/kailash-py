# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: Node init-param-capture must tolerate a non-dict ``self.config``.

A ``Node`` subclass may deliberately replace ``self.config`` (the dict
``Node.__init__`` creates) with a typed config object — e.g. kaizen's
``BaseAgentConfig``, which many ``kaizen_agents`` pattern nodes assign via
``self.config = config or SomeConfig()``.

The ``__init_with_capture`` wrapper merges init params into ``self.config`` for
round-trip faithfulness, iterating ``name in self.config`` and assigning
``self.config[name] = ...``. When ``self.config`` was a typed object rather than
a mapping, that raised ``TypeError: argument of type '<Config>' is not iterable``
at construction time, breaking ~93 ``kaizen_agents`` Pipeline orchestration
tests. The capture is a dict-only convenience and MUST skip (not crash) when
``self.config`` is not a mapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from kailash.nodes.base import Node, NodeParameter


@dataclass
class _TypedConfigStub:
    """Stand-in for a typed config object (e.g. BaseAgentConfig) — not a dict."""

    label: str = "x"


class _NonDictConfigNode(Node):
    """Node subclass that replaces self.config with a typed (non-dict) object."""

    def __init__(self, label: str = "x", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Deliberately clobber the dict Node.__init__ created with a typed object,
        # exactly as the kaizen_agents pattern nodes do with BaseAgentConfig.
        self.config = _TypedConfigStub(label=label)

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {}

    def run(self, **kwargs: Any) -> dict[str, Any]:
        return {}


class _DictConfigNode(Node):
    """Ordinary Node subclass that keeps the dict config Node.__init__ creates."""

    def __init__(self, alpha: str = "a", **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {}

    def run(self, **kwargs: Any) -> dict[str, Any]:
        return {}


@pytest.mark.regression
def test_node_init_capture_tolerates_non_dict_config() -> None:
    """Constructing a Node whose self.config is a typed object must not raise."""
    node = _NonDictConfigNode(label="hello")
    assert isinstance(node.config, _TypedConfigStub)
    assert node.config.label == "hello"


@pytest.mark.regression
def test_node_init_capture_preserves_dict_config_path() -> None:
    """The normal dict-config capture path is unchanged (no regression)."""
    node = _DictConfigNode(alpha="captured")
    assert isinstance(node.config, dict)
