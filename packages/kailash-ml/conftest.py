# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Pytest rootdir conftest for kailash-ml — installs the LLM cost-guard.

kailash-ml declares its own pytest rootdir, so the repo-root conftest guard
never fires for `pytest packages/kailash-ml`. install_cost_guard withholds
provider secret keys on a bare run, monkeypatches dotenv.load_dotenv so any
module-scope load_dotenv self-scrubs, and actively removes any secret already
present (incl. shell-exported) — provider secrets load only with
KAIZEN_ALLOW_REAL_LLM=1.
"""

from pathlib import Path

from kailash.testing.env_cost_guard import install_cost_guard, scrub_provider_secrets

install_cost_guard(Path(__file__).resolve().parents[2] / ".env")


def pytest_collection_finish(session):
    """Backstop: remove any provider secret re-injected during collection."""
    scrub_provider_secrets()
