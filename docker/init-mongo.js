// Initialize MongoDB for SDK Development
// This script creates collections and sample data for Kailash SDK examples

// Switch to kailash database
db = db.getSiblingDB('kailash');

// Create collections
db.createCollection('documents');
db.createCollection('events');
db.createCollection('workflows');
db.createCollection('logs');
db.createCollection('api_responses');

// Create indexes
db.documents.createIndex({ "document_id": 1 }, { unique: true });
db.documents.createIndex({ "created_at": -1 });
db.documents.createIndex({ "metadata.type": 1 });

db.events.createIndex({ "event_id": 1 }, { unique: true });
db.events.createIndex({ "timestamp": -1 });
db.events.createIndex({ "event_type": 1 });

db.workflows.createIndex({ "workflow_id": 1 }, { unique: true });
db.workflows.createIndex({ "status": 1 });
db.workflows.createIndex({ "created_at": -1 });

// Insert sample documents
db.documents.insertMany([
    {
        document_id: "DOC001",
        title: "Financial Report Q1 2024",
        type: "report",
        content: {
            summary: "Quarterly financial performance summary",
            sections: ["revenue", "expenses", "profit", "forecast"],
            data: {
                revenue: 1500000,
                expenses: 1200000,
                profit: 300000
            }
        },
        metadata: {
            type: "financial",
            department: "finance",
            tags: ["quarterly", "2024", "report"]
        },
        created_at: new Date("2024-04-01"),
        updated_at: new Date("2024-04-01")
    },
    {
        document_id: "DOC002",
        title: "Customer Feedback Analysis",
        type: "analysis",
        content: {
            summary: "Analysis of customer feedback from Q1",
            sentiment: {
                positive: 0.65,
                neutral: 0.25,
                negative: 0.10
            },
            topics: ["product quality", "customer service", "pricing"],
            recommendations: ["Improve response time", "Add new features"]
        },
        metadata: {
            type: "analysis",
            department: "customer_success",
            tags: ["feedback", "sentiment", "Q1"]
        },
        created_at: new Date("2024-04-15"),
        updated_at: new Date("2024-04-15")
    }
]);

// Insert sample events
db.events.insertMany([
    {
        event_id: "EVT001",
        event_type: "user_login",
        user_id: "USER123",
        timestamp: new Date(),
        data: {
            ip_address: "192.168.1.100",
            user_agent: "Mozilla/5.0",
            location: "New York, US"
        },
        metadata: {
            session_id: "SESSION123",
            device_type: "desktop"
        }
    },
    {
        event_id: "EVT002",
        event_type: "transaction_processed",
        transaction_id: "TX12345",
        timestamp: new Date(),
        data: {
            amount: 150.00,
            currency: "USD",
            merchant: "Coffee Shop",
            status: "approved"
        },
        metadata: {
            processing_time_ms: 245,
            gateway: "stripe"
        }
    },
    {
        event_id: "EVT003",
        event_type: "error_occurred",
        error_code: "ERR_TIMEOUT",
        timestamp: new Date(),
        data: {
            message: "Request timeout",
            service: "payment_service",
            severity: "warning"
        },
        metadata: {
            retry_count: 2,
            max_retries: 3
        }
    }
]);

// Insert sample workflow definitions
db.workflows.insertMany([
    {
        workflow_id: "WF001",
        name: "Customer Onboarding",
        description: "Automated customer onboarding process",
        status: "active",
        definition: {
            nodes: [
                { id: "start", type: "trigger", config: { event: "new_customer" } },
                { id: "validate", type: "validation", config: { rules: ["email", "phone"] } },
                { id: "enrich", type: "enrichment", config: { source: "clearbit" } },
                { id: "notify", type: "notification", config: { channel: "email" } }
            ],
            connections: [
                { from: "start", to: "validate" },
                { from: "validate", to: "enrich" },
                { from: "enrich", to: "notify" }
            ]
        },
        created_at: new Date("2024-01-01"),
        updated_at: new Date("2024-01-01")
    },
    {
        workflow_id: "WF002",
        name: "Fraud Detection",
        description: "Real-time fraud detection workflow",
        status: "active",
        definition: {
            nodes: [
                { id: "input", type: "stream", config: { topic: "transactions" } },
                { id: "score", type: "ml_model", config: { model: "fraud_detector_v2" } },
                { id: "route", type: "switch", config: { threshold: 0.8 } },
                { id: "alert", type: "alert", config: { severity: "high" } },
                { id: "log", type: "logger", config: { level: "info" } }
            ],
            connections: [
                { from: "input", to: "score" },
                { from: "score", to: "route" },
                { from: "route", to: "alert", condition: "high_risk" },
                { from: "route", to: "log", condition: "low_risk" }
            ]
        },
        created_at: new Date("2024-02-01"),
        updated_at: new Date("2024-02-15")
    }
]);

// Insert sample API responses for mock testing
db.api_responses.insertMany([
    {
        endpoint: "/api/enrich",
        method: "POST",
        response_template: {
            company: {
                name: "{{company_name}}",
                domain: "{{domain}}",
                industry: "Technology",
                size: "100-500",
                founded: 2015
            },
            social: {
                twitter: "@{{company_name}}",
                linkedin: "linkedin.com/company/{{company_name}}"
            }
        }
    },
    {
        endpoint: "/api/fraud/score",
        method: "POST",
        response_template: {
            transaction_id: "{{transaction_id}}",
            risk_score: 0.45,
            risk_factors: ["new_device", "unusual_location"],
            recommendation: "review"
        }
    }
]);

// Create user for application access
db.createUser({
    user: "kailash_app",
    pwd: "kailash123",
    roles: [
        { role: "readWrite", db: "kailash" }
    ]
});

print("MongoDB initialization completed successfully!");
print("Created collections: documents, events, workflows, logs, api_responses");
print("Inserted sample data for testing");
