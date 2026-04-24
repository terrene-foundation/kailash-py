# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for CodeQL py/clear-text-logging-sensitive-data (issue #613).

Each test reads the fixed source file and asserts the structural defense
is in place: the logger calls at the previously-flagged lines MUST NOT
reference URL-derived fields (host, port, database, db_name,
connection_string) OR secret-named attributes (secret_env). These are
Tier-1 structural invariant tests — if a future refactor re-introduces
the leak, the grep fails loudly.

Scope — the 6 HIGH findings closed by the fix:
  1. postgresql.py:98-100 (3 findings) — host/port/database in logger.info
  2. factory.py:146                    — connection_string in logger.info
  3. mongodb.py:78                     — sanitized connection_string in f-string
  4. mongodb.py:158                    — db_name in logger.info extra
  5. webhooks.py:539                   — webhook_config.secret_env in logger.error
"""

from __future__ import annotations

from pathlib import Path

# Repo root resolved from the test file path (packages/kailash-dataflow/tests/regression)
_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[4]


def _read(rel_path: str) -> str:
    return (_REPO_ROOT / rel_path).read_text()


class TestPostgresqlAdapterLogHygiene:
    PATH = "packages/kailash-dataflow/src/dataflow/adapters/postgresql.py"

    def test_connection_pool_created_log_does_not_echo_url_fields(self) -> None:
        src = _read(self.PATH)
        # The log line MUST NOT include host/port/database derived fields.
        assert "safe_log_value(self.host)" not in src
        assert "safe_log_value(self.port)" not in src
        assert "safe_log_value(self.database)" not in src
        # And MUST NOT inline them either.
        assert 'host=%s port=%s database=%s"' not in src
        # The canonical event name survives for operator triage.
        assert '"postgresql.connection_pool.created"' in src


class TestFactoryAdapterLogHygiene:
    PATH = "packages/kailash-dataflow/src/dataflow/adapters/factory.py"

    def test_created_adapter_log_does_not_echo_connection_string(self) -> None:
        src = _read(self.PATH)
        # The factory MUST NOT include the masked connection_string in the
        # log extra (CodeQL traces taint through the mask helper).
        assert '"connection_string": mask_url(connection_string)' not in src
        # Canonical event name survives.
        assert '"factory.created_adapter"' in src


class TestMongoDBAdapterLogHygiene:
    PATH = "packages/kailash-dataflow/src/dataflow/adapters/mongodb.py"

    def test_initialize_log_does_not_echo_connection_string(self) -> None:
        src = _read(self.PATH)
        # The init INFO must NOT contain the sanitized connection string.
        assert (
            "MongoDBAdapter initialized with connection string" not in src
        ), "initialize log regressed: do not echo connection_string even after masking"
        assert '"mongodb.adapter_initialized"' in src

    def test_connect_log_does_not_echo_db_name(self) -> None:
        src = _read(self.PATH)
        # db_name is derived from urlparse(connection_string).path and
        # inherits the URL's CodeQL taint.
        assert 'extra={"db_name": db_name}' not in src


class TestWebhooksLogHygiene:
    PATH = "packages/kailash-dataflow/src/dataflow/fabric/webhooks.py"

    def test_secret_missing_error_does_not_echo_secret_env(self) -> None:
        src = _read(self.PATH)
        # The ERROR log MUST NOT emit webhook_config.secret_env (CodeQL
        # matches the "secret" substring on attribute names even when the
        # value is an env var NAME, not a secret VALUE).
        assert "webhook_config.secret_env,\n" not in src
        # The source_name remains in the log — it is not URL-derived and
        # is the action signal operators need.
        assert "source '%s'" in src
