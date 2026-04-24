# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W16 — ModelRegistry unit tests.

Exercises the pure validation / hashing / dataclass surface of
``kailash_ml.tracking.registry`` without any I/O. Storage round-trips
live in ``tests/integration/test_w16_registry_register.py``.
"""
from __future__ import annotations

import json
import warnings

import pytest
from kailash_ml.tracking import (
    InvalidModelNameError,
    Lineage,
    LineageRequiredError,
    ModelRegistry,
    ModelSignature,
    RegisterResult,
    SignatureMismatchError,
    default_idempotency_key,
)
from kailash_ml.tracking.registry import MODEL_NAME_REGEX, RESERVED_MODEL_NAME_PREFIXES

SIG = ModelSignature(
    inputs=(("x", "Float64", False, None), ("y", "Int64", True, (2,))),
    outputs=(("prediction", "Float64", False, None),),
    params={"C": 0.1, "solver": "lbfgs"},
)
LINEAGE = Lineage(
    run_id="run-test-1",
    dataset_hash="sha256:abc123",
    code_sha="0123deadbeef",
)


class TestModelNameValidation:
    """§3.3 — reserved prefix + regex."""

    @pytest.mark.parametrize(
        "name",
        ["_kml_foo", "system_health", "internal_state", "__dunder"],
    )
    def test_reserved_prefixes_rejected(self, name: str) -> None:
        with pytest.raises(InvalidModelNameError, match="reserved prefix"):
            ModelRegistry._validate_name(name)

    @pytest.mark.parametrize(
        "name",
        ["1starts_with_digit", "has space", "has.dot", "", "special$char"],
    )
    def test_regex_rejected(self, name: str) -> None:
        with pytest.raises(InvalidModelNameError):
            ModelRegistry._validate_name(name)

    @pytest.mark.parametrize(
        "name",
        [
            "fraud",
            "Fraud_Detector",
            "CreditScore-v2",
            "_user_facing",  # single-underscore OK per §3.3
            "a" * 128,  # max length
        ],
    )
    def test_valid_names_accepted(self, name: str) -> None:
        ModelRegistry._validate_name(name)  # no raise

    def test_name_too_long_rejected(self) -> None:
        with pytest.raises(InvalidModelNameError):
            ModelRegistry._validate_name("a" * 129)

    def test_non_string_rejected(self) -> None:
        with pytest.raises(InvalidModelNameError):
            ModelRegistry._validate_name(42)  # type: ignore[arg-type]

    def test_reserved_prefixes_constant_is_public(self) -> None:
        # The tuple is imported by downstream consumers (e.g. the
        # dataflow-ml-integration validator) — freezing its public
        # shape catches silent refactors that split one prefix across
        # two consumers.
        assert RESERVED_MODEL_NAME_PREFIXES == (
            "_kml_",
            "system_",
            "internal_",
            "__",
        )

    def test_regex_constant_matches_spec(self) -> None:
        # Spec §3.3 pins the regex. A refactor that widens the charset
        # silently permits names spec says are reserved. The leading
        # ``_`` in the character class matches the §3.3 prose "single-
        # underscore-prefix is permitted" — reserved-prefix enforcement
        # catches ``_kml_`` / ``__`` separately.
        assert MODEL_NAME_REGEX.pattern == r"^[a-zA-Z_][a-zA-Z0-9_-]{0,127}$"


class TestModelSignature:
    """§5.1 — canonical form + hash stability."""

    def test_canonical_json_is_deterministic(self) -> None:
        a = ModelSignature(
            inputs=(("x", "Float64", False, None),),
            outputs=(("y", "Int64", False, None),),
            params={"lr": 0.01, "batch": 32},
        )
        b = ModelSignature(
            inputs=(("x", "Float64", False, None),),
            outputs=(("y", "Int64", False, None),),
            # Same semantic params, different insertion order
            params={"batch": 32, "lr": 0.01},
        )
        assert a.canonical_json() == b.canonical_json()
        assert a.sha256() == b.sha256()

    def test_sha256_differs_on_semantic_change(self) -> None:
        a = SIG
        b = ModelSignature(
            inputs=(("x", "Float64", False, None),),  # dropped second input
            outputs=SIG.outputs,
            params=SIG.params,
        )
        assert a.sha256() != b.sha256()

    def test_canonical_json_shape(self) -> None:
        parsed = json.loads(SIG.canonical_json())
        assert set(parsed.keys()) == {"inputs", "outputs", "params"}
        assert parsed["inputs"][0] == ["x", "Float64", False, None]
        # Shape tuple is preserved as list
        assert parsed["inputs"][1] == ["y", "Int64", True, [2]]


class TestDefaultIdempotencyKey:
    """§7.3 — ``sha256(dataset_hash + code_sha + signature_json)``."""

    def test_same_inputs_same_key(self) -> None:
        k1 = default_idempotency_key(LINEAGE, SIG)
        k2 = default_idempotency_key(LINEAGE, SIG)
        assert k1 == k2

    def test_different_dataset_hash_changes_key(self) -> None:
        other = Lineage(
            run_id=LINEAGE.run_id,
            dataset_hash="sha256:DIFFERENT",
            code_sha=LINEAGE.code_sha,
        )
        assert default_idempotency_key(other, SIG) != default_idempotency_key(
            LINEAGE, SIG
        )

    def test_different_code_sha_changes_key(self) -> None:
        other = Lineage(
            run_id=LINEAGE.run_id,
            dataset_hash=LINEAGE.dataset_hash,
            code_sha="9876abc",
        )
        assert default_idempotency_key(other, SIG) != default_idempotency_key(
            LINEAGE, SIG
        )

    def test_different_signature_changes_key(self) -> None:
        other = ModelSignature(
            inputs=(("z", "Int64", False, None),),
            outputs=SIG.outputs,
        )
        assert default_idempotency_key(LINEAGE, other) != default_idempotency_key(
            LINEAGE, SIG
        )

    def test_run_id_does_NOT_affect_key(self) -> None:
        # Rerunning the same training dataset+code under a fresh run_id
        # MUST dedup (§7.3) — run_id is forensic metadata, not an input
        # to the idempotency hash.
        other = Lineage(
            run_id="completely-different-run",
            dataset_hash=LINEAGE.dataset_hash,
            code_sha=LINEAGE.code_sha,
        )
        assert default_idempotency_key(other, SIG) == default_idempotency_key(
            LINEAGE, SIG
        )


class TestLineageResolution:
    """§6.2 — registration without lineage MUST raise."""

    def test_missing_lineage_raises(self) -> None:
        with pytest.raises(LineageRequiredError, match="Lineage"):
            ModelRegistry._resolve_lineage(None, None)

    def test_empty_run_id_raises(self) -> None:
        with pytest.raises(LineageRequiredError, match="run_id"):
            ModelRegistry._resolve_lineage(
                Lineage(run_id="", dataset_hash="h", code_sha="c"),
                None,
            )

    def test_empty_dataset_hash_raises(self) -> None:
        with pytest.raises(LineageRequiredError, match="dataset_hash"):
            ModelRegistry._resolve_lineage(
                Lineage(run_id="r", dataset_hash="", code_sha="c"),
                None,
            )

    def test_empty_code_sha_raises(self) -> None:
        with pytest.raises(LineageRequiredError, match="code_sha"):
            ModelRegistry._resolve_lineage(
                Lineage(run_id="r", dataset_hash="h", code_sha=""),
                None,
            )

    def test_explicit_lineage_passes_through(self) -> None:
        out = ModelRegistry._resolve_lineage(LINEAGE, None)
        assert out is LINEAGE


class TestSignatureResolution:
    """§5.1 — registration without signature MUST raise."""

    def test_missing_signature_raises(self) -> None:
        with pytest.raises(SignatureMismatchError):
            ModelRegistry._require_signature(None, None)

    def test_explicit_signature_passes_through(self) -> None:
        out = ModelRegistry._require_signature(SIG, None)
        assert out is SIG


class TestRegisterResult:
    """§7.1 — frozen dataclass shape + §7.1.1 back-compat shim."""

    def _result(self, **overrides) -> RegisterResult:
        from datetime import datetime, timezone

        base = dict(
            tenant_id="acme",
            model_name="fraud",
            version=1,
            actor_id="agent-42",
            registered_at=datetime.now(timezone.utc),
            artifact_uris={"onnx": "file:///tmp/m.onnx"},
            signature_sha256="abc" * 21 + "a",
            lineage_run_id="run-1",
            lineage_dataset_hash="sha256:x",
            lineage_code_sha="0123",
        )
        base.update(overrides)
        return RegisterResult(**base)  # type: ignore[arg-type]

    def test_frozen(self) -> None:
        r = self._result()
        with pytest.raises(Exception):  # FrozenInstanceError
            r.version = 99  # type: ignore[misc]

    def test_artifact_uri_deprecation_warning(self) -> None:
        r = self._result()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            uri = r.artifact_uri
            assert uri == "file:///tmp/m.onnx"
            assert any(issubclass(x.category, DeprecationWarning) for x in w)

    def test_artifact_uri_prefers_onnx(self) -> None:
        r = self._result(artifact_uris={"onnx": "on", "pickle": "pk"})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            assert r.artifact_uri == "on"

    def test_artifact_uri_falls_back_to_single_entry(self) -> None:
        r = self._result(artifact_uris={"pickle": "pk"})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            assert r.artifact_uri == "pk"

    def test_artifact_uri_raises_on_empty(self) -> None:
        r = self._result(artifact_uris={})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with pytest.raises(KeyError):
                _ = r.artifact_uri
