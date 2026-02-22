# Java SDK Plan

## 1. Overview

The Java SDK (`kailash-java`) targets enterprise Java/Spring developers. It wraps the shared
Rust core via JNI and implements DataFlow-Java, Nexus-Java, and Kaizen-Java using native Java
ecosystem libraries (JDBC, Spring Boot, LangChain4j).

## 2. Maven Module Structure

```xml
<!-- Root POM -->
<project>
    <groupId>com.kailash</groupId>
    <artifactId>kailash-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>kailash-core</module>       <!-- JNI bindings -->
        <module>kailash-workflow</module>   <!-- Workflow builder -->
        <module>kailash-runtime</module>    <!-- Runtime engine -->
        <module>kailash-nodes</module>      <!-- Node base types -->
        <module>kailash-dataflow</module>   <!-- DataFlow framework -->
        <module>kailash-nexus</module>      <!-- Nexus framework -->
        <module>kailash-kaizen</module>     <!-- Kaizen framework -->
        <module>kailash-spring-boot</module><!-- Spring Boot starters -->
    </modules>
</project>
```

### 2.1 Directory Structure

```
kailash-java/
+-- pom.xml                         # Parent POM
+-- kailash-core/                   # JNI bindings to Rust
|   +-- pom.xml
|   +-- src/main/java/com/kailash/core/
|   |   +-- KailashCore.java        # JNI loader
|   |   +-- WorkflowGraph.java      # Graph wrapper
|   |   +-- NativeLib.java          # JNI method declarations
|   |   +-- types/
|   |   |   +-- NodeId.java
|   |   |   +-- ConnectionInfo.java
|   |   |   +-- ValidationResult.java
|   |   +-- errors/
|   |       +-- KailashException.java
|   |       +-- GraphException.java
|   |       +-- ValidationException.java
|   |       +-- ExecutionException.java
|   +-- src/main/resources/native/
|   |   +-- linux-x86_64/libkailash_jni.so
|   |   +-- linux-aarch64/libkailash_jni.so
|   |   +-- darwin-x86_64/libkailash_jni.dylib
|   |   +-- darwin-aarch64/libkailash_jni.dylib
|   |   +-- windows-x86_64/kailash_jni.dll
|   +-- src/test/java/com/kailash/core/
+-- kailash-workflow/
|   +-- pom.xml
|   +-- src/main/java/com/kailash/workflow/
|       +-- WorkflowBuilder.java
|       +-- Workflow.java
|       +-- Node.java
|       +-- Connection.java
|       +-- Parameter.java
+-- kailash-runtime/
|   +-- pom.xml
|   +-- src/main/java/com/kailash/runtime/
|       +-- Runtime.java             # Interface
|       +-- LocalRuntime.java        # Sync implementation
|       +-- AsyncRuntime.java        # CompletableFuture-based
|       +-- ExecutionResult.java
|       +-- NodeMetrics.java
+-- kailash-dataflow/
|   +-- pom.xml
|   +-- src/main/java/com/kailash/dataflow/
|       +-- DataFlow.java            # Main engine
|       +-- annotation/
|       |   +-- DataFlowModel.java
|       |   +-- PrimaryKey.java
|       |   +-- Required.java
|       |   +-- Unique.java
|       |   +-- Column.java
|       +-- operations/
|       |   +-- CrudOperations.java
|       |   +-- BulkOperations.java
|       +-- filter/
|       |   +-- Filter.java
|       |   +-- FilterBuilder.java
|       +-- repository/
|           +-- DataFlowRepository.java
|           +-- DataFlowCrudRepository.java
+-- kailash-nexus/
|   +-- pom.xml
|   +-- src/main/java/com/kailash/nexus/
|       +-- Nexus.java
|       +-- handler/
|       |   +-- Handler.java
|       |   +-- HandlerContext.java
|       +-- middleware/
|       |   +-- Middleware.java
|       |   +-- MiddlewareChain.java
|       +-- channel/
|       |   +-- ApiChannel.java
|       |   +-- CliChannel.java
|       |   +-- McpChannel.java
|       +-- auth/
|           +-- AuthPlugin.java
|           +-- JwtConfig.java
+-- kailash-kaizen/
|   +-- pom.xml
|   +-- src/main/java/com/kailash/kaizen/
|       +-- Agent.java
|       +-- AgentConfig.java
|       +-- AgentResult.java
|       +-- tool/
|       |   +-- Tool.java
|       |   +-- ToolRegistry.java
|       +-- memory/
|       |   +-- Memory.java
|       |   +-- SessionMemory.java
|       +-- provider/
|           +-- LlmProvider.java
|           +-- OpenAiProvider.java
|           +-- AnthropicProvider.java
+-- kailash-spring-boot/
    +-- kailash-spring-boot-starter/
    |   +-- pom.xml
    |   +-- src/main/java/com/kailash/spring/
    |       +-- KailashAutoConfiguration.java
    |       +-- KailashProperties.java
    +-- kailash-spring-boot-starter-dataflow/
    +-- kailash-spring-boot-starter-nexus/
    +-- kailash-spring-boot-starter-kaizen/
```

