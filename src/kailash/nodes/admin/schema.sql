-- Unified Admin Node Database Schema
-- Complete RBAC/ABAC system with user management and permission checking
-- Production-ready schema for Kailash Admin Nodes

-- =====================================================
-- Core User Management
-- =====================================================

-- Users table - Central user registry
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(255) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(255),
    password_hash VARCHAR(255), -- Optional, for local auth
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    display_name VARCHAR(255),

    -- Admin node compatibility fields
    roles JSONB DEFAULT '[]', -- For compatibility with PermissionCheckNode
    attributes JSONB DEFAULT '{}', -- User attributes for ABAC

    -- Status and lifecycle
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'suspended', 'pending', 'deleted')),
    is_active BOOLEAN DEFAULT TRUE,
    is_system_user BOOLEAN DEFAULT FALSE,

    -- Multi-tenancy
    tenant_id VARCHAR(255) NOT NULL,

    -- External auth integration
    external_auth_id VARCHAR(255), -- For SSO integration
    auth_provider VARCHAR(100), -- 'local', 'oauth2', 'saml', etc.

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT 'system',
    last_login_at TIMESTAMP WITH TIME ZONE,

    -- Constraints
    UNIQUE(email, tenant_id),
    UNIQUE(username, tenant_id) -- Allow same username across tenants
);

-- =====================================================
-- Role-Based Access Control (RBAC)
-- =====================================================

-- Roles table - Hierarchical role definitions
CREATE TABLE IF NOT EXISTS roles (
    role_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    role_type VARCHAR(50) DEFAULT 'custom' CHECK (role_type IN ('system', 'custom', 'template', 'temporary')),

    -- RBAC permissions and hierarchy
    permissions JSONB DEFAULT '[]', -- Direct permissions
    parent_roles JSONB DEFAULT '[]', -- Role inheritance
    child_roles JSONB DEFAULT '[]', -- Derived roles (maintained automatically)

    -- ABAC attributes and conditions
    attributes JSONB DEFAULT '{}', -- Role attributes
    conditions JSONB DEFAULT '{}', -- Dynamic conditions for role activation

    -- Lifecycle and constraints
    is_active BOOLEAN DEFAULT TRUE,
    is_system_role BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMP WITH TIME ZONE, -- For temporary roles

    -- Multi-tenancy
    tenant_id VARCHAR(255) NOT NULL,

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT 'system',

    -- Constraints
    UNIQUE(name, tenant_id)
);

-- User Role Assignments - Many-to-many with metadata
CREATE TABLE IF NOT EXISTS user_role_assignments (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    role_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,

    -- Assignment metadata
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(255) DEFAULT 'system',
    expires_at TIMESTAMP WITH TIME ZONE, -- For temporary assignments

    -- Conditional assignments (ABAC)
    conditions JSONB DEFAULT '{}', -- When this assignment is active
    context_requirements JSONB DEFAULT '{}', -- Required context for activation

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_inherited BOOLEAN DEFAULT FALSE, -- True if inherited from group/org

    -- Constraints
    UNIQUE(user_id, role_id, tenant_id),

    -- Foreign keys (enforced at application level for flexibility)
    CONSTRAINT fk_user_role_user CHECK (user_id IS NOT NULL),
    CONSTRAINT fk_user_role_role CHECK (role_id IS NOT NULL)
);

-- =====================================================
-- Permission Management and Caching
-- =====================================================

-- Permission definitions - Centralized permission registry
CREATE TABLE IF NOT EXISTS permissions (
    permission_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    resource_type VARCHAR(100) NOT NULL, -- 'workflow', 'node', 'data', etc.
    action VARCHAR(100) NOT NULL, -- 'read', 'write', 'execute', etc.

    -- Permission metadata
    scope VARCHAR(100) DEFAULT 'tenant', -- 'global', 'tenant', 'user'
    is_system_permission BOOLEAN DEFAULT FALSE,

    -- ABAC conditions
    default_conditions JSONB DEFAULT '{}', -- Default conditions for this permission
    required_attributes JSONB DEFAULT '{}', -- Required user/resource attributes

    -- Multi-tenancy
    tenant_id VARCHAR(255) NOT NULL,

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    UNIQUE(name, resource_type, action, tenant_id)
);

-- Permission Cache - High-performance permission checking
CREATE TABLE IF NOT EXISTS permission_cache (
    cache_key VARCHAR(512) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    resource VARCHAR(255) NOT NULL,
    permission VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,

    -- Cache result
    result BOOLEAN NOT NULL,
    decision_path JSONB, -- How the decision was made (for auditing)
    context_hash VARCHAR(64), -- Hash of context used for decision

    -- Cache metadata
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    hit_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Indexes will be created separately
    CHECK (expires_at > created_at)
);

-- =====================================================
-- Attribute-Based Access Control (ABAC)
-- =====================================================

-- User Attributes - Dynamic user properties for ABAC
CREATE TABLE IF NOT EXISTS user_attributes (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,

    -- Attribute definition
    attribute_name VARCHAR(255) NOT NULL,
    attribute_value JSONB NOT NULL,
    attribute_type VARCHAR(50) DEFAULT 'string', -- 'string', 'number', 'boolean', 'array', 'object'

    -- Attribute metadata
    is_computed BOOLEAN DEFAULT FALSE, -- True if computed from other attributes
    computation_rule JSONB, -- How to compute this attribute
    source VARCHAR(100) DEFAULT 'manual', -- 'manual', 'computed', 'imported', 'inherited'

    -- Lifecycle
    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMP WITH TIME ZONE,

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT 'system',

    -- Constraints
    UNIQUE(user_id, attribute_name, tenant_id)
);

