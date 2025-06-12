-- Admin Framework Database Schema for Session 066
-- This extends the base Kailash schema with comprehensive admin tables

-- Ensure we're using the kailash schema
SET search_path TO kailash, public;

-- Enhanced Users table for admin framework
-- (Extends the basic users table with admin fields)
ALTER TABLE users
ADD COLUMN IF NOT EXISTS user_id VARCHAR(255) UNIQUE,
ADD COLUMN IF NOT EXISTS username VARCHAR(255) UNIQUE,
ADD COLUMN IF NOT EXISTS first_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS last_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS password_hash TEXT,
ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'active',
ADD COLUMN IF NOT EXISTS roles JSONB DEFAULT '[]',
ADD COLUMN IF NOT EXISTS attributes JSONB DEFAULT '{}',
ADD COLUMN IF NOT EXISTS last_login TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS force_password_change BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS created_by VARCHAR(255) DEFAULT 'system';

-- Create indexes for admin operations
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id);

-- Roles table for RBAC
CREATE TABLE IF NOT EXISTS roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    role_id VARCHAR(255) UNIQUE NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    permissions JSONB DEFAULT '[]',
    parent_role_id VARCHAR(255),
    attributes JSONB DEFAULT '{}',
    is_system BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT 'system',
    UNIQUE(tenant_id, name)
);

-- User-Role assignments
CREATE TABLE IF NOT EXISTS user_roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,
    role_id VARCHAR(255) NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(255),
    expires_at TIMESTAMP WITH TIME ZONE,
    attributes JSONB DEFAULT '{}',
    UNIQUE(user_id, role_id, tenant_id)
);

-- Permissions table for fine-grained access control
CREATE TABLE IF NOT EXISTS permissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    permission_id VARCHAR(255) UNIQUE NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    resource_type VARCHAR(100) NOT NULL,
    resource_id VARCHAR(255),
    permission VARCHAR(100) NOT NULL,
    conditions JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, resource_type, resource_id, permission)
);

-- Enhanced audit logs for admin operations
CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    audit_id VARCHAR(255) UNIQUE NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id VARCHAR(255),
    event_type VARCHAR(100) NOT NULL,
    severity VARCHAR(50) DEFAULT 'low',
    action VARCHAR(255) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    description TEXT,
    metadata JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    session_id VARCHAR(255),
    status VARCHAR(50) DEFAULT 'success',
    error_message TEXT,
    compliance_tags JSONB DEFAULT '[]',
    retention_days INTEGER DEFAULT 2555, -- 7 years for compliance
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    indexed_at TIMESTAMP WITH TIME ZONE
);

-- Security events table
CREATE TABLE IF NOT EXISTS security_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id VARCHAR(255) UNIQUE NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    threat_level VARCHAR(50) NOT NULL DEFAULT 'low',
    user_id VARCHAR(255),
    source_ip INET,
    target_resource VARCHAR(255),
    description TEXT,
    indicators JSONB DEFAULT '{}',
    detection_method VARCHAR(100),
    response_actions JSONB DEFAULT '[]',
    risk_score INTEGER DEFAULT 0,
    mitigated BOOLEAN DEFAULT false,
    mitigated_at TIMESTAMP WITH TIME ZONE,
    mitigated_by VARCHAR(255),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- Session management
CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(255) UNIQUE NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    ip_address INET,
    user_agent TEXT,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}'
);

-- Failed login attempts tracking
CREATE TABLE IF NOT EXISTS failed_login_attempts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(255),
    email VARCHAR(255),
    ip_address INET,
    user_agent TEXT,
    reason VARCHAR(255),
    attempted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE
);

-- Password reset tokens
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,
    token_hash VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_roles_tenant ON roles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_roles_parent ON roles(parent_role_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role_id);
CREATE INDEX IF NOT EXISTS idx_permissions_resource ON permissions(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_admin_audit_tenant_created ON admin_audit_logs(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_user_created ON admin_audit_logs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_event_type ON admin_audit_logs(event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_compliance ON admin_audit_logs(compliance_tags);
CREATE INDEX IF NOT EXISTS idx_security_events_tenant ON security_events(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_events_threat ON security_events(threat_level, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_events_user ON security_events(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON user_sessions(is_active, expires_at);
CREATE INDEX IF NOT EXISTS idx_failed_logins_ip ON failed_login_attempts(ip_address, attempted_at DESC);

-- Create admin database for standalone admin operations
CREATE DATABASE IF NOT EXISTS kailash_admin;

-- Connect to admin database
\c kailash_admin;

-- Create admin schema in admin database
CREATE SCHEMA IF NOT EXISTS admin;
SET search_path TO admin, public;

-- Create the same tables in admin database
-- (This allows admin framework to work independently)

-- Copy all table definitions from above...
-- (In practice, you'd use the same CREATE TABLE statements)

-- Insert default admin roles
INSERT INTO roles (role_id, tenant_id, name, description, permissions, is_system)
VALUES
(
    'super_admin',
    'b1e7a5d4-7e9c-4f3a-9c2b-1a3b5c7d9e1f',
    'Super Administrator',
    'Full system access with all permissions',
    '["*"]',
    true
),
(
    'admin',
    'b1e7a5d4-7e9c-4f3a-9c2b-1a3b5c7d9e1f',
    'Administrator',
    'Administrative access to most features',
    '["users:*", "roles:*", "audit:read", "security:read"]',
    true
),
(
    'manager',
    'b1e7a5d4-7e9c-4f3a-9c2b-1a3b5c7d9e1f',
    'Manager',
    'Management access to team resources',
    '["users:read", "users:update", "audit:read", "reports:*"]',
    true
),
(
    'employee',
    'b1e7a5d4-7e9c-4f3a-9c2b-1a3b5c7d9e1f',
    'Employee',
    'Basic employee access',
    '["profile:read", "profile:update"]',
    true
)
ON CONFLICT (role_id) DO NOTHING;

-- Create triggers for updated_at
CREATE TRIGGER update_roles_updated_at BEFORE UPDATE ON roles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA admin TO kailash;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA admin TO kailash;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA admin TO kailash;
