# Data and comparison rules

One SQLite database represents one repository. Schema version 1 stores explicit runs and raw testcase observations; report bytes are not copied into the database. Each source has a SHA-256 digest, relative path and supplied shard name. Parser version is recorded. These are provenance references, not proof of test execution.

## Identity and context

Test identity is SHA-256 of the canonical JSON tuple `(classname, name, file)`. Shard names and parent suite labels are excluded so moving a test between shards need not reset its history. The consequence is that workspaces with identical class/name/file labels collide: use repository-relative file paths, properly namespaced class names and workflow/job metadata. Renaming a test or changing its file creates a new identity. The importer does not guess renames.

Every duplicate identity inside one run is preserved as an ambiguous observation. Ambiguous observations are excluded from transition, mixed-outcome and timing calculations. This also means retry dialects expressed as repeated testcase nodes are not silently interpreted as separate clean runs. Supported data does not have a retry-attempt model yet.

Run identity is explicit and must be unique within the database. A repeated run ID with identical source/metadata digests is a no-op. Different bytes or metadata for that ID reject the entire import transaction. Identical report bytes under distinct run IDs remain separate observations. A parser version change changes the digest; v0 does not automatically migrate existing evidence. Preserve the source artifacts and rebuild a new database if changing parser semantics.

## JUnit subset

UTF-8 `testsuite` or `testsuites` documents are supported, including nested suites and XML namespace labels. Testcase `name` is required; `classname`, `file` and `time` are optional. A single `failure` or `error` outcome counts as failed; `skipped` is separate; a testcase without outcome children is passed. Conflicting outcomes, unsupported testcase children and nonstandard status attributes become unknown. Known non-outcome children (`system-out`, `system-err`, `properties`) are ignored and their text is not retained. DTD/entity declarations are rejected.

Timing accepts finite nonnegative numbers. Missing or invalid timing is unknown, not zero. Declared suite test-count mismatches, empty reports, malformed timing, unknown outcomes, duplicates and missing declared shards appear as warnings. Any warning makes the run's evidence-completeness flag false; this is conservative and does not erase otherwise valid individual observations. Complete declared reports cannot prove that the test runner emitted its entire intended inventory.

## Comparisons

Comparisons use the same `(workflow, environment, branch)` and the run's supplied UTC-normalized start time. Import order is irrelevant. The baseline is the immediately preceding imported run in that context. A tie at the preceding timestamp makes the baseline ambiguous and suppresses the comparison; a current run with the same timestamp is also not ordered against its tie.

A new failure requires the same unambiguous test to be **observed passing in the baseline and failing in the current run**. A newly introduced failing test has no passing baseline. A skipped, absent, unknown or ambiguous baseline cannot produce this event. Resolved failures use the reverse rule. These are observations, not a claim that the current commit caused a change.

Mixed outcomes require a pass and failure for the same unambiguous test under one commit, workflow, environment and branch across distinct runs. Identical commit IDs do not prove identical external state or inputs. The UI therefore calls these mixed outcomes, not proven flaky tests.

A duration increase requires two successive comparable passing observations, a positive baseline, at least 2x elapsed testcase time and at least 0.1 seconds absolute increase. It is a simple investigation filter, not a statistically established performance regression. Summed testcase durations describe recorded test execution effort, not workflow wall time. Median values in the UI are scoped by the selected context; top-level JSON test summaries pool all contexts and must not be interpreted as a single-environment estimate.

## Bounds

- Manifest: 2 MiB; 1–1,000 runs; 1–1,000 received reports and declared shards per run.
- XML: 20 MiB per file, 100 MiB total input bytes per manifest, 100,000 testcases per report, 500,000 observations per manifest; suite nesting capped at 100.
- Paths: relative to the manifest directory; no parent traversal or symlinks.
- Dashboard: displays up to 48 run bars, 20 recent-history cells and 500 matching test rows at once. JSON export retains all imported observations; browser memory still grows with total history.

These are input limits, not performance guarantees or adversarial-upload certification. Export loads database history into memory; unbounded retention and databases approaching millions of observations need a paged design before use.
