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
import sys

import pytest

from kailash.gateway.resource_resolver import ResourceResolver
from kailash.gateway.security import FileSecretBackend
from kailash.runtime.parameter_injector import WorkflowParameterInjector
from kailash.runtime.resource_manager import ResourceCoordinator
from kailash.trust.plane.integration.cursor.hook import _log_verdict
from kailash.utils.file_permissions import restrict_to_owner
from kailash.utils.url_credentials import process_local_config_key

PASSWORD = "sup3r-s3cret-p4ssw0rd"
OTHER_PASSWORD = "a-completely-different-p4ssw0rd"
BEARER = "sk-live-0123456789abcdefghij"
AWS_SECRET = "wJalrXUtnFEMI-K7MDENG-bPxRfiCYEXAMPLEKEY"
# FileSecretBackend fails closed without a master key since #2024; these tests
# are about file permissions, so they supply one and move on.
MASTER_KEY = "test-master-key-for-permission-tests"


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
# 5. Trust audit log written world-readable
# ---------------------------------------------------------------------------


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


# POSIX mode bits do not express "only the owner may READ" on Windows --
# os.chmod there toggles the read-only attribute and nothing else. So the
# 0o600 assertions below are POSIX-only by nature, not by convenience. The
# cross-platform contract (the call must not raise, and must report honestly
# whether it protected the file) is asserted separately in
# TestRestrictToOwnerIsCrossPlatform, which runs everywhere.
posix_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX mode bits do not restrict readers on Windows; see "
    "kailash.utils.file_permissions and the cross-platform tests below",
)


