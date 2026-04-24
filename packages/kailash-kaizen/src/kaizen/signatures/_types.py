# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Shared types for ``kaizen.signatures``.

Breaks the static import cycle between :mod:`kaizen.signatures.core`
and :mod:`kaizen.signatures.enterprise`. ``core.py`` previously
``TYPE_CHECKING``-imported :class:`SignatureComposition` from
``enterprise``, while ``enterprise`` imports :class:`Signature` /
:class:`SignatureValidator` / :class:`ValidationResult` from ``core``
at module scope.

The break is structural rather than data-class extraction: the only
``core``-side need for ``SignatureComposition`` is to type-narrow the
``Union[Signature, SignatureComposition]`` argument of two
:class:`SignatureValidator` / :class:`SignatureCompiler` methods. The
runtime check is ``hasattr(sig, "signatures")``. We expose a
:class:`typing.Protocol` capturing exactly that shape so ``core``
imports it eagerly from this leaf module — never reaching back into
``enterprise``.

The concrete :class:`kaizen.signatures.enterprise.SignatureComposition`
satisfies this protocol structurally (it exposes ``.signatures``).

The protocol is :func:`runtime_checkable` so static analyzers see a
valid runtime type, but the canonical runtime check inside
:mod:`core` remains ``hasattr(sig, "signatures")``. ``isinstance(x,
SignatureCompositionProtocol)`` is available technically but is NOT
recommended in security-sensitive paths: any duck-typed object with
a ``.signatures`` attribute would pass, which is exactly the
auth-bypass shape documented in ``rules/orphan-detection.md``.
Where the caller needs an admission check against the concrete
class (e.g. kaizen memory / kaizen-agents dataflow integration
sites that pin ``isinstance(db, DataFlow)``), keep the concrete
``isinstance(x, SignatureComposition)`` — not the Protocol.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["SignatureCompositionProtocol"]


@runtime_checkable
class SignatureCompositionProtocol(Protocol):
    """Structural shape of :class:`kaizen.signatures.enterprise.SignatureComposition`.

    The validator and compiler in :mod:`kaizen.signatures.core` need only
    one observable: a ``signatures`` collection. Full
    ``SignatureComposition`` behaviour (orchestration, dependency
    resolution, ordering) lives in ``enterprise.py`` and is invoked by
    higher-level callers; ``core`` only needs to recognise the shape.
    """

    signatures: Any


"""The ordered collection of constituent :class:`Signature` instances.

``Any`` rather than a precise type so this protocol stays free of
edges back into ``enterprise``; the concrete class declares the real
collection type.
"""
