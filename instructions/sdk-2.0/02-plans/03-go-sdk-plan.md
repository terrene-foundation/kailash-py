# Go SDK Plan

## 1. Overview

The Go SDK (`kailash-go`) is the second language binding, targeting Go developers who need
workflow automation with idiomatic Go patterns. It wraps the shared Rust core via CGo and
implements DataFlow-Go, Nexus-Go, and Kaizen-Go using native Go libraries.

## 2. Module Structure

```
github.com/kailash-sdk/kailash-go/
+-- go.mod
+-- go.sum
+-- core/                       # CGo bindings to Rust core
|   +-- core.go                 # Low-level CGo wrapper
|   +-- core_test.go
|   +-- graph.go                # Go-friendly graph API
|   +-- runtime.go              # Go-friendly runtime API
|   +-- types.go                # Go type definitions
|   +-- errors.go               # Error types
|   +-- lib/                    # Pre-built Rust shared libraries
|       +-- linux_amd64/
|       |   +-- libkailash_ffi.so
|       +-- linux_arm64/
|       |   +-- libkailash_ffi.so
|       +-- darwin_amd64/
|       |   +-- libkailash_ffi.dylib
|       +-- darwin_arm64/
|       |   +-- libkailash_ffi.dylib
|       +-- windows_amd64/
|           +-- kailash_ffi.dll
+-- workflow/                   # Workflow builder (Go-idiomatic)
|   +-- builder.go
|   +-- builder_test.go
|   +-- workflow.go
|   +-- node.go
|   +-- connection.go
+-- runtime/                    # Runtime implementations
|   +-- local.go                # Synchronous runtime
|   +-- async.go                # Goroutine-based async runtime
|   +-- runtime.go              # Runtime interface
|   +-- runtime_test.go
+-- nodes/                      # Base node types
|   +-- node.go                 # Node interface
|   +-- registry.go             # Node registry
|   +-- parameter.go            # Parameter definitions
+-- dataflow/                   # DataFlow framework
|   +-- dataflow.go             # Main DataFlow engine
|   +-- model.go                # Model definition
|   +-- operations.go           # CRUD operations
|   +-- bulk.go                 # Bulk operations
|   +-- filter.go               # Query filters
|   +-- migration.go            # Schema migration
|   +-- drivers/
|       +-- postgres.go         # PostgreSQL driver
|       +-- sqlite.go           # SQLite driver
|       +-- mysql.go            # MySQL driver
+-- nexus/                      # Nexus framework
|   +-- nexus.go                # Main Nexus app
|   +-- handler.go              # Handler registration
|   +-- middleware.go           # Middleware support
|   +-- api.go                  # REST API channel
|   +-- cli.go                  # CLI channel
|   +-- mcp.go                  # MCP channel
|   +-- auth/
|       +-- plugin.go           # Auth plugin
|       +-- jwt.go              # JWT support
+-- kaizen/                     # Kaizen framework
|   +-- agent.go                # Agent implementation
|   +-- config.go               # Agent configuration
|   +-- strategy.go             # Execution strategies
|   +-- memory.go               # Memory providers
|   +-- tools.go                # Tool registration
|   +-- providers/
|       +-- openai.go           # OpenAI provider
|       +-- anthropic.go        # Anthropic provider
+-- examples/
    +-- basic_workflow/
    +-- dataflow_crud/
    +-- nexus_api/
    +-- kaizen_agent/
```

## 3. CGo Bindings to Rust Core

### 3.1 CGo Wrapper

