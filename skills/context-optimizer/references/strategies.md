# Strategies

One handler per input class. Detection is by extension first, then a bounded content sniff;
`--strategy` overrides both. Each section below says what the handler scans for, what a brief that
works looks like, which flags matter, and the failure mode the handler exists to prevent.

The capability-level explanation is [`docs/context-optimizer.md`](../../../docs/context-optimizer.md).
This file is the operating detail.

## Choosing a strategy by hand

`auto` is right almost always. Force it when the extension lies:

| Situation | Force |
| --- | --- |
| A `.txt` or `.log` that is really a unified diff | `--strategy diff` |
| A `.log` that is a CI or build run | `--strategy ci` |
| A `.log` full of JSON lines you want treated as prose | `--strategy text` |
| A `.sql` you want searched textually, not parsed as a schema | `--strategy text` |
| A config file with no extension | `--strategy structured` |
| A `.txt` that is generated source | `--strategy source` |

If `inspect` reports a strategy you did not expect, that is worth a second look before packing —
the sniff is usually right and the surprise is usually informative.

## `log`

**Scans for:** severity levels and their counts, timestamp flavour, error and exception class
names, stack-trace starts and their full extent, repeated-line groups with counts and first/last
occurrence, and any line matching the brief.

**Selection priority:**

1. The first genuine failure in the file. A cascade has one cause.
2. Lines carrying an identifier from the brief.
3. Stack traces, followed to the last frame and kept whole.
4. Warnings and failure vocabulary near the above.

**Two kinds of repetition, handled differently.** This distinction is the heart of the strategy:

- **Collapsed** — a repeated line with no severity, no failure vocabulary, and no brief match is
  noise. The count survives; the copies do not. `4,821 identical health-check lines` becomes one
  omission record.
- **Sampled** — a repeated line that *does* match the brief is not noise, but forty near-identical
  `initialised bean X in Yms` lines are still forty copies of one observation. The first three and
  the last are kept and the count is reported.

The same file therefore compresses differently for different briefs, which is the point.

**Cascade suppression.** After the first occurrence of an error signature is selected, its repeats
are counted into a `cascade` omission and dropped. The exception is a repeat carrying an
identifier-strength match from the brief, and even that is capped at three.

**Flags worth reading:** `first-failure` (this is the earliest genuine failure), `cascade` (a repeat
of something already selected), `downstream` (an error after the first failure, possibly caused by
it), `credential-redacted`, `untrusted-instruction-shaped`.

**Briefs that work:**

```text
"Why did payment settlement fail for transaction 84721?"
"What happened to order 55231 between 14:00 and 14:05?"
"Which SocketTimeoutException came first and what was it calling?"
```

**Briefs that do not:**

```text
"analyse this log"          -- nothing to select on
"find all errors"           -- the map already counts them; this selects nearly at random
```

**Flags that matter:** `--window-before` / `--window-after` when the lines around an event carry
the meaning — a request/response pair, a transaction boundary, a retry sequence. Defaults are 3 and
6.

**Guarding against:** quoting 4,821 health checks while dropping the one stack trace that mattered.

## `ci`

Everything `log` does, plus CI-specific structure.

**Scans additionally for:** the failing commands as echoed by the runner, tool and language
versions, failing test names, CI markers (`##[error]`, `npm ERR!`, `BUILD FAILURE`, `--- FAIL:`),
compile and type errors, and the final summary.

**Selection priority:** a compile or type error outranks everything it broke. Four hundred
`NoClassDefFoundError` test failures caused by one `cannot find symbol` are one finding, and the
`cannot find symbol` line is the one worth the budget.

**Read the map first here.** `commands`, `tool versions`, and `failing tests` answer most triage
questions before any fragment is read: which command failed, in which environment, and how many
distinct tests are involved.

**Briefs that work:**

```text
"Which test failed first in this run, and what caused the rest?"
"Why did the Maven build fail?"
"Is this failure the product or the suite?"
```

**Guarding against:** feeding an agent four hundred cascading failures and letting it conclude
there are four hundred problems. Triage routinely finds that 42 failures are three causes.

## `sql`

**Scans for:** every `CREATE TABLE | VIEW | INDEX | FUNCTION | PROCEDURE | TYPE | SEQUENCE |
TRIGGER` and every `ALTER TABLE`, with exact source and line ranges; the foreign-key graph in both
directions.

**Selection:** tables the brief names are seeds. Foreign-key neighbours are followed to
`--relation-depth` (default 1), in both directions — "what references `payment_attempt`" is as
useful as "what `payment_attempt` references". Indexes, constraints, views, and routines attached
to a selected table come with it. Exact SQL is preserved; nothing is paraphrased.

**`--relation-depth` guidance:**

| Depth | Use it for |
| --- | --- |
| `0` | Only the tables named. A question about one table's own columns. |
| `1` | Default. The named tables plus their immediate relations. |
| `2` | A join path across an intermediate table, or a cascade-delete question. |
| `3`+ | Rarely useful. In a normalised schema depth 3 reaches most of it, which is the whole schema again. |

