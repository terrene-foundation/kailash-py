#!/bin/bash
# Manual disaster recovery script for Kailash platform
# Usage: ./manual-recovery.sh [SCENARIO] [OPTIONS]

set -e

# Configuration
VELERO_NAMESPACE="velero"
BACKUP_BUCKET="kailash-velero-backups"
DR_REGION="us-west-2"
PRIMARY_REGION="us-east-1"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if kubectl is available
    if ! command -v kubectl &> /dev/null; then
        error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    # Check if velero CLI is available
    if ! command -v velero &> /dev/null; then
        error "velero CLI is not installed or not in PATH"
        exit 1
    fi
    
    # Check if AWS CLI is available
    if ! command -v aws &> /dev/null; then
        error "aws CLI is not installed or not in PATH"
        exit 1
    fi
    
    # Check kubectl connectivity
    if ! kubectl cluster-info &> /dev/null; then
        error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    success "Prerequisites check passed"
}

# List available backups
list_backups() {
    log "Listing available backups..."
    
    echo "Recent backups:"
    velero backup get --show-labels | head -20
    
    echo ""
    echo "Backup storage locations:"
    velero backup-location get
}

# Restore namespace from backup
restore_namespace() {
    local backup_name="$1"
    local target_namespace="$2"
    local source_namespace="${3:-$target_namespace}"
    
    if [[ -z "$backup_name" || -z "$target_namespace" ]]; then
        error "Usage: restore_namespace <backup_name> <target_namespace> [source_namespace]"
        return 1
    fi
    
    log "Restoring namespace '$source_namespace' to '$target_namespace' from backup '$backup_name'"
    
    # Create restore name
    local restore_name="restore-${target_namespace}-$(date +%s)"
    
    # Check if target namespace exists, create if not
    if ! kubectl get namespace "$target_namespace" &> /dev/null; then
        log "Creating target namespace: $target_namespace"
        kubectl create namespace "$target_namespace"
    fi
    
    # Create restore
    local restore_cmd="velero restore create $restore_name --from-backup $backup_name"
    
    if [[ "$source_namespace" != "$target_namespace" ]]; then
        restore_cmd="$restore_cmd --namespace-mappings $source_namespace:$target_namespace"
    else
        restore_cmd="$restore_cmd --include-namespaces $source_namespace"
    fi
    
    log "Executing: $restore_cmd"
    eval "$restore_cmd"
    
    # Wait for restore to complete
    log "Waiting for restore to complete..."
    velero restore wait "$restore_name" --timeout=30m
    
    # Check restore status
    local status=$(velero restore get "$restore_name" -o json | jq -r '.status.phase')
    
    if [[ "$status" == "Completed" ]]; then
        success "Restore completed successfully"
        log "Restore details:"
        velero restore describe "$restore_name"
    else
        error "Restore failed with status: $status"
        log "Restore logs:"
        velero restore logs "$restore_name"
        return 1
    fi
}

# Full cluster recovery
full_cluster_recovery() {
    local backup_name="$1"
    local confirm="${2:-false}"
    
    if [[ -z "$backup_name" ]]; then
        error "Usage: full_cluster_recovery <backup_name> [confirm]"
        return 1
    fi
    
    if [[ "$confirm" != "CONFIRM" ]]; then
        warn "This will restore the entire cluster from backup: $backup_name"
        warn "This operation will overwrite existing resources!"
        echo "To proceed, run: $0 full_cluster_recovery $backup_name CONFIRM"
        return 1
    fi
    
    log "Starting full cluster recovery from backup: $backup_name"
    
    # Create restore name
    local restore_name="full-cluster-restore-$(date +%s)"
    
    # Exclude system namespaces and velero itself
    local excluded_namespaces="kube-system,kube-public,kube-node-lease,velero,local-path-storage"
    
    # Create full cluster restore
    log "Creating full cluster restore..."
    velero restore create "$restore_name" \
        --from-backup "$backup_name" \
        --exclude-namespaces "$excluded_namespaces" \
        --include-cluster-resources=true
    
    # Wait for restore to complete
    log "Waiting for restore to complete (this may take a while)..."
    velero restore wait "$restore_name" --timeout=60m
    
    # Check restore status
    local status=$(velero restore get "$restore_name" -o json | jq -r '.status.phase')
    
    if [[ "$status" == "Completed" ]]; then
        success "Full cluster restore completed successfully"
        
        # Validate critical services
        log "Validating critical services..."
        validate_services
        
    else
        error "Full cluster restore failed with status: $status"
        log "Restore logs:"
        velero restore logs "$restore_name"
        return 1
    fi
}

