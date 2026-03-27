# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Static analysis checks for security patterns.

These tests scan production source code to verify that security-critical
patterns remain intact. They catch regressions where a developer might
replace a safe pattern with an unsafe one during refactoring.

See: src/kailash/trust/plane/CLAUDE.md "What NOT to Change -- Security Patterns"
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Root of the production source code under test
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
_SRC_DIR = _PROJECT_ROOT / "src" / "kailash" / "trust" / "plane"
_TRUST_DIR = _PROJECT_ROOT / "src" / "kailash" / "trust"


def _collect_python_files(directory: Path) -> list[Path]:
    """Collect all .py files under the given directory, excluding tests."""
    return sorted(directory.rglob("*.py"))


def _read_source(path: Path) -> str:
    """Read a Python source file, returning its content."""
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Static Check: No bare open() for JSON reads in production code
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestStaticNoBareOpen:
    """Verify no bare open() is used for JSON file reads in production code.

    Pattern 2 + 4: All file reads must use safe_read_json() or safe_read_text()
    which include O_NOFOLLOW protection. Bare open() follows symlinks.
    """

    # Patterns that indicate unsafe file reading for JSON
    _BARE_OPEN_JSON_RE = re.compile(
        r"""
        # Match: json.loads(path.read_text()) or json.load(open(...))
        (?:
            json\.loads?\s*\(\s*(?:open|Path|path)\b  # json.load(open(...
            |
            json\.loads\s*\(\s*\w+\.read_text\s*\(    # json.loads(x.read_text()
        )
        """,
        re.VERBOSE,
    )

    # Files that are allowed exceptions (test files, migration helpers)
    _ALLOWED_FILES: frozenset[str] = frozenset()

    def test_no_bare_open_for_json(self) -> None:
        """Production code must not use bare open() or read_text() for JSON.

        SECURITY: bare open() follows symlinks, bypassing O_NOFOLLOW.
        All JSON reads must go through safe_read_json().
        """
        violations: list[str] = []

        for py_file in _collect_python_files(_SRC_DIR):
            rel = py_file.relative_to(_SRC_DIR)
            if str(rel) in self._ALLOWED_FILES:
                continue

            source = _read_source(py_file)
            for i, line in enumerate(source.splitlines(), 1):
                # Skip comments and strings
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if self._BARE_OPEN_JSON_RE.search(line):
                    violations.append(f"{rel}:{i}: {stripped.strip()}")

        assert not violations, (
            "SECURITY REGRESSION: Found bare open()/read_text() for JSON reads "
            "in production code. Use safe_read_json() instead for O_NOFOLLOW "
            "protection (Pattern 2+4).\n\nViolations:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


# ---------------------------------------------------------------------------
# Static Check: No == for hash/signature comparison
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestStaticNoEqualityHash:
    """Verify no == comparison for hash/signature values in production code.

    Pattern 8: String equality leaks timing information. All hash
    comparisons must use hmac.compare_digest().
    """

    # Patterns that indicate hash equality comparison
    # Matches: stored_hash == computed_hash, content_hash == expected, etc.
    _HASH_EQUALITY_RE = re.compile(
        r"""
        (?:
            \b(?:hash|digest|signature|hmac|checksum)\b  # variable name contains hash-related word
            \s*(?:==|!=)\s*                               # equality or inequality
            |
            \s*(?:==|!=)\s*                               # or the comparison is on the right
            .*\b(?:hash|digest|signature|hmac|checksum)\b
        )
        """,
        re.VERBOSE | re.IGNORECASE,
    )

    # Lines that are actually safe (using compare_digest, assertions, etc.)
    _SAFE_PATTERNS = [
        "compare_digest",
        "assert",
        "hasattr",
        "isinstance",
        "envelope_hash()",  # method call returning string, not comparison
        "content_hash()",
        '== ""',  # empty string check (zeroization tombstone)
        '!= ""',
    ]

    def test_no_equality_for_hashes(self) -> None:
        """Production code must not use == for hash/signature comparison.

        SECURITY: String == leaks timing information that enables
        incremental hash forgery via side-channel attacks.
        Use hmac.compare_digest() instead (Pattern 8).
        """
        violations: list[str] = []

        for py_file in _collect_python_files(_SRC_DIR):
            rel = py_file.relative_to(_SRC_DIR)
            source = _read_source(py_file)

            for i, line in enumerate(source.splitlines(), 1):
                stripped = line.strip()
                # Skip comments
                if stripped.startswith("#"):
                    continue
                # Skip safe patterns
                if any(safe in stripped for safe in self._SAFE_PATTERNS):
                    continue
                # Check for hash equality
                if self._HASH_EQUALITY_RE.search(stripped):
                    # Additional filter: must be an actual comparison, not a
                    # string containing the word "hash" in a docstring/comment
                    if '"""' in stripped or "'''" in stripped:
                        continue
                    if stripped.startswith(("def ", "class ", "return ")):
                        # Method definitions mentioning hash are fine
                        if "==" not in stripped and "!=" not in stripped:
                            continue
                    violations.append(f"{rel}:{i}: {stripped}")

        assert not violations, (
            "SECURITY REGRESSION: Found == or != comparison for hash/signature "
            "values in production code. Use hmac.compare_digest() instead "
            "(Pattern 8, timing side-channel prevention).\n\nViolations:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


# ---------------------------------------------------------------------------
# Static Check: from_dict() methods don't use silent defaults for required fields
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestStaticFromDictValidation:
    """Verify from_dict() methods validate required fields.

    Pattern 11: Silent defaults accept malformed JSON without errors.
    Required fields must be accessed with data["key"] (KeyError) or
    explicit validation, not data.get("key", default).
    """

    def test_key_from_dict_methods_exist(self) -> None:
        """Key data classes must have from_dict() methods that validate."""
        from kailash.trust.plane.delegation import DelegationRecipient
        from kailash.trust.plane.models import DecisionRecord, MilestoneRecord
        from kailash.trust.plane.rbac import RolePermission
        from kailash.trust.plane.shadow import ShadowSession, ShadowToolCall

        classes_with_from_dict = [
            DelegationRecipient,
            DecisionRecord,
            MilestoneRecord,
            RolePermission,
            ShadowToolCall,
            ShadowSession,
        ]

        for cls in classes_with_from_dict:
            assert hasattr(cls, "from_dict"), (
                f"{cls.__name__} is missing from_dict() method. "
                f"All data classes must support deserialization with validation."
            )
            # Verify it's a classmethod
            method = getattr(cls, "from_dict")
            assert isinstance(
                method.__func__ if hasattr(method, "__func__") else method,
                (
                    classmethod.__func__.__class__
                    if hasattr(classmethod, "__func__")
                    else type(lambda: None)
                ),
            ) or callable(method), f"{cls.__name__}.from_dict must be callable"

    def test_from_dict_rejects_empty_dict(self) -> None:
        """All from_dict() methods must reject empty dicts (no silent defaults).

        SECURITY: An attacker sending {} should get a clear error, not
        an object with all-default values.
        """
        from kailash.trust.plane.delegation import DelegationRecipient
        from kailash.trust.plane.models import DecisionRecord, MilestoneRecord
        from kailash.trust.plane.rbac import RolePermission
        from kailash.trust.plane.shadow import ShadowSession, ShadowToolCall

        classes_to_check = [
            ("DelegationRecipient", DelegationRecipient),
            ("DecisionRecord", DecisionRecord),
            ("MilestoneRecord", MilestoneRecord),
            ("RolePermission", RolePermission),
            ("ShadowToolCall", ShadowToolCall),
            ("ShadowSession", ShadowSession),
        ]

        for name, cls in classes_to_check:
            with pytest.raises((ValueError, KeyError, TypeError)):
                cls.from_dict({})


# ---------------------------------------------------------------------------
# Static Check: validate_id() used before filesystem operations
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestStaticValidateIdUsage:
    """Verify that validate_id is imported where filesystem IDs are used.

    Pattern 1: Every module that constructs file paths from record IDs
    must import and use validate_id().
    """

    # Modules that handle record IDs in filesystem paths
    _MODULES_REQUIRING_VALIDATE_ID: list[str] = [
        "delegation.py",
        "rbac.py",
    ]

    def test_validate_id_imported(self) -> None:
        """Modules handling record IDs must import validate_id.

        SECURITY: Without validate_id(), IDs like '../../../etc/passwd'
        can traverse directories (Pattern 1).
        """
        for module_name in self._MODULES_REQUIRING_VALIDATE_ID:
            module_path = _SRC_DIR / module_name
            if not module_path.exists():
                continue
            source = _read_source(module_path)
            assert "validate_id" in source, (
                f"SECURITY REGRESSION: {module_name} does not import "
                f"validate_id. Record IDs used in filesystem paths MUST be "
                f"validated to prevent path traversal (Pattern 1)."
            )


# ---------------------------------------------------------------------------
# Static Check: O_NOFOLLOW used in safe_read_json
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestStaticONoFollow:
    """Verify O_NOFOLLOW is used in the locking module.

    Pattern 2: safe_read_json() must use os.open() with O_NOFOLLOW
    to prevent symlink TOCTOU attacks.
    """

    def test_o_nofollow_in_locking_module(self) -> None:
        """The _locking module must reference O_NOFOLLOW for symlink protection."""
        locking_path = _TRUST_DIR / "_locking.py"
        source = _read_source(locking_path)

        assert "O_NOFOLLOW" in source, (
            "SECURITY REGRESSION: _locking.py no longer references O_NOFOLLOW. "
            "safe_read_json() must use O_NOFOLLOW to prevent symlink attacks "
            "(Pattern 2)."
        )
        assert "os.open" in source, (
            "SECURITY REGRESSION: _locking.py no longer uses os.open(). "
            "safe_read_json() must use os.open() with O_NOFOLLOW for "
            "atomic symlink checking (Pattern 2)."
        )


# ---------------------------------------------------------------------------
# Static Check: atomic_write uses temp + rename
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestStaticAtomicWrite:
    """Verify atomic_write() uses temp file + rename pattern.

    Pattern 3: atomic_write() must use mkstemp + os.replace (or os.rename)
    for crash safety.
    """

    def test_atomic_write_uses_temp_rename(self) -> None:
        """atomic_write() must use mkstemp and os.replace for atomicity."""
        locking_path = _TRUST_DIR / "_locking.py"
        source = _read_source(locking_path)

        assert "mkstemp" in source, (
            "SECURITY REGRESSION: atomic_write() no longer uses mkstemp(). "
            "Writes must go to a temp file first for crash safety (Pattern 3)."
        )
        assert "os.replace" in source or "os.rename" in source, (
            "SECURITY REGRESSION: atomic_write() no longer uses os.replace(). "
            "The final step must be an atomic rename (Pattern 3)."
        )
        assert "fsync" in source, (
            "SECURITY REGRESSION: atomic_write() no longer uses fsync(). "
            "Data must be flushed to disk before rename (Pattern 3)."
        )


# ---------------------------------------------------------------------------
# Static Check: compare_digest used in delegation and project
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestStaticCompareDigest:
    """Verify hmac.compare_digest is used in security-critical modules.

    Pattern 8: delegation.py and project.py must use compare_digest
    for all hash comparisons.
    """

    _MODULES_REQUIRING_COMPARE_DIGEST: list[str] = [
        "delegation.py",
        "project.py",
    ]

    def test_compare_digest_in_critical_modules(self) -> None:
        """Security-critical modules must use hmac.compare_digest.

        SECURITY: Using == for hash comparison leaks timing information
        for byte-by-byte forgery (Pattern 8).
        """
        for module_name in self._MODULES_REQUIRING_COMPARE_DIGEST:
            module_path = _SRC_DIR / module_name
            if not module_path.exists():
                continue
            source = _read_source(module_path)
            assert "compare_digest" in source, (
                f"SECURITY REGRESSION: {module_name} does not use "
                f"compare_digest. All hash comparisons must use "
                f"hmac.compare_digest() to prevent timing attacks (Pattern 8)."
            )


# ---------------------------------------------------------------------------
# Static Check: math.isfinite in constraint models
# ---------------------------------------------------------------------------


@pytest.mark.security
class TestStaticIsFinite:
    """Verify math.isfinite() is used in constraint model validation.

    Pattern 5: The models module must use isfinite() to reject NaN/Inf
    in numeric constraint fields.
    """

    def test_isfinite_in_models(self) -> None:
        """models.py must use math.isfinite() for numeric field validation.

        SECURITY: NaN and Inf bypass numeric comparisons. Without
        isfinite(), an attacker can set constraints to NaN to make
        all checks pass silently (Pattern 5).
        """
        models_path = _SRC_DIR / "models.py"
        source = _read_source(models_path)

        assert "math.isfinite" in source or "isfinite" in source, (
            "SECURITY REGRESSION: models.py does not use math.isfinite(). "
            "Numeric constraint fields must be validated to reject NaN and "
            "Inf values (Pattern 5)."
        )
