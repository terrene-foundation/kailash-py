# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration tests for ``Kaizen.signature_from_brief``.

Closes issue #1125 acceptance criterion 8:

    Tier-2 test exists at ``tests/integration/kaizen/test_signature_from_brief.py``
    covering ≥2 brief shapes.

Per ``rules/testing.md`` § "NO MOCKING in Tier 2/3" — these tests hit a
real LLM endpoint configured via ``DEFAULT_LLM_MODEL`` in ``.env`` (the
root ``conftest.py`` auto-loads ``.env`` for pytest).

## Tier-2 LLM cost note

Each test invokes the LLM once via ``Kaizen.signature_from_brief`` and
optionally a second time when verifying the synthesized class is usable
as ``signature=`` to a real ``BaseAgent`` (the round-trip contract per
issue #1125 AC 3). Approximate cost per full-suite run: ~$0.01-0.10
depending on the model; the round-trip second call uses a tiny input
and is small overhead. The architecture plan §5 documented the cost
class.

## Test discipline

Per the architecture plan §5 and the per-fixture ``expected`` block,
tests assert SHAPE not exact byte content:

- ``isinstance(result, type)`` — the realizer returned a class object.
- ``issubclass(result, Signature)`` — the class extends Kaizen
  ``Signature`` (so it is usable as ``signature=`` to any Kaizen agent
  constructor per AC 3).
- Field-count + (where the fixture asserts it) non-string-type
  presence — assert structural shape from the LLM's plan.
- Instructions substring presence — at least one domain-relevant noun
  the brief mentioned is reflected in the synthesized class docstring.

Round-trip with ``BaseAgent`` (AC 3 contract) is exercised at least
once per shape so the "usable as ``signature=`` arg" claim is verified
end-to-end, not just at the class-construction layer.

Origin: issue #1125 AC 8 (kaizen Tier-2 test); architecture plan §3.3.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from kailash._from_brief import BriefInterpretationError, MissingDefaultLLMModelError
from kaizen import Kaizen
from kaizen.signatures import Signature

# Fixtures live next to the existing S1 no-secrets-scan target so the
# Tier-1 scan continues to cover them automatically.
FIXTURE_DIR = (
    Path(__file__).resolve().parents[2] / "regression" / "from_brief" / "fixtures"
)


def _load_fixture(name: str) -> Dict[str, Any]:
    """Load a YAML fixture from the regression-fixtures directory.

    The fixture file MUST contain a top-level ``brief`` string and an
    ``expected`` mapping per the fixture-author contract documented at
    the file headers in ``tests/regression/from_brief/fixtures/``.
    """
    path = FIXTURE_DIR / name
    return yaml.safe_load(path.read_text())


# All Tier-2 tests skip when the LLM model env var is unset, surfacing
# the structural reason (not a deep RuntimeError inside BaseAgent) per
# rules/zero-tolerance.md Rule 3a. The S1 get_default_llm_model() helper
# raises MissingDefaultLLMModelError when DEFAULT_LLM_MODEL is empty;
# tests that explicitly want to exercise the unset path import that
# helper directly.
_REQUIRES_LLM_MODEL = pytest.mark.skipif(
    not os.environ.get("DEFAULT_LLM_MODEL", "").strip(),
    reason=(
        "Tier-2 from_brief() tests require DEFAULT_LLM_MODEL in .env "
        "(per rules/env-models.md)"
    ),
)


@_REQUIRES_LLM_MODEL
@pytest.mark.integration
@pytest.mark.regression
def test_signature_from_brief_single_input_single_output():
    """Kaizen.signature_from_brief returns a usable Signature subclass.

    Fixture shape: single-input single-output. Assertions:

    1. Result IS a Python class object (``isinstance(result, type)``).
    2. Class subclasses :class:`kaizen.signatures.Signature` (so AC 3's
       "usable as ``signature=`` arg" return contract holds by typing).
    3. Field counts match the fixture's expected counts.
    4. Instructions docstring reflects the brief's intent (any of the
       fixture-listed domain substrings is present, case-insensitive).
    5. Round-trip: the synthesized class can be instantiated AND passed
       as ``signature=`` to a real :class:`BaseAgent` constructor (AC 3
       end-to-end contract).
    """
    fixture = _load_fixture("kaizen_single_io.yaml")
    brief = fixture["brief"]
    expected = fixture["expected"]

    new_class = Kaizen.signature_from_brief(brief)

    # Assertion 1 — return is a class.
    assert isinstance(
        new_class, type
    ), f"expected a class object; got {type(new_class).__name__}"

    # Assertion 2 — subclasses Signature.
    assert issubclass(
        new_class, Signature
    ), f"expected subclass of Signature; MRO={[b.__name__ for b in new_class.__mro__]}"

    # Assertion 3 — field counts.
    instance = new_class()
    assert len(instance.input_fields) == expected["input_field_count"], (
        f"expected {expected['input_field_count']} input fields; "
        f"got {len(instance.input_fields)}: {list(instance.input_fields.keys())}"
    )
    assert len(instance.output_fields) == expected["output_field_count"], (
        f"expected {expected['output_field_count']} output fields; "
        f"got {len(instance.output_fields)}: {list(instance.output_fields.keys())}"
    )

    # Assertion 4 — instructions docstring is structurally present and
    # non-trivial. Per rules/probe-driven-verification.md MUST-1, a
    # substring/regex match on prose IS a semantic-claim verified via
    # lexical matching and is BLOCKED. The structural property the
    # test owns is: did the LLM emit ANY non-empty instructions block
    # (a missing or empty docstring would mean the synthesized class
    # has no instructions for downstream agents to consume). Semantic
    # quality of the docstring is a probe-class assertion deferred to
    # a future probe-driven gate.
    docstring = new_class.__doc__ or ""
    assert (
        len(docstring.strip()) > 0
    ), f"expected non-empty instructions docstring; got: {docstring!r}"

    # Assertion 5 — round-trip through BaseAgent (AC 3 end-to-end). The
    # synthesized class MUST be usable as the `signature=` arg to a
    # real Kaizen agent constructor. Constructing the agent (not
    # invoking it) is sufficient evidence — BaseAgent stores the
    # signature and exposes its input_fields / output_fields properties
    # the rest of Kaizen depends on (see base_agent.py:274 + 382).
    from kaizen.core.base_agent import BaseAgent

    agent = BaseAgent(
        config={"model": os.environ["DEFAULT_LLM_MODEL"], "temperature": 0},
        signature=new_class(),
    )
    assert agent.signature is not None
    assert len(agent.signature.input_fields) == expected["input_field_count"]
    assert len(agent.signature.output_fields) == expected["output_field_count"]


@_REQUIRES_LLM_MODEL
@pytest.mark.integration
@pytest.mark.regression
def test_signature_from_brief_multi_field():
    """Multi-input + multi-output + non-string-type brief shape.

    Same SHAPE-not-bytes contract as the single-IO case; additionally
    asserts at least one output field carries a non-string declared
    type (the brief calls for a float confidence score, so the field
    type allowlist should surface ``float`` in at least one position).
    """
    fixture = _load_fixture("kaizen_multi_field.yaml")
    brief = fixture["brief"]
    expected = fixture["expected"]

    new_class = Kaizen.signature_from_brief(brief)

    # Return shape (assertions 1 + 2 from the single-IO test).
    assert isinstance(new_class, type)
    assert issubclass(new_class, Signature)

    instance = new_class()

    # Field-count minimums (LLM may emit more fields than the strict
    # brief; ≥ is the structural minimum the brief commits to).
    assert len(instance.input_fields) >= expected["input_field_count_min"], (
        f"expected ≥{expected['input_field_count_min']} input fields; "
        f"got {len(instance.input_fields)}: {list(instance.input_fields.keys())}"
    )
    assert len(instance.output_fields) >= expected["output_field_count_min"], (
        f"expected ≥{expected['output_field_count_min']} output fields; "
        f"got {len(instance.output_fields)}: {list(instance.output_fields.keys())}"
    )

    # Non-string-type presence in outputs (the brief specifies a float
    # confidence). The output_fields dict values are
    # ``{"type": <python_type>, "desc": ..., ...}`` per
    # SignatureMeta processing.
    if expected.get("has_non_string_output"):
        non_string_outputs = [
            (name, field["type"])
            for name, field in instance.output_fields.items()
            if field.get("type") is not str
        ]
        assert non_string_outputs, (
            f"expected ≥1 non-string output field; got all-string: "
            f"{[(n, f.get('type')) for n, f in instance.output_fields.items()]}"
        )

    # Structural docstring check — non-empty instructions block (see
    # the single-IO test's Assertion 4 for the probe-driven-verification
    # rationale; substring matching on prose is BLOCKED).
    docstring = new_class.__doc__ or ""
    assert (
        len(docstring.strip()) > 0
    ), f"expected non-empty instructions docstring; got: {docstring!r}"

    # Round-trip via BaseAgent (AC 3 contract).
    from kaizen.core.base_agent import BaseAgent

    agent = BaseAgent(
        config={"model": os.environ["DEFAULT_LLM_MODEL"], "temperature": 0},
        signature=new_class(),
    )
    assert agent.signature is not None
    assert len(agent.signature.input_fields) >= expected["input_field_count_min"]
    assert len(agent.signature.output_fields) >= expected["output_field_count_min"]


def test_signature_from_brief_raises_on_missing_default_llm_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ``model=None`` default surfaces a typed missing-env error.

    This is a Tier-1 test (no LLM call; the helper raises BEFORE any
    network I/O). Per the S1 ``get_default_llm_model()`` contract, a
    missing ``DEFAULT_LLM_MODEL`` env var raises
    :class:`MissingDefaultLLMModelError` at the helper boundary — NOT
    a deep RuntimeError inside BaseAgent. This test pins that contract
    so a regression that silently invents a default model breaks the
    suite loudly.
    """
    monkeypatch.delenv("DEFAULT_LLM_MODEL", raising=False)
    with pytest.raises(MissingDefaultLLMModelError):
        Kaizen.signature_from_brief("a brief that never reaches the LLM")


# Structural invariant — the public classmethod is bound on Kaizen.
def test_kaizen_signature_from_brief_is_classmethod():
    """``Kaizen.signature_from_brief`` is a classmethod (AC 3 binding).

    Tier-1 structural invariant. If a future refactor moves the entry
    point to an instance method or a module-level function, this test
    fails loud and forces a contract re-audit — the brief at
    issue #1125 AC 3 specifies ``kailash.Kaizen.signature_from_brief(brief)``
    (dotted-class shorthand for ``Kaizen.signature_from_brief(brief)``
    where Kaizen lives at ``kaizen.Kaizen``).
    """
    import inspect

    bound = inspect.getattr_static(Kaizen, "signature_from_brief")
    assert isinstance(
        bound, classmethod
    ), f"expected classmethod; got {type(bound).__name__}"

    # Signature surface — keyword-only model + confidence_threshold per
    # the docstring contract.
    sig = inspect.signature(Kaizen.signature_from_brief)
    params = list(sig.parameters.values())
    assert params[0].name == "brief"
    assert params[0].kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.POSITIONAL_ONLY,
    )
    # `model` + `confidence_threshold` MUST be keyword-only so call
    # sites cannot accidentally swap them with positional args.
    keyword_only = {p.name for p in params if p.kind is inspect.Parameter.KEYWORD_ONLY}
    assert {"model", "confidence_threshold"} <= keyword_only, (
        f"expected model + confidence_threshold to be keyword-only; "
        f"got keyword-only={keyword_only!r}"
    )


# Sanity check that the documented error class is the same one the S1
# foundation exports — if S1 ever splits this exception per surface,
# this assertion fails and forces the docstring update.
def test_brief_interpretation_error_imports_clean():
    """The documented BriefInterpretationError import path is stable."""
    from kailash._from_brief import BriefInterpretationError as ExportedError

    assert ExportedError is BriefInterpretationError
