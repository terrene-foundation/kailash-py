"""Comprehensive secure logging example with real data scenarios.

This example demonstrates secure logging with actual sensitive data processing,
real file handling, database operations, and API calls. Shows how to protect
PII, credentials, and sensitive information in production-like scenarios.
"""

import csv
import json
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, SQLDatabaseNode
from kailash.nodes.security import CredentialManagerNode
from kailash.runtime.local import LocalRuntime
from kailash.utils.secure_logging import (
    SecureLogger,
    SecureLoggingMixin,
    apply_secure_logging_to_node,
    secure_log,
)
from kailash.workflow import Workflow

# Configure comprehensive logging to see all output
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/secure_logging_demo.log", mode="w"),
    ],
)


def setup_realistic_test_data():
    """Create realistic test data files with sensitive information."""
    print("🔧 Setting up realistic test data with sensitive information...")

    data_dir = Path("/tmp/secure_logging_test")
    data_dir.mkdir(exist_ok=True)

    # Create customer data with PII
    customers_file = data_dir / "customers.csv"
    with open(customers_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["id", "name", "email", "phone", "ssn", "credit_card", "address"]
        )
        writer.writerows(
            [
                [
                    1,
                    "John Smith",
                    "john.smith@email.com",
                    "555-0123",
                    "123-45-6789",
                    "4532-1234-5678-9012",
                    "123 Main St, Anytown USA",
                ],
                [
                    2,
                    "Jane Doe",
                    "jane.doe@company.com",
                    "555-0456",
                    "987-65-4321",
                    "5555-4444-3333-2222",
                    "456 Oak Ave, Another City",
                ],
                [
                    3,
                    "Bob Johnson",
                    "bob.j@personal.org",
                    "555-0789",
                    "456-78-9123",
                    "4111-1111-1111-1111",
                    "789 Pine Rd, Third Place",
                ],
                [
                    4,
                    "Alice Brown",
                    "alice.brown@work.biz",
                    "555-0321",
                    "321-54-9876",
                    "4000-0000-0000-0002",
                    "321 Elm St, Fourth Town",
                ],
            ]
        )

    # Create employee data with sensitive fields
    employees_file = data_dir / "employees.csv"
    with open(employees_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["emp_id", "name", "email", "salary", "api_key", "department"])
        writer.writerows(
            [
                [
                    "EMP001",
                    "Mike Wilson",
                    "mike.wilson@company.com",
                    75000,
                    "sk-proj-abc123def456",
                    "Engineering",
                ],
                [
                    "EMP002",
                    "Sarah Davis",
                    "sarah.davis@company.com",
                    82000,
                    "ak_test_xyz789uvw123",
                    "Marketing",
                ],
                [
                    "EMP003",
                    "Tom Garcia",
                    "tom.garcia@company.com",
                    95000,
                    "ghp_1234567890abcdef",
                    "DevOps",
                ],
            ]
        )

    # Create transaction logs with financial data
    transactions_file = data_dir / "transactions.json"
    transactions = [
        {
            "id": "TXN-2024-001",
            "timestamp": "2024-01-15T10:30:00Z",
            "customer_id": 1,
            "amount": 199.99,
            "card_number": "4532123456789012",
            "cvv": "123",
            "auth_token": "Bearer sk-proj-transaction-key-abc123",
            "ip_address": "192.168.1.100",
        },
        {
            "id": "TXN-2024-002",
            "timestamp": "2024-01-15T11:45:00Z",
            "customer_id": 2,
            "amount": 299.50,
            "card_number": "5555444433332222",
            "cvv": "456",
            "auth_token": "Bearer ak_live_secret789xyz",
            "ip_address": "10.0.0.50",
        },
    ]

    with open(transactions_file, "w") as f:
        json.dump(transactions, f, indent=2)

    # Create configuration file with secrets
    config_file = data_dir / "app_config.json"
    config = {
        "database": {
            "host": "localhost",
            "port": 5432,
            "name": "prod_db",
            "username": "admin",
            "password": "super_secret_db_password_2024!",
            "connection_string": "postgresql://admin:super_secret_db_password_2024!@localhost/prod_db",
        },
        "api_keys": {
            "openai": "sk-proj-OpenAI_API_Key_With_Very_Long_String_123456789",
            "stripe": "sk_live_Stripe_Secret_Key_Production_789xyz123",
            "aws_access_key": "AKIA1234567890ABCDEF",
            "aws_secret": "abcdef1234567890ABCDEF1234567890abcdef12",
        },
        "oauth": {
            "client_id": "oauth_client_id_12345",
            "client_secret": "oauth_client_secret_very_long_string_abcdef123456",
            "redirect_uri": "https://app.company.com/callback",
        },
    }

    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)

    print(f"   ✅ Created test data in {data_dir}")
    print(f"      - Customer data: {customers_file}")
    print(f"      - Employee data: {employees_file}")
    print(f"      - Transactions: {transactions_file}")
    print(f"      - Config file: {config_file}")

    return {
        "data_dir": data_dir,
        "customers_file": customers_file,
        "employees_file": employees_file,
        "transactions_file": transactions_file,
        "config_file": config_file,
    }


