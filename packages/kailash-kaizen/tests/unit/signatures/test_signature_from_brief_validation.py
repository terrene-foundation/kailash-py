# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 regression tests for SEC-2 — Kaizen ``signature_from_brief``
class-name + field-name validation.

Closes the SEC-2 finding at
``workspaces/from-brief-1125/04-validate/round-02-security.md:55-77``.

The validators ``_validate_class_name`` and ``_validate_triples`` are
the typed gate between the LLM's emitted plan and ``type(name, bases,
ns)``-mediated class construction. Before SEC-2, the gate used only
``str.isidentifier()`` which accepts:

  - Python keywords (``"class"``, ``"True"``)
  - Dunder names (``"__init_subclass__"``)
  - Unicode identifiers (``"Modèl"``)

Each subverts ``SignatureMeta``. The SEC-2 fix adds a regex (ASCII-only)
+ keyword denylist + dunder denylist on top of ``isidentifier()``.

Per ``rules/probe-driven-verification.md`` Rule 3 these are structural
probes (the assertion is "the validator raised the typed error") — no
LLM judge required, deterministic.
"""

from __future__ import annotations

import pytest

from kailash._from_brief.exceptions import BriefInterpretationError
from kaizen.signatures.from_brief import (
    _DUNDER_DENYLIST,
    _validate_class_name,
    _validate_triples,
)


# ---------------------------------------------------------------------------
# _validate_class_name — SEC-2 regression
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_class_name_rejects_python_keyword_class() -> None:
    """SEC-2: ``class`` is a Python keyword; ``isidentifier()`` says yes
    but the strict gate MUST reject it."""
    with pytest.raises(BriefInterpretationError) as exc_info:
        _validate_class_name("class")
    assert exc_info.value.malformed


@pytest.mark.regression
def test_class_name_rejects_python_keyword_true() -> None:
    """SEC-2: ``True`` is a Python keyword (literal); ``isidentifier()``
    returns True but the strict gate MUST reject it."""
    with pytest.raises(BriefInterpretationError) as exc_info:
        _validate_class_name("True")
    assert exc_info.value.malformed


@pytest.mark.regression
def test_class_name_rejects_dunder_init_subclass() -> None:
    """SEC-2: ``__init_subclass__`` is a Python data-model slot;
    ``isidentifier()`` accepts it but the strict gate MUST reject."""
    with pytest.raises(BriefInterpretationError) as exc_info:
        _validate_class_name("__init_subclass__")
    assert exc_info.value.malformed
    # Sanity: the denylist constant covers it.
    assert "__init_subclass__" in _DUNDER_DENYLIST


@pytest.mark.regression
def test_class_name_rejects_lowercase_leading_letter() -> None:
    """SEC-2: class names MUST start with an uppercase letter
    (the strict regex enforces this)."""
    with pytest.raises(BriefInterpretationError) as exc_info:
        _validate_class_name("lowercase_class_name")
    assert exc_info.value.malformed


@pytest.mark.regression
def test_class_name_rejects_unicode_identifier() -> None:
    """SEC-2: unicode-identifier ``Modèl`` passes ``isidentifier()`` but
    the ASCII-only regex MUST reject it. Unicode-collision attacks
    (``Modèl`` vs Cyrillic-equivalent) are blocked at this gate."""
    with pytest.raises(BriefInterpretationError) as exc_info:
        _validate_class_name("Modèl")
    assert exc_info.value.malformed


@pytest.mark.regression
def test_class_name_accepts_canonical_QASignature() -> None:
    """Regression guard: legitimate class names continue to pass after
    the SEC-2 tightening."""
    # Should NOT raise.
    _validate_class_name("QASignature")


# ---------------------------------------------------------------------------
# _validate_triples (field names) — SEC-2 regression
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_field_name_rejects_python_keyword_class() -> None:
    """SEC-2: field name ``class`` is a Python keyword; the strict gate
    MUST reject."""
    triples = [["class", "str", "A field"]]
    with pytest.raises(BriefInterpretationError) as exc_info:
        _validate_triples(triples, field_kind="input")
    assert exc_info.value.malformed


@pytest.mark.regression
def test_field_name_rejects_dunder_class() -> None:
    """SEC-2: field name ``__class__`` collides with a Python data-model
    slot; the strict gate MUST reject."""
    triples = [["__class__", "str", "A field"]]
    with pytest.raises(BriefInterpretationError) as exc_info:
        _validate_triples(triples, field_kind="output")
    assert exc_info.value.malformed
    assert "__class__" in _DUNDER_DENYLIST


@pytest.mark.regression
def test_field_name_accepts_canonical_question() -> None:
    """Regression guard: legitimate field names continue to pass after
    the SEC-2 tightening."""
    triples = [["question", "str", "User's question text"]]
    validated = _validate_triples(triples, field_kind="input")
    assert validated == [("question", "str", "User's question text")]
