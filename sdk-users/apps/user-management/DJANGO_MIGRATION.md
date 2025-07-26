# Django to Kailash User Management - Migration Guide

## 🔄 Why Migrate?

### Kailash Advantages over Django
- **Built-in Multi-tenancy**: Tenant isolation at the core
- **Enterprise Features**: Bulk operations, RBAC/ABAC, audit logging
- **Performance**: 200+ users/second bulk operations
- **Flexibility**: NoSQL-style attributes with PostgreSQL reliability
- **Modern Architecture**: Async-first, microservice-ready

## 📊 Feature Comparison

| Feature | Django | Kailash |
|---------|--------|---------|
| User Model | ✅ Built-in | ✅ UserManagementNode |
| Groups | ✅ django.contrib.auth | ✅ RoleManagementNode |
| Permissions | ✅ Model-based | ✅ Flexible string-based |
| Custom Fields | ⚠️ Extend User model | ✅ JSONB attributes |
| Multi-tenancy | ⚠️ Third-party packages | ✅ Native support |
| Bulk Operations | ❌ Manual implementation | ✅ Built-in |
| Audit Logging | ⚠️ Third-party | ✅ Built-in |
| Password Reset | ✅ Built-in views | ✅ Token-based API |
| Social Auth | ⚠️ Third-party | ✅ OAuth2 ready |

## 🚀 Migration Steps

### Step 1: Install Kailash

```bash
pip install kailash-sdk
```

### Step 2: Set Up Database

```python
from kailash.nodes.admin.schema_manager import AdminSchemaManager

# Your existing Django database can be used
db_config = {
    "connection_string": "postgresql://user:pass@localhost/djangodb",
    "database_type": "postgresql"
}

# Create Kailash tables (won't affect Django tables)
schema_manager = AdminSchemaManager(db_config)
schema_manager.create_full_schema()
```

### Step 3: Migration Script

```python
from django.contrib.auth.models import User as DjangoUser, Group
from kailash.nodes.admin import UserManagementNode, RoleManagementNode
import hashlib

# Initialize Kailash nodes
kailash_user = UserManagementNode()
kailash_role = RoleManagementNode()

# Configuration
tenant_id = "migrated_from_django"
db_config = {
    "connection_string": "postgresql://localhost/mydb",
    "database_type": "postgresql"
}

# Migrate Groups to Roles
print("Migrating Django Groups to Kailash Roles...")
role_mapping = {}

for group in Group.objects.all():
    # Get permissions for this group
    permissions = [
        f"{p.content_type.app_label}.{p.codename}"
        for p in group.permissions.all()
    ]

    # Create Kailash role
    result = kailash_role.execute(
        operation="create_role",
        tenant_id=tenant_id,
        database_config=db_config,
        role_data={
            "name": group.name,
            "description": f"Migrated from Django group: {group.name}",
            "permissions": permissions,
            "attributes": {
                "django_group_id": group.id
            }
        }
    )
    role_mapping[group.id] = result["result"]["role"]["role_id"]
    print(f"✅ Migrated group: {group.name}")

# Migrate Users
print("\nMigrating Django Users to Kailash...")
user_mapping = {}

for django_user in DjangoUser.objects.all():
    # Prepare user data
    user_data = {
        "email": django_user.email,
        "username": django_user.username,
        "first_name": django_user.first_name,
        "last_name": django_user.last_name,
        "attributes": {
            "django_user_id": django_user.id,
            "date_joined": django_user.date_joined.isoformat(),
            "last_login": django_user.last_login.isoformat() if django_user.last_login else None,
            "is_staff": django_user.is_staff,
            "is_superuser": django_user.is_superuser,
            "is_active": django_user.is_active
        }
    }

    # Determine status
    status = "active" if django_user.is_active else "inactive"

    # Create Kailash user
    result = kailash_user.execute(
        operation="create_user",
        tenant_id=tenant_id,
        database_config=db_config,
        user_data=user_data,
        password_hash=django_user.password  # Django passwords are already hashed
    )

    kailash_user_id = result["result"]["user"]["user_id"]
    user_mapping[django_user.id] = kailash_user_id

    # Assign roles based on groups
    for group in django_user.groups.all():
        if group.id in role_mapping:
            kailash_role.execute(
                operation="assign_user",
                tenant_id=tenant_id,
                database_config=db_config,
                user_id=kailash_user_id,
                role_id=role_mapping[group.id]
            )

    # Handle superuser
    if django_user.is_superuser:
        # Create or get superuser role
        superuser_role = kailash_role.execute(
            operation="create_role",
            tenant_id=tenant_id,
            database_config=db_config,
            role_data={
                "name": "superuser",
                "description": "Django superuser equivalent",
                "permissions": ["*"]  # All permissions
            }
        )

        kailash_role.execute(
            operation="assign_user",
            tenant_id=tenant_id,
            database_config=db_config,
            user_id=kailash_user_id,
            role_id=superuser_role["result"]["role"]["role_id"]
        )

    print(f"✅ Migrated user: {django_user.username}")

print(f"\n✅ Migration complete!")
print(f"   - Migrated {len(role_mapping)} roles")
print(f"   - Migrated {len(user_mapping)} users")
```

