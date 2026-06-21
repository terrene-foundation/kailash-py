# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: every trust-plane signing / hash / HMAC PRE-IMAGE rejects NaN/Inf.

A ``json.dumps`` over a signing or integrity-hash pre-image that omits
``allow_nan=False`` emits RFC-8259-invalid ``NaN`` / ``Infinity`` literals.
Python's permissive ``json`` signs/hashes them fine, but a strict cross-SDK
parser (Rust ``serde_json``) rejects them, so a Python-signed/hashed artifact
whose pre-image carried a NaN/Inf cannot be re-verified cross-SDK — the parity
hazard the canonical-encoder family exists to close.

This is the trust-plane-WIDE sweep of the NaN/Inf-in-pre-image bug class, found
by the pre-release ``/redteam`` multi-site sweep that started from the witness
family (``selective_disclosure.py``) and the envelope HMAC pre-image
(``envelope.to_canonical_json``, commit 9dfb1d968 / PR #1411). Per
``security.md`` Multi-Site Kwarg Plumbing, EVERY signing/hash pre-image site is
swept in the same PR; leaving a sibling on the unqualified signature ships the
exact failure the kwarg fixes.

These surfaces are OUTSIDE ``specs/trust-canonical-encoders.md``'s Family-B
spec table (no pinned cross-SDK byte vectors), so adding ``allow_nan=False`` is
byte-neutral on every finite input and needs no kailash-rs lockstep — it only
newly rejects the already-broken NaN/Inf case. The finite-input "still produces
a stable digest" assertions below pin that byte-neutrality.

Deliberately NOT swept (correct by design): ``pact/audit.py``'s
``_compute_hash_legacy`` / ``_compute_hash_prefix_format`` omit ``allow_nan``
on purpose to reproduce historical pre-fix bytes for forensic
re-seal-vs-tamper disambiguation.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kailash.trust import audit_store as audit_store_mod
from kailash.trust._locking import compute_wal_hash
from kailash.trust.audit_store import AuditRecord
from kailash.trust.chain import ActionResult, AuditAnchor
from kailash.trust.messaging.envelope import SecureMessageEnvelope
from kailash.trust.orchestration.execution_context import TrustExecutionContext

UTC = timezone.utc
_NONFINITE = (float("nan"), float("inf"), float("-inf"))
_MATCH = "JSON compliant"


def _anchor(context: dict) -> AuditAnchor:
    return AuditAnchor(
        id="anc-1",
        agent_id="agent-1",
        action="read",
        timestamp=datetime(2026, 1, 15, 11, 0, 0, tzinfo=UTC),
        trust_chain_hash="h",
        result=ActionResult.SUCCESS,
        signature="s",
        resource="r",
        context=context,
    )


def _envelope(payload: dict) -> SecureMessageEnvelope:
    return SecureMessageEnvelope(
        message_id="m1",
        sender_agent_id="a",
        recipient_agent_id="b",
        payload=payload,
        timestamp=datetime(2026, 1, 15, 11, 0, 0, tzinfo=UTC),
        nonce="n",
        trust_chain_hash="h",
    )


@pytest.mark.regression
class TestTrustSigningPreimageRejectsNanInf:
    """HIGH — messaging Ed25519 signing pre-image (signer.py / verifier.py)."""

    def test_secure_message_signing_payload_rejects_nan_inf(self) -> None:
        for bad in _NONFINITE:
            with pytest.raises(ValueError, match=_MATCH):
                _envelope({"amount": bad}).get_signing_payload()

    def test_secure_message_signing_payload_finite_is_byte_neutral(self) -> None:
        # Finite input still signs deterministically (byte-neutrality).
        out = _envelope({"amount": 1.5, "note": "ok"}).get_signing_payload()
        assert isinstance(out, bytes) and b'"amount":1.5' in out

    # MED — audit-chain Merkle digest (typed Optional[float] duration_ms).
    def test_compute_event_hash_rejects_nan_inf_duration(self) -> None:
        for bad in _NONFINITE:
            with pytest.raises(ValueError, match=_MATCH):
                audit_store_mod._compute_event_hash(
                    "e1", "t", "actor", "act", "res", "ok", "0" * 64, None, bad, {}
                )

    def test_compute_event_hash_rejects_nan_inf_metadata(self) -> None:
        with pytest.raises(ValueError, match=_MATCH):
            audit_store_mod._compute_event_hash(
                "e1",
                "t",
                "actor",
                "act",
                "res",
                "ok",
                "0" * 64,
                None,
                1.0,
                {"score": float("nan")},
            )

    def test_compute_event_hash_finite_is_byte_neutral(self) -> None:
        h = audit_store_mod._compute_event_hash(
            "e1", "t", "actor", "act", "res", "ok", "0" * 64, None, 12.5, {}
        )
        assert isinstance(h, str) and len(h) == 64

    # MED — AuditRecord integrity hash (anchor.to_signing_payload + context).
    def test_audit_record_integrity_hash_rejects_nan_inf_context(self) -> None:
        with pytest.raises(ValueError, match=_MATCH):
            AuditRecord(anchor=_anchor({"cost": float("inf")}), sequence_number=1)

    def test_audit_record_integrity_hash_finite_is_byte_neutral(self) -> None:
        rec = AuditRecord(anchor=_anchor({"cost": 2.0}), sequence_number=1)
        assert len(rec.integrity_hash) == 64

    # LOW — WAL tamper-detection hash (planned_revocations free list).
    def test_compute_wal_hash_rejects_nan_inf(self) -> None:
        with pytest.raises(ValueError, match=_MATCH):
            compute_wal_hash(
                {
                    "root_delegate_id": "r",
                    "planned_revocations": [{"cost": float("nan")}],
                    "reason": "x",
                }
            )

    def test_compute_wal_hash_finite_is_byte_neutral(self) -> None:
        h = compute_wal_hash(
            {"root_delegate_id": "r", "planned_revocations": [], "reason": "x"}
        )
        assert isinstance(h, str) and len(h) == 64

    # LOW — delegation execution-context state hash (inherited_constraints).
    def test_execution_context_state_hash_rejects_nan_inf(self) -> None:
        ctx = TrustExecutionContext.create(
            parent_agent_id="sup",
            task_id="t1",
            delegated_capabilities=["read"],
            inherited_constraints={"max_cost": float("inf")},
        )
        with pytest.raises(ValueError, match=_MATCH):
            ctx.compute_hash()

    def test_execution_context_state_hash_finite_is_byte_neutral(self) -> None:
        ctx = TrustExecutionContext.create(
            parent_agent_id="sup",
            task_id="t1",
            delegated_capabilities=["read"],
            inherited_constraints={"max_cost": 100.0},
        )
        assert len(ctx.compute_hash()) == 64

    # MED — PACT SqliteAuditLog chain content_hash over free-form details dict.
    def test_pact_sqlite_audit_log_append_rejects_nan_inf(self, tmp_path) -> None:
        from kailash.trust.pact.stores.sqlite import SqliteAuditLog

        store = SqliteAuditLog(str(tmp_path / "audit.db"))
        for bad in _NONFINITE:
            with pytest.raises(ValueError, match=_MATCH):
                store.append("test-action", {"cost": bad})

    def test_pact_sqlite_audit_log_append_finite_is_byte_neutral(
        self, tmp_path
    ) -> None:
        from kailash.trust.pact.stores.sqlite import SqliteAuditLog

        store = SqliteAuditLog(str(tmp_path / "audit.db"))
        store.append("test-action", {"cost": 2.0})  # finite: must not raise


# ---------------------------------------------------------------------------
# Structural invariant — the multi-site contract guard (security.md Multi-Site)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_trust_plane_signing_preimages_all_carry_allow_nan() -> None:
    """AST invariant: EVERY canonical ``json.dumps`` in a sign/hash MODULE across
    the trust plane + PACT carries ``allow_nan=False`` — except documented exclusions.

    This is the durable guard for the trust-plane-wide NaN/Inf multi-site sweep
    (``security.md`` Multi-Site Kwarg Plumbing). It fails loudly if a future
    refactor (a) drops ``allow_nan=False`` from any signing/hash PRE-IMAGE site,
    OR (b) adds a NEW canonical signing/hash ``json.dumps`` without it — the exact
    "missed sibling" failure the sweep closed. STRUCTURAL (AST-shape) probe per
    ``probe-driven-verification.md`` Rule 3, not a source-grep.

    MODULE-granularity (NOT per-function): a pre-image ``json.dumps`` often lives
    in a tiny bytes-producing HELPER (``_serialize_authority_block`` /
    ``_b64url_encode_json`` / ``_json_encode_canonical``) while the ``_ed25519_sign``
    call is in the CALLER — a per-function check false-negatives (the 2026-06-21
    convergence redteam found biscuit/sd_jwt/ucan exactly this way). Gating on the
    MODULE containing any sign/hash token catches the helper-encoder pattern. Only
    CANONICAL calls (``sort_keys`` / ``separators`` — deterministic pre-images) are
    flagged, never ``indent=`` human/file/CLI/dashboard output.

    LIMITATION (honest): a cross-FILE helper that returns a canonical STRING whose
    CALLER (in another file whose own module has no sign/hash token) hashes it is
    NOT caught structurally — that pattern is the semantic ``/redteam`` gate's job
    (it traced ``pact/conformance/vectors.py::canonical_json_dumps`` →
    ``runner.py::_sha256_hex`` and surfaced it; now fixed + guarded here).

    DOCUMENTED EXCLUSIONS (correct by design):
    - ``pact/audit.py::_compute_hash_legacy`` / ``_compute_hash_prefix_format`` —
      deliberately omit ``allow_nan`` to reproduce historical pre-fix bytes for
      forensic re-seal-vs-tamper disambiguation.
    - ``enforce/decorators.py::_hash_args`` / ``_hash_result`` — LOCAL in-process
      memoization cache keys for the ``@verified`` / ``shadow`` decorators; never
      signed, never cross-SDK, never tamper-evidence, and both are guarded by an
      ``except (TypeError, ValueError)`` repr-hash fallback. Not pre-images in the
      cross-SDK/tamper-evidence sense this contract governs.
    """
    import ast
    import pathlib

    repo = pathlib.Path(__file__).resolve().parents[2]
    roots = [
        repo / "src" / "kailash" / "trust",
        repo / "packages" / "kailash-pact" / "src",
    ]

    # MODULE-granularity sign/hash signal — a json.dumps pre-image is often in a
    # tiny bytes-producing HELPER while the _ed25519_sign / sha256 call is in the
    # CALLER, so a per-function check false-negatives (the 2026-06-21 redteam found
    # biscuit/sd_jwt/ucan that way). Gate on the MODULE containing any sign/hash token.
    HASHY = (
        "sha256",
        "sha512",
        "hmac",
        "hexdigest",
        "digest",
        ".sign(",
        "_sign",
        "signing",
        "compare_digest",
        "ed25519",
        "Ed25519",
    )
    # (path-suffix, function-name) deliberately excluded (see docstring):
    #   pact/audit.py legacy/prefix — forensic pre-fix-byte reproduction;
    #   enforce/decorators.py _hash_* — local in-process memoization caches.
    EXCLUDED = {
        ("pact/audit.py", "_compute_hash_legacy"),
        ("pact/audit.py", "_compute_hash_prefix_format"),
        ("enforce/decorators.py", "_hash_args"),
        ("enforce/decorators.py", "_hash_result"),
    }

    def _enclosing_fn(tree: ast.AST, lineno: int) -> str:
        best = None
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                fn.lineno <= lineno <= (fn.end_lineno or fn.lineno)
            ):
                if best is None or fn.lineno > best.lineno:
                    best = fn
        return best.name if best else "<module>"

    offenders: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.rglob("*.py"):
            if "test" in p.parts or p.name.startswith("test_"):
                continue
            txt = p.read_text()
            try:
                tree = ast.parse(txt)
            except SyntaxError:
                continue
            if not any(h in txt for h in HASHY):  # MODULE-granularity gate
                continue
            # Pre-image-by-encode: linenos of ``json.dumps(...).encode(...)`` — a
            # bytes-producing chain feeding a signature/hash even when the dumps is
            # BARE (no sort_keys/separators). The 2026-06-21 redteam found
            # a2a/auth.py signing a bare-json.dumps JWT pre-image exactly this way,
            # which the canonical-shape predicate alone missed.
            encoded_dumps: set[int] = set()
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "encode"
                    and isinstance(node.func.value, ast.Call)
                    and isinstance(node.func.value.func, ast.Attribute)
                    and node.func.value.func.attr == "dumps"
                    and isinstance(node.func.value.func.value, ast.Name)
                    and node.func.value.func.value.id == "json"
                ):
                    encoded_dumps.add(node.func.value.lineno)
            for node in ast.walk(tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "dumps"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "json"
                ):
                    continue
                kws = {k.arg for k in node.keywords}
                # A pre-image is canonical (sort_keys/separators) OR bytes-chained
                # (.encode()). Human/file output (indent=) is never a pre-image.
                is_canonical = "sort_keys" in kws or "separators" in kws
                is_preimage = is_canonical or node.lineno in encoded_dumps
                if "indent" in kws or not is_preimage:
                    continue  # human/file output — not a deterministic pre-image
                if "allow_nan" in kws:
                    continue  # correctly guarded
                idx = p.parts.index("src") if "src" in p.parts else -1
                rel = "/".join(p.parts[idx + 1 :])
                fn_name = _enclosing_fn(tree, node.lineno)
                if any(rel.endswith(ef) and fn_name == efn for ef, efn in EXCLUDED):
                    continue  # documented exclusion
                offenders.append(f"{rel}:{node.lineno} fn={fn_name}")

    assert not offenders, (
        "Canonical signing/hash json.dumps pre-image(s) missing allow_nan=False "
        "(security.md Multi-Site Kwarg Plumbing — cross-SDK NaN/Inf parity hazard):\n  "
        + "\n  ".join(sorted(offenders))
    )


