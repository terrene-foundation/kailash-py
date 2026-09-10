# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2163 -- anchor tip taken from a capped page.

``TrustProject.load`` derived the chain tip as::

    anchors = tp_store.list_anchors()      # default limit=1000
    last_anchor_id = anchors[-1].get("anchor_id")

so past 1000 anchors it selected the 1000th-OLDEST record as the tip and the
next anchor minted chained to a mid-chain parent -- corrupting the very
tamper-evidence record anchors exist to be.

A second instance of the same assumption: anchor files are named
``{audit_seq:04d}-{anchor_id}.json`` and were walked with a plain lexicographic
``sorted()``. ``{:04d}`` stops padding at five digits, so ``"10000-"`` sorts
BEFORE ``"9999-"`` and the chain silently reorders past 9999 anchors -- which
also made ``_verify_locked``'s linkage walk report a false ``chain_valid=False``
on an intact chain.

Both are now closed by asking the store for the tip directly
(``latest_anchor()``) and by ordering anchor files on the numerically parsed
sequence (``sort_anchor_files``), so no cap and no padding width can
reintroduce the class at a larger N.

Discrimination (``rules/instrument-discipline.md`` MUST-1): every test asserts
the tip is the NEWEST anchor by identity, and the counts deliberately EXCEED
the cap / padding width. Against the pre-fix code these assert the specific
wrong value the bug produced (the 1000th-oldest, and ``9999-`` respectively),
so they would have caught the original -- and a control at a count BELOW the
cap pins that the fix did not simply invert the ordering.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from kailash.trust.plane.models import ConstraintEnvelope, OperationalConstraints
from kailash.trust.plane.project import TrustProject
from kailash.trust.plane.store import TrustPlaneStore
from kailash.trust.plane.store.filesystem import (
    FileSystemTrustPlaneStore,
    anchor_sequence_key,
)

#: The default page size of ``list_anchors`` -- the window the old tip
#: derivation was silently bounded by.
LIST_ANCHORS_DEFAULT_LIMIT = 1000


def _anchor_id(seq: int) -> str:
    return f"aud-{seq:08d}-0000-0000-0000-000000000000"


def _sync_audit_counter(trust_dir: Path, next_seq: int) -> None:
    """Point the manifest's audit counter past the synthetic chain.

    ``_record_*_locked`` names each anchor file from ``manifest.total_audits``.
    A synthetic chain written straight to disk must move that counter too, or
    the next real anchor is filed at sequence 0 and lands at the head of the
    chain instead of its tail -- a fixture artefact, not product behaviour.
    """
    manifest_path = trust_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["total_audits"] = next_seq
    manifest_path.write_text(json.dumps(manifest))


def _write_anchor_chain(anchors_dir: Path, sequences: list[int]) -> list[str]:
    """Write a correctly parent-linked anchor chain at *sequences*.

    Uses the production filename convention ``{audit_seq:04d}-{anchor_id}.json``
    written by ``TrustProject._record_*_locked``.
    """
    anchors_dir.mkdir(parents=True, exist_ok=True)
    for stale in anchors_dir.glob("*.json"):
        stale.unlink()

    parent: str | None = None
    ids: list[str] = []
    for seq in sequences:
        anchor_id = _anchor_id(seq)
        (anchors_dir / f"{seq:04d}-{anchor_id}.json").write_text(
            json.dumps(
                {
                    "anchor_id": anchor_id,
                    "parent_anchor_id": parent,
                    "agent_id": "agent-2163",
                    "action": "record_decision",
                    "resource": f"decision/{seq}",
                    "result": "success",
                    "trust_chain_hash": "0" * 64,
                    "signature": "",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "context": {"parent_anchor_id": parent},
                }
            )
        )
        parent = anchor_id
        ids.append(anchor_id)
    return ids


@pytest.fixture
def trust_dir(tmp_path):
    envelope = ConstraintEnvelope(
        operational=OperationalConstraints(
            allowed_actions=["draft_content", "record_decision"],
            blocked_actions=["fabricate"],
        ),
        signed_by="Regression 2163",
    )
    path = tmp_path / "trust-plane"
    asyncio.run(
        TrustProject.create(
            trust_dir=str(path),
            project_name="Issue 2163",
            author="Regression 2163",
            constraint_envelope=envelope,
        )
    )
    return path


class TestAnchorSequenceKey:
    """The ordering primitive itself, at and past the padding width."""

    def test_padding_overflow_orders_numerically(self):
        names = ["10000-aud-x.json", "9999-aud-y.json", "0001-aud-z.json"]
        assert sorted(names) == [
            "0001-aud-z.json",
            "10000-aud-x.json",
            "9999-aud-y.json",
        ], "control: plain lexicographic sort puts 10000 before 9999"
        assert sorted(names, key=anchor_sequence_key) == [
            "0001-aud-z.json",
            "9999-aud-y.json",
            "10000-aud-x.json",
        ]

    def test_unsequenced_files_sort_first_and_stably(self):
        """Anchors written via ``store_anchor`` carry no sequence prefix."""
        names = ["0002-aud-b.json", "anc-zzz.json", "0001-aud-a.json", "anc-aaa.json"]
        assert sorted(names, key=anchor_sequence_key) == [
            "anc-aaa.json",
            "anc-zzz.json",
            "0001-aud-a.json",
            "0002-aud-b.json",
        ]


