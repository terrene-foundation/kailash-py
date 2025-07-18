#!/usr/bin/env python3
"""
DataFlow Progressive Disclosure Configuration Demo

Demonstrates the progressive configuration system that allows users to start with
zero configuration and progressively enable more advanced features as needed.

Features:
- Zero-config defaults (just works)
- Progressive complexity levels
- Feature-driven configuration
- Environment-aware settings
- Enterprise scalability
"""

import os
import sys
from pathlib import Path

# Add the DataFlow app to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from dataflow.configuration import (
    ConfigurationLevel,
    FeatureFlag,
    ProgressiveConfiguration,
    basic_config,
    create_configuration,
    enterprise_config,
    production_config,
    zero_config,
)


def demonstrate_zero_config():
    """Demonstrate zero-configuration setup."""
    print("🚀 Step 1: Zero Configuration")
    print("-" * 30)

    print("📋 Creating zero-config DataFlow instance:")
    print("  config = zero_config()  # That's it!")

    config = zero_config()

    print("\n✅ Configuration created with smart defaults:")
    print(f"  Level: {config.level.value}")
    print(f"  Environment: {config.environment}")
    print(f"  Database URL: {config.get_database_url()}")
    print(f"  Pool Size: {config.database.pool_size}")
    print(f"  SQL Logging: {'Enabled' if config.database.echo else 'Disabled'}")
    print(f"  Caching: {'Enabled' if config.cache.enabled else 'Disabled'}")

    print(f"\n🎯 Enabled Features ({len(config.enabled_features)}):")
    for feature in sorted(config.enabled_features, key=lambda f: f.value):
        print(f"  ✅ {feature.value.replace('_', ' ').title()}")

    return config


def demonstrate_basic_config():
    """Demonstrate basic configuration."""
    print("\n🔧 Step 2: Basic Configuration")
    print("-" * 30)

    print("📋 Upgrading to basic configuration:")
    print("  config = basic_config()  # Enables caching and monitoring")

    config = basic_config()

    print("\n✅ Basic configuration features:")
    print(f"  Level: {config.level.value}")
    print(f"  Pool Size: {config.database.pool_size} (increased)")
    print(f"  Slow Query Threshold: {config.database.slow_query_threshold}ms")
    print(f"  Cache Backend: {config.cache.backend}")
    print(f"  Cache Max Size: {config.cache.max_size} items")
    print(
        f"  Performance Metrics: {'Enabled' if config.monitoring.performance_metrics else 'Disabled'}"
    )
    print(
        f"  Slow Query Logging: {'Enabled' if config.monitoring.slow_query_logging else 'Disabled'}"
    )

    print("\n🎯 New Features Enabled:")
    basic_features = {
        FeatureFlag.CACHING: "In-memory caching for faster queries",
        FeatureFlag.MONITORING: "Performance metrics and slow query logging",
    }

    for feature, description in basic_features.items():
        if feature in config.enabled_features:
            print(f"  ✅ {feature.value.replace('_', ' ').title()}: {description}")

    return config


def demonstrate_production_config():
    """Demonstrate production-ready configuration."""
    print("\n🏭 Step 3: Production Configuration")
    print("-" * 35)

    print("📋 Setting up production configuration:")
    print(
        "  config = production_config()  # Intermediate level with production features"
    )

    config = production_config()

    print("\n✅ Production-ready features:")
    print(f"  Level: {config.level.value}")
    print(f"  Pool Size: {config.database.pool_size} (production-ready)")
    print(f"  Pool Max Overflow: {config.database.pool_max_overflow}")
    print(f"  Pool Recycle: {config.database.pool_recycle}s")
    print(f"  Cache Backend: {config.cache.backend}")
    print(f"  Cache TTL: {config.cache.ttl}s")
    print(
        f"  Health Checks: {'Enabled' if config.monitoring.health_checks else 'Disabled'}"
    )
    print(f"  Alerting: {'Enabled' if config.monitoring.alerting else 'Disabled'}")
    print(
        f"  Prometheus: {'Enabled' if config.monitoring.prometheus_enabled else 'Disabled'}"
    )
    print(f"  OAuth2: {'Enabled' if config.security.oauth2_enabled else 'Disabled'}")
    print(f"  RBAC: {'Enabled' if config.security.rbac_enabled else 'Disabled'}")

    print(f"\n🎯 Production Features ({len(config.enabled_features)}):")
    production_features = [
        FeatureFlag.QUERY_OPTIMIZATION,
        FeatureFlag.INDEX_RECOMMENDATIONS,
        FeatureFlag.CACHING,
        FeatureFlag.MONITORING,
    ]

    for feature in production_features:
        if feature in config.enabled_features:
            print(f"  ✅ {feature.value.replace('_', ' ').title()}")

    return config


