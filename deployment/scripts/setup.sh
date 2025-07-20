#!/bin/bash
# Setup script for Kailash SDK Template deployment
# Aligned with test infrastructure and deployment patterns

set -euo pipefail

# Variables
PROJECT_NAME="$(basename "$(pwd)")"
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"
ENVIRONMENT="development"
CLEANUP="false"
FORCE="false"
SKIP_MODELS="false"
CUSTOM_BASE_PORT=""
VERBOSE="false"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show help
show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy Kailash SDK Template with Docker infrastructure.

Options:
    -e, --environment ENV    Environment to deploy (development|production) [default: development]
    -c, --cleanup           Clean up existing containers before deploying
    -f, --force             Force deployment even if containers exist
    -s, --skip-models       Skip Ollama model downloads
    -p, --custom-base-port  Custom base port for services
    -v, --verbose           Enable verbose logging
    -h, --help              Show this help message

Examples:
    $0                                    # Deploy development environment
    $0 -e production                      # Deploy production environment
    $0 -e development -c                  # Clean up and deploy development
    $0 -e production -f                   # Force production deployment
    $0 -p 7000                           # Use custom base port 7000
    $0 -c -s                             # Clean up and skip model downloads

Environment Files:
    The script will look for environment files in the following order:
    1. deployment/docker/.env.{environment}
    2. deployment/docker/.env.example (as fallback)

Port Configuration:
    Ports are automatically allocated based on project name hash.
    Use -p to override with custom base port.

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -c|--cleanup)
            CLEANUP="true"
            shift
            ;;
        -f|--force)
            FORCE="true"
            shift
            ;;
        -s|--skip-models)
            SKIP_MODELS="true"
            shift
            ;;
        -p|--custom-base-port)
            CUSTOM_BASE_PORT="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE="true"
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Validate environment
if [[ "$ENVIRONMENT" != "development" && "$ENVIRONMENT" != "production" ]]; then
    log_error "Invalid environment: $ENVIRONMENT. Must be 'development' or 'production'."
    exit 1
fi

# Enable verbose logging if requested
if [[ "$VERBOSE" == "true" ]]; then
    set -x
fi

log_info "Starting deployment setup for $PROJECT_NAME in $ENVIRONMENT environment"

# Check for required tools
check_requirements() {
    log_info "Checking requirements..."
    
    local missing_tools=()
    
    if ! command -v docker &> /dev/null; then
        missing_tools+=("docker")
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        missing_tools+=("docker-compose")
    fi
    
    if ! command -v curl &> /dev/null; then
        missing_tools+=("curl")
    fi
    
    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        log_error "Please install them and try again."
        exit 1
    fi
    
    log_success "All requirements satisfied"
}

# Setup port configuration
setup_ports() {
    log_info "Setting up port configuration..."
    
    # Use tests/utils setup if available
    if [[ -f "$ROOT_DIR/tests/utils/setup_local_docker.py" ]]; then
        cd "$ROOT_DIR"
        
        local setup_args=()
        if [[ -n "$CUSTOM_BASE_PORT" ]]; then
            setup_args+=("--custom-base-port" "$CUSTOM_BASE_PORT")
        fi
        
        if [[ "$CLEANUP" == "true" ]]; then
            setup_args+=("--cleanup")
        fi
        
        python tests/utils/setup_local_docker.py "${setup_args[@]}"
        
        cd "$DEPLOY_DIR"
        log_success "Port configuration completed"
    else
        log_warning "Port configuration script not found, using default ports"
    fi
}

# Setup environment file
setup_env_file() {
    log_info "Setting up environment file..."
    
    local env_file="$DEPLOY_DIR/docker/.env.$ENVIRONMENT"
    local example_file="$DEPLOY_DIR/docker/.env.example"
    
    if [[ ! -f "$env_file" ]]; then
        if [[ -f "$example_file" ]]; then
            log_info "Creating environment file from example: $env_file"
            cp "$example_file" "$env_file"
            
            # Update project name
            sed -i.bak "s/PROJECT_NAME=template/PROJECT_NAME=$PROJECT_NAME/g" "$env_file"
            rm "$env_file.bak"
            
            log_warning "Please edit $env_file with your configuration values"
        else
            log_error "Environment file not found: $env_file"
            log_error "Please create it or run with --help for guidance"
            exit 1
        fi
    fi
    
    log_success "Environment file ready: $env_file"
}

# Cleanup existing containers
cleanup_containers() {
    if [[ "$CLEANUP" == "true" ]]; then
        log_info "Cleaning up existing containers..."
        
        cd "$DEPLOY_DIR/docker"
        
        # Try to stop and remove containers
        docker-compose -f "docker-compose.$ENVIRONMENT.yml" down --remove-orphans --volumes || true
        
        # Remove any dangling containers with our project name
        docker ps -a --filter "name=$PROJECT_NAME" --format "{{.Names}}" | xargs -r docker rm -f || true
        
        # Prune unused networks
        docker network prune -f || true
        
        log_success "Cleanup completed"
    fi
}

