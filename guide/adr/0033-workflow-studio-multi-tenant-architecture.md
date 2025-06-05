# ADR-0033: Workflow Studio Multi-Tenant Architecture

## Status
Accepted (2025-06-05) - Foundation implemented in Session 48

## Context
We need to create a visual workflow studio that serves as the primary user interface for the Kailash Python SDK. The studio must:
1. Faithfully represent all SDK capabilities (66+ nodes across 10 categories)
2. Support multiple isolated tenants with persistent storage
3. Be flexible enough to adapt quickly as the SDK grows
4. Provide both development and production deployment options

## Decision
We will implement a multi-tenant architecture with the following components:

### 1. Frontend Architecture
- **React 18 + TypeScript** for the UI following `guide/frontend/` patterns
- **Component-based architecture** matching SDK node categories:
  - NodePalette: Dynamically generated from SDK node registry
  - WorkflowCanvas: React Flow for visual workflow editing
  - PropertyPanel: Dynamic form generation based on node parameters
  - ExecutionPanel: Real-time workflow execution monitoring
- **API-first approach**: All SDK capabilities exposed through REST/WebSocket APIs

### 2. Backend API Enhancement
Extend the existing SDK with a comprehensive API layer:
```python
# New module: src/kailash/api/studio.py
class WorkflowStudioAPI:
    """API endpoints for the workflow studio"""
    
    # Node Discovery
    GET /api/nodes - List all available nodes with metadata
    GET /api/nodes/{category} - List nodes by category
    GET /api/nodes/{node_id}/schema - Get node parameter schema
    
    # Workflow Management (per tenant)
    GET /api/workflows - List tenant workflows
    POST /api/workflows - Create new workflow
    GET /api/workflows/{id} - Get workflow details
    PUT /api/workflows/{id} - Update workflow
    DELETE /api/workflows/{id} - Delete workflow
    
    # Workflow Execution
    POST /api/workflows/{id}/execute - Execute workflow
    GET /api/executions/{id} - Get execution status
    WS /ws/executions/{id} - Real-time execution updates
    
    # Export/Import
    GET /api/workflows/{id}/export?format=python|yaml - Export workflow
    POST /api/workflows/import - Import workflow from code
```

### 3. Multi-Tenant Architecture
```yaml
# docker-compose.yml
version: '3.8'

services:
  # Shared services
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: kailash_studio
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    
  # Per-tenant services (dynamically created)
  tenant_template:
    build: .
    environment:
      TENANT_ID: ${TENANT_ID}
      DATABASE_URL: postgresql://.../${TENANT_ID}
      REDIS_URL: redis://redis:6379/${TENANT_DB_NUMBER}
    volumes:
      - ./tenants/${TENANT_ID}/workflows:/app/workflows
      - ./tenants/${TENANT_ID}/data:/app/data
```

### 4. Tenant Isolation Strategy
- **Database**: Schema-per-tenant in PostgreSQL
- **File Storage**: Directory-per-tenant for workflows and data
- **Cache**: Redis database-per-tenant
- **Authentication**: JWT with tenant_id claim
- **API**: Tenant ID extracted from JWT or subdomain

### 5. Dynamic Node Registry
```typescript
// Frontend: src/services/nodeRegistry.ts
interface NodeDefinition {
  id: string;
  category: string;
  name: string;
  description: string;
  parameters: ParameterSchema[];
  inputs: PortSchema[];
  outputs: PortSchema[];
}

class NodeRegistry {
  async fetchNodes(): Promise<NodeDefinition[]> {
    // Fetch from backend API
    return api.get('/api/nodes');
  }
  
  generateComponent(node: NodeDefinition): React.Component {
    // Dynamically generate UI component
    return <DynamicNode definition={node} />;
  }
}
```

### 6. Deployment Options

#### Development Mode
```bash
# Single command to start everything
make studio-dev

# Starts:
# - Backend API (port 8000)
# - Frontend dev server (port 3000)
# - PostgreSQL & Redis
```

#### Production Mode
```bash
# Deploy new tenant
./scripts/deploy-tenant.sh --tenant-id acme --domain acme.studio.kailash.ai

# Creates isolated:
# - Docker container with unique ports
# - PostgreSQL schema
# - Redis database
# - Nginx routing
```

## Consequences

### Positive
- **True SDK representation**: Studio automatically reflects all SDK capabilities
- **Scalable**: Each tenant gets isolated resources
- **Maintainable**: Clear separation between SDK and UI
- **Flexible**: New nodes automatically appear in the studio
- **Production-ready**: Docker-based deployment with proper isolation

### Negative
- **Complexity**: Multi-tenant adds operational complexity
- **Resource usage**: Each tenant needs separate containers
- **Initial setup**: Requires PostgreSQL and Redis

### Mitigation
- Provide single-tenant development mode for simplicity
- Create tenant management CLI tools
- Document deployment patterns thoroughly

## Implementation Plan

### Phase 1: Core Studio (Week 1-2)
1. Implement WorkflowStudioAPI in the SDK
2. Create basic React app with node palette and canvas
3. Dynamic node discovery and rendering
4. Basic workflow CRUD operations

### Phase 2: Execution Engine (Week 3-4)
1. Workflow execution API endpoints
2. WebSocket for real-time updates
3. Execution monitoring UI
4. Error handling and logging

### Phase 3: Multi-Tenant (Week 5-6)
1. PostgreSQL schema isolation
2. Tenant authentication/authorization
3. Docker compose templates
4. Deployment scripts

### Phase 4: Production Features (Week 7-8)
1. Export/import functionality
2. Version control integration
3. Collaboration features
4. Performance optimization

## Implementation Status (Session 48)

### Completed
- ✅ Frontend development guidelines created (`guide/frontend/`)
- ✅ React 18 + TypeScript + Vite project structure (`studio/`)
- ✅ Docker infrastructure for multi-tenant deployment
- ✅ Deployment scripts (`deploy-tenant.sh`, `start-studio.sh`)
- ✅ ADR documentation finalized

### In Progress
- 🚧 WorkflowStudioAPI backend implementation
- 🚧 Core UI components (NodePalette, Canvas, PropertyPanel)
- 🚧 Node discovery API integration

### Remaining
- ⏳ WebSocket real-time updates
- ⏳ PostgreSQL schema isolation
- ⏳ Tenant authentication
- ⏳ Production deployment patterns

## References
- Frontend Guidelines: `guide/frontend/`
- Node Catalog: `guide/reference/node-catalog.md`
- API Registry: `guide/reference/api-registry.yaml`
- Security Architecture: ADR-0032