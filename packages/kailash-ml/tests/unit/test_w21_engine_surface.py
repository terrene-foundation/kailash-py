# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W21 — MLEngine register()/serve() dispatch invariant tests.

Covers the 6 invariants from the master wave plan §W21 against
``specs/ml-engines-v2.md §2.1 MUST 9-10 + §6`` at the engine dispatch
layer (Tier 1). Heavy Tier 2 coverage (full ONNX round-trip across the
six-framework matrix, real Nexus ml-endpoints registration) lives in
``tests/integration/test_engine_register_onnx_matrix.py`` and the W31
cross-framework cycle.

Invariants (§W21 plan + spec §2.1 MUST 9-10 + §6.1 MUST 1/5):

1. ``register()`` default ``format`` is ``"onnx"`` — `_export_and_save_onnx`
   dispatches with format="onnx" when no kwarg is supplied.
2. ``register()`` returns ``RegisterResult`` with ``artifact_uris["onnx"]``
   present on a successful ONNX export.
3. ``register(format="both")`` invokes ONNX export AND writes a pickle
   artifact; both keys land in ``artifact_uris``.
4. ``register(format="pickle")`` skips ONNX entirely (no call into
   `_export_and_save_onnx`) and writes only a pickle artifact.
5. ``serve(channels=["rest", "mcp"])`` brings up both channels from a
   single call; ``ServeResult.uris`` carries one entry per requested
   channel and ``.channels`` reflects the requested order.
6. ``serve(channels=["grpc"])`` dispatches to ``_bind_grpc`` — validates
   the enum gate accepts "grpc" at the dispatch layer. Real gRPC bind
   still requires the ``[grpc]`` extra (not exercised here).

Plus argument-validation invariants:

- ``register(format="xml")`` raises ``ValueError`` on unknown format.
- ``register(stage="prod")`` raises ``ValueError`` on unknown stage.
- ``serve(channels=[])`` raises ``ValueError`` on empty channel list.
- ``serve(channels=["websocket"])`` raises ``ValueError`` on unsupported.
"""
from __future__ import annotations

import pickle
from typing import Any

import pytest

from kailash_ml import MLEngine


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


class _PicklableModel:
    """Minimal picklable stand-in. Not ONNX-exportable."""

    def __init__(self, k: int = 3) -> None:
        self.k = k

    def predict(
        self, X: Any
    ) -> list[int]:  # pragma: no cover — unused in dispatch tests
        return [self.k] * len(X)


def _training_result_with_model() -> Any:
    """TrainingResult-shaped object that register() will accept.

    The ``model`` slot carries a picklable object so register(format="pickle"|
    "both") exercises the pickle path without depending on sklearn/xgboost.
    """
    from kailash_ml._result import TrainingResult

    tr = TrainingResult(
        family="sklearn",  # any valid family key works; ONNX path is stubbed
        metrics={"accuracy": 0.9},
        model_uri="models://w21-capture/v1",
        device_used="cpu",
        accelerator="cpu",
        precision="32-true",
        elapsed_seconds=0.01,
        tracker_run_id=None,
        tenant_id=None,
        artifact_uris={},
        lightning_trainer_config={},
    )
    object.__setattr__(tr, "model", _PicklableModel())
    return tr


async def _stub_ok_onnx(
    self: Any,
    *,
    model: Any,
    framework: str,
    name: str,
    version: int,
    artifact_store: Any,
    format: str,
) -> str:
    """Stub for ``_export_and_save_onnx`` that records the dispatch call.

    Returns a deterministic fake URI so register() records
    ``artifact_uris["onnx"]`` without invoking the real ONNX bridge.
    """
    self._w21_onnx_calls.append(
        {
            "framework": framework,
            "name": name,
            "version": version,
            "format": format,
        }
    )
    return f"file:///stub/onnx/{name}/v{version}/model.onnx"


@pytest.fixture
def engine_env(tmp_path: Any, monkeypatch: Any) -> None:
    """Route the engine's default store + artifact root into tmp_path."""
    monkeypatch.setenv("KAILASH_ML_STORE_URL", f"sqlite:///{tmp_path}/w21.db")
    monkeypatch.setenv("KAILASH_ML_ARTIFACT_ROOT", str(tmp_path))


