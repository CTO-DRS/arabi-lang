# -*- coding: utf-8 -*-
"""السجل المجتمعي (الإصدار 1.20) — خادم فهرس حزم تستضيفه بنفسك.

واجهة المتصفح (الإصدار 1.22): الجذر / يخدم لوحة عربية كاملة الاتجاه
(RTL) تعرض حالة السجل وحزمه مع بحث ومربّع تحميل وصفحة تفاصيل لكل
حزمة على /عرض/<اسم> — وكل ذلك بلا أي أصول خارجية: CSS مدمج في الصفحة
ولا جافاسكربت ولا خطوط من الشبكة، فتعمل في الشبكات المعزولة تمامًا
كما يعمل الخادم نفسه. وكل قيمة قادمة من الحزم تُهرَّب بـ html.escape
فلا حزمة تلوّث الصفحة. من يريد سطر الأوامر وحده يعطل الواجهة
بعلم --بلا_واجهة فيعود الجذر نصًا كما كان في 1.20-1.21، والترحيب
النصي متاح دائمًا على /ترحيب في الحالتين.

الفلسفة:
- سجل الحزم (1.12) قرأ فهرسه من رابط GitHub أو مسار محلي — وهذا
  يكفي المستهلك لكنه لا يخدم الفريق: لا مكان تنشر إليه حزمك الخاصة،
  ولا شبكة معزولة تعمل دون إنترنت. هذا الخادم يملأ الفراغ: ملف واحد
  يشغّل سجلًا كاملًا بنفس بروتوكول الفهرس تمامًا — فالعميل الحالي
  (تثبيت/بحث/تحديث/قيود النسخ/التبعيات/القفل) يعمل عليه دون أي تعديل
  بتمرير --الفهرس إلى عنوان الخادم.
- المخزن مجلد عادي يمكن نسخه ونسخه الاحتياطي:
      سجل/حزم/<اسم>/<نسخة>.zip     الحزمة كما نُشرت
      سجل/حزم/<اسم>/<نسخة>.json   بيانها وحجمها وبصمتها
- النسخ غير قابلة للتعديل (كما في السجلات الكبيرة): إعادة نشر نسخة
  موجودة تُرفض 409 — والفهرس يعرض أحدث نسخة لكل حزمة دومًا.
- لا ينشر السجل كودًا غير سليم: كل حزمة تُفحص نحويًا (بفاحص اللغة
  نفسه) ويجب أن يطابق اسمها ونسختها عنوان النشر قبل التخزين.
- النشر المحمي (1.19 يتكامل): أدرج مفتاحًا سريًا عند بدء الخادم فيصبح
  كل نشر يتطلب ترويسة X-Arabi-Signature = HMAC-SHA256(مفتاح، محتوى
  الحزمة) — والتحقق بمقارنة زمن ثابت. السجل المفتوح بلا مفتاح مناسب
  للشبكة المحلية والتجريب؛ وللشبكة العامة أدرج مفتاحًا دائمًا.
- كل المسارات عربية — والردود JSON بترميز utf-8 كامل.

هذا الملف يستورد من packages (فحص البيان والصياغة) ومن errors فقط —
ولا يستورد من runtime فلا دورانية.
"""

import hashlib
import hmac
import html as _html
import json
import os
import re
import shutil
import tempfile
import threading
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .errors import ArabiError
from .packages import MANIFEST_NAME, _validate_source, read_manifest

# هوية السجل ومساراته
REGISTRY_NAME = 'سجل عربي المجتمعي'
INDEX_PATH = '/الفهرس.json'          # المسار القياسي للفهرس (بروتوكول 1.12)
INFO_PATH = '/معلومات'
STORE_SUBDIR = 'حزم'                  # مجلد المخزن داخل مجلد السجل
WELCOME_SEGMENT = 'ترحيب'             # الترحيب النصي — دائمًا متاح
WEB_PACKAGE_SEGMENT = 'عرض'           # صفحة تفاصيل حزمة /عرض/<اسم>
SEARCH_PARAM = 'بحث'                  # معامل البحث في الجذر /?بحث=كلمة

# إصدار اللغة في تذييل الصفحات — والوالد محمّل قبل أي وحدة فرعية
try:
    from . import __version__ as _LANG_VERSION
except Exception:                          # حارس نظري — لا يحدث عمليًا
    _LANG_VERSION = '1.22'

# ترويسة توقيع النشر — والمفتاح من تشفير.مفتاح_آمن (1.19)
AUTH_HEADER = 'X-Arabi-Signature'
MAX_PACKAGE_BYTES = 64 * 1024 * 1024   # حد حجم الحزمة المنشورة (64 م.ب)

# المجلد الافتراضي لمخزن السجل عند تشغيله بلا مجلد صريح
DEFAULT_STORE_NAME = 'سجل-الحزم'

# مقطع النسخة الصالح في طلبات التنزيل — يمنع أي فاصل مسار (الإصلاح الأمني)
_SAFE_VERSION_RE = re.compile(r'^[A-Za-z0-9._+~-]+$')


