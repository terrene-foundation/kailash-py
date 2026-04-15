"""Regression: Python 3.14 PEP 649/749 lazy annotations.

Symptom: every Kaizen agent using a class-based ``Signature`` failed to
register on Python 3.14 because the metaclass read
``namespace.get("__annotations__", {})``, which returns ``{}`` on 3.14 since
the compiler now emits a lazy ``__annotate__`` callable into the namespace
instead.

Fix: a single shared helper module in ``kailash.utils.annotations`` with
three primitives — ``get_namespace_annotations``, ``get_class_annotations``,
and ``get_resolved_type_hints`` — exercised by every annotation read in
production code so the 3.13 / 3.14 differences are handled in one place.

These tests are behavioural — they exercise the actual call paths rather
than grepping source.  The lazy ``__annotate__`` path is covered by
constructing a synthetic namespace dict that mimics the 3.14 compiler's
output, so the suite runs (and asserts) the same on 3.13 and 3.14+.
"""

# NOTE: deliberately NOT using ``from __future__ import annotations`` here.
# That import would stringify every annotation in this file, hiding the
# very behaviour these tests assert (eager-vs-lazy 3.13/3.14 differences
# in how class annotations resolve to concrete Python types).

import sys
from typing import List

import pytest

# -----------------------------------------------------------------------
# Shared-helper unit tests — exercise each primitive directly.
# -----------------------------------------------------------------------


@pytest.mark.regression
def test_get_namespace_annotations_eager_form_returns_dict():
    """Pre-3.14 namespace shape: ``__annotations__`` already a dict."""
    from kailash.utils.annotations import get_namespace_annotations

    namespace = {
        "__annotations__": {"x": int, "y": str},
        "x": 0,
    }
    result = get_namespace_annotations(namespace)
    assert result == {"x": int, "y": str}


@pytest.mark.regression
def test_get_namespace_annotations_empty_namespace_returns_empty_dict():
    """A namespace with neither form returns ``{}`` rather than raising."""
    from kailash.utils.annotations import get_namespace_annotations

    assert get_namespace_annotations({}) == {}


@pytest.mark.regression
def test_get_namespace_annotations_lazy_annotate_form():
    """3.14 namespace shape: ``__annotate__`` callable, no eager dict.

    The helper MUST evaluate ``__annotate__`` and return the dict.  A
    pre-3.14 interpreter exercises the same branch via the integer-format
    fallback (``Format.VALUE == 1``).
    """
    from kailash.utils.annotations import get_namespace_annotations

    expected = {"a": int, "b": str}

    def fake_annotate(format):
        # Format.VALUE == 1, Format.FORWARDREF == 2 — accept both so the
        # helper's fallback path also resolves on pre-3.14 interpreters.
        if format in (1, 2):
            return dict(expected)
        return {}

    namespace = {"__annotate__": fake_annotate}
    assert get_namespace_annotations(namespace) == expected


@pytest.mark.regression
def test_get_namespace_annotations_lazy_falls_back_on_nameerror():
    """If VALUE format raises ``NameError``, fall back to FORWARDREF."""
    from kailash.utils.annotations import get_namespace_annotations

    forwardref_dict = {"x": "Unresolved"}

    def fake_annotate(format):
        if format == 1:  # Format.VALUE — pretend a forward ref breaks it.
            raise NameError("name 'Unresolved' is not defined")
        if format == 2:  # Format.FORWARDREF — succeeds with raw string.
            return dict(forwardref_dict)
        return {}

    namespace = {"__annotate__": fake_annotate}
    assert get_namespace_annotations(namespace) == forwardref_dict


@pytest.mark.regression
def test_get_class_annotations_returns_dict_for_annotated_class():
    """``get_class_annotations`` returns a copy of the class annotation dict."""
    from kailash.utils.annotations import get_class_annotations

    class _Sample:
        a: int
        b: str = "default"

    result = get_class_annotations(_Sample)
    assert result == {"a": int, "b": str}


@pytest.mark.regression
def test_get_class_annotations_returns_empty_dict_for_unannotated_class():
    """Classes without annotations return ``{}`` rather than raising."""
    from kailash.utils.annotations import get_class_annotations

    class _NoAnnotations:
        pass

    assert get_class_annotations(_NoAnnotations) == {}


@pytest.mark.regression
def test_get_class_annotations_accepts_instance_input():
    """Passing an instance defensively falls back to ``type(instance)``."""
    from kailash.utils.annotations import get_class_annotations

    class _Sample:
        x: int

    instance = _Sample()
    assert get_class_annotations(instance) == {"x": int}


@pytest.mark.regression
def test_get_resolved_type_hints_resolves_simple_class():
    """``get_resolved_type_hints`` returns fully resolved Python types."""
    from kailash.utils.annotations import get_resolved_type_hints

    class _Sample:
        name: str
        age: int

    result = get_resolved_type_hints(_Sample)
    assert result == {"name": str, "age": int}


