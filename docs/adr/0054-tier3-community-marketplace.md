# ADR-0054: Community Marketplace for Workflow Sharing

## Status
Proposed

## Context

Kailash Studio enables users to create powerful workflows, but there's no mechanism for discovering, sharing, and reusing workflows created by other users. This creates several problems:

### Current Limitations
- **Discovery Gap**: Users can't find existing solutions to common problems
- **Duplication**: Multiple users reinvent the same workflows
- **Knowledge Silos**: Best practices trapped within individual organizations
- **No Quality Signals**: No ratings, reviews, or usage metrics
- **Limited Collaboration**: No community-driven improvement

### Business Requirements
- **Workflow Discovery**: Enable users to find and import community workflows
- **Knowledge Sharing**: Foster community contributions and collaboration
- **Quality Curation**: Surface high-quality workflows through ratings and curation
- **Author Recognition**: Reward contributors with reputation and visibility
- **Marketplace Economy**: Potential future monetization (premium workflows)

### Technical Context
- WorkflowTemplate model exists with `is_public` flag
- User model has reputation, profile data
- AuditLog model tracks user activities
- Need content moderation for public sharing
- PostgreSQL full-text search for discovery

## Decision

We will implement a **Community Marketplace** for workflow discovery, publishing, importing, rating, and curation.

### Core Architecture

```
┌──────────────────────────────────────────────────────────┐
│                  Marketplace Frontend                    │
├──────────────────────────────────────────────────────────┤
│  MarketplaceUI                                           │
│    ├── MarketplaceGrid                                   │
│    │     ├── FeaturedCarousel (curated highlights)       │
│    │     ├── TemplateList (cards with metrics)           │
│    │     └── Pagination                                  │
│    │                                                      │
│    ├── MarketplaceSidebar                                │
│    │     ├── CategoryFilter                              │
│    │     ├── TagCloud                                    │
│    │     ├── FrameworkFilter                             │
│    │     ├── RatingFilter                                │
│    │     └── SortControls                                │
│    │                                                      │
│    ├── TemplateDetailModal                               │
│    │     ├── WorkflowPreview (visual)                    │
│    │     ├── ReviewsSection (ratings + comments)         │
│    │     ├── Documentation (markdown)                    │
│    │     └── VersionHistory                              │
│    │                                                      │
│    ├── PublishWorkflowDialog                             │
│    │     ├── WorkflowSelector                            │
│    │     ├── MetadataForm (name, desc, category, tags)   │
│    │     └── LicenseSelector                             │
│    │                                                      │
│    └── AuthorProfileModal                                │
│          ├── AuthorStatistics                            │
│          ├── PublishedTemplates                          │
│          └── Badges and Reputation                       │
└──────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────┐
│                  Backend Services                        │
├──────────────────────────────────────────────────────────┤
│  Marketplace API                                         │
│    ├── Search and Discovery                              │
│    ├── Template Publishing                               │
│    ├── Template Importing                                │
│    ├── Ratings and Reviews                               │
│    └── Content Moderation                                │
│                                                          │
│  Curation Service                                        │
│    ├── Featured Selection                                │
│    ├── Quality Scoring                                   │
│    └── Spam Detection                                    │
│                                                          │
│  Analytics Service                                       │
│    ├── Usage Tracking                                    │
│    ├── Download Counting                                 │
│    └── Author Reputation                                 │
└──────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────┐
│                  Data Layer                              │
├──────────────────────────────────────────────────────────┤
│  WorkflowTemplate (extended)                             │
│    ├── is_marketplace_published: bool                    │
│    ├── average_rating: float                             │
│    ├── download_count: int                               │
│    ├── license: str                                      │
│    └── preview_image_url: str                            │
│                                                          │
│  TemplateReview (NEW)                                    │
│    ├── rating: int (1-5)                                 │
│    ├── comment: str                                      │
│    └── helpful_count: int                                │
│                                                          │
│  TemplateDownload (NEW - analytics)                      │
│    └── Track downloads for trending                     │
│                                                          │
│  TemplateReport (NEW - moderation)                       │
│    ├── reason: str (spam, malicious, copyright)         │
│    └── status: str (pending, reviewed, dismissed)       │
└──────────────────────────────────────────────────────────┘
```

### Key Design Decisions

#### 1. Hybrid Moderation Model
**Decision**: Automated spam detection + manual review for reports

**Rationale**:
- **Automated First Line**: Catch obvious spam/malicious content
- **Human Judgment**: Manual review for nuanced cases
- **Scalability**: Automation handles volume, humans handle edge cases
- **Quality**: Maintains high marketplace quality

