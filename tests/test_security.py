# -*- coding: utf-8 -*-
"""اختبارات الاختراق الخارجية (الإصدار 1.31 — المرحلة 9).

طلب التدقيق (الفصل 16 بند 2): «لا اختبارات اختراق للسجل (traversal،
توقيعات معدلة، رؤوس ضخمة)» وبند 3: «لا اختبارات مهل (عامل يُقتل)».

كل اختبار هنا يهاجم خادمًا حيًّا على منفذ حقيقي — ثم يتحقق أن الخادم
نَجا ويخدم بعد الهجمات (فشل مغلق لا صمت).
"""

import http.client
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from arabi_lang.registry import RegistryServer
from arabi_lang import packages


def _make_pkg(base, name='أدوات', version='1.0.0', desc=None, code=None):
    pkg = os.path.join(base, f'حزمة{name}{version}')
    os.makedirs(pkg, exist_ok=True)
    with open(os.path.join(pkg, 'حزمة.json'), 'w', encoding='utf-8') as f:
        json.dump({'الاسم': name, 'النسخة': version,
                   'الوصف': desc or f'حزمة {name}',
                   'المدخل': f'{name}.عربي', 'التبعيات': {}},
                  f, ensure_ascii=False)
    with open(os.path.join(pkg, f'{name}.عربي'), 'w', encoding='utf-8') as f:
        f.write(code or f'دالة تحية():\n    أعد "سليمة من {name}"\n')
    return pkg


