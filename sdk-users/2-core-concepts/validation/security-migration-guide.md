# Security Migration Guide: Connection Parameter Validation

*Complete guide for migrating to secure-by-default connection parameter validation*

## 🚨 **BREAKING CHANGE (v0.8.6+): Security-First Defaults**

**Default changed from `warn` to `strict` mode for enterprise security**

```python
# OLD (v0.8.5 and earlier)
runtime = LocalRuntime()  # Used connection_validation="warn"

# NEW (v0.8.6+) 
runtime = LocalRuntime()  # Uses connection_validation="strict" - SECURE BY DEFAULT!
```

---

## 📋 **Quick Migration Checklist**

### ✅ **For New Projects (v0.8.6+)**
- **Nothing to do!** - Secure by default with high performance
- `LocalRuntime()` automatically prevents SQL injection, type confusion, parameter attacks
- Built-in performance optimization makes validation faster than previous versions
- Enterprise security compliance out-of-the-box

### ✅ **For Most Existing Projects**
- **Upgrade and test** - Most workflows will work immediately
- **Performance boost** - Validation is now faster due to caching
- **Remove explicit security config** - `connection_validation="strict"` no longer needed

### ⚠️ **For Complex Legacy Projects**
1. **Test Phase**: Upgrade and run existing workflows
2. **Fix Phase**: Address any new validation errors (rare)
3. **Optimize Phase**: Remove manual security configuration
4. **Monitor Phase**: Verify improved security metrics

---

## 🔧 **Migration Strategies by Complexity**

### **Strategy 1: Simple Workflows (Most Common - v0.8.6+)**

**Scenario**: Basic workflows with 1-3 nodes, simple parameter passing

```python
# ✅ AFTER UPGRADE (works automatically)
workflow = WorkflowBuilder()
workflow.add_node("DataProcessorNode", "processor", {"threshold": 0.9})
workflow.add_node("OutputNode", "output", {})
workflow.add_connection("processor", "results", "output", "data")

runtime = LocalRuntime()  # Secure by default, faster than before
results, _ = runtime.execute(workflow.build())
# Performance boost: validation now uses caching
```

**Expected Issues**: None for most workflows
**Fix Time**: 0 minutes - works automatically with better performance

### **Strategy 2: Complex Workflows (Medium Risk)**

**Scenario**: Multi-stage data pipelines, nested parameter passing

```python
# Complex workflow migration example
workflow = WorkflowBuilder()

# Stage 1: Data ingestion
workflow.add_node("CSVReaderNode", "ingestion", {"file_path": "data.csv"})

# Stage 2: Data processing with PythonCodeNode
workflow.add_node("PythonCodeNode", "processor", {
    "code": """
# Correct pattern for PythonCodeNode
data = result  # Input from connection becomes 'result' variable
result = {
    'processed_data': data.get('rows', []),
    'metadata': {'source': 'csv', 'processed_at': 'now'}
}
"""
})

# Stage 3: Database insertion
workflow.add_node("SQLDatabaseNode", "storage", {
    "connection_string": "postgresql://localhost/mydb"
})

# Connections with proper output mapping
workflow.add_connection("ingestion", "data", "processor", "")  # Goes to 'result' var
workflow.add_connection("processor", "processed_data", "storage", "records")

# Migration steps
print("🔍 Step 1: Testing with new secure defaults...")
runtime = LocalRuntime()  # Secure by default with caching
try:
    results, _ = runtime.execute(workflow.build())
    print("   ✅ Workflow works with secure defaults!")
except Exception as e:
    print(f"   ⚠️ Need migration: {e}")
    
    print("🔧 Step 2: Temporary legacy mode (if needed)...")
    runtime_legacy = LocalRuntime(connection_validation="warn")
    results, _ = runtime_legacy.execute(workflow.build())
    print("   ✅ Legacy mode works - now fix validation issues")
```

**Expected Issues**: Type conversions, nested parameter access, database connection strings
**Fix Time**: 1-2 hours per workflow

### **Strategy 3: Enterprise Workflows (High Risk)**

**Scenario**: Multi-tenant, dynamic workflows with runtime parameter injection

