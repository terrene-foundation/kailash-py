# RAG Agent Deployment

Production deployment for a Retrieval-Augmented Generation (RAG) agent with vector database.

## Architecture

This deployment includes:
- ChromaDB vector database
- RAG-enabled Kaizen agent
- Persistent vector storage
- Document embedding and retrieval
- Semantic search capabilities

## Services

### ChromaDB
- Vector database for embeddings
- Persistent storage
- HTTP API for queries
- Exposed on port 8000

### RAG Agent
- Document processing and embedding
- Semantic search and retrieval
- Context-aware responses
- 1-2 CPU cores, 1-2GB memory

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
# Add your API keys
```

### 2. Start Services

```bash
docker-compose up -d
```

### 3. Verify ChromaDB

```bash
curl http://localhost:8000/api/v1/heartbeat
```

### 4. View Logs

```bash
docker-compose logs -f rag-agent
```

### 5. Stop Services

```bash
docker-compose down
```

## Configuration

### Environment Variables

- `KAIZEN_ENV`: Environment name
- `OPENAI_API_KEY`: OpenAI API key for embeddings
- `CHROMA_HOST`: ChromaDB host (auto-configured)
- `CHROMA_PORT`: ChromaDB port (default: 8000)

### Vector Database

ChromaDB is configured with:
- Persistent storage in `/chroma/chroma`
- Telemetry disabled
- Reset API enabled (disable in production)

## Usage

### Loading Documents

Add documents to the vector database:

```python
from chromadb import Client

client = Client(host='localhost', port=8000)
collection = client.create_collection("documents")

collection.add(
    documents=["Document content..."],
    ids=["doc1"],
    metadatas=[{"source": "file.pdf"}]
)
```

### Querying

The RAG agent automatically:
1. Converts queries to embeddings
2. Retrieves relevant documents
3. Augments context with retrieved content
4. Generates responses

## Monitoring

### ChromaDB Status

Check health:
```bash
curl http://localhost:8000/api/v1/heartbeat
```

List collections:
```bash
curl http://localhost:8000/api/v1/collections
```

### Resource Usage

```bash
docker stats kaizen-rag-agent kaizen-chromadb
```

## Production Considerations

### Scaling

For large document sets:
1. Increase ChromaDB memory
2. Use distributed ChromaDB
3. Add caching layer
4. Implement document sharding

### Performance

1. Batch document embedding
2. Cache frequent queries
3. Tune retrieval parameters
4. Monitor embedding API usage

### Security

1. Enable ChromaDB authentication
2. Use HTTPS for ChromaDB API
3. Implement access controls
4. Encrypt vectors at rest

## Troubleshooting

### ChromaDB Connection Failed

Check service status:
```bash
docker-compose ps chromadb
```

Check logs:
```bash
docker-compose logs chromadb
```

### Slow Retrieval

Increase ChromaDB resources:
```yaml
deploy:
  resources:
    limits:
      memory: 4G
```

### Storage Issues

Check volume usage:
```bash
docker volume inspect rag-agent_chroma-data
```

Clean old collections:
```bash
docker-compose exec chromadb chroma reset
```

## Next Steps

- Add document processing pipeline
- Implement batch embedding
- Add query caching with Redis
- Deploy with Kubernetes
- Add monitoring with Prometheus
- Implement vector backup strategy