@pytest.fixture
async def managed_engines() -> Any:
    """Yield an MLEngine factory that closes each engine's ConnectionManager.

    MLEngine lazily constructs an aiosqlite ConnectionManager in
    ``_acquire_connection()``; without explicit close(), aiosqlite's
    worker thread outlives the per-test event loop and the subsequent
    test run trips ``RuntimeError: Event loop is closed`` during GC.
    """
    created: list[MLEngine] = []

    def _make(*args: Any, **kwargs: Any) -> MLEngine:
        engine = MLEngine(*args, **kwargs)
        created.append(engine)
        return engine

    yield _make

    for engine in created:
        cm = engine._connection_manager
        if cm is not None and hasattr(cm, "close"):
            try:
                await cm.close()
            except Exception:  # pragma: no cover — best-effort teardown
                pass


def _install_onnx_stub(monkeypatch: Any, engine: MLEngine) -> list[dict[str, Any]]:
    """Install the success-path ONNX stub on the engine and return call log."""
    engine._w21_onnx_calls = []  # type: ignore[attr-defined]
    monkeypatch.setattr(
        MLEngine,
        "_export_and_save_onnx",
        _stub_ok_onnx,
        raising=True,
    )
    return engine._w21_onnx_calls  # type: ignore[return-value]


# ----------------------------------------------------------------------
# Invariant 1 — register() default format is "onnx"
# ----------------------------------------------------------------------


class TestInvariant1OnnxIsDefault:
    @pytest.mark.asyncio
    async def test_register_default_dispatches_onnx(
        self, engine_env: None, monkeypatch: Any, managed_engines: Any
    ) -> None:
        engine = managed_engines()
        calls = _install_onnx_stub(monkeypatch, engine)

        reg = await engine.register(_training_result_with_model())

        assert len(calls) == 1
        # ONNX dispatch MUST receive format="onnx" when caller omitted it.
        assert calls[0]["format"] == "onnx"
        # Sanity: register returned a RegisterResult, not a raw dict.
        # The synthesised name comes from _synthesise_model_name(result);
        # the family prefix is the one stable component across runs.
        assert reg.name.startswith("sklearn")
        assert reg.stage == "staging"

    @pytest.mark.asyncio
    async def test_register_explicit_onnx_is_identical(
        self, engine_env: None, monkeypatch: Any, managed_engines: Any
    ) -> None:
        """Passing format='onnx' explicitly dispatches identically to default."""
        engine = managed_engines()
        calls = _install_onnx_stub(monkeypatch, engine)

        await engine.register(_training_result_with_model(), format="onnx")

        assert len(calls) == 1
        assert calls[0]["format"] == "onnx"


# ----------------------------------------------------------------------
# Invariant 2 — RegisterResult.artifact_uris["onnx"] present on success
# ----------------------------------------------------------------------


class TestInvariant2ArtifactUrisOnnxKey:
    @pytest.mark.asyncio
    async def test_onnx_key_present_on_success(
        self, engine_env: None, monkeypatch: Any, managed_engines: Any
    ) -> None:
        engine = managed_engines()
        _install_onnx_stub(monkeypatch, engine)

        reg = await engine.register(_training_result_with_model())

        assert "onnx" in reg.artifact_uris
        # Pickle MUST NOT be present on format="onnx" (default) per §6.1 MUST 5.
        assert "pickle" not in reg.artifact_uris
        # The URI is the exact value the stub returned (dispatch-layer assertion).
        assert reg.artifact_uris["onnx"].endswith("/model.onnx")


# ----------------------------------------------------------------------
# Invariant 3 — format="both" writes onnx + pickle
# ----------------------------------------------------------------------


