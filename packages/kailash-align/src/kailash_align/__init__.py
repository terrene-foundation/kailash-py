# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""kailash-align: LLM fine-tuning and alignment framework."""
from __future__ import annotations

from kailash_align._version import __version__

__all__ = [
    "__version__",
    "AdapterRegistry",
    "AlignmentPipeline",
    "AlignmentConfig",
    "LoRAConfig",
    "SFTConfig",
    "DPOConfig",
    "AdapterSignature",
    "AlignmentResult",
    "AlignmentEvaluator",
    "EvalResult",
    "TaskResult",
    "EvalConfig",
    "AlignmentServing",
    "ServingConfig",
    "AdapterMerger",
    "KaizenModelBridge",
    "BridgeConfig",
    "OnPremModelCache",
    "OnPremConfig",
]


def __getattr__(name: str):
    """Lazy imports to avoid loading torch/transformers on import."""
    _imports = {
        "AdapterRegistry": ".registry",
        "AlignmentPipeline": ".pipeline",
        "AlignmentConfig": ".config",
        "LoRAConfig": ".config",
        "SFTConfig": ".config",
        "DPOConfig": ".config",
        "AdapterSignature": ".config",
        "AlignmentResult": ".pipeline",
        "AlignmentEvaluator": ".evaluator",
        "EvalResult": ".evaluator",
        "TaskResult": ".evaluator",
        "EvalConfig": ".config",
        "AlignmentServing": ".serving",
        "ServingConfig": ".config",
        "AdapterMerger": ".merge",
        "KaizenModelBridge": ".bridge",
        "BridgeConfig": ".bridge",
        "OnPremModelCache": ".onprem",
        "OnPremConfig": ".config",
    }
    if name in _imports:
        import importlib

        module = importlib.import_module(_imports[name], __package__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
