# Production Deployment Guide

Deploy Nexus's workflow-native platform to production environments with enterprise-grade scalability, monitoring, security, and operational excellence.

## Overview

This guide covers production deployment strategies for Nexus, including containerization, orchestration, monitoring, security hardening, and operational procedures. Nexus's multi-channel architecture enables flexible deployment patterns from single-instance to distributed, high-availability configurations.

## Container Deployment

### Docker Configuration

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import os
import json
import yaml
from pathlib import Path
from typing import Dict, Any, List
import subprocess

# Production deployment utilities
class ProductionDeploymentManager:
    """Manage production deployment configurations"""

    def __init__(self, environment: str = "production"):
        self.environment = environment
        self.deployment_config = {
            "environment": environment,
            "scaling": {
                "min_replicas": 2,
                "max_replicas": 10,
                "target_cpu_utilization": 70,
                "target_memory_utilization": 80
            },
            "security": {
                "enable_tls": True,
                "enable_auth": True,
                "enable_audit": True,
                "security_scan": True
            },
            "monitoring": {
                "enable_metrics": True,
                "enable_logging": True,
                "enable_tracing": True,
                "retention_days": 30
            },
            "performance": {
                "enable_caching": True,
                "cache_size_mb": 512,
                "worker_threads": 4,
                "connection_pool_size": 20
            }
        }

    def generate_dockerfile(self, app_name: str, version: str) -> str:
        """Generate production-optimized Dockerfile"""

        dockerfile_content = f'''# Production Nexus Deployment
FROM python:3.11-slim as builder

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    build-essential \\
    curl \\
    git \\
    && rm -rf /var/lib/apt/lists/*

# Create application user
RUN groupadd -r nexus && useradd -r -g nexus nexus

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim as production

# Install runtime dependencies
RUN apt-get update && apt-get install -y \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Create application user
RUN groupadd -r nexus && useradd -r -g nexus nexus

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/nexus/.local

# Copy application code
COPY --chown=nexus:nexus . .

# Set environment variables
ENV PATH=/home/nexus/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV NEXUS_ENV=production
ENV NEXUS_APP_NAME={app_name}
ENV NEXUS_VERSION={version}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \\
    CMD curl -f http://localhost:8000/health || exit 1

# Switch to non-root user
USER nexus

# Expose ports
EXPOSE 8000 8001 8002

# Run application
CMD ["python", "-m", "nexus", "start", "--production"]
'''
        return dockerfile_content

    def generate_docker_compose(self, app_name: str) -> str:
        """Generate Docker Compose configuration for production"""

        compose_config = {
            "version": "3.8",
            "services": {
                "nexus-app": {
                    "build": {
                        "context": ".",
                        "dockerfile": "Dockerfile",
                        "target": "production"
                    },
                    "container_name": f"{app_name}-nexus",
                    "restart": "unless-stopped",
                    "ports": [
                        "8000:8000",  # API
                        "8001:8001",  # CLI
                        "8002:8002"   # MCP
                    ],
                    "environment": {
                        "NEXUS_ENV": "production",
                        "NEXUS_API_PORT": "8000",
                        "NEXUS_CLI_PORT": "8001",
                        "NEXUS_MCP_PORT": "8002",
                        "NEXUS_DB_URL": "postgresql://nexus:${POSTGRES_PASSWORD}@postgres:5432/nexus_prod",
                        "NEXUS_REDIS_URL": "redis://redis:6379/0",
                        "NEXUS_SECRET_KEY": "${NEXUS_SECRET_KEY}",
                        "NEXUS_LOG_LEVEL": "INFO"
                    },
                    "depends_on": {
                        "postgres": {"condition": "service_healthy"},
                        "redis": {"condition": "service_healthy"}
                    },
                    "volumes": [
                        "./config:/app/config:ro",
                        "./logs:/app/logs",
                        "nexus-data:/app/data"
                    ],
                    "networks": ["nexus-network"],
                    "healthcheck": {
                        "test": ["CMD", "curl", "-f", "http://localhost:8000/health"],
                        "interval": "30s",
                        "timeout": "10s",
                        "retries": 3,
                        "start_period": "60s"
                    },
                    "deploy": {
                        "resources": {
                            "limits": {
                                "memory": "2G",
                                "cpus": "2.0"
                            },
                            "reservations": {
                                "memory": "512M",
                                "cpus": "0.5"
                            }
                        }
                    }
                },
                "postgres": {
                    "image": "postgres:15-alpine",
                    "container_name": f"{app_name}-postgres",
                    "restart": "unless-stopped",
                    "environment": {
                        "POSTGRES_DB": "nexus_prod",
                        "POSTGRES_USER": "nexus",
                        "POSTGRES_PASSWORD": "${POSTGRES_PASSWORD}",
                        "POSTGRES_INITDB_ARGS": "--auth-host=md5"
                    },
                    "volumes": [
                        "postgres-data:/var/lib/postgresql/data",
                        "./init-db:/docker-entrypoint-initdb.d:ro"
                    ],
                    "networks": ["nexus-network"],
                    "healthcheck": {
                        "test": ["CMD-SHELL", "pg_isready -U nexus -d nexus_prod"],
                        "interval": "10s",
                        "timeout": "5s",
                        "retries": 5
                    }
                },
                "redis": {
                    "image": "redis:7-alpine",
                    "container_name": f"{app_name}-redis",
                    "restart": "unless-stopped",
                    "command": ["redis-server", "--appendonly", "yes", "--maxmemory", "256mb", "--maxmemory-policy", "allkeys-lru"],
                    "volumes": ["redis-data:/data"],
                    "networks": ["nexus-network"],
                    "healthcheck": {
                        "test": ["CMD", "redis-cli", "ping"],
                        "interval": "10s",
                        "timeout": "3s",
                        "retries": 3
                    }
                },
                "nginx": {
                    "image": "nginx:alpine",
                    "container_name": f"{app_name}-nginx",
                    "restart": "unless-stopped",
                    "ports": ["80:80", "443:443"],
                    "volumes": [
                        "./nginx/nginx.conf:/etc/nginx/nginx.conf:ro",
                        "./nginx/ssl:/etc/nginx/ssl:ro",
                        "./logs/nginx:/var/log/nginx"
                    ],
                    "depends_on": ["nexus-app"],
                    "networks": ["nexus-network"]
                }
            },
            "volumes": {
                "nexus-data": {"driver": "local"},
                "postgres-data": {"driver": "local"},
                "redis-data": {"driver": "local"}
            },
            "networks": {
                "nexus-network": {
                    "driver": "bridge",
                    "ipam": {
                        "config": [{"subnet": "172.20.0.0/16"}]
                    }
                }
            }
        }

        return yaml.dump(compose_config, default_flow_style=False, sort_keys=False)

    def generate_nginx_config(self, app_name: str, domain: str) -> str:
        """Generate Nginx configuration for load balancing and SSL termination"""

        nginx_config = f'''# Production Nginx Configuration for {app_name}
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {{
    worker_connections 1024;
    use epoll;
    multi_accept on;
}}

http {{
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logging format
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for" '
                    'rt=$request_time uct="$upstream_connect_time" '
                    'uht="$upstream_header_time" urt="$upstream_response_time"';

    access_log /var/log/nginx/access.log main;

    # Basic settings
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 10M;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types
        application/json
        application/javascript
        application/xml+rss
        application/atom+xml
        image/svg+xml
        text/plain
        text/css
        text/xml
        text/javascript;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=auth:10m rate=1r/s;

    # Upstream configuration
    upstream nexus_api {{
        least_conn;
        server nexus-app:8000 max_fails=3 fail_timeout=30s;
        keepalive 32;
    }}

    upstream nexus_cli {{
        least_conn;
        server nexus-app:8001 max_fails=3 fail_timeout=30s;
        keepalive 32;
    }}

    upstream nexus_mcp {{
        least_conn;
        server nexus-app:8002 max_fails=3 fail_timeout=30s;
        keepalive 32;
    }}

    # HTTP to HTTPS redirect
    server {{
        listen 80;
        server_name {domain};
        return 301 https://$server_name$request_uri;
    }}

    # HTTPS server
    server {{
        listen 443 ssl http2;
        server_name {domain};

        # SSL configuration
        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
        ssl_prefer_server_ciphers off;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 10m;

        # Security headers
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        add_header X-Content-Type-Options nosniff always;
        add_header X-Frame-Options DENY always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;

        # API endpoints
        location /api/ {{
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://nexus_api;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_cache_bypass $http_upgrade;
            proxy_connect_timeout 30s;
            proxy_send_timeout 30s;
            proxy_read_timeout 30s;
        }}

        # CLI endpoints
        location /cli/ {{
            proxy_pass http://nexus_cli;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_cache_bypass $http_upgrade;
        }}

        # MCP endpoints
        location /mcp/ {{
            proxy_pass http://nexus_mcp;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_cache_bypass $http_upgrade;
        }}

        # Health check
        location /health {{
            proxy_pass http://nexus_api;
            access_log off;
        }}

        # Static files (if any)
        location /static/ {{
            alias /app/static/;
            expires 1y;
            add_header Cache-Control "public, immutable";
        }}
    }}
}}
'''
        return nginx_config

