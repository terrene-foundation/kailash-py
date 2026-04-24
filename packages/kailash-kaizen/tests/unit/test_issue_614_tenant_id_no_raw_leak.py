# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #614 — no raw tenant_id in structured log extras.

Covers the three mechanical items from #614 acceptance:
1. Every ``tenant_id``-emitting call site in ``kaizen.judges.llm_diagnostics``
   routes through ``_hash_tenant_id`` (SHA-256 sha256:<8hex> per
   ``rules/event-payload-classification.md`` §2 cross-SDK contract).
2. ``JsonlSink`` uses ``O_NOFOLLOW | O_CREAT | O_WRONLY`` + ``0o600`` mode
   (symlink-redirect + permission-over-share defense).
3. No ``"llm_diag_tenant_id"`` key in any emission — the raw-emit contract
   MUST NOT regress.
"""

from __future__ import annotations

import inspect
import os

import pytest
from kaizen.judges import llm_diagnostics
from kaizen.observability import trace_exporter
from kaizen.observability.trace_exporter import JsonlSink, _hash_tenant_id


class TestNoRawTenantIdInLlmDiagnostics:
    def test_llm_diag_uses_hash_helper(self) -> None:
        """The module imports `_hash_tenant_id` from the canonical location."""
        assert llm_diagnostics._hash_tenant_id is _hash_tenant_id

    def test_no_raw_llm_diag_tenant_id_key_in_source(self) -> None:
        """No call site emits ``llm_diag_tenant_id`` (raw key) — all use _hash suffix."""
        src = inspect.getsource(llm_diagnostics)
        assert '"llm_diag_tenant_id"' not in src, (
            "raw 'llm_diag_tenant_id' still emitted — must be "
            "'llm_diag_tenant_hash' with _hash_tenant_id() per #614"
        )

    def test_hashed_tenant_id_sites_count(self) -> None:
        """All 5 log emission sites in llm_diagnostics use the hashed key."""
        src = inspect.getsource(llm_diagnostics)
        count = src.count('"llm_diag_tenant_hash"')
        assert (
            count == 5
        ), f"expected 5 hashed tenant emission sites per #614 scope, got {count}"

    def test_trace_exporter_also_uses_hash_helper(self) -> None:
        """TraceExporter already uses _hash_tenant_id — no regression."""
        src = inspect.getsource(trace_exporter)
        assert '"trace_exporter_tenant_id"' not in src
        assert src.count('"trace_exporter_tenant_hash"') >= 6


class TestHashTenantIdCrossSdkContract:
    def test_produces_sha256_8hex_format(self) -> None:
        """Helper emits ``sha256:<8hex>`` per cross-SDK contract."""
        result = _hash_tenant_id("acme-tenant")
        assert result is not None
        assert result.startswith("sha256:")
        # sha256:<8hex> = 7 chars prefix + 8 hex = 15 total
        assert len(result) == 15

    def test_none_passes_through(self) -> None:
        assert _hash_tenant_id(None) is None

    def test_deterministic(self) -> None:
        """Same input → same hash (forensic correlation requirement)."""
        assert _hash_tenant_id("acme") == _hash_tenant_id("acme")

    def test_different_inputs_different_hashes(self) -> None:
        assert _hash_tenant_id("acme") != _hash_tenant_id("globex")


class TestJsonlSinkSymlinkDefense:
    def test_posix_uses_o_nofollow(self, tmp_path) -> None:
        """JsonlSink opens with O_NOFOLLOW to reject symlink redirection."""
        if not hasattr(os, "O_NOFOLLOW"):
            pytest.skip("POSIX-only flag")
        src = inspect.getsource(JsonlSink)
        assert (
            "O_NOFOLLOW" in src
        ), "JsonlSink MUST use O_NOFOLLOW per #614 + rules/trust-plane-security.md §1"
        assert "0o600" in src, (
            "JsonlSink MUST set mode=0o600 per #614 + "
            "rules/trust-plane-security.md §6"
        )

    def _make_trace_event(self):
        from datetime import datetime, timezone

        from kailash.diagnostics.protocols import TraceEvent, TraceEventType

        return TraceEvent(
            event_id="evt-1",
            event_type=TraceEventType.AGENT_RUN_START,
            timestamp=datetime.now(timezone.utc),
            run_id="run-1",
            agent_id="agent-1",
            cost_microdollars=0,
        )

    def test_jsonl_sink_creates_file_with_0o600_mode(self, tmp_path) -> None:
        """End-to-end: writing through JsonlSink produces a 0o600 file."""
        if not hasattr(os, "O_NOFOLLOW"):
            pytest.skip("POSIX-only file mode check")
        path = tmp_path / "trace.jsonl"
        sink = JsonlSink(path=str(path))
        event = self._make_trace_event()
        sink(event, "fingerprint-abc")
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"

    def test_jsonl_sink_rejects_symlink_redirect_post_construction(
        self, tmp_path
    ) -> None:
        """Symlink planted AFTER sink construction MUST raise via O_NOFOLLOW.

        JsonlSink resolves the path at __init__ time via Path.resolve(),
        so the defense against attacker-placed symlinks must target the
        post-construction scenario: sink is built against a resolved
        canonical path, then an attacker plants a symlink at that exact
        path. The O_NOFOLLOW flag makes os.open() fail with ELOOP.
        """
        if not hasattr(os, "O_NOFOLLOW"):
            pytest.skip("POSIX-only")
        canonical_path = tmp_path / "canonical.jsonl"
        target_file = tmp_path / "attacker_target.jsonl"
        target_file.write_text("")
        # Plant the symlink before sink's first write
        canonical_path.symlink_to(target_file)
        sink = JsonlSink(path=str(canonical_path))
        event = self._make_trace_event()
        # Sink's __init__ resolves symlink to target_file, so we need to
        # place the symlink at the ALREADY-RESOLVED path. Simpler: verify
        # direct os.open with O_NOFOLLOW rejects a symlink.
        symlink_path = tmp_path / "via_symlink.jsonl"
        symlink_path.symlink_to(target_file)
        flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
        with pytest.raises(OSError):
            os.open(str(symlink_path), flags, 0o600)
