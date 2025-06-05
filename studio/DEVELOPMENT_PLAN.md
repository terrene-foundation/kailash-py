# Kailash Workflow Studio - Development Plan

## Overview
The Kailash Workflow Studio is a visual interface for the Kailash Python SDK that faithfully represents all SDK capabilities through a dynamic, extensible architecture.

## Core Principles
1. **SDK-First**: The studio is a reflection of SDK capabilities, not an idealized workflow builder
2. **Dynamic Discovery**: New SDK nodes automatically appear in the studio without code changes
3. **Multi-Tenant**: Each tenant gets isolated resources and persistent storage
4. **Production-Ready**: Docker-based deployment with proper security and isolation

## Architecture Summary
- **Frontend**: React 18 + TypeScript + Tailwind CSS
- **Backend**: Enhanced Kailash SDK with REST/WebSocket APIs
- **Storage**: PostgreSQL (workflows) + Redis (cache) + Filesystem (data)
- **Deployment**: Docker Compose with per-tenant isolation

## Development Phases

### Phase 1: Backend API Enhancement (Week 1)
**Goal**: Expose all SDK capabilities through a comprehensive API

1. **Create WorkflowStudioAPI** (`src/kailash/api/studio.py`)
   - Node discovery endpoints
   - Workflow CRUD operations
   - Execution management
   - Export/Import functionality

2. **Node Registry API**
   ```python
   GET /api/nodes
   Response: {
     "categories": {
       "ai": [
         {
           "id": "LLMAgentNode",
           "name": "LLM Agent",
           "description": "Interact with Large Language Models",
           "parameters": [...],
           "inputs": [...],
           "outputs": [...]
         }
       ],
       "data": [...],
       "logic": [...],
       ...
     }
   }
   ```

3. **Workflow Storage Schema**
   ```sql
   CREATE SCHEMA IF NOT EXISTS tenant_{tenant_id};
   
   CREATE TABLE tenant_{tenant_id}.workflows (
     id UUID PRIMARY KEY,
     name VARCHAR(255),
     description TEXT,
     definition JSONB,
     created_at TIMESTAMP,
     updated_at TIMESTAMP
   );
   
   CREATE TABLE tenant_{tenant_id}.executions (
     id UUID PRIMARY KEY,
     workflow_id UUID REFERENCES workflows(id),
     status VARCHAR(50),
     started_at TIMESTAMP,
     completed_at TIMESTAMP,
     result JSONB
   );
   ```

### Phase 2: Core Studio Components (Week 2)
**Goal**: Build the foundational UI components

1. **App.tsx** - Main application shell
   ```typescript
   function App() {
     return (
       <WorkflowProvider>
         <div className="flex h-screen">
           <NodePalette />
           <WorkflowCanvas />
           <PropertyPanel />
         </div>
       </WorkflowProvider>
     );
   }
   ```

2. **NodePalette Component**
   - Fetch node definitions from API
   - Group by category (AI, Data, Logic, etc.)
   - Drag-and-drop initialization
   - Search/filter functionality

3. **WorkflowCanvas Component**
   - React Flow integration
   - Custom node components
   - Connection validation
   - Pan/zoom controls

4. **PropertyPanel Component**
   - Dynamic form generation
   - Parameter validation
   - Help text and examples
   - Real-time updates

### Phase 3: Workflow Management (Week 3)
**Goal**: Complete workflow CRUD and persistence

1. **Workflow Operations**
   - Create/Save workflows
   - Load existing workflows
   - Auto-save functionality
   - Version tracking

2. **Node Configuration**
   - Dynamic parameter forms
   - Input/output mapping
   - Validation feedback
   - Default values

3. **Connection Management**
   - Type-safe connections
   - Visual feedback
   - Auto-layout options
   - Connection validation

### Phase 4: Execution Engine (Week 4)
**Goal**: Integrate workflow execution with real-time monitoring

1. **Execution API Integration**
   - Start workflow execution
   - Monitor progress
   - Handle errors
   - Display results

2. **WebSocket Integration**
   - Real-time status updates
   - Node execution progress
   - Log streaming
   - Error notifications

3. **Execution Panel**
   - Execution history
   - Live monitoring
   - Log viewer
   - Result visualization

### Phase 5: Multi-Tenant Infrastructure (Week 5)
**Goal**: Implement tenant isolation and deployment

1. **Docker Configuration**
   ```yaml
   # docker-compose.yml
   version: '3.8'
   
   services:
     studio-backend:
       build: .
       environment:
         - TENANT_ID=${TENANT_ID}
         - DATABASE_URL=postgresql://postgres:password@postgres:5432/kailash_${TENANT_ID}
       volumes:
         - ./tenants/${TENANT_ID}:/app/tenant_data
   
     studio-frontend:
       build: ./studio
       environment:
         - REACT_APP_API_URL=http://studio-backend:8000
         - REACT_APP_TENANT_ID=${TENANT_ID}
   ```

2. **Tenant Management**
   - Tenant provisioning script
   - Database schema creation
   - Storage directory setup
   - Nginx routing configuration

3. **Authentication System**
   - JWT-based authentication
   - Tenant ID in token claims
   - API middleware for validation
   - Frontend auth context

### Phase 6: Advanced Features (Week 6-8)
**Goal**: Production-ready features

1. **Export/Import**
   - Export to Python code
   - Export to YAML
   - Import from code
   - Template library

2. **Collaboration**
   - Workflow sharing
   - Read-only views
   - Comments/annotations
   - Change tracking

3. **Performance**
   - Lazy loading nodes
   - Canvas virtualization
   - Caching strategies
   - CDN integration

4. **Security**
   - Input sanitization
   - CORS configuration
   - Rate limiting
   - Audit logging

## File Structure
```
studio/
├── src/
│   ├── index.tsx              # Entry point
│   ├── App.tsx                # Main app component
│   ├── elements/              # High-level components
│   │   ├── NodePalette/
│   │   ├── WorkflowCanvas/
│   │   ├── PropertyPanel/
│   │   └── ExecutionPanel/
│   ├── components/            # Reusable UI components
│   │   ├── DynamicNode/
│   │   ├── ParameterForm/
│   │   └── ConnectionLine/
│   ├── services/              # API integration
│   │   ├── nodeRegistry.ts
│   │   ├── workflowApi.ts
│   │   └── executionApi.ts
│   ├── store/                 # State management
│   │   ├── workflowStore.ts
│   │   └── executionStore.ts
│   └── hooks/                 # Custom hooks
│       ├── useNodeDefinitions.ts
│       └── useWorkflowExecution.ts
```

## Development Commands
```bash
# Start development environment
make studio-dev

# Run tests
cd studio && npm test

# Build for production
cd studio && npm run build

# Deploy new tenant
./scripts/deploy-tenant.sh --tenant-id acme

# Access studio
http://localhost:3000 (development)
https://acme.studio.kailash.ai (production)
```

## Success Criteria
1. All 66+ SDK nodes are available in the palette
2. Workflows can be created, saved, and executed
3. Real-time execution monitoring works
4. Multi-tenant isolation is complete
5. Export generates valid Python/YAML code
6. Performance is acceptable (< 100ms interactions)

## Next Steps
1. Start with Phase 1: Backend API implementation
2. Set up development environment
3. Create initial React application
4. Implement node discovery
5. Build first visual workflow