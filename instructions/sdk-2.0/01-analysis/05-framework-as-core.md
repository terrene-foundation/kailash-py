# Framework-as-Core: Native Framework Design Per Language

## 1. Overview

Each language SDK implements DataFlow, Nexus, and Kaizen as **native framework layers** that
feel idiomatic to developers in that language. The Rust core provides execution infrastructure;
the frameworks wrap language-native libraries for databases, web servers, and LLM SDKs.

This document specifies how each framework maps to each target language.

## 2. Design Principle

**"A Go developer using Kailash DataFlow should feel like they're using a Go database library,
not a Python SDK transpiled to Go."**

Each framework layer must:

1. Use the language's standard patterns (error handling, concurrency, packaging)
2. Wrap the language's dominant libraries (not reinvent them)
3. Expose APIs that match the language's conventions
4. Integrate with the language's build/test/deploy tooling
5. Share only the Rust core for execution (DAG, scheduling, validation)

## 3. DataFlow Per Language

### 3.1 DataFlow-Python (Current, Reference Implementation)

**Wraps**: SQLAlchemy (sync), aiosqlite (async), asyncpg (PostgreSQL async)

```python
from dataflow import DataFlow

db = DataFlow("sqlite:///app.db")

@db.model
class User:
    id: int = field(primary_key=True)
    name: str
    email: str

# Auto-generates 11 nodes: CreateUser, ReadUser, UpdateUser, DeleteUser,
# ListUser, UpsertUser, CountUser, BulkCreateUser, BulkUpdateUser,
# BulkDeleteUser, BulkUpsertUser

# Execute via workflow
result = db.execute(CreateUser(name="Alice", email="alice@example.com"))
```

**Key characteristics**:

- Decorator-based model definition (`@db.model`)
- Auto-node generation (11 nodes per model)
- SQLAlchemy connection string compatibility
- Pydantic-style type annotations
- Async-first with sync wrapper

### 3.2 DataFlow-Go

**Wraps**: `database/sql` (stdlib), `pgx` (PostgreSQL), `go-sqlite3`

```go
package main

import (
    "github.com/kailash-sdk/kailash-go/dataflow"
)

type User struct {
    ID    int    `df:"primary_key"`
    Name  string `df:"required"`
    Email string `df:"required,unique"`
}

func main() {
    db, err := dataflow.Open("sqlite:///app.db")
    if err != nil {
        log.Fatal(err)
    }
    defer db.Close()

    // Register model (generates 11 operations)
    db.Register(&User{})

    // Create
    user := &User{Name: "Alice", Email: "alice@example.com"}
    result, err := db.Create(user)
    if err != nil {
        log.Fatal(err)
    }

    // List with filters
    users, err := db.List(&User{}, dataflow.Filter{
        "name": dataflow.Like("Ali%"),
    })

    // Bulk create
    users := []*User{
        {Name: "Bob", Email: "bob@example.com"},
        {Name: "Charlie", Email: "charlie@example.com"},
    }
    results, err := db.BulkCreate(users)

    // Context-aware operations
    ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
    defer cancel()
    result, err := db.CreateCtx(ctx, user)
}
```

**Go-specific patterns**:

- Struct tags for model definition (`df:"primary_key"`)
- Error returns (no exceptions)
- `context.Context` for cancellation/timeouts
- `io.Closer` interface for cleanup
- Generics for type-safe operations (Go 1.18+)
- `database/sql` driver interface for connection management
- `sql.Scanner` and `driver.Valuer` for custom types

**Internal architecture**:

```go
// dataflow/engine.go
type Engine struct {
    core    *kailash.Runtime  // Rust core via CGo
    db      *sql.DB           // Native Go database connection
    models  map[string]*Model // Registered models
}

func (e *Engine) Create(model interface{}) (*Result, error) {
    // 1. Build workflow via Rust core
    wf := e.core.NewWorkflow()
    wf.AddNode("Create"+modelName, nodeID, config)

    // 2. Execute via Rust scheduler
    // Rust calls back into Go for actual SQL execution
    results, err := e.core.Execute(wf, func(nodeID string, inputs map[string]interface{}) (interface{}, error) {
        // 3. Execute SQL using native Go database/sql
        return e.executeSQL(inputs)
    })

    return results, err
}
```

### 3.3 DataFlow-Java

**Wraps**: JDBC (sync), JPA/Hibernate (ORM), Spring Data (repository pattern)

