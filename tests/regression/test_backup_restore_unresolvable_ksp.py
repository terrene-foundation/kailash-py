# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression -- restore must not RE-AUTHORISE the policies it is restoring.

Blast-radius guard for issue #2238.  Making ``create_ksp`` fail closed on an
unresolvable unit address also made the KSP leg of ``restore_governance_store``
fail closed, because that leg re-feeds every backed-up policy through the
PUBLIC API::

    src/kailash/trust/pact/stores/backup.py:298    engine.create_ksp(ksp)

A backup written by ANY pre-fix build can contain such a policy -- the pre-fix
``create_ksp`` persisted its argument verbatim, with no validation at all, and
the HTTP body for both unit fields is an unconstrained ``str``.  So a restore
written to recover state could instead raise ``PactError`` part-way through a
loop whose clearances and envelopes were ALREADY applied above it, leaving a
half-restored engine while the operator sees "restore failed".  The function's
own ``Raises:`` block documents only ``FileNotFoundError`` / ``JSONDecodeError``
/ ``KeyError`` -- a mid-loop ``PactError`` is not even part of its contract.

THE RESTORE PATH IS A PRIVILEGED ADMIN OPERATION, NOT A RE-AUTHORISATION.
The bridge leg of the same function already says so and bypasses the gate::

    backup.py:300-303  "Restore bridges directly to store -- bypass LCA approval
                        check. Restored bridges were already approved when
                        originally created; requiring re-approval during restore
                        would be circular and block legitimate backup recovery.
                        This is a privileged admin operation."

That reasoning is not bridge-specific: a backup is a cross-org-version artifact
(the docstring notes the engine's EXISTING org is preserved and the backup's org
is used only for verification), so an address that resolved when the backup was
written need not resolve in the org being restored into.  The KSP leg now takes
the same route as the bridge leg.

Stated scope: the clearance leg has the SAME latent shape and is deliberately
NOT changed here -- ``grant_clearance`` resolves fail-closed on the base commit
already, so that hazard predates this work and is reported rather than folded
into this fix.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kailash.trust.pact.access import KnowledgeSharePolicy
from kailash.trust.pact.clearance import ConfidentialityLevel
from kailash.trust.pact.compilation import RoleDefinition, compile_org
from kailash.trust.pact.config import DepartmentConfig, OrgDefinition, TeamConfig
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.stores.backup import (
    backup_governance_store,
    restore_governance_store,
)

pytestmark = [pytest.mark.regression]


def _org() -> OrgDefinition:
    return OrgDefinition(
        org_id="backup-legacy-org",
        name="Backup Legacy Org",
        departments=[DepartmentConfig(department_id="d-eng", name="Engineering")],
        teams=[TeamConfig(id="t-backend", name="Backend", workspace="ws-backend")],
        roles=[
            RoleDefinition(
                role_id="r-vp",
                name="VP Engineering",
                reports_to_role_id=None,
                is_primary_for_unit="d-eng",
            ),
            RoleDefinition(
                role_id="r-lead",
                name="Lead Developer",
                reports_to_role_id="r-vp",
                is_primary_for_unit="t-backend",
            ),
        ],
    )


def test_restore_of_legacy_backup_with_unresolvable_ksp_units(
    tmp_path: Path,
) -> None:
    """A backed-up KSP naming units absent from the target org still restores.

    The policy below is exactly the shape a pre-fix build persisted: the units
    name nothing.  It is written straight to the store here because that is the
    only way to build the legacy artifact -- which is itself the point, since a
    pre-fix release had no gate to stop it and the resulting FILE outlives the
    release.
    """
    engine1 = GovernanceEngine(compile_org(_org()))
    engine1._access_policy_store.save_ksp(
        KnowledgeSharePolicy(
            id="ksp-legacy",
            source_unit_address="D9",
            target_unit_address="D8",
            max_classification=ConfidentialityLevel.RESTRICTED,
        )
    )

    backup_path = tmp_path / "legacy-backup.json"
    backup_governance_store(engine1, str(backup_path))

    engine2 = GovernanceEngine(compile_org(_org()))
    # The assertion under test: a privileged restore must not re-authorise.
    restore_governance_store(engine2, str(backup_path))

    restored = {k.id: k for k in engine2._access_policy_store.list_ksps()}
    assert set(restored) == {"ksp-legacy"}
    # Round-tripped verbatim -- restore preserves the stored bytes, it does not
    # silently rewrite the address the backup recorded.
    assert restored["ksp-legacy"].source_unit_address == "D9"
    assert restored["ksp-legacy"].target_unit_address == "D8"


def test_restore_is_not_half_applied_when_a_legacy_ksp_is_present(
    tmp_path: Path,
) -> None:
    """The failure this guards against was a PARTIAL restore.

    Clearances and envelopes are applied ABOVE the KSP loop, so a raise inside
    that loop leaves them durably applied while the KSPs and bridges are not.
    With the KSP leg bypassing re-authorisation the whole file applies, so the
    envelope that precedes the loop is still in force afterwards.
    """
    from kailash.trust.pact.config import (
        ConstraintEnvelopeConfig,
        FinancialConstraintConfig,
    )
    from kailash.trust.pact.envelopes import RoleEnvelope

    compiled1 = compile_org(_org())
    addresses = {node.name: addr for addr, node in compiled1.nodes.items()}
    vp, lead = addresses["VP Engineering"], addresses["Lead Developer"]

    engine1 = GovernanceEngine(compiled1)
    engine1.set_role_envelope(
        RoleEnvelope(
            id="re-lead",
            defining_role_address=vp,
            target_role_address=lead,
            envelope=ConstraintEnvelopeConfig(
                id="env-lead",
                financial=FinancialConstraintConfig(max_spend_usd=250.0),
            ),
        )
    )
    engine1._access_policy_store.save_ksp(
        KnowledgeSharePolicy(
            id="ksp-legacy",
            source_unit_address="D9",
            target_unit_address="D8",
            max_classification=ConfidentialityLevel.RESTRICTED,
        )
    )

    backup_path = tmp_path / "legacy-backup-half.json"
    backup_governance_store(engine1, str(backup_path))

    engine2 = GovernanceEngine(compile_org(_org()))
    restore_governance_store(engine2, str(backup_path))

    effective = engine2.compute_envelope(lead)
    assert effective is not None
    assert effective.financial is not None
    assert effective.financial.max_spend_usd == 250.0
    assert {k.id for k in engine2._access_policy_store.list_ksps()} == {"ksp-legacy"}


def test_the_creation_gate_is_unchanged_by_the_restore_bypass() -> None:
    """The negative pole: restoring directly does NOT reopen the create gate.

    ``create_ksp`` is still the only authoring path a caller can reach, and it
    still refuses an unresolvable unit.  Without this, the restore bypass would
    read as a general loosening rather than a privileged one.
    """
    from kailash.trust.pact.exceptions import PactError

    engine = GovernanceEngine(compile_org(_org()))
    with pytest.raises(PactError):
        engine.create_ksp(
            KnowledgeSharePolicy(
                id="ksp-ghost",
                source_unit_address="D9",
                target_unit_address="D8",
                max_classification=ConfidentialityLevel.RESTRICTED,
            )
        )
