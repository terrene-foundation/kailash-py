-- Performance Testing Database Schema
-- Optimized tables for load testing scenarios

-- Extensions for performance testing
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "btree_gin";
CREATE EXTENSION IF NOT EXISTS "btree_gist";

-- Performance test results table
CREATE TABLE IF NOT EXISTS test_results (
    id SERIAL PRIMARY KEY,
    test_run_id UUID DEFAULT uuid_generate_v4(),
    test_type VARCHAR(50) NOT NULL,
    concurrent_workflows INTEGER NOT NULL,
    total_workflows INTEGER NOT NULL,
    successful_workflows INTEGER DEFAULT 0,
    failed_workflows INTEGER DEFAULT 0,
    execution_time DECIMAL(10,3) NOT NULL,
    throughput DECIMAL(10,3) DEFAULT 0,
    avg_latency DECIMAL(10,3) DEFAULT 0,
    p50_latency DECIMAL(10,3) DEFAULT 0,
    p90_latency DECIMAL(10,3) DEFAULT 0,
    p99_latency DECIMAL(10,3) DEFAULT 0,
    peak_memory_mb DECIMAL(10,2) DEFAULT 0,
    peak_cpu_percent DECIMAL(5,2) DEFAULT 0,
    peak_connections INTEGER DEFAULT 0,
    error_rate DECIMAL(5,2) DEFAULT 0,
    timeout_errors INTEGER DEFAULT 0,
    connection_errors INTEGER DEFAULT 0,
    resource_exhaustion_errors INTEGER DEFAULT 0,
    test_start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    test_end_time TIMESTAMP,
    test_config JSONB,
    metrics_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes for performance
    INDEX idx_test_results_run_id (test_run_id),
    INDEX idx_test_results_type (test_type),
    INDEX idx_test_results_start_time (test_start_time),
    INDEX idx_test_results_throughput (throughput),
    INDEX idx_test_results_config (test_config) USING GIN
);

-- Workflow execution details table
CREATE TABLE IF NOT EXISTS workflow_executions (
    id BIGSERIAL PRIMARY KEY,
    test_run_id UUID NOT NULL,
    workflow_id VARCHAR(100) NOT NULL,
    workflow_type VARCHAR(50) NOT NULL,
    node_count INTEGER DEFAULT 0,
    execution_time DECIMAL(10,3) NOT NULL,
    success BOOLEAN DEFAULT false,
    error_message TEXT,
    resource_usage JSONB,
    node_execution_times JSONB,
    connection_metrics JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes
    INDEX idx_workflow_executions_run_id (test_run_id),
    INDEX idx_workflow_executions_type (workflow_type),
    INDEX idx_workflow_executions_success (success),
    INDEX idx_workflow_executions_execution_time (execution_time),
    INDEX idx_workflow_executions_created_at (created_at)
);

-- Resource usage metrics table (time series)
CREATE TABLE IF NOT EXISTS resource_metrics (
    id BIGSERIAL PRIMARY KEY,
    test_run_id UUID NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cpu_percent DECIMAL(5,2),
    memory_mb DECIMAL(10,2),
    disk_io_read_mb DECIMAL(10,2),
    disk_io_write_mb DECIMAL(10,2),
    network_io_sent_mb DECIMAL(10,2),
    network_io_recv_mb DECIMAL(10,2),
    open_connections INTEGER,
    active_threads INTEGER,
    gc_collections INTEGER DEFAULT 0,
    gc_time_ms DECIMAL(10,2) DEFAULT 0,

    -- Time series partitioning
    INDEX idx_resource_metrics_run_timestamp (test_run_id, timestamp),
    INDEX idx_resource_metrics_timestamp (timestamp)
);

-- Database connection metrics
CREATE TABLE IF NOT EXISTS database_metrics (
    id BIGSERIAL PRIMARY KEY,
    test_run_id UUID NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    database_type VARCHAR(20) NOT NULL, -- postgresql, mysql, redis, mongodb
    active_connections INTEGER DEFAULT 0,
    idle_connections INTEGER DEFAULT 0,
    waiting_connections INTEGER DEFAULT 0,
    max_connections INTEGER DEFAULT 0,
    connection_errors INTEGER DEFAULT 0,
    query_time_avg DECIMAL(10,3) DEFAULT 0,
    query_time_max DECIMAL(10,3) DEFAULT 0,
    slow_queries INTEGER DEFAULT 0,
    deadlocks INTEGER DEFAULT 0,
    lock_waits INTEGER DEFAULT 0,

    INDEX idx_database_metrics_run_timestamp (test_run_id, timestamp),
    INDEX idx_database_metrics_type (database_type)
);