@pytest.mark.regression
def test_get_resolved_type_hints_raises_actionable_error_on_unresolvable_forward_ref():
    """An unresolvable forward reference produces a per-field error.

    On Python 3.14+ we delegate to ``annotationlib`` and raise a clear
    ``RuntimeError`` naming the class, the field, and the forward-arg.
    On pre-3.14 we let ``typing.get_type_hints``'s native ``NameError``
    propagate (no ``annotationlib`` to fall back to).
    """
    from kailash.utils.annotations import get_resolved_type_hints

    # Build a class whose annotation references a name that doesn't exist
    # in any scope.  ``typing.get_type_hints`` will raise ``NameError``.
    namespace: dict = {}
    exec(  # noqa: S102 - controlled test scaffold, no user input
        "class _ForwardRefSample:\n" "    field_a: 'CompletelyUnknownType'\n",
        namespace,
    )
    cls = namespace["_ForwardRefSample"]

    if sys.version_info >= (3, 14):
        with pytest.raises(RuntimeError) as exc_info:
            get_resolved_type_hints(cls)
        message = str(exc_info.value)
        assert "field_a" in message
        assert "CompletelyUnknownType" in message
    else:
        with pytest.raises(NameError):
            get_resolved_type_hints(cls)


# -----------------------------------------------------------------------
# Integration: Kaizen ``Signature`` subclass — the original symptom.
# -----------------------------------------------------------------------


@pytest.mark.regression
def test_kaizen_signature_subclass_extracts_inputs_and_outputs():
    """Original symptom: declaring a ``Signature`` subclass with annotated
    ``InputField`` / ``OutputField`` defaults must populate
    ``_signature_inputs`` and ``_signature_outputs`` on the class.

    Before the fix, on Python 3.14 the metaclass read
    ``namespace["__annotations__"]`` directly, saw ``{}``, and produced a
    Signature with zero fields — which then caused every dependent
    BaseAgent to refuse to construct.
    """
    from kaizen.signatures.core import InputField, OutputField, Signature

    class _DemoSignature(Signature):
        """Demo signature used to exercise the metaclass fix."""

        question: str = InputField(description="The question to answer")
        context: str = InputField(description="Background context", default="")
        answer: str = OutputField(description="Final answer")
        confidence: float = OutputField(description="Confidence 0-1")

    assert set(_DemoSignature._signature_inputs.keys()) == {"question", "context"}
    assert set(_DemoSignature._signature_outputs.keys()) == {"answer", "confidence"}
    assert _DemoSignature._signature_inputs["question"]["type"] is str
    assert _DemoSignature._signature_outputs["confidence"]["type"] is float


# -----------------------------------------------------------------------
# Integration: Core SDK Port descriptor — uses ``get_class_annotations``.
# -----------------------------------------------------------------------


@pytest.mark.regression
def test_port_descriptor_extracts_type_hint_from_owner_class():
    """``Port.__set_name__`` reads the owner's annotations to pick up the
    declared type for the port.  The fix routes that read through
    ``get_class_annotations`` so 3.14 lazy annotations resolve safely.
    """
    from kailash.nodes.ports import InputPort

    class _DemoNode:
        value: InputPort[int] = InputPort(name="value")

    # ``__set_name__`` fires at class-body execution time; the port should
    # have picked up the ``int`` type argument from the annotation.
    port = _DemoNode.__dict__["value"]
    assert port._type_hint is int


# -----------------------------------------------------------------------
# Wiring: every patched call site successfully imports the helper.
# -----------------------------------------------------------------------


@pytest.mark.regression
def test_all_patched_modules_import_cleanly():
    """If a patched module had a typo in the helper import, the module
    would fail to import and every dependent agent / DataFlow model would
    crash at first use.  This catches that regression structurally.
    """
    import importlib

    modules = [
        "kailash.nodes.ports",
        "dataflow.core.engine",
        "dataflow.core.model_registry",
        "dataflow.migrations.fk_aware_model_integration",
        "kaizen.signatures.core",
        "kaizen.deploy.introspect",
        "kaizen.core.type_introspector",
        "kaizen.core.autonomy.state.types",
        "kaizen.memory.enterprise",
        "kaizen.strategies.single_shot",
        "kaizen.strategies.multi_cycle",
        "kaizen_agents.integrations.dataflow.connection",
    ]
    for module_name in modules:
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            # Optional sub-package not installed in this environment.
            continue
        except Exception as exc:  # pragma: no cover - regression failure path
            pytest.fail(
                f"Patched module {module_name!r} failed to import after the "
                f"PEP 649/749 fix: {exc!r}"
            )
