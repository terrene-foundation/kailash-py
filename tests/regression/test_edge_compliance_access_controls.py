"""Regression: the MFA and RBAC compliance checks were hardcoded to pass.

``ComplianceRouter._check_mfa_support`` and ``_check_rbac_support`` both read::

    # For now, assume all locations support MFA
    return {"compliant": True, "message": "MFA support available"}

They ignored both of their arguments, so a HIPAA (MFA_REQUIRED) or PCI-DSS
(RBAC_REQUIRED) route certified EVERY location as meeting the control — a
fail-open authorization check reachable from the public ``route_compliant``
path. ``EdgeCapabilities`` carried no field either check could have read.

Both poles are pinned here: a location that DECLARES the control is allowed, a
location that does not is prohibited. Without the fix the prohibited pole is
allowed and every assertion below about ``prohibited_locations`` fails.
"""

import pytest

from kailash.edge.compliance import (
    ComplianceContext,
    ComplianceRouter,
    ComplianceZone,
    DataClassification,
)
from kailash.edge.location import (
    EdgeCapabilities,
    EdgeLocation,
    EdgeRegion,
    GeographicCoordinates,
)


def _location(location_id: str, **capability_overrides) -> EdgeLocation:
    """A US-East location whose only varying axis is the access-control set."""
    return EdgeLocation(
        location_id=location_id,
        name=location_id,
        region=EdgeRegion.US_EAST,
        coordinates=GeographicCoordinates(39.0458, -77.5081),
        capabilities=EdgeCapabilities(
            cpu_cores=8,
            memory_gb=32,
            storage_gb=500,
            **capability_overrides,
        ),
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_phi_route_prohibits_a_location_without_mfa():
    """HIPAA requires MFA; a location that does not declare it is NOT compliant."""
    with_mfa = _location("us-east-mfa", mfa_supported=True)
    without_mfa = _location("us-east-no-mfa")  # fail-closed default

    decision = await ComplianceRouter().route_compliant(
        ComplianceContext(
            data_classification=DataClassification.PHI,
            explicit_compliance_zones=[ComplianceZone.HIPAA],
        ),
        [with_mfa, without_mfa],
    )

    allowed = {loc.location_id for loc in decision.allowed_locations}
    prohibited = {loc.location_id for loc in decision.prohibited_locations}

    assert allowed == {
        "us-east-mfa"
    }, "a location declaring MFA support must stay allowed for PHI"
    assert prohibited == {
        "us-east-no-mfa"
    }, "a location with no declared MFA support must be prohibited for PHI"
    assert any("MFA" in v for v in decision.violations), decision.violations


@pytest.mark.regression
@pytest.mark.asyncio
async def test_pci_route_prohibits_a_location_without_rbac():
    """PCI-DSS requires RBAC; a location that does not declare it is NOT compliant."""
    with_rbac = _location("us-east-rbac", rbac_supported=True)
    without_rbac = _location("us-east-no-rbac")  # fail-closed default

    decision = await ComplianceRouter().route_compliant(
        ComplianceContext(
            data_classification=DataClassification.PCI,
            explicit_compliance_zones=[ComplianceZone.PCI_DSS],
        ),
        [with_rbac, without_rbac],
    )

    allowed = {loc.location_id for loc in decision.allowed_locations}
    prohibited = {loc.location_id for loc in decision.prohibited_locations}

    assert allowed == {"us-east-rbac"}
    assert prohibited == {"us-east-no-rbac"}
    assert any("RBAC" in v for v in decision.violations), decision.violations


@pytest.mark.regression
def test_capability_round_trip_preserves_every_compliance_control():
    """``to_dict`` omitted the compliance controls, so a round-trip restored the
    permissive default — the same fail-open shape one serializer over."""
    original = _location(
        "us-east-partial",
        encryption_at_rest=False,
        encryption_in_transit=False,
        audit_logging=False,
        mfa_supported=True,
        rbac_supported=True,
    )

    restored = EdgeLocation.from_dict(original.to_dict())

    assert restored.capabilities.encryption_at_rest is False
    assert restored.capabilities.encryption_in_transit is False
    assert restored.capabilities.audit_logging is False
    assert restored.capabilities.mfa_supported is True
    assert restored.capabilities.rbac_supported is True


@pytest.mark.regression
def test_undeclared_access_controls_default_closed():
    """An older payload carrying no access-control keys reads as NOT supported."""
    legacy = {
        "cpu_cores": 4,
        "memory_gb": 16,
        "storage_gb": 100,
    }
    caps = EdgeCapabilities(**legacy)

    assert caps.mfa_supported is False
    assert caps.rbac_supported is False
