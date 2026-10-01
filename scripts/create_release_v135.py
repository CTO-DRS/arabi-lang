# -*- coding: utf-8 -*-
"""إنشاء صفحة إصدار v1.35.0 بمرفق الحزمة — التوكن من GH_TOKEN فقط."""
import io
import json
import os
import subprocess
import urllib.error
import urllib.request

TOKEN = os.environ.get('GH_TOKEN')
assert TOKEN, 'GH_TOKEN مطلوب'
REPO = 'CTO-DRS/arabi-lang'
TAG = 'v1.35.0'
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
        'name': 'v1.35.0 — المنقّح التفاعلي: بند أول من أفق التمكين',
        'body': (
            '## المنقّح التفاعلي — بند أول من خارطة الطريق الجديدة (أفق التمكين)\n\n'
            '**الجديد:**\n'
            '- **جلسة تنقيح عربية كاملة:** `python3 arabi.py --نقح برنامج.عربي` '
            '— توقف على أول جملة ثم `توقف عند 5` و`توقف عند دالة احسب` '
            '(موثقة مقابل أسطر الشجرة) و`متابعة/خطوة/تالية/من_الدالة` '
            'و`اطبع تعبير` في بيئة الإطار الموقوف و`متغيرات/عالمي/أين/مصدر` '
            'و`إنهاء` — بأسطر مصدر تُعرض حول الموقف بعلامة\n'
            '- **مهايئ بروتوكول DAP للمحررات:** `--منقح-بروتوكول` — البروتوكول '
            'الذي تنقّح به المحررات القائمة على خوادم اللغة: '
            'launch/setBreakpoints (verified مقابل أسطر الشجرة)/stackTrace '
            '(إطار ٠ = الجملة الحالية، والصاعد بسطر استدعائه)/scopes/variables'
            '/continue/next/stepIn/stepOut/disconnect مع أحداث '
            'initialized/stopped بأسبابها/output/terminated/exited — ومخرجات '
            'البرنامج تُحوَّل أحداث output فلا تلوث القناة\n'
            '- **التصميم مؤسس بمسبار حي (٩/٩):** خطاف وحيد `debug_hook` على '
            '`execute()` يرى كل جمل الممسح الشجري بكلفة صفرية على التشغيل '
            'العادي (لمسة ثانية في `run()` للتعبيرية العلوية التي تتجاوزها '
            'بنيويًا) — والقرارات مثبتة في الفصل ٩ من المواصفة (ق٢٥/ق٢٦)\n'
            '- **حدود صادقة موثقة (٩٫٤):** لا نقاط مشروطة ولا تعديل قيم حي '
            'بعد — والدولاب معطل أثناء الجلسة (أجسامه لا تمر بالخطاف أصلًا) '
            'والخيط المُنقَّح وحده يتوقف (أجسام المولدات بخيوط عامل)\n\n'
            '**الأرقام:** 38 اختبارًا جديدًا على ثلاث طبقات (المحرك بواجهة '
            'مجدولة · CLI عبر subprocess كما يفعله المستخدم · DAP بمحادثات '
            'مؤطرة حقيقية) — المجموعة **1457/1457** على 3.12 (مرتين: قبل '
            'الكومِت وبعده) · الأمثلة 90/90 بالوضعين · بوابات benchmarks '
            'سليمة (دولاب 1.631s / شجري 2.393s — بلا تراجع) · مسح AST أمني '
            'نظيف (لا eval/exec/شبكة — التقييم عبر مفسر اللغة نفسه)\n\n'
            '**المرفق:** `arabi-lang-1.35.0.zip` — المصدر عند الوسم من '
            '`git archive` (بلا نفايات: لا .git ولا __pycache__)'),
        'draft': False,
        'prerelease': False,
    }
    status, rel = api(f'{API}/repos/{REPO}/releases', method='POST',
                      data=json.dumps(body).encode('utf-8'))
    assert status in (201, 200), f'{status}: {rel}'
    rel_id = rel['id']
    print(f'أُنشئت الصفحة: {rel["html_url"]}')

# 3) رفع المرفق
asset_name = 'arabi-lang-1.35.0.zip'
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
