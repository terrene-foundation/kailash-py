# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shared test fixtures for kailash-mcp."""

from pathlib import Path

from kailash.testing.env_cost_guard import load_env_cost_guarded

# Load .env from the project root with the repo's LLM cost-guard applied.
# kailash-mcp declares its own pytest rootdir, so the repo-root conftest's
# cost-guard (which withholds provider secret keys on a bare pytest run) does
# NOT fire here. Loading via the shared guarded loader keeps a bare
# `pytest packages/kailash-mcp/tests` from re-injecting OPENAI_API_KEY and
# making a billed LLM call — provider secrets load only with
# KAIZEN_ALLOW_REAL_LLM=1.
_project_root = Path(__file__).resolve().parents[3]
load_env_cost_guarded(_project_root / ".env")
