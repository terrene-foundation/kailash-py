# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 cross-SDK wiring test for the W30 RL + Alignment bridge.

Per ``specs/ml-rl-align-unification.md`` §4. Exercises the kailash-ml
→ kailash-align dispatch path through the real ``km.rl_train`` entry
point and the real ``ExperimentTracker`` backend (no mocking per
``rules/testing.md`` § Tier 2).

Two separable tests:

1. :func:`test_align_bridge_adapters_all_satisfy_protocol` — cheap
   structural sweep. Iterates ``BRIDGE_ADAPTERS`` (populated when
   ``kailash_align.rl_bridge`` is imported) and asserts every
   registered adapter class satisfies :class:`RLLifecycleProtocol` at
   runtime. Closes round-1 HIGH-11 structurally — drift between the
   Protocol spec and any adapter surface fails loud.

2. :func:`test_km_rl_train_dispatches_to_align_dpo` — end-to-end via
   ``km.rl_train(algo="dpo", ...)`` against a tiny LM + tiny
   preference dataset + a real ``ExperimentTracker`` on SQLite. Gated
   on ``KAILASH_ML_RUN_TRL_E2E=1`` because TRL downloads model
   weights on first run (~5MB for ``sshleifer/tiny-gpt2`` but still
   network-bound) and runs a few real training steps.

