# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP constraint templates.

Provides pre-built constraint templates for common agent archetypes.
Templates can be loaded by name and applied to agents via the CLI
or programmatic API.

Available templates:
    - governance: Organizational governance agent
    - finance: Financial operations agent
    - community: Community-facing agent
    - standards: Compliance/standards agent
    - audit: Audit trail agent
    - minimal: Bare minimum constraints
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Template directory (same as this module)
_TEMPLATE_DIR = Path(__file__).parent

# Built-in templates
TEMPLATES: Dict[str, Dict[str, Any]] = {
    "governance": {
        "name": "governance",
        "description": "Organizational governance agent — internal operations, read + approve actions",
        "constraints": {
            "scope": {
                "actions": ["read", "approve", "review", "report"],
                "visibility": "internal",
            },
            "financial": {
                "max_amount": 0,
                "currency": "USD",
                "commerce_types": [],
            },
            "temporal": {
                "hours": "business",
                "business_hours_start": "09:00",
                "business_hours_end": "17:00",
                "timezone": "UTC",
                "max_duration_days": 365,
            },
            "communication": {
                "allowed_endpoints": ["internal"],
                "rate_limit_per_minute": 100,
                "external_access": False,
            },
            "data_access": {
                "classification_max": "internal",
                "read_only": True,
            },
        },
    },
    "finance": {
        "name": "finance",
        "description": "Financial operations agent — trade execution, risk assessment",
        "constraints": {
            "scope": {
                "actions": [
                    "execute_trade",
                    "assess_risk",
                    "calculate_exposure",
                    "generate_report",
                    "approve_transaction",
                ],
                "visibility": "internal",
            },
            "financial": {
                "max_amount": 100000,
                "currency": "USD",
                "daily_limit": 100000,
                "commerce_types": ["purchase", "sale", "exchange"],
                "attribution_required": True,
            },
            "temporal": {
                "hours": "market",
                "market_hours_start": "09:30",
                "market_hours_end": "16:00",
                "timezone": "US/Eastern",
                "max_duration_days": 90,
            },
            "communication": {
                "allowed_endpoints": ["internal", "approved_exchanges"],
                "rate_limit_per_minute": 50,
                "external_access": True,
                "approved_domains": ["*.exchange.com", "*.trading.com"],
            },
            "data_access": {
                "classification_max": "confidential",
                "read_only": False,
            },
        },
    },
    "community": {
        "name": "community",
        "description": "Community-facing agent — content moderation, user support",
        "constraints": {
            "scope": {
                "actions": [
                    "moderate_content",
                    "respond_user",
                    "escalate",
                    "tag_content",
                    "send_notification",
                ],
                "visibility": "public",
            },
            "financial": {
                "max_amount": 0,
                "currency": "USD",
                "commerce_types": [],
            },
            "temporal": {
                "hours": "24/7",
                "max_duration_days": 180,
            },
            "communication": {
                "allowed_endpoints": ["public_channels", "internal"],
                "rate_limit_per_minute": 30,
                "external_access": True,
                "content_filter": True,
            },
            "data_access": {
                "classification_max": "public",
                "read_only": False,
                "pii_access": False,
            },
        },
    },
    "standards": {
        "name": "standards",
        "description": "Compliance/standards agent — audit review, compliance checking",
        "constraints": {
            "scope": {
                "actions": [
                    "review_audit",
                    "check_compliance",
                    "generate_report",
                    "flag_violation",
                    "read_policy",
                ],
                "visibility": "internal",
            },
            "financial": {
                "max_amount": 0,
                "currency": "USD",
                "commerce_types": [],
            },
            "temporal": {
                "hours": "business",
                "business_hours_start": "08:00",
                "business_hours_end": "18:00",
                "timezone": "UTC",
                "max_duration_days": 365,
            },
            "communication": {
                "allowed_endpoints": ["internal", "regulatory"],
                "rate_limit_per_minute": 60,
                "external_access": True,
                "approved_domains": ["*.regulator.gov"],
            },
            "data_access": {
                "classification_max": "confidential",
                "read_only": True,
            },
        },
    },
    "audit": {
        "name": "audit",
        "description": "Audit trail agent — read-only audit access",
        "constraints": {
            "scope": {
                "actions": ["read_audit", "query_logs", "verify_chain"],
                "visibility": "internal",
            },
            "financial": {
                "max_amount": 0,
                "currency": "USD",
                "commerce_types": [],
            },
            "temporal": {
                "hours": "24/7",
                "max_duration_days": 30,
            },
            "communication": {
                "allowed_endpoints": ["internal"],
                "rate_limit_per_minute": 200,
                "external_access": False,
            },
            "data_access": {
                "classification_max": "confidential",
                "read_only": True,
            },
        },
    },
    "minimal": {
        "name": "minimal",
        "description": "Bare minimum constraints — single action, short-lived",
        "constraints": {
            "scope": {
                "actions": ["__SPECIFY__"],
                "visibility": "internal",
            },
            "financial": {
                "max_amount": 0,
                "currency": "USD",
                "commerce_types": [],
            },
            "temporal": {
                "hours": "24/7",
                "max_duration_days": 1,
            },
            "communication": {
                "allowed_endpoints": [],
                "rate_limit_per_minute": 10,
                "external_access": False,
            },
            "data_access": {
                "classification_max": "internal",
                "read_only": True,
            },
        },
    },
}


