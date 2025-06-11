-- Initialize SDK Development Databases
-- This script creates all necessary databases and tables for Kailash SDK examples

-- Note: Database creation is handled by the workflow script
-- This file only contains table creation and sample data

-- Connect to transactions database
\c transactions;

-- Create transactions table
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id VARCHAR(50) PRIMARY KEY,
    account_id VARCHAR(50) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    transaction_type VARCHAR(20),
    merchant_id VARCHAR(50),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    location JSONB,
    device_info JSONB,
    risk_factors JSONB,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_transactions_account ON transactions(account_id);
CREATE INDEX idx_transactions_timestamp ON transactions(timestamp);
CREATE INDEX idx_transactions_processed ON transactions(processed);

-- Insert sample transactions
INSERT INTO transactions (transaction_id, account_id, amount, currency, transaction_type, merchant_id, location, risk_factors)
VALUES
    ('TX001', 'ACC-12345', 2500.00, 'USD', 'purchase', 'MERCH-001', '{"country": "US", "city": "New York"}', '{"is_first_transaction": false}'),
    ('TX002', 'ACC-67890', 15000.00, 'USD', 'transfer', NULL, '{"country": "UK", "city": "London"}', '{"unusual_amount": true}'),
    ('TX003', 'ACC-11111', 750.50, 'EUR', 'purchase', 'MERCH-002', '{"country": "FR", "city": "Paris"}', '{}'),
    ('TX004', 'ACC-22222', 50000.00, 'USD', 'wire', NULL, '{"country": "CH", "city": "Zurich"}', '{"high_risk_country": true}'),
    ('TX005', 'ACC-33333', 125.00, 'GBP', 'purchase', 'MERCH-003', '{"country": "UK", "city": "Manchester"}', '{}');

-- Connect to compliance database
\c compliance;

-- Create compliance reports table
CREATE TABLE IF NOT EXISTS compliance_reports (
    report_id SERIAL PRIMARY KEY,
    report_type VARCHAR(50) NOT NULL,
    transaction_id VARCHAR(50),
    account_id VARCHAR(50),
    amount DECIMAL(12, 2),
    currency VARCHAR(3),
    filing_required BOOLEAN DEFAULT FALSE,
    report_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

-- Connect to analytics database
\c analytics;

-- Create financial reports table
CREATE TABLE IF NOT EXISTS financial_reports (
    report_id SERIAL PRIMARY KEY,
    report_type VARCHAR(50) NOT NULL,
    report_date DATE NOT NULL,
    total_volume DECIMAL(15, 2),
    transaction_count INTEGER,
    metrics JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create performance metrics table
CREATE TABLE IF NOT EXISTS performance_metrics (
    metric_id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(12, 4),
    metric_unit VARCHAR(20),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

-- Connect to CRM database
\c crm;

-- Create leads table
CREATE TABLE IF NOT EXISTS leads (
    lead_id VARCHAR(50) PRIMARY KEY,
    company VARCHAR(200) NOT NULL,
    contact_name VARCHAR(100),
    email VARCHAR(200),
    phone VARCHAR(50),
    industry VARCHAR(100),
    company_size VARCHAR(50),
    score INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'new',
    source VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert sample leads
INSERT INTO leads (lead_id, company, contact_name, email, industry, company_size, score, source)
VALUES
    ('LEAD001', 'TechCorp Inc', 'John Smith', 'john@techcorp.com', 'Software', '100-500', 85, 'website'),
    ('LEAD002', 'Global Finance Ltd', 'Sarah Johnson', 'sarah@globalfinance.com', 'Finance', '1000+', 92, 'referral'),
    ('LEAD003', 'StartupXYZ', 'Mike Chen', 'mike@startupxyz.com', 'SaaS', '10-50', 65, 'marketing'),
    ('LEAD004', 'Enterprise Solutions', 'Lisa Brown', 'lisa@enterprise.com', 'Consulting', '500-1000', 78, 'event'),
    ('LEAD005', 'Digital Innovations', 'Alex Turner', 'alex@digital.com', 'Technology', '50-100', 70, 'website');

-- Connect to marketing database
\c marketing;

-- Create campaigns table
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id SERIAL PRIMARY KEY,
    campaign_name VARCHAR(200) NOT NULL,
    campaign_type VARCHAR(50),
    start_date DATE,
    end_date DATE,
    budget DECIMAL(10, 2),
    status VARCHAR(50) DEFAULT 'active',
    metrics JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create engagement table
CREATE TABLE IF NOT EXISTS engagement (
    engagement_id SERIAL PRIMARY KEY,
    lead_id VARCHAR(50),
    campaign_id INTEGER REFERENCES campaigns(campaign_id),
    action_type VARCHAR(50),
    action_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

-- Insert sample campaigns
INSERT INTO campaigns (campaign_name, campaign_type, start_date, end_date, budget, status)
VALUES
    ('Q1 Email Campaign', 'email', '2024-01-01', '2024-03-31', 10000.00, 'completed'),
    ('Product Launch', 'multi-channel', '2024-02-15', '2024-04-15', 25000.00, 'active'),
    ('Summer Promotion', 'social', '2024-06-01', '2024-08-31', 15000.00, 'planned');

-- Connect to reports database
\c reports;

-- Create report templates table
CREATE TABLE IF NOT EXISTS report_templates (
    template_id SERIAL PRIMARY KEY,
    template_name VARCHAR(200) NOT NULL,
    template_type VARCHAR(50),
    template_config JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create generated reports table
CREATE TABLE IF NOT EXISTS generated_reports (
    report_id SERIAL PRIMARY KEY,
    template_id INTEGER REFERENCES report_templates(template_id),
    report_name VARCHAR(200),
    report_data JSONB,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    generated_by VARCHAR(100)
);
