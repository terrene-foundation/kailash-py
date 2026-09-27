# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Real HTTP dependency records are private only within owned operations."""

import asyncio
import io
import logging
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from kailash.utils import http_logging
from kaizen.llm.http_client import LlmHttpClient
from nexus.http_client import HttpClient, HttpClientConfig

OWNED = "private-person@owned.invalid"
UNOWNED = "foreign-person@unowned.invalid"


@pytest.fixture
def capture_logs():
    records = []
    output = io.StringIO()
    root = logging.getLogger()
    level, factory = root.level, logging.getLogRecordFactory()

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.__dict__.copy())

    raw, stream = Capture(), logging.StreamHandler(output)
    root.addHandler(raw)
    root.addHandler(stream)
    root.setLevel(logging.DEBUG)
    try:
        yield records, output
    finally:
        root.removeHandler(raw)
        root.removeHandler(stream)
        root.setLevel(level)
        logging.setLogRecordFactory(factory)


@asynccontextmanager
async def server():
    seen, writers, tasks = [], set(), set()
    arrived, release = asyncio.Event(), asyncio.Event()

    async def handle(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        writers.add(writer)
        try:
            data = await reader.readuntil(b"\r\n\r\n")
            lines = data.decode().split("\r\n")
            target = lines[0].split()[1]
            headers = dict(line.split(": ", 1) for line in lines[1:] if ": " in line)
            body = await reader.readexactly(int(headers.get("Content-Length", "0")))
            if headers.get("Transfer-Encoding") == "chunked":
                while True:
                    size = int((await reader.readline()).strip(), 16)
                    if not size:
                        await reader.readexactly(2)
                        break
                    body += await reader.readexactly(size)
                    await reader.readexactly(2)
            marker = parse_qs(urlsplit(target).query)["recipient"][0]
            seen.append((target, headers, body))
            arrived.set()
            if target.startswith("/broken"):
                writer.write((marker + "\r\n\r\n").encode())
            else:
                payload = b"first\nsecond\n"
                writer.write(
                    (
                        f"HTTP/1.1 200 OK\r\nX-Person: {marker}\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n"
                    ).encode()
                )
                await writer.drain()
                if target.startswith("/hold"):
                    await release.wait()
                writer.write(payload)
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionResetError, BrokenPipeError):
                pass
            writers.discard(writer)
            tasks.discard(task)

    listener = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    try:
        yield f"http://localhost:{port}", seen, arrived, release
    finally:
        release.set()
        listener.close()
        await listener.wait_closed()
        for writer in list(writers):
            writer.close()
        if tasks:
            await asyncio.gather(*tasks)
        assert not writers and not tasks


def client(surface):
    return (
        HttpClient(HttpClientConfig(allow_loopback=True))
        if surface == "nexus"
        else LlmHttpClient()
    )


