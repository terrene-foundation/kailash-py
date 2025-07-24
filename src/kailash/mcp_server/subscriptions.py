"""MCP server resource subscription implementation."""

import asyncio
import uuid
import fnmatch
import json
from datetime import datetime, timedelta
from typing import Dict, Set, List, Optional, Callable, Any, Union
from dataclasses import dataclass, field
import weakref
import hashlib

from .protocol import ResourceChange, ResourceChangeType
from .auth import AuthManager, PermissionError as PermissionDeniedError


class SubscriptionError(Exception):
    """Raised when subscription operations fail."""
    pass


@dataclass
class ResourceSubscription:
    """Represents a resource subscription."""
    
    id: str
    connection_id: str
    uri_pattern: str
    cursor: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def matches_uri(self, uri: str) -> bool:
        """Check if URI matches subscription pattern.
        
        Supports:
        - Single wildcard (*) - matches within directory
        - Double wildcard (**) - matches across directories
        - Extension patterns (*.json, *.md)
        """
        # Convert ** to a pattern that matches across directories
        pattern = self.uri_pattern.replace("**", "|||DOUBLESTAR|||")
        pattern = pattern.replace("*", "|||STAR|||")
        
        # Escape special characters except our placeholders
        pattern = pattern.replace(".", r"\.")
        pattern = pattern.replace("?", r"\?")
        pattern = pattern.replace("[", r"\[")
        pattern = pattern.replace("]", r"\]")
        
        # Convert back to regex
        pattern = pattern.replace("|||DOUBLESTAR|||", ".*")
        pattern = pattern.replace("|||STAR|||", "[^/]*")
        
        # Add anchors
        pattern = f"^{pattern}$"
        
        import re
        return bool(re.match(pattern, uri))


class CursorManager:
    """Manages cursor generation and validation for pagination."""
    
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self._cursors: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    def generate_cursor(self) -> str:
        """Generate a unique cursor."""
        cursor_id = str(uuid.uuid4())
        timestamp = datetime.utcnow()
        
        cursor_data = f"{cursor_id}:{timestamp.isoformat()}"
        cursor = hashlib.sha256(cursor_data.encode()).hexdigest()[:16]
        
        self._cursors[cursor] = {
            "created_at": timestamp,
            "data": {}
        }
        
        return cursor
    
    def create_cursor_for_position(self, items: List[Any], position: int) -> str:
        """Create cursor for specific position in list."""
        cursor = self.generate_cursor()
        self._cursors[cursor]["data"]["position"] = position
        self._cursors[cursor]["data"]["items_hash"] = hashlib.sha256(
            str(items).encode()
        ).hexdigest()[:8]
        return cursor
    
    def is_valid(self, cursor: str) -> bool:
        """Check if cursor is valid and not expired."""
        if cursor not in self._cursors:
            return False
        
        cursor_data = self._cursors[cursor]
        age = datetime.utcnow() - cursor_data["created_at"]
        
        if age > timedelta(seconds=self.ttl_seconds):
            # Clean up expired cursor
            del self._cursors[cursor]
            return False
        
        return True
    
    def get_cursor_position(self, cursor: str) -> Optional[int]:
        """Get position from cursor if valid."""
        if not self.is_valid(cursor):
            return None
        
        return self._cursors[cursor]["data"].get("position")
    
    async def cleanup_expired(self):
        """Remove expired cursors."""
        async with self._lock:
            now = datetime.utcnow()
            expired = []
            
            for cursor, data in self._cursors.items():
                age = now - data["created_at"]
                if age > timedelta(seconds=self.ttl_seconds):
                    expired.append(cursor)
            
            for cursor in expired:
                del self._cursors[cursor]