def default_store_dir():
    """مجلد المخزن الافتراضي للسجل — مجلد «سجل-الحزم» في دليل العمل."""
    return os.path.join(os.getcwd(), DEFAULT_STORE_NAME)


def _safe_version_segment(version):
    """يطهّر مقطع النسخة القادم من طلب تنزيل شبكي — يعيد None إن كان خطيرًا.

    مقطع المسار يفك ترميزه بعد القسمة على '/' فتدسّ '..' أو الفواصل
    المرمزة (%2F) داخل المقطع الواحد — أي مقطع لا يطابق نمط الإصدارات
    الصرفة يرفض قبل لمس نظام الملفات (ثغرة التنقل: تقرير التدقيق م11).
    """
    if not version or '..' in version or not _SAFE_VERSION_RE.match(version):
        return None
    return version


# ================== أدوات المخزن ==================

def _store_root(store_dir):
    """جذر المخزن: مجلد الحزم داخل مجلد السجل."""
    return os.path.join(store_dir, STORE_SUBDIR)


def _pkg_root(store_dir, name):
    """مجلد حزمة واحدة داخل المخزن."""
    return os.path.join(_store_root(store_dir), name)


def _version_meta_path(store_dir, name, version):
    """مسار بيان نسخة منشورة."""
    return os.path.join(_pkg_root(store_dir, name), version + '.json')


def _version_zip_path(store_dir, name, version):
    """مسار أرشيف نسخة منشورة — حصر داخل جذر الحزمة (دفاع ثانٍ).

    حتى لو تسرب مقطع نسخة خبيث من طبقة التطهير، يرفض الدمج أي مسار
    يخرج عن جذر الحزمة داخل المخزن.
    """
    root = os.path.abspath(_pkg_root(store_dir, name))
    path = os.path.abspath(os.path.join(root, version + '.zip'))
    if not path.startswith(root + os.sep):
        raise ArabiError(
            f"مقطع النسخة '{version}' يحاول الخروج من مجلد الحزمة")
    return path


def _scan_versions(store_dir, name):
    """يعيد قائمة نسخ حزمة مخزنة مرتبة تصاعديًا — من ملفات البيانات."""
    root = _pkg_root(store_dir, name)
    if not os.path.isdir(root):
        return []
    versions = []
    for entry in os.listdir(root):
        if entry.endswith('.json'):
            with open(os.path.join(root, entry), encoding='utf-8') as f:
                try:
                    meta = json.load(f)
                except ValueError:
                    continue
            if isinstance(meta, dict) and meta.get('النسخة'):
                versions.append(meta)
    # فرز متسامح: المقطع الرقمي يرتب رقميًا، وغير الرقمي (1.0-beta مثلاً)
    # يرتب نصيًا بعده — بدل انفجار ValueError يأسّر كل مسارات الفحص
    def _ver_key(v):
        parts = []
        for x in v.split('.'):
            if x.isdigit():
                parts.append((0, int(x), ''))
            else:
                num = ''
                for ch in x:
                    if ch.isdigit():
                        num += ch
                    else:
                        break
                rest = x[len(num):]
                parts.append((0 if num else 1, int(num) if num else 0, rest))
        return parts

    versions.sort(key=lambda m: _ver_key(m['النسخة']))
    return versions


def _scan_index(store_dir):
    """يبني فهرس السجل (بروتوكول 1.12): اسم ← {المصدر، النسخة، الوصف}.

    المصدر رابط تحميل أحدث نسخة من هذا الخادم نفسه — والعميل يحمل
    العنوان من --الفهرس فيبني روابط صحيحة بلا أي إعداد إضافي.
    """
    from .packages import compare_versions
    index = {}
    root = _store_root(store_dir)
    if not os.path.isdir(root):
        return index
    for name in sorted(os.listdir(root)):
        versions = _scan_versions(store_dir, name)
        if not versions:
            continue
        latest = versions[-1]
        for meta in versions[1:]:
            if compare_versions(meta['النسخة'],
                                latest['النسخة']) > 0:
                latest = meta
        # روابط تنزيل بترميز النسبة — سطر طلب HTTP آسكي فقط
        link = urllib.parse.quote(
            f'/تحميل/{name}/{latest["النسخة"]}', safe='/.')
        index[name] = {
            'المصدر': link,
            'النسخة': latest['النسخة'],
            'الوصف': latest.get('الوصف', ''),
        }
    return index


def _fmt_size(n):
    """حجم مقروء: بايت ثم ك.ب ثم م.ب — وأكبر من ذلك نادر في الحزم."""
    n = int(n)
    if n < 1024:
        return f'{n} بايت'
    if n < 1024 * 1024:
        return f'{n / 1024:.1f} ك.ب'
    return f'{n / (1024 * 1024):.1f} م.ب'


def _esc(text):
    """تهريب HTML لكل قيمة قادمة من الحزم — لا تلوث للصفحة أبدًا."""
    return _html.escape(str(text), quote=True)


