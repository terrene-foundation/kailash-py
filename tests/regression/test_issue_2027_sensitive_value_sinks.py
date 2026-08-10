# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Issue #2027 — sensitive values reaching logs, cache keys, and a world-readable file.

Every assertion here is BEHAVIORAL: it drives the real code path and inspects
what actually reached the sink (a captured log record, the key handed to the
resource registry, the mode reported by ``os.stat``). Source-grep assertions
are deliberately absent — they would pass against a comment.

The cache-key tests pin an invariant that is easy to get backwards. The secret
MUST stay in the key material: dropping it (keying on host/user/region alone)
would make a rotated password collide with the key of the pool built from the
OLD password, silently handing callers a live connection authenticated with a
revoked credential. What must NOT happen is the secret being *recoverable*
from the key, which ``hashlib.md5(config)[:8]`` allowed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import stat

import pytest

from kailash.gateway.resource_resolver import ResourceResolver
from kailash.gateway.security import FileSecretBackend
from kailash.runtime.parameter_injector import WorkflowParameterInjector
from kailash.runtime.resource_manager import ResourceCoordinator
from kailash.trust.plane.integration.cursor.hook import _log_verdict
from kailash.utils.url_credentials import process_local_config_key

PASSWORD = "sup3r-s3cret-p4ssw0rd"
OTHER_PASSWORD = "a-completely-different-p4ssw0rd"
BEARER = "sk-live-0123456789abcdefghij"
AWS_SECRET = "wJalrXUtnFEMI-K7MDENG-bPxRfiCYEXAMPLEKEY"


class _RecordingRegistry:
    """Registry stand-in that records the key each resolver asks for.

    ``get_resource`` succeeds so the resolver returns at its first lookup and
    never builds a real pool/client. Not a mock: it exposes exactly the two
    attributes the resolvers touch, with fixed behaviour.
    """

    def __init__(self) -> None:
        self.requested_keys: list[str] = []

    async def get_resource(self, name: str):
        self.requested_keys.append(name)
        return object()

    def register_factory(self, *args, **kwargs):  # pragma: no cover - unused
        raise AssertionError("factory path must not be reached in these tests")


def _resolver() -> tuple[ResourceResolver, _RecordingRegistry]:
    registry = _RecordingRegistry()
    return ResourceResolver(registry, secret_manager=None), registry


def _key_for(coro_factory) -> str:
    resolver, registry = _resolver()
    asyncio.run(coro_factory(resolver))
    assert len(registry.requested_keys) == 1
    return registry.requested_keys[0]


# ---------------------------------------------------------------------------
# 1. MD5 over secret material used as a registry key (4 sites)
# ---------------------------------------------------------------------------


def _suffix(key: str, prefix: str) -> str:
    assert key.startswith(prefix), key
    return key[len(prefix) :]


@pytest.mark.regression
class TestResourceResolverKeysDoNotExposeSecrets:
    """resource_resolver.py — db / http / mq / s3 key derivation.

    On the discriminating assertion: ``PASSWORD not in key`` is deliberately
    NOT relied on here. A hex digest never contains its plaintext, so that
    check passes against the unfixed MD5 code too — it is a vacuous guard
    against literal embedding, kept only as a cheap backstop. The assertion
    that actually reds on the old code is the digest WIDTH: MD5 was truncated
    to 8 hex characters (32 bits), which collides at roughly 2**16 configs and
    hands the caller another tenant's authenticated connection. The fix widens
    to 16. The database case additionally pins the exact legacy digest.
    """

    def test_database_pool_key_excludes_plaintext_password(self) -> None:
        key = _key_for(
            lambda r: r._resolve_database(
                {"host": "db.internal", "database": "app"},
                {"user": "svc", "password": PASSWORD},
            )
        )
        assert PASSWORD not in key
        assert len(_suffix(key, "db_")) == 16

    def test_database_pool_key_is_not_the_md5_of_the_config(self) -> None:
        """The exact pre-fix digest must not appear; MD5 is a reversible
        oracle for the password when the rest of the config is known."""
        config = {"host": "db.internal", "database": "app"}
        creds = {"user": "svc", "password": PASSWORD}
        merged = {**config, **creds}
        legacy = hashlib.md5(json.dumps(merged, sort_keys=True).encode()).hexdigest()[
            :8
        ]
        key = _key_for(lambda r: r._resolve_database(dict(config), dict(creds)))
        assert legacy not in key

    def test_rotating_the_password_changes_the_pool_key(self) -> None:
        """Correctness invariant: a rotated credential MUST NOT reuse the pool
        built from the old one. This is why the secret stays in key material."""
        config = {"host": "db.internal", "database": "app"}
        first = _key_for(
            lambda r: r._resolve_database(
                dict(config), {"user": "svc", "password": PASSWORD}
            )
        )
        second = _key_for(
            lambda r: r._resolve_database(
                dict(config), {"user": "svc", "password": OTHER_PASSWORD}
            )
        )
        assert first != second

    def test_identical_config_yields_a_stable_key(self) -> None:
        """Cache must still hit for genuinely identical connection identity."""
        config = {"host": "db.internal", "database": "app"}
        creds = {"user": "svc", "password": PASSWORD}
        first = _key_for(lambda r: r._resolve_database(dict(config), dict(creds)))
        second = _key_for(lambda r: r._resolve_database(dict(config), dict(creds)))
        assert first == second

    def test_http_client_key_excludes_the_bearer_token(self) -> None:
        key = _key_for(
            lambda r: r._resolve_http_client(
                {"base_url": "https://api.example.com"}, {"api_key": BEARER}
            )
        )
        assert BEARER not in key
        assert len(_suffix(key, "http_")) == 16

    def test_message_queue_key_excludes_the_broker_password(self) -> None:
        key = _key_for(
            lambda r: r._resolve_message_queue(
                {"host": "mq.internal", "type": "rabbitmq"},
                {"username": "svc", "password": PASSWORD},
            )
        )
        assert PASSWORD not in key
        assert len(_suffix(key, "mq_rabbitmq_")) == 16

    def test_s3_key_excludes_the_aws_secret_access_key(self) -> None:
        key = _key_for(
            lambda r: r._resolve_s3_client(
                {"default_bucket": "assets"},
                {
                    "access_key": "AKIAIOSFODNN7EXAMPLE",
                    "secret_key": AWS_SECRET,
                    "region": "eu-west-1",
                },
            )
        )
        assert AWS_SECRET not in key
        assert len(_suffix(key, "s3_eu-west-1_")) == 16