```java
package com.example;

import com.kailash.dataflow.DataFlow;
import com.kailash.dataflow.annotation.*;

@DataFlowModel
public class User {
    @PrimaryKey
    private int id;

    @Required
    private String name;

    @Required @Unique
    private String email;

    // Standard getters/setters or use Lombok @Data
}

public class Main {
    public static void main(String[] args) {
        DataFlow db = DataFlow.open("jdbc:sqlite:app.db");

        // Register model (generates 11 operations)
        db.register(User.class);

        // Create
        User user = new User();
        user.setName("Alice");
        user.setEmail("alice@example.com");
        Result result = db.create(user);

        // List with filters
        List<User> users = db.list(User.class,
            Filter.where("name").like("Ali%"));

        // Bulk create
        List<User> newUsers = List.of(
            new User("Bob", "bob@example.com"),
            new User("Charlie", "charlie@example.com")
        );
        List<Result> results = db.bulkCreate(newUsers);

        db.close();
    }
}
```

**Spring Data Integration**:

```java
@Configuration
public class DataFlowConfig {
    @Bean
    public DataFlow dataFlow(DataSource dataSource) {
        return DataFlow.fromDataSource(dataSource);
    }
}

// Spring Data-style repository
@DataFlowRepository
public interface UserRepository extends DataFlowCrudRepository<User, Integer> {
    List<User> findByNameContaining(String name);
    Optional<User> findByEmail(String email);
}
```

**Java-specific patterns**:

- Annotation-based model definition (`@DataFlowModel`, `@PrimaryKey`)
- Exception-based error handling (`DataFlowException`)
- `AutoCloseable` for resource management
- Optional Spring Data repository interface
- Builder pattern for filters
- CompletableFuture for async operations
- JPA entity compatibility (annotations map bidirectionally)

## 4. Nexus Per Language

### 4.1 Nexus-Python (Current, Reference Implementation)

```python
from nexus import Nexus

app = Nexus()

@app.handler("greet", description="Greeting handler")
async def greet(name: str, greeting: str = "Hello") -> dict:
    return {"message": f"{greeting}, {name}!"}

app.start()  # API on :8000, CLI available, MCP exposed
```

### 4.2 Nexus-Go

**Wraps**: `net/http` (stdlib), Gin/Echo (optional), `gorilla/mux`

```go
package main

import (
    "github.com/kailash-sdk/kailash-go/nexus"
)

func main() {
    app := nexus.New()

    // Handler registration (Go-idiomatic function signature)
    app.Handle("greet", nexus.HandlerFunc(func(ctx nexus.Context) error {
        name := ctx.Param("name")
        greeting := ctx.ParamDefault("greeting", "Hello")
        return ctx.JSON(map[string]string{
            "message": greeting + ", " + name + "!",
        })
    }), nexus.WithDescription("Greeting handler"))

    // Workflow registration
    app.Register("process", processWorkflow)

    // Middleware (Go-idiomatic)
    app.Use(nexus.Logger())
    app.Use(nexus.Recovery())
    app.Use(nexus.CORS(nexus.CORSConfig{
        AllowOrigins: []string{"*"},
    }))

    // Auth plugin
    app.UsePlugin(nexus.NewAuthPlugin(nexus.AuthConfig{
        JWTSecret: os.Getenv("JWT_SECRET"),
        RBAC: map[string][]string{
            "admin": {"*"},
            "user":  {"greet", "process"},
        },
    }))

    // Start (API :8000, CLI, MCP)
    if err := app.Start(); err != nil {
        log.Fatal(err)
    }
}
```

**Go-specific patterns**:

- `http.Handler` compatible middleware
- `context.Context` propagation through handlers
- Functional options (`nexus.WithDescription(...)`)
- Error return values (not panics)
- Graceful shutdown via `app.Shutdown(ctx)`
- Compatible with existing Go HTTP middleware ecosystem

### 4.3 Nexus-Java

**Wraps**: Spring Boot (primary), Jakarta EE (alternative)

```java
package com.example;

import com.kailash.nexus.Nexus;
import com.kailash.nexus.annotation.*;

@NexusApplication
public class App {
    public static void main(String[] args) {
        Nexus app = Nexus.create();

        // Handler registration
        app.handle("greet", (ctx) -> {
            String name = ctx.param("name");
            String greeting = ctx.paramOrDefault("greeting", "Hello");
            return Map.of("message", greeting + ", " + name + "!");
        }, HandlerOptions.builder()
            .description("Greeting handler")
            .build());

        app.start();  // API :8000, CLI, MCP
    }
}
```

