# Security Checklist

OWASP-aligned security review for any backend service.

## Authentication & authorization

- [ ] Role / permission checks restricted to the minimum required roles — never use catch-all roles
- [ ] No `permitAll()` / `allow_all` on wildcard endpoints (`/**`) — scope explicitly
- [ ] JWT tokens validated: signature, issuer (`iss`), audience (`aud`), expiration (`exp`)
- [ ] Token revocation mechanism considered (especially for logout flows)
- [ ] IdP roles and scopes mapped correctly to the application's authorities
- [ ] Session management: stateless with JWT, or properly secured server-side sessions
- [ ] CORS configured restrictively — no `@CrossOrigin("*")` / `Access-Control-Allow-Origin: *` in production

## Secrets management

- [ ] No hardcoded passwords, API keys, tokens, or connection strings in source code
- [ ] Secrets stored in environment variables, Kubernetes secrets, cloud secret managers, or a vault
- [ ] Build-config credentials reference env vars (e.g. `${env.VAR}`) or CI/CD secrets, never literals
- [ ] `.env` files are gitignored — never committed
- [ ] Passwords hashed with a current algorithm (bcrypt, argon2, scrypt)

## Input validation

- [ ] All user input validated at the API boundary:
  - Request body: schema / Bean Validation annotations (`@NotNull`, `@Size`, `@Pattern`, etc.)
  - Path variables: type-safe and validated
  - Query parameters: validated and sanitized
  - Headers: validated where used for logic
- [ ] SQL injection prevented: parameterized queries / ORM only
- [ ] XSS prevented: output encoding for all user-supplied data in responses
- [ ] Command injection prevented: never concatenate user input into shell commands
- [ ] Path traversal prevented: validate all file path inputs (resolve, canonicalise, check prefix)
- [ ] SSRF prevented: whitelist / validate external URLs before HTTP calls
- [ ] Untrusted-data deserialization prevented: type-validate before deserializing

## Data protection

- [ ] Sensitive data (PII) not logged: names, emails, phone numbers, account ids
- [ ] API responses don't leak internal implementation details in errors
- [ ] Stack traces not exposed to API consumers — use a global error handler
- [ ] Database queries don't return more data than needed (avoid `SELECT *`)

## Cryptography

- [ ] TLS used for all external communication
- [ ] No MD5 or SHA-1 for security purposes — use SHA-256+
- [ ] `SecureRandom` (or platform equivalent) for security-sensitive random values
- [ ] Certificate validation **not** disabled (no `TrustAllCerts`, no `ALLOW_ALL_HOSTNAME_VERIFIER`, no `rejectUnauthorized: false`)

## Dependencies

- [ ] Dependency vulnerability scan passes (`mvn org.owasp:dependency-check-maven:check`, `npm audit`, `pip-audit`, etc.)
- [ ] No known critical CVEs in direct dependencies
- [ ] Dependencies pulled from trusted sources only
- [ ] Framework version current enough to receive security patches

## Logging & monitoring

- [ ] Security-relevant events logged: auth failures, authorization denials, input-validation failures
- [ ] Log entries include a correlation id for traceability
- [ ] No sensitive data in logs
- [ ] Log injection prevented: user input sanitized before inclusion in log messages
