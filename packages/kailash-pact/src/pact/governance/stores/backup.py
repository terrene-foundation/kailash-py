# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Governance store backup and restore -- JSON export/import of all governance state.

Provides functions to backup and restore the complete governance state:
- Organization structure
- Role envelopes and task envelopes
- Clearance assignments
- Knowledge Share Policies (KSPs)
- Cross-Functional Bridges
- Backup metadata (timestamp, schema version)

The backup format is a single JSON file with deterministic key ordering
for reproducible snapshots.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pact.build.config.schema import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
)
from pact.governance.access import KnowledgeSharePolicy, PactBridge
from pact.governance.clearance import RoleClearance, VettingStatus
from pact.governance.envelopes import RoleEnvelope

logger = logging.getLogger(__name__)

__all__ = ["backup_governance_store", "restore_governance_store"]


def backup_governance_store(engine: Any, path: str) -> None:
    """Export all governance state to a JSON file.

    Backs up the complete governance state from the engine's stores:
    - Organization structure (org_id, nodes)
    - Role envelopes
    - Clearance assignments
    - KSPs
    - Bridges
    - Metadata (timestamp, schema version)

    Args:
        engine: A GovernanceEngine instance.
        path: File path for the JSON backup.

    Raises:
        OSError: If the file cannot be written.
    """
    compiled_org = engine.get_org()

    # Export org structure
    org_data: dict[str, Any] = {
        "org_id": compiled_org.org_id,
        "nodes": {},
    }
    for addr, node in compiled_org.nodes.items():
        org_data["nodes"][addr] = {
            "address": node.address,
            "node_type": node.node_type.value,
            "name": node.name,
            "node_id": node.node_id,
            "parent_address": node.parent_address,
            "children_addresses": list(node.children_addresses),
            "is_vacant": node.is_vacant,
            "is_external": node.is_external,
        }

    # Export envelopes
    envelopes_data: list[dict[str, Any]] = []
    for addr in compiled_org.nodes:
        role_env = engine._envelope_store.get_role_envelope(addr)
        if role_env is not None:
            envelopes_data.append(
                {
                    "id": role_env.id,
                    "defining_role_address": role_env.defining_role_address,
                    "target_role_address": role_env.target_role_address,
                    "envelope": role_env.envelope.model_dump(),
                    "version": role_env.version,
                    "created_at": role_env.created_at.isoformat(),
                    "modified_at": role_env.modified_at.isoformat(),
                }
            )

    # Export clearances
    clearances_data: list[dict[str, Any]] = []
    for addr in compiled_org.nodes:
        clr = engine._clearance_store.get_clearance(addr)
        if clr is not None:
            clearances_data.append(
                {
                    "role_address": clr.role_address,
                    "max_clearance": clr.max_clearance.value,
                    "compartments": sorted(clr.compartments),
                    "granted_by_role_address": clr.granted_by_role_address,
                    "vetting_status": clr.vetting_status.value,
                    "review_at": clr.review_at.isoformat() if clr.review_at else None,
                    "nda_signed": clr.nda_signed,
                }
            )

    # Export KSPs
    ksps_data: list[dict[str, Any]] = []
    for ksp in engine._access_policy_store.list_ksps():
        ksps_data.append(
            {
                "id": ksp.id,
                "source_unit_address": ksp.source_unit_address,
                "target_unit_address": ksp.target_unit_address,
                "max_classification": ksp.max_classification.value,
                "compartments": sorted(ksp.compartments),
                "created_by_role_address": ksp.created_by_role_address,
                "active": ksp.active,
                "expires_at": ksp.expires_at.isoformat() if ksp.expires_at else None,
            }
        )

    # Export bridges
    bridges_data: list[dict[str, Any]] = []
    for bridge in engine._access_policy_store.list_bridges():
        bridges_data.append(
            {
                "id": bridge.id,
                "role_a_address": bridge.role_a_address,
                "role_b_address": bridge.role_b_address,
                "bridge_type": bridge.bridge_type,
                "max_classification": bridge.max_classification.value,
                "operational_scope": list(bridge.operational_scope),
                "bilateral": bridge.bilateral,
                "expires_at": bridge.expires_at.isoformat() if bridge.expires_at else None,
                "active": bridge.active,
            }
        )

    backup_data = {
        "org": org_data,
        "envelopes": envelopes_data,
        "clearances": clearances_data,
        "ksps": ksps_data,
        "bridges": bridges_data,
        "metadata": {
            "backup_timestamp": datetime.now(UTC).isoformat(),
            "schema_version": 1,
        },
    }

    output_path = Path(path)
    output_path.write_text(
        json.dumps(backup_data, indent=2, sort_keys=False, default=str),
        encoding="utf-8",
    )

    logger.info(
        "Backed up governance state for org '%s' to '%s' "
        "(%d envelopes, %d clearances, %d KSPs, %d bridges)",
        compiled_org.org_id,
        path,
        len(envelopes_data),
        len(clearances_data),
        len(ksps_data),
        len(bridges_data),
    )


