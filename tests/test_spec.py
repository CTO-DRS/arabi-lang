# -*- coding: utf-8 -*-
"""اختبارات مواصفة اللغة — المرحلة 2 (الإصدار 1.24.0).

لكل قرار محسوم في docs/مواصفة-اللغة.md اختبار يثبت سلوكه:
  ق١  معامل ٪ العربية و٪=                → TestModulo
  ق٢  سياسة التشكيل (يُقبل ولا يميز)     → TestDiacritics
  ق٣  الكشيدة مقبولة مع إرشاد ذكي        → TestTatweel
  ق٤  محارف bidi مرفوضة في الكود          → TestBidiSecurity
  ق٥  ٫ عشري و٬ فاصل آلاف                → TestArabicNumbers
  ق٦  التقاط بالصنف بكـ                   → TestClassCatching
  ق٧  بدل كلمة مفتاحية بلا شدة            → TestDiacritics
  ق٨  ربط الحلقة المثبت (متوافق بايثون 3) → TestLoopBinding
  ق٩  المزخرفات مع غير المتزامنة          → TestAsyncDecorators
  ق١٠ الرسائل الدقيقة للصيغ المرفوضة      → TestImprovedMessages
"""

import io
import os
import sys
import unittest
from contextlib import redirect_stdout

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from arabi import run_code                                  # noqa: E402
from arabi_lang.interpreter import Interpreter              # noqa: E402
from arabi_lang.lexer import Lexer                          # noqa: E402
from arabi_lang.parser import Parser                        # noqa: E402
from arabi_lang.errors import (                             # noqa: E402
    ArabiRuntimeError, LexerError, ParseError,
)


def last(src, script_dir=None):
    """ينفذ ويعيد قيمة آخر تعبير — فحص قيمي مباشر (الممسح الشجري)."""
    tree = Parser(Lexer(src).tokenize()).parse()
    interp = Interpreter(script_dir=script_dir or os.getcwd())
    return interp.run(tree)


def last_vm(src, script_dir=None):
    """نفس الفحص عبر مسار الدولاب (الافتراضي في التشغيل الفعلي)."""
    tree = Parser(Lexer(src).tokenize()).parse()
    interp = Interpreter(script_dir=script_dir or os.getcwd(),
                         use_bytecode=False)
    return interp.run(tree)


def expect_error(src, exc_type, keyword):
    """ينفذ متوقعًا الخطأ — يفشل إن لم يرفع أو لم تحوِ الرسالة المفتاح."""
    try:
        run_code(src)
    except exc_type as exc:
        assert keyword in str(exc), (
            f"الرسالة '{exc}' لا تحتوي على '{keyword}'")
        return exc
    raise AssertionError(
        f"لم يُرفع {exc_type.__name__} للكود: {src[:60]}")


# ======================= ق١: معامل ٪ و٪= =======================

class TestModulo(unittest.TestCase):
    """معامل باقي القسمة بالعلامتين العربية والغربية والإسناد المركب."""

    def test_basic(self):
        self.assertEqual(last('٧ ٪ ٢'), 1)
        self.assertEqual(last('٧ % ٢'), 1)

    def test_sign_follows_divisor(self):
        # الدلالة الموثقة: إشارة الناتج تتبع المقسوم عليه
        self.assertEqual(last('-٧ ٪ ٣'), 2)
        self.assertEqual(last('٧ ٪ -٣'), -2)

    def test_float(self):
        self.assertAlmostEqual(last('٧.٥ ٪ ٢'), 1.5)

    def test_precedence_with_multiplication(self):
        # ٪ في مستوى الضربة: ٧ ٪ ٤ * ٢ = (٧ ٪ ٤) * ٢ = ٦
        self.assertEqual(last('٧ ٪ ٤ * ٢'), 6)
        self.assertEqual(last('٢ * ٧ ٪ ٤'), 2)

    def test_modulo_assign_arabic(self):
        self.assertEqual(last('س = ٧\nس ٪= ٢\nس'), 1)

    def test_modulo_assign_ascii(self):
        self.assertEqual(last('س = ٧\nس %= ٢\nس'), 1)

    def test_modulo_assign_index_and_attr(self):
        self.assertEqual(
            last('ل = [١٠]\nل[٠] ٪= ٣\nل[٠]'), 1)

    def test_zero_division_arabic_message(self):
        expect_error('اطبع(٥ ٪ ٠)', ArabiRuntimeError,
                     'قسمة على صفر')

    def test_non_numbers_rejected(self):
        expect_error('اطبع("نص" ٪ ٢)', ArabiRuntimeError, 'يحتاج عددين')

    def test_vm_parity(self):
        # التكافؤ بين الممسح والدولاب على كل الصيغ الجديدة
        cases = ['٧ ٪ ٢', '-٧ ٪ ٣', '٧.٥ ٪ ٢', '١٠ ٪ ٤ * ٢']
        for src in cases:
            self.assertEqual(last(src), last_vm(src),
                             f'اختلاف التكافؤ في: {src}')
        self.assertEqual(
            last('س = ١٧\nس ٪= ٥\nس'), last_vm('س = ١٧\nس ٪= ٥\nس'))

    def test_in_fstring(self):
        self.assertEqual(
            run_code('اطبع(ق"الباقي {١٠ ٪ ٣}")'), 'الباقي 1\n')

    def test_operator_overload_baqi(self):
        # تحميل العامل على الكائنات بطريقة 'باقي' — يعمل بالعلامتين
        src = (
            'صنف زوجي:\n'
            '    دالة باقي(آخر):\n'
            '        أعد ٩\n'
            'اطبع(زوجي() ٪ ٤)\n'
            'اطبع(زوجي() % ٤)\n'
        )
        self.assertEqual(run_code(src), '9\n9\n')