-- Error tracking table
CREATE TABLE IF NOT EXISTS error_events (
    id BIGSERIAL PRIMARY KEY,
    test_run_id UUID NOT NULL,
    workflow_id VARCHAR(100),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_type VARCHAR(50) NOT NULL,
    error_category VARCHAR(30) NOT NULL, -- timeout, connection, resource, application
    error_message TEXT,
    stack_trace TEXT,
    node_id VARCHAR(100),
    retry_count INTEGER DEFAULT 0,
    recovery_time DECIMAL(10,3),
    context_data JSONB,

    INDEX idx_error_events_run_id (test_run_id),
    INDEX idx_error_events_type (error_type),
    INDEX idx_error_events_category (error_category),
    INDEX idx_error_events_timestamp (timestamp)
);

-- Performance regression tracking
CREATE TABLE IF NOT EXISTS regression_analysis (
    id SERIAL PRIMARY KEY,
    baseline_run_id UUID NOT NULL,
    current_run_id UUID NOT NULL,
    analysis_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    throughput_change_percent DECIMAL(8,2),
    latency_change_percent DECIMAL(8,2),
    memory_change_percent DECIMAL(8,2),
    error_rate_change_percent DECIMAL(8,2),
    regression_detected BOOLEAN DEFAULT false,
    regression_severity VARCHAR(20), -- none, minor, major, critical
    recommendations TEXT[],
    analysis_data JSONB,

    INDEX idx_regression_analysis_runs (baseline_run_id, current_run_id),
    INDEX idx_regression_analysis_timestamp (analysis_timestamp),
    INDEX idx_regression_analysis_severity (regression_severity)
);

-- Test data tables for workflow testing

-- Large table for performance testing
CREATE TABLE IF NOT EXISTS test_data_large (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    value INTEGER NOT NULL,
    category VARCHAR(20) NOT NULL,
    description TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_test_data_large_category (category),
    INDEX idx_test_data_large_value (value),
    INDEX idx_test_data_large_created_at (created_at),
    INDEX idx_test_data_large_metadata (metadata) USING GIN
);

-- Wide table for testing column performance
CREATE TABLE IF NOT EXISTS test_data_wide (
    id SERIAL PRIMARY KEY,
    col_01 VARCHAR(50), col_02 VARCHAR(50), col_03 VARCHAR(50), col_04 VARCHAR(50), col_05 VARCHAR(50),
    col_06 VARCHAR(50), col_07 VARCHAR(50), col_08 VARCHAR(50), col_09 VARCHAR(50), col_10 VARCHAR(50),
    col_11 VARCHAR(50), col_12 VARCHAR(50), col_13 VARCHAR(50), col_14 VARCHAR(50), col_15 VARCHAR(50),
    col_16 VARCHAR(50), col_17 VARCHAR(50), col_18 VARCHAR(50), col_19 VARCHAR(50), col_20 VARCHAR(50),
    col_21 INTEGER, col_22 INTEGER, col_23 INTEGER, col_24 INTEGER, col_25 INTEGER,
    col_26 INTEGER, col_27 INTEGER, col_28 INTEGER, col_29 INTEGER, col_30 INTEGER,
    col_31 DECIMAL(10,2), col_32 DECIMAL(10,2), col_33 DECIMAL(10,2), col_34 DECIMAL(10,2), col_35 DECIMAL(10,2),
    col_36 BOOLEAN, col_37 BOOLEAN, col_38 BOOLEAN, col_39 BOOLEAN, col_40 BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Normalized tables for join testing
CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    country VARCHAR(100),
    registration_date DATE DEFAULT CURRENT_DATE,
    status VARCHAR(20) DEFAULT 'active',

    INDEX idx_customers_email (email),
    INDEX idx_customers_country (country),
    INDEX idx_customers_status (status)
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
    order_date DATE DEFAULT CURRENT_DATE,
    total_amount DECIMAL(12,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',

    INDEX idx_orders_customer_id (customer_id),
    INDEX idx_orders_date (order_date),
    INDEX idx_orders_status (status),
    INDEX idx_orders_amount (total_amount)
);

CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
    product_name VARCHAR(255) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,

    INDEX idx_order_items_order_id (order_id),
    INDEX idx_order_items_product (product_name)
);

-- Insert sample data for testing

-- Insert test data
INSERT INTO test_data_large (name, value, category, description, metadata)
SELECT
    'test_item_' || generate_series,
    (random() * 1000)::integer,
    CASE (random() * 4)::integer
        WHEN 0 THEN 'A'
        WHEN 1 THEN 'B'
        WHEN 2 THEN 'C'
        WHEN 3 THEN 'D'
        ELSE 'E'
    END,
    'Performance test data item ' || generate_series,
    jsonb_build_object(
        'test_run', 'initial_data',
        'priority', (random() * 10)::integer,
        'tags', ARRAY['performance', 'test', 'data']
    )
FROM generate_series(1, 100000); -- 100K records

-- Insert customer data
INSERT INTO customers (name, email, country, registration_date, status)
SELECT
    'Customer ' || generate_series,
    'customer' || generate_series || '@example.com',
    CASE (random() * 5)::integer
        WHEN 0 THEN 'USA'
        WHEN 1 THEN 'Canada'
        WHEN 2 THEN 'UK'
        WHEN 3 THEN 'Germany'
        WHEN 4 THEN 'France'
        ELSE 'Other'
    END,
    CURRENT_DATE - (random() * 365)::integer,
    CASE (random() * 3)::integer
        WHEN 0 THEN 'active'
        WHEN 1 THEN 'inactive'
        ELSE 'pending'
    END
