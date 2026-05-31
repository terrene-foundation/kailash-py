# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring tests for the Multipart / UploadFile extractors (AC 4).

Drives the REAL resolver chain (``build_resolver_chain`` + ``resolve_and_call``)
against a REAL Starlette ``Request`` carrying a REAL ``multipart/form-data``
body. The body is parsed by Starlette's ``MultiPartParser`` (backed by the real
``python-multipart`` dependency) into real spooled ``UploadFile`` objects, and
the MIME content-sniff runs through the real ``puremagic`` dependency. NO
MOCKING — every primitive is the production code path.

Scope note (transport boundary): the Core SDK gateway's ``/workflows/<name>/
execute`` route binds a JSON ``WorkflowRequest`` body model, so a raw
``multipart/form-data`` POST to that route is rejected with HTTP 422 BEFORE the
resolver runs (FastAPI parses the body model first). Wiring a non-JSON
multipart-capable HTTP route into the Core SDK gateway is a gateway-layer
concern OUT OF this shard's scope — the same boundary Shard 1 documented for the
``Bytes`` extractor (its HTTP-transport tests drive ``_bytes_from_request``
directly for the same reason). These tests therefore exercise the resolver
contract directly against a real multipart request — the authoritative AC-4
deliverable (transport binding + the six input-validation MUSTs, spec §66-77).