def assert_private(capture):
    records, output = capture
    assert OWNED not in repr(records)
    assert OWNED not in output.getvalue()
    dependency = [
        r for r in records if r["name"] == "httpx" or r["name"].startswith("httpcore.")
    ]
    assert dependency
    assert all(r["args"] == () and r["exc_info"] is None for r in dependency)
    assert all(r.get("http_event") for r in dependency)
    assert any(r.get("status_code") == 200 for r in dependency)
    assert any(
        r.get("http_event") == "receive_response_headers.complete" for r in dependency
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["nexus", "kaizen"])
async def test_raw_records_and_streams_keep_url_headers_and_payload_private(
    surface, capture_logs
):
    async with server() as (base, seen, _, _):
        url = base + "/send?recipient=" + OWNED
        async with client(surface) as http:
            response = await http.post(
                url, content=OWNED.encode(), headers={"X-Recipient": OWNED}
            )
            assert response.status_code == 200 and str(response.url) == url
            assert response.headers["x-person"] == OWNED
        assert seen[0][0] == "/send?recipient=" + OWNED
        assert seen[0][1]["Host"] == urlsplit(base).netloc
        assert seen[0][1]["X-Recipient"] == OWNED and seen[0][2] == OWNED.encode()
    assert_private(capture_logs)


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["nexus", "kaizen"])
async def test_failed_protocol_keeps_public_error_but_no_automatic_payload(
    surface, capture_logs
):
    async with server() as (base, _, _, _):
        async with client(surface) as http:
            with pytest.raises(httpx.RemoteProtocolError) as raised:
                await http.get(base + "/broken?recipient=" + OWNED)
            assert OWNED in str(raised.value)
    records, output = capture_logs
    assert OWNED not in repr(records) and OWNED not in output.getvalue()
    assert any(r.get("exception_type") == "RemoteProtocolError" for r in records)
    assert not http_logging._owned.get()


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["nexus", "kaizen"])
async def test_stream_yield_and_close_do_not_capture_unowned_requests(
    surface, capture_logs
):
    async with server() as (base, seen, _, _):
        async with client(surface) as http:
            url = base + "/stream?recipient=" + OWNED
            iterator = (
                await http.stream("GET", url, chunk_size=6)
                if surface == "nexus"
                else http.stream_lines("GET", url)
            )
            try:
                first = await iterator.__anext__()
                assert first in (b"first\n", "first")
                assert not http_logging._owned.get()
                async with httpx.AsyncClient(trust_env=False) as raw:
                    assert (
                        await raw.get(base + "/raw?recipient=" + UNOWNED)
                    ).status_code == 200
            finally:
                await iterator.aclose()
        assert len(seen) == 2
    records, output = capture_logs
    assert OWNED not in repr(records) and OWNED not in output.getvalue()
    assert UNOWNED in repr(records) and UNOWNED in output.getvalue()
    assert not http_logging._owned.get()


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["nexus", "kaizen"])
async def test_cancellation_restores_scope_and_parallel_unowned_logging(
    surface, capture_logs
):
    async with server() as (base, _, arrived, release):
        async with client(surface) as http:
            task = asyncio.create_task(http.get(base + "/hold?recipient=" + OWNED))
            try:
                await asyncio.wait_for(arrived.wait(), 2)
                async with httpx.AsyncClient(trust_env=False) as raw:
                    assert (
                        await raw.get(base + "/raw?recipient=" + UNOWNED)
                    ).status_code == 200
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    records, output = capture_logs
    assert OWNED not in repr(records) and OWNED not in output.getvalue()
    assert UNOWNED in repr(records) and UNOWNED in output.getvalue()
    assert not http_logging._owned.get()


@pytest.mark.asyncio
@pytest.mark.parametrize("callback_kind", ["trace", "auth", "body"])
async def test_nested_unowned_callback_traffic_and_raw_trace_contract(
    callback_kind, capture_logs
):
    async with server() as (base, seen, _, _):
        async with httpx.AsyncClient(trust_env=False) as raw:
            called = []
            trace_info = []

            async def foreign():
                called.append(True)
                assert (
                    await raw.get(base + "/foreign?recipient=" + UNOWNED)
                ).status_code == 200

            async def trace(name, info):
                trace_info.append((name, repr(info)))
                if not called:
                    await foreign()

            class Auth(httpx.Auth):
                async def async_auth_flow(self, request):
                    await foreign()
                    yield request

            async def body():
                await foreign()
                yield OWNED.encode()

            options = (
                {"extensions": {"trace": trace}}
                if callback_kind == "trace"
                else (
                    {"auth": Auth()} if callback_kind == "auth" else {"content": body()}
                )
            )
            async with LlmHttpClient() as http:
                response = await http.post(
                    base + "/owned?recipient=" + OWNED, **options
                )
                assert response.status_code == 200
                if callback_kind == "trace":
                    assert response.request.extensions["trace"] is trace
                    assert any(OWNED in value for _, value in trace_info)
                if callback_kind == "body":
                    assert seen[-1][2] == OWNED.encode()
            assert len(called) == 1 and len(seen) == 2
    records, output = capture_logs
    assert OWNED not in repr(records) and OWNED not in output.getvalue()
    assert UNOWNED in repr(records) and UNOWNED in output.getvalue()


