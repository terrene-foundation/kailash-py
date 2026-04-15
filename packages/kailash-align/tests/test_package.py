# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for package skeleton: version, lazy imports, module structure."""
from __future__ import annotations

import re
import sys

import pytest


class TestVersion:
    # Contract: both surfaces expose a PEP 440 release version and agree.
    # Asserting a literal here goes stale on every release bump (was "0.2.1"
    # after kailash-align 0.3.1 shipped in commit ce5d4b78).
    _SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+")

    def test_version_accessible(self):
        from kailash_align._version import __version__

        assert self._SEMVER_RE.match(__version__), __version__

    def test_version_from_package(self):
        import kailash_align
        from kailash_align._version import __version__ as canonical

        assert kailash_align.__version__ == canonical


class TestLazyImports:
    def test_import_does_not_load_torch(self):
        """Importing kailash_align should NOT load torch."""
        # If torch was already loaded by another test, skip this test
        if "torch" in sys.modules:
            pytest.skip("torch already loaded by another test in this process")

        # Save and remove kailash_align modules to test fresh import
        saved_modules = {
            k: sys.modules[k]
            for k in list(sys.modules)
            if k.startswith("kailash_align")
        }
        for mod in saved_modules:
            del sys.modules[mod]

        try:
            import kailash_align  # noqa: F401

            # torch should NOT be in sys.modules from just importing kailash_align
            assert (
                "torch" not in sys.modules
            ), "Importing kailash_align loaded torch -- lazy imports broken"
        finally:
            # Restore original modules to prevent contamination
            for mod in list(sys.modules):
                if mod.startswith("kailash_align"):
                    del sys.modules[mod]
            sys.modules.update(saved_modules)

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
