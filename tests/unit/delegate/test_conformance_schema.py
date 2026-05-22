"""Tier-1 tests for the kailash.delegate.conformance schema (S7, #1035).

Covers the behavioural-only vector schema (vendored from rs canonical),
:func:`receipts_agree` counts-based protocol, :func:`receipts_agree_dict`
dict-shape comparator, and :class:`ConformanceVectorLoader` tamper-
detection.

Tier-1 (no infrastructure): the schema is pure data; tests are pure
constructor/serde round-trip checks. Fence B verified by the package
shell test (`test_package_shell.py`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kailash.delegate.conformance import (
    BehaviouralOutcome,
    ConformanceReceipt,
    ConformanceVector,
    ConformanceVectorIntegrityError,
    ConformanceVectorLoader,
    ReceiptError,
    ReceiptsAgreeReport,
    ReceiptsAgreementError,
    SchemaError,
    SpecAnchor,
    assert_receipts_agree,
    canonical_vector_set_digest,
    receipts_agree,
    receipts_agree_dict,
    validate_vector_set,
)


# ---------------------------------------------------------------------------
# SpecAnchor -- mandatory dotted-decimal Delegate-spec § anchor
# ---------------------------------------------------------------------------


class TestSpecAnchor:
    def test_accepts_dotted_decimal_sections(self) -> None:
        for section in ("7", "7.3", "11", "12.1", "3.4.2"):
            anchor = SpecAnchor.from_str(section)
            assert anchor.section == section
            assert anchor.to_wire() == section
            assert str(anchor) == f"§{section}"

    @pytest.mark.parametrize(
        "bad",
        ["", ".7", "7.", "7..3", "seven", "§7.3", "7.3a", "F1"],
    )
    def test_rejects_malformed_sections(self, bad: str) -> None:
        with pytest.raises(SchemaError) as excinfo:
            SpecAnchor.from_str(bad)
        assert excinfo.value.kind == "invalid_spec_anchor"

    def test_frozen(self) -> None:
        anchor = SpecAnchor.from_str("7.3")
        with pytest.raises(AttributeError):
            anchor.section = "9"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BehaviouralOutcome -- CLOSED taxonomy
# ---------------------------------------------------------------------------


class TestBehaviouralOutcome:
    def test_closed_taxonomy_pascal_case_values(self) -> None:
        # Wire shape MUST be PascalCase (rs serde default).
        assert BehaviouralOutcome.ACCEPT.value == "Accept"
        assert BehaviouralOutcome.REJECT.value == "Reject"
        assert BehaviouralOutcome.ESCALATE_TO_HUMAN.value == "EscalateToHuman"

    def test_from_wire_round_trip(self) -> None:
        for member in BehaviouralOutcome:
            assert BehaviouralOutcome.from_wire(member.value) is member

    def test_from_wire_rejects_unknown_variant(self) -> None:
        with pytest.raises(SchemaError) as excinfo:
            BehaviouralOutcome.from_wire("TighteningOrder")
        assert excinfo.value.kind == "unknown_outcome"


# ---------------------------------------------------------------------------
# ConformanceVector -- spec-anchored behavioural assertion
# ---------------------------------------------------------------------------


def _make_vector(
    id_: str = "DV-7.3-001",
    section: str = "7.3",
    expected: BehaviouralOutcome = BehaviouralOutcome.REJECT,
) -> ConformanceVector:
    return ConformanceVector(
        id=id_,
        spec_anchor=SpecAnchor.from_str(section),
        given="Genesis Record G and a Delegation D",
        behaviour="the runtime MUST exhibit the spec-§ behaviour",
        expected=expected,
    )


class TestConformanceVector:
    def test_carries_mandatory_spec_anchor(self) -> None:
        v = _make_vector()
        assert v.spec_anchor.section == "7.3"
        assert v.expected is BehaviouralOutcome.REJECT
        v.validate()

    @pytest.mark.parametrize(
        ("id_", "given", "behaviour", "want_field"),
        [
            ("", "g", "b", "id"),
            ("DV-1", "", "b", "given"),
            ("DV-1", "g", "  ", "behaviour"),
        ],
    )
    def test_rejects_empty_required_fields(
        self, id_: str, given: str, behaviour: str, want_field: str
    ) -> None:
        with pytest.raises(SchemaError) as excinfo:
            ConformanceVector(
                id=id_,
                spec_anchor=SpecAnchor.from_str("7.3"),
                given=given,
                behaviour=behaviour,
                expected=BehaviouralOutcome.ACCEPT,
            )
        assert excinfo.value.kind == "empty_field"
        assert excinfo.value.detail.get("field") == want_field

    def test_expected_is_closed_behavioural_taxonomy(self) -> None:
        # Constructing with each member MUST succeed; constructing with
        # something OUTSIDE the enum MUST fail at validate().
        for outcome in BehaviouralOutcome:
            v = _make_vector(expected=outcome)
            assert v.expected is outcome
        with pytest.raises(SchemaError) as excinfo:
            ConformanceVector(
                id="DV-1",
                spec_anchor=SpecAnchor.from_str("7"),
                given="g",
                behaviour="b",
                expected="not-an-enum",  # type: ignore[arg-type]
            )
        assert "expected" in str(excinfo.value)

    def test_to_dict_from_dict_round_trip(self) -> None:
        original = _make_vector(
            id_="DV-12.1-001",
            section="12.1",
            expected=BehaviouralOutcome.ESCALATE_TO_HUMAN,
        )
        data = original.to_dict()
        # Wire shape: bare section string, PascalCase outcome.
        assert data["spec_anchor"] == "12.1"
        assert data["expected"] == "EscalateToHuman"
        restored = ConformanceVector.from_dict(data)
        assert restored == original

    def test_from_dict_rejects_empty_required_fields(self) -> None:
        bad = {
            "id": "",
            "spec_anchor": "7.3",
            "given": "g",
            "behaviour": "b",
            "expected": "Accept",
        }
        with pytest.raises(SchemaError) as excinfo:
            ConformanceVector.from_dict(bad)
        assert excinfo.value.kind == "empty_field"

    def test_from_dict_rejects_malformed_anchor(self) -> None:
        bad = {
            "id": "DV-1",
            "spec_anchor": "engine-internal",
            "given": "g",
            "behaviour": "b",
            "expected": "Reject",
        }
        with pytest.raises(SchemaError) as excinfo:
            ConformanceVector.from_dict(bad)
        assert excinfo.value.kind == "invalid_spec_anchor"

    def test_from_dict_rejects_unknown_outcome(self) -> None:
        bad = {
            "id": "DV-1",
            "spec_anchor": "7.3",
            "given": "g",
            "behaviour": "b",
            "expected": "TighteningOrder",
        }
        with pytest.raises(SchemaError) as excinfo:
            ConformanceVector.from_dict(bad)
        assert excinfo.value.kind == "unknown_outcome"

    def test_from_dict_requires_dict_type(self) -> None:
        with pytest.raises(TypeError):
            ConformanceVector.from_dict("not-a-dict")  # type: ignore[arg-type]


class TestValidateVectorSet:
    def test_accepts_unique_well_formed_set(self) -> None:
        validate_vector_set(
            [
                _make_vector("DV-7.3-001", "7.3", BehaviouralOutcome.REJECT),
                _make_vector("DV-7.3-002", "7.3", BehaviouralOutcome.ACCEPT),
                _make_vector(
                    "DV-12.1-001", "12.1", BehaviouralOutcome.ESCALATE_TO_HUMAN
                ),
            ]
        )

    def test_rejects_duplicate_ids(self) -> None:
        with pytest.raises(SchemaError) as excinfo:
            validate_vector_set(
                [
                    _make_vector("DV-7.3-001", "7.3"),
                    _make_vector("DV-7.3-001", "9"),
                ]
            )
        assert excinfo.value.kind == "duplicate_id"
        assert excinfo.value.detail.get("id") == "DV-7.3-001"

    def test_empty_set_is_valid(self) -> None:
        validate_vector_set([])


# ---------------------------------------------------------------------------
# ConformanceReceipt + receipts_agree (F4 counts-based)
# ---------------------------------------------------------------------------


def _receipt(
    impl: str = "kailash-py",
    version: str = "0.1.0",
    sha: str = "abc123",
    total: int = 5,
    passed: int = 5,
) -> ConformanceReceipt:
    return ConformanceReceipt(
        implementation=impl,
        vector_crate_version=version,
        commit_sha=sha,
        vectors_total=total,
        vectors_passed=passed,
    )


class TestConformanceReceipt:
    @pytest.mark.parametrize(
        ("impl", "version", "sha", "want_field"),
        [
            ("", "0.1.0", "abc", "implementation"),
            ("kailash-py", "", "abc", "vector_crate_version"),
            ("kailash-py", "0.1.0", "   ", "commit_sha"),
        ],
    )
    def test_rejects_empty_identity_fields(
        self, impl: str, version: str, sha: str, want_field: str
    ) -> None:
        with pytest.raises(ReceiptError) as excinfo:
            ConformanceReceipt(
                implementation=impl,
                vector_crate_version=version,
                commit_sha=sha,
                vectors_total=2,
                vectors_passed=2,
            )
        assert excinfo.value.kind == "empty_field"
        assert excinfo.value.detail.get("field") == want_field

    def test_rejects_passed_exceeding_total(self) -> None:
        with pytest.raises(ReceiptError) as excinfo:
            ConformanceReceipt(
                implementation="kailash-py",
                vector_crate_version="0.1.0",
                commit_sha="abc",
                vectors_total=2,
                vectors_passed=3,
            )
        assert excinfo.value.kind == "passed_exceeds_total"

    def test_conforms_requires_nonempty_fully_passing_run(self) -> None:
        assert _receipt(total=2, passed=2).conforms()
        assert not _receipt(total=2, passed=1).conforms()
        # Empty run asserts nothing -- does NOT conform.
        assert not _receipt(total=0, passed=0).conforms()

    def test_to_dict_from_dict_round_trip(self) -> None:
        r = _receipt(impl="kailash-py", version="0.2.1", sha="abc123def456")
        restored = ConformanceReceipt.from_dict(r.to_dict())
        assert restored == r

    def test_from_dict_rejects_invalid_receipt(self) -> None:
        bad = {
            "implementation": "kailash-py",
            "vector_crate_version": "0.1.0",
            "commit_sha": "abc",
            "vectors_total": 2,
            "vectors_passed": 5,
        }
        with pytest.raises(ReceiptError) as excinfo:
            ConformanceReceipt.from_dict(bad)
        assert excinfo.value.kind == "passed_exceeds_total"

    def test_from_dict_requires_dict_type(self) -> None:
        with pytest.raises(TypeError):
            ConformanceReceipt.from_dict([1, 2, 3])  # type: ignore[arg-type]


class TestReceiptsAgree:
    """Mirrors rs receipts_agree (receipt.rs §215-221) semantics."""

    def test_agree_when_same_vector_set_and_both_conform(self) -> None:
        rs = _receipt("kailash-rs")
        py = _receipt("kailash-py")
        assert receipts_agree(rs, py)
        # Symmetric.
        assert receipts_agree(py, rs)

    def test_disagree_on_version_mismatch(self) -> None:
        rs = _receipt("kailash-rs", version="0.1.0")
        py = _receipt("kailash-py", version="0.2.0")
        assert not receipts_agree(rs, py)

    def test_disagree_on_sha_mismatch(self) -> None:
        rs = _receipt("kailash-rs", sha="abc")
        py = _receipt("kailash-py", sha="def")
        assert not receipts_agree(rs, py)

    def test_disagree_when_either_run_did_not_conform(self) -> None:
        rs = _receipt("kailash-rs", total=5, passed=5)
        py_partial = _receipt("kailash-py", total=5, passed=4)
        assert not receipts_agree(rs, py_partial)

    def test_disagree_for_same_implementation(self) -> None:
        # Cross-impl claim REQUIRES distinct impls.
        a = _receipt("kailash-py")
        b = _receipt("kailash-py")
        assert not receipts_agree(a, b)
        # Self-agree also rejected.
        assert not receipts_agree(a, a)


# ---------------------------------------------------------------------------
# receipts_agree_dict -- dict-shape parity (the brief's intent)
# ---------------------------------------------------------------------------


def _runtime_result_dict(
    *,
    run_id: str = "00000000-0000-0000-0000-000000000001",
    audit_head: str | None = "0" * 64,
    terminated_at: str = "2026-05-22T00:00:00+00:00",
    posture: str = "EXECUTE",
    transitions: list[dict] | None = None,
    audit_entries: list[str] | None = None,
) -> dict:
    """Build a RuntimeExecutionResult-shaped dict for comparator testing.

    Mirrors the Python ``RuntimeExecutionResult.to_dict()`` shape without
    importing it (the conformance/ subpackage is Fence-B-fenced).
    """
    return {
        "run_id": run_id,
        "dispatch_result": {
            "connector_id": "test-connector",
            "executed_at": "2026-05-22T00:00:00+00:00",
            "audit_chain_entries": audit_entries or ["a1", "a2", "a3"],
            "payload": {"key": "value"},
        },
        "taod_state": {
            "transitions": transitions
            or [
                {"phase": "INITIATED", "at": "2026-05-22T00:00:00+00:00"},
                {"phase": "THINKING", "at": "2026-05-22T00:00:01+00:00"},
                {"phase": "COMPLETED", "at": "2026-05-22T00:00:02+00:00"},
            ],
            "current": "COMPLETED",
        },
        "audit_head_hash": audit_head,
        "terminated_at": terminated_at,
        "posture_at_execute": posture,
    }


class TestReceiptsAgreeDict:
    def test_identical_dicts_agree(self) -> None:
        a = _runtime_result_dict()
        b = _runtime_result_dict()
        report = receipts_agree_dict(a, b)
        assert report.agree is True
        assert report.mismatches == ()

    def test_run_id_divergence_flagged(self) -> None:
        a = _runtime_result_dict(run_id="aaaaaaaa-0000-0000-0000-000000000000")
        b = _runtime_result_dict(run_id="bbbbbbbb-0000-0000-0000-000000000000")
        report = receipts_agree_dict(a, b)
        assert report.agree is False
        assert "run_id" in report.mismatches

    def test_timestamps_ignored_by_default(self) -> None:
        # terminated_at differs but agreement holds (excluded by default).
        a = _runtime_result_dict(terminated_at="2026-01-01T00:00:00+00:00")
        b = _runtime_result_dict(terminated_at="2099-12-31T23:59:59+00:00")
        report = receipts_agree_dict(a, b)
        assert report.agree is True
        assert "terminated_at" in report.excluded_fields

    def test_nested_executed_at_ignored(self) -> None:
        # executed_at lives inside dispatch_result -- still excluded.
        a = _runtime_result_dict()
        b = _runtime_result_dict()
        b["dispatch_result"]["executed_at"] = "2099-12-31T23:59:59+00:00"
        report = receipts_agree_dict(a, b)
        assert report.agree is True

    def test_audit_chain_entries_ordered_comparison(self) -> None:
        # Reordering audit entries MUST surface as divergence (chain order
        # is part of the cross-impl contract).
        a = _runtime_result_dict(audit_entries=["a1", "a2", "a3"])
        b = _runtime_result_dict(audit_entries=["a3", "a2", "a1"])
        report = receipts_agree_dict(a, b)
        assert report.agree is False
        # First element differs at index 0.
        assert any("audit_chain_entries[0]" in m for m in report.mismatches)

    def test_transitions_ordered_comparison(self) -> None:
        # TAOD transitions are ordered; phase swap MUST flag.
        a_trans = [
            {"phase": "INITIATED", "at": "t0"},
            {"phase": "THINKING", "at": "t1"},
            {"phase": "COMPLETED", "at": "t2"},
        ]
        b_trans = [
            {"phase": "INITIATED", "at": "t0"},
            {"phase": "COMPLETED", "at": "t1"},  # swapped
            {"phase": "THINKING", "at": "t2"},
        ]
        report = receipts_agree_dict(
            _runtime_result_dict(transitions=a_trans),
            _runtime_result_dict(transitions=b_trans),
        )
        assert report.agree is False
        # signed_at is excluded; but 'phase' under transitions[1] differs.
        # The 'at' field is NOT in default exclusions (only signed_at /
        # executed_at / terminated_at / started_at); but for THIS test we
        # care about the phase column.
        assert any("transitions[1]" in m for m in report.mismatches)

    def test_audit_head_hash_divergence_flagged(self) -> None:
        a = _runtime_result_dict(audit_head="a" * 64)
        b = _runtime_result_dict(audit_head="b" * 64)
        report = receipts_agree_dict(a, b)
        assert report.agree is False
        assert "audit_head_hash" in report.mismatches

    def test_caller_supplied_exclusions_union_with_defaults(self) -> None:
        # Adding 'run_id' to caller exclusions: defaults still apply
        # (timestamps still excluded).
        a = _runtime_result_dict(
            run_id="aaa", terminated_at="2026-01-01T00:00:00+00:00"
        )
        b = _runtime_result_dict(
            run_id="bbb", terminated_at="2099-12-31T23:59:59+00:00"
        )
        report = receipts_agree_dict(a, b, exclude_fields=frozenset({"run_id"}))
        assert report.agree is True
        # Both run_id (caller) and terminated_at (default) excluded.
        assert "run_id" in report.excluded_fields
        assert "terminated_at" in report.excluded_fields

    def test_mismatch_details_carry_both_values(self) -> None:
        a = _runtime_result_dict(audit_head="aaa" * 21 + "a")  # 64 chars
        b = _runtime_result_dict(audit_head="bbb" * 21 + "b")
        report = receipts_agree_dict(a, b)
        assert "audit_head_hash" in report.mismatch_details
        a_val, b_val = report.mismatch_details["audit_head_hash"]
        assert a_val.startswith("aaa")
        assert b_val.startswith("bbb")

    def test_extra_key_in_one_dict_flagged(self) -> None:
        a = _runtime_result_dict()
        b = _runtime_result_dict()
        b["extra_field"] = "unexpected"
        report = receipts_agree_dict(a, b)
        assert report.agree is False


class TestAssertReceiptsAgree:
    def test_passes_silently_on_agreement(self) -> None:
        a = _runtime_result_dict()
        b = _runtime_result_dict()
        # No exception.
        assert_receipts_agree(a, b)

    def test_raises_typed_error_with_report_on_disagreement(self) -> None:
        a = _runtime_result_dict(run_id="aaa")
        b = _runtime_result_dict(run_id="bbb")
        with pytest.raises(ReceiptsAgreementError) as excinfo:
            assert_receipts_agree(a, b)
        assert isinstance(excinfo.value.report, ReceiptsAgreeReport)
        assert excinfo.value.report.agree is False
        assert "run_id" in excinfo.value.report.mismatches


# ---------------------------------------------------------------------------
# ConformanceVectorLoader -- tamper-evident fixture loading
# ---------------------------------------------------------------------------


class TestConformanceVectorLoader:
    def test_load_canonical_succeeds(self) -> None:
        vectors = ConformanceVectorLoader.load_canonical()
        assert len(vectors) == 5
        # All five canonical IDs present.
        ids = {v.id for v in vectors}
        assert ids == {"DV-3-001", "DV-5-001", "DV-7-001", "DV-9-001", "DV-10-001"}

    def test_load_canonical_returns_tuple(self) -> None:
        vectors = ConformanceVectorLoader.load_canonical()
        # Tuple = immutable; callers cannot mutate the canonical set.
        assert isinstance(vectors, tuple)

    def test_integrity_check_detects_tamper(self, tmp_path: Path) -> None:
        # Build a valid fixture in tmp, then mutate ONE vector body without
        # updating the digest; load MUST fail.
        v = _make_vector()
        digest = canonical_vector_set_digest([v])
        fixture = {
            "schema_version": 1,
            "digest": digest,
            "vectors": [v.to_dict()],
        }
        path = tmp_path / "tampered.json"
        path.write_text(json.dumps(fixture), encoding="utf-8")
        # Load clean first.
        ConformanceVectorLoader.load_from_file(path)
        # Now mutate the vector body -- digest no longer matches.
        fixture["vectors"][0]["given"] = "mutated scenario"
        path.write_text(json.dumps(fixture), encoding="utf-8")
        with pytest.raises(ConformanceVectorIntegrityError):
            ConformanceVectorLoader.load_from_file(path)

    def test_load_from_file_rejects_wrong_schema_version(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text(
            json.dumps({"schema_version": 999, "digest": "x", "vectors": []}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="schema_version"):
            ConformanceVectorLoader.load_from_file(path)

    def test_load_from_file_rejects_missing_digest(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text(
            json.dumps({"schema_version": 1, "vectors": []}),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="digest"):
            ConformanceVectorLoader.load_from_file(path)

    def test_load_from_file_rejects_malformed_vector(self, tmp_path: Path) -> None:
        bad_vector = {
            "id": "",  # empty id triggers SchemaError
            "spec_anchor": "7.3",
            "given": "g",
            "behaviour": "b",
            "expected": "Accept",
        }
        path = tmp_path / "bad.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "digest": "ignored-validation-fails-first",
                    "vectors": [bad_vector],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(SchemaError) as excinfo:
            ConformanceVectorLoader.load_from_file(path)
        assert excinfo.value.kind == "empty_field"

    def test_load_from_file_rejects_duplicate_ids(self, tmp_path: Path) -> None:
        v1 = _make_vector("DUP", "7.3").to_dict()
        v2 = _make_vector("DUP", "9").to_dict()
        path = tmp_path / "dup.json"
        # Compute the digest as if the file were honest, so we get past
        # the integrity check and into validate_vector_set.
        from kailash.delegate.conformance.schema import _canonical_json_bytes
        import hashlib

        digest = hashlib.sha256(_canonical_json_bytes([v1, v2])).hexdigest()
        path.write_text(
            json.dumps({"schema_version": 1, "digest": digest, "vectors": [v1, v2]}),
            encoding="utf-8",
        )
        with pytest.raises(SchemaError) as excinfo:
            ConformanceVectorLoader.load_from_file(path)
        assert excinfo.value.kind == "duplicate_id"

    def test_load_from_file_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            ConformanceVectorLoader.load_from_file(tmp_path / "does-not-exist.json")

    def test_load_from_file_rejects_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "junk.json"
        path.write_text("not json at all {{{", encoding="utf-8")
        with pytest.raises(ValueError, match="not valid JSON"):
            ConformanceVectorLoader.load_from_file(path)


class TestCanonicalVectorSetDigest:
    def test_digest_is_deterministic(self) -> None:
        v = _make_vector()
        d1 = canonical_vector_set_digest([v])
        d2 = canonical_vector_set_digest([v])
        assert d1 == d2

    def test_digest_changes_on_content_change(self) -> None:
        v1 = _make_vector(id_="A")
        v2 = _make_vector(id_="B")
        assert canonical_vector_set_digest([v1]) != canonical_vector_set_digest([v2])

    def test_digest_order_sensitive(self) -> None:
        # Re-ordering vectors changes the digest by design (the canonical
        # set order is part of the contract).
        a = _make_vector(id_="A")
        b = _make_vector(id_="B")
        assert canonical_vector_set_digest([a, b]) != canonical_vector_set_digest(
            [b, a]
        )
