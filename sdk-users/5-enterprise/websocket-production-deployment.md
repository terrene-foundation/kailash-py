# WebSocket MCP Production Deployment Guide

*Enterprise deployment patterns for WebSocket-based MCP implementations at scale*

## Overview

This guide covers production deployment strategies for WebSocket MCP implementations, including load balancing, security hardening, monitoring, and troubleshooting for enterprise environments.

## Architecture Patterns

### Single-Server Deployment

For small to medium deployments (< 1000 concurrent connections):

```python
# production_server.py
from kailash.mcp_server import MCPServer
from kailash.mcp_server.transports import WebSocketServerTransport
from kailash.mcp_server.auth import APIKeyAuth
import os
import logging

# Production logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/mcp-server.log'),
        logging.StreamHandler()
    ]
)

# Production authentication
auth_provider = APIKeyAuth({
    os.getenv("MCP_API_KEY"): {
        "permissions": ["tools", "resources"],
        "rate_limit": {"requests": 1000, "window": 60}
    }
})

# Production WebSocket transport
transport = WebSocketServerTransport(
    host="0.0.0.0",
    port=int(os.getenv("MCP_PORT", "3001")),
    ping_interval=30.0,        # Longer intervals for production
    ping_timeout=10.0,         # Quick failure detection
    max_message_size=5 * 1024 * 1024,  # 5MB limit
    max_connections=500        # Connection limit
)

# Production server configuration
server = MCPServer(
    name="production-mcp-server",
    transport=transport,
    auth_provider=auth_provider,
    enable_metrics=True,
    enable_logging=True,
    log_level="INFO"
)

# Add health check endpoint
@server.tool()
def health_check() -> dict:
    """Health check endpoint for load balancers."""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "server_id": os.getenv("SERVER_ID", "unknown"),
        "active_connections": transport.get_connection_count()
    }

if __name__ == "__main__":
    # Graceful shutdown handling
    import signal

    def signal_handler(signum, frame):
        print("Shutting down gracefully...")
        server.shutdown()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Start server
    server.run()
```

### High-Availability Cluster Deployment

For enterprise deployments requiring high availability:

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  # Load Balancer
  nginx-lb:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/ssl/certs
    depends_on:
      - mcp-server-1
      - mcp-server-2
      - mcp-server-3
    restart: unless-stopped
    networks:
      - mcp-network

  # MCP Server Cluster
  mcp-server-1:
    image: company/mcp-server:v1.2.0
    environment:
      - SERVER_ID=mcp-server-1
      - MCP_PORT=3001
      - REDIS_URL=redis://redis:6379
      - POSTGRES_URL=postgresql://user:pass@postgres:5432/mcp
      - MCP_API_KEY=${MCP_API_KEY}
      - LOG_LEVEL=INFO
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:3001/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    deploy:
      resources:
        limits:
          memory: 1GB
          cpus: '0.5'
    networks:
      - mcp-network
    restart: unless-stopped

  mcp-server-2:
    image: company/mcp-server:v1.2.0
    environment:
      - SERVER_ID=mcp-server-2
      - MCP_PORT=3001
      - REDIS_URL=redis://redis:6379
      - POSTGRES_URL=postgresql://user:pass@postgres:5432/mcp
      - MCP_API_KEY=${MCP_API_KEY}
      - LOG_LEVEL=INFO
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:3001/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    deploy:
      resources:
        limits:
          memory: 1GB
          cpus: '0.5'
    networks:
      - mcp-network
    restart: unless-stopped

  mcp-server-3:
    image: company/mcp-server:v1.2.0
    environment:
      - SERVER_ID=mcp-server-3
      - MCP_PORT=3001
      - REDIS_URL=redis://redis:6379
      - POSTGRES_URL=postgresql://user:pass@postgres:5432/mcp
      - MCP_API_KEY=${MCP_API_KEY}
      - LOG_LEVEL=INFO
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:3001/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    deploy:
      resources:
        limits:
          memory: 1GB
          cpus: '0.5'
    networks:
      - mcp-network
    restart: unless-stopped

  # Shared Services
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis-data:/data
    networks:
      - mcp-network
    restart: unless-stopped

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: mcp
      POSTGRES_USER: user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - mcp-network
    restart: unless-stopped

  # Monitoring
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    networks:
      - mcp-network
    restart: unless-stopped

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    volumes:
      - grafana-data:/var/lib/grafana
    networks:
      - mcp-network
    restart: unless-stopped

volumes:
  redis-data:
  postgres-data:
  prometheus-data:
  grafana-data:

networks:
  mcp-network:
    driver: bridge
```

## Load Balancer Configuration

### NGINX WebSocket Load Balancing

```nginx
# nginx.conf
events {
    worker_connections 1024;
}

