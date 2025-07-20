-- Create PostgreSQL extensions for Kailash SDK Template
-- This script runs during database initialization

-- Enable pgvector extension for vector operations
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable uuid-ossp for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pg_stat_statements for query performance monitoring
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Enable pg_trgm for text similarity search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Enable btree_gin for advanced indexing
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- Enable hstore for key-value storage
CREATE EXTENSION IF NOT EXISTS hstore;

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_gin_trgm ON pg_trgm USING gin (word gin_trgm_ops);

-- Log successful extension creation
DO $$
BEGIN
    RAISE NOTICE 'PostgreSQL extensions created successfully for Kailash SDK Template';
END $$;