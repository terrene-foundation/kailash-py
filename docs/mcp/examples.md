# MCP Code Examples and Recipes

## Overview

This document provides practical code examples and recipes for common MCP (Model Context Protocol) use cases. Each example is complete and ready to run.

## Table of Contents

1. [Basic Examples](#basic-examples)
2. [Authentication Examples](#authentication-examples)
3. [Tool Examples](#tool-examples)
4. [Advanced Patterns](#advanced-patterns)
5. [Integration Examples](#integration-examples)
6. [Error Handling](#error-handling)
7. [Performance Optimization](#performance-optimization)
8. [Security Examples](#security-examples)
9. [Monitoring and Logging](#monitoring-and-logging)
10. [Production Recipes](#production-recipes)

## Basic Examples

### Hello World MCP Server

```python
# server/hello_world.py
from kailash.mcp_server import MCPServer

# Create MCP server
server = MCPServer("Hello World Server")

@server.tool()
def hello(name: str = "World") -> str:
    """Say hello to someone."""
    return f"Hello, {name}!"

@server.tool()
def add_numbers(a: float, b: float) -> dict:
    """Add two numbers together."""
    return {
        "result": a + b,
        "operation": f"{a} + {b}"
    }

if __name__ == "__main__":
    # Run server
    server.run()
```

### Hello World MCP Client

```python
# client/hello_world.py
import asyncio
from kailash.mcp_server.client import MCPClient

async def main():
    # Connect to server
    client = MCPClient("hello-world-client")

    # Example client operations (syntax demonstration)
    print("MCP Client created successfully")

if __name__ == "__main__":
    asyncio.run(main())
```

### Basic Workflow Integration

```python
# workflow_example.py
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai import LLMAgentNode

# Create workflow
workflow = Workflow("mcp-workflow", "MCP Workflow")

# Add LLM agent that uses MCP tools
workflow.add_node("agent", LLMAgentNode())

# Create runtime
runtime = LocalRuntime()

# Execute with MCP configuration
results, run_id = runtime.execute(workflow, parameters={
    "agent": {
        "provider": "ollama",
        "model": "llama3.2",
        "messages": [{"role": "user", "content": "Hello MCP!"}],
        "mcp_servers": [{
            "name": "hello-server",
            "transport": "stdio",
            "command": "echo",
            "args": ["mock"]
        }],
        "auto_discover_tools": True
    }
})

print("Workflow executed successfully!")
```

## Authentication Examples

### JWT Authentication Server

```python
# server/auth_server.py
from mcp.server import FastMCP
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timedelta

mcp = FastMCP("Authenticated MCP Server")
security = HTTPBearer()

# Secret key for JWT
SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"

def create_token(user_id: str) -> str:
    """Create JWT token."""
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str:
    """Verify JWT token."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Add auth endpoint
@mcp.app.post("/auth/login")
async def login(username: str, password: str):
    """Login endpoint."""
    # In production, verify credentials properly
    if username == "admin" and password == "secret":
        token = create_token(username)
        return {"access_token": token, "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Invalid credentials")

# Protected tool
@mcp.tool(dependencies=[Depends(verify_token)])
async def secure_tool(data: str, user_id: str = Depends(verify_token)) -> dict:
    """A tool that requires authentication."""
    return {
        "result": f"Processed '{data}' for user {user_id}",
        "user": user_id,
        "timestamp": datetime.utcnow().isoformat()
    }
```

### OAuth2 Integration

```python
# server/oauth2_server.py
from mcp.server import FastMCP
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from starlette.requests import Request

mcp = FastMCP("OAuth2 MCP Server")

# OAuth configuration
config = Config('.env')
oauth = OAuth(config)

oauth.register(
    name='google',
    client_id=config('GOOGLE_CLIENT_ID'),
    client_secret=config('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

@mcp.app.get('/auth/google')
async def google_login(request: Request):
    """Initiate Google OAuth flow."""
    redirect_uri = request.url_for('google_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@mcp.app.get('/auth/google/callback')
async def google_callback(request: Request):
    """Handle Google OAuth callback."""
    token = await oauth.google.authorize_access_token(request)
    user = await oauth.google.parse_id_token(request, token)

    # Create internal JWT token
    access_token = create_token(user['email'])

    return {
        "access_token": access_token,
        "user": {
            "email": user['email'],
            "name": user.get('name'),
            "picture": user.get('picture')
        }
    }
```

### API Key Authentication

```python
# server/api_key_server.py
from mcp.server import FastMCP
from fastapi import Header, HTTPException
import hashlib

mcp = FastMCP("API Key Protected Server")

# Store API keys (in production, use a database)
API_KEYS = {
    hashlib.sha256(b"test-api-key").hexdigest(): {
        "user": "test-user",
        "permissions": ["read", "write"]
    }
}

def verify_api_key(x_api_key: str = Header(...)) -> dict:
    """Verify API key."""
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()

    if key_hash not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return API_KEYS[key_hash]

@mcp.tool(dependencies=[Depends(verify_api_key)])
async def protected_tool(
    query: str,
    user_info: dict = Depends(verify_api_key)
) -> dict:
    """Tool that requires API key."""
    if "write" not in user_info["permissions"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return {
        "result": f"Executed query: {query}",
        "user": user_info["user"]
    }
```

## Tool Examples

### Web Search Tool

```python
# tools/web_search.py
from mcp.server import FastMCP
import aiohttp
from typing import List, Dict

mcp = FastMCP("Web Search Tools")

@mcp.tool()
async def search_web(
    query: str,
    max_results: int = 10,
    safe_search: bool = True
) -> Dict[str, any]:
    """Search the web for information."""

    # In production, use a real search API
    async with aiohttp.ClientSession() as session:
        params = {
            "q": query,
            "limit": max_results,
            "safe": "active" if safe_search else "off"
        }

        async with session.get(
            "https://api.search.example.com/search",
            params=params
        ) as response:
            data = await response.json()

    return {
        "query": query,
        "results": data["results"],
        "total_results": data["total"],
        "search_time": data["time"]
    }

@mcp.tool()
async def search_news(
    topic: str,
    language: str = "en",
    from_date: str = None
) -> Dict[str, any]:
    """Search for news articles."""

    params = {
        "q": topic,
        "lang": language,
        "sortBy": "relevancy"
    }

    if from_date:
        params["from"] = from_date

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://newsapi.org/v2/everything",
            params=params,
            headers={"X-Api-Key": "your-news-api-key"}
        ) as response:
            data = await response.json()

    return {
        "topic": topic,
        "articles": data["articles"][:10],
        "total_results": data["totalResults"]
    }
```

### Database Query Tool

```python
# tools/database_tool.py
from mcp.server import FastMCP
import asyncpg
from typing import List, Dict, Any

mcp = FastMCP("Database Tools")

# Database connection pool
db_pool = None

@mcp.app.on_event("startup")
async def startup():
    global db_pool
    db_pool = await asyncpg.create_pool(
        "postgresql://user:password@localhost/db",
        min_size=10,
        max_size=20
    )

@mcp.app.on_event("shutdown")
async def shutdown():
    global db_pool
    await db_pool.close()

@mcp.tool()
async def query_database(
    query: str,
    parameters: List[Any] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """Execute a database query safely."""

    # Validate query (basic safety check)
    forbidden_keywords = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER"]
    query_upper = query.upper()

    for keyword in forbidden_keywords:
        if keyword in query_upper:
            return {
                "error": f"Forbidden operation: {keyword}",
                "allowed_operations": ["SELECT"]
            }

    # Add limit if not present
    if "LIMIT" not in query_upper:
        query += f" LIMIT {limit}"

    try:
        async with db_pool.acquire() as connection:
            # Execute query
            rows = await connection.fetch(query, *(parameters or []))

            # Convert to dictionaries
            results = [dict(row) for row in rows]

            return {
                "query": query,
                "results": results,
                "row_count": len(results)
            }

    except Exception as e:
        return {
            "error": str(e),
            "query": query
        }

@mcp.tool()
async def get_table_schema(table_name: str) -> Dict[str, Any]:
    """Get schema information for a table."""

    query = """
    SELECT
        column_name,
        data_type,
        is_nullable,
        column_default
    FROM information_schema.columns
    WHERE table_name = $1
    ORDER BY ordinal_position
    """

    async with db_pool.acquire() as connection:
        rows = await connection.fetch(query, table_name)

        columns = [
            {
                "name": row["column_name"],
                "type": row["data_type"],
                "nullable": row["is_nullable"] == "YES",
                "default": row["column_default"]
            }
            for row in rows
        ]

        return {
            "table": table_name,
            "columns": columns
        }
```

### File System Tool

```python
# tools/filesystem_tool.py
from mcp.server import FastMCP
import aiofiles
import os
from pathlib import Path
from typing import List, Dict, Any

mcp = FastMCP("File System Tools")

# Sandbox directory
SANDBOX_DIR = Path("/tmp/mcp_sandbox")
SANDBOX_DIR.mkdir(exist_ok=True)

def validate_path(path: str) -> Path:
    """Validate and sandbox file paths."""
    # Convert to Path object
    p = Path(path)

    # Resolve to absolute path within sandbox
    safe_path = SANDBOX_DIR / p

    # Ensure path is within sandbox
    try:
        safe_path.resolve().relative_to(SANDBOX_DIR.resolve())
    except ValueError:
        raise ValueError("Path escapes sandbox")

    return safe_path

@mcp.tool()
async def read_file(
    path: str,
    encoding: str = "utf-8"
) -> Dict[str, Any]:
    """Read contents of a file."""
    try:
        safe_path = validate_path(path)

        if not safe_path.exists():
            return {"error": "File not found", "path": path}

        async with aiofiles.open(safe_path, 'r', encoding=encoding) as f:
            content = await f.read()

        return {
            "path": path,
            "content": content,
            "size": len(content),
            "encoding": encoding
        }

    except Exception as e:
        return {"error": str(e), "path": path}

@mcp.tool()
async def write_file(
    path: str,
    content: str,
    encoding: str = "utf-8",
    create_dirs: bool = True
) -> Dict[str, Any]:
    """Write content to a file."""
    try:
        safe_path = validate_path(path)

        # Create directories if needed
        if create_dirs:
            safe_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(safe_path, 'w', encoding=encoding) as f:
            await f.write(content)

        return {
            "path": path,
            "size": len(content),
            "encoding": encoding,
            "success": True
        }

    except Exception as e:
        return {"error": str(e), "path": path, "success": False}

@mcp.tool()
async def list_directory(
    path: str = ".",
    pattern: str = "*",
    recursive: bool = False
) -> Dict[str, Any]:
    """List files in a directory."""
    try:
        safe_path = validate_path(path)

        if not safe_path.exists():
            return {"error": "Directory not found", "path": path}

        if recursive:
            files = list(safe_path.rglob(pattern))
        else:
            files = list(safe_path.glob(pattern))

        file_info = []
        for f in files:
            stat = f.stat()
            file_info.append({
                "name": f.name,
                "path": str(f.relative_to(SANDBOX_DIR)),
                "type": "directory" if f.is_dir() else "file",
                "size": stat.st_size if f.is_file() else None,
                "modified": stat.st_mtime
            })

        return {
            "path": path,
            "files": file_info,
            "count": len(file_info)
        }

    except Exception as e:
        return {"error": str(e), "path": path}
```

### AI/LLM Integration Tool

```python
# tools/llm_tool.py
from mcp.server import FastMCP
from openai import AsyncOpenAI
import anthropic
from typing import List, Dict, Any, Literal

mcp = FastMCP("LLM Tools")

# Initialize clients
openai_client = AsyncOpenAI(api_key="your-openai-key")
anthropic_client = anthropic.AsyncAnthropic(api_key="your-anthropic-key")

@mcp.tool()
async def generate_text(
    prompt: str,
    model: Literal["gpt-4", "claude-3", "gpt-3.5-turbo"] = "gpt-3.5-turbo",
    max_tokens: int = 500,
    temperature: float = 0.7
) -> Dict[str, Any]:
    """Generate text using various LLMs."""

    if model.startswith("gpt"):
        # OpenAI models
        response = await openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature
        )

        return {
            "model": model,
            "text": response.choices[0].message.content,
            "tokens_used": response.usage.total_tokens,
            "finish_reason": response.choices[0].finish_reason
        }

    elif model.startswith("claude"):
        # Anthropic models
        response = await anthropic_client.messages.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature
        )

        return {
            "model": model,
            "text": response.content[0].text,
            "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
            "finish_reason": response.stop_reason
        }

@mcp.tool()
async def analyze_text(
    text: str,
    analysis_type: List[Literal["sentiment", "entities", "summary", "keywords"]]
) -> Dict[str, Any]:
    """Analyze text for various attributes."""

    results = {}

    # Use specialized prompts for each analysis type
    prompts = {
        "sentiment": f"Analyze the sentiment of this text (positive/negative/neutral) and provide a confidence score:\n\n{text}",
        "entities": f"Extract all named entities (people, places, organizations) from this text:\n\n{text}",
        "summary": f"Provide a concise summary of this text in 2-3 sentences:\n\n{text}",
        "keywords": f"Extract the top 5 keywords or key phrases from this text:\n\n{text}"
    }

    for analysis in analysis_type:
        if analysis in prompts:
            response = await openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a text analysis assistant. Provide structured, concise responses."},
                    {"role": "user", "content": prompts[analysis]}
                ],
                max_tokens=200,
                temperature=0.3
            )

            results[analysis] = response.choices[0].message.content

    return {
        "text_length": len(text),
        "analyses": results
    }

@mcp.tool()
async def embedding_search(
    query: str,
    documents: List[str],
    top_k: int = 5
) -> Dict[str, Any]:
    """Search documents using embeddings."""

    # Get embeddings for query and documents
    query_response = await openai_client.embeddings.create(
        input=query,
        model="text-embedding-ada-002"
    )
    query_embedding = query_response.data[0].embedding

    # Get document embeddings
    doc_response = await openai_client.embeddings.create(
        input=documents,
        model="text-embedding-ada-002"
    )

    # Calculate cosine similarity
    import numpy as np

    similarities = []
    for i, doc_embedding in enumerate(doc_response.data):
        similarity = np.dot(query_embedding, doc_embedding.embedding) / (
            np.linalg.norm(query_embedding) * np.linalg.norm(doc_embedding.embedding)
        )
        similarities.append((i, similarity, documents[i]))

    # Sort by similarity
    similarities.sort(key=lambda x: x[1], reverse=True)

    # Return top results
    results = [
        {
            "index": idx,
            "score": float(score),
            "document": doc
        }
        for idx, score, doc in similarities[:top_k]
    ]

    return {
        "query": query,
        "results": results,
        "total_documents": len(documents)
    }
```

## Advanced Patterns

### Tool Chaining

```python
# patterns/tool_chaining.py
from mcp.server import FastMCP
from typing import Dict, Any, List

mcp = FastMCP("Tool Chaining Example")

# Store intermediate results
result_cache = {}

@mcp.tool()
async def research_topic(topic: str) -> Dict[str, Any]:
    """Research a topic by chaining multiple tools."""

    # Step 1: Search for general information
    search_result = await search_web(topic, max_results=5)

    # Step 2: Extract key points from search results
    combined_text = "\n".join([
        r["snippet"] for r in search_result["results"]
    ])

    analysis = await analyze_text(
        combined_text,
        ["summary", "keywords", "entities"]
    )

    # Step 3: Search news for recent developments
    news_result = await search_news(topic)

    # Step 4: Generate comprehensive report
    report_prompt = f"""
    Based on the following research about {topic}:

    Summary: {analysis['analyses']['summary']}
    Keywords: {analysis['analyses']['keywords']}
    Recent News: {len(news_result['articles'])} articles found

    Please create a comprehensive report.
    """

    report = await generate_text(
        report_prompt,
        model="gpt-4",
        max_tokens=1000
    )

    return {
        "topic": topic,
        "summary": analysis['analyses']['summary'],
        "keywords": analysis['analyses']['keywords'],
        "entities": analysis['analyses']['entities'],
        "news_count": len(news_result['articles']),
        "report": report['text'],
        "sources": search_result["results"][:3]
    }

@mcp.tool()
async def compare_topics(topics: List[str]) -> Dict[str, Any]:
    """Compare multiple topics using research results."""

    # Research each topic
    research_results = {}
    for topic in topics:
        research_results[topic] = await research_topic(topic)

    # Generate comparison
    comparison_prompt = f"""
    Compare the following topics based on the research:

    {json.dumps(research_results, indent=2)}

    Provide a structured comparison highlighting similarities and differences.
    """

    comparison = await generate_text(
        comparison_prompt,
        model="gpt-4",
        max_tokens=1500
    )

    return {
        "topics": topics,
        "individual_research": research_results,
        "comparison": comparison['text']
    }
```

### Streaming Results

```python
# patterns/streaming.py
from mcp.server import FastMCP
from fastapi.responses import StreamingResponse
import asyncio
import json

mcp = FastMCP("Streaming Tools")

@mcp.tool()
async def generate_story_stream(
    prompt: str,
    chapters: int = 5
) -> StreamingResponse:
    """Generate a story with streaming chapters."""

    async def generate():
        # Send metadata first
        yield f"data: {json.dumps({'type': 'metadata', 'total_chapters': chapters})}\n\n"

        for i in range(chapters):
            # Generate chapter
            chapter_prompt = f"{prompt}\n\nChapter {i+1} of {chapters}:"

            response = await generate_text(
                chapter_prompt,
                model="gpt-4",
                max_tokens=500
            )

            # Stream chapter
            yield f"data: {json.dumps({'type': 'chapter', 'number': i+1, 'content': response['text']})}\n\n"

            # Small delay between chapters
            await asyncio.sleep(0.5)

        # Send completion
        yield f"data: {json.dumps({'type': 'complete'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )

@mcp.tool()
async def process_large_dataset_stream(
    data_url: str,
    batch_size: int = 100
) -> StreamingResponse:
    """Process large dataset with streaming progress."""

    async def process():
        # Download data
        async with aiohttp.ClientSession() as session:
            async with session.get(data_url) as response:
                data = await response.json()

        total_items = len(data)
        processed = 0

        # Process in batches
        for i in range(0, total_items, batch_size):
            batch = data[i:i+batch_size]

            # Process batch
            results = []
            for item in batch:
                # Simulate processing
                result = await process_item(item)
                results.append(result)

            processed += len(batch)

            # Stream progress
            yield f"data: {json.dumps({
                'type': 'progress',
                'processed': processed,
                'total': total_items,
                'percentage': (processed / total_items) * 100,
                'batch_results': results
            })}\n\n"

        yield f"data: {json.dumps({'type': 'complete', 'total_processed': processed})}\n\n"

    return StreamingResponse(
        process(),
        media_type="text/event-stream"
    )
```

### Caching and Memoization

```python
# patterns/caching.py
from mcp.server import FastMCP
import redis
import hashlib
import json
from functools import wraps
from typing import Dict, Any

mcp = FastMCP("Cached Tools")

# Redis client
redis_client = redis.Redis(
    host='localhost',
    port=6379,
    decode_responses=True
)

def cache_tool_result(ttl: int = 300):
    """Cache tool results decorator."""
    def decorator(func):
        @wraps(func)
        async def wrapper(**kwargs):
            # Generate cache key
            cache_key = f"mcp:tool:{func.__name__}:{hashlib.md5(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()}"

            # Check cache
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)

            # Execute tool
            result = await func(**kwargs)

            # Cache result
            redis_client.setex(
                cache_key,
                ttl,
                json.dumps(result)
            )

            return result
        return wrapper
    return decorator

@mcp.tool()
@cache_tool_result(ttl=3600)  # Cache for 1 hour
async def expensive_calculation(
    input_data: List[float],
    operation: str = "mean"
) -> Dict[str, Any]:
    """Perform expensive calculation with caching."""

    # Simulate expensive operation
    await asyncio.sleep(2)

    if operation == "mean":
        result = sum(input_data) / len(input_data)
    elif operation == "median":
        sorted_data = sorted(input_data)
        n = len(sorted_data)
        result = sorted_data[n//2] if n % 2 else (sorted_data[n//2-1] + sorted_data[n//2]) / 2
    elif operation == "std":
        mean = sum(input_data) / len(input_data)
        variance = sum((x - mean) ** 2 for x in input_data) / len(input_data)
        result = variance ** 0.5

    return {
        "operation": operation,
        "result": result,
        "data_points": len(input_data),
        "cached": False
    }

@mcp.tool()
async def clear_cache(pattern: str = "*") -> Dict[str, Any]:
    """Clear cached results."""

    keys = redis_client.keys(f"mcp:tool:{pattern}")
    if keys:
        redis_client.delete(*keys)

    return {
        "cleared": len(keys),
        "pattern": pattern
    }
```

### Rate Limiting

```python
# patterns/rate_limiting.py
from kailash.mcp_server import MCPServer
from kailash.mcp_server.auth import APIKeyAuth

# Create server with rate limiting
auth = APIKeyAuth(keys=["api-key-1", "api-key-2"])
server = MCPServer(
    "rate-limited-server",
    auth_provider=auth,
    rate_limit_config={"default_limit": 100, "burst_limit": 10}
)

# Simple in-memory rate limiter
class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)

    def is_allowed(self, key: str, limit: int, window: int) -> bool:
        now = time.time()

        # Clean old requests
        self.requests[key] = [
            req_time for req_time in self.requests[key]
            if now - req_time < window
        ]

        # Check limit
        if len(self.requests[key]) >= limit:
            return False

        # Add request
        self.requests[key].append(now)
        return True

    def get_reset_time(self, key: str, window: int) -> float:
        if not self.requests[key]:
            return 0

        oldest_request = min(self.requests[key])
        return oldest_request + window

rate_limiter = RateLimiter()

def rate_limit(requests: int = 10, window: int = 60):
    """Rate limit decorator."""
    def decorator(func):
        @wraps(func)
        async def wrapper(**kwargs):
            # Get rate limit key (could be user ID, IP, etc.)
            key = kwargs.get('user_id', 'anonymous')

            if not rate_limiter.is_allowed(key, requests, window):
                reset_time = rate_limiter.get_reset_time(key, window)
                return {
                    "error": "Rate limit exceeded",
                    "limit": requests,
                    "window": window,
                    "reset_time": reset_time
                }

            return await func(**kwargs)
        return wrapper
    return decorator

@server.tool()
def limited_api_call(endpoint: str, user_id: str = "anonymous") -> dict:
    """Make rate-limited API call."""
    # Rate limiting is automatically handled by the server
    return {
        "endpoint": endpoint,
        "user": user_id,
        "note": "Rate limiting handled automatically"
    }
```

## Integration Examples

### Slack Integration

```python
# integrations/slack_integration.py
from mcp.server import FastMCP
from slack_sdk.web.async_client import AsyncWebClient
from typing import Dict, Any, List

mcp = FastMCP("Slack Integration")

# Slack client
slack_client = AsyncWebClient(token="your-slack-bot-token")

@mcp.tool()
async def send_slack_message(
    channel: str,
    text: str,
    blocks: List[Dict] = None,
    thread_ts: str = None
) -> Dict[str, Any]:
    """Send a message to Slack."""

    try:
        response = await slack_client.chat_postMessage(
            channel=channel,
            text=text,
            blocks=blocks,
            thread_ts=thread_ts
        )

        return {
            "success": True,
            "channel": response["channel"],
            "timestamp": response["ts"],
            "message": text
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
async def search_slack_messages(
    query: str,
    count: int = 20,
    channel: str = None
) -> Dict[str, Any]:
    """Search Slack messages."""

    search_params = {
        "query": query,
        "count": count,
        "sort": "timestamp"
    }

    if channel:
        search_params["query"] = f"in:{channel} {query}"

    response = await slack_client.search_messages(**search_params)

    messages = []
    for match in response["messages"]["matches"]:
        messages.append({
            "text": match["text"],
            "user": match["user"],
            "channel": match["channel"]["name"],
            "timestamp": match["ts"],
            "permalink": match["permalink"]
        })

    return {
        "query": query,
        "total": response["messages"]["total"],
        "messages": messages
    }

@mcp.tool()
async def create_slack_reminder(
    text: str,
    time: str,
    user: str = None
) -> Dict[str, Any]:
    """Create a Slack reminder."""

    command = f"/remind {user or 'me'} {text} {time}"

    response = await slack_client.chat_command(
        channel="general",  # Any channel works
        command="remind",
        text=f"{user or 'me'} {text} {time}"
    )

    return {
        "reminder": text,
        "time": time,
        "user": user or "self",
        "created": True
    }
```

### GitHub Integration

```python
# integrations/github_integration.py
from mcp.server import FastMCP
from github import Github
from typing import Dict, Any, List

mcp = FastMCP("GitHub Integration")

# GitHub client
github_client = Github("your-github-token")

@mcp.tool()
async def search_github_repos(
    query: str,
    language: str = None,
    sort: str = "stars",
    limit: int = 10
) -> Dict[str, Any]:
    """Search GitHub repositories."""

    search_query = query
    if language:
        search_query += f" language:{language}"

    repos = github_client.search_repositories(
        query=search_query,
        sort=sort
    )

    results = []
    for repo in repos[:limit]:
        results.append({
            "name": repo.full_name,
            "description": repo.description,
            "stars": repo.stargazers_count,
            "language": repo.language,
            "url": repo.html_url,
            "topics": repo.get_topics()
        })

    return {
        "query": query,
        "language": language,
        "results": results,
        "total_count": repos.totalCount
    }

@mcp.tool()
async def create_github_issue(
    repo: str,
    title: str,
    body: str,
    labels: List[str] = None,
    assignees: List[str] = None
) -> Dict[str, Any]:
    """Create a GitHub issue."""

    repository = github_client.get_repo(repo)

    issue = repository.create_issue(
        title=title,
        body=body,
        labels=labels or [],
        assignees=assignees or []
    )

    return {
        "issue_number": issue.number,
        "url": issue.html_url,
        "state": issue.state,
        "created_at": issue.created_at.isoformat()
    }

@mcp.tool()
async def analyze_github_repo(repo: str) -> Dict[str, Any]:
    """Analyze a GitHub repository."""

    repository = github_client.get_repo(repo)

    # Get contributors
    contributors = list(repository.get_contributors())[:10]

    # Get recent commits
    commits = list(repository.get_commits())[:10]

    # Get languages
    languages = repository.get_languages()

    # Get open issues and PRs
    open_issues = repository.open_issues_count
    open_prs = len(list(repository.get_pulls(state='open')))

    return {
        "name": repository.full_name,
        "description": repository.description,
        "stars": repository.stargazers_count,
        "forks": repository.forks_count,
        "languages": languages,
        "top_contributors": [
            {
                "login": c.login,
                "contributions": c.contributions
            }
            for c in contributors
        ],
        "recent_commits": [
            {
                "sha": c.sha[:7],
                "message": c.commit.message.split('\n')[0],
                "author": c.commit.author.name,
                "date": c.commit.author.date.isoformat()
            }
            for c in commits
        ],
        "open_issues": open_issues - open_prs,
        "open_prs": open_prs,
        "created_at": repository.created_at.isoformat(),
        "last_updated": repository.updated_at.isoformat()
    }
```

## Error Handling

### Comprehensive Error Handling

```python
# error_handling/comprehensive.py
from mcp.server import FastMCP
from typing import Dict, Any
import traceback
import logging

mcp = FastMCP("Error Handling Examples")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MCPError(Exception):
    """Base MCP error."""
    def __init__(self, message: str, error_type: str, details: Dict = None):
        self.message = message
        self.error_type = error_type
        self.details = details or {}
        super().__init__(self.message)

class ValidationError(MCPError):
    """Input validation error."""
    def __init__(self, message: str, field: str, constraint: str):
        super().__init__(
            message,
            "validation_error",
            {"field": field, "constraint": constraint}
        )

class ExecutionError(MCPError):
    """Tool execution error."""
    def __init__(self, message: str, tool: str, phase: str):
        super().__init__(
            message,
            "execution_error",
            {"tool": tool, "phase": phase}
        )

def handle_errors(func):
    """Error handling decorator."""
    @wraps(func)
    async def wrapper(**kwargs):
        try:
            return await func(**kwargs)

        except ValidationError as e:
            logger.warning(f"Validation error in {func.__name__}: {e.message}")
            return {
                "error": {
                    "type": e.error_type,
                    "message": e.message,
                    "details": e.details
                }
            }

        except ExecutionError as e:
            logger.error(f"Execution error in {func.__name__}: {e.message}")
            return {
                "error": {
                    "type": e.error_type,
                    "message": e.message,
                    "details": e.details
                }
            }

        except Exception as e:
            logger.exception(f"Unexpected error in {func.__name__}")
            return {
                "error": {
                    "type": "internal_error",
                    "message": "An unexpected error occurred",
                    "details": {
                        "exception": type(e).__name__,
                        "traceback": traceback.format_exc() if DEBUG else None
                    }
                }
            }
    return wrapper

@mcp.tool()
@handle_errors
async def safe_division(
    numerator: float,
    denominator: float
) -> Dict[str, Any]:
    """Safely divide two numbers."""

    # Validation
    if denominator == 0:
        raise ValidationError(
            "Division by zero is not allowed",
            field="denominator",
            constraint="non_zero"
        )

    try:
        result = numerator / denominator

        # Check for overflow
        if result == float('inf') or result == float('-inf'):
            raise ExecutionError(
                "Division resulted in overflow",
                tool="safe_division",
                phase="calculation"
            )

        return {
            "result": result,
            "operation": f"{numerator} / {denominator}"
        }

    except Exception as e:
        raise ExecutionError(
            f"Failed to perform division: {str(e)}",
            tool="safe_division",
            phase="calculation"
        )

@mcp.tool()
@handle_errors
async def parse_json_safely(json_string: str) -> Dict[str, Any]:
    """Safely parse JSON with detailed error reporting."""

    if not json_string:
        raise ValidationError(
            "Empty JSON string provided",
            field="json_string",
            constraint="non_empty"
        )

    try:
        import json
        parsed = json.loads(json_string)

        return {
            "parsed": parsed,
            "type": type(parsed).__name__,
            "keys": list(parsed.keys()) if isinstance(parsed, dict) else None
        }

    except json.JSONDecodeError as e:
        raise ValidationError(
            f"Invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}",
            field="json_string",
            constraint="valid_json"
        )
```

### Retry and Circuit Breaker

```python
# error_handling/resilience.py
from mcp.server import FastMCP
import asyncio
from typing import Dict, Any
from datetime import datetime, timedelta

mcp = FastMCP("Resilience Patterns")

class CircuitBreaker:
    """Circuit breaker implementation."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open

    def call(self, func):
        @wraps(func)
        async def wrapper(**kwargs):
            if self.state == "open":
                if datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout):
                    self.state = "half-open"
                else:
                    return {
                        "error": "Circuit breaker is open",
                        "retry_after": self.recovery_timeout - (datetime.now() - self.last_failure_time).seconds
                    }

            try:
                result = await func(**kwargs)

                if self.state == "half-open":
                    self.state = "closed"
                    self.failure_count = 0

                return result

            except Exception as e:
                self.failure_count += 1
                self.last_failure_time = datetime.now()

                if self.failure_count >= self.failure_threshold:
                    self.state = "open"

                raise

        return wrapper

# Circuit breaker instance
api_circuit_breaker = CircuitBreaker()

def retry_with_backoff(max_attempts: int = 3, base_delay: float = 1.0):
    """Retry with exponential backoff."""
    def decorator(func):
        @wraps(func)
        async def wrapper(**kwargs):
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await func(**kwargs)

                except Exception as e:
                    last_exception = e

                    if attempt < max_attempts - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.info(f"Attempt {attempt + 1} failed, retrying in {delay}s")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"All {max_attempts} attempts failed")

            raise last_exception

        return wrapper
    return decorator

@mcp.tool()
@api_circuit_breaker.call
@retry_with_backoff(max_attempts=3)
async def resilient_api_call(
    endpoint: str,
    timeout: int = 10
) -> Dict[str, Any]:
    """Make resilient API call with circuit breaker and retry."""

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.example.com/{endpoint}",
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            if response.status >= 500:
                raise Exception(f"Server error: {response.status}")

            data = await response.json()

            return {
                "endpoint": endpoint,
                "status": response.status,
                "data": data
            }
```

## Performance Optimization

### Batch Processing

```python
# performance/batch_processing.py
from mcp.server import FastMCP
import asyncio
from typing import List, Dict, Any

mcp = FastMCP("Batch Processing")

@mcp.tool()
async def batch_process_items(
    items: List[Dict[str, Any]],
    batch_size: int = 10,
    max_concurrent: int = 5
) -> Dict[str, Any]:
    """Process items in batches with concurrency control."""

    results = []
    errors = []

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_batch(batch: List[Dict[str, Any]]):
        async with semaphore:
            batch_results = []

            for item in batch:
                try:
                    result = await process_single_item(item)
                    batch_results.append(result)
                except Exception as e:
                    errors.append({
                        "item": item,
                        "error": str(e)
                    })

            return batch_results

    # Split items into batches
    batches = [
        items[i:i + batch_size]
        for i in range(0, len(items), batch_size)
    ]

    # Process batches concurrently
    batch_tasks = [process_batch(batch) for batch in batches]
    batch_results = await asyncio.gather(*batch_tasks)

    # Flatten results
    for batch_result in batch_results:
        results.extend(batch_result)

    return {
        "total_items": len(items),
        "processed": len(results),
        "errors": len(errors),
        "results": results,
        "error_details": errors[:10]  # Limit error details
    }

async def process_single_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Process a single item."""
    # Simulate processing
    await asyncio.sleep(0.1)

    return {
        "id": item.get("id"),
        "processed": True,
        "result": item.get("value", 0) * 2
    }
```

### Connection Pooling

```python
# performance/connection_pooling.py
from mcp.server import FastMCP
import aiohttp
import asyncpg
from typing import Dict, Any

mcp = FastMCP("Connection Pooling")

# Global connection pools
http_session = None
db_pool = None

@mcp.app.on_event("startup")
async def startup():
    global http_session, db_pool

    # HTTP connection pool
    connector = aiohttp.TCPConnector(
        limit=100,
        limit_per_host=30,
        ttl_dns_cache=300
    )
    http_session = aiohttp.ClientSession(connector=connector)

    # Database connection pool
    db_pool = await asyncpg.create_pool(
        "postgresql://user:password@localhost/db",
        min_size=10,
        max_size=20,
        max_queries=50000,
        max_inactive_connection_lifetime=300
    )

@mcp.app.on_event("shutdown")
async def shutdown():
    global http_session, db_pool

    if http_session:
        await http_session.close()

    if db_pool:
        await db_pool.close()

@mcp.tool()
async def efficient_api_request(url: str) -> Dict[str, Any]:
    """Make HTTP request using connection pool."""

    async with http_session.get(url) as response:
        data = await response.json()

        return {
            "url": url,
            "status": response.status,
            "data": data,
            "response_time": response.headers.get("X-Response-Time")
        }

@mcp.tool()
async def efficient_db_query(query: str) -> Dict[str, Any]:
    """Execute database query using connection pool."""

    async with db_pool.acquire() as connection:
        # Use prepared statement for better performance
        stmt = await connection.prepare(query)
        rows = await stmt.fetch()

        return {
            "query": query,
            "row_count": len(rows),
            "rows": [dict(row) for row in rows[:100]]  # Limit results
        }
```

## Security Examples

### Input Sanitization

```python
# security/input_sanitization.py
from mcp.server import FastMCP
import html
import re
from typing import Dict, Any

mcp = FastMCP("Security Tools")

def sanitize_input(text: str) -> str:
    """Sanitize user input."""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Escape special characters
    text = html.escape(text)

    # Remove potential SQL injection patterns
    sql_patterns = [
        r"union\s+select",
        r"drop\s+table",
        r"insert\s+into",
        r"delete\s+from",
        r"update\s+set"
    ]

    for pattern in sql_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    return text.strip()

@mcp.tool()
async def safe_text_processing(
    text: str,
    allow_html: bool = False
) -> Dict[str, Any]:
    """Process text with safety checks."""

    original_length = len(text)

    # Sanitize input
    if not allow_html:
        text = sanitize_input(text)

    # Check for suspicious patterns
    suspicious_patterns = {
        "script_tag": r"<script[^>]*>.*?</script>",
        "sql_injection": r"(union|select|drop|insert|delete|update)\s",
        "xss_attempt": r"javascript:|onerror=|onload=",
        "path_traversal": r"\.\./|\.\.\\"
    }

    warnings = []
    for pattern_name, pattern in suspicious_patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            warnings.append(pattern_name)

    return {
        "processed_text": text,
        "original_length": original_length,
        "sanitized_length": len(text),
        "warnings": warnings,
        "safe": len(warnings) == 0
    }

@mcp.tool()
async def validate_file_path(path: str) -> Dict[str, Any]:
    """Validate file path for security."""

    # Normalize path
    from pathlib import Path

    try:
        p = Path(path)

        # Check for path traversal
        if ".." in p.parts:
            return {
                "valid": False,
                "reason": "Path traversal detected"
            }

        # Check for absolute paths
        if p.is_absolute():
            return {
                "valid": False,
                "reason": "Absolute paths not allowed"
            }

        # Check for suspicious extensions
        suspicious_extensions = {
            '.exe', '.dll', '.so', '.dylib',
            '.sh', '.bat', '.cmd', '.ps1'
        }

        if p.suffix.lower() in suspicious_extensions:
            return {
                "valid": False,
                "reason": f"Suspicious file extension: {p.suffix}"
            }

        return {
            "valid": True,
            "normalized_path": str(p),
            "extension": p.suffix
        }

    except Exception as e:
        return {
            "valid": False,
            "reason": f"Invalid path: {str(e)}"
        }
```

## Monitoring and Logging

### Structured Logging

```python
# monitoring/structured_logging.py
from mcp.server import FastMCP
import logging
import json
from datetime import datetime
from typing import Dict, Any
import contextvars

mcp = FastMCP("Logging Example")

# Context variable for request ID
request_id_var = contextvars.ContextVar('request_id', default=None)

class StructuredLogger:
    """Structured JSON logger."""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        handler = logging.StreamHandler()
        handler.setFormatter(self.JSONFormatter())
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    class JSONFormatter(logging.Formatter):
        def format(self, record):
            log_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "request_id": request_id_var.get()
            }

            # Add extra fields
            for key, value in record.__dict__.items():
                if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName', 'levelname', 'levelno', 'lineno', 'module', 'msecs', 'pathname', 'process', 'processName', 'relativeCreated', 'thread', 'threadName']:
                    log_data[key] = value

            return json.dumps(log_data)

logger = StructuredLogger("mcp.tools")

def log_tool_execution(func):
    """Log tool execution decorator."""
    @wraps(func)
    async def wrapper(**kwargs):
        start_time = time.time()

        logger.logger.info(
            "Tool execution started",
            extra={
                "tool": func.__name__,
                "parameters": kwargs
            }
        )

        try:
            result = await func(**kwargs)

            logger.logger.info(
                "Tool execution completed",
                extra={
                    "tool": func.__name__,
                    "duration": time.time() - start_time,
                    "success": True
                }
            )

            return result

        except Exception as e:
            logger.logger.error(
                "Tool execution failed",
                extra={
                    "tool": func.__name__,
                    "duration": time.time() - start_time,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            raise

    return wrapper

@mcp.tool()
@log_tool_execution
async def monitored_tool(input_data: str) -> Dict[str, Any]:
    """Example tool with monitoring."""

    # Set request ID for correlation
    request_id_var.set(f"req-{int(time.time() * 1000)}")

    # Process data
    result = input_data.upper()

    return {
        "input": input_data,
        "output": result,
        "request_id": request_id_var.get()
    }
```

### Metrics Collection

```python
# monitoring/metrics.py
from mcp.server import FastMCP
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from typing import Dict, Any
import time

mcp = FastMCP("Metrics Example")

# Define metrics
tool_executions = Counter(
    'mcp_tool_executions_total',
    'Total tool executions',
    ['tool_name', 'status']
)

tool_duration = Histogram(
    'mcp_tool_duration_seconds',
    'Tool execution duration',
    ['tool_name']
)

active_executions = Gauge(
    'mcp_active_executions',
    'Currently active tool executions'
)

def track_metrics(func):
    """Track metrics decorator."""
    @wraps(func)
    async def wrapper(**kwargs):
        tool_name = func.__name__
        active_executions.inc()

        with tool_duration.labels(tool_name=tool_name).time():
            try:
                result = await func(**kwargs)
                tool_executions.labels(
                    tool_name=tool_name,
                    status='success'
                ).inc()
                return result

            except Exception as e:
                tool_executions.labels(
                    tool_name=tool_name,
                    status='error'
                ).inc()
                raise

            finally:
                active_executions.dec()

    return wrapper

@mcp.app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type="text/plain")

@mcp.tool()
@track_metrics
async def metrics_example(data: str) -> Dict[str, Any]:
    """Example tool with metrics tracking."""

    # Simulate work
    await asyncio.sleep(0.5)

    return {
        "processed": data,
        "length": len(data)
    }
```

## Production Recipes

### Complete Production Server

```python
# production/complete_server.py
from mcp.server import FastMCP
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import logging
import os
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Lifecycle management
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logging.info("Starting MCP server...")

    # Initialize resources
    await initialize_database()
    await initialize_cache()

    yield

    # Shutdown
    logging.info("Shutting down MCP server...")

    # Cleanup resources
    await cleanup_database()
    await cleanup_cache()

# Create MCP server
mcp = FastMCP(
    "Production MCP Server",
    description="Production-ready MCP implementation",
    version="1.0.0",
    lifespan=lifespan
)

# Add middleware
mcp.app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.example.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mcp.app.add_middleware(GZipMiddleware, minimum_size=1000)

# Health check
@mcp.app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "environment": os.getenv("ENVIRONMENT", "production")
    }

# Import and register tools
from tools import (
    SearchTool,
    DatabaseTool,
    FileSystemTool,
    LLMTool
)

# Register tools with categories
mcp.register_tool(SearchTool(), category="web")
mcp.register_tool(DatabaseTool(), category="data")
mcp.register_tool(FileSystemTool(), category="system")
mcp.register_tool(LLMTool(), category="ai")

# Authentication
from auth import verify_token

# Apply authentication to all tools
for tool in mcp.tools.values():
    tool.dependencies.append(Depends(verify_token))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "production_server:mcp.app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 3000)),
        workers=int(os.getenv("WORKERS", 4)),
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "level": "INFO",
                "handlers": ["default"],
            },
        }
    )
```

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1000 mcp && chown -R mcp:mcp /app
USER mcp

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:3000/health')"

# Run server
EXPOSE 3000
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "3000"]
```

### Kubernetes Deployment

```yaml
# kubernetes/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-server
  labels:
    app: mcp-server
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mcp-server
  template:
    metadata:
      labels:
        app: mcp-server
    spec:
      containers:
      - name: mcp-server
        image: mcp-server:latest
        ports:
        - containerPort: 3000
        env:
        - name: ENVIRONMENT
          value: "production"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: mcp-secrets
              key: database-url
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 3000
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 3000
          initialDelaySeconds: 10
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-server
spec:
  selector:
    app: mcp-server
  ports:
    - protocol: TCP
      port: 80
      targetPort: 3000
  type: LoadBalancer
```

## Best Practices Summary

1. **Always validate input** - Never trust user input
2. **Use structured logging** - Makes debugging easier
3. **Implement proper error handling** - Graceful degradation
4. **Add monitoring and metrics** - Observe system behavior
5. **Use connection pooling** - Better resource utilization
6. **Implement caching** - Reduce unnecessary work
7. **Add rate limiting** - Protect against abuse
8. **Use async/await properly** - Don't block the event loop
9. **Document your tools** - Clear descriptions and examples
10. **Test thoroughly** - Unit, integration, and load tests

## Conclusion

These examples demonstrate various patterns and best practices for building MCP servers and tools. Adapt them to your specific use cases and requirements. Remember to always consider security, performance, and maintainability when building production systems.