def demonstrate_enterprise_config():
    """Demonstrate enterprise configuration."""
    print("\n🏢 Step 4: Enterprise Configuration")
    print("-" * 33)

    print("📋 Setting up enterprise configuration:")
    print("  config = enterprise_config()  # All features enabled")

    config = enterprise_config()

    print("\n✅ Enterprise features:")
    print(f"  Level: {config.level.value}")
    print(f"  Pool Size: {config.database.pool_size} (enterprise-scale)")
    print(f"  Pool Max Overflow: {config.database.pool_max_overflow}")
    print(
        f"  Compression: {'Enabled' if config.database.compression_enabled else 'Disabled'}"
    )
    print(
        f"  Multi-Region Cache: {'Enabled' if config.cache.multi_region else 'Disabled'}"
    )
    print(
        f"  Cache Encryption: {'Enabled' if config.cache.encryption_enabled else 'Disabled'}"
    )
    print(
        f"  SLA Monitoring: {'Enabled' if config.monitoring.sla_monitoring else 'Disabled'}"
    )
    print(
        f"  Compliance Reporting: {'Enabled' if config.monitoring.compliance_reporting else 'Disabled'}"
    )
    print(
        f"  Audit Trail: {'Enabled' if config.monitoring.audit_trail else 'Disabled'}"
    )
    print(f"  Compliance Mode: {config.security.compliance_mode}")
    print(
        f"  Threat Detection: {'Enabled' if config.security.advanced_threat_detection else 'Disabled'}"
    )
    print(
        f"  Zero Trust: {'Enabled' if config.security.zero_trust_network else 'Disabled'}"
    )

    print(f"\n🎯 Enterprise Features ({len(config.enabled_features)}):")
    enterprise_features = [
        FeatureFlag.DISTRIBUTED_TRANSACTIONS,
        FeatureFlag.READ_REPLICAS,
        FeatureFlag.SHARDING,
        FeatureFlag.COMPLIANCE,
        FeatureFlag.ADVANCED_SECURITY,
    ]

    for feature in enterprise_features:
        if feature in config.enabled_features:
            print(f"  ✅ {feature.value.replace('_', ' ').title()}")

    return config


def demonstrate_custom_configuration():
    """Demonstrate custom feature-driven configuration."""
    print("\n🎯 Step 5: Custom Feature Configuration")
    print("-" * 40)

    print("📋 Creating custom configuration with specific features:")
    print("  config = create_configuration(")
    print("      level='basic',")
    print("      features=['multi_tenant', 'encryption', 'audit_logging']")
    print("  )")

    config = create_configuration(
        level="basic", features=["multi_tenant", "encryption", "audit_logging"]
    )

    print("\n✅ Custom configuration:")
    print(f"  Base Level: {config.level.value}")
    print("  Custom Features: 3 additional")

    custom_features = [
        FeatureFlag.MULTI_TENANT,
        FeatureFlag.ENCRYPTION,
        FeatureFlag.AUDIT_LOGGING,
    ]

    print("\n🎯 Custom Features Enabled:")
    for feature in custom_features:
        if feature in config.enabled_features:
            print(f"  ✅ {feature.value.replace('_', ' ').title()}")

    # Show feature-specific configuration
    print("\n🔧 Feature-Specific Configuration:")
    if config.is_feature_enabled(FeatureFlag.ENCRYPTION):
        print(
            f"  🔒 Field-level encryption: {'Enabled' if config.security.field_level_encryption else 'Disabled'}"
        )
    if config.is_feature_enabled(FeatureFlag.AUDIT_LOGGING):
        print(
            f"  📝 Audit trail: {'Enabled' if config.monitoring.audit_trail else 'Disabled'}"
        )

    return config


