"""Shared fixtures for saas_starter Tier-2 integration tests.

The three saas_starter modules that handle JWT signing
(``auth.jwt_auth``, ``workflows.auth``, ``middleware.tenant``) read
``SAAS_STARTER_JWT_SECRET`` at import time and fail loudly if it's unset
(see security.md § No Hardcoded Secrets + env-models.md). The autouse
fixture below installs a >=32-byte test secret BEFORE the conftest's own
imports / pytest's collection so the integration tests can import the
saas_starter modules without tripping the import-time RuntimeError.

Tests that need a specific JWT secret (e.g. to sign a token in one
process and verify it in another) can override per-test by setting the
env var before importing the module.
"""

import os

# Set BEFORE any saas_starter import. conftest.py runs at collection time,
# strictly before the test modules' top-level imports. >=32 bytes per
# rules/testing.md § JWT Test Secrets >= 32 Bytes (RFC 7518 §3.2).
os.environ.setdefault(
    "SAAS_STARTER_JWT_SECRET",
    "test-secret-saas-starter-tier2-32bytes-minimum-floor",
)
