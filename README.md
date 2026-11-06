# Telecom Customer Intelligence Platform (FastAPI + HTML/CSS/JS frontend)

Churn prediction and retention decision prototype built during an internship at e& Egypt. The model is trained on the
public **IBM Telco Customer Churn** dataset (7,043 customers), not on e& customer data.

## Model & results

Five algorithms (Logistic Regression, KNN, SVM, Random Forest, XGBoost) were compared under three class-imbalance
strategies (none, class weights, SMOTE) with stratified 5-fold cross-validation and randomized hyperparameter search.
The selected model is **SVM + SMOTE**, evaluated once on a held-out test set (1,409 customers, 26.5% churn):

| Decision rule | Threshold | Precision | Recall | F1 |
| :--- | :---: | :---: | :---: | :---: |
| Default | 0.50 | 0.523 | 0.775 | 0.625 |
| Best F1 | 0.64 | 0.573 | 0.717 | 0.637 |
| Business cost (missed churner = 5× false alarm) | 0.26 | 0.438 | **0.909** | 0.591 |

Test ROC-AUC: **0.844**. Global churn drivers were analysed with SHAP in the notebook; the app shows rule-based driver
explanations derived from that analysis (`app/core/shap_engine.py`), not per-customer SHAP values.

The LLM layer (free-text extraction and analyst Q&A) defaults to `deepseek-ai/DeepSeek-V3-0324` through Hugging Face
Inference Providers; set `CHAT_MODEL_ID` to use another model.

## طريقة التشغيل

```bash
pip install -r requirements.txt
cp .env.example .env      # وحط توكن HF_TOKEN مجاني من https://huggingface.co/settings/tokens

uvicorn app.main:app --reload
```

افتح المتصفح على: **http://127.0.0.1:8000**

ده كل حاجة — سيرفر FastAPI واحد بيخدم الـ API وبيعرض واجهة الـ HTML/CSS/JS
اللي في `static/` (مفيش Streamlit، مفيش build step، مفيش npm).

## بنية المشروع
```
static/
  index.html    # الواجهة (SPA بسيطة، بدون framework)
  style.css     # نظام التصميم الكامل (dark ops-console theme)
  app.js        # منطق الشات + استدعاء الـ API + رسم لوحات التحليل
app/
  __init__.py
  main.py       # FastAPI: /health, /analyze-customer, /chat + /api/* (extract, analyze, chat, compare, override)
  engine.py     # facade بيعيد تصدير app/core/* (churn, value, segmentation, campaigns, upsell)
  schemas.py    # Pydantic models
  core/         # المحرك الحتمي مقسّم لموديولز (churn_engine, financial_engine, segmentation, campaign_engine, upsell_engine, decision_engine...)
  llm/          # طبقة الـ LLM: extraction (نص → بيانات) + conversation (شرح النتائج)
  config/
    campaigns.json   # كتالوج الحملات (قابل للتعديل من غير كود)
  feedback/
    feedback_store.py  # تسجيل الـ human override + نتائج الحملات الفعلية
models/
  churn_model.joblib   # الموديل المدرّب (جاهز، مش محتاج تعيد تدريبه)
tests/
  conftest.py
  test_engine.py
my-e-first-task.ipynb   # النوتبوك اللي فيه الـ EDA + تدريب الموديل (مرجع فقط، مش بيتشغّل وقت الـ runtime)
data/                  # data/customers_dataset.csv بيتبني وقت الـ runtime (مفيش seed CSV متوزّع مع المشروع)
requirements.txt
.env.example
```

## اللي اتغيّر آخر تحديث
- **الواجهة بقت HTML/CSS/JS خالص** بدل Streamlit — نفس الـ FastAPI backend
  بيخدمها كـ static files (`app.mount("/static", ...)` + `GET /` بيرجع
  `index.html`)، فمنتج واحد قابل للنشر (deploy) بدون سيرفرين منفصلين.
