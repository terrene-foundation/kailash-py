# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for the three allowlist helpers.

Each helper has the same contract: pass on hit, raise
:class:`BriefInterpretationError` with ``unknown_value`` set on miss.
Tests cover hit, miss, and edge cases (empty allowlist).
"""

from __future__ import annotations

import pytest

from kailash._from_brief.allowlist import (
    validate_config_value,
    validate_field_type,
    validate_node_type,
)
from kailash._from_brief.exceptions import BriefInterpretationError


class TestValidateNodeType:
    def test_known_passes(self):
        # No raise; returns None.
        validate_node_type("CSVReaderNode", {"CSVReaderNode", "WriterNode"})

    def test_unknown_raises_with_name(self):
        with pytest.raises(BriefInterpretationError) as excinfo:
            validate_node_type("UnknownNode", {"CSVReaderNode"})
        assert excinfo.value.unknown_value == "UnknownNode"
        assert excinfo.value.low_confidence is False
        assert excinfo.value.malformed is False

    def test_empty_allowlist_rejects_everything(self):
        with pytest.raises(BriefInterpretationError) as excinfo:
            validate_node_type("AnyNode", set())
        assert excinfo.value.unknown_value == "AnyNode"

    def test_case_sensitive(self):
        with pytest.raises(BriefInterpretationError):
            validate_node_type("csvreadernode", {"CSVReaderNode"})


class TestValidateFieldType:
    def test_known_passes(self):
        validate_field_type("str", {"str", "int", "float"})

    def test_unknown_raises_with_name(self):
        with pytest.raises(BriefInterpretationError) as excinfo:
            validate_field_type("exotic_pointer", {"str", "int"})
        assert excinfo.value.unknown_value == "exotic_pointer"

    def test_empty_allowlist_rejects(self):
        with pytest.raises(BriefInterpretationError):
            validate_field_type("anything", set())


class TestValidateConfigValue:
    ALLOWED = {
        "mode": {"json", "yaml", "csv"},
        "compression": {"none", "gzip"},
    }

    def test_known_field_known_value_passes(self):
        validate_config_value("mode", "json", self.ALLOWED)

    def test_known_field_unknown_value_raises(self):
        with pytest.raises(BriefInterpretationError) as excinfo:
            validate_config_value("mode", "xml", self.ALLOWED)
        assert excinfo.value.unknown_value == "xml"

    def test_unknown_field_raises_with_field_name(self):
        with pytest.raises(BriefInterpretationError) as excinfo:
            validate_config_value("unknown_field", "whatever", self.ALLOWED)
        assert excinfo.value.unknown_value == "unknown_field"

    def test_empty_allowlist_dict_rejects_every_field(self):
        with pytest.raises(BriefInterpretationError) as excinfo:
            validate_config_value("mode", "json", {})
        assert excinfo.value.unknown_value == "mode"

    def test_field_with_empty_value_set_rejects(self):
        with pytest.raises(BriefInterpretationError) as excinfo:
            validate_config_value("mode", "json", {"mode": set()})
        assert excinfo.value.unknown_value == "json"
