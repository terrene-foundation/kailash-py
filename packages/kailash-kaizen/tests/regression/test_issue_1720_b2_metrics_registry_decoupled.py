# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-B2 integration invariant — metrics is decoupled from the legacy
provider registry AT RUNTIME.

This is a WAVE-level property that holds ONLY with BOTH B2 shards applied:

* **B2b** repointed ``production/metrics.py`` off ``providers.registry`` onto the
  pure-data ``providers.provider_names`` module (source-level decoupling), AND
* **B2a** converted the ``nodes/ai/__init__`` + ``providers/__init__`` barrels to
  lazy PEP 562 ``__getattr__`` shims, so ``import kaizen`` no longer eager-loads
  the registry (which the barrels previously imported at module top).

Together they make ``import kaizen.production.metrics`` load NEITHER the legacy
``providers.registry`` NOR any ``providers.llm.*`` provider class. This matters
for the Wave-C delete: once the registry / ``providers/llm/`` are deleted,
``metrics.py`` (a pure-Prometheus module) must not have dragged them in.

Asserted in a FRESH subprocess so the result is order-independent — an unrelated
test importing a provider earlier in the same interpreter cannot mask a
regression here (rules/testing.md § deterministic + isolated).
"""

from __future__ import annotations

import subprocess
import sys

import pytest

# Probe: import ONLY metrics in a clean interpreter, then inspect sys.modules.
_PROBE = """
import kaizen.production.metrics
import sys
registry = "kaizen.providers.registry" in sys.modules
llm_classes = sorted(k for k in sys.modules if k.startswith("kaizen.providers.llm."))
print("REGISTRY", registry)
print("LLM", ",".join(llm_classes))
"""


@pytest.mark.regression
def test_importing_metrics_does_not_load_registry_or_provider_classes():
    """`import kaizen.production.metrics` must not pull in the legacy registry
    or any provider class (Wave-C delete-safety invariant)."""
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert (
        proc.returncode == 0
    ), f"probe crashed:\nstdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    out = proc.stdout
    assert "REGISTRY False" in out, (
        "importing kaizen.production.metrics loaded kaizen.providers.registry — "
        "the B2 metrics/registry decoupling has regressed (a barrel or an "
        f"eager import re-coupled them).\nprobe stdout:\n{out}"
    )
    assert "LLM \n" in out or out.rstrip().endswith("LLM"), (
        "importing kaizen.production.metrics loaded a providers.llm.* provider "
        f"class — decoupling regressed.\nprobe stdout:\n{out}"
    )


@pytest.mark.regression
def test_bare_import_kaizen_does_not_eager_load_registry():
    """Bare `import kaizen` must not eager-load the registry (B2a lazified the
    barrels that previously imported it at module top)."""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import kaizen, sys; print('REGISTRY', 'kaizen.providers.registry' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"probe crashed: {proc.stderr!r}"
    assert "REGISTRY False" in proc.stdout, (
        "bare `import kaizen` eager-loaded kaizen.providers.registry — the B2a "
        f"barrel lazification has regressed.\nprobe stdout:\n{proc.stdout}"
    )
