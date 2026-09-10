# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for the fail-closed read-only attribute proxy (#2224).

The proxy exists because a ``__getattr__``-guarded view is not a containment
boundary: ``__getattr__`` is consulted only when NORMAL lookup fails, so the
wrapped target -- a real instance attribute -- escapes the guard entirely.

Every test here is bipolar where it can be: the allowed pole proves the proxy
still WORKS, the denied pole proves it CONTAINS. A deny-only suite cannot
distinguish a correct proxy from one that is simply broken.
"""

from __future__ import annotations

import copy
import pickle

import pytest

from kailash.trust.readonly_proxy import ReadOnlyAttributeProxy, ReadOnlyProxyError


class _Target:
    """Stand-in for a mutable subsystem behind a read-only view."""

    def __init__(self) -> None:
        self.mutations: list[str] = []

    @property
    def name(self) -> str:
        return "target-name"

    def read_value(self) -> str:
        return "read-ok"

    def mutate(self) -> str:
        self.mutations.append("mutate")
        return "MUTATED"


@pytest.fixture
def target() -> _Target:
    return _Target()


@pytest.fixture
def proxy(target: _Target) -> ReadOnlyAttributeProxy:
    return ReadOnlyAttributeProxy(target, {"name", "read_value"})


class TestAllowedPole:
    """The proxy must still WORK -- a deny-only suite proves nothing."""

    def test_allowed_property_reads_through(
        self, proxy: ReadOnlyAttributeProxy
    ) -> None:
        assert proxy.name == "target-name"

    def test_allowed_method_calls_through(self, proxy: ReadOnlyAttributeProxy) -> None:
        assert proxy.read_value() == "read-ok"

    def test_allowed_access_reaches_the_real_target(self, target: _Target) -> None:
        """Proves the proxy forwards to THIS target, not a copy or a stub."""
        proxy = ReadOnlyAttributeProxy(target, {"mutations"})
        target.mutations.append("sentinel")
        assert proxy.mutations == ["sentinel"]


class TestDeniedPole:
    def test_mutation_method_is_denied(self, proxy: ReadOnlyAttributeProxy) -> None:
        with pytest.raises(ReadOnlyProxyError, match="does not expose 'mutate'"):
            proxy.mutate  # noqa: B018 -- intentional attribute access

    def test_target_handle_is_denied(self, proxy: ReadOnlyAttributeProxy) -> None:
        """The #2224 defect: a __getattr__ guard leaks the target itself."""
        with pytest.raises(ReadOnlyProxyError, match="does not expose '_target'"):
            proxy._target  # noqa: B018 -- intentional attribute access

    def test_dict_is_denied(self, proxy: ReadOnlyAttributeProxy) -> None:
        """__dict__ would hand back the target just as directly as _target."""
        with pytest.raises(ReadOnlyProxyError):
            proxy.__dict__  # noqa: B018 -- intentional attribute access

    def test_name_on_no_list_at_all_is_denied(
        self, proxy: ReadOnlyAttributeProxy
    ) -> None:
        """Default-deny, not a bigger blocklist.

        ``never_heard_of_this`` is on no allowlist and no blocklist anywhere in
        the codebase, and does not exist on the target. A blocklist-based proxy
        passes this through; an allowlist-based one denies it.
        """
        with pytest.raises(ReadOnlyProxyError):
            proxy.never_heard_of_this  # noqa: B018

    def test_allowlist_internals_are_denied(
        self, proxy: ReadOnlyAttributeProxy
    ) -> None:
        for name in ("_allowed", "_label", "_message_template", "_overrides"):
            with pytest.raises(ReadOnlyProxyError):
                getattr(proxy, name)

    def test_denial_is_an_attribute_error(self, proxy: ReadOnlyAttributeProxy) -> None:
        """hasattr()/getattr(default) keep their ordinary meaning."""
        assert issubclass(ReadOnlyProxyError, AttributeError)
        assert hasattr(proxy, "read_value") is True
        assert hasattr(proxy, "mutate") is False
        assert getattr(proxy, "mutate", "fallback") == "fallback"

    def test_denial_names_what_was_denied(self, proxy: ReadOnlyAttributeProxy) -> None:
        """Typed error, not a silent None (zero-tolerance Rule 3)."""
        with pytest.raises(ReadOnlyProxyError) as excinfo:
            proxy.mutate  # noqa: B018
        assert excinfo.value.attribute == "mutate"
        assert excinfo.value.proxy_label == "_Target read-only view"


