"""
Test Custom Node Creation with Studio API

This example demonstrates creating and testing custom nodes using the Studio API.
It can run in standalone mode (direct database) or API client mode.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from custom_node_templates import (
    data_validator_template,
    geocoding_api_template,
    sentiment_analyzer_template,
)

from kailash.api.database import CustomNodeRepository, get_db_session, init_database


def test_custom_node_creation():
    """Test creating custom nodes in the database"""
    print("=== Testing Custom Node Creation ===\n")

    # Initialize database
    SessionLocal, _ = init_database("./test_custom_nodes.db")

    with get_db_session(SessionLocal) as session:
        repo = CustomNodeRepository(session)

        # Test templates
        templates = [
            sentiment_analyzer_template,
            data_validator_template,
            geocoding_api_template,
        ]

        created_nodes = []

        for template in templates:
            try:
                # Create node
                node = repo.create(tenant_id="test-tenant", node_data=template)
                created_nodes.append(node)
                print(f"✅ Created {template['implementation_type']} node: {node.name}")

                # Verify node data
                assert node.name == template["name"]
                assert node.implementation_type == template["implementation_type"]
                assert node.parameters == template.get("parameters", [])

            except Exception as e:
                print(f"❌ Failed to create {template['name']}: {e}")

        # List all nodes
        print(f"\n📦 Total nodes created: {len(created_nodes)}")

        # Test retrieval
        all_nodes = repo.list("test-tenant")
        print(f"📋 Retrieved {len(all_nodes)} nodes from database")

        # Test update
        if created_nodes:
            node_to_update = created_nodes[0]
            updated = repo.update(
                node_to_update.id, {"description": "Updated description for testing"}
            )
            print(f"\n✅ Updated node: {updated.name}")
            print(f"   New description: {updated.description}")

        # Test node execution simulation
        print("\n=== Simulating Node Execution ===")
        for node in created_nodes[:2]:  # Test first two nodes
            print(f"\n🔧 Testing {node.name}...")

            if node.implementation_type == "python":
                print("   Would execute Python code:")
                if (
                    isinstance(node.implementation, dict)
                    and "code" in node.implementation
                ):
                    code_preview = node.implementation["code"][:100] + "..."
                    print(f"   {code_preview}")

            elif node.implementation_type == "api":
                print("   Would make API call to:")
                if (
                    isinstance(node.implementation, dict)
                    and "base_url" in node.implementation
                ):
                    print(f"   {node.implementation['base_url']}")

    # Cleanup
    if os.path.exists("./test_custom_nodes.db"):
        os.remove("./test_custom_nodes.db")
        print("\n🧹 Cleaned up test database")


def test_custom_node_validation():
    """Test custom node validation rules"""
    print("\n=== Testing Custom Node Validation ===\n")

    # Test invalid node data
    invalid_nodes = [
        {
            "name": "InvalidNode1",
            # Missing implementation_type
            "category": "test",
        },
        {
            "name": "InvalidNode2",
            "implementation_type": "invalid_type",  # Invalid type
            "category": "test",
        },
        {"name": "", "implementation_type": "python", "category": "test"},  # Empty name
    ]

    SessionLocal, _ = init_database("./test_validation.db")

    with get_db_session(SessionLocal) as session:
        repo = CustomNodeRepository(session)

        for invalid_node in invalid_nodes:
            try:
                repo.create("test-tenant", invalid_node)
                print(f"❌ Should have failed: {invalid_node}")
            except Exception as e:
                print(f"✅ Correctly rejected invalid node: {e}")

    # Cleanup
    if os.path.exists("./test_validation.db"):
        os.remove("./test_validation.db")


if __name__ == "__main__":
    print("=== Custom Node Testing Suite ===\n")

    # Run tests
    test_custom_node_creation()
    test_custom_node_validation()

    print("\n✅ All custom node tests completed!")

    print("\n📝 Next steps:")
    print("1. Use these templates with the Studio API")
    print("2. Create custom nodes via POST /api/custom-nodes")
    print("3. Use custom nodes in your workflows")
