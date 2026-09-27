"""The bulk BOUND-PARAMETER debug logs must not dump caller data unbounded.

``BulkOperations.bulk_update`` / ``bulk_delete`` logged their resolved statement
together with the BOUND PARAMETER LIST at DEBUG::

    logger.debug(f"BULK_UPDATE: Executing query='{query}' with params={params}")

``params`` are caller row VALUES at bulk scale. Two distinct hazards live here,
and re-derivation showed they are NOT equally reachable -- recording both so a
later reader does not re-assert the stronger claim:

* **Volume / PII (REACHABLE, and what these tests pin).** ``params`` is a
  ``list``, so the f-string renders it in full: an entire batch of caller row
  values lands in one log record. Log aggregators have broader access than the
  database, so this is bulk PII disclosure by way of a debug line.
* **Log forgery (NOT reachable through ``params``).** A ``list`` renders via
  ``repr``, which ESCAPES control characters -- a value containing a real
  newline is rendered as the two characters ``\\`` ``n`` and cannot end the
  record. Measured directly against the unpatched code: the emitted record was
  ONE line. The ``query`` operand IS ``str``-interpolated and so would forge if
  a newline ever reached it, but the statement is built from
  identifier-validated schema names. Routing ``query`` through the barrier is
  therefore DEFENSE IN DEPTH, not a demonstrated hole, and is deliberately not
  claimed as this file's discriminating property.

The barrier is ``sanitize_log_value`` (``kailash/utils/secure_logging.py``,
issues #2040 / #2088), which bounds length AND flattens non-printables. Sibling
of ``test_dataflow_delete_log_injection.py`` (commit 16e616fb), where the value
WAS ``str``-interpolated and the forgery half was live.

DISCRIMINATION (measured, not asserted): with the raw f-strings restored,
``test_bulk_update_params_log_is_bounded`` and its DELETE sibling fail on the
length assertion, reporting a record tens of thousands of characters long.
"""

from __future__ import annotations

import logging
import pathlib
import sys
import uuid

import pytest