class TestNoWrites:
    def test_setattr_is_denied(self, proxy: ReadOnlyAttributeProxy) -> None:
        with pytest.raises(ReadOnlyProxyError, match="read-only"):
            proxy.injected = "malicious"

    def test_delattr_is_denied(self, proxy: ReadOnlyAttributeProxy) -> None:
        with pytest.raises(ReadOnlyProxyError, match="read-only"):
            del proxy.name


class TestNoSerializationEscape:
    """Pickle/copy would otherwise reconstruct a handle on the target."""

    @pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
    def test_pickle_is_denied(
        self, proxy: ReadOnlyAttributeProxy, protocol: int
    ) -> None:
        with pytest.raises(pickle.PicklingError):
            pickle.dumps(proxy, protocol)

    def test_shallow_copy_is_denied(self, proxy: ReadOnlyAttributeProxy) -> None:
        with pytest.raises(copy.Error):
            copy.copy(proxy)

    def test_deep_copy_is_denied(self, proxy: ReadOnlyAttributeProxy) -> None:
        with pytest.raises(copy.Error):
            copy.deepcopy(proxy)


class TestIntrospectionStillWorks:
    def test_class_is_readable(self, proxy: ReadOnlyAttributeProxy) -> None:
        assert proxy.__class__ is ReadOnlyAttributeProxy
        assert isinstance(proxy, ReadOnlyAttributeProxy)

    def test_repr_does_not_leak_target_state(
        self, proxy: ReadOnlyAttributeProxy
    ) -> None:
        text = repr(proxy)
        assert "_Target read-only view" in text
        assert "target-name" not in text


class TestAllowlistConstructionIsFailClosed:
    """An allowlist must never be usable to expose internals."""

    @pytest.mark.parametrize("bad", ["_target", "__dict__", "_engine", "not an id"])
    def test_non_public_identifier_rejected(self, target: _Target, bad: str) -> None:
        with pytest.raises(ValueError, match="public identifiers"):
            ReadOnlyAttributeProxy(target, {"name", bad})

    def test_public_identifiers_accepted(self, target: _Target) -> None:
        assert ReadOnlyAttributeProxy(target, {"name"}).name == "target-name"


class TestOverrides:
    def test_override_message_is_used(self, target: _Target) -> None:
        proxy = ReadOnlyAttributeProxy(
            target,
            {"name"},
            label="Custom",
            overrides={"mutate": "mutate is blocked for a specific reason"},
        )
        with pytest.raises(ReadOnlyProxyError, match="a specific reason"):
            proxy.mutate  # noqa: B018

    def test_template_used_when_no_override(self, target: _Target) -> None:
        proxy = ReadOnlyAttributeProxy(
            target,
            {"name"},
            label="Custom",
            message_template="'{label}' refuses '{name}'",
        )
        with pytest.raises(ReadOnlyProxyError, match="'Custom' refuses 'mutate'"):
            proxy.mutate  # noqa: B018


class TestGuardIsOnGetattributeNotGetattr:
    """Pins the structural property that the #2224 fix turns on.

    A ``__getattr__``-only guard is the defect. If someone later "simplifies"
    this class back to ``__getattr__``, the target escapes again -- and every
    deny-assertion above would still pass for names that do not exist on the
    proxy, because ``__getattr__`` IS consulted for those. Only ``_target``
    (a real attribute) distinguishes the two, so the structural assertion is
    the honest pin.
    """

    def test_getattribute_is_overridden(self) -> None:
        assert "__getattribute__" in ReadOnlyAttributeProxy.__dict__

    def test_no_instance_dict_to_leak(self, proxy: ReadOnlyAttributeProxy) -> None:
        assert ReadOnlyAttributeProxy.__slots__
        with pytest.raises(AttributeError):
            object.__getattribute__(proxy, "__dict__")
