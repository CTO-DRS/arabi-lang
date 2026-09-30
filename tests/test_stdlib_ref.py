# -*- coding: utf-8 -*-
"""بوابة المكتبة القياسية (الإصدار 1.27) — مرجع لا ينزلق.

يحرس بندَي الفصل ١٠ من تقرير التدقيق الهندسي:
1. «لا صفحة توثيق برمجي للوحدات العشرين» → docs/مرجع-المكتبة-القياسية.md
   تُقارن أعضاء كل وحدة **كما هي في زمن التشغيل الفعلي** مع المرجع في
   الاتجاهين: كل عضو حقيقي موثق، وكل عضو موثق موجود — فلا يُضاف عضو
   لوحدة دون توثيقه، ولا يوثق عضو غير موجود.
2. «help يذكر ١٧ من ٢٠ وحدة» → أمر المساعدة يجب أن يذكر العشرين كلها.
3. تحذير الموزع الخارجي بلا مفتاح (أمن الإتاحة الموزعة منذ 1.27).
"""

import contextlib
import io
import re
import unittest

import arabi  # noqa: F401  (تأكد أن جذر المشروع في المسار)
from arabi import show_help

from arabi_lang.errors import ArabiRuntimeError
from arabi_lang.interpreter import Interpreter
from arabi_lang.lexer import Lexer
from arabi_lang.parser import Parser
from arabi_lang import runtime

REF_PATH = 'docs/مرجع-المكتبة-القياسية.md'
_strip = runtime.strip_tashkeel


def _stdlib_inventory():
    """يستبطن الوحدات المدمجة والدوال الجاهزة من زمن التشغيل الحقيقي."""
    env = runtime.Env(None)
    with contextlib.redirect_stdout(io.StringIO()):
        runtime.install_builtins(env)
    modules, builtins = {}, set()
    for name, val in env.vars.items():
        if isinstance(val, runtime.ModuleValue):
            modules[name] = set(val.members.keys())
        else:
            builtins.add(name)
    return modules, builtins


def _parse_reference():
    """يستخلص الوحدات وأعضاءها والدوال العامة من ملف المرجع."""
    with open(REF_PATH, encoding='utf-8') as f:
        text = f.read()
    doc_modules, doc_builtins = {}, set()
    sections = re.split(r'^## ', text, flags=re.M)
    for sec in sections:
        lines = sec.split('\n')
        head = lines[0].strip()
        # جدول عام: الأسطر التي تبدأ بـ| `اسم` |
        names = [m.group(1) for line in lines
                 for m in [re.match(r'^\| `([^`]+)` \|', line)] if m]
        if head == 'الدوال الجاهزة العامة':
            doc_builtins = {_strip(n) for n in names}
        elif head.startswith('وحدة '):
            mod = _strip(head[len('وحدة '):].strip())
            doc_modules[mod] = {_strip(n) for n in names}
    return doc_modules, doc_builtins


def _interp(src):
    interp = Interpreter(use_vm=False)
    interp.run(Parser(Lexer(src).tokenize()).parse())
    return interp


class TestReferenceCompleteness(unittest.TestCase):
    """المرجع مطابق للواقع: لا انزلاق واجهة بلا توثيق."""

    def setUp(self):
        self.modules, self.builtins = _stdlib_inventory()
        self.doc_modules, self.doc_builtins = _parse_reference()

    def test_reference_file_exists(self):
        with open(REF_PATH, encoding='utf-8') as f:
            self.assertIn('مرجع المكتبة القياسية', f.read(200))

    def test_twenty_modules_exist(self):
        self.assertEqual(len(self.modules), 20,
                         'عدد الوحدات المدمجة تغيّر — حدّث المرجع والاختبار معًا')

    def test_module_set_parity(self):
        self.assertEqual(
            set(self.doc_modules) - set(self.modules), set(),
            'المرجع يوثق وحدات غير موجودة في زمن التشغيل')
        self.assertEqual(
            set(self.modules) - set(self.doc_modules), set(),
            'وحدات حقيقية بلا قسم في المرجع — وثّقها فورًا')

    def test_every_member_is_documented(self):
        for mod, actual in self.modules.items():
            missing = actual - self.doc_modules.get(mod, set())
            self.assertEqual(
                missing, set(),
                f'أعضاء وحدة {mod} غير موثقين في المرجع: {sorted(missing)}')

    def test_no_phantom_members(self):
        for mod, documented in self.doc_modules.items():
            phantom = documented - self.modules.get(mod, set())
            self.assertEqual(
                phantom, set(),
                f'المرجع يوثق أعضاء غير موجودين في وحدة {mod}: {sorted(phantom)}')

    def test_global_builtins_parity(self):
        self.assertEqual(
            self.builtins - self.doc_builtins, set(),
            f'دوال جاهزة حقيقية غير موثقة: {sorted(self.builtins - self.doc_builtins)}')
        self.assertEqual(
            self.doc_builtins - self.builtins, set(),
            f'المرجع يوثق دوال جاهزة غير موجودة: {sorted(self.doc_builtins - self.builtins)}')


class TestHelpListsAllModules(unittest.TestCase):
    """التدقيق: help يذكر ١٧ من ٢٠ — يجب أن يذكر العشرين كلها."""

    def test_help_output_lists_twenty_modules(self):
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                show_help()
        except SystemExit:
            pass
        out = buf.getvalue()
        modules, _ = _stdlib_inventory()
        for mod in modules:
            self.assertIn(mod, out,
                          f"أمر المساعدة لا يذكر وحدة '{mod}'")
        self.assertIn('٢٠', out, 'يجب ذكر عدد الوحدات (٢٠) في المساعدة')


class TestKeylessExternalDispatcherWarning(unittest.TestCase):
    """موزع بلا مفتاح على عنوان غير محلي = تعرض بلا مصادقة — لا يجوز أن يمر صامتًا."""

    def test_external_keyless_warns(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            interp = _interp('م = موزعة.موزع(0، "0.0.0.0")')
            interp.globals.get('م').shutdown()
        self.assertIn('تحذير أمني', buf.getvalue())
        self.assertIn('0.0.0.0', buf.getvalue())

    def test_external_with_key_is_silent(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            interp = _interp('م = موزعة.موزع(0، "0.0.0.0"، "مفتاح-تجريبي-123456")')
            interp.globals.get('م').shutdown()
        self.assertNotIn('تحذير أمني', buf.getvalue())

    def test_loopback_keyless_is_silent(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            interp = _interp('م = موزعة.موزع(0، "127.0.0.1")')
            interp.globals.get('م').shutdown()
        self.assertNotIn('تحذير أمني', buf.getvalue())

    def test_warning_guides_to_fix(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            interp = _interp('م = موزعة.موزع(0، "0.0.0.0")')
            interp.globals.get('م').shutdown()
        out = buf.getvalue()
        self.assertIn('مفتاح', out, 'التحذير يجب أن يرشد لتمرير مفتاح')
        self.assertIn('127.0.0.1', out, 'التحذير يجب أن يرشد للربط المحلي')


if __name__ == '__main__':
    unittest.main()
