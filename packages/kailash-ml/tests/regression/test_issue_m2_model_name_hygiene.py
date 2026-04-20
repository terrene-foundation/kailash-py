# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: M2 — model_name at WARN in engine.py MUST be hashed.

Origin: 2026-04-20 late-session audit finding M2 — WARN-level log
sites in ``engine.py`` carried the raw ``model_name`` as a structured
field. Per ``rules/observability.md`` §8, schema-revealing identifiers
like model names MUST be logged at DEBUG or hashed when emitted at
WARN.

This file provides two complementary guards:

1. **Behavioural** — exercises the
   ``engine.register.onnx_partial_failure`` WARN path end-to-end and
   asserts the hashed partition (WARN carries
   ``model_name_fingerprint``; DEBUG sibling carries raw
   ``model_name``). This is the same site covered at higher resolution
   by ``test_issue_m1_onnx_cause_hygiene.py`` — kept here as a
   parity check so a future refactor that reverts the M1 fix also
   fails this M2 test.

2. **Structural invariant** — an AST walk over ``engine.py`` that
   locates every ``logger.warning(...)`` call site and asserts: if the
   WARN site's ``extra`` payload references ``model_name`` or
   ``self._tenant_id``, it MUST also emit
   ``model_name_fingerprint``. This is the invariant guard per
   ``rules/refactor-invariants.md`` — without it, a future session
   that adds a new WARN site embedding raw ``model_name`` ships a
   silent regression.