@pytest.mark.regression
class TestProcessLocalConfigKey:
    """The shared helper every one of those call sites routes through."""

    def test_is_not_reproducible_from_the_plaintext_alone(self) -> None:
        """Keyed, so knowing the whole config does not let an attacker who saw
        the key confirm a guessed password."""
        payload = json.dumps({"password": PASSWORD}, sort_keys=True)
        assert (
            process_local_config_key(payload)
            != hashlib.blake2b(payload.encode(), digest_size=8).hexdigest()
        )

    def test_defaults_to_64_bits(self) -> None:
        """8 hex chars collide at ~2**16 configs; a collision hands over
        another tenant's authenticated connection, so widen the key."""
        assert len(process_local_config_key("x")) == 16

    def test_distinct_payloads_give_distinct_keys(self) -> None:
        assert process_local_config_key("a") != process_local_config_key("b")


@pytest.mark.regression
def test_shared_resource_manager_id_excludes_the_password() -> None:
    """resource_manager.py — same class, caller-supplied config carries a DSN."""
    manager = ResourceCoordinator(runtime_id="rt-test")
    resource_id = manager.allocate_shared_resource(
        "connection_pool",
        {"host": "db.internal", "password": PASSWORD},
    )
    assert PASSWORD not in resource_id
    legacy = hashlib.md5(
        str(sorted({"host": "db.internal", "password": PASSWORD}.items())).encode()
    ).hexdigest()[:8]
    assert legacy not in resource_id


# ---------------------------------------------------------------------------
# 2. Workflow parameter VALUES logged
# ---------------------------------------------------------------------------


class _StubWorkflow:
    """Minimal workflow exposing only what the injector reads."""

    def __init__(self) -> None:
        self.metadata = {"_workflow_inputs": {"node_a": {"api_key": "credential"}}}
        self.nodes: dict = {}
        self._node_instances: dict = {}


@pytest.mark.regression
def test_parameter_injector_does_not_log_the_parameter_value(caplog) -> None:
    injector = WorkflowParameterInjector(_StubWorkflow(), debug=True)
    with caplog.at_level(logging.DEBUG):
        injector.transform_workflow_parameters({"api_key": BEARER})

    assert BEARER not in caplog.text, "workflow parameter value reached the log"
    # The mapping line must still be emitted, now carrying the type instead.
    assert "Mapping workflow input api_key" in caplog.text
    assert "type: str" in caplog.text


