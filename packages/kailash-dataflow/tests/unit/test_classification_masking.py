# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for standalone masking primitives (GH #1337).

Covers the directly-callable masking surface + the record-agnostic redaction
filter, AND the byte-for-byte alignment between the free functions and the
classification-aware ``ClassificationPolicy.apply_masking_strategy`` dispatch.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re

import pytest

from dataflow.classification import (
    ClassificationPolicy,
    MaskingStrategy,
    RedactionFilter,
    hash_value,
    last_four,
    redact,
    redact_mapping,
    redact_text,
)


@pytest.mark.unit
class TestHashValue:
    def test_unsalted_is_plain_sha256(self) -> None:
        assert hash_value("secret") == hashlib.sha256(b"secret").hexdigest()

    def test_salted_is_hmac_sha256(self) -> None:
        expected = hmac.new(b"pepper", b"secret", hashlib.sha256).hexdigest()
        assert hash_value("secret", salt="pepper") == expected

    def test_salt_changes_digest(self) -> None:
        assert hash_value("secret") != hash_value("secret", salt="pepper")

    def test_deterministic(self) -> None:
        assert hash_value("x", salt="s") == hash_value("x", salt="s")

    def test_bytes_salt_accepted(self) -> None:
        assert hash_value("x", salt=b"s") == hash_value("x", salt="s")

    def test_length_truncates(self) -> None:
        full = hash_value("x")
        assert hash_value("x", length=16) == full[:16]
        assert len(hash_value("x", length=8)) == 8

    def test_negative_length_raises(self) -> None:
        with pytest.raises(ValueError):
            hash_value("x", length=-1)

    def test_non_str_value_coerced(self) -> None:
        assert hash_value(12345) == hashlib.sha256(b"12345").hexdigest()


@pytest.mark.unit
class TestLastFour:
    def test_masks_all_but_last_four(self) -> None:
        assert last_four("4111111111111111") == "************1111"

    def test_short_string_fully_masked(self) -> None:
        assert last_four("abcd") == "****"
        assert last_four("ab") == "**"

    def test_empty_string(self) -> None:
        assert last_four("") == ""

    def test_only_last_four_survive(self) -> None:
        out = last_four("supersecret99")
        assert out.endswith("t99")
        assert out[:-4] == "*" * (len("supersecret99") - 4)


@pytest.mark.unit
class TestRedact:
    def test_constant_sentinel(self) -> None:
        assert redact() == "[REDACTED]"
        assert redact("anything") == "[REDACTED]"
        assert redact(12345) == "[REDACTED]"


@pytest.mark.unit
class TestPolicyDelegationParity:
    """apply_masking_strategy MUST stay byte-for-byte aligned with the free funcs."""

    def test_hash_parity(self) -> None:
        assert ClassificationPolicy.apply_masking_strategy(
            "v", MaskingStrategy.HASH
        ) == hash_value("v")

    def test_last_four_parity(self) -> None:
        assert ClassificationPolicy.apply_masking_strategy(
            "4111111111111111", MaskingStrategy.LAST_FOUR
        ) == last_four("4111111111111111")

    def test_redact_parity(self) -> None:
        assert (
            ClassificationPolicy.apply_masking_strategy("v", MaskingStrategy.REDACT)
            == redact()
        )

    def test_none_passthrough(self) -> None:
        assert (
            ClassificationPolicy.apply_masking_strategy("v", MaskingStrategy.NONE)
            == "v"
        )

    def test_encrypt_sentinel(self) -> None:
        assert (
            ClassificationPolicy.apply_masking_strategy("v", MaskingStrategy.ENCRYPT)
            == "[ENCRYPTED]"
        )

    def test_none_value(self) -> None:
        assert (
            ClassificationPolicy.apply_masking_strategy(None, MaskingStrategy.HASH)
            is None
        )

    def test_unknown_strategy_fails_closed(self) -> None:
        # Raw-string unknown value reaches the fail-closed default.
        assert ClassificationPolicy.apply_masking_strategy("v", "bogus") == "[REDACTED]"

    def test_raw_string_strategy_dispatches(self) -> None:
        # MaskingStrategy is a str-Enum; raw values dispatch identically.
        assert ClassificationPolicy.apply_masking_strategy(
            "4111111111111111", "last_four"
        ) == last_four("4111111111111111")


