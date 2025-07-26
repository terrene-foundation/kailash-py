# API Backend Example

Complete REST API backend built with DataFlow, featuring authentication, validation, and production-ready patterns.

## Overview

This example demonstrates building a production-grade REST API:
- **RESTful API design** with proper HTTP methods and status codes
- **JWT authentication** and authorization
- **Request validation** and error handling
- **API versioning** and documentation
- **Rate limiting** and security
- **Database operations** through DataFlow workflows
- **Testing and monitoring** for production deployment

## API Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Client App    │    │   API Gateway   │    │   DataFlow      │
│                 │───▶│   (FastAPI)     │───▶│   Workflows     │
│                 │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
   HTTP Requests           Route Handlers         Database Ops
   - JSON payload         - Authentication        - CRUD operations
   - Headers              - Validation           - Bulk operations
   - Query params         - Error handling       - Transactions
```

## Data Models

```python
# models.py
from kailash_dataflow import DataFlow
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, EmailStr, validator

db = DataFlow()

class UserRole(Enum):
    ADMIN = "admin"
    USER = "user"
    MANAGER = "manager"

@db.model
class User:
    """User model with authentication support."""
    email: str
    username: str
    password_hash: str
    first_name: str
    last_name: str
    role: UserRole = UserRole.USER
    is_active: bool = True
    is_verified: bool = False
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    __dataflow__ = {
        'soft_delete': True,
        'audit': True,
        'indexes': [
            {'name': 'idx_email', 'fields': ['email'], 'unique': True},
            {'name': 'idx_username', 'fields': ['username'], 'unique': True},
            {'name': 'idx_role', 'fields': ['role']},
            {'name': 'idx_active', 'fields': ['is_active']}
        ]
    }

@db.model
class APIKey:
    """API key for programmatic access."""
    user_id: int
    key_hash: str
    name: str
    permissions: List[str] = []
    is_active: bool = True
    expires_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    created_at: datetime

    __dataflow__ = {
        'indexes': [
            {'name': 'idx_user_key', 'fields': ['user_id', 'key_hash']},
            {'name': 'idx_key_hash', 'fields': ['key_hash'], 'unique': True}
        ]
    }

@db.model
class Category:
    """Product category."""
    name: str
    description: str
    slug: str
    parent_id: Optional[int] = None
    is_active: bool = True
    sort_order: int = 0
    metadata: Dict[str, Any] = {}

    __dataflow__ = {
        'indexes': [
            {'name': 'idx_slug', 'fields': ['slug'], 'unique': True},
            {'name': 'idx_parent', 'fields': ['parent_id']},
            {'name': 'idx_active_sort', 'fields': ['is_active', 'sort_order']}
        ]
    }

@db.model
class Product:
    """Product model with rich metadata."""
    name: str
    description: str
    sku: str
    price: float
    cost: Optional[float] = None
    category_id: int
    stock_quantity: int = 0
    weight: Optional[float] = None
    dimensions: Dict[str, float] = {}  # length, width, height
    attributes: Dict[str, Any] = {}
    tags: List[str] = []
    images: List[str] = []
    is_active: bool = True
    featured: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None

    __dataflow__ = {
        'indexes': [
            {'name': 'idx_sku', 'fields': ['sku'], 'unique': True},
            {'name': 'idx_category', 'fields': ['category_id']},
            {'name': 'idx_active_featured', 'fields': ['is_active', 'featured']},
            {'name': 'idx_price', 'fields': ['price']},
            {'name': 'idx_stock', 'fields': ['stock_quantity']}
        ]
    }

@db.model
class Order:
    """Order with comprehensive tracking."""
    user_id: int
    order_number: str
    status: str = "pending"  # pending, confirmed, shipped, delivered, cancelled
    subtotal: float
    tax_amount: float = 0.0
    shipping_amount: float = 0.0
    total: float
    currency: str = "USD"
    payment_method: str
    payment_status: str = "pending"  # pending, paid, failed, refunded
    shipping_address: Dict[str, str] = {}
    billing_address: Dict[str, str] = {}
    notes: Optional[str] = None
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    __dataflow__ = {
        'indexes': [
            {'name': 'idx_order_number', 'fields': ['order_number'], 'unique': True},
            {'name': 'idx_user_orders', 'fields': ['user_id', 'created_at']},
            {'name': 'idx_status', 'fields': ['status']},
            {'name': 'idx_payment_status', 'fields': ['payment_status']}
        ]
    }