# ======================= ق٢/ق٧: سياسة التشكيل =======================

class TestDiacritics(unittest.TestCase):
    """التشكيل يُقبل ولا يميز: كلمات مفتاحية ومعرفات بتشكيلها الطبيعي."""

    def test_keyword_with_diacritics(self):
        self.assertEqual(
            run_code('لَوَ صَح:\n    اطبع("أول")\nوَإِلَّا:\n    اطبع("ثان")'),
            'أول\n')

    def test_compound_keyword_with_diacritics(self):
        self.assertEqual(
            run_code('لَوَ خَطَأ:\n    اطبع("أول")\nوَإِلَا إِذَا صَح:\n    اطبع("ثان")'),
            'ثان\n')

    def test_identifiers_equivalent(self):
        # معرفان يختلفان بتشكيل = متغير واحد
        self.assertEqual(
            last('مُهَنْدِس = ٥\nمهندس = مهندس + ١\nمُهندس'), 6)

    def test_def_keyword_stripped(self):
        src = (
            'دَالَة جمع(أ، ب):\n'
            '    أَعُدّ أ + ب\n'
            'جمع(٢، ٣)\n'
        )
        self.assertEqual(last(src), 5)

    def test_badal_without_shadda_is_keyword(self):
        # قرار ق٧: بدل كلمة مفتاحية بلا شدة شرط
        src = (
            'يوم = "أحد"\n'
            'بدل يوم\n'
            'حالة "سبت":\n'
            '    اطبع("عطلة")\n'
            'حالة "أحد":\n'
            '    اطبع("دوام")\n'
        )
        self.assertEqual(run_code(src), 'دوام\n')

    def test_badal_with_shadda_still_keyword(self):
        src = (
            'يوم = "اثنين"\n'
            'بدّل يوم\n'
            'حالة "سبت":\n'
            '    اطبع("عطلة")\n'
            'حالة "اثنين":\n'
            '    اطبع("دوام")\n'
        )
        self.assertEqual(run_code(src), 'دوام\n')

    def test_waw_with_diacritic_is_and(self):
        self.assertTrue(last('صَح وَ صَح'))

    def test_strings_keep_diacritics(self):
        # السلاسل محتوى نصي مشروع — تشكيلها لا يُمس
        self.assertEqual(
            run_code('اطبع("مُحَمَّد")'), 'مُحَمَّد\n')

    def test_comments_keep_diacritics(self):
        self.assertEqual(
            run_code('# تعليقٌ مشكَّلٌ بالكامل\nاطبع("تم")'), 'تم\n')

    def test_diacritics_in_tashkeel_only_names_reported_plain(self):
        # الرسائل تسمي الاسم المجرّد — سلوك موثق في المواصفة ١٫٢
        exc = expect_error('اطبع(مُتغَير)', ArabiRuntimeError, 'متغير')


# ======================= ق٣: الكشيدة =======================

