"""DEFENSE-3 — Fabric smoke invariants (issue #979 S6).

Tier-1 placeholders compensating for COVERAGE-LOSS-1 (SSRF) and
COVERAGE-LOSS-2 (fabric-integrity classification) that vanished from
``tests/unit/fabric/*`` when S3 moved the fabric suite to the
integration tier per ``briefs/00-brief.md:43-45`` AC #3.

Both subjects under test are pure functions in ``dataflow.fabric.*``
that do NOT require ``[fabric]`` extras (no httpx, no Starlette, no
network I/O), so they belong in tier-1 by construction — see
``rules/testing.md`` § 3-Tier Testing.

If the SSRF validator's blocklist regresses (e.g. someone narrows
``_BLOCKED_NETWORKS`` to remove cloud metadata) OR the route classifier
weakens its exempt/fabric-required precedence, these tests fail
loudly in unit-tier CI before any integration suite has a chance to
run against real httpx middleware.
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
def test_ssrf_validator_rejects_private_and_metadata_ranges() -> None:
    """COVERAGE-LOSS-1 compensation: every documented SSRF blocklist
    entry in ``dataflow.fabric.ssrf._BLOCKED_NETWORKS`` MUST raise
    ``SSRFError`` when the URL targets it. The cloud-metadata IP
    (169.254.169.254) is the highest-value sentinel — losing that
    coverage is how SSRF regressions land in production.
    """
    from dataflow.fabric.ssrf import SSRFError, validate_url_safe

    blocked_urls = [
        "http://10.0.0.1/x",  # RFC1918 — /8
        "http://172.16.0.1/x",  # RFC1918 — /12
        "http://192.168.1.1/x",  # RFC1918 — /16
        "http://127.0.0.1/x",  # loopback /8
        "http://169.254.169.254/x",  # cloud metadata (AWS / GCP / Azure)
        "http://[::1]/x",  # IPv6 loopback
    ]
    for url in blocked_urls:
        with pytest.raises(SSRFError):
            validate_url_safe(url)


@pytest.mark.unit
def test_ssrf_validator_allows_public_https_addresses() -> None:
    """SSRF validator MUST NOT false-positive on public IP literals —
    a too-aggressive blocklist would break every legitimate outbound
    HTTP call from RestSourceAdapter / OAuth2Auth.
    """
    from dataflow.fabric.ssrf import validate_url_safe

    # 8.8.8.8 is Google Public DNS — public, routable, not in any
    # blocked range. Validator MUST pass it through.
    assert validate_url_safe("https://8.8.8.8/") == "https://8.8.8.8/"


@pytest.mark.unit
def test_fabric_route_classifier_partitions_correctly() -> None:
    """COVERAGE-LOSS-2 compensation: ``classify_route`` is the pure
    function that gates ``FabricIntegrityMiddleware``'s silent-bypass
    detection. The four-way partition MUST hold per priority order
    (exempt > fabric_required > direct_storage > neutral).
    """
    from dataflow.fabric.integrity import FabricIntegrityConfig, classify_route

    config = FabricIntegrityConfig(
        extra_direct_storage_patterns=("/api/legacy/",),
    )

    # Priority 1: exempt methods (OPTIONS for CORS preflight)
    assert classify_route("/fabric/dashboard", "OPTIONS", config) == "exempt"

    # Priority 2: exempt prefixes (health/metrics/docs)
    assert classify_route("/health", "GET", config) == "exempt"
    assert classify_route("/fabric/metrics", "GET", config) == "exempt"

    # Priority 3: fabric_required (the silent-bypass detection target)
    assert classify_route("/fabric/dashboard", "GET", config) == "fabric_required"

    # Priority 4: direct_storage (migration-candidate signal)
    assert classify_route("/api/legacy/products", "GET", config) == "direct_storage"

    # Priority 5: neutral default
    assert classify_route("/api/v1/orders", "POST", config) == "neutral"
