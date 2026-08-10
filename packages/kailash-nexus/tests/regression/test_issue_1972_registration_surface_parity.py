"""#1972 follow-up — name validation at EVERY registration surface, and the
auto-discovery regression that tightening created.

Both gaps were found by the round-2 correctness lens AFTER the fixes landed:

* The `HandlerRegistry.register_workflow` validation shipped with **zero** test
  coverage. Removing the check left the full nexus suite at 1880 passed — the
  surface was wide open (`'my workflow'`, `'a&b'`, `'a/b'` all accepted, the last
  being a path separator) and nothing failed. A fix no test protects is one
  refactor away from silently reverting.

* Tightening `register()` introduced a REGRESSION in auto-discovery. Discovery
  derives workflow names from FILENAMES (`file_path.stem`), and a filename may
  legally contain a space, parenthesis or non-ASCII character that is not a legal
  workflow name. `_auto_discover_workflows` had no guard, so ONE such file raised
  out of the loop and every OTHER discovered workflow silently failed to
  register — strictly worse than skipping the unnameable one.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Surface parity — HandlerRegistry is an INDEPENDENT public registration surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_name",
    [
        "my workflow",  # space
        "a&b",  # shell metacharacter
        "x#y",  # fragment delimiter
        "f(o)",  # parentheses
        "naïve",  # non-ASCII — percent-encodes, breaks workflow:// round-trip
        "a/b",  # path separator
    ],
)
def test_handler_registry_rejects_invalid_names(bad_name: str) -> None:
    """`HandlerRegistry` is exported from `nexus`, so it is a supported entry
    point. Validating only `Nexus.register()` would leave this path admitting a
    name the execute route later rejects — the exact asymmetry #1972 closed.
    """
    from nexus.registry import HandlerRegistry

    registry = HandlerRegistry()

    with pytest.raises(ValueError):
        registry.register_workflow(bad_name, object())

    # Fail-closed: a rejected name must leave NOTHING behind.
    assert bad_name not in registry._workflows
    assert registry._workflows == {}


def test_handler_registry_still_accepts_legal_names() -> None:
    """Guard against over-tightening: the allowlist must not reject valid names."""
    from nexus.registry import HandlerRegistry

    registry = HandlerRegistry()
    for good in ("my_workflow", "my-workflow.v2", "wf123"):
        registry.register_workflow(good, object())

    assert set(registry._workflows) == {"my_workflow", "my-workflow.v2", "wf123"}


def test_handler_registry_validates_before_mutating_state() -> None:
    """Validation must run BEFORE any state write, not after a partial one."""
    from nexus.registry import HandlerRegistry

    registry = HandlerRegistry()
    registry.register_workflow("good_one", object())

    with pytest.raises(ValueError):
        registry.register_workflow("bad name", object(), metadata={"k": "v"})

    assert set(registry._workflows) == {"good_one"}
    assert "bad name" not in registry._workflow_metadata


# ---------------------------------------------------------------------------
# Auto-discovery must survive an un-nameable file
# ---------------------------------------------------------------------------


def test_auto_discovery_skips_invalid_name_and_keeps_going(monkeypatch, caplog) -> None:
    """ONE un-nameable file must not abort registration of every other workflow.

    Before the guard, `_auto_discover_workflows` let the `ValueError` escape, so
    a single `sales report.workflow.py` in the directory meant NONE of the
    sibling workflows registered — and `Nexus.start()` aborted.
    """
    import logging

    from nexus.core import Nexus

    discovered = {
        "good_workflow": object(),
        "sales report.workflow": object(),  # legal filename, illegal workflow name
        "étude_workflow": object(),  # non-ASCII filename
        "another_good_one": object(),
    }

    monkeypatch.setattr(
        "nexus.discovery.discover_workflows", lambda *a, **k: discovered
    )

    from nexus.registry import HandlerRegistry

    app = Nexus.__new__(Nexus)  # bypass __init__ side effects (ports, servers)
    # `Nexus._workflows` is a property delegating to `self._registry`, so the
    # bare instance needs a real registry before it is touched.
    app._registry = HandlerRegistry()
    registered: list[str] = []

    def _fake_register(self, name, workflow):
        # Stand in for the real register(), which needs a fully-built Nexus.
        # Keeps the ONE behaviour under test: it validates and raises on a bad
        # name, exactly as the real surface does since #1972.
        from nexus.validation import validate_workflow_name

        validate_workflow_name(name)
        self._workflows[name] = workflow
        registered.append(name)

    # Class-level patch: an instance attribute does NOT shadow the bound method
    # reliably here, so `self.register(...)` inside the loop kept reaching the
    # real implementation.
    monkeypatch.setattr(Nexus, "register", _fake_register, raising=True)

    with caplog.at_level(logging.WARNING, logger="nexus.core"):
        # Must NOT raise.
        Nexus._auto_discover_workflows(app)

    assert "good_workflow" in registered, (
        "a valid workflow after the invalid one was never registered — the "
        "invalid name aborted the discovery loop"
    )
    assert "another_good_one" in registered
    assert "sales report.workflow" not in registered
    assert "étude_workflow" not in registered

    # Skipping must be LOUD — a silent skip is its own defect.
    skipped = [r for r in caplog.records if "invalid name" in r.getMessage()]
    assert (
        len(skipped) == 2
    ), f"expected 2 warnings, got {[r.getMessage() for r in skipped]}"
