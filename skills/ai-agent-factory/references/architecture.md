# Architecture reference

## Task contract
Record: project/task ID, objective, acceptance tests (mandatory vs optional), inputs and provenance, deliverable, risk level, permitted tools/resources, data classification, deadline, cost/call ceilings, and stop/approval conditions. Ask only about unresolved consequential choices.

## Role card
Each role has a name/version, objective, input/output schema, permissions, model selection rationale, acceptance tests, maximum calls, forbidden actions, handoff recipient and failure conditions. Typical roles: Lead (orchestration), Planner, Researcher, Builder, Reviewer, Security Reviewer. Select only necessary roles. A reviewer must not author the artifact it accepts; use separate context and deterministic tests, and when warranted a different model or human.

## Workflow
`Goal -> contract -> baseline -> role selection -> dependency graph -> execution -> verification -> human approval when required -> delivery -> improvement proposal`.
For failed gates, route exact failures back to the responsible role; default maximum two revision rounds; stop safely on exhaustion. Parallelize only independent operations; serialize shared writes. Each handoff contains task ID, artifact, status, provenance, evidence, assumptions, outstanding issues and next check. Checkpoint after validated output. Use idempotency keys for supported external actions; otherwise never retry uncertain side effects blindly.

## Evaluation
Define checks before work. Suggested dimensions: correctness 25%, coverage 20%, security 20%, evidence 15%, efficiency 10%, maintainability 10%. Default target 90/100; mandatory tests and critical safety failures override the score. Record test commands and actual results, not model assurances. Compare single-agent or deterministic baseline with team on same inputs, scoring and budget. Distinguish measured cost/time from estimates.

## Memory and improvement
Separate working, agent and project memory; record decisions, sources, dates and evidence. Do not turn speculation into facts. Avoid secrets and isolate projects; enforce retention and deletion rules. Track quality, failure rates, rework, latency and actual costs. Propose changes as versioned experiments with rollback; compare on fixed fixtures. Human approves policy changes and deployments. Do not claim continual learning or background schedules without actual implementation.

## Deliverables
Include what ran, output paths, verification, unresolved failures, operating instructions, permissions, rollback where relevant and next step. For build mode include runnable code, tests and README. For simulation clearly label it as such.
