# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ML Kaizen agents -- LLM-first agents for ML lifecycle augmentation.

Requires ``pip install kailash-ml[agents]`` (kailash-kaizen).
All agents follow the LLM-first rule: reasoning via Signatures,
tools are dumb data endpoints.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Eager for static analyzers (CodeQL py/undefined-export, pyright, mypy,
    # Sphinx autodoc). Runtime loading stays lazy via __getattr__ below so
    # kailash-ml users don't pay the kaizen-import cost without [agents] extra.
    from kailash_ml.agents.data_scientist import DataScientistAgent
    from kailash_ml.agents.drift_analyst import DriftAnalystAgent
    from kailash_ml.agents.experiment_interpreter import ExperimentInterpreterAgent
    from kailash_ml.agents.feature_engineer import FeatureEngineerAgent
    from kailash_ml.agents.model_selector import ModelSelectorAgent
    from kailash_ml.agents.retraining_decision import RetrainingDecisionAgent

__all__ = [
    "DataScientistAgent",
    "FeatureEngineerAgent",
    "ModelSelectorAgent",
    "ExperimentInterpreterAgent",
    "DriftAnalystAgent",
    "RetrainingDecisionAgent",
]


def __getattr__(name: str):  # noqa: N807
    _map = {
        "DataScientistAgent": "kailash_ml.agents.data_scientist",
        "FeatureEngineerAgent": "kailash_ml.agents.feature_engineer",
        "ModelSelectorAgent": "kailash_ml.agents.model_selector",
        "ExperimentInterpreterAgent": "kailash_ml.agents.experiment_interpreter",
        "DriftAnalystAgent": "kailash_ml.agents.drift_analyst",
        "RetrainingDecisionAgent": "kailash_ml.agents.retraining_decision",
    }
    if name in _map:
        import importlib

        module = importlib.import_module(_map[name])
        return getattr(module, name)
    raise AttributeError(f"module 'kailash_ml.agents' has no attribute {name!r}")
