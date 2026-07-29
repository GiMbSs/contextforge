# MVP Acceptance Report

**Release:** ContextForge 0.1.0

**Initial acceptance:** 2026-07-26

**Latest revalidation:** 2026-07-29

**Reference:** CF-014 I100 — Execute the canonical MVP acceptance scenario

## Summary

The canonical MVP acceptance scenario was executed successfully against a
controlled fixture project. All 13 steps completed without errors and produced
auditable artifacts.

The scenario was reexecuted after the retrieval, grounded-response validation,
evaluation-gate, and reproducible-release improvements. The same 13-step
workflow passed without changing its approval or mutation boundaries.

## Fixture project

```text
acceptance_project/
├── .contextforge/
│   └── config.toml
└── src/
    └── example.py
```

`src/example.py`:

```python
def greet(name: str) -> str:
    return f'Hello, {name}!'
```

## Scenario steps

| Step | Command / Operation | Result |
|------|---------------------|--------|
| 1 | Initialize project | `.contextforge` metadata created |
| 2 | Scan project | Inventory produced with artifact count >= 1 |
| 3 | Build index | Project index produced successfully |
| 4 | Submit analysis task | Analysis-only task completed with mock provider |
| 5 | Inspect retrieved context | Context bundle summary available |
| 6 | Inspect prompt measurements | Prompt measurements available |
| 7 | Invoke local provider | Patch task executed through the production provider pipeline |
| 8 | Generate validated Patch Proposal | Structured patch proposal created for `src/contextforge_generated.py` |
| 9 | Review proposal | One create operation identified |
| 10 | Approve exact proposal | Proposal approved with non-interactive binding |
| 11 | Apply proposal safely | File created; status `applied` |
| 12 | Verify resulting project fingerprint | Fingerprint changed after mutation |
| 13 | Confirm traceability and diagnostics | Diagnostics command returned healthy status |

## Generated artifact

The acceptance scenario created `src/contextforge_generated.py`:

```python
value = 42
```

## Evidence

- Automated test: `tests/test_acceptance_scenario.py`
- Transcript produced by the test: `.contextforge/acceptance/transcript.json`
  inside the fixture project.
- Latest validation command:
  `pytest -q tests/test_acceptance_scenario.py -s`
- Latest result: `1 passed` on 2026-07-29.

## Known limitations

- The acceptance scenario uses the deterministic mock provider. Real remote
  providers require separate configuration and credentials.
- Retrieval and context construction use the production scanner, Python-aware
  index, lexical and structural ranking, evidence budgeting, and filesystem
  materialization pipeline.
- The deterministic mock provider is used so acceptance remains reproducible
  and does not require network access.

## Conclusion

The MVP acceptance scenario demonstrates that ContextForge 0.1.0 can:

- initialize a project;
- scan and index a project;
- execute an analysis-only task with the local mock provider;
- inspect context, prompt, and provider state;
- generate, review, approve, and apply a patch proposal safely;
- preserve traceability and diagnostics throughout the workflow.

The release candidate is accepted subject to the known limitations above.
