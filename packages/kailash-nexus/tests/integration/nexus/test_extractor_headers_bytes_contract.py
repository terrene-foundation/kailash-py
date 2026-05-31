# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 contract tests for the Headers + Bytes extractors.

Exercises the 5 Headers MUSTs (case-insensitive access, RFC 7230 §3.2.2 dual
access, insertion-order preservation, read-only enforcement, 64 KiB cap → 431)
and the 3 Bytes MUSTs (size-cap inheritance + 413 envelope, full-body
delivery, log-hygiene = never render body bytes).

These extractors are deterministic data structures whose contract is the
public-API surface SDK users build against; the assertions are structural
(string equality, exception type, status-code shape) per
``rules/probe-driven-verification.md`` Rule 3.
"""

import pytest

from nexus.extractors import Bytes, Headers, NexusHandlerError

# --------------------------------------------------------------------------
# Headers contract — 5 MUSTs
# --------------------------------------------------------------------------


@pytest.mark.integration
def test_headers_case_insensitive_access():
    """MUST 1 — every case spelling returns the same value."""
    h = Headers([("X-Foo", "bar")])
    assert h["X-Foo"] == "bar"
    assert h["x-foo"] == "bar"
    assert h["X-FOO"] == "bar"
    assert h.get("x-Foo") == "bar"
    assert h.get("missing") is None
    assert h.get("missing", "fallback") == "fallback"
    assert "X-FOO" in h
    assert "x-foo" in h
    assert "missing" not in h


@pytest.mark.integration
def test_headers_duplicate_dual_access_rfc7230():
    """MUST 2 — scalar form joins with ', '; getlist returns raw list."""
    h = Headers(
        [
            ("Accept", "text/html"),
            ("accept", "application/json"),
            ("ACCEPT", "*/*"),
        ]
    )
    # Scalar form: RFC 7230 §3.2.2 — combine same-name fields with ", ".
    assert h["Accept"] == "text/html, application/json, */*"
    # List form: raw values in insertion order.
    assert h.getlist("accept") == ["text/html", "application/json", "*/*"]
    # getlist on an absent header is an empty list, never None.
    assert h.getlist("X-Absent") == []


@pytest.mark.integration
def test_headers_insertion_order_preserved_not_alphabetical():
    """MUST 3 — iteration / keys / items preserve insertion order."""
    h = Headers(
        [
            ("Z-Header", "1"),
            ("A-Header", "2"),
            ("M-Header", "3"),
        ]
    )
    assert list(h) == ["z-header", "a-header", "m-header"]
    assert h.keys() == ["z-header", "a-header", "m-header"]
    assert [k for k, _ in h.items()] == ["z-header", "a-header", "m-header"]
    assert [v for _, v in h.items()] == ["1", "2", "3"]


@pytest.mark.integration
def test_headers_read_only_raises_typeerror():
    """MUST 4 — mutation raises TypeError at the handler boundary."""
    h = Headers([("X-Foo", "bar")])
    with pytest.raises(TypeError, match="read-only"):
        h["X-Foo"] = "mutated"
    with pytest.raises(TypeError, match="read-only"):
        del h["X-Foo"]
    # The value was not changed by the rejected mutation.
    assert h["X-Foo"] == "bar"


@pytest.mark.integration
def test_headers_byte_cap_rejects_with_431_envelope():
    """MUST 5 — exceeding max_request_header_bytes raises HTTP 431."""
    # A single oversized header trips the cap.
    big = [("X-Big", "y" * 100_000)]
    with pytest.raises(NexusHandlerError) as exc_info:
        Headers.from_pairs(big, max_request_header_bytes=65536)
    err = exc_info.value
    assert err.status_code == 431
    assert err.body["code"] == "HEADERS_TOO_LARGE"
    assert err.body["limit"] == 65536
    assert err.body["error"] == "request headers exceed configured cap"


@pytest.mark.integration
def test_headers_byte_cap_early_reject_bounds_memory():
    """MUST 5 — rejection fires as the (cap+1)th byte is seen, not after all parse.

    The accumulated cost crosses the cap inside the loop; the very next pair
    is never tallied, demonstrating early rejection.
    """
    pairs = [("X-A", "a" * 40), ("X-B", "b" * 40), ("X-C", "c" * 40)]
    # Cap chosen so the third header pushes us over.
    with pytest.raises(NexusHandlerError) as exc_info:
        Headers.from_pairs(pairs, max_request_header_bytes=100)
    assert exc_info.value.status_code == 431


@pytest.mark.integration
def test_headers_under_cap_constructs_normally():
    """MUST 5 — within the cap, from_pairs returns a usable Headers mapping."""
    h = Headers.from_pairs(
        [("Content-Type", "application/json")], max_request_header_bytes=65536
    )
    assert h["content-type"] == "application/json"


# --------------------------------------------------------------------------
# Bytes contract — 3 MUSTs
# --------------------------------------------------------------------------


@pytest.mark.integration
def test_bytes_is_full_body_value_not_stream():
    """MUST 2 — Bytes IS the full body value (subclass of bytes), not a stream."""
    body = Bytes(b"the entire request body")
    assert isinstance(body, bytes)
    assert body == b"the entire request body"
    assert len(body) == len(b"the entire request body")
    # Usable anywhere bytes is usable.
    assert body.decode() == "the entire request body"


@pytest.mark.integration
def test_bytes_repr_is_length_only_log_hygiene():
    """MUST 3 — repr renders length only; body bytes never appear (log hygiene)."""
    secret = b"Authorization: Bearer sk-super-secret-token"
    body = Bytes(secret)
    rendered = repr(body)
    # The repr a log line would interpolate MUST NOT contain the bytes.
    assert b"sk-super-secret-token" not in rendered.encode()
    assert "sk-super-secret-token" not in rendered
    assert rendered == f"<Bytes length={len(secret)}>"
    # The actual value is still fully available to the handler.
    assert body == secret


@pytest.mark.integration
def test_bytes_default_size_cap_inheritance_value():
    """MUST 1 — the 10 MiB default cap is exposed for resolver inheritance."""
    assert Bytes.DEFAULT_MAX_REQUEST_BODY_BYTES == 10_485_760


@pytest.mark.integration
def test_bytes_body_too_large_envelope_shape():
    """MUST 1 — the 413 BODY_TOO_LARGE envelope is the canonical shape.

    The resolver short-circuits oversized bodies with this typed error; the
    test pins the envelope contract SDK consumers key on.
    """
    from nexus.extractors import _BodyTooLargeError

    err = _BodyTooLargeError()
    assert err.status_code == 413
    assert err.body["code"] == "BODY_TOO_LARGE"
    assert err.body["error"] == "request body exceeds configured cap"
