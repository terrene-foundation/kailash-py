# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: GH issue #701 part 2 — kind aliases + cross-package dispatch.

Before this fix, ``_wrappers.py:diagnose()`` accepted four ``kind``
literals (``alignment``, ``llm``, ``agent``, ``clustering``) without
dispatch branches — they silently fell through to ``DLDiagnostics``.
And the colloquial aliases ``classifier`` / ``regressor`` were rejected
with ``ValueError`` despite mapping 1:1 to the canonical
``classical_classifier`` / ``classical_regressor`` literals.

Shard S3b lands the fix:

  1. ``kind="classifier"`` aliases ``classical_classifier``.
  2. ``kind="regressor"`` aliases ``classical_regressor``.
  3. ``kind="alignment"`` dispatches to
     ``kailash_align.diagnostics.alignment.AlignmentDiagnostics`` with
     loud ImportError + install hint when kailash-align missing.
  4. ``kind="llm"`` dispatches to
     ``kaizen.judges.llm_diagnostics.LLMDiagnostics`` with the same
     try/except pattern.
  5. ``kind="agent"`` dispatches to
     ``kaizen.observability.agent_diagnostics.AgentDiagnostics``.
  6. ``kind="clustering"`` is removed from the accepted-literals list
     and rejects with an explicit "not yet implemented" message.

Per ``rules/testing.md``:

  * Tests 1, 2, 4, 5 are Tier-2 (NO mocking; real sibling classes via
    ``pytest.importorskip`` to skip cleanly when extras absent).
  * Test 3 is Tier-1 unit (simulates missing kailash-align via
    ``monkeypatch.setitem(sys.modules, ...)``); the assertion is
    behavioural — call the function and assert the typed exception
    fires with the install hint visible.
"""

from __future__ import annotations

import sys

import pytest


@pytest.mark.regression
@pytest.mark.integration
def test_diagnose_kind_classifier_alias_dispatches_to_classical_classifier() -> None:
    """``kind="classifier"`` aliases ``classical_classifier`` end-to-end.

    Pre-fix the alias raised ``ValueError`` at literal validation. Post-fix
    the alias map normalises before validation and the call returns a
    classical-classifier diagnostic — same return shape as
    ``kind="classical_classifier"`` directly.
    """
    sklearn = pytest.importorskip("sklearn")  # noqa: F841
    import numpy as np
    from kailash_ml import diagnose
    from sklearn.linear_model import LogisticRegression

    # Tiny deterministic dataset — Tier-2 NO mocking, real sklearn.
    rng = np.random.default_rng(seed=0)
    X = rng.standard_normal((40, 4))
    y = (X[:, 0] > 0).astype(int)
    model = LogisticRegression().fit(X, y)

    # The alias path.
    via_alias = diagnose(model, kind="classifier", data=(X, y))
    # The canonical path.
    via_canonical = diagnose(model, kind="classical_classifier", data=(X, y))

    # Both paths produce the same result type (classical-classifier
    # diagnostic). The exact type comes from
    # ``kailash_ml._wrappers.diagnose_classifier`` — we assert type
    # parity, not internals.
    assert type(via_alias) is type(via_canonical), (
        "kind='classifier' alias diverged from kind='classical_classifier' "
        f"(alias={type(via_alias)!r} canonical={type(via_canonical)!r})"
    )


@pytest.mark.regression
@pytest.mark.integration
def test_diagnose_kind_regressor_alias_dispatches_to_classical_regressor() -> None:
    """``kind="regressor"`` aliases ``classical_regressor`` end-to-end."""
    sklearn = pytest.importorskip("sklearn")  # noqa: F841
    import numpy as np
    from kailash_ml import diagnose
    from sklearn.linear_model import LinearRegression

    rng = np.random.default_rng(seed=0)
    X = rng.standard_normal((40, 4))
    y = X[:, 0] * 2 + rng.standard_normal(40) * 0.1
    model = LinearRegression().fit(X, y)

    via_alias = diagnose(model, kind="regressor", data=(X, y))
    via_canonical = diagnose(model, kind="classical_regressor", data=(X, y))

    assert type(via_alias) is type(via_canonical), (
        "kind='regressor' alias diverged from kind='classical_regressor' "
        f"(alias={type(via_alias)!r} canonical={type(via_canonical)!r})"
    )


@pytest.mark.regression
def test_diagnose_kind_alignment_raises_importerror_when_kailash_align_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``kind="alignment"`` raises ImportError with install hint when dep missing.

    Tier-1 unit test. Simulates the absent-dep state via
    ``monkeypatch.setitem(sys.modules, ...)`` so the test runs even on
    a machine where kailash-align IS installed. The assertion is
    behavioural — call ``diagnose`` and verify the typed exception
    fires with the install hint visible to the user.

    Per ``rules/dependencies.md`` § BLOCKED Anti-Patterns: missing
    optional dep MUST raise loudly at the call site; silent fallback
    is BLOCKED. The error message MUST name the install command so
    users can recover without consulting docs.
    """
    from kailash_ml import diagnose

    # Pre-emptively poison the sub-modules touched by the import chain
    # ``from kailash_align.diagnostics.alignment import AlignmentDiagnostics``.
    # Setting them to ``None`` triggers ``ImportError`` on the first
    # ``from <pkg>.x import y`` per CPython ``_handle_fromlist`` semantics.
    monkeypatch.setitem(sys.modules, "kailash_align", None)
    monkeypatch.setitem(sys.modules, "kailash_align.diagnostics", None)
    monkeypatch.setitem(sys.modules, "kailash_align.diagnostics.alignment", None)

    with pytest.raises(ImportError) as exc_info:
        diagnose("subject_irrelevant", kind="alignment")

    # Behavioural assertion: install hint MUST be in the message so a
    # user reading the traceback can recover.
    assert "kailash-ml[alignment]" in str(exc_info.value), (
        "ImportError message MUST name the install command for #701 "
        f"recovery; got: {exc_info.value!r}"
    )
    assert "kailash-align" in str(exc_info.value), (
        "ImportError message MUST name the missing dep package for "
        f"clarity; got: {exc_info.value!r}"
    )


