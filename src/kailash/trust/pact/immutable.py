# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Immutable collection types for PACT governance value objects.

Why this module exists
----------------------
``model_config = ConfigDict(frozen=True)`` on a pydantic model blocks attribute
*assignment*. It does NOT freeze the model's collection fields: a ``list[str]``
field on a frozen model is still an ordinary list, and ``.append()`` on it
mutates the model in place. The same is true of ``@dataclass(frozen=True)`` and
a ``dict`` field.

That gap was a privilege escalation (#2226). ``GovernanceEngine`` hands out the
LIVE envelope object -- the store returns its own object, and the verdict path
reads the same list -- so a holder of the deliberately read-only
``PactEngine.governance`` view could permanently grant itself a denied action
without ever touching a denied name::

    view.get_context(ADDR).effective_envelope.operational.allowed_actions.append(
        "wire_transfer"
    )

The containment proxy (:mod:`kailash.trust.readonly_proxy`, #2224) cannot close
this: it contains the PROXY, and this attack never touches the proxy again after
the first allowlisted read. The only place it can be closed is the value object
itself, which is what this module provides.

Design
------
``tuple`` covers the sequence fields directly -- it is the type the sibling
model in :mod:`kailash.trust.envelope` already uses for exactly these fields
("Coerce lists to tuples for frozen immutability"), so this module brings
``pact.config`` in line with the convention already established in the tree.

Mappings need more care. ``types.MappingProxyType`` is the tree's convention for
frozen *dataclasses* (``pact.outbound``, ``pact.compilation``,
``trust.identity.resolver``), but it is the wrong tool inside a *pydantic* model
on two measured counts: pydantic emits
``PydanticSerializationUnexpectedValue`` for every ``model_dump()``, and
``mappingproxy`` cannot be pickled, so ``copy.deepcopy()`` of any model holding
one raises ``TypeError``. :class:`FrozenMapping` is a ``dict`` SUBCLASS instead,
which keeps ``isinstance(x, dict)`` true for every existing consumer, serializes
natively, and round-trips through ``deepcopy``/``pickle`` via the explicit
reduction below.

Scope, stated honestly
----------------------
These types make the CONTAINER immutable. They do not deep-freeze arbitrary
values placed inside them: a ``FrozenMapping`` whose value is a plain ``list``
still hands out a mutable list. Governance value objects hold scalars and nested
frozen models, so this is sufficient there -- but it is a boundary, not a
guarantee about arbitrary payloads.
"""

from __future__ import annotations

import copy
from typing import Annotated, Any, Mapping, TypeVar

from pydantic.functional_validators import AfterValidator

__all__ = [
    "FrozenMapping",
    "FrozenAnyMapping",
    "FrozenFloatMapping",
    "freeze_mapping",
]

_K = TypeVar("_K")
_V = TypeVar("_V")


class FrozenMapping(dict):
    """A ``dict`` that refuses every in-place mutation.

    Subclasses ``dict`` deliberately. A ``MappingProxyType`` would be the more
    obvious choice, but it breaks pydantic serialization and cannot be pickled
    or deep-copied; a ``dict`` subclass keeps every existing consumer working
    (``isinstance(value, dict)`` stays true, ``json.dumps`` stays happy) while
    turning every mutating method into a typed refusal.

    Reads are unaffected: indexing, ``.get()``, ``.keys()``, ``.items()``,
    iteration, ``len()`` and ``in`` all behave exactly as on a plain dict.

    Raises:
        TypeError: On any attempt to set, delete, update, pop, or clear.
    """

    __slots__ = ()

    def _refuse(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError(
            f"{type(self).__name__} is immutable and cannot be mutated in place. "
            f"This mapping belongs to a governance value object; mutating it "
            f"would change an authorization decision without any audit record. "
            f"Build a new object instead (e.g. model_copy(update=...))."
        )

    # Every mutating entry point on dict, including the operator forms.
    __setitem__ = _refuse
    __delitem__ = _refuse
    __ior__ = _refuse
    clear = _refuse
    pop = _refuse
    popitem = _refuse
    setdefault = _refuse
    update = _refuse

    def __reduce__(self) -> tuple[Any, ...]:
        """Reconstruct through ``__init__`` rather than item assignment.

        ``dict``'s default reduction replays the contents with ``obj[k] = v``,
        which this class refuses -- so without this, pickling and
        ``copy.deepcopy`` of any model holding a FrozenMapping would raise.
        """
        return (type(self), (dict(self),))

    def __copy__(self) -> FrozenMapping:
        return type(self)(dict(self))

    def __deepcopy__(self, memo: dict[int, Any]) -> FrozenMapping:
        return type(self)(
            {
                copy.deepcopy(key, memo): copy.deepcopy(value, memo)
                for key, value in self.items()
            }
        )


def freeze_mapping(value: Mapping[_K, _V]) -> FrozenMapping:
    """Coerce any mapping into a :class:`FrozenMapping`.

    Used as a pydantic ``AfterValidator`` so the frozen form is installed on
    every construction path -- direct instantiation, YAML load, JSON
    round-trip, and ``model_validate`` alike. Idempotent.

    Args:
        value: Any mapping.

    Returns:
        A FrozenMapping holding a shallow copy of ``value``.
    """
    return FrozenMapping(value)


#: A ``dict[str, Any]`` field that is immutable once the model is constructed.
FrozenAnyMapping = Annotated[Mapping[str, Any], AfterValidator(freeze_mapping)]

#: A ``dict[str, float]`` field that is immutable once the model is constructed.
FrozenFloatMapping = Annotated[Mapping[str, float], AfterValidator(freeze_mapping)]
