# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Nexus handler extractor surface.

This module exposes the extractor primitives that ``Nexus.handler_extract``
inspects to build a per-handler resolver chain. SDK users coming from other
Python web ecosystems recognise the surface names (``Depends``, ``Request``,
``UploadFile``, ``Multipart``); the semantics, transport, dispatch, and the
resolver chain are Nexus-native.

Surface (Shard 1 scope):

- ``Depends`` — dependency-injection marker. ``x = Depends(callable)`` stores
  the callable; the resolver invokes it once per request (memoised), and the
  callable may itself take extractors (recursive resolution).
- ``Request`` — re-export of ``starlette.requests.Request``; the resolver
  binds the originating HTTP request. Untrusted proxy headers
  (``X-Forwarded-For`` / ``X-Forwarded-Proto`` / ``X-Real-IP`` / RFC 7239
  ``Forwarded``) are NOT trusted by default (see ``nexus/extractors/proxy.py``).
- ``UploadFile`` — re-export of ``starlette.datastructures.UploadFile``
  (single-file upload extractor; transport wiring is a follow-up shard).
- ``Multipart`` — type alias ``list[UploadFile]`` (declaration only;
  multipart TRANSPORT parsing + input-validation are a follow-up shard).
- ``Bytes`` — raw-bytes body extractor (size-cap inheritance + 413
  short-circuit + log hygiene).
- ``Headers`` — case-insensitive, read-only mapping of inbound headers
  (RFC 7230 §3.2.2 dual access + 64 KiB cap + 431 reject).
- ``NexusHandlerError`` — typed status return per
  ``rules/nexus-http-status-convention.md`` MUST Rule 4.

