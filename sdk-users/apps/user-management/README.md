# User Management System - Developer Guide

## 🚀 Quick Start (Django-Style)

The Kailash User Management system provides Django-like simplicity with enterprise features built-in.

### Installation & Setup

```python
# 1. Import the user management components
from kailash.nodes.admin import UserManagementNode, RoleManagementNode
from kailash.nodes.admin.schema_manager import AdminSchemaManager

# 2. Set up your database (just like Django's migrate)
db_config = {
    "connection_string": "postgresql://user:pass@localhost/myapp",
    "database_type": "postgresql"
}

# Create tables (equivalent to python manage.py migrate)
schema_manager = AdminSchemaManager(db_config)
schema_manager.create_full_schema()
```

### Basic Usage - Just Like Django!

```python
# Initialize the user manager (like Django's User model)
User = UserManagementNode()

# Create a user (like User.objects.create_user())
user = User.execute(
    operation="create_user",
    tenant_id="default",
    database_config=db_config,
    user_data={
        "email": "john@example.com",
        "username": "john_doe",
        "first_name": "John",
        "last_name": "Doe"
    },
    password="SecurePass123!"  # Automatically hashed
)

# Get a user (like User.objects.get())
user = User.execute(
    operation="get_user",
    tenant_id="default",
    database_config=db_config,
    user_id="user-uuid-here"
)

# List users (like User.objects.filter())
users = User.execute(
    operation="list_users",
    tenant_id="default",
    database_config=db_config,
    filters={"status": "active"},
    limit=10
)

# Authenticate (like authenticate())
result = User.execute(
    operation="authenticate",
    tenant_id="default",
    database_config=db_config,
    username="john_doe",
    password="SecurePass123!"
)
if result["authenticated"]:
    print("Login successful!")
```

## 📚 Complete Feature Guide

### 1. User Management

#### Create User
```python
from kailash.nodes.admin import UserManagementNode
import hashlib

User = UserManagementNode()

# Simple creation with automatic password hashing
result = User.execute(
    operation="create_user",
    tenant_id="my_app",
    database_config=db_config,
    user_data={
        "email": "user@example.com",
        "username": "newuser",
        "first_name": "Jane",
        "last_name": "Smith",
        "attributes": {  # Custom fields (like Django's profile)
            "department": "Engineering",
            "employee_id": "EMP001"
        }
    },
    password="MySecurePassword123!"  # Auto-hashed
)

user_id = result["result"]["user"]["user_id"]
```

#### Update User
```python
# Update user details
result = User.execute(
    operation="update_user",
    tenant_id="my_app",
    database_config=db_config,
    user_id=user_id,
    user_data={
        "first_name": "Jane",
        "last_name": "Doe",
        "attributes": {
            "department": "Management"
        }
    }
)
```

#### List & Search Users
```python
# List with filters (like Django QuerySet)
active_users = User.execute(
    operation="list_users",
    tenant_id="my_app",
    database_config=db_config,
    filters={"status": "active"},
    limit=20,
    offset=0
)

# Search users
search_results = User.execute(
    operation="search_users",
    tenant_id="my_app",
    database_config=db_config,
    search_query="john",
    limit=10
)
```

### 2. Authentication & Password Management

#### Login
```python
# Authenticate user
auth_result = User.execute(
    operation="authenticate",
    tenant_id="my_app",
    database_config=db_config,
    username="john_doe",  # or use email
    password="UserPassword123!"
)

if auth_result["authenticated"]:
    user_id = auth_result["user_id"]
    # Create session, JWT token, etc.
```

#### Password Reset Flow
```python
# 1. Generate reset token
token_result = User.execute(
    operation="generate_reset_token",
    tenant_id="my_app",
    database_config=db_config,
    user_id=user_id
)
reset_token = token_result["token"]
# Send reset_token via email

# 2. Reset password with token
reset_result = User.execute(
    operation="reset_password",
    tenant_id="my_app",
    database_config=db_config,
    token=reset_token,
    new_password="NewSecurePass123!"
)
```

### 3. Role-Based Access Control (RBAC)