@pytest.mark.asyncio
async def test_factory_chains_once_preserves_other_records_and_caller_logging(
    capture_logs,
):
    original = logging.getLogRecordFactory()
    calls = []

    def existing(*args, **kwargs):
        record = original(*args, **kwargs)
        record.factory_marker = "retained"
        calls.append(record)
        return record

    logging.setLogRecordFactory(existing)
    capture_logs[0].clear()
    with http_logging._scope(True):
        installed = logging.getLogRecordFactory()
        with http_logging._scope(True):
            assert logging.getLogRecordFactory() is installed
        # Explicit caller logging is not an automatic dependency producer.
        logging.getLogger("httpx").info("caller-authored %s", UNOWNED)
    assert logging.getLogRecordFactory() is installed
    async with server() as (base, _, _, _):
        async with client("nexus") as http:
            assert (
                await http.get(base + "/owned?recipient=" + OWNED)
            ).status_code == 200
    records, output = capture_logs
    assert all(r.get("factory_marker") == "retained" for r in records)
    assert OWNED not in repr(records) and OWNED not in repr([r.__dict__ for r in calls])
    assert UNOWNED in output.getvalue()


@pytest.mark.asyncio
async def test_auth_body_buffering_and_response_reads_preserve_private_stream_ownership(
    capture_logs,
):
    observations = []

    class Auth(httpx.Auth):
        requires_request_body = True
        requires_response_body = True

        def auth_flow(self, request):
            observations.append(request.content)
            response = yield request
            observations.append(response.content)

    async def body():
        yield OWNED.encode()

    async with server() as (base, seen, _, _):
        async with LlmHttpClient() as http:
            response = await http.post(
                base + "/auth?recipient=" + OWNED, content=body(), auth=Auth()
            )
            assert response.request.content == OWNED.encode()
            assert observations == [OWNED.encode(), b"first\nsecond\n"]
            assert seen[0][2] == OWNED.encode()
            assert [chunk async for chunk in response.request.stream] == [
                OWNED.encode()
            ]
    assert_private(capture_logs)


@pytest.mark.asyncio
async def test_public_event_hooks_read_owned_response_and_leave_nested_raw_client_unchanged(
    capture_logs,
):
    async with server() as (base, seen, _, _):
        async with httpx.AsyncClient(trust_env=False) as raw:
            hooks = []

            async def response_hook(response):
                hooks.append(await response.aread())
                assert not http_logging._owned.get()
                assert (
                    await raw.get(base + "/foreign?recipient=" + UNOWNED)
                ).status_code == 200

            async with http_logging.DiagnosticAsyncClient(
                trust_env=False, event_hooks={"response": [response_hook]}
            ) as owned:
                response = await owned.get(base + "/owned?recipient=" + OWNED)
                assert response.content == b"first\nsecond\n"
            assert hooks == [b"first\nsecond\n"] and len(seen) == 2
    records, output = capture_logs
    assert OWNED not in repr(records) and OWNED not in output.getvalue()
    assert UNOWNED in repr(records) and UNOWNED in output.getvalue()


@pytest.mark.asyncio
async def test_tls_context_configuration_remains_exact_without_logging_repr(
    capture_logs,
):
    import ssl

    class Context(ssl.SSLContext):
        def __repr__(self):
            return OWNED

    context = Context(ssl.PROTOCOL_TLS_CLIENT)
    context.load_default_certs()
    from kailash.utils.http_transport import DnsPinnedAsyncTransport

    transport = DnsPinnedAsyncTransport(
        resolve_addresses=lambda _: ("127.0.0.1",),
        validate_url=lambda _: None,
        verify=context,
    )
    try:
        assert transport._pool._ssl_context is context
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    finally:
        await transport.aclose()
    records, output = capture_logs
    assert OWNED not in repr(records) and OWNED not in output.getvalue()
    assert not http_logging._owned.get()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["trace", "body"])
