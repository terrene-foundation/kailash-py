"""Unit tests for edge computing infrastructure."""

import asyncio
from datetime import datetime, timedelta

import pytest
from kailash.edge.compliance import (
    ComplianceContext,
    ComplianceRouter,
    DataClassification,
)
from kailash.edge.discovery import (
    EdgeDiscovery,
    EdgeDiscoveryRequest,
    EdgeSelectionStrategy,
)
from kailash.edge.location import (
    ComplianceZone,
    EdgeCapabilities,
    EdgeLocation,
    EdgeMetrics,
    EdgeRegion,
    GeographicCoordinates,
    get_predefined_location,
)


class TestEdgeLocation:
    """Test EdgeLocation functionality."""

    def test_edge_location_creation(self):
        """Test creating an edge location."""
        coords = GeographicCoordinates(40.7128, -74.0060)  # New York
        capabilities = EdgeCapabilities(
            cpu_cores=8, memory_gb=32, storage_gb=500, gpu_available=True
        )

        location = EdgeLocation(
            location_id="test-location",
            name="Test Location",
            region=EdgeRegion.US_EAST,
            coordinates=coords,
            capabilities=capabilities,
        )

        assert location.location_id == "test-location"
        assert location.name == "Test Location"
        assert location.region == EdgeRegion.US_EAST
        assert location.is_healthy
        assert location.is_available_for_workload

    def test_latency_calculation(self):
        """Test latency calculation between locations."""
        ny_coords = GeographicCoordinates(40.7128, -74.0060)  # New York
        london_coords = GeographicCoordinates(51.5074, -0.1278)  # London

        ny_location = EdgeLocation(
            location_id="ny",
            name="New York",
            region=EdgeRegion.US_EAST,
            coordinates=ny_coords,
            capabilities=EdgeCapabilities(cpu_cores=4, memory_gb=16, storage_gb=100),
        )

        # Calculate latency from NY to London (should be significant)
        latency = ny_location.calculate_latency_to(london_coords)
        assert latency > 50  # Trans-Atlantic latency should be > 50ms

        # Calculate latency from NY to nearby location (should be low)
        nearby_coords = GeographicCoordinates(40.8176, -74.0431)  # Nearby NYC
        nearby_latency = ny_location.calculate_latency_to(nearby_coords)
        assert nearby_latency < 10  # Local latency should be very low

    def test_compliance_support(self):
        """Test compliance zone support checking."""
        location = EdgeLocation(
            location_id="eu-location",
            name="EU Location",
            region=EdgeRegion.EU_WEST,
            coordinates=GeographicCoordinates(53.3498, -6.2603),
            capabilities=EdgeCapabilities(cpu_cores=4, memory_gb=16, storage_gb=100),
            compliance_zones=[ComplianceZone.GDPR, ComplianceZone.PUBLIC],
        )

        # Should support GDPR
        assert location.supports_compliance([ComplianceZone.GDPR])

        # Should not support HIPAA
        assert not location.supports_compliance([ComplianceZone.HIPAA])

        # Should support multiple zones if all are present
        assert location.supports_compliance(
            [ComplianceZone.GDPR, ComplianceZone.PUBLIC]
        )

    def test_capabilities_checking(self):
        """Test capability requirement checking."""
        location = EdgeLocation(
            location_id="test",
            name="Test",
            region=EdgeRegion.US_EAST,
            coordinates=GeographicCoordinates(40.7128, -74.0060),
            capabilities=EdgeCapabilities(
                cpu_cores=8,
                memory_gb=32,
                storage_gb=1000,
                gpu_available=True,
                database_support=["postgresql", "redis"],
                ai_models_available=["llama3.2"],
            ),
        )

        # Should support reasonable requirements
        assert location.supports_capabilities(
            {"cpu_cores": 4, "memory_gb": 16, "database_support": ["postgresql"]}
        )

        # Should not support excessive requirements
        assert not location.supports_capabilities(
            {"cpu_cores": 16}
        )  # More than available

        # Should not support unavailable features
        assert not location.supports_capabilities(
            {"ai_models": ["gpt-4"]}
        )  # Not available

    def test_workload_management(self):
        """Test workload addition and removal."""
        location = EdgeLocation(
            location_id="test",
            name="Test",
            region=EdgeRegion.US_EAST,
            coordinates=GeographicCoordinates(40.7128, -74.0060),
            capabilities=EdgeCapabilities(cpu_cores=4, memory_gb=16, storage_gb=100),
        )

        # Initially no workloads
        assert len(location.active_workloads) == 0

        # Add workload
        location.add_workload("workload-1", {"type": "test"})
        assert len(location.active_workloads) == 1
        assert "workload-1" in location.active_workloads

        # Remove workload
        location.remove_workload("workload-1")
        assert len(location.active_workloads) == 0

    def test_predefined_locations(self):
        """Test predefined edge locations."""
        us_east = get_predefined_location("us-east-1")
        assert us_east is not None
        assert us_east.region == EdgeRegion.US_EAST
        assert ComplianceZone.PUBLIC in us_east.compliance_zones

        eu_west = get_predefined_location("eu-west-1")
        assert eu_west is not None
        assert eu_west.region == EdgeRegion.EU_WEST
        assert ComplianceZone.GDPR in eu_west.compliance_zones


