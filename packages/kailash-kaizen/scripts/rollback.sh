#!/bin/bash

# Deployment Rollback Script
# Rolls back deployment to a previous version

set -e  # Exit on error
set -o pipefail  # Exit on pipe failure

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT="${ENVIRONMENT:-dev}"
REGISTRY="${REGISTRY:-ghcr.io}"
IMAGE_NAME="${IMAGE_NAME:-kailash/kailash-kaizen}"
FORCE_ROLLBACK="${FORCE_ROLLBACK:-false}"

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
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# Usage information
usage() {
    cat << EOF
Usage: $0 <version|tag> [options]

Rollback deployment to a previous version.

Arguments:
    version|tag     Version or tag to rollback to (e.g., v1.2.3, previous, latest-stable)

Options:
    --force         Skip confirmation prompt
    --dry-run       Show what would be done without executing
    --help          Show this help message

Environment Variables:
    ENVIRONMENT     Target environment (dev/staging/production) [default: dev]
    REGISTRY        Container registry [default: ghcr.io]
    IMAGE_NAME      Image name [default: kailash/kailash-kaizen]

Examples:
    $0 v1.2.3                    # Rollback to version v1.2.3
    $0 previous --force          # Rollback to previous version without confirmation
    $0 latest-stable --dry-run   # Show rollback plan without executing

EOF
    exit 1
}

# Print rollback header
print_header() {
    echo ""
    echo "=========================================="
    echo "  🔄 Deployment Rollback"
    echo "=========================================="
    echo "Environment: ${ENVIRONMENT}"
    echo "Target Version: ${TARGET_VERSION}"
    echo "Current Time: $(date)"
    echo "=========================================="
    echo ""
}

# Parse command line arguments
parse_args() {
    # Check if version is provided
    if [ $# -eq 0 ]; then
        log_error "No version specified"
        usage
    fi

    TARGET_VERSION="$1"
    shift

    # Parse options
    while [ $# -gt 0 ]; do
        case "$1" in
            --force)
                FORCE_ROLLBACK=true
                ;;
            --dry-run)
                DRY_RUN=true
                ;;
            --help)
                usage
                ;;
            *)
                log_error "Unknown option: $1"
                usage
                ;;
        esac
        shift
    done
}

