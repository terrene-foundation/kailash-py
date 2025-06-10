#!/bin/bash

# Kailash SDK Environment Setup Script
# This script ensures Docker is installed and sets up the SDK development environment

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}Kailash SDK Environment Setup${NC}"
echo -e "${BLUE}======================================${NC}"
echo

# Function to detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            OS=$ID
            VER=$VERSION_ID
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        VER=$(sw_vers -productVersion)
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        OS="windows"
    else
        OS="unknown"
    fi
    echo $OS
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check Docker installation
check_docker() {
    echo -e "${YELLOW}Checking Docker installation...${NC}"
    
    if command_exists docker; then
        echo -e "${GREEN}✓ Docker is installed${NC}"
        docker --version
        
        # Check if Docker daemon is running
        if docker info >/dev/null 2>&1; then
            echo -e "${GREEN}✓ Docker daemon is running${NC}"
        else
            echo -e "${RED}✗ Docker daemon is not running${NC}"
            echo -e "${YELLOW}Please start Docker and run this script again${NC}"
            exit 1
        fi
        
        # Check Docker Compose
        if docker compose version >/dev/null 2>&1; then
            echo -e "${GREEN}✓ Docker Compose v2 is installed${NC}"
        elif command_exists docker-compose; then
            echo -e "${YELLOW}⚠ Docker Compose v1 detected. Please upgrade to v2${NC}"
        else
            echo -e "${RED}✗ Docker Compose is not installed${NC}"
            return 1
        fi
        
        return 0
    else
        echo -e "${RED}✗ Docker is not installed${NC}"
        return 1
    fi
}

# Function to install Docker on macOS
install_docker_macos() {
    echo -e "${YELLOW}Installing Docker on macOS...${NC}"
    
    if command_exists brew; then
        echo "Using Homebrew to install Docker Desktop..."
        brew install --cask docker
        echo -e "${GREEN}✓ Docker Desktop installed via Homebrew${NC}"
        echo -e "${YELLOW}Please start Docker Desktop from Applications${NC}"
    else
        echo "Homebrew not found. Downloading Docker Desktop..."
        ARCH=$(uname -m)
        if [[ "$ARCH" == "arm64" ]]; then
            DMG_URL="https://desktop.docker.com/mac/main/arm64/Docker.dmg"
        else
            DMG_URL="https://desktop.docker.com/mac/main/amd64/Docker.dmg"
        fi
        
        curl -o ~/Downloads/Docker.dmg "$DMG_URL"
        echo -e "${GREEN}✓ Docker Desktop downloaded to ~/Downloads/Docker.dmg${NC}"
        echo -e "${YELLOW}Please install Docker.dmg and start Docker Desktop${NC}"
        open ~/Downloads/
    fi
}

# Function to install Docker on Linux
install_docker_linux() {
    echo -e "${YELLOW}Installing Docker on Linux...${NC}"
    
    # Use official Docker installation script
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    
    # Add user to docker group
    sudo usermod -aG docker $USER
    
    # Install Docker Compose plugin
    sudo apt-get update
    sudo apt-get install docker-compose-plugin
    
    rm get-docker.sh
    
    echo -e "${GREEN}✓ Docker installed successfully${NC}"
    echo -e "${YELLOW}Please log out and back in for group changes to take effect${NC}"
}

# Function to install Docker on Windows
install_docker_windows() {
    echo -e "${YELLOW}Docker installation on Windows${NC}"
    echo
    echo "Please install Docker Desktop for Windows manually:"
    echo "1. Ensure WSL2 is enabled"
    echo "2. Download Docker Desktop from: https://www.docker.com/products/docker-desktop"
    echo "3. Install and start Docker Desktop"
    echo "4. Re-run this script after installation"
}