class TestTatweel(unittest.TestCase):
    """الكشيدة جزء مشروع من المعرف؛ وإرشاد ذكي عند إخفائها كلمة مفتاحية."""

    def test_ha_tatweel_binding_unchanged(self):
        # الرابط هـ في صيغته الراسخة يعمل كما كان دائمًا
        src = (
            'صنف صنف_س من استثناء:\n'
            '    دالة إنشاء():\n'
            '        هذا.رسالة = "س"\n'
            'جرب:\n'
            '    ارفع صنف_س()\n'
            'باستثناء هـ:\n'
            '    اطبع(هـ.رسالة)\n'
        )
        self.assertEqual(run_code(src), 'س\n')

    def test_bare_ka_is_identifier(self):
        # ك معرف حقيقي في أمثلة قائمة — لا يحجز
        self.assertEqual(last('ك = ٥\nك'), 5)

    def test_ka_tatweel_keyword(self):
        # كـ داخل جرب: عام مع ربط — تمر على الكتل المطابقة
        self.assertEqual(
            run_code('جرب:\n    اطبع(١)\nباستثناء كـ هـ:\n    اطبع(٢)'),
            '1\n')

    def test_tatweel_in_plain_identifier_accepted(self):
        self.assertEqual(last('اسمـ_ممدود = ٣\nاسمـ_ممدود'), 3)

    def test_tatweel_hint_when_hiding_keyword(self):
        # لوـ (بكشيدة) لا يصير معرفًا صامتًا — إرشاد يكشف القصد
        exc = expect_error('لَوـ صَح:\nاطبع("لا")', LexerError, 'لو')
        self.assertIn('كشيدة', str(exc))

    def test_tatweel_inside_string_kept(self):
        self.assertEqual(
            run_code('اطبع("الـــســــلام")'), 'الـــســــلام\n')


# ======================= ق٤: محارف bidi =======================

class TestBidiSecurity(unittest.TestCase):
    """محارف الاتجاه مرفوضة في الكود (دفاع المصدر الطروادي) ومقبولة نصًا."""

    def test_rlm_in_code_rejected_with_escape(self):
        src = 'س = ١\u200f٠'          # RLM بين رقمي العدد
        exc = expect_error(src, LexerError, 'U+200F')
        self.assertIn('اتجاه', str(exc))

    def test_lro_in_code_rejected(self):
        exc = expect_error('اطبع(\u202e"س")', LexerError, 'U+202E')

    def test_bidi_inside_string_accepted(self):
        # حق الكاتب العربي في ضبط اتجاه نصه داخل السلاسل
        self.assertEqual(
            run_code('اطبع("عربي \u200fداخل نص")'), 'عربي \u200fداخل نص\n')

    def test_bidi_inside_comment_accepted(self):
        self.assertEqual(
            run_code('# التعليق \u200fهنا\nاطبع("تم")'), 'تم\n')


# ======================= ق٥: أرقام ٫ و٬ =======================

class TestArabicNumbers(unittest.TestCase):
    """الفاصلة العشرية العربية وفاصل الآلاف داخل الأعداد."""

    def test_thousands_separator(self):
        self.assertEqual(last('١٬٢٣٤'), 1234)
        self.assertEqual(last('١٬٢٣٤٬٥٦٧'), 1234567)

    def test_thousands_mixed_scripts(self):
        self.assertEqual(last('1٬234'), 1234)
        self.assertEqual(last('١2٬3'), 123)

    def test_decimal_separator(self):
        self.assertAlmostEqual(last('٣٫١٤'), 3.14)
        self.assertAlmostEqual(last('١٬٢٣٤٫٥٦'), 1234.56)

    def test_ascii_still_works(self):
        self.assertAlmostEqual(last('3.14'), 3.14)
        self.assertEqual(last('1234'), 1234)

    def test_misplaced_thousands_named_clearly(self):
        exc = expect_error('س = ١٬', LexerError, 'فاصل الآلاف')
        self.assertIn('U+066C', str(exc))

    def test_misplaced_decimal_named_clearly(self):
        exc = expect_error('اطبع(٫٥)', LexerError, 'عشرية')

    def test_vm_parity(self):
        self.assertEqual(last('١٬٢٣٤ + ١'), last_vm('١٬٢٣٤ + ١'))


# ======================= ق٦: التقاط بالصنف =======================

HIERARCHY = (
    'صنف خطأ_دفع من استثناء:\n'
    '    دالة إنشاء(رسالة):\n'
    '        هذا.رسالة = رسالة\n'
    '\n'
    'صنف خطأ_رصيد من خطأ_دفع:\n'
    '    دالة إنشاء(رسالة):\n'
    '        الأصل.إنشاء(رسالة)\n'
)