```go
// core/core.go
package core

/*
#cgo LDFLAGS: -L${SRCDIR}/lib/${GOOS}_${GOARCH} -lkailash_ffi
#include "kailash_ffi.h"

// Callback wrapper for node execution
extern int go_execute_node_callback(void* ctx, const char* node_id,
    const char* node_type, const char* inputs_json, size_t inputs_len,
    char** output_json, size_t* output_len, char** error_msg);
*/
import "C"
import (
    "encoding/json"
    "fmt"
    "runtime"
    "sync"
    "unsafe"
)

// WorkflowHandle wraps the Rust WorkflowGraph opaque pointer
type WorkflowHandle struct {
    ptr    unsafe.Pointer
    mu     sync.Mutex
    closed bool
}

// NewWorkflow creates a new workflow graph via Rust core
func NewWorkflow(id, name string) (*WorkflowHandle, error) {
    cID := C.CString(id)
    defer C.free(unsafe.Pointer(cID))
    cName := C.CString(name)
    defer C.free(unsafe.Pointer(cName))

    ptr := C.kailash_create_workflow(cID, cName)
    if ptr == nil {
        return nil, fmt.Errorf("kailash: failed to create workflow")
    }

    h := &WorkflowHandle{ptr: ptr}
    runtime.SetFinalizer(h, (*WorkflowHandle).Close)
    return h, nil
}

// AddNode adds a node to the workflow graph
func (h *WorkflowHandle) AddNode(nodeID, nodeType string, config map[string]interface{}, isAsync bool) error {
    h.mu.Lock()
    defer h.mu.Unlock()

    configJSON, err := json.Marshal(config)
    if err != nil {
        return fmt.Errorf("kailash: marshal config: %w", err)
    }

    cNodeID := C.CString(nodeID)
    defer C.free(unsafe.Pointer(cNodeID))
    cNodeType := C.CString(nodeType)
    defer C.free(unsafe.Pointer(cNodeType))
    cConfig := C.CString(string(configJSON))
    defer C.free(unsafe.Pointer(cConfig))

    var cAsync C.int
    if isAsync {
        cAsync = 1
    }

    result := C.kailash_add_node(h.ptr, cNodeID, cNodeType, cConfig, C.size_t(len(configJSON)), cAsync)
    if result != 0 {
        return h.getLastError()
    }
    return nil
}

// TopologicalSort returns nodes in execution order
func (h *WorkflowHandle) TopologicalSort() ([]string, error) {
    h.mu.Lock()
    defer h.mu.Unlock()

    var resultPtr *C.char
    var resultLen C.size_t

    status := C.kailash_topological_sort(h.ptr, &resultPtr, &resultLen)
    if status != 0 {
        return nil, h.getLastError()
    }
    defer C.kailash_free_string(resultPtr)

    resultJSON := C.GoStringN(resultPtr, C.int(resultLen))
    var order []string
    if err := json.Unmarshal([]byte(resultJSON), &order); err != nil {
        return nil, fmt.Errorf("kailash: unmarshal sort result: %w", err)
    }
    return order, nil
}

// Close frees the Rust workflow graph
func (h *WorkflowHandle) Close() error {
    h.mu.Lock()
    defer h.mu.Unlock()
    if h.closed {
        return nil
    }
    C.kailash_free_workflow(h.ptr)
    h.closed = true
    return nil
}
```

### 3.2 Callback Mechanism

```go
// core/callback.go
package core

/*
#include "kailash_ffi.h"
*/
import "C"
import (
    "encoding/json"
    "sync"
    "unsafe"
)

// NodeExecutor is the interface that language-side node implementations satisfy
type NodeExecutor interface {
    ExecuteNode(nodeID, nodeType string, inputs map[string]interface{}) (map[string]interface{}, error)
}

// Global registry for callback context (CGo can't pass Go pointers directly)
var (
    callbackMu       sync.Mutex
    callbackRegistry = make(map[uintptr]NodeExecutor)
    nextCallbackID   uintptr
)

func registerCallback(executor NodeExecutor) uintptr {
    callbackMu.Lock()
    defer callbackMu.Unlock()
    nextCallbackID++
    callbackRegistry[nextCallbackID] = executor
    return nextCallbackID
}

func unregisterCallback(id uintptr) {
    callbackMu.Lock()
    defer callbackMu.Unlock()
    delete(callbackRegistry, id)
}

//export go_execute_node_callback
func go_execute_node_callback(
    ctx unsafe.Pointer,
    nodeID *C.char,
    nodeType *C.char,
    inputsJSON *C.char,
    inputsLen C.size_t,
    outputJSON **C.char,
    outputLen *C.size_t,
    errorMsg **C.char,
) C.int {
    id := uintptr(ctx)
    callbackMu.Lock()
    executor, ok := callbackRegistry[id]
    callbackMu.Unlock()

    if !ok {
        msg := C.CString("callback not registered")
        *errorMsg = msg
        return 1
    }

    goNodeID := C.GoString(nodeID)
    goNodeType := C.GoString(nodeType)
    goInputs := C.GoStringN(inputsJSON, C.int(inputsLen))

    var inputs map[string]interface{}
    if err := json.Unmarshal([]byte(goInputs), &inputs); err != nil {
        msg := C.CString(err.Error())
        *errorMsg = msg
        return 1
    }

    result, err := executor.ExecuteNode(goNodeID, goNodeType, inputs)
    if err != nil {
        msg := C.CString(err.Error())
        *errorMsg = msg
        return 1
    }

    resultBytes, err := json.Marshal(result)
    if err != nil {
        msg := C.CString(err.Error())
        *errorMsg = msg
        return 1
    }

    *outputJSON = C.CString(string(resultBytes))
    *outputLen = C.size_t(len(resultBytes))
    return 0
}
```

