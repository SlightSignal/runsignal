# Problem and competitive evidence

Research date: September 8, 2026. The project direction came from public search, firsthand developer discussions and current official competitor documentation. A direct Google result-page open failed in the browsing tool; the available web search and primary-page tools supplied the research. No keyword-volume provider or advertising account was used. Search snippets and Google rankings cannot establish paying demand.

## Selected problem

A [developer request for CI health visibility](https://www.reddit.com/r/github/comments/1t3bmg2/tool_to_give_me_ci_health_overview/) describes a large monorepo with sharded tests and asks to see failures and changes against commits while keeping existing runners. The author later says they had not found a suitable tool. Both passages were directly inspected. This is a problem statement, not an accepted buyer, recruited user or testimonial for RunSignal.

Our initial workflow is existing JUnit artifacts → explicit run manifest → local history → portable interactive report. It addresses test history, not runner provisioning, missing-job collection, code coverage or automated root-cause diagnosis. Reduced onboarding effort and evidence clarity are hypotheses to validate through actual usage.

## Alternatives

| Alternative | Verified documented overlap | Positioning consequence |
| --- | --- | --- |
| [Allure Report 3](https://allurereport.org/docs/v3/configure/) | Local history, environment configuration, trends and status transitions | Serverless history is already available. RunSignal must earn preference through a focused artifact import experience. No comparative usability benchmark has been run. |
| [Trunk](https://docs.trunk.io/flaky-tests/detection) | Detection policies, environment variants and mixed-result signals | The underlying semantics are established. RunSignal offers a local descriptive subset, not equivalent automation. |
| [GitLab unit test reports](https://docs.gitlab.com/ci/testing/unit_test_reports/) | JUnit import, branch comparison and failure history | Existing CI providers already cover parts of the workflow. A portable repository database is useful only if users want that independence. |
| [ReportPortal](https://reportportal.io/docs/dashboards-and-widgets/WidgetCreation/) | Official indexed documentation lists trends, comparisons and flaky-test views | A mature competitor. The primary page was retrieved through search; direct open failed, and the application was not installed or evaluated. |

The [Testmo JUnit format reference](https://github.com/testmoapp/junitxml) and GitLab's documented supported subset informed the parser design. RunSignal supports a declared subset and preserves ambiguity instead of claiming universal dialect compatibility.

## Other opportunities screened

- Local CI step debugging has firsthand requests in [this developer discussion](https://news.ycombinator.com/item?id=46345827), but current tools already include [ActDebug](https://actdebug.com/) and [ci-debugger](https://github.com/murataslan1/ci-debugger). Building a new partial workflow emulator was not the chosen first product.
- Install-behavior reports have a close existing implementation in [npm-script-lens](https://github.com/Booyaka101/npm-script-lens), as an independent review found. A broad scanner clone was not selected.
- Generic CSV comparison and codebase graphs have numerous close competitors. Their presence does not prove there is no opportunity, but this screen produced a clearer concrete user problem for test history.

## Validation that still matters

The next adoption evidence is a developer successfully importing their permitted reports and answering a history question faster or more reliably than their current workflow. A comparison should use the same input with RunSignal and a named alternative, record setup time, correctness and missing functionality, and preserve failures. Stars, generated demos and repository publication are not substitutes for that result.

Potential future revenue is optional managed storage/integrations or paid implementation around the open-source core. No rate, conversion, revenue forecast or near-term subscription funding is validated. The GitHub project is an adoption experiment with a usable core, not a promise of passive income.
