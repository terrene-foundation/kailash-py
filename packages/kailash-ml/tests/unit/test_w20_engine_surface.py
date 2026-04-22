# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W20 — MLEngine fit/predict/finalize/evaluate invariant tests.

Covers the 10 invariants from the master wave plan §W20 against
``specs/ml-engines-v2.md §2.1 MUST 8-9 + §2.2 + §2.3`` at the engine
dispatch layer (Tier 1). The T2 integration tests (DDP rank-0
callback firing + lr_find round-trip) live in W20.b — they require
the ``[dl]`` extra (torch + lightning) and CPU-DDP determinism.

Invariants:

1. ``fit(family=, trainable=)`` mutually exclusive → ``ConflictingArgumentsError``
2. ``fit()`` called without setup() or direct data → ``EngineNotSetUpError``
3. Raw-loop trainable (``_raw_loop=True``) → ``UnsupportedTrainerError``
4. ``strategy="ddp" | "fsdp" | "deepspeed"`` plumbs onto ``TrainingContext.strategy``
5. ``enable_checkpointing=True`` is the default; flag plumbs onto context
6. ``auto_find_lr=True`` plumbs onto ``TrainingContext.auto_find_lr``
7. ``predict(channel=...)`` enforces the "direct"|"rest"|"mcp" enum
8. ``finalize(full_fit=True)`` retrains by dispatching through ``self.fit()``
9. ``evaluate(mode=...)`` enforces the "holdout"|"shadow"|"live" enum
10. ``SchemaDriftError`` on fit-time schema != setup-time schema
"""
from __future__ import annotations

from typing import Any

import polars as pl
import pytest

from kailash_ml import MLEngine
from kailash_ml.engine import (
    ConflictingArgumentsError,
    EngineNotSetUpError,
    SchemaDriftError,
    UnsupportedTrainerError,
)
from kailash_ml.trainable import TrainingContext


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _frame(n: int = 20) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "x1": list(range(n)),
            "x2": [i * 2 for i in range(n)],
            "y": [i % 2 for i in range(n)],
        }
    )


class _CaptureTrainable:
    """Duck-typed Trainable that captures the TrainingContext.

    fit() returns a minimal TrainingResult-shaped object so the engine's
    post-dispatch tenant_id normalization (§4.2 MUST 3) works without
    requiring the heavy family adapters.
    """

    family_name = "capture-fake"

    def __init__(self, *, raw_loop: bool = False) -> None:
        if raw_loop:
            # Apply marker only when requested — absence is the default
            # (non-raw-loop). Attached as instance attr so engine's
            # getattr(trainable, "_raw_loop", False) resolves correctly.
            self._raw_loop = True
        self.captured_ctx: TrainingContext | None = None
        self.captured_hp: dict[str, Any] | None = None

    def fit(self, data: Any, *, hyperparameters: Any, context: TrainingContext) -> Any:
        self.captured_ctx = context
        self.captured_hp = dict(hyperparameters)
        from kailash_ml._result import TrainingResult

        return TrainingResult(
            family=self.family_name,
            metrics={"accuracy": 0.5},
            model_uri="models://w20-capture/v1",
            device_used="cpu",
            accelerator="cpu",
            precision="32-true",
            elapsed_seconds=0.0,
            tracker_run_id=None,
            tenant_id=None,
            artifact_uris={},
            lightning_trainer_config={},
            hyperparameters=dict(hyperparameters),
            feature_importance=None,
            device=None,
        )


# ----------------------------------------------------------------------
# Invariant 1: family + trainable mutually exclusive
# ----------------------------------------------------------------------


class TestInvariant1ConflictingArguments:
    @pytest.mark.asyncio
    async def test_family_and_trainable_both_raises(self) -> None:
        engine = MLEngine()
        df = _frame()
        with pytest.raises(ConflictingArgumentsError):
            await engine.fit(
                data=df,
                target="y",
                family="sklearn",
                trainable=_CaptureTrainable(),
            )


# ----------------------------------------------------------------------
# Invariant 2: EngineNotSetUpError when no setup + no direct data
# ----------------------------------------------------------------------


class TestInvariant2EngineNotSetUp:
    @pytest.mark.asyncio
    async def test_no_setup_no_data_raises(self) -> None:
        engine = MLEngine()
        with pytest.raises(EngineNotSetUpError):
            await engine.fit(data=None, target="y")


# ----------------------------------------------------------------------
# Invariant 3: raw-loop detection → UnsupportedTrainerError
# ----------------------------------------------------------------------


class TestInvariant3RawLoopRejected:
    @pytest.mark.asyncio
    async def test_raw_loop_marker_raises(self) -> None:
        engine = MLEngine()
        df = _frame()
        raw = _CaptureTrainable(raw_loop=True)
        with pytest.raises(UnsupportedTrainerError) as exc_info:
            await engine.fit(data=df, target="y", trainable=raw)
        # Error carries the family name + reason (§2.3 signature)
        assert exc_info.value.family == "capture-fake"
        assert "raw" in exc_info.value.reason.lower()

    @pytest.mark.asyncio
    async def test_non_raw_loop_trainable_not_rejected(self) -> None:
        """Sanity: trainables without the marker dispatch normally."""
        engine = MLEngine()
        df = _frame()
        ok = _CaptureTrainable(raw_loop=False)
        # Must NOT raise UnsupportedTrainerError.
        result = await engine.fit(data=df, target="y", trainable=ok)
        assert ok.captured_ctx is not None
        assert result.family == "capture-fake"


# ----------------------------------------------------------------------
# Invariant 4: strategy="ddp"/"fsdp"/"deepspeed" plumbs onto context
# ----------------------------------------------------------------------


class TestInvariant4StrategyPassthrough:
    @pytest.mark.parametrize("strategy", ["ddp", "fsdp", "deepspeed"])
    @pytest.mark.asyncio
    async def test_string_strategy_plumbs(self, strategy: str) -> None:
        engine = MLEngine()
        df = _frame()
        t = _CaptureTrainable()
        await engine.fit(data=df, target="y", trainable=t, strategy=strategy)
        assert t.captured_ctx is not None
        assert t.captured_ctx.strategy == strategy

    @pytest.mark.asyncio
    async def test_default_strategy_is_none(self) -> None:
        """None preserves Lightning's single-device default (§3.2 MUST 6)."""
        engine = MLEngine()
        df = _frame()
        t = _CaptureTrainable()
        await engine.fit(data=df, target="y", trainable=t)
        assert t.captured_ctx is not None
        assert t.captured_ctx.strategy is None

    @pytest.mark.asyncio
    async def test_num_nodes_plumbs(self) -> None:
        engine = MLEngine()
        df = _frame()
        t = _CaptureTrainable()
        await engine.fit(data=df, target="y", trainable=t, num_nodes=4)
        assert t.captured_ctx is not None
        assert t.captured_ctx.num_nodes == 4


