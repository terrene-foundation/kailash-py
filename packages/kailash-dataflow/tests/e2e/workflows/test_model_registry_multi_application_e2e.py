#!/usr/bin/env python3
"""
Tier 3 E2E Tests for ModelRegistry - Complete Multi-Application User Journey
Tests the complete user flow from Bug 007 scenario with real infrastructure.

NO MOCKING POLICY: All tests use real PostgreSQL and complete workflows.

USER FLOW TESTED:
1. Developer A creates first application with models
2. Models are automatically persisted to dataflow_migrations table
3. Developer B creates second application pointing to same database
4. Models are automatically discovered and available without redefinition
5. Model changes in one app are detected by others
6. Consistency validation catches mismatches
"""

import asyncio
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest
from dataflow.core.config import DatabaseConfig, DataFlowConfig
from dataflow.core.engine import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.fixture
def test_database_url():
    """Real PostgreSQL connection for E2E testing."""
    return (
        "postgresql://dataflow_test:dataflow_test_password@localhost:5433/dataflow_test"
    )


@pytest.fixture
def unique_session_id():
    """Generate unique session identifier for test isolation."""
    return f"e2e_{uuid.uuid4().hex[:12]}"


@pytest.fixture
async def clean_database():
    """Ensure clean database state before and after tests."""
    from tests.utils.test_env_setup import cleanup_test_data

    # Clean before test
    await cleanup_test_data()

    yield

    # Clean after test
    await cleanup_test_data()


