# مصنع الوكلاء — منصة v0.3 التجريبية

[English](PLATFORM.md) · [الهيكل v0.2](ARCHITECTURE.ar.md)

إضافة إلى المحرك السابق لا تغير أوامر تشغيله. Python 3.10 فأحدث. النظام محلي أولًا؛ الأدوات الخارجية تعمل بأوامر صريحة من المشغل، وليس بتنفيذ أوامر يقررها النموذج تلقائيًا. ليس جاهزًا للإنتاج.

## التشغيل والنماذج

```sh
python -m factory.platform --project demo run examples/architecture.ar.json
python -m factory.platform --project work --route ollama/YOUR_MODEL run examples/architecture.ar.json
python -m factory.platform --project work --route ollama/YOUR_MODEL --role-route security=ollama/YOUR_OTHER_MODEL run examples/architecture.ar.json
```

استأنف التشغيل بنفس إعدادات النماذج الأصلية باستخدام `resume RUN_ID`. الوضع الافتراضي محاكاة حتمية، وليس ذكاء اصطناعيًا. اختر اسم نموذج مثبت فعليًا في Ollama. لدعم GPT وClaude وGemini، اضبط مفاتيحك في متغيرات البيئة محليًا (`OPENAI_API_KEY` أو `ANTHROPIC_API_KEY` أو `GEMINI_API_KEY`)، ولا تشاركها في المحادثات أو المستودعات.

```sh
python -m factory.platform --route openai/YOUR_MODEL --allow-cloud run examples/architecture.ar.json --calls 8
python -m factory.platform --route anthropic/YOUR_MODEL --allow-cloud run examples/architecture.ar.json --calls 8
python -m factory.platform --route gemini/YOUR_MODEL --allow-cloud run examples/architecture.ar.json --calls 8
```

الخيار `--allow-cloud` موافقة صريحة على إرسال بيانات المهمة للمزود وإمكان تكبد رسوم. لا يوجد انتقال تلقائي إلى مزود آخر أو إعادة محاولة تلقائية. سقف الطلبات 30 لكل تشغيل وسقف الإخراج الافتراضي 2048 توكن لكل طلب؛ ليست حدودًا مالية مضمونة، لذلك اضبط الميزانية لدى المزود. اختر نموذجًا يدعم الواجهة والمخرجات المنظمة المطلوبة.

## إنشاء وكلاء مخصصين ومهارات

```sh
python -m factory.platform --route ollama/YOUR_MODEL run examples/architecture.ar.json --specialists examples/specialists.json --calls 24
```

عرّف ما يصل إلى خمسة وكلاء متخصصين في ملف JSON يتضمن الاسم والمهمة والاعتماديات. تعمل الأدوار المستقلة بالتوازي، وتدخل مخرجاتها في المحرك بوصفها تحليلات مولدة غير موثقة. تحسب الطلبات ضمن السقف نفسه، ولا تدعم مرحلة الوكلاء المخصصين الاستئناف قبل إنشاء حالة المحرك الرئيسي. لتوليد مهارة من تعريف دور مستقل (`depends_on: []`) استخدم `python -m factory.platform skill role.json`. لا يحصل الوكلاء على صلاحيات تنفيذ النظام.

## البحث وMCP

```sh
python -m factory.platform web https://example.org/ --host example.org --approve > web.json
python -m factory.platform mcp --port 8765 --tool read_document --args args.json --approve > mcp.json
python -m factory.platform run examples/architecture.ar.json --source web.json --source mcp.json
```

يدعم جلب نصوص صفحات HTTPS العامة المحددة دون إعادة توجيه أو بيانات اعتماد أو معاملات استعلام. ليس محرك بحث مستقلًا. يدعم MCP محليًا بإصدار بروتوكول 2026-07-28 واستجابات JSON فقط عند `/mcp`. يتطلب خادمًا موثوقًا وأداة محددة بمعرفة المستخدم موسومة للقراءة فقط؛ هذه الوسمة ليست ضمانًا تقنيًا ضد التعديل. لا يدعم SSE أو OAuth أو الاستدعاء التلقائي للأدوات أو الخوادم البعيدة. ملف `args.json` كائن JSON. تُعامل النتائج باعتبارها بيانات غير موثوقة.