# ----------------------------------------------------------------------
# Invariant 5: enable_checkpointing default=True + plumb-through
# ----------------------------------------------------------------------


class TestInvariant5CheckpointingDefault:
    @pytest.mark.asyncio
    async def test_default_is_true(self) -> None:
        """Per §3.2 MUST 7 the default flipped to True at 1.0.0."""
        engine = MLEngine()
        df = _frame()
        t = _CaptureTrainable()
        await engine.fit(data=df, target="y", trainable=t)
        assert t.captured_ctx is not None
        assert t.captured_ctx.enable_checkpointing is True

    @pytest.mark.asyncio
    async def test_explicit_false_plumbs(self) -> None:
        engine = MLEngine()
        df = _frame()
        t = _CaptureTrainable()
        await engine.fit(data=df, target="y", trainable=t, enable_checkpointing=False)
        assert t.captured_ctx is not None
        assert t.captured_ctx.enable_checkpointing is False

    @pytest.mark.asyncio
    async def test_user_callbacks_plumb(self) -> None:
        """User-supplied callbacks flow through context (§2.2 signature)."""
        engine = MLEngine()
        df = _frame()
        t = _CaptureTrainable()
        sentinel_cb = object()
        await engine.fit(data=df, target="y", trainable=t, callbacks=[sentinel_cb])
        assert t.captured_ctx is not None
        assert t.captured_ctx.callbacks is not None
        assert sentinel_cb in t.captured_ctx.callbacks


