"""Unit tests for the WorkflowVersionRegistry module.

Tests registration, latest resolution, deprecation, semver ordering,
and edge cases for the versioning system.
"""

from unittest.mock import MagicMock

import pytest

from kailash.workflow.versioning import (
    VersionedWorkflow,
    WorkflowVersionRegistry,
    parse_semver,
)


class TestParseSemver:
    """Tests for the parse_semver utility function."""

    def test_standard_version(self):
        """Standard semver strings should parse correctly."""
        assert parse_semver("1.0.0") == (1, 0, 0)
        assert parse_semver("0.12.5") == (0, 12, 5)
        assert parse_semver("10.20.30") == (10, 20, 30)

    def test_version_with_prerelease(self):
        """Pre-release suffixes should be stripped for ordering."""
        assert parse_semver("1.0.0-beta.1") == (1, 0, 0)
        assert parse_semver("2.0.0-rc.3") == (2, 0, 0)
        assert parse_semver("0.1.0-alpha") == (0, 1, 0)

    def test_invalid_version_raises(self):
        """Invalid semver strings should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid semver"):
            parse_semver("not-a-version")

        with pytest.raises(ValueError, match="Invalid semver"):
            parse_semver("1.0")

        with pytest.raises(ValueError, match="Invalid semver"):
            parse_semver("")

        with pytest.raises(ValueError, match="Invalid semver"):
            parse_semver("v1.0.0")

    def test_ordering(self):
        """Parsed tuples should sort correctly."""
        versions = ["2.0.0", "1.1.0", "1.0.0", "0.9.9", "1.0.1"]
        parsed = [parse_semver(v) for v in versions]
        sorted_parsed = sorted(parsed)

        assert sorted_parsed == [
            (0, 9, 9),
            (1, 0, 0),
            (1, 0, 1),
            (1, 1, 0),
            (2, 0, 0),
        ]


class TestVersionedWorkflow:
    """Tests for the VersionedWorkflow dataclass."""

    def test_creation_with_defaults(self):
        """VersionedWorkflow should have sensible defaults."""
        builder = MagicMock()
        vw = VersionedWorkflow(version="1.0.0", workflow_builder=builder)

        assert vw.version == "1.0.0"
        assert vw.workflow_builder is builder
        assert vw.deprecated is False
        assert vw.migration_fn is None

    def test_creation_with_migration_fn(self):
        """VersionedWorkflow should accept a migration function."""
        builder = MagicMock()
        migration = lambda old: {**old, "new_key": True}
        vw = VersionedWorkflow(
            version="2.0.0",
            workflow_builder=builder,
            migration_fn=migration,
        )

        assert vw.migration_fn is migration
        result = vw.migration_fn({"old_key": 1})
        assert result == {"old_key": 1, "new_key": True}

    def test_invalid_version_in_post_init(self):
        """VersionedWorkflow should reject invalid version strings."""
        with pytest.raises(ValueError, match="Invalid semver"):
            VersionedWorkflow(version="bad", workflow_builder=MagicMock())


class TestWorkflowVersionRegistry:
    """Tests for the WorkflowVersionRegistry."""

    def test_register_and_get(self):
        """Basic register/get flow should work."""
        registry = WorkflowVersionRegistry()
        builder = MagicMock()

        vw = registry.register("my_wf", "1.0.0", builder)

        assert vw.version == "1.0.0"
        assert vw.workflow_builder is builder

        retrieved = registry.get("my_wf", version="1.0.0")
        assert retrieved is vw

    def test_get_latest_returns_highest_version(self):
        """get() without version should return the highest non-deprecated version."""
        registry = WorkflowVersionRegistry()
        b1 = MagicMock(name="builder_v1")
        b2 = MagicMock(name="builder_v2")
        b3 = MagicMock(name="builder_v3")

        registry.register("wf", "1.0.0", b1)
        registry.register("wf", "2.0.0", b2)
        registry.register("wf", "1.5.0", b3)

        latest = registry.get("wf")
        assert latest.version == "2.0.0"
        assert latest.workflow_builder is b2

    def test_get_latest_skips_deprecated(self):
        """get() should skip deprecated versions when resolving latest."""
        registry = WorkflowVersionRegistry()
        b1 = MagicMock(name="builder_v1")
        b2 = MagicMock(name="builder_v2")

        registry.register("wf", "1.0.0", b1)
        registry.register("wf", "2.0.0", b2)
        registry.deprecate("wf", "2.0.0")

        latest = registry.get("wf")
        assert latest.version == "1.0.0"

    def test_get_explicit_version_returns_deprecated(self):
        """get() with explicit version should return even deprecated versions."""
        registry = WorkflowVersionRegistry()
        builder = MagicMock()

        registry.register("wf", "1.0.0", builder)
        registry.deprecate("wf", "1.0.0")

        result = registry.get("wf", version="1.0.0")
        assert result.version == "1.0.0"
        assert result.deprecated is True

    def test_get_nonexistent_workflow_raises(self):
        """get() should raise KeyError for unregistered workflow names."""
        registry = WorkflowVersionRegistry()

        with pytest.raises(KeyError, match="not registered"):
            registry.get("nonexistent")

    def test_get_nonexistent_version_raises(self):
        """get() should raise KeyError for unregistered versions."""
        registry = WorkflowVersionRegistry()
        registry.register("wf", "1.0.0", MagicMock())

        with pytest.raises(KeyError, match="not found"):
            registry.get("wf", version="9.9.9")

    def test_get_all_deprecated_raises(self):
        """get() should raise KeyError when all versions are deprecated."""
        registry = WorkflowVersionRegistry()
        registry.register("wf", "1.0.0", MagicMock())
        registry.register("wf", "2.0.0", MagicMock())
        registry.deprecate("wf", "1.0.0")
        registry.deprecate("wf", "2.0.0")

        with pytest.raises(KeyError, match="All versions are deprecated"):
            registry.get("wf")

    def test_register_duplicate_version_raises(self):
        """register() should reject duplicate version numbers."""
        registry = WorkflowVersionRegistry()
        registry.register("wf", "1.0.0", MagicMock())

        with pytest.raises(ValueError, match="already registered"):
            registry.register("wf", "1.0.0", MagicMock())

    def test_register_invalid_version_raises(self):
        """register() should reject invalid semver strings."""
        registry = WorkflowVersionRegistry()

        with pytest.raises(ValueError, match="Invalid semver"):
            registry.register("wf", "bad-version", MagicMock())

    def test_list_versions_sorted_by_semver(self):
        """list_versions should return versions sorted by semver ascending."""
        registry = WorkflowVersionRegistry()
        registry.register("wf", "2.0.0", MagicMock())
        registry.register("wf", "1.0.0", MagicMock())
        registry.register("wf", "1.5.0", MagicMock())
        registry.register("wf", "0.1.0", MagicMock())

        versions = registry.list_versions("wf")

        assert [v.version for v in versions] == [
            "0.1.0",
            "1.0.0",
            "1.5.0",
            "2.0.0",
        ]

    def test_list_versions_includes_deprecated(self):
        """list_versions should include deprecated versions."""
        registry = WorkflowVersionRegistry()
        registry.register("wf", "1.0.0", MagicMock())
        registry.register("wf", "2.0.0", MagicMock())
        registry.deprecate("wf", "1.0.0")

        versions = registry.list_versions("wf")
        assert len(versions) == 2
        assert versions[0].deprecated is True
        assert versions[1].deprecated is False

    def test_list_versions_nonexistent_raises(self):
        """list_versions should raise KeyError for unregistered names."""
        registry = WorkflowVersionRegistry()

        with pytest.raises(KeyError, match="not registered"):
            registry.list_versions("nonexistent")

    def test_deprecate_workflow(self):
        """deprecate should mark the version as deprecated."""
        registry = WorkflowVersionRegistry()
        registry.register("wf", "1.0.0", MagicMock())

        assert registry.get("wf", version="1.0.0").deprecated is False
        registry.deprecate("wf", "1.0.0")
        assert registry.get("wf", version="1.0.0").deprecated is True

    def test_deprecate_nonexistent_workflow_raises(self):
        """deprecate should raise KeyError for unregistered names."""
        registry = WorkflowVersionRegistry()

        with pytest.raises(KeyError, match="not registered"):
            registry.deprecate("nonexistent", "1.0.0")

    def test_deprecate_nonexistent_version_raises(self):
        """deprecate should raise KeyError for unregistered versions."""
        registry = WorkflowVersionRegistry()
        registry.register("wf", "1.0.0", MagicMock())

        with pytest.raises(KeyError, match="not found"):
            registry.deprecate("wf", "9.9.9")

    def test_list_workflow_names(self):
        """list_workflow_names should return sorted names."""
        registry = WorkflowVersionRegistry()
        registry.register("zeta_wf", "1.0.0", MagicMock())
        registry.register("alpha_wf", "1.0.0", MagicMock())
        registry.register("mid_wf", "1.0.0", MagicMock())

        names = registry.list_workflow_names()
        assert names == ["alpha_wf", "mid_wf", "zeta_wf"]

    def test_list_workflow_names_empty(self):
        """list_workflow_names should return empty list when no workflows registered."""
        registry = WorkflowVersionRegistry()
        assert registry.list_workflow_names() == []

    def test_remove_version(self):
        """remove should delete a specific version."""
        registry = WorkflowVersionRegistry()
        registry.register("wf", "1.0.0", MagicMock())
        registry.register("wf", "2.0.0", MagicMock())

        registry.remove("wf", "1.0.0")

        versions = registry.list_versions("wf")
        assert len(versions) == 1
        assert versions[0].version == "2.0.0"

    def test_remove_last_version_cleans_up_name(self):
        """Removing the last version should clean up the workflow name."""
        registry = WorkflowVersionRegistry()
        registry.register("wf", "1.0.0", MagicMock())

        registry.remove("wf", "1.0.0")

        assert "wf" not in registry.list_workflow_names()
        with pytest.raises(KeyError):
            registry.get("wf")

    def test_remove_nonexistent_raises(self):
        """remove should raise KeyError for missing workflow or version."""
        registry = WorkflowVersionRegistry()

        with pytest.raises(KeyError, match="not registered"):
            registry.remove("nonexistent", "1.0.0")

        registry.register("wf", "1.0.0", MagicMock())
        with pytest.raises(KeyError, match="not found"):
            registry.remove("wf", "9.9.9")

    def test_semver_ordering_with_patch_versions(self):
        """Patch version differences should be ordered correctly."""
        registry = WorkflowVersionRegistry()
        registry.register("wf", "1.0.2", MagicMock())
        registry.register("wf", "1.0.0", MagicMock())
        registry.register("wf", "1.0.10", MagicMock())
        registry.register("wf", "1.0.1", MagicMock())

        latest = registry.get("wf")
        assert latest.version == "1.0.10"

        versions = registry.list_versions("wf")
        assert [v.version for v in versions] == [
            "1.0.0",
            "1.0.1",
            "1.0.2",
            "1.0.10",
        ]

    def test_multiple_workflows_independent(self):
        """Different workflow names should be independent."""
        registry = WorkflowVersionRegistry()
        b1 = MagicMock(name="wf_a_builder")
        b2 = MagicMock(name="wf_b_builder")

        registry.register("wf_a", "1.0.0", b1)
        registry.register("wf_b", "1.0.0", b2)

        assert registry.get("wf_a").workflow_builder is b1
        assert registry.get("wf_b").workflow_builder is b2

        registry.deprecate("wf_a", "1.0.0")
        assert registry.get("wf_b").deprecated is False

    def test_register_with_migration_fn(self):
        """register should store the migration function."""
        registry = WorkflowVersionRegistry()
        migration = lambda old: {**old, "v2_flag": True}

        vw = registry.register("wf", "2.0.0", MagicMock(), migration_fn=migration)

        assert vw.migration_fn is migration
        result = vw.migration_fn({"key": "val"})
        assert result == {"key": "val", "v2_flag": True}
