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

المرحلة 3 (الإصدار 1.25.0) — الفصل ٥ من المواصفة:
  ق١١ عقد بروتوكول التكرار (رفض المولد)   → TestIterationProtocol
  ق١٢ توحيد الانتظار الخلفي              → TestUnifiedAwait
  ٥٫٢ كسل التكرار على المدى والنص         → TestLazyRange
  ٥٫٤ كاش ترجمة الدولاب                  → TestVmCodeCache
  ٣٫٥ القسمة النظيفة (اختبار التدقيق)     → TestCleanDivision
  تدقيق ف9 تكافؤ الصحة عبر المسارين       → TestTruthyParityAcrossPaths
  تدقيق ف6 لا تسريب تمثيل خام            → TestSpecialValueDisplay

المرحلة 4 (الإصدار 1.26.0) — الفصل ٦ من المواصفة:
  ق١٣–ق١٦ نظام الأنواع التدريجي           → TestTypeSystem
  إصلاح كاش الترجمة (هوية الجسم)          → TestVmCacheIdentity
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


# ======================= ق١١: عقد بروتوكول التكرار =======================

_GEN_CLASS = '''صنف باب:
    دالة تالٍ():
        أنتج ١
        أنتج ٢

'''

_COUNTER_CLASS = '''صنف عدّاد:
    دالة إنشاء():
        هذا.ن = ٠

    دالة تالٍ():
        هذا.ن = هذا.ن + ١
        لو هذا.ن <= ٣:
            أعد هذا.ن
        وإلا:
            أعد ولا شيء

'''


class TestIterationProtocol(unittest.TestCase):
    """ق١١ — تالٍ تعيد قيمة واحدة أو لا شيء؛ المولد مرفوض برسالة موجِّهة.

    قبل 1.25 كانت الحلقة تدور بلا نهاية بصمت (مسبر حي: تعليق > 6 ثوانٍ
    بلا أي مخرجات) — أسوأ نمط فشل لمستخدم مبتدئ.
    """

    def test_next_as_generator_rejected_in_for(self):
        expect_error(_GEN_CLASS + 'لكل س في باب():\n    اطبع(س)\n',
                     ArabiRuntimeError, 'أعادت مولدًا')

    def test_next_as_generator_rejected_in_for_inside_function(self):
        # مسار الدولاب: OP_FOR_SETUP يسلم الكائن للممسح داخل جسم دالة
        # (لا تسمّ الدالة «جرّب» — شدّتها تُمحى فتصير كلمة جرب المحجوزة)
        expect_error(_GEN_CLASS + '''دالة اختبار():
    لكل س في باب():
        اطبع(س)

اختبار()
''', ArabiRuntimeError, 'أعادت مولدًا')

    def test_next_as_generator_rejected_in_membership(self):
        expect_error(_GEN_CLASS + 'اطبع(٥ في باب())',
                     ArabiRuntimeError, 'أعادت مولدًا')

    def test_next_as_generator_rejected_in_spread(self):
        # مسار التفكيك (...) يمشي على البروتوكول نفسه — نفس الحرس
        expect_error(_GEN_CLASS + '''دالة اجمع(...ق):
    أعد طول(ق)

اطبع(اجمع(...باب()))
''', ArabiRuntimeError, 'أعادت مولدًا')

    def test_guard_also_in_tree_mode(self):
        tree = Parser(Lexer(
            _GEN_CLASS + 'لكل س في باب():\n    اطبع(س)\n').tokenize()).parse()
        interp = Interpreter(use_vm=False)
        with self.assertRaises(ArabiRuntimeError) as ctx:
            interp.run(tree)
        self.assertIn('أعادت مولدًا', str(ctx.exception))

    def test_valid_protocol_still_iterates_for(self):
        self.assertEqual(
            run_code(_COUNTER_CLASS + 'لكل س في عدّاد():\n    اطبع(س)\n'),
            '1\n2\n3\n')

    def test_valid_protocol_still_iterates_membership(self):
        self.assertEqual(
            run_code(_COUNTER_CLASS + 'اطبع(٢ في عدّاد())\n'), 'صح\n')

    def test_valid_protocol_with_first_returns_iterator(self):
        src = '''صنف دفتر:
    دالة إنشاء():
        هذا.فهرس = ٠

    دالة أول():
        أعد هذا

    دالة تالٍ():
        هذا.فهرس = هذا.فهرس + ١
        لو هذا.فهرس <= ٢:
            أعد هذا.فهرس * ١٠
        وإلا:
            أعد ولا شيء

لكل قيمة في دفتر():
    اطبع(قيمة)
'''
        self.assertEqual(run_code(src), '10\n20\n')


