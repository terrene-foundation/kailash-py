# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for VerificationBundle (M6-01, M6-05).

Tests bundle creation, JSON/HTML export, verification,
confidentiality filtering, and tamper detection.
"""

import asyncio
import json

import pytest

from kailash.trust.plane.bundle import VerificationBundle
from kailash.trust.plane.models import (
    DecisionRecord,
    DecisionType,
    EscalationRecord,
    ExecutionRecord,
    HumanCompetency,
    InterventionRecord,
)
from kailash.trust.plane.project import TrustProject


@pytest.fixture
def tmp_trust_dir(tmp_path):
    return tmp_path / "trust-plane"


@pytest.fixture
def project(tmp_trust_dir):
    return asyncio.run(
        TrustProject.create(
            trust_dir=str(tmp_trust_dir),
            project_name="Bundle Test",
            author="Test Author",
        )
    )


@pytest.fixture
def project_with_data(project):
    """Project with decisions, milestones, and mirror records."""
    asyncio.run(
        project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.SCOPE,
                decision="Focus on governance",
                rationale="Core mission alignment",
            )
        )
    )
    asyncio.run(
        project.record_decision(
            DecisionRecord(
                decision_type=DecisionType.ARGUMENT,
                decision="Mirror Thesis is central",
                rationale="Most novel contribution",
                confidence=0.95,
            )
        )
    )
    asyncio.run(project.record_milestone("v0.1", "First draft"))
    asyncio.run(project.record_execution(ExecutionRecord(action="draft_content")))
    asyncio.run(
        project.record_escalation(
            EscalationRecord(
                trigger="Overclaim check",
                competency_categories=[HumanCompetency.ETHICAL_JUDGMENT],
            )
        )
    )
    asyncio.run(
        project.record_intervention(
            InterventionRecord(
                observation="Audience mismatch",
                competency_categories=[HumanCompetency.CONTEXTUAL_WISDOM],
                human_authority="Test Author",
            )
        )
    )
    return project


class TestBundleCreation:
    def test_create_from_empty_project(self, project):
        bundle = asyncio.run(VerificationBundle.create(project))
        assert bundle.project_metadata["project_name"] == "Bundle Test"
        assert bundle.genesis != {}
        assert bundle.public_key != ""

    def test_create_from_project_with_data(self, project_with_data):
        bundle = asyncio.run(VerificationBundle.create(project_with_data))
        assert len(bundle.anchors) >= 5  # decisions + milestone + mirror records
        assert len(bundle.reasoning_traces) >= 2  # at least decision reasoning
        assert bundle.chain_hash != ""

    def test_bundle_contains_genesis(self, project_with_data):
        bundle = asyncio.run(VerificationBundle.create(project_with_data))
        assert "genesis_id" in bundle.genesis

    def test_bundle_includes_mirror_summary(self, project_with_data):
        bundle = asyncio.run(VerificationBundle.create(project_with_data))
        assert bundle.mirror_summary is not None
        assert bundle.mirror_summary["total_actions"] >= 3


class TestBundleJson:
    def test_to_json_valid(self, project_with_data):
        bundle = asyncio.run(VerificationBundle.create(project_with_data))
        j = bundle.to_json()
        parsed = json.loads(j)
        assert parsed["bundle_version"] == "1.0"
        assert parsed["project"]["project_name"] == "Bundle Test"
        assert len(parsed["anchors"]) >= 5
        assert "verification" in parsed

    def test_to_dict_contains_all_fields(self, project_with_data):
        bundle = asyncio.run(VerificationBundle.create(project_with_data))
        d = bundle.to_dict()
        assert "genesis" in d
        assert "anchors" in d
        assert "reasoning_traces" in d
        assert "public_key" in d
        assert "chain_hash" in d
        assert "verification" in d
        assert "mirror_summary" in d


class TestBundleHtml:
    def test_html_self_contained(self, project_with_data):
        bundle = asyncio.run(VerificationBundle.create(project_with_data))
        html = bundle.to_html()
        assert "<!DOCTYPE html>" in html
        assert "Bundle Test" in html
        assert "verifyBundle" in html
        assert "crypto.subtle.digest" in html

    def test_html_has_timeline(self, project_with_data):
        bundle = asyncio.run(VerificationBundle.create(project_with_data))
        html = bundle.to_html()
        assert "Anchor Timeline" in html
        assert "record_decision" in html


class TestBundleVerification:
    def test_verify_valid_bundle(self, project_with_data):
        bundle = asyncio.run(VerificationBundle.create(project_with_data))
        j = bundle.to_json()
        result = VerificationBundle.verify(j)
        assert result["valid"] is True
        assert result["chain_hash_valid"] is True
        assert result["parent_chain_valid"] is True
        assert result["issues"] == []

    def test_verify_detects_tampered_chain_hash(self, project_with_data):
        bundle = asyncio.run(VerificationBundle.create(project_with_data))
        data = json.loads(bundle.to_json())
        data["chain_hash"] = "0000tampered"
        tampered = json.dumps(data)
        result = VerificationBundle.verify(tampered)
        assert result["valid"] is False
        assert result["chain_hash_valid"] is False

    def test_verify_detects_removed_anchor(self, project_with_data):
        bundle = asyncio.run(VerificationBundle.create(project_with_data))
        data = json.loads(bundle.to_json())
        if len(data["anchors"]) > 1:
            data["anchors"].pop(1)  # Remove an anchor
        tampered = json.dumps(data)
        result = VerificationBundle.verify(tampered)
        # Either chain hash or parent chain should fail
        assert result["valid"] is False

    def test_verify_detects_reordered_anchors(self, project_with_data):
        bundle = asyncio.run(VerificationBundle.create(project_with_data))
        data = json.loads(bundle.to_json())
        if len(data["anchors"]) >= 2:
            data["anchors"][0], data["anchors"][1] = (
                data["anchors"][1],
                data["anchors"][0],
            )
        tampered = json.dumps(data)
        result = VerificationBundle.verify(tampered)
        assert result["valid"] is False

    def test_verify_empty_project(self, project):
        bundle = asyncio.run(VerificationBundle.create(project))
        j = bundle.to_json()
        result = VerificationBundle.verify(j)
        assert result["valid"] is True
        assert result["anchor_count"] == 0


class TestConfidentialityFiltering:
    def test_public_ceiling_includes_public(self, project_with_data):
        from kailash.trust.reasoning.traces import ConfidentialityLevel

        bundle = asyncio.run(
            VerificationBundle.create(
                project_with_data,
                confidentiality_ceiling=ConfidentialityLevel.PUBLIC,
            )
        )
        # All traces in test project are PUBLIC
        for trace in bundle.reasoning_traces:
            assert "redacted" not in trace or trace.get("redacted") is False

    def test_redacted_preserves_hash(self, project_with_data):
        """Redacted traces should have a content_hash for integrity."""
        from kailash.trust.reasoning.traces import ConfidentialityLevel

        # Record a decision with confidential reasoning
        asyncio.run(
            project_with_data.record_decision(
                DecisionRecord(
                    decision_type=DecisionType.POLICY,
                    decision="Confidential policy",
                    rationale="Secret rationale",
                    confidentiality="confidential",
                )
            )
        )

        bundle = asyncio.run(
            VerificationBundle.create(
                project_with_data,
                confidentiality_ceiling=ConfidentialityLevel.PUBLIC,
            )
        )

        # At least one trace should be redacted
        redacted = [t for t in bundle.reasoning_traces if t.get("redacted")]
        assert len(redacted) >= 1
        assert "content_hash" in redacted[0]
