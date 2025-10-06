# ADR-0051: Advanced Search Filters for Workflow Discovery

## Status
Proposed

## Context

Kailash Studio users need efficient ways to discover workflows in large repositories. As organizations accumulate hundreds or thousands of workflows, the basic search functionality becomes insufficient for workflow discovery and management.

### Current Limitations
- Basic name-only search
- No filtering by workflow attributes (status, author, date, framework)
- No tag-based organization
- No saved search presets
- Limited sorting options

### Business Requirements
- **Workflow Discovery**: Help users find relevant workflows quickly
- **Organization**: Support enterprise workflow management patterns
- **Productivity**: Enable power users to create saved search presets
- **User Experience**: Provide intuitive filtering with real-time updates

### Technical Context
- Existing infrastructure: PostgreSQL with JSON support, DataFlow models
- Workflow model has tags, status, framework_type, created_by, dates
- User preferences stored in JSON field
- Frontend using Ant Design components

## Decision

We will implement **Advanced Search Filters** with multi-criteria filtering, saved presets, and faceted navigation.

### Core Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Frontend Components                    │
├─────────────────────────────────────────────────────────┤
│  AdvancedSearchPanel                                    │
│    ├── SearchFilterBar                                  │
│    │     ├── TagFilter (AND/OR logic)                   │
│    │     ├── DateRangeFilter (created, updated)         │
│    │     ├── AuthorFilter (multi-select)                │
│    │     ├── StatusFilter (draft, published, archived)  │
│    │     └── FrameworkFilter (core, dataflow, nexus)    │
│    │                                                     │
│    ├── SearchPresets (save/load filter combinations)    │
│    │                                                     │
│    └── SearchResults                                    │
│          ├── ResultList (paginated)                     │
│          ├── FacetedNavigation (click to refine)        │
│          └── Pagination                                 │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                  Backend Services                       │
├─────────────────────────────────────────────────────────┤
│  SearchQueryBuilder                                     │
│    └── Builds complex SQL from filter criteria         │
│                                                         │
│  FacetAggregator                                        │
│    └── Generates facet counts for refinement           │
│                                                         │
│  PresetManager                                          │
│    └── Saves/loads user search presets                 │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│                  Data Layer                             │
├─────────────────────────────────────────────────────────┤
│  PostgreSQL Full-Text Search (for query text)          │
│  JSON Operators (for tags, preferences)                │
│  B-tree Indexes (for dates, status, framework)         │
│  Redis Cache (for facet counts, autocomplete)          │
└─────────────────────────────────────────────────────────┘
```

### Key Design Decisions

#### 1. Query Builder Pattern
**Decision**: Build SQL queries dynamically from filter criteria

**Rationale**:
- Flexible: Supports any combination of filters
- Performance: Leverages PostgreSQL query optimizer
- Maintainable: Centralized query logic

**Implementation**:
```python
class AdvancedSearchQueryBuilder:
    def build_query(self, filters: SearchFiltersRequest) -> str:
        conditions = []

        # Tag filtering with AND/OR logic
        if filters.tags:
            if filters.tagMode == 'AND':
                conditions.append("tags @> %s")  # Contains all
            else:
                conditions.append("tags && %s")  # Contains any

        # Date range filtering
        if filters.createdAfter:
            conditions.append("created_at >= %s")
        if filters.createdBefore:
            conditions.append("created_at <= %s")

        # Author filtering
        if filters.authorIds:
            conditions.append("created_by = ANY(%s)")

        # Status filtering
        if filters.statuses:
            conditions.append("status = ANY(%s)")

        # Framework filtering
        if filters.frameworkTypes:
            conditions.append("framework_type = ANY(%s)")

        # Project filtering
        if filters.projectIds:
            conditions.append("project_id = ANY(%s)")

        # Combine with AND
        where_clause = " AND ".join(conditions)

        # Build final query with sorting and pagination
        query = f"""
            SELECT * FROM workflows
            WHERE organization_id = %s
            {f"AND {where_clause}" if where_clause else ""}
            ORDER BY {filters.sortBy} {filters.sortOrder}
            LIMIT %s OFFSET %s
        """

        return query