# ---------------------------------------------------------------------------
# Behavioral — interop cross-impl token signing pre-images + cross-SDK serialization
# (the helper-encoder sites the per-function guard missed; found 2026-06-21 redteam)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestInteropCrossSDKSerializationRejectNanInf:
    def test_sd_jwt_b64url_encode_json_rejects_nan_inf(self) -> None:
        from kailash.trust.interop.sd_jwt import _b64url_encode_json

        for bad in _NONFINITE:
            with pytest.raises(ValueError, match=_MATCH):
                _b64url_encode_json({"claim": bad})
        # finite still encodes (byte-neutral)
        assert isinstance(_b64url_encode_json({"claim": 1.5}), str)

    def test_ucan_json_encode_canonical_rejects_nan_inf(self) -> None:
        from kailash.trust.interop.ucan import _json_encode_canonical

        for bad in _NONFINITE:
            with pytest.raises(ValueError, match=_MATCH):
                _json_encode_canonical({"fct": bad})
        assert isinstance(_json_encode_canonical({"fct": 1.5}), bytes)

    def test_pact_conformance_canonical_json_dumps_rejects_nan_inf(self) -> None:
        from pact.conformance.vectors import canonical_json_dumps

        for bad in _NONFINITE:
            with pytest.raises(ValueError, match=_MATCH):
                canonical_json_dumps({"score": bad})
        assert isinstance(canonical_json_dumps({"score": 1.5}), str)

    def test_secure_message_to_json_rejects_nan_inf(self) -> None:
        # cross-SDK wire format — a NaN would emit invalid JSON a Rust receiver rejects
        for bad in _NONFINITE:
            with pytest.raises(ValueError, match=_MATCH):
                _envelope({"amount": bad}).to_json()
        assert isinstance(_envelope({"amount": 1.5}).to_json(), str)

    def test_a2a_encode_token_rejects_nan_inf_constraint(self) -> None:
        # Ed25519-signed A2A JWT pre-image — a non-finite constraint claim must
        # fail closed at the bare json.dumps (before sign()), not emit an
        # RFC-8259-invalid Infinity a cross-SDK verifier rejects on re-parse.
        from datetime import timedelta

        from kailash.trust.a2a.auth import A2AAuthenticator
        from kailash.trust.a2a.models import A2AToken
        from kailash.trust.signing.crypto import generate_keypair

        priv, _pub = generate_keypair()
        # _encode_token does not touch trust_operations; None is safe at runtime.
        auth = A2AAuthenticator(
            trust_operations=None,  # type: ignore[arg-type]
            agent_id="agent-1",
            private_key=priv,
        )
        now = datetime(2026, 1, 15, 11, 0, 0, tzinfo=UTC)

        def _tok(constraints: dict) -> A2AToken:
            return A2AToken(
                sub="a",
                iss="a",
                aud="b",
                exp=now + timedelta(seconds=60),
                iat=now,
                jti="j",
                authority_id="x",
                trust_chain_hash="h",
                capabilities=[],
                constraints=constraints,
            )

        for bad in _NONFINITE:
            with pytest.raises(ValueError, match=_MATCH):
                auth._encode_token(_tok({"max_cost": bad}))
        # finite constraint still signs (byte-neutral)
        assert isinstance(auth._encode_token(_tok({"max_cost": 100.0})), str)
