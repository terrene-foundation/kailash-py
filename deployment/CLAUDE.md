# Enterprise Deployment Guide for Claude Code

This guide provides step-by-step instructions for Claude Code to deploy the complete Kailash enterprise infrastructure.

## 🚀 Quick Deployment Commands

### Local Testing
```bash
cd deployment/local
docker-compose -f docker-compose.simple.yml up -d
./test-security-features.sh
```

### Cloud Production Deployment
```bash
# AWS EKS
cd deployment/terraform/aws
terraform apply -var-file=environments/prod.tfvars
aws eks update-kubeconfig --name $(terraform output -raw cluster_name)

# GCP GKE  
cd deployment/terraform/gcp
terraform apply -var-file=environments/prod.tfvars
gcloud container clusters get-credentials $(terraform output -raw cluster_name) --location $(terraform output -raw cluster_location)

# Azure AKS
cd deployment/terraform/azure
terraform apply -var-file=environments/prod.tfvars
az aks get-credentials --resource-group $(terraform output -raw resource_group_name) --name $(terraform output -raw aks_cluster_name)
```

### Enterprise Stack Deployment
```bash
# Deploy complete enterprise infrastructure
kubectl apply -k deployment/

# Verify deployment
kubectl get pods --all-namespaces | grep -v Running
```

## 📋 Deployment Sequence

When asked to deploy enterprise infrastructure, follow this sequence:

```bash
# 1. Infrastructure
cd deployment/terraform/aws && terraform apply -var-file=environments/prod.tfvars

# 2. Configure kubectl
aws eks update-kubeconfig --name $(terraform output -raw cluster_name)

# 3. Security baseline
kubectl apply -k deployment/security/

# 4. Monitoring stack
kubectl apply -k deployment/monitoring/

# 5. Logging stack (ELK)
kubectl create -f https://download.elastic.co/downloads/eck/2.10.0/crds.yaml
kubectl apply -f https://download.elastic.co/downloads/eck/2.10.0/operator.yaml
kubectl apply -k deployment/monitoring/elk/

# 6. Distributed tracing
kubectl create namespace observability
kubectl create -f https://github.com/jaegertracing/jaeger-operator/releases/download/v1.52.0/jaeger-operator.yaml -n observability
kubectl apply -k deployment/monitoring/tracing/

# 7. Backup and Disaster Recovery
kubectl apply -k deployment/backup/

# 8. Ingress & SSL
helm install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml

# 9. Secrets management
helm install vault hashicorp/vault -n vault-system --create-namespace

# 10. Application
kubectl apply -k deployment/kubernetes/app/
```

## 🔍 Validation Commands

After deployment, validate with these commands:

```bash
# Check cluster health
kubectl get nodes && kubectl get pods --all-namespaces | grep -v Running

# Check security
kubectl get networkpolicies --all-namespaces && kubectl get secrets -A | grep Opaque

# Check monitoring & observability
curl -s localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'
curl -k -u elastic:PASSWORD https://localhost:9200/_cluster/health
curl localhost:16686/api/services

# Check backup
velero backup get && velero backup-location get
```

## 🚨 Troubleshooting

### Common Issues
1. **Pods not starting**: `kubectl describe pod POD_NAME -n NAMESPACE && kubectl logs POD_NAME -n NAMESPACE`
2. **Monitoring issues**: `kubectl get servicemonitor -A --show-labels | grep prometheus`
3. **Logging issues**: `kubectl get elasticsearch -n logging && kubectl logs daemonset/filebeat -n logging`
4. **Backup issues**: `velero backup get | grep -v Completed && kubectl logs deployment/velero -n velero`

### Access Services Locally
```bash
# Port-forward to access services
kubectl port-forward -n monitoring svc/prometheus 9090:9090 &
kubectl port-forward -n monitoring svc/grafana 3000:3000 &
kubectl port-forward -n logging svc/kailash-kibana-kb-http 5601:5601 &
kubectl port-forward -n tracing svc/kailash-jaeger-query 16686:16686 &

echo "Prometheus: http://localhost:9090"
echo "Grafana: http://localhost:3000" 
echo "Kibana: http://localhost:5601"
echo "Jaeger: http://localhost:16686"
```

## 📚 Detailed Guides

For comprehensive information, see these specialized guides:

- **[Security Guide](security/README.md)** - CIS benchmarks, network policies, compliance
- **[Monitoring Guide](monitoring/README.md)** - Prometheus, Grafana, alerting setup
- **[Logging Guide](monitoring/elk/README.md)** - ELK stack configuration and operations
- **[Backup Guide](backup/README.md)** - Velero backup and disaster recovery
- **[CI/CD Guide](cicd/README.md)** - Pipeline setup and automation
- **[Compliance Guide](compliance/README.md)** - SOC2, HIPAA, ISO27001 controls

## ⚡ Emergency Procedures

### Disaster Recovery
```bash
# Use the disaster recovery script
./deployment/backup/scripts/manual-recovery.sh list-backups
./deployment/backup/scripts/manual-recovery.sh restore-namespace <backup-name> <namespace>
./deployment/backup/scripts/manual-recovery.sh emergency-backup
```

### Quick Fixes
```bash
# Restart failed pods
kubectl delete pod -l app=APPLICATION_NAME -n NAMESPACE

# Scale applications
kubectl scale deployment APPLICATION_NAME --replicas=3 -n NAMESPACE

# Check resource usage
kubectl top nodes && kubectl top pods --all-namespaces
```

This guide focuses on **essential commands** for Claude Code. Detailed implementation information is in the specialized guides linked above.