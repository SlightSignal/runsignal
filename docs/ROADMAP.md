# From local history to a CI workbench

The initial release makes a few test-history questions inspectable. The larger direction is a portable workbench that lets teams retain their CI provider and runners while understanding results across jobs, shards and revisions.

1. **Existing artifacts, trustworthy core — implemented.** Manifest import, SQLite history, shard reconciliation, explicit uncertainty and an offline report. Validation evidence is in VERIFICATION.md.
2. **Import usability — next.** Generate manifests from exported GitHub/GitLab run metadata; add repository/workspace identities and genuine framework fixtures. Explicitly record jobs with no reports, partial attempts and retries. Do not require an account token just to try a downloaded artifact set.
3. **Comparative investigation.** Select arbitrary baselines, inspect new/missing tests, compare duration distributions and trace failure signatures under an explicit log-retention policy. Require accurate denominators and sufficient samples before labeling trends.
4. **Scale and integration.** Incremental/paged queries, retention policies, optional CI adapters and a reusable action. Keep online integration separate from the offline core. Add adapters only with clearly scoped credentials and reproducible fixtures.
5. **Optional shared service.** Team history, permissions and hosted storage could fund maintenance if users request them. This is a product hypothesis, not an implemented service or income projection.

Release gate for each increment: a concrete user workflow, documented input contract, a minimal reproduction, meaningful tests and an inspectable demo. Prefer a useful thin integration over promises to diagnose every flaky test automatically.
