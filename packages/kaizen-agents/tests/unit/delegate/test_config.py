"""Tests for kz.config — configuration loading, merging, and effort levels."""

from __future__ import annotations

from pathlib import Path

import pytest

from kaizen_agents.delegate.config.effort import EffortLevel, EffortPreset, get_effort_preset
from kaizen_agents.delegate.config.loader import (
    KzConfig,
    _deep_merge,
    load_config,
    load_kzignore,
    matches_kzignore,
)


# =====================================================================
# Effort levels
# =====================================================================


class TestEffortLevel:
    """EffortLevel enum and preset resolution."""

    def test_low_preset_returns_fast_model(self) -> None:
        preset = get_effort_preset(EffortLevel.LOW)
        assert preset.level is EffortLevel.LOW
        assert preset.model == "gpt-4o-mini"
        assert preset.temperature == 0.2
        assert preset.max_tokens == 4096
        assert preset.reasoning_effort == "low"

    def test_medium_preset_is_default(self) -> None:
        preset = get_effort_preset(EffortLevel.MEDIUM)
        assert preset.level is EffortLevel.MEDIUM
        assert preset.model == "gpt-4o"
        assert preset.temperature == 0.4
        assert preset.max_tokens == 16384
        assert preset.reasoning_effort == "medium"

    def test_high_preset_returns_best_model(self) -> None:
        preset = get_effort_preset(EffortLevel.HIGH)
        assert preset.level is EffortLevel.HIGH
        assert preset.model == "o3"
        assert preset.temperature == 1.0
        assert preset.max_tokens == 65536
        assert preset.reasoning_effort == "high"

    def test_string_level_accepted(self) -> None:
        preset = get_effort_preset("low")
        assert preset.level is EffortLevel.LOW

    def test_string_level_case_insensitive(self) -> None:
        preset = get_effort_preset("HIGH")
        assert preset.level is EffortLevel.HIGH

    def test_invalid_string_level_raises(self) -> None:
        with pytest.raises(ValueError, match="turbo"):
            get_effort_preset("turbo")

    def test_model_override(self) -> None:
        preset = get_effort_preset(EffortLevel.LOW, model_override="custom-model")
        assert preset.model == "custom-model"
        # Other fields unchanged
        assert preset.temperature == 0.2

    def test_temperature_override(self) -> None:
        preset = get_effort_preset(EffortLevel.MEDIUM, temperature_override=0.9)
        assert preset.temperature == 0.9
        assert preset.model == "gpt-4o"

    def test_max_tokens_override(self) -> None:
        preset = get_effort_preset(EffortLevel.HIGH, max_tokens_override=1024)
        assert preset.max_tokens == 1024

    def test_preset_is_frozen(self) -> None:
        preset = get_effort_preset(EffortLevel.LOW)
        with pytest.raises(AttributeError):
            preset.model = "something-else"  # type: ignore[misc]


# =====================================================================
# Deep merge
# =====================================================================


class TestDeepMerge:
    """_deep_merge utility."""

    def test_flat_override(self) -> None:
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self) -> None:
        base = {"tools": {"allow": ["*"], "deny": []}}
        override = {"tools": {"deny": ["bash"]}}
        result = _deep_merge(base, override)
        assert result == {"tools": {"allow": ["*"], "deny": ["bash"]}}

    def test_does_not_mutate_inputs(self) -> None:
        base = {"a": {"x": 1}}
        override = {"a": {"y": 2}}
        _deep_merge(base, override)
        assert base == {"a": {"x": 1}}
        assert override == {"a": {"y": 2}}


# =====================================================================
# Config loading
# =====================================================================