# ======================= ق١٢: توحيد الانتظار الخلفي =======================

class TestUnifiedAwait(unittest.TestCase):
    """ق١٢ — انتظر_الجميع/سباق تقبل الخيوط والعمليات كالمهام (واجهة واحدة)."""

    def test_wait_all_accepts_threads_in_order(self):
        src = '''استورد خيوط

دالة مهمة(ن):
    أعد ن * ٢

خ١ = خيوط.شغّل(مهمة، ٢١)
خ٢ = خيوط.شغّل(مهمة، ٥٠)
اطبع(انتظر_الجميع([خ١، خ٢]))
'''
        self.assertEqual(run_code(src), '[42، 100]\n')

    def test_wait_all_accepts_process(self):
        src = '''استورد عمليات

دالة مربع(ن):
    أعد ن * ن

ع = عمليات.شغّل(مربع، ٧)
اطبع(انتظر_الجميع([ع]))
'''
        self.assertEqual(run_code(src), '[49]\n')

    def test_race_accepts_threads(self):
        src = '''استورد خيوط

دالة أ():
    أعد ١

دالة ب():
    أعد ٢

ن = انتظر سباق([خيوط.شغّل(أ)، خيوط.شغّل(ب)])
اطبع(ن == ١ أو ن == ٢)
'''
        self.assertEqual(run_code(src), 'صح\n')

    def test_thread_error_propagates_through_wait_all(self):
        src = '''استورد خيوط

دالة منهارة():
    ارفع("انفجرت")

خ = خيوط.شغّل(منهارة)
انتظر_الجميع([خ])
'''
        expect_error(src, ArabiRuntimeError, 'انفجرت')

    def test_reject_message_lists_all_sources(self):
        expect_error('انتظر_الجميع([٥])', ArabiRuntimeError, 'خيوط.شغّل')


# ======================= ٥٫٢: كسل التكرار =======================

