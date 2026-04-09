# Security Rules

ALL code changes in the repository.

## No Hardcoded Secrets

All sensitive data MUST use environment variables.

**Why:** Hardcoded secrets end up in git history, CI logs, and error traces, making them permanently extractable even after deletion.

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

**Why:** Without parameterized queries, user input becomes executable SQL, enabling data theft, deletion, or privilege escalation.

```
❌ f"SELECT * FROM users WHERE id = {user_id}"
❌ "DELETE FROM users WHERE name = '" + name + "'"

✅ "SELECT * FROM users WHERE id = %s", (user_id,)
✅ cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
✅ User.query.filter_by(id=user_id)  # ORM
```

## Input Validation

All user input MUST be validated before use: type checking, length limits, format validation, whitelist when possible. Applies to API endpoints, CLI inputs, file uploads, form submissions.

**Why:** Unvalidated input is the entry point for injection attacks, buffer overflows, and type confusion across every attack surface.

## Output Encoding

All user-generated content MUST be encoded before display in HTML templates, JSON responses, and log output.

**Why:** Unencoded user content enables cross-site scripting (XSS), allowing attackers to execute arbitrary JavaScript in other users' browsers.

```
❌ element.innerHTML = userContent
❌ dangerouslySetInnerHTML={{ __html: userContent }}

✅ element.textContent = userContent
✅ DOMPurify.sanitize(userContent)
```

## MUST NOT

- **No eval() on user input**: `eval()`, `exec()`, `subprocess.call(cmd, shell=True)` — BLOCKED

**Why:** `eval()` on user input is arbitrary code execution — the attacker runs whatever they want on the server.

- **No secrets in logs**: MUST NOT log passwords, tokens, or PII

**Why:** Log files are widely accessible (CI, monitoring, support staff) and rarely encrypted, turning every logged secret into a breach.

- **No .env in Git**: .env in .gitignore, use .env.example for templates

**Why:** Once committed, secrets persist in git history even after removal, and are exposed to anyone with repo access.

## Kailash-Specific Security

- **DataFlow**: Access controls on models, validate at model level, never expose internal IDs
- **Nexus**: Authentication on protected routes, rate limiting, CORS configured
- **Kaizen**: Prompt injection protection, sensitive data filtering, output validation

## Exceptions

Security exceptions require: written justification, security-reviewer approval, documentation, and time-limited remediation plan.