def restore_governance_store(engine: Any, path: str) -> None:
    """Import governance state from a JSON backup file.

    Restores clearances, envelopes, KSPs, and bridges from a backup
    created by backup_governance_store(). The organization structure
    in the backup is used for verification but the engine's existing
    org is preserved (the engine was initialized with an org already).

    Args:
        engine: A GovernanceEngine instance to restore into.
        path: File path of the JSON backup.

    Raises:
        FileNotFoundError: If the backup file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
        KeyError: If required fields are missing from the backup.
    """
    input_path = Path(path)
    if not input_path.exists():
        raise FileNotFoundError(f"Backup file not found: {path}")

    data = json.loads(input_path.read_text(encoding="utf-8"))

    # Restore clearances
    for clr_data in data.get("clearances", []):
        review_at = None
        if clr_data.get("review_at") is not None:
            review_at = datetime.fromisoformat(clr_data["review_at"])

        clearance = RoleClearance(
            role_address=clr_data["role_address"],
            max_clearance=ConfidentialityLevel(clr_data["max_clearance"]),
            compartments=frozenset(clr_data.get("compartments", [])),
            granted_by_role_address=clr_data.get("granted_by_role_address", ""),
            vetting_status=VettingStatus(clr_data.get("vetting_status", "active")),
            review_at=review_at,
            nda_signed=clr_data.get("nda_signed", False),
        )
        engine._clearance_store.grant_clearance(clearance)

    # Restore envelopes
    for env_data in data.get("envelopes", []):
        envelope_config = ConstraintEnvelopeConfig.model_validate(env_data["envelope"])
        role_envelope = RoleEnvelope(
            id=env_data["id"],
            defining_role_address=env_data["defining_role_address"],
            target_role_address=env_data["target_role_address"],
            envelope=envelope_config,
            version=env_data.get("version", 1),
            created_at=datetime.fromisoformat(env_data["created_at"]),
            modified_at=datetime.fromisoformat(env_data["modified_at"]),
        )
        engine._envelope_store.save_role_envelope(role_envelope)

    # Restore KSPs
    for ksp_data in data.get("ksps", []):
        expires_at = None
        if ksp_data.get("expires_at") is not None:
            expires_at = datetime.fromisoformat(ksp_data["expires_at"])

        ksp = KnowledgeSharePolicy(
            id=ksp_data["id"],
            source_unit_address=ksp_data["source_unit_address"],
            target_unit_address=ksp_data["target_unit_address"],
            max_classification=ConfidentialityLevel(ksp_data["max_classification"]),
            compartments=frozenset(ksp_data.get("compartments", [])),
            created_by_role_address=ksp_data.get("created_by_role_address", ""),
            active=ksp_data.get("active", True),
            expires_at=expires_at,
        )
        engine._access_policy_store.save_ksp(ksp)

    # Restore bridges
    for bridge_data in data.get("bridges", []):
        expires_at = None
        if bridge_data.get("expires_at") is not None:
            expires_at = datetime.fromisoformat(bridge_data["expires_at"])

        bridge = PactBridge(
            id=bridge_data["id"],
            role_a_address=bridge_data["role_a_address"],
            role_b_address=bridge_data["role_b_address"],
            bridge_type=bridge_data.get("bridge_type", "standing"),
            max_classification=ConfidentialityLevel(bridge_data["max_classification"]),
            operational_scope=tuple(bridge_data.get("operational_scope", [])),
            bilateral=bridge_data.get("bilateral", True),
            expires_at=expires_at,
            active=bridge_data.get("active", True),
        )
        engine._access_policy_store.save_bridge(bridge)

    logger.info(
        "Restored governance state from '%s': " "%d envelopes, %d clearances, %d KSPs, %d bridges",
        path,
        len(data.get("envelopes", [])),
        len(data.get("clearances", [])),
        len(data.get("ksps", [])),
        len(data.get("bridges", [])),
    )
