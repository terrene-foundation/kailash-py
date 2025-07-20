-- Create database schema for Kailash SDK Template
-- This script runs after extensions are created

-- Create application schema
CREATE SCHEMA IF NOT EXISTS app;

-- Create monitoring schema
CREATE SCHEMA IF NOT EXISTS monitoring;

-- Create audit schema
CREATE SCHEMA IF NOT EXISTS audit;

-- Grant permissions to app user
GRANT USAGE ON SCHEMA app TO app_user;
GRANT CREATE ON SCHEMA app TO app_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA app TO app_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA app TO app_user;

-- Grant monitoring permissions
GRANT USAGE ON SCHEMA monitoring TO app_user;
GRANT CREATE ON SCHEMA monitoring TO app_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA monitoring TO app_user;

-- Grant audit permissions (read-only)
GRANT USAGE ON SCHEMA audit TO app_user;
GRANT SELECT ON ALL TABLES IN SCHEMA audit TO app_user;

-- Set default permissions for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT ALL ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT ALL ON SEQUENCES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA monitoring GRANT ALL ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT SELECT ON TABLES TO app_user;

-- Create basic application tables
CREATE TABLE IF NOT EXISTS app.workflows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    definition JSONB NOT NULL,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255),
    is_active BOOLEAN DEFAULT true
);

-- Create workflow execution history
CREATE TABLE IF NOT EXISTS app.workflow_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID REFERENCES app.workflows(id),
    run_id VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    input_data JSONB,
    output_data JSONB,
    error_message TEXT,
    execution_time_ms INTEGER
);

-- Create vector embeddings table
CREATE TABLE IF NOT EXISTS app.embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content TEXT NOT NULL,
    embedding VECTOR(384),  -- For all-MiniLM-L6-v2 model
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    source VARCHAR(255)
);

-- Create monitoring tables
CREATE TABLE IF NOT EXISTS monitoring.metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    metric_name VARCHAR(255) NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL,
    labels JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS monitoring.health_checks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service_name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,
    response_time_ms INTEGER,
    error_message TEXT,
    checked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create audit table
CREATE TABLE IF NOT EXISTS audit.activity_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255),
    action VARCHAR(255) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_workflows_name ON app.workflows(name);
CREATE INDEX IF NOT EXISTS idx_workflows_active ON app.workflows(is_active);
CREATE INDEX IF NOT EXISTS idx_workflow_executions_workflow_id ON app.workflow_executions(workflow_id);
CREATE INDEX IF NOT EXISTS idx_workflow_executions_status ON app.workflow_executions(status);
CREATE INDEX IF NOT EXISTS idx_workflow_executions_started_at ON app.workflow_executions(started_at);
CREATE INDEX IF NOT EXISTS idx_embeddings_content_gin ON app.embeddings USING gin(to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS idx_embeddings_embedding_cosine ON app.embeddings USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_metrics_name_timestamp ON monitoring.metrics(metric_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_health_checks_service_timestamp ON monitoring.health_checks(service_name, checked_at);
CREATE INDEX IF NOT EXISTS idx_activity_log_user_timestamp ON audit.activity_log(user_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_activity_log_action_timestamp ON audit.activity_log(action, timestamp);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for workflows table
CREATE TRIGGER update_workflows_updated_at
    BEFORE UPDATE ON app.workflows
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Log successful schema creation
DO $$
BEGIN
    RAISE NOTICE 'Database schema created successfully for Kailash SDK Template';
END $$;