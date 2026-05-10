# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Structural invariant test — every history_store / subscriber-error WARN+ emission
hashes record-level identifiers (#876 C-1 + same-class follow-on).

Per `rules/observability.md` Rule 8 + `specs/core-runtime.md` §4.7.1:
record-level identifier fields (`run_id`, `workflow_id`) at WARN+ level
MUST be hashed via `_hash_short` (8-char SHA-256 prefix); the field name
ends in `_hash` to signal the hashing.

This test is the structural defense recommended by `/redteam` Round 1
security-reviewer (LOW finding): without an invariant gate, a sibling
emission can drift back to raw-identifier shape and the next reviewer
cycle has to re-discover it.

The test is AST-walking, not regex — per `rules/probe-driven-verification.md`
MUST-3, structural probes (AST) are correct for this kind of literal
property check. The probe asks the question directly: "is the dict-literal
extra= argument keyed with a raw record-level identifier?"
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Files in scope: every emission named history_store.* OR durable.on_node_complete.*
# (the subscriber chain that handles record_event events).
_FILES_IN_SCOPE = [
    "src/kailash/infrastructure/history_store.py",
    "src/kailash/runtime/durable.py",
]

# Record-level identifiers that MUST be hashed at WARN+. The ALLOWLIST below
# is what the spec contract permits raw at WARN+ (counts, structural fields,
# numeric sequences, hashed siblings, mode tags).
_RAW_IDENTIFIER_KEYS = {"run_id", "workflow_id"}

# Allowlist (raw at WARN+ is OK):
# - counts / numeric / structural fields
# - already-hashed siblings (the *_hash variants)
# - mode tags / structural strings
_ALLOWED_RAW_KEYS = {
    "attempted",
    "failed",
    "cap",
    "count",
    "deleted",
    "evicted",
    "event_seq",  # numeric sequence per spec §4.7.1 carve-out
    "callback",
    "error_type",
    "mode",
    "first_failure",
    "first_error",
    "node_id_hash",
    "run_id_hash",
    "workflow_id_hash",
    "tenant_id_hash",
    "sample_run_id_hash",
    "field_hash",
    "sweep_interval_seconds",
    "elapsed_seconds",
    "deleted_runs",
    "deleted_events",
    "before_ts",  # ISO-8601 cutoff timestamp; structural, not record-level
}


def _project_root() -> Path:
    """Project root resolves to the worktree the test runs in."""
    return Path(__file__).resolve().parents[2]


def _enumerate_warn_info_emissions(file_path: Path) -> list[tuple[int, str, set[str]]]:
    """Return (lineno, event_name, extra_keys) for every WARN/INFO emission.

    Walks the AST for `logger.warning(...)` and `logger.info(...)` calls,
    extracts the event-name string (positional arg 0), and the keys of the
    `extra=` dict-literal kwarg.

    Emissions whose event-name does NOT start with `history_store.` or
    `durable.on_node_complete.` are skipped — the contract scope is
    audit-log emission paths, not the broader WARN+ surface.
    """
    source = file_path.read_text()
    tree = ast.parse(source, filename=str(file_path))

    emissions: list[tuple[int, str, set[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # logger.warning(...) / logger.info(...) shape: Call(func=Attribute)
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"warning", "info"}:
            continue
        # Positional arg 0 must be a string literal (the event name).
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        event_name = node.args[0].value
        if not isinstance(event_name, str):
            continue
        # Scope: history_store.* OR durable.on_node_complete.*
        if not (
            event_name.startswith("history_store.")
            or event_name.startswith("durable.on_node_complete.")
        ):
            continue
        # Find extra= kwarg (dict literal).
        extra_keys: set[str] = set()
        for kw in node.keywords:
            if kw.arg == "extra" and isinstance(kw.value, ast.Dict):
                for key_node in kw.value.keys:
                    if isinstance(key_node, ast.Constant) and isinstance(
                        key_node.value, str
                    ):
                        extra_keys.add(key_node.value)
        emissions.append((node.lineno, event_name, extra_keys))

    return emissions


@pytest.mark.parametrize("rel_path", _FILES_IN_SCOPE)
def test_history_store_log_emissions_hash_record_level_identifiers(rel_path):
    """Every WARN/INFO emission in scope MUST NOT include raw record-level IDs.

    Structural defense per `rules/observability.md` Rule 8 +
    `specs/core-runtime.md` §4.7.1. Field names listed in
    `_RAW_IDENTIFIER_KEYS` MUST NOT appear in the `extra=` dict; the
    `*_hash` variants are required instead.

    Also asserts every emission's `extra=` keys are in the allowlist —
    catches future emissions that introduce new schema-revealing field
    names without updating either the spec or this test.
    """
    file_path = _project_root() / rel_path
    assert file_path.exists(), f"file in scope must exist: {rel_path}"

    emissions = _enumerate_warn_info_emissions(file_path)
    assert (
        emissions
    ), f"no in-scope emissions found in {rel_path}; the test scope may be wrong"

    raw_violations: list[tuple[str, str, str, int]] = []
    unknown_keys: list[tuple[str, str, str, int]] = []
    for lineno, event_name, extra_keys in emissions:
        for key in extra_keys:
            if key in _RAW_IDENTIFIER_KEYS:
                raw_violations.append((rel_path, event_name, key, lineno))
            elif key not in _ALLOWED_RAW_KEYS:
                unknown_keys.append((rel_path, event_name, key, lineno))

    if raw_violations:
        msg = "\n".join(
            f"  {p}:{ln} event={e!r} key={k!r} (raw record-level identifier)"
            for p, e, k, ln in raw_violations
        )
        pytest.fail(
            f"raw record-level identifiers in WARN/INFO emission "
            f"(observability.md Rule 8 + specs/core-runtime.md §4.7.1):\n{msg}\n\n"
            f"Replace with hashed sibling (e.g. 'run_id' -> 'run_id_hash' "
            f"via _hash_short)."
        )

    if unknown_keys:
        msg = "\n".join(
            f"  {p}:{ln} event={e!r} key={k!r} (not in allowlist)"
            for p, e, k, ln in unknown_keys
        )
        pytest.fail(
            f"WARN/INFO emission introduces a new schema-revealing field name "
            f"NOT in the test's allowlist:\n{msg}\n\n"
            f"Either (a) update _ALLOWED_RAW_KEYS in this test if the new key "
            f"is structural / numeric / pre-hashed, OR (b) hash the field via "
            f"_hash_short and add the *_hash variant to the allowlist."
        )