@db.model
class OrderItem:
    """Individual items within an order."""
    order_id: int
    product_id: int
    quantity: int
    unit_price: float
    total_price: float
    product_snapshot: Dict[str, Any] = {}  # Product details at time of order

    __dataflow__ = {
        'indexes': [
            {'name': 'idx_order_items', 'fields': ['order_id']},
            {'name': 'idx_product_orders', 'fields': ['product_id']}
        ]
    }

# Pydantic models for API serialization
class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    first_name: str
    last_name: str
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    first_name: str
    last_name: str
    role: Optional[UserRole] = UserRole.USER

    @validator('username')
    def validate_username(cls, v):
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters')
        if not v.isalnum():
            raise ValueError('Username must be alphanumeric')
        return v.lower()

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

class ProductResponse(BaseModel):
    id: int
    name: str
    description: str
    sku: str
    price: float
    category_id: int
    stock_quantity: int
    weight: Optional[float] = None
    dimensions: Dict[str, float] = {}
    attributes: Dict[str, Any] = {}
    tags: List[str] = []
    images: List[str] = []
    is_active: bool
    featured: bool
    created_at: datetime

    class Config:
        from_attributes = True

class ProductCreate(BaseModel):
    name: str
    description: str
    sku: str
    price: float
    cost: Optional[float] = None
    category_id: int
    stock_quantity: int = 0
    weight: Optional[float] = None
    dimensions: Dict[str, float] = {}
    attributes: Dict[str, Any] = {}
    tags: List[str] = []
    images: List[str] = []
    featured: bool = False

    @validator('price')
    def validate_price(cls, v):
        if v < 0:
            raise ValueError('Price must be non-negative')
        return v

    @validator('sku')
    def validate_sku(cls, v):
        if len(v) < 3:
            raise ValueError('SKU must be at least 3 characters')
        return v.upper()

class OrderResponse(BaseModel):
    id: int
    user_id: int
    order_number: str
    status: str
    subtotal: float
    tax_amount: float
    shipping_amount: float
    total: float
    currency: str
    payment_status: str
    created_at: datetime
    items: List[Dict[str, Any]] = []

    class Config:
        from_attributes = True

class OrderCreate(BaseModel):
    items: List[Dict[str, Any]]  # [{"product_id": 1, "quantity": 2}, ...]
    shipping_address: Dict[str, str]
    billing_address: Optional[Dict[str, str]] = None
    payment_method: str
    notes: Optional[str] = None

    @validator('items')
    def validate_items(cls, v):
        if not v:
            raise ValueError('Order must have at least one item')

        for item in v:
            if 'product_id' not in item or 'quantity' not in item:
                raise ValueError('Each item must have product_id and quantity')
            if item['quantity'] <= 0:
                raise ValueError('Quantity must be positive')

        return v
```

## Authentication System

```python
# auth.py
import jwt
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from models import db, User, APIKey, UserRole

security = HTTPBearer()

class AuthManager:
    """JWT-based authentication manager."""

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.runtime = LocalRuntime()

    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash."""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

    def create_access_token(self, user_id: int, expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token."""
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(hours=24)

        to_encode = {
            "sub": str(user_id),
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "access"
        }

        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, user_id: int) -> str:
        """Create JWT refresh token."""
        expire = datetime.utcnow() + timedelta(days=30)

        to_encode = {
            "sub": str(user_id),
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "refresh"
        }

        return jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

    def register_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Register new user."""
        workflow = WorkflowBuilder()

        # Check if email/username exists
        workflow.add_node("UserListNode", "check_existing", {
            "filter": {
                "$or": [
                    {"email": user_data["email"]},
                    {"username": user_data["username"]}
                ]
            },
            "limit": 1
        })

        # Hash password and create user
        workflow.add_node("PythonCodeNode", "process_registration", {
            "code": f"""
existing_users = get_input_data("check_existing")["data"]

if existing_users:
    result = {{"error": "Email or username already exists"}}
else:
    # Hash password
    import bcrypt
    password = "{user_data['password']}"
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    # Prepare user data
    user_data = {{
        "email": "{user_data['email']}",
        "username": "{user_data['username']}",
        "password_hash": password_hash,
        "first_name": "{user_data['first_name']}",
        "last_name": "{user_data['last_name']}",
        "role": "{user_data.get('role', 'user')}"
    }}

    result = {{"user_data": user_data, "proceed": True}}
