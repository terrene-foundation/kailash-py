# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Coverage verification test.

Verifies that all kailash.trust modules are importable and the public API
exports all expected symbols.

    pytest tests/trust/test_coverage_verification.py -v
"""

import importlib
import pkgutil

import pytest


def _get_module_names():
    """Get all importable kailash.trust module names."""
    import kailash.trust

    modules = set()
    for importer, modname, ispkg in pkgutil.walk_packages(
        kailash.trust.__path__, prefix="kailash.trust."
    ):
        modules.add(modname)
    return sorted(modules)


class TestModuleImportability:
    """Verify all trust modules are importable (basic smoke test)."""

    CORE_MODULES = [
        "kailash.trust",
        "kailash.trust.chain",
        "kailash.trust.signing.crypto",
        "kailash.trust.exceptions",
        "kailash.trust.posture.postures",
        "kailash.trust.signing.merkle",
        "kailash.trust.authority",
        "kailash.trust.scoring",
    ]

    OPERATIONS_MODULES = [
        "kailash.trust.operations",
    ]

    STORE_MODULES = [
        "kailash.trust.chain_store",
        "kailash.trust.chain_store.memory",
        "kailash.trust.chain_store.filesystem",
    ]

    CONSTRAINT_MODULES = [
        "kailash.trust.constraints",
        "kailash.trust.constraints.builtin",
        "kailash.trust.constraints.dimension",
        "kailash.trust.constraints.evaluator",
    ]

    ENFORCE_MODULES = [
        "kailash.trust.enforce",
        "kailash.trust.enforce.strict",
        "kailash.trust.enforce.shadow",
        "kailash.trust.enforce.decorators",
        "kailash.trust.enforce.challenge",
        "kailash.trust.enforce.selective_disclosure",
    ]

    INTEROP_MODULES = [
        "kailash.trust.interop",
        "kailash.trust.interop.jwt",
        "kailash.trust.interop.w3c_vc",
        "kailash.trust.interop.did",
        "kailash.trust.interop.ucan",
        "kailash.trust.interop.sd_jwt",
        "kailash.trust.interop.biscuit",
    ]

    TEMPLATE_MODULES = [
        "kailash.trust.templates",
    ]

    CLI_MODULES = [
        "kailash.trust.cli",
        "kailash.trust.cli.commands",
    ]

    @pytest.mark.parametrize("module_name", CORE_MODULES)
    def test_core_modules_importable(self, module_name):
        """Core modules are importable."""
        mod = importlib.import_module(module_name)
        assert mod is not None

    @pytest.mark.parametrize("module_name", OPERATIONS_MODULES)
    def test_operations_modules_importable(self, module_name):
        """Operations modules are importable."""
        mod = importlib.import_module(module_name)
        assert mod is not None

    @pytest.mark.parametrize("module_name", STORE_MODULES)
    def test_store_modules_importable(self, module_name):
        """Store modules are importable."""
        mod = importlib.import_module(module_name)
        assert mod is not None

    @pytest.mark.parametrize("module_name", CONSTRAINT_MODULES)
    def test_constraint_modules_importable(self, module_name):
        """Constraint modules are importable."""
        mod = importlib.import_module(module_name)
        assert mod is not None

    @pytest.mark.parametrize("module_name", ENFORCE_MODULES)
    def test_enforce_modules_importable(self, module_name):
        """Enforce modules are importable."""
        mod = importlib.import_module(module_name)
        assert mod is not None

    @pytest.mark.parametrize("module_name", INTEROP_MODULES)
    def test_interop_modules_importable(self, module_name):
        """Interop modules are importable."""
        mod = importlib.import_module(module_name)
        assert mod is not None

    @pytest.mark.parametrize("module_name", TEMPLATE_MODULES)
    def test_template_modules_importable(self, module_name):
        """Template modules are importable."""
        mod = importlib.import_module(module_name)
        assert mod is not None

    @pytest.mark.parametrize("module_name", CLI_MODULES)
    def test_cli_modules_importable(self, module_name):
        """CLI modules are importable."""
        mod = importlib.import_module(module_name)
        assert mod is not None


class TestPublicAPICompleteness:
    """Verify the public API exports all expected symbols."""

    def test_init_exports_trust_operations(self):
        """TrustOperations is exported from kailash.trust."""
        from kailash.trust import TrustOperations

        assert TrustOperations is not None

    def test_init_exports_chain_types(self):
        """Chain types are exported from kailash.trust."""
        from kailash.trust import (
            AuditAnchor,
            AuthorityType,
            CapabilityAttestation,
            CapabilityType,
            ConstraintEnvelope,
            DelegationRecord,
            GenesisRecord,
            TrustLineageChain,
            VerificationLevel,
            VerificationResult,
        )

        assert all(
            t is not None
            for t in [
                GenesisRecord,
                CapabilityAttestation,
                DelegationRecord,
                ConstraintEnvelope,
                AuditAnchor,
                TrustLineageChain,
                VerificationResult,
                VerificationLevel,
                AuthorityType,
                CapabilityType,
            ]
        )

    def test_init_exports_crypto(self):
        """Crypto functions are exported from kailash.trust."""
        from kailash.trust import generate_keypair, sign, verify_signature

        assert all(f is not None for f in [generate_keypair, sign, verify_signature])

    def test_init_exports_stores(self):
        """Store types are importable from submodules."""
        from kailash.trust.chain_store.memory import InMemoryTrustStore

        assert InMemoryTrustStore is not None

    def test_init_exports_authority(self):
        """Authority types are exported from kailash.trust."""
        from kailash.trust import AuthorityPermission, OrganizationalAuthority

        assert OrganizationalAuthority is not None
        assert AuthorityPermission is not None

    def test_init_exports_postures(self):
        """Posture types are exported from kailash.trust."""
        from kailash.trust import PostureStateMachine, TrustPosture

        assert TrustPosture is not None
        assert PostureStateMachine is not None

    def test_init_exports_exceptions(self):
        """Exception types are exported from kailash.trust."""
        from kailash.trust import TrustChainNotFoundError, TrustError

        assert TrustError is not None
        assert TrustChainNotFoundError is not None

    def test_version_defined(self):
        """Package version is defined."""
        import kailash.trust

        assert hasattr(kailash.trust, "__version__")
        # Version should be a valid semver string, not hardcoded to a specific version
        assert isinstance(kailash.trust.__version__, str)
        assert len(kailash.trust.__version__.split(".")) == 3

    def test_all_list_complete(self):
        """__all__ list contains all public symbols."""
        import kailash.trust

        assert hasattr(kailash.trust, "__all__")
        assert len(kailash.trust.__all__) >= 15
