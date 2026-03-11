"""
Comprehensive DataFlow Write Protection Demo

Demonstrates all protection features and integration patterns with Core SDK.
Shows how protection works seamlessly with existing DataFlow workflows.
"""

import asyncio
import logging
from datetime import time
from typing import Any, Dict

# DataFlow imports
from dataflow.core.protected_engine import ProtectedDataFlow
from dataflow.core.protection import (
    ConnectionProtection,
    FieldProtection,
    GlobalProtection,
    ModelProtection,
    OperationType,
    ProtectionLevel,
    ProtectionViolation,
    TimeWindow,
    WriteProtectionConfig,
)

from kailash.runtime.local import LocalRuntime

# Core SDK imports (standard pattern)
from kailash.workflow.builder import WorkflowBuilder

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WriteProtectionDemo:
    """Comprehensive demonstration of DataFlow write protection features."""

    def __init__(self):
        # Initialize protected DataFlow instance
        self.db = ProtectedDataFlow(
            database_url="sqlite:///demo.db", enable_protection=True, debug=True
        )

        # Define demo models
        self._setup_demo_models()

    def _setup_demo_models(self):
        """Setup demonstration models."""

        @self.db.model
        class User:
            id: int
            username: str
            email: str
            password: str  # Will be protected
            created_at: str
            is_admin: bool

        @self.db.model
        class BankAccount:
            id: int
            account_number: str  # Will be protected
            balance: float
            user_id: int
            is_active: bool

        @self.db.model
        class AuditLog:
            id: int
            action: str
            user_id: int
            timestamp: str

        self.user_model = User
        self.bank_account_model = BankAccount
        self.audit_log_model = AuditLog

    async def demo_global_protection(self):
        """Demonstrate global read-only protection."""
        print("\n=== Global Protection Demo ===")

        # Enable global read-only mode
        self.db.enable_read_only_mode("System maintenance in progress")

        # Create workflow that tries to create a user
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserCreateNode",
            "create_user",
            {
                "username": "testuser",
                "email": "test@example.com",
                "password": "secret123",
                "created_at": "2024-01-01T10:00:00",
                "is_admin": False,
            },
        )

        # Try to execute with protection
        try:
            runtime = self.db.create_protected_runtime()
            results, run_id = runtime.execute(workflow.build())
            print("❌ Unexpected: Operation should have been blocked")
        except ProtectionViolation as e:
            print(f"✅ Global protection working: {e}")

        # Show that reads still work
        workflow_read = WorkflowBuilder()
        workflow_read.add_node("UserListNode", "list_users", {})

        try:
            results, run_id = runtime.execute(workflow_read.build())
            print("✅ Read operations allowed during global protection")
        except Exception as e:
            print(f"Read failed: {e}")

    async def demo_model_protection(self):
        """Demonstrate model-specific protection."""
        print("\n=== Model Protection Demo ===")

        # Reset to allow normal operations
        self.db.disable_protection()

        # Protect BankAccount model - only allow reads
        self.db.add_model_protection(
            "BankAccount",
            protection_level=ProtectionLevel.BLOCK,
            allowed_operations={OperationType.READ},
            reason="Bank accounts are protected assets",
        )

        # Try to create a bank account (should fail)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "BankAccountCreateNode",
            "create_account",
            {
                "account_number": "123456789",
                "balance": 1000.0,
                "user_id": 1,
                "is_active": True,
            },
        )

        try:
            runtime = self.db.create_protected_runtime()
            results, run_id = runtime.execute(workflow.build())
            print("❌ Unexpected: BankAccount creation should be blocked")
        except ProtectionViolation as e:
            print(f"✅ Model protection working: {e}")

        # Show that User operations still work
        workflow_user = WorkflowBuilder()
        workflow_user.add_node(
            "UserCreateNode",
            "create_user",
            {
                "username": "testuser2",
                "email": "test2@example.com",
                "password": "secret456",
                "created_at": "2024-01-01T11:00:00",
                "is_admin": False,
            },
        )

        try:
            results, run_id = runtime.execute(workflow_user.build())
            print("✅ Non-protected models still work")
        except Exception as e:
            print(f"User creation failed: {e}")

    async def demo_field_protection(self):
        """Demonstrate field-level protection."""
        print("\n=== Field Protection Demo ===")

        # Reset protection
        self.db.disable_protection()

        # Protect sensitive fields
        self.db.add_field_protection(
            "User",
            "password",
            protection_level=ProtectionLevel.BLOCK,
            allowed_operations={OperationType.READ},
            reason="Password field is sensitive",
        )

        self.db.add_field_protection(
            "BankAccount",
            "account_number",
            protection_level=ProtectionLevel.AUDIT,
            allowed_operations={OperationType.READ},
            reason="Account numbers are PII",
        )

        # Create workflows that access protected fields
        workflow = WorkflowBuilder()

        # This should work - creating user without updating password field directly
        workflow.add_node(
            "UserCreateNode",
            "create_user",
            {
                "username": "fieldtest",
                "email": "fieldtest@example.com",
                "password": "newpassword",  # This might be blocked depending on implementation
                "created_at": "2024-01-01T12:00:00",
                "is_admin": False,
            },
        )

        try:
            runtime = self.db.create_protected_runtime()
            results, run_id = runtime.execute(workflow.build())
            print(
                "✅ User creation completed (field protection may vary by implementation)"
            )
        except ProtectionViolation as e:
            print(f"⚠️ Field protection active: {e}")

    async def demo_time_based_protection(self):
        """Demonstrate time-based protection."""
        print("\n=== Time-Based Protection Demo ===")

        # Create business hours protection (9 AM - 5 PM, weekdays only)
        self.db.enable_business_hours_protection(9, 17)

        # Check current protection status
        status = self.db.get_protection_status()
        print(f"Protection status: {status}")

        # Try operation (will depend on current time)
        workflow = WorkflowBuilder()
        workflow.add_node(
            "AuditLogCreateNode",
            "create_audit",
            {"action": "login", "user_id": 1, "timestamp": "2024-01-01T10:00:00"},
        )

        try:
            runtime = self.db.create_protected_runtime()
            results, run_id = runtime.execute(workflow.build())
            print("✅ Operation allowed (outside business hours or weekend)")
        except ProtectionViolation as e:
            print(f"⏰ Time-based protection active: {e}")

    async def demo_connection_protection(self):
        """Demonstrate connection-level protection."""
        print("\n=== Connection Protection Demo ===")

        # Create production database protection
        config = WriteProtectionConfig()
        config.connection_protections.append(
            ConnectionProtection(
                connection_pattern=r".*prod.*|.*production.*",
                protection_level=ProtectionLevel.BLOCK,
                allowed_operations={OperationType.READ},
                reason="Production database is protected",
            )
        )

        self.db.set_protection_config(config)

        # Test with production-like connection string
        prod_db = ProtectedDataFlow(
            database_url="postgresql://user:pass@prod-db:5432/myapp_production",
            protection_config=config,
        )

        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserCreateNode",
            "create_user",
            {
                "username": "prodtest",
                "email": "prod@example.com",
                "password": "secret",
                "created_at": "2024-01-01T13:00:00",
                "is_admin": False,
            },
        )

        try:
            runtime = prod_db.create_protected_runtime()
            results, run_id = runtime.execute(workflow.build())
            print("❌ Unexpected: Production write should be blocked")
        except ProtectionViolation as e:
            print(f"✅ Connection protection working: {e}")

    async def demo_dynamic_protection(self):
        """Demonstrate dynamic context-aware protection."""
        print("\n=== Dynamic Protection Demo ===")

        # Create protection with custom condition
        def business_logic_condition(context: Dict[str, Any]) -> bool:
            """Custom protection condition based on context."""
            # Example: Block operations if user is not admin
            user_context = context.get("user_context", {})
            return user_context.get("is_admin", False)

        model_protection = ModelProtection(
            model_name="BankAccount",
            protection_level=ProtectionLevel.BLOCK,
            allowed_operations={OperationType.READ, OperationType.CREATE},
            conditions=[business_logic_condition],
            reason="Admin-only access required",
        )

        config = WriteProtectionConfig()
        config.model_protections.append(model_protection)
        self.db.set_protection_config(config)

        # Test with non-admin context
        runtime = self.db.create_protected_runtime(
            user_context={"username": "regular_user", "is_admin": False}
        )

        workflow = WorkflowBuilder()
        workflow.add_node(
            "BankAccountCreateNode",
            "create_account",
            {
                "account_number": "987654321",
                "balance": 500.0,
                "user_id": 2,
                "is_active": True,
            },
        )

        try:
            results, run_id = runtime.execute(workflow.build())
            print("❌ Unexpected: Non-admin operation should be blocked")
        except ProtectionViolation as e:
            print(f"✅ Dynamic protection working: {e}")

        # Test with admin context
        admin_runtime = self.db.create_protected_runtime(
            user_context={"username": "admin_user", "is_admin": True}
        )

        try:
            results, run_id = admin_runtime.execute(workflow.build())
            print("✅ Admin operations allowed")
        except Exception as e:
            print(f"Admin operation failed: {e}")

    async def demo_audit_logging(self):
        """Demonstrate comprehensive audit logging."""
        print("\n=== Audit Logging Demo ===")

        # Enable audit-level protection
        config = WriteProtectionConfig()
        config.global_protection = GlobalProtection(
            protection_level=ProtectionLevel.AUDIT,
            allowed_operations={OperationType.READ},
            reason="Audit all write operations",
        )

        self.db.set_protection_config(config)

        # Perform various operations
        operations = [
            (
                "UserCreateNode",
                {
                    "username": "audituser",
                    "email": "audit@test.com",
                    "password": "secret",
                    "created_at": "2024-01-01T14:00:00",
                    "is_admin": False,
                },
            ),
            ("UserUpdateNode", {"id": 1, "username": "updated_user"}),
            ("UserDeleteNode", {"id": 1}),
        ]

        for node_type, params in operations:
            workflow = WorkflowBuilder()
            workflow.add_node(node_type, "operation", params)

            try:
                runtime = self.db.create_protected_runtime()
                results, run_id = runtime.execute(workflow.build())
            except ProtectionViolation:
                pass  # Expected for audit level

        # Show audit log
        audit_events = self.db.get_protection_audit_log()
        print(f"✅ Audit log contains {len(audit_events)} events")
        for event in audit_events[-3:]:  # Show last 3 events
            print(
                f"  - {event['timestamp']}: {event['operation']} {event['status']} - {event.get('reason', event['message'])}"
            )

    async def demo_protection_combinations(self):
        """Demonstrate combining multiple protection levels."""
        print("\n=== Combined Protection Demo ===")

        # Create layered protection
        config = WriteProtectionConfig()

        # Global: Allow all operations (base level)
        config.global_protection = GlobalProtection(
            protection_level=ProtectionLevel.OFF
        )

        # Connection: Protect production
        config.connection_protections.append(
            ConnectionProtection(
                connection_pattern=r".*prod.*",
                protection_level=ProtectionLevel.BLOCK,
                allowed_operations={OperationType.READ},
            )
        )

        # Model: Protect sensitive models
        config.model_protections.append(
            ModelProtection(
                model_name="BankAccount",
                protection_level=ProtectionLevel.BLOCK,
                allowed_operations={OperationType.READ},
                protected_fields=[
                    FieldProtection(
                        field_name="account_number",
                        protection_level=ProtectionLevel.AUDIT,
                        allowed_operations={OperationType.READ},
                    )
                ],
            )
        )

        self.db.set_protection_config(config)

        print("✅ Multi-layer protection configured:")
        print("  - Global: Open")
        print("  - Connection: Production protected")
        print("  - Model: BankAccount protected")
        print("  - Field: account_numbers audited")

        status = self.db.get_protection_status()
        print(f"Final protection status: {status}")

    async def run_all_demos(self):
        """Run all demonstration scenarios."""
        print("🔒 DataFlow Write Protection Comprehensive Demo")
        print("=" * 50)

        demos = [
            self.demo_global_protection,
            self.demo_model_protection,
            self.demo_field_protection,
            self.demo_time_based_protection,
            self.demo_connection_protection,
            self.demo_dynamic_protection,
            self.demo_audit_logging,
            self.demo_protection_combinations,
        ]

        for demo in demos:
            try:
                await demo()
            except Exception as e:
                print(f"❌ Demo failed: {e}")
                logger.exception("Demo error")

        print("\n" + "=" * 50)
        print("🏁 All demos completed!")


# Production usage examples
async def production_patterns():
    """Show production-ready protection patterns."""
    print("\n🏭 Production Protection Patterns")
    print("=" * 40)

    # Pattern 1: Secure by default
    db = (
        ProtectedDataFlow(
            database_url="postgresql://app:secret@prod-db:5432/myapp",
            enable_protection=True,
        )
        .protect_production()
        .protect_during_maintenance()
    )

    # Pattern 2: PII protection
    pii_fields = {
        "User": ["password", "ssn", "phone"],
        "BankAccount": ["account_number", "routing_number"],
        "CreditCard": ["card_number", "cvv"],
    }
    db.protect_pii_fields(pii_fields)

    # Pattern 3: Business hours compliance
    db.enable_business_hours_protection(9, 17)

    # Pattern 4: Sensitive model protection
    db.protect_sensitive_models(["BankAccount", "CreditCard", "TaxRecord"])

    print("✅ Production patterns applied")
    print(f"Protection status: {db.get_protection_status()}")


if __name__ == "__main__":
    # Run comprehensive demo
    demo = WriteProtectionDemo()
    asyncio.run(demo.run_all_demos())

    # Show production patterns
    asyncio.run(production_patterns())
