"""
api_gateway_starter integration-test conftest.

The api_gateway_starter template's config module reads ``SAAS_STARTER_JWT_SECRET``
from the environment at import time and raises ``RuntimeError`` if unset
(see ``packages/kailash-dataflow/templates/api_gateway_starter/example_app/config.py``).
The Tier-2 test suite for api_gateway_starter imports that module via
``from templates.api_gateway_starter.example_app.main import create_app`` and
also exchanges tokens with saas_starter, so a 32+ byte test secret MUST be
present BEFORE any test imports.

This conftest uses ``os.environ.setdefault`` so:
- Production deployments (which set ``SAAS_STARTER_JWT_SECRET`` to a real
  value before pytest) are not overridden.
- Local / CI runs without the variable get a 52-byte synthetic test secret.

The test secret meets the >=32 byte floor mandated by RFC 7518 §3.2 and
``rules/testing.md`` § "JWT Test Secrets >= 32 Bytes". Matches the value
used by the sibling saas_starter conftest so cross-template token exchange
(api_gateway verifies tokens signed by saas_starter) works without test
infrastructure drift.

Cross-reference: ``rules/security.md`` § "No Hardcoded Secrets" +
``rules/env-models.md``.
"""

import os

os.environ.setdefault(
    "SAAS_STARTER_JWT_SECRET",
    "test-secret-saas-starter-tier2-32bytes-minimum-floor",
)