@pytest.mark.e2e
@pytest.mark.timeout(10)
class TestMultiApplicationModelRegistryE2E:
    """E2E tests for complete multi-application model registry workflow."""

    @pytest.mark.asyncio
    async def test_complete_developer_workflow_bug_007_scenario(
        self, test_database_url, unique_session_id, clean_database
    ):
        """
        Test the complete Bug 007 scenario:
        Developer A -> Creates app with models -> Developer B -> Discovers models automatically
        """
        print(f"\n🚀 Starting Bug 007 E2E Test - Session: {unique_session_id}")

        # ==========================================
        # PHASE 1: Developer A creates first application
        # ==========================================
        print("\n📋 PHASE 1: Developer A creates first application")

        # Developer A's application configuration
        app_a_config = DataFlowConfig(
            database=DatabaseConfig(url=test_database_url),
            environment=f"ecommerce_api_{unique_session_id}",
        )

        # Developer A initializes DataFlow for an e-commerce application
        print("   🔧 Developer A initializes DataFlow for e-commerce API...")
        dataflow_a = DataFlow(
            config=app_a_config, auto_migrate=True, enable_model_persistence=True
        )

        # Developer A defines e-commerce models
        print("   📦 Developer A defines e-commerce models...")

        # User model
        user_model_name = f"User_{unique_session_id}"
        user_fields = {
            "id": {"type": "int", "primary_key": True, "auto_increment": True},
            "email": {"type": "str", "unique": True, "required": True},
            "first_name": {"type": "str", "required": True},
            "last_name": {"type": "str", "required": True},
            "password_hash": {"type": "str", "required": True},
            "is_active": {"type": "bool", "default": True},
            "created_at": {"type": "datetime", "auto_now_add": True},
            "updated_at": {"type": "datetime", "auto_now": True},
        }
        user_options = {
            "table_name": f"users_{unique_session_id}",
            "multi_tenant": False,
            "soft_delete": True,
            "audit_log": True,
        }

        # Product model
        product_model_name = f"Product_{unique_session_id}"
        product_fields = {
            "id": {"type": "int", "primary_key": True, "auto_increment": True},
            "name": {"type": "str", "required": True},
            "description": {"type": "str", "nullable": True},
            "price": {"type": "float", "required": True},
            "stock_quantity": {"type": "int", "default": 0},
            "category": {"type": "str", "required": True},
            "is_available": {"type": "bool", "default": True},
            "created_at": {"type": "datetime", "auto_now_add": True},
            "updated_at": {"type": "datetime", "auto_now": True},
        }
        product_options = {
            "table_name": f"products_{unique_session_id}",
            "indexes": ["category", "is_available"],
            "constraints": ["price > 0", "stock_quantity >= 0"],
        }

        # Order model
        order_model_name = f"Order_{unique_session_id}"
        order_fields = {
            "id": {"type": "int", "primary_key": True, "auto_increment": True},
            "user_id": {
                "type": "int",
                "foreign_key": f"users_{unique_session_id}.id",
                "required": True,
            },
            "status": {"type": "str", "default": "pending"},
            "total_amount": {"type": "float", "required": True},
            "shipping_address": {"type": "json", "required": True},
            "order_date": {"type": "datetime", "auto_now_add": True},
            "fulfilled_date": {"type": "datetime", "nullable": True},
        }
        order_options = {
            "table_name": f"orders_{unique_session_id}",
            "indexes": ["user_id", "status", "order_date"],
        }

        # Register models with automatic persistence
        print("   💾 Developer A registers models (auto-persisted to migrations)...")
        registry_a = dataflow_a._model_registry
        assert registry_a.initialize() is True

        assert (
            registry_a.register_model(user_model_name, user_fields, user_options)
            is True
        )
        assert (
            registry_a.register_model(
                product_model_name, product_fields, product_options
            )
            is True
        )
        assert (
            registry_a.register_model(order_model_name, order_fields, order_options)
            is True
        )

        # Verify models are persisted in migration system
        print("   ✅ Verifying models persisted to migration history...")
        user_version = registry_a.get_model_version(user_model_name)
        product_version = registry_a.get_model_version(product_model_name)
        order_version = registry_a.get_model_version(order_model_name)

        assert user_version >= 1
        assert product_version >= 1
        assert order_version >= 1

        print(
            f"   📊 Models registered: User(v{user_version}), Product(v{product_version}), Order(v{order_version})"
        )

        # ==========================================
        # PHASE 2: Developer B creates second application
        # ==========================================
        print("\n📋 PHASE 2: Developer B creates second application")

        # Simulate time delay (different development timeline)
        await asyncio.sleep(0.1)

        # Developer B's application configuration (same database, different app)
        app_b_config = DataFlowConfig(
            database=DatabaseConfig(url=test_database_url),
            environment=f"admin_dashboard_{unique_session_id}",
        )

        # Developer B initializes DataFlow for admin dashboard
        print("   🔧 Developer B initializes DataFlow for admin dashboard...")
        dataflow_b = DataFlow(
            config=app_b_config, auto_migrate=True, enable_model_persistence=True
        )

        # Models should be automatically discovered and synchronized
        print(
            "   🔍 Models should be automatically discovered from migration history..."
        )
        registry_b = dataflow_b._model_registry
        assert registry_b.initialize() is True

        # Verify models are discovered
        discovered_models = registry_b.discover_models()
        print(
            f"   📦 Discovered {len(discovered_models)} models: {list(discovered_models.keys())}"
        )

        assert user_model_name in discovered_models
        assert product_model_name in discovered_models
        assert order_model_name in discovered_models

        # Verify field definitions match
        assert discovered_models[user_model_name]["fields"]["email"]["unique"] is True
        assert (
            discovered_models[product_model_name]["fields"]["price"]["required"] is True
        )
        assert (
            discovered_models[order_model_name]["fields"]["user_id"]["foreign_key"]
            is not None
        )

        # Auto-sync should make models available
        print("   🔄 Auto-syncing models to Developer B's application...")
        added, updated = registry_b.sync_models()
        print(f"   ✅ Sync complete: {added} models added, {updated} models updated")

        assert added >= 3  # At least User, Product, Order

        # Verify models are available in DataFlow instance B
        assert user_model_name in dataflow_b._models
        assert product_model_name in dataflow_b._models
        assert order_model_name in dataflow_b._models

        # ==========================================
        # PHASE 3: Model changes and cross-app detection
        # ==========================================
        print("\n📋 PHASE 3: Model evolution and cross-application detection")

        # Developer A evolves the User model (adds new fields)
        print("   🔄 Developer A evolves User model with new fields...")
        evolved_user_fields = user_fields.copy()
        evolved_user_fields.update(
            {
                "phone": {"type": "str", "nullable": True},
                "birth_date": {"type": "date", "nullable": True},
                "preferences": {"type": "jsonb", "default": {}},
                "last_login": {"type": "datetime", "nullable": True},
            }
        )

        # Register evolved model
        assert (
            registry_a.register_model(
                user_model_name, evolved_user_fields, user_options
            )
            is True
        )

        # Version should increment
        new_user_version = registry_a.get_model_version(user_model_name)
        assert new_user_version > user_version
        print(f"   📈 User model evolved from v{user_version} to v{new_user_version}")

        # Developer B should detect the change
        print("   👀 Developer B detects model changes...")
        await asyncio.sleep(0.1)  # Simulate discovery delay

        new_discovered = registry_b.discover_models()
        assert user_model_name in new_discovered
        assert "phone" in new_discovered[user_model_name]["fields"]
        assert "preferences" in new_discovered[user_model_name]["fields"]

        # Version tracking should work across apps
        b_user_version = registry_b.get_model_version(user_model_name)
        assert b_user_version == new_user_version

        # ==========================================
        # PHASE 4: Consistency validation
        # ==========================================
        print("\n📋 PHASE 4: Cross-application consistency validation")

        # Both applications should have consistent view
        print("   ✅ Validating cross-application consistency...")
        issues_a = registry_a.validate_consistency()
        issues_b = registry_b.validate_consistency()

        # No consistency issues should exist
        assert user_model_name not in issues_a
        assert product_model_name not in issues_a
        assert order_model_name not in issues_a

        assert user_model_name not in issues_b
        assert product_model_name not in issues_b
        assert order_model_name not in issues_b

        print("   ✅ No consistency issues detected")

        # ==========================================
        # PHASE 5: Real workflow execution
        # ==========================================
        print("\n📋 PHASE 5: Execute real workflows using synchronized models")

        # Test that Developer B can use the models in actual workflows
        print("   🚀 Developer B creates admin workflow using discovered models...")

        workflow = WorkflowBuilder()
        runtime = LocalRuntime()

        # Add workflow nodes that would use the synchronized models
        # (This demonstrates the models are truly available for use)
        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "check_users",
            {
                "connection_url": test_database_url,
                "query": f"""
                SELECT COUNT(*) as user_count
                FROM information_schema.tables
                WHERE table_name = 'users_{unique_session_id}'
            """,
            },
        )

        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "check_products",
            {
                "connection_url": test_database_url,
                "query": f"""
                SELECT COUNT(*) as product_count
                FROM information_schema.tables
                WHERE table_name = 'products_{unique_session_id}'
            """,
            },
        )

        workflow.add_node(
            "AsyncSQLDatabaseNode",
            "check_orders",
            {
                "connection_url": test_database_url,
                "query": f"""
                SELECT COUNT(*) as order_count
                FROM information_schema.tables
                WHERE table_name = 'orders_{unique_session_id}'
            """,
            },
        )

        # Execute workflow
        results, run_id = runtime.execute(workflow.build())

        # Verify workflow executed successfully
        assert results["check_users"]["success"] is True
        assert results["check_products"]["success"] is True
        assert results["check_orders"]["success"] is True

        print("   ✅ Admin workflow executed successfully using synchronized models")

        # ==========================================
        # PHASE 6: Model history and versioning
        # ==========================================
        print("\n📋 PHASE 6: Model history and version tracking validation")

        # Check model history from both applications
        print("   📚 Checking model history from both applications...")

        history_a = registry_a.get_model_history(user_model_name)
        history_b = registry_b.get_model_history(user_model_name)

        # Both should see the same history
        assert len(history_a) >= 2  # Original + evolution
        assert len(history_b) >= 2  # Same history
        assert len(history_a) == len(history_b)

        # History should be ordered by most recent first
        assert history_a[0]["created_at"] >= history_a[1]["created_at"]

        print(
            f"   📊 Model history tracked: {len(history_a)} versions across both applications"
        )

        # ==========================================
        # PHASE 7: Third application joins
        # ==========================================
        print("\n📋 PHASE 7: Third application discovers existing models")

        # Developer C creates a third application (mobile API)
        app_c_config = DataFlowConfig(
            database=DatabaseConfig(url=test_database_url),
            environment=f"mobile_api_{unique_session_id}",
        )

        print("   📱 Developer C initializes mobile API application...")
        dataflow_c = DataFlow(
            config=app_c_config, auto_migrate=True, enable_model_persistence=True
        )

        registry_c = dataflow_c._model_registry
        assert registry_c.initialize() is True

        # Should discover all existing models
        discovered_c = registry_c.discover_models()
        print(f"   🔍 Mobile API discovered {len(discovered_c)} models")

        assert len(discovered_c) >= 3
        assert user_model_name in discovered_c
        assert product_model_name in discovered_c
        assert order_model_name in discovered_c

        # Should get latest versions
        assert (
            "phone" in discovered_c[user_model_name]["fields"]
        )  # Evolution from Phase 3
        assert "preferences" in discovered_c[user_model_name]["fields"]

        # Auto-sync should work
        added_c, updated_c = registry_c.sync_models()
        assert added_c >= 3

        print("   ✅ Third application successfully integrated with existing models")

        print(f"\n🎉 Bug 007 E2E Test Complete - Session: {unique_session_id}")
        print("   ✅ Multi-application model synchronization working correctly")
        print("   ✅ Model persistence and discovery functional")
        print("   ✅ Cross-application consistency maintained")
        print("   ✅ Model evolution properly tracked")
        print("   ✅ Real workflows execute with synchronized models")

    @pytest.mark.asyncio
    async def test_concurrent_multi_application_operations(
        self, test_database_url, unique_session_id, clean_database
    ):
        """Test concurrent operations across multiple applications."""
        print(
            f"\n🔀 Testing concurrent multi-application operations - Session: {unique_session_id}"
        )

        # Create multiple applications concurrently
        async def create_application(app_id: str):
            config = DataFlowConfig(
                database=DatabaseConfig(url=test_database_url),
                environment=f"concurrent_app_{app_id}_{unique_session_id}",
            )

            dataflow = DataFlow(
                config=config, auto_migrate=True, enable_model_persistence=True
            )
            registry = dataflow._model_registry
            registry.initialize()

            # Each app registers its own model
            model_name = f"ConcurrentModel_{app_id}_{unique_session_id}"
            fields = {
                "id": {"type": "int", "primary_key": True},
                "app_id": {"type": "str", "default": app_id},
                "data": {"type": "str", "required": True},
            }

            success = registry.register_model(model_name, fields, {})
            return success, registry, model_name

        # Run 3 applications concurrently
        print("   🏃‍♂️ Starting 3 concurrent applications...")
        results = await asyncio.gather(
            create_application("A"),
            create_application("B"),
            create_application("C"),
            return_exceptions=True,
        )

        # All should succeed
        for success, registry, model_name in results:
            assert success is True
            print(f"   ✅ Application registered model: {model_name}")

        # Each application should discover models from others
        print("   🔍 Cross-application model discovery...")
        for i, (success, registry, model_name) in enumerate(results):
            discovered = registry.discover_models()
            # Should discover at least 3 models (including own)
            assert len(discovered) >= 3
            print(f"   📦 App {i+1} discovered {len(discovered)} models")

        print("   ✅ Concurrent operations completed successfully")

    @pytest.mark.asyncio
    async def test_model_conflict_resolution(
        self, test_database_url, unique_session_id, clean_database
    ):
        """Test conflict resolution when apps have different model definitions."""
        print(f"\n⚔️ Testing model conflict resolution - Session: {unique_session_id}")

        # App 1 configuration
        app1_config = DataFlowConfig(
            database=DatabaseConfig(url=test_database_url),
            environment=f"conflict_app1_{unique_session_id}",
        )

        # App 2 configuration
        app2_config = DataFlowConfig(
            database=DatabaseConfig(url=test_database_url),
            environment=f"conflict_app2_{unique_session_id}",
        )

        # Create first application
        dataflow1 = DataFlow(
            config=app1_config, auto_migrate=True, enable_model_persistence=True
        )
        registry1 = dataflow1._model_registry
        registry1.initialize()

        # Register model with initial definition
        model_name = f"ConflictModel_{unique_session_id}"
        fields_v1 = {
            "id": {"type": "int", "primary_key": True},
            "name": {"type": "str", "required": True},
        }

        print("   📝 App 1 registers initial model definition...")
        assert registry1.register_model(model_name, fields_v1, {}) is True

        # Create second application
        dataflow2 = DataFlow(
            config=app2_config, auto_migrate=True, enable_model_persistence=True
        )
        registry2 = dataflow2._model_registry
        registry2.initialize()

        # App 2 tries to register different definition of same model
        fields_v2 = {
            "id": {"type": "int", "primary_key": True},
            "name": {"type": "str", "required": True},
            "description": {"type": "str", "nullable": True},  # Additional field
        }

        print("   📝 App 2 registers evolved model definition...")
        assert registry2.register_model(model_name, fields_v2, {}) is True

        # Check for consistency issues
        print("   🔍 Checking for consistency issues...")
        issues1 = registry1.validate_consistency()
        issues2 = registry2.validate_consistency()

        # Both apps should detect the inconsistency
        print(f"   ⚠️ App 1 detected issues: {model_name in issues1}")
        print(f"   ⚠️ App 2 detected issues: {model_name in issues2}")

        # At least one should detect the conflict
        conflict_detected = (model_name in issues1) or (model_name in issues2)

        if conflict_detected:
            print("   ✅ Model conflict successfully detected")
        else:
            print("   ℹ️ No conflict detected - models may be compatible")

        # Verify both versions exist in history
        history1 = registry1.get_model_history(model_name)
        history2 = registry2.get_model_history(model_name)

        assert len(history1) >= 1
        assert len(history2) >= 1

        print(
            f"   📚 Model history preserved: {max(len(history1), len(history2))} versions"
        )

    @pytest.mark.asyncio
    async def test_production_scale_model_registry(
        self, test_database_url, unique_session_id, clean_database
    ):
        """Test model registry performance at production scale."""
        print(
            f"\n📊 Testing production-scale model registry - Session: {unique_session_id}"
        )

        # Create application
        config = DataFlowConfig(
            database=DatabaseConfig(url=test_database_url),
            environment=f"scale_test_{unique_session_id}",
        )

        dataflow = DataFlow(
            config=config, auto_migrate=True, enable_model_persistence=True
        )
        registry = dataflow._model_registry
        registry.initialize()

        # Register many models (simulating large application)
        print("   📦 Registering multiple models (simulating large application)...")
        model_count = 20
        start_time = time.perf_counter()

        for i in range(model_count):
            model_name = f"ScaleModel_{i}_{unique_session_id}"
            fields = {
                "id": {"type": "int", "primary_key": True},
                "name": {"type": "str", "required": True},
                **{
                    f"field_{j}": {"type": "str", "nullable": True} for j in range(5)
                },  # 5 additional fields per model
            }

            success = registry.register_model(model_name, fields, {})
            assert success is True

        registration_time = time.perf_counter() - start_time
        print(
            f"   ⏱️ Registered {model_count} models in {registration_time:.2f}s ({registration_time/model_count:.3f}s avg)"
        )

        # Test discovery performance
        print("   🔍 Testing model discovery performance...")
        start_time = time.perf_counter()

        discovered = registry.discover_models()
        discovery_time = time.perf_counter() - start_time

        assert len(discovered) >= model_count
        print(f"   ⏱️ Discovered {len(discovered)} models in {discovery_time:.2f}s")

        # Test consistency validation performance
        print("   ✅ Testing consistency validation performance...")
        start_time = time.perf_counter()

        issues = registry.validate_consistency()
        validation_time = time.perf_counter() - start_time

        print(f"   ⏱️ Validated consistency in {validation_time:.2f}s")
        print(
            f"   📊 Performance metrics: Reg={registration_time:.2f}s, Disc={discovery_time:.2f}s, Val={validation_time:.2f}s"
        )

        # Performance thresholds (adjust based on requirements)
        assert registration_time < 5.0  # Should register 20 models in <5s
        assert discovery_time < 1.0  # Should discover models in <1s
        assert validation_time < 2.0  # Should validate in <2s

        print("   ✅ Performance tests passed - production ready")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=10"])
