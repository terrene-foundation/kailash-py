const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const morgan = require('morgan');

const app = express();
const PORT = process.env.PORT || 8888;

// Middleware
app.use(cors());
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));
app.use(morgan('dev'));

// Load test API routes if available
try {
    const testApiRoutes = require('./routes/test-api');
    app.use('/', testApiRoutes);
    console.log('Test API routes loaded');
} catch (err) {
    console.log('Test API routes not available:', err.message);
}

// Health check endpoint
app.get('/health', (req, res) => {
    res.json({ status: 'healthy', timestamp: new Date().toISOString() });
});

// Transaction webhook endpoint
app.get('/transactions/pending', (req, res) => {
    res.json({
        data: {
            transactions: [
                {
                    id: 'TX' + Math.random().toString(36).substr(2, 9),
                    account: 'ACC-' + Math.floor(Math.random() * 90000 + 10000),
                    value: Math.floor(Math.random() * 50000) + 1000,
                    curr: ['USD', 'EUR', 'GBP'][Math.floor(Math.random() * 3)],
                    type: ['purchase', 'transfer', 'withdrawal'][Math.floor(Math.random() * 3)],
                    merchant: 'MERCH-' + Math.floor(Math.random() * 999),
                    time: new Date().toISOString(),
                    loc: { country: 'US', city: 'New York' },
                    device: { type: 'web', id: 'device123' }
                }
            ]
        }
    });
});

// Fraud alert endpoint
app.post('/alerts', (req, res) => {
    const { transaction_id, risk_score } = req.body;
    res.json({
        alert_id: 'ALERT-' + Math.random().toString(36).substr(2, 9),
        transaction_id: transaction_id || 'unknown',
        risk_score: risk_score || 0.5,
        status: 'created',
        timestamp: new Date().toISOString()
    });
});

// Notification endpoint
app.post('/send', (req, res) => {
    const { recipient, message, type } = req.body;
    res.json({
        notification_id: 'NOTIF-' + Math.random().toString(36).substr(2, 9),
        recipient: recipient || 'default@example.com',
        message: message || 'Notification sent',
        type: type || 'email',
        status: 'sent',
        timestamp: new Date().toISOString()
    });
});

// Lead enrichment endpoint
app.post('/enrichment', (req, res) => {
    const { company, email } = req.body;
    res.json({
        enrichment_id: 'ENR-' + Math.random().toString(36).substr(2, 9),
        company: {
            name: company || 'Unknown Company',
            domain: company ? `${company.toLowerCase().replace(/\s+/g, '')}.com` : 'example.com',
            industry: ['Technology', 'Finance', 'Healthcare', 'Retail'][Math.floor(Math.random() * 4)],
            size: ['1-10', '11-50', '51-200', '201-500', '500+'][Math.floor(Math.random() * 5)],
            founded: 2000 + Math.floor(Math.random() * 24)
        },
        person: {
            email: email || 'contact@example.com',
            role: ['CEO', 'CTO', 'VP Sales', 'Manager'][Math.floor(Math.random() * 4)],
            linkedin: 'https://linkedin.com/in/example'
        },
        score: Math.floor(Math.random() * 100)
    });
});

// Generic webhook endpoint for testing
app.post('/webhook', (req, res) => {
    console.log('Webhook received:', req.body);
    res.json({
        webhook_id: 'WH-' + Math.random().toString(36).substr(2, 9),
        received: true,
        timestamp: new Date().toISOString(),
        data: req.body
    });
});

// Error handling middleware
app.use((err, req, res, next) => {
    console.error(err.stack);
    res.status(500).json({
        error: 'Internal Server Error',
        message: err.message
    });
});

// 404 handler
app.use((req, res) => {
    res.status(404).json({
        error: 'Not Found',
        path: req.path
    });
});

// Start server
app.listen(PORT, () => {
    console.log(`Mock API Server running on port ${PORT}`);
    console.log('Available endpoints:');
    console.log('  GET  /health');
    console.log('  GET  /transactions/pending');
    console.log('  POST /alerts');
    console.log('  POST /send');
    console.log('  POST /enrichment');
    console.log('  POST /webhook');
    console.log('\nTest API endpoints:');
    console.log('  GET  /v1/users (paginated)');
    console.log('  GET  /v1/users/:id');
    console.log('  POST /v1/users');
    console.log('  PATCH /v1/users/:id');
    console.log('  DELETE /v1/users/:id');
    console.log('  GET  /v1/products');
    console.log('  GET  /users, /posts, /comments');
    console.log('  POST /oauth/token');
    console.log('  POST /graphql');
});
