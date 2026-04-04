# Security Rules

ALL code changes in the repository.

## No Hardcoded Secrets

All sensitive data MUST use environment variables.

```
❌ api_key = "sk-..."
❌ password = "admin123"
❌ DATABASE_URL = "postgres://user:pass@..."

✅ api_key = os.environ.get("API_KEY")
✅ password = os.environ["DB_PASSWORD"]
✅ from dotenv import load_dotenv; load_dotenv()
```

## Parameterized Queries

All database queries MUST use parameterized queries or ORM.

```
❌ f"SELECT * FROM users WHERE id = {user_id}"
❌ "DELETE FROM users WHERE name = '" + name + "'"

✅ "SELECT * FROM users WHERE id = %s", (user_id,)
✅ cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
✅ User.query.filter_by(id=user_id)  # ORM
```

## Input Validation

All user input MUST be validated before use: type checking, length limits, format validation, whitelist when possible. Applies to API endpoints, CLI inputs, file uploads, form submissions.

## Output Encoding

All user-generated content MUST be encoded before display in HTML templates, JSON responses, and log output.

```
❌ element.innerHTML = userContent
❌ dangerouslySetInnerHTML={{ __html: userContent }}

✅ element.textContent = userContent
✅ DOMPurify.sanitize(userContent)
```

## MUST NOT

- **No eval() on user input**: `eval()`, `exec()`, `subprocess.call(cmd, shell=True)` — BLOCKED
- **No secrets in logs**: MUST NOT log passwords, tokens, or PII
- **No .env in Git**: .env in .gitignore, use .env.example for templates

## Kailash-Specific Security

- **DataFlow**: Access controls on models, validate at model level, never expose internal IDs
- **Nexus**: Authentication on protected routes, rate limiting, CORS configured
- **Kaizen**: Prompt injection protection, sensitive data filtering, output validation

## Exceptions

Security exceptions require: written justification, security-reviewer approval, documentation, and time-limited remediation plan.