# Cross-region disaster recovery
cross_region_recovery() {
    local backup_name="$1"
    local confirm="${2:-false}"
    
    if [[ -z "$backup_name" ]]; then
        error "Usage: cross_region_recovery <backup_name> [confirm]"
        return 1
    fi
    
    if [[ "$confirm" != "CONFIRM" ]]; then
        warn "This will perform cross-region disaster recovery"
        warn "Make sure you have:"
        warn "1. Provisioned infrastructure in DR region ($DR_REGION)"
        warn "2. Configured cross-region backup replication"
        warn "3. Updated DNS/load balancer configuration"
        echo "To proceed, run: $0 cross_region_recovery $backup_name CONFIRM"
        return 1
    fi
    
    log "Starting cross-region disaster recovery from backup: $backup_name"
    
    # Switch to DR region
    log "Switching to DR region: $DR_REGION"
    export AWS_DEFAULT_REGION="$DR_REGION"
    
    # Update kubeconfig for DR cluster
    local dr_cluster_name="kailash-dr-cluster"
    log "Updating kubeconfig for DR cluster: $dr_cluster_name"
    aws eks update-kubeconfig --region "$DR_REGION" --name "$dr_cluster_name"
    
    # Check if Velero is installed in DR cluster
    if ! kubectl get namespace "$VELERO_NAMESPACE" &> /dev/null; then
        log "Installing Velero in DR cluster..."
        install_velero_dr
    fi
    
    # Configure cross-region backup storage location
    log "Configuring cross-region backup access..."
    kubectl apply -f - <<EOF
apiVersion: velero.io/v1
kind: BackupStorageLocation
metadata:
  name: cross-region-restore
  namespace: $VELERO_NAMESPACE
spec:
  provider: aws
  objectStorage:
    bucket: $BACKUP_BUCKET
    prefix: cross-region
  config:
    region: $PRIMARY_REGION
    serverSideEncryption: AES256
EOF
    
    # Create restore from cross-region backup
    local restore_name="cross-region-restore-$(date +%s)"
    
    log "Creating cross-region restore..."
    velero restore create "$restore_name" \
        --from-backup "$backup_name" \
        --storage-location cross-region-restore \
        --exclude-namespaces "kube-system,kube-public,kube-node-lease,velero"
    
    # Wait for restore to complete
    log "Waiting for cross-region restore to complete..."
    velero restore wait "$restore_name" --timeout=90m
    
    # Validate restore
    local status=$(velero restore get "$restore_name" -o json | jq -r '.status.phase')
    
    if [[ "$status" == "Completed" ]]; then
        success "Cross-region disaster recovery completed successfully"
        
        log "Post-recovery tasks:"
        log "1. Update DNS records to point to DR region"
        log "2. Update load balancer configuration"
        log "3. Verify external integrations"
        log "4. Notify stakeholders of DR activation"
        
        validate_services
        
    else
        error "Cross-region disaster recovery failed with status: $status"
        velero restore logs "$restore_name"
        return 1
    fi
}

# Install Velero in DR cluster
install_velero_dr() {
    log "Installing Velero in DR cluster..."
    
    # Create Velero namespace
    kubectl create namespace "$VELERO_NAMESPACE" || true
    
    # Install Velero with cross-region configuration
    velero install \
        --provider aws \
        --plugins velero/velero-plugin-for-aws:v1.8.2 \
        --bucket "$BACKUP_BUCKET" \
        --backup-location-config region="$PRIMARY_REGION" \
        --snapshot-location-config region="$DR_REGION" \
        --secret-file ./credentials-velero
    
    # Wait for Velero to be ready
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=velero -n "$VELERO_NAMESPACE" --timeout=300s
    
    success "Velero installed successfully in DR cluster"
}