"""
        })

        # Create user if validation passes
        workflow.add_node("UserCreateNode", "create_user", {
            "email": ":email",
            "username": ":username",
            "password_hash": ":password_hash",
            "first_name": ":first_name",
            "last_name": ":last_name",
            "role": ":role"
        })

        # Connect workflow
        workflow.add_connection("check_existing", "result", "process_registration", "input")
        workflow.add_connection("source", "result", "target", "input")  # Fixed complex pattern

        results, run_id = self.runtime.execute(workflow.build())

        # Check for errors
        if "error" in results["process_registration"]:
            raise HTTPException(status_code=400, detail=results["process_registration"]["error"])

        user = results["create_user"]["data"]

        # Generate tokens
        access_token = self.create_access_token(user["id"])
        refresh_token = self.create_refresh_token(user["id"])

        return {
            "user": user,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }

    def authenticate_user(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate user with email/password."""
        workflow = WorkflowBuilder()

        # Get user by email
        workflow.add_node("UserListNode", "get_user", {
            "filter": {"email": email, "is_active": True},
            "limit": 1
        })

        # Verify password
        workflow.add_node("PythonCodeNode", "verify_password", {
            "code": f"""
users = get_input_data("get_user")["data"]

if not users:
    result = {{"error": "Invalid credentials"}}
else:
    user = users[0]
    import bcrypt
    password = "{password}"

    if bcrypt.checkpw(password.encode('utf-8'), user["password_hash"].encode('utf-8')):
        result = {{"user": user, "authenticated": True}}
    else:
        result = {{"error": "Invalid credentials"}}
"""
        })

        # Update last login
        workflow.add_node("UserUpdateNode", "update_login", {
            "id": ":user_id",
            "last_login": ":current_timestamp"
        })

        # Connect workflow
        workflow.add_connection("get_user", "result", "verify_password", "input")
        workflow.add_connection("verify_password", "update_login", "user.id", "user_id")

        results, run_id = self.runtime.execute(workflow.build())

        # Check authentication result
        if "error" in results["verify_password"]:
            raise HTTPException(status_code=401, detail=results["verify_password"]["error"])

        user = results["verify_password"]["user"]

        # Generate tokens
        access_token = self.create_access_token(user["id"])
        refresh_token = self.create_refresh_token(user["id"])

        return {
            "user": user,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }

    def get_current_user(self, credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
        """Get current user from JWT token."""
        payload = self.verify_token(credentials.credentials)

        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")

        user_id = int(payload.get("sub"))

        # Get user details
        workflow = WorkflowBuilder()

        workflow.add_node("UserReadNode", "get_user", {
            "id": user_id
        })

        results, run_id = self.runtime.execute(workflow.build())
        user = results["get_user"]["data"]

        if not user or not user["is_active"]:
            raise HTTPException(status_code=401, detail="User not found or inactive")

        return user

def require_role(required_role: UserRole):
    """Decorator to require specific user role."""
    def role_checker(current_user: Dict = Depends(auth_manager.get_current_user)):
        user_role = UserRole(current_user["role"])

        # Admin can access everything
        if user_role == UserRole.ADMIN:
            return current_user

        # Check specific role requirement
        if user_role != required_role:
            raise HTTPException(
                status_code=403,
                detail=f"Requires {required_role.value} role"
            )

        return current_user

    return role_checker

# Global auth manager instance
auth_manager = AuthManager(secret_key="your-secret-key-here")  # Use env variable in production
```

## API Routes

```python
# api.py
from fastapi import FastAPI, HTTPException, Depends, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
from datetime import datetime
import uvicorn

from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from models import (
    db, User, Product, Category, Order, OrderItem,
    UserResponse, UserCreate, ProductResponse, ProductCreate,
    OrderResponse, OrderCreate, UserRole
)
from auth import auth_manager, require_role

# Initialize FastAPI app
app = FastAPI(
    title="DataFlow E-commerce API",
    description="Complete e-commerce API built with DataFlow",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add security middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Configure for production
)

# Global runtime instance
runtime = LocalRuntime()

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "status_code": 500}
    )

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# Authentication endpoints
@app.post("/auth/register", response_model=Dict[str, Any])
async def register(user_data: UserCreate):
    """Register new user."""
    return auth_manager.register_user(user_data.dict())

@app.post("/auth/login", response_model=Dict[str, Any])
async def login(email: str, password: str):
    """User login."""
    return auth_manager.authenticate_user(email, password)

@app.get("/auth/me", response_model=UserResponse)
async def get_current_user(current_user: Dict = Depends(auth_manager.get_current_user)):
    """Get current user profile."""
    return UserResponse(**current_user)

