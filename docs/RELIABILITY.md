# v0.4 reliability preview — Tamken Digital

New runs use checkpoint v3. Old v2 checkpoints remain readable with show, but are deliberately not resumable or approvable by the new orchestrator: keep the v0.3 branch for archival access and start a new run. This is a local integrity check, not cryptographic authentication against a writer who can modify all files. Never share state files containing private prompts.

The global call limit includes specialist and main-role attempts; reserves are persisted before dispatch, and unfinished reservations remain charged. Specialist outputs are checkpointed at layer boundaries. A hard crash can lose outputs of an in-flight layer, not the reservation. Custom specialists remain a pre-stage, not arbitrary repairable DAG nodes. The original task contract is distinct from generated specialist evidence.

The platform defaults to one automatic schema-recovery attempt per role and revision round; --output-retries 0 disables it, 2 increases it. All attempts share the original call budget. Unknown policy errors, transport failures and suspected secrets do not automatically retry. Manual resume may try again within the budget. Error codes are allowlisted, never raw provider responses. Review counts and criterion IDs are explicit; Ollama gets a schema object, other providers receive it in the prompt. Local validation remains authoritative. No missing review is fabricated. No automatic model fallback or publication.

Reports include attempt IDs, UTC timestamps for completed attempts, known token subtotals even when aggregate usage is incomplete, and a unified call count (the legacy total_calls_this_invocation field is a cumulative alias). No monetary cost guarantee. The secret scanner is heuristic, not DLP.

Tests are fixtures, not live inference. Native Antigravity/Codex coordination was performed by the hosts using the skill; neither is a runtime adapter yet. Laravel/MySQL deterministic cross-artifact validation, generic artifact store, configurable DAG workers, native adapters, learning and interactive dashboard remain future work. Do not claim production readiness.