# Validate critical services
validate_services() {
    log "Validating critical services..."
    
    local critical_namespaces=("kailash-app" "monitoring" "logging" "vault-system")
    local validation_failed=false
    
    for namespace in "${critical_namespaces[@]}"; do
        log "Checking namespace: $namespace"
        
        if kubectl get namespace "$namespace" &> /dev/null; then
            local ready_pods=$(kubectl get pods -n "$namespace" --field-selector=status.phase=Running --no-headers | wc -l)
            local total_pods=$(kubectl get pods -n "$namespace" --no-headers | wc -l)
            
            log "  Pods ready: $ready_pods/$total_pods"
            
            if [[ "$ready_pods" -eq 0 ]] && [[ "$total_pods" -gt 0 ]]; then
                error "  No pods running in namespace $namespace"
                validation_failed=true
            fi
        else
            warn "  Namespace $namespace does not exist"
        fi
    done
    
    # Check critical services
    log "Checking critical service endpoints..."
    
    local services=("prometheus" "grafana" "elasticsearch" "jaeger")
    
    for service in "${services[@]}"; do
        if kubectl get service "$service" -A &> /dev/null; then
            success "  Service $service is available"
        else
            warn "  Service $service not found"
        fi
    done
    
    if [[ "$validation_failed" == "true" ]]; then
        error "Service validation failed - manual intervention required"
        return 1
    else
        success "Service validation completed successfully"
    fi
}

# Create emergency backup
emergency_backup() {
    local backup_name="emergency-$(date +%Y%m%d-%H%M%S)"
    
    log "Creating emergency backup: $backup_name"
    
    velero backup create "$backup_name" \
        --include-cluster-resources=true \
        --snapshot-volumes=true \
        --wait
    
    local status=$(velero backup get "$backup_name" -o json | jq -r '.status.phase')
    
    if [[ "$status" == "Completed" ]]; then
        success "Emergency backup completed: $backup_name"
    else
        error "Emergency backup failed with status: $status"
        velero backup logs "$backup_name"
        return 1
    fi
}

# Show recovery status
show_status() {
    log "Current recovery status:"
    
    echo ""
    echo "=== Velero Status ==="
    velero get backup
    echo ""
    velero get restore
    echo ""
    
    echo "=== Cluster Status ==="
    kubectl cluster-info
    echo ""
    
    echo "=== Critical Namespaces ==="
    kubectl get namespaces kailash-app monitoring logging vault-system 2>/dev/null || echo "Some critical namespaces missing"
    echo ""
    
    echo "=== Pod Status ==="
    kubectl get pods --all-namespaces | grep -E "(kailash-app|monitoring|logging|vault-system)" || echo "No critical pods found"
}

# Usage information
usage() {
    cat <<EOF
Kailash Platform Disaster Recovery Script

Usage: $0 <command> [arguments]

Commands:
    list-backups                           List available backups
    restore-namespace <backup> <namespace> [source_ns]  Restore specific namespace
    full-recovery <backup> [CONFIRM]       Full cluster recovery (destructive!)
    cross-region-recovery <backup> [CONFIRM]  Cross-region disaster recovery
    emergency-backup                       Create emergency backup now
    validate                              Validate current system status
    status                                Show current recovery status
    help                                  Show this help message

Examples:
    $0 list-backups
    $0 restore-namespace daily-critical-20240120-020000 kailash-app-test kailash-app
    $0 full-recovery weekly-full-20240120-030000 CONFIRM
    $0 cross-region-recovery monthly-dr-20240101-040000 CONFIRM
    $0 emergency-backup
    $0 validate
    $0 status

Prerequisites:
    - kubectl configured for target cluster
    - velero CLI installed
    - aws CLI configured with appropriate permissions
    - Appropriate IAM roles for Velero operations

EOF
}

# Main script logic
main() {
    local command="$1"
    shift
    
    case "$command" in
        "list-backups")
            check_prerequisites
            list_backups
            ;;
        "restore-namespace")
            check_prerequisites
            restore_namespace "$@"
            ;;
        "full-recovery")
            check_prerequisites
            full_cluster_recovery "$@"
            ;;
        "cross-region-recovery")
            check_prerequisites
            cross_region_recovery "$@"
            ;;
        "emergency-backup")
            check_prerequisites
            emergency_backup
            ;;
        "validate")
            check_prerequisites
            validate_services
            ;;
        "status")
            check_prerequisites
            show_status
            ;;
        "help"|"--help"|"-h"|"")
            usage
            ;;
        *)
            error "Unknown command: $command"
            usage
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"