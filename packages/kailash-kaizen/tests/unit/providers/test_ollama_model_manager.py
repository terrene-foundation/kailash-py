"""
Unit tests for Ollama model download and management.

Tests the OllamaModelManager functionality for downloading and managing models.
Following TDD pattern from TODO-148/149.
"""

from unittest.mock import MagicMock, patch


class TestModelExistence:
    """Test checking if models exist locally."""

    def test_check_model_exists_method(self):
        """Test model_exists method is available."""
        from kaizen.providers import OllamaModelManager

        manager = OllamaModelManager()
        assert hasattr(manager, "model_exists")

    def test_check_model_exists_returns_bool(self):
        """Test model_exists returns boolean value."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama.list() to return a model
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
            result = manager.model_exists("llama2")
            assert isinstance(result, bool)

    def test_check_model_exists_when_present(self):
        """Test model_exists returns True when model is present."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama.list() with specific model
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
            manager = OllamaModelManager()
            result = manager.model_exists("llava:13b")
            assert result is True

    def test_check_model_exists_when_absent(self):
        """Test model_exists returns False when model is absent."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama.list() with empty models
        mock_ollama = MagicMock()
        mock_response = MagicMock()
        mock_response.models = []
        mock_ollama.list.return_value = mock_response

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            result = manager.model_exists("nonexistent-model")
            assert result is False


class TestModelDownload:
    """Test downloading Ollama models."""

    def test_download_model_llava_method_exists(self):
        """Test download_model method is available."""
        from kaizen.providers import OllamaModelManager

        manager = OllamaModelManager()
        assert hasattr(manager, "download_model")

    def test_download_model_llava_success(self):
        """Test successful download of llava:13b model."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama.pull() to simulate successful download
        mock_ollama = MagicMock()

        def mock_pull(model_name, stream=True):
            """Mock pull generator that yields progress updates."""
            yield {"status": "downloading", "completed": 1000, "total": 10000}
            yield {"status": "downloading", "completed": 5000, "total": 10000}
            yield {"status": "downloading", "completed": 10000, "total": 10000}
            yield {"status": "success"}

        mock_ollama.pull = mock_pull

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            result = manager.download_model("llava:13b")
            assert result is True

    def test_download_model_bakllava_success(self):
        """Test successful download of bakllava model."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama.pull() to simulate successful download
        mock_ollama = MagicMock()

        def mock_pull(model_name, stream=True):
            """Mock pull generator for bakllava."""
            yield {"status": "downloading", "completed": 2000, "total": 5000}
            yield {"status": "downloading", "completed": 5000, "total": 5000}
            yield {"status": "success"}

        mock_ollama.pull = mock_pull

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            result = manager.download_model("bakllava")
            assert result is True

    def test_download_model_failure(self):
        """Test download failure handling."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama.pull() to raise exception
        mock_ollama = MagicMock()
        mock_ollama.pull.side_effect = Exception("Network error")

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            result = manager.download_model("llava:13b")
            assert result is False