# User management endpoints
@app.get("/users", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    role: Optional[UserRole] = None,
    is_active: Optional[bool] = None,
    current_user: Dict = Depends(require_role(UserRole.ADMIN))
):
    """List users (admin only)."""
    workflow = WorkflowBuilder()

    # Build filter
    filter_params = {}
    if role:
        filter_params["role"] = role.value
    if is_active is not None:
        filter_params["is_active"] = is_active

    workflow.add_node("UserListNode", "list_users", {
        "filter": filter_params,
        "offset": skip,
        "limit": limit,
        "order_by": ["-created_at"]
    })

    results, run_id = runtime.execute(workflow.build())
    users = results["list_users"]["data"]

    return [UserResponse(**user) for user in users]

@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int = Path(..., gt=0),
    current_user: Dict = Depends(auth_manager.get_current_user)
):
    """Get user by ID."""
    # Users can only see their own profile unless they're admin
    if current_user["id"] != user_id and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    workflow = WorkflowBuilder()

    workflow.add_node("UserReadNode", "get_user", {
        "id": user_id
    })

    results, run_id = runtime.execute(workflow.build())
    user = results["get_user"]["data"]

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(**user)

@app.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int = Path(..., gt=0),
    updates: Dict[str, Any] = {},
    current_user: Dict = Depends(auth_manager.get_current_user)
):
    """Update user."""
    # Users can only update their own profile unless they're admin
    if current_user["id"] != user_id and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    # Remove sensitive fields for non-admin users
    if current_user["role"] != "admin":
        updates.pop("role", None)
        updates.pop("is_active", None)

    workflow = WorkflowBuilder()

    workflow.add_node("UserUpdateNode", "update_user", {
        "id": user_id,
        **updates,
        "updated_at": ":current_timestamp"
    })

    results, run_id = runtime.execute(workflow.build())
    user = results["update_user"]["data"]

    return UserResponse(**user)

# Category endpoints
@app.get("/categories", response_model=List[Dict[str, Any]])
async def list_categories(
    parent_id: Optional[int] = None,
    is_active: Optional[bool] = True
):
    """List product categories."""
    workflow = WorkflowBuilder()

    filter_params = {}
    if parent_id is not None:
        filter_params["parent_id"] = parent_id
    if is_active is not None:
        filter_params["is_active"] = is_active

    workflow.add_node("CategoryListNode", "list_categories", {
        "filter": filter_params,
        "order_by": ["sort_order", "name"]
    })

    results, run_id = runtime.execute(workflow.build())
    return results["list_categories"]["data"]

@app.post("/categories", response_model=Dict[str, Any])
async def create_category(
    category_data: Dict[str, Any],
    current_user: Dict = Depends(require_role(UserRole.ADMIN))
):
    """Create new category (admin only)."""
    workflow = WorkflowBuilder()

    workflow.add_node("CategoryCreateNode", "create_category", category_data)

    results, run_id = runtime.execute(workflow.build())
    return results["create_category"]["data"]

# Product endpoints
@app.get("/products", response_model=List[ProductResponse])
async def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    category_id: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    search: Optional[str] = None,
    featured: Optional[bool] = None,
    is_active: Optional[bool] = True
):
    """List products with filtering and search."""
    workflow = WorkflowBuilder()

    # Build filter
    filter_params = {}
    if category_id:
        filter_params["category_id"] = category_id
    if min_price is not None:
        filter_params["price"] = {"$gte": min_price}
    if max_price is not None:
        if "price" in filter_params:
            filter_params["price"]["$lte"] = max_price
        else:
            filter_params["price"] = {"$lte": max_price}
    if featured is not None:
        filter_params["featured"] = featured
    if is_active is not None:
        filter_params["is_active"] = is_active
    if search:
        filter_params["$or"] = [
            {"name": {"$regex": search}},
            {"description": {"$regex": search}},
            {"sku": {"$regex": search}}
        ]

    workflow.add_node("ProductListNode", "list_products", {
        "filter": filter_params,
        "offset": skip,
        "limit": limit,
        "order_by": ["-featured", "-created_at"]
    })

    results, run_id = runtime.execute(workflow.build())
    products = results["list_products"]["data"]

    return [ProductResponse(**product) for product in products]

@app.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: int = Path(..., gt=0)):
    """Get product by ID."""
    workflow = WorkflowBuilder()

    workflow.add_node("ProductReadNode", "get_product", {
        "id": product_id
    })

    results, run_id = runtime.execute(workflow.build())
    product = results["get_product"]["data"]

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return ProductResponse(**product)

