# ContextForge — Effectiveness Evaluation Plan

**Document ID:** CF-015  
**Repository path:** `docs/planning/CF-015-EFFECTIVENESS-EVALUATION-PLAN.md`  
**Status:** Completed

**Version:** 1.0.0

**Baseline:** ContextForge main after commit `56f9ac6`

**Purpose:** Measure whether ContextForge selects useful context and improves
software-engineering outcomes, beyond verifying that its implementation is
technically correct.

---

## 1. Objective

Build a deterministic, offline-first evaluation harness that answers:

1. Did retrieval find the artifacts required to solve the task?
2. How much irrelevant context was selected?
3. Did ranking place the most important evidence first?
4. Did the Context Bundle preserve required evidence within its budget?
5. Did the generated analysis or patch satisfy the task?
6. Does ContextForge outperform simple context-selection baselines?
7. Did a change improve quality without unacceptable cost or latency?

The harness SHALL produce machine-readable results and a concise human-readable
report. It SHALL support local execution and an optional CI regression gate.

## 2. Scope

### 2.1 Included

- Versioned fixture projects with deterministic tasks.
- Gold relevance judgments for files and, where useful, symbols.
- Retrieval, ranking, context, analysis, and patch outcome metrics.
- Simple baselines for meaningful comparison.
- Mock-provider evaluation for deterministic CI.
- Optional real-provider runs that are explicitly enabled.
- JSON result artifacts and Markdown summaries.
- Threshold-based regression detection.

### 2.2 Not included initially

- A public benchmark leaderboard.
- Automatic LLM-as-judge scoring in required CI.
- Network access during the default evaluation.
- Provider cost optimization across commercial vendors.
- Training, fine-tuning, or prompt search.
- Broad multi-language coverage before the Python benchmark is stable.

## 3. Evaluation principles

1. **Deterministic before subjective:** required CI metrics must be reproducible.
2. **Gold data is versioned:** tasks and expected evidence change only through
   reviewed repository changes.
3. **No benchmark leakage:** expected answers and relevance labels must not be
   included in generated task context.
4. **Quality and cost are separate:** a quality gain may not conceal excessive
   context size or latency.
5. **Baselines are mandatory:** absolute scores without comparison are
   insufficient.
6. **Failures remain inspectable:** every score must be traceable to task,
   selected evidence, configuration, and implementation version.
7. **Real-provider evaluation is optional:** CI must not require credentials,
   internet access, or nondeterministic external services.

## 4. Proposed architecture

```text
Evaluation Suite
    ├── Fixture Project
    ├── Task Specification
    ├── Gold Relevance Labels
    └── Expected Outcome
             │
             ▼
Evaluation Runner
    ├── ContextForge strategy
    ├── lexical-only baseline
    └── explicit/all-files baseline
             │
             ▼
Metric Calculators
    ├── retrieval and ranking
    ├── context efficiency
    ├── analysis evidence
    ├── patch correctness
    └── latency and size
             │
             ▼
Result Storage
    ├── result.json
    └── report.md
```

Recommended package boundary:

```text
src/contextforge/evaluation/
    models.py
    metrics.py
    runner.py
    reporting.py
    ports.py

src/contextforge/adapters/evaluation/
    filesystem.py

tests/fixtures/evaluation/
    suites/
    projects/
```

Evaluation code SHALL consume public application/domain contracts where
possible. It SHALL NOT add benchmark-specific decisions to retrieval,
context-building, provider, or patch domain modules.

## 5. Dataset contracts

Each evaluation case SHALL contain:

- Stable case identifier.
- Fixture project identifier and immutable fixture fingerprint.
- Task text and task kind.
- Requested output type.
- Required relevant artifact paths.
- Optional supporting artifact paths.
- Optional relevant symbols.
- Explicitly irrelevant distractors when useful.
- Expected analysis evidence or patch outcome.
- Context budget and strategy configuration.
- Tags such as `retrieval`, `dependency`, `analysis`, or `patch`.

