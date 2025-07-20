"""Edge resource management components."""

from .resource_analyzer import ResourceAnalyzer, ResourceMetric, ResourceType
from .resource_pools import ResourcePool, ResourceRequest, AllocationResult
from .predictive_scaler import (
    PredictiveScaler,
    ScalingStrategy,
    PredictionHorizon,
    ScalingPrediction,
    ScalingDecision,
)
from .cost_optimizer import (
    CostOptimizer,
    CloudProvider,
    InstanceType,
    OptimizationStrategy,
    CostMetric,
    CostOptimization,
)

# Phase 4.4 Integration & Testing components
from .kubernetes_integration import (
    KubernetesIntegration,
    KubernetesResource,
    KubernetesResourceType,
    PodScalingSpec,
    ScalingPolicy,
)
from .docker_integration import (
    DockerIntegration,
    ContainerSpec,
    ServiceSpec,
    ContainerState,
    RestartPolicyType,
    NetworkMode,
    ContainerMetrics,
)
from .cloud_integration import (
    CloudIntegration,
    CloudProvider as CloudProviderType,
    InstanceSpec,
    InstanceState,
    CloudInstance,
    CloudMetrics,
)
from .platform_integration import (
    PlatformIntegration,
    PlatformType,
    ResourceScope,
    ResourceRequest as PlatformResourceRequest,
    ResourceAllocation,
    PlatformConfig,
)

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