@app.post("/products", response_model=ProductResponse)
async def create_product(
    product_data: ProductCreate,
    current_user: Dict = Depends(require_role(UserRole.ADMIN))
):
    """Create new product (admin only)."""
    workflow = WorkflowBuilder()

    workflow.add_node("ProductCreateNode", "create_product", product_data.dict())

    results, run_id = runtime.execute(workflow.build())
    product = results["create_product"]["data"]

    return ProductResponse(**product)

@app.put("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int = Path(..., gt=0),
    updates: Dict[str, Any] = {},
    current_user: Dict = Depends(require_role(UserRole.ADMIN))
):
    """Update product (admin only)."""
    workflow = WorkflowBuilder()

    workflow.add_node("ProductUpdateNode", "update_product", {
        "id": product_id,
        **updates,
        "updated_at": ":current_timestamp"
    })

    results, run_id = runtime.execute(workflow.build())
    product = results["update_product"]["data"]

    return ProductResponse(**product)

@app.delete("/products/{product_id}")
async def delete_product(
    product_id: int = Path(..., gt=0),
    current_user: Dict = Depends(require_role(UserRole.ADMIN))
):
    """Delete product (admin only)."""
    workflow = WorkflowBuilder()

    workflow.add_node("ProductDeleteNode", "delete_product", {
        "id": product_id,
        "soft_delete": True
    })

    results, run_id = runtime.execute(workflow.build())

    return {"message": "Product deleted successfully"}

# Order endpoints
@app.get("/orders", response_model=List[OrderResponse])
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = None,
    current_user: Dict = Depends(auth_manager.get_current_user)
):
    """List orders for current user or all orders for admin."""
    workflow = WorkflowBuilder()

    filter_params = {}

    # Non-admin users can only see their own orders
    if current_user["role"] != "admin":
        filter_params["user_id"] = current_user["id"]

    if status:
        filter_params["status"] = status

    workflow.add_node("OrderListNode", "list_orders", {
        "filter": filter_params,
        "offset": skip,
        "limit": limit,
        "order_by": ["-created_at"],
        "include": ["items"]
    })

    results, run_id = runtime.execute(workflow.build())
    orders = results["list_orders"]["data"]

    return [OrderResponse(**order) for order in orders]

@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int = Path(..., gt=0),
    current_user: Dict = Depends(auth_manager.get_current_user)
):
    """Get order by ID."""
    workflow = WorkflowBuilder()

    workflow.add_node("OrderReadNode", "get_order", {
        "id": order_id,
        "include": ["items"]
    })

    results, run_id = runtime.execute(workflow.build())
    order = results["get_order"]["data"]

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Users can only see their own orders unless they're admin
    if order["user_id"] != current_user["id"] and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    return OrderResponse(**order)

