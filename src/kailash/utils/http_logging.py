# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Owner-scoped HTTP dependency diagnostics without suppressing log records.

Registration uses Python's public LogRecord factory. Only HTTPX/HTTPCore source
records emitted inside an owned operation are sanitized, before the previous
factory or any handler sees their arguments. Caller logging and unowned clients
retain their normal records. Public callbacks execute outside the owned scope.
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from pathlib import Path

try:
    import httpcore
    import httpx
except ImportError as exc:
    raise ImportError(
        "HTTP diagnostics require pip install kailash[http-client]"
    ) from exc

from kailash.utils.secure_logging import safe_type_name

_owned = ContextVar("kailash_owned_http_diagnostics", default=False)
_trace_metadata = ContextVar("kailash_http_trace_metadata", default=None)
_request_cleanup = ContextVar("kailash_http_request_cleanup", default=None)
_missing_trace = object()
_registration_lock = threading.RLock()
_sources = {
    str(Path(httpx.__file__).resolve().parent / "_client.py"),
    str(Path(httpx.__file__).resolve().parent / "_config.py"),
    str(Path(httpcore.__file__).resolve().parent / "_trace.py"),
}
_events = frozenset(
    {
        "connect_tcp",
        "connect_unix_socket",
        "start_tls",
        "retry",
        "send_request_headers",
        "send_request_body",
        "receive_response_headers",
        "receive_response_body",
        "response_closed",
        "close",
        "send_connection_init",
        "receive_remote_settings",
    }
)


def _safe_event(message):
    # Exact builtins prevent subclass hooks from supplying diagnostic payloads.
    head = message.split(" ", 1)[0] if type(message) is str else ""  # noqa: E721
    event, _, phase = head.rpartition(".")
    return (
        head
        if event in _events and phase in {"started", "complete", "failed"}
        else "transport.event"
    )


def _install_factory():
    with _registration_lock:
        previous = logging.getLogRecordFactory()
        if getattr(previous, "_kailash_http_diagnostics", False):
            return

        def factory(
            name, level, fn, lno, msg, args, exc_info, func=None, sinfo=None, **kwargs
        ):
            guarded = (
                _owned.get()
                and (name == "httpx" or name.startswith("httpcore."))
                and os.path.realpath(fn) in _sources
            )
            fields = {}
            if guarded:
                if name == "httpx" and os.path.basename(fn) == "_config.py":
                    fields["http_event"] = "configuration.loaded"
                    msg = "HTTP configuration loaded"
                elif name == "httpx":
                    fields["http_event"] = "request.complete"
                    if isinstance(args, tuple) and len(args) == 5:
                        method, _, version, status, _ = args
                        # Admit only builtins, excluding overloaded subclass hooks.
                        if type(method) is str and method in {  # noqa: E721
                            "GET",
                            "POST",
                            "PUT",
                            "PATCH",
                            "DELETE",
                            "HEAD",
                            "OPTIONS",
                            "CONNECT",
                            "TRACE",
                        }:
                            fields["http_method"] = method
                        if type(status) is int and 100 <= status <= 599:  # noqa: E721
                            fields["status_code"] = status
                        if type(version) is str and version in {  # noqa: E721
                            "HTTP/1.0",
                            "HTTP/1.1",
                            "HTTP/2",
                            "HTTP/3",
                        }:
                            fields["http_version"] = version
                    msg = "HTTP request completed"
                else:
                    fields["http_event"] = _safe_event(msg)
                    metadata = _trace_metadata.get()
                    if metadata is not None and metadata[0] == fields["http_event"]:
                        if metadata[1] is not None:
                            fields["exception_type"] = metadata[1]
                    msg = "HTTP transport event"
                args, exc_info, sinfo = (), None, None
            record = previous(
                name, level, fn, lno, msg, args, exc_info, func, sinfo, **kwargs
            )
            record.__dict__.update(fields)
            return record

        factory._kailash_http_diagnostics = True
        logging.setLogRecordFactory(factory)


@contextmanager
def _scope(owned):
    if owned:
        _install_factory()
    token = _owned.set(owned)
    metadata_token = _trace_metadata.set(None)
    try:
        yield
    finally:
        _trace_metadata.reset(metadata_token)
        _owned.reset(token)


@contextmanager
def owned_http_diagnostics():
    """Scope automatic dependency diagnostics for owned HTTP construction."""
    with _scope(True):
        yield


@contextmanager
def unowned_http_diagnostics():
    """Keep caller-supplied HTTP callbacks outside the owned diagnostic scope."""
    with _scope(False):
        yield


class _TraceCallback:
    def __init__(self, original):
        # Redirects may copy the prepared request's extension mapping.
        self.original = (
            original.original if type(original) is _TraceCallback else original
        )

    async def __call__(self, name, info):
        if self.original is not _missing_trace and self.original is not None:
            with _scope(False):
                await self.original(name, info)
        event = name.split(".", 1)[-1]
        error = info.get("exception")
        _trace_metadata.set(
            (event, safe_type_name(error) if isinstance(error, BaseException) else None)
        )


