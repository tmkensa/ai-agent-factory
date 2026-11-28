# v0.5 dynamic team preview — Tamken Digital

The existing v0.4 run path is unchanged when --team is omitted; v3 checkpoints remain resumable on that path. The opt-in dynamic path uses checkpoint v4. It is a model-call DAG, not a native process/session adapter, and only drafts/reviews. No shell, arbitrary file writes, or autonomous tools.

## Inspect and execute

    python -m factory.platform team-plan examples/architecture.ar.json --team examples/team-checklist.json --workers 2
    python -m factory.platform --project dynamic-demo run examples/architecture.ar.json --team examples/team-checklist.json --calls 18
    python -m factory.platform --project dynamic-local --route ollama/qwen2.5-coder:3b --output-retries 2 run examples/architecture.ar.json --team examples/team-checklist.json --workers 2 --calls 24

Use --team auto (fixed heuristic), single (one producer plus three mandatory reviewers), multi (up to four criterion-focused specialists), or an operator-authored JSON plan. The custom plan defines up to eight specialists, dependencies, and exactly one owner per criterion (zero-based order). Mandatory executor, security, tester and evaluator are generated and cannot be replaced or removed. The executor receives all specialist artifacts; reviewers see the draft and evaluator also sees the two reviews. Direct dependencies are passed in full, with a bounded context; previous producer output is included during repair. No silent truncation, token counting or semantic retrieval in this stage.

An explicit per-agent route is supported, e.g. --role-route agent:backup=ollama/model. The generic specialist route remains available. Cloud routes still require --allow-cloud. Choose model IDs and data transfer deliberately. No fallback or new tool permissions are inferred.

## Repair and provenance

Each call is charged before dispatch. Independent layers run with 1–4 workers. A failed/aborted reservation stays charged. Every valid artifact version is stored in the local checkpoint with its digest and dependency attempt IDs. The review record maps a failed criterion to its preassigned owner; unstructured critical issues default to executor. Rerun that owner and all descendants, including all mandatory reviewers, retaining unrelated outputs. Previous producer artifact and assigned feedback are supplied; a downstream specialist receives revised dependencies. Stop on identical producer artifacts and repeated failure signature, two revision rounds, budget exhaustion, or a hard error. No score overrides veto. The convergence rule is deliberately conservative, not semantic equivalence.

Use the existing show/resume/approve commands with the same project and route configuration. show includes full stored artifact contents; use synthetic data and keep checkpoint files private. Approval exports only the exact approved Markdown draft, never a runnable project. The ledger detects inconsistent local state, not an attacker with arbitrary write access. It does not discover omitted schema references or run Laravel/MySQL. The separate contract-check command remains opt-in. Native host adapters, AI-generated autonomous agent plans, learned routing, advanced artifact storage and execution sandboxing remain later stages.

## Verification

Unit tests use deterministic doubles or mocked transport; they do not establish live-model quality or security. Re-run real Ollama, Gemini and hybrid tests after checkout. Compare scores only for matching original task contracts and interpret model review as provisional. No release or production claim.

Integration smoke additionally exercises the dynamic CLI over actual loopback HTTP with synthetic provider replies, per-agent model selection and a local digest-approved export. No live inference is performed by this fixture. The CLI plan command is read-only and makes no model calls. Approval requires explicit digest and destination but no provider credentials because it is a local export.