-- Resource Attributes - Dynamic resource properties for ABAC
CREATE TABLE IF NOT EXISTS resource_attributes (
    id SERIAL PRIMARY KEY,
    resource_id VARCHAR(255) NOT NULL,
    resource_type VARCHAR(100) NOT NULL, -- 'workflow', 'node', 'data', etc.
    tenant_id VARCHAR(255) NOT NULL,

    -- Attribute definition
    attribute_name VARCHAR(255) NOT NULL,
    attribute_value JSONB NOT NULL,
    attribute_type VARCHAR(50) DEFAULT 'string',

    -- Attribute metadata
    is_computed BOOLEAN DEFAULT FALSE,
    computation_rule JSONB,
    source VARCHAR(100) DEFAULT 'manual',

    -- Lifecycle
    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMP WITH TIME ZONE,

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT 'system',

    -- Constraints
    UNIQUE(resource_id, attribute_name, tenant_id)
);

-- =====================================================
-- Sessions and Security
-- =====================================================

-- User Sessions - Track active user sessions
CREATE TABLE IF NOT EXISTS user_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,

    -- Session data
    session_token_hash VARCHAR(255) UNIQUE NOT NULL,
    refresh_token_hash VARCHAR(255),
    device_info JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,

    -- Session lifecycle
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,

    -- Security
    failed_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP WITH TIME ZONE,

    CHECK (expires_at > created_at)
);

-- =====================================================
-- Audit and Compliance
-- =====================================================

-- Admin Audit Log - Comprehensive audit trail
CREATE TABLE IF NOT EXISTS admin_audit_log (
    id SERIAL PRIMARY KEY,

    -- Who, What, When, Where
    user_id VARCHAR(255),
    tenant_id VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100) NOT NULL,
    resource_id VARCHAR(255),

    -- Action details
    operation VARCHAR(100), -- 'create', 'read', 'update', 'delete', 'execute'
    old_values JSONB, -- Before state
    new_values JSONB, -- After state
    context JSONB DEFAULT '{}', -- Request context

    -- Result
    success BOOLEAN NOT NULL,
    error_message TEXT,
    duration_ms INTEGER,

    -- Request metadata
    ip_address INET,
    user_agent TEXT,
    session_id UUID,
    request_id VARCHAR(255),

    -- Timestamp
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- Performance Indexes
-- =====================================================

-- User indexes
CREATE INDEX IF NOT EXISTS idx_users_tenant_status ON users(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_external_auth ON users(external_auth_id, auth_provider);
CREATE INDEX IF NOT EXISTS idx_users_last_login ON users(last_login_at);

-- Role indexes
CREATE INDEX IF NOT EXISTS idx_roles_tenant_active ON roles(tenant_id, is_active);
CREATE INDEX IF NOT EXISTS idx_roles_type ON roles(role_type);
CREATE INDEX IF NOT EXISTS idx_roles_parent_roles ON roles USING GIN(parent_roles);
CREATE INDEX IF NOT EXISTS idx_roles_permissions ON roles USING GIN(permissions);

-- Assignment indexes
CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_role_assignments(user_id, tenant_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_role_assignments(role_id, tenant_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_active ON user_role_assignments(is_active, expires_at);

-- Permission cache indexes
CREATE INDEX IF NOT EXISTS idx_permission_cache_user ON permission_cache(user_id, tenant_id);
CREATE INDEX IF NOT EXISTS idx_permission_cache_expires ON permission_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_permission_cache_resource ON permission_cache(resource, permission);

-- Attribute indexes
CREATE INDEX IF NOT EXISTS idx_user_attributes_user ON user_attributes(user_id, tenant_id);
CREATE INDEX IF NOT EXISTS idx_user_attributes_name ON user_attributes(attribute_name, is_active);
CREATE INDEX IF NOT EXISTS idx_resource_attributes_resource ON resource_attributes(resource_id, resource_type);

-- Session indexes
CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id, tenant_id);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(session_token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON user_sessions(expires_at, is_active);

-- Audit indexes
CREATE INDEX IF NOT EXISTS idx_audit_user ON admin_audit_log(user_id, tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON admin_audit_log(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON admin_audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_action ON admin_audit_log(action, operation);

-- =====================================================
-- Data Integrity and Maintenance
-- =====================================================

-- Auto-update timestamps trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply auto-update triggers with conflict resolution
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_roles_updated_at ON roles;
CREATE TRIGGER update_roles_updated_at BEFORE UPDATE ON roles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_permissions_updated_at ON permissions;
CREATE TRIGGER update_permissions_updated_at BEFORE UPDATE ON permissions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_attributes_updated_at ON user_attributes;
CREATE TRIGGER update_user_attributes_updated_at BEFORE UPDATE ON user_attributes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_resource_attributes_updated_at ON resource_attributes;
CREATE TRIGGER update_resource_attributes_updated_at BEFORE UPDATE ON resource_attributes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Cache cleanup function
CREATE OR REPLACE FUNCTION cleanup_expired_cache()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM permission_cache WHERE expires_at < CURRENT_TIMESTAMP;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Session cleanup function
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM user_sessions WHERE expires_at < CURRENT_TIMESTAMP;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;