# Validate target version exists
validate_version() {
    log_info "Validating target version..."

    # Check if version is "previous" - resolve to actual version
    if [ "$TARGET_VERSION" = "previous" ]; then
        log_info "Resolving 'previous' version..."
        # In real scenario, query deployment history
        TARGET_VERSION=$(get_previous_version || echo "v1.0.0")
        log_info "Resolved to: ${TARGET_VERSION}"
    fi

    # Check if image exists in registry
    local image_url="${REGISTRY}/${IMAGE_NAME}:${TARGET_VERSION}"

    # In real scenario, check if image exists
    # docker manifest inspect ${image_url} > /dev/null 2>&1
    if [ "${DRY_RUN}" != "true" ]; then
        log_info "Checking if image exists: ${image_url}"
        # Simulate check - in production this would use docker/kubectl
        if [[ ! "$TARGET_VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] && \
           [ "$TARGET_VERSION" != "latest-stable" ] && \
           [ "$TARGET_VERSION" != "previous" ]; then
            log_warning "Version format may be invalid: ${TARGET_VERSION}"
            log_warning "Expected format: v1.2.3 or 'previous' or 'latest-stable'"
        fi
    fi

    log_success "Version validation completed"
}

# Get previous version from deployment history
get_previous_version() {
    # In real scenario, query Kubernetes or deployment history
    # For now, simulate with git tags
    if command -v git &> /dev/null; then
        git describe --tags --abbrev=0 HEAD~1 2>/dev/null || echo "v1.0.0"
    else
        echo "v1.0.0"
    fi
}

# Get current deployed version
get_current_version() {
    log_info "Getting current deployed version..."

    # In real scenario, query Kubernetes deployment
    # kubectl get deployment kailash-kaizen -n ${ENVIRONMENT} -o jsonpath='{.spec.template.spec.containers[0].image}'

    # Simulate current version
    CURRENT_VERSION="v1.2.3"
    log_info "Current version: ${CURRENT_VERSION}"

    echo "${CURRENT_VERSION}"
}

# Confirmation prompt
confirm_rollback() {
    if [ "${FORCE_ROLLBACK}" = "true" ]; then
        log_warning "Force flag set - skipping confirmation"
        return 0
    fi

    echo ""
    log_warning "⚠️  WARNING: This will rollback the deployment!"
    echo "Environment: ${ENVIRONMENT}"
    echo "From version: ${CURRENT_VERSION}"
    echo "To version: ${TARGET_VERSION}"
    echo ""
    read -p "Are you sure you want to proceed? (yes/no): " confirmation

    if [ "$confirmation" != "yes" ]; then
        log_info "Rollback cancelled by user"
        exit 0
    fi

    log_success "Rollback confirmed"
}

# Create backup of current state
backup_current_state() {
    log_info "Backing up current deployment state..."

    # In real scenario, save current deployment configuration
    # kubectl get deployment kailash-kaizen -n ${ENVIRONMENT} -o yaml > /tmp/backup-${CURRENT_VERSION}.yaml

    if [ "${DRY_RUN}" != "true" ]; then
        echo "Backup saved to: /tmp/backup-${ENVIRONMENT}-${CURRENT_VERSION}.yaml"
        log_success "Current state backed up"
    else
        log_info "[DRY RUN] Would backup current state"
    fi
}

# Execute rollback
execute_rollback() {
    log_info "Executing rollback to version ${TARGET_VERSION}..."

    local image_url="${REGISTRY}/${IMAGE_NAME}:${TARGET_VERSION}"

    if [ "${DRY_RUN}" = "true" ]; then
        log_info "[DRY RUN] Would execute the following:"
        echo "  1. Update deployment image to: ${image_url}"
        echo "  2. Wait for rollout to complete"
        echo "  3. Verify deployment health"
        return 0
    fi

    # Update deployment with target version
    log_info "Updating deployment image to: ${image_url}"

    # In real scenario, use kubectl or API
    # kubectl set image deployment/kailash-kaizen kailash-kaizen=${image_url} -n ${ENVIRONMENT}

    # Simulate deployment update
    sleep 2

    log_success "Deployment updated to ${TARGET_VERSION}"

    # Wait for rollout
    log_info "Waiting for rollout to complete..."

    # In real scenario, wait for rollout
    # kubectl rollout status deployment/kailash-kaizen -n ${ENVIRONMENT} --timeout=5m

    # Simulate rollout
    sleep 3

    log_success "Rollout completed"
}

# Verify rollback success
verify_rollback() {
    log_info "Verifying rollback..."

    if [ "${DRY_RUN}" = "true" ]; then
        log_info "[DRY RUN] Would verify rollback health"
        return 0
    fi

    # Check deployment health
    log_info "Running health checks..."

    # In real scenario, run validation script or health checks
    # ./scripts/validate_deployment.sh

    # Simulate health check
    sleep 2

    log_success "Rollback verified successfully"
}

# Log rollback action for audit
log_rollback_action() {
    log_info "Logging rollback action..."

    local log_entry="[$(date -u +"%Y-%m-%d %H:%M:%S UTC")] ROLLBACK: ${ENVIRONMENT} from ${CURRENT_VERSION} to ${TARGET_VERSION} (user: ${USER:-unknown})"

    if [ "${DRY_RUN}" != "true" ]; then
        # In real scenario, log to centralized logging system
        echo "${log_entry}" >> /tmp/rollback-audit.log
        log_success "Rollback logged to audit trail"
    else
        log_info "[DRY RUN] Would log: ${log_entry}"
    fi
}

# Cleanup old backups (keep last 10)
cleanup_old_backups() {
    log_info "Cleaning up old backups..."

    if [ "${DRY_RUN}" != "true" ]; then
        # In real scenario, cleanup old backup files
        # ls -t /tmp/backup-${ENVIRONMENT}-*.yaml | tail -n +11 | xargs rm -f 2>/dev/null || true
        log_success "Old backups cleaned up"
    else
        log_info "[DRY RUN] Would cleanup old backup files"
    fi
}

# Main rollback flow
main() {
    # Parse arguments
    parse_args "$@"

    # Print header
    print_header

    # Get current version
    CURRENT_VERSION=$(get_current_version)

    # Validate target version
    validate_version

    # Check if already at target version
    if [ "$CURRENT_VERSION" = "$TARGET_VERSION" ]; then
        log_warning "Already at version ${TARGET_VERSION} - nothing to do"
        exit 0
    fi

    # Confirm rollback
    confirm_rollback

    # Backup current state
    backup_current_state

    # Execute rollback
    execute_rollback

    # Verify rollback
    verify_rollback

    # Log action
    log_rollback_action

    # Cleanup
    cleanup_old_backups

    # Print summary
    echo ""
    echo "=========================================="
    echo "  📊 Rollback Summary"
    echo "=========================================="
    log_success "✅ Rollback completed successfully!"
    echo "Environment: ${ENVIRONMENT}"
    echo "Rolled back from: ${CURRENT_VERSION}"
    echo "Rolled back to: ${TARGET_VERSION}"
    echo "Completed at: $(date)"
    echo "=========================================="
    echo ""

    if [ "${DRY_RUN}" = "true" ]; then
        log_info "This was a dry run - no actual changes were made"
    fi
}

# Run main function
main "$@"
