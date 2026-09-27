"""Real sockets with a local routing seam; no external HTTP or TLS traffic."""

import asyncio
import datetime
import hashlib
import hmac
import io
import json
import logging
import secrets
import socket
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from nexus.transports.webhook import DeliveryStatus, WebhookTransport

HOST = "webhook-owned.invalid"
PUBLIC = "93.184.216.34"


@pytest.fixture(params=[False, True], ids=["http", "https"])
def endpoint(request, monkeypatch, tmp_path):
    """Observe numeric TCP destinations, routing only our public test IP locally."""
    state = {"requests": [], "connections": [], "sni": [], "statuses": [200]}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            state["requests"].append((self.path, body, dict(self.headers)))
            statuses = state["statuses"]
            status = statuses.pop(0) if len(statuses) > 1 else statuses[0]
            self.send_response(status)
            if status == 302:
                self.send_header(
                    "Location", f"http://127.0.0.1:{self.server.server_port}/private"
                )
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            state["requests"].append((self.path, b"", dict(self.headers)))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    if request.param:
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
        cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
        context.set_servername_callback(
            lambda sock, hostname, ctx: state["sni"].append(hostname)
        )
        server.socket = context.wrap_socket(server.socket, server_side=True)
        monkeypatch.setenv("SSL_CERT_FILE", str(cert_path))
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("no_proxy", "*")
    original_dns, original_connect = socket.getaddrinfo, socket.socket.connect

    def resolve(host, port, *args, **kwargs):
        if isinstance(host, bytes):
            host = host.decode("ascii")
        assert host in (HOST, PUBLIC, "127.0.0.1"), host
        return original_dns(PUBLIC if host == HOST else host, port, *args, **kwargs)

    def connect(sock, address):
        assert address[1] == server.server_port and address[0] in (
            PUBLIC,
            "127.0.0.1",
        ), address
        state["connections"].append(address[0])
        return original_connect(sock, ("127.0.0.1", server.server_port))

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(socket.socket, "connect", connect)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    state["url"] = (
        f"{'https' if request.param else 'http'}://{HOST}:{server.server_port}/hook"
    )
    state["tls"] = request.param
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
        assert not thread.is_alive()


@pytest.mark.asyncio
async def test_default_signed_delivery_retains_origin_and_tls(endpoint):
    secret = secrets.token_hex(24)
    transport = WebhookTransport(secret=secret, max_retries=1)
    payload = {"event": "owned-delivery", "value": 42}
    delivery = await transport.deliver("hook", payload, endpoint["url"])
    assert delivery.status == DeliveryStatus.DELIVERED
    assert delivery.attempts == 1 and delivery.last_error is None
    assert delivery.delivered_at is not None
    assert delivery.payload is payload and delivery.target_url == endpoint["url"]
    assert transport.get_delivery(delivery.delivery_id) is delivery
    assert len(endpoint["requests"]) == 1
    path, body, headers = endpoint["requests"][0]
    assert path == "/hook" and json.loads(body) == payload
    assert headers["Host"] == urlparse(endpoint["url"]).netloc
    assert hmac.compare_digest(
        headers["X-Webhook-Signature"],
        "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
    )
    assert endpoint["connections"] == [PUBLIC]
    if endpoint["tls"]:
        assert endpoint["sni"] == [HOST]


@pytest.mark.asyncio
async def test_default_redirect_never_dispatches_private_hop(endpoint):
    endpoint["statuses"] = [302]
    delivery = await WebhookTransport(max_retries=1).deliver(
        "hook", {}, endpoint["url"]
    )
    assert (
        delivery.status == DeliveryStatus.FAILED and delivery.last_error == "HTTP 302"
    )
    assert [row[0] for row in endpoint["requests"]] == ["/hook"]
    assert endpoint["connections"] == [PUBLIC]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "statuses,expected,attempts",
    [
        ([204], DeliveryStatus.DELIVERED, 1),
        ([400], DeliveryStatus.FAILED, 1),
        ([429, 201], DeliveryStatus.DELIVERED, 2),
        ([500, 202], DeliveryStatus.DELIVERED, 2),
        ([503], DeliveryStatus.FAILED, 3),
    ],
)
async def test_real_http_status_retry_contract(endpoint, statuses, expected, attempts):
    endpoint["statuses"] = list(statuses)
    delivery = await WebhookTransport(max_retries=3, base_delay=0).deliver(
        "hook", {"x": 1}, endpoint["url"]
    )
    assert delivery.status == expected and delivery.attempts == attempts
    assert len(endpoint["requests"]) == attempts
    assert all(
        row[0] == "/hook" and json.loads(row[1]) == {"x": 1}
        for row in endpoint["requests"]
    )
    assert endpoint["connections"] == [PUBLIC] * attempts


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["failed", "empty", "private", "mixed"])
@pytest.mark.parametrize("custom", [False, True])
async def test_delivery_dns_failure_never_reaches_sender(monkeypatch, failure, custom):
    calls = []
    original = socket.getaddrinfo

    def resolve(host, port, *args, **kwargs):
        if failure == "failed":
            raise socket.gaierror("offline")
        if failure == "empty":
            return []
        rows = original("127.0.0.1", port, *args, **kwargs)
        return (
            original(PUBLIC, port, *args, **kwargs) + rows
            if failure == "mixed"
            else rows
        )

    async def sender(*args):
        calls.append(args)
        return 200

    def forbidden_connect(*args):
        calls.append(args)
        pytest.fail("Unvalidated destination reached TCP")

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(socket.socket, "connect", forbidden_connect)
    transport = WebhookTransport(max_retries=1)
    url = f"http://{HOST}/hook"
    if failure in ("failed", "empty"):
        transport.register_target("hook", url)
        assert transport._target_urls["hook"] == [url]
    with pytest.raises(ValueError):
        await transport.deliver("hook", {}, url, send_func=sender if custom else None)
    assert calls == [] and transport.list_deliveries() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("sender_kind", ["function", "false_bool", "empty_length"])