def _link(path):
    """رابط آمن بترميز النسبة — سطر href يقبل العربية."""
    return urllib.parse.quote(path, safe='/.')


# ================== قوالب واجهة المتصفح (1.22) ==================
# CSS مدمج بلا أي أصول خارجية — تعمل اللوحة في الشبكة المعزولة كما
# يعمل الخادم نفسه، ولا جافاسكربت إطلاقًا فكل شيء روابط ونماذج فقط.

_PAGE_STYLE = '''
:root{--زيتي:#0e7a5f;--غامق:#123f33;--ورقي:#f4f2ec;--حد:#e3ded2;--رمادي:#6b7280}
*{box-sizing:border-box}
body{margin:0;background:var(--ورقي);color:#1f2937;line-height:1.75;
 font-family:'Segoe UI',Tahoma,'Noto Naskh Arabic','Noto Sans Arabic',sans-serif}
a{color:var(--زيتي)}
.wrap{max-width:960px;margin:0 auto;padding:0 20px}
header{background:var(--غامق);color:#fff;padding:30px 0 46px}
header h1{margin:0;font-size:1.65rem;letter-spacing:.2px}
header .sub{margin:6px 0 0;color:#bfe3d4;font-size:.95rem;direction:ltr;text-align:right}
main.wrap{margin-top:-26px}
.cards{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:22px}
.card{background:#fff;border:1px solid var(--حد);border-radius:10px;
 padding:12px 22px;min-width:150px;box-shadow:0 2px 6px rgba(0,0,0,.06)}
.card b{display:block;font-size:1.45rem;color:var(--غامق)}
.card span{color:var(--رمادي);font-size:.85rem}
form.search{display:flex;gap:10px;margin:0 0 22px}
form.search input{flex:1;padding:10px 14px;border:1px solid #d6d0c2;
 border-radius:8px;font-size:1rem;font-family:inherit}
form.search button{background:var(--زيتي);color:#fff;border:0;border-radius:8px;
 padding:10px 28px;font-size:1rem;cursor:pointer;font-family:inherit}
form.search button:hover{background:#0a5c48}
table.pkgs{width:100%;border-collapse:collapse;background:#fff;
 border:1px solid var(--حد)}
th{background:#eaf2ec;color:var(--غامق);text-align:right;padding:10px 14px;
 font-size:.9rem;border-bottom:2px solid var(--حد)}
td{padding:12px 14px;border-top:1px solid #efe9dc;vertical-align:top}
td .desc{color:var(--رمادي);font-size:.92rem;margin:2px 0 6px}
a.btn{display:inline-block;padding:4px 14px;border-radius:7px;text-decoration:none;
 font-size:.87rem;margin:2px 0 2px 6px}
a.btn.dl{background:var(--زيتي);color:#fff}
a.btn.info{border:1px solid var(--زيتي);color:var(--زيتي)}
.badge{background:var(--زيتي);color:#fff;border-radius:99px;padding:1px 12px;
 font-size:.8rem;margin-right:8px}
.empty{background:#fff;border:1px dashed #cfc8b8;border-radius:10px;
 padding:36px;text-align:center;color:var(--رمادي)}
h2.sec{font-size:1.15rem;color:var(--غامق);margin:26px 0 12px}
.cmd{background:#10241d;color:#d9f2e6;padding:12px 16px;border-radius:8px;
 font-family:Consolas,'Courier New',monospace;direction:ltr;text-align:left;
 overflow-x:auto;margin:12px 0;font-size:.92rem}
code{font-family:Consolas,'Courier New',monospace;direction:ltr;
 unicode-bidi:embed;background:#ece9df;border-radius:5px;padding:0 6px}
.bread{margin:0 0 14px;font-size:.92rem}
.bread a{color:#bfe3d4}
.error-box{background:#fff;border:1px solid var(--حد);border-right:5px solid #b91c1c;
 border-radius:10px;padding:28px;margin-top:26px}
.error-box h2{margin:0 0 8px;color:#b91c1c;font-size:1.15rem}
footer{margin-top:34px;padding:16px 0 30px;border-top:1px solid #e0dacb;
 color:var(--رمادي);font-size:.88rem}
'''


def _page(title, body, base_url):
    """يغلّف الصفحة بقالب عربي كامل — ترويسة وتذييل وروابط مرجعية."""
    return f'''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>{_PAGE_STYLE}</style>
</head>
<body>
<header><div class="wrap">
<h1>{_esc(REGISTRY_NAME)}</h1>
<p class="sub">{_esc(base_url)}</p>
</div></header>
<main class="wrap">
{body}
</main>
<footer><div class="wrap">
مدعوم بلغة عربي {_esc(_LANG_VERSION)} —
<a href="{_link(INDEX_PATH)}">الفهرس (بروتوكول 1.12)</a> ·
<a href="{_link('/' + WELCOME_SEGMENT)}">الترحيب النصي</a> ·
<a href="{_link('/' + INFO_PATH.lstrip('/'))}">معلومات</a>
</div></footer>
</body>
</html>'''


