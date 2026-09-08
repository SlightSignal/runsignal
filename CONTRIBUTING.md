# Contributing

Run the standard-library suite with `python3 -m unittest discover -s tests -p 'test_*.py' -v`. No dependency installation is needed for application development.

For parser or comparison changes, include the smallest synthetic or appropriately permitted JUnit report and run manifest that demonstrate the issue. State the expected counts and comparison results. Avoid personal data, credentials, customer logs and proprietary code. Preserve distinctions between missing evidence, duplicate identities, retries and observed outcomes.

For UI changes, use `examples/make_demo.py` to generate the demo. `tests/browser_smoke.py` creates a local HTML file with interaction checks that run in a browser. It is a development check, not a hosted service.

Compatibility and observed behavior matter more than adding unsupported format names. Document semantic changes and bump the parser version when they invalidate existing evidence digests.
