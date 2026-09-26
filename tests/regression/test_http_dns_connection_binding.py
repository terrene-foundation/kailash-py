# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Real TCP/TLS pinning; numeric test addresses route only to owned local sockets.

The socket.connect seam records the actual numeric destination before routing
93.184.216.34 to the ephemeral loopback fixture. DNS and HTTP/TLS remain real;
no external traffic or MockTransport is involved.
"""

import asyncio
import datetime
import ipaddress
import socket
import ssl
import threading
from contextlib import asynccontextmanager
from types import MethodType

import httpcore
import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from kaizen.llm.errors import InvalidEndpoint
from kaizen.llm.http_client import LlmHttpClient, SafeDnsResolver, _SafeHttpTransport
from nexus.http_client import (
    HttpClient,
    HttpClientConfig,
    InvalidEndpointError,
    SafeDnsTransport,
)

HOST = "approved-dns.invalid"
OTHER = "second-dns.invalid"
PUBLIC = "93.184.216.34"


@pytest.fixture
def tls_contexts(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOST)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(HOST)]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    certfile = tmp_path / "cert.pem"
    keyfile = tmp_path / "key.pem"
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(certfile, keyfile)
    monkeypatch.setenv("SSL_CERT_FILE", str(certfile))
    return server


@asynccontextmanager
async def wire(monkeypatch, *, answers=None, tls=None):
    seen, connected, dns, sni = [], [], [], []
    writers, tasks = set(), set()
    arrived, release = asyncio.Event(), asyncio.Event()
    if tls:
        tls.set_servername_callback(lambda sock, host, context: sni.append(host))

    async def serve(reader, writer):
        writers.add(writer)
        task = asyncio.current_task()
        tasks.add(task)
        try:
            while True:
                try:
                    data = await reader.readuntil(b"\r\n\r\n")
                except (asyncio.IncompleteReadError, ConnectionResetError):
                    break
                lines = data.decode().split("\r\n")
                path = lines[0].split()[1]
                host = next(
                    line[6:] for line in lines if line.lower().startswith("host: ")
                )
                seen.append((path, host, id(writer)))
                arrived.set()
                if path == "/hold":
                    await release.wait()
                location = None
                if path == "/private":
                    location = f"http://127.0.0.1:{port}/target"
                elif path == "/other":
                    location = f"http://{OTHER}:{port}/target"
                body = b"owned endpoint"
                headers = (
                    "HTTP/1.1 302 Found\r\n" if location else "HTTP/1.1 200 OK\r\n"
                )
                if location:
                    headers += f"Location: {location}\r\n"
                writer.write(
                    (headers + f"Content-Length: {len(body)}\r\n\r\n").encode() + body
                )
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionResetError, BrokenPipeError):
                pass
            writers.discard(writer)
            tasks.discard(task)

    server = await asyncio.start_server(serve, "127.0.0.1", 0, ssl=tls)
    port = server.sockets[0].getsockname()[1]
    original_dns, original_connect = socket.getaddrinfo, socket.socket.connect

    def resolve(host, requested_port, *args, **kwargs):
        host = host.decode() if isinstance(host, bytes) else host
        if host in (HOST, OTHER):
            addresses = answers(len(dns)) if answers else [PUBLIC]
            dns.append((host, tuple(addresses)))
            return [
                entry
                for address in addresses
                for entry in original_dns(address, requested_port, *args, **kwargs)
            ]
        ipaddress.ip_address(host)  # Unknown external names are forbidden here.
        return original_dns(host, requested_port, *args, **kwargs)

    def connect(sock, address):
        if not isinstance(address, tuple):
            return original_connect(sock, address)
        host, requested_port = address[:2]
        assert requested_port == port and host in (PUBLIC, "127.0.0.1")
        connected.append(host)
        return original_connect(sock, ("127.0.0.1", requested_port))

    with monkeypatch.context() as patch:
        patch.setattr(socket, "getaddrinfo", resolve)
        patch.setattr(socket.socket, "connect", connect)
        try:
            yield {
                "port": port,
                "seen": seen,
                "connected": connected,
                "dns": dns,
                "sni": sni,
                "arrived": arrived,
                "release": release,
            }
        finally:
            release.set()
            server.close()
            await server.wait_closed()
            for writer in list(writers):
                writer.close()
            if tasks:
                await asyncio.gather(*list(tasks))
            assert not writers and not tasks


def client_for(surface, timeout=2):
    if surface == "nexus":
        return HttpClient(
            HttpClientConfig(timeout_seconds=timeout, connect_timeout_seconds=timeout)
        )
    return LlmHttpClient(timeout=timeout)


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["nexus", "kaizen"])
async def test_rebinding_connects_only_the_validated_numeric_answer(
    surface, monkeypatch
):
    async with wire(
        monkeypatch,
        answers=lambda n: (
            [PUBLIC] if n < (2 if surface == "nexus" else 1) else ["127.0.0.1"]
        ),
    ) as net:
        async with client_for(surface) as client:
            response = await client.get(f"http://{HOST}:{net['port']}/ok")
            assert response.status_code == 200
            assert str(response.url) == f"http://{HOST}:{net['port']}/ok"
        assert net["connected"] == [PUBLIC]
        assert net["dns"] == [(HOST, (PUBLIC,))]
        assert net["seen"][0][:2] == ("/ok", f"{HOST}:{net['port']}")


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["nexus", "kaizen"])
@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        [PUBLIC, "10.1.2.3"],
        [PUBLIC, "169.254.169.254"],
        [PUBLIC, "::ffff:127.0.0.1"],
        [],
    ],
)
async def test_every_candidate_is_checked_before_any_socket(
    surface, addresses, monkeypatch
):
    async with wire(monkeypatch, answers=lambda n: addresses) as net:
        async with client_for(surface) as client:
            with pytest.raises((InvalidEndpoint, InvalidEndpointError)) as raised:
                await client.get(
                    f"http://{HOST}:{net['port']}/secret?token=private-value"
                )
            assert "private-value" not in str(raised.value)
        assert net["connected"] == []
        assert net["seen"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["nexus", "kaizen"])
async def test_pool_origin_redirect_and_same_origin_reuse(surface, monkeypatch):
    async with wire(monkeypatch) as net:
        async with client_for(surface) as client:
            base = f"http://{HOST}:{net['port']}"
            assert (await client.get(base + "/ok")).status_code == 200
            assert (
                await client.get(base + "/other", follow_redirects=True)
            ).status_code == 200
            assert (await client.get(base + "/again")).status_code == 200
            with pytest.raises((InvalidEndpoint, InvalidEndpointError)):
                await client.get(base + "/private", follow_redirects=True)
        assert len(net["connected"]) == 2
        first, redirect, second, again, private = net["seen"]
        assert first[2] == redirect[2] == again[2] == private[2]
        assert second[2] != first[2]
        assert second[1] == f"{OTHER}:{net['port']}"
        assert [row[0] for row in net["seen"]] == [
            "/ok",
            "/other",
            "/target",
            "/again",
            "/private",
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["nexus", "kaizen"])
async def test_tls_sni_host_and_original_certificate_name(
    surface, monkeypatch, tls_contexts
):
    async with wire(monkeypatch, tls=tls_contexts) as net:
        async with client_for(surface) as client:
            url = f"https://{HOST}:{net['port']}/ok"
            response = await client.get(url)
            assert response.status_code == 200 and str(response.url) == url
            with pytest.raises(
                (httpx.ConnectError, ssl.SSLCertVerificationError),
                match="CERTIFICATE_VERIFY_FAILED",
            ):
                await client.get(f"https://{OTHER}:{net['port']}/bad")
        assert net["connected"] == [PUBLIC, PUBLIC]
        assert net["sni"] == [HOST, OTHER]
        assert len(net["seen"]) == 1 and net["seen"][0][1] == f"{HOST}:{net['port']}"


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["nexus", "kaizen"])
async def test_cancellation_closes_connection_and_client_remains_usable(
    surface, monkeypatch
):
    async with wire(monkeypatch) as net:
        async with client_for(surface) as client:
            base = f"http://{HOST}:{net['port']}"
            task = asyncio.create_task(client.get(base + "/hold"))
            try:
                await asyncio.wait_for(net["arrived"].wait(), 2)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                net["release"].set()
            assert (await client.get(base + "/again")).status_code == 200
        assert len(net["connected"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["nexus", "kaizen"])
@pytest.mark.parametrize("cancel", [False, True])
async def test_dns_admission_is_cancellable_and_within_connect_budget(
    surface, cancel, monkeypatch
):
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    original = socket.getaddrinfo

    def delayed(host, port, *args, **kwargs):
        assert host == HOST
        entered.set()
        try:
            assert release.wait(2)
            return original(PUBLIC, port, *args, **kwargs)
        finally:
            done.set()

    async with wire(monkeypatch) as net:
        monkeypatch.setattr(socket, "getaddrinfo", delayed)
        async with client_for(surface, timeout=0.05 if not cancel else 2) as client:
            task = asyncio.create_task(client.get(f"http://{HOST}:{net['port']}/ok"))
            try:
                assert await asyncio.to_thread(entered.wait, 1)
                if cancel:
                    task.cancel()
                with pytest.raises(
                    asyncio.CancelledError if cancel else httpx.ConnectTimeout
                ):
                    await asyncio.wait_for(task, 0.5)
                assert net["connected"] == []
            finally:
                release.set()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        # Join abandoned DNS work before fixture/socket restoration.
        assert await asyncio.to_thread(done.wait, 1)


@pytest.mark.asyncio
async def test_all_addresses_share_one_connect_budget(monkeypatch):
    calls = []

    async def slow_connect(self, host, port, **kwargs):
        calls.append(host)
        await asyncio.sleep(0.04)
        raise httpcore.ConnectError("controlled unavailable address")

    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", slow_connect)
    async with wire(
        monkeypatch, answers=lambda n: [PUBLIC, "8.8.8.8", "1.1.1.1"]
    ) as net:
        async with client_for("nexus", timeout=0.06) as client:
            with pytest.raises(httpx.ConnectTimeout):
                await client.get(f"http://{HOST}:{net['port']}/ok")
        assert calls == [PUBLIC, "8.8.8.8"]
        assert net["connected"] == []


@pytest.mark.parametrize("surface", ["nexus", "kaizen"])
@pytest.mark.parametrize(
    "option", [{"proxy": "http://localhost:8888"}, {"uds": "/tmp/guard-bypass.sock"}]
)
def test_proxy_and_unix_socket_cannot_bypass_destination_admission(surface, option):
    with pytest.raises(ValueError, match="does not support proxy or uds"):
        if surface == "nexus":
            SafeDnsTransport(**option)
        else:
            _SafeHttpTransport(SafeDnsResolver(), **option)


@pytest.mark.asyncio
@pytest.mark.parametrize("deny", [False, True])
async def test_custom_resolver_hook_is_preserved_without_bypassing_ip_guard(
    deny, monkeypatch
):
    checked = []

    class NarrowingResolver(SafeDnsResolver):
        def check_host(self, host):
            checked.append(host)
            if deny:
                raise InvalidEndpoint("scheme", raw_url=host)

    async with wire(monkeypatch, answers=lambda n: ["127.0.0.1"]) as net:
        async with LlmHttpClient(resolver=NarrowingResolver()) as client:
            with pytest.raises(InvalidEndpoint) as raised:
                await client.get(f"http://{HOST}:{net['port']}/ok")
        assert checked == [HOST]
        assert raised.value.reason == ("scheme" if deny else "loopback")
        assert net["connected"] == [] and net["seen"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("callable_object", [False, True, "transparent"])
async def test_effective_instance_hook_can_deny_an_otherwise_allowed_request(
    callable_object, monkeypatch
):
    calls = []

    class PolicyDenied(Exception):
        pass

    class Resolver(SafeDnsResolver):
        pass

    resolver = Resolver()

    def deny(host):
        calls.append(host)
        raise PolicyDenied("policy denied")

    class CallableHook:
        # Merely advertising bound-method attributes must not skip this hook.
        @property
        def __func__(self):
            return SafeDnsResolver.check_host

        @property
        def __self__(self):
            return resolver

        def __call__(self, host):
            deny(host)

    class TransparentHook(CallableHook):
        @property
        def __class__(self):
            return MethodType

    resolver.check_host = (
        TransparentHook()
        if callable_object == "transparent"
        else CallableHook() if callable_object else deny
    )
    async with wire(monkeypatch) as net:
        async with LlmHttpClient(resolver=resolver) as client:
            with pytest.raises(PolicyDenied, match="policy denied"):
                await client.get(f"http://{HOST}:{net['port']}/allowed")
        assert calls == [HOST]
        assert net["connected"] == [] and net["seen"] == []
