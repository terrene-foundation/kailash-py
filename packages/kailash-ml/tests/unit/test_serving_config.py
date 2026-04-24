# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests — ``InferenceServerConfig`` validation.

W25 invariants covered:

* Invariant 6 — runtime is ``"onnx"`` (default) or ``"pickle"`` only;
  unknown runtimes raise at construction.
* Invariant 8 — the ``"grpc"`` channel is accepted at config-time even
  when the [grpc] extra is missing. Channel *binding* raises; config
  construction does NOT — enables validation of config payloads without
  loading the extra.
* Invariant 2 — ``batch_size`` default is ``None`` (no batch) with
  positive-int override via ``options={"batch_size": N}``.
"""
from __future__ import annotations

import pytest

from kailash_ml.serving import (
    ALLOWED_CHANNELS,
    ALLOWED_RUNTIMES,
    DEFAULT_CHANNELS,
    InferenceServerConfig,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConfigConstants:
    def test_allowed_runtimes_is_onnx_and_pickle_only(self):
        assert ALLOWED_RUNTIMES == ("onnx", "pickle")

    def test_allowed_channels_matches_spec(self):
        assert ALLOWED_CHANNELS == ("rest", "mcp", "grpc")

    def test_default_channels_is_rest_only(self):
        assert DEFAULT_CHANNELS == ("rest",)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestConfigHappyPath:
    def test_minimal_construction(self):
        config = InferenceServerConfig(
            tenant_id="acme",
            model_name="fraud",
            model_version=1,
        )
        assert config.tenant_id == "acme"
        assert config.model_name == "fraud"
        assert config.model_version == 1
        assert config.alias is None
        assert config.channels == DEFAULT_CHANNELS
        assert config.runtime == "onnx"
        assert config.batch_size is None

    def test_multi_channel_construction(self):
        config = InferenceServerConfig(
            tenant_id="acme",
            model_name="fraud",
            model_version=2,
            channels=("rest", "mcp"),
        )
        assert config.channels == ("rest", "mcp")

    def test_pickle_runtime_accepted(self):
        config = InferenceServerConfig(
            tenant_id=None,
            model_name="legacy",
            model_version=1,
            runtime="pickle",
        )
        assert config.runtime == "pickle"

    def test_single_tenant_allows_none_tenant_id(self):
        # Single-tenant deployments explicitly set tenant_id=None
        config = InferenceServerConfig(
            tenant_id=None,
            model_name="fraud",
            model_version=1,
        )
        assert config.tenant_id is None

    def test_batch_size_accepted(self):
        config = InferenceServerConfig(
            tenant_id="acme",
            model_name="fraud",
            model_version=1,
            batch_size=64,
        )
        assert config.batch_size == 64

    def test_grpc_channel_accepts_config_time(self):
        # Invariant 8: config-time acceptance; bind_grpc raises when
        # the [grpc] extra is missing. Users can author config payloads
        # without the extra installed.
        config = InferenceServerConfig(
            tenant_id="acme",
            model_name="fraud",
            model_version=1,
            channels=("rest", "grpc"),
        )
        assert "grpc" in config.channels

    def test_alias_stored_verbatim(self):
        config = InferenceServerConfig(
            tenant_id="acme",
            model_name="fraud",
            model_version=7,
            alias="@production",
        )
        assert config.alias == "@production"


# ---------------------------------------------------------------------------
# Rejections
# ---------------------------------------------------------------------------


class TestConfigRejections:
    def test_empty_model_name_raises(self):
        with pytest.raises(ValueError, match="model_name is required"):
            InferenceServerConfig(tenant_id="acme", model_name="", model_version=1)

    def test_zero_version_raises(self):
        with pytest.raises(ValueError, match="model_version must be >= 1"):
            InferenceServerConfig(tenant_id="acme", model_name="fraud", model_version=0)

    def test_negative_version_raises(self):
        with pytest.raises(ValueError, match="model_version must be >= 1"):
            InferenceServerConfig(
                tenant_id="acme", model_name="fraud", model_version=-1
            )

    def test_unknown_runtime_raises(self):
        with pytest.raises(ValueError, match="runtime must be one of"):
            InferenceServerConfig(
                tenant_id="acme",
                model_name="fraud",
                model_version=1,
                runtime="torchscript",  # type: ignore[arg-type]
            )

    def test_empty_channels_raises(self):
        with pytest.raises(ValueError, match="channels must be a non-empty"):
            InferenceServerConfig(
                tenant_id="acme",
                model_name="fraud",
                model_version=1,
                channels=(),
            )

    def test_unsupported_channel_raises(self):
        with pytest.raises(ValueError, match="unsupported channels"):
            InferenceServerConfig(
                tenant_id="acme",
                model_name="fraud",
                model_version=1,
                channels=("rest", "websocket"),
            )

    def test_zero_batch_size_raises(self):
        with pytest.raises(ValueError, match="batch_size must be >= 1"):
            InferenceServerConfig(
                tenant_id="acme",
                model_name="fraud",
                model_version=1,
                batch_size=0,
            )

    def test_negative_batch_size_raises(self):
        with pytest.raises(ValueError, match="batch_size must be >= 1"):
            InferenceServerConfig(
                tenant_id="acme",
                model_name="fraud",
                model_version=1,
                batch_size=-5,
            )
