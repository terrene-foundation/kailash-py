"""
Enhanced Database Repositories for Kailash Middleware

Uses SDK database nodes for all database operations instead of raw SQLAlchemy
or other database libraries. Provides consistent patterns and automatic features
like connection pooling, retry logic, and monitoring.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from ...nodes.data import AsyncSQLDatabaseNode, SQLDatabaseNode
from ...nodes.security import CredentialManagerNode
from ...nodes.transform import DataTransformer

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository class using SDK database nodes."""

    def __init__(self, connection_string: str, table_name: str, use_async: bool = True):
        self.connection_string = connection_string
        self.table_name = table_name
        self.use_async = use_async

        # Use appropriate database node
        if use_async:
            self.db_node = AsyncSQLDatabaseNode(
                name=f"{table_name}_async_db",
                connection_string=connection_string,
                pool_size=10,
                max_overflow=20,
            )
        else:
            self.db_node = SQLDatabaseNode(
                name=f"{table_name}_db", connection_string=connection_string
            )

        # Data transformer for result mapping
        self.transformer = DataTransformer(name=f"{table_name}_transformer")

        # Credential management for database security
        self.credential_manager = CredentialManagerNode(
            name=f"{table_name}_credentials",
            credential_name="database_secrets",
            credential_type="database",
        )

    async def _execute_query(
        self, query: str, params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Execute database query using SDK node."""
        try:
            if self.use_async:
                result = await self.db_node.execute_async(
                    query=query, params=params or {}
                )
            else:
                result = self.db_node.execute(query=query, params=params or {})

            return result
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            raise

    async def _transform_result(self, data: Any, schema: Dict[str, str]) -> Any:
        """Transform database result using DataTransformer."""
        if not data:
            return data

        result = await self.transformer.execute(data=data, schema=schema)

        return result["result"]

    async def _log_operation(
        self, operation: str, entity_id: str = None, details: Dict[str, Any] = None
    ):
        """Log database operation for audit trail."""
        logger.info(
            f"Database operation: {self.table_name}_{operation} for entity {entity_id}"
        )


class SessionRepository(BaseRepository):
    """Repository for session management using SDK database nodes."""

    def __init__(self, connection_string: str):
        super().__init__(connection_string, "sessions", use_async=True)

    async def create_session(self, user_id: str) -> str:
        """Create a new session."""
        session_id = str(uuid4())
        await self._execute_query(
            "INSERT INTO sessions (id, user_id, created_at, active) VALUES (?, ?, ?, ?)",
            {
                "id": session_id,
                "user_id": user_id,
                "created_at": datetime.now(timezone.utc),
                "active": True,
            },
        )
        await self._log_operation("create", session_id)
        return session_id

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session by ID."""
        result = await self._execute_query(
            "SELECT * FROM sessions WHERE id = ?", {"id": session_id}
        )
        return (
            result.get("result", {}).get("rows", [{}])[0]
            if result.get("result", {}).get("rows")
            else None
        )


class WorkflowRepository(BaseRepository):
    """Repository for workflow management using SDK database nodes."""

    def __init__(self, connection_string: str):
        super().__init__(connection_string, "workflows", use_async=True)

    async def create_workflow(self, workflow_config: Dict[str, Any]) -> str:
        """Create a new workflow."""
        workflow_id = str(uuid4())
        await self._execute_query(
            "INSERT INTO workflows (id, name, config, created_at) VALUES (?, ?, ?, ?)",
            {
                "id": workflow_id,
                "name": workflow_config.get("name", "unnamed"),
                "config": json.dumps(workflow_config),
                "created_at": datetime.now(timezone.utc),
            },
        )
        await self._log_operation("create", workflow_id)
        return workflow_id

    async def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow by ID."""
        result = await self._execute_query(
            "SELECT * FROM workflows WHERE id = ?", {"id": workflow_id}
        )
        return (
            result.get("result", {}).get("rows", [{}])[0]
            if result.get("result", {}).get("rows")
            else None
        )


class MiddlewareWorkflowRepository(BaseRepository):
    """Workflow repository using SDK database nodes."""

    def __init__(self, connection_string: str):
        super().__init__(connection_string, "workflows")
        self._ensure_table()

    def _ensure_table(self):
        """Ensure workflow table exists."""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS workflows (
            id VARCHAR(255) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            config JSON NOT NULL,
            created_by VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            metadata JSON
        )
        """

        # Execute synchronously for table creation
        sync_db = SQLDatabaseNode(
            name="table_creator", connection_string=self.connection_string
        )
        sync_db.execute(query=create_table_query)

    async def create(self, workflow_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new workflow."""
        workflow_id = workflow_data.get("id", str(uuid4()))

        query = """
        INSERT INTO workflows (id, name, description, config, created_by, metadata)
        VALUES (:id, :name, :description, :config, :created_by, :metadata)
        RETURNING *
        """

        params = {
            "id": workflow_id,
            "name": workflow_data["name"],
            "description": workflow_data.get("description", ""),
            "config": json.dumps(workflow_data.get("config", {})),
            "created_by": workflow_data.get("created_by"),
            "metadata": json.dumps(workflow_data.get("metadata", {})),
        }

        result = await self._execute_query(query, params)

        if result["rows"]:
            workflow = await self._transform_workflow(result["rows"][0])
            await self._log_operation(
                "create", workflow_id, {"name": workflow_data["name"]}
            )
            return workflow

        raise Exception("Failed to create workflow")

    async def get(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow by ID."""
        query = "SELECT * FROM workflows WHERE id = :id AND is_active = TRUE"
        result = await self._execute_query(query, {"id": workflow_id})

        if result["rows"]:
            workflow = await self._transform_workflow(result["rows"][0])
            await self._log_operation("read", workflow_id)
            return workflow

        return None

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        created_by: str = None,
        is_active: bool = True,
    ) -> List[Dict[str, Any]]:
        """List workflows with filtering."""
        query = """
        SELECT * FROM workflows
        WHERE is_active = :is_active
        """
        params = {"is_active": is_active}

        if created_by:
            query += " AND created_by = :created_by"
            params["created_by"] = created_by

        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        params.update({"limit": limit, "offset": offset})

        result = await self._execute_query(query, params)

        workflows = []
        for row in result["rows"]:
            workflow = await self._transform_workflow(row)
            workflows.append(workflow)

        await self._log_operation("list", details={"count": len(workflows)})
        return workflows

    async def update(self, workflow_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update workflow."""
        set_clauses = []
        params = {"id": workflow_id}

        if "name" in updates:
            set_clauses.append("name = :name")
            params["name"] = updates["name"]

        if "description" in updates:
            set_clauses.append("description = :description")
            params["description"] = updates["description"]

        if "config" in updates:
            set_clauses.append("config = :config")
            params["config"] = json.dumps(updates["config"])

        if "metadata" in updates:
            set_clauses.append("metadata = :metadata")
            params["metadata"] = json.dumps(updates["metadata"])

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")

        query = f"""
        UPDATE workflows
        SET {', '.join(set_clauses)}
        WHERE id = :id
        RETURNING *
        """

        result = await self._execute_query(query, params)

        if result["rows"]:
            workflow = await self._transform_workflow(result["rows"][0])
            await self._log_operation(
                "update", workflow_id, {"updates": list(updates.keys())}
            )
            return workflow

        raise Exception("Workflow not found")

    async def delete(self, workflow_id: str, soft_delete: bool = True):
        """Delete workflow (soft delete by default)."""
        if soft_delete:
            query = """
            UPDATE workflows
            SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """
        else:
            query = "DELETE FROM workflows WHERE id = :id"

        await self._execute_query(query, {"id": workflow_id})
        await self._log_operation("delete", workflow_id, {"soft_delete": soft_delete})

    async def _transform_workflow(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Transform database row to workflow object."""
        schema = {
            "id": "string",
            "name": "string",
            "description": "string",
            "config": "json",
            "created_by": "string",
            "created_at": "datetime",
            "updated_at": "datetime",
            "is_active": "boolean",
            "metadata": "json",
        }

        workflow = await self._transform_result(row, schema)

        # Parse JSON fields
        if isinstance(workflow.get("config"), str):
            workflow["config"] = json.loads(workflow["config"])
        if isinstance(workflow.get("metadata"), str):
            workflow["metadata"] = json.loads(workflow["metadata"])

        return workflow


class MiddlewareExecutionRepository(BaseRepository):
    """Execution repository using SDK database nodes."""

    def __init__(self, connection_string: str):
        super().__init__(connection_string, "executions")
        self._ensure_table()

    def _ensure_table(self):
        """Ensure execution table exists."""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS executions (
            id VARCHAR(255) PRIMARY KEY,
            workflow_id VARCHAR(255) NOT NULL,
            session_id VARCHAR(255),
            user_id VARCHAR(255),
            status VARCHAR(50) NOT NULL,
            inputs JSON,
            outputs JSON,
            error TEXT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            metadata JSON
        )
        """

        sync_db = SQLDatabaseNode(
            name="table_creator", connection_string=self.connection_string
        )
        sync_db.execute(query=create_table_query)

    async def create(self, execution_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create execution record."""
        execution_id = execution_data.get("id", str(uuid4()))

        query = """
        INSERT INTO executions (
            id, workflow_id, session_id, user_id, status, inputs, metadata
        ) VALUES (
            :id, :workflow_id, :session_id, :user_id, :status, :inputs, :metadata
        ) RETURNING *
        """

        params = {
            "id": execution_id,
            "workflow_id": execution_data["workflow_id"],
            "session_id": execution_data.get("session_id"),
            "user_id": execution_data.get("user_id"),
            "status": "pending",
            "inputs": json.dumps(execution_data.get("inputs", {})),
            "metadata": json.dumps(execution_data.get("metadata", {})),
        }

        result = await self._execute_query(query, params)

        if result["rows"]:
            execution = await self._transform_execution(result["rows"][0])
            await self._log_operation(
                "create",
                execution_id,
                {
                    "workflow_id": execution_data["workflow_id"],
                    "user_id": execution_data.get("user_id"),
                },
            )
            return execution

        raise Exception("Failed to create execution")

    async def update_status(
        self,
        execution_id: str,
        status: str,
        outputs: Dict[str, Any] = None,
        error: str = None,
    ) -> Dict[str, Any]:
        """Update execution status."""
        query = """
        UPDATE executions
        SET status = :status,
            outputs = :outputs,
            error = :error,
            completed_at = CASE WHEN :status IN ('completed', 'failed') THEN CURRENT_TIMESTAMP ELSE NULL END
        WHERE id = :id
        RETURNING *
        """

        params = {
            "id": execution_id,
            "status": status,
            "outputs": json.dumps(outputs) if outputs else None,
            "error": error,
        }

        result = await self._execute_query(query, params)

        if result["rows"]:
            execution = await self._transform_execution(result["rows"][0])
            await self._log_operation("update_status", execution_id, {"status": status})
            return execution

        raise Exception("Execution not found")

    async def get(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get execution by ID."""
        query = "SELECT * FROM executions WHERE id = :id"
        result = await self._execute_query(query, {"id": execution_id})

        if result["rows"]:
            return await self._transform_execution(result["rows"][0])

        return None

    async def list_by_workflow(
        self, workflow_id: str, limit: int = 100, status: str = None
    ) -> List[Dict[str, Any]]:
        """List executions for a workflow."""
        query = "SELECT * FROM executions WHERE workflow_id = :workflow_id"
        params = {"workflow_id": workflow_id}

        if status:
            query += " AND status = :status"
            params["status"] = status

        query += " ORDER BY started_at DESC LIMIT :limit"
        params["limit"] = limit

        result = await self._execute_query(query, params)

        executions = []
        for row in result["rows"]:
            execution = await self._transform_execution(row)
            executions.append(execution)

        return executions

    async def _transform_execution(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Transform database row to execution object."""
        schema = {
            "id": "string",
            "workflow_id": "string",
            "session_id": "string",
            "user_id": "string",
            "status": "string",
            "inputs": "json",
            "outputs": "json",
            "error": "string",
            "started_at": "datetime",
            "completed_at": "datetime",
            "metadata": "json",
        }

        execution = await self._transform_result(row, schema)

        # Parse JSON fields
        for field in ["inputs", "outputs", "metadata"]:
            if isinstance(execution.get(field), str):
                execution[field] = json.loads(execution[field])

        return execution


class MiddlewareUserRepository(BaseRepository):
    """User repository using SDK database nodes."""

    def __init__(self, connection_string: str):
        super().__init__(connection_string, "users")
        self._ensure_table()

    def _ensure_table(self):
        """Ensure user table exists."""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(255) PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            full_name VARCHAR(255),
            is_active BOOLEAN DEFAULT TRUE,
            is_superuser BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata JSON
        )
        """

        sync_db = SQLDatabaseNode(
            name="table_creator", connection_string=self.connection_string
        )
        sync_db.execute(query=create_table_query)

    async def create(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new user."""
        user_id = user_data.get("id", str(uuid4()))

        query = """
        INSERT INTO users (id, username, email, full_name, metadata)
        VALUES (:id, :username, :email, :full_name, :metadata)
        RETURNING *
        """

        params = {
            "id": user_id,
            "username": user_data["username"],
            "email": user_data["email"],
            "full_name": user_data.get("full_name", ""),
            "metadata": json.dumps(user_data.get("metadata", {})),
        }

        result = await self._execute_query(query, params)

        if result["rows"]:
            user = await self._transform_user(result["rows"][0])
            await self._log_operation(
                "create", user_id, {"username": user_data["username"]}
            )
            return user

        raise Exception("Failed to create user")

    async def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""
        query = "SELECT * FROM users WHERE username = :username AND is_active = TRUE"
        result = await self._execute_query(query, {"username": username})

        if result["rows"]:
            return await self._transform_user(result["rows"][0])

        return None

    async def _transform_user(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Transform database row to user object."""
        schema = {
            "id": "string",
            "username": "string",
            "email": "string",
            "full_name": "string",
            "is_active": "boolean",
            "is_superuser": "boolean",
            "created_at": "datetime",
            "updated_at": "datetime",
            "metadata": "json",
        }

        user = await self._transform_result(row, schema)

        if isinstance(user.get("metadata"), str):
            user["metadata"] = json.loads(user["metadata"])

        return user


class MiddlewarePermissionRepository(BaseRepository):
    """Permission repository using SDK database nodes."""

    def __init__(self, connection_string: str):
        super().__init__(connection_string, "permissions")
        self._ensure_table()

    def _ensure_table(self):
        """Ensure permission tables exist."""
        create_tables_query = """
        CREATE TABLE IF NOT EXISTS permissions (
            id VARCHAR(255) PRIMARY KEY,
            resource VARCHAR(255) NOT NULL,
            action VARCHAR(255) NOT NULL,
            description TEXT,
            UNIQUE(resource, action)
        );

        CREATE TABLE IF NOT EXISTS user_permissions (
            user_id VARCHAR(255) NOT NULL,
            permission_id VARCHAR(255) NOT NULL,
            granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            granted_by VARCHAR(255),
            expires_at TIMESTAMP,
            PRIMARY KEY (user_id, permission_id)
        );
        """

        sync_db = SQLDatabaseNode(
            name="table_creator", connection_string=self.connection_string
        )
        for query in create_tables_query.split(";"):
            if query.strip():
                sync_db.execute(query=query.strip())

    async def grant_permission(
        self,
        user_id: str,
        resource: str,
        action: str,
        granted_by: str = None,
        expires_at: datetime = None,
    ):
        """Grant permission to user."""
        # First ensure permission exists
        perm_query = """
        INSERT INTO permissions (id, resource, action)
        VALUES (:id, :resource, :action)
        ON CONFLICT (resource, action) DO NOTHING
        RETURNING id
        """

        perm_id = f"{resource}:{action}"
        perm_params = {"id": perm_id, "resource": resource, "action": action}

        await self._execute_query(perm_query, perm_params)

        # Grant to user
        grant_query = """
        INSERT INTO user_permissions (user_id, permission_id, granted_by, expires_at)
        VALUES (:user_id, :permission_id, :granted_by, :expires_at)
        ON CONFLICT (user_id, permission_id) DO UPDATE
        SET granted_at = CURRENT_TIMESTAMP, granted_by = :granted_by, expires_at = :expires_at
        """

        grant_params = {
            "user_id": user_id,
            "permission_id": perm_id,
            "granted_by": granted_by,
            "expires_at": expires_at,
        }

        await self._execute_query(grant_query, grant_params)
        await self._log_operation(
            "grant",
            user_id,
            {"resource": resource, "action": action, "granted_by": granted_by},
        )

    async def check_permission(self, user_id: str, resource: str, action: str) -> bool:
        """Check if user has permission."""
        query = """
        SELECT 1 FROM user_permissions up
        JOIN permissions p ON up.permission_id = p.id
        WHERE up.user_id = :user_id
        AND p.resource = :resource
        AND p.action = :action
        AND (up.expires_at IS NULL OR up.expires_at > CURRENT_TIMESTAMP)
        """

        params = {"user_id": user_id, "resource": resource, "action": action}

        result = await self._execute_query(query, params)
        has_permission = len(result["rows"]) > 0

        await self._log_operation(
            "check",
            user_id,
            {"resource": resource, "action": action, "granted": has_permission},
        )

        return has_permission