class TestEdgeDiscovery:
    """Test EdgeDiscovery functionality."""

    @pytest.fixture
    def sample_locations(self):
        """Create sample edge locations for testing."""
        locations = [
            EdgeLocation(
                location_id="us-east",
                name="US East",
                region=EdgeRegion.US_EAST,
                coordinates=GeographicCoordinates(40.7128, -74.0060),
                capabilities=EdgeCapabilities(
                    cpu_cores=8, memory_gb=32, storage_gb=500
                ),
                compliance_zones=[ComplianceZone.PUBLIC, ComplianceZone.HIPAA],
            ),
            EdgeLocation(
                location_id="eu-west",
                name="EU West",
                region=EdgeRegion.EU_WEST,
                coordinates=GeographicCoordinates(53.3498, -6.2603),
                capabilities=EdgeCapabilities(
                    cpu_cores=4, memory_gb=16, storage_gb=200
                ),
                compliance_zones=[ComplianceZone.GDPR, ComplianceZone.PUBLIC],
            ),
            EdgeLocation(
                location_id="asia-east",
                name="Asia East",
                region=EdgeRegion.ASIA_EAST,
                coordinates=GeographicCoordinates(35.6762, 139.6503),
                capabilities=EdgeCapabilities(
                    cpu_cores=6, memory_gb=24, storage_gb=300
                ),
                compliance_zones=[ComplianceZone.PUBLIC],
            ),
        ]
        return locations

    def test_discovery_initialization(self, sample_locations):
        """Test edge discovery initialization."""
        discovery = EdgeDiscovery(locations=sample_locations)

        assert len(discovery) == 3
        assert "us-east" in discovery
        assert discovery.get_location("us-east") is not None

    @pytest.mark.asyncio
    async def test_optimal_edge_discovery(self, sample_locations):
        """Test discovering optimal edges."""
        discovery = EdgeDiscovery(locations=sample_locations)

        # Request from New York (should prefer US East)
        ny_coords = GeographicCoordinates(40.7128, -74.0060)
        request = EdgeDiscoveryRequest(
            user_coordinates=ny_coords,
            selection_strategy=EdgeSelectionStrategy.LATENCY_OPTIMAL,
            max_results=2,
        )

        results = await discovery.discover_optimal_edges(request)

        assert len(results) <= 2
        assert len(results) > 0

        # First result should be US East (closest)
        best_location = results[0].location
        assert best_location.location_id == "us-east"
        assert results[0].estimated_latency_ms < 50  # Should be very low latency

    @pytest.mark.asyncio
    async def test_compliance_filtering(self, sample_locations):
        """Test filtering by compliance requirements."""
        discovery = EdgeDiscovery(locations=sample_locations)

        # Request GDPR compliance
        request = EdgeDiscoveryRequest(
            compliance_zones=[ComplianceZone.GDPR], max_results=5
        )

        results = await discovery.discover_optimal_edges(request)

        # Should only return EU location
        assert len(results) == 1
        assert results[0].location.location_id == "eu-west"

    @pytest.mark.asyncio
    async def test_capability_requirements(self, sample_locations):
        """Test filtering by capability requirements."""
        discovery = EdgeDiscovery(locations=sample_locations)

        # Request high CPU requirements
        request = EdgeDiscoveryRequest(
            min_cpu_cores=7, max_results=5
        )  # Only US East has 8 cores

        results = await discovery.discover_optimal_edges(request)

        # Should only return US East
        assert len(results) == 1
        assert results[0].location.location_id == "us-east"

    @pytest.mark.asyncio
    async def test_cost_optimization(self, sample_locations):
        """Test cost-optimized selection."""
        discovery = EdgeDiscovery(locations=sample_locations)

        request = EdgeDiscoveryRequest(
            selection_strategy=EdgeSelectionStrategy.COST_OPTIMAL, max_results=3
        )

        results = await discovery.discover_optimal_edges(request)
        assert len(results) > 0

        # Results should be sorted by cost score
        for i in range(len(results) - 1):
            assert results[i].total_score >= results[i + 1].total_score

    def test_location_management(self, sample_locations):
        """Test adding and removing locations."""
        discovery = EdgeDiscovery(locations=sample_locations[:2])  # Start with 2

        assert len(discovery) == 2

        # Add third location
        discovery.add_location(sample_locations[2])
        assert len(discovery) == 3

        # Remove location
        discovery.remove_location("asia-east")
        assert len(discovery) == 2
        assert "asia-east" not in discovery