Gold relevance levels:

- `required`: omission makes the task unsolvable or incorrect.
- `supporting`: useful evidence that improves completeness.
- `irrelevant`: known distractor used to measure precision.
- Unlabeled artifacts are neutral and SHALL NOT automatically count as
  irrelevant.

Fixture projects must be small enough to inspect manually, but realistic enough
to include naming ambiguity, dependency chains, distractors, and budget
pressure.

## 6. Metrics

### 6.1 Retrieval and ranking

- Required-artifact recall.
- Supporting-artifact recall.
- Precision over judged artifacts.
- Recall at K.
- Mean reciprocal rank for the first required artifact.
- Normalized discounted cumulative gain when graded relevance is present.
- Complete-evidence rate: percentage of cases containing every required item.

### 6.2 Context Bundle

- Required evidence retained after budgeting.
- Supporting evidence retained after budgeting.
- Context precision over judged items.
- Context byte and token estimates.
- Budget utilization.
- Irrelevant-context ratio.
- Truncation or exclusion reason distribution.

### 6.3 Analysis outcomes

Deterministic mock-provider scenarios SHALL verify:

- Required evidence references are present.
- References bind to the evaluated Context Bundle.
- Unsupported references are rejected.
- Expected structured findings are present.

Real-provider runs MAY add rubric scores, but SHALL be reported separately from
required deterministic metrics.

### 6.4 Patch outcomes

- Expected files changed.
- Unexpected files changed.
- Expected operation types.
- Resulting fixture tests passed.
- Patch application status.
- Project fingerprint after application.
- Rollback/recovery behavior when the case exercises failure paths.

Patch effectiveness SHALL be determined by project state and executable tests,
not by textual similarity to a reference patch.

### 6.5 Operational cost

- Scan, index, retrieval, context, and total wall-clock duration.
- Artifact and candidate counts.
- Context bytes and estimated tokens.
- Incremental reuse counts.
- Provider invocation count.

Performance metrics SHALL initially be informational. Regression thresholds
should be introduced only after stable baselines exist.

## 7. Baselines

Every retrieval evaluation SHALL compare ContextForge with at least:

1. Lexical-only ranking using the task text.
2. Explicit-reference-only selection when the task contains paths or symbols.
3. Deterministic all-files selection limited by the same context budget.

A baseline must use the same fixture snapshot and budget. Reports SHALL show
both absolute scores and deltas from each baseline.

## 8. Implementation increments

### CF-015-E001 — Immutable evaluation models

Implement suite, case, relevance judgment, strategy result, metric result, and
run result models.

Acceptance criteria:

- Invalid identifiers, paths, duplicate labels, and contradictory judgments
  fail closed.
- Serialization ordering is deterministic.
- Models contain no filesystem or provider behavior.

### CF-015-E002 — Filesystem suite loader

Load versioned cases and fixtures through a dedicated adapter.

Acceptance criteria:

- Paths cannot escape the evaluation root.
- Fixture fingerprints are verified before execution.
- Schema errors identify the exact case and field.
- Gold labels are never copied into task context.

### CF-015-E003 — Retrieval and ranking metrics

Implement recall, precision, Recall@K, reciprocal rank, NDCG, and
complete-evidence rate.

Acceptance criteria:

- Metrics have table-driven unit tests.
- Empty and partially judged result sets have explicit semantics.
- Scores are deterministic and bounded.

### CF-015-E004 — Context efficiency metrics

Evaluate post-budget Context Bundles and record exclusion reasons, size, and
required-evidence preservation.

Acceptance criteria:

- Retrieval quality and Context Bundle quality are reported separately.
- Budget pressure cases demonstrate measurable evidence loss or preservation.
- Token estimates use the existing prompt measurement contracts.

### CF-015-E005 — Baseline strategies