http {
    # WebSocket connection upgrade map
    map $http_upgrade $connection_upgrade {
        default upgrade;
        '' close;
    }

    # Upstream server pool
    upstream mcp_websocket_servers {
        # Sticky sessions based on client IP
        ip_hash;

        server mcp-server-1:3001 max_fails=3 fail_timeout=30s;
        server mcp-server-2:3001 max_fails=3 fail_timeout=30s;
        server mcp-server-3:3001 max_fails=3 fail_timeout=30s;

        # Health check (requires nginx-plus or custom module)
        # health_check interval=10s fails=3 passes=2;
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=websocket_limit:10m rate=10r/s;
    limit_conn_zone $binary_remote_addr zone=conn_limit:10m;

    server {
        listen 80;
        server_name api.company.com;

        # Redirect HTTP to HTTPS
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name api.company.com;

        # SSL Configuration
        ssl_certificate /etc/ssl/certs/api.company.com.crt;
        ssl_certificate_key /etc/ssl/certs/api.company.com.key;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
        ssl_prefer_server_ciphers off;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 10m;

        # Security headers
        add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
        add_header X-Content-Type-Options nosniff always;
        add_header X-Frame-Options DENY always;
        add_header X-XSS-Protection "1; mode=block" always;

        # WebSocket MCP endpoint
        location /mcp {
            # Rate limiting
            limit_req zone=websocket_limit burst=20 nodelay;
            limit_conn conn_limit 50;

            # Proxy configuration
            proxy_pass http://mcp_websocket_servers;
            proxy_http_version 1.1;

            # WebSocket upgrade headers
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;

            # Standard proxy headers
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            # WebSocket timeouts
            proxy_read_timeout 300s;
            proxy_send_timeout 300s;
            proxy_connect_timeout 60s;

            # Buffer settings for WebSocket
            proxy_buffering off;
            proxy_cache off;
        }

        # Health check endpoint
        location /health {
            proxy_pass http://mcp_websocket_servers;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_connect_timeout 5s;
            proxy_read_timeout 5s;
        }

        # Metrics endpoint (restrict access)
        location /metrics {
            allow 10.0.0.0/8;
            allow 172.16.0.0/12;
            allow 192.168.0.0/16;
            deny all;

            proxy_pass http://mcp_websocket_servers;
        }
    }
}
```

### HAProxy Alternative Configuration

```haproxy
# haproxy.cfg
global
    daemon
    chroot /var/lib/haproxy
    stats socket /run/haproxy/admin.sock mode 660 level admin
    stats timeout 30s
    user haproxy
    group haproxy

defaults
    mode http
    timeout connect 5000ms
    timeout client 300000ms
    timeout server 300000ms
    option httplog
    option dontlognull

# WebSocket MCP backend
backend mcp_websocket_servers
    balance roundrobin
    option httpchk GET /health
    http-check expect status 200

    server mcp1 mcp-server-1:3001 check inter 10s fall 3 rise 2
    server mcp2 mcp-server-2:3001 check inter 10s fall 3 rise 2
    server mcp3 mcp-server-3:3001 check inter 10s fall 3 rise 2

# Frontend for WebSocket connections
frontend mcp_websocket_frontend
    bind *:443 ssl crt /etc/ssl/certs/api.company.com.pem

    # WebSocket upgrade detection
    acl is_websocket hdr(Upgrade) -i websocket
    acl is_websocket_conn hdr_beg(Connection) -i upgrade

    # Route WebSocket traffic
    use_backend mcp_websocket_servers if is_websocket is_websocket_conn

    # Rate limiting
    stick-table type ip size 100k expire 30s store http_req_rate(10s)
    http-request track-sc0 src
    http-request reject if { sc_http_req_rate(0) gt 20 }

# Statistics interface
listen stats
    bind *:8404
    stats enable
    stats uri /stats
    stats refresh 30s
    stats admin if TRUE
```

## Security Hardening

### SSL/TLS Configuration

```python
# secure_websocket_server.py
import ssl
from kailash.mcp_server.transports import WebSocketServerTransport

# Create SSL context
ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
ssl_context.load_cert_chain('/etc/ssl/certs/server.crt', '/etc/ssl/private/server.key')

# Harden SSL configuration
ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
ssl_context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE  # Client cert verification handled at app level

# WebSocket server with SSL
transport = WebSocketServerTransport(
    host="0.0.0.0",
    port=3001,
    ssl_context=ssl_context,
    ping_interval=30.0,
    ping_timeout=10.0,
    max_message_size=1024*1024,  # 1MB limit for security
)
```

### Authentication & Authorization

```python
# enterprise_security.py
from kailash.mcp_server.auth import JWTAuth, APIKeyAuth, RoleBasedAuth
import os
import jwt
from datetime import datetime, timedelta

# Multi-factor authentication setup
class EnterpriseAuth:
    def __init__(self):
        # API Key auth for service-to-service
        self.api_auth = APIKeyAuth({
            os.getenv("SERVICE_API_KEY"): {
                "permissions": ["tools", "resources", "admin"],
                "rate_limit": {"requests": 10000, "window": 60},
                "metadata": {"type": "service", "name": "internal"}
            }
        })

        # JWT auth for user sessions
        self.jwt_auth = JWTAuth(
            secret=os.getenv("JWT_SECRET"),
            algorithm="HS256",
            token_expiry=3600  # 1 hour
        )

        # Role-based permissions
        self.rbac = RoleBasedAuth({
            "admin": ["tools", "resources", "admin", "metrics"],
            "operator": ["tools", "resources"],
            "readonly": ["resources"]
        })

    async def authenticate(self, request):
        """Multi-method authentication."""

        # Try API key first
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return await self.api_auth.authenticate({"api_key": api_key})

        # Try JWT token
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
                return {
                    "user_id": payload["user_id"],
                    "permissions": payload.get("permissions", []),
                    "expires": payload["exp"]
                }
            except jwt.InvalidTokenError:
                pass

        # No valid authentication
        raise AuthenticationError("Invalid or missing authentication")

    def authorize(self, user_context, required_permission):
        """Check if user has required permission."""
        user_permissions = user_context.get("permissions", [])
        return required_permission in user_permissions

# Usage in server
auth_provider = EnterpriseAuth()

@server.tool(required_permission="tools")
async def secure_tool(data: str, auth_context=None) -> dict:
    """Tool that requires authentication and authorization."""

    # Additional authorization checks
    if not auth_provider.authorize(auth_context, "tools"):
        raise PermissionError("Insufficient permissions")

    return {"result": f"Processed: {data}", "user": auth_context.get("user_id")}
```

### Network Security

```python
# network_security.py
from kailash.mcp_server.transports import WebSocketServerTransport
import ipaddress

class SecureWebSocketTransport(WebSocketServerTransport):
    def __init__(self, allowed_networks=None, blocked_ips=None, **kwargs):
        super().__init__(**kwargs)

        # IP allowlist/blocklist
        self.allowed_networks = [ipaddress.ip_network(net) for net in (allowed_networks or [])]
        self.blocked_ips = set(blocked_ips or [])

        # Connection limits per IP
        self.connection_counts = {}
        self.max_connections_per_ip = 10

    async def handle_connection(self, websocket, path):
        """Enhanced connection handling with security checks."""

        client_ip = websocket.remote_address[0]

        # IP blocklist check
        if client_ip in self.blocked_ips:
            await websocket.close(code=1008, reason="IP blocked")
            return

        # IP allowlist check (if configured)
        if self.allowed_networks:
            client_addr = ipaddress.ip_address(client_ip)
            if not any(client_addr in network for network in self.allowed_networks):
                await websocket.close(code=1008, reason="IP not allowed")
                return

        # Connection limit per IP
        current_connections = self.connection_counts.get(client_ip, 0)
        if current_connections >= self.max_connections_per_ip:
            await websocket.close(code=1008, reason="Too many connections")
            return

        # Update connection count
        self.connection_counts[client_ip] = current_connections + 1

        try:
            # Handle the connection normally
            await super().handle_connection(websocket, path)
        finally:
            # Clean up connection count
            self.connection_counts[client_ip] -= 1
            if self.connection_counts[client_ip] <= 0:
                del self.connection_counts[client_ip]

# Production security configuration
secure_transport = SecureWebSocketTransport(
    host="0.0.0.0",
    port=3001,
    allowed_networks=[
        "10.0.0.0/8",      # Internal network
        "172.16.0.0/12",   # Docker networks
        "192.168.0.0/16"   # Private networks
    ],
    blocked_ips=[
        "192.168.1.100",   # Known bad actor
    ],
    max_connections_per_ip=5,
    ping_interval=30.0,
    max_message_size=512*1024  # 512KB limit
)
```

## Monitoring & Observability

### Prometheus Metrics Integration

```python
# metrics_integration.py
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
import time
import json

class WebSocketMetrics:
    def __init__(self):
        self.registry = CollectorRegistry()

        # Connection metrics
        self.connections_total = Counter(
            'websocket_connections_total',
            'Total WebSocket connections established',
            ['server_id'],
            registry=self.registry
        )

        self.active_connections = Gauge(
            'websocket_active_connections',
            'Currently active WebSocket connections',
            ['server_id'],
            registry=self.registry
        )

        # Message metrics
        self.messages_total = Counter(
            'websocket_messages_total',
            'Total WebSocket messages processed',
            ['server_id', 'direction', 'status'],
            registry=self.registry
        )

        self.message_duration = Histogram(
            'websocket_message_duration_seconds',
            'Time spent processing WebSocket messages',
            ['server_id', 'tool_name'],
            registry=self.registry
        )

        # Error metrics
        self.errors_total = Counter(
            'websocket_errors_total',
            'Total WebSocket errors',
            ['server_id', 'error_type'],
            registry=self.registry
        )

        # Pool metrics
        self.pool_efficiency = Gauge(
            'websocket_pool_efficiency_percent',
            'WebSocket connection pool efficiency',
            ['server_id'],
            registry=self.registry
        )

# Enhanced server with metrics
class MonitoredMCPServer(MCPServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.metrics = WebSocketMetrics()
        self.server_id = os.getenv("SERVER_ID", "unknown")

    async def handle_websocket_connection(self, websocket, path):
        """Handle WebSocket connection with metrics."""

        # Record connection
        self.metrics.connections_total.labels(server_id=self.server_id).inc()
        self.metrics.active_connections.labels(server_id=self.server_id).inc()

        try:
            await super().handle_websocket_connection(websocket, path)
        except Exception as e:
            # Record error
            error_type = type(e).__name__
            self.metrics.errors_total.labels(
                server_id=self.server_id,
                error_type=error_type
            ).inc()
            raise
        finally:
            # Connection closed
            self.metrics.active_connections.labels(server_id=self.server_id).dec()

    async def handle_tool_call(self, tool_name, params):
        """Handle tool call with timing metrics."""

        start_time = time.time()

        try:
            result = await super().handle_tool_call(tool_name, params)

            # Record success
            self.metrics.messages_total.labels(
                server_id=self.server_id,
                direction="inbound",
                status="success"
            ).inc()

            return result

        except Exception as e:
            # Record error
            self.metrics.messages_total.labels(
                server_id=self.server_id,
                direction="inbound",
                status="error"
            ).inc()

            error_type = type(e).__name__
            self.metrics.errors_total.labels(
                server_id=self.server_id,
                error_type=error_type
            ).inc()

            raise

        finally:
            # Record duration
            duration = time.time() - start_time
            self.metrics.message_duration.labels(
                server_id=self.server_id,
                tool_name=tool_name
            ).observe(duration)

    def get_metrics_handler(self):
        """Return Prometheus metrics handler."""
        from prometheus_client import generate_latest

        def metrics_handler():
            return generate_latest(self.metrics.registry)

        return metrics_handler

# Metrics endpoint setup
server = MonitoredMCPServer("production-server")

# Expose metrics on separate port
from http.server import HTTPServer, BaseHTTPRequestHandler

class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
            self.end_headers()

            metrics_data = server.get_metrics_handler()()
            self.wfile.write(metrics_data)
        else:
            self.send_response(404)
            self.end_headers()

# Start metrics server
metrics_server = HTTPServer(('0.0.0.0', 9090), MetricsHandler)
```

### Logging Configuration

```python
# production_logging.py
import logging
import json
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

class StructuredFormatter(logging.Formatter):
    """JSON structured logging formatter."""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields
        if hasattr(record, 'server_id'):
            log_entry['server_id'] = record.server_id
        if hasattr(record, 'client_ip'):
            log_entry['client_ip'] = record.client_ip
        if hasattr(record, 'tool_name'):
            log_entry['tool_name'] = record.tool_name
        if hasattr(record, 'duration'):
            log_entry['duration'] = record.duration

        # Add exception info
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_entry)

def setup_production_logging():
    """Configure production logging."""

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Structured formatter
    formatter = StructuredFormatter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation
    file_handler = RotatingFileHandler(
        '/var/log/mcp-server.log',
        maxBytes=100*1024*1024,  # 100MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Error file handler
    error_handler = RotatingFileHandler(
        '/var/log/mcp-server-error.log',
        maxBytes=50*1024*1024,   # 50MB
        backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)

# Enhanced server with structured logging
class LoggingMCPServer(MCPServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.server_id = os.getenv("SERVER_ID", "unknown")

    async def handle_websocket_connection(self, websocket, path):
        """Handle connection with structured logging."""

        client_ip = websocket.remote_address[0]

        self.logger.info(
            "WebSocket connection established",
            extra={
                "server_id": self.server_id,
                "client_ip": client_ip,
                "path": path
            }
        )

        start_time = time.time()

        try:
            await super().handle_websocket_connection(websocket, path)

        except Exception as e:
            self.logger.error(
                "WebSocket connection error",
                extra={
                    "server_id": self.server_id,
                    "client_ip": client_ip,
                    "error": str(e),
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            raise

        finally:
            duration = time.time() - start_time
            self.logger.info(
                "WebSocket connection closed",
                extra={
                    "server_id": self.server_id,
                    "client_ip": client_ip,
                    "duration": duration
                }
            )

    async def handle_tool_call(self, tool_name, params):
        """Handle tool call with structured logging."""

        self.logger.info(
            "Tool call started",
            extra={
                "server_id": self.server_id,
                "tool_name": tool_name,
                "params_size": len(json.dumps(params))
            }
        )

        start_time = time.time()

        try:
            result = await super().handle_tool_call(tool_name, params)

            duration = time.time() - start_time
            self.logger.info(
                "Tool call completed",
                extra={
                    "server_id": self.server_id,
                    "tool_name": tool_name,
                    "duration": duration,
                    "result_size": len(json.dumps(result))
                }
            )

            return result

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(
                "Tool call failed",
                extra={
                    "server_id": self.server_id,
                    "tool_name": tool_name,
                    "duration": duration,
                    "error": str(e),
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            raise

# Setup logging
setup_production_logging()
```

## Performance Optimization

### Connection Pool Tuning

```python
# performance_tuning.py
from kailash.mcp_server import MCPClient
import asyncio
import time

class PerformanceTunedClient:
    """Performance-optimized MCP client for high-throughput scenarios."""

    def __init__(self, server_urls, max_concurrent=50):
        self.server_urls = server_urls
        self.max_concurrent = max_concurrent

        # Create multiple clients for load distribution
        self.clients = []
        for i, url in enumerate(server_urls):
            client = MCPClient(
                connection_pool_config={
                    "max_connections": 20,        # Higher connection pool
                    "connection_timeout": 15.0,   # Faster timeout
                    "pool_cleanup_interval": 60,  # More frequent cleanup
                    "keep_alive": True,
                    "ping_interval": 60.0,        # Less frequent pings for performance
                    "ping_timeout": 5.0           # Quick ping timeout
                },
                enable_metrics=True
            )
            self.clients.append(client)

        self.client_index = 0
        self.semaphore = asyncio.Semaphore(max_concurrent)

    def get_next_client(self):
        """Round-robin client selection."""
        client = self.clients[self.client_index]
        self.client_index = (self.client_index + 1) % len(self.clients)
        return client

    async def call_tool_optimized(self, tool_name, params):
        """Optimized tool call with load balancing."""

        async with self.semaphore:  # Limit concurrent calls
            client = self.get_next_client()

            # Try primary server
            try:
                async with client:
                    return await client.call_tool(
                        self.server_urls[0],
                        tool_name,
                        params
                    )

            except Exception as e:
                # Failover to other servers
                for backup_url in self.server_urls[1:]:
                    try:
                        async with client:
                            return await client.call_tool(backup_url, tool_name, params)
                    except Exception:
                        continue

                # All servers failed
                raise e

    async def batch_call_tools(self, calls):
        """Batch process multiple tool calls efficiently."""

        tasks = []
        for tool_name, params in calls:
            task = self.call_tool_optimized(tool_name, params)
            tasks.append(task)

        # Process in batches to avoid overwhelming servers
        batch_size = self.max_concurrent
        results = []

        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            results.extend(batch_results)

        return results

    async def get_performance_stats(self):
        """Get performance statistics from all clients."""

        stats = {
            "total_clients": len(self.clients),
            "server_urls": self.server_urls,
            "max_concurrent": self.max_concurrent,
            "client_stats": []
        }

        for i, client in enumerate(self.clients):
            metrics = client.get_metrics()
            client_stats = {
                "client_id": i,
                "pool_hits": metrics.get('websocket_pool_hits', 0),
                "pool_misses": metrics.get('websocket_pool_misses', 0),
                "active_connections": len(client._websocket_pools),
                "connection_errors": metrics.get('connection_errors', 0)
            }

            # Calculate efficiency
            hits = client_stats["pool_hits"]
            misses = client_stats["pool_misses"]
            if hits + misses > 0:
                client_stats["pool_efficiency"] = (hits / (hits + misses)) * 100

            stats["client_stats"].append(client_stats)

        return stats

# Usage example
async def high_performance_example():
    """Demonstrate high-performance WebSocket usage."""

    # Multiple server URLs for load balancing
    server_urls = [
        "wss://api1.company.com/mcp",
        "wss://api2.company.com/mcp",
        "wss://api3.company.com/mcp"
    ]

    client = PerformanceTunedClient(server_urls, max_concurrent=100)

    # Batch processing example
    calls = [
        ("search", {"query": f"query_{i}"})
        for i in range(1000)
    ]

    start_time = time.time()
    results = await client.batch_call_tools(calls)
    elapsed = time.time() - start_time

    # Performance analysis
    successful = sum(1 for r in results if not isinstance(r, Exception))
    failed = len(results) - successful

    print(f"Performance Results:")
    print(f"  Total calls: {len(calls)}")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    print(f"  Total time: {elapsed:.2f}s")
    print(f"  Calls per second: {len(calls)/elapsed:.1f}")

    # Get detailed stats
    stats = await client.get_performance_stats()
    print(f"  Pool efficiency: {sum(s.get('pool_efficiency', 0) for s in stats['client_stats'])/len(stats['client_stats']):.1f}%")

# Run performance test
asyncio.run(high_performance_example())
```

## Troubleshooting

### Production Troubleshooting Toolkit

```python
# troubleshooting_toolkit.py
import asyncio
import websockets
import json
import time
import psutil
from kailash.mcp_server import MCPClient

class ProductionDiagnostics:
    """Comprehensive production diagnostics for WebSocket MCP."""

    def __init__(self, server_urls):
        self.server_urls = server_urls if isinstance(server_urls, list) else [server_urls]
        self.results = {}

    async def run_full_diagnostics(self):
        """Run complete diagnostic suite."""

        print("=== Production WebSocket MCP Diagnostics ===\n")

        # System diagnostics
        await self.check_system_resources()

        # Network diagnostics
        await self.check_network_connectivity()

        # WebSocket diagnostics
        await self.check_websocket_functionality()

        # MCP protocol diagnostics
        await self.check_mcp_protocol()

        # Performance diagnostics
        await self.check_performance_metrics()

        # Generate report
        self.generate_diagnostic_report()

    async def check_system_resources(self):
        """Check system resource utilization."""

        print("1. System Resource Check")

        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        self.results['cpu_usage'] = cpu_percent

        # Memory usage
        memory = psutil.virtual_memory()
        self.results['memory_usage'] = {
            'percent': memory.percent,
            'available_gb': memory.available / (1024**3),
            'total_gb': memory.total / (1024**3)
        }

        # Disk usage
        disk = psutil.disk_usage('/')
        self.results['disk_usage'] = {
            'percent': (disk.used / disk.total) * 100,
            'free_gb': disk.free / (1024**3)
        }

        # Network connections
        connections = psutil.net_connections(kind='tcp')
        websocket_connections = [c for c in connections if c.laddr.port in [3001, 8080, 443]]
        self.results['websocket_connections'] = len(websocket_connections)

        print(f"   CPU Usage: {cpu_percent:.1f}%")
        print(f"   Memory Usage: {memory.percent:.1f}% ({memory.available/(1024**3):.1f}GB available)")
        print(f"   Disk Usage: {(disk.used/disk.total)*100:.1f}% ({disk.free/(1024**3):.1f}GB free)")
        print(f"   WebSocket Connections: {len(websocket_connections)}")

        if cpu_percent > 80:
            print("   ⚠️  HIGH CPU USAGE - consider scaling")
        if memory.percent > 80:
            print("   ⚠️  HIGH MEMORY USAGE - check for memory leaks")
        if (disk.used/disk.total)*100 > 90:
            print("   ⚠️  LOW DISK SPACE - clean up logs")

        print()

    async def check_network_connectivity(self):
        """Check network connectivity to servers."""

        print("2. Network Connectivity Check")

        for i, url in enumerate(self.server_urls):
            try:
                # Parse URL
                if url.startswith("wss://"):
                    host = url.replace("wss://", "").split("/")[0]
                    port = 443
                elif url.startswith("ws://"):
                    host = url.replace("ws://", "").split("/")[0]
                    port = 80
                else:
                    continue

                if ":" in host:
                    host, port = host.split(":")
                    port = int(port)

                # Test TCP connection
                start_time = time.time()
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=5.0
                )
                writer.close()
                await writer.wait_closed()

                latency = (time.time() - start_time) * 1000
                print(f"   Server {i+1} ({host}:{port}): ✅ Connected ({latency:.1f}ms)")

                self.results[f'server_{i+1}_connectivity'] = {
                    'status': 'connected',
                    'latency_ms': latency
                }

            except asyncio.TimeoutError:
                print(f"   Server {i+1} ({host}:{port}): ❌ Timeout")
                self.results[f'server_{i+1}_connectivity'] = {'status': 'timeout'}
            except Exception as e:
                print(f"   Server {i+1} ({host}:{port}): ❌ Error: {e}")
                self.results[f'server_{i+1}_connectivity'] = {'status': 'error', 'error': str(e)}

        print()

    async def check_websocket_functionality(self):
        """Test basic WebSocket functionality."""

        print("3. WebSocket Functionality Check")

        for i, url in enumerate(self.server_urls):
            try:
                print(f"   Testing {url}")

                # Test WebSocket upgrade
                start_time = time.time()
                async with websockets.connect(url, ping_interval=None) as ws:
                    connect_time = (time.time() - start_time) * 1000

                    # Test ping/pong
                    ping_start = time.time()
                    pong_waiter = await ws.ping()
                    await pong_waiter
                    ping_time = (time.time() - ping_start) * 1000

                    # Test message send/receive
                    test_message = {"type": "test", "timestamp": time.time()}
                    await ws.send(json.dumps(test_message))

                    try:
                        response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        message_received = True
                    except asyncio.TimeoutError:
                        message_received = False

                    print(f"     ✅ WebSocket upgrade: {connect_time:.1f}ms")
                    print(f"     ✅ Ping/Pong: {ping_time:.1f}ms")
                    print(f"     {'✅' if message_received else '⚠️'} Message handling: {'Working' if message_received else 'No response'}")

                    self.results[f'server_{i+1}_websocket'] = {
                        'status': 'working',
                        'connect_time_ms': connect_time,
                        'ping_time_ms': ping_time,
                        'message_handling': message_received
                    }

            except Exception as e:
                print(f"     ❌ WebSocket test failed: {e}")
                self.results[f'server_{i+1}_websocket'] = {'status': 'failed', 'error': str(e)}

        print()

    async def check_mcp_protocol(self):
        """Test MCP protocol functionality."""

        print("4. MCP Protocol Check")

        client = MCPClient(enable_metrics=True)

        for i, url in enumerate(self.server_urls):
            try:
                print(f"   Testing MCP protocol on {url}")

                async with client:
                    # Test tool discovery
                    start_time = time.time()
                    tools = await client.discover_tools(url)
                    discovery_time = (time.time() - start_time) * 1000

                    print(f"     ✅ Tool discovery: {len(tools)} tools ({discovery_time:.1f}ms)")

                    # Test tool execution (if tools available)
                    if tools:
                        tool_name = list(tools.keys())[0]
                        try:
                            start_time = time.time()
                            result = await client.call_tool(url, tool_name, {})
                            execution_time = (time.time() - start_time) * 1000

                            print(f"     ✅ Tool execution ({tool_name}): {execution_time:.1f}ms")

                            self.results[f'server_{i+1}_mcp'] = {
                                'status': 'working',
                                'tools_count': len(tools),
                                'discovery_time_ms': discovery_time,
                                'execution_time_ms': execution_time
                            }

                        except Exception as e:
                            print(f"     ⚠️ Tool execution failed: {e}")
                            self.results[f'server_{i+1}_mcp'] = {
                                'status': 'partial',
                                'tools_count': len(tools),
                                'discovery_time_ms': discovery_time,
                                'execution_error': str(e)
                            }
                    else:
                        print(f"     ⚠️ No tools available for testing")
                        self.results[f'server_{i+1}_mcp'] = {
                            'status': 'no_tools',
                            'discovery_time_ms': discovery_time
                        }

            except Exception as e:
                print(f"     ❌ MCP protocol test failed: {e}")
                self.results[f'server_{i+1}_mcp'] = {'status': 'failed', 'error': str(e)}

        print()

    async def check_performance_metrics(self):
        """Check performance and connection pooling."""

        print("5. Performance & Pool Efficiency Check")

        client = MCPClient(
            connection_pool_config={"max_connections": 10},
            enable_metrics=True
        )

        if self.server_urls:
            url = self.server_urls[0]  # Test with first server

            try:
                async with client:
                    # Make multiple calls to test pooling
                    start_time = time.time()

                    tasks = []
                    for i in range(5):
                        task = client.discover_tools(url)
                        tasks.append(task)

                    await asyncio.gather(*tasks, return_exceptions=True)

                    total_time = time.time() - start_time

                    # Check metrics
                    metrics = client.get_metrics()
                    pool_hits = metrics.get('websocket_pool_hits', 0)
                    pool_misses = metrics.get('websocket_pool_misses', 0)

                    if pool_hits + pool_misses > 0:
                        efficiency = (pool_hits / (pool_hits + pool_misses)) * 100
                    else:
                        efficiency = 0

                    print(f"   Multiple calls test: {total_time:.2f}s total")
                    print(f"   Pool hits: {pool_hits}")
                    print(f"   Pool misses: {pool_misses}")
                    print(f"   Pool efficiency: {efficiency:.1f}%")
                    print(f"   Active connections: {len(client._websocket_pools)}")

                    self.results['performance'] = {
                        'total_time': total_time,
                        'pool_hits': pool_hits,
                        'pool_misses': pool_misses,
                        'pool_efficiency': efficiency,
                        'active_connections': len(client._websocket_pools)
                    }

                    if efficiency > 60:
                        print("   ✅ Good pool efficiency")
                    elif efficiency > 20:
                        print("   ⚠️ Moderate pool efficiency")
                    else:
                        print("   ❌ Poor pool efficiency - check connection settings")

            except Exception as e:
                print(f"   ❌ Performance test failed: {e}")
                self.results['performance'] = {'status': 'failed', 'error': str(e)}

        print()

    def generate_diagnostic_report(self):
        """Generate comprehensive diagnostic report."""

        print("=== DIAGNOSTIC REPORT ===")

        # System health
        cpu = self.results.get('cpu_usage', 0)
        memory = self.results.get('memory_usage', {}).get('percent', 0)

        if cpu < 70 and memory < 70:
            print("✅ System Health: GOOD")
        elif cpu < 85 and memory < 85:
            print("⚠️ System Health: MODERATE")
        else:
            print("❌ System Health: POOR - resource constraints detected")

        # Connectivity status
        connected_servers = sum(
            1 for key, value in self.results.items()
            if key.endswith('_connectivity') and value.get('status') == 'connected'
        )
        total_servers = len([k for k in self.results.keys() if k.endswith('_connectivity')])

        if connected_servers == total_servers:
            print("✅ Network Connectivity: ALL SERVERS REACHABLE")
        elif connected_servers > total_servers // 2:
            print("⚠️ Network Connectivity: PARTIAL - some servers unreachable")
        else:
            print("❌ Network Connectivity: POOR - most servers unreachable")

        # WebSocket functionality
        working_websockets = sum(
            1 for key, value in self.results.items()
            if key.endswith('_websocket') and value.get('status') == 'working'
        )
        total_websockets = len([k for k in self.results.keys() if k.endswith('_websocket')])

        if working_websockets == total_websockets:
            print("✅ WebSocket Functionality: ALL WORKING")
        elif working_websockets > 0:
            print("⚠️ WebSocket Functionality: PARTIAL")
        else:
            print("❌ WebSocket Functionality: FAILED")

        # MCP protocol
        working_mcp = sum(
            1 for key, value in self.results.items()
            if key.endswith('_mcp') and value.get('status') == 'working'
        )
        total_mcp = len([k for k in self.results.keys() if k.endswith('_mcp')])

        if working_mcp == total_mcp:
            print("✅ MCP Protocol: ALL WORKING")
        elif working_mcp > 0:
            print("⚠️ MCP Protocol: PARTIAL")
        else:
            print("❌ MCP Protocol: FAILED")

        # Performance
        perf = self.results.get('performance', {})
        efficiency = perf.get('pool_efficiency', 0)

        if efficiency > 60:
            print("✅ Performance: OPTIMAL")
        elif efficiency > 20:
            print("⚠️ Performance: MODERATE")
        else:
            print("❌ Performance: POOR - connection pooling issues")

        print("\n=== RECOMMENDATIONS ===")

        # Resource recommendations
        if cpu > 80:
            print("- Scale out servers or optimize CPU-intensive operations")
        if memory > 80:
            print("- Investigate memory leaks or increase server memory")

        # Connectivity recommendations
        if connected_servers < total_servers:
            print("- Check network connectivity to unreachable servers")
            print("- Verify firewall and security group settings")

        # Performance recommendations
        if efficiency < 30:
            print("- Review connection pool configuration")
            print("- Check server keep-alive settings")
            print("- Consider increasing ping intervals")

        # Export results
        with open('/var/log/mcp-diagnostics.json', 'w') as f:
            json.dump(self.results, f, indent=2)

        print(f"\nFull diagnostic results saved to: /var/log/mcp-diagnostics.json")

# Usage
async def run_production_diagnostics():
    """Run production diagnostics."""

    server_urls = [
        "wss://api1.company.com/mcp",
        "wss://api2.company.com/mcp",
        "wss://api3.company.com/mcp"
    ]

    diagnostics = ProductionDiagnostics(server_urls)
    await diagnostics.run_full_diagnostics()

# Run diagnostics
if __name__ == "__main__":
    asyncio.run(run_production_diagnostics())
```

## Disaster Recovery

### Backup & Recovery Procedures

```python
# disaster_recovery.py
import asyncio
import json
import boto3
from datetime import datetime, timedelta
import logging

class MCPDisasterRecovery:
    """Disaster recovery procedures for MCP WebSocket deployments."""

    def __init__(self, backup_config):
        self.backup_config = backup_config
        self.s3_client = boto3.client('s3') if backup_config.get('s3_enabled') else None
        self.logger = logging.getLogger(__name__)

    async def create_backup(self):
        """Create complete backup of MCP server state."""

        timestamp = datetime.utcnow().isoformat()
        backup_data = {
            "timestamp": timestamp,
            "version": "1.0",
            "components": {}
        }

        # Backup server configuration
        backup_data["components"]["configuration"] = await self.backup_configuration()

        # Backup connection pool state
        backup_data["components"]["connection_pools"] = await self.backup_connection_pools()

        # Backup metrics and monitoring data
        backup_data["components"]["metrics"] = await self.backup_metrics()

        # Backup certificates and keys (metadata only, not actual files)
        backup_data["components"]["certificates"] = await self.backup_certificate_info()

        # Save backup locally
        backup_filename = f"mcp-backup-{timestamp.replace(':', '-')}.json"
        local_path = f"/var/backups/{backup_filename}"

        with open(local_path, 'w') as f:
            json.dump(backup_data, f, indent=2)

        self.logger.info(f"Backup created: {local_path}")

        # Upload to S3 if configured
        if self.s3_client:
            try:
                self.s3_client.upload_file(
                    local_path,
                    self.backup_config['s3_bucket'],
                    f"mcp-backups/{backup_filename}"
                )
                self.logger.info(f"Backup uploaded to S3: {backup_filename}")
            except Exception as e:
                self.logger.error(f"S3 upload failed: {e}")

        return backup_data

    async def backup_configuration(self):
        """Backup server configuration."""

        config = {
            "server_settings": {
                "host": os.getenv("WEBSOCKET_HOST", "0.0.0.0"),
                "port": int(os.getenv("WEBSOCKET_PORT", "3001")),
                "max_connections": int(os.getenv("MAX_CONNECTIONS", "500")),
                "ping_interval": float(os.getenv("PING_INTERVAL", "30.0")),
                "ping_timeout": float(os.getenv("PING_TIMEOUT", "10.0"))
            },
            "authentication": {
                "enabled": bool(os.getenv("AUTH_ENABLED", "true")),
                "method": os.getenv("AUTH_METHOD", "api_key")
            },
            "monitoring": {
                "metrics_enabled": bool(os.getenv("METRICS_ENABLED", "true")),
                "logging_level": os.getenv("LOG_LEVEL", "INFO")
            }
        }

        return config

    async def backup_connection_pools(self):
        """Backup connection pool statistics."""

        # In a real implementation, this would backup pool state
        # from running servers via API calls

        pool_data = {
            "pool_statistics": {
                "total_pools": 0,
                "active_connections": 0,
                "pool_efficiency": 0.0
            },
            "pool_configuration": {
                "max_connections": 20,
                "connection_timeout": 30.0,
                "cleanup_interval": 300
            }
        }

        return pool_data

    async def backup_metrics(self):
        """Backup metrics and monitoring data."""

        # This would connect to Prometheus/metrics endpoint
        # and backup recent metrics data

        metrics_data = {
            "collection_time": datetime.utcnow().isoformat(),
            "metrics": {
                "websocket_connections_total": 0,
                "websocket_messages_total": 0,
                "websocket_errors_total": 0
            }
        }

        return metrics_data

    async def backup_certificate_info(self):
        """Backup certificate information (not the actual certificates)."""

        cert_info = {
            "ssl_enabled": bool(os.getenv("SSL_ENABLED", "true")),
            "certificate_paths": {
                "cert_file": os.getenv("SSL_CERT_PATH", "/etc/ssl/certs/server.crt"),
                "key_file": os.getenv("SSL_KEY_PATH", "/etc/ssl/private/server.key")
            },
            "expiry_check_needed": True
        }

        return cert_info

    async def restore_from_backup(self, backup_file):
        """Restore MCP server from backup."""

        self.logger.info(f"Starting restore from backup: {backup_file}")

        try:
            with open(backup_file, 'r') as f:
                backup_data = json.load(f)

            # Restore configuration
            await self.restore_configuration(backup_data["components"]["configuration"])

            # Restore connection pool settings
            await self.restore_connection_pool_config(backup_data["components"]["connection_pools"])

            # Validate certificates
            await self.validate_certificates(backup_data["components"]["certificates"])

            self.logger.info("Restore completed successfully")
            return True

        except Exception as e:
            self.logger.error(f"Restore failed: {e}")
            return False

    async def restore_configuration(self, config_data):
        """Restore server configuration."""

        self.logger.info("Restoring server configuration")

        # In a real implementation, this would update environment variables
        # or configuration files and restart services

        server_settings = config_data["server_settings"]
        auth_settings = config_data["authentication"]
        monitoring_settings = config_data["monitoring"]

        # Update environment variables (example)
        os.environ["WEBSOCKET_HOST"] = server_settings["host"]
        os.environ["WEBSOCKET_PORT"] = str(server_settings["port"])
        os.environ["MAX_CONNECTIONS"] = str(server_settings["max_connections"])

        self.logger.info("Configuration restored")

    async def restore_connection_pool_config(self, pool_data):
        """Restore connection pool configuration."""

        self.logger.info("Restoring connection pool configuration")

        pool_config = pool_data["pool_configuration"]

        # Update pool settings
        os.environ["POOL_MAX_CONNECTIONS"] = str(pool_config["max_connections"])
        os.environ["POOL_CONNECTION_TIMEOUT"] = str(pool_config["connection_timeout"])
        os.environ["POOL_CLEANUP_INTERVAL"] = str(pool_config["cleanup_interval"])

        self.logger.info("Connection pool configuration restored")

    async def validate_certificates(self, cert_info):
        """Validate SSL certificates are present and valid."""

        if not cert_info["ssl_enabled"]:
            self.logger.info("SSL not enabled, skipping certificate validation")
            return

        cert_file = cert_info["certificate_paths"]["cert_file"]
        key_file = cert_info["certificate_paths"]["key_file"]

        # Check if certificate files exist
        import os
        if not os.path.exists(cert_file):
            self.logger.error(f"Certificate file not found: {cert_file}")
            raise FileNotFoundError(f"Certificate file not found: {cert_file}")

        if not os.path.exists(key_file):
            self.logger.error(f"Key file not found: {key_file}")
            raise FileNotFoundError(f"Key file not found: {key_file}")

        # Check certificate expiry
        try:
            import ssl
            import socket
            from datetime import datetime

            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

            # This is a simplified check - in production you'd use proper certificate parsing
            self.logger.info("Certificate files validated successfully")

        except Exception as e:
            self.logger.warning(f"Certificate validation warning: {e}")

    async def automated_backup_schedule(self):
        """Run automated backup on schedule."""

        while True:
            try:
                # Create daily backup
                await self.create_backup()

                # Clean up old backups (keep last 7 days)
                await self.cleanup_old_backups(days=7)

                # Wait 24 hours
                await asyncio.sleep(24 * 60 * 60)

            except Exception as e:
                self.logger.error(f"Automated backup failed: {e}")
                # Wait 1 hour before retrying
                await asyncio.sleep(60 * 60)

    async def cleanup_old_backups(self, days=7):
        """Clean up backups older than specified days."""

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Clean up local backups
        import glob
        backup_files = glob.glob("/var/backups/mcp-backup-*.json")

        for backup_file in backup_files:
            try:
                # Extract timestamp from filename
                filename = os.path.basename(backup_file)
                timestamp_str = filename.replace("mcp-backup-", "").replace(".json", "")
                timestamp_str = timestamp_str.replace("-", ":")

                file_date = datetime.fromisoformat(timestamp_str)

                if file_date < cutoff_date:
                    os.remove(backup_file)
                    self.logger.info(f"Removed old backup: {backup_file}")

            except Exception as e:
                self.logger.warning(f"Failed to clean up backup {backup_file}: {e}")

        # Clean up S3 backups if configured
        if self.s3_client:
            try:
                response = self.s3_client.list_objects_v2(
                    Bucket=self.backup_config['s3_bucket'],
                    Prefix='mcp-backups/'
                )

                for obj in response.get('Contents', []):
                    if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                        self.s3_client.delete_object(
                            Bucket=self.backup_config['s3_bucket'],
                            Key=obj['Key']
                        )
                        self.logger.info(f"Removed old S3 backup: {obj['Key']}")

            except Exception as e:
                self.logger.error(f"S3 cleanup failed: {e}")

# Production usage
backup_config = {
    "s3_enabled": True,
    "s3_bucket": "company-mcp-backups",
    "retention_days": 30
}

dr_manager = MCPDisasterRecovery(backup_config)

# Start automated backup schedule
asyncio.create_task(dr_manager.automated_backup_schedule())
```

## Best Practices Summary

### 1. Security Checklist
- ✅ Always use `wss://` in production
- ✅ Implement proper authentication (API keys or JWT)
- ✅ Enable rate limiting and connection limits
- ✅ Use SSL/TLS termination at load balancer
- ✅ Implement IP allowlisting for sensitive environments
- ✅ Regular security audits and certificate rotation

### 2. Performance Optimization
- ✅ Configure connection pooling appropriately
- ✅ Use multiple server instances behind load balancer
- ✅ Monitor pool efficiency and connection metrics
- ✅ Implement proper error handling and retries
- ✅ Use structured logging for troubleshooting

### 3. Monitoring & Alerting
- ✅ Implement comprehensive metrics collection
- ✅ Set up alerts for connection failures and high error rates
- ✅ Monitor resource utilization (CPU, memory, connections)
- ✅ Track pool efficiency and connection health
- ✅ Regular diagnostic health checks

### 4. Disaster Recovery
- ✅ Automated backup procedures
- ✅ Multiple deployment regions for high availability
- ✅ Documented recovery procedures
- ✅ Regular disaster recovery testing
- ✅ Configuration management and version control

This production deployment guide provides the foundation for running WebSocket MCP implementations at enterprise scale with proper security, monitoring, and reliability practices.
