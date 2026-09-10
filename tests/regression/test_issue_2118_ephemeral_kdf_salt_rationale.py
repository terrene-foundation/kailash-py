# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2118 -- why SecureKeyStorage's KDF salt is safe.

#2118 is documentation-only: the ephemeral-salt branch in ``SecureKeyStorage``
has the exact shape of the defect class #2063 upgraded and #2083 / #2092 closed
elsewhere (generate-on-unconfigured, WARN, continue), and PR #2098 dispositioned
it "correctly ephemeral" without recording WHY. A future reader applying that
blanket rule mechanically would wave through a genuinely unsafe sibling.

The comment now states two measured properties. These tests pin those
properties, so the comment cannot silently go stale:

1. ``_keys`` is in-memory only -- no file, database, or network sink anywhere
   in the class. Nothing encrypted here outlives the process, so a salt that
   does not survive a restart costs nothing that is not already lost.
2. Zero construction sites in shipped source -- it is reachable only by a user
   who deliberately constructs it, having seen the WARNING.

Either property changing is exactly the "REVISIT IF" trigger the comment names,
and the assertion messages point back at it.
"""

from __future__ import annotations

import ast
import base64
import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SECURITY_MODULE = REPO_ROOT / "src" / "kailash" / "trust" / "security.py"
MASTER_KEY_ENV = "KAILASH_TEST_2118_KEY"

# Sinks that would make an ephemeral salt unsafe: anything that outlives the
# process or hands ciphertext to another one.
PERSISTENCE_MARKERS = (
    "open(",
    "Path(",
    "pathlib",
    "shelve",
    "pickle.dump",
    "json.dump",
    "sqlite3",
    "redis",
    "requests.",
    "urllib",
    "socket",
    "boto3",
)


@pytest.fixture
def master_key(monkeypatch):
    monkeypatch.setenv(MASTER_KEY_ENV, "unit-test-master-key")
    monkeypatch.delenv(f"{MASTER_KEY_ENV}_SALT", raising=False)
    return MASTER_KEY_ENV


def _secure_key_storage_class_source() -> str:
    tree = ast.parse(SECURITY_MODULE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "SecureKeyStorage":
            return ast.get_source_segment(
                SECURITY_MODULE.read_text(encoding="utf-8"), node
            )
    raise AssertionError("SecureKeyStorage class not found")


# ---------------------------------------------------------------------------
# Property 1 -- the store is in-memory only.
# ---------------------------------------------------------------------------


def test_keys_are_held_in_a_plain_in_memory_dict(master_key):
    from kailash.trust.security import SecureKeyStorage

    storage = SecureKeyStorage(master_key)
    assert isinstance(storage._keys, dict)
    assert storage._keys == {}

    storage.store_key("agent-001", b"private-key-bytes")
    assert list(storage._keys) == ["agent-001"]
    assert storage.retrieve_key("agent-001") == b"private-key-bytes"

    # A second instance shares nothing: the store has no backing at all.
    assert SecureKeyStorage(master_key)._keys == {}


def test_secure_key_storage_has_no_persistent_sink():
    """REVISIT trigger: a persistent sink makes the ephemeral salt unsafe."""
    source = _secure_key_storage_class_source()
    # Strip comments so the REVISIT commentary itself cannot trip the scan.
    code = "\n".join(re.sub(r"#.*$", "", line) for line in source.splitlines())

    found = [marker for marker in PERSISTENCE_MARKERS if marker in code]
    assert found == [], (
        f"SecureKeyStorage gained a persistent sink ({found}). The ephemeral "
        "KDF salt is only safe because nothing it encrypts outlives the "
        "process -- see the 'REVISIT IF' note at the os.urandom(32) branch in "
        f"{SECURITY_MODULE.relative_to(REPO_ROOT)}."
    )


def test_control_persistence_scan_detects_a_sink():
    """The scan must be able to return the opposite verdict."""
    code = "class X:\n    def save(self):\n        open('/tmp/keys', 'wb')\n"
    assert [m for m in PERSISTENCE_MARKERS if m in code] == ["open("]


# ---------------------------------------------------------------------------
# Property 2 -- no shipped code constructs it on a default path.
# ---------------------------------------------------------------------------


def test_no_shipped_code_constructs_secure_key_storage():
    """REVISIT trigger: a shipped construction site reaches the WARN branch."""
    hits: list[str] = []
    roots = [REPO_ROOT / "src"]
    roots.extend(
        package / "src"
        for package in sorted((REPO_ROOT / "packages").glob("*"))
        if (package / "src").is_dir()
    )

    for root in roots:
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(source)):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "SecureKeyStorage"
                ):
                    hits.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")

    assert hits == [], (
        f"SecureKeyStorage is now constructed by shipped code ({hits}). The "
        "ephemeral-salt disposition assumed it was reachable only by a caller "
        "who had read the WARNING -- see the 'REVISIT IF' note in "
        f"{SECURITY_MODULE.relative_to(REPO_ROOT)}."
    )


def test_control_construction_scan_detects_a_call():
    tree = ast.parse("storage = SecureKeyStorage()\n")
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "SecureKeyStorage"
    ]
    assert len(found) == 1


# ---------------------------------------------------------------------------
# The rationale itself is present and behaviour is unchanged (#2118 is docs-only).
# ---------------------------------------------------------------------------


def test_rationale_comment_records_both_properties_and_the_revisit_trigger():
    source = SECURITY_MODULE.read_text(encoding="utf-8")
    for fragment in (
        "WHY THE EPHEMERAL SALT IS SAFE HERE (#2118)",
        "NOTHING THIS CLASS ENCRYPTS OUTLIVES THE PROCESS",
        "NO SHIPPED CODE CONSTRUCTS IT",
        "REVISIT IF",
    ):
        assert fragment in source, f"rationale lost its '{fragment}' clause"


def test_salt_resolution_behaviour_is_unchanged(master_key, monkeypatch, caplog):
    """#2118 must not alter behaviour: three-way salt priority still holds."""
    import logging

    from kailash.trust.security import SecureKeyStorage

    explicit = os.urandom(32)
    assert SecureKeyStorage(master_key, salt=explicit)._salt == explicit

    env_salt = os.urandom(32)
    monkeypatch.setenv(f"{master_key}_SALT", base64.b64encode(env_salt).decode())
    assert SecureKeyStorage(master_key)._salt == env_salt

    monkeypatch.delenv(f"{master_key}_SALT")
    with caplog.at_level(logging.WARNING, logger="kailash.trust.security"):
        generated = SecureKeyStorage(master_key)
    assert len(generated._salt) == 32
    assert generated._salt not in (explicit, env_salt)
    # The loud WARN is the whole reason this branch is acceptable.
    assert any(
        "No salt configured" in record.message for record in caplog.records
    ), "the ephemeral-salt branch must announce itself at WARNING"
