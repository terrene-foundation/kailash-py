# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for platform-agnostic resource path normalization."""

from __future__ import annotations

import fnmatch

import pytest

from trustplane.pathutils import normalize_resource_path


class TestNormalizeResourcePath:
    """Core normalization behavior."""

    def test_backslash_converted_to_forward_slash(self):
        """Windows-style backslashes become forward slashes."""
        assert (
            normalize_resource_path("src\\trustplane\\models.py")
            == "src/trustplane/models.py"
        )

    def test_mixed_separators_normalized(self):
        """Mixed forward and back slashes become all forward slashes."""
        assert (
            normalize_resource_path("src\\trustplane/models.py")
            == "src/trustplane/models.py"
        )

    def test_trailing_slash_removed(self):
        """Trailing slash is stripped from normalized path."""
        assert normalize_resource_path("src/trustplane/") == "src/trustplane"

    def test_multiple_trailing_slashes_removed(self):
        """Multiple trailing slashes are all stripped."""
        assert normalize_resource_path("src/trustplane///") == "src/trustplane"

    def test_double_slash_collapsed(self):
        """Internal double slashes are collapsed to single."""
        assert (
            normalize_resource_path("src//trustplane//models.py")
            == "src/trustplane/models.py"
        )

    def test_unc_path_leading_double_slash_preserved(self):
        """Windows UNC path leading \\\\ becomes // and is preserved."""
        result = normalize_resource_path("\\\\server\\share\\file.txt")
        assert result == "//server/share/file.txt"

    def test_unc_path_forward_slash_preserved(self):
        """UNC-style //server/share is preserved."""
        result = normalize_resource_path("//server/share/file.txt")
        assert result == "//server/share/file.txt"

    def test_empty_string_returns_empty(self):
        """Empty string normalizes to empty string."""
        assert normalize_resource_path("") == ""

    def test_bare_slash_stays_as_slash(self):
        """A single '/' stays as '/'."""
        assert normalize_resource_path("/") == "/"

    def test_bare_backslash_becomes_slash(self):
        """A single backslash becomes '/'."""
        assert normalize_resource_path("\\") == "/"

    def test_absolute_path_preserved(self):
        """Absolute paths keep their leading slash."""
        assert normalize_resource_path("/usr/local/bin") == "/usr/local/bin"

    def test_absolute_path_trailing_slash_removed(self):
        """Absolute paths lose trailing slash."""
        assert normalize_resource_path("/usr/local/bin/") == "/usr/local/bin"

    def test_path_object_accepted(self):
        """pathlib.Path objects are accepted and converted."""
        from pathlib import PurePosixPath

        result = normalize_resource_path(PurePosixPath("src/trustplane/models.py"))
        assert result == "src/trustplane/models.py"

    def test_windows_path_string(self):
        """Full Windows-style path string converts correctly."""
        result = normalize_resource_path("C:\\Users\\dev\\project\\src")
        assert result == "C:/Users/dev/project/src"

    def test_dot_segments_not_resolved(self):
        """Dot segments (. and ..) are NOT resolved -- pure string transform."""
        # normalize_resource_path is a pure string function; it does NOT
        # do filesystem resolution. Dot segments are left intact.
        assert (
            normalize_resource_path("src/../keys/private.key")
            == "src/../keys/private.key"
        )
        assert normalize_resource_path("./src/main.py") == "./src/main.py"

    def test_triple_slash_collapsed_to_single(self):
        """Triple (or more) internal slashes collapse to single."""
        assert normalize_resource_path("src///models.py") == "src/models.py"

    def test_unc_path_internal_double_slash_collapsed(self):
        """UNC paths only preserve leading //; internal doubles collapse."""
        result = normalize_resource_path("//server//share//file.txt")
        assert result == "//server/share/file.txt"


