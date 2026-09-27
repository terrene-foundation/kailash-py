"""Generated DELETE diagnostics retain categories without private row values.

Real SQLite operations prove that private identifiers still reach CRUD while
raw records and formatted output cannot expose them or forge another line.
"""

from __future__ import annotations

import json
import logging
import pathlib
import sys

import pytest

# Pin BOTH packages to THIS checkout, relative to this file -- never to an
# absolute path. Unpinned, `import dataflow` resolves to whichever copy is
# installed in site-packages, so a worktree running this test would silently
# verify a DIFFERENT tree's source and report a false GREEN.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
for _path in (REPO_ROOT / "packages" / "kailash-dataflow" / "src", REPO_ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import dataflow  # noqa: E402
import kailash  # noqa: E402
from dataflow import DataFlow  # noqa: E402

# The module logger the DELETE site uses (`logging.getLogger(__name__)`).
NODES_LOGGER = "dataflow.core.nodes"

# A record_id that forges a whole extra record if interpolated raw.
FORGERY = "FORGED[CRITICAL] dataflow: all rows deleted by root (id=*)"


def test_both_packages_resolve_to_this_checkout():
    """Guards every other assertion in this file against the site-packages
    false-green: if `dataflow` came from an installed copy, a GREEN below
    would describe source this checkout does not contain."""
    for module in (dataflow, kailash):
        assert pathlib.Path(module.__file__).resolve().is_relative_to(REPO_ROOT), (
            f"{module.__name__} resolved to {module.__file__}, outside {REPO_ROOT}; "
            "the test would verify a different tree"
        )


async def _capture_delete_log(caplog, tmp_path, record_id):
    """Delete an existing real row and capture the reached diagnostic."""
    db = DataFlow(f"sqlite:///{tmp_path / 'delete.db'}", test_mode=False)
    try:

        @db.model
        class LogInjectionWidget:
            id: str
            name: str

        await db.initialize()
        create = db._nodes["LogInjectionWidgetCreateNode"]()
        delete = db._nodes["LogInjectionWidgetDeleteNode"]()
        listing = db._nodes["LogInjectionWidgetListNode"]()
        created = await create.execute_async(
            id=record_id, name="private.person@example.invalid"
        )
        assert created["id"] == record_id
        before = await listing.execute_async()
        assert [row["id"] for row in before["records"]] == [record_id]
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger=NODES_LOGGER):
            result = await delete.execute_async(id=record_id)
        assert result == {"id": record_id, "deleted": True}
        after = await listing.execute_async()
        assert after["records"] == []
        records = [r for r in caplog.records if r.name == NODES_LOGGER]
        assert record_id not in json.dumps([r.__dict__ for r in records], default=str)
        assert record_id.splitlines()[0] not in repr([r.__dict__ for r in records])
        assert "private.person@example.invalid" not in repr(
            [r.__dict__ for r in records]
        )
        return [r for r in records if r.getMessage() == "nodes.delete.execute"]
    finally:
        await db.close_async()


@pytest.mark.parametrize(
    "break_seq, name", [("\n", "LF"), ("\r", "CR"), ("\r\n", "CRLF")]
)
async def test_delete_log_cannot_forge_a_second_record(
    caplog, tmp_path, break_seq, name
):
    """A line-break-bearing id must render as ONE line, not two."""
    records = await _capture_delete_log(
        caplog, tmp_path, f"widget-1{break_seq}{FORGERY}"
    )

    assert len(records) == 1, (
        f"expected exactly one 'nodes.delete.execute' record, got {len(records)}; "
        "the site did not log -- this test would prove nothing"
    )
    message = records[0].getMessage()

    # The load-bearing assertion: what a consumer actually reads off the wire.
    rendered = logging.Formatter("%(message)s").format(records[0])
    assert len(rendered.splitlines()) == 1, (
        f"{name} in record_id forged {len(rendered.splitlines())} log lines; "
        f"line 2 would read: {rendered.splitlines()[1]!r}"
    )
    assert "\n" not in message and "\r" not in message, repr(message)


async def test_private_id_reaches_delete_without_entering_diagnostics(caplog, tmp_path):
    records = await _capture_delete_log(caplog, tmp_path, f"widget-1\n{FORGERY}")
    assert len(records) == 1
    rendered = logging.Formatter("%(message)s").format(records[0])
    assert rendered == "nodes.delete.execute"
    assert len(rendered.splitlines()) == 1
    assert "widget-1" not in repr(records[0].__dict__)
    assert FORGERY not in repr(records[0].__dict__)


async def test_delete_keeps_table_metadata_without_query_or_row_values(
    caplog, tmp_path
):
    records = await _capture_delete_log(caplog, tmp_path, "plain-private-id")
    assert len(records) == 1
    record = records[0]
    assert record.getMessage() == "nodes.delete.execute"
    assert record.table == "log_injection_widgets"
    assert "DELETE FROM" not in repr(record.__dict__)
    assert "plain-private-id" not in repr(record.__dict__)
    assert len(logging.Formatter().format(record).splitlines()) == 1