Covers spec §66-77 (issue #1174 AC 4):
- ``Multipart`` binds list[UploadFile] of length 3; each ``read()`` returns the
  original bytes (transport binding MUST).
- Single ``UploadFile`` variant binds the first parsed file.
- Per-file size cap → 413 ``BODY_TOO_LARGE`` (no partial acceptance).
- File-count cap → 413 ``TOO_MANY_FILES`` carrying the configured limit.
- Total-body cap → 413 ``BODY_TOO_LARGE`` (Content-Length short-circuit).
- MIME content-sniff: handler sees ``content_type`` derived from the BODY, NOT
  the (lying) client header; the client header is captured as
  ``client_declared_content_type``. Operator ``mime_sniffer`` override wins.
"""

import asyncio

import pytest

from nexus.context import _current_request, set_current_request
from nexus.extractors import Multipart, NexusHandlerError, UploadFile
from nexus.extractors.resolver import build_resolver_chain

_MULTIPART_BOUNDARY = b"----nexus-multipart-test-boundary"
# A real 8-byte PNG signature so the content-sniff resolves to image/png.
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _build_multipart_request(
    parts,
    *,
    max_request_body_bytes: int = 10_485_760,
    max_upload_file_bytes: int = 10_485_760,
    max_multipart_files: int = 100,
    mime_sniffer=None,
):
    """Build a REAL Starlette Request carrying a real multipart/form-data body.

    ``parts`` is a list of ``(field_name, filename, data_bytes, content_type)``.
    The returned request carries the same ``_nexus_*`` cap stamps the
    ``RequestCaptureMiddleware`` applies in production, so the resolver enforces
    the configured caps exactly as it would on a live HTTP request.
    """
    from starlette.requests import Request

    chunks = []
    for field, filename, data, ctype in parts:
        chunks.append(b"--" + _MULTIPART_BOUNDARY + b"\r\n")
        chunks.append(
            (
                'Content-Disposition: form-data; name="%s"; filename="%s"\r\n'
                % (field, filename)
            ).encode()
        )
        chunks.append(("Content-Type: %s\r\n\r\n" % ctype).encode())
        chunks.append(data + b"\r\n")
    chunks.append(b"--" + _MULTIPART_BOUNDARY + b"--\r\n")
    body = b"".join(chunks)

    headers = [
        (b"content-type", b"multipart/form-data; boundary=" + _MULTIPART_BOUNDARY),
        (b"content-length", str(len(body)).encode()),
    ]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": headers,
        "query_string": b"",
    }
    state = {"sent": False}

    async def receive():
        if state["sent"]:
            return {"type": "http.disconnect"}
        state["sent"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(scope, receive=receive)
    # Stamp the caps exactly as RequestCaptureMiddleware does in production.
    request._nexus_max_request_body_bytes = max_request_body_bytes
    request._nexus_max_upload_file_bytes = max_upload_file_bytes
    request._nexus_max_multipart_files = max_multipart_files
    request._nexus_mime_sniffer = mime_sniffer
    return request


def _run_resolver(handler, request):
    """Resolve + call ``handler`` with ``request`` bound to the resolver ContextVar."""
    chain = build_resolver_chain(handler)
    token = set_current_request(request)
    try:
        return asyncio.run(chain.resolve_and_call({}))
    finally:
        _current_request.reset(token)


@pytest.mark.integration
def test_multipart_binds_three_files_with_original_bytes():
    """A Multipart param binds list[UploadFile] of length 3; bytes round-trip."""

    async def upload(files: Multipart) -> dict:
        out = []
        for f in files:
            data = await f.read()
            out.append({"name": f.filename, "body": data.decode()})
        return {"count": len(files), "files": out}

    req = _build_multipart_request(
        [
            ("files", "a.txt", b"alpha", "text/plain"),
            ("files", "b.txt", b"bravo", "text/plain"),
            ("files", "c.txt", b"charlie", "text/plain"),
        ]
    )
    out = _run_resolver(upload, req)

    assert out["count"] == 3, out
    bodies = {f["name"]: f["body"] for f in out["files"]}
    assert bodies == {"a.txt": "alpha", "b.txt": "bravo", "c.txt": "charlie"}, bodies


@pytest.mark.integration
def test_single_uploadfile_binds_first_file():
    """A single UploadFile param binds the (first) parsed file; bytes round-trip."""

    async def one(f: UploadFile) -> dict:
        data = await f.read()
        return {"name": f.filename, "body": data.decode()}

    req = _build_multipart_request([("f", "solo.txt", b"the-only-bytes", "text/plain")])
    out = _run_resolver(one, req)
    assert out == {"name": "solo.txt", "body": "the-only-bytes"}, out


@pytest.mark.integration
def test_single_uploadfile_none_when_no_file_part():
    """A single UploadFile param binds None when the form has no file part."""

    async def one(f: UploadFile) -> dict:
        return {"is_none": f is None}

    # An empty multipart body (no parts) → no UploadFile to bind.
    req = _build_multipart_request([])
    out = _run_resolver(one, req)
    assert out == {"is_none": True}, out


@pytest.mark.integration
def test_per_file_cap_rejects_whole_request_413():
    """A file over the per-file cap rejects the WHOLE request with 413 (no partial)."""

    handler_ran = {"value": False}

    async def upload(files: Multipart) -> dict:
        handler_ran["value"] = True
        return {"count": len(files)}

    req = _build_multipart_request(
        [
            ("files", "small.txt", b"tiny", "text/plain"),
            ("files", "big.txt", b"X" * 64, "text/plain"),  # > 16-byte cap
        ],
        max_upload_file_bytes=16,
    )
    with pytest.raises(NexusHandlerError) as exc_info:
        _run_resolver(upload, req)

    assert exc_info.value.status_code == 413
    assert exc_info.value.body["code"] == "BODY_TOO_LARGE", exc_info.value.body
    # No-partial: the handler MUST NOT have run.
    assert handler_ran["value"] is False
    # The error body MUST NOT echo the attacker-controlled filename.
    assert "big.txt" not in str(exc_info.value.body)


@pytest.mark.integration
def test_file_count_cap_rejects_413_too_many_files_with_limit():
    """Exceeding max_multipart_files → 413 TOO_MANY_FILES carrying the limit."""

    async def upload(files: Multipart) -> dict:
        return {"count": len(files)}

    req = _build_multipart_request(
        [
            ("files", "a.txt", b"a", "text/plain"),
            ("files", "b.txt", b"b", "text/plain"),
            ("files", "c.txt", b"c", "text/plain"),  # the 3rd exceeds cap=2
        ],
        max_multipart_files=2,
    )
    with pytest.raises(NexusHandlerError) as exc_info:
        _run_resolver(upload, req)

    assert exc_info.value.status_code == 413
    assert exc_info.value.body["code"] == "TOO_MANY_FILES", exc_info.value.body
    assert exc_info.value.body["limit"] == 2, exc_info.value.body


@pytest.mark.integration
def test_total_body_cap_short_circuits_413_before_parse():
    """Content-Length over the total-body cap → 413 BODY_TOO_LARGE pre-parse."""

    async def upload(files: Multipart) -> dict:
        return {"count": len(files)}

    req = _build_multipart_request(
        [("files", "big.txt", b"X" * 256, "text/plain")],
        max_request_body_bytes=16,  # tiny total-body cap
    )
    with pytest.raises(NexusHandlerError) as exc_info:
        _run_resolver(upload, req)

    assert exc_info.value.status_code == 413
    assert exc_info.value.body["code"] == "BODY_TOO_LARGE", exc_info.value.body


@pytest.mark.integration
def test_content_type_sniffed_from_body_not_client_header():
    """content_type is derived from the BODY (image/png), NOT the lying header."""

    async def upload(f: UploadFile) -> dict:
        return {
            "content_type": f.content_type,
            "client_declared": getattr(f, "client_declared_content_type", None),
        }

    png_body = _PNG_MAGIC + b"\x00" * 64
    # The client LIES: declares text/plain for a PNG body.
    req = _build_multipart_request([("f", "image.bin", png_body, "text/plain")])
    out = _run_resolver(upload, req)

    # Sniffed from the PNG magic bytes — NOT the client's "text/plain" lie.
    assert out["content_type"] == "image/png", out
    # The client-declared header is preserved for audit, distinct from the sniff.
    assert out["client_declared"] == "text/plain", out


@pytest.mark.integration
def test_operator_mime_sniffer_override_used():
    """Nexus(mime_sniffer=...) override takes precedence over the default sniff."""

    def fixed_sniffer(head: bytes) -> str:
        return "application/x-operator-decided"

    async def upload(f: UploadFile) -> dict:
        return {"content_type": f.content_type}

    png_body = _PNG_MAGIC + b"\x00" * 64
    req = _build_multipart_request(
        [("f", "image.bin", png_body, "text/plain")],
        mime_sniffer=fixed_sniffer,
    )
    out = _run_resolver(upload, req)
    assert out["content_type"] == "application/x-operator-decided", out
