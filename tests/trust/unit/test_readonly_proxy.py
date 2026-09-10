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


class TestTargetIsUnreachableByOrdinaryAttributeAccess:
    """Adversarial regressions. Each of these DEFEATED the first version.

    The first fix gated attribute NAMES and stored the target in a slot. That
    left four routes that never touch a denied name, found by an adversarial
    review of the fix itself. All four are pinned here.
    """

    def test_allowlisted_method_is_not_a_bound_method(
        self, proxy: ReadOnlyAttributeProxy, target: _Target
    ) -> None:
        """``view.allowed_method.__self__`` was the target. Two plain reads.

        This is the sharpest one: the caller never touches a denied name, so
        every deny-assertion in this file passed while the allowlist was
        completely defeated.
        """
        forwarder = proxy.read_value
        assert getattr(forwarder, "__self__", None) is not target
        assert getattr(forwarder, "__self__", None) is None
        # and it still forwards
        assert forwarder() == "read-ok"

    def test_forwarder_closure_holds_no_reference_to_the_target(
        self, proxy: ReadOnlyAttributeProxy, target: _Target
    ) -> None:
        """Closing over the bound method would move the leak, not close it."""
        forwarder = proxy.read_value
        cells = [c.cell_contents for c in (forwarder.__closure__ or ())]
        assert target not in cells
        assert not any(getattr(c, "__self__", None) is target for c in cells)

    def test_super_does_not_yield_the_target(self, target: _Target) -> None:
        """``super()`` walks the MRO and never consults __getattribute__.

        Uses a SUBCLASS deliberately: ``super(cls, obj)`` starts AFTER ``cls``
        in the MRO, so this route exists only when the proxy is subclassed --
        which all three real proxies (_ReadOnlyGovernanceView, _ReadOnlyView,
        _ProtectedInnerProxy) are. Testing it on the base class would find
        ``object``, pass trivially, and prove nothing.
        """

        class _Sub(ReadOnlyAttributeProxy):
            __slots__ = ()

        proxy = _Sub(target, {"name"})
        sealed = super(_Sub, proxy)._target
        assert sealed is not target
        with pytest.raises(ReadOnlyProxyError):
            sealed("not-the-token")
        assert proxy.name == "target-name"  # allowed pole intact

    def test_slot_descriptor_does_not_yield_the_target(
        self, proxy: ReadOnlyAttributeProxy, target: _Target
    ) -> None:
        """``__slots__`` installs a member descriptor on the always-reachable
        class; ``type(x)`` needs no attribute access at all."""
        descriptor = ReadOnlyAttributeProxy.__dict__["_target"]
        sealed = descriptor.__get__(proxy)
        assert sealed is not target
        with pytest.raises(ReadOnlyProxyError):
            sealed(object())

    def test_reinitialisation_is_refused(
        self, proxy: ReadOnlyAttributeProxy, target: _Target
    ) -> None:
        """__init__ writes via object.__setattr__, which __setattr__ cannot
        police -- so re-invoking it would widen a live proxy in place."""
        with pytest.raises(ReadOnlyProxyError, match="already initialised"):
            type(proxy).__init__(proxy, target, {"name", "mutate"})
        assert not hasattr(proxy, "mutate")

    def test_no_allowlisted_member_yields_the_target(self, target: _Target) -> None:
        """Sweep: no allowlisted member, nor its __self__, is the target."""
        proxy = ReadOnlyAttributeProxy(target, {"name", "read_value", "mutations"})
        for name in ("name", "read_value", "mutations"):
            value = getattr(proxy, name)
            assert value is not target
            assert getattr(value, "__self__", None) is not target