class TestLazyRange(unittest.TestCase):
    """٥٫٢ — لكل على مدى/نص بكسل في المسارين، ولقطة القوائم/المفاتيح مثبتة.

    مسبر التدقيق P4: التمويد كان يستهلك قمة تخصيص ~80MB لمدى ٢ مليون.
    """

    def test_range_sum_inside_function_vm_path(self):
        src = '''دالة مجموع_حتى(ن):
    مجموع = ٠
    لكل س في مدى(ن):
        مجموع += س
    أعد مجموع

اطبع(مجموع_حتى(٢٠٠٠٠٠))
'''
        self.assertEqual(run_code(src), '19999900000\n')

    def test_range_with_step_top_level_tree_path(self):
        src = '''نصي = ""
لكل س في مدى(٠، ١٠، ٣):
    نصي += نص(س) + "،"
اطبع(نصي)
'''
        self.assertEqual(run_code(src), '0،3،6،9،\n')

    def test_string_chars_iteration(self):
        src = '''دالة إحصاء(مدخل):
    عدد = ٠
    لكل حرف في مدخل:
        عدد += ١
    أعد عدد

اطبع(إحصاء("سلام عليكم"))
'''
        self.assertEqual(run_code(src), '10\n')

    def _peak_mb(self, src, use_vm):
        import tracemalloc
        tree = Parser(Lexer(src).tokenize()).parse()
        tracemalloc.start()
        try:
            Interpreter(use_vm=use_vm).run(tree)
        finally:
            _cur, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        return peak

    def test_big_range_memory_is_constant_tree(self):
        peak = self._peak_mb('لكل س في مدى(٥٠٠٠٠٠):\n    ص = س\n', False)
        self.assertLess(peak, 8 * 1024 * 1024,
                        f'قمة التخصيص {peak / 1e6:.1f}MB — التمويد عاد؟')

    def test_big_range_memory_is_constant_vm(self):
        peak = self._peak_mb(
            'دالة ف():\n    لكل س في مدى(٥٠٠٠٠٠):\n        ص = س\n\nف()\n',
            True)
        self.assertLess(peak, 8 * 1024 * 1024,
                        f'قمة التخصيص {peak / 1e6:.1f}MB — التمويد عاد؟')

    def test_list_snapshot_during_iteration(self):
        # دلالة مثبتة (٥٫٢): القائمة تُلتقط عند دخول الحلقة — التعديل
        # أثناء الحلقة لا يمددها (لو كانت حية لدارت الاختبار للأبد)
        src = '''ل = [١، ٢، ٣]
عدد = ٠
لكل س في ل:
    ل.أضف(س)
    عدد += ١

اطبع(عدد)
'''
        self.assertEqual(run_code(src), '3\n')

    def test_dict_keys_snapshot_during_iteration(self):
        src = '''ق = {"أ": ١، "ب": ٢}
عدد = ٠
لكل مفتاح في ق:
    ق["ج"] = ٣
    عدد += ١

اطبع(عدد)
'''
        self.assertEqual(run_code(src), '2\n')


# ======================= ٣٫٥: القسمة النظيفة (اختبار التدقيق) =======================

class TestCleanDivision(unittest.TestCase):
    """٣٫٥ — `/` بين صحيحين يقسمان يساويًا تعطي صحيحًا؛ وإلا عشري.

    التدقيق (الفصل 7-2): القرار حساس وموثق في المواصفة لكنه بلا
    اختبار مواصفة يثبته — هذا هو الاختبار المطلوب.
    """

    def test_clean_division_values_both_modes(self):
        for helper in (last, last_vm):
            self.assertEqual(helper('٤ / ٢'), 2)
            self.assertEqual(helper('-٤ / ٢'), -2)
            self.assertEqual(helper('٠ / ٥'), 0)
            self.assertEqual(helper('٥ / ٢'), 2.5)
            self.assertEqual(helper('٧ / ٢'), 3.5)

    def test_clean_division_types_both_modes(self):
        for helper in (last, last_vm):
            self.assertEqual(helper('نوع(٤ / ٢)'), 'عدد صحيح')
            self.assertEqual(helper('نوع(٥ / ٢)'), 'عدد عشري')

    def test_zero_division_error(self):
        expect_error('١ / ٠', ArabiRuntimeError, 'قسمة على صفر')


# ======================= تدقيق ف9: تكافؤ الصحة عبر المسارين =======================

class TestTruthyParityAcrossPaths(unittest.TestCase):
    """الفصل 9 (بند 1) — لو/و/أو/الثلاثي متطابقة شجريًا ودولابيًا على
    القيم الحدية كلها. OP_JIF صار عبر _truthy في 1.24 — هذا الاختبار
    يثبت التكافؤ دائمًا فلا تنحرف دلالة الدولاب مستقبلًا.
    """

    EDGE = ['٠', '١', '""', '[]', '{}', '[٠]', 'خطأ', 'صح', 'ولا شيء',
            '٠٫٠', '"صفر"', '٠٫٠٠١']

    BRANCH = '''دالة ف(س):
    لو س:
        أعد "نعم"
    وإلا:
        أعد "لا"

اطبع(ف(%s))
'''

    def _run(self, src, use_vm):
        out = io.StringIO()
        with redirect_stdout(out):
            tree = Parser(Lexer(src).tokenize()).parse()
            Interpreter(use_vm=use_vm).run(tree)
        return out.getvalue()

    def test_if_statement_parity(self):
        for value in self.EDGE:
            self.assertEqual(
                self._run(self.BRANCH % value, True),
                self._run(self.BRANCH % value, False),
                msg=f'انحراف لو بين المسارين على القيمة {value}')

    def test_logical_and_or_parity(self):
        for value in self.EDGE:
            for expr in (f'{value} و ٤٢', f'{value} أو ٤٢',
                         f'٤٢ و {value}', f'٤٢ أو {value}'):
                self.assertEqual(
                    self._run('اطبع(' + expr + ')', True),
                    self._run('اطبع(' + expr + ')', False),
                    msg=f'انحراف منطق بين المسارين على: {expr}')

    def test_ternary_parity(self):
        for value in self.EDGE:
            expr = f'لو {value}: "أ" وإلا "ب"'
            self.assertEqual(
                self._run('اطبع(' + expr + ')', True),
                self._run('اطبع(' + expr + ')', False),
                msg=f'انحراف الثلاثي بين المسارين على القيمة {value}')


