# -*- coding: utf-8 -*-
"""اختبارات التزامن والموزع المتبقية (الإصدار 1.32 — المرحلة 10).

تغلق البنود المفتوحة من تدقيق الفصلين 14 و15:
- ق٢٤: بنية «مع قفل» — الإغلاق مضمون في كل المسارات (استثناء/كسر/إرجاع).
- سقف اتصالات العمالة — الحد يحمي الموارد بلا إنهيار (الفصل 15 بند 4).
- عداد محاولات المهمة — الإلغاء الصادق بدل الارتداد إلى الأبد (بند 5).
- «مع» كلمة سياقية: كل معرف يحمل الاسم نفسه يعمل كما كان.
"""

import os
import subprocess
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arabi_lang.lexer import Lexer
from arabi_lang.parser import Parser
from arabi_lang.interpreter import Interpreter
from arabi_lang.errors import ArabiRuntimeError


def _run(src, use_vm=True, interp=None):
    tree = Parser(Lexer(src).tokenize()).parse()
    interp = interp or Interpreter(use_vm=use_vm)
    interp.run(tree)
    return interp


class TestWithContext(unittest.TestCase):
    """بنية «مع قفل» — قرار المواصفة ق٢٤."""

    def test_lock_released_on_normal_exit(self):
        interp = _run('''
ق = خيوط.قفل()
مفتوح_داخل = ولا شيء
مع ق:
    مفتوح_داخل = صح
''')
        self.assertTrue(interp.globals.get('مفتوح_داخل'))
        # الإغلاق: القفل حر بعد الكتلة — acquisition فوري لا تعليق
        acquired = interp.globals.get('ق').lock.acquire(timeout=1)
        self.assertTrue(acquired, 'القفل لم يُغلق بعد خروج الكتلة')
        interp.globals.get('ق').lock.release()

    def test_lock_released_on_exception(self):
        """بند التدقيق الحرفي: الفتح التلقائي حتى مع استثناء داخل الكتلة."""
        interp = _run('''
ق = خيوط.قفل()
جرب:
    مع ق:
        ارفع("انفجار داخلي")
باستثناء هـ:
    انفجر = صح
''')
        self.assertTrue(interp.globals.get('انفجر'))
        acquired = interp.globals.get('ق').lock.acquire(timeout=1)
        self.assertTrue(acquired, 'القفل لم يُغلق بعد الاستثناء')
        interp.globals.get('ق').lock.release()

    def test_lock_released_on_break(self):
        interp = _run('''
ق = خيوط.قفل()
لكل س في مدى(3):
    مع ق:
        كسر
''')
        acquired = interp.globals.get('ق').lock.acquire(timeout=1)
        self.assertTrue(acquired, 'القفل لم يُغلق بعد الكسر')
        interp.globals.get('ق').lock.release()

    def test_lock_released_on_return(self):
        interp = _run('''
ق = خيوط.قفل()

دالة داخل():
    مع ق:
        أعد 42

النتيجة = داخل()
''')
        self.assertEqual(interp.globals.get('النتيجة'), 42)
        acquired = interp.globals.get('ق').lock.acquire(timeout=1)
        self.assertTrue(acquired, 'القفل لم يُغلق بعد الإرجاع')
        interp.globals.get('ق').lock.release()

    def test_mutual_exclusion_deterministic(self):
        """الحصرية: عداد محمي بـ«مع» يساوي N بالضبط (اختبار حتمي بالقفل)."""
        interp = _run('''
ق = خيوط.قفل()
العدد = 0

دالة زد():
    مع ق:
        مؤقت = العدد
        مؤقت = مؤقت + 1
        العدد = مؤقت

مهام = []
لكل س في مدى(8):
    مهام.أضف(خيوط.شغّل(زد))

انتظر_الجميع(مهام)
''')
        self.assertEqual(interp.globals.get('العدد'), 8,
                         'نمط get→حساب→set بلا قفل يخسر تحديثات — القفل كان يجب أن يمنع')

    def test_non_lock_rejected_arabic(self):
        from arabi_lang.errors import ArabiRuntimeError
        with self.assertRaises(ArabiRuntimeError) as caught:
            _run('''
ق = 5
مع ق:
    اطبع("لن يصل")
''')
        self.assertIn('ق٢٤', str(caught.exception))
        self.assertIn('قفل', str(caught.exception))

    def test_ident_ma_unaffected(self):
        """«مع» كلمة سياقية — كل استعمال آخر يعمل كما كان بلا كسر."""
        interp = _run('''
مع = 10
اطبع(مع + 5)
اطبع(مع * 2)
''')
        self.assertEqual(interp.globals.get('مع'), 10)

    def test_vm_equivalence(self):
        """نفس برنامج «مع» بالوضعين — الدولاب يعيد الجملة للشجري بسلام."""
        src = '''
ق = خيوط.قفل()
مجموع = 0

دالة اربح(ن):
    مع ق:
        لكل س في مدى(ن):
            مجموع += س

اربح(100)
اطبع(مجموع)
'''
        out_tree = self._capture(src, use_vm=False)
        out_vm = self._capture(src, use_vm=True)
        self.assertEqual(out_tree, out_vm)
        self.assertIn('4950', out_tree)

    def _capture(self, src, use_vm):
        import contextlib
        import io
        tree = Parser(Lexer(src).tokenize()).parse()
        interp = Interpreter(use_vm=use_vm)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            interp.run(tree)
        return buf.getvalue()


