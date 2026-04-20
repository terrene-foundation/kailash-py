# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""BLEU evaluation for kailash-kaizen (``kaizen.evaluation.bleu``).

Thin wrapper around ``sacrebleu`` that keeps the algorithmic-metrics
namespace free of any LLM / cost / budget surface. Install the
``[evaluation]`` extra for the underlying package::

    pip install kailash-kaizen[evaluation]

Usage::

    from kaizen.evaluation import BLEU

    score = BLEU.corpus(
        predictions=["Paris is the capital of France."],
        references=["The capital of France is Paris."],
    )
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import polars as pl

logger = logging.getLogger(__name__)

__all__ = ["BLEU"]


def _require_sacrebleu() -> Any:
    try:
        import sacrebleu  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "BLEU requires sacrebleu. Install the evaluation extras: "
            "pip install kailash-kaizen[evaluation]"
        ) from exc
    return sacrebleu


class BLEU:
    """Namespace container for BLEU scoring methods."""

    @classmethod
    def corpus(
        cls,
        predictions: Sequence[str],
        references: Sequence[str],
    ) -> float:
        """Corpus-level BLEU score (single float 0..100).

        sacrebleu's convention is 0..100; we preserve it so callers
        using the raw score need no translation. For 0..1 scores use
        :meth:`corpus_normalized`.
        """
        if len(predictions) != len(references):
            raise ValueError(
                f"predictions/references length mismatch: "
                f"{len(predictions)} != {len(references)}"
            )
        sacrebleu = _require_sacrebleu()
        score = float(
            sacrebleu.corpus_bleu(list(predictions), [list(references)]).score
        )
        logger.info(
            "kaizen.evaluation.bleu.corpus.ok",
            extra={
                "evaluation_metric": "bleu",
                "evaluation_n_samples": len(predictions),
                "evaluation_bleu_score": score,
                "mode": "real",
            },
        )
        return score

    @classmethod
    def corpus_normalized(
        cls,
        predictions: Sequence[str],
        references: Sequence[str],
    ) -> float:
        """Corpus-level BLEU divided by 100 so the score lives in ``[0, 1]``."""
        return cls.corpus(predictions, references) / 100.0

    @classmethod
    def sentence(
        cls,
        predictions: Sequence[str],
        references: Sequence[str],
    ) -> pl.DataFrame:
        """Per-sentence BLEU scores as a polars DataFrame.

        Columns: ``idx, score`` — both as ``float64``. Scores in the
        sacrebleu 0..100 convention to match :meth:`corpus`.
        """
        if len(predictions) != len(references):
            raise ValueError(
                f"predictions/references length mismatch: "
                f"{len(predictions)} != {len(references)}"
            )
        sacrebleu = _require_sacrebleu()
        rows = []
        for i, (pred, ref) in enumerate(zip(predictions, references, strict=False)):
            s = float(sacrebleu.sentence_bleu(pred, [ref]).score)
            rows.append({"idx": i, "score": s})
        logger.info(
            "kaizen.evaluation.bleu.sentence.ok",
            extra={
                "evaluation_metric": "bleu",
                "evaluation_n_samples": len(rows),
                "mode": "real",
            },
        )
        return pl.DataFrame(rows)