## 3. JNI Bindings to Rust Core

### 3.1 JNI Method Declarations

```java
// kailash-core/src/main/java/com/kailash/core/NativeLib.java
package com.kailash.core;

public class NativeLib {
    static {
        NativeLoader.load("kailash_jni");
    }

    // Workflow graph operations
    public static native long createWorkflow(String id, String name);
    public static native void freeWorkflow(long handle);
    public static native int addNode(long handle, String nodeId, String nodeType,
                                      String configJson, boolean isAsync);
    public static native int connect(long handle, String sourceId, String sourceOutput,
                                      String targetId, String targetInput);
    public static native String topologicalSort(long handle);
    public static native String computeLevels(long handle);
    public static native boolean hasCycles(long handle);
    public static native String validate(long handle);
    public static native String getPredecessors(long handle, String nodeId);
    public static native String prepareInputs(long handle, String nodeId, String resultsJson);
    public static native int nodeCount(long handle);
    public static native int edgeCount(long handle);

    // Execution
    public static native String execute(long handle, long callbackHandle);
    public static native long registerCallback(Object executor);
    public static native void unregisterCallback(long callbackHandle);

    // Error handling
    public static native String getLastError(long handle);
}
```

### 3.2 Rust JNI Implementation

```rust
// kailash-java/src/lib.rs
use jni::JNIEnv;
use jni::objects::{JClass, JString, JObject};
use jni::sys::{jlong, jint, jboolean, jstring};
use kailash_core::graph::{WorkflowGraph, NodeId};

#[no_mangle]
pub extern "system" fn Java_com_kailash_core_NativeLib_createWorkflow(
    mut env: JNIEnv,
    _class: JClass,
    id: JString,
    name: JString,
) -> jlong {
    let id: String = env.get_string(&id).unwrap().into();
    let name: String = env.get_string(&name).unwrap().into();

    let graph = Box::new(WorkflowGraph::new(&id, &name));
    Box::into_raw(graph) as jlong
}

#[no_mangle]
pub extern "system" fn Java_com_kailash_core_NativeLib_freeWorkflow(
    _env: JNIEnv,
    _class: JClass,
    handle: jlong,
) {
    unsafe {
        let _ = Box::from_raw(handle as *mut WorkflowGraph);
    }
}

#[no_mangle]
pub extern "system" fn Java_com_kailash_core_NativeLib_addNode(
    mut env: JNIEnv,
    _class: JClass,
    handle: jlong,
    node_id: JString,
    node_type: JString,
    config_json: JString,
    is_async: jboolean,
) -> jint {
    let graph = unsafe { &mut *(handle as *mut WorkflowGraph) };
    let node_id: String = env.get_string(&node_id).unwrap().into();
    let node_type: String = env.get_string(&node_type).unwrap().into();
    let config_str: String = env.get_string(&config_json).unwrap().into();

    let config: serde_json::Value = match serde_json::from_str(&config_str) {
        Ok(v) => v,
        Err(_) => return -1,
    };

    match graph.add_node(NodeId(node_id), &node_type, config, is_async != 0) {
        Ok(()) => 0,
        Err(_) => -1,
    }
}
```

### 3.3 Native Library Loader

```java
// kailash-core/src/main/java/com/kailash/core/NativeLoader.java
package com.kailash.core;

import java.io.*;
import java.nio.file.*;

public class NativeLoader {
    public static void load(String libraryName) {
        String os = System.getProperty("os.name").toLowerCase();
        String arch = System.getProperty("os.arch").toLowerCase();

        String platform;
        String extension;
        if (os.contains("linux")) {
            platform = arch.contains("aarch64") ? "linux-aarch64" : "linux-x86_64";
            extension = ".so";
        } else if (os.contains("mac")) {
            platform = arch.contains("aarch64") ? "darwin-aarch64" : "darwin-x86_64";
            extension = ".dylib";
        } else if (os.contains("win")) {
            platform = "windows-x86_64";
            extension = ".dll";
        } else {
            throw new UnsupportedOperationException("Unsupported platform: " + os + "/" + arch);
        }

        String resourcePath = "/native/" + platform + "/lib" + libraryName + extension;
        try (InputStream in = NativeLoader.class.getResourceAsStream(resourcePath)) {
            if (in == null) {
                throw new RuntimeException("Native library not found: " + resourcePath);
            }

            Path tempFile = Files.createTempFile("kailash", extension);
            tempFile.toFile().deleteOnExit();
            Files.copy(in, tempFile, StandardCopyOption.REPLACE_EXISTING);
            System.load(tempFile.toString());
        } catch (IOException e) {
            throw new RuntimeException("Failed to load native library", e);
        }
    }
}
```

