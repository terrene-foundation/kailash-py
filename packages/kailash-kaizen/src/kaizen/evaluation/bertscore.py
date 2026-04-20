# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""BERTScore evaluation for kailash-kaizen (``kaizen.evaluation.bertscore``).

Thin wrapper around ``bert-score`` that keeps the algorithmic-metrics
namespace free of any LLM / cost / budget surface.

Install::

    pip install kailash-kaizen[evaluation]

``bert-score`` pulls transformers + torch at import time — the
:func:`_require_bert_score` helper surfaces the ``[evaluation]``
extra name in the ImportError so the operator knows the exact fix.

Usage::

    from kaizen.evaluation import BERTScore

    df = BERTScore.score(
        predictions=["Paris is the capital of France."],
        references=["The capital of France is Paris."],
        lang="en",
    )
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

import polars as pl

logger = logging.getLogger(__name__)

__all__ = ["BERTScore"]


def _require_bert_score() -> Any:
    try:
        from bert_score import score as _bs  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "BERTScore requires bert-score. Install the evaluation extras: "
            "pip install kailash-kaizen[evaluation]"
        ) from exc
    return _bs


class BERTScore:
    """Namespace container for BERTScore scoring methods."""

    @classmethod
    def score(
        cls,
        predictions: Sequence[str],
        references: Sequence[str],
        *,
        lang: str = "en",
        model_type: str | None = None,
        verbose: bool = False,
    ) -> pl.DataFrame:
        """Return per-pair precision / recall / f1 as a polars DataFrame.

        Args:
            predictions: Sequence of predicted strings.
            references: Same-length sequence of reference strings.
            lang: ISO-639-1 language code (``"en"`` / ``"zh"`` / ...).
            model_type: Optional HuggingFace model name. When ``None``
                bert-score picks its per-language default.
            verbose: Forward to bert-score's progress reporter.

        Returns:
            Polars DataFrame with columns ``idx, precision, recall, f1``.

        Raises:
            ValueError: On length mismatch.
            ImportError: When ``bert-score`` is not installed; names
                the ``[evaluation]`` extra.
        """
        if len(predictions) != len(references):
            raise ValueError(
                f"predictions/references length mismatch: "
                f"{len(predictions)} != {len(references)}"
            )
        if not predictions:
            return pl.DataFrame(
                schema={
                    "idx": pl.Int64,
                    "precision": pl.Float64,
                    "recall": pl.Float64,
                    "f1": pl.Float64,
                }
            )
        _bs = _require_bert_score()
        p, r, f = _bs(
            list(predictions),
            list(references),
            lang=lang,
            model_type=model_type,
            verbose=verbose,
        )
        rows = []
        for i in range(len(predictions)):
            rows.append(
                {
                    "idx": i,
                    "precision": float(p[i]),
                    "recall": float(r[i]),
                    "f1": float(f[i]),
                }
            )
        logger.info(
            "kaizen.evaluation.bertscore.ok",
            extra={
                "evaluation_metric": "bertscore",
                "evaluation_n_samples": len(rows),
                "evaluation_lang": lang,
                "evaluation_model_type": model_type,
                "mode": "real",
            },
        )
        return pl.DataFrame(rows)

    @classmethod
    def corpus_f1(
        cls,
        predictions: Sequence[str],
        references: Sequence[str],
        *,
        lang: str = "en",
        model_type: str | None = None,
    ) -> float:
        """Arithmetic mean of per-pair ``f1``. Returns ``0.0`` on empty input."""
        df = cls.score(predictions, references, lang=lang, model_type=model_type)
        if df.height == 0:
            return 0.0
        raw = df["f1"].mean()
        return float(raw) if raw is not None else 0.0
