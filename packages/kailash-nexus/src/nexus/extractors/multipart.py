# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Multipart / UploadFile transport binding + input-validation (issue #1174 AC 4).

A handler signature ``async def upload(files: Multipart)`` or
``async def one(f: UploadFile)`` triggers the resolver to parse the originating
request's multipart form (via Starlette's ``request.form()`` MultiPartParser)
and bind the parsed file(s) to the handler parameter. Before any handler body
sees an ``UploadFile``, the resolver MUST enforce the six input-validation
MUSTs from ``specs/nexus-fastapi-parity.md`` §66-77:

1. **Total-body cap** — ``Nexus(max_request_body_bytes=...)`` (10 MiB default);
   exceed → HTTP 413 ``BODY_TOO_LARGE``.
2. **Per-file size cap** — ``Nexus(max_upload_file_bytes=...)`` (10 MiB default);
   the FIRST file over cap rejects the WHOLE request → HTTP 413 (no partial).
3. **Filename sanitization** — the client ``filename`` is UNTRUSTED; sanitized
   via ``pathlib.PurePosixPath(name).name`` (strips ``../``, leading ``/``,
   ``\\``, reserved dirs). The raw value is DROPPED at the resolver boundary.
4. **MIME derivation** — ``content_type`` is sniffed from the first 4 KiB of the
   body (``puremagic.from_string``), NOT trusted from the client header. The
   client header is captured as ``client_declared_content_type`` for audit.
   ``Nexus(mime_sniffer=callable)`` overrides the default; if ``puremagic``
   import fails AND no override, degrade to the client-declared value + WARN.
5. **Tempfile lifecycle** — Starlette spools each upload to disk above the spool
   threshold; cleanup (``await upload.close()``) MUST fire in BOTH the success
   AND exception branches — no spooled-tempfile leak.
6. **File-count cap** — ``Nexus(max_multipart_files=...)`` (100 default);
   exceed → HTTP 413 ``TOO_MANY_FILES`` with the configured ``limit``. Rejection
   fires as soon as the (cap+1)th file is observed (early — bounds memory).

The resolver dispatches a ``Multipart`` annotation to ``list[UploadFile]`` and an
``UploadFile`` annotation to a single ``UploadFile`` (or ``None`` when no file
part is present). Both routes share :func:`parse_multipart_uploads`, which owns
the validation contract; the resolver owns only the list-vs-single shaping +
the ``finally`` cleanup.
"""

import logging
from pathlib import PurePosixPath
from typing import Callable, List, Optional, Tuple

from starlette.datastructures import UploadFile
from starlette.requests import Request

from nexus.extractors import NexusHandlerError
from nexus.extractors import UploadFile as _ExportedUploadFile

logger = logging.getLogger(__name__)

__all__ = [
    "parse_multipart_uploads",
    "sanitize_upload_filename",
    "derive_content_type",
    "TooManyFilesError",
    "UploadFileTooLargeError",
    "DEFAULT_MAX_UPLOAD_FILE_BYTES",
    "DEFAULT_MAX_MULTIPART_FILES",
    "MIME_SNIFF_BYTES",
]

# Re-export-consistency guard: the Multipart alias resolves to the SAME
# UploadFile the public extractor surface exports, so a handler-declared
# ``list[UploadFile]`` and the parsed value share one type.
assert UploadFile is _ExportedUploadFile  # noqa: S101 — module-load invariant

# Default per-file cap (10 MiB) — see spec §73 (LOW-1). The 10/10 pairing with
# the total-body cap is canonical: a per-file cap above the body cap is
# meaningless (body cap fires first); below it tightens multi-file uploads on
# the smaller axis.
DEFAULT_MAX_UPLOAD_FILE_BYTES = 10_485_760
# Default file-count cap (100) — see spec §77 (MED-3 / MED-S2).
DEFAULT_MAX_MULTIPART_FILES = 100
# Content-sniff window: the first 4 KiB of each file body (spec §75 LOW-2).
MIME_SNIFF_BYTES = 4096


class TooManyFilesError(NexusHandlerError):
    """Internal — raised when a multipart submission exceeds the file-count cap.

    Surfaces as HTTP 413 + the canonical ``TOO_MANY_FILES`` envelope carrying
    the configured ``limit`` (spec §77). Rejection fires as soon as the parser
    observes the (cap+1)th file — early, to bound memory when a malicious client
    batches thousands of files.
    """

    def __init__(self, limit: int) -> None:
        super().__init__(
            status_code=413,
            body={
                "error": "multipart request exceeds configured file-count cap",
                "code": "TOO_MANY_FILES",
                "limit": limit,
            },
        )


class UploadFileTooLargeError(NexusHandlerError):
    """Internal — raised when an individual file exceeds the per-file size cap.

    Surfaces as HTTP 413 + the canonical ``BODY_TOO_LARGE`` envelope. The FIRST
    over-cap file rejects the WHOLE request (no partial acceptance — spec §73).
    The error body does NOT echo the offending filename (which is
    attacker-controlled) — only the canonical shape + code.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=413,
            body={
                "error": "uploaded file exceeds configured per-file cap",
                "code": "BODY_TOO_LARGE",
            },
        )