### Step 4: Update Your Code

#### Authentication Views

**Django:**
```python
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required

def login_view(request):
    username = request.POST['username']
    password = request.POST['password']
    user = authenticate(request, username=username, password=password)
    if user is not None:
        login(request, user)
        return redirect('home')
```

**Kailash:**
```python
from kailash.nodes.admin import UserManagementNode

user_manager = UserManagementNode()

@app.post("/login")
async def login_view(username: str, password: str):
    result = user_manager.execute(
        operation="authenticate",
        tenant_id="my_app",
        database_config=db_config,
        username=username,
        password=password
    )

    if result["authenticated"]:
        # Create session/JWT token
        return {"token": create_jwt_token(result["user_id"])}

    raise HTTPException(401, "Invalid credentials")
```

#### User Creation

**Django:**
```python
from django.contrib.auth.models import User

user = User.objects.create_user(
    username='john',
    email='john@example.com',
    password='password123'
)
user.first_name = 'John'
user.last_name = 'Doe'
user.save()
```

**Kailash:**
```python
user_manager.execute(
    operation="create_user",
    tenant_id="my_app",
    database_config=db_config,
    user_data={
        "username": "john",
        "email": "john@example.com",
        "first_name": "John",
        "last_name": "Doe"
    },
    password="password123"
)
```

#### Permission Checking

**Django:**
```python
if user.has_perm('app.add_model'):
    # User can add model

if user.groups.filter(name='editors').exists():
    # User is in editors group
```

**Kailash:**
```python
from kailash.nodes.admin import PermissionCheckNode

perm_checker = PermissionCheckNode()

# Check permission
result = perm_checker.execute(
    operation="check_permission",
    tenant_id="my_app",
    database_config=db_config,
    user_id=user_id,
    permission="app.add_model"
)

if result["has_permission"]:
    # User can add model

# Check role
user_roles = role_manager.execute(
    operation="get_user_roles",
    tenant_id="my_app",
    database_config=db_config,
    user_id=user_id
)

if any(role["name"] == "editors" for role in user_roles["result"]["roles"]):
    # User is in editors role
```

### Step 5: Middleware Integration

#### Django Middleware
```python
class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Set tenant based on subdomain
        request.tenant = get_tenant_from_request(request)
        response = self.get_response(request)
        return response
```

#### Kailash Middleware
```python
from kailash.api.middleware import create_gateway

app = create_gateway(title="My App")

@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    # Extract tenant from request
    tenant_id = request.headers.get("X-Tenant-ID", "default")
    request.state.tenant_id = tenant_id
    response = await call_next(request)
    return response
```

## 🔧 Common Patterns

### Custom User Model Fields

**Django:**
```python
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    department = models.CharField(max_length=100)
    employee_id = models.CharField(max_length=50)
```

**Kailash:**
```python
# No model needed - use attributes
user_data = {
    "email": "user@example.com",
    "username": "user",
    "attributes": {
        "department": "Engineering",
        "employee_id": "EMP001",
        # Add any custom fields here
    }
}
```

### Signals and Hooks

**Django:**
```python
from django.db.models.signals import post_save

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
```

**Kailash:**
```python
# Use workflow events or wrap operations
async def create_user_with_profile(user_data):
    # Create user
    user_result = user_manager.execute(
        operation="create_user",
        tenant_id="my_app",
        database_config=db_config,
        user_data=user_data,
        password=user_data.pop("password")
    )

    # Additional operations
    await send_welcome_email(user_result["result"]["user"]["email"])
    await create_default_settings(user_result["result"]["user"]["user_id"])

    return user_result
```

## 📋 Checklist

- [ ] Install Kailash SDK
- [ ] Create database schema
- [ ] Migrate existing users
- [ ] Migrate groups to roles
- [ ] Update authentication code
- [ ] Update permission checks
- [ ] Test user operations
- [ ] Update API endpoints
- [ ] Run parallel for testing
- [ ] Switch over production

## 🎯 Best Practices

1. **Run in Parallel**: Keep Django running while testing Kailash
2. **Gradual Migration**: Migrate feature by feature
3. **Test Thoroughly**: Especially authentication and permissions
4. **Keep Mapping**: Store Django ID → Kailash ID mappings
5. **Backup First**: Always backup before migration

## 🆘 Troubleshooting

### Issue: Password verification fails
**Solution**: Django uses PBKDF2 by default. For compatibility:
```python
# Option 1: Re-hash passwords on first login
# Option 2: Implement PBKDF2 verification in Kailash
# Option 3: Force password reset for all users
```

### Issue: Permission structure different
**Solution**: Map Django's app.permission to your structure:
```python
django_perm = "auth.change_user"
kailash_perm = "users.update"  # Your naming convention
```

### Issue: Session management
**Solution**: Use JWT tokens or Redis sessions:
```python
from kailash.middleware.session import SessionManager

session_manager = SessionManager(redis_url="redis://localhost")
```

## 📚 Resources

- [Kailash User Management Guide](./README.md)
- [API Reference](./API_REFERENCE.md)
- [Django Compatibility Layer](https://github.com/kailash/django-compat)
- [Migration Tools](https://github.com/kailash/migration-tools)
