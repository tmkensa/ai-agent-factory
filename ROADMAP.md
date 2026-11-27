# Roadmap / خارطة الطريق

## 0.1.0 — delivered / منجز
- Portable skill, role contracts, governance guidance, bilingual documentation.
- Bounded sequential draft workflow, JSON validation, checkpoints, reports, demo and optional Ollama adapter.

## 0.2 preview — implemented on a review branch / معاينة منفذة على فرع مراجعة
- Modular executive orchestration; planner/researcher/executor/security/tester/evaluator.
- Dynamic inclusion of the researcher, validated DAG, parallel independent layers, bounded retries and resume.
- Per-role local model selection, deterministic output checks, explicit digest-bound approval for new Markdown export, project-scoped run storage, token/time measurements and optimization proposals.
- Local verification: 26 unit tests and both demo examples; no live model verification. See [architecture](docs/ARCHITECTURE.md) and [العربية](docs/ARCHITECTURE.ar.md).

## 0.3 platform preview — implemented on the review branch / معاينة المنصة
- Adapters for Ollama, OpenAI, Anthropic and Gemini, explicit cloud consent, per-role routing and call/output budgets.
- User-defined specialist agents with validated dependencies and reusable skill export.
- Operator-approved public HTTPS evidence and a restricted local JSON-only MCP client.
- Digest-approved new-workspace staging and optional Docker runner for Python tests/PHP lint.
- SQLite project notes with lexical lookup and optional local embeddings; recurring job definitions with explicit tick/claim; read-only HTML dashboard; run comparison.
- Local verification: 57 unit/integration tests plus end-to-end fixture smoke. See [Platform](docs/PLATFORM.md), [العربية](docs/PLATFORM.ar.md), and [Testing](TESTING.md).

## Remaining / المتبقي
- Verify actual local and cloud model inference and model quality, actual Docker isolation/test execution and a real trusted MCP server. Resolve hosted CI billing restriction and verify the OS matrix before merge.
- Broader research/search connectors, real project editing with human-reviewed diffs, more test suites (including Laravel), scoped tool contracts and stronger approval policies.
- Encrypted memory and retention, authenticated interactive dashboard, durable scheduler service if explicitly configured, complete audit trails and concurrency/cost hardening.
- Independent security review, adversarial evaluation and measured version comparisons before a stable release.

المنصة الآن معاينة تطوير، وليست جاهزة للإنتاج. تشمل الوظائف السابقة ضمن حدود محلية وموافقات صريحة. تُستكمل الاختبارات الحية والعزل والمراجعة الأمنية قبل إصدار مستقر؛ لا تعني الاختبارات الحتمية نجاح نموذج حي.