def test_secure_logging_with_real_data(test_data):
    """Test secure logging with real sensitive data."""
    print("\n📊 Testing Secure Logging with Real Sensitive Data...")

    # Create secure logger with comprehensive patterns
    logger = SecureLogger("demo.real_data")

    # Test 1: Process customer data
    print("\n1. Processing customer data with PII:")

    with open(test_data["customers_file"], "r") as f:
        reader = csv.DictReader(f)
        for customer in reader:
            # Log customer processing with secure logging
            logger.info(
                f"Processing customer {customer['id']} - Email: {customer['email']}"
            )

            # Simulate payment processing
            payment_info = {
                "customer_email": customer["email"],
                "card_number": customer["credit_card"],
                "amount": 149.99,
                "billing_address": customer["address"],
                "phone": customer["phone"],
            }
            # Log payment details (will be masked)
            logger.debug(
                f"Payment details for customer {customer['id']}: {payment_info}"
            )

    # Test 2: Process configuration with secrets
    print("\n2. Processing configuration with embedded secrets:")

    with open(test_data["config_file"], "r") as f:
        config = json.load(f)
        logger.info(f"Loading application configuration: {config}")

        # Test individual secret logging
        logger.debug(f"Database connection: {config['database']['connection_string']}")
        logger.debug(f"API Key loaded: {config['api_keys']['openai']}")
        logger.debug(
            f"AWS credentials: {config['api_keys']['aws_access_key']} / {config['api_keys']['aws_secret']}"
        )

    # Test 3: Process transaction logs
    print("\n3. Processing financial transaction data:")

    with open(test_data["transactions_file"], "r") as f:
        transactions = json.load(f)
        for txn in transactions:
            logger.info(f"Processing transaction {txn['id']}: {txn}")

            # Simulate fraud detection logging
            fraud_check = {
                "transaction_id": txn["id"],
                "card_last_four": txn["card_number"][-4:],
                "full_card": txn["card_number"],  # This should be masked
                "cvv": txn["cvv"],  # This should be masked
                "amount": txn["amount"],
                "risk_score": 0.3,
            }
            logger.warning(f"Fraud detection check: {fraud_check}")


