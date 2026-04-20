# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
#
# Portions of this module were originally contributed from MLFP
# (Apache-2.0) and re-authored for the Kailash ecosystem. See
# ``specs/alignment-diagnostics.md`` § "Attribution" for the full donation
# history (kailash-py issue #567, PR#3 of 7).
"""Alignment-lens diagnostics for kailash-align.

``AlignmentDiagnostics`` is the concrete Align adapter that satisfies the
``kailash.diagnostics.protocols.Diagnostic`` Protocol for an LLM
fine-tuning run. It consumes preference tuples, per-token log-probability
arrays, and training metric streams — it does NO model loading and
installs no hooks. The heavy training itself lives in
:class:`~kailash_align.AlignmentPipeline` (or any equivalent trainer);
this lens observes its output.

Three primary readings:

    1. **Pair evaluation** — :meth:`AlignmentDiagnostics.evaluate_pair`
       computes KL(base || tuned), reward-margin, and pairwise win-rate
       from paired log-probability arrays + a preference set.
    2. **Training-curve tracking** — :meth:`AlignmentDiagnostics.track_training`
       ingests an iterable of ``{step, reward, kl, loss, ...}`` dicts
       (or an :class:`~kailash_align.AlignmentPipeline` exposing
       ``metrics_stream()`` / ``metrics``). The buffered history is
       memory-bounded via the ``window`` constructor argument.
    3. **Reward-hacking detection** — :meth:`AlignmentDiagnostics.detect_reward_hacking`
       flags the canonical signature of a sudden reward spike
       co-occurring with a KL blow-up (the tuned model has learned a
       shortcut the reward model rewards but the base distribution does
       not support).

KL is implemented closed-form over paired per-token log-probabilities
(``KL(P || Q) ≈ mean(logP - logQ)`` with per-token clipping). ``trl``'s
statistical helpers (``trl.trainer.utils.kl_divergence``) are used as an
optimization when installed AND torch is importable; otherwise the
closed-form numpy path runs. ``trl`` is already in kailash-align's base
dependencies, so in practice the torch+trl path is used unless the
caller strips both.

``report()`` returns a structured dict with:
    - ``run_id`` — the session identifier (matches ``self.run_id``).
    - ``pairs`` — count of :meth:`evaluate_pair` readings recorded.
    - ``training_steps`` — count of training steps ingested.
    - ``reward_hacking_findings`` — count of flagged steps.
    - ``pair_summary`` / ``training_summary`` /
      ``reward_hacking`` — each is a ``{severity, message}`` dict.

Severity values are ``"HEALTHY"`` / ``"WARNING"`` / ``"CRITICAL"`` /
``"UNKNOWN"``. ``report()`` never raises on empty state — it returns a
dict whose sections read ``UNKNOWN`` when the corresponding reading has
not been taken.

The ``plot_*()`` methods return :class:`plotly.graph_objects.Figure`
objects. ``plotly`` is currently a transitive dependency of the
kailash-align base install, so the plot surface works out of the box;
the helpers route through ``_require_plotly()`` so a future extras-split
produces a loud, actionable ImportError rather than a bare
``ModuleNotFoundError``.

All DataFrames returned by ``*_df()`` accessors are polars. All plots
are plotly. No matplotlib, no pandas.

Quick start::

    from kailash_align.diagnostics import AlignmentDiagnostics

    with AlignmentDiagnostics(label="dpo_run42") as diag:
        diag.evaluate_pair(base_logprobs, tuned_logprobs, preferences)
        diag.track_training(pipeline.metrics_stream())
        diag.detect_reward_hacking(threshold=2.5)
        report = diag.report()

See ``specs/alignment-diagnostics.md`` for the full API contract and
``src/kailash/diagnostics/protocols.py`` for the cross-SDK Protocol.
"""
from __future__ import annotations

import logging
import math
import uuid
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence

import polars as pl

if TYPE_CHECKING:  # pragma: no cover — typing-only imports
    import plotly.graph_objects as go_types  # noqa: F401

logger = logging.getLogger(__name__)

__all__ = ["AlignmentDiagnostics"]


# ---------------------------------------------------------------------------
# Plot-dependency gating
# ---------------------------------------------------------------------------


def _require_plotly() -> Any:
    """Import and return the ``plotly.graph_objects`` module or raise loudly.

    Plotly is currently a transitive dependency of the kailash-align base
    install; the ``report()`` and ``*_df()`` accessors work without any
    import, but the ``plot_*()`` methods route through this helper so a
    future extras-split (or a stripped install) surfaces an actionable
    error naming the remediation rather than a bare ``ModuleNotFoundError``.
    """
    try:
        import plotly.graph_objects as go  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "Plotting methods require plotly. Install kailash-align with "
            "its base dependencies: pip install kailash-align"
        ) from exc
    return go


