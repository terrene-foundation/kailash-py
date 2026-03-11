#!/usr/bin/env python3
"""
Validation script for PostgresTrustStore implementation.

Performs quick smoke tests to verify:
1. Module imports work
2. DataFlow model is correctly defined
3. Basic operations don't have syntax errors
4. Exception hierarchy is correct

Run with:
    python scripts/validate_trust_store.py
"""

import sys
from datetime import datetime, timedelta


def validate_imports():
    """Validate that all required imports work."""
    print("✓ Validating imports...")

    try:
        from kaizen.trust.store import PostgresTrustStore

        print("  ✓ PostgresTrustStore imported")
    except ImportError as e:
        print(f"  ✗ Failed to import PostgresTrustStore: {e}")
        return False

    try:
        from kaizen.trust import (
            AuthorityType,
            CapabilityAttestation,
            CapabilityType,
            GenesisRecord,
            TrustLineageChain,
        )

        print("  ✓ Trust chain classes imported")
    except ImportError as e:
        print(f"  ✗ Failed to import trust chain classes: {e}")
        return False

    try:
        from kaizen.trust.exceptions import (
            TrustChainInvalidError,
            TrustChainNotFoundError,
            TrustStoreDatabaseError,
            TrustStoreError,
        )

        print("  ✓ Trust store exceptions imported")
    except ImportError as e:
        print(f"  ✗ Failed to import trust store exceptions: {e}")
        return False

    try:
        from dataflow import DataFlow

        print("  ✓ DataFlow imported")
    except ImportError as e:
        print(f"  ✗ Failed to import DataFlow: {e}")
        return False

    try:
        from kailash.runtime import AsyncLocalRuntime

        print("  ✓ AsyncLocalRuntime imported")
    except ImportError as e:
        print(f"  ✗ Failed to import AsyncLocalRuntime: {e}")
        return False

    return True


