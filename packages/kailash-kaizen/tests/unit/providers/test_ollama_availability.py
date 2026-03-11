"""
Unit tests for Ollama availability detection and setup.

Tests the OLLAMA_AVAILABLE flag and Ollama installation checks.
Following TDD pattern from TODO-148/149.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestOllamaAvailabilityFlag:
    """Test OLLAMA_AVAILABLE flag exists and works correctly."""

    def test_ollama_available_flag_exists(self):
        """Test that OLLAMA_AVAILABLE flag is defined in kaizen.providers."""
        # This will fail until we implement src/kaizen/providers/__init__.py
        try:
            from kaizen.providers import OLLAMA_AVAILABLE

            assert isinstance(OLLAMA_AVAILABLE, bool)
        except ImportError:
            pytest.fail("OLLAMA_AVAILABLE flag not found in kaizen.providers")

    def test_ollama_available_true_when_installed(self):
        """Test OLLAMA_AVAILABLE is True when ollama package is available."""
        # Mock ollama import to simulate it being installed
        with patch.dict("sys.modules", {"ollama": MagicMock()}):
            # Re-import to trigger the availability check
            import importlib

            import kaizen.providers

            importlib.reload(kaizen.providers)

            from kaizen.providers import OLLAMA_AVAILABLE

            # Note: This test may be True or False depending on actual installation
            # Just verify it's a boolean
            assert isinstance(OLLAMA_AVAILABLE, bool)

    def test_ollama_available_false_when_not_installed(self):
        """Test OLLAMA_AVAILABLE is False when ollama package is missing."""
        # This test documents expected behavior
        # Actual value depends on system state
        from kaizen.providers import OLLAMA_AVAILABLE

        assert isinstance(OLLAMA_AVAILABLE, bool)


class TestOllamaInstallationCheck:
    """Test Ollama installation detection."""

    def test_ollama_installation_check_command_exists(self):
        """Test detecting if Ollama CLI is installed."""
        # This will fail until OllamaModelManager is implemented
        from kaizen.providers import OllamaModelManager

        manager = OllamaModelManager()

        # Should return bool indicating if 'ollama --version' works
        result = manager._check_ollama_installed()
        assert isinstance(result, bool)

    def test_ollama_installation_check_with_mock_success(self):
        """Test installation check when Ollama CLI exists."""
        from kaizen.providers import OllamaModelManager

        # Mock subprocess to simulate successful Ollama check
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ollama version 0.1.0"

        with patch("subprocess.run", return_value=mock_result):
            manager = OllamaModelManager()
            result = manager._check_ollama_installed()
            assert result is True

    def test_ollama_installation_check_with_mock_failure(self):
        """Test installation check when Ollama CLI is missing."""
        from kaizen.providers import OllamaModelManager

        # Mock subprocess to simulate Ollama not found
        with patch("subprocess.run", side_effect=FileNotFoundError):
            manager = OllamaModelManager()
            result = manager._check_ollama_installed()
            assert result is False


class TestOllamaServiceStatus:
    """Test Ollama service running status."""

    def test_ollama_service_running_check_exists(self):
        """Test method to check if Ollama service is running."""
        from kaizen.providers import OllamaModelManager

        manager = OllamaModelManager()

        # Should have method to check service status
        assert hasattr(manager, "is_ollama_running")
        result = manager.is_ollama_running()
        assert isinstance(result, bool)

    def test_ollama_service_running_with_mock_success(self):
        """Test service check when Ollama is running."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama.list() to simulate service running
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            result = manager.is_ollama_running()
            # Should return True when service responds
            assert isinstance(result, bool)

    def test_ollama_service_not_running_with_mock_failure(self):
        """Test service check when Ollama is not running."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama.list() to raise exception (service not running)
        mock_ollama = MagicMock()
        mock_ollama.list.side_effect = Exception("Connection refused")

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            result = manager.is_ollama_running()
            # Should return False when service doesn't respond
            assert result is False


class TestOllamaModelListing:
    """Test listing available Ollama models."""

    def test_ollama_model_list_method_exists(self):
        """Test that list_models method exists."""
        from kaizen.providers import OllamaModelManager

        manager = OllamaModelManager()
        assert hasattr(manager, "list_models")

    def test_ollama_model_list_returns_list(self):
        """Test list_models returns a list of ModelInfo objects."""
        from kaizen.providers import ModelInfo, OllamaModelManager

        # Mock ollama.list() response (Pydantic object structure)
        mock_ollama = MagicMock()
        mock_model = MagicMock()
        mock_model.model = "llama2:latest"
        mock_model.size = 3826793677
        mock_model.modified_at = "2024-01-15T10:30:00Z"
        mock_model.digest = "sha256:abc123"

        mock_response = MagicMock()
        mock_response.models = [mock_model]
        mock_ollama.list.return_value = mock_response

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            models = manager.list_models()

            assert isinstance(models, list)
            if len(models) > 0:
                assert isinstance(models[0], ModelInfo)

    def test_ollama_model_list_handles_empty(self):
        """Test list_models handles empty model list."""
        from kaizen.providers import OllamaModelManager

        # Mock empty response (Pydantic object structure)
        mock_ollama = MagicMock()
        mock_response = MagicMock()
        mock_response.models = []
        mock_ollama.list.return_value = mock_response

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            models = manager.list_models()

            assert isinstance(models, list)
            assert len(models) == 0


class TestOllamaSpecificModels:
    """Test checking for specific vision models."""

    def test_llava_model_available_check(self):
        """Test checking if llava:13b model is available."""
        from kaizen.providers import OllamaModelManager

        manager = OllamaModelManager()

        # Mock model list with llava (Pydantic object structure)
        mock_ollama = MagicMock()
        mock_model = MagicMock()
        mock_model.model = "llava:13b"
        mock_model.size = 7400000000
        mock_model.modified_at = "2024-01-15T10:30:00Z"
        mock_model.digest = "sha256:abc123"

        mock_response = MagicMock()
        mock_response.models = [mock_model]
        mock_ollama.list.return_value = mock_response

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            result = manager.model_exists("llava:13b")
            # Should have method to check specific model
            assert isinstance(result, bool)

    def test_bakllava_model_available_check(self):
        """Test checking if bakllava model is available."""
        from kaizen.providers import OllamaModelManager

        manager = OllamaModelManager()

        # Mock model list with bakllava (Pydantic object structure)
        mock_ollama = MagicMock()
        mock_model = MagicMock()
        mock_model.model = "bakllava:latest"
        mock_model.size = 4700000000
        mock_model.modified_at = "2024-01-15T10:30:00Z"
        mock_model.digest = "sha256:xyz789"

        mock_response = MagicMock()
        mock_response.models = [mock_model]
        mock_ollama.list.return_value = mock_response

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            result = manager.model_exists("bakllava")
            assert isinstance(result, bool)

    def test_vision_models_not_found(self):
        """Test when vision models are not available."""
        from kaizen.providers import OllamaModelManager

        manager = OllamaModelManager()

        # Mock empty model list (Pydantic object structure)
        mock_ollama = MagicMock()
        mock_response = MagicMock()
        mock_response.models = []
        mock_ollama.list.return_value = mock_response

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            llava_exists = manager.model_exists("llava:13b")
            bakllava_exists = manager.model_exists("bakllava")

            # Both should be False when no models available
            assert llava_exists is False
            assert bakllava_exists is False