# Function to setup SDK environment
setup_sdk_environment() {
    echo -e "${YELLOW}Setting up SDK development environment...${NC}"
    
    cd "$PROJECT_ROOT/docker"
    
    # Create .env file if it doesn't exist
    if [ ! -f "$PROJECT_ROOT/sdk-users/.env.sdk-dev" ]; then
        echo "Creating environment configuration..."
        cat > "$PROJECT_ROOT/sdk-users/.env.sdk-dev" << EOF
# SDK Development Environment Configuration
SDK_DEV_MODE=true

# PostgreSQL
POSTGRES_PASSWORD=kailash123
TRANSACTION_DB=postgresql://kailash:kailash123@localhost:5432/transactions
COMPLIANCE_DB=postgresql://kailash:kailash123@localhost:5432/compliance
ANALYTICS_DB=postgresql://kailash:kailash123@localhost:5432/analytics
CRM_DB=postgresql://kailash:kailash123@localhost:5432/crm
MARKETING_DB=postgresql://kailash:kailash123@localhost:5432/marketing
REPORTS_DB=postgresql://kailash:kailash123@localhost:5432/reports

# MongoDB
MONGO_USERNAME=kailash
MONGO_PASSWORD=kailash123
MONGO_URL=mongodb://kailash:kailash123@localhost:27017/kailash

# Kafka
KAFKA_BROKERS=localhost:9092

# APIs
WEBHOOK_API=http://localhost:8888
FRAUD_ALERT_API=http://localhost:8888
NOTIFICATION_API=http://localhost:8888
ENRICHMENT_API=http://localhost:8888

# LLM
OLLAMA_HOST=http://localhost:11434

# MCP
MCP_SERVER_URL=http://localhost:8765
EOF
        echo -e "${GREEN}✓ Environment configuration created${NC}"
    fi
    
    # Start services
    echo -e "${YELLOW}Starting SDK development services...${NC}"
    docker compose -f docker-compose.sdk-dev.yml up -d
    
    # Wait for services to be healthy
    echo -e "${YELLOW}Waiting for services to be ready...${NC}"
    sleep 10
    
    # Check service health
    if curl -s http://localhost:8889/health >/dev/null 2>&1; then
        echo -e "${GREEN}✓ All services are healthy${NC}"
    else
        echo -e "${YELLOW}⚠ Some services may still be starting up${NC}"
    fi
    
    echo
    echo -e "${GREEN}SDK Development Environment is ready!${NC}"
    echo
    echo "Services available at:"
    echo "  PostgreSQL:      localhost:5432"
    echo "  MongoDB:         localhost:27017"
    echo "  MongoDB Express: http://localhost:8081"
    echo "  Qdrant:          http://localhost:6333"
    echo "  Kafka:           localhost:9092"
    echo "  Kafka UI:        http://localhost:8082"
    echo "  Ollama:          http://localhost:11434"
    echo "  Mock API:        http://localhost:8888"
    echo "  MCP Server:      http://localhost:8765"
    echo
}

# Function to show menu
show_menu() {
    echo "Choose installation level:"
    echo "1. Full (Docker + all services) - Recommended"
    echo "2. Check only (See what's installed)"
    echo "3. No Docker (Alternative setup guide)"
    echo "4. Start SDK services (if Docker already installed)"
    echo "5. Stop SDK services"
    echo "6. Reset SDK services (clean data)"
    echo "0. Exit"
    echo
    read -p "Enter your choice [1-6]: " choice
}

# Main execution
main() {
    OS=$(detect_os)
    echo "Detected OS: $OS"
    echo
    
    while true; do
        show_menu
        
        case $choice in
            1)
                if check_docker; then
                    echo -e "${GREEN}Docker is already installed${NC}"
                else
                    case $OS in
                        macos)
                            install_docker_macos
                            ;;
                        ubuntu|debian|fedora|centos)
                            install_docker_linux
                            ;;
                        windows)
                            install_docker_windows
                            ;;
                        *)
                            echo -e "${RED}Unsupported OS: $OS${NC}"
                            echo "Please install Docker manually from https://www.docker.com"
                            exit 1
                            ;;
                    esac
                fi
                
                if check_docker; then
                    setup_sdk_environment
                fi
                ;;
            2)
                check_docker
                ;;
            3)
                echo -e "${YELLOW}Alternative Setup Without Docker${NC}"
                echo "See: $PROJECT_ROOT/sdk-users/INFRASTRUCTURE_NO_DOCKER.md"
                ;;
            4)
                if check_docker; then
                    setup_sdk_environment
                else
                    echo -e "${RED}Docker is not installed. Please choose option 1 first.${NC}"
                fi
                ;;
            5)
                echo -e "${YELLOW}Stopping SDK services...${NC}"
                cd "$PROJECT_ROOT/docker"
                docker compose -f docker-compose.sdk-dev.yml down
                echo -e "${GREEN}✓ Services stopped${NC}"
                ;;
            6)
                echo -e "${YELLOW}Resetting SDK services...${NC}"
                cd "$PROJECT_ROOT/docker"
                docker compose -f docker-compose.sdk-dev.yml down -v
                echo -e "${GREEN}✓ Services reset (all data cleared)${NC}"
                ;;
            0)
                echo "Exiting..."
                exit 0
                ;;
            *)
                echo -e "${RED}Invalid choice. Please try again.${NC}"
                ;;
        esac
        
        echo
        read -p "Press Enter to continue..."
        echo
    done
}

# Run main function
main