@app.post("/orders", response_model=OrderResponse)
async def create_order(
    order_data: OrderCreate,
    current_user: Dict = Depends(auth_manager.get_current_user)
):
    """Create new order."""
    workflow = WorkflowBuilder()

    # Calculate order totals
    workflow.add_node("PythonCodeNode", "calculate_totals", {
        "code": f"""
items = {order_data.items}
subtotal = 0.0
order_items = []

# Get product details and calculate totals
for item in items:
    product_workflow = WorkflowBuilder()
    product_workflow.add_node("ProductReadNode", "get_product", {{
        "id": item["product_id"]
    }})
    product_results, _ = runtime.execute(product_workflow.build())
    product = product_results["get_product"]["data"]

    if not product:
        raise Exception(f"Product {{item['product_id']}} not found")

    if product["stock_quantity"] < item["quantity"]:
        raise Exception(f"Insufficient stock for product {{product['name']}}")

    item_total = product["price"] * item["quantity"]
    subtotal += item_total

    order_items.append({{
        "product_id": item["product_id"],
        "quantity": item["quantity"],
        "unit_price": product["price"],
        "total_price": item_total,
        "product_snapshot": {{
            "name": product["name"],
            "sku": product["sku"],
            "price": product["price"]
        }}
    }})

# Calculate tax and shipping (simplified)
tax_rate = 0.08  # 8% tax
shipping_amount = 9.99 if subtotal < 50 else 0  # Free shipping over $50

tax_amount = subtotal * tax_rate
total = subtotal + tax_amount + shipping_amount

# Generate order number
import uuid
order_number = f"ORD-{{str(uuid.uuid4())[:8].upper()}}"

result = {{
    "order_number": order_number,
    "subtotal": subtotal,
    "tax_amount": tax_amount,
    "shipping_amount": shipping_amount,
    "total": total,
    "order_items": order_items
}}
"""
    })

    # Create order
    workflow.add_node("OrderCreateNode", "create_order", {
        "user_id": current_user["id"],
        "order_number": ":order_number",
        "subtotal": ":subtotal",
        "tax_amount": ":tax_amount",
        "shipping_amount": ":shipping_amount",
        "total": ":total",
        "currency": "USD",
        "payment_method": order_data.payment_method,
        "shipping_address": order_data.shipping_address,
        "billing_address": order_data.billing_address or order_data.shipping_address,
        "notes": order_data.notes
    })

    # Create order items
    workflow.add_node("OrderItemBulkCreateNode", "create_order_items", {
        "data": ":order_items_with_order_id"
    })

    # Update product stock
    workflow.add_node("PythonCodeNode", "update_stock", {
        "code": """
order_items = get_input_data("calculate_totals")["order_items"]

for item in order_items:
    stock_workflow = WorkflowBuilder()
    stock_workflow.add_node("ProductUpdateNode", "update_stock", {
        "id": item["product_id"],
        "stock_quantity": f"stock_quantity - {item['quantity']}"
    })
    runtime.execute(stock_workflow.build())

result = {"items_updated": len(order_items)}
"""
    })

    # Connect workflow
    workflow.add_connection("calculate_totals", "result", "create_order", "input")
    workflow.add_connection("create_order", "create_order_items", "order_items", "order_items_with_order_id")
    workflow.add_connection("create_order_items", "result", "update_stock", "input")

    results, run_id = runtime.execute(workflow.build())
    order = results["create_order"]["data"]
    order["items"] = results["create_order_items"]["data"]

    return OrderResponse(**order)

@app.put("/orders/{order_id}/status")
async def update_order_status(
    order_id: int = Path(..., gt=0),
    status: str = Query(...),
    current_user: Dict = Depends(require_role(UserRole.ADMIN))
):
    """Update order status (admin only)."""
    valid_statuses = ["pending", "confirmed", "shipped", "delivered", "cancelled"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    workflow = WorkflowBuilder()

    updates = {"status": status}
    if status == "shipped":
        updates["shipped_at"] = ":current_timestamp"
    elif status == "delivered":
        updates["delivered_at"] = ":current_timestamp"

    workflow.add_node("OrderUpdateNode", "update_order_status", {
        "id": order_id,
        **updates,
        "updated_at": ":current_timestamp"
    })

    results, run_id = runtime.execute(workflow.build())

    return {"message": f"Order status updated to {status}"}

# Analytics endpoints (admin only)
@app.get("/analytics/sales")
async def get_sales_analytics(
    days: int = Query(30, ge=1, le=365),
    current_user: Dict = Depends(require_role(UserRole.ADMIN))
):
    """Get sales analytics (admin only)."""
    workflow = WorkflowBuilder()

    workflow.add_node("PythonCodeNode", "calculate_analytics", {
        "code": f"""
from datetime import datetime, timedelta

end_date = datetime.now()
start_date = end_date - timedelta(days={days})

# Get orders in date range
orders_workflow = WorkflowBuilder()
orders_workflow.add_node("OrderListNode", "get_orders", {{
    "filter": {{
        "created_at": {{"$gte": start_date.isoformat()}},
        "status": {{"$ne": "cancelled"}}
    }},
    "include": ["items"]
}})
orders_results, _ = runtime.execute(orders_workflow.build())
orders = orders_results["get_orders"]["data"]

# Calculate metrics
total_revenue = sum(order["total"] for order in orders)
total_orders = len(orders)
avg_order_value = total_revenue / total_orders if total_orders > 0 else 0

# Product sales
product_sales = {{}}
for order in orders:
    for item in order.get("items", []):
        product_id = item["product_id"]
        if product_id not in product_sales:
            product_sales[product_id] = {{"quantity": 0, "revenue": 0}}
        product_sales[product_id]["quantity"] += item["quantity"]
        product_sales[product_id]["revenue"] += item["total_price"]

# Daily sales
daily_sales = {{}}
for order in orders:
    date = order["created_at"][:10]  # YYYY-MM-DD
    if date not in daily_sales:
        daily_sales[date] = {{"orders": 0, "revenue": 0}}
    daily_sales[date]["orders"] += 1
    daily_sales[date]["revenue"] += order["total"]

result = {{
    "period_days": {days},
    "total_revenue": total_revenue,
    "total_orders": total_orders,
    "average_order_value": avg_order_value,
    "daily_sales": daily_sales,
    "top_products": sorted(
        [{{"product_id": k, **v}} for k, v in product_sales.items()],
        key=lambda x: x["revenue"],
        reverse=True
    )[:10]
}}
"""
    })

    results, run_id = runtime.execute(workflow.build())
    return results["calculate_analytics"]

if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        access_log=True
    )