# Deploy services
deploy_services() {
    log_info "Deploying services..."
    
    cd "$DEPLOY_DIR/docker"
    
    # Check if containers are already running
    if docker-compose -f "docker-compose.$ENVIRONMENT.yml" ps --services --filter "status=running" | grep -q .; then
        if [[ "$FORCE" == "true" ]]; then
            log_warning "Forcing deployment despite running containers"
        else
            log_error "Containers are already running. Use --force to override or --cleanup to clean up first."
            exit 1
        fi
    fi
    
    # Deploy with the appropriate compose file
    local compose_file="docker-compose.$ENVIRONMENT.yml"
    
    if [[ ! -f "$compose_file" ]]; then
        log_error "Compose file not found: $compose_file"
        exit 1
    fi
    
    # Load environment variables
    if [[ -f ".env.$ENVIRONMENT" ]]; then
        export $(cat ".env.$ENVIRONMENT" | grep -v '^#' | xargs)
    fi
    
    # Load port configuration from lock file (only valid key=value pairs)
    if [[ -f "$ROOT_DIR/tests/.docker-ports.lock" ]]; then
        while IFS= read -r line; do
            if [[ $line =~ ^[A-Z_]+=[0-9]+$ ]]; then
                export "$line"
            fi
        done < "$ROOT_DIR/tests/.docker-ports.lock"
    fi
    
    # Start services
    log_info "Starting services with $compose_file"
    docker-compose -f "$compose_file" up -d
    
    # Wait for services to be healthy
    log_info "Waiting for services to be healthy..."
    local max_wait=300  # 5 minutes
    local wait_time=0
    
    while [[ $wait_time -lt $max_wait ]]; do
        local running_services=$(docker-compose -f "$compose_file" ps --services --filter "status=running" | wc -l)
        local total_services=$(docker-compose -f "$compose_file" config --services | wc -l)
        
        if [[ $running_services -eq $total_services ]]; then
            break
        fi
        sleep 10
        wait_time=$((wait_time + 10))
        log_info "Waiting for services... (${wait_time}s/${max_wait}s)"
    done
    
    if [[ $wait_time -ge $max_wait ]]; then
        log_error "Services failed to start within $max_wait seconds"
        docker-compose -f "$compose_file" logs --tail=50
        exit 1
    fi
    
    log_success "Services deployed successfully"
}

# Download Ollama models
download_models() {
    if [[ "$SKIP_MODELS" == "true" ]]; then
        log_info "Skipping Ollama model downloads"
        return
    fi
    
    log_info "Downloading Ollama models..."
    
    # Get Ollama port from environment or use default
    local ollama_port="11434"
    if [[ -f "$ROOT_DIR/tests/.docker-ports.lock" ]]; then
        ollama_port=$(grep "OLLAMA_PORT" "$ROOT_DIR/tests/.docker-ports.lock" | cut -d'=' -f2)
    fi
    
    local ollama_url="http://localhost:$ollama_port"
    
    # Wait for Ollama to be available
    local max_wait=180  # 3 minutes
    local wait_time=0
    
    while [[ $wait_time -lt $max_wait ]]; do
        if curl -s "$ollama_url/api/tags" > /dev/null 2>&1; then
            break
        fi
        sleep 5
        wait_time=$((wait_time + 5))
        log_info "Waiting for Ollama... (${wait_time}s/${max_wait}s)"
    done
    
    if [[ $wait_time -ge $max_wait ]]; then
        log_error "Ollama not available after $max_wait seconds"
        return 1
    fi
    
    # Download models
    local models=("llama3.2:1b" "nomic-embed-text")
    
    for model in "${models[@]}"; do
        log_info "Downloading model: $model"
        curl -X POST "$ollama_url/api/pull" \
            -H "Content-Type: application/json" \
            -d "{\"name\": \"$model\"}" \
            --max-time 600 || log_warning "Failed to download model: $model"
    done
    
    log_success "Model downloads completed"
}

# Show status
show_status() {
    log_info "Deployment Status:"
    
    cd "$DEPLOY_DIR/docker"
    
    # Show running containers
    echo
    log_info "Running containers:"
    docker-compose -f "docker-compose.$ENVIRONMENT.yml" ps
    
    # Show access URLs
    echo
    log_info "Access URLs:"
    
    # Get ports from lock file if available
    local app_port="8000"
    local grafana_port="3000"
    local prometheus_port="9090"
    
    if [[ -f "$ROOT_DIR/tests/.docker-ports.lock" ]]; then
        # For development, show actual ports
        if [[ "$ENVIRONMENT" == "development" ]]; then
            echo "  Application:     http://localhost:$app_port"
            echo "  Adminer:         http://localhost:8080"
            echo "  Redis Commander: http://localhost:8081"
            echo "  Grafana:         http://localhost:$grafana_port"
            echo "  Prometheus:      http://localhost:$prometheus_port"
        fi
    else
        # For production, show domain-based URLs
        if [[ "$ENVIRONMENT" == "production" ]]; then
            local domain="localhost"
            if [[ -f ".env.$ENVIRONMENT" ]]; then
                domain=$(grep "DOMAIN=" ".env.$ENVIRONMENT" | cut -d'=' -f2 | head -1)
            fi
            echo "  Application:     https://$domain"
            echo "  Traefik Dashboard: http://localhost:8080"
            echo "  Grafana:         http://localhost:$grafana_port"
            echo "  Prometheus:      http://localhost:$prometheus_port"
        else
            echo "  Application:     http://localhost:$app_port"
            echo "  Grafana:         http://localhost:$grafana_port"
            echo "  Prometheus:      http://localhost:$prometheus_port"
        fi
    fi
    
    echo
    log_success "Deployment completed successfully!"
}

# Main execution
main() {
    check_requirements
    setup_ports
    setup_env_file
    cleanup_containers
    deploy_services
    download_models
    show_status
}

# Run main function
main "$@"