class TestInvariant3FormatBoth:
    @pytest.mark.asyncio
    async def test_format_both_invokes_onnx_and_writes_pickle(
        self, engine_env: None, monkeypatch: Any, managed_engines: Any
    ) -> None:
        engine = managed_engines()
        calls = _install_onnx_stub(monkeypatch, engine)

        reg = await engine.register(_training_result_with_model(), format="both")

        # ONNX dispatch fires with format="both" (the engine propagates the
        # kwarg so the helper can tolerate partial failure per §6.1 MUST 5).
        assert len(calls) == 1
        assert calls[0]["format"] == "both"
        # Both artifacts land on the result envelope.
        assert "onnx" in reg.artifact_uris
        assert "pickle" in reg.artifact_uris


# ----------------------------------------------------------------------
# Invariant 4 — format="pickle" skips ONNX entirely
# ----------------------------------------------------------------------


class TestInvariant4FormatPickleSkipsOnnx:
    @pytest.mark.asyncio
    async def test_pickle_skips_onnx_dispatch(
        self, engine_env: None, monkeypatch: Any, managed_engines: Any
    ) -> None:
        engine = managed_engines()
        calls = _install_onnx_stub(monkeypatch, engine)

        reg = await engine.register(_training_result_with_model(), format="pickle")

        # ONNX helper MUST NOT be called on format="pickle" per §6.1 MUST 5.
        assert calls == []
        assert "onnx" not in reg.artifact_uris
        assert "pickle" in reg.artifact_uris


# ----------------------------------------------------------------------
# Invariant 5 — serve() multi-channel from one call
# ----------------------------------------------------------------------


class _FakeBinding:
    """Minimal _ServeBinding-shaped object for dispatch capture."""

    def __init__(self, channel: str, uri: str) -> None:
        self.channel = channel
        self.uri = uri

    async def shutdown(self) -> None:  # pragma: no cover — used on rollback path
        return None


def _install_bind_stubs(
    monkeypatch: Any, *, fail_channel: str | None = None
) -> list[str]:
    """Stub `_bind_rest/_bind_mcp/_bind_grpc` to record dispatch order.

    If ``fail_channel`` is set, that channel's bind raises
    ``RuntimeError`` to exercise the partial-failure rollback path.
    """
    dispatched: list[str] = []

    async def _mk(
        self: Any, name: str, ver: int, *, autoscale: bool, options: Any
    ) -> Any:
        channel = getattr(_mk, "_channel", "?")
        dispatched.append(channel)
        if fail_channel == channel:
            raise RuntimeError(f"simulated {channel} bind failure")
        return _FakeBinding(channel, f"stub://{channel}/{name}/v{ver}")

    def _bind_factory(channel_name: str) -> Any:
        async def _bound(
            self: Any, name: str, ver: int, *, autoscale: bool, options: Any
        ) -> Any:
            dispatched.append(channel_name)
            if fail_channel == channel_name:
                raise RuntimeError(f"simulated {channel_name} bind failure")
            return _FakeBinding(channel_name, f"stub://{channel_name}/{name}/v{ver}")

        return _bound

    monkeypatch.setattr(MLEngine, "_bind_rest", _bind_factory("rest"), raising=True)
    monkeypatch.setattr(MLEngine, "_bind_mcp", _bind_factory("mcp"), raising=True)
    monkeypatch.setattr(MLEngine, "_bind_grpc", _bind_factory("grpc"), raising=True)
    return dispatched


def _install_resolve_model_stub(monkeypatch: Any) -> None:
    """Stub `_resolve_model` so serve() doesn't need a registered row."""

    async def _resolve(
        self: Any, model: Any, version: Any
    ) -> tuple[str, int, str, Any]:
        # Mirror the real resolver shape; return ("w21model", 1, uri, None).
        name = "w21model"
        resolved = 1
        return name, resolved, f"models://{name}/v{resolved}", None

    monkeypatch.setattr(MLEngine, "_resolve_model", _resolve, raising=True)