# ----------------------------------------------------------------------
# Invariant 6: auto_find_lr flag plumbs
# ----------------------------------------------------------------------


class TestInvariant6AutoFindLrPassthrough:
    @pytest.mark.asyncio
    async def test_default_is_false(self) -> None:
        """Per §3.2 MUST 8 auto_find_lr is opt-in, default OFF."""
        engine = MLEngine()
        df = _frame()
        t = _CaptureTrainable()
        await engine.fit(data=df, target="y", trainable=t)
        assert t.captured_ctx is not None
        assert t.captured_ctx.auto_find_lr is False

    @pytest.mark.asyncio
    async def test_true_plumbs(self) -> None:
        engine = MLEngine()
        df = _frame()
        t = _CaptureTrainable()
        await engine.fit(data=df, target="y", trainable=t, auto_find_lr=True)
        assert t.captured_ctx is not None
        assert t.captured_ctx.auto_find_lr is True


# ----------------------------------------------------------------------
# Invariant 7: predict() channel enum
# ----------------------------------------------------------------------


class TestInvariant7PredictChannelEnum:
    @pytest.mark.asyncio
    async def test_invalid_channel_rejected(self) -> None:
        engine = MLEngine()
        with pytest.raises(ValueError, match="channel"):
            await engine.predict(
                model="models://nope/v1",
                features={"x1": 1, "x2": 2},
                channel="grpc",
            )

    @pytest.mark.asyncio
    async def test_accepted_values(self) -> None:
        """Sanity: the three accepted values pass validation (downstream may
        raise ModelNotFoundError, not ValueError-on-channel)."""
        engine = MLEngine()
        for ch in ("direct", "rest", "mcp"):
            with pytest.raises(Exception) as exc_info:
                await engine.predict(
                    model="models://nope/v1",
                    features={"x1": 1, "x2": 2},
                    channel=ch,
                )
            # The failure MUST NOT be the channel enum check — it's
            # downstream model resolution. A ValueError on channel would
            # mean our enum check rejected the value.
            assert not (
                isinstance(exc_info.value, ValueError)
                and "channel" in str(exc_info.value).lower()
            ), f"channel={ch!r} should be accepted; got {exc_info.value}"


# ----------------------------------------------------------------------
# Invariant 8: finalize(full_fit=True) dispatches through self.fit()
# ----------------------------------------------------------------------


