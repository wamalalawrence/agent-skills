# Framework And Repository Discovery

What to establish about a repository's automation stack **before** writing or changing a single
test. Discovery is not optional context-gathering; it is the step that decides which patterns are
correct here, and skipping it is how an agent ends up introducing a second framework alongside a
perfectly good one.

The governing rule:

> Prefer the repository's established automation stack unless there is evidence that it is
> inadequate for the job. Familiarity is not evidence.

## The discovery sweep

Run it once per task, cheaply, before proposing an approach. Most of it is reading, not executing.

| Dimension | What to establish | Where it usually lives |
| --- | --- | --- |
| Language and runtime | Version, package manager, build tool | `pom.xml`, `build.gradle`, `package.json`, `pyproject.toml`, `go.mod`, `Gemfile` |
| Test frameworks | One per level, and which level each covers | Dev dependencies, test directory names |
| Runner and invocation | The exact command a human runs | `README.md`, `CONTRIBUTING.md`, `Makefile`, `package.json` scripts |
| Assertion library | House style, custom matchers | Existing test files, a shared assertions helper |
| Fixtures and setup | Scope, lifetime, teardown ownership | `conftest.py`, `*Fixture*`, `beforeEach`, base test classes |
| Page / component objects | Whether an abstraction layer exists, and its shape | `pages/`, `components/`, `support/`, `*.po.ts` |
| API clients | A shared typed client, or raw HTTP per test | `clients/`, generated SDKs, `RestAssured` helpers |
| Test-data builders | Builders, factories, fakers, seeded fixtures | `factories/`, `builders/`, `*TestDataBuilder*` |
| Mocks and stubs | What is faked, at which boundary | Mock servers, dependency-injection test config |
| Container / environment deps | Docker, Testcontainers, compose files, seeded databases | `docker-compose*.yml`, `*Container*`, CI service blocks |
| Reporting | Report format, where artifacts land | Reporter config, CI upload steps |
| Coverage | Tool, thresholds, whether it gates | Coverage config, CI gate steps |
| CI commands | The command CI runs, which may differ from the local one | Workflow / pipeline files |
| Tags, groups, suites | How a subset is selected | Annotations, `@tag`, `-m marker`, `grep` config |
| Retries and quarantine | Existing retry counts, skip lists, quarantine markers | Runner config, CI flags, skip annotations |
| Parallelism and sharding | Workers, shards, isolation guarantees | Runner config, CI matrix |
| Selectors and test ids | The convention already in use | Existing tests, component source |
| Repository conventions | Naming, directory layout, review rules | `CONTRIBUTING.md`, per-module `README.md`, existing tests |

Record the answers on the blackboard. The next agent should not have to repeat this sweep.

## Recognising the ecosystem

Naming a framework is useful only for reading the repository's intent. It is never a reason to
pick one. Stacks encountered often enough to be worth recognising on sight:

```text
UI / browser     Playwright, Cypress, Selenium, WebdriverIO, Puppeteer
Mobile           Appium, Espresso, XCUITest, Detox
API              REST Assured, Karate, Supertest, requests + pytest, Postman/Newman
Unit / harness   JUnit, TestNG, pytest, Vitest, Jest, NUnit, xUnit, RSpec, Go testing
BDD              Cucumber, SpecFlow, Behave, pytest-bdd
Contract         Pact, Spring Cloud Contract, schema/OpenAPI diffing
Environment      Testcontainers, docker-compose, WireMock, MockServer, LocalStack
```

An unfamiliar framework is not a problem to route around. Read three existing tests, the runner
config, and the CI invocation; that is enough to follow the convention. Every dimension in the
sweep above is answerable from files, regardless of which product wrote them.

## When a new framework is genuinely warranted

Rare, and it needs a written tradeoff before any migration work starts. Legitimate triggers:

- The level the work needs has **no** existing harness at all — for example, the repository has UI
  tests and unit tests but nothing that can exercise the HTTP API.
- The existing tool cannot reach the surface under test (no mobile driver, no contract verifier).
- The existing tool is unmaintained or incompatible with the runtime the project has moved to.

"The existing framework is unfamiliar", "the new one is faster to write", and "the newer tool is
more popular" are not triggers. Neither is a preference expressed by whoever is holding the
keyboard, unless they own the suite.

When a trigger genuinely applies, record a decision before migrating:

```yaml
framework_decision:
  current: "<what the repository uses today>"
  proposed: "<what would replace or sit beside it>"
  trigger: "<which of the triggers above applies, with the evidence>"
  scope: replace | add-alongside | pilot-one-suite
  migration_cost: "<tests affected, CI changes, who maintains both during overlap>"
  rollback: "<how the change is undone if the pilot fails>"
  decided_by: "<the human who owns this suite>"
```

A migration that would be hard to reverse belongs in an ADR — hand it to
[`domain-modeler`](../../domain-modeler/SKILL.md) rather than deciding it inside a test task.
Without a named human owner, propose the decision and stop; do not migrate.

## Discovery failure modes

- **Writing tests before reading three existing ones.** The single most reliable source of the
  house convention is the tests already in the repository.
- **Trusting the local command as the CI command.** They diverge often — different profiles,
  different service dependencies, different tags. Read the workflow file.
- **Missing an existing abstraction and building a parallel one.** A second page-object layer or a
  second HTTP client is a maintenance tax paid forever.
- **Assuming absence from a dependency list means absence.** Vendored harnesses, internal shared
  libraries, and platform-provided runners do not always appear where you first look.