- ديزاين "console" احترافي غامق (dark ops-console)، Arabic RTL كامل،
  مع gauge دائري لاحتمال الـ churn، بطاقات مالية، بدائل الحملات، أداة
  What-if للمقارنة، وفورم الـ Human Override — كله شغال live عن طريق
  `/api/*` endpoints جديدة في `app/main.py`.
- **success_probability بقت context-aware**: مش رقم ثابت لكل حملة — بتاخد
  boost لو الحملة بتعالج درايفر فعلي عند العميل، وboost تاني لو بتستهدف
  الـ behavioral segment بتاعه (`app/core/campaign_engine.py`). ده بيمنع
  إن كل العملاء ياخدوا نفس الحملة.
- **اتشال الـ Customer ID lookup** بناءً على طلب صريح — التطبيق شاتبوت
  فقط، العميل بيتوصف بالكلام مش برقم من قاعدة بيانات.


- **`engine.py` كان فيه باگ**: الموديل المحفوظ متدرب على features مشتقة
  (`TenureGroup`, `AvgMonthlySpend`, `IsNewCustomer`, `HighMonthlyCharge`,
  `ServicesCount`, `AutoPayment`) مش موجودة في `CustomerInput` الخام، فكان
  بيرمي `ValueError: columns are missing`. اتضاف `engineer_model_features()`
  بنفس منطق النوتبوك بالظبط (نفس الـ bins ونفس الـ threshold المحسوب من
  بيانات التدريب: `HighMonthlyCharge = MonthlyCharges > 70.35`).
- **`scikit-learn` لازم يبقى `==1.6.1`** بالظبط (نفس نسخة التدريب)، وإلا
  الـ joblib بيرفض يفك الموديل (`InconsistentVersionWarning` / attribute
  errors). ده متثبت في `requirements.txt`.
- **محرك الـ Retention Campaign كان دايمًا بيرجع `campaign: null`**. اتضاف
  `select_retention_campaign()` بمنطق شبيه بمحرك الـ upsell: بيختار من بين
  كذا كامبين (Contract upgrade, Tech Support trial, Security trial,
  Loyalty discount, High-touch call) على أساس أعلى **Expected Net
  Benefit**، ولو مفيش كامبين بيغطي تكلفته بيرجع "Low-Cost Monitoring"
  بدل ما يفرض كامبين مكلف من غير مبرر اقتصادي (زي ما مطلوب في السبيك).
- اتضاف `churn_drivers` (تفسير مبسّط لأهم أسباب الخطورة) في مخرجات
  `analyze_customer` عشان الشاتبوت يقدر يجاوب على "ليه العميل ده هيسيب؟".
- اتضاف `app.llm.extract_customer_data(...)`: دي اللي كانت ناقصة فعليًا —
  اللي بتحوّل وصف الموظف النصي (عربي/إنجليزي) لحقول `CustomerInput`
  المطلوبة، من غير ما تخترع أي قيمة مش مذكورة، وبترجع الحقول الناقصة عشان
  الشاتبوت يسأل عنها.
- الـ `.env.example` معمول مسبقًا على `deepseek-ai/DeepSeek-V3-0324`، عبر
  `huggingface_hub.InferenceClient.chat_completion` — أي حساب Hugging Face
  مجاني شغال معاه.

## خطوات التشغيل

### 1) تجهيز البيئة
```bash
python -m venv .venv
source .venv/bin/activate      # على ويندوز: .venv\Scripts\activate
pip install -r requirements.txt
```

`models/churn_model.joblib` موجود جاهز في الملف المضغوط، **مش محتاج تعيد
تدريب الموديل ولا تشغّل النوتبوك** عشان تجرب المشروع. النوتبوك موجود
للمرجعية فقط لو حبيت تفهم/تعدّل خط التدريب.

### 2) حط توكن Hugging Face المجاني
سجّل توكن من: https://huggingface.co/settings/tokens

```bash
cp .env.example .env
# افتح .env وحط التوكن بتاعك في HF_TOKEN
```
الموديل الافتراضي متحدد عن طريق `CHAT_MODEL_ID` داخل `.env` (راجع
`.env.example` للقيمة الحالية والبدائل المتاحة).