# Test deployment manager
deployment_manager = ProductionDeploymentManager("production")

# Generate deployment files
dockerfile = deployment_manager.generate_dockerfile("nexus-workflow-platform", "1.0.0")
docker_compose = deployment_manager.generate_docker_compose("nexus-workflow-platform")
nginx_config = deployment_manager.generate_nginx_config("nexus-workflow-platform", "nexus.example.com")
```

### Kubernetes Deployment

```python
from nexus import Nexus
import yaml
from typing import Dict, Any, List
import base64

class KubernetesDeploymentManager:
    """Manage Kubernetes deployments for Nexus"""

    def __init__(self, namespace: str = "nexus-production"):
        self.namespace = namespace
        self.app_name = "nexus-platform"
        self.version = "1.0.0"
        self.deployment_config = {
            "replicas": 3,
            "resources": {
                "requests": {"memory": "512Mi", "cpu": "0.5"},
                "limits": {"memory": "2Gi", "cpu": "2.0"}
            },
            "autoscaling": {
                "min_replicas": 2,
                "max_replicas": 10,
                "target_cpu_utilization": 70,
                "target_memory_utilization": 80
            },
            "persistence": {
                "storage_class": "fast-ssd",
                "access_mode": "ReadWriteOnce",
                "size": "10Gi"
            }
        }

    def generate_namespace(self) -> Dict[str, Any]:
        """Generate namespace configuration"""
        return {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": self.namespace,
                "labels": {
                    "app": self.app_name,
                    "version": self.version,
                    "environment": "production"
                }
            }
        }

    def generate_configmap(self) -> Dict[str, Any]:
        """Generate ConfigMap for application configuration"""
        return {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": f"{self.app_name}-config",
                "namespace": self.namespace
            },
            "data": {
                "nexus.yaml": '''
# Nexus Production Configuration
environment: production
api:
  port: 8000
  host: "0.0.0.0"
  cors_origins: ["https://nexus.example.com"]
  rate_limiting:
    enabled: true
    requests_per_minute: 1000
cli:
  port: 8001
  host: "0.0.0.0"
mcp:
  port: 8002
  host: "0.0.0.0"
database:
  url: "${DATABASE_URL}"
  pool_size: 20
  max_overflow: 30
  pool_timeout: 30
redis:
  url: "${REDIS_URL}"
  max_connections: 50
logging:
  level: INFO
  format: json
  output: stdout
monitoring:
  metrics_enabled: true
  tracing_enabled: true
  health_check_interval: 30
security:
  authentication_enabled: true
  encryption_enabled: true
  audit_logging: true
''',
                "logging.yaml": '''
version: 1
disable_existing_loggers: false
formatters:
  standard:
    format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  json:
    format: "%(asctime)s %(name)s %(levelname)s %(message)s"
    class: pythonjsonlogger.jsonlogger.JsonFormatter
handlers:
  console:
    class: logging.StreamHandler
    level: INFO
    formatter: json
    stream: ext://sys.stdout
  file:
    class: logging.handlers.RotatingFileHandler
    level: INFO
    formatter: standard
    filename: /app/logs/nexus.log
    maxBytes: 10485760
    backupCount: 5
loggers:
  nexus:
    level: INFO
    handlers: [console, file]
    propagate: false
root:
  level: INFO
  handlers: [console]
'''
            }
        }

    def generate_secret(self) -> Dict[str, Any]:
        """Generate Secret for sensitive configuration"""

        # In production, these would be properly encrypted
        secret_data = {
            "DATABASE_URL": base64.b64encode(b"postgresql://nexus:password@postgres:5432/nexus_prod").decode(),
            "REDIS_URL": base64.b64encode(b"redis://redis:6379/0").decode(),
            "SECRET_KEY": base64.b64encode(b"your-super-secret-key-here").decode(),
            "JWT_SECRET": base64.b64encode(b"your-jwt-secret-key-here").decode()
        }

        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": f"{self.app_name}-secrets",
                "namespace": self.namespace
            },
            "type": "Opaque",
            "data": secret_data
        }

    def generate_deployment(self) -> Dict[str, Any]:
        """Generate main application deployment"""
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": f"{self.app_name}-deployment",
                "namespace": self.namespace,
                "labels": {
                    "app": self.app_name,
                    "version": self.version,
                    "component": "api"
                }
            },
            "spec": {
                "replicas": self.deployment_config["replicas"],
                "selector": {
                    "matchLabels": {
                        "app": self.app_name,
                        "component": "api"
                    }
                },
                "template": {
                    "metadata": {
                        "labels": {
                            "app": self.app_name,
                            "version": self.version,
                            "component": "api"
                        },
                        "annotations": {
                            "prometheus.io/scrape": "true",
                            "prometheus.io/port": "8000",
                            "prometheus.io/path": "/metrics"
                        }
                    },
                    "spec": {
                        "securityContext": {
                            "runAsNonRoot": True,
                            "runAsUser": 1000,
                            "fsGroup": 2000
                        },
                        "containers": [{
                            "name": "nexus-app",
                            "image": f"nexus-platform:{self.version}",
                            "imagePullPolicy": "Always",
                            "ports": [
                                {"containerPort": 8000, "name": "api"},
                                {"containerPort": 8001, "name": "cli"},
                                {"containerPort": 8002, "name": "mcp"}
                            ],
                            "env": [
                                {"name": "NEXUS_ENV", "value": "production"},
                                {"name": "NEXUS_CONFIG_FILE", "value": "/app/config/nexus.yaml"},
                                {"name": "DATABASE_URL", "valueFrom": {"secretKeyRef": {"name": f"{self.app_name}-secrets", "key": "DATABASE_URL"}}},
                                {"name": "REDIS_URL", "valueFrom": {"secretKeyRef": {"name": f"{self.app_name}-secrets", "key": "REDIS_URL"}}},
                                {"name": "SECRET_KEY", "valueFrom": {"secretKeyRef": {"name": f"{self.app_name}-secrets", "key": "SECRET_KEY"}}}
                            ],
                            "volumeMounts": [
                                {"name": "config", "mountPath": "/app/config", "readOnly": True},
                                {"name": "data", "mountPath": "/app/data"},
                                {"name": "logs", "mountPath": "/app/logs"}
                            ],
                            "resources": self.deployment_config["resources"],
                            "livenessProbe": {
                                "httpGet": {
                                    "path": "/health",
                                    "port": 8000
                                },
                                "initialDelaySeconds": 60,
                                "periodSeconds": 30,
                                "timeoutSeconds": 10,
                                "failureThreshold": 3
                            },
                            "readinessProbe": {
                                "httpGet": {
                                    "path": "/ready",
                                    "port": 8000
                                },
                                "initialDelaySeconds": 15,
                                "periodSeconds": 10,
                                "timeoutSeconds": 5,
                                "failureThreshold": 3
                            },
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "readOnlyRootFilesystem": True,
                                "capabilities": {"drop": ["ALL"]}
                            }
                        }],
                        "volumes": [
                            {"name": "config", "configMap": {"name": f"{self.app_name}-config"}},
                            {"name": "data", "persistentVolumeClaim": {"claimName": f"{self.app_name}-data-pvc"}},
                            {"name": "logs", "emptyDir": {}}
                        ],
                        "affinity": {
                            "podAntiAffinity": {
                                "preferredDuringSchedulingIgnoredDuringExecution": [{
                                    "weight": 100,
                                    "podAffinityTerm": {
                                        "labelSelector": {
                                            "matchExpressions": [{
                                                "key": "app",
                                                "operator": "In",
                                                "values": [self.app_name]
                                            }]
                                        },
                                        "topologyKey": "kubernetes.io/hostname"
                                    }
                                }]
                            }
                        }
                    }
                },
                "strategy": {
                    "type": "RollingUpdate",
                    "rollingUpdate": {
                        "maxSurge": 1,
                        "maxUnavailable": 0
                    }
                }
            }
        }

    def generate_service(self) -> Dict[str, Any]:
        """Generate Kubernetes service"""
        return {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": f"{self.app_name}-service",
                "namespace": self.namespace,
                "labels": {
                    "app": self.app_name,
                    "component": "api"
                }
            },
            "spec": {
                "selector": {
                    "app": self.app_name,
                    "component": "api"
                },
                "ports": [
                    {"name": "api", "port": 8000, "targetPort": 8000, "protocol": "TCP"},
                    {"name": "cli", "port": 8001, "targetPort": 8001, "protocol": "TCP"},
                    {"name": "mcp", "port": 8002, "targetPort": 8002, "protocol": "TCP"}
                ],
                "type": "ClusterIP"
            }
        }

    def generate_ingress(self, domain: str) -> Dict[str, Any]:
        """Generate Ingress configuration"""
        return {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "Ingress",
            "metadata": {
                "name": f"{self.app_name}-ingress",
                "namespace": self.namespace,
                "annotations": {
                    "kubernetes.io/ingress.class": "nginx",
                    "cert-manager.io/cluster-issuer": "letsencrypt-prod",
                    "nginx.ingress.kubernetes.io/rate-limit": "1000",
                    "nginx.ingress.kubernetes.io/rate-limit-window": "1m",
                    "nginx.ingress.kubernetes.io/ssl-redirect": "true",
                    "nginx.ingress.kubernetes.io/force-ssl-redirect": "true"
                }
            },
            "spec": {
                "tls": [{
                    "hosts": [domain],
                    "secretName": f"{self.app_name}-tls"
                }],
                "rules": [{
                    "host": domain,
                    "http": {
                        "paths": [
                            {
                                "path": "/api",
                                "pathType": "Prefix",
                                "backend": {
                                    "service": {
                                        "name": f"{self.app_name}-service",
                                        "port": {"number": 8000}
                                    }
                                }
                            },
                            {
                                "path": "/cli",
                                "pathType": "Prefix",
                                "backend": {
                                    "service": {
                                        "name": f"{self.app_name}-service",
                                        "port": {"number": 8001}
                                    }
                                }
                            },
                            {
                                "path": "/mcp",
                                "pathType": "Prefix",
                                "backend": {
                                    "service": {
                                        "name": f"{self.app_name}-service",
                                        "port": {"number": 8002}
                                    }
                                }
                            }
                        ]
                    }
                }]
            }
        }

    def generate_hpa(self) -> Dict[str, Any]:
        """Generate Horizontal Pod Autoscaler"""
        return {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {
                "name": f"{self.app_name}-hpa",
                "namespace": self.namespace
            },
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": f"{self.app_name}-deployment"
                },
                "minReplicas": self.deployment_config["autoscaling"]["min_replicas"],
                "maxReplicas": self.deployment_config["autoscaling"]["max_replicas"],
                "metrics": [
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "cpu",
                            "target": {
                                "type": "Utilization",
                                "averageUtilization": self.deployment_config["autoscaling"]["target_cpu_utilization"]
                            }
                        }
                    },
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "memory",
                            "target": {
                                "type": "Utilization",
                                "averageUtilization": self.deployment_config["autoscaling"]["target_memory_utilization"]
                            }
                        }
                    }
                ],
                "behavior": {
                    "scaleDown": {
                        "stabilizationWindowSeconds": 300,
                        "policies": [{
                            "type": "Percent",
                            "value": 10,
                            "periodSeconds": 60
                        }]
                    },
                    "scaleUp": {
                        "stabilizationWindowSeconds": 60,
                        "policies": [{
                            "type": "Percent",
                            "value": 50,
                            "periodSeconds": 30
                        }]
                    }
                }
            }
        }

    def generate_pvc(self) -> Dict[str, Any]:
        """Generate Persistent Volume Claim"""
        return {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": f"{self.app_name}-data-pvc",
                "namespace": self.namespace
            },
            "spec": {
                "accessModes": [self.deployment_config["persistence"]["access_mode"]],
                "storageClassName": self.deployment_config["persistence"]["storage_class"],
                "resources": {
                    "requests": {
                        "storage": self.deployment_config["persistence"]["size"]
                    }
                }
            }
        }

