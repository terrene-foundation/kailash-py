"""Annotation introspection helpers.

Python 3.14 (PEP 649 / PEP 749) made class annotations lazy. The class-body
compiler now emits a ``__annotate__`` callable into the class namespace; the
``__annotations__`` dict is computed only on attribute access of the *built*
class, and may raise ``NameError`` if any annotation contains an unresolved
forward reference at evaluation time.

This shifted two contracts that the Kailash stack relied on:

1. **Metaclass namespace.**  Pre-3.14, ``namespace["__annotations__"]`` was
   a pre-built dict during ``__new__``.  In 3.14 the dict is gone — the
   namespace carries ``__annotate__`` instead.  Code that did
   ``namespace.get("__annotations__", {})`` silently sees ``{}`` and produces
   classes with no field metadata.  This is what broke every Kaizen agent
   using the declarative class-based ``Signature`` style.

2. **Class attribute.**  ``cls.__annotations__`` still works on 3.14, but
   may raise ``NameError`` instead of returning a string for unresolved
   forward references.  ``getattr(cls, "__annotations__", {})`` does NOT
   catch that — the default is only used on ``AttributeError``.

Every annotation read in Kailash production code MUST go through one of the
three primitives in this module so the 3.13 / 3.14 differences are handled
in exactly one place.
"""

from __future__ import annotations

import inspect
import sys
import typing
from typing import Any, Dict, Mapping, Type

if sys.version_info >= (3, 14):
    # ``annotationlib`` is a stdlib module added in Python 3.14 (PEP 749).
    # Type checkers configured for older Python targets cannot resolve it.
    import annotationlib as _annotationlib  # type: ignore[import-not-found]

    _ANNOTATION_FORMAT = _annotationlib.Format
    _FORWARDREF_TYPE: Any = _annotationlib.ForwardRef
else:  # pragma: no cover - exercised on 3.14+ only
    _annotationlib = None  # type: ignore[assignment]
    _ANNOTATION_FORMAT = None  # type: ignore[assignment]
    _FORWARDREF_TYPE = typing.ForwardRef


__all__ = [
    "get_namespace_annotations",
    "get_class_annotations",
    "get_resolved_type_hints",
]


def get_namespace_annotations(namespace: Mapping[str, Any]) -> Dict[str, Any]:
    """Return class-body annotations from a metaclass ``__new__`` namespace.

    Pre-3.14 sets ``namespace["__annotations__"]`` directly; 3.14 emits a
    lazy ``namespace["__annotate__"]`` callable instead.  This helper reads
    whichever form is present and returns a plain dict.

    The forward-reference (``FORWARDREF``) format is preferred so unresolved
    names do not raise during class construction — callers that store the
    annotation as descriptive metadata (Kaizen ``Signature``) accept the
    ``ForwardRef`` object as-is.
    """
    annotations = namespace.get("__annotations__")
    if annotations:
        return dict(annotations)

    annotate = namespace.get("__annotate__")
    if annotate is None:
        return {}

    if _ANNOTATION_FORMAT is not None:
        try:
            return dict(annotate(_ANNOTATION_FORMAT.VALUE) or {})
        except NameError:
            return dict(annotate(_ANNOTATION_FORMAT.FORWARDREF) or {})

    # Pre-3.14 interpreter that nonetheless exposes ``__annotate__``
    # (a backport, or a manually-built class).  Format.VALUE == 1,
    # Format.FORWARDREF == 2.
    try:
        return dict(annotate(1) or {})
    except NameError:
        return dict(annotate(2) or {})
    except Exception:
        return {}


def get_class_annotations(cls: Type[Any]) -> Dict[str, Any]:
    """Return ``cls`` annotations as a dict, robust across 3.13 and 3.14+.

    Wraps :func:`inspect.get_annotations` (added in Python 3.10) which knows
    how to evaluate the lazy ``__annotate__`` callable on 3.14 while still
    reading the eager ``__annotations__`` dict on older interpreters.

    ``eval_str`` is left ``False`` so string forward references are returned
    as-is rather than evaluated against the class module's globals — the
    annotations are surfaced to callers that store the type as descriptive
    metadata, not for runtime ``isinstance`` checks.

    Returns an empty dict for non-class inputs or any unexpected failure
    rather than raising — matches the historical
    ``getattr(cls, "__annotations__", {})`` semantics callers were written
    against.
    """
    if not isinstance(cls, type):
        # Defensive — callers occasionally pass instances or other objects.
        cls = type(cls)
    try:
        return inspect.get_annotations(cls, eval_str=False) or {}
    except Exception:
        return {}


def get_resolved_type_hints(cls: Type[Any]) -> Dict[str, Any]:
    """Return ``cls`` annotations with forward references resolved to types.

    Use this when the caller actually needs the resolved Python type (e.g.
    DataFlow ``@db.model`` registration, which maps each field type to a
    SQL column type).  For callers that only need the raw annotation dict,
    prefer :func:`get_class_annotations`.

    On Python 3.14, falls back to ``annotationlib.get_annotations`` with the
    ``FORWARDREF`` format and raises a clear, per-field error when an
    annotation cannot be resolved — matching the kailash-rs handler so the
    two SDKs surface the same actionable message.

    Raises:
        RuntimeError: if any field on ``cls`` has an unresolvable forward
            reference.  The message names the class, the field, and the
            forward-referenced name so the caller can fix the import.
    """
    try:
        return typing.get_type_hints(cls) or {}
    except NameError:
        if sys.version_info < (3, 14) or _annotationlib is None:
            raise

        raw = _annotationlib.get_annotations(
            cls, format=_annotationlib.Format.FORWARDREF
        )

        resolved: Dict[str, Any] = {}
        for name, ann in raw.items():
            if isinstance(ann, _FORWARDREF_TYPE):
                forward_arg = getattr(ann, "__forward_arg__", str(ann))
                raise RuntimeError(
                    f"{cls.__module__}.{cls.__name__}: field '{name}' has "
                    f"an unresolvable type '{forward_arg}'. Import the "
                    f"type at runtime (not under TYPE_CHECKING) so the "
                    f"annotation can be resolved during class registration."
                )
            resolved[name] = ann
        return resolved