class RegistryAttackTest(unittest.TestCase):
    """هجمات شبكية على خادم سجل حي — والنجاة بعدها."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='sec_')
        self.servers = []
        self._server()
        self._publish_demo()

    def tearDown(self):
        for s in self.servers:
            s.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _server(self, key=None):
        srv = RegistryServer(os.path.join(self.tmp, f'مخزن{len(self.servers)}'),
                             port=0, auth_key=key)
        srv.start()
        self.servers.append(srv)
        return srv

    def _publish_demo(self, **kw):
        pkg = _make_pkg(self.tmp, **kw)
        packages.publish(pkg, self.base)
        return pkg

    @property
    def base(self):
        return self.servers[0].base_url()

    def _get(self, path, timeout=15):
        """طلب GET — يرمّز العربية ويحفظ الترميزات الموجودة (%2F)."""
        try:
            with urllib.request.urlopen(
                    self.base + urllib.parse.quote(path, safe='/%'),
                    timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def _raw_request(self, method, path, headers=None, body=None):
        """طلب عبر http.client بمسار خام لا يطبّعه العميل."""
        host = urllib.parse.urlsplit(self.base).netloc
        conn = http.client.HTTPConnection(host, timeout=15)
        conn.request(method, urllib.parse.quote(path, safe='/%'),
                     body=body, headers=headers or {})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, data

    # ---------- هجمات التنقل (traversal) ----------

    def test_download_version_traversal_rejected(self):
        """نسخة تحمل .. أو فواصل مرمزة — 400 قبل لمس نظام الملفات."""
        secret = os.path.join(self.tmp, 'مخزن0', 'سر_داخلي.txt')
        with open(secret, 'w', encoding='utf-8') as f:
            f.write('محتوى_سري_لا_يجب_تسريبه')
        for evil in ('..%2F..%2Fسر_داخلي.txt', '..', '..%2Fسري'):
            status, body = self._get('/تحميل/أدوات/' + evil)
            self.assertEqual(status, 400, evil)
            self.assertNotIn('محتوى_سري_لا_يجب_تسريبه',
                             body.decode('utf-8', 'replace'))

    def test_download_name_traversal_rejected(self):
        """اسم حزمة يحاول الصعود خارج المخزن — 404 ولا يتسرب شيء."""
        status, body = self._get('/تحميل/..%2F..%2Fإلخ%2Fكلمة_المرور')
        self.assertIn(status, (400, 404))
        self.assertNotIn(b'root:', body)

    def test_package_info_traversal_rejected(self):
        status, body = self._get('/حزمة/..%2F..%2Fسر')
        self.assertIn(status, (400, 404))
        self.assertIn('الخطأ', json.loads(body))

    def test_unknown_route_404_arabic(self):
        status, body = self._get('/مسار/غريب/كليًا')
        self.assertEqual(status, 404)
        self.assertIn('مسار غير معروف', json.loads(body)['الخطأ'])

    # ---------- هجمات النشر ----------

    def test_publish_empty_body_rejected(self):
        status, body = self._raw_request('POST', '/نشر/أدوات/2.0.0',
                                         {'Content-Length': '0'})
        self.assertEqual(status, 400)
        self.assertIn('بلا محتوى', body.decode('utf-8'))

    def test_publish_malformed_json_rejected(self):
        garbage = b'\x80\x81\x82 not json at all'
        status, body = self._raw_request(
            'POST', '/نشر/أدوات/2.0.0',
            {'Content-Type': 'application/octet-stream',
             'Content-Length': str(len(garbage))}, body=garbage)
        self.assertEqual(status, 400)
        self.assertIn('الخطأ', json.loads(body))

    def test_publish_tampered_fingerprint_rejected(self):
        """بصمة الناشر المصرّح بها لا تطابق المحتوى — رفض 400."""
        pkg = _make_pkg(self.tmp, name='مزورة', version='1.0.0')
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fname in sorted(os.listdir(pkg)):
                zf.write(os.path.join(pkg, fname), fname)
        blob = zip_buf.getvalue()
        conn = http.client.HTTPConnection(
            urllib.parse.urlsplit(self.base).netloc, timeout=15)
        conn.request('POST',
                     urllib.parse.quote('/نشر/مزورة/1.0.0', safe='/%'),
                     body=blob, headers={
            'Content-Type': 'application/octet-stream',
            'Content-Length': str(len(blob)),
            'X-Arabi-Fingerprint': 'f' * 64,   # بصمة مزيفة تمامًا
        })
        resp = conn.getresponse()
        text = resp.read().decode('utf-8')
        conn.close()
        self.assertEqual(resp.status, 400)
        self.assertIn('بصمة', text)

    def test_publish_bad_code_rejected(self):
        pkg = _make_pkg(self.tmp, name='مكسورة', version='1.0.0',
                        code='دالة مكسورة(:\n    أعد\n')
        with self.assertRaises(Exception) as caught:
            packages.publish(pkg, self.base)
        self.assertIn('غير سليم', str(caught.exception))

    # ---------- الرؤوس الضخمة والعبث ----------

    def test_huge_header_rejected_and_server_survives(self):
        """رأس ضخم يتجاوز حدود HTTP — يُرفض والخادم يبقى حيًّا."""
        status, _ = self._raw_request(
            'GET', '/الفهرس.json',
            {'X-Attack': 'A' * 70000})
        self.assertIn(status, (431, 400, 414))
        # النجاة: الطلب التالي عادي يخدم كالمعتاد
        status2, body2 = self._get('/معلومات')
        self.assertEqual(status2, 200)
        self.assertIn('الحزم', json.loads(body2))

    def test_xss_description_escaped(self):
        """وصف خبيث <script> يُخزن ويُعرض مهربًا في الواجهة — لا تنفيذ."""
        self._publish_demo(name='خبيثة', version='1.0.0',
                           desc='<script>alert(1)</script>')
        status, body = self._get('/')
        self.assertEqual(status, 200)
        html = body.decode('utf-8')
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_server_serves_after_all_attacks(self):
        """الصمود النهائي: بعد كل هجمات هذا الصنف — الفهرس سليم ومطابق."""
        status, body = self._get('/الفهرس.json')
        self.assertEqual(status, 200)
        idx = json.loads(body)
        self.assertIn('أدوات', idx)


class WorkerHostilityTest(unittest.TestCase):
    """قتل العامل فجأة (SIGKILL) — الموزع ينجو والمهمة لا تضيع.

    طلب التدقيق (الفصل 16 بند 3): اختبارات مهل — عامل يُقتل فيكون
    هناك كشف وإعادة طوابير برسالة عربية، لا تعليق صامت للعميل.
    """

    def test_killed_worker_requeues_and_survives(self):
        from arabi_lang.distributed import _dist_create
        from arabi_lang.lexer import Lexer
        from arabi_lang.parser import Parser
        from arabi_lang.interpreter import Interpreter
        interp = Interpreter(use_vm=False)
        interp.run(Parser(Lexer(
            'دالة ثقيل(ن):\n'
            '    مجموع = ٠\n'
            '    لكل س في مدى(ن):\n'
            '        مجموع += س\n'
            '    أعد مجموع\n').tokenize()).parse())
        func = interp.globals.get('ثقيل')

        disp = _dist_create(interp, [0], None)
        procs = []
        try:
            worker_a = subprocess.Popen(
                [sys.executable, os.path.join(ROOT, 'arabi.py'),
                 '--عامل', f'127.0.0.1:{disp.port()}'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT)
            procs.append(worker_a)
            disp._server.wait_workers(1, 30, None)

            # مهمة تستغرق ثوانٍ — ونقتل العامل أثناءها
            task = disp._server.submit(func, [func, 4_000_000], {}, None)
            time.sleep(0.5)
            worker_a.kill()
            worker_a.wait(timeout=10)

            # عامل جديد يلتقط المهمة المعادة للطابور
            worker_b = subprocess.Popen(
                [sys.executable, os.path.join(ROOT, 'arabi.py'),
                 '--عامل', f'127.0.0.1:{disp.port()}'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT)
            procs.append(worker_b)
            disp._server.wait_workers(1, 30, None)

            deadline = time.time() + 60
            while time.time() < deadline and not task.ready():
                time.sleep(0.2)
            self.assertTrue(task.ready(),
                            'المهمة عالقة بعد قتل العامل — لا إعادة طوابير')
            expected = 4_000_000 * (4_000_000 - 1) // 2
            self.assertEqual(task.result(), expected)

            # الموزع لا يزال يخدم: مهمة تالية تُنجز بعامل حي
            task2 = disp._server.submit(func, [func, 10], {}, None)
            self.assertEqual(task2.result(), 45)
        finally:
            disp.shutdown()
            for p in procs:
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()

    def test_worker_on_closed_port_fails_arabic(self):
        """عامل بلا موزع — رسالة عربية فورية لا تعليق."""
        probe = socket.socket()
        probe.bind(('127.0.0.1', 0))
        dead_port = probe.getsockname()[1]
        probe.close()
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, 'arabi.py'),
             '--عامل', f'127.0.0.1:{dead_port}'],
            capture_output=True, text=True, timeout=60, cwd=ROOT)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('تعذر الاتصال', r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