def sanitize_upload_filename(raw: Optional[str]) -> str:
    """Sanitize an UNTRUSTED client-supplied multipart filename (spec §74).

    The client ``filename`` is attacker-controlled bytes. Path-traversal
    sequences (``../../../etc/passwd``), leading ``/``, Windows-style ``\\``
    separators, and reserved directory references MUST be stripped before any
    filesystem use. ``PurePosixPath(name).name`` is the structural defense: it
    parses the value as a POSIX path and returns ONLY the final component.

    Windows separators are normalized to ``/`` first so a payload like
    ``..\\..\\windows\\system32`` collapses to ``system32`` rather than being
    treated as a single opaque component on a POSIX parser.

    Returns the sanitized basename, or ``"upload"`` when the result is empty
    (a payload that sanitizes to nothing — e.g. ``"../"`` or ``"/"`` — MUST NOT
    yield an empty filename a downstream consumer might mishandle).
    """
    if not raw:
        return "upload"
    # Strip NUL bytes FIRST — a NUL in a filename truncates at the C / syscall
    # layer (``open("foo\\x00.txt")`` → ``foo``), a known path-injection vector,
    # and is never a legitimate filename character.
    # Normalize Windows separators so a POSIX path parser sees the real
    # component boundaries (``..\\..\\system32`` → ``../../system32``).
    normalized = raw.replace("\x00", "").replace("\\", "/")
    # PurePosixPath(...).name strips every directory component AND traversal
    # token, returning only the final path element.
    name = PurePosixPath(normalized).name
    # Reject empty / dot / traversal-token results, AND any result that still
    # LEADS with ``..``. A basename beginning with ``..`` is never a legitimate
    # upload name and is the residue of an encoded-separator payload — e.g.
    # ``..%2f..%2fetc`` carries no real ``/`` for PurePosixPath to split, so its
    # ``.name`` is the whole string, but it would traverse if a downstream
    # consumer URL-decoded it. (Legitimate single-dot names like ``.gitignore``
    # do NOT start with ``..`` and are preserved.) Defence-in-depth: the
    # contract is "no real path separators"; callers MUST treat the result as an
    # opaque single filename and never re-decode it before filesystem use.
    if not name or name in (".", "..") or name.startswith(".."):
        return "upload"
    return name


def _default_sniff(head: bytes) -> Optional[str]:
    """Default MIME sniffer — content-sniff via puremagic (pure-Python).

    Returns the sniffed MIME type, or ``None`` when puremagic cannot import
    (degrade path — the caller falls back to the client-declared value + WARN)
    or cannot identify the content. Never raises: a sniff failure MUST NOT take
    down the request, only fall back.
    """
    try:
        import puremagic
    except ImportError:
        logger.warning(
            "multipart.mime_sniff.puremagic_unavailable",
            extra={
                "detail": "puremagic import failed; falling back to "
                "client-declared content_type (degraded — install "
                "puremagic or pass Nexus(mime_sniffer=...))"
            },
        )
        return None
    if not head:
        return None
    try:
        # from_string returns the most-likely MIME type for the byte prefix;
        # it raises puremagic.PureError (an Exception subclass) when it cannot
        # identify the content — a non-fatal "no match", degrade to None.
        guessed = puremagic.from_string(head, mime=True)
    except Exception:
        return None
    return guessed or None


