# Docker infrastructure configuration
# Standardized test environment configuration
# Use ./test-env script to manage Docker services
import os

# PostgreSQL configuration - using Docker container on port 5434
DATABASE_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5434")),
    "database": os.getenv("DB_NAME", "kailash_test"),
    "user": os.getenv("DB_USER", "test_user"),
    "password": os.getenv("DB_PASSWORD", "test_password"),
}

# Redis configuration - using test Redis on port 6380
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", "6380")),
}

# MongoDB configuration
MONGODB_CONFIG = {
    "host": os.getenv("MONGO_HOST", "localhost"),
    "port": int(os.getenv("MONGO_PORT", "27017")),
    "username": os.getenv("MONGO_USER", "kailash"),
    "password": os.getenv("MONGO_PASSWORD", "kailash123"),
}

# Kafka configuration
KAFKA_CONFIG = {
    "bootstrap_servers": os.getenv("KAFKA_SERVERS", "localhost:9092"),
}

# MySQL configuration - using test MySQL on port 3307
MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", "3307")),
    "database": os.getenv("MYSQL_DATABASE", "kailash_test"),
    "user": os.getenv("MYSQL_USER", "kailash_test"),
    "password": os.getenv("MYSQL_PASSWORD", "test_password"),
}

# Ollama configuration - using test Ollama on port 11435
OLLAMA_CONFIG = {
    "host": os.getenv("OLLAMA_HOST", "localhost"),
    "port": int(os.getenv("OLLAMA_PORT", "11435")),
    "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11435"),
}

# OAuth2 configuration
OAUTH2_CONFIG = {
    "host": os.getenv("OAUTH2_HOST", "http://localhost:8080"),
}

# Qdrant configuration
QDRANT_CONFIG = {
    "host": os.getenv("QDRANT_HOST", "localhost"),
    "port": int(os.getenv("QDRANT_PORT", "6333")),
}


# Connection string helpers
def get_postgres_connection_string(database=None):
    """Get PostgreSQL connection string for the Docker setup."""
    db = database or DATABASE_CONFIG["database"]
    return (
        f"postgresql://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}"
        f"@{DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{db}"
    )


def get_mongodb_connection_string(database="kailash"):
    """Get MongoDB connection string for the Docker setup."""
    return (
        f"mongodb://{MONGODB_CONFIG['username']}:{MONGODB_CONFIG['password']}"
        f"@{MONGODB_CONFIG['host']}:{MONGODB_CONFIG['port']}/{database}"
    )


def get_redis_url():
    """Get Redis URL for the Docker setup."""
    return f"redis://{REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}"


def get_mysql_connection_string(database=None):
    """Get MySQL connection string for the Docker setup."""
    db = database or MYSQL_CONFIG["database"]
    return (
        f"mysql://{MYSQL_CONFIG['user']}:{MYSQL_CONFIG['password']}"
        f"@{MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}/{db}"
    )


# Test database names
TEST_DATABASES = {
    "admin": "kailash_admin",
    "test": "kailash_test",
    "enterprise": "kailash_enterprise",
    "dev": "kailash_dev",
}


async def ensure_docker_services():
    """Ensure Docker services are available."""
    import asyncio

    import httpx

    try:
        # Check PostgreSQL
        import asyncpg

        conn = await asyncpg.connect(get_postgres_connection_string())
        await conn.close()

        # Check Redis
        import redis

        r = redis.Redis(**REDIS_CONFIG)
        r.ping()

        # Check MySQL
        import pymysql

        conn = pymysql.connect(
            host=MYSQL_CONFIG["host"],
            port=MYSQL_CONFIG["port"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"],
            database=MYSQL_CONFIG["database"],
        )
        conn.close()

        # Check Ollama
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://{OLLAMA_CONFIG['host']}:{OLLAMA_CONFIG['port']}/api/tags",
                timeout=5.0,
            )
            if response.status_code != 200:
                return False

        return True
    except Exception as e:
        print(f"Docker services check failed: {e}")
        return False