# ======================= تدقيق ف6: لا تسريب تمثيل خام =======================

class TestSpecialValueDisplay(unittest.TestCase):
    """الفصل 6/9 — كل قيمة تُعرض عربيًا؛ لا <arabi_lang.runtime.X object>."""

    def test_property_display_not_raw(self):
        out = run_code('''صنف دائرة:
    خاصية المساحة:
        أعِد ٧

اطبع(دائرة.المساحة)
''')
        self.assertIn('<خاصية المساحة>', out)
        self.assertNotIn('arabi_lang.runtime', out)

    def test_property_via_instance_still_computes(self):
        out = run_code('''صنف دائرة:
    خاصية المساحة:
        أعِد ٧

ك = دائرة()
اطبع(ك.المساحة)
''')
        self.assertEqual(out, '7\n')

    def test_property_typename(self):
        src = '''صنف دائرة:
    خاصية المساحة:
        أعِد ٧

'''
        for helper in (last, last_vm):
            self.assertEqual(helper(src + 'نوع(دائرة.المساحة)'), 'خاصية')

    def test_native_ctor_display(self):
        out = run_code('اطبع(استثناء.إنشاء)')
        self.assertIn('<منشئ أصلي إنشاء>', out)
        self.assertNotIn('arabi_lang.runtime', out)


# ======================= ٥٫٤: كاش ترجمة الدولاب =======================

class TestVmCodeCache(unittest.TestCase):
    """٥٫٤ — الدالة المعرفة داخل حلقة ساخنة تُترجم مرة واحدة (كاش على
    عقدة AST) ويبقى سلوك الإغلاق والتعاود مطابقًا.
    """

    def test_funcdef_in_hot_loop_correct_results(self):
        src = '''دالة خارجية():
    مجموع = ٠
    لكل س في مدى(٥٠):
        دالة داخلية(ن):
            أعد ن + س
        مجموع += داخلية(س)
    أعد مجموع

اطبع(خارجية())
'''
        self.assertEqual(run_code(src), '2450\n')

    def test_closures_still_capture_own_env(self):
        src = '''دالة مصنع(ن):
    دالة داخل(س):
        أعد س + ن
    أعد داخل

د١ = مصنع(١٠)
د٢ = مصنع(٢٠)
اطبع(د١(٥))
اطبع(د٢(٥))
'''
        self.assertEqual(run_code(src), '15\n25\n')

    def test_recursion_unaffected_by_cache(self):
        src = '''دالة فيبو(ن):
    لو ن < ٢:
        أعد ن
    أعد فيبو(ن - ١) + فيبو(ن - ٢)

اطبع(فيبو(١٥))
'''
        self.assertEqual(run_code(src), '610\n')

    def test_cache_key_is_node_not_instance(self):
        # عقدتان مختلفتان بنفس النص = كودان مستقلان؛ وعقدة واحدة تُترجم مرة
        src = '''دالة أ():
    دالة داخلية():
        أعد ١
    أعد داخلية

دالة ب():
    دالة داخلية():
        أعد ٢
    أعد داخلية

اطبع(أ()())
اطبع(ب()())
'''
        self.assertEqual(run_code(src), '1\n2\n')




