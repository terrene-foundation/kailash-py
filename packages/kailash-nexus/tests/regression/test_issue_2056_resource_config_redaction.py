# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Credential redaction on the MCP resource surface.

Found by an adversarial review of the #2056 / #2171 change rather than by
either issue. Two fixes in ``nexus/resources.py`` combined to make a
credential-disclosure surface REACHABLE where it previously was not:

* #2013's dead-guard repair made ``_extract_workflow_info`` return real nodes
  (it had returned empty lists for every genuine workflow), and
* #2056's template repair made the ``workflow://`` handler invocable at all
  (``workflow://*`` matched no URI and, under official FastMCP, refused to
  register).

``node.config`` routinely carries ``api_key`` / ``connection_string`` /
``password``. Measured before redaction, ``workflow://{name}`` returned
``"api_key": "sk-SUPERSECRET-abc123"`` and a live DB password verbatim to any
MCP client. ``rules/zero-tolerance.md`` Rule 1a: a finding that is "pre-existing
but newly reachable" belongs to the change that made it reachable.
"""

import json
import types

import pytest

from kailash.workflow.builder import WorkflowBuilder
from nexus.resources import REDACTED, NexusResourceManager, redact_config

SECRET = "sk-SUPERSECRET-abc123"
DB_URL = "postgres://user:hunter2@db/prod"


class _FallbackServer:
    def __init__(self):
        self._resources = {}

    def resource(self, uri):
        def decorator(func):
            self._resources[uri] = func
            return func

        return decorator


def _manager(workflows=None, rate_limit_config=None):
    nexus = types.SimpleNamespace(
        _workflows=workflows or {},
        _api_port=8000,
        _mcp_port=3001,
        _enable_auth=False,
        _enable_monitoring=False,
        _enable_discovery=False,
        rate_limit_config=rate_limit_config if rate_limit_config is not None else {},
        _get_enabled_transports=lambda: ["websocket"],
    )
    return NexusResourceManager(_FallbackServer(), nexus)


def _workflow_with_secrets():
    builder = WorkflowBuilder()
    builder.add_node(
        "PythonCodeNode",
        "fetch",
        {"code": "result = {}", "api_key": SECRET, "connection_string": DB_URL},
    )
    workflow = builder.build()
    workflow.metadata = {}
    return workflow


# --------------------------------------------------------------------------
# The surface that leaked
# --------------------------------------------------------------------------


def test_workflow_resource_does_not_emit_node_credentials():
    """The exact leak: api_key and a DB password in the resource body."""
    manager = _manager({"w": _workflow_with_secrets()})

    content = manager._workflow_response("w")["content"]

    assert SECRET not in content, "node api_key was served to the MCP client"
    assert "hunter2" not in content, "DB password was served to the MCP client"
    assert DB_URL not in content

    params = json.loads(content)["nodes"][0]["parameters"]
    assert params["api_key"] == REDACTED
    assert params["connection_string"] == REDACTED


def test_redaction_preserves_non_sensitive_parameters():
    """Redaction must not gut the resource's usefulness.

    The point of ``workflow://`` is letting an agent discover what a workflow
    does; blanking everything would be a different kind of failure.
    """
    manager = _manager({"w": _workflow_with_secrets()})

    params = json.loads(manager._workflow_response("w")["content"])["nodes"][0][
        "parameters"
    ]

    assert params["code"] == "result = {}"
    assert params["name"] == "fetch"
    assert params["sandbox_mode"] == "restricted"


def test_workflow_metadata_is_redacted():
    """Metadata is author-supplied and free-form -- a natural place for a leak."""
    workflow = _workflow_with_secrets()
    workflow.metadata = {"owner": "team-a", "deploy_token": SECRET}
    manager = _manager({"w": workflow})

    content = manager._workflow_response("w")["content"]

    assert SECRET not in content
    assert json.loads(content)["metadata"]["owner"] == "team-a"


def test_configuration_resource_masks_rate_limit_url_credentials():
    """``config://limits`` exposes rate_limit_config, which embeds redis_url.

    ``redis_url`` is measurably NOT in the canonical sensitive-key set, and the
    credential lives in the VALUE rather than the key name, so key matching
    cannot catch it. The canonical URL masker strips the userinfo while leaving
    the host readable -- an operator still needs to know which cache the
    limiter points at.
    """
    manager = _manager(rate_limit_config={"redis_url": "redis://:p4ss@cache:6379/0"})

    content = manager._configuration_response("limits")["content"]

    assert "p4ss" not in content, "redis password served to the MCP client"
    # `_get_configuration` returns the named section itself, not a wrapper.
    masked = json.loads(content)["rate_limit"]["redis_url"]
    assert "cache:6379" in masked, "host was destroyed; the value is now useless"


def test_url_credentials_are_masked_wherever_they_appear():
    """A credential inside a URL value is caught regardless of its key name."""
    result = redact_config({"harmless_name": "postgres://user:hunter2@db/prod"})

    assert "hunter2" not in result["harmless_name"]
    assert "db/prod" in result["harmless_name"]


def test_non_url_strings_are_left_alone():
    """The URL masker must not mangle ordinary values into a sentinel."""
    result = redact_config({"code": "result = {}", "path": "/health", "n": 5})

    assert result["code"] == "result = {}"
    assert result["path"] == "/health"
    assert result["n"] == 5


# --------------------------------------------------------------------------
# The helper itself
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "apikey",
        "API-KEY",
        "password",
        "secret",
        "token",
        "connection_string",
        "db_connection_string",
        "aws_secret_access_key",
        "private_key",
        "passphrase",
        "credentials",
        "session_key",
        "bearer_token",
        "dsn",
    ],
)
def test_sensitive_key_names_are_redacted(key):
    """Covers BOTH the canonical set and the documented supplement.

    ``connection_string``, ``credentials``, ``passphrase``, ``dsn``, ``bearer``
    and ``aws_secret_access_key`` are measurably NOT in
    ``is_sensitive_query_key``'s set, which is why the supplement exists.
    """
    assert redact_config({key: "sensitive"})[key] == REDACTED


@pytest.mark.parametrize(
    "key", ["code", "name", "timeout", "public_key", "max_retries", "sandbox_mode"]
)
def test_non_sensitive_key_names_survive(key):
    """No false positives. ``public_key`` is deliberately here: a public key is
    not a secret, and the canonical set already draws that distinction."""
    assert redact_config({key: "visible"})[key] == "visible"


def test_redaction_recurses_into_nested_structures():
    """A credential one level down must not escape."""
    payload = {
        "outer": {"api_key": SECRET, "safe": 1},
        "items": [{"password": SECRET}, {"ok": "yes"}],
    }

    result = redact_config(payload)

    assert result["outer"]["api_key"] == REDACTED
    assert result["outer"]["safe"] == 1
    assert result["items"][0]["password"] == REDACTED
    assert result["items"][1]["ok"] == "yes"
    assert SECRET not in json.dumps(result)


def test_redaction_does_not_preserve_secret_length():
    """A length-preserving mask leaks the secret's length."""
    short = redact_config({"api_key": "a"})["api_key"]
    long = redact_config({"api_key": "a" * 500})["api_key"]

    assert short == long == REDACTED
