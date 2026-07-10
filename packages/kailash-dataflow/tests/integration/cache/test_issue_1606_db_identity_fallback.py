"""#1606 DB-identity engine wiring — Tier 2 (real DataFlow engine, no mocking).

Exercises the exact ``DataFlow._initialize_cache_integration`` path (redteam
FINDING 1): a falsy/absent URL or a non-URL DSN MUST emit a loud operator
warning that cross-DB cache isolation is INACTIVE, and MUST fall back to the
credential-free component config (host/port/dbname) when available so
isolation still holds for URL-less instances.

These construct a real DataFlow engine and drive the real cache-integration
setup; no mocks. Redis may or may not be present — irrelevant here, the
assertions are on the key generator's db_identity + the emitted warnings.

Tier: 2 (real engine wiring).
"""

import logging

import pytest

from dataflow import DataFlow

_ENGINE_LOGGER = "dataflow.core.engine"
_QUERY_SQL = "SELECT * FROM users WHERE active = $1"
_QUERY_PARAMS = [True]


def _reinit_cache(db) -> None:
    """Re-run the cache-integration setup after mutating config.database."""
    db._cache_integration = None
    db._initialize_cache_integration()


def test_falsy_db_url_warns_isolation_inactive():
    """FINDING 1(b): absent URL + no components -> loud WARN, identity None."""
    db = DataFlow("sqlite:///:memory:", cache_enabled=True)
    # Simulate a config with no usable database identity at all.
    db.config.database.url = None
    db.config.database.database_url = None
    db.config.database.host = None
    db.config.database.port = None
    db.config.database.database = None

    with caplog_at_warning() as caplog:
        _reinit_cache(db)

    assert db._cache_integration is not None
    assert db._cache_integration.key_generator.db_identity is None
    assert "db_identity_disabled" in caplog.text
    assert "INACTIVE" in caplog.text


def test_falsy_db_url_with_components_uses_component_identity_no_disabled_warn():
    """FINDING 1(a): URL-less config derives identity from host/port/dbname."""
    db = DataFlow("sqlite:///:memory:", cache_enabled=True)
    db.config.database.url = None
    db.config.database.database_url = None
    db.config.database.host = "h1"
    db.config.database.port = 5432
    db.config.database.database = "app_db"

    with caplog_at_warning() as caplog:
        _reinit_cache(db)

    identity = db._cache_integration.key_generator.db_identity
    assert identity is not None, "component config must yield an identity"
    # No "disabled" warning — isolation is active via component config.
    assert "db_identity_disabled" not in caplog.text


def test_unparseable_dsn_warns():
    """FINDING 1(b): a non-URL keyword/value DSN -> WARN (not a silent constant)."""
    db = DataFlow("sqlite:///:memory:", cache_enabled=True)
    db.config.database.url = "host=a dbname=x"  # libpq keyword DSN, no ://
    db.config.database.database_url = "host=a dbname=x"
    db.config.database.host = None
    db.config.database.port = None
    db.config.database.database = None

    with caplog_at_warning() as caplog:
        _reinit_cache(db)

    # url_unparseable warning fires; with no components, identity stays None.
    assert "db_identity_url_unparseable" in caplog.text
    assert db._cache_integration.key_generator.db_identity is None


def test_component_config_identity_isolates_two_urlless_instances():
    """FINDING 1(a): two URL-less engines at different DBs -> different query keys."""
    db_a = DataFlow("sqlite:///:memory:", cache_enabled=True)
    db_a.config.database.url = None
    db_a.config.database.database_url = None
    db_a.config.database.host = "host-a"
    db_a.config.database.port = 5432
    db_a.config.database.database = "db_a"
    _reinit_cache(db_a)

    db_b = DataFlow("sqlite:///:memory:", cache_enabled=True)
    db_b.config.database.url = None
    db_b.config.database.database_url = None
    db_b.config.database.host = "host-b"
    db_b.config.database.port = 5432
    db_b.config.database.database = "db_b"
    _reinit_cache(db_b)

    key_a = db_a._cache_integration.key_generator.generate_key(
        "User", _QUERY_SQL, _QUERY_PARAMS
    )
    key_b = db_b._cache_integration.key_generator.generate_key(
        "User", _QUERY_SQL, _QUERY_PARAMS
    )
    assert key_a != key_b, (
        "two URL-less DataFlow instances at different databases must NOT "
        f"collide on the same query cache key (a={key_a!r} b={key_b!r})"
    )


# --- caplog helper -------------------------------------------------------

class _CapLog:
    def __init__(self):
        self.records = []

    @property
    def text(self):
        return "\n".join(r.getMessage() for r in self.records)


class _ListHandler(logging.Handler):
    def __init__(self, sink):
        super().__init__(level=logging.WARNING)
        self._sink = sink

    def emit(self, record):
        self._sink.records.append(record)


class caplog_at_warning:
    """Minimal caplog: capture WARNING+ from the engine logger during the block.

    Self-contained (no pytest caplog fixture dependency) so the assertions are
    robust to the engine's own logging configuration.
    """

    def __enter__(self):
        self._sink = _CapLog()
        self._handler = _ListHandler(self._sink)
        self._logger = logging.getLogger(_ENGINE_LOGGER)
        self._prev_level = self._logger.level
        self._prev_propagate = self._logger.propagate
        self._logger.addHandler(self._handler)
        self._logger.setLevel(logging.WARNING)
        return self._sink

    def __exit__(self, *exc):
        self._logger.removeHandler(self._handler)
        self._logger.setLevel(self._prev_level)
        self._logger.propagate = self._prev_propagate
        return False
