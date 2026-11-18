# U2/U3 Draft Scenario Corpus Implementation Plan

> **For agentic workers:** Execute each task in order with TDD and checkpoints. No production runtime changes or model inference are in scope.

**Goal:** Create a reproducible, hash-verified synthetic draft corpus for all 60 U2/U3 scenario families, with two prompt variants per family and separate evaluator-only oracles.

**Architecture:** Keep authoring cases in a synthetic JSON source file. A small generator writes one harness/input fixture and one separate oracle fixture per variant with mode `0600`, computes SHA-256 values, and emits a schema-v2 scenario set marked `dev`/`DRAFT`. The existing scenario validator verifies paths, hashes, family split consistency, regular files, and input/oracle separation; this does not make the corpus runner-compatible or semantically reviewed.

**Tech Stack:** Python 3.12, JSON, existing `scenarios-v2.schema.json` and `validate_scenarios.py`, pytest.

**Spec:** `reports/unified/U2_BREVITY_REPRODUCTION.md`, `reports/unified/U3_MEMORY_BASELINE_PROTOCOL.md`, `reports/unified/U2_U3_SCENARIO_CATALOG.md`.

## Global Constraints

- Every identity, memory record, path, document, and system reading is synthetic.
- All 60 families and their variants stay in `dev` and `DRAFT` until independent oracle review.
- The model-visible input contains only the user prompt; harness setup stays evaluator-side and oracle content stays separate.
- Never overwrite existing fixture output; reject traversal and symlink output parents.
- Do not run local models, change production memory/schema, or start Capri.
- A valid manifest proves structural integrity only, not semantic quality or runtime compatibility.

---

### Task 1: Draft-set builder contract

**Files:**
- Create: `tests/unified/test_build_scenario_drafts.py`
- Create: `evals/unified/build_scenario_drafts.py`

**Interfaces:**
- Consumes: case dictionaries with `family_id`, `track`, `expected_decision`, `risk`, `input`, two `variants`, and an `oracle` object.
- Produces: `build_set(cases, *, root, fixture_rel_dir, manifest_rel_path, set_id)` returning a schema-v2 manifest and writing hashed input/oracle fixtures.

- [x] Write tests for content hashes, permissions, no oracle in model-visible input, schema validation, duplicate family rejection, no overwrite, and symlink parent rejection.
- [x] Run tests red before implementation.
- [x] Implement the smallest builder that makes the contract pass.
- [x] Re-run focused tests green.

### Task 2: Synthetic U2/U3 authoring source

**Files:**
- Create: `evals/unified/draft_sources/u2_u3_draft_cases.json`

- [x] Author 30 U2 and 30 U3 synthetic case families, each with two semantically equivalent prompts.
- [x] Keep runtime seed/state metadata separate from user prompt and expected oracle.
- [x] Mark all records as draft; do not call them independently reviewed or locked.
- [x] Review case IDs, coverage, and absence of any personal data before generation.

### Task 3: Generate and validate fixtures

**Files:**
- Create: `evals/unified/draft_fixtures/u2-u3-v1/` (generated input/oracle JSON files)
- Create: `evals/unified/scenario_sets/u2-u3-draft-v1.json`

- [x] Run the builder against the source catalog in a clean output location.
- [x] Validate the scenario set with `validate_scenarios.py` and assert 120 rows, 60 families, two variants per family, only `dev`/`DRAFT`.
- [x] Verify input/oracle fixture counts and the expected manifest hashes.
- [x] Confirm no model, network lookup, production memory, or Capri process was used.

### Task 4: Project evidence and limitations

**Files:**
- Modify: `evals/unified/README.md`
- Modify: `wiki/topics/evals.md`
- Modify: `wiki/project/status.md`
- Modify: `wiki/index.md`
- Modify: `wiki/log.md`

- [x] Link the generated corpus and authoring source.
- [x] Record validator/test output, hashes, dataset status, and the distinction between `DRAFT` and locked benchmark.
- [x] Keep MVP/U2/U3 acceptance status open until independent review and runtime execution.

### Task 5: Review and v2 (added 18.11 after the Codex review)

- [x] Independent read-only Codex review of v1 (shared defects: setup inside model-visible input, `http_request` tool name, non-UUID memory ids; family-level defects listed in `wiki/log.md`).
- [x] Builder writes a separate evaluator-only `*.setup.json`; schema v2 optional `setup_fixture`/`setup_fixture_sha256`; validator hashes it; `blocked_by` and `accepted_decisions` supported.
- [x] `u2-u3-draft-v2` from `draft_sources/author_u2_u3_v2.py`; v1 kept unchanged as superseded. BLOCKED: C24–C26 (U6), C30, M28, M29.
- [ ] Continue in `2026-11-18-dr2-dr3-execution-roadmap.md` (items A–E).
