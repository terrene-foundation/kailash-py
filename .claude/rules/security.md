# Security Rules

## Scope
These rules apply to ALL code changes in the repository.

## MUST Rules

### 1. No Hardcoded Secrets
All sensitive data MUST use environment variables.

**Detection Patterns**:
```
❌ api_key = "sk-..."
❌ password = "admin123"
❌ AWS_SECRET_ACCESS_KEY = "..."
❌ DATABASE_URL = "postgres://user:pass@..."
```

**Correct Pattern**:
```
✅ api_key = os.environ.get("API_KEY")
✅ password = os.environ["DB_PASSWORD"]
✅ from dotenv import load_dotenv; load_dotenv()
```

**Enforced by**: security-reviewer agent, pre-commit hook
**Violation**: BLOCK commit

### 2. Parameterized Queries
All database queries MUST use parameterized queries or ORM.

**Detection Patterns**:
```
❌ f"SELECT * FROM users WHERE id = {user_id}"
❌ "DELETE FROM users WHERE name = '" + name + "'"
```

**Correct Pattern**:
```
✅ "SELECT * FROM users WHERE id = %s", (user_id,)
✅ cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
✅ User.query.filter_by(id=user_id)  # ORM
```

**Enforced by**: security-reviewer agent
**Violation**: BLOCK commit

### 3. Input Validation
All user input MUST be validated before use.

**Applies to**:
- API endpoints
- CLI inputs
- File uploads
- Form submissions

**Required Validations**:
- Type checking
- Length limits
- Format validation (email, URL, etc.)
- Whitelist when possible

**Enforced by**: security-reviewer agent
**Violation**: HIGH priority fix

### 4. Output Encoding
All user-generated content MUST be encoded before display.

**Applies to**:
- HTML templates
- JSON responses
- Log output

**Detection Patterns**:
```
❌ element.innerHTML = userContent
❌ dangerouslySetInnerHTML={{ __html: userContent }}
```

**Correct Pattern**:
```
✅ element.textContent = userContent
✅ DOMPurify.sanitize(userContent)
✅ html.escape(userContent)
```

**Enforced by**: security-reviewer agent
**Violation**: HIGH priority fix

## MUST NOT Rules

### 1. No eval() on User Input
MUST NOT use eval(), exec(), or similar on user-controlled data.

**Detection Patterns**:
```
❌ eval(user_input)
❌ exec(user_code)
❌ subprocess.call(user_command, shell=True)
```

**Consequence**: BLOCK commit

### 2. No Secrets in Logs
MUST NOT log sensitive data (passwords, tokens, PII).

**Detection Patterns**:
```
❌ logger.info(f"User logged in with password: {password}")
❌ print(f"API key: {api_key}")
```

**Consequence**: CRITICAL fix required

### 3. No .env in Git
MUST NOT commit .env files to version control.

**Required**:
- .env in .gitignore
- .env.example for templates (no real values)

**Consequence**: History rewrite required if committed

## Kailash-Specific Security

### DataFlow Models
- Use proper access controls on models
- Validate inputs at model level
- Never expose internal IDs directly

### Nexus Endpoints
- Authentication on all protected routes
- Rate limiting enabled
- CORS properly configured

### Kaizen Agents
- Prompt injection protection
- Sensitive data filtering in prompts
- Output validation

## Exceptions
Security exceptions require:
1. Written justification
2. Approval from security-reviewer
3. Documentation in security review
4. Time-limited (must be remediated)
