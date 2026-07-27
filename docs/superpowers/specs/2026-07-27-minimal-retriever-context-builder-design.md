# Design: Minimal Context Retriever and Builder for `run --analysis-only`

**Date:** 2026-07-27  
**Topic:** minimal-retriever-context-builder  
**Status:** Approved  
**References:** CF-007, CF-008, CF-014-I030..I045, CF-014-I075

## 1. Goal

Make `contextforge run --analysis-only` produce a real `ContextBundle` that contains project content selected by a simple, deterministic lexical relevance signal.

The current CLI uses `_EmptyRetriever` and `_EmptyContextBuilder`, which always produce an empty bundle. This increment replaces those stubs with minimal working implementations.

## 2. Non-goals

- Explicit path/symbol resolution beyond simple string matching.
- Relationship traversal or dependency closure.
- Semantic or embedding-based retrieval.
- Provider-assisted retrieval.
- Task operation type influence (`explain`, `fix`, `modify`, etc.).
- Advanced coverage evaluation.

## 3. Components

### 3.1 `SimpleContextRetriever`

- **Location:** `src/contextforge/retrieval/simple_retriever.py`
- **Contract:** implements `ContextRetriever` (`retrieve(request: RetrievalRequest) -> RetrievalResult`).
- **Behavior:**
  1. Validate inputs.
  2. Normalize the task text into searchable terms using `TaskQueryNormalizer`.
  3. Generate candidates from `ProjectIndex`:
     - `SearchUnit` candidates.
     - `Symbol` candidates.
  4. Score each candidate by term overlap:
     - path match: +3
     - symbol name match: +2
     - content match: +1
  5. Sort candidates by score descending, then by size ascending, then by deterministic identifier.
  6. Select candidates under the active `ContextBudget` (`max_items`, `max_bytes`).
  7. If no candidate scores above zero, fall back to the smallest indexed artifacts until the budget is used.
  8. Build `SelectedContextItem`, `SelectionRationale`, and `RetrievalEvidence` for each selection.
  9. Return `RetrievalResult` with status `COMPLETE` or `INCOMPLETE`.

### 3.2 `SimpleContextBuilder`

- **Location:** `src/contextforge/context/simple_builder.py`
- **Contract:** implements `ContextBundleBuilder` (`build(retrieval_result, *, project_id) -> ContextBundle`).
- **Behavior:**
  1. Materialize selected items via `ContextItemMaterializer` and a `ContextContentSource` backed by the project filesystem.
  2. Order materialized items with `ContextItemOrderer`.
  3. Create one `ContextSection` (`PRIMARY_IMPLEMENTATION`) containing all items in order.
  4. Compute `ContextStatistics` (item count, byte count, character count, line count, estimated tokens, artifact count, symbol count, excerpt count).
  5. Set `ContextCoverage` to `PARTIAL` for targets and `NOT_APPLICABLE` for other dimensions.
  6. Return a validated `ContextBundle`.

### 3.3 CLI integration

- **Location:** `src/contextforge/adapters/project_commands.py`
- **Change:** in `LocalProjectCommandGateway.analyze`, replace:
  ```python
  retriever=_EmptyRetriever(),
  context_builder=_EmptyContextBuilder(),
  ```
  with:
  ```python
  retriever=SimpleContextRetriever(),
  context_builder=SimpleContextBuilder(_LocalSource(root.path)),
  ```
- The existing `_LocalSource` adapter is reused as the content source.

## 4. Data flow

```text
TaskSpecification
      │
      ▼
SimpleContextRetriever
      │
      ├── TaskQueryNormalizer
      ├── ProjectIndex (search_units, symbols, indexed_artifacts)
      └── ContextBudget
      │
      ▼
RetrievalResult
      │
      ▼
SimpleContextBuilder
      │
      ├── ContextItemMaterializer
      ├── ContextItemOrderer
      └── ContextBundleValidator
      │
      ▼
ContextBundle
```

## 5. Scoring and selection rules

### 5.1 Term extraction

- Use `TaskQueryNormalizer` to produce normalized terms.
- Filter out terms shorter than 3 characters.
- Remove a small built-in stop-word list (`the`, `and`, `this`, `that`, `for`, `with`, `from`, `into`, `about`, `explain`, `describe`, `what`, `how`, etc.).

### 5.2 Candidate scoring

For each candidate, compute:

```text
score = 3 * path_term_matches + 2 * name_term_matches + 1 * content_term_matches
```

- `path_term_matches`: unique terms found in the artifact path.
- `name_term_matches`: unique terms found in the symbol name (symbols only).
- `content_term_matches`: unique terms found in the search unit or symbol signature content.

### 5.3 Budget selection

- Iterate sorted candidates.
- Stop when `max_items` or `max_bytes` is reached.
- Estimate bytes as the full artifact size for symbol candidates and the search unit byte length for search-unit candidates.
- Record budget-excluded candidates with `SelectionReason.CONTEXT_BUDGET_EXCEEDED`.

### 5.4 Fallback

If the highest score is zero:

- Select the smallest `IndexedArtifact` records as full-artifact candidates.
- Limit to `max_items` and `max_bytes`.
- Rationale primary reason: `REQUIRED_CONTEXT`.

## 6. Error handling

- Invalid `RetrievalRequest`: raise `ValueError` (protocol consumers already validate).
- Empty `ProjectIndex`: return `RetrievalResult` with status `INCOMPLETE` and diagnostic `RETRIEVAL_NO_CANDIDATES`.
- Stale content during materialization: `ContextItemMaterializer` raises `StaleContextContentError`; `SimpleContextBuilder` catches it, emits a diagnostic, and excludes the item.

## 7. Testing strategy

### 7.1 Unit tests

- `tests/test_simple_context_retriever.py`
  - Empty index returns incomplete result.
  - Term match in search unit selects the unit.
  - Path match scores higher than content match.
  - Budget limits are respected.
  - Fallback selects smallest artifacts.
- `tests/test_simple_context_builder.py`
  - Builds bundle from fake retrieval result.
  - Materializes full artifacts and source spans.
  - Excludes stale items with diagnostic.
  - Statistics match content.

### 7.2 Integration test

- Extend `tests/test_cli_run_analysis.py` or add a new test to assert that `contextforge run --analysis-only` in a fixture project produces a non-empty `ContextBundle`.

### 7.3 Manual verification

- Run in `D:\Py_Projetos\testes`:
  ```bash
  contextforge --project "D:\Py_Projetos\testes" run --analysis-only "explain the database module"
  contextforge --project "D:\Py_Projetos\testes" context list
  ```
  Expected: `item_count > 0` and items include `db.py` content.

## 8. Quality gate

Before completion, run:

```bash
ruff format --check .
ruff check .
mypy src/contextforge
pytest
python -m build
```

## 9. Known limitations

- No explicit path resolution beyond string matching.
- No relationship traversal.
- No operation-type influence.
- Simple token counting for token estimation.
- One context section only.

## 10. Future increments

- Add explicit-reference strategy.
- Add structural relationship expansion.
- Add dependency closure.
- Add task-operation-type influence on scoring.
- Add multiple context sections.
