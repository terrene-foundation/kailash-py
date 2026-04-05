# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for package skeleton: version, lazy imports, module structure."""
from __future__ import annotations

import sys

import pytest


class TestVersion:
    def test_version_accessible(self):
        from kailash_align._version import __version__

        assert __version__ == "0.2.0"

    def test_version_from_package(self):
        import kailash_align

        assert kailash_align.__version__ == "0.2.0"


class TestLazyImports:
    def test_import_does_not_load_torch(self):
        """Importing kailash_align should NOT load torch (verified in subprocess)."""
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import kailash_align; import sys; "
                "assert 'torch' not in sys.modules, "
                "'Importing kailash_align loaded torch -- lazy imports broken'",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            result.returncode == 0
        ), f"Lazy import test failed: {result.stderr.strip()}"

    def test_lazy_getattr_raises_for_unknown(self):
        import kailash_align

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = kailash_align.NonExistentClass

    def test_all_exports_listed(self):
        import kailash_align

        expected = [
            "__version__",
            "AdapterRegistry",
            "AlignmentPipeline",
            "AlignmentConfig",
            "LoRAConfig",
            "SFTConfig",
            "DPOConfig",
            "AdapterSignature",
            "AlignmentResult",
        ]
        for name in expected:
            assert name in kailash_align.__all__


class TestModuleStructure:
    def test_exceptions_importable(self):
        from kailash_align.exceptions import AlignmentError, TrainingError

        assert issubclass(TrainingError, AlignmentError)

    def test_config_importable(self):
        from kailash_align.config import (
            AlignmentConfig,
            DPOConfig,
            LoRAConfig,
            SFTConfig,
        )

        assert LoRAConfig is not None
        assert SFTConfig is not None
        assert DPOConfig is not None
        assert AlignmentConfig is not None

    def test_models_importable(self):
        from kailash_align.models import (
            ALIGN_ADAPTER_FIELDS,
            ALIGN_ADAPTER_VERSION_FIELDS,
        )

        assert "id" in ALIGN_ADAPTER_FIELDS
        assert "id" in ALIGN_ADAPTER_VERSION_FIELDS
        assert ALIGN_ADAPTER_FIELDS["model_type"] == "TEXT NOT NULL DEFAULT 'alignment'"

    def test_registry_importable(self):
        from kailash_align.registry import AdapterRegistry, AdapterVersion

        assert AdapterRegistry is not None
        assert AdapterVersion is not None

    def test_py_typed_exists(self):
        """PEP 561 py.typed marker must exist."""
        from pathlib import Path

        import kailash_align

        pkg_dir = Path(kailash_align.__file__).parent
        assert (pkg_dir / "py.typed").exists()