```

## Testing the API

```python
# test_api.py
import pytest
import asyncio
from httpx import AsyncClient
from fastapi.testclient import TestClient
from api import app
from models import db
from auth import auth_manager

client = TestClient(app)

class TestAPIEndpoints:
    def setup_method(self):
        """Setup test environment."""
        # Create test database or use test fixtures
        self.test_user_data = {
            "email": "test@example.com",
            "username": "testuser",
            "password": "testpassword123",
            "first_name": "Test",
            "last_name": "User"
        }

        self.test_product_data = {
            "name": "Test Product",
            "description": "A test product",
            "sku": "TEST-001",
            "price": 29.99,
            "category_id": 1,
            "stock_quantity": 100
        }

    def test_health_check(self):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_user_registration(self):
        """Test user registration."""
        response = client.post("/auth/register", json=self.test_user_data)
        assert response.status_code == 200

        data = response.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == self.test_user_data["email"]

    def test_user_login(self):
        """Test user login."""
        # First register user
        client.post("/auth/register", json=self.test_user_data)

        # Then login
        response = client.post("/auth/login", params={
            "email": self.test_user_data["email"],
            "password": self.test_user_data["password"]
        })

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    def test_protected_endpoint(self):
        """Test protected endpoint access."""
        # Try without token
        response = client.get("/auth/me")
        assert response.status_code == 403

        # Register and get token
        reg_response = client.post("/auth/register", json=self.test_user_data)
        token = reg_response.json()["access_token"]

        # Try with token
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/auth/me", headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert data["email"] == self.test_user_data["email"]

    def test_product_listing(self):
        """Test product listing."""
        response = client.get("/products")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

    def test_product_search(self):
        """Test product search and filtering."""
        # Test search
        response = client.get("/products?search=test")
        assert response.status_code == 200

        # Test price filtering
        response = client.get("/products?min_price=10&max_price=50")
        assert response.status_code == 200

        # Test category filtering
        response = client.get("/products?category_id=1")
        assert response.status_code == 200

    def test_product_creation_requires_admin(self):
        """Test that product creation requires admin role."""
        # Register regular user
        reg_response = client.post("/auth/register", json=self.test_user_data)
        token = reg_response.json()["access_token"]

        headers = {"Authorization": f"Bearer {token}"}
        response = client.post("/products", json=self.test_product_data, headers=headers)

        # Should fail because user is not admin
        assert response.status_code == 403

    def test_order_creation(self):
        """Test order creation workflow."""
        # Register user and get token
        reg_response = client.post("/auth/register", json=self.test_user_data)
        token = reg_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create order
        order_data = {
            "items": [{"product_id": 1, "quantity": 2}],
            "shipping_address": {
                "street": "123 Main St",
                "city": "Test City",
                "state": "TS",
                "postal_code": "12345",
                "country": "US"
            },
            "payment_method": "credit_card"
        }

        response = client.post("/orders", json=order_data, headers=headers)

        if response.status_code == 200:
            data = response.json()
            assert "order_number" in data
            assert data["user_id"] == reg_response.json()["user"]["id"]

    def test_order_listing_authorization(self):
        """Test order listing authorization."""
        # Register two users
        user1_data = {**self.test_user_data, "email": "user1@example.com", "username": "user1"}
        user2_data = {**self.test_user_data, "email": "user2@example.com", "username": "user2"}

        reg1 = client.post("/auth/register", json=user1_data)
        reg2 = client.post("/auth/register", json=user2_data)

        token1 = reg1.json()["access_token"]
        token2 = reg2.json()["access_token"]

        # User 1 should only see their orders
        headers1 = {"Authorization": f"Bearer {token1}"}
        response1 = client.get("/orders", headers=headers1)
        assert response1.status_code == 200

        # User 2 should only see their orders
        headers2 = {"Authorization": f"Bearer {token2}"}
        response2 = client.get("/orders", headers=headers2)
        assert response2.status_code == 200

    def test_analytics_requires_admin(self):
        """Test that analytics endpoints require admin role."""
        # Register regular user
        reg_response = client.post("/auth/register", json=self.test_user_data)
        token = reg_response.json()["access_token"]

        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/analytics/sales", headers=headers)

        # Should fail because user is not admin
        assert response.status_code == 403

    def test_input_validation(self):
        """Test input validation."""
        # Test invalid email
        invalid_user = {**self.test_user_data, "email": "invalid-email"}
        response = client.post("/auth/register", json=invalid_user)
        assert response.status_code == 422

        # Test short password
        invalid_user = {**self.test_user_data, "password": "123"}
        response = client.post("/auth/register", json=invalid_user)
        assert response.status_code == 422

        # Test negative price
        invalid_product = {**self.test_product_data, "price": -10}
        # Would need admin token to test this properly

    def test_pagination(self):
        """Test pagination parameters."""
        response = client.get("/products?skip=0&limit=10")
        assert response.status_code == 200

        response = client.get("/products?skip=10&limit=5")
        assert response.status_code == 200

    def test_error_handling(self):
        """Test error handling."""
        # Test 404 for non-existent product
        response = client.get("/products/99999")
        assert response.status_code == 404

        # Test 401 for invalid token
        headers = {"Authorization": "Bearer invalid_token"}
        response = client.get("/auth/me", headers=headers)
        assert response.status_code == 401