## 4. DataFlow-Java: JPA/Hibernate Integration

### 4.1 Annotation-Based Model

```java
// kailash-dataflow/src/main/java/com/kailash/dataflow/annotation/DataFlowModel.java
package com.kailash.dataflow.annotation;

import java.lang.annotation.*;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface DataFlowModel {
    String tableName() default "";
    boolean softDelete() default false;
}

@Target(ElementType.FIELD)
@Retention(RetentionPolicy.RUNTIME)
public @interface PrimaryKey {
    boolean autoIncrement() default true;
}

@Target(ElementType.FIELD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Required {}

@Target(ElementType.FIELD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Unique {}
```

### 4.2 DataFlow Engine

```java
// kailash-dataflow/src/main/java/com/kailash/dataflow/DataFlow.java
package com.kailash.dataflow;

import com.kailash.core.WorkflowGraph;
import com.kailash.dataflow.annotation.*;
import javax.sql.DataSource;
import java.sql.*;
import java.util.*;

public class DataFlow implements AutoCloseable {
    private final DataSource dataSource;
    private final Map<String, ModelMetadata> models = new HashMap<>();
    private final WorkflowGraph graph;

    public static DataFlow open(String jdbcUrl) {
        // Create DataSource from JDBC URL
        return new DataFlow(createDataSource(jdbcUrl));
    }

    public static DataFlow fromDataSource(DataSource dataSource) {
        return new DataFlow(dataSource);
    }

    public <T> void register(Class<T> modelClass) {
        ModelMetadata metadata = ModelMetadata.fromClass(modelClass);
        models.put(metadata.getName(), metadata);

        // Auto-create table if not exists
        try (Connection conn = dataSource.getConnection()) {
            createTableIfNotExists(conn, metadata);
        } catch (SQLException e) {
            throw new DataFlowException("Failed to register model: " + metadata.getName(), e);
        }
    }

    public <T> Result create(T entity) {
        ModelMetadata metadata = getMetadata(entity.getClass());
        Map<String, Object> values = metadata.extractValues(entity);

        String sql = buildInsertSQL(metadata, values);
        try (Connection conn = dataSource.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)) {
            bindParameters(stmt, values);
            stmt.executeUpdate();

            try (ResultSet rs = stmt.getGeneratedKeys()) {
                if (rs.next()) {
                    return new Result(rs.getLong(1), 1);
                }
            }
            return new Result(0, 1);
        } catch (SQLException e) {
            throw new DataFlowException("Create failed", e);
        }
    }

    public <T> List<T> list(Class<T> modelClass, Filter... filters) {
        ModelMetadata metadata = getMetadata(modelClass);
        String sql = buildSelectSQL(metadata, filters);

        try (Connection conn = dataSource.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql)) {
            bindFilterParameters(stmt, filters);
            try (ResultSet rs = stmt.executeQuery()) {
                return mapResults(rs, modelClass, metadata);
            }
        } catch (SQLException e) {
            throw new DataFlowException("List failed", e);
        }
    }

    // Bulk operations
    public <T> List<Result> bulkCreate(List<T> entities) {
        if (entities.isEmpty()) return Collections.emptyList();

        ModelMetadata metadata = getMetadata(entities.get(0).getClass());
        String sql = buildInsertSQL(metadata, metadata.extractValues(entities.get(0)));

        try (Connection conn = dataSource.getConnection()) {
            conn.setAutoCommit(false);
            try (PreparedStatement stmt = conn.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)) {
                for (T entity : entities) {
                    Map<String, Object> values = metadata.extractValues(entity);
                    bindParameters(stmt, values);
                    stmt.addBatch();
                }
                stmt.executeBatch();
                conn.commit();
            } catch (SQLException e) {
                conn.rollback();
                throw e;
            }
        } catch (SQLException e) {
            throw new DataFlowException("Bulk create failed", e);
        }
        return Collections.emptyList(); // Simplified
    }

    @Override
    public void close() {
        // Clean up resources
    }
}
```

