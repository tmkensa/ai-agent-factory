# Publish to GitHub / النشر على GitHub

This package is prepared for publication but has not been uploaded. Review the files, decide the owner and copyright notice, and confirm the MIT license. Do not upload run logs, credentials, or private tasks.

## GitHub CLI (Windows, Linux, macOS)

Install Git and GitHub CLI separately if needed. Open a terminal in the extracted repository root. If you already have a Git repository or remote, inspect it first and do not overwrite it. Configure your own Git identity if required.

```bash
git init -b main
git add .
git status --short
git commit -m "Initial release of AI Agent Factory"
gh auth login
gh repo create ai-agent-factory --public --source=. --remote=origin --push
```

Inspect `git status --short` before committing. The last command creates a public repository under the authenticated account and publishes your files. If the name is taken or you prefer an organization, choose the appropriate `OWNER/REPO` explicitly. Do not use force push. Verify the returned repository URL and CI results before announcing it. Optional release after review:

```bash
gh release create v0.1.0 --generate-notes
```

## بالعربية

الحزمة جاهزة للمراجعة والنشر، لكنها لم ترفع بعد. تأكد من المالك والترخيص ونسبة حقوق النشر. ثبت Git وGitHub CLI إذا لم يكونا موجودين، ثم افتح الطرفية داخل مجلد المشروع ونفذ الأوامر أعلاه. سجل الدخول عبر `gh auth login` دون مشاركة كلمة المرور أو المفتاح في المحادثة. راجع الملفات بعد `git status --short`، ثم ينشئ أمر `gh repo create` مستودعًا عامًا ويرفع الملفات إليه. تحقق من الرابط الفعلي ونتائج GitHub Actions قبل الإعلان. لا تستخدم رفعًا إجباريًا، ولا تستبدل مستودعًا موجودًا. ويمكن إنشاء إصدار v0.1.0 بعد المراجعة بالأمر الاختياري أعلاه.

بديل دون CLI: أنشئ مستودعًا عامًا فارغًا من https://github.com/new ثم ارفع الملفات والمجلدات كما هي، مع إظهار المجلدات المخفية مثل `.github` وملف `.gitignore`. لا ترفع ملف ZIP وحده بدل الشيفرة. راجع الملفات المنشورة بعد الرفع.
