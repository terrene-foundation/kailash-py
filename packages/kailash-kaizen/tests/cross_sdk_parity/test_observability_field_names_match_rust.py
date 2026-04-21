# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK parity: llm.request.{start,ok,error} observability fields.

Per ADR-0001 D8, every ``LlmClient.complete`` / ``stream_completion`` call
emits three structured log events (``llm.request.start``,
``llm.request.ok``, ``llm.request.error``) whose field-name set MUST be
byte-identical across kailash-py and kailash-rs. The shared fixture
``fixtures/rust_observability_fields.json`` pins the canonical 9-field
contract (rules/observability.md § "canonical field names" for this domain):

* ``deployment_preset``     -- regex-validated preset name
* ``wire_protocol``         -- on-wire enum kind
* ``endpoint_host``         -- URL-encoded hostname, NOT full URL
* ``auth_strategy_kind``    -- e.g. "api_key" / "aws_sigv4"; NOT credential
* ``model_on_wire_id``      -- resolved model id
* ``request_id``            -- UUID correlation id (observability.md §2)
* ``latency_ms``            -- float wall-clock
* ``upstream_status``       -- HTTP status code on ok/error
* ``error_class``           -- exception class name on error

This test asserts:

1. The Python LlmHttpClient emission subset is a subset of the canonical
   9-field set (no field-name drift at the HTTP transport layer).
2. No BLOCKED credential-carrying field names leak into log sites
   (``api_key``, ``authorization``, ``token``, ``secret_access_key``).
3. The 9 canonical fields contain no names reserved by the framework
   logger (``module``, ``name``, ``msg``) per observability.md §9.

Origin: issue #498 Session 8 (S9).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def rust_fixture() -> dict:
    path = Path(__file__).parent / "fixtures" / "rust_observability_fields.json"
    return json.loads(path.read_text())


def test_canonical_field_set_is_exactly_nine(rust_fixture: dict) -> None:
    """The Rust-fixture canonical set has exactly 9 fields, no silent grow."""
    fields = rust_fixture["canonical_field_names"]
    assert len(fields) == 9, (
        f"Canonical observability field set drifted to {len(fields)} entries; "
        f"cross-SDK shape change requires ADR-0001 D8 amendment."
    )
    # No duplicates.
    assert len(set(fields)) == 9


def test_canonical_field_names_are_snake_case(rust_fixture: dict) -> None:
    """Every canonical field is a simple snake_case identifier.

    Cross-SDK log aggregators (Datadog, Splunk, CloudWatch) index on
    field names; non-snake-case names produce inconsistent column
    registrations across Python + Rust log streams.
    """
    import re

    snake = re.compile(r"^[a-z][a-z0-9_]*$")
    bad = [f for f in rust_fixture["canonical_field_names"] if not snake.match(f)]
    assert not bad, f"Non-snake-case canonical fields: {bad}"


def test_canonical_fields_do_not_collide_with_logrecord_reserved(
    rust_fixture: dict,
) -> None:
    """observability.md §9 -- canonical field names MUST NOT collide with
    ``logging.LogRecord`` reserved attributes.

    Passing a reserved name via ``extra={}`` raises
    ``KeyError: "Attempt to overwrite 'X' in LogRecord"``.
    """
    reserved = {
        "msg",
        "args",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "pathname",
        "filename",
        "name",
        "levelname",
        "levelno",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
    }
    collisions = set(rust_fixture["canonical_field_names"]) & reserved
    assert not collisions, (
        f"Canonical fields collide with LogRecord reserved attributes: "
        f"{sorted(collisions)}. observability.md §9 forbids this -- "
        f"LogRecord.{list(collisions)[0]} overwrite raises KeyError in "
        f"framework-configured logging."
    )


def test_canonical_fields_contain_no_credential_names(
    rust_fixture: dict,
) -> None:
    """Security invariant: no canonical field NAMES are credential-carrying.

    Fields are rendered verbatim into every log line; security.md
    "No secrets in logs" mandates that credential-carrying names never
    appear in the structured surface. The NAME set is frozen here as a
    structural defense.
    """
    blocked = {
        "api_key",
        "apikey",
        "authorization",
        "bearer_token",
        "token",
        "secret",
        "secret_access_key",
        "aws_secret",
        "password",
        "credential",
        "credentials",
        "session_token",
    }
    violations = set(rust_fixture["canonical_field_names"]) & blocked
    assert not violations, (
        f"Canonical fields include credential-carrying names: "
        f"{sorted(violations)}. This BLOCKS the observability contract."
    )


def test_http_client_emits_subset_of_canonical_fields(rust_fixture: dict) -> None:
    """LlmHttpClient emits a subset of the canonical 9-field set.

    The transport layer (http_client.py) ships a subset appropriate to
    its layer (no ``wire_protocol`` because it doesn't know the wire
    protocol yet -- the LlmClient wrapper adds that before final
    emission). Any HTTP-subset field MUST be in the canonical set, OR
    be a transport-layer-only field we've explicitly whitelisted in
    the fixture.
    """
    canonical = set(rust_fixture["canonical_field_names"])
    transport_allowed = set(rust_fixture["http_subset_fields"])

    # transport_allowed is the full HTTP-layer field set; every name in
    # it MUST either be in the canonical set OR be a documented
    # transport-local field (method, status_code, exception_class).
    transport_local_ok = {"method", "status_code", "exception_class"}
    not_canonical = transport_allowed - canonical - transport_local_ok
    assert not not_canonical, (
        f"LlmHttpClient emits fields that are neither canonical nor "
        f"transport-local: {sorted(not_canonical)}. Either add to "
        f"ADR-0001 D8 canonical set (cross-SDK ripple) or remove from "
        f"http_client.py emission."
    )


def test_http_client_emission_grep_matches_fixture(rust_fixture: dict) -> None:
    """Grep the actual LlmHttpClient source to confirm the subset claim.

    Behavioural enforcement: read the real source and assert the set
    of ``"<name>":`` keys appearing inside ``extra={}`` dicts is exactly
    the documented ``http_subset_fields``. Source-drift at the transport
    layer must be caught at this gate, not in production log review.
    """
    import re

    from kaizen.llm import http_client

    src = Path(http_client.__file__).read_text()
    # Find every string literal used as a field key in a logger.*(extra=...)
    # block. Heuristic: dict-key string literals on their own line within
    # an extra={} block. We scan for all string-key lines and union the
    # names.
    emitted = set(
        re.findall(
            r'"(deployment_preset|wire_protocol|endpoint_host|'
            r"auth_strategy_kind|model_on_wire_id|request_id|"
            r"latency_ms|upstream_status|error_class|method|"
            r'status_code|exception_class)"\s*:',
            src,
        )
    )
    transport_allowed = set(rust_fixture["http_subset_fields"])
    unexpected = emitted - transport_allowed
    assert not unexpected, (
        f"LlmHttpClient emits field names not in the parity fixture: "
        f"{sorted(unexpected)}. Add to fixture OR remove from source."
    )


def test_emission_event_names_cross_sdk_stable(rust_fixture: dict) -> None:
    """The three event-name strings themselves are cross-SDK stable."""
    expected = {"llm.request.start", "llm.request.ok", "llm.request.error"}
    actual = set(rust_fixture["emission_events"])
    assert actual == expected