**Moderation Flow**:
```python
class ModerationService:
    def validate_template_for_publishing(self, template: WorkflowTemplate) -> dict:
        checks = []

        # Automated checks
        checks.append(self.check_malicious_code(template))
        checks.append(self.check_spam_indicators(template))
        checks.append(self.check_license_compliance(template))
        checks.append(self.check_metadata_completeness(template))

        # Determine status
        if any(check['severity'] == 'critical' for check in checks):
            return {'status': 'rejected', 'checks': checks}
        elif any(check['severity'] == 'warning' for check in checks):
            return {'status': 'pending_review', 'checks': checks}
        else:
            return {'status': 'published', 'checks': checks}

    def check_malicious_code(self, template: dict) -> dict:
        """Scan for SQL injection, XSS, etc."""
        suspicious_patterns = [
            r'DROP\s+TABLE',
            r'<script>',
            r'eval\(',
            r'exec\(',
        ]

        definition_str = json.dumps(template['workflow_definition'])

        for pattern in suspicious_patterns:
            if re.search(pattern, definition_str, re.IGNORECASE):
                return {
                    'check': 'malicious_code',
                    'severity': 'critical',
                    'message': f'Detected suspicious pattern: {pattern}'
                }

        return {'check': 'malicious_code', 'severity': 'pass'}
```

#### 2. Multi-Tier Licensing Support
**Decision**: Support common open-source licenses + proprietary option

**Rationale**:
- **Creator Choice**: Authors decide how workflows can be used
- **Compliance**: Clear licensing prevents legal issues
- **Monetization**: Proprietary license enables future paid marketplace
- **Attribution**: Licenses ensure proper credit

**Supported Licenses**:
```python
SUPPORTED_LICENSES = {
    'MIT': {
        'name': 'MIT License',
        'commercial_use': True,
        'modification': True,
        'distribution': True,
        'private_use': True,
        'attribution_required': True
    },
    'Apache-2.0': {
        'name': 'Apache License 2.0',
        'commercial_use': True,
        'modification': True,
        'distribution': True,
        'private_use': True,
        'patent_grant': True,
        'attribution_required': True
    },
    'GPL-3.0': {
        'name': 'GNU General Public License v3.0',
        'commercial_use': True,
        'modification': True,
        'distribution': True,
        'copyleft': True,
        'attribution_required': True
    },
    'Proprietary': {
        'name': 'Proprietary License',
        'commercial_use': False,
        'modification': False,
        'distribution': False,
        'custom_terms': True
    }
}
```

#### 3. Author Reputation System
**Decision**: Reputation based on published templates, downloads, ratings

**Rationale**:
- **Quality Signal**: High-reputation authors indicate quality
- **Motivation**: Incentivizes contributions and quality
- **Discovery**: Can filter by author reputation
- **Gamification**: Badges and achievements encourage participation

**Reputation Calculation**:
```python
def calculate_author_reputation(user_id: str) -> int:
    # Base reputation from published templates
    published_count = WorkflowTemplate.query.filter_by(
        created_by=user_id,
        is_marketplace_published=True
    ).count()
    reputation = published_count * 10

    # Bonus from downloads
    total_downloads = db.session.query(
        func.sum(WorkflowTemplate.download_count)
    ).filter_by(created_by=user_id).scalar() or 0
    reputation += total_downloads

    # Bonus from ratings
    avg_rating = db.session.query(
        func.avg(WorkflowTemplate.average_rating)
    ).filter_by(created_by=user_id).scalar() or 0
    reputation += int(avg_rating * 20)

    # Penalties from reports
    report_count = TemplateReport.query.filter(
        TemplateReport.template_id.in_(
            select([WorkflowTemplate.id]).where(
                WorkflowTemplate.created_by == user_id
            )
        ),
        TemplateReport.status == 'action_taken'
    ).count()
    reputation -= report_count * 50

    return max(0, reputation)  # Floor at 0
```

#### 4. Featured Content Curation
**Decision**: Admin-curated featured carousel + algorithmic recommendations

**Rationale**:
- **Quality**: Manual curation ensures featured content is high-quality
- **Discovery**: Featured content gets prominent placement
- **Diversity**: Curators ensure variety of use cases
- **Authority**: Official endorsement signals trust

