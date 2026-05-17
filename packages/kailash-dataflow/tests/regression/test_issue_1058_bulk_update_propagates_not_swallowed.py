"""Regression: ``Express.bulk_update`` MUST re-raise ``ProtectionViolation``
— never fold it into ``failed_count``.

Issue #1058 (post-#1050 follow-up).

The per-record loop in ``bulk_update`` has ``try / except Exception:
failed_count += 1`` for legitimate per-row data failures. Without the
explicit ``except ProtectionViolation: raise`` shim added by the #1050
workstream (express.py:1461-1477), a write-protection block on the
nested ``self.update()`` call would be caught by that generic clause,
swallowed into ``failed_count``, and ``bulk_update`` would return an
empty results list with NO exception — silently bypassing
write-protection at the bulk_update Express surface.

This file is the standalone, grep-able regression guard for that
specific failure mode. The mutation matrix at
``tests/integration/test_issue_1050_protection_mutation_matrix.py``
covers ``bulk_update`` parametrically with seven sibling mutations;
this test isolates the *swallow-vs-propagate* contract so the failure
mode is named in one place and one place only:

    pytest -k bulk_update_protection_violation_propagates_not_swallowed

Spec anchor: ``specs/dataflow-protection.md`` §2 path 1 + I5 — Express
MUST surface protection violations as exceptions, not result dicts.

Tier 2 per ``rules/testing.md`` — real backend, no mocking. File-SQLite
chosen because (a) the contract is dialect-independent (the fix lives
in pure-Python ``express.py`` between the loop and the per-record
``await self.update(...)`` call, with no SQL involved), and (b) the
test must run in any CI lane without the shared Docker stack.
"""

from __future__ import annotations

import tempfile

import pytest

from dataflow.core.protected_engine import ProtectedDataFlow
from dataflow.core.protection import ProtectionViolation


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_bulk_update_protection_violation_propagates_not_swallowed():
    """Read-only-protected ``bulk_update`` MUST raise ``ProtectionViolation``
    AND leave every row unchanged.

    Pre-fix failure mode this guards against:

      results = await db.express.bulk_update(model, [...])
      # would return [] silently; failed_count = 1; NO exception;
      # caller has no signal that write-protection blocked the call.

    Post-fix contract:

      with pytest.raises(ProtectionViolation):
          await db.express.bulk_update(model, [...])
      # AND the seeded rows are unchanged.
    """
    tmpdir = tempfile.mkdtemp(prefix="issue1058_bulk_update_propagates_")
    db = ProtectedDataFlow(
        database_url=f"sqlite:///{tmpdir}/test.db",
        enable_protection=True,
    )

    @db.model  # noqa: B903 — DataFlow model decorator
    class Issue1058Doc:
        id: str
        title: str

    try:
        await db.initialize()

        # Seed two baseline rows under permissive protection so the
        # bulk_update call below has real targets and the
        # "rows unchanged after blocked write" assertion is meaningful.
        await db.express.create("Issue1058Doc", {"id": "seed-1", "title": "original-1"})
        await db.express.create("Issue1058Doc", {"id": "seed-2", "title": "original-2"})

        # Engage global read-only protection at BLOCK level. Every
        # mutation surface MUST now raise — including bulk_update,
        # whose per-record loop must NOT swallow the violation into
        # failed_count.
        db.enable_read_only_mode("issue #1058 bulk_update propagation guard")

        # Contract — propagation: the violation MUST surface to the
        # caller, NOT fold into a silent empty-results return.
        with pytest.raises(ProtectionViolation):
            await db.express.bulk_update(
                "Issue1058Doc",
                [
                    {"id": "seed-1", "title": "MUTATED-1"},
                    {"id": "seed-2", "title": "MUTATED-2"},
                ],
            )

        # State-persistence verification (rules/testing.md § State
        # Persistence Verification): the blocked bulk_update left every
        # row exactly as it was. A pre-fix swallow would have left
        # `failed_count = 2` and `results = []` — undetectable from
        # the caller and therefore undetectable here without explicit
        # read-back through the same Express surface a user would use.
        survived_1 = await db.express.read("Issue1058Doc", "seed-1")
        assert survived_1 is not None
        assert survived_1["title"] == "original-1", (
            "bulk_update mutated seed-1 despite read-only protection — "
            "the propagation contract bypassed (violation swallowed)"
        )

        survived_2 = await db.express.read("Issue1058Doc", "seed-2")
        assert survived_2 is not None
        assert survived_2["title"] == "original-2", (
            "bulk_update mutated seed-2 despite read-only protection — "
            "the propagation contract bypassed (violation swallowed)"
        )
    finally:
        db.close()