```

#### 2. Saved Search Presets
**Decision**: Store presets in User.preferences JSON field

**Rationale**:
- No schema changes required
- User-specific data (per-user presets)
- Flexible structure for future extensions

**Data Structure**:
```json
{
  "search_presets": [
    {
      "id": "uuid-1",
      "name": "My Active Workflows",
      "filters": {
        "statuses": ["draft", "published"],
        "authorIds": ["user-123"],
        "sortBy": "updated_at",
        "sortOrder": "desc"
      }
    }
  ]
}
```

#### 3. Faceted Navigation
**Decision**: Generate facet counts alongside search results

**Rationale**:
- Guided discovery: Users see what options are available
- Transparency: Shows result counts for each facet
- Refinement: Click facet to add filter

**Implementation**:
```python
def get_facets(organization_id: str, current_filters: dict) -> dict:
    # Use same filters but aggregate by facet dimensions
    facets = {
        "tags": db.query("""
            SELECT DISTINCT unnest(tags) as tag, COUNT(*) as count
            FROM workflows
            WHERE organization_id = %s
            GROUP BY tag
            ORDER BY count DESC
        """),
        "authors": db.query("""
            SELECT created_by as user_id,
                   users.username,
                   COUNT(*) as count
            FROM workflows
            JOIN users ON workflows.created_by = users.id
            WHERE workflows.organization_id = %s
            GROUP BY created_by, users.username
        """),
        # ... similar for statuses, frameworks
    }
    return facets
```

#### 4. Performance Optimization
**Decision**: Use Redis cache for expensive aggregations

**Rationale**:
- Facet counts are expensive to compute
- Facet data changes infrequently
- Cache invalidation on workflow create/update

**Caching Strategy**:
```python
@cache_with_ttl(ttl=300)  # 5-minute TTL
def get_cached_facets(organization_id: str) -> dict:
    return compute_facets(organization_id)

@invalidate_cache(key_pattern="facets:*")
def on_workflow_changed(workflow_id: str):
    pass  # Cache automatically invalidated