**Curation Criteria**:
```python
class CurationService:
    def select_featured_templates(self) -> List[WorkflowTemplate]:
        """Select templates for featured carousel."""

        candidates = WorkflowTemplate.query.filter_by(
            is_marketplace_published=True,
            is_verified=True
        ).filter(
            WorkflowTemplate.average_rating >= 4.5,
            WorkflowTemplate.download_count >= 50
        ).all()

        # Manual curator can override
        featured_ids = get_curator_selections()
        if featured_ids:
            return WorkflowTemplate.query.filter(
                WorkflowTemplate.id.in_(featured_ids)
            ).all()

        # Algorithmic selection: diversity across categories
        featured = []
        categories_covered = set()

        for template in sorted(candidates,
                               key=lambda t: t.average_rating * t.download_count,
                               reverse=True):
            if template.category not in categories_covered:
                featured.append(template)
                categories_covered.add(template.category)

            if len(featured) >= 10:
                break

        return featured
```

#### 5. One Review Per User Per Template
**Decision**: Enforce unique constraint on (template_id, user_id)

**Rationale**:
- **Prevents Spam**: Can't submit multiple reviews
- **Authenticity**: One voice per user per template
- **Edit Support**: User can update their review
- **Simplicity**: Clear rules, easy to enforce

**Implementation**:
```python
@db.model
class TemplateReview:
    id: str
    template_id: str
    user_id: str
    rating: int  # 1-5
    comment: str
    helpful_count: int = 0

    class Meta:
        table_name = "template_reviews"
        unique_fields = ["template_id", "user_id"]  # Enforced at DB level
```

#### 6. Progressive Image Loading
**Decision**: Thumbnail (150x150) for cards, full preview (800x600) for modal

**Rationale**:
- **Performance**: Thumbnails load fast for grid view
- **Bandwidth**: Save bandwidth on initial page load
- **UX**: Progressive enhancement for detail view
- **Storage**: Two image sizes vs. on-the-fly resize

**Image Storage**:
```python
class ImageUploadService:
    def process_preview_image(self, image_file: UploadFile) -> dict:
        # Generate thumbnail
        thumbnail = self.resize_image(image_file, width=150, height=150)
        thumbnail_url = self.upload_to_s3(thumbnail, 'thumbnails/')

        # Generate full preview
        preview = self.resize_image(image_file, width=800, height=600)
        preview_url = self.upload_to_s3(preview, 'previews/')

        return {
            'thumbnail_url': thumbnail_url,
            'preview_url': preview_url
        }
```

## Alternatives Considered

### Option 1: GitHub-Based Marketplace
**Description**: Host workflows as GitHub repositories, marketplace is a directory

**Pros**:
- Leverages GitHub for version control, stars, forks
- No storage infrastructure needed
- Built-in collaboration tools
- Familiarity for developers

**Cons**:
- Non-developers find GitHub intimidating
- No unified UX (external navigation)
- Can't control quality/moderation
- Dependency on GitHub uptime

**Rejection Reason**: Want integrated, user-friendly experience for non-technical users. GitHub is complementary, not a replacement.

### Option 2: NPM-Style Package Registry
**Description**: CLI-based package manager (`kailash install workflow-name`)

**Pros**:
- Familiar to developers
- Programmatic access
- Version management
- Dependency resolution

**Cons**:
- CLI-only (no visual browsing)
- Steep learning curve for non-devs
- Complex dependency management
- Over-engineered for workflows

**Rejection Reason**: Workflows are visual and discoverable. CLI is complementary but shouldn't be primary interface.

### Option 3: Third-Party Marketplace (Zapier App Directory Model)
**Description**: Partner with existing marketplace platform

**Pros**:
- Existing user base
- Proven marketplace mechanics
- No development needed

**Cons**:
- Revenue sharing
- Less control over UX
- Integration complexity
- Brand dilution

**Rejection Reason**: Want full control over marketplace experience and economics.

### Option 4: Peer-to-Peer Sharing (No Central Marketplace)
**Description**: Users share workflows via export/import, no central catalog

**Pros**:
- Simple implementation
- No moderation needed
- No infrastructure costs
- Maximum privacy

**Cons**:
- No discovery mechanism
- No quality signals
- Difficult to find workflows
- Limited collaboration

**Rejection Reason**: Doesn't solve the discovery problem, which is the core value proposition.

## Consequences

### Positive Consequences

#### User Benefits
- **Faster Development**: Import existing workflows vs. build from scratch
- **Learning**: Discover best practices from community
- **Recognition**: Authors gain reputation and visibility
- **Collaboration**: Community-driven improvement

#### Business Benefits
- **Network Effects**: More workflows → more users → more workflows
- **Differentiation**: Unique community asset
- **Monetization**: Future paid marketplace opportunity
- **Retention**: Community ties increase stickiness