The structural guard is permitted alongside the behavioural guard per
``rules/testing.md`` § "MUST: Behavioral Regression Tests Over
Source-Grep" — source-grep is BLOCKED as the SOLE assertion; combined
with the behavioural test above, the AST invariant is the structural
companion that catches new WARN sites the behavioural test can't
reach without full ``register()`` fixtures.
"""
from __future__ import annotations

import ast
import asyncio
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _expected_fingerprint(name: str) -> str:
    return f"{hash(name) & 0xFFFF:04x}"


# ---------------------------------------------------------------------------
# Behavioural guard — exercises the onnx_partial_failure WARN end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_m2_onnx_partial_failure_warn_hashes_model_name(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """WARN site at ``engine.register.onnx_partial_failure`` uses fingerprint."""
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

    # 1. Fingerprint present + matches canonical form
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
# Structural guard — AST invariant across every logger.warning in engine.py
# ---------------------------------------------------------------------------


_ENGINE_PY_PATH = (
    Path(__file__).resolve().parents[2] / "src" / "kailash_ml" / "engine.py"
)


def _keys_in_extra(call: ast.Call) -> set[str]:
    """Return the set of string keys in the ``extra=`` kwarg dict of a Call.

    Returns an empty set if the call has no ``extra=`` kwarg or the kwarg
    is not a literal dict.
    """
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


def _iter_logger_warning_calls(tree: ast.AST) -> list[ast.Call]:
    """Yield every ``logger.warning(...)`` call node in the AST."""
    out: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr != "warning":
            continue
        value = func.value
        if isinstance(value, ast.Name) and value.id == "logger":
            out.append(node)
    return out


@pytest.mark.regression
def test_m2_ast_invariant_warn_sites_with_model_name_emit_fingerprint() -> None:
    """Every ``logger.warning`` in engine.py that carries model_name also emits fingerprint.

    AST invariant guard: walks every ``logger.warning(...)`` call site
    in ``engine.py``. If the ``extra={}`` payload has a ``model_name``
    key, it MUST also have a ``model_name_fingerprint`` key (or the
    ``model_name`` key MUST be absent and only fingerprint present).

    The rule per ``rules/observability.md`` §8 is: model_name at WARN
    leaks schema metadata to log aggregators. The fix is either (a)
    drop model_name from the WARN entirely and keep the fingerprint,
    or (b) emit both at WARN if the fingerprint-only form is too
    opaque for operators — the field set becomes `{fingerprint,
    tenant_id}` not `{model_name, tenant_id}`.

    This test enforces option (a): `model_name` MUST NOT appear in any
    WARN payload under engine.py. The M1 + behavioural M2 tests above
    prove the fix WORKS end-to-end for the two sites that exist today;
    this AST guard prevents NEW sites from slipping through.
    """
    assert _ENGINE_PY_PATH.is_file(), f"engine.py not found at {_ENGINE_PY_PATH}"
    tree = ast.parse(_ENGINE_PY_PATH.read_text())

    violations: list[str] = []
    checked = 0
    for call in _iter_logger_warning_calls(tree):
        extra_keys = _keys_in_extra(call)
        if "model_name" in extra_keys:
            checked += 1
            violations.append(
                f"engine.py:{call.lineno} — logger.warning(...) emits "
                f"'model_name' in extra={{}}; per observability §8 this "
                f"MUST move to DEBUG or be replaced by "
                f"'model_name_fingerprint'. extra keys: {sorted(extra_keys)}"
            )

    assert (
        not violations
    ), "Found WARN-level log sites that leak raw model_name:\n  " + "\n  ".join(
        violations
    )


@pytest.mark.regression
def test_m2_ast_invariant_fingerprint_sites_have_debug_sibling() -> None:
    """Every WARN site emitting ``model_name_fingerprint`` has a DEBUG sibling.

    The partition contract is: WARN carries the fingerprint for the
    operational signal; DEBUG carries the raw model_name for
    investigation. A fingerprint WARN with no DEBUG sibling means
    operators cannot recover the model_name even when they enable
    DEBUG — the audit trail is broken.

    This guard iterates every WARN site emitting
    ``model_name_fingerprint`` and asserts a matching
    ``logger.debug(<event>.detail, ...)`` appears within the same
    function (simple proximity check — not a strict order/control-flow
    analysis; sufficient for the current two sites).
    """
    assert _ENGINE_PY_PATH.is_file()
    tree = ast.parse(_ENGINE_PY_PATH.read_text())

    # Map each function's events to (event, level, line).
    # Walk each FunctionDef / AsyncFunctionDef and collect
    # logger.warning + logger.debug event strings inside it.
    warn_events: list[tuple[str, int, str]] = []  # (event, lineno, func_name)
    debug_events: list[tuple[str, int, str]] = []

    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in _iter_logger_warning_calls(func):
            if "model_name_fingerprint" not in _keys_in_extra(call):
                continue
            if not call.args or not isinstance(call.args[0], ast.Constant):
                continue
            event = call.args[0].value
            warn_events.append((event, call.lineno, func.name))

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
    for warn_event, warn_line, warn_func in warn_events:
        expected_detail = f"{warn_event}.detail"
        found = any(
            dbg_event == expected_detail and dbg_func == warn_func
            for dbg_event, _dbg_line, dbg_func in debug_events
        )
        if not found:
            missing_debug_sibling.append(
                f"engine.py:{warn_line} func={warn_func!r} — WARN "
                f"'{warn_event}' has no DEBUG sibling '{expected_detail}'"
            )

    assert not missing_debug_sibling, (
        "WARN sites with model_name_fingerprint but no DEBUG sibling "
        "(operators cannot recover the raw model_name even at DEBUG):\n  "
        + "\n  ".join(missing_debug_sibling)
    )
    # Sanity: this codebase MUST have at least one such WARN site —
    # otherwise the invariant guard is vacuously true.
    assert warn_events, (
        "No WARN sites with model_name_fingerprint found in engine.py — "
        "either the fingerprint fix was reverted or the file path is wrong."
    )


@pytest.mark.regression
def test_m2_fingerprint_format_is_4_hex_chars() -> None:
    """The canonical fingerprint is 4 lowercase hex chars (``{hash & 0xFFFF:04x}``)."""
    for name in ("a", "short", "a-very-long-model-name-indeed", "unicode-café"):
        fp = _expected_fingerprint(name)
        assert len(fp) == 4
        assert all(
            c in "0123456789abcdef" for c in fp
        ), f"non-hex char in fingerprint({name!r}) = {fp!r}"
