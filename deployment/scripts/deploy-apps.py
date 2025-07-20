#!/usr/bin/env python3
"""
Dynamic multi-app deployment script
Automatically discovers and deploys apps from the apps/ directory
"""

import os
import sys
import yaml
import subprocess
import argparse
from pathlib import Path
from typing import Dict, List, Optional


class AppDiscovery:
    """Discovers and manages app deployments"""
    
    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.apps_path = root_path / "apps"
        self.deployment_path = root_path / "deployment"
        
    def discover_apps(self) -> List[Dict]:
        """Discover all deployable apps"""
        apps = []
        
        if not self.apps_path.exists():
            print("❌ Apps directory not found")
            return apps
            
        for app_dir in self.apps_path.iterdir():
            if app_dir.is_dir() and not app_dir.name.startswith('_'):
                manifest_path = app_dir / "manifest.yaml"
                if manifest_path.exists():
                    try:
                        with open(manifest_path) as f:
                            manifest = yaml.safe_load(f)
                        
                        app_info = {
                            "name": app_dir.name,
                            "path": app_dir,
                            "manifest": manifest,
                            "type": manifest.get("type", "api"),
                            "enabled": manifest.get("deployment", {}).get("enabled", True)
                        }
                        apps.append(app_info)
                        print(f"✅ Discovered app: {app_dir.name}")
                    except Exception as e:
                        print(f"⚠️  Failed to load manifest for {app_dir.name}: {e}")
                        
        return apps
    
    def generate_docker_compose(self, apps: List[Dict], output_file: Path):
        """Generate dynamic docker-compose with discovered apps"""
        
        # Load base compose file
        base_compose_path = self.deployment_path / "docker" / "docker-compose.dynamic.yml"
        with open(base_compose_path) as f:
            compose_config = yaml.safe_load(f)
        
        # Add services for each app
        for app in apps:
            if not app["enabled"]:
                continue
                
            manifest = app["manifest"]
            app_name = app["name"].replace("_", "-")
            
            # Generate service configuration
            service_config = {
                "build": {
                    "context": "../..",
                    "dockerfile": f"deployment/docker/services/Dockerfile.{app_name}",
                    "args": {
                        "APP_NAME": app["name"]
                    }
                },
                "environment": self._get_app_environment(manifest),
                "depends_on": self._get_app_dependencies(manifest),
                "healthcheck": {
                    "test": ["CMD", "curl", "-f", f"http://localhost:{manifest.get('capabilities', {}).get('api', {}).get('port', 8000)}/health"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3
                },
                "networks": ["default"],
                "restart": "unless-stopped"
            }
            
            # Add port mapping if API enabled
            if manifest.get("capabilities", {}).get("api", {}).get("enabled"):
                port = manifest["capabilities"]["api"]["port"]
                service_config["ports"] = [f"${{{app_name.upper()}_PORT:-{port}}}:{port}"]
            
            # Add volumes if specified
            if "volumes" in manifest.get("deployment", {}):
                service_config["volumes"] = manifest["deployment"]["volumes"]
            
            compose_config["services"][app_name] = service_config
        
        # Write the generated compose file
        with open(output_file, 'w') as f:
            yaml.dump(compose_config, f, default_flow_style=False, indent=2)
        
        print(f"📝 Generated docker-compose.yml with {len([app for app in apps if app['enabled']])} apps")
    
    def _get_app_environment(self, manifest: Dict) -> List[str]:
        """Extract environment variables for an app"""
        env_vars = [
            "LOG_LEVEL=${LOG_LEVEL:-INFO}",
            "POSTGRES_URL=postgresql://kailash:${POSTGRES_PASSWORD:-kailash_secure}@postgres:5432/kailash_platform",
            "REDIS_URL=redis://redis:6379"
        ]
        
        # Add app-specific environment variables
        deployment_env = manifest.get("deployment", {}).get("environment", [])
        env_vars.extend(deployment_env)
        
        return env_vars
    
    def _get_app_dependencies(self, manifest: Dict) -> Dict:
        """Get service dependencies for an app"""
        dependencies = {
            "postgres": {"condition": "service_healthy"},
            "redis": {"condition": "service_healthy"}
        }
        
        # Add optional dependencies if specified
        optional_deps = manifest.get("dependencies", {}).get("optional", [])
        for dep in optional_deps:
            if dep not in dependencies:
                dependencies[dep] = {"condition": "service_healthy"}
        
        return dependencies
    
    def generate_dockerfiles(self, apps: List[Dict]):
        """Generate individual Dockerfiles for each app"""
        services_path = self.deployment_path / "docker" / "services"
        services_path.mkdir(exist_ok=True)
        
        dockerfile_template = self.deployment_path / "docker" / "Dockerfile.template"
        
        for app in apps:
            if not app["enabled"]:
                continue
                
            app_name = app["name"].replace("_", "-")
            dockerfile_path = services_path / f"Dockerfile.{app_name}"
            
            # Read template
            with open(dockerfile_template) as f:
                dockerfile_content = f.read()
            
            # Customize for specific app
            manifest = app["manifest"]
            
            # Add app-specific modifications
            dockerfile_content += f"\n# App-specific configuration for {app['name']}\n"
            dockerfile_content += f"WORKDIR /app/apps/{app['name']}\n"
            
            # Add custom command if specified
            if "command" in manifest.get("deployment", {}):
                custom_cmd = manifest["deployment"]["command"]
                dockerfile_content += f'CMD {custom_cmd}\n'
            else:
                # Default command based on app type
                if manifest.get("type") == "mcp":
                    dockerfile_content += f'CMD ["python", "-m", "apps.{app["name"]}.main"]\n'
                else:
                    port = manifest.get("capabilities", {}).get("api", {}).get("port", 8000)
                    dockerfile_content += f'CMD ["python", "-m", "uvicorn", "apps.{app["name"]}.main:app", "--host", "0.0.0.0", "--port", "{port}"]\n'
            
            with open(dockerfile_path, 'w') as f:
                f.write(dockerfile_content)
            
            print(f"🐳 Generated Dockerfile for {app['name']}")
    
    def generate_kubernetes_manifests(self, apps: List[Dict]):
        """Generate Kubernetes manifests for discovered apps"""
        k8s_apps_path = self.deployment_path / "kubernetes" / "apps"
        
        for app in apps:
            if not app["enabled"]:
                continue
                
            app_name = app["name"].replace("_", "-")
            app_k8s_path = k8s_apps_path / app_name
            app_k8s_path.mkdir(parents=True, exist_ok=True)
            
            manifest = app["manifest"]
            
            # Generate deployment manifest
            self._generate_k8s_deployment(app, app_k8s_path)
            self._generate_k8s_service(app, app_k8s_path)
            self._generate_k8s_configmap(app, app_k8s_path)
            
            if manifest.get("capabilities", {}).get("api", {}).get("enabled"):
                self._generate_k8s_ingress(app, app_k8s_path)
            
            print(f"☸️  Generated Kubernetes manifests for {app['name']}")
    
    def _generate_k8s_deployment(self, app: Dict, output_path: Path):
        """Generate Kubernetes deployment manifest"""
        app_name = app["name"].replace("_", "-")
        manifest = app["manifest"]
        
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": app_name,
                "namespace": "kailash-platform",
                "labels": {
                    "app": app_name,
                    "component": "application",
                    "type": manifest.get("type", "api")
                }
            },
            "spec": {
                "replicas": "${REPLICAS:-1}",
                "selector": {
                    "matchLabels": {
                        "app": app_name
                    }
                },
                "template": {
                    "metadata": {
                        "labels": {
                            "app": app_name,
                            "component": "application",
                            "type": manifest.get("type", "api")
                        }
                    },
                    "spec": {
                        "containers": [{
                            "name": app_name,
                            "image": f"kailash-platform/{app_name}:latest",
                            "ports": [{
                                "containerPort": manifest.get("capabilities", {}).get("api", {}).get("port", 8000),
                                "name": "http"
                            }],
                            "env": [
                                {"name": "LOG_LEVEL", "value": "${LOG_LEVEL:-INFO}"},
                                {"name": "POSTGRES_URL", "valueFrom": {"secretKeyRef": {"name": "database-secret", "key": "url"}}},
                                {"name": "REDIS_URL", "valueFrom": {"secretKeyRef": {"name": "redis-secret", "key": "url"}}}
                            ],
                            "resources": {
                                "requests": {
                                    "memory": "256Mi",
                                    "cpu": "100m"
                                },
                                "limits": {
                                    "memory": "512Mi",
                                    "cpu": "500m"
                                }
                            },
                            "livenessProbe": {
                                "httpGet": {
                                    "path": "/health",
                                    "port": "http"
                                },
                                "initialDelaySeconds": 30,
                                "periodSeconds": 10
                            },
                            "readinessProbe": {
                                "httpGet": {
                                    "path": "/health",
                                    "port": "http"
                                },
                                "initialDelaySeconds": 5,
                                "periodSeconds": 5
                            }
                        }]
                    }
                }
            }
        }
        
        with open(output_path / "deployment.yaml", 'w') as f:
            yaml.dump(deployment, f, default_flow_style=False, indent=2)
    
    def _generate_k8s_service(self, app: Dict, output_path: Path):
        """Generate Kubernetes service manifest"""
        app_name = app["name"].replace("_", "-")
        manifest = app["manifest"]
        
        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": app_name,
                "namespace": "kailash-platform",
                "labels": {
                    "app": app_name,
                    "component": "application"
                }
            },
            "spec": {
                "selector": {
                    "app": app_name
                },
                "ports": [{
                    "port": 80,
                    "targetPort": manifest.get("capabilities", {}).get("api", {}).get("port", 8000),
                    "protocol": "TCP",
                    "name": "http"
                }],
                "type": "ClusterIP"
            }
        }
        
        with open(output_path / "service.yaml", 'w') as f:
            yaml.dump(service, f, default_flow_style=False, indent=2)
    
    def _generate_k8s_configmap(self, app: Dict, output_path: Path):
        """Generate Kubernetes ConfigMap manifest"""
        app_name = app["name"].replace("_", "-")
        
        configmap = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": f"{app_name}-config",
                "namespace": "kailash-platform"
            },
            "data": {
                "LOG_LEVEL": "INFO",
                "APP_NAME": app["name"],
                "APP_TYPE": app["manifest"].get("type", "api")
            }
        }
        
        with open(output_path / "configmap.yaml", 'w') as f:
            yaml.dump(configmap, f, default_flow_style=False, indent=2)
    
    def _generate_k8s_ingress(self, app: Dict, output_path: Path):
        """Generate Kubernetes Ingress manifest"""
        app_name = app["name"].replace("_", "-")
        
        ingress = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "Ingress",
            "metadata": {
                "name": app_name,
                "namespace": "kailash-platform",
                "annotations": {
                    "nginx.ingress.kubernetes.io/rewrite-target": "/",
                    "kubernetes.io/ingress.class": "nginx"
                }
            },
            "spec": {
                "rules": [{
                    "host": f"{app_name}.${DOMAIN:-localhost}",
                    "http": {
                        "paths": [{
                            "path": "/",
                            "pathType": "Prefix",
                            "backend": {
                                "service": {
                                    "name": app_name,
                                    "port": {
                                        "number": 80
                                    }
                                }
                            }
                        }]
                    }
                }]
            }
        }
        
        with open(output_path / "ingress.yaml", 'w') as f:
            yaml.dump(ingress, f, default_flow_style=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Deploy multi-app Kailash platform")
    parser.add_argument("--mode", choices=["docker", "kubernetes", "both"], default="both",
                       help="Deployment mode")
    parser.add_argument("--output-dir", type=Path, help="Output directory for generated files")
    parser.add_argument("--dry-run", action="store_true", help="Generate configs without deploying")
    
    args = parser.parse_args()
    
    # Find project root
    current_path = Path.cwd()
    while current_path != current_path.parent:
        if (current_path / "pyproject.toml").exists():
            break
        current_path = current_path.parent
    else:
        print("❌ Could not find project root (pyproject.toml not found)")
        sys.exit(1)
    
    discovery = AppDiscovery(current_path)
    apps = discovery.discover_apps()
    
    if not apps:
        print("❌ No deployable apps found")
        sys.exit(1)
    
    print(f"🚀 Found {len(apps)} deployable apps")
    
    output_dir = args.output_dir or current_path / "deployment"
    
    if args.mode in ["docker", "both"]:
        print("\n🐳 Generating Docker configurations...")
        discovery.generate_dockerfiles(apps)
        compose_output = output_dir / "docker" / "docker-compose.generated.yml"
        discovery.generate_docker_compose(apps, compose_output)
        
        if not args.dry_run:
            print("🚀 Starting Docker deployment...")
            result = subprocess.run([
                "docker-compose", "-f", str(compose_output), "up", "-d"
            ], cwd=output_dir / "docker")
            
            if result.returncode == 0:
                print("✅ Docker deployment successful")
            else:
                print("❌ Docker deployment failed")
    
    if args.mode in ["kubernetes", "both"]:
        print("\n☸️  Generating Kubernetes configurations...")
        discovery.generate_kubernetes_manifests(apps)
        
        if not args.dry_run:
            print("🚀 Deploying to Kubernetes...")
            k8s_path = output_dir / "kubernetes"
            
            # Deploy infrastructure first
            subprocess.run(["kubectl", "apply", "-f", str(k8s_path / "infrastructure")])
            
            # Deploy apps
            subprocess.run(["kubectl", "apply", "-f", str(k8s_path / "apps")], recursive=True)
            
            print("✅ Kubernetes deployment successful")
    
    print("\n🎉 Deployment complete!")
    print(f"📊 Deployed {len([app for app in apps if app['enabled']])} apps")


if __name__ == "__main__":
    main()