async def test_auth_replacement_requests_keep_caller_callbacks_unowned(
    kind, capture_logs
):
    originals = []
    replacements = []
    called = []
    async with server() as (base, seen, _, _):
        async with httpx.AsyncClient(trust_env=False) as raw:

            async def foreign():
                called.append(True)
                assert (
                    await raw.get(base + "/foreign?recipient=" + UNOWNED)
                ).status_code == 200

            async def trace(name, info):
                if not called:
                    await foreign()

            async def later_trace(name, info):
                pass

            async def body():
                await foreign()
                yield OWNED.encode()

            class Auth(httpx.Auth):
                async def async_auth_flow(self, request):
                    originals.append(request)
                    first = yield request
                    assert first.status_code == 200
                    request.extensions["trace"] = later_trace
                    replacement = httpx.Request(
                        "POST",
                        base + "/replacement?recipient=" + OWNED,
                        content=body() if kind == "body" else OWNED.encode(),
                        extensions={"trace": trace} if kind == "trace" else {},
                    )
                    replacements.append(replacement)
                    yield replacement

            async with LlmHttpClient() as owned:
                response = await owned.get(
                    base + "/initial?recipient=" + OWNED, auth=Auth()
                )
                assert response.request is replacements[0]
            assert originals[0].extensions["trace"] is later_trace
            assert replacements[0].extensions.get("trace") is (
                trace if kind == "trace" else None
            )
            assert len(seen) == 3 and len(called) == 1 and seen[-1][2] == OWNED.encode()
    records, output = capture_logs
    assert OWNED not in repr(records) and OWNED not in output.getvalue()
    assert UNOWNED in repr(records) and UNOWNED in output.getvalue()


@pytest.mark.asyncio
async def test_request_iterator_factory_tasks_inherit_unowned_scope(capture_logs):
    tasks = []
    scopes = []
    async with server() as (base, seen, _, _):
        async with httpx.AsyncClient(trust_env=False) as raw:

            async def foreign():
                assert (
                    await raw.get(base + "/foreign?recipient=" + UNOWNED)
                ).status_code == 200

            class Stream(httpx.AsyncByteStream):
                def __aiter__(self):
                    scopes.append(http_logging._owned.get())
                    tasks.append(asyncio.create_task(foreign()))

                    async def body():
                        yield OWNED.encode()

                    return body()

            async with http_logging.DiagnosticAsyncClient(trust_env=False) as owned:
                request = httpx.Request(
                    "POST",
                    base + "/owned?recipient=" + OWNED,
                    headers={
                        "Content-Length": str(len(OWNED)),
                        "Host": urlsplit(base).netloc,
                    },
                    stream=Stream(),
                )
                try:
                    response = await owned.send(request)
                    assert response.status_code == 200
                finally:
                    await asyncio.gather(*tasks)
            assert scopes == [False] and len(seen) == 2
    records, output = capture_logs
    assert OWNED not in repr(records) and OWNED not in output.getvalue()
    assert UNOWNED in repr(records) and UNOWNED in output.getvalue()


@pytest.mark.asyncio
async def test_custom_resolver_http_uses_unowned_worker_context(capture_logs):
    from kaizen.llm.http_client import SafeDnsResolver

    scopes = []
    async with server() as (base, seen, _, _):

        class Resolver(SafeDnsResolver):
            def check_host(self, host):
                scopes.append(http_logging._owned.get())
                with httpx.Client(trust_env=False) as raw:
                    assert (
                        raw.get(base + "/foreign?recipient=" + UNOWNED).status_code
                        == 200
                    )

        async with LlmHttpClient(resolver=Resolver()) as owned:
            assert (
                await owned.get(base + "/owned?recipient=" + OWNED)
            ).status_code == 200
        assert scopes == [False] and len(seen) == 2
    records, output = capture_logs
    assert OWNED not in repr(records) and OWNED not in output.getvalue()
    assert UNOWNED in repr(records) and UNOWNED in output.getvalue()