## 4. Idiomatic Go Patterns

### 4.1 Error Handling

```go
// All functions return (result, error)
result, err := runtime.Execute(workflow)
if err != nil {
    var validationErr *kailash.ValidationError
    if errors.As(err, &validationErr) {
        // Handle validation errors specifically
        for _, issue := range validationErr.Issues {
            log.Printf("Validation: %s (node: %s)", issue.Message, issue.NodeID)
        }
    }
    return err
}
```

### 4.2 Context Support

```go
// All long-running operations accept context.Context
ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
defer cancel()

result, err := runtime.ExecuteCtx(ctx, workflow)
if errors.Is(err, context.DeadlineExceeded) {
    log.Println("Workflow timed out")
}
```

### 4.3 Interfaces

```go
// nodes/node.go
package nodes

// Node is the interface all nodes must implement
type Node interface {
    // GetParameters returns parameter definitions
    GetParameters() map[string]Parameter

    // Execute runs the node with given inputs
    Execute(ctx context.Context, inputs map[string]interface{}) (map[string]interface{}, error)
}

// AsyncNode extends Node with async execution
type AsyncNode interface {
    Node
    ExecuteAsync(ctx context.Context, inputs map[string]interface{}) <-chan Result
}

// Result wraps output or error from async execution
type Result struct {
    Output map[string]interface{}
    Error  error
}
```

### 4.4 Builder Pattern

```go
// workflow/builder.go
package workflow

type Builder struct {
    core   *core.WorkflowHandle
    nodes  map[string]NodeConfig
    conns  []Connection
}

func NewBuilder() *Builder {
    return &Builder{
        nodes: make(map[string]NodeConfig),
    }
}

func (b *Builder) AddNode(nodeType, nodeID string, config map[string]interface{}) *Builder {
    b.nodes[nodeID] = NodeConfig{Type: nodeType, Config: config}
    return b  // Fluent API
}

func (b *Builder) Connect(sourceID, sourceOutput, targetID, targetInput string) *Builder {
    b.conns = append(b.conns, Connection{
        SourceNode: sourceID, SourceOutput: sourceOutput,
        TargetNode: targetID, TargetInput: targetInput,
    })
    return b  // Fluent API
}

func (b *Builder) Build() (*Workflow, error) {
    // Create Rust workflow graph
    h, err := core.NewWorkflow(uuid.New().String(), "workflow")
    if err != nil {
        return nil, err
    }

    for nodeID, config := range b.nodes {
        if err := h.AddNode(nodeID, config.Type, config.Config, false); err != nil {
            h.Close()
            return nil, fmt.Errorf("add node %s: %w", nodeID, err)
        }
    }

    for _, conn := range b.conns {
        if err := h.Connect(conn.SourceNode, conn.SourceOutput, conn.TargetNode, conn.TargetInput); err != nil {
            h.Close()
            return nil, fmt.Errorf("connect %s->%s: %w", conn.SourceNode, conn.TargetNode, err)
        }
    }

    return &Workflow{handle: h, nodes: b.nodes}, nil
}
```

## 5. DataFlow-Go Implementation

### 5.1 Model Definition

