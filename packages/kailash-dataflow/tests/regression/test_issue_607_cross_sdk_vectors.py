"""Regression test for issue #607 — cross-SDK byte-shape vectors.

The fixture
``packages/kailash-dataflow/tests/fixtures/security_definer_vectors.json``
is the cross-SDK byte-shape contract for
:class:`SecurityDefinerBuilder`. Both kailash-py and
``esperie-enterprise/kailash-rs`` MUST produce byte-identical SQL when
fed the same builder chain.

This file loads each vector and asserts the emitted SQL matches the
``expected`` array exactly (modulo no whitespace normalization). If
either SDK drifts, the corresponding test fails loudly and the
diverging line surfaces in the diff.

See ``rules/cross-sdk-inspection.md`` MUST Rule 3 (EATP D6 compliance)
and MUST Rule 3a (structural API-divergence disposition) for the
discipline this test enforces.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from dataflow.migration import SecurityDefinerBuilder

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "security_definer_vectors.json"
)


def _load_vectors() -> List[Dict[str, Any]]:
    """Load the cross-SDK fixture once at module import."""
    with _FIXTURE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data["vectors"]


def _build_from_vector(spec: Dict[str, Any]) -> SecurityDefinerBuilder:
    """Reconstruct a builder from a JSON vector spec."""
    b = SecurityDefinerBuilder(spec["function_name"])
    b = b.search_path(spec["search_path"])
    b = b.authenticator_role(spec["authenticator_role"])
    b = b.user_table(spec["user_table"])
    b = b.password_column(spec["password_column"])
    if "tenant_column" in spec:
        b = b.tenant_column(spec["tenant_column"])
    if "primary_lookup_column" in spec:
        b = b.primary_lookup_column(spec["primary_lookup_column"])
    if "active_column" in spec:
        b = b.active_column(spec["active_column"])
    for name, pg_type in spec["params"]:
        b = b.param(name, pg_type)
    for name, pg_type in spec["return_columns"]:
        b = b.return_column(name, pg_type)
    return b


_VECTORS = _load_vectors()


@pytest.mark.regression
@pytest.mark.parametrize(
    "vector",
    _VECTORS,
    ids=[v["name"] for v in _VECTORS],
)
def test_issue_607_cross_sdk_byte_shape(vector: Dict[str, Any]) -> None:
    """Each fixture vector MUST produce byte-identical SQL across SDKs."""
    stmts = _build_from_vector(vector["builder"]).build()
    expected = vector["expected"]
    assert len(stmts) == len(expected), (
        f"vector {vector['name']!r}: builder emitted {len(stmts)} statements, "
        f"fixture expects {len(expected)}"
    )
    for i, (actual, want) in enumerate(zip(stmts, expected)):
        assert actual == want, (
            f"vector {vector['name']!r} stmt[{i}] drift:\n"
            f"--- actual ---\n{actual}\n--- expected ---\n{want}\n"
        )


@pytest.mark.regression
def test_issue_607_fixture_vectors_present() -> None:
    """At least one vector MUST be present — guards against empty fixture
    files silently making the cross-SDK contract an empty contract."""
    assert len(_VECTORS) >= 1
    # Pin the canonical multi-tenant vector by name so a future fixture
    # edit cannot rename it without intent.
    names = [v["name"] for v in _VECTORS]
    assert "canonical_multi_tenant" in names, (
        "fixture MUST retain the canonical_multi_tenant vector — "
        "this is the byte-shape kailash-rs's Tier 1 snapshot test pins"
    )
