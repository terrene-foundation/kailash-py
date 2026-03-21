# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""HTML templates for the TrustPlane web dashboard.

Uses Python string.Template for safe variable substitution
without external dependencies (no Jinja2).
"""

from __future__ import annotations

import logging
from pathlib import Path
from string import Template

from kailash.trust._locking import safe_read_text

logger = logging.getLogger(__name__)

__all__ = ["load_template", "render_template"]

_TEMPLATE_DIR = Path(__file__).parent


def load_template(name: str) -> Template:
    """Load a template file by name (without .html extension).

    Args:
        name: Template name (e.g., 'base', 'overview').

    Returns:
        A string.Template instance.

    Raises:
        FileNotFoundError: If the template file does not exist.
    """
    path = _TEMPLATE_DIR / f"{name}.html"
    if not path.exists():
        raise FileNotFoundError(f"Template not found: {path}")
    return Template(safe_read_text(path))


def render_template(name: str, **kwargs: str) -> str:
    """Load and render a template with the given variables.

    Uses safe_substitute so missing variables produce no errors
    (they remain as $variable_name in the output).

    Args:
        name: Template name (e.g., 'overview').
        **kwargs: Template variables.

    Returns:
        Rendered HTML string.
    """
    tmpl = load_template(name)
    return tmpl.safe_substitute(**kwargs)
