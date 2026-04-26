# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for ``kaizen.judges``.

Per ``rules/testing.md`` Tier 1 contract: mocks allowed, <1s per test,
no real LLM / network. Coverage scope follows ``specs/kaizen-judges.md``
§ 11 ("Test discipline") — 24 tests across construction, signatures,
scoring, position-swap bias mitigation, budget enforcement, error
taxonomy, classification redaction, and helper math.
"""