class TestInvariant5ServeMultiChannel:
    @pytest.mark.asyncio
    async def test_rest_and_mcp_from_single_call(
        self, engine_env: None, monkeypatch: Any, managed_engines: Any
    ) -> None:
        engine = managed_engines()
        _install_resolve_model_stub(monkeypatch)
        dispatched = _install_bind_stubs(monkeypatch)

        result = await engine.serve("models://w21model/v1", channels=["rest", "mcp"])

        # Both channels dispatched, in the order requested.
        assert dispatched == ["rest", "mcp"]
        # Result envelope carries one URI per channel.
        assert set(result.uris.keys()) == {"rest", "mcp"}
        # Channels tuple preserves request order per §2.1 MUST 10.
        assert result.channels == ("rest", "mcp")
        assert result.model_uri == "models://w21model/v1"
        assert result.model_version == 1

    @pytest.mark.asyncio
    async def test_duplicate_channels_collapse(
        self, engine_env: None, monkeypatch: Any, managed_engines: Any
    ) -> None:
        """serve(channels=["rest", "rest"]) MUST bind REST once, not twice."""
        engine = managed_engines()
        _install_resolve_model_stub(monkeypatch)
        dispatched = _install_bind_stubs(monkeypatch)

        result = await engine.serve(
            "models://w21model/v1", channels=["rest", "rest", "mcp"]
        )

        # Duplicate "rest" collapses; dispatch order preserves first occurrence.
        assert dispatched == ["rest", "mcp"]
        assert result.channels == ("rest", "mcp")


# ----------------------------------------------------------------------
# Invariant 6 — serve() dispatches to _bind_grpc for channel="grpc"
# ----------------------------------------------------------------------


class TestInvariant6GrpcDispatched:
    @pytest.mark.asyncio
    async def test_grpc_channel_dispatches_to_bind_grpc(
        self, engine_env: None, monkeypatch: Any, managed_engines: Any
    ) -> None:
        engine = managed_engines()
        _install_resolve_model_stub(monkeypatch)
        dispatched = _install_bind_stubs(monkeypatch)

        result = await engine.serve("models://w21model/v1", channels=["grpc"])

        # gRPC is in the accepted enum and MUST route to _bind_grpc per §2.1 MUST 10.
        assert dispatched == ["grpc"]
        assert "grpc" in result.uris

    @pytest.mark.asyncio
    async def test_all_three_channels_from_one_call(
        self, engine_env: None, monkeypatch: Any, managed_engines: Any
    ) -> None:
        """The spec's canonical example — rest+mcp+grpc all from one call."""
        engine = managed_engines()
        _install_resolve_model_stub(monkeypatch)
        dispatched = _install_bind_stubs(monkeypatch)

        result = await engine.serve(
            "models://w21model/v1", channels=["rest", "mcp", "grpc"]
        )

        assert dispatched == ["rest", "mcp", "grpc"]
        assert set(result.uris.keys()) == {"rest", "mcp", "grpc"}
        assert result.channels == ("rest", "mcp", "grpc")


# ----------------------------------------------------------------------
# Partial-failure rollback — no partial ServeResult per §2.1 MUST 10
# ----------------------------------------------------------------------


class TestPartialFailureRollback:
    @pytest.mark.asyncio
    async def test_mid_channel_failure_raises_and_rolls_back(
        self, engine_env: None, monkeypatch: Any, managed_engines: Any
    ) -> None:
        """If channel N fails, channels 1..N-1 are torn down; no partial result."""
        engine = managed_engines()
        _install_resolve_model_stub(monkeypatch)
        # REST succeeds; MCP blows up; GRPC must never dispatch.
        dispatched = _install_bind_stubs(monkeypatch, fail_channel="mcp")

        with pytest.raises(RuntimeError, match="simulated mcp bind failure"):
            await engine.serve("models://w21model/v1", channels=["rest", "mcp", "grpc"])

        # REST + MCP attempted; GRPC never reached.
        assert dispatched == ["rest", "mcp"]