async def test_custom_sender_preserves_pinned_url_host_and_body(endpoint, sender_kind):
    observed = []
    secret = secrets.token_hex(24)

    async def sender(url, body, headers):
        observed.append((url, body, headers))
        return 200

    class FalseCallable:
        def __bool__(self):
            return False

        async def __call__(self, url, body, headers):
            return await sender(url, body, headers)

    class EmptyCallable:
        def __len__(self):
            return 0

        async def __call__(self, url, body, headers):
            return await sender(url, body, headers)

    selected = {
        "function": sender,
        "false_bool": FalseCallable(),
        "empty_length": EmptyCallable(),
    }[sender_kind]
    delivery = await WebhookTransport(secret=secret).deliver(
        "hook", {"x": 1}, endpoint["url"], send_func=selected
    )
    assert delivery.status == DeliveryStatus.DELIVERED
    assert len(observed) == 1 and endpoint["connections"] == []
    url, body, headers = observed[0]
    assert urlparse(url).hostname == PUBLIC and urlparse(url).path == "/hook"
    assert headers["Host"] == urlparse(endpoint["url"]).netloc
    assert json.loads(body) == {"x": 1}
    assert hmac.compare_digest(
        headers["X-Webhook-Signature"],
        "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(),
    )


@pytest.mark.asyncio
async def test_default_client_owner_closes_after_delivery(endpoint, monkeypatch):
    from nexus.http_client import HttpClient

    closed = []
    original = HttpClient.aclose

    async def close(client):
        await original(client)
        closed.append(client.is_closed)

    monkeypatch.setattr(HttpClient, "aclose", close)
    await WebhookTransport(max_retries=1).deliver("hook", {}, endpoint["url"])
    assert closed == [True]


@pytest.mark.asyncio
async def test_custom_cancellation_is_not_retried(endpoint):
    original = asyncio.CancelledError("caller cancellation")
    calls = []

    async def sender(*args):
        calls.append(args)
        raise original

    with pytest.raises(asyncio.CancelledError) as caught:
        await WebhookTransport(max_retries=3).deliver(
            "hook", {}, endpoint["url"], send_func=sender
        )
    assert caught.value is original and len(calls) == 1
    assert endpoint["connections"] == []


@pytest.mark.asyncio
async def test_outbound_diagnostics_omit_private_url_and_error(endpoint, caplog):
    private = "delivery-person@example.invalid"
    error = ValueError(private)
    logger = logging.getLogger("nexus.transports.webhook")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)

    async def failed_sender(*args):
        raise error

    async def ok_sender(*args):
        return 200

    try:
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            transport = WebhookTransport(max_retries=1)
            url = endpoint["url"] + "?person=" + private
            failed = await transport.deliver("hook", {}, url, send_func=failed_sender)
            success = await transport.deliver("hook", {}, url, send_func=ok_sender)
    finally:
        logger.removeHandler(handler)
        handler.close()
    assert failed.status == DeliveryStatus.FAILED and failed.last_error == private
    assert failed.target_url == url and success.status == DeliveryStatus.DELIVERED
    records = [r for r in caplog.records if r.name == logger.name]
    assert [r.getMessage() for r in records] == [
        "Webhook delivery attempt failed",
        "Webhook delivery exhausted retries",
        "Webhook delivered",
    ]
    assert records[0].error_type == "ValueError" and records[0].error_frames
    assert private not in stream.getvalue()
    assert all(private not in repr(record.__dict__) for record in records)


@pytest.mark.asyncio
async def test_custom_ipv6_sender_preserves_bracketed_host():
    observed = []

    async def sender(url, body, headers):
        observed.append((url, headers["Host"]))
        return 200

    url = "https://[2606:4700:4700::1111]:8443/hook"
    delivery = await WebhookTransport(max_retries=1).deliver(
        "hook", {}, url, send_func=sender
    )
    assert delivery.status == DeliveryStatus.DELIVERED
    assert observed == [(url, "[2606:4700:4700::1111]:8443")]
