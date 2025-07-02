const express = require('express');
const router = express.Router();

// Test data matching the Python test file
const USERS_DATA = [
    {
        id: 1,
        name: "Sarah Johnson",
        email: "sarah.johnson@techcorp.com",
        role: "Senior Developer",
        department: "Engineering",
        created_at: "2024-01-15T10:30:00Z"
    },
    {
        id: 2,
        name: "Michael Chen",
        email: "michael.chen@techcorp.com",
        role: "Product Manager",
        department: "Product",
        created_at: "2024-02-20T14:45:00Z"
    },
    {
        id: 3,
        name: "Emily Rodriguez",
        email: "emily.rodriguez@techcorp.com",
        role: "Data Scientist",
        department: "Analytics",
        created_at: "2024-03-10T09:15:00Z"
    }
];

const PRODUCTS_DATA = [
    {
        id: "prod_001",
        name: "Enterprise Analytics Suite",
        description: "Advanced analytics platform for business intelligence",
        price: 4999.99,
        category: "Software",
        features: ["Real-time dashboards", "ML predictions", "Data integration"],
        available: true
    },
    {
        id: "prod_002",
        name: "Cloud Storage Pro",
        description: "Secure cloud storage with advanced encryption",
        price: 299.99,
        category: "Infrastructure",
        features: ["256-bit encryption", "Auto-backup", "Version control"],
        available: true
    }
];

const POSTS_DATA = [
    {
        id: 1,
        userId: 1,
        title: "Test Post 1",
        body: "Test content 1"
    },
    {
        id: 2,
        userId: 2,
        title: "Test Post 2",
        body: "Test content 2"
    },
    {
        id: 3,
        userId: 1,
        title: "Test Post 3",
        body: "Test content 3"
    }
];

const COMMENTS_DATA = [
    {
        id: 1,
        postId: 1,
        name: "Comment 1",
        body: "Comment body 1"
    },
    {
        id: 2,
        postId: 1,
        name: "Comment 2",
        body: "Comment body 2"
    },
    {
        id: 3,
        postId: 2,
        name: "Comment 3",
        body: "Comment body 3"
    }
];

// In-memory storage for CRUD operations
let users = [...USERS_DATA];
let nextUserId = 4;

// GET /v1/users - List users with pagination
router.get('/v1/users', (req, res) => {
    const page = parseInt(req.query.page) || 1;
    const per_page = parseInt(req.query.per_page) || 10;
    const start = (page - 1) * per_page;
    const end = start + per_page;

    const paginatedUsers = users.slice(start, end);

    res.json({
        users: paginatedUsers,
        total: users.length,
        page: page,
        per_page: per_page,
        has_next: end < users.length
    });
});

// GET /v1/users/:id - Get specific user
router.get('/v1/users/:id', (req, res) => {
    const userId = parseInt(req.params.id);
    const user = users.find(u => u.id === userId);

    if (!user) {
        return res.status(404).json({
            error: {
                code: "NOT_FOUND",
                message: "User not found",
                details: `No user exists with ID: ${userId}`
            }
        });
    }

    res.json(user);
});

// POST /v1/users - Create new user
router.post('/v1/users', (req, res) => {
    const newUser = {
        id: nextUserId++,
        ...req.body,
        created_at: new Date().toISOString()
    };

    users.push(newUser);
    res.status(201).json(newUser);
});

// PATCH /v1/users/:id - Update user
router.patch('/v1/users/:id', (req, res) => {
    const userId = parseInt(req.params.id);
    const userIndex = users.findIndex(u => u.id === userId);

    if (userIndex === -1) {
        return res.status(404).json({
            error: {
                code: "NOT_FOUND",
                message: "User not found"
            }
        });
    }

    users[userIndex] = { ...users[userIndex], ...req.body };
    res.json(users[userIndex]);
});

// DELETE /v1/users/:id - Delete user
router.delete('/v1/users/:id', (req, res) => {
    const userId = parseInt(req.params.id);
    const userIndex = users.findIndex(u => u.id === userId);

    if (userIndex === -1) {
        return res.status(404).json({
            error: {
                code: "NOT_FOUND",
                message: "User not found"
            }
        });
    }

    users.splice(userIndex, 1);
    res.status(204).send();
});