@pytest.mark.regression
class TestTrustAuditLogPermissions:
    @posix_only
    def test_new_audit_log_is_owner_only(self, tmp_path) -> None:
        log_path = tmp_path / "audit.jsonl"
        _log_verdict(log_path, "Write", "/etc/passwd", "BLOCKED", "strict", {})
        assert log_path.exists()
        assert _mode(log_path) == 0o600, "trust audit log must not be world-readable"

    @posix_only
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

    @posix_only
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
        monkeypatch.setenv("KAILASH_SECRETS_MASTER_KEY", MASTER_KEY)

        manager = FileSecretBackend(str(tmp_path))
        asyncio.run(manager.store_secret("db-creds", {"password": PASSWORD}))

        assert observed, "the write path never ran; test would be vacuous"
        assert (
            observed[0] == 0o600
        ), f"secret was world-readable during the write (mode {observed[0]:o})"

    @posix_only
    def test_final_mode_and_content_are_preserved(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("KAILASH_SECRETS_MASTER_KEY", MASTER_KEY)
        manager = FileSecretBackend(str(tmp_path))
        asyncio.run(manager.store_secret("db-creds", {"password": PASSWORD}))

        secret_file = tmp_path / "db-creds.json"
        assert _mode(secret_file) == 0o600
        # Content is checked through the class, not by reading the file: since
        # #2024 the file holds a ciphertext envelope, and asserting the
        # password is readable from disk would now be asserting the bug.
        assert asyncio.run(manager.get_secret("db-creds")) == {"password": PASSWORD}
        assert PASSWORD not in secret_file.read_text()


# ---------------------------------------------------------------------------
# Cross-platform: os.fchmod is POSIX-only and crashed the hardened write path
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestRestrictToOwnerIsCrossPlatform:
    """``os.fchmod`` does not exist on Windows.

    The first version of this fix called it unguarded, so every hardened write
    raised ``AttributeError`` on Windows -- and because the audit-log writer
    catches only ``OSError``, that escaped as a crash rather than degrading to
    best-effort. These tests run on every platform.
    """

    def test_writing_a_secret_does_not_raise_on_any_platform(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("KAILASH_SECRETS_MASTER_KEY", MASTER_KEY)
        manager = FileSecretBackend(str(tmp_path))
        asyncio.run(manager.store_secret("db-creds", {"password": PASSWORD}))
        assert asyncio.run(manager.get_secret("db-creds")) == {"password": PASSWORD}

    def test_writing_an_audit_log_does_not_raise_on_any_platform(
        self, tmp_path
    ) -> None:
        log_path = tmp_path / "audit.jsonl"
        _log_verdict(log_path, "Write", "/srv/x", "BLOCKED", "strict", {"why": "p"})
        assert json.loads(log_path.read_text().strip())["verdict"] == "BLOCKED"

    def test_the_posix_path_uses_the_descriptor_not_the_path(self, tmp_path) -> None:
        """fd-based, so a symlink swapped in after the open cannot redirect it."""
        if sys.platform == "win32":
            pytest.skip("no fchmod on Windows; the DACL path is path-based")
        target = tmp_path / "secret"
        target.write_text("x")
        seen: list[int] = []
        real_fchmod = os.fchmod

        def spying_fchmod(fd, mode):
            seen.append(mode)
            return real_fchmod(fd, mode)

        fd = os.open(str(target), os.O_WRONLY)
        try:
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(os, "fchmod", spying_fchmod)
                assert restrict_to_owner(target, fd=fd) is True
        finally:
            os.close(fd)
        assert seen == [0o600], "restrict_to_owner did not use the descriptor"

    def test_reports_false_when_windows_cannot_enforce(self, tmp_path, caplog) -> None:
        """The honest-failure contract: on Windows without pywin32 there is NO
        mechanism to restrict readers, so the helper must say so rather than
        let a caller believe the 0o600 in the source is in force.
        """
        import kailash.utils.file_permissions as fp

        target = tmp_path / "secret"
        target.write_text("x")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(fp.sys, "platform", "win32")
            fp._warn_no_acl_mechanism.cache_clear()
            # No pywin32 in this environment, so the import inside the helper
            # raises ImportError -- the exact state a Windows user without the
            # optional dependency is in.
            with caplog.at_level(logging.WARNING):
                applied = fp.restrict_to_owner(target)

        assert applied is False, "helper claimed protection it did not apply"
        assert "NOT access-controlled" in caplog.text
        assert "pywin32" in caplog.text, "operator is not told how to fix it"

    def test_warns_only_once_per_process(self, tmp_path, caplog) -> None:
        """A per-write warning on a busy audit log would flood the operator."""
        import kailash.utils.file_permissions as fp

        target = tmp_path / "secret"
        target.write_text("x")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(fp.sys, "platform", "win32")
            fp._warn_no_acl_mechanism.cache_clear()
            with caplog.at_level(logging.WARNING):
                fp.restrict_to_owner(target)
                fp.restrict_to_owner(target)

        assert caplog.text.count("NOT access-controlled") == 1

    def test_both_write_paths_survive_an_os_without_fchmod(
        self, tmp_path, monkeypatch
    ) -> None:
        """Reproduces the CI failure directly: Windows' ``os`` module simply
        has no ``fchmod`` attribute, so removing it here is the same condition
        rather than an approximation of it. Against the unguarded version this
        raised ``AttributeError: module 'os' has no attribute 'fchmod'`` --
        verbatim what Windows py3.11/3.12 reported.
        """
        with pytest.MonkeyPatch.context() as mp:
            mp.delattr(os, "fchmod", raising=False)
            assert not hasattr(os, "fchmod"), "the mutation did not take effect"

            log_path = tmp_path / "audit.jsonl"
            _log_verdict(log_path, "Write", "/srv/x", "BLOCKED", "strict", {"w": "p"})
            assert json.loads(log_path.read_text().strip())["verdict"] == "BLOCKED"

            monkeypatch.setenv("KAILASH_SECRETS_MASTER_KEY", MASTER_KEY)
            manager = FileSecretBackend(str(tmp_path))
            asyncio.run(manager.store_secret("creds", {"password": PASSWORD}))
            assert asyncio.run(manager.get_secret("creds")) == {"password": PASSWORD}