def _require_plotly_subplots() -> Any:
    """Return the ``plotly.subplots.make_subplots`` function or raise loudly."""
    try:
        from plotly.subplots import make_subplots  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "Plotting methods require plotly. Install kailash-align with "
            "its base dependencies: pip install kailash-align"
        ) from exc
    return make_subplots


# ---------------------------------------------------------------------------
# Plot theme (module-local — intentionally not a cross-package import)
# ---------------------------------------------------------------------------


_PLOT_TEMPLATE = "plotly_white"
_PRIMARY = "steelblue"
_WARN = "firebrick"
_ACCENT = "orange"
_MUTED = "lightgray"


# ---------------------------------------------------------------------------
# Data classes — session-internal record shapes
# ---------------------------------------------------------------------------


@dataclass
class _PairReading:
    label: str
    kl_divergence: float
    reward_margin: float
    win_rate: float
    n: int


@dataclass
class _TrainingStep:
    step: int
    reward: float
    kl: float
    loss: float
    extras: dict[str, Any]


@dataclass
class _HackFinding:
    step: int
    reward_zscore: float
    kl_value: float
    reward_value: float
    label: str


# ---------------------------------------------------------------------------
# AlignmentDiagnostics — concrete Diagnostic adapter
# ---------------------------------------------------------------------------