class ResourceMonitor:
    """Monitors resources for changes."""
    
    def __init__(self):
        self._resource_states: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    def _compute_hash(self, content: Dict[str, Any]) -> str:
        """Compute hash of resource content."""
        # Sort keys for consistent hashing
        sorted_content = json.dumps(content, sort_keys=True)
        return hashlib.sha256(sorted_content.encode()).hexdigest()
    
    async def register_resource(self, uri: str, content: Dict[str, Any]):
        """Register resource for monitoring."""
        async with self._lock:
            self._resource_states[uri] = {
                "hash": self._compute_hash(content),
                "content": content,
                "last_checked": datetime.utcnow()
            }
    
    def is_monitored(self, uri: str) -> bool:
        """Check if resource is being monitored."""
        return uri in self._resource_states
    
    async def check_for_changes(self, uri: str, content: Dict[str, Any]) -> Optional[ResourceChange]:
        """Check if resource has changed."""
        async with self._lock:
            new_hash = self._compute_hash(content)
            
            if uri not in self._resource_states:
                # New resource
                self._resource_states[uri] = {
                    "hash": new_hash,
                    "content": content,
                    "last_checked": datetime.utcnow()
                }
                return ResourceChange(
                    type=ResourceChangeType.CREATED,
                    uri=uri,
                    timestamp=datetime.utcnow()
                )
            
            old_hash = self._resource_states[uri]["hash"]
            
            if old_hash != new_hash:
                # Resource updated
                self._resource_states[uri] = {
                    "hash": new_hash,
                    "content": content,
                    "last_checked": datetime.utcnow()
                }
                return ResourceChange(
                    type=ResourceChangeType.UPDATED,
                    uri=uri,
                    timestamp=datetime.utcnow()
                )
            
            # No change
            self._resource_states[uri]["last_checked"] = datetime.utcnow()
            return None
    
    async def check_for_deletion(self, uri: str) -> Optional[ResourceChange]:
        """Mark resource as deleted."""
        async with self._lock:
            if uri in self._resource_states:
                del self._resource_states[uri]
                return ResourceChange(
                    type=ResourceChangeType.DELETED,
                    uri=uri,
                    timestamp=datetime.utcnow()
                )
            return None