class TestClassCatching(unittest.TestCase):
    """باستثناء [صنف] [كـ [اسم]]: — عدد كتل حر وأول مطابق يفوز."""

    def test_catch_by_class(self):
        src = HIERARCHY + (
            'جرب:\n'
            '    ارفع خطأ_رصيد("الرصيد غير كافٍ")\n'
            'باستثناء خطأ_رصيد كـ هـ:\n'
            '    اطبع("رصيد: " + هـ.رسالة)\n'
        )
        self.assertEqual(run_code(src), 'رصيد: الرصيد غير كافٍ\n')

    def test_parent_filter_catches_subclass(self):
        src = HIERARCHY + (
            'جرب:\n'
            '    ارفع خطأ_رصيد("مرفوض")\n'
            'باستثناء خطأ_دفع كـ هـ:\n'
            '    اطبع("دفع: " + هـ.رسالة)\n'
        )
        self.assertEqual(run_code(src), 'دفع: مرفوض\n')

    def test_first_matching_wins(self):
        src = HIERARCHY + (
            'جرب:\n'
            '    ارفع خطأ_رصيد("س")\n'
            'باستثناء خطأ_رصيد كـ هـ:\n'
            '    اطبع("الأول")\n'
            'باستثناء خطأ_دفع كـ هـ:\n'
            '    اطبع("الثاني")\n'
        )
        self.assertEqual(run_code(src), 'الأول\n')

    def test_catch_all_after_specific(self):
        src = HIERARCHY + (
            'جرب:\n'
            '    ارفع خطأ_دفع("س")\n'
            'باستثناء خطأ_رصيد كـ هـ:\n'
            '    اطبع("رصيد")\n'
            'باستثناء كـ هـ:\n'
            '    اطبع("عام: " + هـ.رسالة)\n'
        )
        self.assertEqual(run_code(src), 'عام: س\n')

    def test_filter_without_binding(self):
        src = HIERARCHY + (
            'جرب:\n'
            '    ارفع خطأ_دفع("س")\n'
            'باستثناء خطأ_دفع كـ:\n'
            '    اطبع("أمسك بلا ربط")\n'
        )
        self.assertEqual(run_code(src), 'أمسك بلا ربط\n')

    def test_base_exception_filter_catches_all_user_errors(self):
        src = HIERARCHY + (
            'جرب:\n'
            '    ارفع خطأ_دفع("س")\n'
            'باستثناء استثناء كـ هـ:\n'
            '    اطبع("مستثناء مخصص")\n'
        )
        self.assertEqual(run_code(src), 'مستثناء مخصص\n')

    def test_builtin_errors_do_not_match_filters(self):
        # الأخطاء المدمجة أخطاء برمجية — الفلاتر لأخطاء الأعمال حصرًا
        src = (
            'جرب:\n'
            '    اطبع(١ / ٠)\n'
            'باستثناء استثناء كـ هـ:\n'
            '    اطبع("لا يجب أن يُمسك")\n'
        )
        expect_error(src, ArabiRuntimeError, 'قسمة على صفر')

    def test_builtin_errors_caught_by_general_clause(self):
        src = HIERARCHY + (
            'جرب:\n'
            '    اطبع(١ / ٠)\n'
            'باستثناء خطأ_دفع كـ هـ:\n'
            '    اطبع("دفع")\n'
            'باستثناء كـ هـ:\n'
            '    اطبع("العام أمسك: " + هـ)\n'
        )
        self.assertEqual(run_code(src), 'العام أمسك: قسمة على صفر\n')

    def test_no_match_reraises_original(self):
        src = HIERARCHY + (
            'جرب:\n'
            '    ارفع خطأ_رصيد("الأصلية")\n'
            'باستثناء استثناء كـ هـ:\n'
            '    اطبع("لا")\n'
        )
        # كل الكتل هنا مطابقة؛ لاختبار إعادة الرفع نستخدم فلترًا لا يطابق
        # ولا كتلة عامة: فلتر خطأ_رصيد على خطأ_دفع الأب؟ الابن يطابق الأب
        # — لذا نرفع الأب وفلتر الابن:
        src = HIERARCHY + (
            'جرب:\n'
            '    ارفع خطأ_دفع("الأصلية")\n'
            'باستثناء خطأ_رصيد كـ هـ:\n'
            '    اطبع("لا يجب")\n'
        )
        exc = expect_error(src, ArabiRuntimeError, 'الأصلية')
        self.assertIn('خطأ', str(exc))

    def test_filter_must_be_class(self):
        src = HIERARCHY + (
            'س = ٥\n'
            'جرب:\n'
            '    ارفع خطأ_دفع("س")\n'
            'باستثناء س كـ هـ:\n'
            '    اطبع("لا")\n'
        )
        expect_error(src, ArabiRuntimeError, 'صنفًا')

    def test_legacy_binding_form_unchanged(self):
        src = HIERARCHY + (
            'جرب:\n'
            '    ارفع خطأ_دفع("قديم")\n'
            'باستثناء هـ:\n'
            '    اطبع(هـ.رسالة)\n'
        )
        self.assertEqual(run_code(src), 'قديم\n')

    def test_legacy_no_binding_form_unchanged(self):
        src = HIERARCHY + (
            'جرب:\n'
            '    ارفع خطأ_دفع("قديم")\n'
            'باستثناء:\n'
            '    اطبع("أمُسك")\n'
        )
        self.assertEqual(run_code(src), 'أمُسك\n')

    def test_multiple_clauses_with_finally_order(self):
        src = HIERARCHY + (
            'جرب:\n'
            '    ارفع خطأ_رصيد("س")\n'
            'باستثناء خطأ_دفع كـ هـ:\n'
            '    اطبع("التقط")\n'
            'اخيرا:\n'
            '    اطبع("وأخيرًا")\n'
        )
        self.assertEqual(run_code(src), 'التقط\nوأخيرًا\n')

    def test_undefined_filter_name_propagates(self):
        # سلوك بايثون نفسها: خطأ تقييم الفلتر يحل محل الأصلي
        src = HIERARCHY + (
            'جرب:\n'
            '    ارفع خطأ_دفع("س")\n'
            'باستثناء صنف_غير_معرف كـ هـ:\n'
            '    اطبع("لا")\n'
        )
        expect_error(src, ArabiRuntimeError, 'صنف_غير_معرف')

    def test_try_requires_except_or_finally(self):
        expect_error('جرب:\n    اطبع(١)', ParseError, 'باستثناء')

    def test_vm_parity(self):
        src = HIERARCHY + (
            'دالة شغل():\n'
            '    جرب:\n'
            '        ارفع خطأ_رصيد("ف")\n'
            '    باستثناء خطأ_دفع كـ هـ:\n'
            '        أعد هـ.رسالة\n'
            'شغل()\n'
        )
        self.assertEqual(last(src), last_vm(src))