def derive_content_type(
    head: bytes,
    client_declared: Optional[str],
    sniffer: Optional[Callable[[bytes], str]],
) -> str:
    """Derive the handler-visible ``content_type`` from a content-sniff (spec §75).

    The client-declared ``Content-Type`` header is attacker-controllable and
    MUST NOT be the value handlers see. The MIME is sniffed from the first 4 KiB
    of the body:

    - ``sniffer`` (the operator ``Nexus(mime_sniffer=...)`` override) is used
      when present — caller-responsible-for-security per spec §75.
    - else the default puremagic content-sniff runs.

    When BOTH the override (if any) and the default sniff cannot identify the
    content (or puremagic is unavailable), the resolver degrades to the
    client-declared value (documented WARN already emitted by ``_default_sniff``
    on the import-failure path). A final fallback of
    ``"application/octet-stream"`` ensures a non-empty value.
    """
    sniffed: Optional[str] = None
    if sniffer is not None:
        try:
            sniffed = sniffer(head[:MIME_SNIFF_BYTES])
        except Exception:
            # An operator-supplied sniffer that raises MUST NOT take down the
            # request; fall back to the default path. (The override is
            # caller-responsible-for-security but a crash is degrade-not-fail.)
            logger.warning(
                "multipart.mime_sniff.override_raised",
                extra={"detail": "operator mime_sniffer raised; using default"},
            )
            sniffed = None
    if not sniffed:
        sniffed = _default_sniff(head[:MIME_SNIFF_BYTES])
    if sniffed:
        return sniffed
    # Degrade: no sniff result — use the client-declared value if present.
    if client_declared:
        return client_declared
    return "application/octet-stream"


def _rewrap_validated(
    original: UploadFile,
    *,
    sanitized_filename: str,
    sniffed_content_type: str,
) -> UploadFile:
    """Produce the handler-visible UploadFile with sanitized/sniffed metadata.

    Starlette's ``UploadFile.filename`` is a plain mutable attribute, but
    ``.content_type`` is a READ-ONLY property derived from ``.headers``. Per
    spec §74 the RAW client filename is dropped (NOT preserved as a sibling
    attribute); per spec §75 the SNIFFED content_type replaces the client
    header, and the client header is captured as
    ``client_declared_content_type`` for audit.

    We mutate the SAME UploadFile object (preserving its spooled file handle +
    ``read()``/``seek()``/``close()`` semantics so the handler reads the
    original bytes) — overwriting ``.filename`` directly and rebuilding
    ``.headers`` so the ``.content_type`` property returns the sniffed value.
    """
    from starlette.datastructures import Headers as _StarletteHeaders

    # Capture the client-declared header BEFORE overwriting (audit, spec §75).
    original.client_declared_content_type = original.content_type
    original.filename = sanitized_filename
    # content_type is a property reading from .headers — rebuild headers with the
    # sniffed value so handlers see the derived type, never the client header.
    original.headers = _StarletteHeaders({"content-type": sniffed_content_type})
    return original