class AlignmentDiagnostics:
    """LLM fine-tuning / alignment diagnostics (Diagnostic Protocol).

    Records KL(base || tuned), reward-margin, pairwise win-rate, training
    metric streams, and reward-hacking findings; exposes polars DataFrame
    accessors, plotly visualisations, and an automated report that
    surfaces drifted-too-far, weak-preference-signal, and
    reward-hacking-suspected findings.

    The adapter satisfies the cross-SDK :class:`kailash.diagnostics.
    protocols.Diagnostic` Protocol (``run_id`` + ``__enter__`` +
    ``__exit__`` + ``report()``). ``isinstance(diag, Diagnostic)``
    returns ``True`` at runtime because the Protocol is
    ``@runtime_checkable``.

    Args:
        label: Short tag applied to every recorded reading (useful when
            comparing multiple runs side-by-side). Defaults to ``"run"``.
        window: Maximum number of training steps retained in the
            in-memory history buffer. Older steps are evicted FIFO once
            the buffer fills. Must be ``>= 1``. Defaults to ``10_000``.
        run_id: Optional correlation identifier for this diagnostic
            session. When omitted, a UUID4 hex is generated. Matches
            :class:`Diagnostic.run_id` in the cross-SDK Protocol.

    Raises:
        ValueError: If ``label`` is an empty string, ``window < 1``, or
            ``run_id`` is explicitly passed as an empty string.

    Example:
        >>> with AlignmentDiagnostics(label="dpo_run42") as diag:
        ...     diag.evaluate_pair(base_logprobs, tuned_logprobs, prefs)
        ...     diag.track_training(pipeline.metrics_stream())
        ...     diag.detect_reward_hacking(threshold=2.5)
        ...     report = diag.report()
    """

    def __init__(
        self,
        *,
        label: str = "run",
        window: int = 10_000,
        run_id: Optional[str] = None,
    ) -> None:
        if not isinstance(label, str) or not label:
            raise ValueError("label must be a non-empty string")
        if window < 1:
            raise ValueError("window must be >= 1")
        if run_id is not None and not run_id:
            raise ValueError("run_id must be a non-empty string when provided")

        self._label = label
        self._window = window
        # Satisfies kailash.diagnostics.protocols.Diagnostic.run_id.
        self.run_id: str = run_id if run_id is not None else uuid.uuid4().hex

        # Unbounded lists for pair readings + findings (low-cardinality;
        # one entry per evaluate_pair / detect_reward_hacking call).
        self._pair_log: list[_PairReading] = []
        self._hack_findings: list[_HackFinding] = []
        # Bounded training history — one entry per ingested step.
        self._training_log: deque[_TrainingStep] = deque(maxlen=window)

        logger.debug(
            "alignment_diagnostics.init",
            extra={
                "alignment_label": label,
                "alignment_run_id": self.run_id,
                "alignment_window": window,
            },
        )

    # ── Context-manager support ────────────────────────────────────────────

    def __enter__(self) -> "AlignmentDiagnostics":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> Optional[bool]:
        # Alignment diagnostics has no hooks to detach — the only
        # cleanup responsibility is to avoid raising from __exit__.
        return None

    # ── Pair evaluation ────────────────────────────────────────────────────

    def evaluate_pair(
        self,
        base_policy: Sequence[Sequence[float]],
        tuned_policy: Sequence[Sequence[float]],
        preferences: Sequence[dict[str, Any]],
        *,
        label: Optional[str] = None,
    ) -> pl.DataFrame:
        """Compute KL(base || tuned), reward margin, and pair win-rate.

        Args:
            base_policy: Per-example token log-probabilities from the
                base model. Length ``N``, each element a sequence of
                per-token log-probs.
            tuned_policy: Same shape, from the tuned model.
            preferences: Iterable of ``{chosen_reward, rejected_reward,
                chosen_won}`` dicts. ``chosen_won`` is coerced via
                ``bool()``; missing keys silently default to ``0.0`` /
                ``False`` so partial preference streams still produce a
                usable reading.
            label: Optional sub-label overriding the instance label.

        Returns:
            A one-row Polars DataFrame with ``label``, ``kl_divergence``,
            ``reward_margin``, ``win_rate``, and ``n`` columns.

        Raises:
            ValueError: If ``base_policy`` and ``tuned_policy`` have
                different lengths.
        """
        if len(base_policy) != len(tuned_policy):
            raise ValueError("base_policy and tuned_policy must be same length")
        label = label or self._label

        kls = [
            self._kl_from_logprobs(b, t) for b, t in zip(base_policy, tuned_policy)
        ]
        kl_mean = _mean(kls)

        if preferences:
            margins = [
                float(p.get("chosen_reward", 0.0))
                - float(p.get("rejected_reward", 0.0))
                for p in preferences
            ]
            wins = sum(1 for p in preferences if bool(p.get("chosen_won")))
            win_rate = wins / len(preferences)
            reward_margin = _mean(margins)
        else:
            win_rate = float("nan")
            reward_margin = float("nan")

        reading = _PairReading(
            label=label,
            kl_divergence=kl_mean,
            reward_margin=reward_margin,
            win_rate=win_rate,
            n=len(base_policy),
        )
        self._pair_log.append(reading)
        logger.debug(
            "alignment.evaluate_pair",
            extra={
                "alignment_run_id": self.run_id,
                "alignment_label": label,
                "alignment_kl": kl_mean,
                "alignment_reward_margin": reward_margin,
                "alignment_win_rate": win_rate,
                "alignment_n": len(base_policy),
            },
        )
        return pl.DataFrame(
            [
                {
                    "label": reading.label,
                    "kl_divergence": reading.kl_divergence,
                    "reward_margin": reading.reward_margin,
                    "win_rate": reading.win_rate,
                    "n": reading.n,
                }
            ]
        )

    def kl_divergence(
        self,
        p_logprobs: Sequence[float],
        q_logprobs: Sequence[float],
    ) -> float:
        """KL(p || q) from paired per-token log-probabilities.

        Delegates to the closed-form estimator. When ``trl`` is installed
        AND torch is importable, the ``trl.trainer.utils.kl_divergence``
        helper is used as a numerical optimization; otherwise the
        closed-form numpy path runs. The two paths are behaviorally
        equivalent up to floating-point rounding.
        """
        return self._kl_from_logprobs(p_logprobs, q_logprobs)

    def win_rate(self, preferences: Sequence[dict[str, Any]]) -> float:
        """Fraction of preference rows where the chosen policy won.

        Returns ``NaN`` for empty input (undefined for an empty sample).
        """
        if not preferences:
            return float("nan")
        wins = sum(1 for p in preferences if bool(p.get("chosen_won")))
        return wins / len(preferences)

    # ── Training-curve tracking ────────────────────────────────────────────

    def track_training(
        self,
        metrics: Iterable[dict[str, Any]] | Any,
    ) -> pl.DataFrame:
        """Record a training-metrics stream from an Align pipeline.

        Accepts either:
            * an iterable of ``{step, reward, kl, loss, ...}`` dicts, or
            * any object exposing a ``metrics_stream()`` method or a
              ``metrics`` attribute (e.g. a Kailash Align
              :class:`~kailash_align.AlignmentPipeline`).

        Any missing field defaults to ``float("nan")`` so partial
        streams (e.g. SFT runs without a reward signal) still produce a
        usable DataFrame. Extra keys are preserved in the ``extras``
        field of the stored record but are NOT surfaced in the returned
        DataFrame (which keeps a stable 4-column schema).

        The training history is memory-bounded — once the buffer hits
        its ``window`` capacity, the oldest step is evicted before the
        newest is appended.

        Returns:
            A polars DataFrame with ``step``, ``reward``, ``kl``,
            ``loss`` columns, one row per ingested step.
        """
        iterable = _resolve_metrics_iterable(metrics)
        rows: list[dict[str, Any]] = []
        for raw in iterable:
            step = int(raw.get("step", len(self._training_log)))
            reward = float(raw.get("reward", float("nan")))
            kl = float(raw.get("kl", raw.get("kl_divergence", float("nan"))))
            loss = float(raw.get("loss", float("nan")))
            extras = {
                k: v
                for k, v in raw.items()
                if k not in {"step", "reward", "kl", "kl_divergence", "loss"}
            }
            self._training_log.append(
                _TrainingStep(
                    step=step, reward=reward, kl=kl, loss=loss, extras=extras
                )
            )
            rows.append({"step": step, "reward": reward, "kl": kl, "loss": loss})
        df = pl.DataFrame(rows) if rows else _empty_training_df()
        logger.debug(
            "alignment.track_training",
            extra={
                "alignment_run_id": self.run_id,
                "alignment_steps_ingested": df.height,
                "alignment_buffer_size": len(self._training_log),
            },
        )
        return df

    # ── Reward hacking detection ───────────────────────────────────────────

    def detect_reward_hacking(
        self,
        history: Optional[Sequence[dict[str, Any]]] = None,
        *,
        threshold: float = 2.5,
        label: Optional[str] = None,
    ) -> pl.DataFrame:
        """Flag reward-spike + KL-blowup steps.

        Reward-hacking's canonical signature is a sudden jump in reward
        that coincides with a divergence blow-up — the tuned model has
        learned a shortcut the reward model rewards but the base
        distribution does not support. The detector flags any step
        where ``(reward[t] - reward[t-1]) / stdev(rewards) > threshold``
        AND ``kl[t] > max(median(kl) * 1.5, 0.05)``.

        Args:
            history: Optional pre-recorded training history. When
                ``None``, uses the history accumulated via
                :meth:`track_training`.
            threshold: Z-score above which a reward delta is flagged.
                Must be positive. Defaults to ``2.5``.
            label: Optional label applied to findings.

        Returns:
            A polars DataFrame of findings (``step``,
            ``reward_zscore``, ``kl_value``, ``reward_value``,
            ``label``). Empty DataFrame when no findings.

        Raises:
            ValueError: If ``threshold`` is non-positive.
        """
        if threshold <= 0:
            raise ValueError("threshold must be positive")

        if history is not None:
            series: list[_TrainingStep] = [
                _TrainingStep(
                    step=int(h.get("step", i)),
                    reward=float(h.get("reward", float("nan"))),
                    kl=float(h.get("kl", float("nan"))),
                    loss=float(h.get("loss", float("nan"))),
                    extras={},
                )
                for i, h in enumerate(history)
            ]
        else:
            series = list(self._training_log)
        if len(series) < 4:
            return _empty_findings_df()

        rewards = [s.reward for s in series if not math.isnan(s.reward)]
        if len(rewards) < 4:
            return _empty_findings_df()
        mu = _mean(rewards)
        sigma = _stdev(rewards, mu) or 1e-9
        median_kl = _median([s.kl for s in series if not math.isnan(s.kl)])

        label = label or self._label
        findings: list[_HackFinding] = []
        for prev, cur in zip(series, series[1:]):
            if math.isnan(cur.reward) or math.isnan(prev.reward):
                continue
            delta = cur.reward - prev.reward
            z = delta / sigma
            if (
                z > threshold
                and not math.isnan(cur.kl)
                and cur.kl > max(median_kl * 1.5, 0.05)
            ):
                findings.append(
                    _HackFinding(
                        step=cur.step,
                        reward_zscore=z,
                        kl_value=cur.kl,
                        reward_value=cur.reward,
                        label=label,
                    )
                )

        self._hack_findings.extend(findings)
        if findings:
            # WARN is the right level here: "reward-hacking detected" is
            # an operator-actionable event, and the log does NOT expose
            # any schema / column / PII content — it reports counts + a
            # z-score threshold. See rules/observability.md §3.
            logger.warning(
                "alignment.reward_hacking.detected",
                extra={
                    "alignment_run_id": self.run_id,
                    "alignment_label": label,
                    "alignment_n_findings": len(findings),
                    "alignment_threshold_z": threshold,
                },
            )
        return (
            pl.DataFrame(
                [
                    {
                        "step": f.step,
                        "reward_zscore": f.reward_zscore,
                        "kl_value": f.kl_value,
                        "reward_value": f.reward_value,
                        "label": f.label,
                    }
                    for f in findings
                ]
            )
            if findings
            else _empty_findings_df()
        )

    # ── DataFrame accessors ────────────────────────────────────────────────

    def pair_df(self) -> pl.DataFrame:
        """Return the cumulative pair-reading log as a polars DataFrame."""
        if not self._pair_log:
            return pl.DataFrame(
                schema={
                    "label": pl.Utf8,
                    "kl_divergence": pl.Float64,
                    "reward_margin": pl.Float64,
                    "win_rate": pl.Float64,
                    "n": pl.Int64,
                }
            )
        return pl.DataFrame(
            [
                {
                    "label": r.label,
                    "kl_divergence": r.kl_divergence,
                    "reward_margin": r.reward_margin,
                    "win_rate": r.win_rate,
                    "n": r.n,
                }
                for r in self._pair_log
            ]
        )

    def training_df(self) -> pl.DataFrame:
        """Return the buffered training-step history as a polars DataFrame."""
        if not self._training_log:
            return _empty_training_df()
        return pl.DataFrame(
            [
                {"step": s.step, "reward": s.reward, "kl": s.kl, "loss": s.loss}
                for s in self._training_log
            ]
        )

    def findings_df(self) -> pl.DataFrame:
        """Return all recorded reward-hacking findings as a polars DataFrame."""
        if not self._hack_findings:
            return _empty_findings_df()
        return pl.DataFrame(
            [
                {
                    "step": f.step,
                    "reward_zscore": f.reward_zscore,
                    "kl_value": f.kl_value,
                    "reward_value": f.reward_value,
                    "label": f.label,
                }
                for f in self._hack_findings
            ]
        )

    # ── Plots ──────────────────────────────────────────────────────────────

    def plot_training_curves(self) -> "go_types.Figure":
        """Reward and KL curves over training steps.

        Returns a two-trace plotly Figure with reward on the primary
        y-axis and KL on the secondary y-axis. Empty state produces a
        titled figure with a "no data" annotation rather than raising.
        """
        go = _require_plotly()
        df = self.training_df()
        fig = go.Figure()
        if df.height == 0:
            fig.update_layout(
                title="Alignment Training Curves — no data",
                template=_PLOT_TEMPLATE,
            )
            return fig
        fig.add_trace(
            go.Scatter(
                x=df["step"].to_list(),
                y=df["reward"].to_list(),
                mode="lines+markers",
                name="reward",
                line=dict(color=_PRIMARY, width=2),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=df["step"].to_list(),
                y=df["kl"].to_list(),
                mode="lines+markers",
                name="kl",
                line=dict(color=_WARN, width=2),
                yaxis="y2",
            )
        )
        fig.update_layout(
            title="Alignment Training Curves",
            xaxis_title="step",
            yaxis=dict(title="reward"),
            yaxis2=dict(
                title="KL divergence",
                overlaying="y",
                side="right",
            ),
            template=_PLOT_TEMPLATE,
            hovermode="x unified",
        )
        return fig

    def plot_reward_vs_kl(self) -> "go_types.Figure":
        """Reward-vs-KL scatter with reward-hacking findings highlighted.

        One dot per training step. Findings from
        :meth:`detect_reward_hacking` are overlaid as red X markers.
        """
        go = _require_plotly()
        df = self.training_df()
        fig = go.Figure()
        if df.height == 0:
            fig.update_layout(
                title="Reward vs KL — no data",
                template=_PLOT_TEMPLATE,
            )
            return fig
        fig.add_trace(
            go.Scatter(
                x=df["kl"].to_list(),
                y=df["reward"].to_list(),
                mode="markers",
                marker=dict(
                    color=_PRIMARY,
                    size=8,
                    line=dict(width=1, color=_MUTED),
                ),
                name="steps",
            )
        )
        findings = self.findings_df()
        if findings.height:
            fig.add_trace(
                go.Scatter(
                    x=findings["kl_value"].to_list(),
                    y=findings["reward_value"].to_list(),
                    mode="markers",
                    marker=dict(
                        color=_WARN,
                        size=14,
                        symbol="x",
                        line=dict(width=2),
                    ),
                    name="reward-hacking finding",
                )
            )
        fig.update_layout(
            title="Reward vs KL (reward-hacking scan)",
            xaxis_title="KL divergence",
            yaxis_title="reward",
            template=_PLOT_TEMPLATE,
            hovermode="closest",
        )
        return fig

    def plot_win_rate(self) -> "go_types.Figure":
        """Bar chart of pair win-rates, one bar per recorded pair evaluation."""
        go = _require_plotly()
        df = self.pair_df()
        fig = go.Figure()
        if df.height == 0:
            fig.update_layout(
                title="Pair win-rate — no data",
                template=_PLOT_TEMPLATE,
            )
            return fig
        fig.add_trace(
            go.Bar(
                x=df["label"].to_list(),
                y=df["win_rate"].to_list(),
                marker_color=_PRIMARY,
                name="win_rate",
            )
        )
        fig.add_hline(
            y=0.5,
            line=dict(color=_ACCENT, dash="dash"),
            annotation_text="chance (0.5)",
        )
        fig.update_layout(
            title="Pair Win-Rate by Label",
            xaxis_title="label",
            yaxis_title="win rate",
            template=_PLOT_TEMPLATE,
        )
        return fig

    def plot_alignment_dashboard(self) -> "go_types.Figure":
        """2×2 composite dashboard: reward + KL curves, win-rate, reward-vs-KL.

        Convenience surface that composes the other plot helpers into
        one :class:`plotly.graph_objects.Figure` suitable for notebook
        display. Findings from :meth:`detect_reward_hacking` are
        overlaid on the reward-vs-KL scatter.
        """
        go = _require_plotly()
        make_subplots = _require_plotly_subplots()

        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                "Reward over training steps",
                "KL divergence over training steps",
                "Pair win-rate",
                "Reward vs KL (reward-hacking scan)",
            ),
        )

        train_df = self.training_df()
        if train_df.height:
            fig.add_trace(
                go.Scatter(
                    x=train_df["step"].to_list(),
                    y=train_df["reward"].to_list(),
                    mode="lines+markers",
                    line=dict(color=_PRIMARY),
                    name="reward",
                ),
                row=1,
                col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=train_df["step"].to_list(),
                    y=train_df["kl"].to_list(),
                    mode="lines+markers",
                    line=dict(color=_WARN),
                    name="kl",
                ),
                row=1,
                col=2,
            )
            fig.add_trace(
                go.Scatter(
                    x=train_df["kl"].to_list(),
                    y=train_df["reward"].to_list(),
                    mode="markers",
                    marker=dict(
                        color=_PRIMARY,
                        size=8,
                        line=dict(width=1, color=_MUTED),
                    ),
                    name="steps",
                ),
                row=2,
                col=2,
            )
            findings_df = self.findings_df()
            if findings_df.height:
                fig.add_trace(
                    go.Scatter(
                        x=findings_df["kl_value"].to_list(),
                        y=findings_df["reward_value"].to_list(),
                        mode="markers",
                        marker=dict(
                            color=_WARN,
                            size=14,
                            symbol="x",
                            line=dict(width=2),
                        ),
                        name="reward-hacking finding",
                    ),
                    row=2,
                    col=2,
                )

        pair_df = self.pair_df()
        if pair_df.height:
            fig.add_trace(
                go.Bar(
                    x=pair_df["label"].to_list(),
                    y=pair_df["win_rate"].to_list(),
                    marker_color=_PRIMARY,
                    name="win_rate",
                ),
                row=2,
                col=1,
            )

        fig.update_layout(
            title="Alignment Training Report",
            template=_PLOT_TEMPLATE,
            showlegend=False,
            height=640,
        )
        return fig

    # ── Automated report (Diagnostic.report contract) ──────────────────────

    def report(self) -> dict[str, Any]:
        """Return a structured summary of the captured diagnostic session.

        The return shape satisfies :meth:`kailash.diagnostics.protocols.
        Diagnostic.report`. Keys:

          * ``run_id`` — the session identifier (matches ``self.run_id``).
          * ``pairs`` — count of pair-evaluation readings recorded.
          * ``training_steps`` — count of training steps ingested.
          * ``reward_hacking_findings`` — count of flagged steps.
          * ``pair_summary`` — ``{"severity", "message"}``.
          * ``training_summary`` — ``{"severity", "message"}``.
          * ``reward_hacking`` — ``{"severity", "message"}``.

        Severity values are ``"HEALTHY"`` / ``"WARNING"`` /
        ``"CRITICAL"`` / ``"UNKNOWN"``. The method never raises on
        empty state — missing readings report ``UNKNOWN``.
        """
        out: dict[str, Any] = {
            "run_id": self.run_id,
            "pairs": len(self._pair_log),
            "training_steps": len(self._training_log),
            "reward_hacking_findings": len(self._hack_findings),
        }

        # 1. Pair-evaluation summary.
        pair_df = self.pair_df()
        if pair_df.height:
            max_kl = float(pair_df["kl_divergence"].max() or 0.0)
            min_margin_val = pair_df["reward_margin"].min()
            min_margin = (
                float(min_margin_val)
                if isinstance(min_margin_val, (int, float))
                else 0.0
            )
            if max_kl > 1.0:
                out["pair_summary"] = {
                    "severity": "CRITICAL",
                    "message": (
                        f"KL={max_kl:.3f} > 1.0 — tuned model drifted far from "
                        "base. Reduce LR, add KL-regularization, or shorten "
                        "the training run."
                    ),
                }
            elif not math.isnan(min_margin) and min_margin < 0.05:
                out["pair_summary"] = {
                    "severity": "WARNING",
                    "message": (
                        f"Reward margin={min_margin:.3f} < 0.05 — preference "
                        "signal is too weak. Check reward-model calibration or "
                        "increase preference-data quality."
                    ),
                }
            else:
                out["pair_summary"] = {
                    "severity": "HEALTHY",
                    "message": (
                        f"{pair_df.height} pair reading(s): max KL={max_kl:.3f}, "
                        f"min margin={min_margin:.3f}."
                    ),
                }
        else:
            out["pair_summary"] = {
                "severity": "UNKNOWN",
                "message": "No pair evaluations recorded — call evaluate_pair().",
            }

        # 2. Training-curve summary.
        train_df = self.training_df()
        if train_df.height:
            mean_r = float(train_df["reward"].mean() or 0.0)
            mean_kl = float(train_df["kl"].mean() or 0.0)
            # Loss trend: compare first vs last quintile.
            if train_df.height >= 10:
                quintile = max(1, train_df.height // 5)
                early_loss = float(
                    train_df["loss"].head(quintile).mean() or 0.0
                )
                late_loss = float(
                    train_df["loss"].tail(quintile).mean() or 0.0
                )
                if not math.isnan(early_loss) and not math.isnan(late_loss):
                    if late_loss > early_loss * 1.1:
                        severity = "WARNING"
                        message = (
                            f"Loss trending up: early={early_loss:.3f}, "
                            f"late={late_loss:.3f}. Training may be diverging."
                        )
                    elif late_loss < early_loss * 0.95:
                        severity = "HEALTHY"
                        message = (
                            f"Loss trending down: early={early_loss:.3f}, "
                            f"late={late_loss:.3f}. Training is converging."
                        )
                    else:
                        severity = "HEALTHY"
                        message = (
                            f"Loss plateau: early={early_loss:.3f}, "
                            f"late={late_loss:.3f}."
                        )
                else:
                    severity = "HEALTHY"
                    message = (
                        f"{train_df.height} steps, mean reward={mean_r:.3f}, "
                        f"mean KL={mean_kl:.3f}."
                    )
            else:
                severity = "HEALTHY"
                message = (
                    f"{train_df.height} steps, mean reward={mean_r:.3f}, "
                    f"mean KL={mean_kl:.3f}."
                )
            out["training_summary"] = {"severity": severity, "message": message}
        else:
            out["training_summary"] = {
                "severity": "UNKNOWN",
                "message": "No training steps tracked — call track_training().",
            }

        # 3. Reward-hacking summary.
        findings_df = self.findings_df()
        if findings_df.height:
            top = findings_df.row(0, named=True)
            out["reward_hacking"] = {
                "severity": "WARNING",
                "message": (
                    f"{findings_df.height} suspected step(s). Worst: step "
                    f"{top['step']}, z={top['reward_zscore']:.2f}, "
                    f"kl={top['kl_value']:.3f}. Fix: reduce KL budget, "
                    "strengthen reward model, or shorten training."
                ),
            }
        elif self._training_log:
            out["reward_hacking"] = {
                "severity": "HEALTHY",
                "message": (
                    "No reward-hacking signatures detected "
                    f"(threshold scan over {len(self._training_log)} steps)."
                ),
            }
        else:
            out["reward_hacking"] = {
                "severity": "UNKNOWN",
                "message": (
                    "No training history to scan — call track_training() "
                    "followed by detect_reward_hacking()."
                ),
            }

        return out

    # ── Internal helpers ───────────────────────────────────────────────────

    def _kl_from_logprobs(
        self,
        p_logprobs: Sequence[float],
        q_logprobs: Sequence[float],
    ) -> float:
        """Closed-form KL estimator from paired per-token log-probabilities.

        Primary implementation. When ``trl`` is installed AND torch is
        importable, the ``trl.trainer.utils.kl_divergence`` helper is
        used as a numerical optimization; otherwise the closed-form
        numpy-free path runs. The two paths are behaviorally equivalent
        up to floating-point rounding; the optimization is opportunistic
        and NEVER a fallback for missing deps — trl + torch are base
        deps of kailash-align, so the optimized path is the default in
        practice.
        """
        # Fast path: torch + trl available (both in kailash-align base deps).
        try:
            import torch  # noqa: PLC0415
            from trl.trainer.utils import kl_divergence as trl_kl  # type: ignore[import-not-found]  # noqa: PLC0415
        except ImportError:
            return _kl_closed_form(p_logprobs, q_logprobs)
        except Exception:  # pragma: no cover — defensive for odd trl builds
            return _kl_closed_form(p_logprobs, q_logprobs)
        try:
            p = torch.tensor(list(p_logprobs), dtype=torch.float32)
            q = torch.tensor(list(q_logprobs), dtype=torch.float32)
            return float(trl_kl(p, q).mean().item())
        except Exception as exc:  # pragma: no cover — defensive
            # If the trl path fails numerically (e.g. tensor shape
            # mismatch the closed-form path handles gracefully), fall
            # back rather than propagate. DEBUG-level so forensic grep
            # still catches the transition. Structured field is prefixed
            # (alignment_error) to avoid LogRecord attribute collisions.
            logger.debug(
                "alignment.kl_trl_optimization_failed",
                extra={
                    "alignment_run_id": self.run_id,
                    "alignment_error": str(exc),
                },
            )
            return _kl_closed_form(p_logprobs, q_logprobs)


# ---------------------------------------------------------------------------
# Module-level numeric helpers
# ---------------------------------------------------------------------------


def _mean(xs: Sequence[float]) -> float:
    xs = [x for x in xs if not math.isnan(x)]
    return sum(xs) / len(xs) if xs else float("nan")


def _stdev(xs: Sequence[float], mu: float) -> float:
    xs = [x for x in xs if not math.isnan(x)]
    if len(xs) < 2:
        return 0.0
    return math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1))


