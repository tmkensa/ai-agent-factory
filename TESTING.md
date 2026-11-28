# Release verification / التحقق من الإصدار

Executed in the build environment with Python 3.13.5 on Linux:

- `python -m unittest discover -s tests -v`: 12 tests passed, covering validation, mandatory criteria, blocking issues, revision limits, resume, call budget, unsafe run IDs, locking, backend mismatch, Arabic content and mocked Ollama requests/rejections.
- `python -m factory run examples/task.en.json`: exit 0, REVIEWED_DRAFT, 3 calls, literal checklist score 100, human review required.
- `python -m factory run examples/task.ar.json`: exit 0, REVIEWED_DRAFT, 3 calls, literal checklist score 100, human review required.
- `python -m compileall -q factory tests`: exit 0.

The demo score measures literal fixture checks only, not actual AI quality. Live Ollama inference, native assistant integration, Windows/macOS execution and remote GitHub Actions have not been verified here. CI is configured for Linux and Windows on Python 3.10 and 3.12 but has not yet run on GitHub.

تم تشغيل 12 اختبارًا بنجاح على Linux وPython 3.13.5، وتشغيل المثالين العربي والإنجليزي بنجاح، وفحص ترجمة ملفات Python. درجة المثال تقيس وجود البنود نصيًا فقط. لم يُختبر نموذج Ollama حي، أو اكتشاف المهارة في أدوات البرمجة، أو Windows/macOS عمليًا. أُعد ملف CI ولم يعمل على GitHub بعد.

## Architecture v0.2 preview — local verification / التحقق المحلي

- Python 3.13.5, Linux: 26/26 unit tests passed (12 baseline + 14 new).
- Git blob hashes of the 8 new Python modules, new test file, baseline engine and baseline test file matched the review branch.
- English and Arabic demo workflows: both DEMO_COMPLETE, six calls each, 100 on fixture checks only. No actual AI or real security audit was performed.
- First GitHub Actions run 46024286840 failed in the Ubuntu 3.12 matrix entry; three other entries were cancelled. Job logs returned BlobNotFound and step details were empty. Cause remains undetermined. CI matrix now uses fail-fast: false for independent results.
- Live Ollama, real external tools, and Windows/macOS execution are not verified. Do not interpret fixture scores as real-world accuracy.

نجحت الاختبارات المحلية الـ26 على Linux، وتشغيل المثالين في الوضع التجريبي. لم يعمل نموذج ذكاء اصطناعي حقيقي، ولم يثبت نجاح اختبارات GitHub Actions بعد. سبب فشل التشغيل الأول غير معروف لأن سجلات الخطأ غير متاحة. لا يُعتمد الإصدار للإنتاج بناءً على هذه الاختبارات.

## Extended verification — 2026-11-27 / الاختبارات الموسعة

- Reconstructed the published Python sources locally and matched Git blob hashes. Original 26 tests passed on Linux, Python 3.13.5.
- Added nine regression/integration tests. Two defects were reproduced before fixing: invalid budget reservations (zero, negative, boolean and fractional), and non-verbatim research quotations accepted after trimming whitespace.
- Fixed both; 35/35 tests passed. Python compileall succeeded. Both bilingual demo examples completed with six role calls each. Their 100 scores are fixture checks only.
- Real loopback HTTP transport tested against a deterministic Ollama-compatible fixture server, including per-role routing and token reporting. Invalid JSON, redirect, oversized response, truncation, and unexpected tool calls rejected. This is not a live AI model test.
- GitHub Actions run 46024703947 (including failed-job retry) reported all four matrix jobs failed; job details/logs were unavailable (empty steps / BlobNotFound). Added an independent runner-smoke job to help isolate runner issues. No claim that CI is passing.

نجحت 35/35 من الاختبارات محليًا بعد إصلاح خللين في الميزانية والاقتباسات. اختُبر اتصال HTTP محلي بخادم ردود اصطناعية، لا بنموذج حي. لم تتوفر سجلات تشخيص فشل GitHub Actions، ولا يزال الدمج معلقًا حتى التحقق.

## Platform v0.3 preview — 2026-11-27 / تحقق المنصة

- Combined the locally verified architecture source with the new platform source: **57/57** tests passed under Linux/Python 3.13.5 (35 prior + 22 new). `python -m compileall -q factory tests` succeeded.
- `python tests/smoke_platform.py` passed all three end-to-end fixture groups: bilingual workflow, comparison, project notes/recall, simulated due schedule/claim/cancel, local dashboard, digest-bound staging and actual unit test of the staged sample; real loopback HTTP MCP list/call using a synthetic server; real loopback HTTP model adapter transport through two custom specialists plus six architecture role calls (8 fixture calls), approval/export and embedding retrieval.
- The model and MCP responses were synthetic. No live inference, public web fetch, real MCP integration, actual Docker container, Windows/macOS run or independent security audit was performed in the build environment. Provider API shapes and Docker command policy were tested with fixtures. No external API charges were incurred.
- GitHub Actions account annotation supplied by the owner: jobs did not start due to a billing/payment/spending restriction. Hosted CI is still unverified; do not merge or claim production readiness until the restriction is resolved and required checks pass.

نجحت **57/57** من الاختبارات المحلية، وثلاث مجموعات تحقق كاملة باستخدام ردود محلية حتمية. اختبرنا مسار الوكلاء المخصصين، الموافقة، الذاكرة، الجدولة، اللوحة وتجهيز الملفات. لم نشغل نموذجًا حيًا أو حاوية Docker أو خادم MCP حقيقيًا. تعذر تشغيل CI بسبب قيد فوترة الحساب الذي ظهر في رسالة GitHub. لم يثبت نجاح اختبارات Windows أو macOS أو الأمان المستقل.