# ======================= المرحلة 4 (1.26.0) — نظام الأنواع =======================

class TestTypeSystem(unittest.TestCase):
    """نظام الأنواع التدريجي — الفصل ٦ من المواصفة والقرارات ق١٣–ق١٦.

    ق١٣ توصيف اختياري يفحص وقت التشغيل؛ العائلات تحسم فورًا في موضع
    التوصيف (أسماؤها محجوزة أصلًا بدوال التحويل) والأصناف من نطاق التعريف.
    ق١٤ التعمية لقائمة/قاموس بمستوى واحد. ق١٥ عقد الإرجاع كل المسارات.
    ق١٦ الأصناف والواجهات أنواع بعقد سلسلة الوراثة (MRO).
    """

    # ---------- ق١٣: العائلات المدمجة ----------

    def test_number_param_ok(self):
        self.assertEqual(last('دالة جمع(س: عدد، ص: عدد):\n    أعد س + ص\nجمع(٣، ٤)'), 7)

    def test_number_rejects_string(self):
        expect_error('دالة جمع(س: عدد):\n    أعد س\nجمع("خمسة")',
                     ArabiRuntimeError, "يتوقع 'عدد'")

    def test_bool_is_not_number(self):
        # ق١٥: المنطقي لا يُعد عددًا أبدًا (عكس isinstance في بايثون)
        expect_error('دالة فحص(س: عدد):\n    أعد س\nفحص(صح)',
                     ArabiRuntimeError, 'قيمة منطقية')
        expect_error('دالة فحص(س: عدد):\n    أعد س\nفحص(خطأ)',
                     ArabiRuntimeError, 'قيمة منطقية')

    def test_numeric_tower_decimal_accepts_int(self):
        # ق١٥: «عشري» يقبل الصحيح (برج عددي بأسلوب PEP 484)
        self.assertEqual(last('دالة نصف(س: عشري):\n    أعد س / ٢\nنصف(٥)'), 2.5)

    def test_int_rejects_float(self):
        expect_error('دالة فحص(س: صحيح):\n    أعد س\nفحص(١.٥)',
                     ArabiRuntimeError, 'عدد عشري')

    def test_string_bool_list_dict_range_families(self):
        self.assertEqual(last('دالة بو(ن: نص):\n    أعد طول(ن)\nبو("أب")'), 2)
        self.assertEqual(last('دالة بو(م: منطقي):\n    أعد م\nبو(صح)'), True)
        self.assertEqual(last('دالة بو(ل: قائمة):\n    أعد طول(ل)\nبو([١، ٢])'), 2)
        self.assertEqual(last('دالة بو(د: قاموس):\n    أعد طول(د)\nبو({"أ": ١})'), 1)
        self.assertEqual(last('دالة بو(م: مدى):\n    أعد طول(م)\nبو(مدى(٣))'), 3)

    def test_any_accepts_all(self):
        for v in ('٥', '"نص"', 'صح', 'ولا شيء', '[١]', '{"أ": ١}'):
            self.assertIsNone(last(f'دالة بو(س: أي):\n    تجاهل\nبو({v})'))

    def test_none_family(self):
        self.assertIsNone(last('دالة بو(س: عدم):\n    تجاهل\nبو(ولا شيء)'))
        expect_error('دالة بو(س: عدم):\n    تجاهل\nبو(١)',
                     ArabiRuntimeError, 'عدد صحيح')

    def test_function_family(self):
        self.assertEqual(
            last('دالة طبّق(د: دالة، س: عدد):\n    أعد د(س)\n'
                 'طبّق(دالة(ن) => ن + ١، ٤)'), 5)
        expect_error('دالة طبّق(د: دالة):\n    أعد د\nطبّق(٥)',
                     ArabiRuntimeError, 'ورد عدد صحيح')

    def test_tashkeel_in_family_name(self):
        # ق٢: التشكيل يُمحى من أسماء العائلات كالمعرفات
        self.assertEqual(last('دالة بو(س: عَدَد):\n    أعد س\nبو(٧)'), 7)

    def test_literal_none_and_def_as_type(self):
        self.assertIsNone(last('دالة صامت() -> ولا شيء:\n    تجاهل\nصامت()'))
        self.assertEqual(
            last('دالة طبّق(د: دالة):\n    أعد د(٥)\nطبّق(دالة(ن) => ن)'), 5)

    # ---------- ق١٣: الحسم عند أول استدعاء والأخطاء ----------

    def test_unknown_type_name(self):
        exc = expect_error('دالة بو(س: غير_موجود):\n    أعد ٠\nبو(١)',
                           ArabiRuntimeError, 'غير معروف')
        self.assertIn('بو', str(exc))

    def test_non_type_binding_rejected(self):
        expect_error('س = ٥\nدالة بو(ن: س):\n    أعد ٠\nبو(١)',
                     ArabiRuntimeError, 'ليس نوعًا')

    def test_family_wins_over_user_class(self):
        # اكتشاف المسبار: أسماء العائلات محجوزة بدوال التحويل المدمجة،
        # فالعائلة تحسم فورًا في موضع التوصيف (ق١٣)
        src = '''صنف عدد:
    تجاهل

دالة بو(س: عدد):
    أعد س

اطبع(بو(٥))
'''
        self.assertEqual(run_code(src), '5\n')
        expect_error('صنف عدد:\n    تجاهل\n'
                     'دالة بو(س: عدد):\n    أعد س\nبو(عدد())',
                     ArabiRuntimeError, 'ورد كائن')

    def test_resolution_frozen_after_first_call(self):
        # ق١٣: الحسم عند أول استدعاء ويُجمّد — إعادة تعريف الصنف تصنع
        # هوية ClassValue جديدة يرفضها العقد المجمد على القديمة
        ok = '''صنف حيوان:
    تجاهل

دالة صوت(ح: حيوان):
    أعد "تم"

اطبع(صوت(حيوان()))
'''
        self.assertEqual(run_code(ok), 'تم\n')
        frozen = ok + '''صنف حيوان:
    تجاهل

صوت(حيوان())
'''
        expect_error(frozen, ArabiRuntimeError,
                     "والمطلوب كائن من صنف 'حيوان'")

    # ---------- ق١٣: مواضع الفحص ----------

    def test_kwargs_checked(self):
        expect_error('دالة بو(س: نص):\n    أعد س\nبو(س=٥)',
                     ArabiRuntimeError, "يتوقع 'نص'")

    def test_default_violation_checked_at_call(self):
        expect_error('دالة بو(س: عدد = "خمسة"):\n    أعد س\nبو()',
                     ArabiRuntimeError, "يتوقع 'عدد'")

    def test_rest_annotation(self):
        self.assertEqual(
            last('دالة بو(...الوسائط: قائمة[عدد]):\n    أعد طول(الوسائط)\nبو(١، ٢، ٣)'), 3)
        expect_error('دالة بو(...الوسائط: قائمة[عدد]):\n    أعد ٠\nبو(١، "اثنان")',
                     ArabiRuntimeError, 'العنصر رقم')

    def test_async_param_checked_before_thread(self):
        expect_error('غير متزامنة دالة شغل(س: نص):\n    أعد س\nشغل(٥)',
                     ArabiRuntimeError, "يتوقع 'نص'")

    def test_class_method_annotations(self):
        src = '''صنف حساب:
    الرقم = ١٠
    دالة جمع(س: عدد):
        أعد هذا.الرقم + س

ح = حساب()
اطبع(ح.جمع(٤))
'''
        self.assertEqual(run_code(src), '14\n')
        expect_error('صنف حساب:\n    دالة جمع(س: عدد):\n        أعد س\n'
                     'ح = حساب()\nح.جمع("أربعة")',
                     ArabiRuntimeError, "يتوقع 'عدد'")

    def test_lambda_param_annotations(self):
        self.assertEqual(last('ض = دالة(س: عدد) => س * ٢\nض(٥)'), 10)
        expect_error('ض = دالة(س: عدد) => س * ٢\nض("خمسة")',
                     ArabiRuntimeError, "يتوقع 'عدد'")

    # ---------- ق١٥: عقد الإرجاع ----------

    def test_return_ok_and_violation(self):
        self.assertEqual(last('دالة اسمي() -> نص:\n    أعد "سالم"\nاسمي()'), 'سالم')
        expect_error('دالة اسمي() -> نص:\n    أعد ٥\nاسمي()',
                     ArabiRuntimeError, "تعلن إرجاع 'نص'")

    def test_return_arrow_unicode_and_ascii(self):
        self.assertEqual(last('دالة ضعف(س: عدد) → عدد:\n    أعد س * ٢\nضعف(٥)'), 10)
        self.assertEqual(last('دالة ضعف(س: عدد) -> عدد:\n    أعد س * ٢\nضعف(٥)'), 10)

    def test_implicit_fallthrough_violation(self):
        # السقوط الضمني يعيد ولا شيء — يخالف عقد عدد
        expect_error('دالة وض() -> عدد:\n    لو خطأ:\n        أعد ١\nوض()',
                     ArabiRuntimeError, 'تعلن إرجاع')

    def test_none_contract(self):
        self.assertIsNone(last('دالة صامت() -> ولا شيء:\n    تجاهل\nصامت()'))
        expect_error('دالة صامت() -> ولا شيء:\n    أعد ٥\nصامت()',
                     ArabiRuntimeError, 'ورد عدد صحيح')

    def test_generator_rejects_return_annotation(self):
        expect_error('دالة مولّد() -> عدد:\n    أنتج ١',
                     ParseError, 'المولد')
        expect_error('دالة مولّد() → عدد:\n    أنتج ١',
                     ParseError, 'المولد')

    def test_arrow_function_rejects_return_type(self):
        expect_error('ض = دالة(س: عدد) -> عدد => س',
                     ParseError, 'لا تقبل نوع إرجاع')

    def test_return_checked_in_both_paths(self):
        # تكافؤ المسارين: الممسح الشجري والدولاب
        for run in (last, last_vm):
            self.assertEqual(run('دالة اسمي() -> نص:\n    أعد "تم"\nاسمي()'), 'تم')
            with self.assertRaises(ArabiRuntimeError):
                run('دالة اسمي() -> نص:\n    أعد ٥\nاسمي()')

    # ---------- ق١٤: التعمية ----------

    def test_list_generic_ok_and_element_index(self):
        self.assertEqual(
            last('دالة مجموع(ل: قائمة[عدد]):\n    أعد ل[٠] + ل[١]\nمجموع([١، ٢، ٣])'), 3)
        exc = expect_error('دالة مجموع(ل: قائمة[عدد]):\n    أعد ٠\nمجموع([١، "اثنان"])',
                           ArabiRuntimeError, 'العنصر رقم 2')
        self.assertIn('قائمة[عدد]', str(exc))

    def test_dict_generic_keys_and_values(self):
        self.assertEqual(
            last('دالة بو(د: قاموس[نص: عدد]):\n    أعد د["أ"]\nبو({"أ": ١})'), 1)
        expect_error('دالة بو(د: قاموس[نص: عدد]):\n    أعد ٠\nبو({١: ١})',
                     ArabiRuntimeError, 'المفتاح 1')
        expect_error('دالة بو(د: قاموس[نص: عدد]):\n    أعد ٠\nبو({"أ": "واحد"})',
                     ArabiRuntimeError, 'قيمة المفتاح')

    def test_empty_containers_pass(self):
        self.assertEqual(last('دالة بو(ل: قائمة[عدد]):\n    أعد طول(ل)\nبو([])'), 0)
        self.assertEqual(last('دالة بو(د: قاموس[نص: عدد]):\n    أعد طول(د)\nبو({})'), 0)

    def test_nested_generic_rejected_at_parse(self):
        expect_error('دالة بو(ل: قائمة[قاموس[نص: عدد]]):\n    أعد ٠',
                     ParseError, 'التعمية المتداخلة')

    def test_parameterizing_other_families_rejected(self):
        expect_error('دالة بو(س: عدد[نص]):\n    أعد ٠',
                     ParseError, 'فقط')
        expect_error('دالة بو(س: نص[نص]):\n    أعد ٠',
                     ParseError, 'فقط')

    def test_generic_checked_in_both_paths(self):
        for run in (last, last_vm):
            self.assertEqual(run('دالة مجموع(ل: قائمة[عدد]):\n    أعد ل[٠]\nمجموع([٩])'), 9)
            with self.assertRaises(ArabiRuntimeError):
                run('دالة مجموع(ل: قائمة[عدد]):\n    أعد ل[٠]\nمجموع(["٩"])')

    # ---------- ق١٦: الأصناف والواجهات ----------

    def test_class_type_substitution_lsp(self):
        src = '''صنف حيوان:
    تجاهل

صنف كلب من حيوان:
    تجاهل

دالة صوت(ح: حيوان):
    أعد "صوت"

اطبع(صوت(كلب()))
'''
        self.assertEqual(run_code(src), 'صوت\n')

    def test_class_type_rejects_unrelated(self):
        expect_error('صنف حيوان:\n    تجاهل\nصنف قط:\n    تجاهل\n'
                     'دالة صوت(ح: حيوان):\n    أعد ٠\nصوت(قط())',
                     ArabiRuntimeError, 'والمطلوب كائن من صنف')

    def test_interface_type_conformance(self):
        src = '''واجهة طائر:
    دالة غرد()

صنف عصفور من طائر:
    دالة غرد():
        أعد "زقزقة"

دالة اسمع(ط: طائر):
    أعد ط.غرد()

اطبع(اسمع(عصفور()))
'''
        self.assertEqual(run_code(src), 'زقزقة\n')

    def test_class_annotation_rejects_non_instance(self):
        expect_error('صنف حيوان:\n    تجاهل\n'
                     'دالة صوت(ح: حيوان):\n    أعد ٠\nصوت(٥)',
                     ArabiRuntimeError, 'والمطلوب كائن من صنف')

    def test_generic_on_user_class_rejected_at_parse(self):
        # التعمية نحويًا لقائمة/قاموس فقط — قبل أي حسم وقت تشغيل
        expect_error('صنف صندوق:\n    تجاهل\n'
                     'دالة بو(س: صندوق[عدد]):\n    أعد ٠',
                     ParseError, 'غير مدعومة')

    def test_type_error_line_is_call_site(self):
        exc = expect_error('دالة بو(س: عدد):\n    أعد س\nبو("خمسة")',
                           ArabiRuntimeError, "يتوقع 'عدد'")
        self.assertIn('السطر 3', str(exc))


class TestVmCacheIdentity(unittest.TestCase):
    """انحدار إصلاح 1.26: كاش ترجمة الدولاب كان بمفتاح id(الجسم) بلا
    مرجع قوي — إعادة تعريف دالة قد تعيد استخدام العنوان فتُنفَّذ ترجمة
    دالة أخرى. القيمة الآن (الجسم، الكود) تحبس الجسم حيًّا.
    """

    def test_redefinition_runs_new_body(self):
        src = '''س = ٠
لكل ن في مدى(٢٠٠):
    لو ن ٪ ٢ == ٠:
        دالة بو():
            أعد ١
    وإلا:
        دالة بو():
            أعد ٢
    س += بو()
س
'''
        self.assertEqual(last(src), 300)
        self.assertEqual(last_vm(src), 300)

    def test_redefinition_different_shapes(self):
        src = '''دالة بو():
    أعد ١

اطبع(بو())

دالة بو():
    أعد "نص مختلف تمامًا في الطول"

اطبع(بو())
'''
        self.assertEqual(run_code(src), '1\nنص مختلف تمامًا في الطول\n')


if __name__ == '__main__':
    unittest.main(verbosity=2)
