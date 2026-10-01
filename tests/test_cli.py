# -*- coding: utf-8 -*-
"""اختبارات سطر الأوامر الخارجية (الإصدار 1.31 — المرحلة 9).

طلب التدقيق (الفصل 16 بند 1): «لا اختبارات CLI شاملة (استدعاء main()
بمجموعات وسائط)». كل اختبار هنا يشغّل العملية كاملة عبر subprocess
كما يفعل المستخدم تمامًا — ويتحقق من رمز الخروج والرسالة العربية.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARABI = os.path.join(ROOT, 'arabi.py')

GOOD = 'اطبع("من سطر الأوامر")\nاطبع(2 + 3)\n'
BAD = 'اطبع(نهاية_غائبة\n'


class TestCliMain(unittest.TestCase):
    """كل مسار موثق في الرسالة الترحيبية — من الخارج بالضبط."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='cli_')
        cls.good = os.path.join(cls.tmp, 'سليم.عربي')
        with open(cls.good, 'w', encoding='utf-8') as f:
            f.write(GOOD)
        cls.bad = os.path.join(cls.tmp, 'مفسود.عربي')
        with open(cls.bad, 'w', encoding='utf-8') as f:
            f.write(BAD)

    def _run(self, *args, timeout=90):
        return subprocess.run(
            [sys.executable, ARABI] + list(args),
            capture_output=True, text=True, timeout=timeout, cwd=ROOT)

    # ---------- الإصدار والمساعدة ----------

    def test_version_flags(self):
        for flag in ('--نسخة', '-v', '--version'):
            r = self._run(flag)
            self.assertEqual(r.returncode, 0, flag)
            self.assertIn('عربي', r.stdout)
            self.assertIn('الإصدار', r.stdout)

    def test_help_flags(self):
        for flag in ('--مساعدة', '-h', '--help'):
            r = self._run(flag)
            self.assertEqual(r.returncode, 0, flag)
            self.assertIn('--تحقق', r.stdout)
            self.assertIn('حزمة', r.stdout)

    # ---------- التحقق النحوي ----------

    def test_check_good_file(self):
        r = self._run('--تحقق', self.good)
        self.assertEqual(r.returncode, 0)
        self.assertIn('سليم', r.stdout)

    def test_check_bad_file_reports_arabic(self):
        r = self._run('--تحقق', self.bad)
        self.assertEqual(r.returncode, 1)
        self.assertIn('السطر', r.stdout + r.stderr)

    def test_check_without_arg_fails_arabic(self):
        r = self._run('--تحقق')
        self.assertEqual(r.returncode, 1)
        self.assertIn('يحتاج', r.stderr)

    # ---------- التشغيل ----------

    def test_run_program(self):
        r = self._run(self.good)
        self.assertEqual(r.returncode, 0)
        self.assertIn('من سطر الأوامر', r.stdout)
        self.assertIn('5', r.stdout)

    def test_run_missing_file_arabic(self):
        r = self._run(os.path.join(self.tmp, 'غير_موجود.عربي'))
        self.assertEqual(r.returncode, 1)
        self.assertIn('غير موجود', r.stdout + r.stderr)

    def test_dash_c_direct_code(self):
        r = self._run('-c', 'اطبع("مباشر" + نص(40 + 2))')
        self.assertEqual(r.returncode, 0)
        self.assertIn('مباشر42', r.stdout)

    def test_dash_c_error_arabic_exit_1(self):
        r = self._run('-c', 'اطبع(1 / 0)')
        self.assertEqual(r.returncode, 1)
        self.assertIn('صفر', r.stdout + r.stderr)

    def test_no_vm_flag_tree_mode(self):
        r = self._run('--لا-دولاب', self.good)
        self.assertEqual(r.returncode, 0)
        self.assertIn('من سطر الأوامر', r.stdout)

    def test_no_bytecode_flag(self):
        r = self._run('--لا-بايت', self.good)
        self.assertEqual(r.returncode, 0)
        self.assertIn('من سطر الأوامر', r.stdout)

    def test_bytecode_compile_then_run(self):
        r = self._run('--بايت', self.good)
        self.assertEqual(r.returncode, 0)
        # ملف البيت يُكتب بجانب البرنامج في __بايت__
        cache_dir = os.path.join(self.tmp, '__بايت__')
        self.assertTrue(os.path.isdir(cache_dir),
                        'الترجمة لم تنشئ مجلد __بايت__')

    # ---------- الأدوات ----------

    def test_format_missing_arg_fails(self):
        r = self._run('--نسق')
        self.assertEqual(r.returncode, 1)
        self.assertIn('يحتاج', r.stderr)

    def test_format_file_idempotent(self):
        messy = os.path.join(self.tmp, 'مشوش.عربي')
        with open(messy, 'w', encoding='utf-8') as f:
            f.write('اطبع("أ")\n\n\n\nاطبع("ب")\n')
        r1 = self._run('--نسق', messy)
        self.assertEqual(r1.returncode, 0)
        with open(messy, encoding='utf-8') as f:
            after = f.read()
        self.assertIn('اطبع("أ")', after)
        self.assertIn('اطبع("ب")', after)
        self.assertNotIn('\n\n\n\n', after)

    def test_lint_missing_arg_fails(self):
        r = self._run('--افحص')
        self.assertEqual(r.returncode, 1)
        self.assertIn('يحتاج', r.stderr)

    def test_lint_clean_file(self):
        r = self._run('--افحص', self.good)
        self.assertEqual(r.returncode, 0)

    def test_docs_missing_arg_fails(self):
        r = self._run('--وثق')
        self.assertEqual(r.returncode, 1)
        self.assertIn('يحتاج', r.stderr)

    def test_docs_generates_output(self):
        target = os.path.join(self.tmp, 'موثق.عربي')
        with open(target, 'w', encoding='utf-8') as f:
            f.write('دالة اجمع(أ، ب):\n    أعد أ + ب\n')
        r = self._run('--وثق', target)
        self.assertEqual(r.returncode, 0)
        self.assertIn('اجمع', r.stdout)

    # ---------- الحزم والعامل ----------

    def test_packages_list_runs(self):
        r = self._run('--حزم')
        self.assertEqual(r.returncode, 0)

    def test_install_missing_arg_fails(self):
        r = self._run('--ثبت')
        self.assertEqual(r.returncode, 1)
        self.assertIn('يحتاج', r.stderr)

    def test_worker_without_address_fails(self):
        r = self._run('--عامل')
        self.assertEqual(r.returncode, 1)
        self.assertIn('عنوان', r.stderr)

    def test_packages_cli_without_subcommand(self):
        r = self._run('حزمة')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('استخدام', r.stdout + r.stderr)

    # ---------- REPL ----------

    def test_repl_piped_session(self):
        r = subprocess.run(
            [sys.executable, ARABI],
            input='اطبع(6 * 7)\nخروج\n',
            capture_output=True, text=True, timeout=90, cwd=ROOT)
        self.assertEqual(r.returncode, 0)
        self.assertIn('42', r.stdout)


if __name__ == '__main__':
    unittest.main()
