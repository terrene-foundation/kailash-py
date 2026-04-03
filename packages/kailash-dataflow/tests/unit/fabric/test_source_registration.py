# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 1 unit tests for source registration into DataFlow core engine (TODO-08).

Tests: registration, name conflicts with models, config validation errors,
backward compatibility with existing @db.model usage.
"""

from __future__ import annotations

import pytest

from dataflow import DataFlow
from dataflow.fabric.config import (
    FileSourceConfig,
    RestSourceConfig,
)
from dataflow.fabric.testing import MockSource


class TestSourceRegistration:
    @pytest.fixture
    def db(self):
        return DataFlow("sqlite:///:memory:", auto_migrate=False)

    def test_register_source(self, db):
        db.source("crm", RestSourceConfig(url="https://api.example.com"))
        sources = db.get_sources()
        assert "crm" in sources
        assert isinstance(sources["crm"], RestSourceConfig)

    def test_register_multiple_sources(self, db):
        db.source("crm", RestSourceConfig(url="https://api.example.com"))
        db.source("config", FileSourceConfig(path="/tmp/config.yaml"))
        assert len(db.get_sources()) == 2

    def test_duplicate_source_name_raises(self, db):
        db.source("crm", RestSourceConfig(url="https://api.example.com"))
        with pytest.raises(ValueError, match="already registered"):
            db.source("crm", RestSourceConfig(url="https://other.com"))

    def test_source_name_conflicts_with_model(self, db):
        @db.model
        class User:
            name: str

        with pytest.raises(ValueError, match="conflicts with registered model"):
            db.source("User", RestSourceConfig(url="https://api.example.com"))

    def test_invalid_config_raises_on_register(self, db):
        with pytest.raises(ValueError, match="url must not be empty"):
            db.source("bad", RestSourceConfig())  # Empty URL

    def test_unknown_config_type_raises(self, db):
        with pytest.raises(ValueError, match="Unknown source config type"):
            db.source("bad", {"url": "https://x.com"})  # type: ignore[arg-type]

    def test_existing_model_code_unaffected(self, db):
        """Backward compatibility: @db.model works exactly as before."""

        @db.model
        class Product:
            name: str
            price: float

        models = db.get_models()
        assert "Product" in models
        assert db._sources == {}  # No sources registered

    def test_sources_and_models_coexist(self, db):
        @db.model
        class User:
            name: str

        db.source("crm", RestSourceConfig(url="https://api.example.com"))

        assert "User" in db.get_models()
        assert "crm" in db.get_sources()
        assert len(db._sources) == 1
        assert len(db._models) == 1

    def test_source_adapter_created(self, db):
        db.source("crm", RestSourceConfig(url="https://api.example.com"))
        source_info = db._sources["crm"]
        assert "adapter" in source_info
        assert source_info["adapter"].name == "crm"

    def test_register_adapter_directly(self, db):
        """db.source() accepts a BaseSourceAdapter instance (e.g. MockSource)."""
        mock = MockSource("crm", data={"": {"deals": [1, 2, 3]}})
        db.source("crm", mock)

        source_info = db._sources["crm"]
        assert source_info["adapter"] is mock
        assert source_info["config"] is None
        assert source_info["name"] == "crm"

    def test_register_adapter_name_conflict_with_model(self, db):
        @db.model
        class User:
            name: str

        mock = MockSource("User", data={})
        with pytest.raises(ValueError, match="conflicts with registered model"):
            db.source("User", mock)

    def test_register_adapter_duplicate_raises(self, db):
        mock = MockSource("src", data={})
        db.source("src", mock)
        with pytest.raises(ValueError, match="already registered"):
            db.source("src", MockSource("src2", data={}))

    def test_adapter_and_config_sources_coexist(self, db):
        mock = MockSource("mock_src", data={"": {"ok": True}})
        db.source("mock_src", mock)
        db.source("rest_src", RestSourceConfig(url="https://api.example.com"))

        assert "mock_src" in db._sources
        assert "rest_src" in db._sources
        assert db._sources["mock_src"]["adapter"] is mock
        assert db._sources["rest_src"]["config"] is not None

    def test_fabric_fields_initialized(self):
        """DataFlow.__init__ creates _sources, _products, _fabric."""
        db = DataFlow("sqlite:///:memory:", auto_migrate=False)
        assert hasattr(db, "_sources")
        assert hasattr(db, "_products")
        assert hasattr(db, "_fabric")
        assert db._sources == {}
        assert db._products == {}
        assert db._fabric is None
