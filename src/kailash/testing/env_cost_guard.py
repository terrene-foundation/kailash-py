# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cost-guarded ``.env`` loader shared by sub-package test conftests.

Mirrors the repo-root ``conftest.py`` LLM cost-guard. The root guard withholds
provider secret keys from ``os.environ`` on a bare ``pytest`` run unless the
operator opted in via ``KAIZEN_ALLOW_REAL_LLM=1``, so a test that would reach a
provider finds no credential and cannot bill.

Sub-packages that declare their own pytest ``rootdir`` (e.g. ``kailash-mcp``),
or test subtrees that call ``load_dotenv()`` directly, do NOT get the root
conftest's ``pytest_configure`` guard. Loading their ``.env`` through
:func:`load_env_cost_guarded` keeps a bare ``pytest <subtree>`` run from
re-injecting ``OPENAI_API_KEY`` (and the other ``*_API_KEY`` / ``*_SECRET``
keys) and making a billed LLM call. Model names, DB URLs, and every other
non-secret var still load; already-set env vars are never overridden.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_REAL_LLM_ENV_FLAG = "KAIZEN_ALLOW_REAL_LLM"


def _real_llm_allowed() -> bool:
    """True only when the operator has explicitly opted into real LLM calls."""
    return os.environ.get(_REAL_LLM_ENV_FLAG) == "1"


def _is_provider_secret(key: str) -> bool:
    """A key is a provider secret if it matches the ``*_API_KEY`` / ``*_SECRET``
    secret-name conventions (same predicate as the repo-root conftest)."""
    return key.endswith("_API_KEY") or key.endswith("_SECRET")


def load_env_cost_guarded(env_path: Optional[Path] = None) -> None:
    """Load ``.env`` into ``os.environ`` with the LLM cost-guard applied.

    Provider secret keys are withheld unless ``KAIZEN_ALLOW_REAL_LLM=1``. Model
    names, DB URLs, and other non-secret vars load normally; an already-set env
    var is never overridden.

    Args:
        env_path: Path to the ``.env`` file. When ``None``, the nearest ``.env``
            is located by walking up from the current working directory.
    """
    from dotenv import dotenv_values, find_dotenv

    if env_path is None:
        found = find_dotenv(usecwd=True)
        if not found:
            return
        env_path = Path(found)
    env_path = Path(env_path)
    if not env_path.exists():
        return

    allow_real_llm = _real_llm_allowed()
    for key, val in dotenv_values(str(env_path)).items():
        if val is None:
            continue
        # Cost-guard: do NOT inject provider secret keys on the default path.
        if not allow_real_llm and _is_provider_secret(key):
            continue
        # Only set if not already in environment (don't override explicit env).
        if key not in os.environ:
            os.environ[key] = val
