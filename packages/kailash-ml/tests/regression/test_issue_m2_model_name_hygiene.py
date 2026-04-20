# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: M2 — model_name at INFO/WARN/ERROR in engine.py MUST be hashed.

Origin: 2026-04-20 late-session audit finding M2 — log sites in
``engine.py`` at INFO / WARN / ERROR level carried the raw
``model_name`` as a structured field. Per ``rules/observability.md``
§8, schema-revealing identifiers like model names MUST stay at DEBUG
or be hashed when emitted at any level above DEBUG (rule text:
"MUST be logged at DEBUG level — not WARN or INFO").

The canonical fingerprint format per ``rules/event-payload-classification.md``
MUST Rule 2 is **8 hex chars of SHA-256** (NOT Python's built-in
``hash()`` — that's PYTHONHASHSEED-randomized and differs per process,
which defeats cross-process log-aggregator correlation).

This file provides three complementary guards:

1. **Behavioural WARN** — exercises the
   ``engine.register.onnx_partial_failure`` WARN path end-to-end and
   asserts the hashed partition (WARN carries
   ``model_name_fingerprint``; DEBUG sibling carries raw
   ``model_name``).

2. **AST invariant across ALL log levels** — walks every
   ``logger.info`` / ``logger.warning`` / ``logger.error`` /
   ``logger.exception`` / ``logger.critical`` call in ``engine.py``.
   If the ``extra={}`` payload references ``model_name``, the test
   FAILS — the rule permits ``model_name`` only at ``logger.debug``.

3. **Sibling DEBUG guard** — every non-DEBUG site emitting
   ``model_name_fingerprint`` MUST have a sibling ``logger.debug``
   call with ``model_name`` in the same function so operators can
   recover the raw name at investigation time.

4. **Fingerprint format invariant** — the canonical fingerprint is
   8 lowercase hex chars computed via SHA-256 (NOT Python's
   ``hash()``), matching ``rules/event-payload-classification.md`` §2.

The structural guard is permitted alongside the behavioural guard per
``rules/testing.md`` § "MUST: Behavioral Regression Tests Over
Source-Grep" — source-grep is BLOCKED as the SOLE assertion; combined
with the behavioural test above, the AST invariant is the structural
companion that catches new INFO/WARN/ERROR sites the behavioural
test can't reach without full ``register()`` fixtures.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Canonical fingerprint per rules/observability.md §8 +
# rules/event-payload-classification.md §2 — 8 hex chars of SHA-256.
_NON_DEBUG_LEVELS = {"info", "warning", "error", "exception", "critical"}


def _expected_fingerprint(name: str) -> str:
    """Compute the canonical 8-hex SHA-256 fingerprint."""
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Behavioural guard — exercises the onnx_partial_failure WARN end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_m2_onnx_partial_failure_warn_hashes_model_name(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """WARN site at ``engine.register.onnx_partial_failure`` uses SHA-256 fingerprint."""
    from kailash_ml.bridge import onnx_bridge as onnx_bridge_module

    class _FailedResult:
        success = False
        error_message = "whatever"

    class _StubBridge:
        def export(self, model, framework, output_path):  # noqa: ARG002
            return _FailedResult()

    monkeypatch.setattr(onnx_bridge_module, "OnnxBridge", _StubBridge)

    from kailash_ml.engine import MLEngine

    engine = MLEngine.__new__(MLEngine)
    engine._tenant_id = None

    sentinel = "my-private-credit-model"

    async def _run() -> None:
        with caplog.at_level(logging.DEBUG, logger="kailash_ml.engine"):
            await engine._export_and_save_onnx(
                model=MagicMock(),
                framework="torch",
                name=sentinel,
                version=1,
                format="both",
                artifact_store=MagicMock(),
            )

    asyncio.run(_run())

    warn_records = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING
        and r.getMessage() == "engine.register.onnx_partial_failure"
    ]
    assert len(warn_records) == 1
    warn = warn_records[0]

    # 1. Fingerprint present + matches canonical SHA-256 8-hex form
    assert getattr(warn, "model_name_fingerprint", None) == _expected_fingerprint(
        sentinel
    )
    # 2. Raw model_name NOT in WARN record
    assert sentinel not in repr(vars(warn))
    # 3. No 'model_name' attribute on the WARN record itself
    assert not hasattr(warn, "model_name") or warn.model_name is None

    # 4. Sibling DEBUG carries the raw name
    debug_records = [
        r
        for r in caplog.records
        if r.levelno == logging.DEBUG
        and r.getMessage() == "engine.register.onnx_partial_failure.detail"
    ]
    assert len(debug_records) == 1
    assert debug_records[0].model_name == sentinel