class TestLoadConfig:
    """Three-level config loader."""

    def test_defaults_when_no_files(self, tmp_path: Path) -> None:
        """No config files or env vars -> returns defaults."""
        config = load_config(project_root=tmp_path, user_home=tmp_path / "fakehome")
        assert config.model == "gpt-4o"
        assert config.provider == "openai"
        assert config.effort_level is EffortLevel.MEDIUM
        assert config.max_turns == 50
        assert config.max_tokens == 16384
        assert config.temperature == 0.4
        assert config.tools_allow == []
        assert config.tools_deny == []
        assert config.loaded_from == []

    def test_user_level_config(self, tmp_path: Path) -> None:
        """User ~/.kz/config.toml is loaded."""
        home = tmp_path / "home"
        kz_dir = home / ".kz"
        kz_dir.mkdir(parents=True)
        (kz_dir / "config.toml").write_text(
            'model = "claude-sonnet"\nprovider = "anthropic"\n',
            encoding="utf-8",
        )
        config = load_config(project_root=tmp_path / "proj", user_home=home)
        assert config.model == "claude-sonnet"
        assert config.provider == "anthropic"
        assert str(kz_dir / "config.toml") in config.loaded_from

    def test_project_overrides_user(self, tmp_path: Path) -> None:
        """Project .kz/config.toml overrides user-level."""
        home = tmp_path / "home"
        (home / ".kz").mkdir(parents=True)
        (home / ".kz" / "config.toml").write_text(
            'model = "user-model"\nmax_turns = 10\n',
            encoding="utf-8",
        )

        proj = tmp_path / "proj"
        (proj / ".kz").mkdir(parents=True)
        (proj / ".kz" / "config.toml").write_text(
            'model = "project-model"\n',
            encoding="utf-8",
        )

        config = load_config(project_root=proj, user_home=home)
        assert config.model == "project-model"  # overridden by project
        assert config.max_turns == 10  # inherited from user

    def test_env_overrides_everything(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """KZ_* env vars override file-based config."""
        proj = tmp_path / "proj"
        (proj / ".kz").mkdir(parents=True)
        (proj / ".kz" / "config.toml").write_text(
            'model = "file-model"\n',
            encoding="utf-8",
        )

        monkeypatch.setenv("KZ_MODEL", "env-model")
        monkeypatch.setenv("KZ_MAX_TOKENS", "8192")

        config = load_config(project_root=proj, user_home=tmp_path / "fakehome")
        assert config.model == "env-model"
        assert config.max_tokens == 8192
        assert "env" in config.loaded_from

    def test_effort_level_from_toml(self, tmp_path: Path) -> None:
        """effort_level string in TOML is converted to EffortLevel enum."""
        proj = tmp_path / "proj"
        (proj / ".kz").mkdir(parents=True)
        (proj / ".kz" / "config.toml").write_text(
            'effort_level = "high"\n',
            encoding="utf-8",
        )
        config = load_config(project_root=proj, user_home=tmp_path / "fakehome")
        assert config.effort_level is EffortLevel.HIGH

    def test_effort_level_from_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KZ_EFFORT_LEVEL", "low")
        config = load_config(project_root=tmp_path, user_home=tmp_path / "fakehome")
        assert config.effort_level is EffortLevel.LOW

    def test_tools_config(self, tmp_path: Path) -> None:
        """Tools allow/deny lists from TOML."""
        proj = tmp_path / "proj"
        (proj / ".kz").mkdir(parents=True)
        (proj / ".kz" / "config.toml").write_text(
            '[tools]\nallow = ["file_*", "glob"]\ndeny = ["bash"]\n',
            encoding="utf-8",
        )
        config = load_config(project_root=proj, user_home=tmp_path / "fakehome")
        assert config.tools_allow == ["file_*", "glob"]
        assert config.tools_deny == ["bash"]

    def test_temperature_from_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KZ_TEMPERATURE", "0.8")
        config = load_config(project_root=tmp_path, user_home=tmp_path / "fakehome")
        assert config.temperature == 0.8


# =====================================================================
# .kzignore
# =====================================================================


class TestKzIgnore:
    """kzignore loading and matching."""

    def test_load_empty_when_no_file(self, tmp_path: Path) -> None:
        patterns = load_kzignore(tmp_path)
        assert patterns == []

    def test_load_patterns(self, tmp_path: Path) -> None:
        (tmp_path / ".kzignore").write_text(
            "# comment\nnode_modules/\n*.pyc\n\n!important.pyc\n",
            encoding="utf-8",
        )
        patterns = load_kzignore(tmp_path)
        assert patterns == ["node_modules/", "*.pyc", "!important.pyc"]

    def test_simple_pattern_match(self) -> None:
        assert matches_kzignore("src/foo.pyc", ["*.pyc"]) is True
        assert matches_kzignore("src/foo.py", ["*.pyc"]) is False

    def test_directory_pattern(self) -> None:
        assert matches_kzignore("node_modules/package/index.js", ["node_modules"]) is True

    def test_negation(self) -> None:
        patterns = ["*.log", "!important.log"]
        assert matches_kzignore("debug.log", patterns) is True
        assert matches_kzignore("important.log", patterns) is False

    def test_doublestar_pattern(self) -> None:
        assert matches_kzignore("src/deep/nested/file.tmp", ["**/*.tmp"]) is True

    def test_anchored_pattern(self) -> None:
        patterns = ["/build"]
        assert matches_kzignore("build/output.js", patterns) is True
        # Non-root "build" should not match an anchored pattern
        assert matches_kzignore("src/build/output.js", patterns) is False

    def test_kzignore_loaded_into_config(self, tmp_path: Path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / ".kzignore").write_text("*.log\nnode_modules/\n", encoding="utf-8")
        config = load_config(project_root=proj, user_home=tmp_path / "fakehome")
        assert config.ignore_patterns == ["*.log", "node_modules/"]
