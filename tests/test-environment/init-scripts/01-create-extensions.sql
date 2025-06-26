-- PostgreSQL extensions needed for Kailash SDK testing
-- Run as superuser during database initialization

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pgvector for embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable pg_trgm for text search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Enable btree_gin for better indexing
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- Enable hstore for key-value storage
CREATE EXTENSION IF NOT EXISTS hstore;

-- Grant necessary permissions to test user
GRANT ALL PRIVILEGES ON DATABASE kailash_test TO test_user;
GRANT ALL ON SCHEMA public TO test_user;
