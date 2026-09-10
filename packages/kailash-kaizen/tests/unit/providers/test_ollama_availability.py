"""
Unit tests for Ollama availability detection and setup.

Tests the OLLAMA_AVAILABLE flag and Ollama installation checks.
Following TDD pattern from TODO-148/149.
"""

import contextlib
import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


class _BlockedImportFinder:
    """A ``sys.meta_path`` finder that makes one top-level package unimportable.

    Needed so ``ollama``-absent behaviour can be exercised on a machine where
    ``ollama`` IS installed: dropping the entry from ``sys.modules`` only clears
    the cache, it does not stop the next ``import`` from finding it on disk.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def find_spec(self, fullname, path=None, target=None):
        if fullname == self.name or fullname.startswith(self.name + "."):
            raise ImportError(f"{fullname!r} blocked by test fixture")
        return None


def _fresh_providers():
    """Import ``kaizen.providers`` with a genuinely CLEAN namespace.

    ``importlib.reload()`` is deliberately NOT used here. Reload re-executes the
    module body in the module's EXISTING ``__dict__`` and never deletes stale
    attributes, so a reload performed while ``ollama`` was mocked leaves
    ``OllamaModelManager`` bound forever afterwards -- a later reload flips
    ``OLLAMA_AVAILABLE`` back to False but the export it gates stays visible.
    Dropping the entry from ``sys.modules`` and re-importing builds a new module
    object instead, which is the only form that actually restores state.

    Only the ``kaizen.providers`` barrel is dropped; its submodules stay cached,
    so classes such as ``ModelInfo`` keep their identity across the swap.
    """
    sys.modules.pop("kaizen.providers", None)
    return importlib.import_module("kaizen.providers")


@contextlib.contextmanager
def _providers_reloaded(*, ollama_present: bool):
    """Import ``kaizen.providers`` with ``ollama`` forced present/absent.

    ``kaizen.providers`` binds its legacy Ollama re-exports (``OllamaModelManager``,
    ``ModelInfo``, ``OllamaConfig``, ...) behind an ``if OLLAMA_AVAILABLE:`` guard
    evaluated at IMPORT time, so importing it under a patched ``sys.modules``
    produces a module whose namespace does not match the real environment.

    The ``finally`` restore is the point of this helper: without it the mutated
    module outlives the test and every later test in the process sees it. That
    leak is issue #2149 -- it made unrelated tests in this file pass only
    because this one happened to run first.
    """
    blocker = None
    overrides = {"ollama": MagicMock()} if ollama_present else {}
    try:
        with patch.dict("sys.modules", overrides):
            if not ollama_present:
                sys.modules.pop("ollama", None)
                blocker = _BlockedImportFinder("ollama")
                sys.meta_path.insert(0, blocker)
            yield _fresh_providers()
    finally:
        if blocker is not None and blocker in sys.meta_path:
            sys.meta_path.remove(blocker)
        # Runs after the patch.dict/meta_path overrides are unwound, so this
        # import observes the true environment. Also re-points the parent
        # package attribute (``kaizen.providers``), which patch.dict does not
        # restore on its own.
        _fresh_providers()


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
        import kaizen.providers

        real_value = kaizen.providers.OLLAMA_AVAILABLE

        with _providers_reloaded(ollama_present=True) as providers:
            assert providers.OLLAMA_AVAILABLE is True
            # The availability flag gates the legacy re-exports, so a True flag
            # must also bind them.
            assert hasattr(providers, "OllamaModelManager")

        # The reload must not leak: the module is back on the real environment.
        assert kaizen.providers.OLLAMA_AVAILABLE is real_value

    def test_ollama_available_false_when_not_installed(self):
        """Test OLLAMA_AVAILABLE is False when ollama package is missing."""
        import kaizen.providers

        real_value = kaizen.providers.OLLAMA_AVAILABLE

        with _providers_reloaded(ollama_present=False) as providers:
            assert providers.OLLAMA_AVAILABLE is False
            # A False flag must leave the legacy re-exports unbound.
            assert not hasattr(providers, "OllamaModelManager")

        assert kaizen.providers.OLLAMA_AVAILABLE is real_value


class TestOllamaInstallationCheck:
    """Test Ollama installation detection."""

    def test_ollama_installation_check_command_exists(self):
        """Test detecting if Ollama CLI is installed."""
        # This will fail until OllamaModelManager is implemented
        from kaizen.providers.ollama_model_manager import OllamaModelManager

        manager = OllamaModelManager()

        # Should return bool indicating if 'ollama --version' works
        result = manager._check_ollama_installed()
        assert isinstance(result, bool)

    def test_ollama_installation_check_with_mock_success(self):
        """Test installation check when Ollama CLI exists."""
        from kaizen.providers.ollama_model_manager import OllamaModelManager

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
        from kaizen.providers.ollama_model_manager import OllamaModelManager

        # Mock subprocess to simulate Ollama not found
        with patch("subprocess.run", side_effect=FileNotFoundError):
            manager = OllamaModelManager()
            result = manager._check_ollama_installed()
            assert result is False


class TestOllamaServiceStatus:
    """Test Ollama service running status."""

    def test_ollama_service_running_check_exists(self):
        """Test method to check if Ollama service is running."""
        from kaizen.providers.ollama_model_manager import OllamaModelManager

        manager = OllamaModelManager()

        # Should have method to check service status
        assert hasattr(manager, "is_ollama_running")
        result = manager.is_ollama_running()
        assert isinstance(result, bool)

    def test_ollama_service_running_with_mock_success(self):
        """Test service check when Ollama is running."""
        from kaizen.providers.ollama_model_manager import OllamaModelManager

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
        from kaizen.providers.ollama_model_manager import OllamaModelManager

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
        from kaizen.providers.ollama_model_manager import OllamaModelManager

        manager = OllamaModelManager()
        assert hasattr(manager, "list_models")

    def test_ollama_model_list_returns_list(self):
        """Test list_models returns a list of ModelInfo objects."""
        from kaizen.providers.ollama_model_manager import ModelInfo, OllamaModelManager

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
        from kaizen.providers.ollama_model_manager import OllamaModelManager

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
        from kaizen.providers.ollama_model_manager import OllamaModelManager

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
        from kaizen.providers.ollama_model_manager import OllamaModelManager

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
        from kaizen.providers.ollama_model_manager import OllamaModelManager

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
