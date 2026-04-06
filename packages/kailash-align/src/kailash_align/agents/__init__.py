# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Alignment Kaizen agents -- LLM-first agents for fine-tuning lifecycle.

Requires ``pip install kailash-align[agents]`` (kailash-kaizen).
All agents follow the LLM-first rule: reasoning via Signatures,
tools are dumb data endpoints.
"""
from __future__ import annotations

__all__ = [
    "AlignmentStrategistAgent",
    "DataCurationAgent",
    "TrainingConfigAgent",
    "EvalInterpreterAgent",
]


def __getattr__(name: str):  # noqa: N807
    _map = {
        "AlignmentStrategistAgent": "kailash_align.agents.strategist",
        "DataCurationAgent": "kailash_align.agents.data_curation",
        "TrainingConfigAgent": "kailash_align.agents.training_config",
        "EvalInterpreterAgent": "kailash_align.agents.eval_interpreter",
    }
    if name in _map:
        import importlib

        module = importlib.import_module(_map[name])
        return getattr(module, name)
    raise AttributeError(f"module 'kailash_align.agents' has no attribute {name!r}")
