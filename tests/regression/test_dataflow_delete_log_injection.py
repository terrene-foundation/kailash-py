"""DELETE debug log at ``dataflow/core/nodes.py`` must not be forgeable.

The generated ``<Model>DeleteNode`` logs its resolved statement at DEBUG::

    logger.debug(f"DELETE: table={table_name}, id={record_id}, query={query}")

``record_id`` is caller-controlled. Interpolated raw, a value carrying ``\\r``
or ``\\n`` ends the record mid-line and everything after the break is read by
any log consumer as a SEPARATE, fully-attacker-authored record -- classic log
injection (the ``sanitize_log_value`` barrier in
``kailash/utils/secure_logging.py``, issues #2040 / #2088).

Why this site was missed for so long: ``black`` wraps ``logger.debug(`` and the
f-string onto DIFFERENT lines, so the single-line grep patterns that audit
f-strings-inside-logger-calls never matched it. It was found by a corpus-wide
sweep instead.

DISCRIMINATION (this test is not vacuous -- measured, not asserted):
with the raw f-string restored, ``test_delete_log_cannot_forge_a_second_record``
fails on the ``rendered == 1 line`` assertion, reporting 2 rendered lines whose
second is ``FORGED[CRITICAL] ...``. A length bound alone does NOT clear it --
only the ``\\r``/``\\n`` FLATTEN does, which is why the assertions below test
line COUNT rather than message length.
"""

from __future__ import annotations

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
from kailash.nodes.base import NodeRegistry  # noqa: E402

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


async def _capture_delete_log(caplog, record_id):
    """Drive the REAL generated DeleteNode and return its 'DELETE: ...' records.

    The debug line is emitted BEFORE the statement reaches the database, so the
    node's downstream failure (no such table) is irrelevant to what is captured
    and is deliberately swallowed.
    """
    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    try:

        @db.model
        class LogInjectionWidget:
            name: str

        node = NodeRegistry.get("LogInjectionWidgetDeleteNode")(
            name="delete_under_test", dataflow_instance=db
        )
        with caplog.at_level(logging.DEBUG, logger=NODES_LOGGER):
            try:
                await node.async_run(id=record_id)
            except Exception:
                # The table does not exist; the log under test already fired.
                pass
        return [
            r for r in caplog.records if r.getMessage().startswith("DELETE: table=")
        ]
    finally:
        await db.close_async()


@pytest.mark.parametrize(
    "break_seq, name", [("\n", "LF"), ("\r", "CR"), ("\r\n", "CRLF")]
)
async def test_delete_log_cannot_forge_a_second_record(caplog, break_seq, name):
    """A line-break-bearing id must render as ONE line, not two."""
    records = await _capture_delete_log(caplog, f"widget-1{break_seq}{FORGERY}")

    assert len(records) == 1, (
        f"expected exactly one 'DELETE:' record, got {len(records)}; "
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


async def test_the_payload_survives_on_the_single_line(caplog):
    """Sanitizing is NOT redaction: the attacker-chosen text is usually the
    only diagnostic there is, so it must still be present -- just inert."""
    records = await _capture_delete_log(caplog, f"widget-1\n{FORGERY}")

    assert len(records) == 1
    message = records[0].getMessage()
    assert "widget-1" in message
    assert "FORGED[CRITICAL]" in message, (
        "the value was dropped rather than flattened; a sanitizer that deletes "
        "the diagnostic is not the fix"
    )


async def test_the_query_value_is_still_rendered_after_sanitizing(caplog):
    """The site interpolates TWO values and BOTH now route through the barrier.

    This one does not discriminate the injection (a plain id is single-line
    either way) -- it pins the OTHER direction: that sanitizing `query` did not
    truncate or drop the statement, which a too-small bound would.
    """
    records = await _capture_delete_log(caplog, "plain-id")

    assert len(records) == 1
    message = records[0].getMessage()
    assert "DELETE FROM" in message, f"query not rendered at all: {message!r}"
    assert len(message.splitlines()) == 1
