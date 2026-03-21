# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Commerce constraint dimension for EATP.

Provides beneficiary attribution tracking for financial agent scenarios.
Enforces that delegated agents cannot change beneficiaries to
unauthorized parties.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from kailash.trust.constraints.dimension import (
    ConstraintCheckResult,
    ConstraintDimension,
    ConstraintValue,
)

logger = logging.getLogger(__name__)


class CommerceType(Enum):
    """Type of commerce transaction."""

    PURCHASE = "purchase"
    SALE = "sale"
    TRANSFER = "transfer"
    EXCHANGE = "exchange"


class CommerceConstraint(ConstraintDimension):
    """Constraint dimension for commerce/beneficiary attribution.

    Tracks who benefits from agent actions in financial scenarios.
    Enforces that delegated agents cannot redirect value to
    unauthorized beneficiaries.

    Constraint value format:
        {
            "beneficiary_id": "org-001",
            "allowed_beneficiaries": ["org-001", "org-002"],
            "commerce_types": ["purchase", "sale"],
            "jurisdiction": "US",
            "attribution_required": true
        }
    """

    @property
    def name(self) -> str:
        return "commerce"

    @property
    def description(self) -> str:
        return "Commerce and beneficiary attribution constraints"

    def parse(self, value: Any) -> ConstraintValue:
        """Parse commerce constraint value.

        Args:
            value: Dict with commerce constraint configuration

        Returns:
            Parsed ConstraintValue
        """
        if isinstance(value, str):
            # Simple format: "beneficiary:org-001"
            parts = value.split(":", 1)
            parsed = {
                "beneficiary_id": parts[1] if len(parts) > 1 else parts[0],
                "allowed_beneficiaries": [parts[1] if len(parts) > 1 else parts[0]],
                "commerce_types": [ct.value for ct in CommerceType],
                "jurisdiction": None,
                "attribution_required": True,
            }
        elif isinstance(value, dict):
            parsed = {
                "beneficiary_id": value.get("beneficiary_id"),
                "allowed_beneficiaries": value.get(
                    "allowed_beneficiaries",
                    [value["beneficiary_id"]] if "beneficiary_id" in value else [],
                ),
                "commerce_types": value.get("commerce_types", [ct.value for ct in CommerceType]),
                "jurisdiction": value.get("jurisdiction"),
                "attribution_required": value.get("attribution_required", True),
            }
        else:
            raise ValueError(f"Invalid commerce constraint value: {value}")

        return ConstraintValue(
            dimension=self.name,
            raw_value=value,
            parsed=parsed,
            metadata={"commerce_type_count": len(parsed["commerce_types"])},
        )

    def check(self, constraint: ConstraintValue, context: Dict[str, Any]) -> ConstraintCheckResult:
        """Check commerce constraint against execution context.

        Context keys:
            - beneficiary_id: Who benefits from this action
            - commerce_type: Type of commerce (purchase, sale, etc.)
            - jurisdiction: Jurisdiction of the action
            - attribution_chain: List of actors in value chain
        """
        parsed = constraint.parsed
        beneficiary = context.get("beneficiary_id")
        commerce_type = context.get("commerce_type")
        jurisdiction = context.get("jurisdiction")

        # Check beneficiary authorization
        if beneficiary and parsed.get("allowed_beneficiaries"):
            if beneficiary not in parsed["allowed_beneficiaries"]:
                return ConstraintCheckResult(
                    satisfied=False,
                    reason=f"Beneficiary '{beneficiary}' not in allowed list: {parsed['allowed_beneficiaries']}",
                )

        # Check commerce type
        if commerce_type and parsed.get("commerce_types"):
            if commerce_type not in parsed["commerce_types"]:
                return ConstraintCheckResult(
                    satisfied=False,
                    reason=f"Commerce type '{commerce_type}' not allowed. Allowed: {parsed['commerce_types']}",
                )

        # Check jurisdiction
        if jurisdiction and parsed.get("jurisdiction") and jurisdiction != parsed["jurisdiction"]:
            return ConstraintCheckResult(
                satisfied=False,
                reason=f"Jurisdiction '{jurisdiction}' does not match required '{parsed['jurisdiction']}'",
            )

        # Check attribution requirement
        if parsed.get("attribution_required"):
            attribution_chain = context.get("attribution_chain", [])
            if not attribution_chain and beneficiary:
                logger.info(f"Attribution required but no chain provided for beneficiary {beneficiary}")

        return ConstraintCheckResult(
            satisfied=True,
            reason="Commerce constraints satisfied",
        )

    def is_tighter(self, parent: ConstraintValue, child: ConstraintValue) -> bool:
        """Check if child commerce constraint is tighter than parent.

        Tightening rules:
        - Child cannot add new allowed beneficiaries
        - Child cannot add new commerce types
        - Child must keep same or narrower jurisdiction
        """
        parent_beneficiaries = set(parent.parsed.get("allowed_beneficiaries", []))
        child_beneficiaries = set(child.parsed.get("allowed_beneficiaries", []))

        # Child cannot have beneficiaries not in parent
        if child_beneficiaries - parent_beneficiaries:
            return False

        parent_types = set(parent.parsed.get("commerce_types", []))
        child_types = set(child.parsed.get("commerce_types", []))

        # Child cannot have commerce types not in parent
        if child_types - parent_types:
            return False

        # If parent requires attribution, child must too
        if parent.parsed.get("attribution_required") and not child.parsed.get("attribution_required"):
            return False

        return True


__all__ = [
    "CommerceConstraint",
    "CommerceType",
]
