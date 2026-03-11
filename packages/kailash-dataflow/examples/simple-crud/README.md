# Simple CRUD Example

A basic example showing how to create a simple CRUD application using DataFlow.

## Overview

This example demonstrates:
- Basic model definition
- CRUD operations (Create, Read, Update, Delete)
- Simple workflow integration
- Error handling
- Testing

## Model Definition

```python
# models.py
from kailash_dataflow import DataFlow
from datetime import datetime
from typing import Optional

db = DataFlow()

@db.model
class User:
    """Simple user model."""
    name: str
    email: str
    age: int
    active: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None
```

## CRUD Operations

### Create User

```python
# create_user.py
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from models import db

def create_user(name: str, email: str, age: int) -> dict:
    """Create a new user."""
    workflow = WorkflowBuilder()

    workflow.add_node("UserCreateNode", "create_user", {
        "name": name,
        "email": email,
        "age": age
    })

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    return {
        "success": True,
        "user": results["create_user"]["data"],
        "run_id": run_id
    }

# Example usage
if __name__ == "__main__":
    result = create_user("John Doe", "john@example.com", 30)
    print(f"Created user: {result['user']}")
```

### Read User

```python
# read_user.py
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from models import db

def get_user(user_id: int) -> dict:
    """Get user by ID."""
    workflow = WorkflowBuilder()

    workflow.add_node("UserReadNode", "get_user", {
        "id": user_id
    })

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    return {
        "success": True,
        "user": results["get_user"]["data"],
        "run_id": run_id
    }

def get_user_by_email(email: str) -> dict:
    """Get user by email."""
    workflow = WorkflowBuilder()

    workflow.add_node("UserListNode", "find_user", {
        "filter": {"email": email},
        "limit": 1
    })

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    users = results["find_user"]["data"]

    return {
        "success": True,
        "user": users[0] if users else None,
        "run_id": run_id
    }

# Example usage
if __name__ == "__main__":
    result = get_user(1)
    print(f"Found user: {result['user']}")

    result = get_user_by_email("john@example.com")
    print(f"Found user by email: {result['user']}")
```

### Update User

```python
# update_user.py
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from models import db

def update_user(user_id: int, **updates) -> dict:
    """Update user by ID."""
    workflow = WorkflowBuilder()

    # Add current timestamp to updates
    updates["updated_at"] = ":current_timestamp"

    workflow.add_node("UserUpdateNode", "update_user", {
        "id": user_id,
        **updates
    })

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    return {
        "success": True,
        "user": results["update_user"]["data"],
        "run_id": run_id
    }

def deactivate_user(user_id: int) -> dict:
    """Deactivate user."""
    return update_user(user_id, active=False)

def activate_user(user_id: int) -> dict:
    """Activate user."""
    return update_user(user_id, active=True)

# Example usage
if __name__ == "__main__":
    result = update_user(1, name="John Smith", age=31)
    print(f"Updated user: {result['user']}")

    result = deactivate_user(1)
    print(f"Deactivated user: {result['user']}")
```

### Delete User

```python
# delete_user.py
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from models import db

def delete_user(user_id: int, soft_delete: bool = True) -> dict:
    """Delete user by ID."""
    workflow = WorkflowBuilder()

    workflow.add_node("UserDeleteNode", "delete_user", {
        "id": user_id,
        "soft_delete": soft_delete
    })

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    return {
        "success": True,
        "deleted": results["delete_user"]["success"],
        "run_id": run_id
    }

# Example usage
if __name__ == "__main__":
    result = delete_user(1, soft_delete=True)
    print(f"User deleted: {result['deleted']}")
```

### List Users