**Spring Boot Integration**:

```java
@SpringBootApplication
@EnableNexus
public class App {
    public static void main(String[] args) {
        SpringApplication.run(App.class, args);
    }
}

@NexusController
public class GreetController {
    @NexusHandler(name = "greet", description = "Greeting handler")
    public Map<String, String> greet(
            @NexusParam String name,
            @NexusParam(defaultValue = "Hello") String greeting) {
        return Map.of("message", greeting + ", " + name + "!");
    }
}
```

**Java-specific patterns**:

- Spring Boot auto-configuration
- Annotation-based handler registration
- `@NexusController` maps to Spring `@RestController`
- Jakarta Servlet filter compatibility for middleware
- Spring Security integration for auth
- Actuator integration for health checks

## 5. Kaizen Per Language

### 5.1 Kaizen-Python (Current, Reference Implementation)

```python
from kaizen.api import Agent
import os

model = os.environ.get("OPENAI_PROD_MODEL")
agent = Agent(model=model)
result = await agent.run("What is the capital of France?")
```

### 5.2 Kaizen-Go

**Wraps**: `sashabaranov/go-openai`, `anthropics/anthropic-sdk-go`

```go
package main

import (
    "context"
    "os"

    "github.com/kailash-sdk/kailash-go/kaizen"
)

func main() {
    model := os.Getenv("OPENAI_PROD_MODEL")

    agent, err := kaizen.NewAgent(kaizen.AgentConfig{
        Model: model,
        ExecutionMode: kaizen.Autonomous,
        Memory: kaizen.SessionMemory,
    })
    if err != nil {
        log.Fatal(err)
    }

    ctx := context.Background()
    result, err := agent.Run(ctx, "What is the capital of France?")
    if err != nil {
        log.Fatal(err)
    }
    fmt.Println(result.Content)

    // Multi-agent coordination
    researcher := kaizen.NewAgent(kaizen.AgentConfig{
        Model: model,
        Role:  "researcher",
    })
    writer := kaizen.NewAgent(kaizen.AgentConfig{
        Model: model,
        Role:  "writer",
    })

    team, err := kaizen.NewTeam(researcher, writer)
    result, err = team.Run(ctx, "Write a report on renewable energy")
}
```

**Go-specific patterns**:

- `context.Context` for cancellation and timeouts
- Struct-based configuration (not keyword args)
- Interface-based tool registration
- Channel-based streaming responses
- Error returns for all operations

### 5.3 Kaizen-Java

**Wraps**: LangChain4j, Spring AI (optional)

```java
package com.example;

import com.kailash.kaizen.Agent;
import com.kailash.kaizen.AgentConfig;

public class Main {
    public static void main(String[] args) {
        String model = System.getenv("OPENAI_PROD_MODEL");

        Agent agent = Agent.builder()
            .model(model)
            .executionMode(ExecutionMode.AUTONOMOUS)
            .memory(MemoryType.SESSION)
            .build();

        AgentResult result = agent.run("What is the capital of France?");
        System.out.println(result.getContent());

        // Streaming
        agent.runStream("Tell me a story", chunk -> {
            System.out.print(chunk.getContent());
        });

        // Tool registration
        agent.registerTool("calculator", (input) -> {
            // Evaluate expression
            return eval(input.get("expression"));
        });
    }
}
```

**Spring AI Integration**:

```java
@Configuration
public class KaizenConfig {
    @Bean
    public Agent kaizenAgent(ChatModel chatModel) {
        return Agent.builder()
            .chatModel(chatModel)  // Spring AI ChatModel
            .executionMode(ExecutionMode.AUTONOMOUS)
            .build();
    }
}
```

**Java-specific patterns**:

- Builder pattern for configuration
- CompletableFuture for async operations
- Functional interfaces for tools and callbacks
- Spring AI ChatModel compatibility
- Reactive Streams support (Flux for streaming)

## 6. Cross-Language Consistency

### 6.1 Shared Behaviors (via Rust Core)

These behaviors are identical across all languages because they're implemented in Rust:

| Behavior                  | Implementation        |
| ------------------------- | --------------------- |
| Workflow DAG construction | Rust `WorkflowGraph`  |
| Topological sort order    | Rust scheduler        |
| Cycle detection           | Rust SCC algorithm    |
| Validation rules          | Rust validator        |
| Trust verification        | Rust trust engine     |
| Resource limits           | Rust resource manager |

