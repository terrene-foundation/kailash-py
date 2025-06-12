"""Example demonstrating secure logging with automatic PII and credential masking.

This example shows how to use SecureLoggingMixin and related utilities to
protect sensitive data in logs.
"""

import logging
from kailash.utils.secure_logging import (
    SecureLogger,
    SecureLoggingMixin,
    secure_log,
    apply_secure_logging_to_node
)
from kailash.workflow import Workflow
from kailash.nodes.data import SQLDatabaseNode
from kailash.nodes.api import HTTPRequestNode


# Configure logging to see output
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def demonstrate_basic_masking():
    """Show basic secure logging functionality."""
    print("=== Basic Secure Logging ===\n")
    
    logger = SecureLogger("demo.basic")
    
    # Test various sensitive data patterns
    test_data = {
        "credit_card": "4532-1234-5678-9012",
        "ssn": "123-45-6789",
        "email": "john.doe@example.com",
        "phone": "+1 (555) 123-4567",
        "api_key": "sk-proj-abcdef1234567890abcdef1234567890",
        "password": "MySecretP@ssw0rd!",
        "normal_data": "This is safe to log"
    }
    
    # Log with automatic masking
    logger.info("Processing user data", **test_data)
    
    # Log string with embedded secrets
    message = "User john.doe@example.com with SSN 123-45-6789 and card 4532123456789012"
    logger.info(message)
    
    # Log with password in various formats
    logger.debug("password: secretpass123")
    logger.debug("Authorization: Bearer sk-proj-verysecretapikey123456")


def demonstrate_mixin_usage():
    """Show how to use SecureLoggingMixin in classes."""
    print("\n\n=== SecureLoggingMixin Usage ===\n")
    
    class DataProcessor(SecureLoggingMixin):
        """Example class with secure logging."""
        
        def __init__(self):
            # Define additional sensitive fields for this class
            self._sensitive_fields = {"user_id", "account_number", "routing_number"}
            super().__init__()
        
        def process_payment(self, payment_info):
            """Process payment with secure logging."""
            self.log_info("Processing payment", payment_info)
            
            # Simulate processing
            try:
                if payment_info.get("amount", 0) > 10000:
                    raise ValueError("Amount exceeds limit")
                
                self.log_info("Payment processed successfully")
                return {"status": "success", "transaction_id": "TXN123456"}
                
            except Exception as e:
                self.log_error("Payment failed", e, payment_info)
                raise
    
    # Use the processor
    processor = DataProcessor()
    
    # This sensitive data will be masked in logs
    payment_data = {
        "credit_card": "4532-1234-5678-9012",
        "amount": 250.00,
        "user_id": "USR789456",
        "account_number": "987654321",
        "routing_number": "123456789",
        "merchant": "Example Store"
    }
    
    processor.process_payment(payment_data)


def demonstrate_decorator_pattern():
    """Show @secure_log decorator usage."""
    print("\n\n=== Secure Log Decorator ===\n")
    
    @secure_log(mask_params=["password", "api_key"])
    def authenticate_user(username: str, password: str, api_key: str = None):
        """Authenticate with secure parameter logging."""
        print(f"Authenticating {username}")
        # Sensitive params are masked in decorator logs
        return {"token": "jwt_token_here", "user": username}
    
    # Call with sensitive data - check logs
    result = authenticate_user(
        username="john.doe",
        password="MySecretPassword123!",
        api_key="sk-proj-1234567890abcdef"
    )


def demonstrate_node_enhancement():
    """Show how to add secure logging to nodes."""
    print("\n\n=== Secure Node Enhancement ===\n")
    
    # Create secure versions of nodes
    SecureSQLNode = apply_secure_logging_to_node(SQLDatabaseNode)
    SecureHTTPNode = apply_secure_logging_to_node(HTTPRequestNode)
    
    # Use in workflow
    workflow = Workflow(
        workflow_id="secure_workflow",
        name="Workflow with Secure Logging"
    )
    
    # These nodes will mask sensitive data in logs
    workflow.add_node(
        "fetch_user",
        SecureSQLNode,
        query="SELECT * FROM users WHERE email = %s",
        params=["john.doe@example.com"],
        connection_string="postgresql://user:password@localhost/db"
    )
    
    workflow.add_node(
        "api_call",
        SecureHTTPNode,
        url="https://api.example.com/users",
        headers={
            "Authorization": "Bearer sk-proj-secretapikey123456",
            "X-API-Key": "another-secret-key"
        }
    )
    
    print("✅ Secure nodes configured - sensitive data will be masked in logs")