class TestStoreExposesTheTip:
    def test_protocol_declares_latest_anchor(self):
        """The capability is on the protocol, not bolted onto one backend."""
        assert hasattr(TrustPlaneStore, "latest_anchor")

    def test_empty_store_returns_none(self, trust_dir):
        store = FileSystemTrustPlaneStore(trust_dir)
        store.initialize()
        assert store.latest_anchor() is None

    def test_tip_is_newest_past_the_cap(self, trust_dir):
        count = LIST_ANCHORS_DEFAULT_LIMIT + 5
        ids = _write_anchor_chain(trust_dir / "anchors", list(range(count)))
        store = FileSystemTrustPlaneStore(trust_dir)

        assert len(ids) > LIST_ANCHORS_DEFAULT_LIMIT, "test must exceed the cap"
        # The capped page is exactly what the old derivation indexed.
        page = store.list_anchors()
        assert len(page) == LIST_ANCHORS_DEFAULT_LIMIT
        assert page[-1]["anchor_id"] == ids[LIST_ANCHORS_DEFAULT_LIMIT - 1]
        assert page[-1]["anchor_id"] != ids[-1]

        assert store.latest_anchor()["anchor_id"] == ids[-1]

    def test_tip_is_newest_below_the_cap(self, trust_dir):
        """Control: the fix did not invert or otherwise disturb small chains."""
        ids = _write_anchor_chain(trust_dir / "anchors", list(range(10)))
        store = FileSystemTrustPlaneStore(trust_dir)
        assert store.latest_anchor()["anchor_id"] == ids[-1]

    def test_list_anchors_is_chronological_past_the_padding_width(self, trust_dir):
        ids = _write_anchor_chain(trust_dir / "anchors", [9998, 9999, 10000, 10001])
        store = FileSystemTrustPlaneStore(trust_dir)
        assert [a["anchor_id"] for a in store.list_anchors()] == ids


class TestLoadDerivesTheTip:
    def test_load_past_the_cap_selects_the_newest_anchor(self, trust_dir):
        count = LIST_ANCHORS_DEFAULT_LIMIT + 5
        ids = _write_anchor_chain(trust_dir / "anchors", list(range(count)))
        assert len(list((trust_dir / "anchors").glob("*.json"))) == count

        project = asyncio.run(TrustProject.load(str(trust_dir)))

        assert project._last_anchor_id == ids[-1]
        # Pin the specific wrong value the bug produced, so a regression is
        # identified rather than merely detected.
        assert project._last_anchor_id != ids[LIST_ANCHORS_DEFAULT_LIMIT - 1]

    def test_load_below_the_cap_selects_the_newest_anchor(self, trust_dir):
        """Control pole -- the small-chain case must still be right."""
        ids = _write_anchor_chain(trust_dir / "anchors", list(range(10)))
        project = asyncio.run(TrustProject.load(str(trust_dir)))
        assert project._last_anchor_id == ids[-1]

    def test_load_with_no_anchors_has_no_tip(self, trust_dir):
        project = asyncio.run(TrustProject.load(str(trust_dir)))
        assert project._last_anchor_id is None

    def test_next_anchor_chains_to_the_real_tip_past_the_cap(self, trust_dir):
        """The consequence the issue names: the next anchor's parent link."""
        from kailash.trust.plane.models import DecisionRecord

        count = LIST_ANCHORS_DEFAULT_LIMIT + 5
        ids = _write_anchor_chain(trust_dir / "anchors", list(range(count)))
        _sync_audit_counter(trust_dir, count)

        project = asyncio.run(TrustProject.load(str(trust_dir)))
        asyncio.run(
            project.record_decision(
                DecisionRecord(
                    decision_type="record_decision",
                    decision="Mint an anchor after the cap",
                    rationale="Its parent must be the real tip",
                )
            )
        )

        newest_path = max(
            (trust_dir / "anchors").glob("*.json"),
            key=lambda p: anchor_sequence_key(p.name),
        )
        minted = json.loads(newest_path.read_text())
        # The anchor just minted is the one that is NOT part of the synthetic
        # chain -- asserted, so a mis-selected file fails here rather than
        # silently answering a different question.
        assert minted["anchor_id"] not in set(ids)
        assert minted["parent_anchor_id"] == ids[-1]

        report = asyncio.run(project.verify())
        assert report["chain_valid"] is True, report["integrity_issues"]


class TestVerifyWalkSurvivesPaddingOverflow:
    def test_intact_chain_past_9999_verifies_valid(self, trust_dir):
        """Pre-fix this reported chain_valid=False on an INTACT chain."""
        _write_anchor_chain(trust_dir / "anchors", [9998, 9999, 10000, 10001, 10002])
        project = asyncio.run(TrustProject.load(str(trust_dir)))

        report = asyncio.run(project.verify())
        assert report["chain_valid"] is True, report["integrity_issues"]
        assert report["integrity_issues"] == []

    def test_broken_chain_past_9999_still_reports_invalid(self, trust_dir):
        """Failure pole -- the walk must not have been made blind instead."""
        anchors_dir = trust_dir / "anchors"
        _write_anchor_chain(anchors_dir, [9998, 9999, 10000, 10001, 10002])
        target = anchors_dir / f"10001-{_anchor_id(10001)}.json"
        data = json.loads(target.read_text())
        data["parent_anchor_id"] = "aud-00000000-dead-beef-0000-000000000000"
        data["context"]["parent_anchor_id"] = data["parent_anchor_id"]
        target.write_text(json.dumps(data))

        project = asyncio.run(TrustProject.load(str(trust_dir)))
        report = asyncio.run(project.verify())
        assert report["chain_valid"] is False
        assert any("parent chain broken" in i for i in report["integrity_issues"])