# ---------------------------------------------------------------------------
# 4. Rate-limit identifier logged at WARN
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_rate_limit_warning_does_not_log_the_raw_identifier(caplog) -> None:
    """nexus rate-limit middleware — the identifier is an IP, a user id, or
    (by the extractor's convention) an API key. The exceeded-limit WARN must
    carry a fingerprint, not the value.

    ``dispatch`` is driven directly rather than through a TestClient: the
    middleware's rate-limit decision needs only ``request.url.path`` and the
    injected extractor, and the log line under test is emitted on the 429
    branch of that same method.
    """
    pytest.importorskip("nexus.auth.rate_limit.middleware")
    from kailash.trust.rate_limit.config import RateLimitConfig
    from nexus.auth.rate_limit.middleware import RateLimitMiddleware

    class _Url:
        path = "/api/things"

    class _Request:
        url = _Url()

    middleware = RateLimitMiddleware(
        app=None,
        config=RateLimitConfig(requests_per_minute=1, backend="memory"),
        identifier_extractor=lambda _request: BEARER,
    )

    async def _drive():
        # call_next is only reached while the request is ALLOWED; the
        # middleware then writes rate-limit headers onto what it returns.
        class _AllowedResponse:
            def __init__(self) -> None:
                self.headers: dict = {}
                self.status_code = 200

        async def _ok(_request):
            return _AllowedResponse()

        # Loop until the limit actually trips rather than assuming it does so
        # on request 2: the backend enforces its own default window size, not
        # the ``requests_per_minute=1`` echoed in the X-RateLimit-Limit header
        # (a config-plumbing discrepancy outside this issue's scope). The test
        # asserts a 429 was genuinely reached, so it cannot pass vacuously.
        with caplog.at_level(logging.WARNING):
            for _ in range(40):
                response = await middleware.dispatch(_Request(), _ok)
                if getattr(response, "status_code", None) == 429:
                    return response
        return None

    response = asyncio.run(_drive())

    assert response is not None, "the limit never tripped; test would be vacuous"
    assert response.status_code == 429, "the limit was not enforced"
    assert caplog.text, "no WARN captured; test would be vacuous"
    assert BEARER not in caplog.text, "raw rate-limit identifier reached the log"
    assert "identifier_fp=" in caplog.text


# ---------------------------------------------------------------------------
# 5. Trust audit log written world-readable
# ---------------------------------------------------------------------------


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


@pytest.mark.regression
class TestTrustAuditLogPermissions:
    def test_new_audit_log_is_owner_only(self, tmp_path) -> None:
        log_path = tmp_path / "audit.jsonl"
        _log_verdict(log_path, "Write", "/etc/passwd", "BLOCKED", "strict", {})
        assert log_path.exists()
        assert _mode(log_path) == 0o600, "trust audit log must not be world-readable"

    def test_preexisting_world_readable_log_is_tightened(self, tmp_path) -> None:
        """The mode argument to os.open applies only on creation, so a log
        written by an earlier version would otherwise stay 0o644 forever."""
        log_path = tmp_path / "audit.jsonl"
        log_path.write_text("")
        os.chmod(log_path, 0o644)
        assert _mode(log_path) == 0o644  # precondition

        _log_verdict(log_path, "Read", "/srv/data", "HELD", "strict", {})
        assert _mode(log_path) == 0o600

    def test_the_verdict_is_still_recorded(self, tmp_path) -> None:
        """Tightening the mode must not silently break the audit trail."""
        log_path = tmp_path / "audit.jsonl"
        _log_verdict(
            log_path, "Write", "/srv/x", "BLOCKED", "strict", {"why": "policy"}
        )
        entry = json.loads(log_path.read_text().strip())
        assert entry["verdict"] == "BLOCKED"
        assert entry["details"] == {"why": "policy"}


@pytest.mark.regression
class TestFileSecretBackendPermissions:
    """gateway/security.py — the secret was written under the umask (0o644)
    and only chmod'ed afterwards, leaving it world-readable mid-write."""

    def test_mode_is_owner_only_while_the_secret_is_being_written(
        self, tmp_path, monkeypatch
    ) -> None:
        """Asserting the FINAL mode would be vacuous: the old write-then-chmod
        code also ended at 0o600. The defect is the window in between, so the
        mode is sampled at the instant the payload hits the file.
        """
        from kailash.gateway import security as security_module

        secret_file = tmp_path / "db-creds.json"
        observed: list[int] = []
        real_dump = security_module.json.dump

        def spying_dump(obj, fp, *args, **kwargs):
            observed.append(_mode(secret_file))
            return real_dump(obj, fp, *args, **kwargs)

        monkeypatch.setattr(security_module.json, "dump", spying_dump)

        manager = FileSecretBackend(str(tmp_path))
        asyncio.run(manager.store_secret("db-creds", {"password": PASSWORD}))

        assert observed, "the write path never ran; test would be vacuous"
        assert (
            observed[0] == 0o600
        ), f"secret was world-readable during the write (mode {observed[0]:o})"

    def test_final_mode_and_content_are_preserved(self, tmp_path) -> None:
        manager = FileSecretBackend(str(tmp_path))
        asyncio.run(manager.store_secret("db-creds", {"password": PASSWORD}))

        secret_file = tmp_path / "db-creds.json"
        assert _mode(secret_file) == 0o600
        assert json.loads(secret_file.read_text())["password"] == PASSWORD
