#!/bin/bash
# Start Kailash Workflow Studio (Backend + Frontend)

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting Kailash Workflow Studio...${NC}"

# Check if we're in development or production mode
MODE=${MODE:-development}
TENANT_ID=${TENANT_ID:-default}

if [ "$MODE" = "development" ]; then
    echo -e "${GREEN}Running in development mode${NC}"
    
    # Start backend API
    echo -e "${BLUE}Starting backend API...${NC}"
    cd "$(dirname "$0")/.."
    
    # Install Python dependencies if needed
    if [ ! -d ".venv" ]; then
        echo "Creating virtual environment..."
        python -m venv .venv
    fi
    
    # Activate virtual environment
    source .venv/bin/activate
    
    # Install dependencies
    pip install -e .
    pip install fastapi uvicorn websockets
    
    # Start backend in background
    TENANT_ID=$TENANT_ID python -m kailash.api --port 8000 &
    BACKEND_PID=$!
    
    # Start frontend
    echo -e "${BLUE}Starting frontend...${NC}"
    cd studio
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        echo "Installing frontend dependencies..."
        npm install
    fi
    
    # Start frontend dev server
    REACT_APP_TENANT_ID=$TENANT_ID npm run dev &
    FRONTEND_PID=$!
    
    echo -e "${GREEN}Studio is running!${NC}"
    echo -e "Backend API: http://localhost:8000"
    echo -e "Frontend: http://localhost:3000"
    echo -e "Tenant ID: $TENANT_ID"
    
    # Function to cleanup on exit
    cleanup() {
        echo -e "\n${BLUE}Shutting down...${NC}"
        kill $BACKEND_PID 2>/dev/null || true
        kill $FRONTEND_PID 2>/dev/null || true
        exit 0
    }
    
    # Set trap to cleanup on script exit
    trap cleanup EXIT INT TERM
    
    # Wait for processes
    wait
    
else
    echo -e "${GREEN}Running in production mode${NC}"
    
    # Use Docker Compose for production
    export TENANT_ID
    docker-compose -f docker/docker-compose.studio.yml up
fi