# ----------------------------------------------------------------------
# Argument validation — shared enum gates (reject invalid inputs loudly)
# ----------------------------------------------------------------------


class TestRegisterArgumentValidation:
    @pytest.mark.asyncio
    async def test_unknown_format_raises(
        self, engine_env: None, monkeypatch: Any, managed_engines: Any
    ) -> None:
        engine = managed_engines()
        with pytest.raises(ValueError, match="format"):
            await engine.register(_training_result_with_model(), format="xml")

    @pytest.mark.asyncio
    async def test_unknown_stage_raises(
        self, engine_env: None, monkeypatch: Any, managed_engines: Any
    ) -> None:
        engine = managed_engines()
        with pytest.raises(ValueError, match="stage"):
            await engine.register(_training_result_with_model(), stage="prod")

    @pytest.mark.asyncio
    async def test_result_missing_required_attrs_raises(
        self, engine_env: None, monkeypatch: Any, managed_engines: Any
    ) -> None:
        """Non-TrainingResult-shaped input raises ValueError early."""
        engine = managed_engines()
        with pytest.raises(ValueError, match="TrainingResult-shaped"):
            await engine.register(object())  # type: ignore[arg-type]


class TestServeArgumentValidation:
    @pytest.mark.asyncio
    async def test_empty_channels_raises(
        self, engine_env: None, monkeypatch: Any, managed_engines: Any
    ) -> None:
        engine = managed_engines()
        with pytest.raises(ValueError, match="non-empty"):
            await engine.serve("models://whatever/v1", channels=[])

    @pytest.mark.asyncio
    async def test_unsupported_channel_raises(
        self, engine_env: None, monkeypatch: Any, managed_engines: Any
    ) -> None:
        engine = managed_engines()
        with pytest.raises(ValueError, match="unsupported"):
            await engine.serve("models://whatever/v1", channels=["websocket"])

    @pytest.mark.asyncio
    async def test_mixed_valid_and_invalid_raises_before_dispatch(
        self, engine_env: None, monkeypatch: Any, managed_engines: Any
    ) -> None:
        """One bad channel in the list aborts BEFORE any bind fires."""
        engine = managed_engines()
        _install_resolve_model_stub(monkeypatch)
        dispatched = _install_bind_stubs(monkeypatch)

        with pytest.raises(ValueError, match="unsupported"):
            await engine.serve("models://w21model/v1", channels=["rest", "kafka"])
        # Nothing should have dispatched — validation happens up-front.
        assert dispatched == []


# ----------------------------------------------------------------------
# Sanity: register()'s pickle-only artifact is actually a pickled bytestream
# ----------------------------------------------------------------------


class TestPicklePathWritesValidPickle:
    """Not a W21 invariant per se — guard against a regression where the
    pickle bytes on disk are NOT the result of ``pickle.dumps(model)``."""

    @pytest.mark.asyncio
    async def test_pickle_artifact_roundtrips(
        self,
        engine_env: None,
        monkeypatch: Any,
        tmp_path: Any,
        managed_engines: Any,
    ) -> None:
        engine = managed_engines()
        # No ONNX stub — format="pickle" never calls the ONNX helper.

        reg = await engine.register(_training_result_with_model(), format="pickle")
        assert "pickle" in reg.artifact_uris

        # The URI form is implementation-detail; we only assert the pickle
        # bytes can be round-tripped through the artifact store. reg.name
        # comes from the same _synthesise_model_name path so use it directly.
        store = engine._resolve_artifact_store()
        pickle_bytes = await store.load(reg.name, reg.version, "model.pkl")
        loaded = pickle.loads(pickle_bytes)
        assert isinstance(loaded, _PicklableModel)
        assert loaded.k == 3
