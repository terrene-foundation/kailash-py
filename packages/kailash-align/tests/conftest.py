# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Root conftest for kailash-align tests."""
from __future__ import annotations

import pytest

from kailash_align.config import AdapterSignature
from kailash_align.registry import AdapterRegistry


@pytest.fixture
def adapter_registry() -> AdapterRegistry:
    """Create a fresh in-memory AdapterRegistry."""
    return AdapterRegistry()


@pytest.fixture
def sample_signature() -> AdapterSignature:
    """Create a sample AdapterSignature for testing."""
    return AdapterSignature(
        base_model_id="meta-llama/Llama-3.1-8B",
        adapter_type="lora",
        rank=16,
        alpha=32,
        target_modules=("q_proj", "v_proj"),
        task_type="CAUSAL_LM",
        training_method="sft",
    )
