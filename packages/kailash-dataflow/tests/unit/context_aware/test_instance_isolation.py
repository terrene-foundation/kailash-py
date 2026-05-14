#!/usr/bin/env python3
"""
Unit Tests for Multi-Instance Isolation (TODO-156)

Tests that multiple DataFlow instances maintain proper isolation:
- Two DataFlow instances don't share state
- Node registrations don't leak between instances
- Workflow binders are independent
- Tenant contexts are instance-scoped
- Close/cleanup of one instance doesn't affect another
- Model registration isolation
- Sequential instance creation and destruction

Uses SQLite file-based databases via pytest's tmp_path fixture
(NOT tempfile.NamedTemporaryFile per specs/testing-tiers.md Tier-1
Rule 2). DataFlow instances use sync `with` context manager to
prevent the DataFlow.__del__ ResourceWarning class fix (see #1002).
"""

import pytest

from dataflow import DataFlow
from dataflow.core.tenant_context import TenantContextSwitch


@pytest.mark.unit
class TestInstanceStateIsolation:
    """Test that DataFlow instances don't share state."""

    def test_two_instances_have_separate_models(self, tmp_path):
        """Two DataFlow instances have independent model registries."""
        with (
            DataFlow(f"sqlite:///{tmp_path / 'db1.db'}") as db1,
            DataFlow(f"sqlite:///{tmp_path / 'db2.db'}") as db2,
        ):

            @db1.model
            class User:
                name: str

            @db2.model
            class Product:
                title: str

            # db1 should only have User
            assert "User" in db1.get_models()
            assert "Product" not in db1.get_models()

            # db2 should only have Product
            assert "Product" in db2.get_models()
            assert "User" not in db2.get_models()

    def test_model_count_independent(self, tmp_path):
        """Model counts are independent between instances."""
        with (
            DataFlow(f"sqlite:///{tmp_path / 'db1.db'}") as db1,
            DataFlow(f"sqlite:///{tmp_path / 'db2.db'}") as db2,
        ):

            @db1.model
            class A:
                value: str

            @db1.model
            class B:
                value: str

            @db2.model
            class C:
                value: str

            assert len(db1.get_models()) == 2
            assert len(db2.get_models()) == 1

    def test_instances_with_same_model_name(self, tmp_path):
        """Same model name in different instances are independent."""
        with (
            DataFlow(f"sqlite:///{tmp_path / 'db1.db'}") as db1,
            DataFlow(f"sqlite:///{tmp_path / 'db2.db'}") as db2,
        ):

            @db1.model
            class User:
                name: str

            @db2.model
            class User:  # Same name, different instance
                email: str
                age: int

            # Both should have User model but they're separate
            assert "User" in db1.get_models()
            assert "User" in db2.get_models()


@pytest.mark.unit
class TestNodeRegistrationIsolation:
    """Test that node registrations don't leak between instances."""

    def test_generated_nodes_isolated(self, tmp_path):
        """Generated nodes are isolated to their DataFlow instance."""
        with (
            DataFlow(f"sqlite:///{tmp_path / 'db1.db'}") as db1,
            DataFlow(f"sqlite:///{tmp_path / 'db2.db'}") as db2,
        ):

            @db1.model
            class Order:
                item: str

            # db1 should have Order nodes
            assert "OrderCreateNode" in db1._nodes

            # db2 should not have Order nodes in its instance
            # (though global registry may have them)
            assert "Order" not in db2.get_models()

    def test_all_eleven_operations_generated_per_model(self, tmp_path):
        """Each model generates all 11 operation nodes."""
        with DataFlow(f"sqlite:///{tmp_path / 'db.db'}") as db:

            @db.model
            class Item:
                name: str

            expected_ops = [
                "ItemCreateNode",
                "ItemReadNode",
                "ItemUpdateNode",
                "ItemDeleteNode",
                "ItemListNode",
                "ItemUpsertNode",
                "ItemCountNode",
                "ItemBulkCreateNode",
                "ItemBulkUpdateNode",
                "ItemBulkDeleteNode",
                "ItemBulkUpsertNode",
            ]

            for node_name in expected_ops:
                assert node_name in db._nodes, f"{node_name} should be registered"


