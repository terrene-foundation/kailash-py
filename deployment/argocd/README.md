# ArgoCD GitOps Deployment

This directory contains ArgoCD application configurations for GitOps-based deployment of the Kailash platform.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          ArgoCD                                  │
│                    (App of Apps Pattern)                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐        ┌──────────────────┐             │
│  │   Root App       │───────▶│  Infrastructure  │             │
│  │ (App of Apps)    │        │   Applications   │             │
│  └──────────────────┘        └──────────────────┘             │
│            │                           │                         │
│            │                           ├─ ingress-nginx         │
│            │                           ├─ cert-manager          │
│            │                           ├─ external-dns          │
│            │                           └─ metrics-server        │
│            │                                                     │
│            ├────────────────▶┌──────────────────┐             │
│            │                 │    Monitoring     │             │
│            │                 │   Applications    │             │
│            │                 └──────────────────┘             │
│            │                          │                         │
│            │                          ├─ prometheus-stack      │
│            │                          ├─ loki                  │
│            │                          ├─ tempo                 │
│            │                          └─ promtail              │
│            │                                                     │
│            └────────────────▶┌──────────────────┐             │
│                              │  Kailash Apps    │             │
│                              │ (Multi-Env)      │             │
│                              └──────────────────┘             │
│                                       │                         │
│                                       ├─ kailash-dev           │
│                                       ├─ kailash-staging       │
│                                       └─ kailash-prod          │
└─────────────────────────────────────────────────────────────────┘
```

## 📁 Directory Structure

```
argocd/
├── README.md                      # This file
├── argocd-app-of-apps.yaml       # Root application
├── applications/                  # Individual applications
│   ├── kailash-app.yaml          # Main application (all environments)
│   ├── infrastructure.yaml       # Infrastructure components
│   ├── monitoring.yaml           # Monitoring stack
│   └── security.yaml             # Security components
└── overlays/                     # Environment-specific overlays
    ├── dev/
    ├── staging/
    └── production/
```

## 🚀 Quick Start

### Prerequisites

1. **Kubernetes cluster** with ArgoCD installed
2. **Git repository** with deployment configurations
3. **Container registry** with application images

### Install ArgoCD

```bash
# Create namespace
kubectl create namespace argocd

# Install ArgoCD
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for pods to be ready
kubectl wait --for=condition=Ready pods --all -n argocd --timeout=300s

# Expose ArgoCD server
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Get initial admin password
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d

# Login with CLI
argocd login localhost:8080 --username admin --password <password>
```

### Deploy Applications

1. **Deploy the App of Apps**:
   ```bash
   kubectl apply -f deployment/argocd/argocd-app-of-apps.yaml
   ```

2. **Sync all applications**:
   ```bash
   argocd app sync kailash-platform
   argocd app wait kailash-platform
   ```

3. **Verify deployments**:
   ```bash
   argocd app list
   argocd app get kailash-platform
   ```

## 🔧 Configuration

### Application Management

**Create new application**:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: my-new-app
  namespace: argocd
spec:
  project: kailash
  source:
    repoURL: https://github.com/your-org/my-app
    targetRevision: main
    path: deployment
  destination:
    server: https://kubernetes.default.svc
    namespace: my-app
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

### Multi-Environment Setup

Each environment has its own application instance:

- **Development**: Auto-sync from `develop` branch
- **Staging**: Auto-sync from `main` branch
- **Production**: Manual sync from tags

### Sync Policies

**Automated sync with self-healing**:
```yaml
syncPolicy:
  automated:
    prune: true      # Delete resources not in Git
    selfHeal: true   # Revert manual changes
  syncOptions:
    - CreateNamespace=true
    - PrunePropagationPolicy=foreground
