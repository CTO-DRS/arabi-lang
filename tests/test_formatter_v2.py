# -*- coding: utf-8 -*-
"""اختبارات المنسق الحتمي v2 (الإصدار 1.37 — أفق التمكين).

معيار إغلاق الخارطة: «فارق صفر على الأمثلة كلها + حارس إلزامي في خط
الاستمرارية» — والنمط القياسي المعتمد عقد المواصفة (الفصل ١٠):
  ١. نهايات أسطر \n والملف ينتهي بسطر واحد
  ٢. التبويب مسافات، والإزاحة القياسية = ٤ مسافات × العمق
  ٣. الأسطر الفارغة المتتالية تُضغط إلى سطر واحد
  ٤. الفراغات الطرفية تُقص، والنصوص متعددة الأسطر كما هي
  ٥. المسافات الداخلية تُحفظ كما كتبها الكاتب (عقد 1.33 الصادق)
الحتمية: نسق(نسق(س)) == نسق(س) — على الأمثلة كلها وعلى مدخلات شاذة.
"""

import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARABI = os.path.join(ROOT, 'arabi.py')
sys.path.insert(0, ROOT)

from arabi_lang.tools import format_source

EXAMPLES_DIR = os.path.join(ROOT, 'examples')


def _example_paths():
    return sorted(
        os.path.join(EXAMPLES_DIR, f)
        for f in os.listdir(EXAMPLES_DIR) if f.endswith('.عربي'))


class FormatterIdempotencyTestCase(unittest.TestCase):
    """نسق×٢ = نسق×١ على كل مثال — بلا استثناء واحد."""

    def test_all_examples_idempotent(self):
        for path in _example_paths():
            with self.subTest(os.path.basename(path)):
                with open(path, encoding='utf-8') as f:
                    source = f.read()
                once, changed1 = format_source(source)
                twice, changed2 = format_source(once)
                self.assertEqual(once, twice)
                self.assertEqual(changed2, 0)

    def test_all_examples_canonical_zero_diff(self):
        """فارق صفر: نسق المحفوظ يعيد المحفوظ نفسه — المعيار الحرفي."""
        for path in _example_paths():
            with self.subTest(os.path.basename(path)):
                with open(path, encoding='utf-8') as f:
                    source = f.read()
                formatted, _ = format_source(source)
                self.assertEqual(formatted, source,
                                 'المثال خارج النمط القياسي — ينقص تشغيل '
                                 '--نسق على الملف والتزميت')

    def test_pathological_inputs_idempotent(self):
        cases = [
            'دالة ف():\n\tس=1\n\t\tأعد س\n',            # تبويبات
            'س = 1\n\n\n\n\nس = 2\n',                    # فراغات متتالية
            'س = 1    \nص = 2\t\n',                      # طرفية
            'س = 1',                                     # بلا نهاية سطر
            'ق = [1،\n   2،\n   3]\n',                   # تتمة
            'ن = ق"""سطر واحد\nوسطران"""    \nس = 1\n',  # نص متعدد
        ]
        for source in cases:
            with self.subTest(repr(source[:24])):
                once, _ = format_source(source)
                twice, _ = format_source(once)
                self.assertEqual(once, twice)

    def test_internal_spacing_preserved(self):
        """عقد 1.33: المسافات الداخلية كما كتبها الكاتب لا يلمسها."""
        source = 'س = 1    +    2\n'
        formatted, _ = format_source(source)
        self.assertIn('1    +    2', formatted)

    def test_multiline_string_untouched(self):
        source = 'ن = ق"""سطر\n    بمسافات\tوطرفية   """\nس = 1\n'
        formatted, _ = format_source(source)
        self.assertIn('سطر\n    بمسافات\tوطرفية   ', formatted)

    def test_valid_stays_valid(self):
        """شبكة الأمان: الأصل السليم ناتجه سليم — والناتج يعمل."""
        from arabi_lang.lexer import Lexer
        from arabi_lang.parser import Parser
        source = ('دالة ف(ن):\n\tلو ن > 0:\n\t\tأعد ن\n\tأعد 0\n'
                  'اطبع(ف(5))\nف(5)\n')
        formatted, _ = format_source(source)
        Parser(Lexer(formatted).tokenize()).parse()
        # والسلوك نفسه قبل وبعد
        from arabi_lang.interpreter import Interpreter
        self.assertEqual(
            Interpreter().run(Parser(Lexer(source).tokenize()).parse()), 5)
        self.assertEqual(
            Interpreter().run(
                Parser(Lexer(formatted).tokenize()).parse()), 5)


class FormatterCliGuardTestCase(unittest.TestCase):
    """الحارس الإلزامي: أمر واحد ينسق الأمثلة كلها ثم يقارن."""

    def test_cli_format_keeps_examples_canonical(self):
        """محاكاة الحارس: نسخ مؤقتة — النسق لا يغيّر شيئًا."""
        tmp = tempfile.mkdtemp(prefix='حارس_نسق_')
        self.addCleanup(lambda: subprocess.run(
            ['rm', '-rf', tmp]))
        paths = _example_paths()
        self.assertGreaterEqual(len(paths), 45)
        copies = []
        for path in paths:
            dst = os.path.join(tmp, os.path.basename(path))
            with open(path, encoding='utf-8') as f:
                content = f.read()
            with open(dst, 'w', encoding='utf-8') as f:
                f.write(content)
            copies.append(dst)
        r = subprocess.run(
            [sys.executable, ARABI, '--نسق'] + copies,
            capture_output=True, text=True, timeout=300, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stderr)
        for path, dst in zip(paths, copies):
            with open(path, encoding='utf-8') as f:
                original = f.read()
            with open(dst, encoding='utf-8') as f:
                self.assertEqual(f.read(), original, path)

    def test_workflow_contains_format_guard(self):
        workflow = open(os.path.join(ROOT, '.github', 'workflows',
                                     'tests.yml'),
                        encoding='utf-8').read()
        self.assertIn('حارس التنسيق الحتمي', workflow)
        self.assertIn('git diff --exit-code', workflow)


if __name__ == '__main__':
    unittest.main()