**Briefs that work:**

```text
"Which tables and constraints link payment_attempt to payment and merchant?"
"What does the invoicing part of this schema look like?"
"Which indexes exist on payment_attempt and what do they enforce?"
```

**Guarding against:** loading 800 unrelated tables to answer a question about three. The omission
record names how many were left out and how to reach further.

## `structured`

JSON, YAML, and XML. Three light scanners, not three parsers — a scanner gives the shape, every
node's path, and its exact line range without materialising the document, and it does not fail on
the malformed half-written payloads that show up in real evidence.

**Scans for:** top-level shape with child counts, every node path, large arrays with their element
counts, and scalar values.

**Selection:** the node's own key, or its scalar value. Deliberately **not** the full path — in a
document of four thousand orders, matching `$.orders[...]` would make every element a hit purely
because its ancestor is called `orders`. A matching scalar is promoted to its enclosing container
so the surrounding structure comes with the value.

**Frequency discounting.** A term matching almost every node discriminates nothing. Terms above the
bound are reported in the map as `non-selective` with their hit count, rather than silently
dropped. If your brief's only term shows up there, the brief needs a more specific identifier.

**The path is the provenance.** `$.orders[3178].settlement.status` locates a finding more precisely
than a line number. Both are recorded; cite the path.

**`partial-structure` is not a warning about correctness.** It means the fragment is an excerpt from
inside the document: valid evidence, not a standalone parseable document. Never hand a
`partial-structure` fragment to something that will try to parse it.

**Briefs that work:**

```text
"Find the order whose settlement failed for transaction 84721"
"Which part of this OpenAPI document describes the invoicing endpoints?"
"What is the shape of the retry configuration in this values file?"
```

**Guarding against:** truncating JSON at a character count and producing a fragment that looks
parseable and is not, with nothing saying so.

## `source`

**Scans for:** a symbol map (functions, classes, methods, types, modules), imports and
dependencies, generated-source markers, and minification (lines over 400 characters).

**Selection:** imports first as orientation, then symbols the brief names with their bodies, then
in-file call sites of those symbols as single lines. A matched method inside a matched class is not
emitted twice. Generated files are deprioritised unless the brief points at them.

**Call sites in other files are out of scope.** The host already has a repository search tool, and
reimplementing ripgrep or a language server here would be a worse version of both. The pack says
so in its notes. Use the host's search for cross-file references and pack the specific file it
points you at.

**When no symbol matches**, the strategy falls back to line windows around brief-term matches and
says it did. That is the right answer when the brief names a value rather than a function.

**Briefs that work:**

```text
"How does SettlementService settle a transaction?"
"Where is the retry limit for provider calls defined?"
"What does the generated OrderClient do with a 429?"
```

**Guarding against:** loading a 20,000-line generated client to read one method.

## `diff`

**Scans for:** every changed file with added and removed line counts, every hunk, and a class per
file: `generated`, `test`, `api-schema`, `security-sensitive`, or `code`.

**The changed-file map is always included** and is never quietly dropped to save budget. Without it
a partial diff reads like a whole one. It is written to be cheap: sixty `dist/bundle-0NN.min.js`
rows say one thing, so they collapse to one row with a count.

**Selection:** security-sensitive changes outrank everything, then API and schema changes, then
tests, then ordinary code. Generated files are heavily penalised. Both the path and the hunk
content are classified, so a security-relevant change inside an innocuously named file is still
found.

**Every diff pack carries a completeness line** stating how many hunks of how many were selected
and that the pack is **not** a complete diff review. Never let compression turn a partial diff into
a falsely complete code review — if a reviewer needs completeness, they need the diff, and the pack
should be used to decide where to start rather than to replace it.

**Briefs that work:**

```text
"Review this branch for security regressions before merge"
"Which schema or migration changes are in this diff?"
"What changed in the checkout flow, ignoring the regenerated clients?"
```

**Guarding against:** a reviewer approving a change because the one hunk that mattered was in the
93% the pack dropped without saying so.

## `text`

The fallback. Brief-term windows, repeated-line collapsing, and orientation windows at the start
and end of the input — a document's opening usually says what it is and its end usually says how it
finished.

Use it deliberately for prose, documentation sets, and CSV exports. If `auto` chose `text` for
something you expected to be structured, the input probably is not what you think it is.

## Cost notes

- `log`, `ci`, and `text` **stream**. One pass records byte offsets and per-line features but never
  the text; selected windows are read back by seeking. This is the path that makes a gigabyte-scale
  log affordable.
- `sql`, `structured`, `source`, and `diff` need the whole text to find structure, and are capped by
  `--max-read-bytes` (64 MiB default). Past the cap the runtime refuses with a clear message rather
  than being killed by the kernel.
- A 4.8 MB / 80,000-line log inspects in under a second. A 480 KB JSON document with 20,000 nodes
  packs in under 100 ms. Neither figure is a promise about your hardware; both are the order of
  magnitude to expect.
