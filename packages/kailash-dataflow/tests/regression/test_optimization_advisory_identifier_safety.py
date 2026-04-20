"""Regression tests for dialect-safety on DataFlow optimization advisory DDL.

Per rules/dataflow-identifier-safety.md MUST Rules 1 + 5:
advisory CREATE INDEX strings returned by the optimization layer are still
DDL and MUST route every dynamic identifier through quote_identifier /
_validate_identifier before interpolation. Without this, a table name
like `users"; DROP TABLE customers; --` ends up in an advisory string
that looks executable and may be copy-pasted directly into a shell.

Origin: /redteam 2026-04-20 dialect-safety sweep (kailash 2.8.11).
"""

from __future__ import annotations

import pytest


@pytest.mark.regression
def test_quote_for_rejects_injection_postgres() -> None:
    """sql_query_optimizer._quote_for rejects injection payloads on PostgreSQL."""
    from dataflow.optimization.sql_query_optimizer import SQLDialect, _quote_for

    with pytest.raises(Exception):
        _quote_for(SQLDialect.POSTGRESQL, 'users"; DROP TABLE customers; --')
    with pytest.raises(Exception):
        _quote_for(SQLDialect.POSTGRESQL, "name WITH DATA")
    with pytest.raises(Exception):
        _quote_for(SQLDialect.POSTGRESQL, "123_starts_with_digit")


@pytest.mark.regression
def test_quote_for_rejects_injection_mysql() -> None:
    """sql_query_optimizer._quote_for rejects injection payloads on MySQL."""
    from dataflow.optimization.sql_query_optimizer import SQLDialect, _quote_for

    with pytest.raises(Exception):
        _quote_for(SQLDialect.MYSQL, "users`; DROP TABLE customers; --")


@pytest.mark.regression
def test_quote_for_rejects_injection_sqlite() -> None:
    """sql_query_optimizer._quote_for rejects injection payloads on SQLite."""
    from dataflow.optimization.sql_query_optimizer import SQLDialect, _quote_for

    with pytest.raises(Exception):
        _quote_for(SQLDialect.SQLITE, 'users"; DROP TABLE customers; --')


@pytest.mark.regression
def test_quote_for_happy_path_quotes_valid_identifiers() -> None:
    """Happy path — valid identifiers produce quoted output per dialect."""
    from dataflow.optimization.sql_query_optimizer import SQLDialect, _quote_for

    assert _quote_for(SQLDialect.POSTGRESQL, "users") == '"users"'
    assert _quote_for(SQLDialect.SQLITE, "users") == '"users"'
    assert _quote_for(SQLDialect.MYSQL, "users") == "`users`"


@pytest.mark.regression
def test_sql_query_optimizer_suggest_indexes_rejects_injection() -> None:
    """_suggest_indexes integration path rejects malicious table names."""
    from dataflow.optimization.sql_query_optimizer import (
        SQLDialect,
        SQLQueryOptimizer,
    )

    opt = SQLQueryOptimizer(dialect=SQLDialect.POSTGRESQL)
    with pytest.raises(Exception):
        opt._suggest_indexes(
            tables=['users"; DROP TABLE customers; --', "orders"],
            join_conditions={"left_key": "id", "right_key": "user_id"},
            aggregate_info={},
        )


@pytest.mark.regression
def test_sql_query_optimizer_suggest_indexes_emits_quoted() -> None:
    """Happy path — valid identifiers produce double-quoted output."""
    from dataflow.optimization.sql_query_optimizer import (
        SQLDialect,
        SQLQueryOptimizer,
    )

    opt = SQLQueryOptimizer(dialect=SQLDialect.POSTGRESQL)
    advisories = opt._suggest_indexes(
        tables=["users", "orders"],
        join_conditions={"left_key": "id", "right_key": "user_id"},
        aggregate_info={"group_by": ["status"]},
    )
    assert advisories
    assert all('"' in s for s in advisories), advisories