### 3) شغّل السيرفر
```bash
uvicorn app.main:app --reload
```
افتح **http://127.0.0.1:8000** — هتلاقي الشات مباشرة في الواجهة (مفيش
Streamlit، الواجهة كلها HTML/CSS/JS بتتخدم من نفس السيرفر): تكتب وصف
العميل بالعربي أو الإنجليزي، الشاتبوت هيستخرج البيانات، لو ناقص حاجة
هيسألك عنها، وبعدين هيشغّل محرك التحليل ويعرضلك النتيجة (churn
probability, segment, financial exposure, أفضل كامبين/عرض) — وبعدها
تقدر تكمل تسأل عن نفس العميل ("ليه هيسيب؟"، "ابعتله انهي كامبين؟"، "لو
مش هيسيب, أبيعله ايه؟"...).

أهم الـ endpoints لو عايز تستخدم الـ API لوحده (بدون الواجهة):
- `GET  /health`             → health check
- `POST /analyze-customer`   → بيرجع تحليل العميل (churn, value, segment, action)
- `POST /chat`               → بتبعتله بيانات عميل + سؤال، وبيرجعلك إجابة الموديل
  مبنية على نتيجة `/analyze-customer` فقط (grounded, مش بيخترع أرقام)

### 4) تشغيل التستات
```bash
pytest -v
```

## إضافات آخر تحديث (كل الـ Phases)
- **Customer ID lookup**: تقدر تكتب "حلل العميل 7590-VHVEG" وهيجيب بياناته
  من الداتاسيت الأساسي `data/customers_dataset.csv` (اللي بيتبني وقت
  الـ runtime من العملاء اللي اتحللوا واحد واحد في الشات + أي CSV
  ترفعه) من غير ما يسألك أي سؤال (`app/data/dataset_store.get_customer_row`).
- **Behavioral segmentation**: طبقة تانية فوق الـ Value×Risk (High-Value
  At-Risk, New & Fragile, Service Gap, Price-Sensitive, Loyal
  Underpenetrated, High-Value Loyal, Cross-Sell Opportunity, Low-Value
  High-Risk, Stable Low-Value) بقواعد أهلية واضحة لكل سيجمنت
  (`app/core/segmentation.py`). "Service Recovery" اتسابت عمدًا لحد ما
  يبقى فيه بيانات شكاوى حقيقية.
- **Campaign catalog** بقى ملف config منفصل (`app/config/campaigns.json`)
  مش hardcoded جوه الكود.
- **What-if / campaign comparison**: `compare_campaigns()` في
  `app/core/campaign_engine.py`، وواجهة اختيار ومقارنة في الشات.
- **Human override**: الموظف يقدر يتجاهل توصية الـ AI ويسجل قراره -
  بيتسجل في `feedback_data/overrides.jsonl` (`app/feedback/feedback_store.py`).
- **Feedback loop**: `append_outcome()` جاهزة لتسجيل نتيجة الحملة الفعلية
  لاحقًا (قبلها العميل ولا لأ، فضل عندنا ولا مشي).
- **Next Best Action + Data Quality**: بيتحسبوا ويتعرضوا مع كل تحليل.
- الكود اتقسّم لموديولز منفصلة تحت `app/core/`, `app/llm/`, `app/data/`,
  `app/config/`, `app/feedback/` بدل ملف واحد كبير - راجع بنية المشروع
  فوق. `app/engine.py` و `app/llm/__init__.py` لسه شغالين كـ facade عشان
  أي كود قديم بيستورد منهم يفضل شغال من غير تعديل.

## قاعدة المعمارية اللي المشروع ماشي عليها
الـ LLM (Qwen) **مايتوقعش الـ churn ومايحسبش أي رقم مالي بنفسه** — شغلانته
بس (1) يحوّل كلام الموظف الطبيعي لبيانات structured، و(2) يشرح مخرجات
المحرك الحتمي (`engine.py`) للموظف بلغة بيزنس. المحرك هو مصدر الحقيقة
الوحيد للأرقام والقرارات.
