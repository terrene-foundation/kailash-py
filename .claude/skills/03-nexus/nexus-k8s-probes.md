# Nexus K8s Probes + OpenAPI + Security Middleware

## K8s Probe Endpoints

```python
from nexus import ProbeManager, ProbeState

probe_mgr = ProbeManager()
probe_mgr.install(app)  # registers GET /healthz, /readyz, /startup

# State management (thread-safe, atomic)
probe_mgr.mark_ready()             # STARTING -> READY
probe_mgr.mark_draining()          # READY -> DRAINING
probe_mgr.mark_failed("db down")   # any -> FAILED
```

### Readiness Callbacks

```python
probe_mgr.add_readiness_check(lambda: db.is_connected())
```

## OpenAPI Generation

```python
from nexus import OpenApiGenerator

gen = OpenApiGenerator(title="My API", version="1.0.0")
gen.add_handler("/process", handler_fn)  # auto-derives schema from type hints
spec = gen.generate()  # OpenAPI 3.0.3 dict
# Auto-endpoint: GET /openapi.json
```

## Security Headers Middleware

```python
from nexus.middleware.security_headers import SecurityHeadersMiddleware, SecurityHeadersConfig

config = SecurityHeadersConfig(
    csp="default-src 'self'",
    hsts_max_age=31536000,
    x_frame_options="DENY",
)
# Applies: CSP, HSTS, X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy
```

## CSRF Middleware

```python
from nexus.middleware.csrf import CSRFMiddleware

csrf = CSRFMiddleware(
    allowed_origins=["https://app.example.com"],
    exempt_paths=["/api/webhooks"],
)
# Validates Origin/Referer on POST/PUT/DELETE/PATCH. GET/HEAD/OPTIONS bypass.
```

## Middleware Presets

```python
from nexus import Nexus

app = Nexus([workflow], preset="standard")
# "none": no middleware
# "lightweight": security headers
# "standard": + CSRF + CORS + rate limiting
# "saas": + tenant isolation
# "enterprise": + audit logging
```

## Source Files

- `packages/kailash-nexus/src/nexus/probes.py`
- `packages/kailash-nexus/src/nexus/openapi.py`
- `packages/kailash-nexus/src/nexus/middleware/security_headers.py`
- `packages/kailash-nexus/src/nexus/middleware/csrf.py`
- `packages/kailash-nexus/src/nexus/presets.py`
