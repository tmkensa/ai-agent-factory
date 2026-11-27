# Roadmap / خارطة الطريق

## 0.1.0 — delivered / منجز
- Portable skill, role contracts, governance guidance, bilingual documentation.
- Bounded sequential draft workflow, JSON validation, checkpoints, reports, demo and optional Ollama adapter.

## 0.2 preview — implemented on a review branch / معاينة منفذة على فرع مراجعة
- Modular executive orchestration; planner/researcher/executor/security/tester/evaluator.
- Dynamic inclusion of the researcher, validated DAG, parallel independent layers, bounded retries and resume.
- Per-role local model selection, deterministic output checks, explicit digest-bound approval for new Markdown export, project-scoped run storage, token/time measurements and optimization proposals.
- Local verification: 26 unit tests and both demo examples; no live model verification. See [architecture](docs/ARCHITECTURE.md) and [العربية](docs/ARCHITECTURE.ar.md).

## Proposed, not delivered / مقترح وغير منفذ
- 0.2: live-model integration tests, structured task and evidence schemas, measurable baseline comparison, per-role model configuration and actual token metrics.
- 0.3: declarative dependency graph, dynamic registry, isolated parallel execution, model-provider adapters with explicit data egress approval.
- 0.4: persistent project memory with retention and access control, validated tool allowlists, approval gateway, idempotent side effects, cost and wall-clock limits.
- 0.5: scheduling, monitoring, versioned optimization experiments and production hardening after security review.

الإصدارات التالية مقترحات وليست التزامات زمنية. الأولوية لاختبارات النماذج الحية ومقارنة الأداء، ثم الفرق الديناميكية والتوازي وتعدد المزودين، ثم الصلاحيات والذاكرة المنظمة والجدولة. لا تُفعّل إجراءات خارجية قبل وجود ضوابط برمجية واختبارات ومراجعة أمنية مستقلة.