#### Technical Benefits
- **Leverages Existing Models**: WorkflowTemplate, User, AuditLog
- **Scalability**: PostgreSQL handles 10K+ templates easily
- **Search**: Full-text search for discovery
- **Moderation**: Automated + manual hybrid approach

### Negative Consequences

#### Development Complexity
- **Moderation**: Need content moderation tools and processes
- **Quality Control**: Ensuring marketplace quality
- **Licensing**: Legal compliance for licenses
- **Scaling**: Search performance with large catalog

#### Operational Challenges
- **Moderation Queue**: Need human moderators
- **Spam Prevention**: Constant battle against spam
- **Support**: Users reporting issues with templates
- **Legal**: DMCA, copyright issues

#### Business Risks
- **Quality Dilution**: Low-quality templates damage reputation
- **Spam**: Marketplace overrun with spam
- **Copyright**: Users upload copyrighted content
- **Abuse**: Malicious workflows

### Risk Mitigation Strategies

#### Content Quality Risks
- **Mitigation**: Automated checks + manual review queue
- **Curation**: Featured content highlights quality
- **Ratings**: Community feedback surfaces quality

#### Legal Risks
- **Mitigation**: Clear terms of service, license compliance
- **DMCA Process**: Takedown procedure for copyright issues
- **Moderation**: Review reported content promptly

#### Spam Risks
- **Mitigation**: Rate limiting, spam detection algorithms
- **Reputation**: Low-reputation authors flagged
- **Community Reports**: Easy reporting mechanism

## Implementation Plan

### Phase 1: Data Models and Publishing (3h)
1. Add marketplace fields to WorkflowTemplate model
2. Create TemplateReview, TemplateDownload, TemplateReport models
3. Implement publishing workflow (metadata, validation)
4. Build moderation service (automated checks)
5. Create publishing UI (PublishWorkflowDialog)

### Phase 2: Browse and Discovery (4h)
1. Implement marketplace search API
2. Add faceted navigation (categories, tags, ratings)
3. Build MarketplaceGrid component
4. Create TemplateCard with metrics
5. Add FeaturedCarousel
6. Implement pagination

### Phase 3: Detail and Import (3h)
1. Create TemplateDetailModal
2. Add workflow preview visualization
3. Implement import functionality
4. Build ReviewsSection
5. Add version history tab
6. Create documentation renderer

### Phase 4: Reviews and Curation (2h)
1. Implement review submission
2. Add rating calculation
3. Build moderation dashboard (admin)
4. Create report template functionality
5. Implement author profile pages
6. Add reputation calculation

## Success Metrics

### Adoption Metrics
- Published templates: 100+ in first 3 months
- Active publishers: 30+ contributing users
- Downloads: 500+ imports in first 3 months
- Reviews: 200+ reviews submitted

### Quality Metrics
- Average template rating: >4.0/5
- Spam rate: <5% of submissions
- Review approval rate: >80%
- Featured quality: >4.5/5 average

### Engagement Metrics
- Search usage: 60%+ of users search marketplace weekly
- Import rate: 40%+ of marketplace visitors import template
- Review participation: 20%+ of importers leave review
- Author retention: 50%+ publish second template

## Dependencies

### Technical Dependencies
- WorkflowTemplate model (extended with marketplace fields)
- TemplateReview, TemplateDownload, TemplateReport models (new)
- PostgreSQL full-text search
- S3/MinIO for preview image storage
- Redis for search result caching

### Organizational Dependencies
- Moderation team/process for review queue
- Legal review of terms of service, licenses
- Marketing support for marketplace launch
- Community management resources

### Timeline Dependencies
- Should implement Advanced Search Filters first (marketplace uses search)
- Independent of other Tier 3 features

## Conclusion

The Community Marketplace transforms Kailash Studio from an isolated workflow tool into a collaborative platform. By enabling workflow discovery, sharing, and reuse, we unlock network effects that benefit all users.

The hybrid moderation model balances quality control with scalability, while the reputation system incentivizes high-quality contributions. Multi-tier licensing support prepares for future monetization while respecting creator rights.

This feature is the highest-value Tier 3 addition ($24K business value, 12h effort) and creates a sustainable competitive advantage through community-driven content. The marketplace becomes a moat—the more workflows published, the more valuable the platform becomes, creating a virtuous cycle of growth.

With 12 hours of development effort, we deliver a complete marketplace experience that positions Kailash Studio as a community-first platform for workflow automation.
