# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""ROUGE evaluation for kailash-kaizen (``kaizen.evaluation.rouge``).

Thin polars-native wrapper around ``rouge-score`` that keeps the
algorithmic-metrics namespace free of any LLM / cost / budget surface.
Install the ``[evaluation]`` extra for the underlying package::

    pip install kailash-kaizen[evaluation]

Usage::

    from kaizen.evaluation import ROUGE

    df = ROUGE.score(
        predictions=["Paris is the capital of France."],
        references=["The capital of France is Paris."],
        rouge_type="rougeL",
    )
    print(df["fmeasure"][0])
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import polars as pl

logger = logging.getLogger(__name__)

__all__ = ["ROUGE"]


def _require_rouge_score() -> Any:
    """Import ``rouge_score.rouge_scorer`` or raise loudly.

    Per ``rules/dependencies.md`` "Optional Extras with Loud Failure":
    silent degradation to ``None`` is BLOCKED.
    """
    try:
        from rouge_score import rouge_scorer  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "ROUGE requires rouge-score. Install the evaluation extras: "
            "pip install kailash-kaizen[evaluation]"
        ) from exc
    return rouge_scorer


class ROUGE:
    """Namespace container for ROUGE scoring methods.

    Public methods are classmethods so callers write
    ``ROUGE.score(...)`` uniformly.
    """

    #: Supported rouge types — ``rouge1`` / ``rouge2`` / ``rougeL``.
    SUPPORTED_TYPES: tuple[str, ...] = ("rouge1", "rouge2", "rougeL", "rougeLsum")

    @classmethod
    def score(
        cls,
        predictions: Sequence[str],
        references: Sequence[str],
        *,
        rouge_type: str = "rougeL",
        use_stemmer: bool = True,
    ) -> pl.DataFrame:
        """Return one-row-per-pair DataFrame with precision/recall/fmeasure.

        Args:
            predictions: Sequence of predicted strings.
            references: Same-length sequence of reference strings.
            rouge_type: One of :attr:`SUPPORTED_TYPES`.
            use_stemmer: Stem tokens before scoring (default ``True``
                to match the rouge-score library default).

        Returns:
            Polars DataFrame with columns ``idx, precision, recall,
            fmeasure``.

        Raises:
            ValueError: On length mismatch or unsupported ``rouge_type``.
            ImportError: When ``rouge-score`` is not installed; names
                the ``[evaluation]`` extra.
        """
        if len(predictions) != len(references):
            raise ValueError(
                f"predictions/references length mismatch: "
                f"{len(predictions)} != {len(references)}"
            )
        if rouge_type not in cls.SUPPORTED_TYPES:
            raise ValueError(
                f"rouge_type must be one of {cls.SUPPORTED_TYPES}, "
                f"got {rouge_type!r}."
            )
        rouge_scorer = _require_rouge_score()
        scorer = rouge_scorer.RougeScorer([rouge_type], use_stemmer=use_stemmer)

        rows = []
        for i, (pred, ref) in enumerate(zip(predictions, references, strict=False)):
            s = scorer.score(ref, pred)[rouge_type]
            rows.append(
                {
                    "idx": i,
                    "precision": float(s.precision),
                    "recall": float(s.recall),
                    "fmeasure": float(s.fmeasure),
                }
            )
        logger.info(
            "kaizen.evaluation.rouge.ok",
            extra={
                "evaluation_metric": "rouge",
                "evaluation_rouge_type": rouge_type,
                "evaluation_n_samples": len(rows),
                "mode": "real",
            },
        )
        return pl.DataFrame(rows)

    @classmethod
    def corpus_fmeasure(
        cls,
        predictions: Sequence[str],
        references: Sequence[str],
        *,
        rouge_type: str = "rougeL",
        use_stemmer: bool = True,
    ) -> float:
        """Arithmetic mean of per-pair ``fmeasure``.

        Convenience wrapper around :meth:`score` for callers who want
        a single scalar. Returns ``0.0`` on empty inputs.
        """
        df = cls.score(
            predictions,
            references,
            rouge_type=rouge_type,
            use_stemmer=use_stemmer,
        )
        if df.height == 0:
            return 0.0
        raw = df["fmeasure"].mean()
        return float(raw) if raw is not None else 0.0
