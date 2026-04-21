"""Pin-value regression test for MCP elicitation/create error codes.

Cross-SDK parity with kailash-rs v3.x (issue #572 / kailash-rs#471). The four
JSON-RPC error codes emitted by ``ElicitationSystem`` to MCP clients MUST
match kailash-rs byte-for-byte — MCP is a wire-level protocol and clients
written against one SDK's codes MUST handle the same errors when the server
runs the other SDK.

Canonical source: MCP specification 2025-06-18 / JSON-RPC 2.0 reserved range.
"""

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Terrene Foundation

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from kailash_mcp.errors import MCPError, MCPErrorCode


@pytest.mark.unit
class TestElicitationErrorCodeParity:
    """Cross-SDK parity: the four MCP elicitation/create wire codes."""

    def test_mcp_request_cancelled_pins_to_minus_32800(self) -> None:
        assert MCPErrorCode.MCP_REQUEST_CANCELLED.value == -32800

    def test_mcp_elicitation_timeout_pins_to_minus_32001(self) -> None:
        assert MCPErrorCode.MCP_ELICITATION_TIMEOUT.value == -32001

    def test_mcp_transport_rebound_pins_to_minus_32002(self) -> None:
        assert MCPErrorCode.MCP_TRANSPORT_REBOUND.value == -32002

    def test_mcp_schema_validation_pins_to_minus_32602(self) -> None:
        assert MCPErrorCode.MCP_SCHEMA_VALIDATION.value == -32602

    def test_all_four_codes_together(self) -> None:
        """The four codes as a set — the cross-SDK contract."""
        codes = {
            "RequestCancelled": MCPErrorCode.MCP_REQUEST_CANCELLED.value,
            "SchemaValidation": MCPErrorCode.MCP_SCHEMA_VALIDATION.value,
            "ElicitationTimeout": MCPErrorCode.MCP_ELICITATION_TIMEOUT.value,
            "TransportRebound": MCPErrorCode.MCP_TRANSPORT_REBOUND.value,
        }
        assert codes == {
            "RequestCancelled": -32800,
            "SchemaValidation": -32602,
            "ElicitationTimeout": -32001,
            "TransportRebound": -32002,
        }


@pytest.mark.unit
class TestElicitationWireSerialization:
    """MCPError wraps the MCP code on the wire — the value reaches the client."""

    def test_request_cancelled_serializes_to_minus_32800(self) -> None:
        err = MCPError(
            "Client cancelled elicitation request: decline",
            error_code=MCPErrorCode.MCP_REQUEST_CANCELLED,
        )
        assert err.error_code.value == -32800

    def test_timeout_serializes_to_minus_32001(self) -> None:
        err = MCPError(
            "Elicitation request req-xyz timed out after 30s",
            error_code=MCPErrorCode.MCP_ELICITATION_TIMEOUT,
        )
        assert err.error_code.value == -32001


@pytest.mark.unit
class TestElicitationSystemCallSites:
    """Structural invariant: ElicitationSystem uses the MCP wire codes, not
    the legacy positive application codes (1006/1007). If this regresses the
    server will emit application codes to MCP clients, breaking cross-SDK
    clients written against the spec.
    """

    def test_elicitation_features_uses_mcp_wire_codes(self) -> None:
        features_path = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "kailash_mcp"
            / "advanced"
            / "features.py"
        )
        source = features_path.read_text()

        # Locate the ElicitationSystem class body by text scan.
        start = source.index("class ElicitationSystem")
        end = source.index("class ", start + 1)
        elicitation_src = source[start:end]

        # Cancellation and timeout paths MUST use the MCP wire constants.
        assert "MCPErrorCode.MCP_REQUEST_CANCELLED" in elicitation_src, (
            "ElicitationSystem cancel callback must raise MCP_REQUEST_CANCELLED "
            "(-32800) not REQUEST_CANCELLED (1007). See issue #572."
        )
        assert "MCPErrorCode.MCP_ELICITATION_TIMEOUT" in elicitation_src, (
            "ElicitationSystem timeout path must raise MCP_ELICITATION_TIMEOUT "
            "(-32001) not REQUEST_TIMEOUT (1006). See issue #572."
        )

        # Legacy positive application codes MUST NOT appear inside
        # ElicitationSystem — they belong to non-wire application layers.
        assert "MCPErrorCode.REQUEST_CANCELLED" not in elicitation_src, (
            "ElicitationSystem must not use REQUEST_CANCELLED (1007) — "
            "positive codes are not valid JSON-RPC wire codes. Use "
            "MCP_REQUEST_CANCELLED (-32800) for client-decline / client-cancel."
        )
        assert "MCPErrorCode.REQUEST_TIMEOUT" not in elicitation_src, (
            "ElicitationSystem must not use REQUEST_TIMEOUT (1006). Use "
            "MCP_ELICITATION_TIMEOUT (-32001) for timeout on the wire."
        )

    def test_elicitation_system_constructor_signature_invariant(self) -> None:
        """Locks the ElicitationSystem init signature so a future refactor
        toward a different shape fails loudly.
        """
        from kailash_mcp.advanced.features import ElicitationSystem

        sig = inspect.signature(ElicitationSystem.__init__)
        params = [p for p in sig.parameters.values() if p.name != "self"]
        assert [p.name for p in params] == ["send"], (
            f"ElicitationSystem.__init__ signature drifted: {sig}. "
            f"Cross-SDK parity relies on a fixed send-callable shape."
        )
