# -*- coding: utf-8 -*-
"""اختبارات انحدار إصلاحات تقرير التدقيق الهندسي (1.24).

كل اختبار هنا يحرس إصلاحًا موثقًا في docs/تقرير-التدقيق-الهندسي.md —
هجمات شبكة، مهل، ترميز روابط، ودلالات كان يمكن أن تنكسر صامتة.
"""

import io
import json
import os
import socket
import tempfile
import threading
import time
import unittest
import zipfile

from arabi_lang import registry
from arabi_lang.errors import ArabiError, ArabiRuntimeError
from arabi_lang.interpreter import Interpreter
from arabi_lang.lexer import Lexer
from arabi_lang.nodes import Break, Continue, Null, Pass
from arabi_lang.parser import Parser
from arabi_lang import packages, runtime


def _run(src):
    interp = Interpreter(use_vm=False)
    return interp.run(Parser(Lexer(src).tokenize()).parse())


def _interp(src):
    interp = Interpreter(use_vm=False)
    interp.run(Parser(Lexer(src).tokenize()).parse())
    return interp


def _run_vm(src):
    interp = Interpreter(use_vm=True)
    return interp.run(Parser(Lexer(src).tokenize()).parse())


class TestRegistryTraversalFix(unittest.TestCase):
    """م11-1: ثغرة تنقل المسارات في تنزيل السجل — مغلقة."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = os.path.join(self.tmp, 'store')
        os.makedirs(self.store)
        self.secret = os.path.join(self.tmp, 'secret.zip')
        with open(self.secret, 'wb') as f:
            f.write(b'SECRET-ZIP-OUTSIDE-STORE')
        self.reg = registry.RegistryServer(self.store, '127.0.0.1', 0)
        self.reg.start()
        self.port = self.reg._httpd.server_address[1]
        time.sleep(0.1)
        # حزمة منشورة شرعية (الثغرة تتطلب اسم حزمة قائم)
        pkg = os.path.join(self.tmp, 'tr')
        os.makedirs(pkg)
        with open(os.path.join(pkg, 'tr.عربي'), 'w', encoding='utf-8') as f:
            f.write('دالة تحية():\n    أعد "مرحبا"\n')
        zp = os.path.join(self.tmp, '1.0.0.zip')
        with zipfile.ZipFile(zp, 'w') as z:
            z.write(os.path.join(pkg, 'tr.عربي'), 'tr.عربي')
            z.writestr('حزمة.json', json.dumps(
                {'الاسم': 'tr', 'النسخة': '1.0.0', 'الوصف': 'تج',
                 'المدخل': 'tr.عربي'}, ensure_ascii=False))
        with open(zp, 'rb') as f:
            blob = f.read()
        self.reg.publish_bytes(blob, 'tr', '1.0.0')

    def tearDown(self):
        self.reg.stop()

    def _get(self, raw_path):
        req = (f'GET {raw_path} HTTP/1.1\r\nHost: h\r\n'
               'Connection: close\r\n\r\n')
        s = socket.create_connection(('127.0.0.1', self.port), timeout=5)
        s.sendall(req.encode())
        data = b''
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
        s.close()
        return data

    def test_legitimate_download_works(self):
        data = self._get('/%D8%AA%D8%AD%D9%85%D9%8A%D9%84/tr/1.0.0')
        self.assertIn(b'200 OK', data.split(b'\r\n', 1)[0])
        self.assertIn(b'PK', data)          # أرشيف zip سليم

    def test_traversal_attacks_blocked(self):
        attacks = [
            '/%D8%AA%D8%AD%D9%85%D9%8A%D9%84/tr/..%2F..%2F..%2Fsecret',
            '/%D8%AA%D8%AD%D9%85%D9%8A%D9%84/tr/..%2F..%2Fsecret.zip',
            '/%D8%AA%D8%AD%D9%85%D9%8A%D9%84/tr/%2E%2E%2Fsecret',
            '/%D8%AA%D8%AD%D9%85%D9%8A%D9%84/tr/..%2Fsecret.zip',
        ]
        for path in attacks:
            data = self._get(path)
            status = data.split(b'\r\n', 1)[0]
            self.assertNotIn(b'200 OK', status,
                             f'تسريب عبر {path}')
            self.assertNotIn(b'SECRET-ZIP-OUTSIDE-STORE', data)

    def test_safe_version_segment_rejects_paths(self):
        self.assertIsNone(registry._safe_version_segment('../secret'))
        self.assertIsNone(registry._safe_version_segment('..'))
        self.assertIsNone(registry._safe_version_segment('a/b'))
        self.assertIsNone(registry._safe_version_segment(''))
        self.assertEqual(registry._safe_version_segment('1.2.3'), '1.2.3')
        self.assertEqual(registry._safe_version_segment('1.0-beta'),
                         '1.0-beta')

    def test_zip_path_contained_in_root(self):
        root = os.path.join(self.store, 'حزم', 'tr')
        path = registry._version_zip_path(self.store, 'tr', '1.0.0')
        self.assertTrue(os.path.abspath(path).startswith(
            os.path.abspath(root) + os.sep))
        with self.assertRaises(ArabiError):
            registry._version_zip_path(self.store, 'tr', '../../x')

    def test_version_sort_tolerates_non_numeric(self):
        # نسخة غير رقمية في المخزن كانت تفجر كل مسارات الفحص بـ ValueError
        pkg_root = registry._pkg_root(self.store, 'قدیم')
        os.makedirs(pkg_root, exist_ok=True)
        meta = {'الاسم': 'قدیم', 'النسخة': '1.0-beta', 'الوصف': ''}
        with open(registry._version_meta_path(
                self.store, 'قدیم', '1.0-beta'), 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False)
        versions = registry._scan_versions(self.store, 'قدیم')
        self.assertEqual(versions[0]['النسخة'], '1.0-beta')


class TestDefaultStoreFix(unittest.TestCase):
    """م11-2: «حزمة خادم» بلا مجلد كانت تشير لثابت محذوف."""

    def test_default_store_dir_under_cwd(self):
        d = registry.default_store_dir()
        self.assertTrue(os.path.isabs(d))
        self.assertEqual(os.path.basename(d), 'سجل-الحزم')
        self.assertEqual(d, registry.default_store_dir())

    def test_registry_module_has_no_missing_attr(self):
        # الأثر الأصلي: AttributeError على registry.DEFAULT_STORE
        self.assertTrue(hasattr(registry, 'default_store_dir'))
        self.assertTrue(callable(registry.default_store_dir))


class TestDispatcherHostFix(unittest.TestCase):
    """م15-1: موزع بعنوان ومفتاح كان يهمل العنوان بصمت."""

    def test_host_with_key_is_honored(self):
        interp = _interp('م = موزعة.موزع(0، "127.0.0.1"، "مفتاح-تجريبي-123456")')
        disp = interp.globals.get('م')
        self.assertEqual(disp._server.host(), '127.0.0.1')
        self.assertTrue(disp.encrypted())
        disp.shutdown()

    def test_host_without_key_is_honored(self):
        interp = _interp('م = موزعة.موزع(0، "127.0.0.1")')
        disp = interp.globals.get('م')
        self.assertEqual(disp._server.host(), '127.0.0.1')
        disp.shutdown()

    def test_host_type_still_checked_with_key(self):
        with self.assertRaises(ArabiRuntimeError):
            _interp('م = موزعة.موزع(0، 42، "مفتاح-تجريبي-123456")')


class TestTaskTimeoutFix(unittest.TestCase):
    """م6-1: نتيجة مهمة التجمع كانت تنتظر للأبد."""

    def test_pool_task_result_times_out(self):
        original = runtime.PROCESS_TIMEOUT
        runtime.PROCESS_TIMEOUT = 0.05
        try:
            task = runtime.ProcessTaskValue()
            with self.assertRaises(ArabiRuntimeError) as ctx:
                task.result(3)
            self.assertIn('مهلة', ctx.exception.message)
        finally:
            runtime.PROCESS_TIMEOUT = original

    def test_pool_task_result_still_returns_value(self):
        task = runtime.ProcessTaskValue()
        task._finish(42, None)
        self.assertEqual(task.result(), 42)


class TestContainsLiveFix(unittest.TestCase):
    """م6/م15: حد العمق 12 كان يصنف قيمًا قابلة للنقل كأنها حية."""

    def test_deep_transferable_not_considered_live(self):
        # 30 مستوى تداخل قابل للنقل — كانت تُتخطى صامتة بعد العمق 12
        deep = 'قيمة'
        for _ in range(30):
            deep = [deep]
        from arabi_lang.processes import _contains_live
        self.assertFalse(_contains_live(deep))

    def test_live_object_deep_inside_is_found(self):
        from arabi_lang.processes import _contains_live
        live = runtime.LockValue()
        self.assertTrue(_contains_live([[[live]]]))

    def test_cycle_safe(self):
        from arabi_lang.processes import _contains_live
        cyc = ['بند']
        cyc.append(cyc)
        self.assertFalse(_contains_live(cyc))


class TestVmRegression(unittest.TestCase):
    """م9: الدولاب بعد توحيد اختبار الصحة عبر _truthy وتبسيط الاحتياط."""

    def test_vm_matches_tree_walker(self):
        src = ('دالة مجموع(ن):\n'
               '    م = ٠\n'
               '    لكل س في مدى(ن + ١):\n'
               '        لو س % ٢ == ٠:\n'
               '            م += س\n'
               '        وإلا:\n'
               '            م += ١\n'
               '    أعد م\n'
               'مجموع(١٠٠)')
        self.assertEqual(_run_vm(src), _run(src))

    def test_vm_break_in_try_inside_loop(self):
        src = ('م = ٠\n'
               'لكل س في مدى(٥):\n'
               '    جرب:\n'
               '        لو س == ٣:\n'
               '            كسر\n'
               '        م += س\n'
               '    اخيرا:\n'
               '        م += ١٠٠\n'
               'م')
        self.assertEqual(_run_vm(src), _run(src))

    def test_fallback_stmt_carries_node_only(self):
        from arabi_lang.vm import compile_function, VmCode, OP_EXEC_STMT
        src = ('دالة هم(س):\n'
               '    طابق س\n'
               '    حالة ١:\n'
               '        أعد "واحد"\n'
               '    غير ذلك:\n'
               '        أعد "أخرى"\n')
        tokens = Lexer(src).tokenize()
        tree = Parser(tokens).parse()
        fn_node = tree.statements[0]
        code = compile_function(fn_node.body)
        self.assertIsInstance(code, VmCode)
        # جملة طابق غير مدعومة تُضمَّن عقدة مباشرة (لا صف ثلاثي قديم)
        fallback = [i for i in code.instrs if i[0] == OP_EXEC_STMT]
        self.assertTrue(fallback)
        self.assertNotIsInstance(fallback[0][1], tuple)


class TestNodesCarryLine(unittest.TestCase):
    """م20: عقد كسر/استمر/تجاهل/ولا شيء كانت بلا سطر."""

    def test_break_continue_pass_null_accept_line(self):
        for cls in (Break, Continue, Pass, Null):
            node = cls(7)
            self.assertEqual(node.line, 7)


class TestPackageSafety(unittest.TestCase):
    """م11-5/6: فك نظيف وحارس zip-slip في العميل."""

    def test_safe_extractall_blocks_zip_slip(self):
        tmp = tempfile.mkdtemp()
        target = os.path.join(tmp, 'هدف')
        os.makedirs(target)
        evil = os.path.join(tmp, 'شرير.zip')
        with zipfile.ZipFile(evil, 'w') as z:
            z.writestr('../هارب.عربي', 'محتوى')
        with zipfile.ZipFile(evil) as z:
            with self.assertRaises(ArabiError):
                packages._safe_extractall(z, target)
        # لم يُفك شيء خارج الهدف
        self.assertFalse(os.path.exists(
            os.path.join(tmp, 'هارب.عربي')))

    def test_zip_fetch_does_not_pollute_package(self):
        tmp = tempfile.mkdtemp()
        src = os.path.join(tmp, 'مصدر')
        os.makedirs(src)
        with open(os.path.join(src, 'مكتبة.عربي'), 'w',
                  encoding='utf-8') as f:
            f.write('دالة مرحبا():\n    أعد "أهلا"\n')
        with open(os.path.join(src, 'حزمة.json'), 'w',
                  encoding='utf-8') as f:
            json.dump({'الاسم': 'مكتبة', 'النسخة': '1.0.0',
                       'الوصف': '', 'المدخل': 'مكتبة.عربي'},
                      f, ensure_ascii=False)
        archive = os.path.join(tmp, '1.0.0.zip')
        with zipfile.ZipFile(archive, 'w') as z:
            z.write(os.path.join(src, 'مكتبة.عربي'), 'مكتبة.عربي')
            z.write(os.path.join(src, 'حزمة.json'), 'حزمة.json')
        fetched, _fp = packages._fetch_local(archive, tmp, 'مكتبة',
                                             None, downloaded=True)
        files = []
        for base, _dirs, names in os.walk(fetched):
            files.extend(names)
        self.assertIn('حزمة.json', files)
        self.assertNotIn('1.0.0.zip', files)   # لا بايتات الأرشيف داخلها


class TestToolsUrlQuote(unittest.TestCase):
    """م11/أدوات: روابط عربية كانت تفجر التثبيت بـ UnicodeEncodeError."""

    def test_quote_url_keeps_ascii_intact(self):
        from arabi_lang.tools import _quote_url
        plain = 'http://host:8080/path/file.عربي?x=1#f'
        quoted = _quote_url(plain)
        self.assertEqual(
            quoted,
            'http://host:8080/path/file.%D8%B9%D8%B1%D8%A8%D9%8A'
            '?x=1#f')
        # الرموز البنيوية تبقى كما هي
        self.assertIn('?', quoted)
        self.assertIn('#', quoted)
        self.assertNotIn('%3F', quoted)


class TestLspHygiene(unittest.TestCase):
    """م15/18: إصدار الخادم يطابق الحزمة + رأس ضخم يرفض."""

    def test_lsp_version_matches_package(self):
        import arabi_lang
        from arabi_lang import lsp
        self.assertEqual(lsp.VERSION, arabi_lang.__version__)

    def test_read_message_rejects_oversized(self):
        from arabi_lang.lsp import read_message, MAX_MESSAGE_BYTES
        stream = io.BytesIO(
            f'Content-Length: {MAX_MESSAGE_BYTES + 1}\r\n\r\n'.encode())
        self.assertIsNone(read_message(stream))

    def test_read_message_reads_normal(self):
        from arabi_lang.lsp import read_message
        body = json.dumps({'jsonrpc': '2.0', 'id': 1}).encode('utf-8')
        stream = io.BytesIO(
            f'Content-Length: {len(body)}\r\n\r\n'.encode() + body)
        msg = read_message(stream)
        self.assertEqual(msg['id'], 1)


class TestParserMessageFix(unittest.TestCase):
    """م19: رسالة الإسناد كانت تقول «الجهة اليمين» للهدف الأيسر."""

    def test_assign_target_message_correct_side(self):
        src = '٥ = ٣'
        with self.assertRaises(Exception) as ctx:
            Parser(Lexer(src).tokenize()).parse()
        self.assertIn('اليسرى', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
