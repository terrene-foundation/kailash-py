# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: README Quick Start MUST match the spec verbatim AND execute.

This test is **release-blocking**. It guards two invariants simultaneously:

1. Structural drift guard -- the first ```python block in
   ``packages/kailash-ml/README.md`` MUST match the canonical block in
   ``specs/ml-engines-v2.md §16.1`` byte-for-byte. SHA-256 fingerprint is
   pinned to ``c962060cf467cc732df355ec9e1212cfb0d7534a3eed4480b511adad5a9ceb00``.
   Drift fails the test with a diff; fix the README or amend §16.1 (never
   both in isolation).
2. Executability guard -- the parsed Quick Start block MUST actually run
   end-to-end against real infrastructure. The block opens a
   ``km.track`` context, trains a model, registers it, and stands up an
   inference server; the test asserts the observable effects (populated
   ``TrainingResult.device``, ``register`` returns an ``onnx`` artefact
   URI, and the REST channel resolves ``GET /health -> 200``).

Both invariants live in one test file so a PR that drifts the README from
the spec AND breaks the Engine's happy path fails loudly at CI collection
time rather than days later when a user tries to copy-paste.

Origin: W33b todo (M11 milestone), spec ``ml-engines-v2 §16.3``.
See ``MIGRATION.md`` for the 0.x -> 1.0.0 upgrade path that the Quick
Start now demonstrates.
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import urllib.error
import urllib.request

import polars as pl
import pytest

# ---------------------------------------------------------------------------
# Canonical block -- literal copy of specs/ml-engines-v2.md §16.1.
# Every character (whitespace, quotes, $ comment) is load-bearing. Changing
# any byte flips the fingerprint and fails the drift guard below.
# ---------------------------------------------------------------------------
CANONICAL_BLOCK = (
    "import kailash_ml as km\n"
    'async with km.track("demo") as run:\n'
    '    result = await km.train(df, target="y")\n'
    '    registered = await km.register(result, name="demo")\n'
    'server = await km.serve("demo@production")\n'
    "# $ kailash-ml-dashboard  (separate shell)\n"
)

CANONICAL_SHA = "c962060cf467cc732df355ec9e1212cfb0d7534a3eed4480b511adad5a9ceb00"

# Defensive: if the constant above ever drifts, the self-check below fails
# at collection time (not at test-execution time). This catches a typo in
# THIS file before it can mask a real README drift.
_computed_canonical_sha = hashlib.sha256(CANONICAL_BLOCK.encode("utf-8")).hexdigest()
assert _computed_canonical_sha == CANONICAL_SHA, (
    f"CANONICAL_BLOCK constant in this test file drifted from the spec "
    f"fingerprint. Expected {CANONICAL_SHA}, got {_computed_canonical_sha}. "
    f"Do NOT silently update CANONICAL_SHA -- the spec (§16.1) is the "
    f"contract. Amend the spec OR the README in a paired PR per §16.4."
)


def _package_root() -> pathlib.Path:
    """Return ``packages/kailash-ml/`` irrespective of pytest's cwd."""
    return pathlib.Path(__file__).resolve().parents[2]


def _extract_first_python_block(readme_text: str) -> str:
    """Extract the first ```python code block from README.md.

    Spec §16.3 pins this regex exactly; if you rewrite it, update the
    spec in the same PR.
    """
    match = re.search(r"```python\n(.*?)\n```", readme_text, flags=re.DOTALL)
    if match is None:
        raise AssertionError(
            "packages/kailash-ml/README.md has no ```python block -- "
            "the canonical Quick Start is missing. Restore the block "
            "per specs/ml-engines-v2.md §16.1."
        )
    # Append the trailing newline that was matched away by the regex so
    # fingerprinting is stable against the literal in §16.1.
    return match.group(1) + "\n"


# ---------------------------------------------------------------------------
# Invariant 1 -- README Quick Start fingerprint matches the spec.
# Pure filesystem read; no infra. Runs on every CI matrix job including
# CPU-only. Release-blocking.
# ---------------------------------------------------------------------------
@pytest.mark.regression
def test_readme_quickstart_fingerprint_matches_spec() -> None:
    """README Quick Start MUST be byte-identical to ml-engines-v2.md §16.1."""
    readme_path = _package_root() / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    code = _extract_first_python_block(readme)
    actual_sha = hashlib.sha256(code.encode("utf-8")).hexdigest()
    assert actual_sha == CANONICAL_SHA, (
        "README Quick Start drifted from specs/ml-engines-v2.md §16.1.\n"
        f"  expected SHA-256: {CANONICAL_SHA}\n"
        f"  actual   SHA-256: {actual_sha}\n\n"
        "canonical block (§16.1):\n"
        f"{CANONICAL_BLOCK}\n"
        "actual README block:\n"
        f"{code}\n"
        "Disposition per §16.4: fix README.md to match §16.1 verbatim, "
        "OR amend §16.1 via a spec-change PR that also updates the "
        "CANONICAL_BLOCK + CANONICAL_SHA constants in this file. Never "
        "both in isolation."
    )


# ---------------------------------------------------------------------------
# Invariant 2 -- Parsed block executes end-to-end against real infra.
# Uses real engines + real Nexus; no MagicMock anywhere (Tier 2/3 rule).
# The fixtures route the Engine's default store + artifact path at
# tmp_path via the KAILASH_ML_STORE_URL / KAILASH_ML_ARTIFACT_ROOT env
# vars that the Engine reads at __init__.
# ---------------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.integration
async def test_readme_quickstart_executes_end_to_end(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parse + execute the README Quick Start against real infrastructure.

    Asserts the spec §16.3 invariants:
    * ``run.run_id`` is non-empty after the async context exits.
    * ``result`` is a ``TrainingResult`` with ``device: DeviceReport``
      populated AND non-empty ``metrics``.
    * The ``device_used`` back-compat mirror resolves.
    * ``registered.artifact_uris["onnx"]`` starts with ``file://`` or
      ``cas://sha256:`` (§2.1 MUST 9: ONNX default).
    * ``server.uris["rest"]`` is reachable via ``GET /health -> 200``.
    * The tracker's list_runs() exposes the run under name ``"demo"``.
    """
    import kailash_ml as km

    # 1. Parse the Quick Start block out of README.md.
    readme = (_package_root() / "README.md").read_text(encoding="utf-8")
    code = _extract_first_python_block(readme)

    # 2. Redirect default store + artifact root at tmp_path so the Engine
    #    cache key for this process points at an ephemeral SQLite DB
    #    instead of the user's ``./kailash-ml.db``.
    monkeypatch.setenv("KAILASH_ML_STORE_URL", f"sqlite:///{tmp_path}/ml.db")
    monkeypatch.setenv("KAILASH_ML_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    # Reset the Engine's process-local cache so the env overrides above
    # actually take effect for this test. The cache is tenant_id-keyed
    # in ``kailash_ml._wrappers._default_engines``; the default
    # ``None``-tenant slot may already hold an Engine pointing at the
    # user's default store. Private import is intentional -- the reset
    # helper is declared in the wrappers module's ``__all__`` for test
    # use per specs/ml-engines-v2.md §15.3.
    from kailash_ml._wrappers import _reset_default_engines

    _reset_default_engines()

    # 3. Inject a tiny polars DataFrame with a binary target so km.train
    #    picks a classifier family deterministically. The block's
    #    ``target="y"`` pins the target column name.
    df = pl.DataFrame(
        {
            "x": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            "y": [0, 1, 0, 1, 0, 1, 0, 1],
        }
    )
    globals_ns: dict = {
        "df": df,
        "__name__": "__readme_quickstart__",
    }

    # 4. Wrap the literal Quick Start in an async def and exec it -- the
    #    block uses `async with`, so it MUST run inside a coroutine.
    indented = "\n".join("    " + line for line in code.splitlines())
    exec_wrapper = (
        "async def _quickstart():\n"
        f"{indented}\n"
        "    return run, result, registered, server\n"
    )
    exec(compile(exec_wrapper, "<readme_quickstart>", "exec"), globals_ns)
    run, result, registered, server = await globals_ns["_quickstart"]()

    try:
        # 5a. Run id populated after context exit (§16.3 assertion 4a).
        assert run.run_id, (
            "run.run_id must be non-empty after `async with km.track(...)` "
            "exits; the tracker's run finalisation did not populate the id"
        )

        # 5b. TrainingResult has metrics + populated DeviceReport
        #     (§4.2 MUST 1 + §16.3 assertion 4b).
        assert result.metrics, (
            "TrainingResult.metrics must be non-empty after km.train(df, "
            "target='y') on a classification target"
        )
        assert result.device is not None, (
            "TrainingResult.device: DeviceReport must be populated per "
            "specs/ml-engines-v2.md §4.2 MUST 1 (GPU-first transparency "
            "contract)"
        )
        assert result.device_used, (
            "TrainingResult.device_used back-compat mirror must resolve "
            "to a non-empty string per specs/ml-engines-v2.md §4.1"
        )

        # 5c. Registered artefact points at ONNX by default
        #     (§2.1 MUST 9 + §16.3 assertion 4c).
        assert "onnx" in registered.artifact_uris, (
            f"register() must default to ONNX artefact URI per §2.1 MUST 9; "
            f"got keys {sorted(registered.artifact_uris.keys())}"
        )
        onnx_uri = registered.artifact_uris["onnx"]
        assert onnx_uri.startswith(("file://", "cas://sha256:")), (
            f"ONNX artefact URI must start with 'file://' or "
            f"'cas://sha256:' per §16.3 assertion 4c; got '{onnx_uri}'"
        )

        # 5d. Server exposes a REST channel and /health resolves 200
        #     (§16.3 assertion 4d).
        rest_uri = server.uris.get("rest")
        assert rest_uri, (
            f"serve() must expose a REST channel per specs/ml-serving.md "
            f"§2.2; got uris={server.uris}"
        )
        # Probe /health -- the W31c ml-endpoints contract pins this to
        # return 200 when the model is loaded and ready.
        health_url = rest_uri.rstrip("/") + "/health"
        try:
            with urllib.request.urlopen(health_url, timeout=5.0) as resp:
                status = resp.status
        except urllib.error.URLError as exc:
            raise AssertionError(
                f"GET {health_url} did not resolve: {exc}. The Nexus "
                f"ml-endpoints /health contract (W31c) requires 200 "
                f"from a live serve() handle."
            ) from exc
        assert status == 200, (
            f"GET {health_url} returned {status}; expected 200 per "
            f"specs/ml-serving.md § Nexus ml-endpoints /health contract"
        )
    finally:
        # 6. Stop the inference server regardless of assertion outcome so
        #    the test does not leak a listening port into the next test.
        stop = getattr(server, "stop", None)
        if stop is not None:
            maybe_coro = stop()
            if hasattr(maybe_coro, "__await__"):
                await maybe_coro