# Pin BOTH packages to THIS checkout, relative to this file -- never to an
# absolute path. Unpinned, ``import dataflow`` resolves to whichever copy is
# installed in site-packages, so a worktree running this test would silently
# verify a DIFFERENT tree's source and report a false GREEN.
# packages/kailash-dataflow/tests/regression/<file> -> up 4 -> checkout root.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
for _path in (REPO_ROOT / "packages" / "kailash-dataflow" / "src", REPO_ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import dataflow  # noqa: E402
import kailash  # noqa: E402
from dataflow import DataFlow  # noqa: E402

# The module logger the bulk sites use (``logging.getLogger(__name__)``).
BULK_LOGGER = "dataflow.features.bulk"

# Large enough that an unbounded render is unmistakable, and far above
# sanitize_log_value's 256-character bound.
BULK_VALUE = "P" * 40_000

# The ceiling one sanitized value may contribute, plus room for the statement
# text and the line's fixed prose. Well under an unbounded render.
MAX_REASONABLE_LINE = 2_000


def test_both_packages_resolve_to_this_checkout():
    """Guards every other assertion here against the site-packages false green.

    If ``dataflow`` came from an installed copy, a GREEN below would describe
    source this checkout does not contain.
    """
    for module in (dataflow, kailash):
        assert pathlib.Path(module.__file__).resolve().is_relative_to(REPO_ROOT), (
            f"{module.__name__} resolved to {module.__file__}, outside {REPO_ROOT}; "
            "the test would verify a different tree"
        )


def _fresh_db(tmp_path) -> DataFlow:
    return DataFlow(f"sqlite:///{tmp_path}/inj_{uuid.uuid4().hex}.db")


def _records(caplog, prefix: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith(prefix)]


@pytest.mark.regression
@pytest.mark.asyncio
async def test_bulk_update_params_log_is_bounded(tmp_path, caplog):
    """A 40k-character row value must not land in the log in full."""
    db = _fresh_db(tmp_path)

    @db.model
    class Widget:
        id: str
        name: str

    await db.express.bulk_create("Widget", [{"id": "w1", "name": "before"}])

    with caplog.at_level(logging.DEBUG, logger=BULK_LOGGER):
        await db.bulk.bulk_update(
            model_name="Widget",
            filter_criteria={"id": "w1"},
            update_values={"name": BULK_VALUE},
        )

    messages = _records(caplog, "BULK_UPDATE: Executing")
    assert messages, "the BULK_UPDATE debug line was not emitted; test proves nothing"
    longest = max(len(m) for m in messages)
    assert longest <= MAX_REASONABLE_LINE, (
        f"the bound-parameter log rendered {longest} characters of caller row "
        f"data in one record; log aggregators have broader access than the DB"
    )
    # The value is bounded, not redacted: a short prefix survives on purpose, so
    # the line keeps its diagnostic worth.
    assert any("P" in m for m in messages), (
        "the parameter rendering lost the value entirely; the barrier bounds, "
        "it does not redact"
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_bulk_delete_params_log_is_bounded(tmp_path, caplog):
    """Same barrier on the DELETE path's bound parameters."""
    db = _fresh_db(tmp_path)

    @db.model
    class Widget:
        id: str
        name: str

    await db.express.bulk_create("Widget", [{"id": BULK_VALUE, "name": "x"}])

    with caplog.at_level(logging.DEBUG, logger=BULK_LOGGER):
        await db.bulk.bulk_delete(
            model_name="Widget",
            filter_criteria={"id": BULK_VALUE},
        )

    messages = _records(caplog, "BULK_DELETE: Executing")
    assert messages, "the BULK_DELETE debug line was not emitted; test proves nothing"
    longest = max(len(m) for m in messages)
    assert longest <= MAX_REASONABLE_LINE, (
        f"the bound-parameter log rendered {longest} characters of caller row "
        f"data in one record"
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_every_bulk_statement_log_stays_on_one_line(tmp_path, caplog):
    """No bulk statement log may render as more than one line.

    Holds today through ``repr`` escaping on the params operand (see the module
    docstring); this pins it against a future edit that interpolates a value
    with ``str`` instead, which is exactly how the sibling DELETE-node site
    became forgeable.
    """
    db = _fresh_db(tmp_path)

    @db.model
    class Widget:
        id: str
        name: str

    forgery = "\nFORGED[CRITICAL] dataflow: all rows deleted by root (id=*)"
    with caplog.at_level(logging.DEBUG, logger=BULK_LOGGER):
        await db.bulk.bulk_create(
            model_name="Widget", data=[{"id": "w1", "name": forgery}]
        )
        await db.bulk.bulk_update(
            model_name="Widget",
            filter_criteria={"id": "w1"},
            update_values={"name": forgery},
        )

    messages = _records(caplog, "BULK_")
    assert messages, "no bulk debug lines captured; test proves nothing"
    multiline = [m for m in messages if len(m.splitlines()) > 1]
    assert not multiline, (
        f"{len(multiline)} bulk log record(s) rendered as several lines; "
        f"everything after the first break is attacker-authored: {multiline!r}"
    )


def test_sanitizer_is_the_barrier_these_tests_depend_on():
    """Pins the two properties the tests above rely on.

    If ``sanitize_log_value`` stopped bounding or stopped flattening, the tests
    above could still pass on inputs that happen to be short or newline-free --
    this one fails directly and names the reason.
    """
    from kailash.utils.secure_logging import sanitize_log_value

    flattened = sanitize_log_value("a\nFORGED[CRITICAL] b")
    assert "\n" not in flattened and "\r" not in flattened, (
        f"sanitize_log_value left a line break in {flattened!r}; every log site "
        "routed through it is forgeable again"
    )
    assert len(sanitize_log_value(BULK_VALUE)) < len(BULK_VALUE), (
        "sanitize_log_value stopped bounding length; the bulk parameter logs "
        "would dump caller row data in full again"
    )
