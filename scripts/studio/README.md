# Studio Scripts

Scripts for managing Kailash Studio - the visual workflow builder and management interface.

## 📁 Scripts Overview

| Script | Purpose | Mode | Port |
|--------|---------|------|------|
| `start-studio.sh` | Start Studio in production mode | Production | 3000 |
| `start-studio-dev.sh` | Start Studio in development mode | Development | 3001 |
| `start-runner-service.sh` | Start workflow runner service | Service | 8080 |
| `start-runner-foreground.sh` | Start runner in foreground | Debug | 8080 |

## 🚀 Quick Start

### Development Mode
```bash
# Start Studio for development
./start-studio-dev.sh

# Studio available at http://localhost:3001
```

### Production Mode
```bash
# Start Studio and runner service
./start-studio.sh
./start-runner-service.sh

# Studio available at http://localhost:3000
# Runner API at http://localhost:8080
```

## 📋 Script Details

### `start-studio.sh`
**Purpose**: Start Kailash Studio in production mode

**Features**:
- Production build
- Optimized performance
- SSL/TLS support
- Authentication integration

**Usage**:
```bash
# Start production Studio
./start-studio.sh

# Custom port
./start-studio.sh --port 8080

# With SSL
./start-studio.sh --ssl --cert-path /path/to/cert
```

### `start-studio-dev.sh`
**Purpose**: Start Studio in development mode with hot reload

**Features**:
- Hot module replacement
- Development tools
- Debug mode
- API proxy to backend

**Usage**:
```bash
# Start development Studio
./start-studio-dev.sh

# Custom backend URL
./start-studio-dev.sh --backend http://localhost:8000
```

### `start-runner-service.sh`
**Purpose**: Start workflow runner as background service

**Features**:
- Background daemon mode
- Process management
- Log rotation
- Health monitoring

**Usage**:
```bash
# Start as service
./start-runner-service.sh

# Check status
./start-runner-service.sh status

# Stop service
./start-runner-service.sh stop
```

### `start-runner-foreground.sh`
**Purpose**: Start runner in foreground for debugging

**Features**:
- Console output
- Debug logging
- Interactive mode
- Easy termination

**Usage**:
```bash
# Start in foreground
./start-runner-foreground.sh

# With debug logging
./start-runner-foreground.sh --debug

# Custom log level
./start-runner-foreground.sh --log-level debug
```

## 🔧 Configuration

### Environment Variables
```bash
# Studio configuration
STUDIO_PORT=3000
STUDIO_API_URL=http://localhost:8080
STUDIO_AUTH_ENABLED=true

# Runner configuration
RUNNER_PORT=8080
RUNNER_WORKERS=4
RUNNER_LOG_LEVEL=info
```

### Service Architecture
```
┌─────────────────┐    ┌─────────────────┐
│  Kailash Studio │────│ Workflow Runner │
│   (Frontend)    │    │   (Backend)     │
│   Port 3000     │    │   Port 8080     │
└─────────────────┘    └─────────────────┘
         │                       │
         └───────────────────────┼──────── User Workflows
                                 │
                        ┌─────────────────┐
                        │ SDK Development │
                        │   Environment   │
                        │  (Databases)    │
                        └─────────────────┘
```

## 🐛 Troubleshooting

### Common Issues

**Port conflicts**:
```bash
# Check what's using the port
lsof -i :3000

# Kill conflicting process
kill -9 $(lsof -t -i:3000)
```

**Node.js issues**:
```bash
# Clear npm cache
npm cache clean --force

# Reinstall dependencies
rm -rf node_modules package-lock.json
npm install
```

**Runner connection issues**:
```bash
# Check runner status
curl http://localhost:8080/health

# Verify development environment
../development/check-status.sh
```

### Performance Issues

**Slow Studio startup**:
- Increase Node.js memory: `export NODE_OPTIONS="--max-old-space-size=4096"`
- Use production build for better performance
- Clear browser cache

**Runner performance**:
- Adjust worker count: `--workers 8`
- Monitor resource usage: `htop`
- Check database connections

## 💡 Development Workflow

### Frontend Development
```bash
# Start development environment
../development/start-development.sh

# Start Studio in dev mode
./start-studio-dev.sh

# Start runner for API
./start-runner-foreground.sh --debug
```

### Testing Studio Features
```bash
# Run Studio tests
npm test

# End-to-end tests
npm run e2e

# Visual regression tests
npm run visual-test
```

### Production Deployment
```bash
# Build production assets
npm run build

# Start production services
./start-studio.sh
./start-runner-service.sh

# Verify deployment
curl http://localhost:3000/health
```

## 🤝 Contributing

### Adding New Features
1. Develop using `start-studio-dev.sh`
2. Test with `start-runner-foreground.sh`
3. Validate in production mode
4. Update documentation

### Debugging Issues
- Use foreground runner for detailed logs
- Enable debug mode in Studio
- Check browser developer tools
- Monitor backend API calls

---

**Dependencies**: Node.js 16+, npm, development environment
**Ports Used**: 3000 (Studio), 3001 (Studio Dev), 8080 (Runner)
**Last Updated**: Scripts directory reorganization
