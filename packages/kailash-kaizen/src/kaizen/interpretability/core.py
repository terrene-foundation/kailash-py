# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
#
# Portions of this module were originally contributed from MLFP
# (Apache-2.0) and re-authored for the Kailash ecosystem. See
# ``specs/kaizen-interpretability.md`` § "Attribution" for the full
# donation history (kailash-py issue #567, PR#4 of 7).
"""Open-weight LLM interpretability diagnostics for kailash-kaizen.

``InterpretabilityDiagnostics`` is the concrete Kaizen adapter that
satisfies the ``kailash.diagnostics.protocols.Diagnostic`` Protocol for
a post-hoc interpretability session on a local open-weight language
model. It loads the weights once (lazy, on first use), then exposes
four analyses that share the cached forward cache when possible:

    * **Attention heatmaps** — token-to-token attention weights at a
      chosen ``(layer, head)`` pair. Useful for circuit tracing — see
      Anthropic's induction-head work for worked examples.
    * **Logit lens** — projects each layer's post-residual stream
      through the unembedding and records the top-``k`` next-token
      predictions per layer. Reveals how the model's prediction
      distribution evolves with depth.
    * **Linear probes** — trains a logistic-regression probe on the
      last-token residual stream at a chosen layer, given a labelled
      prompt batch. Cross-validated accuracy reports how linearly
      separable a concept is at that depth.
    * **SAE features (optional)** — loads a pre-trained sparse
      autoencoder (Gemma Scope, TransformerLens-compatible releases)
      and returns the top-``k`` active features. Gated by
      ``pip install kailash-kaizen[interpretability]`` because
      ``sae-lens`` is a heavy optional dep.

Memory discipline:

    Cross-layer data (logit-lens top-k rows, probe activations) is
    stored through bounded ``deque`` buffers so long sessions on
    large models don't exhaust VRAM or host memory. Per
    ``rules/patterns.md`` cleanup discipline, ``close()`` and
    ``__exit__`` release the model + clear the CUDA / MPS cache.

Open-weight only:

    The adapter refuses to load API-only models (``gpt-*``, ``o1-*``,
    ``claude-*``, ``gemini-*``, ``deepseek-*``) and returns
    ``{"mode": "not_applicable"}`` from every interpretability method
    instead. This is honest failure per ``rules/zero-tolerance.md``
    Rule 2 — there is no meaningful attention heatmap to produce when
    the weights live behind a black-box API.

Security posture:

    * Default ``local_files_only=True`` — no silent multi-GB downloads
      during a diagnostic call. Opt in via ``allow_download=True`` if
      you want to pull fresh weights. HF auth token is read from
      ``HF_TOKEN`` / ``HUGGINGFACE_TOKEN`` (not hardcoded).
    * No LLM API calls — every operation runs on local tensors.
    * Model inputs are user-supplied text; the tokenizer handles
      bounds checking. No ``eval`` / ``exec`` on any path.

All DataFrames returned by ``*_df()`` accessors are polars. All plots
return :class:`plotly.graph_objects.Figure`. ``transformers`` is an
optional extra — the adapter raises a loud, actionable
``ImportError`` naming the ``[interpretability]`` extra if the library
is absent when a model-loading method is invoked.
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import polars as pl

logger = logging.getLogger(__name__)

__all__ = [
    "InterpretabilityDiagnostics",
]


# ---------------------------------------------------------------------------
# Model-family classification (open-weight vs API-only)
# ---------------------------------------------------------------------------
#
# The prefix list here is NOT an agent decision path — it is a static
# safety check on a configuration string to refuse loading weights we
# know the adapter cannot introspect (the API provider serves tokens,
# not hidden states). See rules/agent-reasoning.md §"Permitted
# Deterministic Logic" item 4 ("Safety guards — Blocking dangerous
# operations").
_API_ONLY_PREFIXES: tuple[str, ...] = (
    "gpt-",
    "o1-",
    "o3-",
    "o4-",
    "claude-",
    "gemini-",
    "deepseek-",
)


DEFAULT_MODEL = "google/gemma-2-2b"


# ---------------------------------------------------------------------------
# Optional-extras guards
# ---------------------------------------------------------------------------


def _require_transformers() -> tuple[Any, Any]:
    """Import ``(transformers.AutoModelForCausalLM, AutoTokenizer)`` loudly.

    Per ``rules/dependencies.md`` "Optional Extras with Loud Failure",
    we raise an ``ImportError`` naming the extra instead of silently
    degrading to ``None``. Construction of ``InterpretabilityDiagnostics``
    does NOT require transformers — only methods that load the model do.
    """
    try:
        from transformers import (  # noqa: PLC0415
            AutoModelForCausalLM,
            AutoTokenizer,
        )
    except ImportError as exc:
        raise ImportError(
            "InterpretabilityDiagnostics requires transformers. "
            "Install the interpretability extras: "
            "pip install kailash-kaizen[interpretability]"
        ) from exc
    return AutoModelForCausalLM, AutoTokenizer


def _require_torch() -> Any:
    """Import ``torch`` loudly. Same contract as ``_require_transformers``."""
    try:
        import torch  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "InterpretabilityDiagnostics requires PyTorch. "
            "Install the interpretability extras: "
            "pip install kailash-kaizen[interpretability]"
        ) from exc
    return torch


def _require_sae_lens() -> Any:
    """Import ``sae_lens.SAE`` loudly for the SAE features method.

    ``sae-lens`` is the heavier of the two optional deps and is only
    needed for :meth:`InterpretabilityDiagnostics.sae_features`. Users
    who only need attention / logit-lens / probes do not pay the
    ``sae-lens`` install cost.
    """
    try:
        from sae_lens import SAE  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "sae_features() requires sae-lens. "
            "Install the interpretability extras: "
            "pip install kailash-kaizen[interpretability]"
        ) from exc
    return SAE


def _require_plotly() -> Any:
    """Import ``plotly.graph_objects`` loudly.

    Plotting methods route through this helper so a missing install
    surfaces the extra name instead of a bare ``ModuleNotFoundError``.
    """
    try:
        import plotly.graph_objects as go  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "Plotting methods require plotly. Install the "
            "interpretability extras: pip install kailash-kaizen[interpretability]"
        ) from exc
    return go


def _require_matplotlib() -> Any:
    """Import ``matplotlib.pyplot`` loudly for non-plotly plot paths.

    Some interpretability plots (heatmaps with dense labels) render
    better in matplotlib. Treated as optional — callers who never
    invoke a matplotlib-backed plot do not need it.
    """
    try:
        import matplotlib.pyplot as plt  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "matplotlib-backed plots require matplotlib. Install the "
            "interpretability extras: pip install kailash-kaizen[interpretability]"
        ) from exc
    return plt


def _require_sklearn() -> tuple[Any, Any]:
    """Import ``(LogisticRegression, cross_val_score)`` loudly for probes."""
    try:
        from sklearn.linear_model import LogisticRegression  # noqa: PLC0415
        from sklearn.model_selection import cross_val_score  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "Linear probes require scikit-learn. Install the "
            "interpretability extras: pip install kailash-kaizen[interpretability]"
        ) from exc
    return LogisticRegression, cross_val_score


# ---------------------------------------------------------------------------
# Device resolution
# ---------------------------------------------------------------------------


def _resolve_device(preferred: Optional[str] = None) -> str:
    """Pick a torch device string.

    ``preferred`` wins when supplied; otherwise CUDA > MPS > CPU. Any
    probe exception falls back to CPU rather than crashing session
    construction — a partially-broken GPU driver MUST NOT block the
    CPU diagnostic path.
    """
    if preferred:
        return preferred
    try:
        torch = _require_torch()
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:  # noqa: BLE001 — defensive fallback
        logger.debug(
            "interpretability.device_resolver_failed",
            exc_info=True,
        )
    return "cpu"


# ---------------------------------------------------------------------------
# Attention payload (kept small so deque-bounded memory is meaningful)
# ---------------------------------------------------------------------------


@dataclass
class _AttentionRecord:
    run_id: str
    layer: int
    head: int
    tokens: list[str] = field(default_factory=list)
    # matrix stored as a python-list-of-lists so it serialises cleanly
    # into report() without requiring numpy to be loaded just to inspect.
    matrix: list[list[float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# InterpretabilityDiagnostics — concrete Diagnostic adapter
# ---------------------------------------------------------------------------


class InterpretabilityDiagnostics:
    """Open-weight LLM interpretability adapter (Diagnostic Protocol).

    Collects attention heatmaps, logit-lens trajectories, linear-probe
    accuracies, and optional SAE feature activations. Exposes polars
    DataFrame accessors, plotly / matplotlib plots (gated by the
    ``[interpretability]`` extra), and an automated ``report()`` that
    summarises every captured finding.

    The adapter satisfies :class:`kailash.diagnostics.protocols.
    Diagnostic` (``run_id`` + ``__enter__`` + ``__exit__`` +
    ``report()``). ``isinstance(diag, Diagnostic)`` returns ``True``
    at runtime because the Protocol is ``@runtime_checkable``.

    Args:
        model_name: HuggingFace model identifier. Defaults to
            ``google/gemma-2-2b``. MUST be an open-weight model —
            API-only prefixes (``gpt-*``, ``claude-*``, ``gemini-*``,
            ...) are refused at every method call with a typed
            ``not_applicable`` reading.
        device: Torch device string (``"cuda"`` / ``"mps"`` / ``"cpu"``).
            Auto-detected when ``None``.
        dtype: Torch dtype for weights — ``"float16"`` / ``"bfloat16"``
            / ``"float32"``. ``"float16"`` halves VRAM. Defaults to
            ``"float16"``.
        window: Bounded-memory cap for the logit-lens cross-layer row
            buffer. MUST be ``>= 1``. Defaults to ``4096`` — enough
            for a 32-layer model at ``top_k=10`` without VRAM risk.
        run_id: Optional correlation identifier for this diagnostic
            session. When omitted, a UUID4 hex is generated.
        local_files_only: When ``True`` (default), ``from_pretrained``
            refuses to download and uses only the HuggingFace cache.
            Operators who want fresh weights pass ``False`` explicitly
            via ``allow_download=True`` so a diagnostic call NEVER
            silently pulls multi-GB over the network.
        allow_download: Alias for ``not local_files_only`` expressed
            positively so the opt-in reads naturally at the call site.
            When ``True``, overrides ``local_files_only`` to ``False``.

    Raises:
        TypeError: If ``model_name`` is not a string.
        ValueError: If ``window < 1`` or ``run_id`` is an empty string.

    Example:
        >>> with InterpretabilityDiagnostics(model_name="google/gemma-2-2b") as diag:
        ...     fig = diag.attention_heatmap("The cat sat on the mat",
        ...                                  layer=0, head=0)
        ...     df = diag.logit_lens("The capital of France is", top_k=5)
        ...     findings = diag.report()
    """

    # Class-level constants
    DEFAULT_MODEL: str = DEFAULT_MODEL

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_MODEL,
        device: Optional[str] = None,
        dtype: str = "float16",
        window: int = 4096,
        run_id: Optional[str] = None,
        local_files_only: bool = True,
        allow_download: bool = False,
    ) -> None:
        if not isinstance(model_name, str):
            raise TypeError(
                "InterpretabilityDiagnostics requires a string model_name; "
                f"got {type(model_name).__name__}"
            )
        if not model_name:
            raise ValueError("model_name must be a non-empty string")
        if window < 1:
            raise ValueError("window must be >= 1")
        if run_id is not None and not run_id:
            raise ValueError("run_id must be a non-empty string when provided")
        if dtype not in ("float16", "bfloat16", "float32"):
            raise ValueError(
                "dtype must be one of 'float16', 'bfloat16', 'float32'; "
                f"got {dtype!r}"
            )

        self.model_name: str = model_name
        self.device: str = _resolve_device(device)
        self.dtype: str = dtype
        self.window: int = window
        # Satisfies kailash.diagnostics.protocols.Diagnostic.run_id.
        self.run_id: str = run_id if run_id is not None else uuid.uuid4().hex
        # Opt-in download: allow_download=True overrides local_files_only.
        self._local_files_only: bool = bool(local_files_only) and not allow_download

        # Lazy-loaded model handles.
        self._model: Any = None
        self._tokenizer: Any = None

        # Bounded-memory time-series storage per analysis. Lists of
        # dicts converted to polars on demand.
        self._attention_log: deque[_AttentionRecord] = deque(maxlen=self.window)
        self._logit_log: deque[dict[str, Any]] = deque(maxlen=self.window)
        self._probe_log: deque[dict[str, Any]] = deque(maxlen=self.window)
        self._sae_log: deque[dict[str, Any]] = deque(maxlen=self.window)

        logger.info(
            "interp_diagnostics.init",
            extra={
                # Domain-prefixed field names per rules/observability.md
                # MUST Rule 9 (LogRecord reserves `module`, etc.).
                "interp_model_name": model_name,
                "interp_device": self.device,
                "interp_dtype": dtype,
                "interp_window": window,
                "interp_run_id": self.run_id,
                "interp_local_files_only": self._local_files_only,
            },
        )

    # ── Context-manager support ────────────────────────────────────────────

    def __enter__(self) -> "InterpretabilityDiagnostics":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> Optional[bool]:
        self.close()
        return None

    def close(self) -> None:
        """Release the model + tokenizer and clear CUDA / MPS caches.

        Safe to call multiple times. Invoked automatically on context
        exit.
        """
        self._model = None
        self._tokenizer = None
        try:
            torch = _require_torch()
            if hasattr(torch, "cuda") and torch.cuda.is_available():
                torch.cuda.empty_cache()
            if (
                hasattr(torch.backends, "mps")
                and torch.backends.mps.is_available()
                and hasattr(torch.mps, "empty_cache")
            ):
                torch.mps.empty_cache()
        except Exception:  # noqa: BLE001 — cleanup paths may legitimately fail
            # Cleanup failures are benign (torch may already be torn
            # down during interpreter shutdown). Zero-tolerance Rule 3
            # cleanup-path carve-out.
            logger.debug(
                "interp.close.cache_clear_failed",
                exc_info=True,
            )

    # ── Applicability check ────────────────────────────────────────────────

    def _is_api_only(self, model: Optional[str] = None) -> bool:
        """Return True when the model name is an API-only prefix.

        Static safety guard on a configuration string — NOT an agent
        decision path. See module docstring § "Open-weight only".
        """
        m = (model or self.model_name).lower()
        return any(m.startswith(p) for p in _API_ONLY_PREFIXES)

    def _not_applicable(
        self, method: str, model: Optional[str] = None
    ) -> dict[str, Any]:
        """Return the canonical ``not_applicable`` reading.

        Emitted whenever a method that needs hidden states is called
        against an API-only model. Logged at INFO so operators can
        grep for ``mode=not_applicable`` post-incident.
        """
        payload = {
            "mode": "not_applicable",
            "method": method,
            "model": model or self.model_name,
            "reason": (
                "interpretability diagnostics require open-weight models "
                "(Llama, Gemma, Phi, Mistral). API-only models (GPT, "
                "Claude, Gemini, ...) expose tokens but not hidden states."
            ),
        }
        logger.info(
            "interp.not_applicable",
            extra={
                "interp_method": method,
                "interp_model_name": model or self.model_name,
                "interp_mode": "not_applicable",
                "interp_run_id": self.run_id,
            },
        )
        return payload

    # ── Model loading (lazy) ───────────────────────────────────────────────

    def _load_model(self) -> tuple[Any, Any]:
        """Lazy-load the HuggingFace model + tokenizer on first use.

        Subsequent calls return the cached pair. Raises
        :class:`ImportError` if transformers is absent. Raises
        :class:`RuntimeError` if the configured model is API-only.
        """
        if self._model is not None and self._tokenizer is not None:
            return self._model, self._tokenizer

        if self._is_api_only():
            raise RuntimeError(
                f"{self.model_name} is API-only; cannot load weights. Use an "
                "open-weight model such as google/gemma-2-2b, "
                "meta-llama/Llama-3.2-1B, or microsoft/Phi-3-mini-4k-instruct."
            )

        AutoModelForCausalLM, AutoTokenizer = _require_transformers()
        torch = _require_torch()

        # Resolve HF auth token from environment (no hardcoding per
        # rules/security.md). Gated Llama / Gemma families require it.
        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")

        torch_dtype = {
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
            "float32": torch.float32,
        }[self.dtype]

        logger.info(
            "interp.load_model.start",
            extra={
                "interp_model_name": self.model_name,
                "interp_device": self.device,
                "interp_dtype": self.dtype,
                "interp_local_files_only": self._local_files_only,
                "interp_run_id": self.run_id,
            },
        )

        tokenizer_kwargs: dict[str, Any] = {
            "local_files_only": self._local_files_only,
        }
        model_kwargs: dict[str, Any] = {
            "local_files_only": self._local_files_only,
            "torch_dtype": torch_dtype,
            # output_hidden_states + output_attentions enable every
            # analysis path — logit lens needs hidden states, attention
            # heatmap needs attention matrices. The cost is memory
            # proportional to n_layers, bounded by the ``window`` cap
            # on the deque that stores them.
            "output_hidden_states": True,
            "output_attentions": True,
        }
        if token:
            tokenizer_kwargs["token"] = token
            model_kwargs["token"] = token

        tokenizer = AutoTokenizer.from_pretrained(self.model_name, **tokenizer_kwargs)
        model = AutoModelForCausalLM.from_pretrained(self.model_name, **model_kwargs)
        model = model.to(self.device)
        model.eval()

        self._tokenizer = tokenizer
        self._model = model

        n_layers = getattr(getattr(model, "config", None), "num_hidden_layers", None)
        logger.info(
            "interp.load_model.ok",
            extra={
                "interp_model_name": self.model_name,
                "interp_n_layers": n_layers,
                "interp_run_id": self.run_id,
            },
        )
        return model, tokenizer

    # ── Attention heatmap ──────────────────────────────────────────────────

    def attention_heatmap(
        self,
        prompt: str,
        *,
        layer: int = 0,
        head: int = 0,
        run_id: Optional[str] = None,
    ) -> Any:
        """Record + return token-to-token attention at ``(layer, head)``.

        The matrix is stored bounded-memory via ``deque(maxlen=window)``
        and ALSO returned as a plotly Figure when ``[interpretability]``
        is installed. For API-only models returns a labelled empty
        figure (via ``plot_attention_heatmap``) and records the
        ``not_applicable`` reading.

        Args:
            prompt: Input text. Tokenizer handles length truncation.
            layer: 0-indexed transformer block. Out-of-range triggers
                ``IndexError`` from the underlying tensor slice.
            head: 0-indexed attention head.
            run_id: Optional override of the per-reading correlation
                ID (defaults to ``self.run_id`` with a short suffix).

        Returns:
            A plotly Figure. When ``[interpretability]`` is not
            installed, raises :class:`ImportError` from the plot step.
        """
        if self._is_api_only():
            self._not_applicable("attention_heatmap")
            return self._empty_attention_figure(
                f"Attention Heatmap - layer {layer}, head {head}",
                note="not applicable for API-only models",
            )

        record_run_id = run_id or f"{self.run_id}-attn-{uuid.uuid4().hex[:12]}"
        torch = _require_torch()
        model, tokenizer = self._load_model()

        inputs = tokenizer(prompt, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = model(**inputs, output_attentions=True)

        # transformers stores attentions as tuple of
        # [batch, n_heads, q_len, k_len] tensors indexed by layer.
        attentions = outputs.attentions  # tuple len = n_layers
        if layer < 0 or layer >= len(attentions):
            raise IndexError(
                f"layer {layer} out of range; model has {len(attentions)} layers"
            )
        head_matrix = attentions[layer][0, head]
        matrix = head_matrix.detach().to("cpu").float().numpy().tolist()

        input_ids = inputs["input_ids"][0].tolist()
        tokens = [tokenizer.decode([tid]) for tid in input_ids]
        labels = [t.replace("\n", "\\n") or "∅" for t in tokens]

        record = _AttentionRecord(
            run_id=record_run_id,
            layer=layer,
            head=head,
            tokens=labels,
            matrix=matrix,
        )
        self._attention_log.append(record)
        logger.info(
            "interp.attention_heatmap.ok",
            extra={
                "interp_run_id": record_run_id,
                "interp_layer": layer,
                "interp_head": head,
                "interp_n_tokens": len(labels),
                "interp_mode": "real",
            },
        )
        return self.plot_attention_heatmap(record)

    def plot_attention_heatmap(self, record: _AttentionRecord) -> Any:
        """Render a recorded attention matrix as a plotly heatmap."""
        go = _require_plotly()
        fig = go.Figure(
            go.Heatmap(
                z=record.matrix,
                x=record.tokens,
                y=record.tokens,
                colorscale="Viridis",
                colorbar=dict(title="attention"),
            )
        )
        fig.update_layout(
            title=(
                f"Attention - {self.model_name} "
                f"layer {record.layer} head {record.head}"
            ),
            xaxis_title="key token",
            yaxis_title="query token",
            template="plotly_white",
            height=600,
        )
        return fig

    def _empty_attention_figure(self, title: str, *, note: str) -> Any:
        """Labelled empty plotly figure for the ``not_applicable`` path."""
        go = _require_plotly()
        fig = go.Figure()
        fig.update_layout(
            title=f"{title} - {note}",
            template="plotly_white",
            height=400,
        )
        return fig

    # ── Logit lens ─────────────────────────────────────────────────────────

    def logit_lens(
        self,
        prompt: str,
        *,
        top_k: int = 5,
        run_id: Optional[str] = None,
    ) -> pl.DataFrame:
        """Early-exit top-``k`` predictions per transformer layer.

        Projects each layer's post-residual stream through the shared
        unembedding matrix (``lm_head``) and records the top-``k``
        next-token predictions + probabilities. Returns a polars
        DataFrame with columns ``layer``, ``rank``, ``token``, ``prob``,
        ``mode``.

        On API-only models returns an empty DataFrame tagged
        ``mode="not_applicable"`` instead of raising.
        """
        if self._is_api_only():
            self._logit_log.append(self._not_applicable("logit_lens"))
            return pl.DataFrame(
                schema={
                    "layer": pl.Int64,
                    "rank": pl.Int64,
                    "token": pl.Utf8,
                    "prob": pl.Float64,
                    "mode": pl.Utf8,
                }
            )

        record_run_id = run_id or f"{self.run_id}-ll-{uuid.uuid4().hex[:12]}"
        torch = _require_torch()
        model, tokenizer = self._load_model()

        inputs = tokenizer(prompt, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = model(**inputs, output_hidden_states=True)

        hidden_states = outputs.hidden_states  # tuple len = n_layers + 1
        n_layers = len(hidden_states) - 1  # drop the embedding layer

        # Pull the shared unembedding. Gemma / Llama call it lm_head,
        # some configs tie weights with the input embedding.
        lm_head = getattr(model, "lm_head", None)
        if lm_head is None:
            # Fallback: some models expose get_output_embeddings().
            lm_head = model.get_output_embeddings()

        rows: list[dict[str, Any]] = []
        # Start at layer 1 (post-first-block residual) — layer 0 is the
        # raw token embedding and yields trivial predictions.
        for layer_idx in range(1, n_layers + 1):
            resid = hidden_states[layer_idx][0, -1]  # last token
            logits = lm_head(resid)
            probs = torch.softmax(logits, dim=-1)
            top = torch.topk(probs, k=min(top_k, probs.numel()))
            for rank, (p, tok_id) in enumerate(
                zip(top.values.tolist(), top.indices.tolist())
            ):
                token_str = tokenizer.decode([int(tok_id)]).replace("\n", "\\n")
                rows.append(
                    {
                        "layer": layer_idx,
                        "rank": rank,
                        "token": token_str,
                        "prob": float(p),
                        "mode": "real",
                    }
                )

        df = (
            pl.DataFrame(rows)
            if rows
            else pl.DataFrame(
                schema={
                    "layer": pl.Int64,
                    "rank": pl.Int64,
                    "token": pl.Utf8,
                    "prob": pl.Float64,
                    "mode": pl.Utf8,
                }
            )
        )
        self._logit_log.append(
            {
                "run_id": record_run_id,
                "n_layers": n_layers,
                "top_k": top_k,
                "mode": "real",
            }
        )
        logger.info(
            "interp.logit_lens.ok",
            extra={
                "interp_run_id": record_run_id,
                "interp_n_layers": n_layers,
                "interp_top_k": top_k,
                "interp_mode": "real",
            },
        )
        return df

    def plot_logit_lens(self, df: pl.DataFrame) -> Any:
        """Bar chart of top-1 logit-lens probability per layer."""
        go = _require_plotly()
        if df.height == 0:
            return self._empty_attention_figure(
                "Logit Lens", note="no data or not applicable"
            )
        top1 = df.filter(pl.col("rank") == 0).sort("layer")
        fig = go.Figure(
            go.Bar(
                x=top1["layer"].to_list(),
                y=top1["prob"].to_list(),
                text=top1["token"].to_list(),
                marker_color="steelblue",
            )
        )
        fig.update_layout(
            title=f"Logit Lens - top-1 probability per layer ({self.model_name})",
            xaxis_title="layer",
            yaxis_title="probability",
            template="plotly_white",
        )
        return fig

    # ── Linear probe ───────────────────────────────────────────────────────

    def probe(
        self,
        prompts: Sequence[str],
        labels: Sequence[int],
        *,
        layer: int,
        run_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Train a linear probe on last-token hidden state at ``layer``.

        For each prompt, runs a forward pass and pulls the last-token
        residual stream at ``layer``. Fits a logistic regression via
        scikit-learn with cross-validated accuracy reported in the
        return dict.

        Args:
            prompts: Labelled input texts (len = ``N``).
            labels: Integer class labels (len = ``N``, ``>= 2`` distinct).
            layer: 0-indexed transformer block to probe.
            run_id: Optional correlation ID override.

        Returns:
            ``{"run_id", "layer", "n_prompts", "n_classes",
             "cv_accuracy", "mode"}``. On API-only models returns the
            ``not_applicable`` payload.

        Raises:
            ValueError: If ``len(prompts) != len(labels)`` or fewer
                than 2 distinct labels are supplied.
        """
        if self._is_api_only():
            return self._not_applicable("probe")

        if len(prompts) != len(labels):
            raise ValueError("prompts and labels must be same length")
        if len(set(labels)) < 2:
            raise ValueError("probe needs at least 2 distinct labels")

        record_run_id = run_id or f"{self.run_id}-probe-{uuid.uuid4().hex[:12]}"
        torch = _require_torch()
        model, tokenizer = self._load_model()
        LogisticRegression, cross_val_score = _require_sklearn()

        # Limited import here — numpy is a transitive dep of polars,
        # so guaranteed present on the base install.
        import numpy as np  # noqa: PLC0415

        feature_rows: list[Any] = []
        for p in prompts:
            inputs = tokenizer(p, return_tensors="pt").to(self.device)
            with torch.no_grad():
                outputs = model(**inputs, output_hidden_states=True)
            if layer < 0 or layer >= len(outputs.hidden_states):
                raise IndexError(
                    f"layer {layer} out of range; model has "
                    f"{len(outputs.hidden_states)} hidden-state slots"
                )
            last = outputs.hidden_states[layer][0, -1].detach().to("cpu").float()
            feature_rows.append(last.numpy())

        X = np.stack(feature_rows)
        y = np.asarray(labels)
        clf = LogisticRegression(max_iter=500)
        cv = min(5, len(set(labels)))
        scores = cross_val_score(clf, X, y, cv=cv)
        cv_accuracy = float(scores.mean())

        row = {
            "run_id": record_run_id,
            "layer": layer,
            "n_prompts": len(prompts),
            "n_classes": len(set(labels)),
            "cv_accuracy": cv_accuracy,
            "mode": "real",
        }
        self._probe_log.append(row)
        logger.info(
            "interp.probe.ok",
            extra={
                "interp_run_id": record_run_id,
                "interp_layer": layer,
                "interp_n_prompts": len(prompts),
                "interp_n_classes": len(set(labels)),
                "interp_cv_accuracy": cv_accuracy,
                "interp_mode": "real",
            },
        )
        return row

    # ── SAE features (optional sae-lens) ───────────────────────────────────

    def sae_features(
        self,
        prompt: str,
        *,
        layer: int,
        top_k: int = 10,
        release: Optional[str] = None,
        sae_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> pl.DataFrame:
        """Load a pre-trained SAE and return the top-``k`` active features.

        ``release`` is the :mod:`sae_lens` release identifier. When
        ``None``, defaults based on ``self.model_name``. Students do
        NOT train SAEs here — this is a read-only inspection.

        Returns a polars DataFrame with ``feature_index``,
        ``activation``, and a ``mode`` column.
        """
        if self._is_api_only():
            self._sae_log.append(self._not_applicable("sae_features"))
            return pl.DataFrame(
                schema={
                    "feature_index": pl.Int64,
                    "activation": pl.Float64,
                    "mode": pl.Utf8,
                }
            )

        SAE = _require_sae_lens()
        torch = _require_torch()
        model, tokenizer = self._load_model()

        record_run_id = run_id or f"{self.run_id}-sae-{uuid.uuid4().hex[:12]}"
        release = release or _default_sae_release(self.model_name)
        sae_id = sae_id or f"layer_{layer}/width_16k/canonical"

        logger.info(
            "interp.sae_load.start",
            extra={
                "interp_release": release,
                "interp_sae_id": sae_id,
                "interp_layer": layer,
                "interp_run_id": record_run_id,
            },
        )
        sae_tuple = SAE.from_pretrained(release=release, sae_id=sae_id)
        # sae_lens versions differ on return shape — handle both.
        sae_obj = sae_tuple[0] if isinstance(sae_tuple, tuple) else sae_tuple
        sae_obj = sae_obj.to(self.device)

        inputs = tokenizer(prompt, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = model(**inputs, output_hidden_states=True)
            if layer < 0 or layer >= len(outputs.hidden_states):
                raise IndexError(
                    f"layer {layer} out of range; model has "
                    f"{len(outputs.hidden_states)} hidden-state slots"
                )
            resid = outputs.hidden_states[layer][0, -1]
            acts = sae_obj.encode(resid)
        k = min(top_k, int(acts.numel()))
        top = torch.topk(acts, k=k)
        rows = [
            {
                "feature_index": int(idx),
                "activation": float(val),
                "mode": "real",
            }
            for idx, val in zip(top.indices.tolist(), top.values.tolist())
        ]
        df = (
            pl.DataFrame(rows)
            if rows
            else pl.DataFrame(
                schema={
                    "feature_index": pl.Int64,
                    "activation": pl.Float64,
                    "mode": pl.Utf8,
                }
            )
        )
        self._sae_log.append(
            {
                "run_id": record_run_id,
                "layer": layer,
                "release": release,
                "sae_id": sae_id,
                "top_k": top_k,
                "mode": "real",
            }
        )
        logger.info(
            "interp.sae_features.ok",
            extra={
                "interp_run_id": record_run_id,
                "interp_layer": layer,
                "interp_top_k": top_k,
                "interp_mode": "real",
            },
        )
        return df

    # ── Report ─────────────────────────────────────────────────────────────

    def report(self) -> dict[str, Any]:
        """Return a structured summary of the captured session.

        The return shape satisfies :meth:`kailash.diagnostics.protocols.
        Diagnostic.report`:

          * ``run_id`` — the session identifier (matches ``self.run_id``).
          * ``model_name`` — the configured HuggingFace identifier.
          * ``mode`` — ``"not_applicable"`` for API-only models, else
            ``"real"``.
          * ``attention_heatmaps`` — count recorded.
          * ``logit_lens_sweeps`` — count recorded.
          * ``linear_probes`` — ``{"count", "last_accuracy",
            "last_layer"}`` or ``{"count": 0}`` when empty.
          * ``sae_feature_reads`` — count recorded.
          * ``messages`` — list of human-readable summary lines.

        Always callable; never raises on empty state.
        """
        if self._is_api_only():
            return {
                "run_id": self.run_id,
                "model_name": self.model_name,
                "mode": "not_applicable",
                "attention_heatmaps": 0,
                "logit_lens_sweeps": 0,
                "linear_probes": {"count": 0},
                "sae_feature_reads": 0,
                "messages": [
                    (
                        f"{self.model_name} is API-only; attention, logit "
                        "lens, linear probe, and SAE features are not "
                        "applicable. Load an open-weight model "
                        "(e.g. google/gemma-2-2b)."
                    )
                ],
            }

        messages: list[str] = []
        if self._attention_log:
            messages.append(f"attention: {len(self._attention_log)} heatmaps recorded")
        if self._logit_log:
            messages.append(f"logit_lens: {len(self._logit_log)} sweeps recorded")
        probe_summary: dict[str, Any] = {"count": len(self._probe_log)}
        if self._probe_log:
            last = self._probe_log[-1]
            probe_summary["last_accuracy"] = last["cv_accuracy"]
            probe_summary["last_layer"] = last["layer"]
            messages.append(
                f"probe: last CV accuracy={last['cv_accuracy']:.3f} "
                f"on layer {last['layer']}"
            )
        if self._sae_log:
            messages.append(f"sae: {len(self._sae_log)} feature reads recorded")
        if not messages:
            messages.append("interp-lens: no readings recorded yet.")
        return {
            "run_id": self.run_id,
            "model_name": self.model_name,
            "mode": "real",
            "attention_heatmaps": len(self._attention_log),
            "logit_lens_sweeps": len(self._logit_log),
            "linear_probes": probe_summary,
            "sae_feature_reads": len(self._sae_log),
            "messages": messages,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _default_sae_release(model_name: str) -> str:
    """Resolve a reasonable :mod:`sae_lens` release id for ``model_name``.

    Currently returns a Gemma Scope release for Gemma families and
    falls back to the 2B release otherwise — Gemma Scope has the best
    open-weight SAE coverage as of 2026.
    """
    name = model_name.lower()
    if "gemma-2-2b" in name:
        return "gemma-scope-2b-pt-res"
    if "gemma-2-9b" in name:
        return "gemma-scope-9b-pt-res"
    return "gemma-scope-2b-pt-res"


def _fingerprint_prompt(prompt: str) -> str:
    """Short stable hash of a prompt for correlation without leaking content.

    Used in future expansions where operators want to correlate
    attention readings with tracing spans but cannot emit the raw
    prompt text into structured logs (rules/observability.md §4).
    Eight hex chars matches the classification-hash contract in
    ``rules/event-payload-classification.md``.
    """
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8]