@pytest.mark.asyncio
async def test_request_hook_replacements_are_prepared_after_caller_mutation(
    capture_logs,
):
    calls = []
    async with server() as (base, seen, _, _):
        async with httpx.AsyncClient(trust_env=False) as raw:

            async def trace(name, info):
                if not calls:
                    calls.append(True)
                    assert (
                        await raw.get(base + "/foreign?recipient=" + UNOWNED)
                    ).status_code == 200

            async def request_hook(request):
                assert not http_logging._owned.get()
                request.extensions["trace"] = trace
                request.stream = httpx.ByteStream(OWNED.encode())
                request.headers["Content-Length"] = str(len(OWNED))

            async with http_logging.DiagnosticAsyncClient(
                trust_env=False, event_hooks={"request": [request_hook]}
            ) as owned:
                response = await owned.post(
                    base + "/owned?recipient=" + OWNED, content=b"original"
                )
                assert response.request.extensions["trace"] is trace
            assert len(seen) == 2 and seen[-1][2] == OWNED.encode() and len(calls) == 1
    records, output = capture_logs
    assert OWNED not in repr(records) and OWNED not in output.getvalue()
    assert UNOWNED in repr(records) and UNOWNED in output.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["request", "response"])
@pytest.mark.parametrize("mutation", ["append", "replace_list", "setter"])
async def test_mutable_event_hooks_keep_live_callbacks_unowned(
    phase, mutation, capture_logs
):
    scopes = []
    async with server() as (base, seen, _, _):
        async with httpx.AsyncClient(trust_env=False) as raw:

            async def callback(value):
                scopes.append(http_logging._owned.get())
                if phase == "response":
                    assert await value.aread() == b"first\nsecond\n"
                assert (
                    await raw.get(base + "/foreign?recipient=" + UNOWNED)
                ).status_code == 200

            async with http_logging.DiagnosticAsyncClient(trust_env=False) as owned:
                if mutation == "append":
                    owned.event_hooks[phase].append(callback)
                elif mutation == "replace_list":
                    owned.event_hooks[phase] = [callback]
                else:
                    owned.event_hooks = {phase: [callback]}
                response = await owned.get(base + "/owned?recipient=" + OWNED)
                assert response.status_code == 200
                assert owned.event_hooks[phase] == [callback]
            assert scopes == [False] and len(seen) == 2
    records, output = capture_logs
    assert OWNED not in repr(records) and OWNED not in output.getvalue()
    assert UNOWNED in repr(records) and UNOWNED in output.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["auth_object", "callable"])
async def test_reassigned_auth_callbacks_remain_unowned(kind, capture_logs):
    tasks, scopes = [], []
    async with server() as (base, seen, _, _):
        async with httpx.AsyncClient(trust_env=False) as raw:

            async def foreign():
                assert (
                    await raw.get(base + "/foreign?recipient=" + UNOWNED)
                ).status_code == 200

            class Auth(httpx.Auth):
                async def async_auth_flow(self, request):
                    scopes.append(http_logging._owned.get())
                    await foreign()
                    yield request

            def auth(request):
                scopes.append(http_logging._owned.get())
                tasks.append(asyncio.create_task(foreign()))
                return request

            async with http_logging.DiagnosticAsyncClient(trust_env=False) as owned:
                owned.auth = Auth() if kind == "auth_object" else auth
                try:
                    response = await owned.get(base + "/owned?recipient=" + OWNED)
                    assert response.status_code == 200
                finally:
                    await asyncio.gather(*tasks)
            assert scopes == [False] and len(seen) == 2
    records, output = capture_logs
    assert OWNED not in repr(records) and OWNED not in output.getvalue()
    assert UNOWNED in repr(records) and UNOWNED in output.getvalue()