#### Create and Manage Roles
```python
from kailash.nodes.admin import RoleManagementNode

Role = RoleManagementNode()

# Create role with permissions
admin_role = Role.execute(
    operation="create_role",
    tenant_id="my_app",
    database_config=db_config,
    role_data={
        "name": "admin",
        "description": "System Administrator",
        "permissions": [
            "users.create", "users.read", "users.update", "users.delete",
            "roles.manage", "system.configure"
        ]
    }
)

# Assign role to user
Role.execute(
    operation="assign_user",
    tenant_id="my_app",
    database_config=db_config,
    user_id=user_id,
    role_id=admin_role["result"]["role"]["role_id"]
)

# Check user permissions
user_roles = Role.execute(
    operation="get_user_roles",
    tenant_id="my_app",
    database_config=db_config,
    user_id=user_id
)
```

### 4. Bulk Operations

#### Bulk Create Users
```python
# Create multiple users at once
users_data = [
    {
        "email": f"user{i}@company.com",
        "username": f"user{i}",
        "first_name": f"User",
        "last_name": f"{i}",
        "password_hash": hashlib.sha256(f"Pass{i}123!".encode()).hexdigest(),
        "attributes": {"department": "Sales"}
    }
    for i in range(100)
]

bulk_result = User.execute(
    operation="bulk_create",
    tenant_id="my_app",
    database_config=db_config,
    users_data=users_data
)
print(f"Created {bulk_result['result']['bulk_result']['created_count']} users")
```

#### Bulk Update
```python
# Update multiple users
updates = [
    {"user_id": "uuid1", "status": "inactive"},
    {"user_id": "uuid2", "status": "inactive"},
    {"user_id": "uuid3", "attributes": {"department": "HR"}}
]

bulk_update = User.execute(
    operation="bulk_update",
    tenant_id="my_app",
    database_config=db_config,
    users_data=updates
)
```

#### Bulk Delete
```python
# Delete multiple users
user_ids = ["uuid1", "uuid2", "uuid3"]

bulk_delete = User.execute(
    operation="bulk_delete",
    tenant_id="my_app",
    database_config=db_config,
    user_ids=user_ids
)
```

### 5. Advanced Features

#### Multi-Tenancy
```python
# All operations support multi-tenancy
# Users are isolated by tenant_id

# Tenant A users
users_a = User.execute(
    operation="list_users",
    tenant_id="tenant_a",
    database_config=db_config
)

# Tenant B users (completely isolated)
users_b = User.execute(
    operation="list_users",
    tenant_id="tenant_b",
    database_config=db_config
)
```

#### Export Users
```python
# Export to JSON
export_result = User.execute(
    operation="export_users",
    tenant_id="my_app",
    database_config=db_config,
    export_format="json"
)

# Export to CSV
csv_export = User.execute(
    operation="export_users",
    tenant_id="my_app",
    database_config=db_config,
    export_format="csv"
)
```

## 🔄 Migration from Django

### Django → Kailash Equivalents

| Django | Kailash |
|--------|---------|
| `User.objects.create_user()` | `User.execute(operation="create_user")` |
| `User.objects.get(id=x)` | `User.execute(operation="get_user", user_id=x)` |
| `User.objects.filter(is_active=True)` | `User.execute(operation="list_users", filters={"status": "active"})` |
| `authenticate(username, password)` | `User.execute(operation="authenticate", username=x, password=y)` |
| `user.groups.add(group)` | `Role.execute(operation="assign_user", user_id=x, role_id=y)` |
| `user.has_perm('app.perm')` | `PermissionCheck.execute(operation="check_permission", user_id=x, permission="app.perm")` |

### Migration Script Example
```python
from django.contrib.auth.models import User as DjangoUser
from kailash.nodes.admin import UserManagementNode

# Migrate Django users to Kailash
kailash_user = UserManagementNode()

for django_user in DjangoUser.objects.all():
    kailash_user.execute(
        operation="create_user",
        tenant_id="migrated",
        database_config=db_config,
        user_data={
            "email": django_user.email,
            "username": django_user.username,
            "first_name": django_user.first_name,
            "last_name": django_user.last_name,
            "attributes": {
                "django_id": django_user.id,
                "date_joined": django_user.date_joined.isoformat(),
                "is_staff": django_user.is_staff,
                "is_superuser": django_user.is_superuser
            }
        },
        password_hash=django_user.password  # Already hashed
    )
```

## 🏗️ Complete Application Example

