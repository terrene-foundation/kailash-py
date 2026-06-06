"""Single-site type-introspection primitives for DataFlow (issue #772).

Several DataFlow helpers independently re-implemented the same two-spelling
Optional/Union detection -- ``get_origin(a) is Union or get_origin(a) is
types.UnionType`` -- to recognize BOTH the legacy ``typing.Optional[T]`` /
``typing.Union[T, None]`` form AND the PEP 604 ``T | None`` form. Each copy had
to be patched independently whenever a new type-form appeared. That maintenance
tax fired twice: #1207 (the JSONB read-path deserializer) and #1228 (PEP 604
``T | None`` across node generation, ID coercion, type processing, schema
parsing, engine SQL mapping, model validation, and FK inference). Both
incidents had to touch every copy.

This module centralizes ONLY the detection + non-None extraction into one
primitive (``union_non_none_args``) plus the Annotated-strip helper
(``strip_annotated``). Each caller keeps its OWN post-detection policy --
some recurse on the first non-None arg, some return multi-type unions as-is,
some set a nullable flag. The shared primitive means the next union spelling
is handled in exactly one place.

ASCII-only docstrings throughout (Windows source-scanner constraint).
"""

import types
import typing
from typing import Any, Union, get_args, get_origin


def union_non_none_args(annotation: Any) -> list | None:
    """Two-spelling Optional/Union detection -- the SINGLE place a new union
    spelling is handled (issue #772; #1207 / #1228 PEP 604 drift is the
    evidence that motivated consolidating this detection).

    Recognizes BOTH spellings of a union/optional in one predicate:

    1. ``typing.Union[T, ...]`` / ``typing.Optional[T]`` -- ``get_origin``
       returns ``typing.Union``.
    2. PEP 604 ``T | None`` (Python 3.10+) -- ``get_origin`` returns
       ``types.UnionType``.

    Returns:
        - the list of non-``None`` args if ``annotation`` is a union in either
          spelling (``Optional[int]`` -> ``[int]``; ``str | int`` ->
          ``[str, int]``; the all-``None`` edge -> ``[]``). The caller decides
          what to do with a single arg vs multiple args vs an empty list.
        - ``None`` if ``annotation`` is not a union at all (a bare type, a
          parameterized container like ``list[str]``, etc.).

    The ``None`` return is distinct from the ``[]`` return: ``None`` means
    "not a union"; ``[]`` means "a union whose only member was ``NoneType``".
    """
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        return [a for a in get_args(annotation) if a is not type(None)]
    return None


def strip_annotated(annotation: Any) -> Any:
    """``Annotated[T, ...]`` -> ``T`` (single layer); pass through otherwise.

    The next drift example the issue (#772) named explicitly was
    ``typing.Annotated``. Verified on Python 3.12: ``get_origin(Annotated[int,
    "x"]) is typing.Annotated`` and ``get_args(Annotated[int, "x"])[0]`` is the
    wrapped type (``int``). A non-``Annotated`` annotation is returned
    unchanged, so this is safe to call unconditionally before any further
    introspection.
    """
    if get_origin(annotation) is typing.Annotated:
        return get_args(annotation)[0]
    return annotation
