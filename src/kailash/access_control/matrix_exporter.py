# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
RBAC Matrix Export and Policy Conflict Detection.

Provides utilities for exporting the current set of RBAC / ABAC
permission rules as a human-readable matrix (roles x resources x
permissions) and for detecting conflicting rules that may lead to
ambiguous access decisions.

Supported export formats: CSV, JSON, Markdown.

Cross-SDK alignment: esperie-enterprise/kailash-rs#84
"""

from __future__ import annotations

import csv
import io
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class PolicyConflict:
    """A detected conflict between two permission rules.

    Attributes:
        rule_id_a: ID of the first conflicting rule.
        rule_id_b: ID of the second conflicting rule.
        resource_type: Resource type where the conflict occurs.
        resource_id: Resource identifier where the conflict occurs.
        permission: The permission that is in conflict.
        description: Human-readable explanation of the conflict.
        severity: ``"high"`` for allow/deny conflicts, ``"medium"`` for
            overlapping conditionals, ``"low"`` for informational.
    """

    rule_id_a: str
    rule_id_b: str
    resource_type: str
    resource_id: str
    permission: str
    description: str
    severity: str = "medium"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id_a": self.rule_id_a,
            "rule_id_b": self.rule_id_b,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "permission": self.permission,
            "description": self.description,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PolicyConflict:
        return cls(
            rule_id_a=str(data["rule_id_a"]),
            rule_id_b=str(data["rule_id_b"]),
            resource_type=str(data["resource_type"]),
            resource_id=str(data["resource_id"]),
            permission=str(data["permission"]),
            description=str(data["description"]),
            severity=str(data.get("severity", "medium")),
        )


@dataclass
class RBACMatrix:
    """The exported RBAC matrix.

    ``matrix[role][resource] = permission_string``

    Attributes:
        matrix: Nested dict  ``role -> resource -> permission_summary``.
        roles: Sorted list of all discovered roles.
        resources: Sorted list of all discovered resources (``type:id``).
        generated_at: UTC timestamp of when the export was generated.
    """

    matrix: Dict[str, Dict[str, str]]
    roles: List[str]
    resources: List[str]
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matrix": {role: dict(perms) for role, perms in self.matrix.items()},
            "roles": list(self.roles),
            "resources": list(self.resources),
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RBACMatrix:
        return cls(
            matrix={
                str(role): {str(k): str(v) for k, v in perms.items()}
                for role, perms in data.get("matrix", {}).items()
            },
            roles=list(data.get("roles", [])),
            resources=list(data.get("resources", [])),
            generated_at=str(
                data.get(
                    "generated_at", datetime.now(timezone.utc).isoformat()
                )
            ),
        )


# ---------------------------------------------------------------------------
# Exporter
# ---------------------------------------------------------------------------


class RBACMatrixExporter:
    """Export RBAC rules as a matrix and detect policy conflicts.

    The exporter works with raw :class:`PermissionRule` objects (from
    ``kailash.access_control``).  It does **not** import or depend on a
    live :class:`AccessControlManager` instance --- you pass rules in
    directly, keeping the exporter decoupled and testable.

    Thread safety is provided via a :class:`threading.Lock`.

    Example::

        from kailash.access_control import PermissionRule, PermissionEffect, NodePermission
        exporter = RBACMatrixExporter()
        exporter.add_rules([rule1, rule2, rule3])
        matrix = exporter.export_matrix()
        csv_text = exporter.to_csv()
        conflicts = exporter.detect_conflicts()

    Args:
        rules: Optional initial list of permission rules.
    """

    def __init__(self, rules: Optional[List[Any]] = None) -> None:
        self._lock = threading.Lock()
        self._rules: List[Any] = []  # PermissionRule objects
        if rules:
            self._rules.extend(rules)

    # -- rule management -----------------------------------------------------

    def add_rules(self, rules: List[Any]) -> None:
        """Add permission rules to the exporter.

        Args:
            rules: List of ``PermissionRule`` objects.
        """
        with self._lock:
            self._rules.extend(rules)

    def set_rules(self, rules: List[Any]) -> None:
        """Replace all rules with the given list.

        Args:
            rules: List of ``PermissionRule`` objects.
        """
        with self._lock:
            self._rules = list(rules)

    # -- matrix export -------------------------------------------------------

    def export_matrix(self) -> RBACMatrix:
        """Build the roles x resources x permissions matrix.

        Each cell contains a summary string such as ``"allow"``,
        ``"deny"``, ``"allow (conditional)"``, or ``"allow,deny"`` when
        conflicting rules exist for the same role/resource pair.

        Returns:
            :class:`RBACMatrix` with the full matrix, role list, and
            resource list.
        """
        with self._lock:
            rules = list(self._rules)

        # Collect all roles and resources
        roles: Set[str] = set()
        resources: Set[str] = set()

        for rule in rules:
            role = self._get_rule_role(rule)
            if role:
                roles.add(role)
            resource_key = f"{rule.resource_type}:{rule.resource_id}"
            resources.add(resource_key)

        sorted_roles = sorted(roles)
        sorted_resources = sorted(resources)

        # Build matrix
        matrix: Dict[str, Dict[str, str]] = {}
        for role in sorted_roles:
            matrix[role] = {}
            for resource_key in sorted_resources:
                effects = self._collect_effects(rules, role, resource_key)
                matrix[role][resource_key] = self._summarize_effects(effects)

        return RBACMatrix(
            matrix=matrix,
            roles=sorted_roles,
            resources=sorted_resources,
        )

    # -- format converters ---------------------------------------------------

    def to_csv(self) -> str:
        """Export the matrix as a CSV string.

        The first column is ``Role``, subsequent columns are resource
        identifiers.

        Returns:
            CSV-formatted string.
        """
        rbac = self.export_matrix()
        output = io.StringIO()
        writer = csv.writer(output)

        # Header row
        writer.writerow(["Role"] + rbac.resources)

        # Data rows
        for role in rbac.roles:
            row = [role]
            for resource in rbac.resources:
                row.append(rbac.matrix.get(role, {}).get(resource, "-"))
            writer.writerow(row)

        return output.getvalue()

    def to_json(self, indent: int = 2) -> str:
        """Export the matrix as a JSON string.

        Returns:
            JSON-formatted string.
        """
        rbac = self.export_matrix()
        return json.dumps(rbac.to_dict(), indent=indent, sort_keys=True)

    def to_markdown(self) -> str:
        """Export the matrix as a Markdown table.

        Returns:
            Markdown-formatted table string.
        """
        rbac = self.export_matrix()

        if not rbac.roles or not rbac.resources:
            return "_No RBAC rules configured._\n"

        # Header
        header = "| Role | " + " | ".join(rbac.resources) + " |"
        separator = "|------|" + "|".join(
            ["------" for _ in rbac.resources]
        ) + "|"

        lines = [header, separator]

        # Data rows
        for role in rbac.roles:
            cells = []
            for resource in rbac.resources:
                cells.append(rbac.matrix.get(role, {}).get(resource, "-"))
            lines.append(f"| {role} | " + " | ".join(cells) + " |")

        return "\n".join(lines) + "\n"

    # -- conflict detection --------------------------------------------------

    def detect_conflicts(self) -> List[PolicyConflict]:
        """Detect conflicting permission rules.

        Two rules conflict when they target the **same** resource and
        permission, overlap in their user/role/tenant scope, but specify
        **different** effects (e.g. one ALLOW and one DENY without a
        clear priority winner).

        Returns:
            List of :class:`PolicyConflict` objects.
        """
        with self._lock:
            rules = list(self._rules)

        conflicts: List[PolicyConflict] = []
        seen_pairs: Set[tuple] = set()

        for i, rule_a in enumerate(rules):
            for j, rule_b in enumerate(rules):
                if j <= i:
                    continue

                # Same resource + permission?
                if (
                    rule_a.resource_type != rule_b.resource_type
                    or rule_a.resource_id != rule_b.resource_id
                ):
                    continue

                perm_a = self._get_permission_value(rule_a.permission)
                perm_b = self._get_permission_value(rule_b.permission)
                if perm_a != perm_b:
                    continue

                # Overlapping scope?
                if not self._scopes_overlap(rule_a, rule_b):
                    continue

                # Different effects?
                effect_a = self._get_effect_value(rule_a.effect)
                effect_b = self._get_effect_value(rule_b.effect)
                if effect_a == effect_b:
                    continue

                # Deduplicate
                pair_key = (
                    min(rule_a.id, rule_b.id),
                    max(rule_a.id, rule_b.id),
                )
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # Determine severity
                if rule_a.priority == rule_b.priority:
                    severity = "high"
                    desc = (
                        f"Rules '{rule_a.id}' ({effect_a}) and "
                        f"'{rule_b.id}' ({effect_b}) conflict on "
                        f"{rule_a.resource_type}:{rule_a.resource_id} "
                        f"permission={perm_a} with EQUAL priority "
                        f"({rule_a.priority}) -- outcome is ambiguous"
                    )
                else:
                    severity = "medium"
                    winner = rule_a if rule_a.priority > rule_b.priority else rule_b
                    desc = (
                        f"Rules '{rule_a.id}' ({effect_a}, pri={rule_a.priority}) "
                        f"and '{rule_b.id}' ({effect_b}, pri={rule_b.priority}) "
                        f"conflict on {rule_a.resource_type}:{rule_a.resource_id} "
                        f"permission={perm_a} -- resolved by priority "
                        f"('{winner.id}' wins)"
                    )

                conflicts.append(
                    PolicyConflict(
                        rule_id_a=rule_a.id,
                        rule_id_b=rule_b.id,
                        resource_type=rule_a.resource_type,
                        resource_id=rule_a.resource_id,
                        permission=perm_a,
                        description=desc,
                        severity=severity,
                    )
                )

        return conflicts

    # -- internal helpers ----------------------------------------------------

    @staticmethod
    def _get_rule_role(rule: Any) -> Optional[str]:
        """Extract role from a PermissionRule, falling back to user_id."""
        role = getattr(rule, "role", None)
        if role:
            return str(role)
        user_id = getattr(rule, "user_id", None)
        if user_id:
            return f"user:{user_id}"
        tenant_id = getattr(rule, "tenant_id", None)
        if tenant_id:
            return f"tenant:{tenant_id}"
        return "*"

    @staticmethod
    def _get_permission_value(perm: Any) -> str:
        """Get the string value from a permission enum."""
        if hasattr(perm, "value"):
            return str(perm.value)
        return str(perm)

    @staticmethod
    def _get_effect_value(effect: Any) -> str:
        """Get the string value from an effect enum."""
        if hasattr(effect, "value"):
            return str(effect.value)
        return str(effect)

    def _collect_effects(
        self, rules: List[Any], role: str, resource_key: str
    ) -> List[str]:
        """Collect all effect values for a role/resource combination."""
        effects: List[str] = []
        for rule in rules:
            rule_role = self._get_rule_role(rule)
            rule_resource = f"{rule.resource_type}:{rule.resource_id}"
            if rule_role == role and rule_resource == resource_key:
                eff = self._get_effect_value(rule.effect)
                perm = self._get_permission_value(rule.permission)
                effects.append(f"{perm}:{eff}")
        return effects

    @staticmethod
    def _summarize_effects(effects: List[str]) -> str:
        """Produce a cell summary from a list of effect strings."""
        if not effects:
            return "-"
        return ", ".join(sorted(set(effects)))

    @staticmethod
    def _scopes_overlap(rule_a: Any, rule_b: Any) -> bool:
        """Determine whether two rules could apply to the same user."""
        # If either rule has no scope restrictions it applies to everyone
        a_open = not rule_a.role and not rule_a.user_id and not getattr(rule_a, "tenant_id", None)
        b_open = not rule_b.role and not rule_b.user_id and not getattr(rule_b, "tenant_id", None)
        if a_open or b_open:
            return True

        # Same role
        if rule_a.role and rule_b.role and rule_a.role == rule_b.role:
            return True

        # Same user
        if rule_a.user_id and rule_b.user_id and rule_a.user_id == rule_b.user_id:
            return True

        # Same tenant
        a_tenant = getattr(rule_a, "tenant_id", None)
        b_tenant = getattr(rule_b, "tenant_id", None)
        if a_tenant and b_tenant and a_tenant == b_tenant:
            return True

        return False


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "PolicyConflict",
    "RBACMatrix",
    "RBACMatrixExporter",
]