def _stats_cards(reg):
    """بطاقات الحالة الثلاث: الحزم والنسخ ووضع النشر."""
    mode = 'محمي بمفتاح' if reg.keyed() else 'مفتوح'
    return f'''<section class="cards">
<div class="card"><b>{reg.count()}</b><span>حزمة منشورة</span></div>
<div class="card"><b>{reg.total_versions()}</b><span>نسخة محفوظة</span></div>
<div class="card"><b>{_esc(mode)}</b><span>وضع النشر</span></div>
</section>'''


def _search_form(term=''):
    """مربّع البحث — نموذج GET إلى الجذر بمعامل «بحث»."""
    value = _esc(term) if term else ''
    return (f'<form class="search" action="/" method="get">'
            f'<input type="search" name="{_esc(SEARCH_PARAM)}" '
            f'value="{value}" placeholder="ابحث بالاسم أو الوصف…">'
            f'<button type="submit">ابحث</button></form>')


def _packages_table(reg, entries):
    """جدول الحزم: اسم ووصف وأحدث نسخة وروابط التحميل والتفاصيل.

    entries قائمة (اسم، بيان فهرس) — كما تعيدها search() أو الفهرس.
    """
    rows = []
    for name, info in entries:
        version = info.get('النسخة', '')
        desc = info.get('الوصف', '')
        rows.append(
            f'<tr><td><a href="{_link("/" + WEB_PACKAGE_SEGMENT + "/" + name)}" '
            f'style="font-weight:bold;text-decoration:none">{_esc(name)}</a>'
            f'<div class="desc">{_esc(desc)}</div>'
            f'<a class="btn dl" href="{_link("/تحميل/" + name + "/" + version)}">تحميل</a>'
            f'<a class="btn info" href="{_link("/" + WEB_PACKAGE_SEGMENT + "/" + name)}">التفاصيل</a>'
            f'</td><td><code>{_esc(version)}</code></td></tr>')
    return ('<table class="pkgs"><tr><th>الحزمة</th>'
            '<th>أحدث نسخة</th></tr>'
            + ''.join(rows) + '</table>')


def _home_html(reg, term=None):
    """لوحة السجل الرئيسية — أو نتائج البحث عند مرور كلمة."""
    base = reg.base_url()
    parts = [_stats_cards(reg), _search_form(term or '')]
    if term:
        results = reg.search(term)
        heading = (f'<h2 class="sec">نتائج البحث عن «{_esc(term)}» — '
                   f'{len(results)} نتيجة</h2>')
        if results:
            parts.append(heading + _packages_table(reg, results))
        else:
            parts.append(heading
                         + '<div class="empty">لا نتائج — جرّب كلمة '
                           'أخرى، أو <a href="/">اعرض السجل كله</a></div>')
    else:
        entries = sorted(reg.index_for(base).items())
        if entries:
            parts.append('<h2 class="sec">الحزم المنشورة</h2>'
                         + _packages_table(reg, entries))
        else:
            parts.append('<div class="empty">السجل فارغ — انشر أول '
                         'حزمة بأمر «حزمة نشر» وستظهر هنا فورًا</div>')
    return _page(f'{reg._name} — استعراض الحزم',
                 '\n'.join(parts), base)


def _package_html(reg, name, metas):
    """صفحة تفاصيل حزمة: الوصف والنسخ كلها بأحجامها وبصماتها."""
    base = reg.base_url()
    latest = metas[-1]
    desc = latest.get('الوصف', '')
    rows = []
    for i, meta in enumerate(reversed(metas)):
        version = meta['النسخة']
        badge = ('<span class="badge">الأحدث</span>' if i == 0 else '')
        digest = meta.get('البصمة', '')
        short = _esc(digest[:12] + '…') if digest else '—'
        rows.append(
            f'<tr><td><code>{_esc(version)}</code>{badge}</td>'
            f'<td>{_esc(_fmt_size(meta.get("الحجم", 0)))}</td>'
            f'<td><code title="{_esc(digest)}">{short}</code></td>'
            f'<td><a class="btn dl" '
            f'href="{_link("/تحميل/" + name + "/" + version)}">تحميل</a></td></tr>')
    install = (f'arabi حزمة تثبيت {_esc(name)} --الفهرس '
               f'{_esc(base)}{INDEX_PATH}')
    no_desc = '<i style="color:#9ca3af">بلا وصف</i>'
    body = f'''<p class="bread"><a href="/">← عودة لكل الحزم</a></p>
<section class="card" style="min-width:0">
<b style="font-size:1.3rem">{_esc(name)}</b>
<span class="badge">{_esc(latest['النسخة'])}</span>
<p style="margin:8px 0 0">{_esc(desc) or no_desc}</p>
</section>
<h2 class="sec">التثبيت من هذا السجل</h2>
<div class="cmd">{install}</div>
<h2 class="sec">النسخ المنشورة ({len(metas)})</h2>
<table class="pkgs">
<tr><th>النسخة</th><th>الحجم</th><th>البصمة (sha256)</th><th></th></tr>
{''.join(rows)}
</table>'''
    return _page(f'{name} — {reg._name}', body, base)


