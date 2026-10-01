# -*- coding: utf-8 -*-
"""إنشاء صفحة إصدار v1.36.0 بمرفق الحزمة — التوكن من GH_TOKEN فقط."""
import io
import json
import os
import subprocess
import urllib.error
import urllib.request

TOKEN = os.environ.get('GH_TOKEN')
assert TOKEN, 'GH_TOKEN مطلوب'
REPO = 'CTO-DRS/arabi-lang'
TAG = 'v1.36.0'
API = 'https://api.github.com'
UPLOAD = 'https://uploads.github.com'


def api(url, method='GET', data=None, ctype='application/json'):
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header('Authorization', f'token {TOKEN}')
    req.add_header('Accept', 'application/vnd.github+json')
    if ctype:
        req.add_header('Content-Type', ctype)
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read()
            return r.status, (json.loads(body) if body[:1] in (b'{', b'[')
                              else body)
    except urllib.error.HTTPError as e:
        body = e.read()
        return e.code, (json.loads(body) if body[:1] in (b'{', b'[')
                        else body)


# 1) بناء أرشيف الحزمة من الوسم مباشرة
out = subprocess.run(
    ['git', 'archive', '--prefix=arabi-lang/', '--format=zip', TAG],
    cwd='/home/z/my-project/arabi-lang', capture_output=True, check=True)
blob = out.stdout
print(f'الأرشيف من الوسم: {len(blob)} بايت')

# فحص النظافة: لا .git ولا __pycache__
import zipfile
zf = zipfile.ZipFile(io.BytesIO(blob))
names = zf.namelist()
dirty = [n for n in names
         if '/.git/' in n or '__pycache__' in n or n.endswith('.pyc')]
print(f'الملفات: {len(names)} | متسخة: {dirty or "لا شيء"}')
assert not dirty

# 2) هل الصفحة موجودة مسبقًا؟
status, rel = api(f'{API}/repos/{REPO}/releases/tags/{TAG}')
if status == 200:
    print(f'الإصدار موجود مسبقًا: {rel["html_url"]}')
    rel_id = rel['id']
else:
    body = {
        'tag_name': TAG,
        'name': 'v1.36.0 — المدقق الساكن v1: عقود الدوال قبل التشغيل',
        'body': (
            '## المدقق الساكن v1 — بند ثانٍ من خارطة الطريق الجديدة (أفق التمكين)\n\n'
            '**الجديد:**\n'
            '- **`--تحقق-ساكن ملفات…`:** فحص عقود الدوال الموثقة (توصيفات '
            '1.26) **من المصدر وحده قبل التشغيل** — ورمز خروج 1 عند أي '
            'مخالفة: عقد خطوط الاستمرارية مباشرة\n'
            '- **حل أسماء الأنواع ساكنًا:** خطأ إملاء في توصيف دالة لم '
            'تُستدعَ يُكتشف قبل التشغيل بدل أن ينفجر عند أول استدعاء — '
            'والأصناف تُجمع استباقيًا فالترتيب لا يهم (مرآة ق١٣)\n'
            '- **مسار «أعد» بالأدلة الساكنة:** الحرفيات والحساب الحرفي '
            'واستدعاءات التحويل والنص المنسق والثلاثي المحسوم — وما لا '
            'يُحسم يُتخطى صامتًا ويُعدّ (لا تخمين — حد موثق)\n'
            '- **السقوط الضمني المضمون:** دالة تعلن إرجاعًا بلا أي «أعد» '
            'مخالفة ساكنة (المرآة الثابتة لق١٥)\n'
            '- **دُمج في CI فعليًا:** خطوة الفحص على المثال الرسمي '
            '`examples/46_التوصيف_الساكن.عربي` (٦ دوال موثقة تغطي القوائم '
            'والنص والتحويل والصنف كنوع وعدم)\n'
            '- **دلالة واحدة في المسارين:** اختبار مرآة يثبت أن ما يرفضه '
            'الساكن يرفضه فاحص 1.26 وقت التشغيل (القسم ٦٫٨ من المواصفة)\n\n'
            '**الأرقام:** 33 اختبارًا جديدًا (محرك ٢١ · CLI ٦ · تكامل CI ٣ '
            'ومنها مرآة دلالية) — المجموعة **1490/1490** على 3.12 مرتين · '
            'الأمثلة 92/92 بالوضعين · بوابات benchmarks سليمة · مسح AST '
            'أمني نظيف (لا eval/exec — الفحص من الشجرة وحدها)\n\n'
            '**المرفق:** `arabi-lang-1.36.0.zip` — المصدر عند الوسم من '
            '`git archive` (بلا نفايات)'),
        'draft': False,
        'prerelease': False,
    }
    status, rel = api(f'{API}/repos/{REPO}/releases', method='POST',
                      data=json.dumps(body).encode('utf-8'))
    assert status in (201, 200), f'{status}: {rel}'
    rel_id = rel['id']
    print(f'أُنشئت الصفحة: {rel["html_url"]}')

# 3) رفع المرفق
asset_name = 'arabi-lang-1.36.0.zip'
status, assets = api(f'{API}/repos/{REPO}/releases/{rel_id}/assets')
existing = [a['name'] for a in assets] if status == 200 else []
if asset_name in existing:
    print(f'المرفق موجود مسبقًا: {asset_name}')
else:
    url = (f'{UPLOAD}/repos/{REPO}/releases/{rel_id}/assets'
           f'?name={asset_name}')
    status, asset = api(url, method='POST', data=blob,
                        ctype='application/zip')
    assert status in (201, 200), f'{status}: {asset}'
    print(f'رُفع المرفق: {asset["browser_download_url"]}')
