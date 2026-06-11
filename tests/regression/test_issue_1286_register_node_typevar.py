"""Regression test for issue #1286.

`register_node` erased decorated node subclasses to ``type[Node]`` because the
inner decorator was annotated ``def decorator(node_class: type[Node])`` with no
generic return type. Static checkers therefore inferred every
``@register_node()``-decorated class as ``type[Node]``, dropping the subclass and
emitting an ``attr-defined`` diagnostic at every subclass-specific classmethod
call site (e.g. ``PythonCodeNode.from_function(...)``).

The fix makes the decorator generic via a ``TypeVar`` bound to ``Node`` so the
decorated class retains its precise type, with ZERO runtime behaviour change.

This test locks BOTH halves of the contract:
  1. Runtime: the decorator returns the same class object unchanged.
  2. Typing: ``register_node`` returns a generic decorator whose input and output
     carry the SAME ``TypeVar`` bound to ``Node`` — if a future edit reverts the
     signature to ``type[Node]`` the typing assertion fails loudly.
"""

import inspect
import typing

import pytest

from kailash.nodes.base import Node, register_node


@pytest.mark.regression
def test_register_node_returns_class_unchanged_at_runtime():
    """Zero runtime change: the decorator returns the exact class object."""

    class _Probe(Node):
        def get_parameters(self):
            return {}

        def run(self, **kwargs):
            return {}

        @classmethod
        def special(cls) -> str:
            return "ok"

    decorated = register_node()(_Probe)
    assert decorated is _Probe
    # Subclass-specific classmethod survives (the call site #1286 flagged).
    assert decorated.special() == "ok"


@pytest.mark.regression
def test_register_node_alias_returns_class_unchanged_at_runtime():
    """The aliased form preserves identity too."""

    class _AliasProbe(Node):
        def get_parameters(self):
            return {}

        def run(self, **kwargs):
            return {}

    decorated = register_node(alias="AliasProbeCustom")(_AliasProbe)
    assert decorated is _AliasProbe


@pytest.mark.regression
def test_register_node_signature_is_generic_typevar_bound_to_node():
    """Typing contract: register_node -> Callable[[type[T]], type[T]], T bound to Node.

    Locks the fix against a revert to the non-generic ``type[Node]`` signature
    that erased subclasses. base.py does NOT use ``from __future__ import
    annotations`` so the return annotation is the live typing object, not a str.
    """
    ret = inspect.signature(register_node).return_annotation
    assert (
        ret is not inspect.Signature.empty
    ), "register_node lost its return annotation"

    # Callable[[type[T]], type[T]] -> get_args == ([type[T]], type[T])
    callable_args = typing.get_args(ret)
    assert callable_args, f"return annotation not parametrized: {ret!r}"
    params, result = callable_args[0], callable_args[-1]
    assert (
        isinstance(params, list) and len(params) == 1
    ), f"unexpected param shape: {params!r}"

    (in_tv,) = typing.get_args(params[0])  # the type[T] param yields T
    (out_tv,) = typing.get_args(result)  # the type[T] result yields T

    assert isinstance(
        in_tv, typing.TypeVar
    ), f"decorator input is not a TypeVar: {in_tv!r}"
    assert in_tv is out_tv, (
        "register_node erases the subclass type — input and output TypeVar differ "
        "(regressed to a non-generic decorator)"
    )
    assert in_tv.__bound__ is Node, f"TypeVar is not bound to Node: {in_tv.__bound__!r}"