class TestDownloadProgress:
    """Test download progress tracking."""

    def test_download_progress_tracking_callback(self):
        """Test download progress with callback function."""
        from kaizen.providers import OllamaModelManager

        # Track progress calls
        progress_updates = []

        def progress_callback(status: str, percent: float):
            progress_updates.append({"status": status, "percent": percent})

        # Mock ollama.pull() with progress
        mock_ollama = MagicMock()

        def mock_pull(model_name, stream=True):
            yield {"status": "downloading", "completed": 2500, "total": 10000}
            yield {"status": "downloading", "completed": 5000, "total": 10000}
            yield {"status": "downloading", "completed": 10000, "total": 10000}
            yield {"status": "success"}

        mock_ollama.pull = mock_pull

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            result = manager.download_model(
                "llava:13b", progress_callback=progress_callback
            )

            assert result is True
            # Should have received progress updates
            assert len(progress_updates) > 0

    def test_download_progress_percentage_calculation(self):
        """Test progress percentage is calculated correctly."""
        from kaizen.providers import OllamaModelManager

        progress_updates = []

        def progress_callback(status: str, percent: float):
            progress_updates.append({"status": status, "percent": percent})

        # Mock ollama.pull() with known percentages
        mock_ollama = MagicMock()

        def mock_pull(model_name, stream=True):
            # 25%, 50%, 100%
            yield {"status": "downloading", "completed": 2500, "total": 10000}
            yield {"status": "downloading", "completed": 5000, "total": 10000}
            yield {"status": "downloading", "completed": 10000, "total": 10000}

        mock_ollama.pull = mock_pull

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            manager.download_model("llava:13b", progress_callback=progress_callback)

            # Verify percentages are reasonable
            for update in progress_updates:
                assert 0 <= update["percent"] <= 100

    def test_download_progress_without_callback(self):
        """Test download works without progress callback."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama.pull()
        mock_ollama = MagicMock()

        def mock_pull(model_name, stream=True):
            yield {"status": "downloading", "completed": 5000, "total": 10000}
            yield {"status": "success"}

        mock_ollama.pull = mock_pull

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            # Should work without callback
            result = manager.download_model("llava:13b", progress_callback=None)
            assert result is True


class TestModelInfo:
    """Test retrieving model information."""

    def test_model_info_retrieval_method_exists(self):
        """Test get_model_info method exists."""
        from kaizen.providers import OllamaModelManager

        manager = OllamaModelManager()
        assert hasattr(manager, "get_model_info")

    def test_model_info_retrieval_for_existing_model(self):
        """Test get_model_info returns info for existing model."""
        from kaizen.providers import ModelInfo, OllamaModelManager

        # Mock ollama.list() with model data
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
            manager = OllamaModelManager()
            info = manager.get_model_info("llava:13b")

            assert info is not None
            assert isinstance(info, ModelInfo)
            assert info.name == "llava:13b"
            assert info.size == 7400000000

    def test_model_info_retrieval_for_missing_model(self):
        """Test get_model_info returns None for missing model."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama.list() with empty models
        mock_ollama = MagicMock()
        mock_response = MagicMock()
        mock_response.models = []
        mock_ollama.list.return_value = mock_response

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            info = manager.get_model_info("nonexistent-model")

            assert info is None


class TestModelSizeValidation:
    """Test model size validation after download."""

    def test_model_size_validation_after_download(self):
        """Test verifying model size after download."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama for download
        mock_ollama = MagicMock()

        def mock_pull(model_name, stream=True):
            yield {"status": "success"}

        mock_ollama.pull = mock_pull

        # Mock ollama.list() to return downloaded model with size
        mock_model = MagicMock()
        mock_model.model = "llava:13b"
        mock_model.size = 7400000000  # ~7.4GB
        mock_model.modified_at = "2024-01-15T10:30:00Z"
        mock_model.digest = "sha256:abc123"

        mock_response = MagicMock()
        mock_response.models = [mock_model]
        mock_ollama.list.return_value = mock_response

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()

            # Download model
            result = manager.download_model("llava:13b")
            assert result is True

            # Verify size
            info = manager.get_model_info("llava:13b")
            assert info is not None
            assert info.size > 0
            # llava:13b should be around 7.4GB
            assert info.size > 5_000_000_000  # At least 5GB

    def test_model_size_comparison_llava_vs_bakllava(self):
        """Test that llava:13b is larger than bakllava."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama.list() with both models
        mock_ollama = MagicMock()
        mock_model1 = MagicMock()
        mock_model1.model = "llava:13b"
        mock_model1.size = 7400000000  # ~7.4GB
        mock_model1.modified_at = "2024-01-15T10:30:00Z"
        mock_model1.digest = "sha256:abc123"

        mock_model2 = MagicMock()
        mock_model2.model = "bakllava:latest"
        mock_model2.size = 4700000000  # ~4.7GB
        mock_model2.modified_at = "2024-01-15T10:30:00Z"
        mock_model2.digest = "sha256:xyz789"

        mock_response = MagicMock()
        mock_response.models = [mock_model1, mock_model2]
        mock_ollama.list.return_value = mock_response

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()

            llava_info = manager.get_model_info("llava:13b")
            bakllava_info = manager.get_model_info("bakllava")

            assert llava_info is not None
            assert bakllava_info is not None
            # llava should be larger
            assert llava_info.size > bakllava_info.size