This module MUST NOT enable PEP 563 stringized annotations (the future-import
of the same name) — the resolver relies on real (non-string) annotation values
at registration time, and PEP 563 would defeat ``typing.get_type_hints``
resolution of the extractor types.
"""

from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Tuple

from starlette.datastructures import UploadFile
from starlette.requests import Request

from .overrides import DependencyOverrideMap, DependencyOverrideRuntimeMutationError

__all__ = [
    "Depends",
    "Request",
    "UploadFile",
    "Multipart",
    "Bytes",
    "Headers",
    "NexusHandlerError",
    "DependencyOverrideMap",
    "DependencyOverrideRuntimeMutationError",
]


class Depends:
    """Dependency-injection marker used as a parameter default.

    Usage::

        def get_user(request: Request) -> dict:
            return {"id": request.headers.get("x-user-id")}

        @app.handler_extract("me")
        async def me(user: dict = Depends(get_user)) -> dict:
            return user

    The resolver invokes ``dependency`` once per request and memoises the
    result for the duration of that request (so the same ``Depends`` callable
    referenced by two parameters resolves a single time). The wrapped callable
    MAY itself take extractor parameters (``Request``, nested ``Depends``),
    in which case the resolver resolves them recursively.
    """

    __slots__ = ("dependency",)

    def __init__(self, dependency: Callable[..., Any]) -> None:
        if not callable(dependency):
            raise TypeError(
                f"Depends() requires a callable, got {type(dependency).__name__}"
            )
        self.dependency = dependency

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        name = getattr(self.dependency, "__qualname__", repr(self.dependency))
        return f"Depends({name})"


# Multipart is a typed alias for a list of uploaded files. The HTTP-transport
# multipart parsing + input-validation MUSTs (per-file caps, filename
# sanitisation, MIME sniffing, tempfile lifecycle) land in a follow-up shard;
# here it is a declaration only so handler signatures can reference it.
Multipart = List[UploadFile]


class NexusHandlerError(Exception):
    """Typed status return for extractor-based handlers.

    Carries an HTTP ``status_code`` and a response ``body`` (dict or str) per
    ``rules/nexus-http-status-convention.md`` MUST Rule 4. The resolver maps a
    raised ``NexusHandlerError`` to ``status_code`` + ``body`` instead of the
    generic 500 envelope.
    """

    def __init__(self, status_code: int, body: "Dict[str, Any] | str") -> None:
        if not isinstance(status_code, int):
            raise TypeError(
                f"NexusHandlerError status_code must be int, "
                f"got {type(status_code).__name__}"
            )
        if not (100 <= status_code <= 599):
            raise ValueError(
                f"NexusHandlerError status_code must be a valid HTTP status "
                f"(100-599), got {status_code}"
            )
        if not isinstance(body, (dict, str)):
            raise TypeError(
                f"NexusHandlerError body must be dict or str, "
                f"got {type(body).__name__}"
            )
        self.status_code = status_code
        self.body = body
        message = body if isinstance(body, str) else body.get("error", "handler error")
        super().__init__(f"HTTP {status_code}: {message}")


class _HeadersTooLargeError(NexusHandlerError):
    """Internal — raised when inbound headers exceed ``max_request_header_bytes``.

    Surfaces as HTTP 431 + the canonical ``HEADERS_TOO_LARGE`` envelope. Not
    exported; the resolver constructs it from the cap-enforcement path.
    """

    def __init__(self, limit: int) -> None:
        super().__init__(
            status_code=431,
            body={
                "error": "request headers exceed configured cap",
                "code": "HEADERS_TOO_LARGE",
                "limit": limit,
            },
        )


class Headers(Mapping):
    """Case-insensitive, read-only mapping of inbound HTTP headers.

    Implements the contract in ``specs/nexus-fastapi-parity.md`` § Headers
    extractor:

    1. **Case-insensitive access** — ``h["X-Foo"]`` / ``h["x-foo"]`` /
       ``h["X-FOO"]`` / ``h.get("x-Foo")`` all return the same value (keys
       normalised to lowercase per RFC 7230 §3.2).
    2. **Duplicate handling (RFC 7230 §3.2.2)** — ``h["X-Foo"]`` returns the
       values joined by ``", "``; ``h.getlist("X-Foo")`` returns the list of
       raw values in insertion order.
    3. **Insertion-order preservation** — iteration / ``keys()`` / ``items()``
       preserve the original request order, NOT alphabetical.
    4. **Read-only** — mutation methods raise ``TypeError``.
    5. **Inbound header-byte cap** — constructed via ``from_pairs`` with a
       ``max_request_header_bytes`` cap; exceeding the cap raises HTTP 431.

    The handler boundary receives the inbound headers only; response-header
    construction is a separate surface.
    """

    __slots__ = ("_order", "_values")

    # Default total-header-byte cap (64 KiB) — aligns with Starlette's
    # MAX_HEADER_COUNT * MAX_FIELD_SIZE defaults and nginx's
    # large_client_header_buffers typical configuration.
    DEFAULT_MAX_REQUEST_HEADER_BYTES = 65536

    def __init__(self, pairs: "Optional[List[Tuple[str, str]]]" = None) -> None:
        # _order: lowercase keys in first-seen insertion order.
        # _values: lowercase key -> list of raw values (insertion order).
        self._order: List[str] = []
        self._values: Dict[str, List[str]] = {}
        for raw_key, raw_value in pairs or []:
            key = raw_key.lower()
            if key not in self._values:
                self._values[key] = []
                self._order.append(key)
            self._values[key].append(raw_value)

    @classmethod
    def from_pairs(
        cls,
        pairs: "List[Tuple[str, str]]",
        *,
        max_request_header_bytes: int = DEFAULT_MAX_REQUEST_HEADER_BYTES,
    ) -> "Headers":
        """Build from raw (name, value) pairs, enforcing the byte cap.

        Rejection fires as soon as the accumulated header bytes exceed the cap
        — NOT after parsing the full header section — to bound memory cost
        when a malicious client sends many large headers (the canonical OOM
        vector this cap closes). The byte count includes each name + value +
        the ``": "`` and ``CRLF`` framing per RFC 7230 wire shape.
        """
        accumulated = 0
        for name, value in pairs:
            # name + ": " + value + CRLF  (RFC 7230 §3.2 wire framing)
            accumulated += len(name.encode("latin-1", "replace"))
            accumulated += 2  # ": "
            accumulated += len(value.encode("latin-1", "replace"))
            accumulated += 2  # CRLF
            if accumulated > max_request_header_bytes:
                raise _HeadersTooLargeError(limit=max_request_header_bytes)
        return cls(pairs)

    def __getitem__(self, key: str) -> str:
        values = self._values[key.lower()]
        # RFC 7230 §3.2.2: combine multiple same-name fields with ", ".
        return ", ".join(values)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def getlist(self, key: str) -> List[str]:
        """Return all values for ``key`` in insertion order (empty if absent)."""
        return list(self._values.get(key.lower(), []))

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key.lower() in self._values

    def __iter__(self) -> Iterator[str]:
        return iter(self._order)

    def __len__(self) -> int:
        return len(self._order)

    def keys(self):  # type: ignore[override]
        return list(self._order)

    def items(self):  # type: ignore[override]
        return [(k, self[k]) for k in self._order]

    def values(self):  # type: ignore[override]
        return [self[k] for k in self._order]

    # --- read-only enforcement (MUST 4) ---

    def __setitem__(self, key: str, value: str) -> None:
        raise TypeError(
            "Headers is read-only at the handler boundary; request headers "
            "MUST NOT be mutated (response-header construction is a separate "
            "surface)"
        )

    def __delitem__(self, key: str) -> None:
        raise TypeError(
            "Headers is read-only at the handler boundary; request headers "
            "MUST NOT be mutated"
        )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Headers({dict(self.items())!r})"


class Bytes(bytes):
    """Raw-bytes request-body extractor.

    A handler signature ``async def f(body: Bytes) -> ...`` receives the FULL
    (capped) request body as a ``bytes`` value — NOT a generator or stream.

    Contract (per ``specs/nexus-fastapi-parity.md`` § Bytes extractor):

    1. **Inbound size cap inheritance** — inherits
       ``Nexus(max_request_body_bytes=...)``; the resolver short-circuits with
       HTTP 413 + ``BODY_TOO_LARGE`` BEFORE reading the body when
       ``Content-Length`` declares > cap, and rejects mid-stream when an
       accumulator without ``Content-Length`` exceeds the cap.
    2. **Full-body delivery** — the handler receives the complete capped body.
    3. **Log hygiene** — the resolver MUST NOT echo body bytes into server
       logs (the body MAY contain credentials / PII / attack payloads); only
       the body LENGTH is logged. ``Bytes`` subclasses ``bytes`` so it is the
       value the handler sees directly, and ``repr`` is length-only to keep
       the body out of any accidental log line.

    The default 10 MiB cap is exposed as :attr:`DEFAULT_MAX_REQUEST_BODY_BYTES`.
    """

    # Default 10 MiB inbound body cap.
    DEFAULT_MAX_REQUEST_BODY_BYTES = 10_485_760

    def __repr__(self) -> str:
        # Log-hygiene: never render the body bytes — only the length. This
        # keeps credentials / PII / attack payloads out of any log line that
        # interpolates the value.
        return f"<Bytes length={len(self)}>"


class _BodyTooLargeError(NexusHandlerError):
    """Internal — raised when the inbound body exceeds ``max_request_body_bytes``.

    Surfaces as HTTP 413 + the canonical ``BODY_TOO_LARGE`` envelope.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=413,
            body={
                "error": "request body exceeds configured cap",
                "code": "BODY_TOO_LARGE",
            },
        )
