# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Alignment Kaizen agents -- LLM-first agents for fine-tuning lifecycle.

Requires ``pip install kailash-align[agents]`` (kailash-kaizen).
All agents follow the LLM-first rule: reasoning via Signatures,
tools are dumb data endpoints.
"""
from __future__ import annotations

# Eager imports for CodeQL py/modification-of-default-value —
# rules/orphan-detection.md §6 mandates that every __all__ entry resolve
# to a module-scope import. Each sub-module lazy-imports kaizen at call
# time via `_import_kaizen()`, so importing the module object here does
# NOT pull in kailash-kaizen; the ImportError is still raised later when
# the agent is instantiated without the [agents] extra.
from kailash_align.agents.strategist import AlignmentStrategistAgent
from kailash_align.agents.data_curation import DataCurationAgent
from kailash_align.agents.training_config import TrainingConfigAgent
from kailash_align.agents.eval_interpreter import EvalInterpreterAgent

__all__ = [
    "AlignmentStrategistAgent",
    "DataCurationAgent",
    "TrainingConfigAgent",
    "EvalInterpreterAgent",
]
