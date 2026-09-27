# -*- coding: utf-8 -*-
"""السجل المجتمعي (الإصدار 1.20) — خادم فهرس حزم تستضيفه بنفسك.

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
import io
import json
import os
import shutil
import tempfile
import threading
import urllib.parse
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .errors import ArabiError
from .packages import MANIFEST_NAME, _validate_source, read_manifest

# هوية السجل ومساراته
REGISTRY_NAME = 'سجل عربي المجتمعي'
INDEX_PATH = '/الفهرس.json'          # المسار القياسي للفهرس (بروتوكول 1.12)
INFO_PATH = '/معلومات'
STORE_SUBDIR = 'حزم'                  # مجلد المخزن داخل مجلد السجل

# ترويسة توقيع النشر — والمفتاح من تشفير.مفتاح_آمن (1.19)
AUTH_HEADER = 'X-Arabi-Signature'
MAX_PACKAGE_BYTES = 64 * 1024 * 1024   # حد حجم الحزمة المنشورة (64 م.ب)


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
    """مسار أرشيف نسخة منشورة."""
    return os.path.join(_pkg_root(store_dir, name), version + '.zip')


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
    versions.sort(key=lambda m: [int(x) for x in m['النسخة'].split('.')])
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
                 name=REGISTRY_NAME):
        self._store = os.path.abspath(store_dir)
        self._host = host
        self._requested_port = port
        self._auth_key = auth_key
        self._name = name
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
    server_version = 'ArabiRegistry/1.20'
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

    def log_message(self, fmt, *args):    # صمت — الـCLI يطبع ما يلزم
        pass

    # ---------- GET ----------

    def do_GET(self):
        reg = self.registry
        segs = self._segments()
        try:
            if not segs:
                self._send_text(self._welcome_text())
                return
            head = segs[0]
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
                })
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
                    version = segs[2]
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

    def _welcome_text(self):
        reg = self.registry
        lines = [
            f'{reg._name} — على {reg.base_url()}',
            f'الحزم: {reg.count()} | النسخ المنشورة: '
            f'{reg.total_versions()} | النشر: '
            + ('محمي بمفتاح' if reg.keyed() else 'مفتوح'),
            '',
            'المسارات:',
            '  /الفهرس.json          فهرس السجل (بروتوكول 1.12)',
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
                   name=REGISTRY_NAME):
    """يشغل سجل الحزم في الواجهة ويحجب حتى Ctrl+C — ثم يودّع بنظافة."""
    if auth_key is not None and (not isinstance(auth_key, str)
                                 or not auth_key):
        raise ArabiError('مفتاح النشر يكون نصًا غير فارغ — أو احذف '
                         'العلم ليكون السجل مفتوحًا')
    server = RegistryServer(store_dir, host=host, port=port,
                            auth_key=auth_key, name=name)
    try:
        server.start()
    except ArabiError as exc:
        raise ArabiError(getattr(exc, 'message', None) or str(exc))
    print(f'{server._name} يعمل على {server.base_url()}')
    print(f'المخزن: {server.store()}')
    print('النشر: ' + ('محمي بمفتاح سري' if server.keyed()
                       else 'مفتوح (للشبكة المحلية والتجريب)'))
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