## تجهيز الشيفرة واختبارها بعزل Docker

```sh
python -m factory.platform digest examples/stage-plan.json
python -m factory.platform stage examples/stage-plan.json new-workspace --digest EXACT_DIGEST
python -m factory.platform sandbox-test new-workspace --image YOUR_INSTALLED_IMAGE_AT_SHA256_DIGEST --approve
```

راجع خطة الملفات كاملة قبل إدخال البصمة. يُنشئ النظام مجلدًا جديدًا فقط دون تعديل الملفات الموجودة. يجب توفر Docker وصورة Linux موثوقة مثبتة محليًا ومحددة ببصمتها. الاختبار الافتراضي `unittest`، ويمكن استخدام `--suite php-lint` مع PHP 8.3 أو أحدث لفحص الصياغة فقط (ليس اختبار Laravel كاملًا). يأخذ النظام نسخة من الملفات المسموح بها، ثم يركبها للقراءة فقط داخل الحاوية، دون شبكة وبمستخدم غير root وحدود للموارد. لا يثبت حزمًا ولا يسحب صورًا ولا ينفذ أوامر Shell عشوائية أو ينشر إلى الإنتاج. الأمان يعتمد أيضًا على المضيف وصورة Docker؛ لا ضمان لعزل كامل. راجع الشيفرة واستعمل بيئة قابلة للتخلص منها.

## الذاكرة ولوحة المتابعة

```sh
python -m factory.platform --project work remember notes.txt
python -m factory.platform --project work recall "نسخ احتياطي"
python -m factory.platform --project work remember notes.txt --embedding-model YOUR_LOCAL_EMBEDDING_MODEL
python -m factory.platform --project work recall "نسخ احتياطي" --embedding-model YOUR_LOCAL_EMBEDDING_MODEL
python -m factory.platform --project work run examples/architecture.ar.json --memory-query "نسخ احتياطي"
python -m factory.platform --project work compare RUN_A RUN_B
python -m factory.platform --project work dashboard dashboard.html
```

ذاكرة SQLite مستقلة لكل مشروع، وبحث لفظي ودلالي اختياري عبر نموذج تضمين محلي. يمكن إدخال الملاحظات صراحة للمهمة بوصفها غير موثقة. البحث الدلالي يتطلب النموذج نفسه المستخدم عند الحفظ. لا تشفير أو ذاكرة موزعة أو تعلم تلقائي. تقارن أداة `compare` مهامًا متطابقة، وتعرض الطلبات ومجموع زمن الأدوار وليس ضمانًا للجودة أو التكلفة. لوحة المتابعة ملف HTML محلي للقراءة فقط، لا خادم ويب ولا نظام مصادقة.

## الجدولة

```sh
python -m factory.platform --project weekly --route ollama/YOUR_MODEL schedule examples/architecture.ar.json --interval 604800 --approve
python -m factory.platform --project weekly jobs
python -m factory.platform --project weekly tick
python -m factory.platform --project weekly cancel JOB_ID
```

تُحفظ الجدولة في SQLite. يجب إعداد Cron أو Task Scheduler خارجيًا بموافقتك لاستدعاء `tick` دوريًا؛ لا يُنشأ من تلقاء نفسه. يُمنع تشغيل المهام السحابية المتكررة. تُحجز المهمة قبل تشغيلها وتتعطل إعادة المحاولة التلقائية عند الفشل أو الانقطاع. راجع المهام العالقة يدويًا. لا تخزن بيانات حساسة، ولا تستخدم ملفات حالة غير موثوقة.

## حدود الاختبارات

اختُبرت عقود واجهات المزودين وMCP وجلب الويب وأوامر Docker بردود محاكاة. لم تُختبر نماذج حية أو حاويات Docker فعلية أو خادم MCP حي في بيئة البناء. كما أن GitHub Actions متوقف بسبب قيد الفوترة. هذه معاينة تطوير، لا إصدار إنتاجي. المراجع الرسمية وروابط واجهات API في [الدليل الإنجليزي](PLATFORM.md).
