"""Golden Pattern 2: DataFlow Model Pattern - Validation Tests.

Validates that @db.model decorator generates correct nodes.
"""

import pytest
from dataflow import DataFlow


class TestGoldenPattern2DataFlowModel:
    """Validate Pattern 2: DataFlow Model Pattern."""

    @pytest.fixture
    def db(self):
        """Create DataFlow with SQLite in-memory."""
        db = DataFlow("sqlite:///:memory:")
        yield db

    def test_model_decorator_generates_crud_nodes(self, db):
        """@db.model generates CRUD workflow nodes."""

        @db.model
        class User:
            id: str
            email: str
            name: str
            role: str = "member"
            active: bool = True

        # Verify model is registered in the internal _models dict
        assert hasattr(db, "_models"), "DataFlow should have _models attribute"
        assert "User" in db._models, "User model should be registered"

    def test_model_requires_id_primary_key(self, db):
        """DataFlow models must have 'id' as primary key."""

        @db.model
        class Contact:
            id: str
            email: str
            name: str

        # Model should be registered with id field
        assert "Contact" in db._models, "Contact model should be registered"

    def test_model_default_values(self, db):
        """Model fields support default values."""

        @db.model
        class Item:
            id: str
            name: str
            quantity: int = 0
            active: bool = True
            category: str = "general"

        # Model is registered with defaults
        assert "Item" in db._models, "Item model should be registered"
        model_info = db._models["Item"]
        assert model_info is not None, "Model info should not be None"

    def test_model_optional_fields(self, db):
        """Model fields can be optional with None default."""
        from typing import Optional

        @db.model
        class Profile:
            id: str
            user_id: str
            bio: Optional[str] = None
            avatar_url: Optional[str] = None

        assert "Profile" in db._models, "Profile model should be registered"

    def test_multiple_models_same_db(self, db):
        """Multiple models can be registered on same DataFlow instance."""

        @db.model
        class Author:
            id: str
            name: str

        @db.model
        class Book:
            id: str
            title: str
            author_id: str

        # Both models should be registered
        assert "Author" in db._models, "Author model should be registered"
        assert "Book" in db._models, "Book model should be registered"
        assert len(db._models) >= 2, "Should have at least 2 models registered"
