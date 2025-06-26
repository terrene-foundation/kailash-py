-- Sample test data for Kailash SDK integration tests
-- This provides a baseline dataset for consistent testing

-- Insert test tenants
INSERT INTO users (user_id, email, username, tenant_id, status, roles) VALUES
    ('test-admin-1', 'admin@test.com', 'admin', 'test-tenant-1', 'active', '["admin"]'),
    ('test-user-1', 'user1@test.com', 'user1', 'test-tenant-1', 'active', '["user"]'),
    ('test-user-2', 'user2@test.com', 'user2', 'test-tenant-1', 'active', '["user", "developer"]'),
    ('test-admin-2', 'admin@tenant2.com', 'admin2', 'test-tenant-2', 'active', '["admin"]');

-- Insert test roles
INSERT INTO roles (role_id, name, tenant_id, permissions, role_type) VALUES
    ('role-admin', 'admin', 'test-tenant-1', '["*"]', 'system'),
    ('role-user', 'user', 'test-tenant-1', '["read:*", "write:own"]', 'system'),
    ('role-developer', 'developer', 'test-tenant-1', '["read:*", "write:*", "execute:workflows"]', 'custom'),
    ('role-admin-t2', 'admin', 'test-tenant-2', '["*"]', 'system');

-- Insert role assignments
INSERT INTO user_role_assignments (user_id, role_id, tenant_id) VALUES
    ('test-admin-1', 'role-admin', 'test-tenant-1'),
    ('test-user-1', 'role-user', 'test-tenant-1'),
    ('test-user-2', 'role-user', 'test-tenant-1'),
    ('test-user-2', 'role-developer', 'test-tenant-1'),
    ('test-admin-2', 'role-admin-t2', 'test-tenant-2');

-- Insert test permissions
INSERT INTO permissions (permission_id, name, resource_type, action, tenant_id) VALUES
    ('perm-1', 'read_workflows', 'workflow', 'read', 'test-tenant-1'),
    ('perm-2', 'write_workflows', 'workflow', 'write', 'test-tenant-1'),
    ('perm-3', 'execute_workflows', 'workflow', 'execute', 'test-tenant-1'),
    ('perm-4', 'read_data', 'data', 'read', 'test-tenant-1');

-- Create sample tables for data node testing
CREATE TABLE IF NOT EXISTS test_products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    price DECIMAL(10, 2),
    category VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS test_orders (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES test_products(id),
    quantity INTEGER,
    total DECIMAL(10, 2),
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert sample product data
INSERT INTO test_products (name, price, category) VALUES
    ('Laptop', 999.99, 'Electronics'),
    ('Mouse', 29.99, 'Electronics'),
    ('Desk', 299.99, 'Furniture'),
    ('Chair', 199.99, 'Furniture'),
    ('Monitor', 399.99, 'Electronics');

-- Insert sample order data
INSERT INTO test_orders (product_id, quantity, total) VALUES
    (1, 2, 1999.98),
    (2, 5, 149.95),
    (3, 1, 299.99),
    (4, 3, 599.97),
    (5, 2, 799.98);

-- Create vector testing table
CREATE TABLE IF NOT EXISTS test_embeddings (
    id SERIAL PRIMARY KEY,
    content TEXT,
    embedding vector(384),
    metadata JSONB
);

-- Create time series test data
CREATE TABLE IF NOT EXISTS test_metrics (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100),
    value FLOAT,
    tags JSONB,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert sample metrics
INSERT INTO test_metrics (metric_name, value, tags)
SELECT
    'cpu_usage',
    random() * 100,
    jsonb_build_object('host', 'server-' || (i % 5), 'datacenter', 'dc-' || (i % 2))
FROM generate_series(1, 1000) i;

-- Grant permissions on test tables
GRANT ALL ON ALL TABLES IN SCHEMA public TO test_user;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO test_user;
