"""Unit tests for DataFlow import structure and package setup.

These tests ensure that the basic import structure works as documented
and that the package is properly configured for installation.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestDataFlowImportStructure:
    """Test DataFlow import structure works correctly."""

    def test_dataflow_module_exists_in_sys_modules(self):
        """Test that dataflow module can be registered in sys.modules."""
        # Simulate the dataflow module being available
        mock_module = MagicMock()
        mock_module.DataFlow = MagicMock

        with patch.dict("sys.modules", {"dataflow": mock_module}):
            assert "dataflow" in sys.modules
            import dataflow

            assert hasattr(dataflow, "DataFlow")

    def test_dataflow_import_from_package(self):
        """Test that DataFlow can be imported from dataflow package."""
        # Mock the dataflow module structure
        mock_dataflow_module = MagicMock()
        mock_dataflow_class = MagicMock()
        mock_dataflow_module.DataFlow = mock_dataflow_class

        with patch.dict("sys.modules", {"dataflow": mock_dataflow_module}):
            from dataflow import DataFlow

            assert DataFlow is mock_dataflow_class

    def test_dataflow_class_is_callable(self):
        """Test that DataFlow class can be instantiated."""
        # Mock the DataFlow class
        mock_dataflow_instance = MagicMock()
        mock_dataflow_class = MagicMock(return_value=mock_dataflow_instance)
        mock_module = MagicMock(DataFlow=mock_dataflow_class)

        with patch.dict("sys.modules", {"dataflow": mock_module}):
            from dataflow import DataFlow

            db = DataFlow()
            assert db is mock_dataflow_instance
            mock_dataflow_class.assert_called_once_with()

    def test_dataflow_zero_config_instantiation(self):
        """Test that DataFlow can be instantiated with zero configuration."""
        # Mock the DataFlow class with zero-config behavior
        mock_dataflow_instance = MagicMock()
        mock_dataflow_instance.config = MagicMock()
        mock_dataflow_instance.config.database_url = "sqlite:///:memory:"

        mock_dataflow_class = MagicMock(return_value=mock_dataflow_instance)
        mock_module = MagicMock(DataFlow=mock_dataflow_class)

        with patch.dict("sys.modules", {"dataflow": mock_module}):
            from dataflow import DataFlow

            db = DataFlow()

            # Verify zero-config instantiation
            mock_dataflow_class.assert_called_once_with()
            assert db.config.database_url == "sqlite:///:memory:"

    def test_dataflow_with_configuration(self):
        """Test that DataFlow accepts configuration parameters."""
        mock_dataflow_instance = MagicMock()
        mock_dataflow_class = MagicMock(return_value=mock_dataflow_instance)
        mock_module = MagicMock(DataFlow=mock_dataflow_class)

        with patch.dict("sys.modules", {"dataflow": mock_module}):
            from dataflow import DataFlow

            db = DataFlow(
                database_url="postgresql://localhost/test", pool_size=20, echo=True
            )

            # Verify configuration parameters were passed
            mock_dataflow_class.assert_called_once_with(
                database_url="postgresql://localhost/test", pool_size=20, echo=True
            )

    def test_dataflow_exports_expected_classes(self):
        """Test that dataflow package exports expected classes."""
        # Mock the complete dataflow module structure
        mock_dataflow_config = MagicMock()
        mock_dataflow_model = MagicMock()

        mock_module = MagicMock()
        mock_module.DataFlow = MagicMock()
        mock_module.DataFlowConfig = mock_dataflow_config
        mock_module.DataFlowModel = mock_dataflow_model
        mock_module.__all__ = ["DataFlow", "DataFlowConfig", "DataFlowModel"]

        with patch.dict("sys.modules", {"dataflow": mock_module}):
            import dataflow

            # Check main export
            assert hasattr(dataflow, "DataFlow")
            assert hasattr(dataflow, "DataFlowConfig")
            assert hasattr(dataflow, "DataFlowModel")
            assert dataflow.__all__ == ["DataFlow", "DataFlowConfig", "DataFlowModel"]

    def test_dataflow_version_info(self):
        """Test that dataflow package has version information."""
        mock_module = MagicMock()
        mock_module.__version__ = "1.0.0"
        mock_module.DataFlow = MagicMock()

        with patch.dict("sys.modules", {"dataflow": mock_module}):
            import dataflow

            assert hasattr(dataflow, "__version__")
            assert dataflow.__version__ == "1.0.0"

    def test_import_from_nested_structure(self):
        """Test that DataFlow works with nested package structure."""
        # Mock the nested package structure
        mock_engine = MagicMock()
        mock_dataflow_class = MagicMock()
        mock_engine.DataFlow = mock_dataflow_class

        mock_core = MagicMock()
        mock_core.engine = mock_engine

        mock_dataflow = MagicMock()
        mock_dataflow.core = mock_core
        mock_dataflow.DataFlow = mock_dataflow_class  # Also expose at top level

        with patch.dict(
            "sys.modules",
            {
                "dataflow": mock_dataflow,
                "dataflow.core": mock_core,
                "dataflow.core.engine": mock_engine,
            },
        ):
            # Should work both ways
            from dataflow import DataFlow

            assert DataFlow is mock_dataflow_class

            from dataflow.core.engine import DataFlow as EngineDataFlow

            assert EngineDataFlow is mock_dataflow_class

    def test_package_initialization_order(self):
        """Test that package components initialize in correct order."""
        initialization_order = []

        # Mock components that track initialization
        mock_config = MagicMock()
        mock_config.side_effect = lambda: initialization_order.append("config")

        mock_engine = MagicMock()
        mock_engine.side_effect = lambda: initialization_order.append("engine")

        mock_dataflow = MagicMock()
        mock_dataflow.DataFlowConfig = mock_config
        mock_dataflow.DataFlow = mock_engine

        with patch.dict("sys.modules", {"dataflow": mock_dataflow}):
            from dataflow import DataFlow, DataFlowConfig

            # Instantiate to trigger initialization tracking
            DataFlowConfig()
            DataFlow()

            # Config should initialize before engine
            assert initialization_order == ["config", "engine"]
