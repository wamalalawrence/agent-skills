# SonarQube Quality Gate Checklist

Pre-commit checklist to catch issues that would fail a SonarQube quality gate in CI/CD.

> **SonarQube typically runs in CI/CD only.** When `${SONAR_HOST_URL}` is set, that's where the
> official report lives. Use these local tools to catch issues before pushing.

## Local alternatives to SonarQube

### SonarLint (recommended)

IDE plugin that applies SonarQube rules locally in real time. Hundreds of rules out of the box
across Java, JS/TS, Python, and more — bugs, vulnerabilities, code smells, security hotspots.

- **VS Code**: install `SonarSource.sonarlint-vscode` from the Extensions marketplace
- **IntelliJ**: install "SonarQube for IDE" from the JetBrains Marketplace
- **Standalone mode (default)**: works immediately, no configuration. Sufficient for catching most
  quality-gate failures.
- **Connected mode (optional)**: when network access to `${SONAR_HOST_URL}` exists, sync the exact
  CI quality profile so local findings match the pipeline.

### SpotBugs (Java, where configured)

```bash
mvn spotbugs:check
mvn spotbugs:gui   # HTML report
```

### PMD / Checkstyle (Java, where configured)

```bash
mvn pmd:check
mvn checkstyle:check
```

### ESLint / Prettier (JS/TS, where configured)

```bash
npm run lint
npm run format:check
```

### Ruff / Pylint / mypy (Python, where configured)

```bash
ruff check .
pylint <package>
mypy <package>
```

### JaCoCo / Istanbul / coverage.py locally

```bash
mvn verify && open target/site/jacoco/index.html
# Multi-module aggregate:
open coverage/target/site/jacoco-aggregate/index.html
```

## Code smells (maintainability)

### Critical

