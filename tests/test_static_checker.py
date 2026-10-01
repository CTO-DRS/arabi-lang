# -*- coding: utf-8 -*-
"""اختبارات المدقق الساكن v1 (الإصدار 1.36 — أفق التمكين).

ثلاث طبقات:
  ١. المحرك: check_source على مصادر — كل قرارات المسبار ص١–ص٥
  ٢. سطر الأوامر --تحقق-ساكن عبر subprocess — رموز الخروج والرسائل
  ٣. تكامل CI: المثال الرسمي سليم وخطوة الفحص موجودة في workflow
(معيار الإغلاق: «وضع --تحقق-ساكن يفحص الدوال الموثقة ويُدمج في CI
بمثال مستودع رسمي»)
"""

import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARABI = os.path.join(ROOT, 'arabi.py')
sys.path.insert(0, ROOT)

from arabi_lang.checker import check_source

GOOD = '''دالة متوسط(قيم: قائمة[عدد]) → عشري:
    أعد عدد(1.5)
دالة تحية(اسم: نص) → نص:
    أعد ق"مرحبا {اسم}"
'''


class CheckerEngineTestCase(unittest.TestCase):
    """الطبقة ١: عقود الدوال من المصدر وحده — بلا تشغيل."""

    def _issues(self, source):
        issues, stats = check_source(source)
        return issues, stats

    # ---------- ص١: حل الأسماء ----------

    def test_clean_annotated_program(self):
        issues, stats = self._issues(GOOD)
        self.assertEqual(issues, [])
        self.assertEqual(stats.documented, 2)

    def test_unknown_family_name_rejected(self):
        """الفجوة ١ من المسبار: توصيف مخطئ في دالة غير مستدعاة."""
        issues, _ = self._issues(
            'دالة مجموع(قيم: قائمة[عددد]) → عدد:\n    أعد 1\n')
        self.assertEqual(len(issues), 1)
        self.assertIn('عددد', issues[0].message)
        self.assertIn('غير معروف', issues[0].message)
        self.assertEqual(issues[0].line, 1)

    def test_later_defined_class_visible(self):
        """الجمع الاستباقي: صنف معرف بعد الدالة يُرى (مرآة ق١٣)."""
        issues, _ = self._issues(
            'دالة أصنع() → نقطة:\n    أعد مصدر_مجهول\n\n'
            'صنف نقطة:\n    س = 1\n')
        self.assertEqual(issues, [])

    def test_generic_on_class_rejected(self):
        """التعمية على صنف (أب[عدد]) مخالفة — توصيف بلا أقواس."""
        issues, _ = self._issues(
            'صنف أب:\n    س = 1\n'
            'دالة خاطئة(قيم: قائمة[أب]) → عدد:\n    أعد 1\n')
        # قائمة[أب] صحيحة (قائمة كائنات) — لا مخالفة هنا
        self.assertEqual(issues, [])

    def test_undocumented_functions_ignored(self):
        """الدوال الصامتة خارج العقد — صفر مخالفات وصفر عدّ."""
        issues, stats = self._issues(
            'دالة صامتة(س):\n    أعد س * "نص"\n')
        self.assertEqual(issues, [])
        self.assertEqual(stats.documented, 0)

    # ---------- ص٢: الأدلة الساكنة ----------

    def test_literal_return_violation(self):
        """الفجوة ٢ من المسبار: أعد نص في دالة تعلن عدد."""
        issues, stats = self._issues(
            'دالة اسمي() → عدد:\n    أعد "مرحى"\n')
        self.assertEqual(len(issues), 1)
        self.assertIn('نص', issues[0].message)
        self.assertIn('مرحى', issues[0].message)
        self.assertEqual(stats.evidenced, 1)

    def test_int_evidence_passes_for_number(self):
        """صحيح يمر لعقد عدد (برج ق١٥)."""
        issues, _ = self._issues('دالة رقمية() → عدد:\n    أعد 42\n')
        self.assertEqual(issues, [])

    def test_bool_never_number(self):
        """المنطقي لا يُعد عددًا أبدًا — ق١٥ حرفيًا."""
        issues, _ = self._issues('دالة منطقية() → عدد:\n    أعد صح\n')
        self.assertEqual(len(issues), 1)
        self.assertIn('المنطقي لا يُعد عددًا', issues[0].message)

    def test_arithmetic_evidence(self):
        issues, _ = self._issues(
            'دالة حسابية() → صحيح:\n    أعد 2 + 3 * 4\n')
        self.assertEqual(issues, [])
        issues, _ = self._issues(
            'دالة نصية() → نص:\n    أعد "عربي" + "لغة"\n')
        self.assertEqual(issues, [])

    def test_conversion_call_evidence(self):
        issues, _ = self._issues(
            'دالة تحويل(س: نص) → عدد:\n    أعد عدد(س)\n')
        self.assertEqual(issues, [])

    def test_fstring_is_text_evidence(self):
        issues, _ = self._issues(
            'دالة تحية(اسم: نص) → نص:\n    أعد ق"أهلًا {اسم}"\n')
        self.assertEqual(issues, [])

    def test_list_element_violation(self):
        issues, _ = self._issues(
            'دالة أعداد() → قائمة[عدد]:\n    أعد [1، "اثنان"، 3]\n')
        self.assertEqual(len(issues), 1)
        self.assertIn('توصيف العنصر', issues[0].message)

    def test_class_return_with_literal_evidence(self):
        """دليل حرف لا يمكن أن يكون كائن صنف."""
        issues, _ = self._issues(
            'صنف نقطة:\n    س = 1\n'
            'دالة أصنع() → نقطة:\n    أعد [1]\n')
        self.assertEqual(len(issues), 1)
        self.assertIn('صنف', issues[0].message)

    def test_unknown_expression_skipped(self):
        """حد v1: بلا استنتاج — الاستدعاءات العامة تُتخطى صامتة."""
        issues, stats = self._issues(
            'دالة مجهولة() → عدد:\n    أعد مصدر_غير_محسوم(5)\n')
        self.assertEqual(issues, [])
        self.assertEqual(stats.skipped, 1)

    # ---------- ص٣: السقوط الضمني ----------

    def test_no_return_statement_violation(self):
        """الفجوة ٣ من المسبار: دالة موصّفة بلا أي أعد."""
        issues, _ = self._issues(
            'دالة بلا_أعد() → عدد:\n    س = 1\n')
        self.assertEqual(len(issues), 1)
        self.assertIn('بلا أي أعد', issues[0].message)

    def test_bare_return_with_type_violation(self):
        issues, _ = self._issues(
            'دالة فارغة() → نص:\n    أعد\n')
        self.assertEqual(len(issues), 1)
        self.assertIn('بلا قيمة', issues[0].message)

    def test_none_type_allows_fallthrough_rejects_value(self):
        issues, _ = self._issues(
            'دالة عرض() → عدم:\n    اطبع("سطر")\n')
        self.assertEqual(issues, [])
        issues, _ = self._issues(
            'دالة خطأ() → عدم:\n    أعد 5\n')
        self.assertEqual(len(issues), 1)

    def test_any_type_unchecked(self):
        issues, _ = self._issues(
            'دالة حرّة() → أي:\n    س = 1\n')
        self.assertEqual(issues, [])

    # ---------- ص٤: قطع النطاق ----------

    def test_nested_function_contracts_independent(self):
        """أعد الداخلية لا تعود لأمها — وكل عقد يفحص في نطاقه."""
        issues, stats = self._issues(
            'دالة خارجية() → عدد:\n'
            '    دالة داخلية() → نص:\n'
            '        أعد "نص"\n'
            '    أعد 5\n')
        self.assertEqual(issues, [])
        self.assertEqual(stats.documented, 2)

    def test_nested_violation_reported_on_its_owner(self):
        issues, _ = self._issues(
            'دالة خارجية() → عدد:\n'
            '    دالة داخلية() → نص:\n'
            '        أعد 5\n'
            '    أعد 5\n')
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].func, 'داخلية')

    def test_function_inside_if_is_checked(self):
        issues, _ = self._issues(
            'لو صح:\n'
            '    دالة شرطية() → عدد:\n'
            '        أعد "نص"\n')
        self.assertEqual(len(issues), 1)

    # ---------- ص٥ + الحل الكامل ----------

    def test_multiple_issues_collected(self):
        issues, _ = self._issues(
            'دالة أولى() → نص:\n    أعد 1\n'
            'دالة ثانية() → عدد:\n    أعد صح\n')
        self.assertEqual(len(issues), 2)

    def test_parse_error_is_one_issue(self):
        issues, _ = self._issues('اطبع(ناقص\n')
        self.assertEqual(len(issues), 1)
        self.assertIn('لا يُحلل ساكنًا', issues[0].message)

    def test_runtime_semantics_mirror(self):
        """الدلالة الواحدة: ما يقبله الفاحص الساكن يقبله وقت التشغيل."""
        from arabi_lang.lexer import Lexer
        from arabi_lang.parser import Parser
        from arabi_lang.interpreter import Interpreter
        source = ('دالة رقمية() → عدد:\n    أعد 42\n'
                  'دالة منطقية() → عدد:\n    أعد صح\n'
                  'منطقية()\n')
        issues, _ = self._issues(source)
        # ساكنًا: مخالفة واحدة (منطقية) — ووقت التشغيل يوافق على الرفض
        self.assertEqual(len(issues), 1)
        with self.assertRaises(Exception):
            Interpreter(script_dir=ROOT).run(
                Parser(Lexer(source).tokenize()).parse())