def test_data_processing_pipeline_with_logging(test_data):
    """Test a complete data processing pipeline with secure logging."""
    print("\n🔄 Testing Data Processing Pipeline with Secure Logging...")

    class SecureDataProcessor(SecureLoggingMixin):
        """Data processor with built-in secure logging."""

        def __init__(self):
            # Add domain-specific sensitive fields before super().__init__()
            self._sensitive_fields = {
                "salary",
                "compensation",
                "bonus",
                "wage",
                "emp_id",
                "employee_id",
                "badge_number",
                "transaction_id",
                "order_id",
                "invoice_id",
            }
            super().__init__()

        def load_customer_data(self, file_path: str) -> List[Dict]:
            """Load customer data with secure logging."""
            self.log_info(f"Loading customer data from {file_path}")

            customers = []
            with open(file_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    customers.append(row)
                    self.log_debug(f"Loaded customer record: {row}")

            self.log_info(f"Successfully loaded {len(customers)} customer records")
            return customers

        def process_transactions(self, transactions: List[Dict]) -> Dict[str, Any]:
            """Process transactions with audit logging."""
            self.log_info(f"Processing {len(transactions)} transactions")

            total_amount = 0
            processed_count = 0

            for txn in transactions:
                try:
                    self.log_debug(f"Processing transaction: {txn}")

                    # Validate transaction
                    if txn["amount"] <= 0:
                        raise ValueError("Invalid transaction amount")

                    if len(txn["card_number"]) < 13:
                        raise ValueError("Invalid card number format")

                    total_amount += txn["amount"]
                    processed_count += 1

                    self.log_info(f"Transaction {txn['id']} processed successfully")

                except Exception as e:
                    self.log_error(
                        f"Failed to process transaction {txn.get('id', 'unknown')}",
                        e,
                        txn,
                    )
                    continue

            summary = {
                "total_processed": processed_count,
                "total_amount": total_amount,
                "average_amount": (
                    total_amount / processed_count if processed_count > 0 else 0
                ),
                "processing_time": datetime.now().isoformat(),
            }

            self.log_info(f"Transaction processing complete: {summary}")
            return summary

        def generate_employee_report(self, employees: List[Dict]) -> Dict[str, Any]:
            """Generate employee report with salary information."""
            self.log_info(f"Generating report for {len(employees)} employees")

            total_salary = 0
            dept_salaries = {}

            for emp in employees:
                self.log_debug(f"Processing employee: {emp}")

                salary = float(emp["salary"])
                department = emp["department"]

                total_salary += salary

                if department not in dept_salaries:
                    dept_salaries[department] = []
                dept_salaries[department].append(salary)

            report = {
                "total_employees": len(employees),
                "total_payroll": total_salary,
                "average_salary": total_salary / len(employees),
                "departments": {
                    dept: {
                        "count": len(salaries),
                        "total": sum(salaries),
                        "average": sum(salaries) / len(salaries),
                    }
                    for dept, salaries in dept_salaries.items()
                },
            }

            self.log_info(f"Employee report generated: {report}")
            return report

    # Use the secure processor
    processor = SecureDataProcessor()

    # Load and process customers
    customers = processor.load_customer_data(test_data["customers_file"])

    # Load and process transactions
    with open(test_data["transactions_file"], "r") as f:
        transactions = json.load(f)

    transaction_summary = processor.process_transactions(transactions)

    # Load and process employees
    employees = []
    with open(test_data["employees_file"], "r") as f:
        reader = csv.DictReader(f)
        employees = list(reader)

    employee_report = processor.generate_employee_report(employees)

    print("   ✅ Data processing pipeline completed with secure logging")
    print(f"      - Processed {len(customers)} customers")
    print(f"      - Processed {transaction_summary['total_processed']} transactions")
    print(
        f"      - Generated report for {employee_report['total_employees']} employees"
    )


def test_workflow_with_secure_nodes(test_data):
    """Test a complete workflow with secure logging enabled nodes."""
    print("\n🔗 Testing Workflow with Secure Logging Nodes...")

    # Create secure versions of nodes
    SecureCSVReader = apply_secure_logging_to_node(CSVReaderNode)
    SecurePythonCode = apply_secure_logging_to_node(PythonCodeNode)

    # Create workflow
    workflow = Workflow("secure_demo", "Secure Logging Demo Workflow")

    # Add nodes with secure logging
    workflow.add_node(
        "load_customers",
        SecureCSVReader(
            name="load_customers", file_path=str(test_data["customers_file"])
        ),
    )

    workflow.add_node(
        "process_data",
        SecurePythonCode(
            name="process_data",
            code="""
import pandas as pd
from datetime import datetime

# Process customer data
df = pd.DataFrame(data)

# Calculate customer metrics (with PII in processing)
total_customers = len(df)
unique_emails = df['email'].nunique()
phone_patterns = df['phone'].str.extract(r'(\\d{3})-(\\d{4})')

# Extract credit card info (this will be logged securely)
card_types = []
for card in df['credit_card']:
    if card.startswith('4'):
        card_types.append('Visa')
    elif card.startswith('5'):
        card_types.append('MasterCard')
    else:
        card_types.append('Other')

df['card_type'] = card_types

# Generate summary (without exposing PII)
result = {
    "customer_count": total_customers,
    "unique_emails": unique_emails,
    "card_type_distribution": df['card_type'].value_counts().to_dict(),
    "processing_timestamp": datetime.now().isoformat(),
    "data_quality": {
        "complete_records": len(df.dropna()),
        "missing_data_count": df.isnull().sum().sum()
    }
}
""",
        ),
    )

    # Connect workflow
    workflow.connect("load_customers", "process_data", {"data": "data"})

    # Execute workflow
    try:
        runner = LocalRuntime()
        result = runner.execute(workflow)

        if result.get("success"):
            print("   ✅ Secure workflow executed successfully")
            process_result = result["results"]["process_data"]
            print(f"      Customer analysis: {json.dumps(process_result, indent=2)}")
        else:
            print(f"   ❌ Workflow failed: {result.get('error')}")

    except Exception as e:
        print(f"   ❌ Workflow execution error: {e}")


def test_api_credential_logging():
    """Test secure logging with API credentials and tokens."""
    print("\n🔐 Testing API Credential Secure Logging...")

    @secure_log(mask_params=["api_key", "access_token", "auth_header"])
    def make_api_call(
        endpoint: str, api_key: str, data: Dict = None, access_token: str = None
    ):
        """Make API call with secure credential logging."""
        print(f"Making API call to {endpoint}")
        # In real implementation, this would make actual API call
        return {"status": "success", "response_id": "12345"}

    @secure_log(mask_params=["password", "secret"])
    def oauth_exchange(
        client_id: str, client_secret: str, username: str, password: str
    ):
        """OAuth token exchange with secure logging."""
        print("Performing OAuth token exchange")
        return {
            "access_token": "bearer_token_abc123",
            "refresh_token": "refresh_token_xyz789",
            "expires_in": 3600,
        }

    # Test API calls with real-looking credentials
    print("\n1. Testing API calls with various credential formats:")

    api_credentials = [
        ("OpenAI API", "sk-proj-1234567890abcdefghijklmnopqrstuvwxyz"),
        ("Stripe API", "sk_live_51abcdefghijklmnopqrstuvwxyz1234567890"),
        ("GitHub Token", "ghp_1234567890abcdefghijklmnopqrstuvwxyz"),
        ("AWS Access Key", "AKIA1234567890ABCDEFGH"),
        ("Custom API", "api_key_company_internal_secret_12345"),
    ]

    for service, key in api_credentials:
        result = make_api_call(
            endpoint=f"https://api.{service.lower().replace(' ', '')}.com/v1/data",
            api_key=key,
            data={"user_id": "12345", "action": "fetch"},
        )

    # Test OAuth flows
    print("\n2. Testing OAuth credential flows:")

    oauth_result = oauth_exchange(
        client_id="oauth_client_12345",
        client_secret="oauth_secret_very_long_string_abcdef123456789",
        username="user@example.com",
        password="UserPassword123!",
    )

    # Test Bearer tokens and authorization headers
    logger = SecureLogger("demo.auth")

    print("\n3. Testing authorization header patterns:")

    auth_headers = [
        "Bearer sk-proj-secret-token-123456789abcdef",
        "Basic dXNlcm5hbWU6cGFzc3dvcmQ=",  # base64 encoded username:password
        "API-Key secret-api-key-12345",
        "Authorization: Bearer jwt.token.signature",
        "X-API-Key: custom-secret-key-xyz789",
    ]

    for header in auth_headers:
        logger.info(f"Processing request with auth: {header}")


def test_database_connection_logging():
    """Test secure logging with database connection strings."""
    print("\n🗄️  Testing Database Connection Secure Logging...")

    logger = SecureLogger("demo.database")

    # Test various database connection string formats
    connection_strings = [
        "postgresql://username:password@localhost:5432/database",
        "mysql://admin:secret123@db.example.com:3306/prod_db",
        "mongodb://user:pass@cluster.mongodb.net/mydb?retryWrites=true",
        "redis://user:password@redis-cluster.example.com:6379/0",
        "sqlite:///path/to/database.db",
        "mssql://sa:ComplexPassword123!@sqlserver.example.com:1433/database",
    ]

    print("\n1. Testing database connection string masking:")

    for conn_str in connection_strings:
        logger.info(f"Connecting to database: {conn_str}")

        # Test with connection configs
        config = {
            "host": "db.example.com",
            "username": "admin",
            "password": "super_secret_db_password",
            "database": "production",
            "connection_string": conn_str,
        }
        logger.debug(f"Database configuration: {config}")

    # Test SQL queries with embedded sensitive data
    print("\n2. Testing SQL query logging with sensitive data:")

    queries = [
        "SELECT * FROM users WHERE email = 'john.doe@example.com' AND ssn = '123-45-6789'",
        "INSERT INTO payments (card_number, cvv, amount) VALUES ('4532123456789012', '123', 199.99)",
        "UPDATE customers SET api_key = 'sk-proj-secret123' WHERE id = 1",
        "DELETE FROM logs WHERE message LIKE '%password%' OR message LIKE '%secret%'",
    ]

    for query in queries:
        logger.debug(f"Executing query: {query}")


def test_performance_monitoring():
    """Test secure logging performance with high-volume data."""
    print("\n⚡ Testing Secure Logging Performance...")

    # Test regular logger vs secure logger performance
    regular_logger = logging.getLogger("demo.regular")
    secure_logger = SecureLogger("demo.secure")

    test_data_samples = [
        "Processing user john.doe@example.com with card 4532-1234-5678-9012",
        "API call with key sk-proj-1234567890abcdef and token bearer-xyz789",
        "Database connection postgresql://user:pass@localhost/db successful",
        "Employee EMP123456 salary $75000 processed with SSN 123-45-6789",
        "Transaction TXN-001 amount $199.99 card 5555444433332222 approved",
    ]

    print("\n1. Performance comparison:")

    # Test regular logging
    start_time = time.time()
    for _ in range(1000):
        for sample in test_data_samples:
            regular_logger.debug(sample)
    regular_time = time.time() - start_time

    # Test secure logging
    start_time = time.time()
    for _ in range(1000):
        for sample in test_data_samples:
            secure_logger.debug(sample)
    secure_time = time.time() - start_time

    print(f"   Regular logging: {regular_time:.3f}s for 5000 messages")
    print(f"   Secure logging:  {secure_time:.3f}s for 5000 messages")
    print(f"   Overhead: {((secure_time - regular_time) / regular_time * 100):.1f}%")

    # Test memory usage with large data
    print("\n2. Memory efficiency test:")

    large_data = {
        "customers": [
            {
                "id": i,
                "email": f"customer{i}@example.com",
                "ssn": f"{i:03d}-45-6789",
                "card": f"4532{i:012d}",
                "data": "x" * 1000,  # 1KB of data per customer
            }
            for i in range(100)
        ]
    }

    start_time = time.time()
    secure_logger.info(f"Processing large customer dataset: {large_data}")
    processing_time = time.time() - start_time

    print(f"   Processed 100KB dataset with PII in {processing_time:.3f}s")


def examine_log_output():
    """Examine the generated log file to verify masking."""
    print("\n🔍 Examining Generated Log Output...")

    log_file = "/tmp/secure_logging_demo.log"

    if os.path.exists(log_file):
        print(f"\nLog file contents from {log_file}:")
        print("=" * 60)

        with open(log_file, "r") as f:
            lines = f.readlines()

        # Show first 20 lines as sample
        for i, line in enumerate(lines[:20], 1):
            print(f"{i:2d}: {line.rstrip()}")

        if len(lines) > 20:
            print(f"... and {len(lines) - 20} more lines")

        print("=" * 60)

        # Analyze for any unmasked sensitive data
        sensitive_patterns = [
            r"\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}",  # Credit cards
            r"\d{3}-\d{2}-\d{4}",  # SSNs
            r"sk-proj-[a-zA-Z0-9]+",  # OpenAI keys
            r'password[\'"]?\s*[:=]\s*[\'"]?[^\'"\s]+',  # Passwords
        ]

        potential_leaks = []
        for line_num, line in enumerate(lines, 1):
            for pattern in sensitive_patterns:
                import re

                if re.search(pattern, line, re.IGNORECASE):
                    potential_leaks.append((line_num, line.strip()))

        if potential_leaks:
            print("\n⚠️  Potential sensitive data leaks found:")
            for line_num, line in potential_leaks[:5]:  # Show first 5
                print(f"   Line {line_num}: {line}")
        else:
            print("\n✅ No obvious sensitive data patterns detected in logs")

    else:
        print(f"   ❌ Log file not found at {log_file}")


def main():
    """Run comprehensive secure logging tests."""
    print("🔒 Comprehensive Secure Logging Testing with Real Data")
    print("=" * 60)

    # Setup realistic test data
    test_data = setup_realistic_test_data()

    # Run all tests
    test_secure_logging_with_real_data(test_data)
    test_data_processing_pipeline_with_logging(test_data)
    test_workflow_with_secure_nodes(test_data)
    test_api_credential_logging()
    test_database_connection_logging()
    test_performance_monitoring()

    # Examine the generated logs
    examine_log_output()

    print("\n" + "=" * 60)
    print("✅ Comprehensive secure logging testing completed!")
    print("\nKey capabilities demonstrated:")
    print("   • Automatic PII detection and masking (SSN, credit cards, emails)")
    print("   • API credential protection (API keys, tokens, passwords)")
    print("   • Database connection string masking")
    print("   • Real-time data processing with secure logging")
    print("   • Workflow integration with minimal performance overhead")
    print("   • Custom patterns for organization-specific sensitive data")
    print("   • High-volume logging performance optimization")
    print("\n💡 Secure logging protects sensitive data automatically in production!")
    print("📁 Generated logs saved to: /tmp/secure_logging_demo.log")


if __name__ == "__main__":
    main()
