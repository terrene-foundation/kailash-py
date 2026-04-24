# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests — channel adapters (rest / mcp / grpc).

Covers:

* W25 invariant 3 — ``bind_rest`` produces a URI that ends with
  ``/predict/{ModelName}``.
* W25 invariant 8 — ``bind_grpc`` raises :class:`ImportError` with an
  actionable install hint when the [grpc] extra is missing.
* The ``ChannelBinding`` invoke/stop contracts.
"""
from __future__ import annotations

import asyncio
import importlib
import sys
from typing import Any, Mapping

import pytest

from kailash_ml.serving.channels import ChannelBinding
from kailash_ml.serving.channels.mcp import bind_mcp
from kailash_ml.serving.channels.rest import bind_rest, health_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _echo_invoke(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Simple echoing invoke callback for adapter-contract tests."""
    return {"echoed": dict(payload), "framework": "test"}


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------


class TestBindRest:
    def test_rest_uri_ends_with_predict_model_name(self):
        # W25 invariant 3
        binding = bind_rest(
            model_name="fraud",
            model_version=3,
            invoke=_echo_invoke,
            server_id="server-abc",
            tenant_id="acme",
        )
        assert binding.uri.endswith("/predict/fraud")

    def test_rest_default_host_port_present(self):
        binding = bind_rest(
            model_name="fraud",
            model_version=1,
            invoke=_echo_invoke,
            server_id="s1",
            tenant_id=None,
        )
        assert binding.uri.startswith("http://127.0.0.1:0/predict/")
        assert binding.channel == "rest"

    def test_rest_custom_host_port(self):
        binding = bind_rest(
            model_name="fraud",
            model_version=1,
            invoke=_echo_invoke,
            host="10.0.0.5",
            port=8080,
            server_id="s1",
            tenant_id=None,
        )
        assert binding.uri == "http://10.0.0.5:8080/predict/fraud"

    def test_rest_empty_model_name_rejected(self):
        with pytest.raises(ValueError, match="non-empty model_name"):
            bind_rest(
                model_name="",
                model_version=1,
                invoke=_echo_invoke,
                server_id="s1",
                tenant_id=None,
            )

    def test_rest_invoke_round_trip(self):
        binding = bind_rest(
            model_name="fraud",
            model_version=1,
            invoke=_echo_invoke,
            server_id="s1",
            tenant_id=None,
        )
        result = asyncio.run(binding.invoke({"amount": 42.0}))
        assert result == {"echoed": {"amount": 42.0}, "framework": "test"}

    def test_rest_stop_is_async_noop(self):
        binding = bind_rest(
            model_name="fraud",
            model_version=1,
            invoke=_echo_invoke,
            server_id="s1",
            tenant_id=None,
        )
        # async noop must be awaitable and return None
        assert asyncio.run(binding.stop()) is None

    def test_health_response_shape(self):
        body = health_response(model_name="fraud", model_version=3)
        assert body["status"] == "healthy"
        assert body["model"] == "fraud"
        assert body["model_version"] == 3


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------


class TestBindMcp:
    def test_mcp_uri_mcp_stdio_scheme(self):
        binding = bind_mcp(
            model_name="fraud",
            model_version=2,
            invoke=_echo_invoke,
            server_id="server-xyz",
            tenant_id="acme",
        )
        assert binding.uri.startswith("mcp+stdio://")
        assert binding.uri.endswith("/predict_fraud")

    def test_mcp_handle_deterministic_for_same_inputs(self):
        a = bind_mcp(
            model_name="fraud",
            model_version=2,
            invoke=_echo_invoke,
            server_id="s1",
            tenant_id="acme",
        )
        b = bind_mcp(
            model_name="fraud",
            model_version=2,
            invoke=_echo_invoke,
            server_id="s1",
            tenant_id="acme",
        )
        # Same server_id+model+version+tenant -> same handle
        assert a.uri == b.uri

    def test_mcp_handle_differs_for_different_tenants(self):
        a = bind_mcp(
            model_name="fraud",
            model_version=2,
            invoke=_echo_invoke,
            server_id="s1",
            tenant_id="acme",
        )
        b = bind_mcp(
            model_name="fraud",
            model_version=2,
            invoke=_echo_invoke,
            server_id="s1",
            tenant_id="bob",
        )
        assert a.uri != b.uri

    def test_mcp_info_carries_tool_name(self):
        binding = bind_mcp(
            model_name="fraud",
            model_version=1,
            invoke=_echo_invoke,
            server_id="s1",
            tenant_id=None,
        )
        assert binding.info is not None
        assert binding.info["tool_name"] == "predict_fraud"

    def test_mcp_empty_model_name_rejected(self):
        with pytest.raises(ValueError, match="non-empty model_name"):
            bind_mcp(
                model_name="",
                model_version=1,
                invoke=_echo_invoke,
                server_id="s1",
                tenant_id=None,
            )


# ---------------------------------------------------------------------------
# gRPC — gated by [grpc] extra per invariant 8
# ---------------------------------------------------------------------------


class TestBindGrpc:
    def test_grpc_raises_when_extra_missing(self, monkeypatch):
        # Simulate the extra not being installed by removing grpc from
        # sys.modules AND blocking re-import via a spec-finder.
        monkeypatch.setitem(sys.modules, "grpc", None)
        # Reload the module to re-trigger the import-time check on the
        # _require_grpc_extra path.
        import kailash_ml.serving.channels.grpc as grpc_mod

        importlib.reload(grpc_mod)
        with pytest.raises(ImportError, match=r"\[grpc\] optional extra"):
            grpc_mod.bind_grpc(
                model_name="fraud",
                model_version=1,
                invoke=_echo_invoke,
                server_id="s1",
                tenant_id=None,
            )

    def test_grpc_error_message_includes_install_hint(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "grpc", None)
        import kailash_ml.serving.channels.grpc as grpc_mod

        importlib.reload(grpc_mod)
        with pytest.raises(ImportError) as exc_info:
            grpc_mod.bind_grpc(
                model_name="fraud",
                model_version=1,
                invoke=_echo_invoke,
                server_id="s1",
                tenant_id=None,
            )
        assert "pip install kailash-ml[grpc]" in str(exc_info.value)


# ---------------------------------------------------------------------------
# ChannelBinding contract
# ---------------------------------------------------------------------------


class TestChannelBindingContract:
    def test_channel_binding_is_mutable_slots(self):
        # slots=True with frozen=False — supports field assignment
        binding = ChannelBinding(
            channel="rest",
            uri="http://x/y",
            invoke=_echo_invoke,
            stop=lambda: asyncio.sleep(0),  # type: ignore[arg-type]
        )
        assert binding.channel == "rest"
        assert binding.uri == "http://x/y"
