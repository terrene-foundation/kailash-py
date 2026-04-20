# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Algorithmic NLP evaluation metrics for kailash-kaizen.

This namespace hosts pure-algorithmic metrics (no LLM call, no cost
tracking, no budget surface). The split from :mod:`kaizen.judges` is
intentional: the judges namespace carries LLM-specific semantics
(Delegate dispatch, CostTracker, JudgeBudgetExhaustedError,
tenant_id propagation) while this namespace is lightweight math on
strings.

Public surface::

    from kaizen.evaluation import ROUGE, BLEU, BERTScore

    rouge_df = ROUGE.score(predictions=["..."], references=["..."])
    bleu_corpus = BLEU.corpus(predictions=["..."], references=["..."])
    bert_df = BERTScore.score(predictions=["..."], references=["..."])

Each metric class exposes classmethod entry points so downstream
code uses ``ROUGE.score(...)`` uniformly rather than mixing
functions and methods.

Installation::

    pip install kailash-kaizen[evaluation]

The base kaizen install does NOT pull rouge-score / sacrebleu /
bert-score — each metric raises a loud, actionable
:class:`ImportError` at call time naming the ``[evaluation]`` extra
per ``rules/dependencies.md`` "Optional Extras with Loud Failure".
"""
from __future__ import annotations

from kaizen.evaluation.bertscore import BERTScore
from kaizen.evaluation.bleu import BLEU
from kaizen.evaluation.rouge import ROUGE

__all__ = [
    "ROUGE",
    "BLEU",
    "BERTScore",
]