class TestComplianceRouter:
    """Test ComplianceRouter functionality."""

    def test_compliance_router_initialization(self):
        """Test compliance router initialization."""
        router = ComplianceRouter()

        assert len(router.compliance_rules) > 0
        assert ComplianceZone.GDPR in router.compliance_rules
        assert ComplianceZone.HIPAA in router.compliance_rules

    def test_data_classification(self):
        """Test automatic data classification."""
        router = ComplianceRouter()

        # Test PII data
        pii_data = {"name": "John Doe", "email": "john@example.com"}
        classification = router.classify_data(pii_data)
        assert classification == DataClassification.PII

        # Test healthcare data
        health_data = {"patient": "Jane", "diagnosis": "diabetes"}
        classification = router.classify_data(health_data)
        assert classification == DataClassification.PHI

        # Test financial data
        financial_data = {"account_number": "123456", "bank": "First National"}
        classification = router.classify_data(financial_data)
        assert classification == DataClassification.FINANCIAL

        # Test public data
        public_data = {"message": "hello world"}
        classification = router.classify_data(public_data)
        assert classification == DataClassification.PUBLIC

    @pytest.mark.asyncio
    async def test_compliance_routing(self):
        """Test compliance routing decisions."""
        router = ComplianceRouter()

        # Create test locations
        us_location = EdgeLocation(
            location_id="us-test",
            name="US Test",
            region=EdgeRegion.US_EAST,
            coordinates=GeographicCoordinates(40.7128, -74.0060),
            capabilities=EdgeCapabilities(
                cpu_cores=4,
                memory_gb=16,
                storage_gb=100,
                encryption_at_rest=True,
                audit_logging=True,
            ),
            compliance_zones=[ComplianceZone.HIPAA, ComplianceZone.PUBLIC],
        )

        eu_location = EdgeLocation(
            location_id="eu-test",
            name="EU Test",
            region=EdgeRegion.EU_WEST,
            coordinates=GeographicCoordinates(53.3498, -6.2603),
            capabilities=EdgeCapabilities(
                cpu_cores=4,
                memory_gb=16,
                storage_gb=100,
                encryption_at_rest=True,
                audit_logging=True,
            ),
            compliance_zones=[ComplianceZone.GDPR, ComplianceZone.PUBLIC],
        )

        # Test GDPR compliance routing
        gdpr_context = ComplianceContext(
            data_classification=DataClassification.EU_PERSONAL,
            operation_type="process",
            subject_countries=["DE"],
        )

        decision = await router.route_compliant(
            gdpr_context, [us_location, eu_location]
        )

        # Should only allow EU location
        assert len(decision.allowed_locations) == 1
        assert decision.allowed_locations[0].location_id == "eu-test"
        assert len(decision.prohibited_locations) == 1
        assert decision.recommended_location.location_id == "eu-test"

    def test_compliance_requirements(self):
        """Test compliance requirement determination."""
        router = ComplianceRouter()

        # Test GDPR requirements
        gdpr_zones = router.get_applicable_regulations(DataClassification.EU_PERSONAL)
        assert ComplianceZone.GDPR in gdpr_zones

        # Test HIPAA requirements
        hipaa_zones = router.get_applicable_regulations(DataClassification.PHI)
        assert ComplianceZone.HIPAA in hipaa_zones

        # Test PCI requirements
        pci_zones = router.get_applicable_regulations(DataClassification.PCI)
        assert ComplianceZone.PCI_DSS in pci_zones


@pytest.mark.asyncio
async def test_edge_integration():
    """Test integration between edge components."""
    # Create locations
    locations = [
        get_predefined_location("us-east-1"),
        get_predefined_location("eu-west-1"),
    ]

    # Create discovery service
    discovery = EdgeDiscovery(locations=locations)

    # Create compliance router
    router = ComplianceRouter()

    # Test integrated flow: Find GDPR-compliant edge for EU user
    eu_coords = GeographicCoordinates(52.5200, 13.4050)  # Berlin

    # First, get compliance requirements
    context = ComplianceContext(
        data_classification=DataClassification.EU_PERSONAL,
        user_location=eu_coords,
        subject_countries=["DE"],
    )

    compliance_decision = await router.route_compliant(context, locations)

    # Then, find optimal edge from compliant locations
    request = EdgeDiscoveryRequest(
        user_coordinates=eu_coords,
        compliance_zones=[ComplianceZone.GDPR],
        selection_strategy=EdgeSelectionStrategy.BALANCED,
        max_results=1,
    )

    optimal_edges = await discovery.discover_optimal_edges(request)

    # Should find EU location as optimal
    assert len(optimal_edges) == 1
    assert optimal_edges[0].location.region == EdgeRegion.EU_WEST

    # Should match compliance decision
    assert optimal_edges[0].location.location_id in [
        loc.location_id for loc in compliance_decision.allowed_locations
    ]