# ======================= ق٨: ربط الحلقة المثبت =======================

class TestLoopBinding(unittest.TestCase):
    """دلالة لكل والفهم الموثقة في ٣٫٢ — متوافقة بايثون 3 (تجارب 1.24)."""

    def test_for_loop_late_binding(self):
        src = (
            'الدوال = []\n'
            'لكل س في [١، ٢، ٣]:\n'
            '    الدوال.أضف(دالة() => س)\n'
            'اطبع(الدوال[٠]())\n'
        )
        self.assertEqual(run_code(src), '3\n')

    def test_comprehension_late_binding(self):
        src = (
            'الدوال = [دالة() => س لكل س في [١، ٢، ٣]]\n'
            'اطبع(الدوال[٠]())\n'
        )
        self.assertEqual(run_code(src), '3\n')

    def test_for_loop_mutates_outer_variable(self):
        src = (
            'س = "خارجي"\n'
            'لكل س في [١، ٢، ٣]:\n'
            '    تجاهل\n'
            'اطبع(س)\n'
        )
        self.assertEqual(run_code(src), '3\n')

    def test_comprehension_does_not_leak(self):
        src = (
            'س = "خارجي"\n'
            'ل = [س لكل س في [١، ٢، ٣]]\n'
            'اطبع(س)\n'
        )
        self.assertEqual(run_code(src), 'خارجي\n')

    def test_loop_variable_visible_after_break(self):
        src = (
            'لكل س في [١، ٢، ٣، ٤]:\n'
            '    لو س == ٣:\n'
            '        كسر\n'
            'اطبع(س)\n'
        )
        self.assertEqual(run_code(src), '3\n')

    def test_unpacking_for_binds_both(self):
        src = (
            'مجموع = ٠\n'
            'لكل أ، ب في [[١، ٢]، [٣، ٤]]:\n'
            '    مجموع += أ * ب\n'
            'اطبع(مجموع)\n'
        )
        self.assertEqual(run_code(src), '14\n')

    def test_vm_parity_binding(self):
        src = (
            'الدوال = []\n'
            'لكل س في [١، ٢، ٣]:\n'
            '    الدوال.أضف(دالة() => س)\n'
            'الدوال[٢]()\n'
        )
        self.assertEqual(last(src), last_vm(src))


