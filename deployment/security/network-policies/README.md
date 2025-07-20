# Kubernetes Network Policies

## 🛡️ Overview

Network policies provide micro-segmentation and zero-trust networking for Kubernetes clusters. This implementation follows enterprise security best practices and CIS benchmarks.

## 🎯 Security Principles

- **Default Deny All**: Block all traffic by default
- **Least Privilege**: Allow only necessary communications
- **Micro-segmentation**: Isolate workloads by function
- **Ingress/Egress Control**: Manage both incoming and outgoing traffic

## 📁 Network Policy Structure

```
network-policies/
├── 00-default-deny.yaml           # Default deny all traffic
├── 01-namespace-isolation.yaml    # Cross-namespace restrictions
├── 02-kube-system-policies.yaml   # System component networking
├── 03-application-policies.yaml   # Application-specific rules
├── 04-monitoring-policies.yaml    # Metrics and logging access
├── 05-ingress-policies.yaml       # External traffic rules
└── 06-egress-policies.yaml        # Outbound traffic controls
```

## 🚀 Quick Start

### 1. Apply Network Policies
```bash
# Apply in order (important!)
kubectl apply -f deployment/security/network-policies/00-default-deny.yaml
kubectl apply -f deployment/security/network-policies/01-namespace-isolation.yaml
kubectl apply -f deployment/security/network-policies/02-kube-system-policies.yaml
kubectl apply -f deployment/security/network-policies/03-application-policies.yaml
kubectl apply -f deployment/security/network-policies/04-monitoring-policies.yaml
kubectl apply -f deployment/security/network-policies/05-ingress-policies.yaml
kubectl apply -f deployment/security/network-policies/06-egress-policies.yaml
```

### 2. Verify Network Policies
```bash
# List all network policies
kubectl get networkpolicies --all-namespaces

# Test connectivity
kubectl exec -it test-pod -- nc -zv target-service 8080
```

### 3. Monitor Network Policy Effects
```bash
# Check denied connections (requires Cilium or Calico)
kubectl logs -n kube-system -l k8s-app=cilium -f | grep -i "denied"
```

## 📋 Policy Descriptions

### Default Deny (00-default-deny.yaml)
Blocks all ingress and egress traffic to pods unless explicitly allowed by other policies.

### Namespace Isolation (01-namespace-isolation.yaml)  
Prevents cross-namespace communication except for system namespaces.

### Kube-System Policies (02-kube-system-policies.yaml)
Allows necessary communication for Kubernetes system components.

### Application Policies (03-application-policies.yaml)
Defines communication rules for the Kailash SDK application stack.

### Monitoring Policies (04-monitoring-policies.yaml)
Enables metrics collection and logging access for observability.

### Ingress Policies (05-ingress-policies.yaml)
Controls external traffic access to applications.

### Egress Policies (06-egress-policies.yaml)
Manages outbound traffic for internet access, DNS, etc.

## ⚠️ Important Considerations

### CNI Compatibility
Network policies require a CNI plugin that supports them:
- ✅ Calico
- ✅ Cilium  
- ✅ Weave Net
- ❌ Flannel (basic)

### Testing Requirements
Always test network policies in a staging environment first:
```bash
# Test pod connectivity
kubectl run test-client --image=busybox -it --rm -- /bin/sh

# Inside test pod:
nc -zv service-name 8080
nslookup kubernetes.default.svc.cluster.local
```

### Troubleshooting
```bash
# Check policy syntax
kubectl apply --dry-run=client -f policy.yaml

# Describe network policies
kubectl describe networkpolicy policy-name

# Monitor policy logs
kubectl logs -n kube-system -l k8s-app=calico-node -f
```

## 🔧 Customization

### Environment-Specific Policies
```bash
# Development - more permissive
kubectl apply -f network-policies/environments/development/

# Staging - moderate restrictions  
kubectl apply -f network-policies/environments/staging/

# Production - strict enforcement
kubectl apply -f network-policies/environments/production/
```

### Application-Specific Rules
Modify `03-application-policies.yaml` to match your application architecture:
- Database access patterns
- Service mesh integration
- External API dependencies

## 📊 Monitoring & Compliance

### Policy Compliance Dashboard
```yaml
# Grafana query for policy violations
sum(rate(cilium_drop_count_total[5m])) by (reason)
```

### Audit Logs
Network policy decisions are logged in the CNI plugin logs:
```bash
# Calico logs
kubectl logs -n kube-system -l k8s-app=calico-node

# Cilium logs  
kubectl logs -n kube-system -l k8s-app=cilium
```

## 🔗 Related Documentation

- [CIS Benchmarks](../cis-benchmarks/)
- [Security Hardening](../README.md)
- [Pod Security](../pod-security/)
- [Compliance Framework](../../compliance/)

---

**🔒 Network policies are essential for zero-trust security**