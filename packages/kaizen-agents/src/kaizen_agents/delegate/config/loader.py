"""Three-level configuration loader for kz CLI.

Loading order (later overrides earlier):
1. Built-in defaults
2. User-level config: ``~/.kz/config.toml``
3. Project-level config: ``<project>/.kz/config.toml``
4. Environment variables (``KZ_*``)

The result is a frozen :class:`KzConfig` dataclass.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from kaizen_agents.delegate.config.effort import EffortLevel


# ---------------------------------------------------------------------------
# .kzignore
# ---------------------------------------------------------------------------


def load_kzignore(project_root: Path) -> list[str]:
    """Load ``.kzignore`` patterns from a project root.

    Returns a list of gitignore-style patterns. Empty list if the file
    does not exist.
    """
    ignore_path = project_root / ".kzignore"
    if not ignore_path.is_file():
        return []

    patterns: list[str] = []
    for line in ignore_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            patterns.append(stripped)
    return patterns


def matches_kzignore(filepath: str | Path, patterns: list[str]) -> bool:
    """Check whether *filepath* matches any ``.kzignore`` pattern.

    Supports a practical subset of gitignore syntax:
    - ``*`` matches anything except ``/``
    - ``**`` matches any number of directories
    - Leading ``/`` anchors to the root
    - Trailing ``/`` matches directories only (ignored here — caller decides)
    - ``!`` negation patterns invert a previous match
    """
    filepath_str = str(filepath).replace("\\", "/")
    matched = False

    for pattern in patterns:
        negate = False
        p = pattern
        if p.startswith("!"):
            negate = True
            p = p[1:]

        regex = _pattern_to_regex(p)
        if re.search(regex, filepath_str):
            matched = not negate

    return matched


def _pattern_to_regex(pattern: str) -> str:
    """Convert a single gitignore-style pattern to a regex string."""
    anchored = pattern.startswith("/")
    if anchored:
        pattern = pattern[1:]

    # Strip trailing slash (directory indicator — we ignore the distinction)
    pattern = pattern.rstrip("/")

    # Escape regex special chars except our glob tokens
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                # ** — match across directories
                if i + 2 < len(pattern) and pattern[i + 2] == "/":
                    parts.append("(.*/)?")
                    i += 3
                    continue
                else:
                    parts.append(".*")
                    i += 2
                    continue
            else:
                parts.append("[^/]*")
                i += 1
        elif ch == "?":
            parts.append("[^/]")
            i += 1
        elif ch in r"\.+^${}()|[]":
            parts.append("\\" + ch)
            i += 1
        else:
            parts.append(ch)
            i += 1

    body = "".join(parts)
    if anchored:
        return "^" + body + "(/|$)"
    else:
        return "(^|/)" + body + "(/|$)"


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------


@dataclass
class KzConfig:
    """Resolved kz configuration."""

    # LLM settings
    model: str = ""
    provider: str = "openai"
    effort_level: EffortLevel = EffortLevel.MEDIUM

    # Generation settings
    max_turns: int = 50
    max_tokens: int = 16384
    temperature: float = 0.4

    # Tool permissions
    tools_allow: list[str] = field(default_factory=list)
    tools_deny: list[str] = field(default_factory=list)

    # .kzignore patterns (populated after loading)
    ignore_patterns: list[str] = field(default_factory=list)

    # Paths that were loaded (for diagnostics)
    loaded_from: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Deep-merge helper
# ---------------------------------------------------------------------------


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into *base* (new dict, no mutation)."""
    merged = dict(base)
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


# ---------------------------------------------------------------------------
# TOML → flat config
# ---------------------------------------------------------------------------

# Map of TOML paths to KzConfig field names.
_TOML_KEY_MAP: dict[str, str] = {
    "model": "model",
    "provider": "provider",
    "effort_level": "effort_level",
    "max_turns": "max_turns",
    "max_tokens": "max_tokens",
    "temperature": "temperature",
    "tools.allow": "tools_allow",
    "tools.deny": "tools_deny",
}


def _flatten_toml(data: dict[str, Any]) -> dict[str, Any]:
    """Extract known config keys from a (possibly nested) TOML dict."""
    flat: dict[str, Any] = {}

    for toml_path, field_name in _TOML_KEY_MAP.items():
        parts = toml_path.split(".")
        node: Any = data
        for part in parts:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                node = None
                break
        if node is not None:
            flat[field_name] = node

    return flat


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------

_ENV_MAP: dict[str, str] = {
    "KZ_MODEL": "model",
    "KZ_PROVIDER": "provider",
    "KZ_EFFORT_LEVEL": "effort_level",
    "KZ_MAX_TURNS": "max_turns",
    "KZ_MAX_TOKENS": "max_tokens",
    "KZ_TEMPERATURE": "temperature",
}


def _env_overrides() -> dict[str, Any]:
    """Read ``KZ_*`` environment variables and return matching config values."""
    overrides: dict[str, Any] = {}
    for env_key, field_name in _ENV_MAP.items():
        val = os.environ.get(env_key)
        if val is not None:
            overrides[field_name] = val
    return overrides


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------

_FIELD_TYPES: dict[str, type] = {
    "model": str,
    "provider": str,
    "max_turns": int,
    "max_tokens": int,
    "temperature": float,
}


def _coerce(key: str, value: Any) -> Any:
    """Coerce a raw config value to the expected Python type."""
    if key == "effort_level":
        if isinstance(value, EffortLevel):
            return value
        return EffortLevel(str(value).lower())

    target = _FIELD_TYPES.get(key)
    if target is None:
        return value

    if target is int:
        return int(value)
    if target is float:
        return float(value)
    if target is str:
        return str(value)
    return value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(
    project_root: Path | None = None,
    *,
    user_home: Path | None = None,
) -> KzConfig:
    """Load configuration with three-level merging.

    Parameters
    ----------
    project_root:
        Path to the project directory (contains ``.kz/``).  Defaults to cwd.
    user_home:
        Override for ``~`` (useful for testing).
    """
    if project_root is None:
        project_root = Path.cwd()
    if user_home is None:
        user_home = Path.home()

    layers: list[dict[str, Any]] = []
    loaded_paths: list[str] = []

    # Layer 1: user-level config
    user_config_path = user_home / ".kz" / "config.toml"
    if user_config_path.is_file():
        raw = tomllib.loads(user_config_path.read_text(encoding="utf-8"))
        layers.append(_flatten_toml(raw))
        loaded_paths.append(str(user_config_path))

    # Layer 2: project-level config (overrides user)
    project_config_path = project_root / ".kz" / "config.toml"
    if project_config_path.is_file():
        raw = tomllib.loads(project_config_path.read_text(encoding="utf-8"))
        layers.append(_flatten_toml(raw))
        loaded_paths.append(str(project_config_path))

    # Layer 3: environment variables (override everything)
    env = _env_overrides()
    if env:
        layers.append(env)
        loaded_paths.append("env")

    # Merge layers into defaults
    merged: dict[str, Any] = {}
    for layer in layers:
        merged = _deep_merge(merged, layer)

    # Coerce values
    coerced: dict[str, Any] = {}
    for key, val in merged.items():
        coerced[key] = _coerce(key, val)

    # Load .kzignore
    ignore = load_kzignore(project_root)

    return KzConfig(
        **coerced,
        ignore_patterns=ignore,
        loaded_from=loaded_paths,
    )