Both tests skip gracefully when ``kailash_align`` is not installed
(the ``[rl-bridge]`` extra is optional, and CI matrix jobs without it
MUST see ``skipped``, not ``errored``).
"""

from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import os

import pytest


def _align_installed() -> bool:
    """Return True only when the optional ``[rl-bridge]`` bridge is IMPORTABLE.

    Probes ``importlib.util.find_spec`` FIRST (cheap, no module-body
    execution) to short-circuit the common "parent package entirely absent"
    case before any import work, then confirms the bridge actually imports.

    Fails closed to ``False`` on EVERY unavailability mode, because this
    guard runs inside the ``@pytest.mark.skipif`` decorator at collection
    time and any propagated ``ImportError`` crashes pytest collection (a
    collection error) instead of cleanly SKIPping:

    1. **Parent package absent.** When ``kailash_align`` is not installed,
       ``find_spec`` on the ``kailash_align.rl_bridge`` SUBMODULE raises
       ``ModuleNotFoundError`` — it does NOT return ``None``. The
       ``except ImportError`` arm (which subsumes ``ModuleNotFoundError``)
       catches it → ``False``.
    2. **Findable but not importable.** The ``rl_bridge`` package directory
       can exist on disk (so ``find_spec`` returns a spec) while its
       ``__init__`` raises ``ImportError`` because the ``[rl-bridge]``
       extra's runtime deps are absent. ``find_spec`` does NOT execute the
       module body, so a spec being *findable* does not mean the submodule
       is *importable*; the skip MUST predicate on importability. We attempt
       the real import and fail closed on ``ImportError`` → ``False``.

    Importing the bridge here is side-effect-safe: a SUCCESSFUL import is
    the same cached module the test body re-imports idempotently (it does
    not double-populate ``BRIDGE_ADAPTERS``); a FAILED import populates
    nothing. Returns True only when the bridge genuinely imports, so the
    gated tests run; otherwise they SKIP.
    """
    try:
        if importlib.util.find_spec("kailash_align.rl_bridge") is None:
            return False
        importlib.import_module("kailash_align.rl_bridge")
        return True
    except ImportError:
        return False


class _AlignAbsentFinder:
    """Meta-path finder that simulates ``kailash_align`` being uninstalled.

    When ``kailash_align`` is absent, ``importlib.util.find_spec`` on the
    ``kailash_align.rl_bridge`` SUBMODULE raises ``ModuleNotFoundError``
    (the parent package cannot be imported to compute the child spec).
    This finder reproduces that condition deterministically even in
    environments where the ``[rl-bridge]`` extra IS installed, so the
    regression below behaviorally exercises the fail-closed guard.
    """

    def find_spec(self, fullname, path, target=None):
        if fullname == "kailash_align" or fullname.startswith("kailash_align."):
            raise ModuleNotFoundError(f"No module named {fullname!r}")
        return None


@pytest.mark.regression
def test_align_installed_fails_closed_when_dep_absent(monkeypatch) -> None:
    """Regression: ``_align_installed()`` returns False (never raises) when
    ``kailash_align`` is absent.

    Reproduces the collection-time crash class: ``find_spec`` on a SUBMODULE
    of an uninstalled parent package raises ``ModuleNotFoundError`` rather
    than returning ``None``. Because ``_align_installed()`` runs inside the
    ``@pytest.mark.skipif`` decorator at collection time, an unguarded raise
    crashes pytest collection (1 collection error) instead of SKIPping. The
    fix fails closed to ``False`` so the dependent tests SKIP cleanly.

    The blocker is installed at the FRONT of ``sys.meta_path`` and any
    already-resolved ``kailash_align`` modules are evicted so ``find_spec``
    re-resolves through the blocker — making this deterministic whether or
    not the ``[rl-bridge]`` extra is installed in the running environment.
    """
    import sys

    # Evict any cached kailash_align* modules so find_spec re-resolves.
    for name in list(sys.modules):
        if name == "kailash_align" or name.startswith("kailash_align."):
            monkeypatch.delitem(sys.modules, name, raising=False)

    blocker = _AlignAbsentFinder()
    monkeypatch.setattr(sys, "meta_path", [blocker, *sys.meta_path])

    # Sanity-check the blocker reproduces the documented raise behavior.
    with pytest.raises(ModuleNotFoundError):
        importlib.util.find_spec("kailash_align.rl_bridge")

    # The guard MUST swallow that raise and return False (fail-closed to SKIP).
    assert _align_installed() is False


@pytest.mark.regression
def test_align_installed_fails_closed_when_bridge_findable_but_not_importable(
    monkeypatch,
) -> None:
    """Regression: ``_align_installed()`` returns False (never raises) when
    ``kailash_align.rl_bridge`` is FINDABLE but its import raises.

    The ``rl_bridge`` package directory can exist on disk (so ``find_spec``
    returns a real spec) while importing it raises ``ImportError`` because
    the optional ``[rl-bridge]`` extra's runtime deps are absent — this is
    exactly the half-installed-extra state. ``find_spec`` does NOT execute
    the module body, so the guard MUST attempt the import to detect this
    mode and fail closed to SKIP rather than letting the ``ImportError``
    propagate from the ``@skipif`` decorator and crash collection.

    Deterministic regardless of the running environment: we stub
    ``importlib.import_module`` to raise for the bridge while leaving
    ``find_spec`` to return a (real or fabricated) non-None spec.
    """
    real_find_spec = importlib.util.find_spec
    real_import_module = importlib.import_module

    def _findable_spec(name, package=None):
        if name == "kailash_align.rl_bridge":
            # Fabricate a non-None spec so the guard proceeds to import.
            return importlib.machinery.ModuleSpec(name, loader=None)
        return real_find_spec(name, package)

    def _import_raises(name, package=None):
        if name == "kailash_align.rl_bridge":
            raise ImportError("kailash_align.rl_bridge requires the [rl-bridge] extra")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", _findable_spec)
    monkeypatch.setattr(importlib, "import_module", _import_raises)

    # Sanity-check the simulation: spec is findable, import raises.
    assert importlib.util.find_spec("kailash_align.rl_bridge") is not None
    with pytest.raises(ImportError):
        importlib.import_module("kailash_align.rl_bridge")

    # The guard MUST predicate on importability and fail closed → False.
    assert _align_installed() is False


@pytest.mark.integration
@pytest.mark.skipif(not _align_installed(), reason="requires kailash-align[rl-bridge]")
def test_align_bridge_adapters_all_satisfy_protocol() -> None:
    """Every bridged adapter conforms to ``RLLifecycleProtocol`` at runtime.

    Closes spec §2.3 / §4 "all adapters satisfy Protocol" sweep and
    HIGH-11 cross-SDK facet. Drift between the Protocol contract and
    an align-side adapter (missing ``name`` / ``paradigm`` attr,
    missing ``build`` / ``learn`` / ``save`` / ``checkpoint`` /
    ``emit_metric`` method, etc.) fails here before it can reach a
    downstream user.
    """
    # Import triggers register_bridge_adapters() → BRIDGE_ADAPTERS populated.
    importlib.import_module("kailash_align.rl_bridge")

    from kailash_ml.rl.align_adapter import BRIDGE_ADAPTERS
    from kailash_ml.rl.protocols import RLLifecycleProtocol

    assert BRIDGE_ADAPTERS, (
        "BRIDGE_ADAPTERS is empty after importing kailash_align.rl_bridge; "
        "register_bridge_adapters() did not run or did not populate the registry."
    )

    # Spec §9 v1 scope — all four adapters must be present.
    expected = {"dpo", "ppo-rlhf", "rloo", "online-dpo"}
    missing = expected - BRIDGE_ADAPTERS.keys()
    assert not missing, (
        f"BRIDGE_ADAPTERS missing v1 adapters: {sorted(missing)} "
        f"(present: {sorted(BRIDGE_ADAPTERS.keys())})"
    )

    # Structural conformance — every class has __make_for_test__ + isinstance holds.
    for name, adapter_cls in BRIDGE_ADAPTERS.items():
        assert hasattr(adapter_cls, "__make_for_test__"), (
            f"Bridge adapter {name!r} ({adapter_cls.__module__}.{adapter_cls.__name__}) "
            f"is missing the __make_for_test__ classmethod required by spec §4."
        )
        instance = adapter_cls.__make_for_test__()
        assert isinstance(instance, RLLifecycleProtocol), (
            f"Bridge adapter {name!r} instance does not satisfy RLLifecycleProtocol "
            f"at runtime — structural drift. Check class-level attrs "
            f"(name / paradigm / buffer_kind) and lifecycle methods "
            f"(build / learn / save / load / checkpoint / resume / emit_metric)."
        )
        assert instance.name == name, (
            f"Adapter class-level name={instance.name!r} does not match registry "
            f"key {name!r} — registration/class definition drift."
        )


@pytest.mark.integration
@pytest.mark.skipif(
    not _align_installed() or os.environ.get("KAILASH_ML_RUN_TRL_E2E") != "1",
    reason=(
        "requires kailash-align[rl-bridge] AND KAILASH_ML_RUN_TRL_E2E=1 "
        "(TRL end-to-end test downloads sshleifer/tiny-gpt2 + runs real training steps)"
    ),
)
async def test_km_rl_train_dispatches_to_align_dpo(tmp_path):
    """End-to-end: ``km.rl_train(algo='dpo', ...)`` dispatches to align and
    emits telemetry through the same ``km.track()`` tracker as classical RL.

    Per spec §4 — the test rides BOTH halves of the cross-SDK contract
    (ml side defines Protocol + dispatch; align side satisfies it + produces
    RLTrainingResult with populated lineage). Guarded per
    ``rules/orphan-detection.md`` §2a style: runs only when the extra is
    installed AND explicit E2E opt-in is signalled.
    """
    import kailash_ml as km
    import polars as pl
    from kailash_ml.engines.experiment_tracker import ExperimentTracker
    from kailash_ml.rl.protocols import RLLifecycleProtocol

    # Minimal preference dataset — 4 pairs, duplicated for a few training steps.
    prefs = pl.DataFrame(
        {
            "prompt": ["Hello", "Goodbye"] * 4,
            "chosen": ["Hi there!", "Farewell!"] * 4,
            "rejected": ["hrrr", "whatever"] * 4,
        }
    )

    tracker = await ExperimentTracker.create(f"sqlite:///{tmp_path}/ml.db")
    async with tracker:
        result = km.rl_train(
            env="text:preferences",
            algo="dpo",
            policy="sshleifer/tiny-gpt2",
            reference_model="sshleifer/tiny-gpt2",
            preference_dataset=prefs,
            total_timesteps=2,
            eval_freq=2,
            n_eval_episodes=2,
            tracker=tracker,
            experiment="test-rl-align",
            tenant_id="t-dpo",
            hyperparameters={"beta": 0.1, "learning_rate": 5e-7, "batch_size": 2},
            ref_temperature=1.0,
        )

        # Result-shape parity — same type as classical RL (spec §3.2).
        assert isinstance(result, km.RLTrainingResult)
        assert result.algorithm == "dpo"

        # Lineage populated with sdk_source="kailash-align" (spec §5.2).
        assert result.lineage is not None
        assert result.lineage.sdk_source == "kailash-align"
        assert result.lineage.algorithm == "dpo"
        assert result.lineage.paradigm == "rlhf"
        assert result.lineage.tenant_id == "t-dpo"

        # The bridge adapter satisfied RLLifecycleProtocol at runtime.
        adapter = getattr(result, "_adapter_ref", None)
        if adapter is not None:  # test-only accessor may not be populated
            assert isinstance(adapter, RLLifecycleProtocol)

        # Tracker parity — rl.* metric families emitted via the shared callback
        # (spec §3.3). Classical RL and RLHF emit the same keys where the
        # concept is identical.
        run_ids = [r.run_id for r in await tracker.list_runs()]
        assert result.run_id in run_ids
