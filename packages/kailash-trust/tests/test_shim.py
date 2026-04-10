# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the eatp.* -> kailash.trust.* backward-compatibility shim.

Verifies three properties for every shim module:
1. Import succeeds and returns the correct class/function.
2. The re-exported symbol IS the same object as the canonical one.
3. A DeprecationWarning is emitted on import.
"""

from __future__ import annotations

import importlib
import sys
import warnings
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_import(module_name: str) -> Any:
    """Import *module_name* after evicting it (and its parents) from sys.modules.

    This guarantees the module-level ``warnings.warn()`` fires again, which
    is necessary because Python caches imported modules.
    """
    # Remove the target and all parent eatp.* modules so the warning fires
    to_remove = [k for k in sys.modules if k == module_name or k.startswith("eatp")]
    for key in to_remove:
        del sys.modules[key]
    return importlib.import_module(module_name)


def _assert_deprecation_warning(module_name: str) -> None:
    """Assert that importing *module_name* emits a DeprecationWarning."""
    # Evict first so the top-level warn() runs again
    to_remove = [k for k in sys.modules if k == module_name or k.startswith("eatp")]
    for key in to_remove:
        del sys.modules[key]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module(module_name)

    deprecation_msgs = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert (
        len(deprecation_msgs) >= 1
    ), f"Expected DeprecationWarning from {module_name}, got: {caught}"
    # Verify the warning message mentions the module
    assert any("deprecated" in str(w.message).lower() for w in deprecation_msgs)


# ---------------------------------------------------------------------------
# eatp (top-level package)
# ---------------------------------------------------------------------------


class TestEatpPackage:
    def test_import_emits_deprecation(self) -> None:
        _assert_deprecation_warning("eatp")


# ---------------------------------------------------------------------------
# eatp.execution_context
# ---------------------------------------------------------------------------


class TestExecutionContext:
    def test_deprecation_warning(self) -> None:
        _assert_deprecation_warning("eatp.execution_context")

    def test_execution_context_is_canonical(self) -> None:
        from eatp.execution_context import ExecutionContext as ShimEC
        from kailash.trust.execution_context import ExecutionContext as CanonicalEC

        assert ShimEC is CanonicalEC

    def test_human_origin_is_canonical(self) -> None:
        from eatp.execution_context import HumanOrigin as ShimHO
        from kailash.trust.execution_context import HumanOrigin as CanonicalHO

        assert ShimHO is CanonicalHO

    def test_context_functions_re_exported(self) -> None:
        from eatp.execution_context import (
            execution_context,
            get_current_context,
            get_delegation_chain,
            get_human_origin,
            get_trace_id,
            require_current_context,
            set_current_context,
        )
        from kailash.trust.execution_context import execution_context as canon_ec
        from kailash.trust.execution_context import get_current_context as canon_gcc

        assert execution_context is canon_ec
        assert get_current_context is canon_gcc

    def test_all_exports(self) -> None:
        import eatp.execution_context as mod

        assert "ExecutionContext" in mod.__all__
        assert "HumanOrigin" in mod.__all__


# ---------------------------------------------------------------------------
# eatp.pseudo_agent
# ---------------------------------------------------------------------------


class TestPseudoAgent:
    def test_deprecation_warning(self) -> None:
        _assert_deprecation_warning("eatp.pseudo_agent")

    def test_pseudo_agent_is_canonical(self) -> None:
        from eatp.pseudo_agent import PseudoAgent as ShimPA
        from kailash.trust.agents.pseudo_agent import PseudoAgent as CanonicalPA

        assert ShimPA is CanonicalPA

    def test_pseudo_agent_config_is_canonical(self) -> None:
        from eatp.pseudo_agent import PseudoAgentConfig as ShimPAC
        from kailash.trust.agents.pseudo_agent import PseudoAgentConfig as CanonicalPAC

        assert ShimPAC is CanonicalPAC

    def test_auth_provider_is_canonical(self) -> None:
        from eatp.pseudo_agent import AuthProvider as ShimAP
        from kailash.trust.agents.pseudo_agent import AuthProvider as CanonicalAP

        assert ShimAP is CanonicalAP

    def test_all_exports(self) -> None:
        import eatp.pseudo_agent as mod

        assert "PseudoAgent" in mod.__all__
        assert "PseudoAgentConfig" in mod.__all__
        assert "AuthProvider" in mod.__all__
        assert "PseudoAgentFactory" in mod.__all__


# ---------------------------------------------------------------------------
# eatp.operations
# ---------------------------------------------------------------------------


class TestOperations:
    def test_deprecation_warning(self) -> None:
        _assert_deprecation_warning("eatp.operations")

    def test_trust_operations_is_canonical(self) -> None:
        from eatp.operations import TrustOperations as ShimTO
        from kailash.trust.operations import TrustOperations as CanonicalTO

        assert ShimTO is CanonicalTO

    def test_trust_key_manager_is_canonical(self) -> None:
        from eatp.operations import TrustKeyManager as ShimTKM
        from kailash.trust.operations import TrustKeyManager as CanonicalTKM

        assert ShimTKM is CanonicalTKM

    def test_all_exports(self) -> None:
        import eatp.operations as mod

        assert "TrustOperations" in mod.__all__
        assert "TrustKeyManager" in mod.__all__
        assert "CapabilityRequest" in mod.__all__


# ---------------------------------------------------------------------------
# eatp.authority
# ---------------------------------------------------------------------------


class TestAuthority:
    def test_deprecation_warning(self) -> None:
        _assert_deprecation_warning("eatp.authority")

    def test_organizational_authority_is_canonical(self) -> None:
        from eatp.authority import OrganizationalAuthority as ShimOA
        from kailash.trust.authority import OrganizationalAuthority as CanonicalOA

        assert ShimOA is CanonicalOA

    def test_all_exports(self) -> None:
        import eatp.authority as mod

        assert "OrganizationalAuthority" in mod.__all__
        assert "AuthorityPermission" in mod.__all__
        assert "AuthorityRegistryProtocol" in mod.__all__


# ---------------------------------------------------------------------------
# eatp.exceptions
# ---------------------------------------------------------------------------


class TestExceptions:
    def test_deprecation_warning(self) -> None:
        _assert_deprecation_warning("eatp.exceptions")

    def test_trust_error_is_canonical(self) -> None:
        from eatp.exceptions import TrustError as ShimTE
        from kailash.trust.exceptions import TrustError as CanonicalTE

        assert ShimTE is CanonicalTE

    def test_authority_not_found_is_canonical(self) -> None:
        from eatp.exceptions import AuthorityNotFoundError as ShimANF
        from kailash.trust.exceptions import AuthorityNotFoundError as CanonicalANF

        assert ShimANF is CanonicalANF

    def test_authority_inactive_is_canonical(self) -> None:
        from eatp.exceptions import AuthorityInactiveError as ShimAIE
        from kailash.trust.exceptions import AuthorityInactiveError as CanonicalAIE

        assert ShimAIE is CanonicalAIE

    def test_all_exports(self) -> None:
        import eatp.exceptions as mod

        assert "TrustError" in mod.__all__
        assert "AuthorityNotFoundError" in mod.__all__
        assert "AuthorityInactiveError" in mod.__all__
        assert "ConstraintViolationError" in mod.__all__
        assert "InvalidSignatureError" in mod.__all__


# ---------------------------------------------------------------------------
# eatp.store / eatp.store.memory
# ---------------------------------------------------------------------------


class TestStore:
    def test_store_deprecation_warning(self) -> None:
        _assert_deprecation_warning("eatp.store")

    def test_store_memory_deprecation_warning(self) -> None:
        _assert_deprecation_warning("eatp.store.memory")

    def test_trust_store_is_canonical(self) -> None:
        from eatp.store import TrustStore as ShimTS
        from kailash.trust.chain_store import TrustStore as CanonicalTS

        assert ShimTS is CanonicalTS

    def test_in_memory_trust_store_is_canonical(self) -> None:
        from eatp.store.memory import InMemoryTrustStore as ShimIMTS
        from kailash.trust.chain_store.memory import InMemoryTrustStore as CanonicalIMTS

        assert ShimIMTS is CanonicalIMTS

    def test_all_exports(self) -> None:
        import eatp.store as mod
        import eatp.store.memory as mem_mod

        assert "TrustStore" in mod.__all__
        assert "InMemoryTrustStore" in mem_mod.__all__


# ---------------------------------------------------------------------------
# eatp.chain
# ---------------------------------------------------------------------------


class TestChain:
    def test_deprecation_warning(self) -> None:
        _assert_deprecation_warning("eatp.chain")

    def test_verification_level_is_canonical(self) -> None:
        from eatp.chain import VerificationLevel as ShimVL
        from kailash.trust.chain import VerificationLevel as CanonicalVL

        assert ShimVL is CanonicalVL

    def test_genesis_record_is_canonical(self) -> None:
        from eatp.chain import GenesisRecord as ShimGR
        from kailash.trust.chain import GenesisRecord as CanonicalGR

        assert ShimGR is CanonicalGR

    def test_constraint_envelope_alias(self) -> None:
        from eatp.chain import ChainConstraintEnvelope, ConstraintEnvelope

        assert ConstraintEnvelope is ChainConstraintEnvelope

    def test_all_exports(self) -> None:
        import eatp.chain as mod

        assert "VerificationLevel" in mod.__all__
        assert "GenesisRecord" in mod.__all__
        assert "ConstraintEnvelope" in mod.__all__
        assert "DelegationRecord" in mod.__all__


# ---------------------------------------------------------------------------
# eatp.enforce / eatp.enforce.strict
# ---------------------------------------------------------------------------


class TestEnforce:
    def test_enforce_deprecation_warning(self) -> None:
        _assert_deprecation_warning("eatp.enforce")

    def test_enforce_strict_deprecation_warning(self) -> None:
        _assert_deprecation_warning("eatp.enforce.strict")

    def test_strict_enforcer_is_canonical(self) -> None:
        from eatp.enforce.strict import StrictEnforcer as ShimSE
        from kailash.trust.enforce.strict import StrictEnforcer as CanonicalSE

        assert ShimSE is CanonicalSE

    def test_verdict_is_canonical(self) -> None:
        from eatp.enforce.strict import Verdict as ShimV
        from kailash.trust.enforce.strict import Verdict as CanonicalV

        assert ShimV is CanonicalV

    def test_held_behavior_is_canonical(self) -> None:
        from eatp.enforce.strict import HeldBehavior as ShimHB
        from kailash.trust.enforce.strict import HeldBehavior as CanonicalHB

        assert ShimHB is CanonicalHB

    def test_eatp_blocked_error_is_canonical(self) -> None:
        from eatp.enforce.strict import EATPBlockedError as ShimBE
        from kailash.trust.enforce.strict import EATPBlockedError as CanonicalBE

        assert ShimBE is CanonicalBE

    def test_eatp_held_error_is_canonical(self) -> None:
        from eatp.enforce.strict import EATPHeldError as ShimHE
        from kailash.trust.enforce.strict import EATPHeldError as CanonicalHE

        assert ShimHE is CanonicalHE

    def test_all_exports(self) -> None:
        import eatp.enforce.strict as mod

        assert "StrictEnforcer" in mod.__all__
        assert "Verdict" in mod.__all__
        assert "HeldBehavior" in mod.__all__
        assert "EATPBlockedError" in mod.__all__
        assert "EATPHeldError" in mod.__all__
        assert "EnforcementRecord" in mod.__all__


# ---------------------------------------------------------------------------
# Full symbol matrix from issue #360
# ---------------------------------------------------------------------------


class TestIssue360SymbolMatrix:
    """Verify every symbol listed in the issue's coverage table resolves."""

    def test_execution_context(self) -> None:
        from eatp.execution_context import ExecutionContext  # noqa: F401

    def test_human_origin(self) -> None:
        from eatp.execution_context import HumanOrigin  # noqa: F401

    def test_pseudo_agent(self) -> None:
        from eatp.pseudo_agent import PseudoAgent  # noqa: F401

    def test_pseudo_agent_config(self) -> None:
        from eatp.pseudo_agent import PseudoAgentConfig  # noqa: F401

    def test_auth_provider(self) -> None:
        from eatp.pseudo_agent import AuthProvider  # noqa: F401

    def test_trust_operations(self) -> None:
        from eatp.operations import TrustOperations  # noqa: F401

    def test_trust_key_manager(self) -> None:
        from eatp.operations import TrustKeyManager  # noqa: F401

    def test_organizational_authority(self) -> None:
        from eatp.authority import OrganizationalAuthority  # noqa: F401

    def test_authority_not_found_error(self) -> None:
        from eatp.exceptions import AuthorityNotFoundError  # noqa: F401

    def test_authority_inactive_error(self) -> None:
        from eatp.exceptions import AuthorityInactiveError  # noqa: F401

    def test_in_memory_trust_store(self) -> None:
        from eatp.store.memory import InMemoryTrustStore  # noqa: F401

    def test_verification_level(self) -> None:
        from eatp.chain import VerificationLevel  # noqa: F401

    def test_strict_enforcer(self) -> None:
        from eatp.enforce.strict import StrictEnforcer  # noqa: F401

    def test_held_behavior(self) -> None:
        from eatp.enforce.strict import HeldBehavior  # noqa: F401

    def test_verdict(self) -> None:
        from eatp.enforce.strict import Verdict  # noqa: F401

    def test_eatp_blocked_error(self) -> None:
        from eatp.enforce.strict import EATPBlockedError  # noqa: F401

    def test_eatp_held_error(self) -> None:
        from eatp.enforce.strict import EATPHeldError  # noqa: F401
