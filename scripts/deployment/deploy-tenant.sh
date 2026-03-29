#!/bin/bash
# Deploy a new tenant for Kailash Workflow Studio

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
TENANT_ID=""
DOMAIN=""
PORT_OFFSET=0
POSTGRES_PASSWORD="kailash123"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --tenant-id)
            TENANT_ID="$2"
            shift 2
            ;;
        --domain)
            DOMAIN="$2"
            shift 2
            ;;
        --port-offset)
            PORT_OFFSET="$2"
            shift 2
            ;;
        --postgres-password)
            POSTGRES_PASSWORD="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 --tenant-id <id> [options]"
            echo "Options:"
            echo "  --tenant-id <id>         Unique tenant identifier (required)"
            echo "  --domain <domain>        Domain for the tenant (optional)"
            echo "  --port-offset <offset>   Port offset for services (default: 0)"
            echo "  --postgres-password <pw> PostgreSQL password (default: kailash123)"
            echo "  -h, --help              Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Validate required parameters
if [ -z "$TENANT_ID" ]; then
    echo -e "${RED}Error: --tenant-id is required${NC}"
    exit 1
fi

# Sanitize tenant ID (alphanumeric and underscore only)
SAFE_TENANT_ID=$(echo "$TENANT_ID" | tr -cd '[:alnum:]_' | tr '[:upper:]' '[:lower:]')
if [ "$SAFE_TENANT_ID" != "$TENANT_ID" ]; then
    echo -e "${YELLOW}Warning: Tenant ID sanitized from '$TENANT_ID' to '$SAFE_TENANT_ID'${NC}"
    TENANT_ID=$SAFE_TENANT_ID
fi

echo -e "${BLUE}Deploying tenant: $TENANT_ID${NC}"

# Calculate ports
BACKEND_PORT=$((8000 + PORT_OFFSET))
FRONTEND_PORT=$((3000 + PORT_OFFSET))
REDIS_DB=$((1 + PORT_OFFSET))

echo -e "${BLUE}Service ports:${NC}"
echo "  Backend API: $BACKEND_PORT"
echo "  Frontend: $FRONTEND_PORT"
echo "  Redis DB: $REDIS_DB"

# Create tenant directories
echo -e "${BLUE}Creating tenant directories...${NC}"
TENANT_DIR="tenants/$TENANT_ID"
mkdir -p "$TENANT_DIR"/{workflows,data,logs,config}

# Create tenant-specific environment file
echo -e "${BLUE}Creating environment configuration...${NC}"
cat > "$TENANT_DIR/config/.env" << EOF
# Tenant: $TENANT_ID
TENANT_ID=$TENANT_ID
BACKEND_PORT=$BACKEND_PORT
FRONTEND_PORT=$FRONTEND_PORT
REDIS_DB=$REDIS_DB
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
SECRET_KEY=$(openssl rand -hex 32)
DOMAIN=$DOMAIN
EOF

# Create PostgreSQL schema
echo -e "${BLUE}Creating PostgreSQL schema...${NC}"
export PGPASSWORD=$POSTGRES_PASSWORD
psql -h localhost -U kailash -d kailash_studio << EOF
-- Create schema for tenant
CREATE SCHEMA IF NOT EXISTS tenant_$TENANT_ID;

-- Create tables
CREATE TABLE IF NOT EXISTS tenant_$TENANT_ID.workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    definition JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS tenant_$TENANT_ID.executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID REFERENCES tenant_$TENANT_ID.workflows(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    result JSONB,
    logs TEXT
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_workflows_name ON tenant_$TENANT_ID.workflows(name);
CREATE INDEX IF NOT EXISTS idx_executions_workflow ON tenant_$TENANT_ID.executions(workflow_id);
CREATE INDEX IF NOT EXISTS idx_executions_status ON tenant_$TENANT_ID.executions(status);

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA tenant_$TENANT_ID TO kailash;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA tenant_$TENANT_ID TO kailash;
EOF

# Create docker-compose override for tenant
echo -e "${BLUE}Creating Docker Compose configuration...${NC}"
cat > "$TENANT_DIR/docker-compose.yml" << EOF
version: '3.8'

services:
  ${TENANT_ID}-backend:
    extends:
      file: ../../docker/docker-compose.studio.yml
      service: studio-backend
    container_name: kailash-${TENANT_ID}-backend
    environment:
      - TENANT_ID=$TENANT_ID
      - DATABASE_URL=postgresql://kailash:$POSTGRES_PASSWORD@postgres:5432/kailash_studio
      - REDIS_URL=redis://redis:6379/$REDIS_DB
    volumes:
      - ./workflows:/app/workflows
      - ./data:/app/data
      - ./logs:/app/logs
    ports:
      - "$BACKEND_PORT:8000"
    networks:
      - kailash-studio-network

  ${TENANT_ID}-frontend:
    extends:
      file: ../../docker/docker-compose.studio.yml
      service: studio-frontend
    container_name: kailash-${TENANT_ID}-frontend
    build:
      args:
        - REACT_APP_API_URL=http://localhost:$BACKEND_PORT
        - REACT_APP_TENANT_ID=$TENANT_ID
    ports:
      - "$FRONTEND_PORT:80"
    networks:
      - kailash-studio-network

networks:
  kailash-studio-network:
    external: true
EOF

# Create nginx configuration if domain is provided
if [ -n "$DOMAIN" ]; then
    echo -e "${BLUE}Creating nginx configuration for $DOMAIN...${NC}"
    cat > "docker/nginx/conf.d/${TENANT_ID}.conf" << EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://${TENANT_ID}-frontend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /api {
        proxy_pass http://${TENANT_ID}-backend:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /ws {
        proxy_pass http://${TENANT_ID}-backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF
fi

# Start the tenant services
echo -e "${BLUE}Starting tenant services...${NC}"
cd "$TENANT_DIR"
docker-compose up -d

# Wait for services to be ready
echo -e "${BLUE}Waiting for services to be ready...${NC}"
sleep 10

# Check service health
echo -e "${BLUE}Checking service health...${NC}"
if curl -f "http://localhost:$BACKEND_PORT/health" > /dev/null 2>&1; then
    echo -e "${GREEN}Backend API is healthy${NC}"
else
    echo -e "${RED}Backend API health check failed${NC}"
fi

if curl -f "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1; then
    echo -e "${GREEN}Frontend is healthy${NC}"
else
    echo -e "${RED}Frontend health check failed${NC}"
fi

echo -e "${GREEN}Tenant deployment complete!${NC}"
echo -e "${BLUE}Access URLs:${NC}"
echo "  Frontend: http://localhost:$FRONTEND_PORT"
echo "  Backend API: http://localhost:$BACKEND_PORT"
if [ -n "$DOMAIN" ]; then
    echo "  Domain: http://$DOMAIN"
fi
echo -e "${BLUE}Tenant ID: $TENANT_ID${NC}"
