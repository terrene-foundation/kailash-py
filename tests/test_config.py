"""Test configuration for real service connections."""

import os

# Database configuration
TEST_DB_CONFIG = {
    "postgresql": {
        "type": "postgresql",
        "host": os.getenv("TEST_DB_HOST", "localhost"),
        "port": int(os.getenv("TEST_DB_PORT", "5432")),
        "database": os.getenv("TEST_DB_NAME", "test_db"),
        "user": os.getenv("TEST_DB_USER", "kailash"),
        "password": os.getenv("TEST_DB_PASSWORD", "kailash123"),
    },
    "connection_string": os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://kailash:kailash123@localhost:5432/test_db"
    ),
}

# Ollama configuration
OLLAMA_CONFIG = {
    "host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
    "model": os.getenv("OLLAMA_MODEL", "llama3.2:1b"),
}

# Vector database configuration
VECTOR_DB_CONFIG = {
    "connection_string": os.getenv(
        "TEST_VECTOR_DB_URL",
        "postgresql://kailash:kailash123@localhost:5432/test_db"
    ),
    "embedding_dimension": 384,  # For all-MiniLM-L6-v2
}

# Test data
TEST_USERS = [
    {"id": 1, "name": "User 1", "email": "user1@test.com", "active": True},
    {"id": 2, "name": "User 2", "email": "user2@test.com", "active": True},
    {"id": 3, "name": "User 3", "email": "user3@test.com", "active": False},
]

TEST_EMBEDDINGS = [
    {
        "id": 1,
        "content": "Kailash SDK is a powerful workflow automation tool",
        "metadata": {"category": "documentation"},
    },
    {
        "id": 2,
        "content": "PostgreSQL with pgvector enables similarity search",
        "metadata": {"category": "database"},
    },
    {
        "id": 3,
        "content": "Async operations improve performance significantly",
        "metadata": {"category": "performance"},
    },
]