@pytest.mark.regression
@pytest.mark.integration
def test_diagnose_kind_llm_dispatches_to_kaizen_when_installed(monkeypatch) -> None:
    """``kind="llm"`` dispatches to LLMDiagnostics when kailash-kaizen present.

    Tier-2: skipped cleanly when kailash-kaizen is not installed
    (matches the optional-extras posture in pyproject.toml). When
    present, asserts the dispatched return is the real
    ``LLMDiagnostics`` class — proving the cross-package wiring is
    live, not silently mis-routed to ``DLDiagnostics`` (the pre-fix
    failure mode).
    """
    pytest.importorskip("kaizen.judges.llm_diagnostics")
    # LLMJudge resolves model from .env per rules/env-models.md; tests
    # set a placeholder so construction does not raise. Monkeypatch is
    # acceptable in test scope.
    monkeypatch.setenv("KAIZEN_JUDGE_MODEL", "gpt-4o-mini")
    from kailash_ml import diagnose

    from kaizen.judges.llm_diagnostics import LLMDiagnostics

    diag = diagnose("subject_irrelevant", kind="llm")

    # External assertion: the dispatch produced a REAL LLMDiagnostics
    # instance (NOT a DLDiagnostics — the pre-fix silent-fallthrough
    # target). isinstance check survives subclasses; type identity
    # would be too strict.
    assert isinstance(diag, LLMDiagnostics), (
        "kind='llm' must dispatch to LLMDiagnostics, not silently fall "
        f"through to DLDiagnostics; got {type(diag)!r}"
    )


@pytest.mark.regression
def test_diagnose_kind_clustering_raises_value_error() -> None:
    """``kind="clustering"`` rejects with explicit "not yet implemented".

    Pre-fix, ``clustering`` was accepted by the literal validator but
    had no dispatch branch — silent fall-through to ``DLDiagnostics``,
    a ``rules/zero-tolerance.md`` Rule 2 violation (fake dispatch).

    Post-fix, ``clustering`` is removed from the accepted-literals
    list AND a dedicated branch raises ValueError with a message
    pointing the user at the engine they should use directly. This
    test pins the disposition so a future refactor that re-adds
    ``clustering`` to the accepted set must re-derive whether the
    diagnostic class exists OR keep the explicit-refusal contract.
    """
    from kailash_ml import diagnose

    with pytest.raises(ValueError, match="clustering"):
        diagnose("subject_irrelevant", kind="clustering")

    # Behavioural assertion: the message names the migration path so
    # users hitting this branch know what to do next.
    with pytest.raises(ValueError) as exc_info:
        diagnose("subject_irrelevant", kind="clustering")
    msg = str(exc_info.value)
    assert "not yet implemented" in msg, (
        "ValueError MUST tell the user the dispatch is missing, not "
        f"merely refuse the literal; got: {msg!r}"
    )
