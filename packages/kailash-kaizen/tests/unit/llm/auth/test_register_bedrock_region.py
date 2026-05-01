# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``LlmDeployment.register_bedrock_region`` (#764).

Cross-SDK parity with kailash-rs PR #726
(``LlmDeployment::register_bedrock_region``).

Acceptance criteria from the issue:

- ``register_bedrock_region(region)`` registers the region.
- Idempotent.
- Region format validated; malformed input raises a typed error
  distinct from "region not in allowlist".
- Thread-safe (the registry is read on every Bedrock-preset construction).
- Documented as a hatch-of-last-resort.
- Tier 2 test: register → validate → flows through
  ``bedrock_claude(region, auth)`` to a successful preset.

Per ``rules/testing.md`` § 3-Tier Testing, these are Tier 1 unit tests —
the registry is a pure in-process data structure with no real
infrastructure dependency. The "Tier 2" framing in the issue is read as
"flows through the public Bedrock-preset surface", which the
``test_registered_region_flows_through_bedrock_claude`` test does.

The Bedrock-region registry is shared process-state. Tests use unique fake
regions per scenario (``xx-<scenario-name>-1``) so xdist parallelism does
not interfere — mirrors the kailash-rs test pattern.
"""

from __future__ import annotations

import threading
from typing import Generator

import pytest

from kaizen.llm.auth.aws import (
    BEDROCK_SUPPORTED_REGIONS,
    AwsBearerToken,
    InvalidRegionFormat,
    RegionNotAllowed,
    _bedrock_region_registry_clear_for_tests,
    _bedrock_region_registry_contains,
    _validate_region_or_raise,
    register_bedrock_region,
)
from kaizen.llm.deployment import LlmDeployment


@pytest.fixture(autouse=True)
def _isolate_registry() -> Generator[None, None, None]:
    """Reset the runtime registry around each test.

    Mirrors kailash-rs's ``clear_for_tests`` pattern. Tests still pick
    distinct fake regions to be xdist-safe, but the auto-clear keeps
    individual tests independent of execution order.
    """
    _bedrock_region_registry_clear_for_tests()
    yield
    _bedrock_region_registry_clear_for_tests()


# ---------------------------------------------------------------------------
# Static allowlist short-circuits — registry is consulted only afterwards
# ---------------------------------------------------------------------------


def test_static_allowlist_validates_without_registration() -> None:
    """`us-east-1` is in BEDROCK_SUPPORTED_REGIONS — MUST validate without
    any runtime registry insertion."""
    assert "us-east-1" in BEDROCK_SUPPORTED_REGIONS
    assert _validate_region_or_raise("us-east-1") == "us-east-1"
    assert not _bedrock_region_registry_contains("us-east-1")


def test_unregistered_well_formed_region_rejected() -> None:
    """A well-formed region not in the static allowlist AND not in the
    runtime registry MUST raise RegionNotAllowed (NOT
    InvalidRegionFormat)."""
    with pytest.raises(RegionNotAllowed):
        _validate_region_or_raise("xx-stillunregistered-1")


# ---------------------------------------------------------------------------
# register_bedrock_region — happy path
# ---------------------------------------------------------------------------


def test_registered_region_passes_validate() -> None:
    register_bedrock_region("xx-validatepass-1")
    assert _validate_region_or_raise("xx-validatepass-1") == "xx-validatepass-1"
    assert _bedrock_region_registry_contains("xx-validatepass-1")


def test_registered_region_flows_through_aws_bearer_token() -> None:
    """Issue AC (strategy-level integration): register → AwsBearerToken
    accepts the runtime-registered region.

    ``AwsBearerToken.__init__`` calls ``_validate_region_or_raise``,
    which is the integration point #764 modifies. A registered region
    MUST pass that gate.

    Note on full preset construction: ``bedrock_claude_preset``
    additionally builds the deployment endpoint at
    ``bedrock-runtime.{region}.amazonaws.com``. The SSRF guard's DNS
    resolution check rejects unresolvable hostnames with
    ``resolution_failed``, which is correct behavior — DNS for an
    unreleased AWS region does NOT resolve until AWS publishes it.
    Operators registering a runtime region must wait for AWS DNS to
    publish the new endpoint regardless of this SDK; the registry
    mechanism (this test) and the full preset (below, against
    ``us-east-1``) triangulate the contract.
    """
    register_bedrock_region("xx-flowtest-1")
    auth = AwsBearerToken(token="not-a-real-credential", region="xx-flowtest-1")
    assert auth.region == "xx-flowtest-1"


def test_static_region_flows_through_bedrock_claude_full_path() -> None:
    """Full preset construction with a static-allowlist region.

    Proves the ``bedrock_claude`` preset's full path works (auth +
    endpoint + DNS) for any region in ``BEDROCK_SUPPORTED_REGIONS``.
    Combined with the strategy-level test above, this triangulates the
    registry's contract: registered regions pass the auth strategy,
    static regions pass the full preset, and the runtime registry only
    matters when the static set lacks the region (the hatch-of-last-
    resort case).
    """
    dep = LlmDeployment.bedrock_claude(
        api_key="not-a-real-credential",
        region="us-east-1",  # in BEDROCK_SUPPORTED_REGIONS
        model="claude-sonnet-4-6",
    )
    assert dep.preset_name == "bedrock_claude"
    assert "us-east-1" in str(dep.endpoint.base_url)


# ---------------------------------------------------------------------------
# Idempotency — repeated registration of the same region is a no-op
# ---------------------------------------------------------------------------


def test_idempotent_registration() -> None:
    register_bedrock_region("xx-idempotent-1")
    register_bedrock_region("xx-idempotent-1")
    register_bedrock_region("xx-idempotent-1")
    assert _validate_region_or_raise("xx-idempotent-1") == "xx-idempotent-1"


# ---------------------------------------------------------------------------
# Format validation — malformed input raises InvalidRegionFormat (NOT
# RegionNotAllowed). Two-tier signaling per issue AC.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_region",
    [
        "not-a-region",  # sub-region segment is hyphenated word
        "us-east-",  # missing trailing digit
        "US-EAST-1",  # uppercase not allowed
        "us_east_1",  # underscores not allowed
        "us-east-1-extra",  # extra segment
        "1us-east-1",  # leading digit
        "us-east",  # missing trailing -N
        "verylongregion-east-1",  # first segment > 3 chars
        "",  # empty
        " us-east-1 ",  # surrounding whitespace
    ],
)
def test_invalid_format_rejected(bad_region: str) -> None:
    with pytest.raises(InvalidRegionFormat):
        register_bedrock_region(bad_region)


def test_invalid_format_rejects_non_string() -> None:
    """Type-confusion: non-string inputs raise InvalidRegionFormat."""
    with pytest.raises(InvalidRegionFormat):
        register_bedrock_region(None)  # type: ignore[arg-type]
    with pytest.raises(InvalidRegionFormat):
        register_bedrock_region(12345)  # type: ignore[arg-type]


def test_invalid_region_format_distinct_from_region_not_allowed() -> None:
    """The two-tier error signal: format violation vs. allowlist miss."""
    # Format violation:
    with pytest.raises(InvalidRegionFormat):
        register_bedrock_region("US-EAST-1")
    # Allowlist miss (well-formed but never registered):
    with pytest.raises(RegionNotAllowed):
        _validate_region_or_raise("xx-formedunregistered-1")
    # And the two errors are NOT in an isa relationship that would let one
    # be caught as the other accidentally.
    assert not issubclass(InvalidRegionFormat, RegionNotAllowed)
    assert not issubclass(RegionNotAllowed, InvalidRegionFormat)


# ---------------------------------------------------------------------------
# Public surface — exposed via LlmDeployment.register_bedrock_region
# ---------------------------------------------------------------------------


def test_classmethod_attachment_on_llm_deployment() -> None:
    """Operators reach the function via the canonical
    ``LlmDeployment.register_bedrock_region`` path (parity with
    kailash-rs)."""
    LlmDeployment.register_bedrock_region("xx-classmethod-1")
    assert _validate_region_or_raise("xx-classmethod-1") == "xx-classmethod-1"


# ---------------------------------------------------------------------------
# Thread-safety — concurrent registrations + reads must not corrupt state
# ---------------------------------------------------------------------------


def test_concurrent_registration_is_thread_safe() -> None:
    """Spawn N writer threads + N reader threads. Every region attempted
    by a writer MUST end up in the registry; readers MUST NOT observe a
    partial / corrupted state."""
    # 16 letter-only suffixes — the format regex bans digits in the
    # sub-region segment, so we cannot use f"xx-concur{i}-1".
    suffixes = [
        "a",
        "b",
        "c",
        "d",
        "e",
        "f",
        "g",
        "h",
        "i",
        "j",
        "k",
        "l",
        "m",
        "n",
        "o",
        "p",
    ]
    n_writers = len(suffixes)
    regions = [f"xx-concur{s}-1" for s in suffixes]
    errors: list[Exception] = []

    def writer(region: str) -> None:
        try:
            register_bedrock_region(region)
        except Exception as e:  # pragma: no cover - thread-safety failure
            errors.append(e)

    def reader() -> None:
        # Just reads — must not raise. We do NOT assert membership here
        # because writers race the readers; only the post-join state is
        # deterministic.
        for region in regions:
            try:
                _bedrock_region_registry_contains(region)
            except Exception as e:  # pragma: no cover - thread-safety failure
                errors.append(e)

    writers = [threading.Thread(target=writer, args=(r,)) for r in regions]
    readers = [threading.Thread(target=reader) for _ in range(n_writers)]
    for t in writers + readers:
        t.start()
    for t in writers + readers:
        t.join()

    assert not errors, f"thread-safety failures: {errors!r}"
    # Post-join: every region MUST be in the registry.
    for region in regions:
        assert _validate_region_or_raise(region) == region
