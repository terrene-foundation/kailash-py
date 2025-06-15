#!/bin/bash
# Start Kailash Workflow Studio in development mode (Backend + Frontend)
# This script launches both services and manages them properly

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BACKEND_PORT=${BACKEND_PORT:-8000}
FRONTEND_PORT=${FRONTEND_PORT:-3000}
TENANT_ID=${TENANT_ID:-default}

# Get the project root directory
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo -e "${BLUE}🚀 Starting Kailash Workflow Studio${NC}"
echo -e "${BLUE}=================================${NC}"

# Function to check if port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to kill process on port
kill_port() {
    local port=$1
    if check_port $port; then
        echo -e "${YELLOW}Port $port is in use. Killing existing process...${NC}"
        lsof -ti:$port | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
}

# Clean up any existing processes
echo -e "${BLUE}🧹 Cleaning up existing processes...${NC}"
kill_port $BACKEND_PORT
kill_port $FRONTEND_PORT

# Function to cleanup on exit
cleanup() {
    echo -e "\n${BLUE}🛑 Shutting down services...${NC}"

    # Kill backend process
    if [[ ! -z "$BACKEND_PID" ]]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi

    # Kill frontend process
    if [[ ! -z "$FRONTEND_PID" ]]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi

    # Clean up any orphaned processes
    pkill -f "python -m kailash.api.studio" 2>/dev/null || true
    pkill -f "npm run dev" 2>/dev/null || true

    echo -e "${GREEN}✅ Shutdown complete${NC}"
    exit 0
}

# Set trap to cleanup on script exit
trap cleanup EXIT INT TERM

# Start Backend API
echo -e "\n${BLUE}🔧 Starting Backend API...${NC}"
cd "$PROJECT_ROOT"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install/update Python dependencies
echo -e "${BLUE}📦 Installing Python dependencies...${NC}"
pip install -e . >/dev/null 2>&1
pip install fastapi uvicorn websockets sqlalchemy httpx pyjwt passlib bcrypt >/dev/null 2>&1

# Start backend with proper error handling
echo -e "${BLUE}🚀 Launching backend on port $BACKEND_PORT...${NC}"
TENANT_ID=$TENANT_ID python -m kailash.api.studio --port $BACKEND_PORT 2>&1 | while IFS= read -r line; do
    echo -e "${GREEN}[BACKEND]${NC} $line"
done &
BACKEND_PID=$!

# Wait for backend to start
echo -e "${BLUE}⏳ Waiting for backend to start...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:$BACKEND_PORT/health >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Backend is ready!${NC}"
        break
    fi
    sleep 1
done

# Start Frontend
echo -e "\n${BLUE}🎨 Starting Frontend...${NC}"
cd "$PROJECT_ROOT/studio"

# Install frontend dependencies if needed
if [ ! -d "node_modules" ]; then
    echo -e "${BLUE}📦 Installing frontend dependencies...${NC}"
    npm install
fi

# Start frontend dev server
echo -e "${BLUE}🚀 Launching frontend on port $FRONTEND_PORT...${NC}"
VITE_BACKEND_URL=http://localhost:$BACKEND_PORT npm run dev 2>&1 | while IFS= read -r line; do
    echo -e "${GREEN}[FRONTEND]${NC} $line"
done &
FRONTEND_PID=$!

# Wait for frontend to start
echo -e "${BLUE}⏳ Waiting for frontend to start...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:$FRONTEND_PORT >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Frontend is ready!${NC}"
        break
    fi
    sleep 1
done

# Display success message
echo -e "\n${GREEN}🎉 Kailash Workflow Studio is running!${NC}"
echo -e "${GREEN}====================================${NC}"
echo -e "${BLUE}📡 Backend API:${NC} http://localhost:$BACKEND_PORT"
echo -e "${BLUE}🖥️  Frontend UI:${NC} http://localhost:$FRONTEND_PORT"
echo -e "${BLUE}📚 API Docs:${NC}    http://localhost:$BACKEND_PORT/docs"
echo -e "${BLUE}🏢 Tenant ID:${NC}   $TENANT_ID"
echo -e "\n${YELLOW}Press Ctrl+C to stop all services${NC}"

# Keep script running
wait
