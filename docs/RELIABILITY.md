# v0.4 reliability preview — Tamken Digital

New runs use checkpoint v3. Old v2 checkpoints remain readable with show, but are deliberately not resumable or approvable by the new orchestrator: keep the v0.3 branch for archival access and start a new run. This is a local integrity check, not cryptographic authentication against a writer who can modify all files. Never share state files containing private prompts.

The global call limit includes specialist and main-role attempts; reserves are persisted before dispatch, and unfinished reservations remain charged. Specialist outputs are checkpointed at layer boundaries. A hard crash can lose outputs of an in-flight layer, not the reservation. Custom specialists remain a pre-stage, not arbitrary repairable DAG nodes. The original task contract is distinct from generated specialist evidence.

The platform defaults to one automatic schema-recovery attempt per role and revision round; --output-retries 0 disables it, 2 increases it. All attempts share the original call budget. Unknown policy errors, transport failures and suspected secrets do not automatically retry. Manual resume may try again within the budget. Error codes are allowlisted, never raw provider responses. Review counts and criterion IDs are explicit; Ollama gets a schema object, other providers receive it in the prompt. Local validation remains authoritative. No missing review is fabricated. No automatic model fallback or publication.

Reports include attempt IDs, UTC timestamps for completed attempts, known token subtotals even when aggregate usage is incomplete, and a unified call count (the legacy total_calls_this_invocation field is a cumulative alias). No monetary cost guarantee. The secret scanner is heuristic, not DLP.

Tests are fixtures, not live inference. Native Antigravity/Codex coordination was performed by the hosts using the skill; neither is a runtime adapter yet. Laravel/MySQL deterministic cross-artifact validation, generic artifact store, configurable DAG workers, native adapters, learning and interactive dashboard remain future work. Do not claim production readiness.

## Deterministic declared-reference checks

Run `python -m factory.platform contract-check examples/artifact-contract.json examples/artifact-references.json`. Returns exit 2 for mismatches, 1 for malformed inputs, 0 for a passing manifest. Covers missing entities/fields, type mismatches, forbidden null writes, and enum values. It does not discover undeclared references or parse real PHP/SQL; it is an opt-in check, not an automatically enforced gate in the model pipeline. Output digests bind saved role outputs to successful attempts; terminal state is revalidated by show/resume/approve and corrupt v3 summaries are marked CORRUPT. Local digest checks are not signatures.