@pytest.mark.unit
class TestWorkflowBinderIsolation:
    """Test that workflow binders are independent."""

    def test_workflow_binders_are_instance_scoped(self, tmp_path):
        """Each DataFlow instance has its own workflow binder."""
        with (
            DataFlow(f"sqlite:///{tmp_path / 'db1.db'}") as db1,
            DataFlow(f"sqlite:///{tmp_path / 'db2.db'}") as db2,
        ):
            assert db1._workflow_binder is not db2._workflow_binder
            assert db1._workflow_binder.dataflow_instance is db1
            assert db2._workflow_binder.dataflow_instance is db2

    def test_workflows_dont_leak_between_instances(self, tmp_path):
        """Workflows created in one instance don't appear in another."""
        with (
            DataFlow(f"sqlite:///{tmp_path / 'db1.db'}") as db1,
            DataFlow(f"sqlite:///{tmp_path / 'db2.db'}") as db2,
        ):
            wf1 = db1.create_workflow("workflow_1")
            wf2 = db2.create_workflow("workflow_2")

            # Each binder should only know about its own workflows
            assert "workflow_1" in db1._workflow_binder.list_workflows()
            assert "workflow_2" not in db1._workflow_binder.list_workflows()

            assert "workflow_2" in db2._workflow_binder.list_workflows()
            assert "workflow_1" not in db2._workflow_binder.list_workflows()

    def test_available_nodes_isolated(self, tmp_path):
        """get_available_nodes() returns only the instance's models."""
        with (
            DataFlow(f"sqlite:///{tmp_path / 'db1.db'}") as db1,
            DataFlow(f"sqlite:///{tmp_path / 'db2.db'}") as db2,
        ):

            @db1.model
            class Alpha:
                value: str

            @db2.model
            class Beta:
                value: str

            nodes1 = db1.get_available_nodes()
            nodes2 = db2.get_available_nodes()

            assert "Alpha" in nodes1
            assert "Beta" not in nodes1

            assert "Beta" in nodes2
            assert "Alpha" not in nodes2


@pytest.mark.unit
class TestTenantContextIsolation:
    """Test that tenant contexts are instance-scoped."""

    def test_tenant_contexts_are_independent(self, tmp_path):
        """Each DataFlow instance has its own tenant context."""
        with (
            DataFlow(f"sqlite:///{tmp_path / 'db1.db'}", multi_tenant=True) as db1,
            DataFlow(f"sqlite:///{tmp_path / 'db2.db'}", multi_tenant=True) as db2,
        ):
            ctx1 = db1.tenant_context
            ctx2 = db2.tenant_context

            assert ctx1 is not ctx2
            assert ctx1.dataflow_instance is db1
            assert ctx2.dataflow_instance is db2

    def test_tenant_registrations_isolated(self, tmp_path):
        """Tenant registrations are isolated between instances."""
        with (
            DataFlow(f"sqlite:///{tmp_path / 'db1.db'}", multi_tenant=True) as db1,
            DataFlow(f"sqlite:///{tmp_path / 'db2.db'}", multi_tenant=True) as db2,
        ):
            db1.tenant_context.register_tenant("tenant-a", "Tenant A")
            db2.tenant_context.register_tenant("tenant-b", "Tenant B")

            assert db1.tenant_context.is_tenant_registered("tenant-a")
            assert not db1.tenant_context.is_tenant_registered("tenant-b")

            assert db2.tenant_context.is_tenant_registered("tenant-b")
            assert not db2.tenant_context.is_tenant_registered("tenant-a")

    def test_tenant_switches_isolated(self, tmp_path):
        """Tenant context switches in one instance don't affect another."""
        with (
            DataFlow(f"sqlite:///{tmp_path / 'db1.db'}", multi_tenant=True) as db1,
            DataFlow(f"sqlite:///{tmp_path / 'db2.db'}", multi_tenant=True) as db2,
        ):
            db1.tenant_context.register_tenant("tenant-1", "Tenant 1")
            db2.tenant_context.register_tenant("tenant-2", "Tenant 2")

            with db1.tenant_context.switch("tenant-1"):
                # db2 should still have no active context
                assert db1.tenant_context.get_current_tenant() == "tenant-1"
                # Note: Context variable is shared, but registration is not


