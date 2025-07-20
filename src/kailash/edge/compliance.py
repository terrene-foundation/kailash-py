"""Compliance-aware routing for data sovereignty and regulatory requirements."""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .location import ComplianceZone, EdgeLocation, EdgeRegion, GeographicCoordinates

logger = logging.getLogger(__name__)


class DataClassification(Enum):
    """Data classification levels for compliance routing."""

    PUBLIC = "public"  # No restrictions
    INTERNAL = "internal"  # Organization internal
    CONFIDENTIAL = "confidential"  # Restricted access
    RESTRICTED = "restricted"  # Highly restricted

    # Personal data types
    PII = "pii"  # Personally Identifiable Information
    PHI = "phi"  # Protected Health Information
    PCI = "pci"  # Payment Card Information

    # Industry-specific
    FINANCIAL = "financial"  # Financial data
    HEALTHCARE = "healthcare"  # Healthcare data
    EDUCATIONAL = "educational"  # Educational records

    # Regional data types
    EU_PERSONAL = "eu_personal"  # GDPR-protected data
    CALIFORNIA_RESIDENT = "california_resident"  # CCPA-protected data
    CANADIAN_PERSONAL = "canadian_personal"  # PIPEDA-protected data


class ComplianceRule(Enum):
    """Compliance rules and requirements."""

    # Geographic restrictions
    DATA_RESIDENCY = "data_residency"  # Data must stay in specific region
    CROSS_BORDER_TRANSFER = "cross_border_transfer"  # Restrictions on transfers

    # Encryption requirements
    ENCRYPTION_AT_REST = "encryption_at_rest"
    ENCRYPTION_IN_TRANSIT = "encryption_in_transit"
    KEY_MANAGEMENT = "key_management"

    # Access controls
    RBAC_REQUIRED = "rbac_required"  # Role-based access control
    MFA_REQUIRED = "mfa_required"  # Multi-factor authentication
    AUDIT_LOGGING = "audit_logging"

    # Data lifecycle
    RETENTION_PERIOD = "retention_period"
    RIGHT_TO_DELETE = "right_to_delete"  # GDPR Article 17
    DATA_PORTABILITY = "data_portability"  # GDPR Article 20

    # Industry-specific
    HIPAA_SAFEGUARDS = "hipaa_safeguards"
    SOX_CONTROLS = "sox_controls"
    PCI_DSS_REQUIREMENTS = "pci_dss_requirements"


@dataclass
class ComplianceRequirement:
    """Specific compliance requirement with enforcement details."""

    rule: ComplianceRule
    description: str
    enforcement_level: str  # "required", "recommended", "optional"
    applicable_data_types: List[DataClassification]
    applicable_regions: List[EdgeRegion] = None
    exceptions: List[str] = None

    def __post_init__(self):
        if self.applicable_regions is None:
            self.applicable_regions = []
        if self.exceptions is None:
            self.exceptions = []


@dataclass
class ComplianceContext:
    """Context for compliance routing decisions."""

    # Data characteristics
    data_classification: DataClassification
    data_size_gb: float = 0.0
    contains_personal_data: bool = False
    subject_countries: List[str] = None  # ISO country codes

    # User context
    user_location: Optional[GeographicCoordinates] = None
    user_citizenship: Optional[str] = None  # ISO country code
    user_residence: Optional[str] = None  # ISO country code

    # Operation context
    operation_type: str = "read"  # "read", "write", "process", "store"
    retention_period_days: Optional[int] = None
    sharing_scope: str = "internal"  # "internal", "third_party", "public"

    # Compliance overrides
    explicit_compliance_zones: List[ComplianceZone] = None
    override_data_residency: bool = False

    def __post_init__(self):
        if self.subject_countries is None:
            self.subject_countries = []
        if self.explicit_compliance_zones is None:
            self.explicit_compliance_zones = []


