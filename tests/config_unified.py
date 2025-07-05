"""Unified test configuration for all test environments.

This module provides consistent configuration across all tests to ensure
they use the correct Docker services.
"""

import os

# Database configuration - matches Docker setup
POSTGRES_CONFIG = {
    "database_type": "postgresql",
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5434")),
    "database": os.getenv("DB_NAME", "kailash_test"),
    "user": os.getenv("DB_USER", "test_user"),
    "password": os.getenv("DB_PASSWORD", "test_password"),
}

# Connection string for direct use
POSTGRES_URL = (
    f"postgresql://{POSTGRES_CONFIG['user']}:{POSTGRES_CONFIG['password']}"
    f"@{POSTGRES_CONFIG['host']}:{POSTGRES_CONFIG['port']}/{POSTGRES_CONFIG['database']}"
)

# MySQL configuration
MYSQL_CONFIG = {
    "database_type": "mysql",
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3307")),
    "database": os.getenv("MYSQL_DATABASE", "kailash_test"),
    "user": os.getenv("MYSQL_USER", "kailash_test"),
    "password": os.getenv("MYSQL_PASSWORD", "test_password"),
}

# MySQL connection string with pymysql driver
MYSQL_URL = (
    f"mysql+pymysql://{MYSQL_CONFIG['user']}:{MYSQL_CONFIG['password']}"
    f"@{MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}"
)

# Redis configuration
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", "6380")),
    "db": 0,
}

REDIS_URL = f"redis://{REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}"

# Ollama configuration
OLLAMA_CONFIG = {
    "host": os.getenv("OLLAMA_HOST", "localhost"),
    "port": int(os.getenv("OLLAMA_PORT", "11435")),
    "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11435"),
    "model": os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
}

# MongoDB configuration
MONGODB_CONFIG = {
    "host": os.getenv("MONGO_HOST", "localhost"),
    "port": int(os.getenv("MONGO_PORT", "27017")),
    "username": os.getenv("MONGO_USER", "kailash"),
    "password": os.getenv("MONGO_PASSWORD", "kailash123"),
    "database": "kailash_test",
}

MONGODB_URL = (
    f"mongodb://{MONGODB_CONFIG['username']}:{MONGODB_CONFIG['password']}"
    f"@{MONGODB_CONFIG['host']}:{MONGODB_CONFIG['port']}/{MONGODB_CONFIG['database']}"
)

# Test database names
TEST_DATABASES = {
    "default": "kailash_test",
    "admin": "kailash_admin",
    "enterprise": "kailash_enterprise",
}


# Check if Docker services are available
def check_docker_services():
    """Check if Docker test services are available."""
    try:
        import httpx

        # Check Ollama
        response = httpx.get(OLLAMA_CONFIG["base_url"] + "/api/version", timeout=1)
        ollama_available = response.status_code == 200
    except:
        ollama_available = False

    try:
        import redis

        r = redis.Redis(**REDIS_CONFIG)
        r.ping()
        redis_available = True
    except:
        redis_available = False

    try:
        import psycopg2

        conn = psycopg2.connect(
            host=POSTGRES_CONFIG["host"],
            port=POSTGRES_CONFIG["port"],
            database=POSTGRES_CONFIG["database"],
            user=POSTGRES_CONFIG["user"],
            password=POSTGRES_CONFIG["password"],
        )
        conn.close()
        postgres_available = True
    except:
        postgres_available = False

    return {
        "postgres": postgres_available,
        "redis": redis_available,
        "ollama": ollama_available,
    }
