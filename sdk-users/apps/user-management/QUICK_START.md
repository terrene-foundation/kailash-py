# User Management - 5-Minute Quick Start

## 🚀 From Zero to Authentication in 5 Minutes

### Step 1: Install and Setup (30 seconds)

```python
from kailash.nodes.admin import UserManagementNode
from kailash.nodes.admin.schema_manager import AdminSchemaManager

# Database config
db_config = {
    "connection_string": "postgresql://localhost/myapp",
    "database_type": "postgresql"
}

# Create tables (one-time setup)
AdminSchemaManager(db_config).create_full_schema()
```

### Step 2: Create Your First User (30 seconds)

```python
User = UserManagementNode()

# Create a user
new_user = User.execute(
    operation="create_user",
    tenant_id="default",
    database_config=db_config,
    user_data={
        "email": "john@example.com",
        "username": "john"
    },
    password="SecurePass123!"
)

print(f"Created user: {new_user['result']['user']['user_id']}")
```

### Step 3: Authenticate (30 seconds)

```python
# Login
auth = User.execute(
    operation="authenticate",
    tenant_id="default",
    database_config=db_config,
    username="john",
    password="SecurePass123!"
)

if auth["authenticated"]:
    print("Login successful!")
```

### Step 4: Add Roles (1 minute)

```python
from kailash.nodes.admin import RoleManagementNode

Role = RoleManagementNode()

# Create admin role
admin_role = Role.execute(
    operation="create_role",
    tenant_id="default",
    database_config=db_config,
    role_data={
        "name": "admin",
        "permissions": ["users.*", "system.*"]
    }
)

# Assign to user
Role.execute(
    operation="assign_user",
    tenant_id="default",
    database_config=db_config,
    user_id=new_user["result"]["user"]["user_id"],
    role_id=admin_role["result"]["role"]["role_id"]
)
```

### Step 5: Build a Simple API (2 minutes)

```python
from fastapi import FastAPI
from kailash.api.middleware import create_gateway

app = create_gateway(title="My App")
User = UserManagementNode()

@app.post("/register")
async def register(email: str, password: str):
    result = User.execute(
        operation="create_user",
        tenant_id="default",
        database_config=db_config,
        user_data={"email": email, "username": email.split("@")[0]},
        password=password
    )
    return {"user_id": result["result"]["user"]["user_id"]}

@app.post("/login")
async def login(email: str, password: str):
    result = User.execute(
        operation="authenticate",
        tenant_id="default",
        database_config=db_config,
        email=email,
        password=password
    )
    return {"success": result["authenticated"]}

# Run: uvicorn main:app --reload
```

## 🎯 Common Use Cases

### Password Reset Flow
```python
# 1. Request reset
token_result = User.execute(
    operation="generate_reset_token",
    tenant_id="default",
    database_config=db_config,
    user_id=user_id
)
# Email token to user

# 2. Reset with token
User.execute(
    operation="reset_password",
    tenant_id="default",
    database_config=db_config,
    token=token_result["token"],
    new_password="NewPass123!"
)
```

### Bulk Import Users
```python
users = [
    {"email": f"user{i}@example.com", "username": f"user{i}",
     "password_hash": hash_password(f"Pass{i}!")}
    for i in range(100)
]

User.execute(
    operation="bulk_create",
    tenant_id="default",
    database_config=db_config,
    users_data=users
)
```

### Search Users
```python
results = User.execute(
    operation="search_users",
    tenant_id="default",
    database_config=db_config,
    search_query="john",
    limit=10
)
```

## 📝 Cheat Sheet

```python
# Initialize
User = UserManagementNode()
Role = RoleManagementNode()

# Create
User.execute(operation="create_user", ...)

# Read
User.execute(operation="get_user", user_id=...)
User.execute(operation="list_users", ...)

# Update
User.execute(operation="update_user", user_id=..., user_data=...)

# Delete
User.execute(operation="delete_user", user_id=...)

# Auth
User.execute(operation="authenticate", username=..., password=...)
User.execute(operation="generate_reset_token", user_id=...)
User.execute(operation="reset_password", token=..., new_password=...)

# Bulk
User.execute(operation="bulk_create", users_data=[...])
User.execute(operation="bulk_update", users_data=[...])
User.execute(operation="bulk_delete", user_ids=[...])

# Roles
Role.execute(operation="create_role", role_data=...)
Role.execute(operation="assign_user", user_id=..., role_id=...)
Role.execute(operation="get_user_roles", user_id=...)
```

## 🔗 Next Steps
- [Full Tutorial](./README.md) - Complete guide with all features
- [API Reference](./API_REFERENCE.md) - All operations detailed
- [Examples](./examples/) - Real-world examples
