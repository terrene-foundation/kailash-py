# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for #2091 -- unconstrained core proxy destination.

PR #2064 closed the CALLER-driven SSRF on core's two proxy surfaces. The
DESTINATION itself stayed unconstrained: nothing stopped a registration
naming ``http://169.254.169.254/``, so an authenticated caller could read
cloud metadata -- IAM credentials on the usual providers -- through the proxy.

This is a DEPLOYMENT-misconfiguration surface, not a caller-driven one, and
the severity is materially lower than the defects #2064 fixed: ``proxy_url``
comes from a developer calling a Python API, not from request data. It needs
someone to register a bad destination; it does not need an attacker. That is
worth stating rather than glossing -- and it is also why it should not be
left implicit, because a reader of the pre-fix code would reasonably conclude
the destination was deliberately unconstrained.

Fail-first, measured pre-fix on BOTH surfaces::

    WorkflowServer       http://169.254.169.254/          -> REGISTRATION ACCEPTED  <== SSRF
    WorkflowServer       http://metadata.google.internal/ -> REGISTRATION ACCEPTED  <== SSRF
    WorkflowAPIGateway   http://169.254.169.254/          -> REGISTRATION ACCEPTED  <== SSRF
    WorkflowAPIGateway   http://metadata.google.internal/ -> REGISTRATION ACCEPTED  <== SSRF

The guard is the one lifted out of ``nexus.http_client`` into
``kailash.utils.network_guard`` -- the reference implementation #2091 named.
``test_core_and_nexus_share_one_implementation`` pins that they are the same
code object rather than two copies that happen to agree today.
"""

import ipaddress

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from kailash.api.gateway import WorkflowAPIGateway
from kailash.servers.workflow_server import WorkflowServer
from kailash.utils.network_guard import BlockedDestinationError
from kailash.utils.proxy_guard import reject_unsafe_proxy_destination

pytestmark = pytest.mark.regression


async def _allow(request: Request):
    """A real dependency, not a Mock."""
    if request.headers.get("X-Regression-Key") != "let-me-in":
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user_id": "keyed"}


#: Destinations with NO legitimate proxy use. Blocked by default.
BLOCKED_DESTINATIONS = [
    ("http://169.254.169.254/", "metadata_service"),
    ("http://169.254.169.254/latest/meta-data/iam/security-credentials/", "metadata_service"),
    ("http://metadata.google.internal/", "metadata_host"),
    ("http://metadata.azure.com/", "metadata_host"),
    ("http://169.254.1.5/", "link_local"),
    ("http://[fe80::1]/", "link_local"),
]

#: Destinations a reverse proxy is LEGITIMATELY pointed at. A blanket RFC1918
#: block would break the primary use, so both polarities are asserted.
ALLOWED_DESTINATIONS = [
    "http://127.0.0.1:9/",
    "http://10.1.2.3:8080/",
    "http://192.168.1.10/",
    "http://172.16.5.5/",
]


def _make_server():
    return WorkflowServer(title="issue-2091", require_auth=False)


def _make_gateway():
    return WorkflowAPIGateway(require_auth=False, title="issue-2091")


SURFACES = [("WorkflowServer", _make_server), ("WorkflowAPIGateway", _make_gateway)]


# ---------------------------------------------------------------------------
# Enforcement-surface parity -- BOTH surfaces refuse, through ONE guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("surface_name,make", SURFACES)
@pytest.mark.parametrize("url,expected_reason", BLOCKED_DESTINATIONS)
def test_blocked_destination_refused_at_registration(
    surface_name, make, url, expected_reason
):
    surface = make()
    try:
        with pytest.raises(BlockedDestinationError) as exc:
            surface.proxy_workflow(
                name="internal",
                proxy_url=url,
                allowed_paths=["*"],
                auth_dependency=_allow,
            )
        assert exc.value.reason == expected_reason
        # Refused BEFORE anything was recorded -- no half-registered proxy.
        assert "internal" not in surface.workflows
    finally:
        surface.close()


@pytest.mark.parametrize("surface_name,make", SURFACES)
@pytest.mark.parametrize("url", ALLOWED_DESTINATIONS)
def test_legitimate_internal_destination_still_registers(surface_name, make, url):
    """The no-false-positive polarity.

    Proxying to an internal service is the COMMON legitimate use of this
    surface. A control that breaks it gets switched off wholesale, taking the
    metadata protection with it.
    """
    surface = make()
    try:
        surface.proxy_workflow(
            name="internal",
            proxy_url=url,
            allowed_paths=["*"],
            auth_dependency=_allow,
        )
        assert "internal" in surface.workflows
    finally:
        surface.close()


@pytest.mark.parametrize("surface_name,make", SURFACES)
def test_metadata_block_survives_require_public_false(surface_name, make):
    """``allow_private`` must not be a back door to IMDS.

    The two knobs are deliberately separate so that widening the posture for
    internal backends never silently widens cloud metadata too.
    """
    surface = make()
    try:
        with pytest.raises(BlockedDestinationError) as exc:
            surface.proxy_workflow(
                name="internal",
                proxy_url="http://169.254.169.254/",
                allowed_paths=["*"],
                auth_dependency=_allow,
                require_public_destination=False,
            )
        assert exc.value.reason == "metadata_service"
    finally:
        surface.close()


@pytest.mark.parametrize("surface_name,make", SURFACES)
def test_require_public_destination_blocks_rfc1918(surface_name, make):
    """The opt-IN stricter posture, matching nexus's outbound default."""
    surface = make()
    try:
        with pytest.raises(BlockedDestinationError) as exc:
            surface.proxy_workflow(
                name="internal",
                proxy_url="http://10.1.2.3:8080/",
                allowed_paths=["*"],
                auth_dependency=_allow,
                require_public_destination=True,
            )
        assert exc.value.reason == "private_ipv4"
    finally:
        surface.close()


