# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 path-traversal regression for the Multipart resolver (AC 4, spec §79).

Drives the REAL resolver chain against a REAL Starlette ``Request`` carrying a
real ``multipart/form-data`` body whose part declares an UNTRUSTED filename
``../../../etc/passwd``. NO MOCKING of the parser or sniffer — Starlette's
``MultiPartParser`` (real ``python-multipart``) produces a real spooled
``UploadFile`` and the resolver runs its production sanitization.

Per spec §74 the resolver MUST sanitize the filename to its basename BEFORE any
handler body sees it; per spec §79 it MUST NOT invoke any filesystem ``open()``
against the unsanitized value (subprocess-level audit). This test:

1. Asserts the handler sees ``filename == "passwd"`` (sanitized; no ``..`` /
   ``/`` survive).
2. Installs an ``open`` / ``os.open`` audit shim across the resolve+call and
   asserts NO open() call referenced the unsanitized traversal payload nor the
   real ``/etc/passwd`` target the payload was trying to reach.

(Scope note: the Core SDK gateway's ``/workflows/<name>/execute`` route binds a
JSON body model, so a raw multipart POST is rejected with 422 before the
resolver runs — see the wiring-test module docstring. The resolver contract is
the authoritative AC-4 deliverable and is exercised directly here.)
"""

import asyncio
import builtins
import os

import pytest

from nexus.context import _current_request, set_current_request
from nexus.extractors import UploadFile
from nexus.extractors.resolver import build_resolver_chain

_TRAVERSAL = "../../../etc/passwd"
_MULTIPART_BOUNDARY = b"----nexus-traversal-test-boundary"


def _build_multipart_request(filename: str, data: bytes, content_type: str):
    """Build a REAL Starlette multipart Request with one file part."""
    from starlette.requests import Request

    body = b"".join(
        [
            b"--" + _MULTIPART_BOUNDARY + b"\r\n",
            (
                'Content-Disposition: form-data; name="f"; filename="%s"\r\n' % filename
            ).encode(),
            ("Content-Type: %s\r\n\r\n" % content_type).encode(),
            data + b"\r\n",
            b"--" + _MULTIPART_BOUNDARY + b"--\r\n",
        ]
    )
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
    request._nexus_max_request_body_bytes = 10_485_760
    request._nexus_max_upload_file_bytes = 10_485_760
    request._nexus_max_multipart_files = 100
    request._nexus_mime_sniffer = None
    return request


@pytest.mark.integration
def test_multipart_filename_traversal_is_sanitized(monkeypatch):
    """filename="../../../etc/passwd" → handler sees "passwd"; no traversal open()."""

    async def upload(f: UploadFile) -> dict:
        data = await f.read()
        return {"name": f.filename, "body": data.decode()}

    req = _build_multipart_request(_TRAVERSAL, b"not-the-real-passwd", "text/plain")

    # Audit shim: record every open() / os.open() path. Starlette spools the
    # UploadFile to a SpooledTemporaryFile (no path-based open on the client
    # filename), so any open() referencing the traversal payload would be a
    # sanitization bypass.
    opened_paths = []
    real_open = builtins.open
    real_os_open = os.open

    def audit_open(file, *args, **kwargs):
        try:
            opened_paths.append(str(file))
        except Exception:
            pass
        return real_open(file, *args, **kwargs)

    def audit_os_open(path, *args, **kwargs):
        try:
            opened_paths.append(str(path))
        except Exception:
            pass
        return real_os_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", audit_open)
    monkeypatch.setattr(os, "open", audit_os_open)

    chain = build_resolver_chain(upload)
    token = set_current_request(req)
    try:
        out = asyncio.run(chain.resolve_and_call({}))
    finally:
        _current_request.reset(token)

    # (1) The handler sees the sanitized basename — NOT the traversal payload.
    assert out["name"] == "passwd", out
    assert ".." not in out["name"], out
    assert "/" not in out["name"], out
    # The file bytes still round-trip through the sanitized handle.
    assert out["body"] == "not-the-real-passwd", out

    # (2) No filesystem open() referenced the unsanitized traversal value, nor
    # the real /etc/passwd target the payload was trying to reach.
    for path in opened_paths:
        assert "etc/passwd" not in path, f"resolver opened traversal target: {path}"
        assert _TRAVERSAL not in path, f"resolver opened raw payload: {path}"


@pytest.mark.integration
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("../../../etc/passwd", "passwd"),
        ("/abs/leading/slash.txt", "slash.txt"),
        ("..\\..\\windows\\system32\\cmd.exe", "cmd.exe"),
        ("....//....//evil", "evil"),
        ("../", "upload"),
        ("/", "upload"),
        ("", "upload"),
    ],
)
def test_filename_sanitization_matrix(raw, expected):
    """A matrix of traversal payloads all collapse to a safe basename."""

    async def upload(f: UploadFile) -> dict:
        return {"name": f.filename}

    req = _build_multipart_request(raw, b"payload-bytes", "text/plain")
    chain = build_resolver_chain(upload)
    token = set_current_request(req)
    try:
        out = asyncio.run(chain.resolve_and_call({}))
    finally:
        _current_request.reset(token)
    assert out["name"] == expected, (raw, out)
    assert ".." not in out["name"]
    assert "/" not in out["name"]
    assert "\\" not in out["name"]
