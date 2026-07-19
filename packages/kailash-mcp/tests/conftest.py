# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shared test fixtures for kailash-mcp."""

from pathlib import Path

from kailash.testing.env_cost_guard import install_cost_guard, scrub_provider_secrets

# Load .env from the project root with the repo's LLM cost-guard applied.
# kailash-mcp declares its own pytest rootdir, so the repo-root conftest's
# cost-guard does NOT fire here. install_cost_guard withholds provider secret
# keys on a bare `pytest packages/kailash-mcp/tests`, monkeypatches
# dotenv.load_dotenv so any module-scope load_dotenv self-scrubs, and actively
# removes any secret already present — provider secrets load only with
# KAIZEN_ALLOW_REAL_LLM=1.
_project_root = Path(__file__).resolve().parents[3]
install_cost_guard(_project_root / ".env")


def pytest_collection_finish(session):
    """Backstop: remove any provider secret re-injected during collection."""
    scrub_provider_secrets()
