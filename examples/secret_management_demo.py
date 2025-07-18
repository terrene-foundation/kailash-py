"""Demonstration of runtime secret management in Kailash SDK.

This example shows how to use the new runtime secret management capabilities
to inject secrets at runtime without embedding them in workflow parameters.
"""

import os

from kailash.nodes.base import Node, NodeParameter
from kailash.runtime.local import LocalRuntime
from kailash.runtime.secret_provider import EnvironmentSecretProvider, SecretRequirement
from kailash.workflow import WorkflowBuilder


class TokenGeneratorNode(Node):
    """Example node that requires a secret key for token generation."""

    def get_parameters(self):
        return {
            "secret_key": NodeParameter(
                name="secret_key",
                type=str,
                required=True,
                description="Secret key for token generation",
            ),
            "user_id": NodeParameter(
                name="user_id",
                type=str,
                required=True,
                description="User ID to generate token for",
            ),
        }

    @classmethod
    def get_secret_requirements(cls):
        """Declare that this node requires a secret key."""
        return [
            SecretRequirement(
                name="jwt-signing-key", parameter_name="secret_key", optional=False
            )
        ]

    def run(self, secret_key, user_id, **kwargs):
        """Generate a token using the injected secret."""
        # In a real implementation, this would generate a JWT token
        token = f"token_{user_id}_{len(secret_key)}_chars"
        return {
            "token": token,
            "user_id": user_id,
            "secret_used": True,
            "secret_length": len(secret_key),
        }


def demonstrate_secret_management():
    """Demonstrate the complete secret management workflow."""
    print("🔐 Kailash SDK Runtime Secret Management Demo")
    print("=" * 50)

    # 1. Set up environment variable with secret (simulating production secret)
    os.environ["KAILASH_SECRET_JWT_SIGNING_KEY"] = (
        "super_secret_key_for_jwt_signing_12345"
    )

    # 2. Create secret provider
    secret_provider = EnvironmentSecretProvider()
    print("✅ Created EnvironmentSecretProvider")

    # 3. Create runtime with secret provider
    runtime = LocalRuntime(secret_provider=secret_provider)
    print("✅ Created LocalRuntime with secret provider")

    # 4. Register our custom node
    from kailash.nodes.base import NodeRegistry

    NodeRegistry.register(TokenGeneratorNode)
    print("✅ Registered TokenGeneratorNode")

    try:
        # 5. Create workflow WITHOUT providing the secret
        workflow = WorkflowBuilder()
        workflow.add_node(
            "TokenGeneratorNode",
            "token_gen",
            {
                "user_id": "user123"
                # NOTE: No secret_key provided - will be injected at runtime!
            },
        )

        print("✅ Created workflow without secret in parameters")

        # 6. Execute workflow - secret will be injected automatically
        print("\n🚀 Executing workflow with runtime secret injection...")
        results, run_id = runtime.execute(workflow.build())

        # 7. Verify the secret was injected and used
        token_result = results["token_gen"]
        print("\n📋 Results:")
        print(f"   Token: {token_result['token']}")
        print(f"   User ID: {token_result['user_id']}")
        print(f"   Secret was used: {token_result['secret_used']}")
        print(f"   Secret length: {token_result['secret_length']} characters")

        # 8. Demonstrate that secret was not exposed in workflow
        print("\n🔒 Security:")
        print("   Secret was injected at runtime, not stored in workflow")
        print("   Workflow parameters contained only non-sensitive data")

        print("\n✅ Demo completed successfully!")
        print("🎉 Runtime secret management is working!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Clean up
        if "TokenGeneratorNode" in NodeRegistry._nodes:
            del NodeRegistry._nodes["TokenGeneratorNode"]
        if "KAILASH_SECRET_JWT_SIGNING_KEY" in os.environ:
            del os.environ["KAILASH_SECRET_JWT_SIGNING_KEY"]


def demonstrate_anti_pattern():
    """Show the old anti-pattern for comparison."""
    print("\n🚨 Anti-Pattern (OLD WAY - INSECURE)")
    print("=" * 50)

    # Old way: embedding secret in workflow parameters
    workflow = WorkflowBuilder()
    workflow.add_node(
        "PythonCodeNode",
        "insecure_token",
        {
            "code": """
# Anti-pattern: secret embedded in code
secret_key = "super_secret_key_for_jwt_signing_12345"  # SECURITY RISK!
result = {"token": f"token_{secret_key}_exposed", "security_risk": True}
        """
        },
    )

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    print("❌ Old way exposes secrets in workflow code")
    print("❌ Secret is visible in logs and stored in workflow")
    print(f"❌ Result: {results['insecure_token']}")


if __name__ == "__main__":
    demonstrate_secret_management()
    demonstrate_anti_pattern()

    print("\n🎯 Key Benefits of Runtime Secret Management:")
    print("   • Secrets never stored in workflow parameters")
    print("   • Secrets fetched at runtime from secure sources")
    print("   • Supports multiple secret providers (Vault, AWS, etc.)")
    print("   • Backward compatible with existing workflows")
    print("   • Enables secret rotation without code changes")