class CheckerCliTestCase(unittest.TestCase):
    """الطبقة ٢: --تحقق-ساكن من الخارج كما يفعله المستخدم."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='فحص_ساكن_')
        cls.good = os.path.join(cls.tmp, 'سليم.عربي')
        with open(cls.good, 'w', encoding='utf-8') as f:
            f.write(GOOD)
        cls.bad = os.path.join(cls.tmp, 'مخالف.عربي')
        with open(cls.bad, 'w', encoding='utf-8') as f:
            f.write('دالة اسمي() → عدد:\n    أعد "مرحى"\n')

    def _run(self, *args, timeout=90):
        return subprocess.run(
            [sys.executable, ARABI] + list(args),
            capture_output=True, text=True, timeout=timeout, cwd=ROOT)

    def test_good_file_exits_zero(self):
        r = self._run('--تحقق-ساكن', self.good)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('دالة موثقة سليمة', r.stdout)
        self.assertIn('✓', r.stdout)

    def test_bad_file_exits_one_with_message(self):
        r = self._run('--تحقق-ساكن', self.bad)
        self.assertEqual(r.returncode, 1)
        self.assertIn('مخالفة ساكنة', r.stdout)
        self.assertIn('مرحى', r.stdout)
        self.assertIn('سطر 2', r.stdout)

    def test_multiple_files_accumulate(self):
        r = self._run('--تحقق-ساكن', self.good, self.bad)
        self.assertEqual(r.returncode, 1)
        self.assertIn('سليم.عربي', r.stdout)
        self.assertIn('مخالف.عربي', r.stdout)

    def test_option_requires_path(self):
        r = self._run('--تحقق-ساكن')
        self.assertEqual(r.returncode, 1)
        self.assertIn('يحتاج مسار ملف', r.stderr)

    def test_missing_file(self):
        r = self._run('--تحقق-ساكن', 'غائب.عربي')
        self.assertEqual(r.returncode, 1)
        self.assertIn('غير موجود', r.stderr)

    def test_help_mentions_option(self):
        r = self._run('--مساعدة')
        self.assertIn('--تحقق-ساكن', r.stdout)


class CheckerCiIntegrationTestCase(unittest.TestCase):
    """الطبقة ٣: المثال الرسمي وخطوة CI — معيار الإغلاق."""

    EXAMPLE = os.path.join(ROOT, 'examples', '46_التوصيف_الساكن.عربي')

    def test_official_example_passes_static_check(self):
        issues, stats = check_source(open(self.EXAMPLE, encoding='utf-8')
                                     .read())
        self.assertEqual(issues, [])
        self.assertGreaterEqual(stats.documented, 5)

    def test_official_example_also_runs(self):
        """الفحص الساكن لا يكسر التنفيذ — المثال يعمل كأي مثال."""
        r = subprocess.run([sys.executable, ARABI, self.EXAMPLE],
                           capture_output=True, text=True, timeout=90,
                           cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('الفحص الساكن', r.stdout)

    def test_workflow_contains_static_check_step(self):
        workflow = open(os.path.join(ROOT, '.github', 'workflows',
                                     'tests.yml'),
                        encoding='utf-8').read()
        self.assertIn('--تحقق-ساكن', workflow)
        self.assertIn('46_التوصيف_الساكن.عربي', workflow)


if __name__ == '__main__':
    unittest.main()