## 5. Spring Boot Integration

### 5.1 Auto-Configuration

```java
// kailash-spring-boot/kailash-spring-boot-starter/src/main/java/com/kailash/spring/
package com.kailash.spring;

import com.kailash.dataflow.DataFlow;
import com.kailash.nexus.Nexus;
import com.kailash.kaizen.Agent;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import javax.sql.DataSource;

@Configuration
@EnableConfigurationProperties(KailashProperties.class)
public class KailashAutoConfiguration {

    @Bean
    @ConditionalOnClass(DataFlow.class)
    @ConditionalOnMissingBean
    public DataFlow dataFlow(DataSource dataSource) {
        return DataFlow.fromDataSource(dataSource);
    }

    @Bean
    @ConditionalOnClass(Nexus.class)
    @ConditionalOnMissingBean
    public Nexus nexus(KailashProperties properties) {
        return Nexus.builder()
            .port(properties.getNexus().getPort())
            .build();
    }

    @Bean
    @ConditionalOnClass(Agent.class)
    @ConditionalOnMissingBean
    public Agent kaizenAgent(KailashProperties properties) {
        return Agent.builder()
            .model(properties.getKaizen().getModel())
            .build();
    }
}
```

### 5.2 Spring Properties

```java
// KailashProperties.java
package com.kailash.spring;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "kailash")
public class KailashProperties {

    private NexusProperties nexus = new NexusProperties();
    private KaizenProperties kaizen = new KaizenProperties();

    public static class NexusProperties {
        private int port = 8000;
        private boolean enableMcp = true;
        private boolean enableCli = true;
        // getters/setters
    }

    public static class KaizenProperties {
        private String model;
        private String executionMode = "single_shot";
        private String memory = "none";
        // getters/setters
    }

    // getters/setters
}
```

### 5.3 Application Properties

```yaml
# application.yml
kailash:
  nexus:
    port: 8000
    enable-mcp: true
    enable-cli: true
  kaizen:
    model: ${OPENAI_PROD_MODEL}
    execution-mode: autonomous
    memory: session
```

## 6. Build & Distribution

### 6.1 Maven Central Publishing

```xml
<!-- kailash-core/pom.xml -->
<project>
    <groupId>com.kailash</groupId>
    <artifactId>kailash-core</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.google.code.gson</groupId>
            <artifactId>gson</artifactId>
            <version>2.11.0</version>
        </dependency>
    </dependencies>
</project>
```

### 6.2 CI Pipeline

```yaml
# .github/workflows/java-sdk.yml
name: Java SDK
on: [push, pull_request]
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        java: [17, 21]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          java-version: ${{ matrix.java }}
          distribution: temurin
      - name: Build Rust core
        run: cargo build --release --package kailash-java
      - name: Copy native library
        run: |
          mkdir -p kailash-core/src/main/resources/native/$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)
          cp target/release/libkailash_jni.* kailash-core/src/main/resources/native/*/
      - name: Test
        run: mvn test
      - name: Package
        run: mvn package -DskipTests
```

## 7. Java-Specific Dependencies

| Dependency  | Version | Module      | Purpose                   |
| ----------- | ------- | ----------- | ------------------------- |
| JDK         | 17+     | All         | Minimum Java version      |
| Gson        | 2.11    | core        | JSON serialization        |
| HikariCP    | 5.1     | dataflow    | Connection pooling        |
| SLF4J       | 2.0     | All         | Logging facade            |
| JUnit 5     | 5.10    | All (test)  | Testing                   |
| Mockito     | 5.12    | All (test)  | Mocking (unit tests only) |
| Spring Boot | 3.3     | spring-boot | Auto-configuration        |
| Spring Data | 3.3     | spring-boot | Repository pattern        |
| LangChain4j | 0.35    | kaizen      | LLM integration           |

## 8. Timeline

| Month | Milestone                                              |
| ----- | ------------------------------------------------------ |
| 1     | JNI bindings, NativeLoader, WorkflowBuilder            |
| 2     | LocalRuntime, AsyncRuntime (CompletableFuture)         |
| 3     | DataFlow-Java: annotations, CRUD, connection pooling   |
| 4     | DataFlow-Java: bulk operations, filters, Spring Data   |
| 5     | Nexus-Java: API channel, handlers, Spring Boot starter |
| 6     | Nexus-Java: CLI + MCP, auth plugin                     |
| 7     | Kaizen-Java: Agent, OpenAI/Anthropic, Spring AI        |
| 8     | Spring Boot starters, documentation, beta release      |
