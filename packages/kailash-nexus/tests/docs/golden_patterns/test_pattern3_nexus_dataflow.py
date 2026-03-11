"""Golden Pattern 3: Nexus + DataFlow Integration - Validation Tests.

Validates the critical configuration for Nexus + DataFlow without blocking.
"""

import pytest
from dataflow import DataFlow
from nexus import Nexus

from kailash.nodes.handler import make_handler_workflow
from kailash.runtime import AsyncLocalRuntime


class TestGoldenPattern3NexusDataFlow:
    """Validate Pattern 3: Nexus + DataFlow Integration."""

    def test_nexus_auto_discovery_false(self):
        """Nexus must use auto_discovery=False with DataFlow."""
        app = Nexus(auto_discovery=False)
        # Should create without blocking
        assert app is not None

    def test_dataflow_critical_settings(self):
        """DataFlow must use critical settings for Nexus integration."""
        db = DataFlow(
            "sqlite:///:memory:",
            enable_model_persistence=False,
            auto_migrate=False,
        )
        assert db is not None

    def test_handler_with_dataflow_model(self):
        """Handler can work with DataFlow models."""
        db = DataFlow("sqlite:///:memory:", enable_model_persistence=False)

        @db.model
        class Contact:
            id: str
            email: str
            name: str
            company_id: str = None

        app = Nexus(auto_discovery=False)

        @app.handler("create_contact")
        async def create_contact(email: str, name: str, company_id: str = None) -> dict:
            return {
                "id": "contact-test-123",
                "email": email,
                "name": name,
                "company_id": company_id,
            }

        assert "create_contact" in app._handler_registry

    @pytest.mark.asyncio
    async def test_handler_list_with_filters(self):
        """Handler can return filtered list results."""

        async def list_contacts(company_id: str = None, limit: int = 20) -> dict:
            contacts = [
                {"id": "c1", "name": "Alice", "company_id": "comp1"},
                {"id": "c2", "name": "Bob", "company_id": "comp1"},
                {"id": "c3", "name": "Charlie", "company_id": "comp2"},
            ]
            if company_id:
                contacts = [c for c in contacts if c["company_id"] == company_id]
            return {"contacts": contacts[:limit]}

        workflow = make_handler_workflow(list_contacts, node_id="list")
        runtime = AsyncLocalRuntime()
        results, _ = await runtime.execute_workflow_async(
            workflow, inputs={"company_id": "comp1", "limit": 20}
        )

        assert len(results["list"]["contacts"]) == 2
        assert all(c["company_id"] == "comp1" for c in results["list"]["contacts"])

    def test_multiple_handlers_same_app(self):
        """Multiple handlers can be registered on same Nexus app."""
        app = Nexus(auto_discovery=False)

        @app.handler("create_contact")
        async def create_contact(email: str, name: str) -> dict:
            return {"email": email, "name": name}

        @app.handler("list_contacts")
        async def list_contacts(limit: int = 20) -> dict:
            return {"contacts": [], "total": 0}

        @app.handler("delete_contact")
        async def delete_contact(contact_id: str) -> dict:
            return {"deleted": True, "id": contact_id}

        assert "create_contact" in app._handler_registry
        assert "list_contacts" in app._handler_registry
        assert "delete_contact" in app._handler_registry
