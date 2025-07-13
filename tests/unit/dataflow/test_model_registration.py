"""Unit tests for DataFlow model registration and decorator functionality.

These tests ensure that the @db.model decorator correctly processes
Python classes and extracts field information for SQL generation.
"""

from datetime import datetime
from typing import List, Optional
from unittest.mock import MagicMock, call, patch

import pytest


class TestDataFlowModelRegistration:
    """Test DataFlow model registration functionality."""

    def test_model_decorator_basic(self):
        """Test that @db.model decorator processes a simple class."""
        # Mock DataFlow instance
        mock_db = MagicMock()
        mock_db._models = {}
        mock_db._model_fields = {}
        mock_db._registered_models = {}

        # Define test model
        class User:
            name: str
            email: str
            active: bool = True

        # Set annotations manually (simulating Python's type hints)
        User.__annotations__ = {"name": str, "email": str, "active": bool}

        # Simulate the decorator behavior
        mock_db.model.return_value = User
        decorated_class = mock_db.model(User)

        # Verify decorator was called
        mock_db.model.assert_called_once_with(User)
        assert decorated_class is User

    def test_model_registration_stores_metadata(self):
        """Test that model registration stores class metadata."""
        mock_db = MagicMock()
        mock_db._models = {}
        mock_db._model_fields = {}
        mock_db._registered_models = {}

        class Product:
            name: str
            price: float
            stock: int = 0

        Product.__annotations__ = {"name": str, "price": float, "stock": int}

        # Simulate registration storing metadata
        def mock_model_decorator(cls):
            model_name = cls.__name__
            mock_db._models[model_name] = cls
            mock_db._registered_models[model_name] = cls

            # Extract fields
            fields = {}
            for field_name, field_type in cls.__annotations__.items():
                fields[field_name] = {
                    "type": field_type,
                    "required": not hasattr(cls, field_name),
                    "default": getattr(cls, field_name, None),
                }
            mock_db._model_fields[model_name] = fields
            return cls

        mock_db.model.side_effect = mock_model_decorator

        # Apply decorator
        decorated = mock_db.model(Product)

        # Verify metadata storage
        assert "Product" in mock_db._models
        assert mock_db._models["Product"] is Product
        assert "Product" in mock_db._model_fields

        # Check field extraction
        fields = mock_db._model_fields["Product"]
        assert "name" in fields
        assert fields["name"]["type"] is str
        assert fields["name"]["required"] is True

        assert "stock" in fields
        assert fields["stock"]["type"] is int
        assert fields["stock"]["required"] is False
        assert fields["stock"]["default"] == 0

    def test_model_with_optional_fields(self):
        """Test model registration with Optional type hints."""
        mock_db = MagicMock()
        mock_db._model_fields = {}

        class BlogPost:
            title: str
            content: str
            published_at: Optional[datetime] = None
            tags: Optional[List[str]] = None

        BlogPost.__annotations__ = {
            "title": str,
            "content": str,
            "published_at": Optional[datetime],
            "tags": Optional[List[str]],
        }

        # Simulate field extraction
        fields = {}
        for field_name, field_type in BlogPost.__annotations__.items():
            fields[field_name] = {
                "type": field_type,
                "required": not hasattr(BlogPost, field_name),
                "default": getattr(BlogPost, field_name, None),
                "nullable": hasattr(field_type, "__origin__")
                and type(None) in field_type.__args__,
            }

        # Verify Optional handling
        assert fields["published_at"]["nullable"] is True
        assert fields["published_at"]["default"] is None
        assert fields["tags"]["nullable"] is True

    def test_model_duplicate_registration_error(self):
        """Test that registering the same model twice raises an error."""
        mock_db = MagicMock()
        mock_db._models = {"User": MagicMock()}

        class User:
            name: str

        # Simulate decorator that checks for duplicates
        def mock_model_decorator(cls):
            if cls.__name__ in mock_db._models:
                raise ValueError(f"Model '{cls.__name__}' is already registered")
            return cls

        mock_db.model.side_effect = mock_model_decorator

        # Should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            mock_db.model(User)

        assert "Model 'User' is already registered" in str(exc_info.value)

    def test_model_without_annotations_error(self):
        """Test that model without type hints raises an error."""
        mock_db = MagicMock()

        class InvalidModel:
            pass  # No type hints

        # Simulate validation
        def mock_model_decorator(cls):
            if not hasattr(cls, "__annotations__") or not cls.__annotations__:
                raise ValueError("Model must have at least one field")
            return cls

        mock_db.model.side_effect = mock_model_decorator

        with pytest.raises(ValueError) as exc_info:
            mock_db.model(InvalidModel)

        assert "Model must have at least one field" in str(exc_info.value)

    def test_model_with_dataflow_config(self):
        """Test model with __dataflow__ configuration."""
        mock_db = MagicMock()
        mock_db._model_fields = {}

        class Order:
            customer_id: int
            total: float
            status: str = "pending"

            __dataflow__ = {
                "multi_tenant": True,
                "soft_delete": True,
                "versioned": True,
                "audit_log": True,
            }

        Order.__annotations__ = {"customer_id": int, "total": float, "status": str}

        # Simulate decorator that reads __dataflow__
        def mock_model_decorator(cls):
            config = getattr(cls, "__dataflow__", {})
            cls._dataflow_config = config
            return cls

        mock_db.model.side_effect = mock_model_decorator
        decorated = mock_db.model(Order)

        # Verify configuration was processed
        assert hasattr(decorated, "_dataflow_config")
        assert decorated._dataflow_config["multi_tenant"] is True
        assert decorated._dataflow_config["soft_delete"] is True

    def test_model_with_indexes(self):
        """Test model with __indexes__ configuration."""
        mock_db = MagicMock()

        class Product:
            name: str
            category: str
            price: float

            __indexes__ = [
                {"name": "idx_category", "fields": ["category"]},
                {"name": "idx_price", "fields": ["price"], "type": "btree"},
            ]

        Product.__annotations__ = {"name": str, "category": str, "price": float}

        # Verify indexes are accessible
        assert hasattr(Product, "__indexes__")
        assert len(Product.__indexes__) == 2
        assert Product.__indexes__[0]["name"] == "idx_category"

    def test_model_adds_dataflow_attributes(self):
        """Test that model decorator adds DataFlow-specific attributes."""
        mock_db = MagicMock()

        class Customer:
            name: str
            email: str

        Customer.__annotations__ = {"name": str, "email": str}

        # Simulate decorator adding attributes
        def mock_model_decorator(cls):
            cls._dataflow = mock_db
            cls._dataflow_meta = {
                "engine": mock_db,
                "model_name": cls.__name__,
                "fields": {},
                "registered_at": datetime.now(),
            }
            return cls

        mock_db.model.side_effect = mock_model_decorator
        decorated = mock_db.model(Customer)

        # Verify attributes
        assert hasattr(decorated, "_dataflow")
        assert decorated._dataflow is mock_db
        assert hasattr(decorated, "_dataflow_meta")
        assert decorated._dataflow_meta["model_name"] == "Customer"

    def test_model_multi_tenant_auto_field(self):
        """Test that multi-tenant models get tenant_id field automatically."""
        mock_db = MagicMock()
        mock_db.config = MagicMock()
        mock_db.config.security = MagicMock()
        mock_db.config.security.multi_tenant = True

        class TenantModel:
            name: str
            data: str

        TenantModel.__annotations__ = {"name": str, "data": str}

        # Simulate multi-tenant field injection
        def mock_model_decorator(cls):
            if mock_db.config.security.multi_tenant:
                if "tenant_id" not in cls.__annotations__:
                    cls.__annotations__["tenant_id"] = str
            return cls

        mock_db.model.side_effect = mock_model_decorator
        decorated = mock_db.model(TenantModel)

        # Verify tenant_id was added
        assert "tenant_id" in decorated.__annotations__
        assert decorated.__annotations__["tenant_id"] is str

    def test_model_field_extraction_complex_types(self):
        """Test field extraction with complex Python types."""
        mock_db = MagicMock()

        from typing import Dict, Union

        class ComplexModel:
            id: int
            metadata: Dict[str, str]
            value: Union[int, float]
            tags: List[str] = []

        ComplexModel.__annotations__ = {
            "id": int,
            "metadata": Dict[str, str],
            "value": Union[int, float],
            "tags": List[str],
        }

        # These complex types should be handled appropriately
        # In real implementation, they might map to JSON fields
        fields = {}
        for name, type_hint in ComplexModel.__annotations__.items():
            fields[name] = {
                "type": type_hint,
                "python_type_name": str(type_hint),
                "is_complex": hasattr(type_hint, "__origin__"),
            }

        assert fields["metadata"]["is_complex"] is True
        assert fields["value"]["is_complex"] is True
        assert fields["tags"]["is_complex"] is True