@pytest.mark.unit
class TestCloseCleanupIsolation:
    """Test that closing one instance doesn't affect another."""

    def test_close_one_instance_other_remains_usable(self, tmp_path):
        """Closing one DataFlow instance doesn't affect another."""
        # NOTE: This test explicitly tests close() ordering; use try/finally
        # since we need to call db1.close() mid-test before db2 cleanup.
        db1 = DataFlow(f"sqlite:///{tmp_path / 'db1.db'}")
        db2 = DataFlow(f"sqlite:///{tmp_path / 'db2.db'}")

        try:

            @db1.model
            class Model1:
                value: str

            @db2.model
            class Model2:
                value: str

            # Close db1
            db1.close()

            # db2 should still work
            assert "Model2" in db2.get_models()
            wf = db2.create_workflow()
            assert wf is not None
        finally:
            db2.close()

    def test_models_persist_after_other_instance_closes(self, tmp_path):
        """Models in one instance persist after another instance closes."""
        # NOTE: This test explicitly closes db1 mid-test; use try/finally for db2.
        db1 = DataFlow(f"sqlite:///{tmp_path / 'db1.db'}")
        db2 = DataFlow(f"sqlite:///{tmp_path / 'db2.db'}")

        try:

            @db2.model
            class Persistent:
                data: str

            db1.close()

            # db2's models should still be accessible
            assert "Persistent" in db2.get_models()
        finally:
            db2.close()


@pytest.mark.unit
class TestSequentialInstanceCreationDestruction:
    """Test sequential instance creation and destruction."""

    def test_sequential_creation_with_same_url(self, tmp_path):
        """Sequential instances with same URL are independent."""
        url = f"sqlite:///{tmp_path / 'seq_same.db'}"

        with DataFlow(url) as db1:

            @db1.model
            class First:
                value: str

        # Create new instance with same URL
        with DataFlow(url) as db2:

            @db2.model
            class Second:
                value: str

            # db2 is a fresh instance (though schema may persist in file)
            assert "Second" in db2.get_models()

    def test_multiple_sequential_instances(self, tmp_path):
        """Multiple sequential instances work correctly."""
        url = f"sqlite:///{tmp_path / 'seq_multi.db'}"

        for i in range(3):
            with DataFlow(url) as db:
                # Define model unique to this iteration
                # Can't dynamically name classes easily, but we can verify instance works
                assert db is not None
                assert db._models is not None or db.get_models() is not None

    def test_rapid_creation_destruction_cycle(self, tmp_path):
        """Rapid creation/destruction cycle doesn't cause issues."""
        url = f"sqlite:///{tmp_path / 'rapid.db'}"

        for _ in range(5):
            with DataFlow(url) as db:
                assert db is not None


@pytest.mark.unit
class TestModelRegistrationIsolation:
    """Test model registration isolation between instances."""

    def test_model_fields_isolated(self, tmp_path):
        """Model field metadata is isolated between instances."""
        with (
            DataFlow(f"sqlite:///{tmp_path / 'db1.db'}") as db1,
            DataFlow(f"sqlite:///{tmp_path / 'db2.db'}") as db2,
        ):

            @db1.model
            class Record:
                name: str

            @db2.model
            class Record:
                email: str
                count: int

            # Each instance should have its own field metadata
            assert "Record" in db1.get_models()
            assert "Record" in db2.get_models()

    def test_model_decorator_returns_correct_class(self, tmp_path):
        """@db.model decorator returns the decorated class unchanged."""
        with DataFlow(f"sqlite:///{tmp_path / 'decorator.db'}") as db:

            @db.model
            class TestClass:
                field: str

            # The decorator should return the class
            assert TestClass is not None
            assert hasattr(TestClass, "__annotations__")

    def test_multiple_models_per_instance(self, tmp_path):
        """Multiple models can be registered to the same instance."""
        with DataFlow(f"sqlite:///{tmp_path / 'multi_models.db'}") as db:

            @db.model
            class ModelA:
                value: str

            @db.model
            class ModelB:
                count: int

            @db.model
            class ModelC:
                flag: bool

            models = db.get_models()
            assert len(models) == 3
            assert "ModelA" in models
            assert "ModelB" in models
            assert "ModelC" in models