def demonstrate_dynamic_upgrades():
    """Demonstrate dynamic configuration upgrades."""
    print("\n⬆️ Step 6: Dynamic Configuration Upgrades")
    print("-" * 42)

    print("📋 Starting with zero-config and upgrading dynamically:")

    # Start with zero config
    config = zero_config()
    print("\n🚀 Initial Configuration:")
    print(f"  Level: {config.level.value}")
    print(f"  Features: {len(config.enabled_features)}")
    print(f"  Pool Size: {config.database.pool_size}")

    # Upgrade to intermediate
    print("\n⬆️ Upgrading to intermediate:")
    config.upgrade_level("intermediate")
    print(f"  Level: {config.level.value}")
    print(f"  Features: {len(config.enabled_features)} (increased)")
    print(f"  Pool Size: {config.database.pool_size} (increased)")
    print(
        f"  Health Checks: {'Enabled' if config.monitoring.health_checks else 'Disabled'}"
    )

    # Add specific feature
    print("\n➕ Adding encryption feature:")
    config.enable_feature("encryption")
    print(f"  Encryption enabled: {config.is_feature_enabled(FeatureFlag.ENCRYPTION)}")
    print(
        f"  Field-level encryption: {'Enabled' if config.security.field_level_encryption else 'Disabled'}"
    )

    # Final upgrade to enterprise
    print("\n🏢 Final upgrade to enterprise:")
    config.upgrade_level("enterprise")
    print(f"  Level: {config.level.value}")
    print(f"  Features: {len(config.enabled_features)} (maximum)")
    print(f"  Pool Size: {config.database.pool_size} (enterprise-scale)")
    print(f"  Compliance Mode: {config.security.compliance_mode}")

    return config


def demonstrate_environment_awareness():
    """Demonstrate environment-aware configuration."""
    print("\n🌍 Step 7: Environment-Aware Configuration")
    print("-" * 42)

    print("📋 Testing configuration across environments:")

    # Simulate different environments
    environments = [
        ("development", {"ENVIRONMENT": "development"}),
        ("testing", {"CI": "true"}),
        ("production", {}),  # Default environment
    ]

    for env_name, env_vars in environments:
        print(f"\n🏷️ {env_name.title()} Environment:")

        # Temporarily set environment variables
        original_env = {}
        for key, value in env_vars.items():
            original_env[key] = os.environ.get(key)
            os.environ[key] = value

        # Clear other environment indicators
        if env_name == "production":
            for key in ["ENVIRONMENT", "CI", "DEBUG"]:
                if key in os.environ:
                    del os.environ[key]

        config = basic_config()

        print(f"  Detected Environment: {config.environment}")
        print(f"  SQL Logging: {'Enabled' if config.database.echo else 'Disabled'}")
        print(f"  Pool Size: {config.database.pool_size}")
        print(f"  Log Level: {config.monitoring.log_level}")
        print(
            f"  Connection Encryption: {'Enabled' if config.security.connection_encryption else 'Disabled'}"
        )

        # Restore original environment
        for key, value in original_env.items():
            if value is None:
                if key in os.environ:
                    del os.environ[key]
            else:
                os.environ[key] = value

    return config


def demonstrate_configuration_documentation():
    """Demonstrate configuration documentation generation."""
    print("\n📚 Step 8: Configuration Documentation")
    print("-" * 39)

    print("📋 Generating user-friendly documentation:")

    config = production_config()
    doc = config.generate_documentation()

    print("\n📖 Generated Documentation:")
    print("-" * 50)

    # Show first part of documentation
    lines = doc.split("\n")
    for line in lines[:25]:  # Show first 25 lines
        print(line)

    if len(lines) > 25:
        print(f"... and {len(lines) - 25} more lines")

    print("-" * 50)

    # Show configuration summary
    summary = config.get_configuration_summary()
    print("\n📊 Configuration Summary:")
    print(f"  Level: {summary['level']}")
    print(f"  Environment: {summary['environment']}")
    print(f"  Features: {len(summary['enabled_features'])}")
    print(f"  Database Pool: {summary['database']['pool_size']}")
    print(
        f"  Cache: {summary['cache']['backend'] if summary['cache']['enabled'] else 'Disabled'}"
    )

    return config