def _error_html(message, base_url):
    """صفحة خطأ عربية بنفس القالب — بدل JSON الخام في واجهة المتصفح."""
    body = (f'<div class="error-box"><h2>تعذّر عرض الصفحة</h2>'
            f'<p>{_esc(message)}</p>'
            f'<p><a href="/">← عودة للصفحة الرئيسية</a></p></div>')
    return _page('خطأ — ' + REGISTRY_NAME, body, base_url)


def _resolve_source_paths(index, base_url):
    """يحوّل مسارات التحميل النسبية إلى روابط كاملة بعنوان الخادم."""
    for info in index.values():
        info['المصدر'] = base_url.rstrip('/') + info['المصدر']
    return index


# ================== خادم السجل ==================

class RegistryServer:
    """خادم سجل حزم عربي — بروتوكول الفهرس القياسي + النشر المحمي.

    يشغّل ThreadingHTTPServer على خيط خلفي: استدعِ start() ثم استخدم
    port() وhost()، وأنهِ بstop() — أو استخدم run_server_cli للأمر
    التفاعلي. المخزن مجلد عادي: انسخه لتنقل سجلك كله.
    """

    def __init__(self, store_dir, host='127.0.0.1', port=0, auth_key=None,
                 name=REGISTRY_NAME, no_web=False):
        self._store = os.path.abspath(store_dir)
        self._host = host
        self._requested_port = port
        self._auth_key = auth_key
        self._name = name
        self._no_web = bool(no_web)
        self._lock = threading.RLock()
        self._httpd = None
        self._thread = None

    # ---------- الحياة ----------

    def start(self):
        """يبدأ الخادم ويستمع — يعيد نفسه لسهولة السلسلة."""
        os.makedirs(_store_root(self._store), exist_ok=True)
        server = self

        class _Handler(_RegistryHandler):
            registry = server

        try:
            self._httpd = ThreadingHTTPServer(
                (self._host, self._port_arg()), _Handler)
        except OSError as exc:
            raise ArabiError(f'تعذر بدء السجل على '
                             f'{self._host}:{self._port_arg()} — {exc}')
        self._host_bound, self._port_bound = \
            self._httpd.server_address[:2]
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            daemon=True, name='سجل-عربي')
        self._thread.start()
        return self

    def _port_arg(self):
        """المنفذ المطلوب — والصفر اختيار تلقائي من النظام."""
        return getattr(self, '_requested_port', 0)

    def stop(self):
        """يوقف الخادم بنظافة — آمن للاستدعاء المتكرر."""
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    # ---------- القياسات ----------

    def host(self):
        return str(self._host_bound)

    def port(self):
        return self._port_bound

    def base_url(self):
        return f'http://{self.host()}:{self.port()}'

    def store(self):
        return self._store

    def keyed(self):
        return self._auth_key is not None

    def web_enabled(self):
        """واجهة المتصفح مفعلة — يعطلها علم --بلا_واجهة."""
        return not self._no_web

    def count(self):
        """عدد الحزم في السجل."""
        with self._lock:
            return len(_scan_index(self._store))

    def total_versions(self):
        """عدد النسخ المنشورة كله."""
        total = 0
        with self._lock:
            root = _store_root(self._store)
            if os.path.isdir(root):
                for name in os.listdir(root):
                    total += len(_scan_versions(self._store, name))
        return total

    def versions(self, name):
        """نسخ حزمة مخزنة — أحدثها أولاً."""
        with self._lock:
            metas = _scan_versions(self._store, name)
        return [m['النسخة'] for m in reversed(metas)]

    def package_meta(self, name):
        """بيانات حزمة: الوصف والنسخ والأحدث — أو لا شيء."""
        with self._lock:
            metas = _scan_versions(self._store, name)
        if not metas:
            return None
        latest = metas[-1]
        return {
            'الاسم': name,
            'الوصف': latest.get('الوصف', ''),
            'الأحدث': latest['النسخة'],
            'النسخ': [m['النسخة'] for m in reversed(metas)],
        }

    def index_for(self, base_url):
        """الفهرس بروابط كاملة — تحت القفل."""
        with self._lock:
            index = _scan_index(self._store)
        return _resolve_source_paths(index, base_url)

    # ---------- النشر ----------

    def publish_bytes(self, blob, expected_name, expected_version):
        """ينشر أرشيف zip للحزمة بعد فحصه — ويعيد (الاسم، النسخة).

        الفحوص: أرشيف سليم يحمل بيانًا، اسم البيان ونسخته يطابقان
        عنوان النشر، الكود سليم نحويًا، والنسخة غير منشورة سلفًا.
        """
        if not blob:
            raise ArabiError('محتوى النشر فارغ — أرسل أرشيف الحزمة')
        if len(blob) > MAX_PACKAGE_BYTES:
            raise ArabiError(
                f'حجم الحزمة ({len(blob)} بايتًا) يتجاوز حد النشر '
                f'({MAX_PACKAGE_BYTES} بايتًا)')
        if not (isinstance(expected_name, str) and expected_name):
            raise ArabiError('عنوان النشر يفتقد اسم الحزمة')
        if not (isinstance(expected_version, str) and expected_version):
            raise ArabiError('عنوان النشر يفتقد نسخة الحزمة')
        tmp = tempfile.mkdtemp(prefix='عربي-سجل-نشر-')
        try:
            archive = os.path.join(tmp, 'الحزمة.zip')
            with open(archive, 'wb') as f:
                f.write(blob)
            if not zipfile.is_zipfile(archive):
                raise ArabiError(
                    'محتوى النشر ليس أرشيف zip صالحًا — انشر بأمر '
                    '"حزمة نشر" ليُبنى الأرشيف كما يجب')
            with zipfile.ZipFile(archive) as zf:
                names = zf.namelist()
                if any(n.startswith('/') or '..' in n for n in names):
                    raise ArabiError(
                        'الأرشيف يحوي مسارات خطرة — مسارات مطلقة أو '
                        'قفزات .. غير مسموحة في حزم السجل')
                zf.extractall(tmp)
            # البيان في الجذر أو في مجلد واحد داخله (كما يفهمه المثبِّت)
            manifest_dir = tmp
            if not os.path.isfile(os.path.join(tmp, MANIFEST_NAME)):
                subdirs = [os.path.join(tmp, e)
                           for e in sorted(os.listdir(tmp))
                           if os.path.isdir(os.path.join(tmp, e))]
                for sub in subdirs:
                    if os.path.isfile(os.path.join(sub, MANIFEST_NAME)):
                        manifest_dir = sub
                        break
                else:
                    raise ArabiError(
                        f'الأرشيف لا يحتوي {MANIFEST_NAME} — الحزمة '
                        'يجب أن تحمل بيانها')
            data = read_manifest(manifest_dir)
            if data['الاسم'] != expected_name:
                raise ArabiError(
                    f"بيان الحزمة يقول '{data['الاسم']}' وعنوان النشر "
                    f"يقول '{expected_name}' — الاثنان يجب أن يتطابقا")
            if data['النسخة'] != expected_version:
                raise ArabiError(
                    f"بيان الحزمة يقول النسخة {data['النسخة']} وعنوان "
                    f'النشر يقول {expected_version} — الاثنان يجب أن '
                    'يتطابقا')
            _validate_source(manifest_dir)   # لا ينشر كودًا غير سليم
            with self._lock:
                if os.path.isfile(_version_meta_path(
                        self._store, expected_name, expected_version)):
                    raise ArabiError(
                        f"الحزمة '{expected_name}' نسخة {expected_version} "
                        'منشورة مسبقًا — النسخ غير قابلة للتعديل؛ انشر '
                        'نسخة أحدث')
                dest_root = _pkg_root(self._store, expected_name)
                os.makedirs(dest_root, exist_ok=True)
                # تخزين ذري: أرشيف ثم بيان — فلا فهرس يرى نصف حزمة
                zip_dest = _version_zip_path(
                    self._store, expected_name, expected_version)
                tmp_zip = zip_dest + '.جزئي'
                shutil.move(archive, tmp_zip)
                os.replace(tmp_zip, zip_dest)
                meta = {
                    'الاسم': expected_name,
                    'النسخة': expected_version,
                    'الوصف': data.get('الوصف', ''),
                    'الحجم': len(blob),
                    'البصمة': hashlib.sha256(blob).hexdigest(),
                }
                tmp_meta = _version_meta_path(
                    self._store, expected_name,
                    expected_version) + '.جزئي'
                with open(tmp_meta, 'w', encoding='utf-8') as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
                os.replace(tmp_meta, _version_meta_path(
                    self._store, expected_name, expected_version))
            return expected_name, expected_version
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def verify_signature(self, body, signature):
        """يتحقق من توقيع النشر HMAC-SHA256(المفتاح، المحتوى)."""
        if not self._auth_key:
            return True                   # سجل مفتوح — لا مصادقة مطلوبة
        if not isinstance(signature, str) or not signature:
            return False
        expected = hmac.new(self._auth_key.encode('utf-8'),
                            body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected.encode('utf-8'),
                                   signature.encode('utf-8'))

    def search(self, term):
        """يبحث بالاسم أو الوصف — قائمة (اسم، بيان)."""
        term = (term or '').strip()
        with self._lock:
            index = _scan_index(self._store)
        return [(n, i) for n, i in sorted(index.items())
                if not term or term in n or term in (i.get('الوصف') or '')]