# ======================= ق٩: المزخرفات مع غير المتزامنة =======================

class TestAsyncDecorators(unittest.TestCase):
    """@ يسبق 'دالة' و'غير متزامنة دالة' على السواء."""

    WRAPPER = (
        'دالة سجل(ف):\n'
        '    دالة داخلية(...الوسائط):\n'
        '        أعد ف(...الوسائط)\n'
        '    أعد داخلية\n'
    )

    def test_decorator_on_async_function(self):
        src = self.WRAPPER + (
            '@سجل\n'
            'غير متزامنة دالة مهمة():\n'
            '    أعد ٤٢\n'
            'ن = مهمة()\n'
            'اطبع(انتظر ن)\n'
        )
        self.assertEqual(run_code(src), '42\n')

    def test_stacked_decorators_on_async(self):
        src = self.WRAPPER + (
            '@سجل\n'
            '@سجل\n'
            'غير متزامنة دالة مهمة():\n'
            '    أعد ٧\n'
            'اطبع(انتظر (مهمة()))\n'
        )
        self.assertEqual(run_code(src), '7\n')

    def test_decorator_on_async_method(self):
        src = self.WRAPPER + (
            'صنف خدمة:\n'
            '    @سجل\n'
            '    غير متزامنة دالة اجلب():\n'
            '        أعد "بيانات"\n'
            'خ = خدمة()\n'
            'اطبع(انتظر خ.اجلب())\n'
        )
        self.assertEqual(run_code(src), 'بيانات\n')

    def test_async_nature_preserved_through_decorator(self):
        # المزخرف يستلم الدالة غير المتزامنة كما هي — الاستدعاء يعيد مهمة
        src = (
            'دالة شفافة(ف):\n'
            '    أعد ف\n'
            '@شفافة\n'
            'غير متزامنة دالة مهمة():\n'
            '    أعد ٩\n'
            'م = مهمة()\n'
            'اطبع(انتظر م)\n'
        )
        self.assertEqual(run_code(src), '9\n')

    def test_decorator_error_message_names_both_forms(self):
        exc = expect_error(
            '@سجل\nاطبع(١)', ParseError, 'غير متزامنة')
        self.assertIn('@', str(exc))

    def test_plain_functions_still_decorated(self):
        src = self.WRAPPER + (
            '@سجل\n'
            'دالة جمع(أ، ب):\n'
            '    أعد أ + ب\n'
            'اطبع(جمع(٢، ٣))\n'
        )
        self.assertEqual(run_code(src), '5\n')


# ======================= ق١٠: الرسائل الدقيقة =======================

class TestImprovedMessages(unittest.TestCase):
    """الصيغ المرفوضة تعطي رسالة تسمي المشكلة وتقترح البديل."""

    def test_chained_comparison_named(self):
        exc = expect_error('اطبع(١ < ٢ < ٣)', ParseError,
                           'المقارنات المتسلسلة')
        self.assertIn('و', str(exc))          # يقترح الدمج بـ«و»
        self.assertEqual(exc.line, 1)

    def test_chained_membership_also_named(self):
        expect_error('اطبع(١ في [١] في [[١]])', ParseError,
                     'المقارنات المتسلسلة')

    def test_chained_assignment_named(self):
        exc = expect_error('أ = ب = ٣', ParseError, 'الإسناد المتسلسل')
        self.assertIn('جملة مستقلة', str(exc))
        self.assertEqual(exc.line, 1)

    def test_chained_comparison_not_triggered_by_conjunction(self):
        # الشرطية المدمجة بـ«و» مشروعة تمامًا — لا إنذار كاذب
        self.assertEqual(run_code('اطبع(١ < ٢ و ٢ < ٣)'), 'صح\n')

    def test_normal_comparison_unaffected(self):
        self.assertEqual(run_code('اطبع(١ < ٢)'), 'صح\n')
        self.assertEqual(run_code('اطبع(٣ >= ٣)'), 'صح\n')
        self.assertEqual(run_code('اطبع(٥ ليس في [١، ٢])'), 'صح\n')


if __name__ == '__main__':
    unittest.main(verbosity=2)
