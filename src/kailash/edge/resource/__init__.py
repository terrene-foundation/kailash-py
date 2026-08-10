"""Edge resource management components."""

from .cloud_integration import CloudInstance, CloudIntegration, CloudMetrics
from .cloud_integration import CloudProvider as CloudProviderType
from .cloud_integration import InstanceSpec, InstanceState
from .cost_optimizer import (
    CloudProvider,
    CostMetric,
    CostOptimization,
    CostOptimizer,
    InstanceType,
    OptimizationStrategy,
)
from .docker_integration import (
    ContainerMetrics,
    ContainerSpec,
    ContainerState,
    DockerIntegration,
    NetworkMode,
    RestartPolicyType,
    ServiceSpec,
)

# Phase 4.4 Integration & Testing components
from .kubernetes_integration import (
    KubernetesIntegration,
    KubernetesResource,
    KubernetesResourceType,
    PodScalingSpec,
    ScalingPolicy,
)
from .platform_integration import (
    PlatformConfig,
    PlatformIntegration,
    PlatformType,
    ResourceAllocation,
)
from .platform_integration import ResourceRequest as PlatformResourceRequest
from .platform_integration import ResourceScope
from .predictive_scaler import (
    PredictionHorizon,
    PredictiveScaler,
    ScalingDecision,
    ScalingPrediction,
    ScalingStrategy,
)
from .resource_analyzer import ResourceAnalyzer, ResourceMetric, ResourceType
from .resource_pools import AllocationResult, ResourcePool, ResourceRequest

__all__ = [
    "ResourceAnalyzer",
    "ResourceMetric",
    "ResourceType",
    "ResourcePool",
    "ResourceRequest",
    "AllocationResult",
    "PredictiveScaler",
    "ScalingStrategy",
    "PredictionHorizon",
    "ScalingPrediction",
    "ScalingDecision",
    "CostOptimizer",
    "CloudProvider",
    "InstanceType",
    "OptimizationStrategy",
    "CostMetric",
    "CostOptimization",
    # Phase 4.4 components
    "KubernetesIntegration",
    "KubernetesResource",
    "KubernetesResourceType",
    "PodScalingSpec",
    "ScalingPolicy",
    "DockerIntegration",
    "ContainerSpec",
    "ServiceSpec",
    "ContainerState",
    "RestartPolicyType",
    "NetworkMode",
    "ContainerMetrics",
    "CloudIntegration",
    "CloudProviderType",
    "InstanceSpec",
    "InstanceState",
    "CloudInstance",
    "CloudMetrics",
    "PlatformIntegration",
    "PlatformType",
    "ResourceScope",
    "PlatformResourceRequest",
    "ResourceAllocation",
    "PlatformConfig",
]