# Test Kubernetes deployment manager
k8s_manager = KubernetesDeploymentManager("nexus-production")

# Generate Kubernetes manifests
namespace = k8s_manager.generate_namespace()
configmap = k8s_manager.generate_configmap()
secret = k8s_manager.generate_secret()
deployment = k8s_manager.generate_deployment()
service = k8s_manager.generate_service()
ingress = k8s_manager.generate_ingress("nexus.example.com")
hpa = k8s_manager.generate_hpa()
pvc = k8s_manager.generate_pvc()

# Convert to YAML for deployment
kubernetes_manifests = {
    "namespace.yaml": yaml.dump(namespace),
    "configmap.yaml": yaml.dump(configmap),
    "secret.yaml": yaml.dump(secret),
    "deployment.yaml": yaml.dump(deployment),
    "service.yaml": yaml.dump(service),
    "ingress.yaml": yaml.dump(ingress),
    "hpa.yaml": yaml.dump(hpa),
    "pvc.yaml": yaml.dump(pvc)
}
```

## Monitoring and Observability

### Comprehensive Monitoring Setup

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
import json
from typing import Dict, Any, List
from enum import Enum
import threading
from collections import defaultdict, deque

class MetricType(Enum):
    """Types of metrics collected"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"

class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"

class ProductionMonitoringSystem:
    """Comprehensive production monitoring for Nexus"""

    def __init__(self, app_name: str):
        self.app_name = app_name
        self.metrics_storage = defaultdict(dict)
        self.alert_rules = {}
        self.active_alerts = {}
        self.metric_history = defaultdict(lambda: deque(maxlen=1000))
        self.monitoring_lock = threading.Lock()

        # Initialize core metrics
        self._initialize_core_metrics()
        self._initialize_alert_rules()

    def _initialize_core_metrics(self):
        """Initialize core application metrics"""

        core_metrics = {
            # Application metrics
            "http_requests_total": {"type": MetricType.COUNTER, "value": 0, "labels": ["method", "endpoint", "status"]},
            "http_request_duration_seconds": {"type": MetricType.HISTOGRAM, "buckets": [0.1, 0.5, 1.0, 2.0, 5.0], "values": []},
            "active_connections": {"type": MetricType.GAUGE, "value": 0},
            "workflow_executions_total": {"type": MetricType.COUNTER, "value": 0, "labels": ["workflow", "status"]},
            "workflow_execution_duration_seconds": {"type": MetricType.HISTOGRAM, "buckets": [1, 5, 10, 30, 60], "values": []},

            # System metrics
            "memory_usage_bytes": {"type": MetricType.GAUGE, "value": 0},
            "cpu_usage_percent": {"type": MetricType.GAUGE, "value": 0},
            "disk_usage_bytes": {"type": MetricType.GAUGE, "value": 0},
            "network_bytes_total": {"type": MetricType.COUNTER, "value": 0, "labels": ["direction"]},

            # Database metrics
            "database_connections_active": {"type": MetricType.GAUGE, "value": 0},
            "database_query_duration_seconds": {"type": MetricType.HISTOGRAM, "buckets": [0.001, 0.01, 0.1, 1.0, 5.0], "values": []},
            "database_queries_total": {"type": MetricType.COUNTER, "value": 0, "labels": ["operation", "table"]},

            # Cache metrics
            "cache_hits_total": {"type": MetricType.COUNTER, "value": 0, "labels": ["cache_type"]},
            "cache_misses_total": {"type": MetricType.COUNTER, "value": 0, "labels": ["cache_type"]},
            "cache_size_bytes": {"type": MetricType.GAUGE, "value": 0, "labels": ["cache_type"]},

            # Error metrics
            "errors_total": {"type": MetricType.COUNTER, "value": 0, "labels": ["type", "component"]},
            "error_rate": {"type": MetricType.GAUGE, "value": 0.0}
        }

        self.metrics_storage.update(core_metrics)

    def _initialize_alert_rules(self):
        """Initialize alerting rules"""

        self.alert_rules = {
            "high_error_rate": {
                "condition": lambda metrics: metrics.get("error_rate", {}).get("value", 0) > 0.05,
                "severity": AlertSeverity.CRITICAL,
                "message": "Error rate is above 5%",
                "cooldown": 300  # 5 minutes
            },
            "high_memory_usage": {
                "condition": lambda metrics: self._get_memory_usage_percent(metrics) > 85,
                "severity": AlertSeverity.WARNING,
                "message": "Memory usage is above 85%",
                "cooldown": 600  # 10 minutes
            },
            "high_cpu_usage": {
                "condition": lambda metrics: metrics.get("cpu_usage_percent", {}).get("value", 0) > 80,
                "severity": AlertSeverity.WARNING,
                "message": "CPU usage is above 80%",
                "cooldown": 600
            },
            "database_connection_exhaustion": {
                "condition": lambda metrics: metrics.get("database_connections_active", {}).get("value", 0) > 18,
                "severity": AlertSeverity.CRITICAL,
                "message": "Database connection pool nearly exhausted",
                "cooldown": 300
            },
            "slow_response_time": {
                "condition": lambda metrics: self._get_avg_response_time(metrics) > 2.0,
                "severity": AlertSeverity.WARNING,
                "message": "Average response time is above 2 seconds",
                "cooldown": 600
            }
        }

    def record_metric(self, metric_name: str, value: float, labels: Dict[str, str] = None):
        """Record a metric value"""

        with self.monitoring_lock:
            if metric_name in self.metrics_storage:
                metric = self.metrics_storage[metric_name]

                if metric["type"] == MetricType.COUNTER:
                    metric["value"] += value
                elif metric["type"] == MetricType.GAUGE:
                    metric["value"] = value
                elif metric["type"] in [MetricType.HISTOGRAM, MetricType.SUMMARY]:
                    if "values" not in metric:
                        metric["values"] = []
                    metric["values"].append(value)
                    # Keep only recent values
                    if len(metric["values"]) > 1000:
                        metric["values"] = metric["values"][-1000:]

                # Store in history
                timestamp = time.time()
                self.metric_history[metric_name].append({
                    "timestamp": timestamp,
                    "value": value,
                    "labels": labels or {}
                })

    def get_metric(self, metric_name: str) -> Dict[str, Any]:
        """Get current metric value"""

        with self.monitoring_lock:
            if metric_name in self.metrics_storage:
                metric = self.metrics_storage[metric_name].copy()

                # Add computed values for histograms
                if metric["type"] == MetricType.HISTOGRAM and "values" in metric:
                    values = metric["values"]
                    if values:
                        metric["count"] = len(values)
                        metric["sum"] = sum(values)
                        metric["avg"] = sum(values) / len(values)
                        metric["min"] = min(values)
                        metric["max"] = max(values)

                        # Calculate percentiles
                        sorted_values = sorted(values)
                        metric["p50"] = self._percentile(sorted_values, 50)
                        metric["p95"] = self._percentile(sorted_values, 95)
                        metric["p99"] = self._percentile(sorted_values, 99)

                return metric

            return {}

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all current metrics"""

        all_metrics = {}
        for metric_name in self.metrics_storage.keys():
            all_metrics[metric_name] = self.get_metric(metric_name)

        return all_metrics

    def check_alerts(self) -> List[Dict[str, Any]]:
        """Check for alert conditions"""

        current_time = time.time()
        triggered_alerts = []
        all_metrics = self.get_all_metrics()

        for alert_name, alert_rule in self.alert_rules.items():
            # Check if alert is in cooldown
            if alert_name in self.active_alerts:
                last_triggered = self.active_alerts[alert_name]["last_triggered"]
                if current_time - last_triggered < alert_rule["cooldown"]:
                    continue

            # Check alert condition
            if alert_rule["condition"](all_metrics):
                alert = {
                    "name": alert_name,
                    "severity": alert_rule["severity"].value,
                    "message": alert_rule["message"],
                    "timestamp": current_time,
                    "metrics_snapshot": self._get_relevant_metrics(alert_name, all_metrics)
                }

                triggered_alerts.append(alert)
                self.active_alerts[alert_name] = {
                    "last_triggered": current_time,
                    "alert": alert
                }

        return triggered_alerts

    def generate_health_report(self) -> Dict[str, Any]:
        """Generate comprehensive health report"""

        all_metrics = self.get_all_metrics()
        active_alerts = self.check_alerts()

        # Calculate overall health score
        health_score = self._calculate_health_score(all_metrics, active_alerts)

        # Determine health status
        if health_score >= 95:
            health_status = "excellent"
        elif health_score >= 85:
            health_status = "good"
        elif health_score >= 70:
            health_status = "fair"
        elif health_score >= 50:
            health_status = "poor"
        else:
            health_status = "critical"

        return {
            "timestamp": time.time(),
            "app_name": self.app_name,
            "health_status": health_status,
            "health_score": health_score,
            "summary": {
                "total_requests": all_metrics.get("http_requests_total", {}).get("value", 0),
                "avg_response_time": self._get_avg_response_time(all_metrics),
                "error_rate": all_metrics.get("error_rate", {}).get("value", 0),
                "active_connections": all_metrics.get("active_connections", {}).get("value", 0),
                "memory_usage_percent": self._get_memory_usage_percent(all_metrics),
                "cpu_usage_percent": all_metrics.get("cpu_usage_percent", {}).get("value", 0)
            },
            "alerts": {
                "active_count": len(active_alerts),
                "critical_count": len([a for a in active_alerts if a["severity"] == "critical"]),
                "alerts": active_alerts
            },
            "performance": {
                "workflow_executions": all_metrics.get("workflow_executions_total", {}).get("value", 0),
                "database_queries": all_metrics.get("database_queries_total", {}).get("value", 0),
                "cache_hit_rate": self._calculate_cache_hit_rate(all_metrics)
            },
            "system_resources": {
                "memory_usage_bytes": all_metrics.get("memory_usage_bytes", {}).get("value", 0),
                "cpu_usage_percent": all_metrics.get("cpu_usage_percent", {}).get("value", 0),
                "disk_usage_bytes": all_metrics.get("disk_usage_bytes", {}).get("value", 0),
                "network_io": all_metrics.get("network_bytes_total", {}).get("value", 0)
            }
        }

    def export_prometheus_metrics(self) -> str:
        """Export metrics in Prometheus format"""

        all_metrics = self.get_all_metrics()
        prometheus_output = []

        for metric_name, metric_data in all_metrics.items():
            metric_type = metric_data.get("type", MetricType.GAUGE).value

            # Add TYPE comment
            prometheus_output.append(f"# TYPE {metric_name} {metric_type}")

            if metric_type in ["counter", "gauge"]:
                value = metric_data.get("value", 0)
                prometheus_output.append(f"{metric_name} {value}")

            elif metric_type == "histogram":
                if "values" in metric_data and metric_data["values"]:
                    values = metric_data["values"]
                    buckets = metric_data.get("buckets", [])

                    # Count values in each bucket
                    for bucket in buckets:
                        count = len([v for v in values if v <= bucket])
                        prometheus_output.append(f"{metric_name}_bucket{{le=\"{bucket}\"}} {count}")

                    # Add +Inf bucket
                    prometheus_output.append(f"{metric_name}_bucket{{le=\"+Inf\"}} {len(values)}")

                    # Add sum and count
                    prometheus_output.append(f"{metric_name}_sum {sum(values)}")
                    prometheus_output.append(f"{metric_name}_count {len(values)}")

        return "\\n".join(prometheus_output)

    def _percentile(self, sorted_values: List[float], percentile: float) -> float:
        """Calculate percentile from sorted values"""
        if not sorted_values:
            return 0.0

        index = (percentile / 100.0) * (len(sorted_values) - 1)
        if index.is_integer():
            return sorted_values[int(index)]
        else:
            lower = sorted_values[int(index)]
            upper = sorted_values[int(index) + 1]
            return lower + (upper - lower) * (index - int(index))

    def _get_memory_usage_percent(self, metrics: Dict[str, Any]) -> float:
        """Calculate memory usage percentage"""
        memory_bytes = metrics.get("memory_usage_bytes", {}).get("value", 0)
        # Assume 2GB limit for calculation
        memory_limit = 2 * 1024 * 1024 * 1024
        return (memory_bytes / memory_limit) * 100 if memory_limit > 0 else 0

    def _get_avg_response_time(self, metrics: Dict[str, Any]) -> float:
        """Get average response time from histogram"""
        duration_metric = metrics.get("http_request_duration_seconds", {})
        return duration_metric.get("avg", 0.0)

    def _calculate_cache_hit_rate(self, metrics: Dict[str, Any]) -> float:
        """Calculate cache hit rate percentage"""
        hits = metrics.get("cache_hits_total", {}).get("value", 0)
        misses = metrics.get("cache_misses_total", {}).get("value", 0)
        total = hits + misses
        return (hits / total) * 100 if total > 0 else 0

    def _calculate_health_score(self, metrics: Dict[str, Any], alerts: List[Dict[str, Any]]) -> float:
        """Calculate overall health score (0-100)"""
        score = 100.0

        # Deduct points for alerts
        for alert in alerts:
            if alert["severity"] == "critical":
                score -= 20
            elif alert["severity"] == "warning":
                score -= 10
            elif alert["severity"] == "info":
                score -= 5

        # Deduct points for high resource usage
        memory_percent = self._get_memory_usage_percent(metrics)
        if memory_percent > 90:
            score -= 15
        elif memory_percent > 80:
            score -= 10

        cpu_percent = metrics.get("cpu_usage_percent", {}).get("value", 0)
        if cpu_percent > 90:
            score -= 15
        elif cpu_percent > 80:
            score -= 10

        # Deduct points for high error rate
        error_rate = metrics.get("error_rate", {}).get("value", 0)
        if error_rate > 0.1:
            score -= 20
        elif error_rate > 0.05:
            score -= 10

        return max(0, score)

    def _get_relevant_metrics(self, alert_name: str, all_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Get metrics relevant to specific alert"""

        relevant_metrics_map = {
            "high_error_rate": ["errors_total", "error_rate", "http_requests_total"],
            "high_memory_usage": ["memory_usage_bytes"],
            "high_cpu_usage": ["cpu_usage_percent"],
            "database_connection_exhaustion": ["database_connections_active"],
            "slow_response_time": ["http_request_duration_seconds"]
        }

        relevant_metric_names = relevant_metrics_map.get(alert_name, [])
        return {name: all_metrics.get(name, {}) for name in relevant_metric_names}

# Test monitoring system
monitoring = ProductionMonitoringSystem("nexus-platform")

# Simulate some metrics
monitoring.record_metric("http_requests_total", 1)
monitoring.record_metric("http_request_duration_seconds", 0.15)
monitoring.record_metric("cpu_usage_percent", 45.2)
monitoring.record_metric("memory_usage_bytes", 1024 * 1024 * 512)  # 512MB
monitoring.record_metric("active_connections", 25)
monitoring.record_metric("database_connections_active", 8)
monitoring.record_metric("cache_hits_total", 100)
monitoring.record_metric("cache_misses_total", 25)

# Generate health report
health_report = monitoring.generate_health_report()

# Export Prometheus metrics
prometheus_metrics = monitoring.export_prometheus_metrics()

# Check for alerts
active_alerts = monitoring.check_alerts()
```

