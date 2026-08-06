# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""One shared binder for the workflow ``parameters`` envelope.

A workflow registered ONCE is reachable from many entry points -- the HTTP
route, the CLI, several MCP paths, WebSocket, and the Core SDK channels -- and
each one independently decides how to hand the caller's arguments to the
runtime. When they disagree, the SAME registered workflow succeeds on one
channel and raises ``NameError: name 'parameters' is not defined`` on another.

That is exactly what happened: some paths bound the caller's mapping under a
``parameters`` key (so a node could read ``parameters.get("id")``, the
documented Nexus convention) while others passed it through raw (so only bare
top-level names resolved).

This module is the single place that decision is made. Every entry point calls
:func:`bind_parameter_envelope`, so there is one contract to reason about
instead of one per channel, and a future change lands everywhere at once.

Kept free of any ``kailash`` imports on purpose: it is imported from the Core
SDK channels AND from the separately-installed ``kailash-nexus`` transports, so
it must not drag the workflow graph (or anything else) into those import paths.
"""

from typing import Any, Mapping

__all__ = ["bind_parameter_envelope"]


def bind_parameter_envelope(params: Mapping[str, Any] | None) -> dict[str, Any]:
    """Bind a caller's arguments in BOTH shapes for workflow execution.

    Returns a mapping carrying every key at workflow level (the historical
    binding every existing caller relies on) AND the whole mapping under the
    name ``parameters`` (the documented convention a node reads via
    ``parameters.get(...)``).

    Precedence is FIXED, not incidental: when the caller's own arguments
    contain a key literally named ``parameters``, the ENVELOPE wins -- the
    explicit key is applied after the splat. The envelope binding is a contract
    every ``parameters.get(...)`` workflow depends on, so it must not become
    conditional on caller data; the caller's colliding value stays reachable at
    ``parameters["parameters"]``.

    A ``None`` or empty mapping still binds an EMPTY envelope, so a workflow
    written to the convention reaches its own defaults
    (``parameters.get("message", "hi")``) on an argument-less call rather than
    raising ``NameError``.

    Known limitation, shared identically by every channel: the runtime treats a
    workflow-level input whose key matches a NODE ID as node-specific
    parameters and unwraps it into that node alone
    (``kailash/runtime/async_local.py``). A workflow with a node literally named
    ``parameters`` therefore does not receive the envelope as a workflow-level
    input. That is pre-existing runtime scoping and it affects every channel
    equally, so parity is preserved.

    Args:
        params: The caller's arguments, or None.

    Returns:
        A new dict binding both shapes. The input is never mutated.
    """
    if not params:
        return {"parameters": {}}

    resolved = dict(params)
    # Envelope key applied AFTER the splat, so it wins a collision.
    return {**resolved, "parameters": resolved}
