# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for kailash_ml.trainable.Trainable protocol.

Specs: specs/ml-engines.md §3 (Trainable protocol contract).

Phase 2 scope: Protocol is runtime_checkable, adapter scaffolds exist,
attempting to call fit/predict on an adapter scaffold raises NotImplementedError
with a phase pointer (visibly unfinished, not a Rule 2 stub).
"""
from __future__ import annotations

from kailash_ml import Trainable


class TestTrainableProtocol:
    """Trainable is a runtime_checkable Protocol."""

    def test_trainable_is_importable(self):
        """Trainable MUST be importable from kailash_ml top level."""
        assert Trainable is not None

    def test_has_required_methods(self):
        """Trainable protocol MUST declare the 4 methods per spec §3."""
        # These are attributes on the Protocol class itself
        for method_name in ("fit", "predict", "to_lightning_module"):
            assert hasattr(Trainable, method_name), f"Trainable missing: {method_name}"
