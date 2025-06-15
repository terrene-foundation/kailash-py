# Docker infrastructure configuration
import os

# PostgreSQL configuration - using Docker on port 5433
DATABASE_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5433")),
    "database": os.getenv("DB_NAME", "kailash_test"),
    "user": os.getenv("DB_USER", "admin"),
    "password": os.getenv("DB_PASSWORD", "admin"),
}

# Redis configuration
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", "6379")),
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

# Ollama configuration
OLLAMA_CONFIG = {
    "host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
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


# Test database names
TEST_DATABASES = {
    "admin": "kailash_admin",
    "test": "kailash_test",
    "enterprise": "kailash_enterprise",
    "dev": "kailash_dev",
}
