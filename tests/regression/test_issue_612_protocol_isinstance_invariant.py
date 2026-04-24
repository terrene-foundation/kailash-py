# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Structural invariant — protocol classes introduced by #612 MUST NOT be
used in auth-gate ``isinstance`` checks.

Origin: sec-rev-612 MEDIUM condition on PR #616 (fix/issue-612-cyclic-imports).
Cyclic-import refactor introduced three ``@runtime_checkable`` Protocols:

- ``DataFlowProtocol`` in ``dataflow/_types.py``
- ``SignatureCompositionProtocol`` in ``kaizen/signatures/_types.py``
- ``InferenceServerProtocol`` in ``kailash_ml/serving/_types.py``

All three are structural-duck-typing Protocols. If a future session
replaces a concrete ``isinstance(db, DataFlow)`` admission gate with
``isinstance(db, DataFlowProtocol)``, any object exposing the same
duck-typed shape passes — an auth-bypass at the orphan-detection
boundary (see ``rules/orphan-detection.md`` + ``rules/cross-sdk-inspection.md``
§ 3a structural API-divergence disposition).

This test pins the invariant: protocol classes MUST NOT appear inside
``isinstance(...)`` calls in production code (src/ + packages/*/src/).

Tests/ is explicitly allowed to check protocol conformance via
``isinstance`` — that's the documented intent.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The three Protocols introduced by PR #616 (#612 fix).
_PROTOCOL_NAMES = (
    "DataFlowProtocol",
    "SignatureCompositionProtocol",
    "InferenceServerProtocol",
)

# Production trees — tests/ explicitly excluded (those may legitimately
# assert protocol conformance via isinstance).
_PRODUCTION_TREES = (
    "src",
    "packages/kailash/src",
    "packages/kailash-dataflow/src",
    "packages/kailash-kaizen/src",
    "packages/kailash-mcp/src",
    "packages/kailash-ml/src",
    "packages/kailash-align/src",
    "packages/kailash-nexus/src",
    "packages/kailash-pact/src",
    "packages/kaizen-agents/src",
)


@pytest.mark.regression
@pytest.mark.parametrize("protocol_name", _PROTOCOL_NAMES)
def test_protocol_not_used_in_production_isinstance(protocol_name: str) -> None:
    """Protocol classes MUST NOT appear in ``isinstance(..., <Proto>)`` in production code.

    Per sec-rev-612 MEDIUM: structural-duck-typing protocols are unsafe
    admission gates. Keep ``isinstance`` against the concrete class.
    """
    # Match ``isinstance(X, <Proto>)`` with optional whitespace and trailing
    # ``)`` or ``,`` (handles multi-class isinstance). Non-greedy any-chars
    # between ``(`` and the Protocol name.
    pattern = re.compile(
        rf"isinstance\s*\([^,)]+,\s*[^)]*\b{re.escape(protocol_name)}\b"
    )

    offenders: list[str] = []
    for tree in _PRODUCTION_TREES:
        tree_path = _REPO_ROOT / tree
        if not tree_path.is_dir():
            continue
        for py_file in tree_path.rglob("*.py"):
            # Skip the protocol definition site itself.
            if py_file.name == "_types.py":
                continue
            try:
                text = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for match in pattern.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                rel = py_file.relative_to(_REPO_ROOT)
                offenders.append(f"{rel}:{line_no}: {match.group(0)}")

    assert not offenders, (
        f"Found {len(offenders)} production isinstance({protocol_name}) call(s). "
        f"Use the concrete class, not the Protocol — Protocols are "
        f"structural-duck-typing gates and pass for any duck-typed object. "
        f"See sec-rev-612 MEDIUM on PR #616.\n"
        + "\n".join(f"  - {off}" for off in offenders)
    )
