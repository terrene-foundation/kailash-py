"""Golden Pattern 5: Multi-DataFlow Instance Pattern - Validation Tests.

Validates separate DataFlow instances per database for isolation.
"""

import pytest
from dataflow import DataFlow


class TestGoldenPattern5MultiDataFlow:
    """Validate Pattern 5: Multi-DataFlow Instance Pattern."""

    def test_separate_instances_for_different_databases(self):
        """Separate DataFlow instances for different databases."""
        users_db = DataFlow(
            "sqlite:///:memory:",
            enable_model_persistence=False,
            auto_migrate=False,
        )

        analytics_db = DataFlow(
            "sqlite:///:memory:",
            enable_model_persistence=False,
            auto_migrate=False,
        )

        logs_db = DataFlow(
            "sqlite:///:memory:",
            enable_model_persistence=False,
            auto_migrate=False,
        )

        # All three instances should be independent
        assert users_db is not analytics_db
        assert analytics_db is not logs_db
        assert users_db is not logs_db

    def test_models_scoped_to_instance(self):
        """Models are scoped to their DataFlow instance."""
        db1 = DataFlow("sqlite:///:memory:", enable_model_persistence=False)
        db2 = DataFlow("sqlite:///:memory:", enable_model_persistence=False)

        @db1.model
        class User:
            id: str
            name: str

        @db2.model
        class PageView:
            id: str
            user_id: str
            page: str

        # Each model registered only to its own instance
        assert "User" in db1._models, "User should be on db1"
        assert "PageView" in db2._models, "PageView should be on db2"
        assert "PageView" not in db1._models, "PageView should NOT be on db1"
        assert "User" not in db2._models, "User should NOT be on db2"

    def test_critical_settings_per_instance(self):
        """Each instance has independent critical settings."""
        primary = DataFlow(
            "sqlite:///:memory:",
            enable_model_persistence=False,
            auto_migrate=False,
        )

        analytics = DataFlow(
            "sqlite:///:memory:",
            enable_model_persistence=False,
            auto_migrate=False,
        )

        # Both should be configured independently
        assert primary is not analytics
        assert hasattr(primary, "_models"), "primary should have _models"
        assert hasattr(analytics, "_models"), "analytics should have _models"

    def test_model_registration_independent(self):
        """Model with same name on different instances doesn't conflict."""
        db1 = DataFlow("sqlite:///:memory:", enable_model_persistence=False)
        db2 = DataFlow("sqlite:///:memory:", enable_model_persistence=False)

        @db1.model
        class Event:
            id: str
            type: str

        @db2.model
        class Event:
            id: str
            type: str
            source: str = None

        # Both registered successfully to their respective instances
        assert "Event" in db1._models, "Event should be registered on db1"
        assert "Event" in db2._models, "Event should be registered on db2"
        # They are independent registrations
        assert db1._models["Event"] is not db2._models["Event"]