### 6.2 Language-Specific Behaviors

These behaviors differ by language but must produce equivalent results:

| Behavior       | Why Different                                                  |
| -------------- | -------------------------------------------------------------- |
| Error handling | Go: error return, Python: exceptions, Java: exceptions         |
| Concurrency    | Go: goroutines, Python: asyncio, Java: threads/virtual threads |
| Configuration  | Go: structs, Python: kwargs, Java: builders                    |
| Serialization  | Go: encoding/json, Python: json, Java: Jackson                 |
| Logging        | Go: slog, Python: logging, Java: SLF4J                         |
| Testing        | Go: testing, Python: pytest, Java: JUnit                       |

### 6.3 Feature Parity Matrix

| Feature             | Python | Go          | Java        | Notes             |
| ------------------- | ------ | ----------- | ----------- | ----------------- |
| WorkflowBuilder     | v0.11  | v0.1 target | v0.1 target | Core API          |
| LocalRuntime        | v0.11  | v0.1 target | v0.1 target | Sync execution    |
| AsyncRuntime        | v0.11  | v0.1 target | v0.1 target | Async execution   |
| DataFlow Core       | v0.11  | v0.1 target | v0.1 target | CRUD + Bulk       |
| DataFlow Migration  | v0.11  | v0.2 target | v0.2 target | Schema migration  |
| Nexus API Channel   | v1.3   | v0.1 target | v0.1 target | REST API          |
| Nexus CLI Channel   | v1.3   | v0.1 target | v0.1 target | CLI interface     |
| Nexus MCP Channel   | v1.3   | v0.1 target | v0.1 target | MCP integration   |
| Nexus Auth Plugin   | v1.3   | v0.2 target | v0.2 target | JWT/RBAC/SSO      |
| Kaizen Agent        | v1.1   | v0.1 target | v0.1 target | Basic agent       |
| Kaizen Multi-Agent  | v1.1   | v0.2 target | v0.2 target | Team coordination |
| Kaizen Trust (CARE) | v1.1   | v0.2 target | v0.2 target | Trust framework   |

## 7. Migration Path for Python SDK

### 7.1 Phase A: Parallel Implementation

```python
# BEFORE (current): Pure Python
from kailash.workflow.graph import Workflow  # networkx-based

# AFTER (SDK 2.0): Rust-backed
from kailash._rust import WorkflowGraph  # PyO3 binding

class Workflow:
    def __init__(self, ...):
        self._graph = WorkflowGraph()  # Rust core
        # Python-side metadata preserved
```

### 7.2 Phase B: Framework Adaptation

Frameworks continue using the same Python APIs. The internal implementation switches
from networkx to Rust, but the public surface is unchanged:

```python
# DataFlow: No changes needed
db = DataFlow("sqlite:///app.db")
result = db.execute(CreateUser(name="Alice"))
# Internally: WorkflowBuilder -> Rust graph -> Rust scheduler -> Python node callback

# Nexus: No changes needed
app = Nexus()
app.handler("greet")(greet_func)
app.start()
# Internally: Workflow registered in Rust core, execution via Rust scheduler

# Kaizen: No changes needed
agent = Agent(model=model)
result = await agent.run("question")
# Internally: Agent workflow built via Rust core, LLM calls via Python callback
```

## 8. Implementation Complexity Estimate

| Component           | Python (exists)  | Go (new)     | Java (new)   |
| ------------------- | ---------------- | ------------ | ------------ |
| Core bindings (FFI) | 2K LOC (PyO3)    | 3K LOC (CGo) | 4K LOC (JNI) |
| WorkflowBuilder     | 1.3K LOC (adapt) | 1K LOC       | 1.5K LOC     |
| Runtime             | 1K LOC (adapt)   | 1K LOC       | 1.5K LOC     |
| DataFlow            | 6K LOC (adapt)   | 4K LOC       | 5K LOC       |
| Nexus               | 3K LOC (adapt)   | 3K LOC       | 4K LOC       |
| Kaizen              | 3K LOC (adapt)   | 2K LOC       | 3K LOC       |
| Tests               | Adapt existing   | 5K LOC       | 5K LOC       |
| **Total**           | **~16K LOC**     | **~19K LOC** | **~24K LOC** |

Note: Python LOC is primarily adaptation of existing code to use Rust core.
Go and Java are new implementations wrapping native libraries.
