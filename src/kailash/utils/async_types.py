"""Native await-protocol classification for callback results we already own."""

from inspect import CO_ITERABLE_COROUTINE
from types import CoroutineType, GeneratorType


def _is_native_awaitable(value):
    """Inspect the real type without executing unrelated metadata descriptors.

    Special-method lookup for ``await`` uses the actual type's MRO. Instance
    ``__class__`` and metaclass attribute hooks cannot add or remove that protocol.
    Classification does not invoke ``__await__``; the owner awaits exactly once.
    """
    actual = type(value)
    if actual is CoroutineType:
        return True
    if actual is GeneratorType:
        return bool(value.gi_code.co_flags & CO_ITERABLE_COROUTINE)
    for base in type.__dict__["__mro__"].__get__(actual):
        namespace = type.__dict__["__dict__"].__get__(base)
        if "__await__" in namespace:
            return namespace["__await__"] is not None
    return False
