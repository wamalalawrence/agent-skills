# Architecture Patterns

Common module / project structures and conventions. Use as a reference when reading or extending an
unfamiliar repo in `${WORKSPACE_ROOT}`.

## Standard multi-module layout (Java / Spring)

```
project-name/
├── pom.xml                          # Parent POM (packaging: pom)
├── settings.xml                     # Maven settings (artifact registry config)
├── lombok.config                    # Lombok config (Java)
├── spotbugs-ignore.xml              # SpotBugs false-positive suppressions
├── docker-compose.yml               # Local dev Docker services
├── project-name-api/                # API module: DTOs, interfaces, constants
│   └── src/main/java/
├── project-name-persistence/        # Persistence: entities, repositories, migrations
│   └── src/
│       ├── main/java/               # JPA entities, Spring Data repos, specs
│       ├── main/resources/liquibase/  # or db/changelog/, migrations/
│       └── test/java/
├── project-name-service/            # (or -application) Business logic + transport
│   ├── Dockerfile
│   └── src/
│       ├── main/java/               # Services, controllers, config
│       ├── main/resources/          # application.yml, templates
│       └── test/java/
└── coverage/                        # JaCoCo aggregate module
```

## Module naming conventions

| Suffix                      | Purpose              | Contains                                                      |
| --------------------------- | -------------------- | ------------------------------------------------------------- |
| `-api`                      | Public API contracts | DTOs, request/response objects, interfaces, constants, enums  |
| `-persistence`              | Data access          | JPA entities, repositories, specifications, migration scripts |
| `-service` / `-application` | Application logic    | Spring Boot app, services, controllers, config                |
| `coverage`                  | Coverage aggregation | JaCoCo aggregator POM only                                    |

API-module patterns matching `${API_MODULE_PATTERNS}` are automatically flagged by `code-reviewer`
for breaking-change risk.

## Layer responsibilities

### API module

- DTOs only — what goes over the wire
- Interfaces for services that other modules may call
- Constants and enums shared across modules
- **No framework annotations** except validation (`@NotNull`, `@Size`, etc.)

### Persistence module

- ORM entities (JPA `@Entity`, Hibernate annotations)
- Spring Data `JpaRepository` interfaces
- `Specification` classes for dynamic queries
- Migration scripts (Liquibase XML, Flyway SQL, etc.)
- Database-specific configuration

### Service / application module

- `@Service` classes with business logic
- `@RestController` classes (thin — delegate to services)
- `@ControllerAdvice` for exception handling
- `@Configuration` classes (security, web, etc.)
- Application entry point
- Dockerfile

## Key architectural rules

1. **Dependencies flow inward**: Service → Persistence → API (never the other way).
2. **Entities stay in persistence**: never expose JPA entities in API responses — map to DTOs.
3. **Business logic in services**: controllers stay thin, entities stay data holders.
4. **Use a mapper**: MapStruct (Java) or equivalent for entity ↔ DTO conversion. Hand-written
  mappers should be the exception.
5. **`@Transactional` on services only**: never on controllers, never on entities, never on
  interfaces.

## Multi-variant / multi-tenant projects

Some projects serve multiple variants (clients, tenants, regions). When that's the case:

- Configuration is variant-specific: `application-<variant>.yml`
- Migration master files may be per-variant: `master_<variant>.xml`
- Tests may need variant-specific profiles
- A change for one variant **must not break others**
- Always verify cross-variant impact before submitting changes

`SHARED_LIBRARY_NAMES` in `.env` lists the libraries / shared services where cross-variant impact is
most likely; the `code-reviewer` skill calls these out automatically when a diff touches them.

## Build commands (Java / Maven)

```bash
mvn clean verify                  # Full build with tests
mvn clean compile -DskipTests     # Quick compile check
mvn test -Dtest=SomeTest          # Run a single test class
mvn fmt:format && mvn fmt:check   # Format then verify
mvn liquibase:update              # Apply migrations to local DB
```

## Equivalent commands (Node / TypeScript)

```bash
npm ci                            # Reproducible install
npm run lint && npm run format:check
npm test
npm run build
```

## Equivalent commands (Python)

```bash
pip install -e '.[dev]'
ruff check . && ruff format --check .
pytest
mypy <package>
```

## Discovering project-specific conventions

When entering an unfamiliar repo:

1. Read `README.md` and any `CONTRIBUTING.md`.
2. Read the build manifest (`pom.xml`, `package.json`, `pyproject.toml`).
3. Check `.github/workflows/` to see what CI actually runs — that's the real definition of
  "passing".
4. Look at the most recent merged PRs to see commit style, branch style, and review depth.
5. Identify the test runner and run a single existing test to confirm the local environment works.