def demonstrate_custom_patterns():
    """Show how to add custom masking patterns."""
    print("\n\n=== Custom Masking Patterns ===\n")
    
    import re
    
    # Create logger with custom patterns
    custom_patterns = [
        re.compile(r'EMP\d{6}'),  # Employee IDs
        re.compile(r'ORD-\d{10}'),  # Order numbers
        re.compile(r'[A-Z]{2}\d{6}'),  # Custom ID format
    ]
    
    custom_fields = {"employee_id", "order_ref", "internal_code"}
    
    logger = SecureLogger(
        "demo.custom",
        custom_patterns=custom_patterns,
        custom_fields=custom_fields
    )
    
    # Test custom patterns
    data = {
        "employee_id": "EMP123456",
        "order_ref": "ORD-1234567890",
        "internal_code": "AB123456",
        "message": "Employee EMP789012 processed order ORD-0987654321"
    }
    
    logger.info("Processing internal data", **data)


def demonstrate_email_preservation():
    """Show how emails are partially masked."""
    print("\n\n=== Email Domain Preservation ===\n")
    
    logger = SecureLogger("demo.email")
    
    emails = [
        "john.doe@company.com",
        "admin@internal.corp",
        "support+test@example.org",
        "very.long.email.address@subdomain.example.com"
    ]
    
    print("Email masking (preserves domain):")
    for email in emails:
        logger.info(f"Processing user: {email}")


def demonstrate_audit_safe_logging():
    """Show audit-safe logging patterns."""
    print("\n\n=== Audit-Safe Logging ===\n")
    
    class AuditableProcessor(SecureLoggingMixin):
        """Processor with audit trail."""
        
        def process_transaction(self, transaction):
            """Process with audit trail."""
            # Create audit-safe version
            audit_data = {
                "transaction_id": transaction.get("id"),
                "timestamp": transaction.get("timestamp"),
                "amount": transaction.get("amount"),
                "status": "processing",
                # Sensitive fields will be masked
                "card_number": transaction.get("card_number"),
                "cvv": transaction.get("cvv")
            }
            
            self.log_info("Transaction audit", audit_data)
            
            # Process transaction
            return {"status": "completed", "id": transaction["id"]}
    
    processor = AuditableProcessor()
    
    transaction = {
        "id": "TXN-2024-001",
        "timestamp": "2024-01-15T10:30:00Z",
        "amount": 150.00,
        "card_number": "4532123456789012",
        "cvv": "123",
        "merchant": "Example Store"
    }
    
    processor.process_transaction(transaction)


def demonstrate_performance_masking():
    """Show efficient masking for high-volume scenarios."""
    print("\n\n=== Performance-Optimized Masking ===\n")
    
    # Use fixed-length masking for performance
    logger = SecureLogger(
        "demo.performance",
        mask_char="*",
        mask_length=8  # Fixed length is faster
    )
    
    # Simulate high-volume logging
    print("Processing 1000 records with masking...")
    
    import time
    start = time.time()
    
    for i in range(1000):
        logger.debug(f"Processing record {i}: card=4532123456789012, ssn=123-45-6789")
    
    elapsed = time.time() - start
    print(f"✅ Processed 1000 records in {elapsed:.2f}s with secure masking")


if __name__ == "__main__":
    # Run all demonstrations
    demonstrate_basic_masking()
    demonstrate_mixin_usage()
    demonstrate_decorator_pattern()
    demonstrate_node_enhancement()
    demonstrate_custom_patterns()
    demonstrate_email_preservation()
    demonstrate_audit_safe_logging()
    demonstrate_performance_masking()
    
    print("\n\n✅ Secure logging helps protect sensitive data automatically!")
    print("   - Automatic detection of PII and credentials")
    print("   - Customizable patterns for organization-specific data")
    print("   - Minimal performance impact")
    print("   - Easy integration with existing code")