# Performance tests
class TestAPIPerformance:
    def test_concurrent_requests(self):
        """Test handling concurrent requests."""
        import concurrent.futures
        import time

        def make_request():
            response = client.get("/products")
            return response.status_code

        # Test 10 concurrent requests
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [future.result() for future in futures]
        end_time = time.time()

        # All requests should succeed
        assert all(status == 200 for status in results)

        # Should complete within reasonable time
        assert end_time - start_time < 5.0

    def test_large_product_list(self):
        """Test performance with large product lists."""
        response = client.get("/products?limit=100")
        assert response.status_code == 200

        # Response should be reasonably fast
        # This would be more meaningful with actual data

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

## Production Configuration

```python
# config.py
import os
from typing import Optional

class Settings:
    """Application settings."""

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # API
    API_TITLE: str = "DataFlow E-commerce API"
    API_VERSION: str = "1.0.0"
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # CORS
    ALLOWED_ORIGINS: list = os.getenv("ALLOWED_ORIGINS", "*").split(",")

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
    RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", "60"))

    # Email (for notifications)
    SMTP_SERVER: Optional[str] = os.getenv("SMTP_SERVER")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: Optional[str] = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD: Optional[str] = os.getenv("SMTP_PASSWORD")

    # File storage
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", "10485760"))  # 10MB

    # Monitoring
    ENABLE_METRICS: bool = os.getenv("ENABLE_METRICS", "true").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

settings = Settings()
```

## Requirements

```txt
# requirements.txt
kailash>=0.6.6
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic[email]>=2.4.0
python-multipart>=0.0.6
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
httpx>=0.25.0
pytest>=7.4.0
pytest-asyncio>=0.21.0
```

## Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start application
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://api_user:password@db:5432/ecommerce_api
      - SECRET_KEY=your-production-secret-key
      - ALLOWED_ORIGINS=https://yourdomain.com
    depends_on:
      - db
      - redis
    restart: unless-stopped

  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=ecommerce_api
      - POSTGRES_USER=api_user
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - api
    restart: unless-stopped

volumes:
  postgres_data:
```

## Usage

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment:**
   ```bash
   export DATABASE_URL="postgresql://user:password@localhost/ecommerce"
   export SECRET_KEY="your-secret-key"
   ```

3. **Run the API:**
   ```bash
   python api.py
   ```

4. **Access documentation:**
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

5. **Run tests:**
   ```bash
   python test_api.py
   ```

6. **Deploy with Docker:**
   ```bash
   docker-compose up -d
   ```

## What You'll Learn

- Building production-ready REST APIs with FastAPI
- JWT authentication and authorization
- Request validation with Pydantic
- Database operations through DataFlow workflows
- API testing strategies
- Error handling and middleware
- Rate limiting and security
- Production deployment with Docker

## Next Steps

- **Simple CRUD**: [Simple CRUD Example](../simple-crud/) - Basic patterns
- **Enterprise Features**: [Enterprise Example](../enterprise/) - Advanced security
- **Data Migration**: [Data Migration Example](../data-migration/) - Large-scale processing
- **Production Deployment**: [Deployment Guide](../../docs/production/deployment.md)

This example provides a complete, production-ready API backend with authentication, validation, and all the features needed for a modern e-commerce application.
