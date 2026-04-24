# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""kailash-align: LLM fine-tuning and alignment framework."""
from __future__ import annotations

from typing import TYPE_CHECKING

from kailash_align._version import __version__

# Eager imports for symbols flagged by CodeQL
# py/modification-of-default-value when declared in __all__ via lazy
# __getattr__ only. Per rules/orphan-detection.md §6, module-scope
# public imports and __all__ must be consistent — CodeQL flags the
# drift where a name appears in __all__ but no module-scope import
# resolves it. These modules are cheap to import (no torch / no
# transformers load) so eager-import is safe.
from kailash_align.merge import AdapterMerger
from kailash_align.bridge import BridgeConfig, KaizenModelBridge
from kailash_align.onprem import OnPremModelCache
from kailash_align.config import OnPremConfig

# TYPE_CHECKING eager imports for symbols that wrap HEAVY dependencies
# (torch / transformers / peft / vllm). These are lazily-resolved at
# runtime via __getattr__ below so `import kailash_align` does NOT pay
# the torch-import cost. The TYPE_CHECKING block gives static analyzers
# (CodeQL py/undefined-export, pyright, mypy) a module-scope binding
# to resolve the names declared in __all__, closing the
# py/undefined-export finding without forcing eager runtime imports.
if TYPE_CHECKING:  # pragma: no cover — static-analysis only
    from kailash_align.registry import AdapterRegistry
    from kailash_align.pipeline import AlignmentPipeline, AlignmentResult
    from kailash_align.config import (
        AdapterSignature,
        AlignmentConfig,
        DPOConfig,
        EvalConfig,
        GRPOConfig,
        KTOConfig,
        LoRAConfig,
        OnlineDPOConfig,
        ORPOConfig,
        RLOOConfig,
        ServingConfig,
        SFTConfig,
    )
    from kailash_align.evaluator import (
        AlignmentEvaluator,
        EvalResult,
        TaskResult,
    )
    from kailash_align.serving import AlignmentServing
    from kailash_align.method_registry import METHOD_REGISTRY
    from kailash_align.rewards import RewardRegistry, reward_registry
    from kailash_align.gpu_memory import (
        GPUMemoryEstimate,
        estimate_training_memory,
    )
    from kailash_align.vllm_backend import (
        GenerationBackend,
        HFGenerationBackend,
        VLLMBackend,
        VLLMConfig,
    )

__all__ = [
    "__version__",
    # Core
    "AdapterRegistry",
    "AlignmentPipeline",
    "AlignmentResult",
    # Config
    "AlignmentConfig",
    "LoRAConfig",
    "SFTConfig",
    "DPOConfig",
    "KTOConfig",
    "ORPOConfig",
    "GRPOConfig",
    "RLOOConfig",
    "OnlineDPOConfig",
    "AdapterSignature",
    # Evaluation & Serving
    "AlignmentEvaluator",
    "EvalResult",
    "TaskResult",
    "EvalConfig",
    "AlignmentServing",
    "ServingConfig",
    # Utilities
    "AdapterMerger",
    "KaizenModelBridge",
    "BridgeConfig",
    "OnPremModelCache",
    "OnPremConfig",
    # Registry
    "METHOD_REGISTRY",
    "RewardRegistry",
    "reward_registry",
    # GPU Memory
    "GPUMemoryEstimate",
    "estimate_training_memory",
    # Generation Backend
    "VLLMBackend",
    "VLLMConfig",
    "GenerationBackend",
    "HFGenerationBackend",
]


def __getattr__(name: str):
    """Lazy imports to avoid loading torch/transformers on import."""
    _imports = {
        # Core
        "AdapterRegistry": ".registry",
        "AlignmentPipeline": ".pipeline",
        "AlignmentResult": ".pipeline",
        # Config
        "AlignmentConfig": ".config",
        "LoRAConfig": ".config",
        "SFTConfig": ".config",
        "DPOConfig": ".config",
        "KTOConfig": ".config",
        "ORPOConfig": ".config",
        "GRPOConfig": ".config",
        "RLOOConfig": ".config",
        "OnlineDPOConfig": ".config",
        "AdapterSignature": ".config",
        # Evaluation & Serving
        "AlignmentEvaluator": ".evaluator",
        "EvalResult": ".evaluator",
        "TaskResult": ".evaluator",
        "EvalConfig": ".config",
        "AlignmentServing": ".serving",
        "ServingConfig": ".config",
        # Utilities
        "AdapterMerger": ".merge",
        "KaizenModelBridge": ".bridge",
        "BridgeConfig": ".bridge",
        "OnPremModelCache": ".onprem",
        "OnPremConfig": ".config",
        # Registry
        "METHOD_REGISTRY": ".method_registry",
        "RewardRegistry": ".rewards",
        "reward_registry": ".rewards",
        # GPU Memory
        "GPUMemoryEstimate": ".gpu_memory",
        "estimate_training_memory": ".gpu_memory",
        # Generation Backend
        "VLLMBackend": ".vllm_backend",
        "VLLMConfig": ".vllm_backend",
        "GenerationBackend": ".vllm_backend",
        "HFGenerationBackend": ".vllm_backend",
    }
    if name in _imports:
        import importlib

        module = importlib.import_module(_imports[name], __package__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