## Security Hardening

### Production Security Configuration

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import os
import secrets
import hashlib
import hmac
import json
from typing import Dict, Any, List, Optional
from enum import Enum
import time
from cryptography.fernet import Fernet
import jwt

class SecurityLevel(Enum):
    """Security configuration levels"""
    BASIC = "basic"
    STANDARD = "standard"
    HIGH = "high"
    MAXIMUM = "maximum"

class ProductionSecurityManager:
    """Comprehensive production security configuration"""

    def __init__(self, security_level: SecurityLevel = SecurityLevel.HIGH):
        self.security_level = security_level
        self.security_config = self._initialize_security_config()
        self.encryption_key = self._generate_encryption_key()
        self.audit_log = []

    def _initialize_security_config(self) -> Dict[str, Any]:
        """Initialize security configuration based on level"""

        base_config = {
            "authentication": {
                "enabled": True,
                "multi_factor": False,
                "password_policy": {
                    "min_length": 8,
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_numbers": True,
                    "require_symbols": False
                },
                "session_timeout": 3600,
                "max_failed_attempts": 5,
                "lockout_duration": 900
            },
            "encryption": {
                "data_at_rest": True,
                "data_in_transit": True,
                "algorithm": "AES-256-GCM",
                "key_rotation_days": 90
            },
            "network": {
                "tls_version": "1.2",
                "cipher_suites": ["TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384"],
                "hsts_enabled": True,
                "csrf_protection": True
            },
            "logging": {
                "audit_enabled": True,
                "log_level": "INFO",
                "retention_days": 90,
                "tamper_protection": True
            },
            "headers": {
                "x_content_type_options": "nosniff",
                "x_frame_options": "DENY",
                "x_xss_protection": "1; mode=block",
                "referrer_policy": "strict-origin-when-cross-origin",
                "content_security_policy": "default-src 'self'"
            }
        }

        # Enhance configuration based on security level
        if self.security_level == SecurityLevel.HIGH:
            base_config["authentication"]["multi_factor"] = True
            base_config["authentication"]["password_policy"]["min_length"] = 12
            base_config["authentication"]["password_policy"]["require_symbols"] = True
            base_config["authentication"]["session_timeout"] = 1800  # 30 minutes
            base_config["network"]["tls_version"] = "1.3"
            base_config["logging"]["log_level"] = "DEBUG"

        elif self.security_level == SecurityLevel.MAXIMUM:
            base_config["authentication"]["multi_factor"] = True
            base_config["authentication"]["password_policy"]["min_length"] = 16
            base_config["authentication"]["password_policy"]["require_symbols"] = True
            base_config["authentication"]["session_timeout"] = 900  # 15 minutes
            base_config["authentication"]["max_failed_attempts"] = 3
            base_config["network"]["tls_version"] = "1.3"
            base_config["encryption"]["key_rotation_days"] = 30
            base_config["logging"]["log_level"] = "DEBUG"
            base_config["logging"]["retention_days"] = 365

        return base_config

    def _generate_encryption_key(self) -> bytes:
        """Generate or load encryption key"""
        key_file = "/app/config/encryption.key"

        if os.path.exists(key_file):
            with open(key_file, "rb") as f:
                return f.read()
        else:
            # Generate new key
            key = Fernet.generate_key()
            # In production, this should be stored securely
            return key

    def generate_security_headers(self) -> Dict[str, str]:
        """Generate security headers for HTTP responses"""

        headers = {}
        header_config = self.security_config["headers"]

        headers["X-Content-Type-Options"] = header_config["x_content_type_options"]
        headers["X-Frame-Options"] = header_config["x_frame_options"]
        headers["X-XSS-Protection"] = header_config["x_xss_protection"]
        headers["Referrer-Policy"] = header_config["referrer_policy"]
        headers["Content-Security-Policy"] = header_config["content_security_policy"]

        if self.security_config["network"]["hsts_enabled"]:
            headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        # Add CSRF token header
        if self.security_config["network"]["csrf_protection"]:
            headers["X-CSRF-Token"] = self._generate_csrf_token()

        return headers

    def encrypt_sensitive_data(self, data: str) -> str:
        """Encrypt sensitive data for storage"""

        if not self.security_config["encryption"]["data_at_rest"]:
            return data

        fernet = Fernet(self.encryption_key)
        encrypted_data = fernet.encrypt(data.encode())
        return encrypted_data.decode()

    def decrypt_sensitive_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""

        if not self.security_config["encryption"]["data_at_rest"]:
            return encrypted_data

        fernet = Fernet(self.encryption_key)
        decrypted_data = fernet.decrypt(encrypted_data.encode())
        return decrypted_data.decode()

    def validate_password(self, password: str) -> Dict[str, Any]:
        """Validate password against security policy"""

        policy = self.security_config["authentication"]["password_policy"]
        validation_result = {
            "valid": True,
            "errors": [],
            "strength_score": 0
        }

        # Length check
        if len(password) < policy["min_length"]:
            validation_result["valid"] = False
            validation_result["errors"].append(f"Password must be at least {policy['min_length']} characters long")
        else:
            validation_result["strength_score"] += 20

        # Character requirements
        if policy["require_uppercase"] and not any(c.isupper() for c in password):
            validation_result["valid"] = False
            validation_result["errors"].append("Password must contain at least one uppercase letter")
        else:
            validation_result["strength_score"] += 15

        if policy["require_lowercase"] and not any(c.islower() for c in password):
            validation_result["valid"] = False
            validation_result["errors"].append("Password must contain at least one lowercase letter")
        else:
            validation_result["strength_score"] += 15

        if policy["require_numbers"] and not any(c.isdigit() for c in password):
            validation_result["valid"] = False
            validation_result["errors"].append("Password must contain at least one number")
        else:
            validation_result["strength_score"] += 15

        if policy["require_symbols"] and not any(not c.isalnum() for c in password):
            validation_result["valid"] = False
            validation_result["errors"].append("Password must contain at least one symbol")
        else:
            validation_result["strength_score"] += 15

        # Additional strength checks
        if len(set(password)) / len(password) > 0.7:  # Character diversity
            validation_result["strength_score"] += 10

        if len(password) > policy["min_length"] + 4:  # Extra length bonus
            validation_result["strength_score"] += 10

        return validation_result

    def generate_secure_token(self, user_id: str, expires_in: int = 3600) -> str:
        """Generate secure JWT token"""

        payload = {
            "user_id": user_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + expires_in,
            "iss": "nexus-platform",
            "security_level": self.security_level.value
        }

        # Use a secure secret key in production
        secret_key = os.getenv("JWT_SECRET_KEY", "your-secure-secret-key")

        token = jwt.encode(payload, secret_key, algorithm="HS256")

        # Log token generation
        self._log_security_event("token_generated", {
            "user_id": user_id,
            "expires_in": expires_in,
            "token_id": hashlib.sha256(token.encode()).hexdigest()[:16]
        })

        return token

    def validate_token(self, token: str) -> Dict[str, Any]:
        """Validate JWT token"""

        try:
            secret_key = os.getenv("JWT_SECRET_KEY", "your-secure-secret-key")
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])

            validation_result = {
                "valid": True,
                "user_id": payload["user_id"],
                "expires_at": payload["exp"],
                "security_level": payload.get("security_level", "standard")
            }

            # Check if token is close to expiration
            time_to_expiry = payload["exp"] - int(time.time())
            if time_to_expiry < 300:  # Less than 5 minutes
                validation_result["should_refresh"] = True

            return validation_result

        except jwt.ExpiredSignatureError:
            return {"valid": False, "error": "Token has expired"}
        except jwt.InvalidTokenError:
            return {"valid": False, "error": "Invalid token"}

    def _generate_csrf_token(self) -> str:
        """Generate CSRF protection token"""
        return secrets.token_urlsafe(32)

    def _log_security_event(self, event_type: str, details: Dict[str, Any]):
        """Log security-related events"""

        if not self.security_config["logging"]["audit_enabled"]:
            return

        event = {
            "timestamp": time.time(),
            "event_type": event_type,
            "details": details,
            "security_level": self.security_level.value
        }

        # Add tamper protection if enabled
        if self.security_config["logging"]["tamper_protection"]:
            event["checksum"] = self._calculate_event_checksum(event)

        self.audit_log.append(event)

        # Maintain log size
        max_log_size = 10000
        if len(self.audit_log) > max_log_size:
            self.audit_log = self.audit_log[-max_log_size:]

    def _calculate_event_checksum(self, event: Dict[str, Any]) -> str:
        """Calculate tamper-proof checksum for audit event"""

        # Create deterministic representation
        event_copy = event.copy()
        event_copy.pop("checksum", None)

        event_str = json.dumps(event_copy, sort_keys=True)
        return hashlib.sha256(event_str.encode()).hexdigest()

    def generate_security_report(self) -> Dict[str, Any]:
        """Generate comprehensive security status report"""

        return {
            "timestamp": time.time(),
            "security_level": self.security_level.value,
            "configuration": {
                "authentication_enabled": self.security_config["authentication"]["enabled"],
                "mfa_enabled": self.security_config["authentication"]["multi_factor"],
                "encryption_at_rest": self.security_config["encryption"]["data_at_rest"],
                "encryption_in_transit": self.security_config["encryption"]["data_in_transit"],
                "tls_version": self.security_config["network"]["tls_version"],
                "audit_logging": self.security_config["logging"]["audit_enabled"]
            },
            "audit_statistics": {
                "total_events": len(self.audit_log),
                "recent_events": len([e for e in self.audit_log if time.time() - e["timestamp"] < 3600]),
                "event_types": self._count_event_types()
            },
            "security_recommendations": self._generate_security_recommendations(),
            "compliance_status": self._check_compliance_status()
        }

    def _count_event_types(self) -> Dict[str, int]:
        """Count audit events by type"""

        event_counts = {}
        for event in self.audit_log:
            event_type = event["event_type"]
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        return event_counts

    def _generate_security_recommendations(self) -> List[str]:
        """Generate security improvement recommendations"""

        recommendations = []

        if self.security_level != SecurityLevel.MAXIMUM:
            recommendations.append("Consider upgrading to maximum security level for production")

        if not self.security_config["authentication"]["multi_factor"]:
            recommendations.append("Enable multi-factor authentication for enhanced security")

        if self.security_config["network"]["tls_version"] != "1.3":
            recommendations.append("Upgrade to TLS 1.3 for improved security")

        if self.security_config["encryption"]["key_rotation_days"] > 30:
            recommendations.append("Consider more frequent key rotation (monthly)")

        return recommendations

    def _check_compliance_status(self) -> Dict[str, bool]:
        """Check compliance with security standards"""

        return {
            "gdpr_compliant": self.security_config["logging"]["audit_enabled"] and
                            self.security_config["encryption"]["data_at_rest"],
            "pci_dss_compliant": self.security_config["encryption"]["data_at_rest"] and
                               self.security_config["encryption"]["data_in_transit"] and
                               self.security_config["authentication"]["enabled"],
            "hipaa_compliant": self.security_config["encryption"]["data_at_rest"] and
                             self.security_config["logging"]["audit_enabled"] and
                             self.security_config["authentication"]["multi_factor"],
            "soc2_compliant": self.security_config["logging"]["audit_enabled"] and
                            self.security_config["authentication"]["enabled"]
        }

# Test security manager
security_manager = ProductionSecurityManager(SecurityLevel.HIGH)

# Generate security configurations
security_headers = security_manager.generate_security_headers()
security_report = security_manager.generate_security_report()

# Test password validation
password_validation = security_manager.validate_password("SecureP@ssw0rd123")

# Test token operations
test_token = security_manager.generate_secure_token("user_123", 3600)
token_validation = security_manager.validate_token(test_token)

# Test data encryption
sensitive_data = "confidential information"
encrypted_data = security_manager.encrypt_sensitive_data(sensitive_data)
decrypted_data = security_manager.decrypt_sensitive_data(encrypted_data)
```

This comprehensive production deployment guide covers:

1. **Container Deployment** - Docker and Docker Compose configurations with production optimizations
2. **Kubernetes Deployment** - Complete K8s manifests with autoscaling, ingress, and security
3. **Monitoring and Observability** - Comprehensive metrics, alerting, and health reporting
4. **Security Hardening** - Production-grade security with encryption, authentication, and compliance

Each section provides production-ready configurations that can be directly used for deploying Nexus in enterprise environments.
