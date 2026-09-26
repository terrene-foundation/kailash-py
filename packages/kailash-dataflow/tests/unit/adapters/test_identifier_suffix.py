"""All DataFlow dialects reject invalid suffixes across the entire identifier."""

import pytest

from dataflow.adapters.dialect import MySQLDialect, PostgreSQLDialect, SQLiteDialect
from dataflow.adapters.exceptions import InvalidIdentifierError


@pytest.mark.parametrize(
    "dialect_type", [PostgreSQLDialect, MySQLDialect, SQLiteDialect]
)
@pytest.mark.parametrize("name", ["table\n", "table\r\n", "table\x00"])
def test_identifier_suffix_rejected(dialect_type, name):
    dialect = dialect_type()
    assert "table_1" in dialect.quote_identifier("table_1")
    with pytest.raises(InvalidIdentifierError):
        dialect.quote_identifier(name)