@pytest.mark.unit
class TestRedactText:
    def test_no_patterns_passthrough(self) -> None:
        assert redact_text("hello") == "hello"

    def test_pattern_redacted(self) -> None:
        assert redact_text("card 4111111111111111", [r"\d{16}"]) == "card [REDACTED]"

    def test_strategy_applied_to_match(self) -> None:
        assert (
            redact_text("card 4111111111111111", [r"\d{16}"], strategy="last_four")
            == "card ************1111"
        )

    def test_compiled_pattern_accepted(self) -> None:
        pat = re.compile(r"\d{16}")
        assert redact_text("4111111111111111", [pat]) == "[REDACTED]"

    def test_multiple_patterns(self) -> None:
        out = redact_text(
            "ssn 123-45-6789 card 4111111111111111",
            [r"\d{3}-\d{2}-\d{4}", r"\d{16}"],
        )
        assert "123-45-6789" not in out
        assert "4111111111111111" not in out


@pytest.mark.unit
class TestRedactMapping:
    def test_key_redaction(self) -> None:
        assert redact_mapping({"ssn": "123", "ok": "y"}, keys=["ssn"]) == {
            "ssn": "[REDACTED]",
            "ok": "y",
        }

    def test_key_case_insensitive(self) -> None:
        assert redact_mapping({"SSN": "123"}, keys=["ssn"])["SSN"] == "[REDACTED]"

    def test_pattern_redaction(self) -> None:
        out = redact_mapping({"note": "card 4111111111111111"}, patterns=[r"\d{16}"])
        assert "4111111111111111" not in out["note"]

    def test_nested_mapping(self) -> None:
        out = redact_mapping({"a": {"ssn": "123"}}, keys=["ssn"])
        assert out["a"]["ssn"] == "[REDACTED]"

    def test_non_mapping_passthrough(self) -> None:
        assert redact_mapping(("a", "b"), keys=["x"]) == ("a", "b")
        assert redact_mapping("plain", keys=["x"]) == "plain"

    def test_strategy_on_key(self) -> None:
        out = redact_mapping(
            {"card": "4111111111111111"}, keys=["card"], strategy="last_four"
        )
        assert out["card"] == "************1111"


@pytest.mark.unit
class TestRedactionFilter:
    def _record(self, msg: str, args) -> logging.LogRecord:
        return logging.LogRecord("t", logging.INFO, "f.py", 1, msg, args, None)

    def test_returns_true_always(self) -> None:
        flt = RedactionFilter(patterns=[r"\d{16}"])
        rec = self._record("card 4111111111111111", None)
        assert flt.filter(rec) is True

    def test_pattern_redacts_rendered_message(self) -> None:
        flt = RedactionFilter(patterns=[r"\d{16}"], strategy="last_four")
        rec = self._record("card %s ok", ("4111111111111111",))
        flt.filter(rec)
        assert rec.getMessage() == "card ************1111 ok"

    def test_mapping_arg_key_redaction(self) -> None:
        flt = RedactionFilter(keys=["ssn"])
        rec = self._record("user %(name)s ssn=%(ssn)s", {"name": "a", "ssn": "123"})
        flt.filter(rec)
        assert "123" not in rec.getMessage()
        assert "a" in rec.getMessage()

    def test_no_config_is_noop(self) -> None:
        flt = RedactionFilter()
        rec = self._record("nothing %s", ("sensitive",))
        flt.filter(rec)
        assert rec.getMessage() == "nothing sensitive"

    def test_non_string_msg_does_not_raise(self) -> None:
        flt = RedactionFilter(patterns=[r"\d{16}"])
        rec = self._record(12345, None)  # type: ignore[arg-type]
        assert flt.filter(rec) is True

    def test_tuple_string_args_redacted(self) -> None:
        # No %-placeholder for the arg: tuple-arg redaction still applies.
        flt = RedactionFilter(patterns=[r"\d{16}"])
        rec = self._record("plain message", ("4111111111111111",))
        flt.filter(rec)
        # getMessage() with no placeholder ignores args, but the arg itself
        # was redacted in place.
        assert rec.args == ("[REDACTED]",)

    def test_is_logging_filter_subclass(self) -> None:
        assert issubclass(RedactionFilter, logging.Filter)
