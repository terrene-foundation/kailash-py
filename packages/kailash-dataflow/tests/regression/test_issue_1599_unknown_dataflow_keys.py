"""Regression tests for issue #1599 — warn on unknown ``__dataflow__`` keys.

Disposition for #1599 was KEEP-REMOVED for the ``versioned`` flag / optimistic
locking (0% implemented, no speculative build). The hardening half: an
unrecognized ``__dataflow__`` model-config key MUST surface a loud, NON-breaking
``UserWarning`` at model registration so a future ``versioned: True`` (or any
typo'd / fictional key) is visible instead of a silent no-op.

Contract asserted here (Tier-1, registration-time — no DB I/O needed because the
warning fires synchronously at ``@db.model`` decoration):
  * an unknown key (``versioned``, ``bogus_key``) emits ``UserWarning`` naming it
  * a model using ONLY recognized keys emits NO such warning
  * an empty ``__dataflow__`` emits NO warning
  * the guard is a warning, never a raise (registration still succeeds)
"""

import warnings

import pytest

from dataflow import DataFlow

_UNKNOWN_KEY_FRAGMENT = "unknown __dataflow__ key"


def _unknown_key_warnings(records):
    """Filter recorded warnings down to the #1599 unknown-key warning."""
    return [
        w
        for w in records
        if issubclass(w.category, UserWarning)
        and _UNKNOWN_KEY_FRAGMENT in str(w.message)
    ]


@pytest.mark.regression
def test_versioned_flag_emits_unknown_key_warning():
    """The removed ``versioned`` flag must warn — it has zero backing code."""
    with DataFlow(":memory:", migration_enabled=False) as db:
        with pytest.warns(UserWarning, match=r"unknown __dataflow__ key"):

            @db.model
            class VersionedThing:
                id: int
                name: str

                __dataflow__ = {"versioned": True}

        # Registration still succeeded (warning, never raise).
        assert "VersionedThing" in db._models


@pytest.mark.regression
def test_bogus_key_emits_unknown_key_warning_naming_the_key():
    """An arbitrary typo'd key must warn AND name the offending key."""
    with DataFlow(":memory:", migration_enabled=False) as db:
        with pytest.warns(UserWarning, match=r"bogus_key"):

            @db.model
            class BogusThing:
                id: int
                value: int

                __dataflow__ = {"bogus_key": 1}

        assert "BogusThing" in db._models


@pytest.mark.regression
def test_multiple_unknown_keys_all_named():
    """Every unknown key is named; a valid key mixed in is not flagged."""
    with DataFlow(":memory:", migration_enabled=False) as db:
        with warnings.catch_warnings(record=True) as records:
            warnings.simplefilter("always")

            @db.model
            class MixedThing:
                id: int
                name: str

                # soft_delete is recognized; versioned + encryption are not.
                __dataflow__ = {
                    "soft_delete": True,
                    "versioned": True,
                    "encryption": True,
                }

        unknown = _unknown_key_warnings(records)
        assert len(unknown) == 1, unknown
        message = str(unknown[0].message)
        assert "versioned" in message
        assert "encryption" in message
        # The recognized key must NOT be reported as unknown.
        assert "soft_delete" not in message.split("Recognized keys:")[0]


@pytest.mark.regression
def test_recognized_keys_emit_no_unknown_key_warning():
    """A model using only recognized keys must NOT emit the #1599 warning."""
    with DataFlow(":memory:", migration_enabled=False) as db:
        with warnings.catch_warnings(record=True) as records:
            warnings.simplefilter("always")

            @db.model
            class CleanThing:
                id: int
                name: str
                tenant_id: str

                __dataflow__ = {
                    "soft_delete": True,
                    "multi_tenant": True,
                    "audit_log": True,
                }

        assert _unknown_key_warnings(records) == []
        assert "CleanThing" in db._models


@pytest.mark.regression
def test_empty_dataflow_config_emits_no_warning():
    """An empty / absent ``__dataflow__`` must be silent."""
    with DataFlow(":memory:", migration_enabled=False) as db:
        with warnings.catch_warnings(record=True) as records:
            warnings.simplefilter("always")

            @db.model
            class PlainThing:
                id: int
                name: str

                __dataflow__ = {}

            @db.model
            class NoConfigThing:
                id: int
                name: str

        assert _unknown_key_warnings(records) == []
        assert "PlainThing" in db._models
        assert "NoConfigThing" in db._models