class TestInvariant8FinalizeRefitsViaFit:
    @pytest.mark.asyncio
    async def test_full_fit_true_routes_through_fit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Per §2.2 finalize(full_fit=True) refits — MUST use self.fit()."""
        from kailash_ml._result import TrainingResult

        engine = MLEngine()
        calls: list[dict[str, Any]] = []

        async def _fake_fit(**kwargs: Any) -> TrainingResult:
            calls.append(kwargs)
            return TrainingResult(
                family=kwargs.get("family") or "refit",
                metrics={"accuracy": 0.99},
                model_uri="models://refit/v1",
                device_used="cpu",
                accelerator="cpu",
                precision="32-true",
                elapsed_seconds=0.01,
                tracker_run_id=None,
                tenant_id=None,
                artifact_uris={},
                lightning_trainer_config={},
                hyperparameters={},
                feature_importance=None,
                device=None,
            )

        monkeypatch.setattr(engine, "fit", _fake_fit)

        candidate = TrainingResult(
            family="sklearn",
            metrics={"accuracy": 0.8},
            model_uri="models://cand/v1",
            device_used="cpu",
            accelerator="cpu",
            precision="32-true",
            elapsed_seconds=0.01,
            tracker_run_id=None,
            tenant_id=None,
            artifact_uris={},
            lightning_trainer_config={},
            hyperparameters={"n_estimators": 10},
            feature_importance=None,
            device=None,
        )
        df = _frame()
        result = await engine.finalize(candidate, full_fit=True, data=df, target="y")
        assert len(calls) == 1, "finalize(full_fit=True) MUST dispatch to self.fit()"
        assert calls[0]["family"] == "sklearn"
        assert calls[0]["target"] == "y"
        assert result.full_fit is True

    @pytest.mark.asyncio
    async def test_full_fit_false_skips_fit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """full_fit=False wraps the candidate without re-dispatching."""
        from kailash_ml._result import TrainingResult

        engine = MLEngine()

        async def _boom(**kwargs: Any) -> TrainingResult:
            raise AssertionError("finalize(full_fit=False) MUST NOT call self.fit()")

        monkeypatch.setattr(engine, "fit", _boom)
        candidate = TrainingResult(
            family="sklearn",
            metrics={"accuracy": 0.8},
            model_uri="models://cand/v1",
            device_used="cpu",
            accelerator="cpu",
            precision="32-true",
            elapsed_seconds=0.01,
            tracker_run_id=None,
            tenant_id=None,
            artifact_uris={},
            lightning_trainer_config={},
            hyperparameters={},
            feature_importance=None,
            device=None,
        )
        result = await engine.finalize(candidate, full_fit=False)
        assert result.full_fit is False


# ----------------------------------------------------------------------
# Invariant 9: evaluate(mode=) enum
# ----------------------------------------------------------------------


class TestInvariant9EvaluateModeEnum:
    @pytest.mark.asyncio
    async def test_invalid_mode_rejected(self) -> None:
        engine = MLEngine()
        df = _frame()
        with pytest.raises(ValueError, match="mode"):
            await engine.evaluate(model="models://nope/v1", data=df, mode="gibberish")

    @pytest.mark.asyncio
    async def test_accepted_modes_pass_enum_check(self) -> None:
        """The three modes pass the enum gate; downstream failures differ."""
        engine = MLEngine()
        df = _frame()
        for m in ("holdout", "shadow", "live"):
            with pytest.raises(Exception) as exc_info:
                await engine.evaluate(model="models://nope/v1", data=df, mode=m)
            # Failure MUST NOT be the mode enum check.
            assert not (
                isinstance(exc_info.value, ValueError)
                and "mode" in str(exc_info.value).lower()
                and "must be" in str(exc_info.value).lower()
            ), f"mode={m!r} should be accepted; got {exc_info.value}"


# ----------------------------------------------------------------------
# Invariant 10: SchemaDriftError when fit schema != setup schema
# ----------------------------------------------------------------------


class TestInvariant10SchemaDriftDetection:
    @pytest.mark.asyncio
    async def test_drift_between_setup_and_fit(self) -> None:
        engine = MLEngine()
        setup_df = _frame()
        await engine.setup(setup_df, target="y")

        # Mutate: add a new feature column → fit-time schema hash diverges.
        drift_df = setup_df.with_columns(
            pl.Series("x_new", [i * 3 for i in range(len(setup_df))])
        )
        t = _CaptureTrainable()
        with pytest.raises(SchemaDriftError) as exc_info:
            await engine.fit(data=drift_df, target="y", trainable=t)
        assert exc_info.value.before != exc_info.value.after

    @pytest.mark.asyncio
    async def test_matching_schema_passes(self) -> None:
        """Sanity: same frame after setup() fits without drift error."""
        engine = MLEngine()
        df = _frame()
        await engine.setup(df, target="y")
        t = _CaptureTrainable()
        # Must NOT raise SchemaDriftError — re-using the exact frame.
        result = await engine.fit(data=df, target="y", trainable=t)
        assert result.family == "capture-fake"

    @pytest.mark.asyncio
    async def test_no_setup_no_drift_check(self) -> None:
        """With no setup_result, drift cannot be detected — fit proceeds."""
        engine = MLEngine()
        df = _frame()
        t = _CaptureTrainable()
        # No setup() → fit must not raise SchemaDriftError.
        result = await engine.fit(data=df, target="y", trainable=t)
        assert result.family == "capture-fake"
