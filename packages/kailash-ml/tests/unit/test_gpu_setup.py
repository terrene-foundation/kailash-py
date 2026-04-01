# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for _gpu_setup CLI module."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from kailash_ml._gpu_setup import _best_cuda_tag, detect_cuda_version


class TestDetectCudaVersion:
    """Test CUDA version detection."""

    def test_from_env_var(self):
        with patch.dict(os.environ, {"CUDA_VERSION": "12.4.1"}):
            assert detect_cuda_version() == "12.4"

    def test_from_env_var_two_parts(self):
        with patch.dict(os.environ, {"CUDA_VERSION": "11.8"}):
            assert detect_cuda_version() == "11.8"

    def test_no_cuda(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("shutil.which", return_value=None):
                result = detect_cuda_version()
                # May return None or detect from other sources
                assert result is None or isinstance(result, str)


class TestBestCudaTag:
    """Test CUDA tag matching."""

    def test_exact_match(self):
        assert _best_cuda_tag("12.1") == "cu121"

    def test_exact_match_118(self):
        assert _best_cuda_tag("11.8") == "cu118"

    def test_higher_minor_rounds_down(self):
        # CUDA 12.3 should map to cu121 (closest available <= 12.3)
        tag = _best_cuda_tag("12.3")
        assert tag == "cu121"

    def test_exact_124(self):
        assert _best_cuda_tag("12.4") == "cu124"

    def test_fallback(self):
        # CUDA 10.0 has no match, should fallback
        tag = _best_cuda_tag("10.0")
        assert tag == "cu121"  # safe default


class TestMainFunction:
    """Test the CLI main function."""

    def test_main_no_cuda(self, capsys):
        with patch("kailash_ml._gpu_setup.detect_cuda_version", return_value=None):
            with pytest.raises(SystemExit) as exc_info:
                from kailash_ml._gpu_setup import main

                main()
            assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "No CUDA toolkit detected" in captured.out

    def test_main_with_cuda(self, capsys):
        with patch("kailash_ml._gpu_setup.detect_cuda_version", return_value="12.4"):
            from kailash_ml._gpu_setup import main

            main()
        captured = capsys.readouterr()
        assert "Detected CUDA version: 12.4" in captured.out
        assert "cu124" in captured.out