def validate_dataflow_model():
    """Validate that DataFlow model is correctly defined."""
    print("\n✓ Validating DataFlow model definition...")

    try:
        from kaizen.trust.store import PostgresTrustStore

        # Create store instance (doesn't connect to DB yet)
        store = PostgresTrustStore(
            database_url="postgresql://fake:fake@localhost/fake",
            enable_cache=False,
        )

        # Verify DataFlow instance exists
        assert store.db is not None, "DataFlow instance not created"
        print("  ✓ DataFlow instance created")

        # Verify model class is stored
        assert store._TrustChain is not None, "TrustChain model not stored"
        print("  ✓ TrustChain model class stored")

        # Verify DataFlow generated nodes (they should be in db._nodes)
        expected_nodes = [
            "TrustChain_Create",
            "TrustChain_Read",
            "TrustChain_Update",
            "TrustChain_Delete",
            "TrustChain_List",
            "TrustChain_Upsert",
            "TrustChain_Count",
        ]

        for node_name in expected_nodes:
            if node_name not in store.db._nodes:
                print(f"  ⚠ Warning: {node_name} not found in generated nodes")
            else:
                print(f"  ✓ {node_name} node generated")

        return True

    except Exception as e:
        print(f"  ✗ DataFlow model validation failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def validate_exception_hierarchy():
    """Validate that exception hierarchy is correct."""
    print("\n✓ Validating exception hierarchy...")

    try:
        from kaizen.trust.exceptions import (
            TrustChainInvalidError,
            TrustChainNotFoundError,
            TrustError,
            TrustStoreDatabaseError,
            TrustStoreError,
        )

        # Verify inheritance
        assert issubclass(
            TrustStoreError, TrustError
        ), "TrustStoreError should inherit from TrustError"
        print("  ✓ TrustStoreError inherits from TrustError")

        assert issubclass(
            TrustChainInvalidError, TrustStoreError
        ), "TrustChainInvalidError should inherit from TrustStoreError"
        print("  ✓ TrustChainInvalidError inherits from TrustStoreError")

        assert issubclass(
            TrustStoreDatabaseError, TrustStoreError
        ), "TrustStoreDatabaseError should inherit from TrustStoreError"
        print("  ✓ TrustStoreDatabaseError inherits from TrustStoreError")

        # Verify exception instantiation
        exc1 = TrustChainNotFoundError("test-agent")
        assert "test-agent" in str(exc1), "Exception message should contain agent_id"
        print("  ✓ TrustChainNotFoundError instantiates correctly")

        exc2 = TrustChainInvalidError("Test error", agent_id="test-agent")
        assert "Test error" in str(
            exc2
        ), "Exception message should contain custom message"
        print("  ✓ TrustChainInvalidError instantiates correctly")

        exc3 = TrustStoreDatabaseError("DB error", operation="store_chain")
        assert "DB error" in str(exc3), "Exception message should contain error message"
        print("  ✓ TrustStoreDatabaseError instantiates correctly")

        return True

    except Exception as e:
        print(f"  ✗ Exception hierarchy validation failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def validate_trust_chain_serialization():
    """Validate that trust chain serialization works."""
    print("\n✓ Validating trust chain serialization...")

    try:
        from kaizen.trust import (
            AuthorityType,
            CapabilityAttestation,
            CapabilityType,
            GenesisRecord,
            TrustLineageChain,
        )

        # Create a sample trust chain
        genesis = GenesisRecord(
            id="genesis-test",
            agent_id="agent-test",
            authority_id="org-test",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=365),
            signature="test-signature",
        )

        capability = CapabilityAttestation(
            id="cap-test",
            capability="test:capability",
            capability_type=CapabilityType.ACCESS,
            constraints=["test:constraint"],
            attester_id="org-test",
            attested_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=90),
            signature="cap-signature",
        )

        chain = TrustLineageChain(
            genesis=genesis,
            capabilities=[capability],
        )

        # Test serialization
        chain_dict = chain.to_dict()
        assert "genesis" in chain_dict, "Serialized chain should have genesis"
        assert "capabilities" in chain_dict, "Serialized chain should have capabilities"
        assert "chain_hash" in chain_dict, "Serialized chain should have chain_hash"
        print("  ✓ Chain serialization to dict works")

        # Test deserialization
        restored_chain = TrustLineageChain.from_dict(chain_dict)
        assert (
            restored_chain.genesis.agent_id == "agent-test"
        ), "Deserialized chain should preserve agent_id"
        assert (
            len(restored_chain.capabilities) == 1
        ), "Deserialized chain should preserve capabilities"
        print("  ✓ Chain deserialization from dict works")

        # Test hash computation
        hash1 = chain.hash()
        hash2 = restored_chain.hash()
        assert hash1 == hash2, "Hash should be same for original and restored chain"
        print("  ✓ Chain hash computation is deterministic")

        return True

    except Exception as e:
        print(f"  ✗ Trust chain serialization validation failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def validate_store_methods_syntax():
    """Validate that store methods have correct syntax (no runtime execution)."""
    print("\n✓ Validating store methods syntax...")

    try:
        import inspect

        from kaizen.trust.store import PostgresTrustStore

        store = PostgresTrustStore(
            database_url="postgresql://fake:fake@localhost/fake",
            enable_cache=False,
        )

        # Check that all required methods exist
        required_methods = [
            "initialize",
            "store_chain",
            "get_chain",
            "update_chain",
            "delete_chain",
            "list_chains",
            "count_chains",
            "verify_chain_integrity",
            "close",
        ]

        for method_name in required_methods:
            assert hasattr(
                store, method_name
            ), f"Store should have {method_name} method"
            method = getattr(store, method_name)
            assert callable(method), f"{method_name} should be callable"

            # Check if method is async
            if method_name != "__init__":
                assert inspect.iscoroutinefunction(
                    method
                ), f"{method_name} should be async"

            print(f"  ✓ {method_name}() exists and is async")

        return True

    except Exception as e:
        print(f"  ✗ Store methods syntax validation failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all validation checks."""
    print("=" * 60)
    print("PostgresTrustStore Validation")
    print("=" * 60)

    checks = [
        ("Imports", validate_imports),
        ("DataFlow Model", validate_dataflow_model),
        ("Exception Hierarchy", validate_exception_hierarchy),
        ("Trust Chain Serialization", validate_trust_chain_serialization),
        ("Store Methods Syntax", validate_store_methods_syntax),
    ]

    results = []
    for name, check in checks:
        try:
            result = check()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ {name} check failed with exception: {e}")
            import traceback

            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} checks passed")

    if passed == total:
        print("\n🎉 All validation checks passed!")
        print("\nNext steps:")
        print("1. Set POSTGRES_URL environment variable")
        print("2. Run tests: pytest tests/trust/test_postgres_store.py -v")
        print("3. Run examples: python -m examples.trust_store_usage")
        return 0
    else:
        print("\n⚠️  Some validation checks failed. Review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