# ---------------------------------------------------------------------------
# Structural guard — AST invariant across every non-DEBUG logger call
# ---------------------------------------------------------------------------


_ENGINE_PY_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "kailash_ml" / "engine.py"
)


def _keys_in_extra(call: ast.Call) -> set[str]:
    """Return the set of string keys in the ``extra=`` kwarg dict of a Call."""
    for kw in call.keywords:
        if kw.arg != "extra":
            continue
        if not isinstance(kw.value, ast.Dict):
            return set()
        return {
            k.value
            for k in kw.value.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
    return set()


def _iter_non_debug_logger_calls(tree: ast.AST) -> list[tuple[str, ast.Call]]:
    """Yield every ``logger.<level>(...)`` call where level ∈ non-DEBUG set.

    Returns tuples of ``(level, call_node)``. ``logger.debug`` is excluded
    per rule §8 — DEBUG is the one safe level for raw model_name.
    """
    out: list[tuple[str, ast.Call]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in _NON_DEBUG_LEVELS:
            continue
        value = func.value
        if isinstance(value, ast.Name) and value.id == "logger":
            out.append((func.attr, node))
    return out


@pytest.mark.regression
def test_m2_ast_invariant_non_debug_sites_never_emit_raw_model_name() -> None:
    """NO ``logger.{info,warning,error,exception,critical}`` in engine.py emits raw model_name.

    AST invariant guard covering every non-DEBUG log level. If any
    ``extra={}`` payload carries the string key ``model_name``, the
    test FAILS. Per ``rules/observability.md`` §8 rule text: "MUST be
    logged at DEBUG level — not WARN or INFO". ERROR / EXCEPTION /
    CRITICAL levels are a fortiori also blocked.

    The M1 + behavioural M2 tests above prove the fix WORKS end-to-end
    for the WARN site at ``engine.register.onnx_partial_failure``; this
    AST guard prevents NEW non-DEBUG sites at any level from slipping
    through.
    """
    assert _ENGINE_PY_PATH.is_file(), f"engine.py not found at {_ENGINE_PY_PATH}"
    tree = ast.parse(_ENGINE_PY_PATH.read_text())

    violations: list[str] = []
    checked = 0
    for level, call in _iter_non_debug_logger_calls(tree):
        extra_keys = _keys_in_extra(call)
        if "model_name" in extra_keys:
            checked += 1
            violations.append(
                f"engine.py:{call.lineno} — logger.{level}(...) emits "
                f"'model_name' in extra={{}}; per observability §8 this "
                f"MUST move to logger.debug OR be replaced by "
                f"'model_name_fingerprint'. extra keys: {sorted(extra_keys)}"
            )

    assert (
        not violations
    ), "Found non-DEBUG log sites that leak raw model_name:\n  " + "\n  ".join(
        violations
    )


@pytest.mark.regression
def test_m2_ast_invariant_fingerprint_sites_have_debug_sibling() -> None:
    """Every non-DEBUG site emitting ``model_name_fingerprint`` has a DEBUG sibling.

    The partition contract is: INFO/WARN/ERROR carries the fingerprint
    for the operational signal; DEBUG carries the raw model_name for
    investigation. A fingerprint non-DEBUG site with no DEBUG sibling
    means operators cannot recover the model_name even when they
    enable DEBUG — the audit trail is broken.

    This guard iterates every non-DEBUG site emitting
    ``model_name_fingerprint`` and asserts a matching
    ``logger.debug(<event>.detail, ...)`` appears within the same
    function.
    """
    assert _ENGINE_PY_PATH.is_file()
    tree = ast.parse(_ENGINE_PY_PATH.read_text())

    non_debug_events: list[tuple[str, int, str, str]] = (
        []
    )  # (event, lineno, func, level)
    debug_events: list[tuple[str, int, str]] = []  # (event, lineno, func)

    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for level, call in _iter_non_debug_logger_calls(func):
            if "model_name_fingerprint" not in _keys_in_extra(call):
                continue
            if not call.args or not isinstance(call.args[0], ast.Constant):
                continue
            event = call.args[0].value
            non_debug_events.append((event, call.lineno, func.name, level))

        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not (isinstance(fn, ast.Attribute) and fn.attr == "debug"):
                continue
            if not (isinstance(fn.value, ast.Name) and fn.value.id == "logger"):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            event = node.args[0].value
            debug_events.append((event, node.lineno, func.name))

    missing_debug_sibling: list[str] = []
    for evt, lineno, func_name, level in non_debug_events:
        expected_detail = f"{evt}.detail"
        found = any(
            dbg_event == expected_detail and dbg_func == func_name
            for dbg_event, _dbg_line, dbg_func in debug_events
        )
        if not found:
            missing_debug_sibling.append(
                f"engine.py:{lineno} func={func_name!r} level={level} — "
                f"'{evt}' has no DEBUG sibling '{expected_detail}'"
            )

    assert not missing_debug_sibling, (
        "Non-DEBUG sites with model_name_fingerprint but no DEBUG sibling "
        "(operators cannot recover the raw model_name even at DEBUG):\n  "
        + "\n  ".join(missing_debug_sibling)
    )
    # Sanity: this codebase MUST have at least one such site —
    # otherwise the invariant guard is vacuously true.
    assert non_debug_events, (
        "No non-DEBUG sites with model_name_fingerprint found in engine.py — "
        "either the fingerprint fix was reverted or the file path is wrong."
    )


@pytest.mark.regression
def test_m2_fingerprint_format_is_8_hex_sha256() -> None:
    """The canonical fingerprint is 8 lowercase hex chars of SHA-256.

    Per ``rules/event-payload-classification.md`` §2 the cross-SDK
    contract is ``sha256:XXXXXXXX`` (prefix + 8 hex). For log-surface
    hygiene per ``rules/observability.md`` §8, the bare 8-hex form is
    used (no prefix — the field name already carries ``_fingerprint``
    suffix as the type signal).

    Python's built-in ``hash()`` is PYTHONHASHSEED-randomized — the
    same raw ``model_name`` produces different fingerprints across
    processes, which defeats cross-process log aggregator correlation.
    SHA-256 is deterministic across processes AND cross-SDK.
    """
    # 1. Format is 8 lowercase hex chars
    for name in ("a", "short", "a-very-long-model-name-indeed", "unicode-café"):
        fp = _expected_fingerprint(name)
        assert len(fp) == 8, f"fingerprint({name!r}) = {fp!r} (expected 8 chars)"
        assert all(
            c in "0123456789abcdef" for c in fp
        ), f"non-hex char in fingerprint({name!r}) = {fp!r}"

    # 2. Deterministic: same input → same output across calls.
    assert _expected_fingerprint("foo") == _expected_fingerprint("foo")
    # 3. Matches the helper in engine.py (stable contract).
    from kailash_ml.engine import _hash_model_name

    assert _hash_model_name("foo") == _expected_fingerprint("foo")
    assert _hash_model_name("my-private-credit-model") == _expected_fingerprint(
        "my-private-credit-model"
    )


@pytest.mark.regression
def test_m2_all_seven_non_debug_sites_in_engine_carry_fingerprint() -> None:
    """Seven distinct engine.py sites MUST emit model_name_fingerprint.

    Documented scope of the M2 fix — a future refactor that removes
    any of these sites (or stops hashing) fails here loudly. Sites:

    - evaluate.ok                           (INFO)
    - evaluate.drift.no_monitor_configured  (INFO)
    - evaluate.drift.no_reference           (INFO)
    - engine.register.error                 (ERROR via logger.exception)
    - engine.register.ok                    (INFO)
    - engine.register.audit_write_failed    (WARN)
    - engine.register.onnx_partial_failure  (WARN)
    """
    assert _ENGINE_PY_PATH.is_file()
    tree = ast.parse(_ENGINE_PY_PATH.read_text())

    events_with_fingerprint: set[str] = set()
    for _level, call in _iter_non_debug_logger_calls(tree):
        if "model_name_fingerprint" not in _keys_in_extra(call):
            continue
        if not call.args or not isinstance(call.args[0], ast.Constant):
            continue
        events_with_fingerprint.add(call.args[0].value)

    expected_events = {
        "evaluate.ok",
        "evaluate.drift.no_monitor_configured",
        "evaluate.drift.no_reference",
        "engine.register.error",
        "engine.register.ok",
        "engine.register.audit_write_failed",
        "engine.register.onnx_partial_failure",
    }
    missing = expected_events - events_with_fingerprint
    assert not missing, (
        f"Expected fingerprint-emitting events missing from engine.py: "
        f"{sorted(missing)}. Found: {sorted(events_with_fingerprint)}"
    )
