-- Unified database initialization for Kailash SDK
-- This script sets up all necessary databases, tables, and extensions

-- Create pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create all necessary databases
CREATE DATABASE kailash_test;
CREATE DATABASE kailash_enterprise;
CREATE DATABASE kailash_dev;

-- Grant all privileges to admin user
GRANT ALL PRIVILEGES ON DATABASE kailash_admin TO admin;
GRANT ALL PRIVILEGES ON DATABASE kailash_test TO admin;
GRANT ALL PRIVILEGES ON DATABASE kailash_enterprise TO admin;
GRANT ALL PRIVILEGES ON DATABASE kailash_dev TO admin;

-- =====================================================
-- Setup kailash_admin database (main database)
-- =====================================================
\c kailash_admin;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Core user management tables
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_superuser BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
    granted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS permissions (
    id SERIAL PRIMARY KEY,
    resource VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(resource, action)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
    permission_id INTEGER REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

-- Audit and security tables
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    resource VARCHAR(100),
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Workflow tables
CREATE TABLE IF NOT EXISTS workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    definition JSONB NOT NULL,
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workflow_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID REFERENCES workflows(id),
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    result JSONB,
    error TEXT,
    metadata JSONB DEFAULT '{}'
);

-- Vector embeddings table
CREATE TABLE IF NOT EXISTS embeddings (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(384),  -- for all-MiniLM-L6-v2
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_sessions_token ON sessions(token_hash);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);
CREATE INDEX idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_created ON audit_logs(created_at);
CREATE INDEX idx_embeddings_vector ON embeddings USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_workflows_created_by ON workflows(created_by);
CREATE INDEX idx_workflow_executions_workflow ON workflow_executions(workflow_id);
CREATE INDEX idx_workflow_executions_status ON workflow_executions(status);

-- Insert default data
INSERT INTO roles (name, description) VALUES
    ('admin', 'System administrator with full access'),
    ('user', 'Regular user with basic access'),
    ('viewer', 'Read-only access')
ON CONFLICT (name) DO NOTHING;

INSERT INTO permissions (resource, action) VALUES
    ('workflow', 'create'),
    ('workflow', 'read'),
    ('workflow', 'update'),
    ('workflow', 'delete'),
    ('workflow', 'execute'),
    ('user', 'create'),
    ('user', 'read'),
    ('user', 'update'),
    ('user', 'delete'),
    ('system', 'admin')
ON CONFLICT (resource, action) DO NOTHING;

-- Admin role gets all permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT 1, id FROM permissions
ON CONFLICT DO NOTHING;

-- User role gets workflow permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT 2, id FROM permissions WHERE resource = 'workflow'
ON CONFLICT DO NOTHING;

-- Viewer role gets read permissions
INSERT INTO role_permissions (role_id, permission_id)
SELECT 3, id FROM permissions WHERE action = 'read'
ON CONFLICT DO NOTHING;

-- =====================================================
-- Setup kailash_test database
-- =====================================================
\c kailash_test;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Test-specific tables for unit and integration tests
CREATE TABLE IF NOT EXISTS test_data (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    value JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- Setup kailash_enterprise database
-- =====================================================
\c kailash_enterprise;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Multi-tenant schema
CREATE SCHEMA IF NOT EXISTS tenant_shared;
CREATE SCHEMA IF NOT EXISTS tenant_default;

-- Shared tenant configuration
CREATE TABLE IF NOT EXISTS tenant_shared.tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) UNIQUE NOT NULL,
    subdomain VARCHAR(100) UNIQUE NOT NULL,
    settings JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Enterprise features
CREATE TABLE IF NOT EXISTS tenant_shared.sso_providers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenant_shared.tenants(id),
    provider_type VARCHAR(50) NOT NULL,
    configuration JSONB NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Grant permissions
GRANT ALL ON SCHEMA tenant_shared TO admin;
GRANT ALL ON SCHEMA tenant_default TO admin;
GRANT ALL ON ALL TABLES IN SCHEMA tenant_shared TO admin;
GRANT ALL ON ALL TABLES IN SCHEMA tenant_default TO admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA tenant_shared TO admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA tenant_default TO admin;

-- Insert test tenant
INSERT INTO tenant_shared.tenants (name, subdomain, settings) VALUES
    ('Test Tenant', 'test', '{"features": ["workflows", "ai", "security"]}')
ON CONFLICT (subdomain) DO NOTHING;

-- =====================================================
-- Setup kailash_dev database
-- =====================================================
\c kailash_dev;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Development tables for examples and experimentation
CREATE TABLE IF NOT EXISTS example_data (
    id SERIAL PRIMARY KEY,
    category VARCHAR(100),
    content JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Grant final permissions
\c kailash_admin;
GRANT ALL ON ALL TABLES IN SCHEMA public TO admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO admin;