```

## 🔒 Security

### RBAC Configuration

ArgoCD uses Kubernetes RBAC and its own RBAC system:

```yaml
# Developer role
p, role:developer, applications, get, */*, allow
p, role:developer, applications, sync, */*, allow
p, role:developer, applications, action/*, */*, allow
p, role:developer, logs, get, */*, allow
p, role:developer, exec, create, */*, allow
g, kailash:developers, role:developer
```

### Secret Management

1. **Sealed Secrets**:
   ```bash
   # Install sealed-secrets controller
   kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.5/controller.yaml
   
   # Create sealed secret
   echo -n mypassword | kubectl create secret generic mysecret \
     --dry-run=client \
     --from-file=password=/dev/stdin \
     -o yaml | kubeseal -o yaml > mysealedsecret.yaml
   ```

2. **External Secrets Operator**:
   ```yaml
   apiVersion: external-secrets.io/v1beta1
   kind: ExternalSecret
   metadata:
     name: app-secrets
   spec:
     secretStoreRef:
       name: vault-backend
       kind: SecretStore
     target:
       name: app-secrets
     data:
       - secretKey: password
         remoteRef:
           key: secret/data/app
           property: password
   ```

## 📊 Monitoring ArgoCD

### Metrics

ArgoCD exposes Prometheus metrics:

```yaml
apiVersion: v1
kind: ServiceMonitor
metadata:
  name: argocd-metrics
  namespace: argocd
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: argocd-metrics
  endpoints:
    - port: metrics
```

### Notifications

Configure notifications for application events:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: argocd-notifications-cm
  namespace: argocd
data:
  service.slack: |
    token: $slack-token
  template.app-deployed: |
    message: |
      Application {{.app.metadata.name}} is now running new version.
  trigger.on-deployed: |
    - when: app.status.operationState.phase in ['Succeeded'] and app.status.health.status == 'Healthy'
      send: [app-deployed]
```

## 🔄 Application Patterns

### Blue-Green Deployment

```yaml
spec:
  source:
    helm:
      parameters:
        - name: bluegreen.enabled
          value: "true"
        - name: bluegreen.autoPromote
          value: "false"
        - name: bluegreen.previewReplicaCount
          value: "3"
```

### Canary Deployment

```yaml
spec:
  source:
    helm:
      parameters:
        - name: canary.enabled
          value: "true"
        - name: canary.weight
          value: "20"
        - name: canary.analysis.enabled
          value: "true"
```

### Progressive Delivery with Flagger

```yaml
apiVersion: flagger.app/v1beta1
kind: Canary
metadata:
  name: kailash-app
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: kailash-app
  progressDeadlineSeconds: 60
  service:
    port: 80
  analysis:
    interval: 1m
    threshold: 5
    maxWeight: 50
    stepWeight: 10
```

## 🛠️ Troubleshooting

### Common Issues

1. **Sync failures**:
   ```bash
   # Check application status
   argocd app get <app-name>
   
   # View sync details
   argocd app sync <app-name> --dry-run
   
   # Force sync
   argocd app sync <app-name> --force
   ```

2. **Out of sync**:
   ```bash
   # Check differences
   argocd app diff <app-name>
   
   # Refresh application
   argocd app refresh <app-name>
   ```

3. **Resource conflicts**:
   ```bash
   # Remove conflicting resources
   kubectl delete <resource> <name> -n <namespace>
   
   # Sync with replace
   argocd app sync <app-name> --replace
   ```

## 📝 Best Practices

1. **Use App of Apps pattern** for managing multiple applications
2. **Implement proper RBAC** for different teams
3. **Enable automated sync** for non-production environments
4. **Use Git tags** for production deployments
5. **Configure resource limits** in Application specs
6. **Monitor sync status** and set up alerts
7. **Use ApplicationSets** for multi-cluster deployments

## 🔗 Useful Commands

```bash
# List all applications
argocd app list

# Get application details
argocd app get <app-name>

# Sync application
argocd app sync <app-name>

# Delete application (keep resources)
argocd app delete <app-name> --cascade=false

# Show application manifests
argocd app manifests <app-name>

# Show application resources
argocd app resources <app-name>

# Rollback application
argocd app rollback <app-name> <revision>

# Show sync history
argocd app history <app-name>

# Override parameters
argocd app set <app-name> -p key=value

# Patch application
kubectl patch app <app-name> -n argocd --type merge -p '{"spec":{"syncPolicy":{"automated":{"prune":true}}}}'
```

## 📚 References

- [ArgoCD Documentation](https://argo-cd.readthedocs.io/)
- [ArgoCD Examples](https://github.com/argoproj/argocd-example-apps)
- [GitOps Best Practices](https://www.weave.works/technologies/gitops/)
- [App of Apps Pattern](https://argo-cd.readthedocs.io/en/stable/operator-manual/cluster-bootstrapping/)