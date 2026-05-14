# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for issue #979 / Workstream-A S-EV (test_dataflow_events).

Maps to ``briefs/00-brief.md:41-42`` AC#2 — "tests/unit/features/
test_dataflow_events.py — 4+ test failures from PR #976 investigation
diagnosed and fixed."

Root cause diagnosed in clean-venv reproduction
(`workspaces/issue-979-dataflow-unit-triage/journal/0007-DECISION-s-ev-resolution.md`):

1. ``DataFlowEventMixin._init_events`` imports
   ``kailash.middleware.communication.backends.memory.InMemoryEventBus``.
2. Python's import machinery runs ``kailash.middleware/__init__.py`` which
   eagerly imports ``kailash.nodes.admin.user_management`` (requires
   ``bcrypt``) AND ``kailash.middleware.communication.api_gateway``
   (requires ``fastapi``) — both from the ``kailash[server]`` extra.
3. ``kailash-dataflow[dev]`` did NOT declare ``kailash[server]``, so a
   clean ``pip install -e packages/kailash-dataflow[dev]`` left the
   import broken.
4. ``_init_events`` swallowed the ``ImportError`` silently and set
   ``_event_bus = None``. Per ``rules/zero-tolerance.md`` Rule 3a (Typed
   Delegate Guards), the silent fallback then produced
   ``AttributeError: 'NoneType' object has no attribute 'subscribe'`` on
   every subsequent ``_event_bus.subscribe(...)`` call — opaque, with
   no actionable hint pointing at the missing extra.

The fix has two layers:

* **Dep layer** — added ``kailash[server]`` to
  ``packages/kailash-dataflow/pyproject.toml::[dev]`` so clean-venv
  installs resolve the EventBus surface.
* **Code layer** — ``DataFlowEventMixin._init_events`` now records the
  ``ImportError`` into ``_event_bus_import_error`` AND
  ``on_model_change`` raises a typed ``DataFlowError`` naming the
  ``kailash[server]`` extra when ``_event_bus`` is ``None``.

These regressions are STRUCTURAL — config-text + function-signature
checks — per ``rules/probe-driven-verification.md`` MUST Rule 3.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = PACKAGE_ROOT / "pyproject.toml"


@pytest.mark.regression
def test_kailash_server_extra_pinned_in_dev() -> None:
    """``[dev]`` extras MUST declare ``kailash[server]`` so a clean-venv
    install resolves the InMemoryEventBus chain.

    Layer 1 of the S-EV fix. Without this pin, the import in
    ``DataFlowEventMixin._init_events`` fails on a clean install of
    ``kailash-dataflow[dev]`` because ``kailash[server]`` (bcrypt +
    fastapi + uvicorn + cryptography) is not transitively required.

    Uses ``tomllib`` (3.11+) to parse the TOML structurally — grep
    against the raw text mis-matches because dependency lines contain
    embedded ``]`` characters that confuse naive substring searches.
    """
    import tomllib

    with PYPROJECT.open("rb") as fh:
        data = tomllib.load(fh)

    dev_extras = data.get("project", {}).get("optional-dependencies", {}).get("dev", [])
    # Tolerate any specifier (>=X, ==X, no specifier) — the existence
    # of a dep whose name component is exactly ``kailash[server]`` is
    # the contract.
    has_server = any(
        entry.split(";")[0].strip().split(">=")[0].split("==")[0].strip()
        == "kailash[server]"
        for entry in dev_extras
    )
    assert has_server, (
        "kailash-dataflow[dev] MUST include 'kailash[server]' so the "
        "InMemoryEventBus chain resolves on clean-venv install. "
        "Per S-EV / issue #979 root-cause. Current dev extras: "
        f"{dev_extras}"
    )


@pytest.mark.regression
def test_event_mixin_records_import_error_attribute() -> None:
    """``DataFlowEventMixin`` MUST declare ``_event_bus_import_error``
    so ``on_model_change`` can surface a typed error citing the missing
    extra instead of letting ``AttributeError`` propagate from
    ``None.subscribe(...)``.

    Per ``rules/zero-tolerance.md`` Rule 3a (Typed Delegate Guards For
    None Backing Objects).
    """
    from dataflow.core.events import DataFlowEventMixin

    # Class-level default MUST exist so a fresh instance can be queried
    # before ``_init_events`` runs.
    assert hasattr(DataFlowEventMixin, "_event_bus_import_error"), (
        "DataFlowEventMixin MUST declare _event_bus_import_error at "
        "class scope so the typed-guard branch in on_model_change can "
        "read it without an AttributeError of its own."
    )
    assert DataFlowEventMixin._event_bus_import_error is None


@pytest.mark.regression
def test_on_model_change_raises_typed_error_when_bus_missing() -> None:
    """``on_model_change`` MUST raise ``DataFlowError`` (not the opaque
    ``AttributeError: NoneType.subscribe``) when ``_event_bus`` is
    ``None``. The error message MUST name the ``kailash[server]`` extra
    so the user can act on it.
    """
    from dataflow.core.events import DataFlowEventMixin
    from dataflow.exceptions import DataFlowError

    class _Stub(DataFlowEventMixin):
        _connected = True

    stub = _Stub()
    # Simulate the ImportError path WITHOUT actually breaking the
    # process import. We mimic the post-_init_events state where
    # _event_bus is None and the import-error is recorded.
    stub._event_bus = None
    stub._event_bus_import_error = ImportError("simulated missing dep")

    with pytest.raises(DataFlowError) as excinfo:
        stub.on_model_change("User", lambda evt: None)

    msg = str(excinfo.value)
    assert "kailash[server]" in msg, (
        "on_model_change MUST cite the kailash[server] extra so the "
        "user knows how to fix the missing dep. Got: " + msg
    )