@pytest.mark.parametrize("surface_name,make", SURFACES)
def test_extra_blocked_networks_are_enforced(surface_name, make):
    surface = make()
    try:
        with pytest.raises(BlockedDestinationError):
            surface.proxy_workflow(
                name="internal",
                proxy_url="http://10.9.9.9:8080/",
                allowed_paths=["*"],
                auth_dependency=_allow,
                blocked_networks=[ipaddress.ip_network("10.9.0.0/16")],
            )
    finally:
        surface.close()


@pytest.mark.parametrize("surface_name,make", SURFACES)
def test_metadata_opt_out_is_explicit_and_loud(surface_name, make, caplog):
    """``security.md`` § Secure-Default: opt-out is explicit AND logged.

    The escape hatch exists, but it cannot be taken silently -- the WARNING
    names the protection being disabled.
    """
    surface = make()
    try:
        with caplog.at_level("WARNING"):
            surface.proxy_workflow(
                name="internal",
                proxy_url="http://169.254.169.254/",
                allowed_paths=["*"],
                auth_dependency=_allow,
                allow_metadata_destination=True,
            )
        assert "internal" in surface.workflows
        assert any(
            "allow_metadata_destination=True" in r.getMessage() for r in caplog.records
        ), "opt-out was silent -- no WARNING named the disabled protection"
    finally:
        surface.close()


def test_gateway_checks_every_backend_not_just_the_primary():
    """Round-robin means the caller cannot choose which backend serves them.

    Checking only ``primary_url`` would leave the second and later entries
    unconstrained -- the same partial-coverage shape the credential-forwarding
    defect had on this surface before #2025.
    """
    gw = _make_gateway()
    try:
        with pytest.raises(BlockedDestinationError) as exc:
            gw.proxy_workflow(
                name="internal",
                proxy_url="http://10.1.2.3:8080/,http://169.254.169.254/",
                allowed_paths=["*"],
                auth_dependency=_allow,
            )
        assert exc.value.reason == "metadata_service"
        assert "internal" not in gw.workflows
    finally:
        gw.close()


def test_api_channel_plumbs_the_destination_controls():
    """``security.md`` § Multi-Site Kwarg Plumbing.

    ``APIChannel.proxy_workflow`` delegates to ``WorkflowServer``; a gate that
    is unconfigurable through the channel is a gate that gets worked around.
    """
    import inspect

    from kailash.channels.api_channel import APIChannel

    params = inspect.signature(APIChannel.proxy_workflow).parameters
    for kwarg in (
        "blocked_networks",
        "allow_metadata_destination",
        "require_public_destination",
    ):
        assert kwarg in params, f"APIChannel.proxy_workflow does not plumb {kwarg}"

    source = inspect.getsource(APIChannel.proxy_workflow)
    for kwarg in (
        "blocked_networks",
        "allow_metadata_destination",
        "require_public_destination",
    ):
        assert (
            f"{kwarg}={kwarg}" in source
        ), f"APIChannel.proxy_workflow accepts {kwarg} but does not forward it"


# ---------------------------------------------------------------------------
# One implementation, not two
# ---------------------------------------------------------------------------


def test_core_and_nexus_share_one_implementation():
    """#2091's constraint: nexus is the REFERENCE, not a second copy.

    ``kailash-nexus`` depends on ``kailash`` and never the reverse, so the
    shared piece lives in core and nexus imports it. Asserting object identity
    rather than behavioural agreement is deliberate: two copies that agree
    today are exactly the thing that drifts.
    """
    import nexus.http_client as nh

    from kailash.utils import network_guard

    assert nh._core_check_url is network_guard.check_url
    assert nh._DEFAULT_BLOCKED_NETWORKS is network_guard.DEFAULT_BLOCKED_NETWORKS
    assert nh._METADATA_IPS is network_guard.METADATA_IPS
    assert nh._is_private_ipv4 is network_guard.is_private_ipv4
    assert nh._is_private_ipv6 is network_guard.is_private_ipv6
    assert nh._detect_encoded_ip_bypass is network_guard.detect_encoded_ip_bypass


def test_nexus_keeps_its_strict_posture_through_the_shared_guard():
    """The shared guard must not have relaxed nexus's outbound posture.

    Core's proxy permits RFC1918; nexus's outbound client must still refuse
    it. Same implementation, different posture, pinned on both sides.
    """
    from nexus.http_client import InvalidEndpointError, check_url

    with pytest.raises(InvalidEndpointError) as exc:
        check_url("http://10.1.2.3:8080/")
    assert exc.value.reason == "private_ipv4"

    # ...while the core proxy posture accepts exactly that destination.
    reject_unsafe_proxy_destination(
        "http://10.1.2.3:8080/", name="n", surface="test"
    )


def test_unresolvable_destination_is_permitted_but_loud(caplog):
    """A stated limit, asserted so it cannot silently become fail-closed.

    A backend legitimately is not up yet at registration. Refusing there makes
    the control one deployments route around, so registration proceeds -- and
    the WARNING names the destination as unchecked so the gap is visible.
    """
    with caplog.at_level("WARNING"):
        reject_unsafe_proxy_destination(
            "http://no-such-host.invalid.example/",
            name="unresolved",
            surface="test",
        )
    assert any(
        "could not be resolved" in r.getMessage() for r in caplog.records
    ), "unresolvable destination was permitted SILENTLY"