@contextmanager
def _request_scope(request):
    trace = _TraceCallback(request.extensions.get("trace", _missing_trace))
    with _scope(True):
        request.extensions["trace"] = trace
        try:
            yield
        finally:
            if request.extensions.get("trace", _missing_trace) is trace:
                if trace.original is _missing_trace:
                    request.extensions.pop("trace", None)
                else:
                    request.extensions["trace"] = trace.original


@contextmanager
def _request_stream_scope(request):
    original = request.stream
    if isinstance(original, httpx.AsyncByteStream):
        request.stream = _RequestStream(original)
    wrapped = request.stream
    try:
        yield
    finally:
        if request.stream is wrapped:
            request.stream = original


class _UnownedIterator:
    """Delegate the public async-generator protocol outside HTTP diagnostics."""

    def __init__(self, iterator):
        self._iterator = iterator

    def __aiter__(self):
        return self

    async def __anext__(self):
        with _scope(False):
            return await self._iterator.__anext__()

    async def asend(self, value):
        with _scope(False):
            return await self._iterator.asend(value)

    async def athrow(self, *args):
        with _scope(False):
            return await self._iterator.athrow(*args)

    async def aclose(self):
        with _scope(False):
            await self._iterator.aclose()


class _UnownedAuth(httpx.Auth):
    def __init__(self, auth):
        self._auth = auth

    def async_auth_flow(self, request):
        with _scope(False):
            return _UnownedIterator(self._auth.async_auth_flow(request))


def _auth_callback(auth):
    if isinstance(auth, httpx.Auth):
        return _UnownedAuth(auth)
    if callable(auth):

        def invoke(request):
            with _scope(False):
                return auth(request)

        return invoke
    return auth


class _RequestStream(httpx.AsyncByteStream):
    def __init__(self, stream):
        self._stream = stream

    async def __aiter__(self):
        with _scope(False):
            iterator = _UnownedIterator(self._stream.__aiter__())
        async for chunk in iterator:
            yield chunk

    async def aclose(self):
        with _scope(False):
            await self._stream.aclose()


class _ResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream, request):
        self._stream, self._request = stream, request

    async def __aiter__(self):
        with _request_scope(self._request):
            iterator = self._stream.__aiter__()
        while True:
            with _request_scope(self._request):
                try:
                    chunk = await iterator.__anext__()
                except StopAsyncIteration:
                    return
            # Caller processing a chunk is outside our diagnostic scope.
            yield chunk

    async def aclose(self):
        with _request_scope(self._request):
            await self._stream.aclose()


class DiagnosticAsyncClient(httpx.AsyncClient):
    """HTTPX's public client protocol with owner-scoped dependency logging."""

    def __init__(self, *args, **kwargs):
        if "auth" in kwargs:
            kwargs["auth"] = _auth_callback(kwargs["auth"])
        self.event_hooks = kwargs.pop("event_hooks", None) or {}

        async def own_request(request):
            for callback in self.event_hooks["request"]:
                with _scope(False):
                    await callback(request)
            owner, cleanup = _request_cleanup.get()
            assert owner is self
            cleanup.enter_context(_request_scope(request))
            cleanup.enter_context(_request_stream_scope(request))

        async def own_response(response):
            # This public hook precedes auth-flow and caller response reads.
            if not response.is_closed:
                response.stream = _ResponseStream(response.stream, response.request)
            for callback in self.event_hooks["response"]:
                with _scope(False):
                    await callback(response)

        kwargs["event_hooks"] = {
            "request": [own_request],
            "response": [own_response],
        }
        with owned_http_diagnostics():
            super().__init__(*args, **kwargs)

    @property
    def event_hooks(self):
        # Keep HTTPX's mutable mapping/list contract. The dispatchers consult
        # these live lists so post-construction additions cannot inherit scope.
        return self._caller_event_hooks

    @event_hooks.setter
    def event_hooks(self, hooks):
        self._caller_event_hooks = {
            "request": list(hooks.get("request", [])),
            "response": list(hooks.get("response", [])),
        }

    @property
    def auth(self):
        return httpx.AsyncClient.auth.fget(self)

    @auth.setter
    def auth(self, auth):
        httpx.AsyncClient.auth.fset(self, _auth_callback(auth))

    async def send(self, request, **kwargs):
        if "auth" in kwargs:
            kwargs["auth"] = _auth_callback(kwargs["auth"])
        with _scope(True), ExitStack() as cleanup:
            token = _request_cleanup.set((self, cleanup))
            try:
                return await super().send(request, **kwargs)
            finally:
                # Close wrappers while this send still owns their context.
                cleanup.close()
                _request_cleanup.reset(token)

    async def aclose(self):
        with _scope(True):
            await super().aclose()