```python
# list_users.py
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from models import db

def list_users(active_only: bool = True, limit: int = 100) -> dict:
    """List all users."""
    workflow = WorkflowBuilder()

    filter_params = {}
    if active_only:
        filter_params["active"] = True

    workflow.add_node("UserListNode", "list_users", {
        "filter": filter_params,
        "order_by": ["-created_at"],
        "limit": limit
    })

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    return {
        "success": True,
        "users": results["list_users"]["data"],
        "count": len(results["list_users"]["data"]),
        "run_id": run_id
    }

def search_users(query: str, limit: int = 50) -> dict:
    """Search users by name or email."""
    workflow = WorkflowBuilder()

    workflow.add_node("UserListNode", "search_users", {
        "filter": {
            "$or": [
                {"name": {"$regex": query}},
                {"email": {"$regex": query}}
            ]
        },
        "order_by": ["name"],
        "limit": limit
    })

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    return {
        "success": True,
        "users": results["search_users"]["data"],
        "count": len(results["search_users"]["data"]),
        "run_id": run_id
    }

# Example usage
if __name__ == "__main__":
    result = list_users(active_only=True, limit=10)
    print(f"Found {result['count']} users")

    result = search_users("john", limit=5)
    print(f"Search results: {result['count']} users")
```

## Complete Application

```python
# app.py
from kailash_dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from datetime import datetime
from typing import Optional

# Initialize DataFlow
db = DataFlow()

# Define model
@db.model
class User:
    name: str
    email: str
    age: int
    active: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None

class UserManager:
    """Simple user management class."""

    def __init__(self):
        self.runtime = LocalRuntime()

    def create_user(self, name: str, email: str, age: int) -> dict:
        """Create a new user."""
        workflow = WorkflowBuilder()

        workflow.add_node("UserCreateNode", "create_user", {
            "name": name,
            "email": email,
            "age": age
        })

        results, run_id = self.runtime.execute(workflow.build())

        return {
            "success": True,
            "user": results["create_user"]["data"],
            "run_id": run_id
        }

    def get_user(self, user_id: int) -> dict:
        """Get user by ID."""
        workflow = WorkflowBuilder()

        workflow.add_node("UserReadNode", "get_user", {
            "id": user_id
        })

        results, run_id = self.runtime.execute(workflow.build())

        return {
            "success": True,
            "user": results["get_user"]["data"],
            "run_id": run_id
        }

    def update_user(self, user_id: int, **updates) -> dict:
        """Update user."""
        workflow = WorkflowBuilder()

        updates["updated_at"] = ":current_timestamp"

        workflow.add_node("UserUpdateNode", "update_user", {
            "id": user_id,
            **updates
        })

        results, run_id = self.runtime.execute(workflow.build())

        return {
            "success": True,
            "user": results["update_user"]["data"],
            "run_id": run_id
        }

    def delete_user(self, user_id: int) -> dict:
        """Delete user."""
        workflow = WorkflowBuilder()

        workflow.add_node("UserDeleteNode", "delete_user", {
            "id": user_id,
            "soft_delete": True
        })

        results, run_id = self.runtime.execute(workflow.build())

        return {
            "success": True,
            "deleted": results["delete_user"]["success"],
            "run_id": run_id
        }

    def list_users(self, active_only: bool = True, limit: int = 100) -> dict:
        """List users."""
        workflow = WorkflowBuilder()

        filter_params = {}
        if active_only:
            filter_params["active"] = True

        workflow.add_node("UserListNode", "list_users", {
            "filter": filter_params,
            "order_by": ["-created_at"],
            "limit": limit
        })

        results, run_id = self.runtime.execute(workflow.build())

        return {
            "success": True,
            "users": results["list_users"]["data"],
            "count": len(results["list_users"]["data"]),
            "run_id": run_id
        }

# Example usage
if __name__ == "__main__":
    # Initialize user manager
    user_manager = UserManager()

    # Create users
    print("Creating users...")
    user1 = user_manager.create_user("John Doe", "john@example.com", 30)
    user2 = user_manager.create_user("Jane Smith", "jane@example.com", 25)

    print(f"Created user 1: {user1['user']['name']}")
    print(f"Created user 2: {user2['user']['name']}")

    # Get users
    print("\nGetting users...")
    retrieved_user = user_manager.get_user(user1["user"]["id"])
    print(f"Retrieved user: {retrieved_user['user']['name']}")

    # Update user
    print("\nUpdating user...")
    updated_user = user_manager.update_user(
        user1["user"]["id"],
        name="John Smith",
        age=31
    )
    print(f"Updated user: {updated_user['user']['name']}, age: {updated_user['user']['age']}")

    # List users
    print("\nListing users...")
    users_list = user_manager.list_users(active_only=True, limit=10)
    print(f"Found {users_list['count']} users:")
    for user in users_list["users"]:
        print(f"  - {user['name']} ({user['email']})")

    # Delete user
    print("\nDeleting user...")
    delete_result = user_manager.delete_user(user2["user"]["id"])
    print(f"User deleted: {delete_result['deleted']}")

    # List users again
    print("\nListing users after deletion...")
    users_list = user_manager.list_users(active_only=True, limit=10)
    print(f"Found {users_list['count']} users:")
    for user in users_list["users"]:
        print(f"  - {user['name']} ({user['email']})")
```