class ResourceSubscriptionManager:
    """Manages resource subscriptions."""
    
    def __init__(self, auth_manager: Optional[AuthManager] = None, 
                 event_store = None,
                 rate_limiter = None):
        self.auth_manager = auth_manager
        self.event_store = event_store
        self.rate_limiter = rate_limiter
        
        # Subscription tracking
        self._subscriptions: Dict[str, ResourceSubscription] = {}
        self._connection_subscriptions: Dict[str, Set[str]] = {}
        self._pattern_index: Dict[str, Set[str]] = {}  # pattern -> subscription IDs
        
        # Concurrency control
        self._lock = asyncio.Lock()
        
        # Notification callback
        self._notification_callback: Optional[Callable] = None
        
        # Resource monitoring
        self.resource_monitor = ResourceMonitor()
        
        # Cursor management
        self.cursor_manager = CursorManager()
        
        # Cleanup task
        self._cleanup_task = None
    
    async def initialize(self):
        """Initialize subscription manager."""
        # Start periodic cleanup
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
    
    async def shutdown(self):
        """Shutdown subscription manager."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
    
    async def _periodic_cleanup(self):
        """Periodically clean up expired cursors."""
        while True:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                await self.cursor_manager.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception:
                # Log error but continue
                pass
    
    def set_notification_callback(self, callback: Callable):
        """Set callback for sending notifications."""
        self._notification_callback = callback
    
    async def create_subscription(self, connection_id: str, uri_pattern: str,
                                  user_context: Optional[Dict[str, Any]] = None,
                                  cursor: Optional[str] = None) -> str:
        """Create a new subscription."""
        # Check rate limit
        if self.rate_limiter:
            user_id = user_context.get("user_id") if user_context else connection_id
            if not await self.rate_limiter.check_rate_limit(user_id):
                raise SubscriptionError("Rate limit exceeded")
        
        # Check permissions
        if self.auth_manager and user_context:
            try:
                # Use authenticate_and_authorize method if available
                if hasattr(self.auth_manager, 'authenticate_and_authorize'):
                    await self.auth_manager.authenticate_and_authorize(
                        user_context,
                        required_permission="subscribe"
                    )
                else:
                    # Fallback for mocked auth managers
                    permission_check = await self.auth_manager.check_permission(
                        user_context.get("user_id"),
                        "subscribe",
                        {"resource_pattern": uri_pattern}
                    )
                    if not permission_check.get("authorized", False):
                        raise PermissionDeniedError("Not authorized to subscribe to resources")
            except Exception as e:
                raise PermissionDeniedError("Not authorized to subscribe to resources")
        
        # Create subscription
        sub_id = str(uuid.uuid4())
        subscription = ResourceSubscription(
            id=sub_id,
            connection_id=connection_id,
            uri_pattern=uri_pattern,
            cursor=cursor
        )
        
        async with self._lock:
            # Store subscription
            self._subscriptions[sub_id] = subscription
            
            # Track by connection
            if connection_id not in self._connection_subscriptions:
                self._connection_subscriptions[connection_id] = set()
            self._connection_subscriptions[connection_id].add(sub_id)
            
            # Index by pattern
            if uri_pattern not in self._pattern_index:
                self._pattern_index[uri_pattern] = set()
            self._pattern_index[uri_pattern].add(sub_id)
        
        # Log to event store
        if self.event_store:
            await self.event_store.append_event(
                stream_name="subscriptions",
                event_type="subscription.created",
                data={
                    "subscription_id": sub_id,
                    "connection_id": connection_id,
                    "uri_pattern": uri_pattern,
                    "user_id": user_context.get("user_id") if user_context else None
                }
            )
        
        return sub_id
    
    async def remove_subscription(self, subscription_id: str, connection_id: str) -> bool:
        """Remove a subscription."""
        async with self._lock:
            if subscription_id not in self._subscriptions:
                return False
            
            subscription = self._subscriptions[subscription_id]
            
            # Verify ownership
            if subscription.connection_id != connection_id:
                return False
            
            # Remove from indices
            self._connection_subscriptions[connection_id].discard(subscription_id)
            if not self._connection_subscriptions[connection_id]:
                del self._connection_subscriptions[connection_id]
            
            self._pattern_index[subscription.uri_pattern].discard(subscription_id)
            if not self._pattern_index[subscription.uri_pattern]:
                del self._pattern_index[subscription.uri_pattern]
            
            # Remove subscription
            del self._subscriptions[subscription_id]
        
        # Log to event store
        if self.event_store:
            await self.event_store.append_event(
                stream_name="subscriptions",
                event_type="subscription.removed",
                data={
                    "subscription_id": subscription_id,
                    "connection_id": connection_id
                }
            )
        
        return True
    
    def get_subscription(self, subscription_id: str) -> Optional[ResourceSubscription]:
        """Get subscription by ID."""
        return self._subscriptions.get(subscription_id)
    
    def get_connection_subscriptions(self, connection_id: str) -> Set[str]:
        """Get all subscription IDs for a connection."""
        return self._connection_subscriptions.get(connection_id, set()).copy()
    
    async def cleanup_connection(self, connection_id: str) -> int:
        """Remove all subscriptions for a connection."""
        sub_ids = self.get_connection_subscriptions(connection_id)
        removed = 0
        
        for sub_id in sub_ids:
            if await self.remove_subscription(sub_id, connection_id):
                removed += 1
        
        return removed
    
    async def find_matching_subscriptions(self, uri: str) -> List[ResourceSubscription]:
        """Find all subscriptions that match a URI."""
        matching = []
        
        async with self._lock:
            for sub_id, subscription in self._subscriptions.items():
                if subscription.matches_uri(uri):
                    matching.append(subscription)
        
        return matching
    
    async def process_resource_change(self, change: Union[ResourceChange, Dict[str, Any]]):
        """Process a resource change and notify subscribers."""
        # Convert dict to ResourceChange if needed
        if isinstance(change, dict):
            change = ResourceChange(
                type=ResourceChangeType(change["type"]),
                uri=change["uri"],
                timestamp=datetime.fromisoformat(change["timestamp"])
            )
        
        # Find matching subscriptions
        matching_subs = await self.find_matching_subscriptions(change.uri)
        
        if not matching_subs:
            return
        
        # Group by connection for batching
        notifications_by_connection: Dict[str, List[ResourceChange]] = {}
        
        for subscription in matching_subs:
            conn_id = subscription.connection_id
            if conn_id not in notifications_by_connection:
                notifications_by_connection[conn_id] = []
            notifications_by_connection[conn_id].append(change)
        
        # Send notifications
        if self._notification_callback:
            for conn_id, changes in notifications_by_connection.items():
                # Send batched notification
                notification = {
                    "jsonrpc": "2.0",
                    "method": "notifications/resources/updated",
                    "params": {
                        "uri": change.uri,
                        "type": change.type.value,
                        "timestamp": change.timestamp.isoformat()
                    }
                }
                
                # Check if callback is async
                if asyncio.iscoroutinefunction(self._notification_callback):
                    await self._notification_callback(conn_id, notification)
                else:
                    self._notification_callback(conn_id, notification)
        
        # Log to event store
        if self.event_store:
            await self.event_store.append_event(
                stream_name="resource_changes",
                event_type="resource.changed",
                data={
                    "uri": change.uri,
                    "type": change.type.value,
                    "timestamp": change.timestamp.isoformat(),
                    "notified_connections": list(notifications_by_connection.keys())
                }
            )


# Required imports
import json
from typing import Union