```go
// dataflow/model.go
package dataflow

import (
    "reflect"
)

// Model metadata extracted from struct tags
type Model struct {
    Name       string
    TableName  string
    Fields     []Field
    PrimaryKey string
}

type Field struct {
    Name       string
    Column     string
    Type       reflect.Type
    PrimaryKey bool
    Required   bool
    Unique     bool
    Default    interface{}
}

// Register analyzes a struct and creates model metadata + 11 operations
func (db *DataFlow) Register(model interface{}) error {
    t := reflect.TypeOf(model)
    if t.Kind() == reflect.Ptr {
        t = t.Elem()
    }

    m := &Model{
        Name:      t.Name(),
        TableName: toSnakeCase(t.Name()) + "s",
    }

    for i := 0; i < t.NumField(); i++ {
        field := t.Field(i)
        tag := field.Tag.Get("df")

        f := Field{
            Name:   field.Name,
            Column: toSnakeCase(field.Name),
            Type:   field.Type,
        }

        if tag != "" {
            parseTag(tag, &f)
        }
        if f.PrimaryKey {
            m.PrimaryKey = f.Column
        }
        m.Fields = append(m.Fields, f)
    }

    db.models[m.Name] = m

    // Auto-generate 11 operations
    db.generateOperations(m)
    return nil
}
```

### 5.2 Query Execution

```go
// dataflow/operations.go
package dataflow

import (
    "context"
    "database/sql"
    "fmt"
)

func (db *DataFlow) Create(model interface{}) (*Result, error) {
    return db.CreateCtx(context.Background(), model)
}

func (db *DataFlow) CreateCtx(ctx context.Context, model interface{}) (*Result, error) {
    m, values, err := db.extractModelValues(model)
    if err != nil {
        return nil, err
    }

    query := db.buildInsertQuery(m, values)
    result, err := db.db.ExecContext(ctx, query, values...)
    if err != nil {
        return nil, fmt.Errorf("dataflow: create %s: %w", m.Name, err)
    }

    id, _ := result.LastInsertId()
    return &Result{ID: id, RowsAffected: 1}, nil
}

func (db *DataFlow) List(model interface{}, filters ...Filter) (interface{}, error) {
    return db.ListCtx(context.Background(), model, filters...)
}

func (db *DataFlow) ListCtx(ctx context.Context, model interface{}, filters ...Filter) (interface{}, error) {
    m := db.getModel(model)
    query, args := db.buildSelectQuery(m, filters)

    rows, err := db.db.QueryContext(ctx, query, args...)
    if err != nil {
        return nil, fmt.Errorf("dataflow: list %s: %w", m.Name, err)
    }
    defer rows.Close()

    return db.scanRows(rows, model)
}
```

## 6. Nexus-Go Implementation

```go
// nexus/nexus.go
package nexus

import (
    "context"
    "fmt"
    "log/slog"
    "net/http"
    "os"
    "os/signal"
    "syscall"
)

type Nexus struct {
    handlers   map[string]*Handler
    middleware []Middleware
    plugins    []Plugin
    logger     *slog.Logger
    config     Config
}

func New(opts ...Option) *Nexus {
    n := &Nexus{
        handlers: make(map[string]*Handler),
        logger:   slog.Default(),
        config:   defaultConfig(),
    }
    for _, opt := range opts {
        opt(n)
    }
    return n
}

func (n *Nexus) Handle(name string, handler HandlerFunc, opts ...HandlerOption) {
    h := &Handler{
        Name:    name,
        Handler: handler,
    }
    for _, opt := range opts {
        opt(h)
    }
    n.handlers[name] = h
}

func (n *Nexus) Start() error {
    // Start API server
    mux := http.NewServeMux()
    for name, handler := range n.handlers {
        mux.HandleFunc("POST /"+name, n.wrapHandler(handler))
    }

    server := &http.Server{
        Addr:    fmt.Sprintf(":%d", n.config.Port),
        Handler: n.applyMiddleware(mux),
    }

    // Graceful shutdown
    stop := make(chan os.Signal, 1)
    signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)

    go func() {
        n.logger.Info("Nexus started", "port", n.config.Port)
        if err := server.ListenAndServe(); err != http.ErrServerClosed {
            n.logger.Error("Server error", "err", err)
        }
    }()

    <-stop
    ctx, cancel := context.WithTimeout(context.Background(), n.config.ShutdownTimeout)
    defer cancel()
    return server.Shutdown(ctx)
}
```