async def parse_multipart_uploads(
    request: Optional[Request],
) -> Tuple[List[UploadFile], List[UploadFile]]:
    """Parse + validate the multipart form, returning (validated, to_close).

    Returns a tuple ``(uploads, parsed_files)``:

    - ``uploads`` — the validated, metadata-rewritten ``UploadFile`` objects the
      handler sees (sanitized filename + sniffed content_type).
    - ``parsed_files`` — EVERY ``UploadFile`` the parser produced (so the
      resolver's ``finally`` can close ALL of them, even on a validation raise
      mid-list — spec §76 tempfile lifecycle).

    The six input-validation MUSTs (spec §66-77) are enforced here:

    1. Total-body cap (Content-Length pre-check → 413 BODY_TOO_LARGE).
    2. Per-file size cap (first over-cap file → 413 BODY_TOO_LARGE, no partial).
    3. Filename sanitization (PurePosixPath basename).
    4. MIME derivation (content-sniff; client header captured for audit).
    6. File-count cap (Starlette ``max_files`` → 413 TOO_MANY_FILES).

    (5) Tempfile cleanup is the resolver's ``finally`` responsibility using the
    returned ``parsed_files`` list. Raises a ``NexusHandlerError`` subclass on
    any cap violation; the resolver re-raises it as the typed HTTP status.
    """
    from starlette.formparsers import MultiPartException

    from nexus.extractors import _BodyTooLargeError

    if request is None:
        return ([], [])

    body_cap = getattr(request, "_nexus_max_request_body_bytes", None)
    if body_cap is None:
        from nexus.extractors import Bytes

        body_cap = Bytes.DEFAULT_MAX_REQUEST_BODY_BYTES
    file_cap = getattr(request, "_nexus_max_upload_file_bytes", None)
    if file_cap is None:
        file_cap = DEFAULT_MAX_UPLOAD_FILE_BYTES
    count_cap = getattr(request, "_nexus_max_multipart_files", None)
    if count_cap is None:
        count_cap = DEFAULT_MAX_MULTIPART_FILES
    sniffer = getattr(request, "_nexus_mime_sniffer", None)

    # (1) Total-body cap — short-circuit on the declared Content-Length BEFORE
    # parsing so an oversized body is rejected without buffering it.
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = None
        if declared is not None and declared > body_cap:
            raise _BodyTooLargeError()

    # (6) File-count cap — Starlette's MultiPartParser raises MultiPartException
    # as soon as the (max_files+1)th file part is observed (early rejection,
    # bounds memory). We map that to the typed TOO_MANY_FILES envelope.
    parsed_files: List[UploadFile] = []
    try:
        form = await request.form(max_files=count_cap)
    except MultiPartException as exc:
        # Distinguish the file-count overflow from other malformed-multipart
        # errors. Starlette's message for the count cap mentions "Too many
        # files"; any other MultiPartException is a malformed request → 400.
        if "too many files" in str(exc).lower():
            raise TooManyFilesError(limit=count_cap) from exc
        raise NexusHandlerError(
            status_code=400,
            body={"error": "malformed multipart request", "code": "INVALID_INPUT"},
        ) from exc

    uploads: List[UploadFile] = []
    try:
        # Collect every UploadFile part (form may also carry plain string
        # fields; we bind only the file parts to the Multipart/UploadFile param).
        for _field, value in form.multi_items():
            if isinstance(value, UploadFile):
                parsed_files.append(value)

        for upload in parsed_files:
            # (2) Per-file size cap — Starlette populates UploadFile.size; the
            # FIRST over-cap file rejects the WHOLE request (no partial).
            size = upload.size if upload.size is not None else 0
            if size > file_cap:
                raise UploadFileTooLargeError()

            # (4) MIME derivation — sniff the first 4 KiB, then rewind so the
            # handler reads from the start. The client header is captured for
            # audit inside _rewrap_validated.
            head = await upload.read(MIME_SNIFF_BYTES)
            await upload.seek(0)
            sniffed = derive_content_type(head, upload.content_type, sniffer)

            # (3) Filename sanitization — drop the raw client value.
            sanitized = sanitize_upload_filename(upload.filename)

            uploads.append(
                _rewrap_validated(
                    upload,
                    sanitized_filename=sanitized,
                    sniffed_content_type=sniffed,
                )
            )
    except BaseException:
        # On ANY failure mid-parse, close every file already parsed so a
        # validation raise does not leak spooled tempfiles (spec §76). The
        # resolver's finally also closes, but closing here too is idempotent
        # (Starlette's UploadFile.close is safe to call twice) and guarantees
        # cleanup even if the resolver's finally path changes.
        for f in parsed_files:
            try:
                await f.close()
            except Exception:  # cleanup best-effort — never mask the original
                pass
        raise

    return (uploads, parsed_files)
