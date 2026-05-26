# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for the branching realizer helpers.

The realizer is duck-typed against the framework's builder. These
tests use a Protocol-satisfying deterministic adapter (per
``rules/testing.md`` § "Protocol Adapters") — a class that records
every ``add_connection`` invocation in a list so the test can assert
the exact arguments and order the realizer used.
"""

from __future__ import annotations

from typing import List, Tuple

from kailash._from_brief.branching import (
    ConnectionSpec,
    realize_connection,
    realize_connections,
)


class BuilderRecorder:
    """Duck-typed builder that records every ``add_connection`` call.

    Satisfies the realizer's single-method contract. Defined with a
    Recorder suffix to avoid pytest's ``Test*`` collection rule per
    ``rules/testing.md`` § "Helper Classes Use Stub/Helper/Fake
    Suffix".
    """

    def __init__(self) -> None:
        self.calls: List[Tuple[str, str, str, str]] = []

    def add_connection(
        self,
        source_node: str,
        source_output: str,
        target_node: str,
        target_input: str,
    ) -> None:
        self.calls.append((source_node, source_output, target_node, target_input))


class TestRealizeConnection:
    def test_default_ports_resolve_correctly(self):
        builder = BuilderRecorder()
        realize_connection(builder, "src", "dst")
        assert builder.calls == [("src", "result", "dst", "input")]

    def test_explicit_ports_passed_through(self):
        builder = BuilderRecorder()
        realize_connection(
            builder,
            "src",
            "dst",
            source_output="custom_out",
            target_input="custom_in",
        )
        assert builder.calls == [("src", "custom_out", "dst", "custom_in")]

    def test_no_side_effects_beyond_add_connection(self):
        builder = BuilderRecorder()
        realize_connection(builder, "a", "b")
        # Only one call recorded; no other state mutated.
        assert len(builder.calls) == 1


class TestRealizeConnections:
    def test_empty_iterable_no_calls(self):
        builder = BuilderRecorder()
        realize_connections(builder, [])
        assert builder.calls == []

    def test_single_connection(self):
        builder = BuilderRecorder()
        realize_connections(builder, [ConnectionSpec(source_node="a", target_node="b")])
        assert builder.calls == [("a", "result", "b", "input")]

    def test_branching_one_source_two_targets(self):
        builder = BuilderRecorder()
        specs = [
            ConnectionSpec(source_node="parser", target_node="left"),
            ConnectionSpec(source_node="parser", target_node="right"),
        ]
        realize_connections(builder, specs)
        assert builder.calls == [
            ("parser", "result", "left", "input"),
            ("parser", "result", "right", "input"),
        ]

    def test_iteration_order_preserved(self):
        builder = BuilderRecorder()
        specs = [
            ConnectionSpec(source_node="a", target_node="b"),
            ConnectionSpec(source_node="c", target_node="d"),
            ConnectionSpec(source_node="e", target_node="f"),
        ]
        realize_connections(builder, specs)
        sources_in_order = [call[0] for call in builder.calls]
        assert sources_in_order == ["a", "c", "e"]

    def test_custom_ports_per_spec(self):
        builder = BuilderRecorder()
        specs = [
            ConnectionSpec(
                source_node="a",
                target_node="b",
                source_output="rows",
                target_input="data",
            ),
            ConnectionSpec(source_node="a", target_node="c"),
        ]
        realize_connections(builder, specs)
        assert builder.calls == [
            ("a", "rows", "b", "data"),
            ("a", "result", "c", "input"),
        ]

    def test_generator_input_works(self):
        builder = BuilderRecorder()

        def gen():
            yield ConnectionSpec(source_node="x", target_node="y")
            yield ConnectionSpec(source_node="y", target_node="z")

        realize_connections(builder, gen())
        assert len(builder.calls) == 2