```python
from fastapi import FastAPI, HTTPException, Depends
from kailash.nodes.admin import UserManagementNode, RoleManagementNode
from kailash.middleware import create_gateway

# Create FastAPI app with Kailash
app = create_gateway(
    title="My User Management API",
    version="1.0.0"
)

# Database configuration
db_config = {
    "connection_string": "postgresql://localhost/myapp",
    "database_type": "postgresql"
}

# Initialize nodes
User = UserManagementNode()
Role = RoleManagementNode()

# API Endpoints
@app.post("/api/users/register")
async def register(email: str, username: str, password: str):
    """Register a new user"""
    result = User.execute(
        operation="create_user",
        tenant_id="default",
        database_config=db_config,
        user_data={
            "email": email,
            "username": username
        },
        password=password
    )
    return {"user_id": result["result"]["user"]["user_id"]}

@app.post("/api/users/login")
async def login(username: str, password: str):
    """Login user"""
    result = User.execute(
        operation="authenticate",
        tenant_id="default",
        database_config=db_config,
        username=username,
        password=password
    )

    if not result["authenticated"]:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Generate JWT token here
    return {"user_id": result["user_id"], "token": "jwt-token-here"}

@app.get("/api/users/{user_id}")
async def get_user(user_id: str):
    """Get user details"""
    result = User.execute(
        operation="get_user",
        tenant_id="default",
        database_config=db_config,
        user_id=user_id
    )
    return result["result"]["user"]

@app.get("/api/users")
async def list_users(limit: int = 10, offset: int = 0):
    """List all users"""
    result = User.execute(
        operation="list_users",
        tenant_id="default",
        database_config=db_config,
        limit=limit,
        offset=offset
    )
    return result["result"]["users"]

# Run the app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## 📊 Performance & Scalability

- **Bulk Operations**: Process 200+ users/second
- **Concurrent Support**: Handle 500+ concurrent users
- **Multi-Tenant**: Unlimited tenant isolation
- **Caching**: Built-in permission caching
- **Database**: Optimized queries with indexes

## 🔒 Security Features

- **Password Hashing**: SHA256, bcrypt, or argon2
- **Multi-Factor Auth**: 2FA/MFA ready
- **Session Management**: Secure session handling
- **Audit Logging**: Complete audit trail
- **GDPR Compliant**: Data privacy features

## 🧪 Testing

```python
# Test user creation
def test_user_creation():
    user = User.execute(
        operation="create_user",
        tenant_id="test",
        database_config=test_db_config,
        user_data={
            "email": "test@test.com",
            "username": "testuser"
        },
        password="TestPass123!"
    )
    assert user["result"]["user"]["email"] == "test@test.com"
```

## 📚 API Reference

### UserManagementNode Operations

| Operation | Description | Required Parameters |
|-----------|-------------|-------------------|
| `create_user` | Create a new user | `user_data`, `password` |
| `update_user` | Update user details | `user_id`, `user_data` |
| `delete_user` | Delete a user | `user_id` |
| `get_user` | Get user by ID | `user_id` |
| `list_users` | List all users | `limit`, `offset` |
| `authenticate` | Authenticate user | `username/email`, `password` |
| `generate_reset_token` | Create password reset token | `user_id` |
| `reset_password` | Reset password with token | `token`, `new_password` |
| `bulk_create` | Create multiple users | `users_data` |
| `bulk_update` | Update multiple users | `users_data` |
| `bulk_delete` | Delete multiple users | `user_ids` |
| `search_users` | Search users | `search_query` |
| `export_users` | Export user data | `export_format` |

### RoleManagementNode Operations

| Operation | Description | Required Parameters |
|-----------|-------------|-------------------|
| `create_role` | Create a new role | `role_data` |
| `update_role` | Update role details | `role_id`, `role_data` |
| `delete_role` | Delete a role | `role_id` |
| `assign_user` | Assign role to user | `user_id`, `role_id` |
| `get_user_roles` | Get user's roles | `user_id` |

## 🚀 Next Steps

1. Check out the [Complete API Documentation](../API_REFERENCE.md)
2. See [Migration Guide](../migration-guides/django-to-kailash.md)
3. Review [Security Best Practices](../security/README.md)
4. Explore [Advanced Features](../advanced/README.md)

---

**Need Help?**
- 📧 Email: support@kailash.dev
- 💬 Discord: [Join our community](https://discord.gg/kailash)
- 📚 Docs: [Full Documentation](https://docs.kailash.dev)
