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

WHICH ENTRY POINTS BIND
-----------------------

The rule is STRUCTURAL, not name-based::

    An entry point that offers the caller a CHOICE between a raw slot and an
    arguments slot honors that choice.

    An entry point with a SINGLE caller-arguments slot binds the envelope --
    whatever that slot happens to be named.

Keying the rule on the field NAME instead ("a field called ``inputs`` means
opt out") is wrong, because the name is reused for two different roles:

* :class:`~kailash.api.workflow_api.WorkflowRequest` exposes BOTH ``inputs``
  and ``parameters``. The caller picks, so ``inputs`` there genuinely means
  "I am supplying the exact runtime mapping; do not touch it."
* ``APIChannel.handle_request`` and ``MCPChannel._handle_execute_workflow``
  expose ONLY ``inputs``. It is their sole caller-arguments slot -- the same
  role ``parameters`` fills over HTTP, not the same role HTTP's ``inputs``
  fills. Reading it as an opt-out would leave those channels with no envelope
  path at all, and every ``parameters.get(...)`` workflow permanently broken
  there with no way for the caller to ask for the binding.

So the two surfaces are consistent under the structural rule even though they
share a field name, and the EQUIVALENT calls agree: an HTTP body of
``{"parameters": P}`` and a channel call of ``inputs=P`` produce the same
``parameters`` view for the same registered workflow. That equivalence is
pinned by ``tests/regression/test_issue_workflow_parameters_envelope_parity.py``
so it cannot drift back into an accident.

The opt-out is deliberately narrow: it exists only where the caller was given
a second slot to express it, plus the audited programmatic helper recorded in
``tests/regression/test_workflow_input_envelope_entry_points.py``.

A CALLER'S OWN ``parameters`` KEY IS OVERWRITTEN -- INTENTIONALLY
-----------------------------------------------------------------

The binding is ``{**body, "parameters": body}``, so a caller whose payload
already contains a key literally named ``parameters`` does not get that value
at ``parameters``; the envelope does. This is surprising, so it is written
down: the envelope binding is a contract every ``parameters.get(...)``
workflow depends on, and it MUST NOT become conditional on caller data -- a
workflow whose arguments happened to include a ``parameters`` key would
otherwise see ``parameters`` mean something different from every other call.
The caller's colliding value stays reachable at ``parameters["parameters"]``,
so nothing is lost.

The clobber is also IDENTICAL on every surface -- an HTTP ``{"parameters": P}``
body and a channel ``inputs=P`` call both yield ``{**P, "parameters": P}`` --
so it is a property of the shared binder, not a per-channel divergence. Both
halves are pinned (binder, HTTP, and cross-surface) in
``test_channel_parameters_envelope_behaviour.py`` and
``test_issue_workflow_parameters_envelope_parity.py``. Do not "fix" the
overwrite without changing that contract deliberately.

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