# ================== معالج HTTP ==================

class _RegistryHandler(BaseHTTPRequestHandler):
    """معالج طلبات السجل — كل المسارات عربية والردود utf-8."""

    registry = None                    # يضبط عند البناء (فئة مغلقة)
    server_version = 'ArabiRegistry/1.22'
    protocol_version = 'HTTP/1.1'

    # ---------- أدوات الرد ----------

    def _send_json(self, obj, status=200):
        blob = json.dumps(obj, ensure_ascii=False,
                          indent=2).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',
                         'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _send_html(self, text, status=200):
        blob = text.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _send_text(self, text, status=200):
        blob = text.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _send_zip(self, path, status=200):
        with open(path, 'rb') as f:
            blob = f.read()
        self.send_response(status)
        self.send_header('Content-Type', 'application/zip')
        self.send_header('Content-Length', str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _error(self, status, message):
        self._send_json({'الخطأ': message}, status)

    def _segments(self):
        """يقطع المسار إلى مقاطع عربية مفكوكة الترميز."""
        path = urllib.parse.urlsplit(self.path).path
        return [urllib.parse.unquote(s)
                for s in path.split('/') if s]

    def _query_param(self, name):
        """قيمة معامل استعلام واحد من رابط الطلب — أو لا شيء."""
        query = urllib.parse.urlsplit(self.path).query
        values = urllib.parse.parse_qs(query).get(name)
        return values[0] if values else None

    def log_message(self, fmt, *args):    # صمت — الـCLI يطبع ما يلزم
        pass

    # ---------- GET ----------

    def do_GET(self):
        reg = self.registry
        segs = self._segments()
        try:
            if not segs:
                # الجذر: لوحة المتصفح (1.22) — أو النص كما كان قبلها
                if reg._no_web:
                    self._send_text(self._welcome_text())
                else:
                    term = self._query_param(SEARCH_PARAM)
                    self._send_html(_home_html(reg, term))
                return
            head = segs[0]
            if head == WELCOME_SEGMENT:
                # الترحيب النصي — متاح دائمًا لواجهة المتصفح والسطر معًا
                self._send_text(self._welcome_text())
                return
            if head in ('الفهرس.json', 'الفهرس', 'index.json'):
                # اسم آسكي بديل للفهرس — لراحة curl والأدوات القديمة
                self._send_json(reg.index_for(reg.base_url()))
                return
            if head == 'معلومات':
                self._send_json({
                    'السجل': reg._name,
                    'الحزم': reg.count(),
                    'النسخ': reg.total_versions(),
                    'العنوان': reg.base_url(),
                    'النشر': 'مفتاح مطلوب' if reg.keyed()
                             else 'مفتوح',
                    'الواجهة': 'معطلة' if reg._no_web else 'مفعلة',
                })
                return
            if head == WEB_PACKAGE_SEGMENT and len(segs) == 2:
                self._serve_package_page(segs[1])
                return
            if head == 'حزمة' and len(segs) == 2:
                meta = reg.package_meta(segs[1])
                if meta is None:
                    self._error(404, f"الحزمة '{segs[1]}' غير موجودة "
                                     'في السجل')
                else:
                    self._send_json(meta)
                return
            if head == 'بحث' and len(segs) == 2:
                results = [{'الاسم': n, 'النسخة': i.get('النسخة'),
                            'الوصف': i.get('الوصف', '')}
                           for n, i in reg.search(segs[1])]
                self._send_json({'النتائج': results,
                                 'العدد': len(results)})
                return
            if head == 'تحميل' and 2 <= len(segs) <= 3:
                name = segs[1]
                with reg._lock:
                    versions = _scan_versions(reg._store, name)
                if not versions:
                    self._error(404, f"الحزمة '{name}' غير موجودة "
                                     'في السجل')
                    return
                if len(segs) == 3:
                    version = _safe_version_segment(segs[2])
                    if version is None:
                        self._error(
                            400, f"نسخة غير صالحة: '{segs[2]}' — مقطع "
                                 'النسخة لا يقبل فواصل مسار')
                        return
                    if not os.path.isfile(_version_zip_path(
                            reg._store, name, version)):
                        self._error(
                            404, f"الحزمة '{name}' لا تملك نسخة "
                                 f"'{version}' — المتاح: "
                                 f"{'، '.join(m['النسخة'] for m in reversed(versions))}")
                        return
                else:
                    version = versions[-1]['النسخة']
                self._send_zip(_version_zip_path(
                    reg._store, name, version))
                return
            self._error(404, f"مسار غير معروف: "
                             f"{'/'.join(segs)}")
        except BrokenPipeError:
            pass
        except Exception as exc:          # شبكة أمان — لا صمت أبدًا
            try:
                self._error(500, f'عطل داخلي في السجل: {exc}')
            except OSError:
                pass

    def _serve_package_page(self, name):
        """صفحة تفاصيل حزمة بالواجهة العربية — أو صفحة خطأ 404."""
        reg = self.registry
        if reg._no_web:
            self._error(404, 'واجهة المتصفح معطلة على هذا السجل '
                             '(--بلا_واجهة) — استخدم /حزمة/<اسم>')
            return
        with reg._lock:
            metas = _scan_versions(reg._store, name)
        if not metas:
            self._send_html(
                _error_html(f"الحزمة '{name}' غير موجودة في السجل",
                            reg.base_url()), status=404)
            return
        self._send_html(_package_html(reg, name, metas))

    def _welcome_text(self):
        reg = self.registry
        lines = [
            f'{reg._name} — على {reg.base_url()}',
            f'الحزم: {reg.count()} | النسخ المنشورة: '
            f'{reg.total_versions()} | النشر: '
            + ('محمي بمفتاح' if reg.keyed() else 'مفتوح'),
            '',
            'المسارات:',
            '  /                     واجهة المتصفح (استعراض وبحث) — 1.22',
            '  /ترحيب                هذا الترحيب النصي',
            '  /الفهرس.json          فهرس السجل (بروتوكول 1.12)',
            '  /عرض/<اسم>            صفحة تفاصيل حزمة بالمتصفح',
            '  /حزمة/<اسم>           بيانات حزمة ونسخها',
            '  /تحميل/<اسم>/<نسخة>   تنزيل أرشيف نسخة (أو الأحدث بلا نسخة)',
            '  /بحث/<كلمة>           بحث بالاسم أو الوصف',
            '  /معلومات              حالة السجل',
            '  POST /نشر/<اسم>/<نسخة>  نشر حزمة (بتوقيع HMAC إن كان السجل مفتاحيًا)',
            '',
            'التثبيت من هذا السجل:',
            f'  arabi حزمة تثبيت اسم --الفهرس {reg.base_url()}/الفهرس.json',
        ]
        return '\n'.join(lines)

    # ---------- POST (النشر) ----------

    def do_POST(self):
        reg = self.registry
        segs = self._segments()
        try:
            if not (len(segs) == 3 and segs[0] == 'نشر'):
                self._error(404, 'نشر الحزم يكون على '
                                 '/نشر/<اسم>/<نسخة> بالطريقة POST')
                return
            length = int(self.headers.get('Content-Length') or 0)
            if length <= 0:
                self._error(400, 'طلب النشر بلا محتوى — أرسل أرشيف '
                                 'الحزمة في جسم الطلب')
                return
            if length > MAX_PACKAGE_BYTES:
                self._error(400, f'حجم الطلب ({length} بايتًا) يتجاوز '
                                 f'حد النشر ({MAX_PACKAGE_BYTES} بايتًا)')
                return
            body = self.rfile.read(length)
            signature = self.headers.get(AUTH_HEADER)
            if not reg.verify_signature(body, signature):
                self._error(401,
                            'نشر محمي بمفتاح — أرسل الترويسة '
                            f'{AUTH_HEADER} بقيمة '
                            'HMAC-SHA256(المفتاح، محتوى الحزمة) ستر عشري '
                            '— أو استخدم "حزمة نشر --مفتاح" فيوقع لك')
                return
            name, version = reg.publish_bytes(body, segs[1], segs[2])
            self._send_json({'الحالة': 'نُشرت',
                             'الحزمة': name,
                             'النسخة': version}, status=201)
        except ArabiError as exc:
            message = getattr(exc, 'message', None) or str(exc)
            status = 409 if 'منشورة مسبقًا' in message else 400
            self._error(status, message)
        except BrokenPipeError:
            pass
        except Exception as exc:          # شبكة أمان
            try:
                self._error(500, f'عطل داخلي في السجل: {exc}')
            except OSError:
                pass


# ================== سطر الأوامر ==================

def run_server_cli(store_dir, host='127.0.0.1', port=0, auth_key=None,
                   name=REGISTRY_NAME, no_web=False):
    """يشغل سجل الحزم في الواجهة ويحجب حتى Ctrl+C — ثم يودّع بنظافة."""
    if auth_key is not None and (not isinstance(auth_key, str)
                                 or not auth_key):
        raise ArabiError('مفتاح النشر يكون نصًا غير فارغ — أو احذف '
                         'العلم ليكون السجل مفتوحًا')
    server = RegistryServer(store_dir, host=host, port=port,
                            auth_key=auth_key, name=name, no_web=no_web)
    try:
        server.start()
    except ArabiError as exc:
        raise ArabiError(getattr(exc, 'message', None) or str(exc))
    print(f'{server._name} يعمل على {server.base_url()}')
    print(f'المخزن: {server.store()}')
    print('النشر: ' + ('محمي بمفتاح سري' if server.keyed()
                       else 'مفتوح (للشبكة المحلية والتجريب)'))
    if server.web_enabled():
        print(f'واجهة المتصفح: {server.base_url()}/ — استعراض وبحث '
              'وتفاصيل كل حزمة')
    else:
        print('واجهة المتصفح: معطلة (--بلا_واجهة) — الجذر ترحيب نصي')
    print(f'الحزم الحالية: {server.count()}')
    print(f'التثبيت من هذا السجل: arabi حزمة تثبيت اسم --الفهرس '
          f'{server.base_url()}/الفهرس.json')
    print('انتظار الطلبات… (Ctrl+C للإيقاف)')
    try:
        while True:
            import time
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        print('أُوقف السجل بنظافة — المخزن محفوظ كما هو')
    return 0