## 7. Kaizen-Go Implementation

```go
// kaizen/agent.go
package kaizen

import (
    "context"
    "fmt"
    "os"

    openai "github.com/sashabaranov/go-openai"
)

type Agent struct {
    config   AgentConfig
    client   *openai.Client
    memory   Memory
    tools    []Tool
}

func NewAgent(config AgentConfig) (*Agent, error) {
    apiKey := os.Getenv("OPENAI_API_KEY")
    if apiKey == "" {
        return nil, fmt.Errorf("kaizen: OPENAI_API_KEY not set")
    }

    client := openai.NewClient(apiKey)

    return &Agent{
        config: config,
        client: client,
        memory: newMemory(config.Memory),
    }, nil
}

func (a *Agent) Run(ctx context.Context, prompt string) (*AgentResult, error) {
    messages := a.memory.GetMessages()
    messages = append(messages, openai.ChatCompletionMessage{
        Role:    openai.ChatMessageRoleUser,
        Content: prompt,
    })

    resp, err := a.client.CreateChatCompletion(ctx, openai.ChatCompletionRequest{
        Model:    a.config.Model,
        Messages: messages,
        Tools:    a.convertTools(),
    })
    if err != nil {
        return nil, fmt.Errorf("kaizen: llm call: %w", err)
    }

    result := &AgentResult{
        Content: resp.Choices[0].Message.Content,
        Usage: Usage{
            PromptTokens:     resp.Usage.PromptTokens,
            CompletionTokens: resp.Usage.CompletionTokens,
        },
    }

    a.memory.AddMessage(openai.ChatCompletionMessage{
        Role:    openai.ChatMessageRoleAssistant,
        Content: result.Content,
    })

    return result, nil
}
```

## 8. Build & Distribution

### 8.1 Go Module

```
// go.mod
module github.com/kailash-sdk/kailash-go

go 1.22

require (
    github.com/google/uuid v1.6.0
    github.com/sashabaranov/go-openai v1.28.0
    github.com/mattn/go-sqlite3 v1.14.22
    github.com/lib/pq v1.10.9
)
```

### 8.2 Pre-built Rust Libraries

The Go module ships with pre-built Rust shared libraries for all platforms.
Users do not need Rust installed:

```go
// core/core.go
// #cgo linux,amd64 LDFLAGS: -L${SRCDIR}/lib/linux_amd64 -lkailash_ffi
// #cgo linux,arm64 LDFLAGS: -L${SRCDIR}/lib/linux_arm64 -lkailash_ffi
// #cgo darwin,amd64 LDFLAGS: -L${SRCDIR}/lib/darwin_amd64 -lkailash_ffi
// #cgo darwin,arm64 LDFLAGS: -L${SRCDIR}/lib/darwin_arm64 -lkailash_ffi
// #cgo windows,amd64 LDFLAGS: -L${SRCDIR}/lib/windows_amd64 -lkailash_ffi
```

### 8.3 CI Pipeline

```yaml
# .github/workflows/go-sdk.yml
name: Go SDK
on: [push, pull_request]
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        go: ["1.22", "1.23"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-go@v5
        with:
          go-version: ${{ matrix.go }}
      - name: Build Rust core
        run: cargo build --release --package kailash-ffi
      - name: Test
        run: go test ./...
      - name: Vet
        run: go vet ./...
      - name: Lint
        run: golangci-lint run
```

## 9. Timeline

| Month | Milestone                                               |
| ----- | ------------------------------------------------------- |
| 1     | CGo bindings, basic WorkflowBuilder, LocalRuntime       |
| 2     | DataFlow-Go: model registration, CRUD operations        |
| 3     | DataFlow-Go: bulk operations, filters, migrations       |
| 4     | Nexus-Go: API channel, handler registration, middleware |
| 5     | Nexus-Go: CLI + MCP channels, auth plugin               |
| 6     | Kaizen-Go: basic agent, OpenAI/Anthropic providers      |
| 7     | Kaizen-Go: tools, memory, multi-agent                   |
| 8     | Documentation, examples, beta release                   |
