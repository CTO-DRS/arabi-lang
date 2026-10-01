# -*- coding: utf-8 -*-
"""المصفوفة التفاضلية: الدولاب مقابل الممسح الشجري (الإصدار 1.31 — المرحلة 9).

طلب التدقيق (الفصل 16 بند 4): «لا اختبار انحدار VM-vs-Tree آلي موسع —
28 حالة التدقيق اليدوي مرشح تجميل». هذه الملف يجعلها اختبارات دائمة:
كل برنامج يعمل بالوضعين ويقارن المخرجات حرفيًا — والأخطاء كذلك بنصها
وسطرها. أي انحراف بين المسارين يُكتشف هنا قبل أن يصل للمستخدم.
"""

import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arabi_lang.lexer import Lexer
from arabi_lang.parser import Parser
from arabi_lang.interpreter import Interpreter
from arabi_lang.errors import ArabiError


def _run(src, use_vm):
    """ينفذ برنامجًا ويعيد (المخرجات، الخطأ أو None)."""
    tree = Parser(Lexer(src).tokenize()).parse()
    interp = Interpreter(use_vm=use_vm)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            interp.run(tree)
        return buf.getvalue(), None
    except ArabiError as exc:
        return buf.getvalue(), exc


class TestVmDifferential(unittest.TestCase):
    """كل حالة: نفس البرنامج بالوضعين — مخرجات متطابقة حرفيًا."""

    PROGRAMS = {
        'أسبقية_الحساب': '''
اطبع(2 + 3 * 4)
اطبع((2 + 3) * 4)
اطبع(10 - 4 - 3)
اطبع(7 / 2)
''',
        'نصوص_وحقن': '''
اسم = "عربي"
نسخة = 1.31
اطبع(ق"لغة {اسم} الإصدار {نسخة}")
اطبع(طول(اسم))
اطبع(اسم.كبير())
اطبع("السلام".اعكس())
''',
        'قوائم_وفهم': '''
أعداد = [1، 2، 3، 4، 5، 6]
أزواج = [س * س لكل س في أعداد إن س % 2 == 0]
اطبع(أزواج)
اطبع(طول(أعداد))
أعداد.أضف(7)
اطبع(أعداد[-1])
''',
        'قواميس': '''
شخص = {"الاسم": "سالم"، "العمر": 30}
شخص["المدينة"] = "الرياض"
لكل مفتاح في شخص:
    اطبع(مفتاح، "→"، شخص[مفتاح])
''',
        'أصناف_ووراثة': '''
صنف حيوان:
    دالة إنشاء(الاسم):
        هذا.الاسم = الاسم
    دالة صوت():
        أعد "صوت عام"

صنف كلب من حيوان:
    دالة صوت():
        أعد "هو هو"

ب = كلب("rex")
اطبع(ب.الاسم)
اطبع(ب.صوت())
''',
        'مولدات': '''
دالة تصاعد(حتى):
    لكل س في مدى(حتى):
        أنتج س * 2

م = 0
لكل قيمة في تصاعد(5):
    م += قيمة
اطبع(م)
''',
        'إغلاق_ومزخرف': '''
دالة عداد():
    عدد = 0
    دالة زد():
        عدد += 1
        أعد عدد
    أعد زد

د = عداد()
د()
د()
اطبع(د())

دالة هادئ(دالة_داخلية):
    دالة مغلفة():
        أعد "=[" + نص(دالة_داخلية()) + "]="
    أعد مغلفة

@هادئ
دالة القيمة():
    أعد 42
اطبع(القيمة())
''',
        'أخطاء_مخصصة': '''
صنف خطأ_دفع من استثناء:
    دالة إنشاء(المبلغ):
        هذا.رسالة = "المبلغ " + نص(المبلغ) + " غير كافٍ"

جرب:
    ارفع خطأ_دفع(5)
باستثناء هـ:
    اطبع("مسكناها:"، هـ.رسالة)
''',
        'مطابقة_أنماط': '''
دالة صف(قيمة):
    طابق قيمة
    حالة 0:
        أعد "صفر"
    حالة ن:
        أعد "التقطت: " + نص(ن)

اطبع(صف(0))
اطبع(صف("كلمة"))
اطبع(صف(3.5))
''',
        'بدّل': '''
لكل يوم في ["السبت"، "الجمعة"، "خميس"]:
    بدّل يوم
    حالة "السبت":
        اطبع("بداية الأسبوع")
    حالة "الجمعة":
        اطبع("عطلة")
    افتراض:
        اطبع("يوم عمل")
''',
        'تعاود_وفيبوناتشي': '''
دالة فيب(ن):
    لو ن <= 1:
        أعد ن
    أعد فيب(ن - 1) + فيب(ن - 2)

اطبع([فيب(س) لكل س في مدى(10)])
''',
        'منطق_ودوران': '''
مجموع = 0
س = 1
طالما س <= 100:
    مجموع += س
    س += 1
اطبع(مجموع)

النتيجة = لو مجموع == 5050: "صحيح" وإلا "خاطئ"
اطبع(النتيجة)
اطبع(صح و خطأ)
اطبع(ليس خطأ)
''',
    }

    def test_programs_identical_output(self):
        """كل برنامج: مخرجات الشجري = مخرجات الدولاب حرفيًا."""
        for name, src in self.PROGRAMS.items():
            with self.subTest(برنامج=name):
                out_tree, err_tree = _run(src, use_vm=False)
                out_vm, err_vm = _run(src, use_vm=True)
                self.assertIsNone(err_tree, f'{name}: الشجري رفع {err_tree}')
                self.assertIsNone(err_vm, f'{name}: الدولاب رفع {err_vm}')
                self.assertEqual(out_tree, out_vm,
                                 f'{name}: مخرجات المسارين تخالفت')
                self.assertTrue(out_tree.strip(),
                                f'{name}: البرنامج لم ينتج مخرجات أصلًا')

    def test_error_equivalence_undefined_name(self):
        """الخطأ نفسه بنصه وسطره في المسارين — متغير غير معرف."""
        src = 'اطبع(المتغير_الغائب)\nاطبع("لا يصل هنا")\n'
        out_t, err_t = _run(src, use_vm=False)
        out_v, err_v = _run(src, use_vm=True)
        self.assertIsNotNone(err_t)
        self.assertIsNotNone(err_v)
        self.assertEqual(str(err_t), str(err_v))

    def test_error_equivalence_zero_division(self):
        """القسمة على صفر: الرسالة العربية نفسها في المسارين."""
        src = 'ن = 0\nاطبع(5 / ن)\n'
        out_t, err_t = _run(src, use_vm=False)
        out_v, err_v = _run(src, use_vm=True)
        self.assertIsNotNone(err_t)
        self.assertIsNotNone(err_v)
        self.assertEqual(str(err_t), str(err_v))
        self.assertIn('صفر', str(err_t))

    def test_error_equivalence_type_error(self):
        """خطأ النوع: نص + عدد — نفس الرسالة والسطر في المسارين."""
        src = 'ن = 3\nاطبع("نص" + ن)\n'
        out_t, err_t = _run(src, use_vm=False)
        out_v, err_v = _run(src, use_vm=True)
        self.assertIsNotNone(err_t)
        self.assertIsNotNone(err_v)
        self.assertEqual(str(err_t), str(err_v))

    def test_differential_on_project_examples(self):
        """أمثلة المشروع نفسها (الأولى عشرة) متطابقة بين المسارين."""
        examples_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'examples')
        picked = sorted(f for f in os.listdir(examples_dir)
                        if f.endswith('.عربي'))[:10]
        self.assertTrue(picked, 'لا أمثلة في مجلد الأمثلة؟')
        for fname in picked:
            with self.subTest(مثال=fname):
                with open(os.path.join(examples_dir, fname),
                          encoding='utf-8') as f:
                    src = f.read()
                if 'إدخال(' in src:
                    # مثال تفاعلي يقرأ الطرفية (لعبة التخمين) — لا يعمل بلا stdin:
                    # تحت pytest يرفع OSError (الالتقاط) وتحت unittest يرفع EOFError
                    continue
                try:
                    out_t, err_t = _run(src, use_vm=False)
                except (OSError, EOFError):
                    continue
                try:
                    out_v, err_v = _run(src, use_vm=True)
                except (OSError, EOFError):
                    self.fail(f'{fname}: الشجري يعمل والدولاب رفع EOF؟')

                if err_t is not None or err_v is not None:
                    # مثال يرفع خطأً مقصودًا — يجب أن يكون هو نفسه في المسارين
                    self.assertEqual(str(err_t), str(err_v),
                                     f'{fname}: الأخطاء تخالفت')
                else:
                    self.assertEqual(out_t, out_v,
                                     f'{fname}: المخرجات تخالفت')


if __name__ == '__main__':
    unittest.main()