## Testing

```python
# test_crud.py
import pytest
from app import UserManager

class TestUserManager:
    def setup_method(self):
        """Setup test environment."""
        self.user_manager = UserManager()

    def test_create_user(self):
        """Test user creation."""
        result = self.user_manager.create_user("Test User", "test@example.com", 25)

        assert result["success"] is True
        assert result["user"]["name"] == "Test User"
        assert result["user"]["email"] == "test@example.com"
        assert result["user"]["age"] == 25
        assert result["user"]["active"] is True

    def test_get_user(self):
        """Test user retrieval."""
        # Create user first
        create_result = self.user_manager.create_user("Test User", "test@example.com", 25)
        user_id = create_result["user"]["id"]

        # Get user
        result = self.user_manager.get_user(user_id)

        assert result["success"] is True
        assert result["user"]["id"] == user_id
        assert result["user"]["name"] == "Test User"

    def test_update_user(self):
        """Test user update."""
        # Create user first
        create_result = self.user_manager.create_user("Test User", "test@example.com", 25)
        user_id = create_result["user"]["id"]

        # Update user
        result = self.user_manager.update_user(user_id, name="Updated User", age=26)

        assert result["success"] is True
        assert result["user"]["name"] == "Updated User"
        assert result["user"]["age"] == 26

    def test_delete_user(self):
        """Test user deletion."""
        # Create user first
        create_result = self.user_manager.create_user("Test User", "test@example.com", 25)
        user_id = create_result["user"]["id"]

        # Delete user
        result = self.user_manager.delete_user(user_id)

        assert result["success"] is True
        assert result["deleted"] is True

    def test_list_users(self):
        """Test user listing."""
        # Create multiple users
        self.user_manager.create_user("User 1", "user1@example.com", 25)
        self.user_manager.create_user("User 2", "user2@example.com", 30)

        # List users
        result = self.user_manager.list_users(active_only=True, limit=10)

        assert result["success"] is True
        assert result["count"] >= 2
        assert len(result["users"]) >= 2

    def test_user_lifecycle(self):
        """Test complete user lifecycle."""
        # Create
        create_result = self.user_manager.create_user("Lifecycle User", "lifecycle@example.com", 28)
        user_id = create_result["user"]["id"]

        # Read
        read_result = self.user_manager.get_user(user_id)
        assert read_result["user"]["name"] == "Lifecycle User"

        # Update
        update_result = self.user_manager.update_user(user_id, name="Updated Lifecycle User")
        assert update_result["user"]["name"] == "Updated Lifecycle User"

        # Delete
        delete_result = self.user_manager.delete_user(user_id)
        assert delete_result["deleted"] is True

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

## Requirements

```txt
# requirements.txt
kailash>=0.6.6
pytest>=7.0.0
```

## Usage

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the example:**
   ```bash
   python app.py
   ```

3. **Run tests:**
   ```bash
   python test_crud.py
   ```

## What You'll Learn

- How to define simple models with DataFlow
- Basic CRUD operations using workflow nodes
- Error handling and validation
- Testing DataFlow applications
- Workflow patterns for database operations

## Next Steps

- **Enterprise Example**: [Enterprise Example](../enterprise/) - More advanced features
- **API Backend**: [API Backend Example](../api-backend/) - REST API with DataFlow
- **Data Migration**: [Data Migration Example](../data-migration/) - Bulk data processing

This example provides a solid foundation for building CRUD applications with DataFlow.
