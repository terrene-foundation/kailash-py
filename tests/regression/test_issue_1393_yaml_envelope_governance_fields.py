# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression for issue #1393 — YAML envelope governance fields silently dropped.

A YAML-authored constraint envelope's ``confidentiality_clearance`` and
``max_delegation_depth`` were silently discarded on the way to the runtime
engine: ``EnvelopeSpec`` had no slot for them, ``_parse_envelopes`` never read
them, and ``resolve_envelope`` never forwarded them into
``ConstraintEnvelopeConfig``. An operator authoring ``max_delegation_depth: 1``
(cap delegation) got ``None`` (UNLIMITED) at enforcement, with no error.

This regression pins that both fields survive load -> resolve onto the runtime
envelope config, and that malformed values fail closed.

Found by the holistic post-multi-wave redteam of the PACT KSP/Bridge epic.
"""

from __future__ import annotations

import pytest

from kailash.trust.pact.compilation import compile_org
from kailash.trust.pact.config import ConfidentialityLevel
from kailash.trust.pact.yaml_loader import ConfigurationError, load_org_from_dict
from kailash.trust.pact.yaml_resolvers import resolve_envelope

pytestmark = pytest.mark.regression

_BASE = {
    "org_id": "o",
    "name": "O",
    "roles": [{"id": "boss"}, {"id": "worker", "reports_to": "boss"}],
}


def _resolve_one_envelope(envelope_entry: dict):
    loaded = load_org_from_dict(dict(_BASE, envelopes=[envelope_entry]))
    compiled = compile_org(loaded.org_definition)
    return resolve_envelope(loaded.envelopes[0], compiled).envelope


def test_authored_clearance_and_depth_reach_runtime_config():
    """Both fields authored in YAML land on the resolved ConstraintEnvelopeConfig."""
    cfg = _resolve_one_envelope(
        {
            "target": "worker",
            "defined_by": "boss",
            "confidentiality_clearance": "restricted",
            "max_delegation_depth": 1,
        }
    )
    assert cfg.confidentiality_clearance is ConfidentialityLevel.RESTRICTED
    assert cfg.max_delegation_depth == 1


def test_omitted_fields_preserve_config_defaults():
    """Omitting the fields leaves the ConstraintEnvelopeConfig defaults intact."""
    cfg = _resolve_one_envelope({"target": "worker", "defined_by": "boss"})
    assert cfg.confidentiality_clearance is ConfidentialityLevel.PUBLIC
    assert cfg.max_delegation_depth is None


@pytest.mark.parametrize(
    "field, bad_value",
    [
        ("confidentiality_clearance", "nonsense"),
        # Unhashable YAML node positions (list / dict) MUST fail closed with a
        # ConfigurationError, not raise a raw `TypeError: unhashable type` from
        # the `in frozenset` membership test (redteam CC-1).
        ("confidentiality_clearance", ["public"]),
        ("confidentiality_clearance", {"level": "public"}),
        ("max_delegation_depth", 0),
        ("max_delegation_depth", -1),
        ("max_delegation_depth", True),  # bool is not a valid positive int depth
        ("max_delegation_depth", "2"),  # string is not an int
    ],
)
def test_malformed_governance_field_fails_closed(field, bad_value):
    """A malformed authored value raises ConfigurationError, never silently defaults."""
    with pytest.raises(ConfigurationError):
        load_org_from_dict(
            dict(
                _BASE,
                envelopes=[
                    {"target": "worker", "defined_by": "boss", field: bad_value}
                ],
            )
        )