// GET /v1/products - List products
router.get('/v1/products', (req, res) => {
    res.json({
        products: PRODUCTS_DATA
    });
});

// Mock data endpoints for API aggregation tests
router.get('/users', (req, res) => {
    res.json(USERS_DATA.map(u => ({
        id: u.id,
        name: u.name,
        email: u.email,
        company: { name: "Test Co" }
    })));
});

router.get('/posts', (req, res) => {
    res.json(POSTS_DATA);
});

router.get('/comments', (req, res) => {
    res.json(COMMENTS_DATA);
});

// OAuth token endpoint
router.post('/oauth/token', (req, res) => {
    let { grant_type, client_id, client_secret, scope } = req.body;

    // Check for Basic auth (client credentials in header)
    const authHeader = req.headers.authorization;
    if (authHeader && authHeader.startsWith('Basic ')) {
        const credentials = Buffer.from(authHeader.slice(6), 'base64').toString();
        const [headerClientId, headerClientSecret] = credentials.split(':');

        // Use header credentials if available
        if (headerClientId && headerClientSecret) {
            client_id = client_id || headerClientId;
            client_secret = headerClientSecret;
        }
    }

    // Simple validation
    if (!grant_type || !client_id || !client_secret) {
        return res.status(400).json({
            error: "invalid_request",
            error_description: "Missing required parameters"
        });
    }

    res.json({
        access_token: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
        token_type: "Bearer",
        expires_in: 3600,
        refresh_token: "refresh_token_value",
        scope: scope || "read write"
    });
});

// GraphQL endpoint
router.post('/graphql', (req, res) => {
    const { query, variables } = req.body;

    // Simple GraphQL response based on query
    if (query.includes('GetUserWithPosts')) {
        const userId = variables?.userId || "1";
        const user = USERS_DATA.find(u => u.id === parseInt(userId));

        if (!user) {
            return res.json({
                errors: [{
                    message: "User not found",
                    extensions: { code: "NOT_FOUND" }
                }]
            });
        }

        res.json({
            data: {
                user: {
                    id: user.id.toString(),
                    name: user.name,
                    email: user.email,
                    posts: [
                        {
                            id: "101",
                            title: "Building Scalable Microservices",
                            content: "In this post, we'll explore best practices for building scalable microservices...",
                            publishedAt: "2024-11-20T10:00:00Z",
                            tags: ["microservices", "architecture", "scalability"]
                        },
                        {
                            id: "102",
                            title: "Kubernetes in Production",
                            content: "Learn from our experience running Kubernetes in production for 2 years...",
                            publishedAt: "2024-11-25T14:30:00Z",
                            tags: ["kubernetes", "devops", "containers"]
                        }
                    ]
                }
            }
        });
    } else {
        res.json({
            data: {},
            errors: [{
                message: "Query not supported in mock",
                extensions: { code: "NOT_IMPLEMENTED" }
            }]
        });
    }
});

// Rate limiting simulation
let requestCounts = {};
router.use((req, res, next) => {
    const clientIp = req.ip || 'unknown';
    const now = Date.now();
    const minute = Math.floor(now / 60000);
    const key = `${clientIp}:${minute}`;

    if (!requestCounts[key]) {
        requestCounts[key] = 0;
    }

    requestCounts[key]++;

    // Clean old entries
    const oldMinute = minute - 2;
    Object.keys(requestCounts).forEach(k => {
        const [, m] = k.split(':');
        if (parseInt(m) < oldMinute) {
            delete requestCounts[k];
        }
    });

    // Rate limit at 100 requests per minute
    if (requestCounts[key] > 100) {
        return res.status(429).json({
            error: "Rate limit exceeded",
            retry_after: 60
        }).set({
            'X-RateLimit-Limit': '100',
            'X-RateLimit-Remaining': '0',
            'X-RateLimit-Reset': String(Math.floor(now / 1000) + 60)
        });
    }

    res.set({
        'X-RateLimit-Limit': '100',
        'X-RateLimit-Remaining': String(100 - requestCounts[key]),
        'X-RateLimit-Reset': String(Math.floor(now / 1000) + 60)
    });

    next();
});

module.exports = router;