```python
# Enterprise workflow migration pattern
class EnterpriseWorkflowMigration:
    """Complete enterprise migration pattern with monitoring."""
    
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.migration_metrics = {}
    
    def audit_workflow(self, workflow: Workflow, parameters: dict = None):
        """Step 1: Comprehensive audit with detailed logging."""
        print(f"🔍 Auditing workflow for tenant: {self.tenant_id}")
        
        runtime = LocalRuntime(
            connection_validation="warn",
            enable_monitoring=True,
            enable_audit=True
        )
        
        try:
            results, run_id = runtime.execute(workflow, parameters)
            
            # Get validation metrics
            metrics = runtime.get_validation_metrics()
            self.migration_metrics = metrics
            
            print("   📊 Validation Metrics:")
            performance = metrics.get("performance_summary", {})
            print(f"      - Validation overhead: {performance.get('avg_validation_time', 0):.1f}ms")
            print(f"      - Warnings generated: {performance.get('warning_count', 0)}")
            
            security = metrics.get("security_report", {})
            if security.get("violations", 0) > 0:
                print(f"      ⚠️ Security issues: {security['violations']}")
                
            return True, results
            
        except Exception as e:
            print(f"   ❌ Critical issues: {e}")
            return False, None
    
    def test_strict_mode(self, workflow: Workflow, parameters: dict = None):
        """Step 2: Test strict enforcement."""
        print(f"🔒 Testing strict mode for tenant: {self.tenant_id}")
        
        runtime = LocalRuntime(  # Secure by default
            enable_monitoring=True
        )
        
        try:
            results, run_id = runtime.execute(workflow, parameters)
            print("   ✅ Strict mode validation passed!")
            return True, results
            
        except Exception as e:
            print(f"   ❌ Strict mode blocked execution: {str(e)[:100]}...")
            
            # Provide specific fix suggestions
            if "type" in str(e).lower():
                print("      💡 Fix: Check parameter type conversions")
            if "required" in str(e).lower():
                print("      💡 Fix: Add missing required parameters")
            if "unauthorized" in str(e).lower():
                print("      💡 Fix: Remove unauthorized parameters")
                
            return False, str(e)
    
    def deploy_secure_workflow(self, workflow: Workflow, parameters: dict = None):
        """Step 3: Deploy with full security."""
        print(f"🚀 Deploying secure workflow for tenant: {self.tenant_id}")
        
        runtime = LocalRuntime(  # Secure by default
            parameter_validation="strict",  # Enhanced parameter validation
            enable_security=True,
            enable_audit=True,
            enable_monitoring=True
        )
        
        try:
            results, run_id = runtime.execute(workflow, parameters)
            print("   ✅ Secure deployment successful!")
            
            # Final security metrics
            metrics = runtime.get_validation_metrics()
            security = metrics.get("security_report", {})
            print(f"      🛡️ Security status: {security.get('status', 'protected')}")
            
            return True, results
            
        except Exception as e:
            print(f"   ❌ Deployment failed: {e}")
            return False, None

# Usage example
migrator = EnterpriseWorkflowMigration("tenant_123")

# Your existing workflow
workflow = WorkflowBuilder()
# ... add nodes and connections ...

# Complete migration process
audit_success, audit_results = migrator.audit_workflow(workflow, parameters)
if audit_success:
    test_success, test_results = migrator.test_strict_mode(workflow, parameters)
    if test_success:
        deploy_success, final_results = migrator.deploy_secure_workflow(workflow, parameters)
```

**Expected Issues**: Multi-tenancy parameter isolation, dynamic parameter validation, complex error handling
**Fix Time**: 4-8 hours per workflow system

---

## 🛠️ **Common Migration Issues & Solutions**

### **Issue #1: Type Mismatch Errors**

```python
# ❌ PROBLEM: String passed to integer parameter
workflow.add_connection("source", "count_str", "target", "limit")  # "100" -> int

# ✅ SOLUTION 1: Fix source node to output correct type
class FixedSourceNode(Node):
    def run(self, **kwargs):
        return {"count_int": 100}  # Return int, not string

# ✅ SOLUTION 2: Add type conversion in target node
class FixedTargetNode(Node):
    def get_parameters(self):
        return {"limit": NodeParameter(type=int, required=True)}
    
    def validate_inputs(self, **kwargs):
        validated = super().validate_inputs(**kwargs)
        # Convert string to int if needed
        if "limit" in validated and isinstance(validated["limit"], str):
            try:
                validated["limit"] = int(validated["limit"])
            except ValueError:
                raise ValueError(f"Cannot convert limit '{validated['limit']}' to integer")
        return validated
```

### **Issue #2: Missing Required Parameters**

```python
# ❌ PROBLEM: Connection doesn't provide required parameter
class TargetNode(Node):
    def get_parameters(self):
        return {
            "data": NodeParameter(type=dict, required=True),
            "format": NodeParameter(type=str, required=True)  # Missing!
        }

# ✅ SOLUTION 1: Provide default in node definition
def get_parameters(self):
    return {
        "data": NodeParameter(type=dict, required=True),
        "format": NodeParameter(type=str, required=False, default="json")
    }

# ✅ SOLUTION 2: Add missing connection or runtime parameter
workflow.add_connection("source", "output_format", "target", "format")
# OR
runtime.execute(workflow, {"target": {"format": "json"}})
```

### **Issue #3: Nested Parameter Access**

```python
# ❌ PROBLEM: Deep nested parameter access fails
workflow.add_connection("source", "config.database.host", "target", "db_host")

# ✅ SOLUTION: Restructure source node output
class FixedSourceNode(Node):
    def run(self, **kwargs):
        config = {"database": {"host": "localhost", "port": 5432}}
        return {
            "db_host": config["database"]["host"],  # Flatten structure
            "db_port": config["database"]["port"],
            "full_config": config  # Keep original if needed
        }
```