class TestWorkerConnectionCap(unittest.TestCase):
    """سقف اتصالات العمالة (الفصل 15 بند 4)."""

    def test_extra_connection_rejected_politely(self):
        from arabi_lang import distributed as dist
        from arabi_lang.distributed import _dist_create, recv_frame
        import socket as _socket

        interp = Interpreter(use_vm=False)
        disp = _dist_create(interp, [0], None)
        sock = None
        old_cap = dist.MAX_WORKERS
        try:
            dist.MAX_WORKERS = 0    # كل اتصال فوق الصفر يُرفض فورًا
            sock = _socket.socket()
            sock.settimeout(10)
            sock.connect(('127.0.0.1', disp.port()))
            msg = recv_frame(sock)
            self.assertEqual(msg[0], 'رفض')
            self.assertIn('سقف', msg[1])
            # والموزع حي — العمال الوهميون صفر والمقاييس تعمل
            self.assertEqual(disp.workers(), 0)
        finally:
            dist.MAX_WORKERS = old_cap
            if sock is not None:
                sock.close()
            disp.shutdown()


class TestTaskAttemptsLimit(unittest.TestCase):
    """عداد المحاولات: مهمة يُقتل عاملها ثلاث مرات تُلغى نهائيًا (بند 5)."""

    def _spawn_worker(self, port):
        proc = subprocess.Popen(
            [sys.executable, os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'arabi.py'),
             '--عامل', f'127.0.0.1:{port}'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))
        return proc

    def _wait_inflight(self, server, deadline_s=30):
        """ينتظر أن يلتقط أحد العمال المهمة فعلًا (أبيض-الصندوق موثق)."""
        deadline = time.time() + deadline_s
        while time.time() < deadline:
            with server._lock:
                for conn in server._workers.values():
                    if conn.inflight is not None:
                        return True
            time.sleep(0.1)
        return False

    def test_cancelled_after_max_attempts(self):
        from arabi_lang.distributed import _dist_create
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
            task = disp._server.submit(func, [func, 4_000_000], {}, None)
            for _round in range(3):
                proc = self._spawn_worker(disp.port())
                procs.append(proc)
                self._wait_inflight(disp._server)
                proc.kill()
                proc.wait(timeout=10)

            deadline = time.time() + 30
            while time.time() < deadline and not task.ready():
                time.sleep(0.2)
            self.assertTrue(task.ready(),
                            'المهمة لم تُلغِ بعد استنفاد المحاولات')
            with self.assertRaises(ArabiRuntimeError) as caught:
                task.result()
            self.assertIn('أُلغيت', str(caught.exception))
            self.assertIn('محاولات', str(caught.exception))

            # الموزع ينجو ويخدم بعد الإلغاء
            task2 = disp._server.submit(func, [func, 10], {}, None)
            proc_ok = self._spawn_worker(disp.port())
            procs.append(proc_ok)
            self.assertEqual(task2.result(), 45)
        finally:
            disp.shutdown()
            for p in procs:
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()


if __name__ == '__main__':
    unittest.main()
