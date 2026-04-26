# Code Review Checklist

Generic self-review and PR-review checklist. Items prefixed by language tags apply only when
relevant.

## Secure code

- [ ] Role / permission checks restricted to least-privileged roles (no catch-all roles)
- [ ] No `permitAll()` / `allow_all` on wildcard endpoints
- [ ] JWT validation includes signature, issuer, audience, expiration
- [ ] OAuth/JWT token expiration and revocation considered
- [ ] Keys, passwords, tokens stored in config / secrets vaults — never in source code
- [ ] Password storage uses a secure algorithm (bcrypt / argon2 / scrypt)
- [ ] Input validated at every API boundary, with a vetted library
- [ ] Output encoded to prevent XSS
- [ ] Unit tests cover security-critical code paths

## Clean code

- [ ] No business logic in controllers or entity classes
- [ ] Methods short with single responsibility
- [ ] Classes have single responsibility
- [ ] Public methods documented where they clarify intent / params / business rules
- [ ] No `@SuppressWarnings` / `// eslint-disable` / `# noqa` without documented justification
- [ ] No `TODO` / `FIXME` without a linked ticket
- [ ] Consistent error-handling patterns
- [ ] Meaningful variable and method names

## API

- [ ] New endpoints documented (OpenAPI / SpringDoc / equivalent)
- [ ] New endpoints appropriately protected and authorized
- [ ] API response schemas don't expose sensitive fields (PII, credentials)
- [ ] All input validated — request bodies, path variables, headers, query params
- [ ] Exception handling via a single global handler / typed error response
- [ ] Pagination, sorting, filtering handled correctly
- [ ] HTTP status codes semantically correct
- [ ] API versioning considered for breaking changes

## Java / Spring (when applicable)

- [ ] `@Transactional` only applied to Spring-managed beans
- [ ] `@Transactional` **not** in controllers, **not** on interfaces
- [ ] Entities not directly exposed in API layer — use DTOs
- [ ] `Optional` used for nullable returns
- [ ] MapStruct (or equivalent) used for DTO/entity mapping
- [ ] No field injection (`@Autowired` on fields) — constructor injection only
- [ ] Immutable objects where possible (`@Value`, `record`)
- [ ] Spring profiles used correctly for environment-specific config

## Database / migrations

- [ ] Migration changesets have unique id and author
- [ ] Migrations backward-compatible (no dropping columns in use)
- [ ] Indexes added for frequently queried columns
- [ ] No N+1 query patterns (`@EntityGraph`, `JOIN FETCH`, eager loading reviewed)
- [ ] Transactions scoped correctly (not too broad, not too narrow)
- [ ] Multi-variant master files updated only when the change applies to that variant

## Testing

- [ ] New code meets the project coverage target (`${COVERAGE_TARGET_PERCENT}` percent or higher)
- [ ] Tests cover happy path AND error/edge cases
- [ ] Tests independent — no shared mutable state
- [ ] Test names describe the behaviour being tested
- [ ] External dependencies mocked, not called for real, in unit tests
- [ ] Integration tests scoped appropriately (`@SpringBootTest`, `@DataJpaTest`, equivalents)

## SonarQube pre-check

- [ ] No obvious code smells (unused code, complexity, duplication)
- [ ] No potential null-pointer dereferences
- [ ] No resource leaks
- [ ] No security vulnerabilities (injection, hardcoded secrets, etc.)
- [ ] See [SonarQube checklist](./sonarqube-checklist.md) for the full list

## Business logic

- [ ] Change solves the actual problem described in the ticket
- [ ] No regression to existing functionality
- [ ] Edge cases handled
- [ ] Multi-variant / multi-tenant implications considered (if applicable)
- [ ] Cross-project impact assessed (especially for shared services / libraries listed in
      `${SHARED_LIBRARY_NAMES}`)

## PR hygiene

- [ ] Check all applicable items during review
- [ ] If an item is intentionally overridden, leave a PR comment explaining why
- [ ] Merge strategy follows `${GIT_MERGE_STRATEGY}` (commonly `squash`)
- [ ] Squash commit starts with the ticket key