def _median(xs: Sequence[float]) -> float:
    xs = sorted(x for x in xs if not math.isnan(x))
    if not xs:
        return 0.0
    mid = len(xs) // 2
    if len(xs) % 2:
        return xs[mid]
    return 0.5 * (xs[mid - 1] + xs[mid])


def _kl_closed_form(
    p_logprobs: Sequence[float],
    q_logprobs: Sequence[float],
) -> float:
    """KL(P || Q) estimator from paired token log-probabilities.

    Given log p(x_t) and log q(x_t) for the same sequence, the Monte
    Carlo estimator is ``E_{x ~ P}[log p - log q] ≈ mean(p_logprobs -
    q_logprobs)``. Per-token differences are clipped to ``[-50, 50]``
    so a single pathological token cannot dominate the mean.
    """
    n = min(len(p_logprobs), len(q_logprobs))
    if n == 0:
        return 0.0
    total = 0.0
    for i in range(n):
        d = float(p_logprobs[i]) - float(q_logprobs[i])
        # Clip extreme values so a single bad token can't dominate.
        d = max(-50.0, min(50.0, d))
        total += d
    return total / n


def _resolve_metrics_iterable(obj: Any) -> Iterable[dict[str, Any]]:
    """Extract a metrics iterable from a pipeline-like object or a list.

    Supports:
        * ``None`` — treated as empty.
        * Objects with a ``metrics_stream()`` method — called with no args.
        * Objects with a ``.metrics`` attribute — materialised to a list.
        * Any other iterable of dicts — passed through.
    """
    if obj is None:
        return []
    if hasattr(obj, "metrics_stream"):
        return obj.metrics_stream()
    if hasattr(obj, "metrics"):
        return list(obj.metrics)
    return obj  # assume iterable of dicts


def _empty_training_df() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "step": pl.Int64,
            "reward": pl.Float64,
            "kl": pl.Float64,
            "loss": pl.Float64,
        }
    )


def _empty_findings_df() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "step": pl.Int64,
            "reward_zscore": pl.Float64,
            "kl_value": pl.Float64,
            "reward_value": pl.Float64,
            "label": pl.Utf8,
        }
    )
