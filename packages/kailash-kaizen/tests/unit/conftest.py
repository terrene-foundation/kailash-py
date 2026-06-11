"""Tier-1 unit-test conftest for kailash-kaizen.

Issue #829: trait derivation is now LLM-first via ``RoleToTraitsSignature``.
Tier-1 unit tests MUST NOT depend on a live LLM (``rules/testing.md``
§ 3-Tier Testing). The autouse fixture below stubs
``Kaizen._generate_role_based_traits`` with a deterministic default for the
duration of every unit test.

Tier-2 integration and Tier-3 e2e tests live below their own conftests and
DO NOT inherit this stub — derivation runs against the real LLM there.

Tests that want to exercise the LLM derivation explicitly can either:
1. Pass ``behavior_traits=[...]`` in config (skips derivation entirely — the
   documented user-facing escape hatch).
2. Override the autouse fixture via a sibling conftest.

The stub returns the same default list the keyword classifier returned for
"unmatched" roles before this fix, so any unit test that spot-checks
``agent.behavior_traits`` for the default keeps working.
"""

from __future__ import annotations

import os
from typing import List

import pytest

# Unit-tier deterministic model default (issue-822 pattern): agent/framework
# construction resolves the model from the environment and raises
# kaizen.errors.EnvModelMissing otherwise. No CI lane or committed .env
# supplies KAIZEN_DEFAULT_MODEL, so unit tests that construct agents without
# an explicit model fail on clean environments. setdefault preserves any
# operator/.env value; the env-model discipline tests
# (test_kaizen_default_model_env.py) monkeypatch.delenv/setenv per test and
# are unaffected.
os.environ.setdefault("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")

_DEFAULT_TIER1_TRAITS: List[str] = ["professional", "reliable", "adaptive"]


@pytest.fixture(autouse=True)
def _stub_trait_derivation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``Kaizen._generate_role_based_traits`` with a deterministic stub.

    Per Issue #829, real derivation calls an LLM. Tier-1 unit tests MUST NOT
    require a working LLM provider. This stub returns a fixed list so tests
    that rely on the default-derivation path stay deterministic and offline.
    """
    from kaizen.core.framework import Kaizen

    def _stub(self, role: str) -> List[str]:
        return list(_DEFAULT_TIER1_TRAITS)

    monkeypatch.setattr(Kaizen, "_generate_role_based_traits", _stub)