### **Issue #4: PythonCodeNode Parameter Access**

```python
# ❌ PROBLEM: Incorrect parameter access in PythonCodeNode
workflow.add_node("PythonCodeNode", "processor", {
    "code": "result = {'output': parameters.get('input_data')}"  # Wrong!
})

# ✅ SOLUTION: Use correct variable access pattern
workflow.add_node("PythonCodeNode", "processor", {
    "code": """
# Correct pattern: parameters are available as direct variables
input_value = locals().get('input_data', 'default')  
result = {'output': f'processed_{input_value}'}
"""
})
```

---

## 📊 **Migration Monitoring & Metrics**

### **Performance Impact Assessment**

```python
def assess_migration_impact(workflow: Workflow):
    """Measure performance impact of security validation."""
    
    modes = ["off", "warn", "strict"]
    results = {}
    
    for mode in modes:
        runtime = LocalRuntime(connection_validation=mode)
        
        # Measure execution time
        import time
        start = time.time()
        try:
            workflow_results, _ = runtime.execute(workflow)
            execution_time = time.time() - start
            results[mode] = {
                "time_ms": execution_time * 1000,
                "success": True,
                "overhead": "N/A" if mode == "off" else f"{((execution_time / results.get('off', {}).get('time_ms', 1)) - 1) * 100:.1f}%"
            }
        except Exception as e:
            results[mode] = {
                "time_ms": (time.time() - start) * 1000,
                "success": False,
                "error": str(e)[:50]
            }
    
    # Report results
    print("📊 Performance Impact Analysis:")
    for mode, data in results.items():
        status = "✅" if data["success"] else "❌"
        print(f"   {status} {mode.upper()}: {data['time_ms']:.1f}ms {data.get('overhead', '')}")
    
    return results
```

### **Security Validation Metrics**

```python
def get_security_metrics(runtime: LocalRuntime):
    """Get comprehensive security metrics after workflow execution."""
    
    metrics = runtime.get_validation_metrics()
    
    print("🛡️ Security Metrics Report:")
    
    # Performance metrics
    perf = metrics.get("performance_summary", {})
    print(f"   Validation Time: {perf.get('avg_validation_time', 0):.1f}ms")
    print(f"   Cache Hit Rate: {perf.get('cache_hit_rate', 0):.1%}")
    
    # Security metrics
    security = metrics.get("security_report", {})
    print(f"   Security Violations: {security.get('violations', 0)}")
    print(f"   Blocked Attacks: {security.get('blocked_attacks', 0)}")
    
    # Validation issues
    if security.get('violations', 0) > 0:
        print("   ⚠️ Security Issues Detected:")
        for violation in security.get('violation_details', []):
            print(f"      - {violation.get('type', 'Unknown')}: {violation.get('message', '')}")
    
    return metrics
```

---

## 🎯 **Migration Timeline & Planning**

### **Phase 1: Assessment (Week 1)**
- [ ] Inventory all workflows using `LocalRuntime`
- [ ] Run audit phase with `connection_validation="warn"`  
- [ ] Categorize workflows by complexity (Simple/Complex/Enterprise)
- [ ] Document validation warnings and performance metrics

### **Phase 2: Fix & Test (Week 2-3)**  
- [ ] Fix Simple workflows (batch process)
- [ ] Fix Complex workflows (individual attention)
- [ ] Test all workflows (secure by default in v0.8.6+)
- [ ] Update documentation and runbooks

### **Phase 3: Deploy & Monitor (Week 4)**
- [ ] Deploy upgraded workflows (automatically secure)
- [ ] Monitor security metrics and performance
- [ ] Set up alerts for validation failures
- [ ] Train team on new security patterns

### **Phase 4: Optimize (Ongoing)**
- [ ] Optimize validation performance if needed
- [ ] Add custom validation rules as required
- [ ] Review and update security policies
- [ ] Plan for additional security enhancements

---

## 📚 **Additional Resources**

- [Common Security Mistakes](common-mistakes.md#mistake-0-connection-parameter-security-vulnerability)
- [Enterprise Security Patterns](../../5-enterprise/security-patterns.md)
- [Node Parameter Best Practices](../nodes/parameter-best-practices.md)
- [Performance Optimization Guide](../../3-development/performance-optimization.md)

---

## 🆘 **Need Help?**

If you encounter issues during migration:

1. **Check Error Categories**: The enhanced error formatter provides specific fix suggestions
2. **Use Debug Mode**: Enable `enable_parameter_debugging=True` for detailed logging  
3. **Review Metrics**: Use `runtime.get_validation_metrics()` for insights
4. **Gradual Migration**: Use `connection_validation="warn"` during transition
5. **Community Support**: Check the [troubleshooting guide](../../3-development/troubleshooting.md)

**Remember: This security update prevents real attacks. The migration effort is a small investment for significant security improvements.**