def demonstrate_real_world_scenarios():
    """Demonstrate real-world usage scenarios."""
    print("\n🌟 Step 9: Real-World Scenarios")
    print("-" * 32)

    scenarios = [
        {
            "name": "Startup MVP",
            "description": "Quick prototype with minimal setup",
            "config": lambda: zero_config(),
            "benefits": ["Zero configuration", "SQLite database", "Ready to use"],
        },
        {
            "name": "Growing SaaS",
            "description": "Multi-tenant app with monitoring",
            "config": lambda: create_configuration(
                "intermediate", features=["multi_tenant"]
            ),
            "benefits": ["Production database", "Multi-tenancy", "Health monitoring"],
        },
        {
            "name": "Enterprise App",
            "description": "Full compliance and security",
            "config": lambda: enterprise_config(),
            "benefits": ["SOC2 compliance", "Advanced security", "Distributed scaling"],
        },
        {
            "name": "Data Science",
            "description": "Analytics with caching",
            "config": lambda: create_configuration(
                "basic", features=["caching", "monitoring"]
            ),
            "benefits": ["Query caching", "Performance metrics", "Simple setup"],
        },
    ]

    for scenario in scenarios:
        print(f"\n📋 {scenario['name']}: {scenario['description']}")
        config = scenario["config"]()

        print(f"  Configuration Level: {config.level.value}")
        print(f"  Features: {len(config.enabled_features)}")
        print("  Benefits:")
        for benefit in scenario["benefits"]:
            print(f"    ✅ {benefit}")


def main():
    """Run the complete progressive disclosure configuration demonstration."""
    try:
        print("🎯 DataFlow Progressive Disclosure Configuration Demo")
        print("=" * 65)
        print()
        print("This demo showcases the progressive configuration system that allows")
        print("users to start with zero configuration and progressively enable")
        print("more advanced features as their needs grow.")
        print()

        # Run demonstration steps
        demonstrate_zero_config()
        demonstrate_basic_config()
        demonstrate_production_config()
        demonstrate_enterprise_config()
        demonstrate_custom_configuration()
        demonstrate_dynamic_upgrades()
        demonstrate_environment_awareness()
        demonstrate_configuration_documentation()
        demonstrate_real_world_scenarios()

        print("\n" + "=" * 65)
        print("✅ Progressive Disclosure Configuration Demo Complete!")
        print("=" * 65)

        print("\n🎯 Key Benefits Demonstrated:")
        print("  🚀 Zero configuration to get started")
        print("  📈 Progressive complexity scaling")
        print("  🎛️ Feature-driven configuration")
        print("  🌍 Environment-aware settings")
        print("  🏢 Enterprise-ready features")
        print("  📚 Automatic documentation")

        print("\n💡 Usage Examples:")
        print("  # Zero config - just works")
        print("  config = zero_config()")
        print()
        print("  # Production ready")
        print("  config = production_config()")
        print()
        print("  # Custom features")
        print("  config = create_configuration('basic', features=['multi_tenant'])")
        print()
        print("  # Dynamic upgrades")
        print("  config.upgrade_level('enterprise')")
        print("  config.enable_feature('encryption')")

        print("\n🚀 Configuration Levels:")
        print("  1. zero_config() - Just works, SQLite database")
        print("  2. basic_config() - Caching and monitoring")
        print("  3. production_config() - Production features")
        print("  4. enterprise_config() - All enterprise features")

        print("\n🎛️ Progressive Features:")
        print("  • Auto-migrations and visual builder (always)")
        print("  • Query optimization and caching (intermediate+)")
        print("  • Multi-tenancy and encryption (advanced+)")
        print("  • Compliance and sharding (enterprise)")

        return 0

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
