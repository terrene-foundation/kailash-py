"""DataFlow models for test suite."""

import os

from dotenv import load_dotenv

from dataflow import DataFlow

# Load environment variables
load_dotenv()

# Initialize DataFlow with test database
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://admin:changeme123@127.0.0.1:5433/central_it_hub"
)

db = DataFlow(TEST_DATABASE_URL)


@db.model
class User:
    """User model for testing DataFlow bulk operations."""

    id: str  # String ID (not auto-incrementing int)
    email: str
    display_name: str
    country: str
    department: str
    account_enabled: bool