@dataclass
class ComplianceDecision:
    """Result of compliance routing decision."""

    allowed_locations: List[EdgeLocation]
    prohibited_locations: List[EdgeLocation]
    recommended_location: Optional[EdgeLocation]

    # Decision reasoning
    compliance_requirements: List[ComplianceRequirement]
    applied_rules: List[str]
    warnings: List[str]
    violations: List[str]

    # Metadata
    decision_timestamp: datetime
    decision_confidence: float  # 0.0 to 1.0

    def __post_init__(self):
        if self.decision_timestamp is None:
            self.decision_timestamp = datetime.now(UTC)


class ComplianceRouter:
    """Compliance-aware router for data sovereignty and regulatory requirements.

    Routes data processing requests to appropriate edge locations based on
    regulatory compliance requirements and data classification.
    """

    def __init__(self):
        """Initialize compliance router with standard rules."""
        self.compliance_rules = self._load_default_compliance_rules()
        self.country_to_region_mapping = self._load_country_region_mapping()
        self.audit_log: List[Dict] = []

        logger.info("Initialized ComplianceRouter with standard compliance rules")

    def _load_default_compliance_rules(
        self,
    ) -> Dict[ComplianceZone, List[ComplianceRequirement]]:
        """Load default compliance rules for each zone."""
        rules = {
            ComplianceZone.GDPR: [
                ComplianceRequirement(
                    rule=ComplianceRule.DATA_RESIDENCY,
                    description="Personal data of EU residents must be processed within EU/EEA",
                    enforcement_level="required",
                    applicable_data_types=[
                        DataClassification.PII,
                        DataClassification.EU_PERSONAL,
                    ],
                    applicable_regions=[
                        EdgeRegion.EU_WEST,
                        EdgeRegion.EU_CENTRAL,
                        EdgeRegion.EU_NORTH,
                    ],
                ),
                ComplianceRequirement(
                    rule=ComplianceRule.RIGHT_TO_DELETE,
                    description="Data subjects have right to erasure (Article 17)",
                    enforcement_level="required",
                    applicable_data_types=[
                        DataClassification.PII,
                        DataClassification.EU_PERSONAL,
                    ],
                ),
                ComplianceRequirement(
                    rule=ComplianceRule.ENCRYPTION_AT_REST,
                    description="Personal data must be encrypted at rest",
                    enforcement_level="required",
                    applicable_data_types=[
                        DataClassification.PII,
                        DataClassification.EU_PERSONAL,
                    ],
                ),
                ComplianceRequirement(
                    rule=ComplianceRule.AUDIT_LOGGING,
                    description="All data processing must be logged for accountability",
                    enforcement_level="required",
                    applicable_data_types=[
                        DataClassification.PII,
                        DataClassification.EU_PERSONAL,
                    ],
                ),
            ],
            ComplianceZone.CCPA: [
                ComplianceRequirement(
                    rule=ComplianceRule.DATA_RESIDENCY,
                    description="California residents' data should be processed in compliant facilities",
                    enforcement_level="recommended",
                    applicable_data_types=[DataClassification.CALIFORNIA_RESIDENT],
                    applicable_regions=[EdgeRegion.US_WEST],
                ),
                ComplianceRequirement(
                    rule=ComplianceRule.RIGHT_TO_DELETE,
                    description="Consumers have right to delete personal information",
                    enforcement_level="required",
                    applicable_data_types=[DataClassification.CALIFORNIA_RESIDENT],
                ),
                ComplianceRequirement(
                    rule=ComplianceRule.DATA_PORTABILITY,
                    description="Consumers have right to data portability",
                    enforcement_level="required",
                    applicable_data_types=[DataClassification.CALIFORNIA_RESIDENT],
                ),
            ],
            ComplianceZone.HIPAA: [
                ComplianceRequirement(
                    rule=ComplianceRule.ENCRYPTION_AT_REST,
                    description="PHI must be encrypted at rest",
                    enforcement_level="required",
                    applicable_data_types=[
                        DataClassification.PHI,
                        DataClassification.HEALTHCARE,
                    ],
                ),
                ComplianceRequirement(
                    rule=ComplianceRule.ENCRYPTION_IN_TRANSIT,
                    description="PHI must be encrypted in transit",
                    enforcement_level="required",
                    applicable_data_types=[
                        DataClassification.PHI,
                        DataClassification.HEALTHCARE,
                    ],
                ),
                ComplianceRequirement(
                    rule=ComplianceRule.AUDIT_LOGGING,
                    description="All PHI access must be logged",
                    enforcement_level="required",
                    applicable_data_types=[
                        DataClassification.PHI,
                        DataClassification.HEALTHCARE,
                    ],
                ),
                ComplianceRequirement(
                    rule=ComplianceRule.MFA_REQUIRED,
                    description="Multi-factor authentication required for PHI access",
                    enforcement_level="required",
                    applicable_data_types=[
                        DataClassification.PHI,
                        DataClassification.HEALTHCARE,
                    ],
                ),
            ],
            ComplianceZone.PCI_DSS: [
                ComplianceRequirement(
                    rule=ComplianceRule.ENCRYPTION_AT_REST,
                    description="Cardholder data must be encrypted at rest",
                    enforcement_level="required",
                    applicable_data_types=[DataClassification.PCI],
                ),
                ComplianceRequirement(
                    rule=ComplianceRule.ENCRYPTION_IN_TRANSIT,
                    description="Cardholder data must be encrypted in transit",
                    enforcement_level="required",
                    applicable_data_types=[DataClassification.PCI],
                ),
                ComplianceRequirement(
                    rule=ComplianceRule.RBAC_REQUIRED,
                    description="Role-based access control required",
                    enforcement_level="required",
                    applicable_data_types=[DataClassification.PCI],
                ),
            ],
            ComplianceZone.SOX: [
                ComplianceRequirement(
                    rule=ComplianceRule.AUDIT_LOGGING,
                    description="All financial data access must be logged",
                    enforcement_level="required",
                    applicable_data_types=[DataClassification.FINANCIAL],
                ),
                ComplianceRequirement(
                    rule=ComplianceRule.RETENTION_PERIOD,
                    description="Financial records must be retained for 7 years",
                    enforcement_level="required",
                    applicable_data_types=[DataClassification.FINANCIAL],
                ),
            ],
            ComplianceZone.PUBLIC: [
                ComplianceRequirement(
                    rule=ComplianceRule.ENCRYPTION_IN_TRANSIT,
                    description="Data should be encrypted in transit",
                    enforcement_level="recommended",
                    applicable_data_types=[
                        DataClassification.PUBLIC,
                        DataClassification.INTERNAL,
                    ],
                )
            ],
        }

        return rules

    def _load_country_region_mapping(self) -> Dict[str, EdgeRegion]:
        """Load mapping of ISO country codes to edge regions."""
        return {
            # North America
            "US": EdgeRegion.US_EAST,  # Default US region
            "CA": EdgeRegion.CANADA,
            # Europe
            "DE": EdgeRegion.EU_CENTRAL,
            "FR": EdgeRegion.EU_WEST,
            "GB": EdgeRegion.UK,
            "IE": EdgeRegion.EU_WEST,
            "NL": EdgeRegion.EU_WEST,
            "ES": EdgeRegion.EU_WEST,
            "IT": EdgeRegion.EU_WEST,
            "SE": EdgeRegion.EU_NORTH,
            "NO": EdgeRegion.EU_NORTH,
            "FI": EdgeRegion.EU_NORTH,
            "DK": EdgeRegion.EU_NORTH,
            # Asia Pacific
            "JP": EdgeRegion.JAPAN,
            "SG": EdgeRegion.ASIA_SOUTHEAST,
            "AU": EdgeRegion.AUSTRALIA,
            "KR": EdgeRegion.ASIA_EAST,
            "HK": EdgeRegion.ASIA_EAST,
            "IN": EdgeRegion.ASIA_SOUTH,
            "TH": EdgeRegion.ASIA_SOUTHEAST,
            "MY": EdgeRegion.ASIA_SOUTHEAST,
            "ID": EdgeRegion.ASIA_SOUTHEAST,
            # Other regions
            "BR": EdgeRegion.SOUTH_AMERICA,
            "MX": EdgeRegion.SOUTH_AMERICA,
            "ZA": EdgeRegion.AFRICA,
            "AE": EdgeRegion.MIDDLE_EAST,
            "SA": EdgeRegion.MIDDLE_EAST,
        }

    async def route_compliant(
        self, context: ComplianceContext, available_locations: List[EdgeLocation]
    ) -> ComplianceDecision:
        """Route data processing to compliant edge locations.

        Args:
            context: Compliance context with data and user information
            available_locations: List of available edge locations

        Returns:
            Compliance decision with allowed/prohibited locations
        """
        logger.info(
            f"Routing compliance decision for {context.data_classification.value} data"
        )

        # Determine applicable compliance zones
        applicable_zones = self._determine_applicable_zones(context)

        # Get compliance requirements
        requirements = self._get_compliance_requirements(applicable_zones, context)

        # Evaluate each location
        allowed_locations = []
        prohibited_locations = []
        violations = []
        warnings = []
        applied_rules = []

        for location in available_locations:
            evaluation = await self._evaluate_location_compliance(
                location, context, requirements
            )

            if evaluation["compliant"]:
                allowed_locations.append(location)
            else:
                prohibited_locations.append(location)
                violations.extend(evaluation["violations"])

            warnings.extend(evaluation["warnings"])
            applied_rules.extend(evaluation["applied_rules"])

        # Select recommended location
        recommended_location = self._select_recommended_location(
            allowed_locations, context, requirements
        )

        # Calculate decision confidence
        confidence = self._calculate_decision_confidence(
            len(allowed_locations), len(prohibited_locations), len(violations)
        )

        decision = ComplianceDecision(
            allowed_locations=allowed_locations,
            prohibited_locations=prohibited_locations,
            recommended_location=recommended_location,
            compliance_requirements=requirements,
            applied_rules=list(set(applied_rules)),
            warnings=list(set(warnings)),
            violations=list(set(violations)),
            decision_timestamp=datetime.now(UTC),
            decision_confidence=confidence,
        )

        # Log decision for audit trail
        await self._log_compliance_decision(context, decision)

        logger.info(
            f"Compliance routing: {len(allowed_locations)} allowed, "
            f"{len(prohibited_locations)} prohibited locations"
        )

        return decision

    def _determine_applicable_zones(
        self, context: ComplianceContext
    ) -> List[ComplianceZone]:
        """Determine which compliance zones apply to the data and context."""
        zones = []

        # Explicit zones override everything
        if context.explicit_compliance_zones:
            return context.explicit_compliance_zones

        # Data classification-based zones
        if context.data_classification in [
            DataClassification.PII,
            DataClassification.EU_PERSONAL,
        ]:
            # Check if EU resident data
            if any(
                country
                in [
                    "DE",
                    "FR",
                    "IT",
                    "ES",
                    "NL",
                    "BE",
                    "AT",
                    "SE",
                    "DK",
                    "FI",
                    "IE",
                    "PT",
                    "GR",
                    "LU",
                    "MT",
                    "CY",
                    "EE",
                    "LV",
                    "LT",
                    "SI",
                    "SK",
                    "HR",
                    "BG",
                    "RO",
                    "HU",
                    "CZ",
                    "PL",
                ]
                for country in context.subject_countries
            ):
                zones.append(ComplianceZone.GDPR)

        if context.data_classification == DataClassification.CALIFORNIA_RESIDENT:
            zones.append(ComplianceZone.CCPA)

        if context.data_classification in [
            DataClassification.PHI,
            DataClassification.HEALTHCARE,
        ]:
            zones.append(ComplianceZone.HIPAA)

        if context.data_classification == DataClassification.PCI:
            zones.append(ComplianceZone.PCI_DSS)

        if context.data_classification == DataClassification.FINANCIAL:
            zones.append(ComplianceZone.SOX)

        # Geographic-based zones
        if context.user_location:
            # Add region-specific compliance based on user location
            pass  # Could add geo-based logic here

        # Default to public if no specific zones identified
        if not zones:
            zones.append(ComplianceZone.PUBLIC)

        return zones

    def _get_compliance_requirements(
        self, zones: List[ComplianceZone], context: ComplianceContext
    ) -> List[ComplianceRequirement]:
        """Get all compliance requirements for the given zones and context."""
        requirements = []

        for zone in zones:
            zone_requirements = self.compliance_rules.get(zone, [])
            for requirement in zone_requirements:
                # Check if requirement applies to this data type
                if context.data_classification in requirement.applicable_data_types:
                    requirements.append(requirement)

        return requirements

    async def _evaluate_location_compliance(
        self,
        location: EdgeLocation,
        context: ComplianceContext,
        requirements: List[ComplianceRequirement],
    ) -> Dict[str, Any]:
        """Evaluate if a location meets compliance requirements."""
        compliant = True
        violations = []
        warnings = []
        applied_rules = []

        for requirement in requirements:
            rule_result = await self._evaluate_compliance_rule(
                location, context, requirement
            )

            applied_rules.append(requirement.rule.value)

            if not rule_result["compliant"]:
                if requirement.enforcement_level == "required":
                    compliant = False
                    violations.append(rule_result["message"])
                else:
                    warnings.append(rule_result["message"])

        return {
            "compliant": compliant,
            "violations": violations,
            "warnings": warnings,
            "applied_rules": applied_rules,
        }

    async def _evaluate_compliance_rule(
        self,
        location: EdgeLocation,
        context: ComplianceContext,
        requirement: ComplianceRequirement,
    ) -> Dict[str, Any]:
        """Evaluate a specific compliance rule for a location."""
        rule = requirement.rule

        if rule == ComplianceRule.DATA_RESIDENCY:
            return await self._check_data_residency(location, context, requirement)
        elif rule == ComplianceRule.ENCRYPTION_AT_REST:
            return self._check_encryption_at_rest(location, requirement)
        elif rule == ComplianceRule.ENCRYPTION_IN_TRANSIT:
            return self._check_encryption_in_transit(location, requirement)
        elif rule == ComplianceRule.AUDIT_LOGGING:
            return self._check_audit_logging(location, requirement)
        elif rule == ComplianceRule.MFA_REQUIRED:
            return self._check_mfa_support(location, requirement)
        elif rule == ComplianceRule.RBAC_REQUIRED:
            return self._check_rbac_support(location, requirement)
        else:
            # Default pass for unimplemented rules
            return {"compliant": True, "message": f"Rule {rule.value} not evaluated"}

    async def _check_data_residency(
        self,
        location: EdgeLocation,
        context: ComplianceContext,
        requirement: ComplianceRequirement,
    ) -> Dict[str, Any]:
        """Check data residency compliance."""
        if context.override_data_residency:
            return {
                "compliant": True,
                "message": "Data residency requirement overridden",
            }

        # Check if location region is in allowed regions
        if requirement.applicable_regions:
            if location.region not in requirement.applicable_regions:
                return {
                    "compliant": False,
                    "message": f"Data residency violation: {location.region.value} not in allowed regions {[r.value for r in requirement.applicable_regions]}",
                }

        return {"compliant": True, "message": "Data residency requirement met"}

    def _check_encryption_at_rest(
        self, location: EdgeLocation, requirement: ComplianceRequirement
    ) -> Dict[str, Any]:
        """Check encryption at rest support."""
        if location.capabilities.encryption_at_rest:
            return {"compliant": True, "message": "Encryption at rest supported"}
        else:
            return {"compliant": False, "message": "Encryption at rest not supported"}

    def _check_encryption_in_transit(
        self, location: EdgeLocation, requirement: ComplianceRequirement
    ) -> Dict[str, Any]:
        """Check encryption in transit support."""
        if location.capabilities.encryption_in_transit:
            return {"compliant": True, "message": "Encryption in transit supported"}
        else:
            return {
                "compliant": False,
                "message": "Encryption in transit not supported",
            }

    def _check_audit_logging(
        self, location: EdgeLocation, requirement: ComplianceRequirement
    ) -> Dict[str, Any]:
        """Check audit logging support."""
        if location.capabilities.audit_logging:
            return {"compliant": True, "message": "Audit logging supported"}
        else:
            return {"compliant": False, "message": "Audit logging not supported"}

    def _check_mfa_support(
        self, location: EdgeLocation, requirement: ComplianceRequirement
    ) -> Dict[str, Any]:
        """Check multi-factor authentication support."""
        # For now, assume all locations support MFA
        return {"compliant": True, "message": "MFA support available"}

    def _check_rbac_support(
        self, location: EdgeLocation, requirement: ComplianceRequirement
    ) -> Dict[str, Any]:
        """Check role-based access control support."""
        # For now, assume all locations support RBAC
        return {"compliant": True, "message": "RBAC support available"}

    def _select_recommended_location(
        self,
        allowed_locations: List[EdgeLocation],
        context: ComplianceContext,
        requirements: List[ComplianceRequirement],
    ) -> Optional[EdgeLocation]:
        """Select the best recommended location from allowed locations."""
        if not allowed_locations:
            return None

        if len(allowed_locations) == 1:
            return allowed_locations[0]

        # Simple scoring: prefer locations with better compliance coverage
        def score_location(location):
            score = 0

            # Prefer locations with more compliance zones
            score += len(location.compliance_zones) * 10

            # Prefer locations closer to user (if known)
            if context.user_location:
                distance = location.coordinates.distance_to(context.user_location)
                score += max(0, 1000 - distance)  # Closer = higher score

            # Prefer locations with better health
            if location.is_healthy:
                score += 100

            # Prefer locations with lower load
            score += (1.0 - location.get_load_factor()) * 50

            return score

        # Return location with highest score
        return max(allowed_locations, key=score_location)

    def _calculate_decision_confidence(
        self, allowed_count: int, prohibited_count: int, violation_count: int
    ) -> float:
        """Calculate confidence in the compliance decision."""
        total_locations = allowed_count + prohibited_count

        if total_locations == 0:
            return 0.0

        # Base confidence on ratio of allowed to total
        base_confidence = allowed_count / total_locations

        # Reduce confidence if violations found
        violation_penalty = min(0.3, violation_count * 0.1)

        # Ensure we have at least one allowed location for high confidence
        if allowed_count == 0:
            confidence = 0.0
        elif allowed_count >= 3:
            confidence = min(1.0, base_confidence - violation_penalty + 0.2)
        else:
            confidence = base_confidence - violation_penalty

        return max(0.0, min(1.0, confidence))

    async def _log_compliance_decision(
        self, context: ComplianceContext, decision: ComplianceDecision
    ):
        """Log compliance decision for audit trail."""
        audit_entry = {
            "timestamp": decision.decision_timestamp.isoformat(),
            "data_classification": context.data_classification.value,
            "operation_type": context.operation_type,
            "allowed_locations": [
                loc.location_id for loc in decision.allowed_locations
            ],
            "prohibited_locations": [
                loc.location_id for loc in decision.prohibited_locations
            ],
            "recommended_location": (
                decision.recommended_location.location_id
                if decision.recommended_location
                else None
            ),
            "violations": decision.violations,
            "confidence": decision.decision_confidence,
            "compliance_zones": (
                [zone.value for zone in context.explicit_compliance_zones]
                if context.explicit_compliance_zones
                else []
            ),
            "subject_countries": context.subject_countries,
        }

        self.audit_log.append(audit_entry)

        # Keep only last 1000 entries to prevent memory growth
        if len(self.audit_log) > 1000:
            self.audit_log = self.audit_log[-1000:]

    def classify_data(self, data: Dict[str, Any]) -> DataClassification:
        """Automatically classify data based on content patterns."""
        # Simple pattern-based classification
        data_str = json.dumps(data).lower()

        # Check for PII patterns
        pii_patterns = ["email", "ssn", "social_security", "phone", "address", "name"]
        if any(pattern in data_str for pattern in pii_patterns):
            return DataClassification.PII

        # Check for healthcare patterns
        health_patterns = ["medical", "diagnosis", "treatment", "patient", "health"]
        if any(pattern in data_str for pattern in health_patterns):
            return DataClassification.PHI

        # Check for payment patterns
        payment_patterns = ["credit_card", "card_number", "cvv", "payment", "billing"]
        if any(pattern in data_str for pattern in payment_patterns):
            return DataClassification.PCI

        # Check for financial patterns (but not payment patterns)
        financial_patterns = ["account_number", "routing", "bank", "financial"]
        if any(pattern in data_str for pattern in financial_patterns) and not any(
            pattern in data_str for pattern in payment_patterns
        ):
            return DataClassification.FINANCIAL

        # Default to public
        return DataClassification.PUBLIC

    def get_applicable_regulations(
        self, data_classification: DataClassification
    ) -> List[ComplianceZone]:
        """Get applicable regulations for a data classification."""
        regulations = []

        classification_mapping = {
            DataClassification.PII: [ComplianceZone.GDPR, ComplianceZone.CCPA],
            DataClassification.EU_PERSONAL: [ComplianceZone.GDPR],
            DataClassification.CALIFORNIA_RESIDENT: [ComplianceZone.CCPA],
            DataClassification.PHI: [ComplianceZone.HIPAA],
            DataClassification.PCI: [ComplianceZone.PCI_DSS],
            DataClassification.FINANCIAL: [ComplianceZone.SOX],
            DataClassification.PUBLIC: [ComplianceZone.PUBLIC],
        }

        return classification_mapping.get(data_classification, [ComplianceZone.PUBLIC])

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent compliance decisions from audit log."""
        return self.audit_log[-limit:]

    def is_compliant_location(
        self,
        location: "EdgeLocation",
        data_class: DataClassification,
        required_zones: List[str],
    ) -> bool:
        """Check if a location is compliant for given data class and zones.

        Args:
            location: Edge location to check
            data_class: Classification of the data
            required_zones: Required compliance zones

        Returns:
            True if location is compliant
        """
        # Avoid circular import
        from kailash.edge.location import EdgeRegion

        # Check if location has all required compliance zones
        location_zones = [z.value for z in location.compliance_zones]

        # For GDPR compliance, PII/EU_PERSONAL data must be in EU regions or GDPR-compliant zones
        if "gdpr" in required_zones and data_class in [
            DataClassification.PII,
            DataClassification.EU_PERSONAL,
        ]:
            # Check if location has GDPR compliance zone
            return "gdpr" in location_zones

        # For other cases, check if location has the required zones
        return all(zone in location_zones for zone in required_zones)

    def get_compliance_summary(self) -> Dict[str, Any]:
        """Get summary of compliance decisions and performance."""
        if not self.audit_log:
            return {
                "total_decisions": 0,
                "compliance_rate": 1.0,
                "common_violations": [],
                "data_classifications": {},
            }

        total_decisions = len(self.audit_log)
        decisions_with_violations = sum(
            1 for entry in self.audit_log if entry["violations"]
        )
        compliance_rate = 1.0 - (decisions_with_violations / total_decisions)

        # Analyze common violations
        all_violations = []
        for entry in self.audit_log:
            all_violations.extend(entry["violations"])

        violation_counts = {}
        for violation in all_violations:
            violation_counts[violation] = violation_counts.get(violation, 0) + 1

        common_violations = sorted(
            violation_counts.items(), key=lambda x: x[1], reverse=True
        )[:5]

        # Analyze data classifications
        classification_counts = {}
        for entry in self.audit_log:
            classification = entry["data_classification"]
            classification_counts[classification] = (
                classification_counts.get(classification, 0) + 1
            )

        return {
            "total_decisions": total_decisions,
            "compliance_rate": compliance_rate,
            "common_violations": [
                {"violation": v[0], "count": v[1]} for v in common_violations
            ],
            "data_classifications": classification_counts,
            "average_confidence": sum(entry["confidence"] for entry in self.audit_log)
            / total_decisions,
        }