```

## Alternatives Considered

### Option 1: ElasticSearch Integration
**Description**: Use ElasticSearch for advanced search capabilities

**Pros**:
- Best-in-class search performance
- Built-in faceting and aggregations
- Fuzzy search, typo tolerance
- Scalable to millions of workflows

**Cons**:
- Additional infrastructure dependency
- Increased operational complexity
- Data synchronization challenges
- Over-engineered for current scale

**Rejection Reason**: PostgreSQL full-text search sufficient for current scale (<100K workflows). ElasticSearch can be added later if needed.

### Option 2: Client-Side Filtering
**Description**: Load all workflows, filter in browser

**Pros**:
- Instant filtering (no server round-trip)
- Simpler backend implementation
- Works offline

**Cons**:
- Doesn't scale beyond ~1000 workflows
- High initial load time
- Large memory footprint
- No server-side facet computation

**Rejection Reason**: Doesn't meet enterprise scalability requirements.

### Option 3: Dedicated Search Microservice
**Description**: Build separate search service with its own database

**Pros**:
- Independent scaling
- Specialized optimization
- Cleaner separation of concerns

**Cons**:
- Increased complexity
- Data synchronization overhead
- Additional deployment/monitoring
- Over-engineered for MVP

**Rejection Reason**: Premature optimization. Can be extracted later if needed.

## Consequences

### Positive Consequences

#### User Experience Improvements
- **Faster Discovery**: Find workflows in seconds vs. minutes
- **Power User Enablement**: Saved presets for repeated searches
- **Transparency**: Facets show what's available before filtering
- **Flexibility**: Combine any filters without restrictions

#### Technical Benefits
- **Leverages Existing Stack**: PostgreSQL, DataFlow models, Redis
- **Performance**: <300ms for complex queries with 100K workflows
- **Scalability**: Horizontal scaling via read replicas
- **Maintainability**: Query builder pattern centralizes logic

#### Business Value
- **Productivity**: 5x faster workflow discovery
- **Organization**: Better workflow management for enterprises
- **Adoption**: Lower barrier to workflow reuse
- **Data Insights**: Facets reveal workflow usage patterns

### Negative Consequences

#### Development Complexity
- **Query Complexity**: Dynamic SQL generation requires careful validation
- **Testing Overhead**: Need to test all filter combinations
- **Cache Invalidation**: Facet cache invalidation logic complexity

#### Performance Considerations
- **Database Load**: Complex queries on large datasets
- **Cache Dependency**: Redis failure degrades facet performance
- **Index Maintenance**: Multiple indexes increase write overhead

#### User Experience Challenges
- **Learning Curve**: Advanced filters may overwhelm basic users
- **Filter Overload**: Too many options can be confusing
- **Result Confusion**: AND vs. OR logic for tags

### Risk Mitigation Strategies

#### Performance Risks
- **Mitigation**: Database query optimization, index tuning
- **Monitoring**: Query performance metrics, slow query logging
- **Fallback**: Degrade to basic search if advanced search times out

#### Complexity Risks
- **Mitigation**: Comprehensive test coverage, code reviews
- **Documentation**: Clear examples of filter combinations
- **UX Testing**: User testing to validate filter interface

#### Cache Invalidation Risks
- **Mitigation**: Conservative TTL (5 minutes), fallback to database
- **Monitoring**: Cache hit rate, invalidation frequency
- **Graceful Degradation**: Show stale facets if cache fails

## Implementation Plan

### Phase 1: Backend Foundation (2h)
1. Implement AdvancedSearchQueryBuilder
2. Add indexes for filter fields (status, framework_type, created_at, tags)
3. Create /api/workflows/search endpoint
4. Implement facet computation
5. Add Redis caching for facets

### Phase 2: Frontend Components (2h)
1. Create SearchFilterBar component
2. Implement individual filter components (TagFilter, DateRangeFilter, etc.)
3. Build FacetedNavigation component
4. Add SearchPresets UI

### Phase 3: Integration and Testing (1h)
1. Connect frontend to backend API
2. Add WebSocket real-time filter updates
3. Write comprehensive test suite
4. Performance testing with 100K workflows

### Phase 4: Polish (1h)
1. UX refinements based on testing
2. Accessibility improvements (WCAG AA)
3. Documentation and user guide
4. Monitor and optimize performance

## Success Metrics

### Performance Metrics
- Simple filter response: <100ms (target: <50ms)
- Complex filter response: <300ms (target: <150ms)
- Facet computation: <200ms (target: <100ms)
- Preset loading: <100ms (target: <50ms)

### User Metrics
- Filter usage: 60%+ of users use filters weekly
- Preset creation: 30%+ of power users create presets
- Discovery time: 5x faster vs. basic search
- User satisfaction: >4.5/5 NPS for search experience

### Technical Metrics
- Query performance: 95th percentile <300ms
- Cache hit rate: >80% for facet queries
- Database load: <10% increase in query volume
- Index overhead: <5% increase in storage

## Dependencies

### Technical Dependencies
- PostgreSQL 12+ (JSON operators, full-text search)
- Redis 6+ (caching)
- Existing DataFlow models (Workflow, User)
- Ant Design components (frontend)

### Data Dependencies
- Workflow model with indexed fields
- User model with preferences JSON field
- Organization context for multi-tenancy

### Timeline Dependencies
- Must be implemented before Community Marketplace (uses advanced search)
- Can be developed in parallel with Collaboration Presence

## Conclusion

Advanced Search Filters provide essential workflow discovery capabilities for Kailash Studio, enabling efficient management of large workflow repositories. The solution leverages existing PostgreSQL and Redis infrastructure, avoiding the complexity of additional search engines while meeting current scalability requirements.

The query builder pattern provides flexibility for future enhancements, while saved presets empower power users to optimize their workflow. Faceted navigation guides users toward relevant filters, improving the overall discovery experience.

This feature is foundational for enterprise adoption, where workflow organization and discovery are critical for productivity.