- [ ] No unused imports
- [ ] No unused local variables or private fields
- [ ] No unused method parameters (unless interface/override contract requires them)
- [ ] No empty catch blocks — at minimum log the exception
- [ ] No empty methods without an explanatory comment
- [ ] No `System.out.println` / `console.log` / `print` debug leftovers — use a structured logger
- [ ] No commented-out code (it's in git history)

### Major

- [ ] No magic numbers — extract to named constants
- [ ] No magic strings — extract to constants or enums
- [ ] No hardcoded URLs, file paths, or configuration values
- [ ] Cyclomatic complexity ≤ 10 per method (prefer ≤ 5)
- [ ] Cognitive complexity ≤ 15 per method (SonarQube default)
- [ ] No nesting deeper than 3 levels — refactor to helpers
- [ ] Methods ≤ ~30 lines (guideline, not hard rule)
- [ ] Class length reasonable (< ~500 lines preferred)
- [ ] No duplicate string literal > 3 occurrences — extract to constant
- [ ] String concatenation in loops uses a builder
- [ ] Use diamond operator / type inference where supported

### Minor

- [ ] Consistent naming conventions
- [ ] No trailing whitespace, no unnecessary blank lines
- [ ] Boolean expressions simplified (no `if (x == true)`)
- [ ] No unnecessary boxing/unboxing
- [ ] Switch statements have a `default` case

## Bugs (reliability)

### Critical

- [ ] No potential `NullPointerException` / `undefined` access:
  - Return `Optional` (or equivalent) instead of nullable
  - Null-check parameters at system boundaries
  - Chain `Optional.map().orElse()` instead of nested null checks
- [ ] No resource leaks — try-with-resources / `using` / `with` for streams, connections, result
      sets
- [ ] No `equals()` without `hashCode()` (and vice versa) — Java
- [ ] No infinite loops without break conditions
- [ ] No division by zero — validate denominators
- [ ] Collections: check `isEmpty()` before `get(0)` / `next()`

### Major

- [ ] No unchecked type casts — use `instanceof` pattern matching where possible
- [ ] Thread safety: shared mutable state in singletons is synchronized or avoided
- [ ] No legacy date types in new Java code — use `java.time.*`
- [ ] `BigDecimal` comparisons use `compareTo()`, constructed from `String` not `double`
- [ ] Array index bounds checked when user input drives indexing
- [ ] Regex patterns compiled once (cached), not in hot paths

### Minor

- [ ] String comparisons use `.equals()` (Java) — never `==` for value comparison
- [ ] Empty-string check uses `isBlank()` / `isEmpty()` helpers
- [ ] Collection size check uses `isEmpty()` not `size() == 0`

## Vulnerabilities (security)

### Critical

- [ ] No hardcoded passwords, API keys, tokens, or secrets in source code
- [ ] No SQL injection — parameterized queries / ORM only
- [ ] No XSS — encode all user-supplied content in responses
- [ ] No command injection — never concatenate user input into shell commands
- [ ] No path traversal — validate and canonicalize file paths
- [ ] No SSRF — validate / whitelist URLs before external HTTP calls
- [ ] No deserialization of untrusted data without type validation

### Major

- [ ] No `@CrossOrigin("*")` — restrict origins explicitly
- [ ] Cryptographic algorithms current (no MD5/SHA-1 for security)
- [ ] `SecureRandom` used for security-sensitive random generation
- [ ] No sensitive data in logs (PII, passwords, tokens)
- [ ] Session and CSRF tokens handled securely
- [ ] HttpOnly and Secure flags on cookies

### Minor

- [ ] No overly permissive file permissions in code
- [ ] Temp files created securely (`Files.createTempFile()`, `mkstemp`, etc.)

## Security hotspots (manual review required)

- [ ] `@CrossOrigin` annotations justified and documented
- [ ] HTTP client calls verify SSL/TLS validation is not disabled
- [ ] Any `permitAll()` in security config is justified and narrowly scoped
- [ ] Regular expressions: no ReDoS vulnerability (avoid catastrophic backtracking)
- [ ] Reflective access justified and input-validated
- [ ] Dynamic class / module loading: no user-controlled class names

## Duplication (CPD — copy-paste detection)

SonarQube default: flags blocks > 10 duplicated lines.

- [ ] No copy-pasted code blocks — extract to shared methods or utilities
- [ ] Similar test setup: use `@BeforeEach` / fixtures / helper functions
- [ ] Similar DTO/entity patterns: consider generics or base classes
- [ ] `sonar.cpd.exclusions` reviewed (test files and locale files often legitimately excluded)

## Coverage

Typical SonarQube quality gate:

- **80%+ overall coverage** on new code (project target: `${COVERAGE_TARGET_PERCENT}` percent)
- **0 bugs** on new code
- **0 vulnerabilities** on new code

Reports:

- Java / JaCoCo: `target/site/jacoco/index.html`
- Aggregated multi-module: `coverage/target/site/jacoco-aggregate/index.html`
- JS/TS: `coverage/index.html`
- Python: `htmlcov/index.html`

Common exclusions:

- Generated code (JPA metamodel `*_` classes, generated DTOs, gRPC stubs, ORM models)
- Mappers (when they're declarative and trivially generated)

## Project-level configuration knobs

Projects may suppress specific rules via `sonar-project.properties`:

- `sonar.issue.ignore.multicriteria` — suppressed rules with justification
- `sonar.exclusions` — files excluded from analysis
- `sonar.cpd.exclusions` — files excluded from duplication detection
- `sonar.coverage.exclusions` — files excluded from coverage reporting

OWASP dependency-check integration:

- `sonar.dependencyCheck.securityHotspot=true`
- Reports: `target/dependency-check-report.html` and `.json`

## Quick self-check (ten-second mental pass)

Before committing, run through this rapid checklist:

1. **Read the diff** — `git diff --staged` — anything look wrong?
2. **Unused code?** — imports, variables, methods, parameters
3. **Null safety?** — could anything NPE / `undefined`?
4. **Resource leaks?** — streams and connections closed?
5. **Secrets?** — any hardcoded credentials?
6. **Complexity?** — any method too long or nested?
7. **Duplicates?** — copy-pasted blocks?
8. **Tests?** — coverage for all branches?
9. **Logging?** — appropriate level, no PII?
10. **Thread safety?** — shared state in singletons?
