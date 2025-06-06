# Kailash Workflow Studio

A visual workflow builder for the Kailash Python SDK, providing an intuitive drag-and-drop interface for creating, editing, and managing workflows.

## Overview

Kailash Workflow Studio is a React-based web application that allows users to:
- Visually design workflows using drag-and-drop
- Configure nodes with intuitive forms
- Test workflows in real-time
- Export workflows as Python code or YAML
- Monitor workflow execution with live updates

## Directory Structure

```
studio/
├── src/                    # Source code
│   ├── index.jsx          # Application entry point
│   ├── App.jsx            # Main application component
│   ├── elements/          # High-level components
│   ├── components/        # Reusable UI components
│   ├── services/          # API integration layer
│   ├── store/             # State management (Zustand/Redux)
│   ├── hooks/             # Custom React hooks
│   ├── utils/             # Utility functions
│   └── styles/            # Global styles and themes
├── public/                # Static assets
├── tests/                 # Test suites
└── docs/                  # Studio-specific documentation
```

## Technology Stack

- **React 18** with TypeScript
- **Tanstack React Query** for API state management
- **Zustand** for local state management
- **React Flow** for workflow visualization
- **Shadcn/ui** for UI components
- **Tailwind CSS** for styling
- **Vite** for build tooling

## Getting Started

### Prerequisites

- Node.js 18+
- npm or yarn
- Kailash Python SDK backend running

### Installation

```bash
cd studio
npm install
```

### Development

```bash
npm run dev
```

### Building

```bash
npm run build
```

## Architecture

The application follows the guidelines in `guide/frontend/`:
- Component-based architecture with separation of concerns
- API integration through React Query
- Responsive design for mobile and desktop
- Comprehensive error handling and loading states

## Integration with Kailash SDK

The studio communicates with the Kailash Python SDK through:
- REST API for workflow management
- WebSocket for real-time execution updates
- Export functionality for Python/YAML code generation

For detailed frontend development guidelines, see `../guide/frontend/`.