class TestFnmatchWithNormalization:
    """Verify fnmatch works correctly with normalized paths."""

    @pytest.mark.parametrize(
        "pattern,path,expected",
        [
            ("src/trustplane/*", "src/trustplane/models.py", True),
            ("src/trustplane/*", "src/trustplane/project.py", True),
            ("src/trustplane/*", "docs/readme.md", False),
            ("*.py", "models.py", True),
            ("*.py", "models.txt", False),
            ("data/*.json", "data/config.json", True),
            # fnmatch '*' matches '/' on POSIX (unlike Windows).
            # This means '*.key' matches 'src/private.key' on Linux/macOS.
            # This is Python stdlib behavior, not a normalization concern.
            ("data/*.json", "data/nested/config.json", True),
            ("*.key", "private.key", True),
            ("*.key", "src/private.key", True),
            ("credentials*", "credentials.json", True),
            ("credentials*", "credentials_backup.txt", True),
        ],
    )
    def test_fnmatch_with_normalized_paths(self, pattern, path, expected):
        """fnmatch matches correctly when both sides are normalized."""
        norm_path = normalize_resource_path(path).lower()
        norm_pattern = normalize_resource_path(pattern).lower()
        assert fnmatch.fnmatch(norm_path, norm_pattern) == expected

    @pytest.mark.parametrize(
        "pattern,path,expected",
        [
            # Backslash patterns still match after normalization
            ("src\\trustplane\\*", "src/trustplane/models.py", True),
            ("data\\*.json", "data/config.json", True),
        ],
    )
    def test_fnmatch_with_backslash_patterns(self, pattern, path, expected):
        """Patterns with backslashes match after normalization."""
        norm_path = normalize_resource_path(path).lower()
        norm_pattern = normalize_resource_path(pattern).lower()
        assert fnmatch.fnmatch(norm_path, norm_pattern) == expected


class TestDataAccessConstraintsNormalization:
    """DataAccessConstraints normalizes paths on construction."""

    def test_backslash_paths_normalized_on_init(self):
        """Paths with backslashes are normalized in __post_init__."""
        from trustplane.models import DataAccessConstraints

        dac = DataAccessConstraints(
            read_paths=["src\\trustplane\\models.py", "docs\\readme.md"],
            write_paths=["output\\results\\"],
            blocked_paths=["keys\\", ".env"],
            blocked_patterns=["*.key", "credentials*"],
        )
        assert dac.read_paths == ["src/trustplane/models.py", "docs/readme.md"]
        assert dac.write_paths == ["output/results"]
        assert dac.blocked_paths == ["keys", ".env"]
        assert dac.blocked_patterns == ["*.key", "credentials*"]

    def test_mixed_separators_normalized_on_init(self):
        """Mixed separators are normalized in __post_init__."""
        from trustplane.models import DataAccessConstraints

        dac = DataAccessConstraints(
            read_paths=["src\\trustplane/models.py"],
            write_paths=[],
            blocked_paths=[],
            blocked_patterns=[],
        )
        assert dac.read_paths == ["src/trustplane/models.py"]

    def test_double_slashes_collapsed_on_init(self):
        """Double slashes are collapsed in __post_init__."""
        from trustplane.models import DataAccessConstraints

        dac = DataAccessConstraints(
            read_paths=["src//trustplane//models.py"],
            write_paths=[],
            blocked_paths=[],
            blocked_patterns=[],
        )
        assert dac.read_paths == ["src/trustplane/models.py"]

    def test_from_dict_normalizes_paths(self):
        """Paths loaded via from_dict are normalized."""
        from trustplane.models import DataAccessConstraints

        data = {
            "read_paths": ["src\\trustplane\\models.py"],
            "write_paths": ["output\\results\\"],
            "blocked_paths": ["keys\\"],
            "blocked_patterns": ["*.key"],
        }
        dac = DataAccessConstraints.from_dict(data)
        assert dac.read_paths == ["src/trustplane/models.py"]
        assert dac.write_paths == ["output/results"]
        assert dac.blocked_paths == ["keys"]
        assert dac.blocked_patterns == ["*.key"]

    def test_already_normalized_paths_unchanged(self):
        """Forward-slash paths pass through without modification."""
        from trustplane.models import DataAccessConstraints

        dac = DataAccessConstraints(
            read_paths=["src/trustplane/models.py"],
            write_paths=["output/results"],
            blocked_paths=["keys", ".env"],
            blocked_patterns=["*.key"],
        )
        assert dac.read_paths == ["src/trustplane/models.py"]
        assert dac.write_paths == ["output/results"]
        assert dac.blocked_paths == ["keys", ".env"]
        assert dac.blocked_patterns == ["*.key"]
