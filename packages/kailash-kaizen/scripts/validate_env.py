#!/usr/bin/env python3
"""Environment configuration validation script.

Validates that environment configuration files have all required variables
and follow security best practices.
"""
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Required variables for each environment
REQUIRED_VARS = {
    "all": [
        "KAIZEN_ENV",
        "LOG_LEVEL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ],
    "dev": [],  # Dev can be more lenient
    "staging": [
        "DATABASE_URL",
        "REDIS_URL",
    ],
    "prod": [
        "DATABASE_URL",
        "REDIS_URL",
        "SENTRY_DSN",
    ],
}


def load_env_file(env_file: Path) -> Dict[str, str]:
    """Load environment file into a dictionary."""
    env_vars = {}

    with open(env_file) as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Parse key=value
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()

    return env_vars


def validate_required_vars(
    env_vars: Dict[str, str], env_name: str
) -> Tuple[bool, List[str]]:
    """Validate that all required variables are present."""
    missing = []

    # Check common required vars
    for var in REQUIRED_VARS["all"]:
        if var not in env_vars:
            missing.append(var)

    # Check environment-specific vars
    for var in REQUIRED_VARS.get(env_name, []):
        if var not in env_vars:
            missing.append(var)

    return len(missing) == 0, missing


def check_secrets_security(
    env_vars: Dict[str, str], env_name: str
) -> Tuple[bool, List[str]]:
    """Check that production configs don't contain real secrets."""
    issues = []

    # Only check staging and prod
    if env_name not in ["staging", "prod"]:
        return True, []

    for key, value in env_vars.items():
        # Check for placeholder patterns (good)
        if "your-" in value.lower() or "${" in value:
            continue

        # Check for potentially real secrets (bad)
        if key.endswith("_KEY") or key.endswith("_DSN"):
            # If it's not a placeholder and not an env var reference, it might be real
            if not value.startswith("${") and len(value) > 10:
                issues.append(
                    f"{key} may contain a real secret (not using placeholder)"
                )

    return len(issues) == 0, issues


def validate_env_config(env_file: Path, env_name: str) -> bool:
    """Validate a single environment configuration file."""
    print(f"\nValidating {env_name} environment configuration...")
    print(f"File: {env_file}")

    # Load environment file
    try:
        env_vars = load_env_file(env_file)
        print(f"Loaded {len(env_vars)} environment variables")
    except Exception as e:
        print(f"ERROR: Failed to load {env_file}: {e}")
        return False

    # Validate required variables
    has_required, missing = validate_required_vars(env_vars, env_name)
    if not has_required:
        print(f"ERROR: Missing required variables: {', '.join(missing)}")
        return False
    else:
        print("✓ All required variables present")

    # Check secrets security
    secure, issues = check_secrets_security(env_vars, env_name)
    if not secure:
        print("WARNING: Security issues found:")
        for issue in issues:
            print(f"  - {issue}")
        if env_name == "prod":
            return False  # Fail on production security issues
    else:
        print("✓ Security checks passed")

    print(f"\n{env_name.upper()} configuration is VALID")
    return True


def main():
    """Main validation entry point."""
    parser = argparse.ArgumentParser(
        description="Validate Kaizen environment configuration"
    )
    parser.add_argument(
        "--env",
        choices=["dev", "staging", "prod"],
        required=True,
        help="Environment to validate",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path(__file__).parent.parent / "config",
        help="Configuration directory (default: ../config)",
    )

    args = parser.parse_args()

    # Get environment file
    env_file = args.config_dir / f"{args.env}.env"

    if not env_file.exists():
        print(f"ERROR: Configuration file not found: {env_file}")
        return 1

    # Validate
    if validate_env_config(env_file, args.env):
        print("\n✅ Validation successful!")
        return 0
    else:
        print("\n❌ Validation failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
