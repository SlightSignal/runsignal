# Verification — September 8, 2026

Local environment: Linux, Python 3.14.7. The claimed Python 3.11 minimum is represented in prepared CI configuration; that hosted matrix has not run yet.

- **26 independent core tests passed**, recorded execution 0.055 seconds. A separate reviewing agent wrote `tests/test_core.py` and ran it against the real manifest → SQLite → analysis path. The exact transcript is `core-tests.txt`.
- **10 Firefox interaction checks passed** against the generated demo: initial counts, mixed filter, search/empty/reset, test history, selected-run new failure, duration filter, missing-shard warning, run provenance and filter reset. `tests/browser_smoke.py` creates the checking page. `browser-checks.png` shows the result; `preview.png` was also visually inspected.
- The demo reconciles 24 synthetic runs, 40 identities, 950 observations, 1 mixed-outcome test, 1 incomplete run and 6 pass-to-fail events.
- A deterministic synthetic scale check reconciled **49,751 observations across 100 runs and 500 tests**, with one missing shard, one duplicate identity, one mixed test, 51 new-failure events and one duration increase. Exact results and timing are in `benchmark.json`; rerunning the import changed no runs.
- A portable Python zipapp generated the same demo counts from an existing database. A wheel was built using installed setuptools with network/index access disabled. Packaging output and hashes are recorded in `verification.json`.
- One independent release regression passed after fixing Windows-style ZIP member paths. It runs the actual builder with simulated Windows relative paths, checks package/resource layout, and starts the archive outside the checkout with an isolated interpreter. `release-tests.txt` records the result. This was a Linux simulation, not an actual Windows execution.

The synthetic scale run imported in 0.647 seconds, analyzed in 0.282 seconds and serialized HTML in 0.117 seconds on this host. Peak process RSS was about 189 MiB, including fixture generation. The HTML was about 16.8 MiB. This is one local synthetic observation, not a browser-speed, sustained-load, competitor-performance or developer-productivity benchmark. Export currently loads history into memory.

Independent review identified permissive JSON schema typing and an arbitrary baseline after tied timestamps. Both were fixed before the final core test run. Unknown evidence, duplicate identities, missing shards and context separation are exercised by tests; this is not a proof of universal JUnit compatibility or hostile-upload security.

Browser checks used installed headless Firefox with a separate temporary profile. Host execution was approved after prior sandboxed Firefox failures; each render exited. No application server, downloaded dependency or persistent process was introduced. Mobile browsers, multi-repository history, external CI artifact adapters and actual customer reports have not been validated.

An additional report test checks that input strings containing HTML/script syntax remain JSON data. Only `textContent` is used when displaying imported identifiers in the interactive UI. Package metadata and prepared CI are reviewable source, not evidence of a PyPI or GitHub release.