Implement lexical-only, explicit-only, and budgeted all-files baselines behind
an evaluation strategy port.

Acceptance criteria:

- Baselines cannot mutate fixture projects.
- All strategies receive identical task, project snapshot, and budget.
- Reports calculate deltas against each baseline.

### CF-015-E006 — End-to-end evaluation runner

Compose scan, index, retrieval, context construction, optional provider
validation, and patch validation for selected cases.

Acceptance criteria:

- Default execution is offline and deterministic.
- Cases can be filtered by identifier and tag.
- A failed case does not prevent remaining cases from producing results.
- Run metadata records configuration and source revision when available.

### CF-015-E007 — JSON and Markdown reporting

Persist a versioned result document and render a concise comparison report.

Acceptance criteria:

- JSON is stable and machine-readable.
- Markdown shows failures, regressions, baseline deltas, and aggregate metrics.
- Reports do not expose secrets or absolute local paths.

### CF-015-E008 — CLI and optional CI regression gate

Add an explicit command such as:

```bash
contextforge evaluate tests/fixtures/evaluation/suites/core.json \
  --output .contextforge/evaluations/latest
```

Acceptance criteria:

- Read-only evaluation is the default.
- Patch cases operate only on isolated temporary fixture copies.
- Threshold failure returns a stable nonzero exit code.
- CI initially runs a small deterministic smoke suite.
- Threshold changes require a reviewed benchmark update.

## 9. Initial benchmark suite

The first suite SHOULD contain 12–20 Python cases covering:

- Direct filename reference.
- Direct symbol reference.
- Lexical synonym mismatch.
- Dependency closure across two and three files.
- Competing symbols with similar names.
- Test-to-implementation navigation.
- Configuration plus implementation dependency.
- Context budget pressure with distractors.
- Explanation requiring multiple evidence sources.
- Single-file modification.
- Multi-file modification.
- Unsafe or stale patch rejection.

At least one case must be intentionally unsolvable from the available project
to verify that the system reports insufficient evidence rather than fabricating
confidence.

## 10. Initial quality gates

Do not define aggressive pass thresholds before collecting the first baseline.
The first CI gate SHALL require:

- Evaluation schema validity.
- Deterministic repeated results.
- No crash or unhandled case.
- 100% recall of required evidence in a small smoke subset designed for direct
  references.
- No unexpected file mutation.

After two stable baseline runs, record reviewed thresholds for:

- Required-artifact recall.
- Complete-evidence rate.
- Context irrelevant ratio.
- Patch fixture-test pass rate.
- Maximum permitted regression from the stored baseline.

## 11. Deliverables

- Evaluation domain/application contracts.
- Filesystem suite adapter.
- Versioned core fixture suite.
- Baseline strategies.
- Metric calculators.
- Offline evaluation runner.
- JSON schema/versioned result format.
- Markdown report renderer.
- CLI integration.
- CI smoke evaluation.
- User and contributor documentation.

## 12. Completion criteria

CF-015 is complete when:

1. A fresh checkout can run the core evaluation offline.
2. Results are deterministic across supported operating systems.
3. Retrieval and Context Bundle quality are measured separately.
4. ContextForge is compared with documented baselines.
5. Patch cases are evaluated through resulting project behavior.
6. Reports identify the exact evidence behind failures.
7. CI detects a deliberate quality regression in a controlled test.
8. No benchmark code weakens production security or approval boundaries.

## 13. Completion record

CF-015-E001 through E008 are implemented. The reviewed `core` 1.2 suite contains
12 deterministic cases and is compared with all-files, explicit-only, and
lexical baselines. CI applies minimum quality thresholds and a maximum
irrelevant-context ratio. JSON and Markdown reports remain offline and
reproducible.

The next evaluation expansion should be tracked in a new planning document and
should focus on opt-in live-provider answer quality and larger multilingual
fixtures without adding network or credential requirements to the default CI
gate.
