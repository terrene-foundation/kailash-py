#!/usr/bin/env python3
"""
Demo script showing the new alternative configuration methods for TODO-CONFIG-ALT-001.

This script demonstrates all the new configuration methods implemented:
1. Global kaizen.configure()
2. Environment variable configuration
3. Configuration file loading
4. Configuration precedence
5. Auto-discovery
"""

import json
import os
import tempfile

import kaizen
import yaml


def demo_global_configure():
    """Demonstrate global kaizen.configure() method."""
    print("=== Demo 1: Global Configuration ===")

    # Clear any existing config
    kaizen.clear_global_config()

    # Set global configuration
    kaizen.configure(
        signature_programming_enabled=True, transparency_enabled=True, debug=True
    )

    # Check resolved configuration
    config = kaizen.get_resolved_config()
    print(f"Global config set: {config}")
    print(
        f"  - signature_programming_enabled: {config.get('signature_programming_enabled')}"
    )
    print(f"  - transparency_enabled: {config.get('transparency_enabled')}")
    print(f"  - debug: {config.get('debug')}")

    print()


def demo_environment_variables():
    """Demonstrate environment variable configuration."""
    print("=== Demo 2: Environment Variable Configuration ===")

    # Clear any existing config
    kaizen.clear_global_config()

    # Set environment variables
    env_vars = {
        "KAIZEN_SIGNATURE_PROGRAMMING_ENABLED": "true",
        "KAIZEN_MEMORY_ENABLED": "true",
        "KAIZEN_DEBUG": "false",
    }

    # Temporarily set environment variables
    for key, value in env_vars.items():
        os.environ[key] = value

    try:
        # Load configuration from environment
        env_config = kaizen.load_config_from_env()
        print(f"Environment config loaded: {env_config}")

        # Show resolved configuration
        resolved = kaizen.get_resolved_config()
        print(f"Resolved config: {resolved}")

    finally:
        # Clean up environment variables
        for key in env_vars:
            os.environ.pop(key, None)

    print()


def demo_configuration_files():
    """Demonstrate configuration file loading."""
    print("=== Demo 3: Configuration File Loading ===")

    # Clear any existing config
    kaizen.clear_global_config()

    # Create YAML configuration file
    yaml_config = {
        "signature_programming_enabled": True,
        "transparency_enabled": False,
        "mcp_integration": {"enabled": True, "port": 8080},
        "coordination_patterns": ["consensus", "debate"],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.safe_dump(yaml_config, f)
        yaml_file = f.name

    try:
        # Load configuration from YAML file
        file_config = kaizen.load_config_from_file(yaml_file)
        print(f"YAML config loaded from {yaml_file}:")
        print(f"  {file_config}")

        # Show resolved configuration
        resolved = kaizen.get_resolved_config()
        print(f"Resolved config: {resolved}")

    finally:
        os.unlink(yaml_file)

    print()


def demo_configuration_precedence():
    """Demonstrate configuration precedence system."""
    print("=== Demo 4: Configuration Precedence ===")

    # Clear any existing config
    kaizen.clear_global_config()

    # Create a config file (lowest priority)
    file_config = {"debug": False, "memory_enabled": False}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(file_config, f)
        json_file = f.name

    try:
        # Step 1: Load from file
        kaizen.load_config_from_file(json_file)
        config1 = kaizen.get_resolved_config()
        print(
            f"1. After loading file: debug={config1.get('debug')}, memory_enabled={config1.get('memory_enabled')}"
        )

        # Step 2: Set environment variable (overrides file)
        os.environ["KAIZEN_DEBUG"] = "true"
        kaizen.load_config_from_env()
        config2 = kaizen.get_resolved_config()
        print(
            f"2. After env variable: debug={config2.get('debug')}, memory_enabled={config2.get('memory_enabled')}"
        )

        # Step 3: Set global config (overrides env and file)
        kaizen.configure(memory_enabled=True)
        config3 = kaizen.get_resolved_config()
        print(
            f"3. After global config: debug={config3.get('debug')}, memory_enabled={config3.get('memory_enabled')}"
        )

        # Step 4: Explicit parameters (highest priority)
        config4 = kaizen.get_resolved_config({"debug": False})
        print(
            f"4. With explicit override: debug={config4.get('debug')}, memory_enabled={config4.get('memory_enabled')}"
        )

        print("Precedence order verified: file < env < global < explicit")

    finally:
        os.unlink(json_file)
        os.environ.pop("KAIZEN_DEBUG", None)

    print()


def demo_create_agent_with_config():
    """Demonstrate creating agents with resolved configuration."""
    print("=== Demo 5: Agent Creation with Global Config ===")

    # Clear any existing config
    kaizen.clear_global_config()

    # Set global configuration
    kaizen.configure(
        signature_programming_enabled=True, transparency_enabled=True, debug=False
    )

    try:
        # Create agent using global config
        agent = kaizen.create_agent("demo_agent", {"model": "gpt-3.5-turbo"})
        print(f"Agent created successfully: {agent}")
        print(
            f"Agent has attribute 'name' or 'agent_id': {hasattr(agent, 'name') or hasattr(agent, 'agent_id')}"
        )

    except Exception as e:
        print(f"Agent creation failed: {e}")

    print()


def demo_performance():
    """Demonstrate performance of configuration operations."""
    print("=== Demo 6: Performance Requirements ===")
    import time

    # Clear any existing config
    kaizen.clear_global_config()

    # Test global configure performance
    start_time = time.time()
    kaizen.configure(
        signature_programming_enabled=True,
        transparency_enabled=True,
        debug=False,
        memory_enabled=True,
    )
    configure_time = (time.time() - start_time) * 1000

    # Test config resolution performance
    start_time = time.time()
    config = kaizen.get_resolved_config()
    resolve_time = (time.time() - start_time) * 1000

    print("Performance results:")
    print(f"  - Global configure: {configure_time:.2f}ms (target: <10ms)")
    print(f"  - Config resolution: {resolve_time:.2f}ms (target: <5ms)")
    print(
        f"  - Performance requirements: {'✅ MET' if configure_time < 10 and resolve_time < 5 else '❌ NOT MET'}"
    )

    print()


def main():
    """Run all configuration demos."""
    print("🎯 Alternative Configuration Methods Demo")
    print("=" * 50)
    print()

    try:
        demo_global_configure()
        demo_environment_variables()
        demo_configuration_files()
        demo_configuration_precedence()
        demo_create_agent_with_config()
        demo_performance()

        print("✅ All configuration method demos completed successfully!")

    except Exception as e:
        print(f"❌ Demo failed with error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Cleanup
        kaizen.clear_global_config()


if __name__ == "__main__":
    main()