FROM generate_series(1, 10000); -- 10K customers

-- Insert order data
INSERT INTO orders (customer_id, order_date, total_amount, status)
SELECT
    (random() * 10000 + 1)::integer,
    CURRENT_DATE - (random() * 180)::integer,
    (random() * 1000 + 10)::decimal(12,2),
    CASE (random() * 4)::integer
        WHEN 0 THEN 'pending'
        WHEN 1 THEN 'processing'
        WHEN 2 THEN 'shipped'
        WHEN 3 THEN 'delivered'
        ELSE 'cancelled'
    END
FROM generate_series(1, 50000); -- 50K orders

-- Insert order items
INSERT INTO order_items (order_id, product_name, quantity, unit_price)
SELECT
    (random() * 50000 + 1)::integer,
    'Product_' || (random() * 1000 + 1)::integer,
    (random() * 5 + 1)::integer,
    (random() * 100 + 5)::decimal(10,2)
FROM generate_series(1, 150000); -- 150K order items (avg 3 items per order)

-- Create views for common queries
CREATE OR REPLACE VIEW customer_order_summary AS
SELECT
    c.id,
    c.name,
    c.email,
    c.country,
    COUNT(o.id) as total_orders,
    SUM(o.total_amount) as total_spent,
    AVG(o.total_amount) as avg_order_value,
    MAX(o.order_date) as last_order_date
FROM customers c
LEFT JOIN orders o ON c.id = o.customer_id
GROUP BY c.id, c.name, c.email, c.country;

CREATE OR REPLACE VIEW order_performance_metrics AS
SELECT
    DATE_TRUNC('day', order_date) as order_day,
    status,
    COUNT(*) as order_count,
    SUM(total_amount) as daily_revenue,
    AVG(total_amount) as avg_order_value
FROM orders
GROUP BY DATE_TRUNC('day', order_date), status;

-- Performance monitoring functions

CREATE OR REPLACE FUNCTION get_test_performance_summary(run_id UUID)
RETURNS TABLE (
    metric_name VARCHAR,
    metric_value DECIMAL,
    unit VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT 'Total Workflows'::VARCHAR, tr.total_workflows::DECIMAL, 'count'::VARCHAR FROM test_results tr WHERE tr.test_run_id = run_id
    UNION ALL
    SELECT 'Success Rate'::VARCHAR, (tr.successful_workflows::DECIMAL / tr.total_workflows * 100), '%'::VARCHAR FROM test_results tr WHERE tr.test_run_id = run_id
    UNION ALL
    SELECT 'Throughput'::VARCHAR, tr.throughput, 'workflows/sec'::VARCHAR FROM test_results tr WHERE tr.test_run_id = run_id
    UNION ALL
    SELECT 'Average Latency'::VARCHAR, tr.avg_latency, 'seconds'::VARCHAR FROM test_results tr WHERE tr.test_run_id = run_id
    UNION ALL
    SELECT 'P99 Latency'::VARCHAR, tr.p99_latency, 'seconds'::VARCHAR FROM test_results tr WHERE tr.test_run_id = run_id
    UNION ALL
    SELECT 'Peak Memory'::VARCHAR, tr.peak_memory_mb, 'MB'::VARCHAR FROM test_results tr WHERE tr.test_run_id = run_id
    UNION ALL
    SELECT 'Peak CPU'::VARCHAR, tr.peak_cpu_percent, '%'::VARCHAR FROM test_results tr WHERE tr.test_run_id = run_id;
END;
$$ LANGUAGE plpgsql;

-- Function to clean old test data
CREATE OR REPLACE FUNCTION cleanup_old_test_data(days_to_keep INTEGER DEFAULT 7)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER := 0;
BEGIN
    -- Delete old test results
    DELETE FROM test_results WHERE created_at < NOW() - (days_to_keep || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    -- Delete old workflow executions
    DELETE FROM workflow_executions WHERE created_at < NOW() - (days_to_keep || ' days')::INTERVAL;

    -- Delete old resource metrics
    DELETE FROM resource_metrics WHERE timestamp < NOW() - (days_to_keep || ' days')::INTERVAL;

    -- Delete old database metrics
    DELETE FROM database_metrics WHERE timestamp < NOW() - (days_to_keep || ' days')::INTERVAL;

    -- Delete old error events
    DELETE FROM error_events WHERE timestamp < NOW() - (days_to_keep || ' days')::INTERVAL;

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Update statistics for better query performance
ANALYZE test_data_large;
ANALYZE customers;
ANALYZE orders;
ANALYZE order_items;

-- Performance monitoring setup complete
SELECT 'Performance testing database schema initialized successfully' as status;
