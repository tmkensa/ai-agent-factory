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
