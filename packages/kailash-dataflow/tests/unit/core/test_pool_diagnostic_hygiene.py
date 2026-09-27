"""Pool diagnostics preserve probe behavior without retaining credential values."""

import logging

import pytest

from dataflow.core import pool_utils

SECRET = "pool-diagnostic-canary-846291"
LOGGER = "dataflow.core.pool_utils"


def _records(caplog):
    records = [r for r in caplog.records if r.name == LOGGER]
    assert records
    for record in records:
        assert record.exc_info is None
        assert record.exc_text is None
        assert SECRET not in logging.Formatter().format(record)
        assert record.getMessage().isprintable()
    return records


@pytest.mark.parametrize(
    "value",
    [
        '{\n"password":"' + SECRET + '"\n}',
        "?token=" + SECRET + "\u2028FORGED",
    ],
)
def test_unknown_scheme_redacts_metadata_at_debug(caplog, value):
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        assert pool_utils.probe_max_connections(value + "://host/db") is None
    records = _records(caplog)
    assert [r.levelno for r in records] == [logging.DEBUG]
    assert "unrecognized database URL scheme" in records[0].getMessage()


@pytest.mark.parametrize("variable", pool_utils._WORKER_ENV_VARS)
def test_worker_warning_redacts_raw_environment_and_keeps_priority(
    caplog, monkeypatch, variable
):
    for name in pool_utils._WORKER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(variable, '{\n"password":"' + SECRET + '"\n}')
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        assert pool_utils.detect_worker_count() == 1
    records = _records(caplog)
    assert [r.levelno for r in records] == [logging.WARNING]
    assert variable in records[0].getMessage()
    monkeypatch.setenv(variable, "7")
    assert pool_utils.detect_worker_count() == 7


@pytest.mark.parametrize(
    "url,error_type,detail",
    [
        (
            "postgresql://user:password@localhost:" + SECRET + "/db",
            "OperationalError",
            "PostgreSQL probe error details",
        ),
        (
            "mysql://user:password@localhost:" + SECRET + "/db",
            "ValueError",
            "MySQL URL parse error details",
        ),
        (
            "mysql://user:%C4%80@localhost:3306/db",
            "UnicodeEncodeError",
            "MySQL probe error details",
        ),
    ],
)
def test_real_driver_and_parser_failures_do_not_attach_raw_tracebacks(
    caplog, url, error_type, detail
):
    # Real psycopg2/libpq port validation, urllib port validation and PyMySQL
    # password encoding all fail before socket connection; no database mocks.
    import psycopg2  # noqa: F401
    import pymysql  # noqa: F401

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        assert pool_utils.probe_max_connections(url) is None
    records = _records(caplog)
    assert [r.levelno for r in records] == [logging.WARNING, logging.DEBUG]
    assert error_type in records[0].getMessage()
    assert detail in records[1].getMessage()
    assert error_type + "@" in records[1].getMessage()


@pytest.mark.parametrize(
    "driver,scheme", [("psycopg2", "postgresql"), ("pymysql", "mysql")]
)
def test_driver_boundary_exception_messages_and_causes_stay_out_of_logs(
    caplog, monkeypatch, driver, scheme
):
    import importlib

    module = importlib.import_module(driver)

    def fail(*args, **kwargs):
        try:
            raise ValueError(SECRET + " private cause")
        except ValueError as cause:
            raise RuntimeError(SECRET + " opaque driver detail") from cause

    monkeypatch.setattr(module, "connect", fail)
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        assert (
            pool_utils.probe_max_connections(scheme + "://user:password@localhost/db")
            is None
        )
    records = _records(caplog)
    assert [r.levelno for r in records] == [logging.WARNING, logging.DEBUG]
    assert "RuntimeError" in records[0].getMessage()
    assert "RuntimeError@" in records[1].getMessage()


def test_shared_decode_still_rejects_encoded_nul_without_driver_call(caplog):
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        assert (
            pool_utils.probe_max_connections(
                "mysql://user:%00" + SECRET + "@localhost/db"
            )
            is None
        )
    records = _records(caplog)
    assert [r.levelno for r in records] == [logging.WARNING, logging.DEBUG]
    assert "Failed to parse MySQL URL" in records[0].getMessage()
    assert "decode_userinfo_or_raise" in records[1].getMessage()


def test_pool_config_environment_warning_masks_before_formatting(caplog, monkeypatch):
    from dataflow.core.config import DatabaseConfig

    monkeypatch.setenv("DATAFLOW_POOL_SIZE", '{"password":"' + SECRET + '"}')
    with caplog.at_level(logging.WARNING, logger="dataflow.core.config"):
        result = DatabaseConfig(url="sqlite:///:memory:").get_pool_size()
    assert isinstance(result, int) and result >= 1
    records = [r for r in caplog.records if r.name == "dataflow.core.config"]
    assert len(records) == 1 and records[0].levelno == logging.WARNING
    assert SECRET not in records[0].getMessage()
    assert "DATAFLOW_POOL_SIZE" in records[0].getMessage()
    monkeypatch.setenv("DATAFLOW_POOL_SIZE", "9")
    assert DatabaseConfig(url="sqlite:///:memory:").get_pool_size() == 9
    assert DatabaseConfig(url="sqlite:///:memory:", pool_size=4).get_pool_size() == 4
