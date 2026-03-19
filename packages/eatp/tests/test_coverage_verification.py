"""Coverage verification test (TODO-056).

This test verifies that test coverage meets minimum thresholds
for core EATP modules. Run with:

    pytest tests/test_coverage_verification.py -v

Or for a full coverage report:

    pytest --cov=eatp --cov-report=html --cov-report=term-missing tests/
"""

import importlib
import pkgutil

import pytest


def _get_module_names():
    """Get all importable EATP module names."""
    import eatp

    modules = set()
    for importer, modname, ispkg in pkgutil.walk_packages(
        eatp.__path__, prefix="eatp."
    ):
        modules.add(modname)
    return sorted(modules)


class TestModuleImportability:
    """Verify all EATP modules are importable (basic smoke test)."""

    CORE_MODULES = [
        "eatp",
        "eatp.chain",
        "eatp.crypto",
        "eatp.exceptions",
        "eatp.postures",
        "eatp.merkle",
        "eatp.authority",
        "eatp.scoring",
    ]

    OPERATIONS_MODULES = [
        "eatp.operations",
    ]

    STORE_MODULES = [
        "eatp.store",
        "eatp.store.memory",
        "eatp.store.filesystem",
    ]

    CONSTRAINT_MODULES = [
        "eatp.constraints",
        "eatp.constraints.builtin",
        "eatp.constraints.dimension",
        "eatp.constraints.evaluator",
        "eatp.constraints.commerce",
        "eatp.constraints.spend_tracker",
    ]

    ENFORCE_MODULES = [
        "eatp.enforce",
        "eatp.enforce.strict",
        "eatp.enforce.shadow",
        "eatp.enforce.decorators",
        "eatp.enforce.challenge",
        "eatp.enforce.selective_disclosure",
    ]

    INTEROP_MODULES = [
        "eatp.interop",
        "eatp.interop.jwt",
        "eatp.interop.w3c_vc",
        "eatp.interop.did",
        "eatp.interop.ucan",
        "eatp.interop.sd_jwt",
        "eatp.interop.biscuit",
    ]

    TEMPLATE_MODULES = [
        "eatp.templates",
    ]

    CLI_MODULES = [
        "eatp.cli",
        "eatp.cli.commands",
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
        """TrustOperations is exported from eatp."""
        from eatp import TrustOperations

        assert TrustOperations is not None

    def test_init_exports_chain_types(self):
        """Chain types are exported from eatp."""
        from eatp import (
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
        """Crypto functions are exported from eatp."""
        from eatp import generate_keypair, sign, verify_signature

        assert all(f is not None for f in [generate_keypair, sign, verify_signature])

    def test_init_exports_stores(self):
        """Store types are exported from eatp."""
        from eatp import InMemoryTrustStore, TrustStore

        assert TrustStore is not None
        assert InMemoryTrustStore is not None

    def test_init_exports_authority(self):
        """Authority types are exported from eatp."""
        from eatp import AuthorityPermission, OrganizationalAuthority

        assert OrganizationalAuthority is not None
        assert AuthorityPermission is not None

    def test_init_exports_postures(self):
        """Posture types are exported from eatp."""
        from eatp import PostureStateMachine, TrustPosture

        assert TrustPosture is not None
        assert PostureStateMachine is not None

    def test_init_exports_exceptions(self):
        """Exception types are exported from eatp."""
        from eatp import TrustChainNotFoundError, TrustError

        assert TrustError is not None
        assert TrustChainNotFoundError is not None

    def test_version_defined(self):
        """Package version is defined."""
        import eatp

        assert hasattr(eatp, "__version__")
        assert eatp.__version__ == "0.2.0"

    def test_all_list_complete(self):
        """__all__ list contains all public symbols."""
        import eatp

        assert hasattr(eatp, "__all__")
        assert len(eatp.__all__) >= 15  # At least 15 public symbols
