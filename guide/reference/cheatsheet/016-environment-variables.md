# Environment Variables

```python
# Common environment variables for API keys
os.environ["OPENAI_API_KEY"] = "your-key"
os.environ["ANTHROPIC_API_KEY"] = "your-key"
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"

# SharePoint credentials
os.environ["SHAREPOINT_TENANT_ID"] = "your-tenant-id"
os.environ["SHAREPOINT_CLIENT_ID"] = "your-client-id"
os.environ["SHAREPOINT_CLIENT_SECRET"] = "your-secret"

# Use in node config
workflow.add_node("llm", LLMAgentNode(),
    provider="openai",
    model="gpt-4"
    # api_key will be read from OPENAI_API_KEY env var
)
```