def get_template(name: str) -> Dict[str, Any]:
    """Load a constraint template by name.

    Args:
        name: Template name (governance, finance, community, standards, audit, minimal)

    Returns:
        Template configuration dict

    Raises:
        ValueError: If template name is unknown
    """
    template = TEMPLATES.get(name)
    if template is None:
        available = ", ".join(sorted(TEMPLATES.keys()))
        raise ValueError(f"Unknown template '{name}'. Available: {available}")
    # Return a deep copy to prevent mutation
    return json.loads(json.dumps(template))


def list_templates() -> List[Dict[str, str]]:
    """List available constraint templates.

    Returns:
        List of dicts with 'name' and 'description' for each template
    """
    return [
        {"name": t["name"], "description": t["description"]} for t in TEMPLATES.values()
    ]


def get_template_names() -> List[str]:
    """Get available template names.

    Returns:
        Sorted list of template names
    """
    return sorted(TEMPLATES.keys())


def customize_template(
    name: str,
    overrides: Dict[str, Any],
) -> Dict[str, Any]:
    """Load a template and apply customizations.

    Args:
        name: Base template name
        overrides: Dict of constraint overrides to merge

    Returns:
        Customized template configuration
    """
    template = get_template(name)
    constraints = template["constraints"]

    for dimension, values in overrides.items():
        if dimension in constraints:
            if isinstance(values, dict) and isinstance(constraints[dimension], dict):
                constraints[dimension].update(values)
            else:
                constraints[dimension] = values
        else:
            constraints[dimension] = values

    return template


def save_template_json(name: str, path: Optional[Path] = None) -> Path:
    """Save a template as a JSON file.

    Args:
        name: Template name
        path: Output path (defaults to current directory)

    Returns:
        Path to the saved file
    """
    template = get_template(name)
    if path is None:
        path = Path(f"{name}-constraints.json")

    path.write_text(json.dumps(template, indent=2))
    return path


def load_template_file(path: Path) -> Dict[str, Any]:
    """Load a constraint template from a JSON or YAML file.

    Args:
        path: Path to template file (.json or .yaml/.yml)

    Returns:
        Template configuration dict

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If format is unsupported
    """
    if not path.exists():
        raise FileNotFoundError(f"Template file not found: {path}")

    suffix = path.suffix.lower()

    if suffix == ".json":
        return json.loads(path.read_text())
    elif suffix in (".yaml", ".yml"):
        try:
            import yaml

            return yaml.safe_load(path.read_text())
        except ImportError:
            raise ImportError(
                "PyYAML required for YAML templates. Install with: pip install pyyaml"
            )
    else:
        raise ValueError(
            f"Unsupported template format: {suffix}. Use .json or .yaml/.yml"
        )


__all__ = [
    "TEMPLATES",
    "get_template",
    "list_templates",
    "get_template_names",
    "customize_template",
    "save_template_json",
    "load_template_file",
]
