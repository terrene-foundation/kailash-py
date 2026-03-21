# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""TrustPlane project configuration.

Reads per-project settings from ``.trustplane.toml`` at the project root.
Falls back to hardcoded defaults when the file is absent or keys are missing.

Config precedence (highest → lowest):
1. CLI flags (passed at invocation time)
2. Environment variables (``TRUSTPLANE_STORE``, ``TRUSTPLANE_MODE``, etc.)
3. ``.trustplane.toml``
4. Hardcoded defaults
"""

from __future__ import annotations

import logging
import os
import tomllib
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kailash.trust._locking import _safe_write_text

logger = logging.getLogger(__name__)

__all__ = ["TrustPlaneConfig", "CONFIG_FILENAME"]

CONFIG_FILENAME = ".trustplane.toml"

# Valid values for each setting
_VALID_BACKENDS = {"sqlite", "filesystem"}
_VALID_MODES = {"strict", "shadow"}
_VALID_SCHEDULES = {"daily", "weekly", "never"}
_VALID_OUTPUTS = {"stdout", "file"}
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


@dataclass
class TrustPlaneConfig:
    """Per-project configuration for trust-plane.

    Attributes:
        store_backend: Storage backend — ``"sqlite"`` (default) or ``"filesystem"``.
        sqlite_path: Path to SQLite database relative to project dir.
        enforcement_mode: Enforcement mode — ``"strict"`` (default) or ``"shadow"``.
        shadow_report_schedule: Shadow mode report schedule.
        shadow_report_output: Shadow mode report output target.
        shadow_report_file: Path to shadow report file (when output is ``"file"``).
        log_level: Logging level for trust-plane operations.
    """

    store_backend: str = "sqlite"
    sqlite_path: str = ".trust-plane/trust.db"
    enforcement_mode: str = "strict"
    shadow_report_schedule: str = "weekly"
    shadow_report_output: str = "stdout"
    shadow_report_file: str = ".trust-plane/shadow-report.md"
    log_level: str = "WARNING"

    def __post_init__(self) -> None:
        """Validate all settings."""
        if self.store_backend not in _VALID_BACKENDS:
            raise ValueError(
                f"Invalid store_backend: {self.store_backend!r}. "
                f"Must be one of: {', '.join(sorted(_VALID_BACKENDS))}"
            )
        if self.enforcement_mode not in _VALID_MODES:
            raise ValueError(
                f"Invalid enforcement_mode: {self.enforcement_mode!r}. "
                f"Must be one of: {', '.join(sorted(_VALID_MODES))}"
            )
        if self.shadow_report_schedule not in _VALID_SCHEDULES:
            raise ValueError(
                f"Invalid shadow_report_schedule: {self.shadow_report_schedule!r}. "
                f"Must be one of: {', '.join(sorted(_VALID_SCHEDULES))}"
            )
        if self.shadow_report_output not in _VALID_OUTPUTS:
            raise ValueError(
                f"Invalid shadow_report_output: {self.shadow_report_output!r}. "
                f"Must be one of: {', '.join(sorted(_VALID_OUTPUTS))}"
            )
        if self.log_level not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"Invalid log_level: {self.log_level!r}. "
                f"Must be one of: {', '.join(sorted(_VALID_LOG_LEVELS))}"
            )

    @classmethod
    def load(cls, project_dir: str | Path) -> TrustPlaneConfig:
        """Load configuration from ``.trustplane.toml`` in *project_dir*.

        If the file does not exist, returns all defaults.  Unknown keys
        produce a warning (forward compatibility) but do not raise.

        Environment variables override file values:
        - ``TRUSTPLANE_STORE`` → ``store_backend``
        - ``TRUSTPLANE_MODE`` → ``enforcement_mode``
        - ``TRUSTPLANE_LOG_LEVEL`` → ``log_level``

        Args:
            project_dir: Root directory of the trust-plane project.

        Returns:
            A TrustPlaneConfig with merged settings.
        """
        project_dir = Path(project_dir)
        config_path = project_dir / CONFIG_FILENAME

        kwargs: dict[str, Any] = {}

        # Layer 3: .trustplane.toml
        if config_path.is_file():
            # Use os.open with O_NOFOLLOW to prevent symlink attacks
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(str(config_path), flags)
            try:
                with os.fdopen(fd, "rb") as f:
                    data = tomllib.load(f)
            except Exception:
                # fd is consumed by fdopen even on error; re-raise
                raise

            _known_sections = {"store", "enforcement", "shadow", "logging"}
            for key in data:
                if key not in _known_sections:
                    warnings.warn(
                        f"Unknown section [{key}] in {CONFIG_FILENAME}. "
                        f"It will be ignored. Known sections: "
                        f"{', '.join(sorted(_known_sections))}",
                        stacklevel=2,
                    )

            store = data.get("store", {})
            if not isinstance(store, dict):
                raise ValueError(f"[store] must be a table, got {type(store).__name__}")
            _warn_unknown_keys(store, {"backend", "sqlite_path"}, "store")
            if "backend" in store:
                kwargs["store_backend"] = store["backend"]
            if "sqlite_path" in store:
                kwargs["sqlite_path"] = store["sqlite_path"]

            enforcement = data.get("enforcement", {})
            if not isinstance(enforcement, dict):
                raise ValueError(
                    f"[enforcement] must be a table, got {type(enforcement).__name__}"
                )
            _warn_unknown_keys(enforcement, {"mode"}, "enforcement")
            if "mode" in enforcement:
                kwargs["enforcement_mode"] = enforcement["mode"]

            shadow = data.get("shadow", {})
            if not isinstance(shadow, dict):
                raise ValueError(
                    f"[shadow] must be a table, got {type(shadow).__name__}"
                )
            _warn_unknown_keys(
                shadow, {"report_schedule", "report_output", "report_file"}, "shadow"
            )
            if "report_schedule" in shadow:
                kwargs["shadow_report_schedule"] = shadow["report_schedule"]
            if "report_output" in shadow:
                kwargs["shadow_report_output"] = shadow["report_output"]
            if "report_file" in shadow:
                kwargs["shadow_report_file"] = shadow["report_file"]

            logging_section = data.get("logging", {})
            if not isinstance(logging_section, dict):
                raise ValueError(
                    f"[logging] must be a table, got {type(logging_section).__name__}"
                )
            _warn_unknown_keys(logging_section, {"level"}, "logging")
            if "level" in logging_section:
                kwargs["log_level"] = logging_section["level"]

        # Layer 2: Environment variables override file
        env_store = os.environ.get("TRUSTPLANE_STORE")
        if env_store is not None:
            kwargs["store_backend"] = env_store

        env_mode = os.environ.get("TRUSTPLANE_MODE")
        if env_mode is not None:
            kwargs["enforcement_mode"] = env_mode

        env_log = os.environ.get("TRUSTPLANE_LOG_LEVEL")
        if env_log is not None:
            kwargs["log_level"] = env_log

        return cls(**kwargs)

    def to_toml(self) -> str:
        """Serialize configuration to a TOML string.

        The output includes comments documenting each setting and its
        valid values.

        Returns:
            A TOML-formatted string suitable for writing to
            ``.trustplane.toml``.
        """
        return _CONFIG_TEMPLATE.format(
            store_backend=self.store_backend,
            sqlite_path=self.sqlite_path,
            enforcement_mode=self.enforcement_mode,
            shadow_report_schedule=self.shadow_report_schedule,
            shadow_report_output=self.shadow_report_output,
            shadow_report_file=self.shadow_report_file,
            log_level=self.log_level,
        )

    def write(self, project_dir: str | Path) -> Path:
        """Write configuration to ``.trustplane.toml`` in *project_dir*.

        Args:
            project_dir: Root directory of the trust-plane project.

        Returns:
            The path to the written config file.
        """
        project_dir = Path(project_dir)
        config_path = project_dir / CONFIG_FILENAME
        _safe_write_text(config_path, self.to_toml())
        logger.info("Wrote config to %s", config_path)
        return config_path


def _warn_unknown_keys(
    section: dict[str, Any], known: set[str], section_name: str
) -> None:
    """Warn about unknown keys in a TOML section."""
    for key in section:
        if key not in known:
            warnings.warn(
                f"Unknown key '{key}' in [{section_name}] section of "
                f"{CONFIG_FILENAME}. It will be ignored.",
                stacklevel=4,
            )


_CONFIG_TEMPLATE = """\
# TrustPlane project configuration
# Generated by `attest init`. Edit freely.
#
# Config precedence (highest to lowest):
#   1. CLI flags
#   2. Environment variables (TRUSTPLANE_STORE, TRUSTPLANE_MODE, TRUSTPLANE_LOG_LEVEL)
#   3. This file (.trustplane.toml)
#   4. Hardcoded defaults

[store]
# Storage backend: "sqlite" (default) or "filesystem"
# SQLite is recommended for most users (single file, fast, handles high write volume).
# Filesystem stores each record as a JSON file (useful for git-committed audit trails).
backend = "{store_backend}"

# Path to SQLite database file (relative to project directory).
# Only used when backend = "sqlite".
sqlite_path = "{sqlite_path}"

[enforcement]
# Enforcement mode: "strict" (default) or "shadow"
# strict: constraint violations block the action
# shadow: constraint violations are logged but the action proceeds
mode = "{enforcement_mode}"

[shadow]
# Shadow mode reporting settings (only used when enforcement.mode = "shadow")

# How often to generate shadow reports: "daily", "weekly" (default), or "never"
report_schedule = "{shadow_report_schedule}"

# Where to write shadow reports: "stdout" (default) or "file"
report_output = "{shadow_report_output}"

# Path to shadow report file (only used when report_output = "file")
report_file = "{shadow_report_file}"

[logging]
# Logging level for trust-plane operations: "DEBUG", "INFO", "WARNING" (default), "ERROR"
level = "{log_level}"
"""
