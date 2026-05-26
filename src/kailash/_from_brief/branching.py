# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Branching realizer helpers for the ``_from_brief()`` pipeline.

Once an LLM plan has been validated, realization is **deterministic
structural plumbing** — calling the framework's builder methods with
the validated identifiers. The helpers here cover the one shape that
recurs across every primitive: wiring connections between nodes,
including the branching case where a single source node fans out to
multiple targets.

These functions are permitted deterministic logic per
``rules/agent-reasoning.md`` § "Permitted Deterministic Logic" — they
do NOT decide what the agent thinks, only how a validated plan maps
to the framework's API.

Origin: issue #1125 — every plan downstream of validation will have a
connection list; centralizing the realizer makes the wiring uniform
across surfaces and easy to audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List

__all__ = ["ConnectionSpec", "realize_connection", "realize_connections"]


@dataclass(frozen=True)
class ConnectionSpec:
    """A single edge in a validated plan's connection graph.

    Mirrors the 4-argument shape of
    :meth:`kailash.workflow.builder.WorkflowBuilder.add_connection`:
    ``source_node, source_output, target_node, target_input``. Defaults
    match the framework's most common shape (``result`` → ``input``) so
    a minimal plan stays terse.

    Attributes:
        source_node: The source node identifier (matches a node_id
            previously added to the builder).
        target_node: The target node identifier.
        source_output: The source node's output port; default
            ``"result"`` matches the framework's primary output port
            name across most node types.
        target_input: The target node's input port; default
            ``"input"`` matches the framework's primary input port.
        metadata: Optional dict reserved for plan-specific annotations
            (e.g. branching labels). The realizer ignores it; callers
            MAY inspect it for downstream verification.
    """

    source_node: str
    target_node: str
    source_output: str = "result"
    target_input: str = "input"
    metadata: dict[str, Any] = field(default_factory=dict)


def realize_connection(
    builder: Any,
    source_node: str,
    target_node: str,
    source_output: str = "result",
    target_input: str = "input",
) -> None:
    """Add one validated connection to a builder.

    Thin wrapper over the builder's ``add_connection`` method so the
    realizer call site does not have to know the framework's exact
    argument order. The wrapper exists specifically so this module
    holds the single grep target for "where does a from-brief plan
    realize into the framework's connection API".

    Args:
        builder: A framework builder exposing ``add_connection(
            source_node, source_output, target_node, target_input)``.
            Typed as ``Any`` to avoid a circular import with
            ``kailash.workflow.builder``; the duck-typed contract is
            the four-argument method.
        source_node: The source node identifier.
        target_node: The target node identifier.
        source_output: Source output port; defaults to ``"result"``.
        target_input: Target input port; defaults to ``"input"``.
    """
    builder.add_connection(source_node, source_output, target_node, target_input)


def realize_connections(
    builder: Any,
    connection_specs: Iterable[ConnectionSpec],
) -> None:
    """Realize a sequence of connection specs.

    Handles the branching shape (one source fans out to many targets)
    by iterating: a list with two specs sharing ``source_node`` calls
    ``add_connection`` twice, which is exactly the framework's API
    for a branched output.

    Args:
        builder: A framework builder exposing ``add_connection``.
        connection_specs: An iterable of :class:`ConnectionSpec`
            instances. Iteration order is preserved; the realizer
            calls ``add_connection`` in the same order the LLM emitted
            the plan, so a deterministic plan yields a deterministic
            graph.

    Returns:
        ``None``. Mutation of ``builder`` is the side effect.
    """
    specs_list: List[ConnectionSpec] = list(connection_specs)
    for spec in specs_list:
        realize_connection(
            builder,
            spec.source_node,
            spec.target_node,
            source_output=spec.source_output,
            target_input=spec.target_input,
        )