class TestVisionModelSetup:
    """Test automated vision model setup."""

    def test_setup_vision_models_method_exists(self):
        """Test setup_vision_models method exists."""
        from kaizen.providers import OllamaModelManager

        manager = OllamaModelManager()
        assert hasattr(manager, "setup_vision_models")

    def test_setup_vision_models_checks_both_models(self):
        """Test setup_vision_models checks both llava and bakllava."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama
        mock_ollama = MagicMock()
        mock_response = MagicMock()
        mock_response.models = []
        mock_ollama.list.return_value = mock_response

        def mock_pull(model_name, stream=True):
            yield {"status": "success"}

        mock_ollama.pull = mock_pull

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            results = manager.setup_vision_models(auto_download=False)

            # Should return dict with results for both models
            assert isinstance(results, dict)
            assert "llava:13b" in results
            assert "bakllava" in results

    def test_setup_vision_models_with_auto_download(self):
        """Test setup_vision_models downloads missing models when auto_download=True."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama
        mock_ollama = MagicMock()
        mock_response = MagicMock()
        mock_response.models = []
        mock_ollama.list.return_value = mock_response

        download_calls = []

        def mock_pull(model_name, stream=True):
            download_calls.append(model_name)
            yield {"status": "success"}

        mock_ollama.pull = mock_pull

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            manager.setup_vision_models(auto_download=True)

            # Both models should be downloaded
            assert len(download_calls) == 2
            assert "llava:13b" in download_calls
            assert "bakllava" in download_calls

    def test_setup_vision_models_without_auto_download(self):
        """Test setup_vision_models skips download when auto_download=False."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama with no models
        mock_ollama = MagicMock()
        mock_response = MagicMock()
        mock_response.models = []
        mock_ollama.list.return_value = mock_response

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            results = manager.setup_vision_models(auto_download=False)

            # Both should be False (not available, not downloaded)
            assert results["llava:13b"] is False
            assert results["bakllava"] is False


class TestEnsureModelAvailable:
    """Test ensuring models are available with auto-download."""

    def test_ensure_model_available_method_exists(self):
        """Test ensure_model_available method exists."""
        from kaizen.providers import OllamaModelManager

        manager = OllamaModelManager()
        assert hasattr(manager, "ensure_model_available")

    def test_ensure_model_available_when_already_present(self):
        """Test ensure_model_available returns True when model exists."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama with model already present
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
            manager = OllamaModelManager()
            result = manager.ensure_model_available("llava:13b", auto_download=False)

            # Should return True without downloading
            assert result is True

    def test_ensure_model_available_downloads_when_missing(self):
        """Test ensure_model_available downloads when model is missing."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama
        mock_ollama = MagicMock()

        # Start with no models
        call_count = [0]

        def mock_list():
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: no models
                return {"models": []}
            else:
                # After download: model exists
                return {
                    "models": [
                        {
                            "name": "llava:13b",
                            "size": 7400000000,
                            "modified_at": "2024-01-15T10:30:00Z",
                            "digest": "sha256:abc123",
                        }
                    ]
                }

        mock_ollama.list = mock_list

        def mock_pull(model_name, stream=True):
            yield {"status": "success"}

        mock_ollama.pull = mock_pull

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            result = manager.ensure_model_available("llava:13b", auto_download=True)

            # Should download and return True
            assert result is True

    def test_ensure_model_available_skips_download_when_disabled(self):
        """Test ensure_model_available doesn't download when auto_download=False."""
        from kaizen.providers import OllamaModelManager

        # Mock ollama with no models
        mock_ollama = MagicMock()
        mock_response = MagicMock()
        mock_response.models = []
        mock_ollama.list.return_value = mock_response

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            manager = OllamaModelManager()
            result = manager.ensure_model_available("llava:13b", auto_download=False)

            # Should return False without downloading
            assert result is False
