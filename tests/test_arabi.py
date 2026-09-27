# -*- coding: utf-8 -*-
"""اختبارات لغة عربي الشاملة."""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from arabi import run_code                                  # noqa: E402
from arabi_lang.lexer import Lexer                           # noqa: E402
from arabi_lang.tokens import T                              # noqa: E402
from arabi_lang.parser import Parser                         # noqa: E402
from arabi_lang.tools import (                                # noqa: E402
    format_source, lint_source, generate_docs, install_package, list_packages,
)
from arabi_lang.errors import (                              # noqa: E402
    ArabiError, ArabiRuntimeError, ParseError, LexerError,
)


def run_arabi(source):
    return run_code(source)


def expect_error(source, error_type, keyword=None):
    try:
        run_code(source)
    except error_type as exc:
        if keyword is not None:
            assert keyword in str(exc), (
                f"الرسالة '{exc}' لا تحتوي على '{keyword}'")
        return exc
    raise AssertionError(f"لم يُطلع الخطأ المتوقع {error_type.__name__}")


class TestLexer(unittest.TestCase):

    def test_tokens_basics(self):
        from arabi_lang.lexer import Lexer
        from arabi_lang.tokens import T
        toks = Lexer('اطبع(١+٢.٥)').tokenize()
        types = [t.type for t in toks]
        self.assertEqual(
            types,
            [T.IDENT, T.LPAREN, T.INT, T.PLUS, T.FLOAT, T.RPAREN,
             T.NEWLINE, T.EOF])
        self.assertEqual(toks[2].value, 1)
        self.assertEqual(toks[4].value, 2.5)

    def test_arabic_comma(self):
        from arabi_lang.lexer import Lexer
        from arabi_lang.tokens import T
        toks = Lexer('أ، ب').tokenize()
        self.assertEqual(toks[1].type, T.COMMA)

    def test_compound_keywords(self):
        from arabi_lang.lexer import Lexer
        from arabi_lang.tokens import T
        toks = Lexer('وإلا إذا\nولا شيء').tokenize()
        self.assertEqual(toks[0].type, T.ELIF)
        self.assertEqual(toks[1].type, T.NEWLINE)
        self.assertEqual(toks[2].type, T.NONE)

    def test_string_escapes(self):
        self.assertEqual(run_arabi(r'اطبع("س\u0640طر")'), 'سـطر\n')

    def test_unterminated_string(self):
        expect_error('أ = "غير مغلق', LexerError, 'نص غير مغلق')

    def test_unknown_symbol(self):
        # @ أصبح عامل المزخرفات منذ الإصدار 1.7 — نستخدم رمزًا غير معروف فعلاً
        expect_error('أ = ٣ & ٤', LexerError, 'رمز غير معروف')

    def test_inconsistent_indent(self):
        src = 'لو صح:\n    أ = ١\n   ب = ٢\n'
        expect_error(src, LexerError, 'مسافة بادئة غير متسقة')

    def test_unbalanced_bracket(self):
        expect_error('أ = (١ + ٢\n', LexerError, 'بقي مفتوحًا')


class TestNumbers(unittest.TestCase):

    def test_arabic_digits(self):
        self.assertEqual(run_arabi('اطبع(٢ + ٣)'), '5\n')

    def test_precedence(self):
        self.assertEqual(run_arabi('اطبع(٢ + ٣ * ٤)'), '14\n')
        self.assertEqual(run_arabi('اطبع((٢ + ٣) * ٤)'), '20\n')

    def test_power_right_assoc(self):
        self.assertEqual(run_arabi('اطبع(٢ ** ٣ ** ٢)'), '512\n')
        self.assertEqual(run_arabi('اطبع(-٢ ** ٢)'), '-4\n')

    def test_division(self):
        self.assertEqual(run_arabi('اطبع(١٠ / ٢)'), '5\n')
        self.assertEqual(run_arabi('اطبع(٧ / ٢)'), '3.5\n')

    def test_modulo_and_negative(self):
        self.assertEqual(run_arabi('اطبع(١٠ % ٣)'), '1\n')
        self.assertEqual(run_arabi('اطبع(-٥ + ٢)'), '-3\n')

    def test_division_by_zero(self):
        expect_error('اطبع(١ / ٠)', ArabiRuntimeError, 'قسمة على صفر')
        expect_error('اطبع(٥ % ٠)', ArabiRuntimeError, 'قسمة على صفر')

    def test_string_number_concat_error(self):
        expect_error('اطبع("عدد: " + ٥)', ArabiRuntimeError, 'نص()')


class TestStrings(unittest.TestCase):

    def test_concat(self):
        self.assertEqual(run_arabi('اطبع("مرحبا" + " " + "بالعالم")'),
                         'مرحبا بالعالم\n')

    def test_repeat(self):
        self.assertEqual(run_arabi('اطبع("أب" * ٣)'), 'أبأبأب\n')

    def test_index_and_slice(self):
        self.assertEqual(run_arabi('اطبع("مرحبا"[٠])'), 'م\n')
        self.assertEqual(run_arabi('اطبع("مرحبا"[١:٤])'), 'رحب\n')

    def test_methods(self):
        self.assertEqual(run_arabi('اطبع("hello".كبير())'), 'HELLO\n')
        self.assertEqual(run_arabi('اطبع("أ ب ج".قسّم(" "))'),
                         '[أ، ب، ج]\n')
        self.assertEqual(run_arabi('اطبع("2024".يبدأ_بـ("20"))'), 'صح\n')
        self.assertEqual(run_arabi('اطبع("-".اجمع(["أ"، "ب"]))'), 'أ-ب\n')

    def test_membership(self):
        self.assertEqual(run_arabi('اطبع("رح" في "مرحبا")'), 'صح\n')
        self.assertEqual(run_arabi('اطبع("س" ليس في "مرحبا")'), 'صح\n')


class TestControlFlow(unittest.TestCase):

    def test_if_elif_else(self):
        src = '''الدرجة = ٨٥
لو الدرجة >= ٩٠:
    اطبع("ممتاز")
وإلا إذا الدرجة >= ٨٠:
    اطبع("جيد جدًا")
وإلا:
    اطبع("حاول")'''
        self.assertEqual(run_arabi(src), 'جيد جدًا\n')

    def test_while_break_continue(self):
        src = '''أ = ٠
طالما صح:
    أ += ١
    لو أ == ٢:
        استمر
    لو أ > ٤:
        كسر
    اطبع(أ)'''
        self.assertEqual(run_arabi(src), '1\n3\n4\n')

    def test_for_range(self):
        src = '''لكل أ في مدى(٣):
    اطبع(أ)'''
        self.assertEqual(run_arabi(src), '0\n1\n2\n')

    def test_for_list_string_dict(self):
        self.assertEqual(run_arabi('لكل ح في "أب":\n    اطبع(ح)'), 'أ\nب\n')
        src = '''قام = {"أ": ١، "ب": ٢}
لكل مفتاح في قام:
    اطبع(مفتاح)'''
        self.assertEqual(run_arabi(src), 'أ\nب\n')

    def test_for_tuple_unpack(self):
        src = '''لكل أ، ب في [[١، ٢]، [٣، ٤]]:
    اطبع(أ + ب)'''
        self.assertEqual(run_arabi(src), '3\n7\n')

    def test_break_outside_loop(self):
        expect_error('كسر', ArabiRuntimeError, 'خارج حلقة')

    def test_return_outside_function(self):
        expect_error('أعد ٥', ArabiRuntimeError, 'خارج الدوال')


class TestFunctions(unittest.TestCase):

    def test_basic(self):
        src = '''دالة جمع(أ، ب):
    أعد أ + ب
اطبع(جمع(٢، ٣))'''
        self.assertEqual(run_arabi(src), '5\n')

    def test_recursion(self):
        src = '''دالة مضروب(ن):
    لو ن <= ١:
        أعد ١
    أعد ن * مضروب(ن - ١)
اطبع(مضروب(٦))'''
        self.assertEqual(run_arabi(src), '720\n')

    def test_closure(self):
        src = '''دالة عداد():
    العدد = ٠
    دالة زد():
        العدد = العدد + ١
        أعد العدد
    أعد زد
الخطوة = عداد()
اطبع(الخطوة())
اطبع(الخطوة())'''
        self.assertEqual(run_arabi(src), '1\n2\n')

    def test_arity_error(self):
        src = '''دالة ف(أ):
    أعد أ
ف(١، ٢)'''
        expect_error(src, ArabiRuntimeError, 'معامل')

    def test_call_non_function(self):
        expect_error('أ = ٥\nأ()', ArabiRuntimeError, 'لا يمكن استدعاؤها')


class TestDataStructures(unittest.TestCase):

    def test_list_methods(self):
        src = '''ق = [٣، ١، ٢]
ق.رتب()
اطبع(ق)
ق.أضف(٤)
اطبع(ق[-١])
ق.أزل(١)
اطبع(ق)'''
        self.assertEqual(run_arabi(src), '[1، 2، 3]\n4\n[2، 3، 4]\n')

    def test_list_index_error(self):
        expect_error('ق = [١]\nاطبع(ق[٥])', ArabiRuntimeError, 'خارج النطاق')

    def test_dict(self):
        src = '''شخص = {"الاسم": "سارة"، "العمر": ٣٠}
شخص["العمر"] = ٣١
شخص["المدينة"] = "الرياض"
اطبع(شخص["العمر"]، شخص["المدينة"])
اطبع(شخص.مفاتيح())'''
        self.assertEqual(run_arabi(src), '31 الرياض\n[الاسم، العمر، المدينة]\n')

    def test_dict_missing_key(self):
        expect_error('ق = {"أ": ١}\nاطبع(ق["ب"])', ArabiRuntimeError, 'غير موجود')

    def test_multiple_assignment(self):
        src = '''أ، ب = ١، ٢
أ، ب = ب، أ
اطبع(أ، ب)'''
        self.assertEqual(run_arabi(src), '2 1\n')

    def test_augmented_index_assign(self):
        src = '''ق = [١، ٢]
ق[٠] += ١٠
اطبع(ق[٠])'''
        self.assertEqual(run_arabi(src), '11\n')

    def test_builtins(self):
        self.assertEqual(run_arabi('اطبع(طول([١، ٢، ٣]))'), '3\n')
        self.assertEqual(run_arabi('اطبع(جمع([١، ٢، ٣]))'), '6\n')
        self.assertEqual(run_arabi('اطبع(أكبر([٤، ٩، ٢]))'), '9\n')
        self.assertEqual(run_arabi('اطبع(نوع("نص"))'), 'نص\n')
        self.assertEqual(run_arabi('اطبع(نوع(٥))'), 'عدد صحيح\n')


class TestErrorsHandling(unittest.TestCase):

    def test_try_catch(self):
        src = '''جرب:
    أ = ١ / ٠
باستثناء:
    اطبع("التقطت الخطأ")
اطبع("كمل عادي")'''
        self.assertEqual(run_arabi(src), 'التقطت الخطأ\nكمل عادي\n')

    def test_try_finally(self):
        src = '''جرب:
    اطبع("جرب")
باستثناء:
    اطبع("باستثناء")
اخيرا:
    اطبع("اخيرا")'''
        self.assertEqual(run_arabi(src), 'جرب\nاخيرا\n')

    def test_raise_and_catch(self):
        src = '''جرب:
    ارفع "خطأ مخصص"
باستثناء:
    اطبع("التقطته")'''
        self.assertEqual(run_arabi(src), 'التقطته\n')

    def test_uncaught_raise(self):
        expect_error('ارفع "انفجار"', ArabiRuntimeError, 'انفجار')

    def test_undefined_variable(self):
        expect_error('اطبع(المتغير_المجهول)', ArabiRuntimeError, 'غير معرّف')


class TestModules(unittest.TestCase):

    def test_math_module(self):
        src = '''استورد رياضيات
اطبع(رياضيات.جذر(١٦))
اطبع(رياضيات.سقف(٢.١))'''
        self.assertEqual(run_arabi(src), '4.0\n3\n')

    def test_unknown_module(self):
        expect_error('استورد غيره', ArabiRuntimeError, 'لم يتم العثور على الوحدة')


class TestDisplay(unittest.TestCase):

    def test_bool_none_display(self):
        self.assertEqual(run_arabi('اطبع(صح، خطأ، ولا شيء)'), 'صح خطأ ولا شيء\n')

    def test_list_display(self):
        self.assertEqual(run_arabi('اطبع([١، "نص"، صح])'), '[1، نص، صح]\n')


class TestSyntaxErrors(unittest.TestCase):

    def test_missing_colon(self):
        expect_error('لو صح\n    اطبع(١)', ParseError, "':'")

    def test_missing_indent(self):
        expect_error('لو صح:\nاطبع(١)', ParseError, 'مسافة بادئة')

    def test_assign_to_literal(self):
        expect_error('٥ = ٣', ParseError, 'الإسناد')

    def test_unclosed_paren(self):
        expect_error('اطبع(١', LexerError, 'بقي مفتوحًا')

    def test_bad_for_loop(self):
        expect_error('لكل أ من [١]:\n    اطبع(أ)', ParseError, 'في')


class TestClasses(unittest.TestCase):
    """اختبارات البرمجة الكائنية: صنف، هذا، الأصل، والوراثة."""

    def test_class_basic(self):
        src = '''
صنف نقطة:
    دالة إنشاء(س، ص):
        هذا.س = س
        هذا.ص = ص

    دالة المجموع():
        أعد هذا.س + هذا.ص

ن = نقطة(٣، ٤)
اطبع(ن.س)
اطبع(ن.المجموع())
'''.strip()
        self.assertEqual(run_arabi(src), '3\n7\n')

    def test_method_with_params_and_return(self):
        src = '''
صنف آلة_حاسبة:
    دالة إنشاء():
        هذا.الذاكرة = 0

    دالة أضف(قيمة):
        هذا.الذاكرة += قيمة
        أعد هذا.الذاكرة

ح = آلة_حاسبة()
ح.أضف(٥)
ح.أضف(١٠)
اطبع(ح.الذاكرة)
'''.strip()
        self.assertEqual(run_arabi(src), '15\n')

    def test_inheritance(self):
        src = '''
صنف حيوان:
    دالة إنشاء(اسم):
        هذا.اسم = اسم

    دالة صوت():
        أعد "..."

صنف قطة من حيوان:
    دالة صوت():
        أعد "مياو"

ق = قطة("مشمش")
اطبع(ق.اسم)
اطبع(ق.صوت())
'''.strip()
        self.assertEqual(run_arabi(src), 'مشمش\nمياو\n')

    def test_inherited_methods_visible(self):
        src = '''
صنف أساس:
    دالة تحية():
        أعد "مرحبا"

صنف فرع من أساس:
    تجاهل

ف = فرع()
اطبع(ف.تحية())
'''.strip()
        self.assertEqual(run_arabi(src), 'مرحبا\n')

    def test_super_constructor_chain(self):
        src = '''
صنف شخص:
    دالة إنشاء(اسم):
        هذا.اسم = اسم

    دالة عرض():
        أعد "شخص: " + هذا.اسم

صنف موظف من شخص:
    دالة إنشاء(اسم، راتب):
        الأصل.إنشاء(هذا، اسم)
        هذا.راتب = راتب

    دالة عرض():
        أعد الأصل.عرض(هذا) + " — الراتب: " + نص(هذا.راتب)

م = موظف("ليلى"، 9000)
اطبع(م.عرض())
'''.strip()
        self.assertEqual(run_arabi(src), 'شخص: ليلى — الراتب: 9000\n')

    def test_class_constant(self):
        src = '''
صنف إعدادات:
    الحد = 100

اطبع(إعدادات.الحد)
ك = إعدادات()
اطبع(ك.الحد)
'''.strip()
        self.assertEqual(run_arabi(src), '100\n100\n')

    def test_bound_method_value(self):
        src = '''
صنف صندوق:
    دالة إنشاء(قيمة):
        هذا.قيمة = قيمة

    دالة اقرأ():
        أعد هذا.قيمة

ص = صندوق(42)
م = ص.اقرأ
اطبع(م())
'''.strip()
        self.assertEqual(run_arabi(src), '42\n')

    def test_augassign_on_attribute(self):
        src = '''
صنف عداد:
    دالة إنشاء():
        هذا.القيمة = 0

ع = عداد()
ع.القيمة += 5
ع.القيمة *= 2
اطبع(ع.القيمة)
'''.strip()
        self.assertEqual(run_arabi(src), '10\n')

    def test_instance_identity(self):
        src = '''
صنف غلاف:
    تجاهل

أ = غلاف()
ب = غلاف()
اطبع(أ == أ)
اطبع(أ == ب)
'''.strip()
        self.assertEqual(run_arabi(src), 'صح\nخطأ\n')

    def test_missing_member_error(self):
        expect_error(
            'صنف أ:\n    تجاهل\nك = أ()\nك.غير_موجود()',
            ArabiRuntimeError, 'لا يحتوي')

    def test_this_outside_method(self):
        expect_error('اطبع(هذا.س)', ArabiRuntimeError, 'هذا')

    def test_super_without_parent(self):
        src = '''
صنف أ:
    دالة ف():
        أعد الأصل
'''.strip()
        expect_error(src + '\nك = أ()\nك.ف()', ArabiRuntimeError, 'الأصل')

    def test_duplicate_method(self):
        src = '''
صنف أ:
    دالة ف():
        أعد 1
    دالة ف():
        أعد 2
'''.strip()
        expect_error(src, ArabiRuntimeError, 'تكرار تعريف')

    def test_inherit_from_non_class(self):
        expect_error(
            'ب = 5\nصنف أ من ب:\n    تجاهل',
            ArabiRuntimeError, 'ليس صنفًا')

    def test_constant_not_callable(self):
        expect_error(
            'صنف أ:\n    ثابت = 7\nك = أ()\nك.ثابت()',
            ArabiRuntimeError, 'ثابت وليس طريقة')

    def test_illegal_statements_in_class_body(self):
        expect_error(
            'صنف أ:\n    اطبع(1)',
            ArabiRuntimeError, 'لا يُسمح')

    def test_attribute_write_on_non_instance(self):
        expect_error(
            'أ = 5\nأ.خاصية = 3',
            ArabiRuntimeError, 'لا يمكن تعيين خاصية')

    def test_instance_display(self):
        src = '''
صنف طالب:
    دالة إنشاء(اسم):
        هذا.اسم = اسم

ك = طالب("سارة")
اطبع(نوع(ك))
'''.strip()
        self.assertEqual(run_arabi(src), 'كائن\n')


class TestExamples(unittest.TestCase):

    EXAMPLES_DIR = os.path.join(ROOT, 'examples')
    INTERACTIVE = {'10_لعبة_التخمين.عربي'}

    def test_all_examples_run(self):
        names = sorted(os.listdir(self.EXAMPLES_DIR))
        arabic_files = [n for n in names if n.endswith('.عربي')]
        self.assertGreaterEqual(len(arabic_files), 10)
        for name in arabic_files:
            if name in self.INTERACTIVE:
                continue
            with open(os.path.join(self.EXAMPLES_DIR, name),
                      encoding='utf-8') as f:
                source = f.read()
            try:
                # مجلد الأمثلة أساس البحث عن الوحدات المستوردة
                run_code(source, script_dir=self.EXAMPLES_DIR)
            except ArabiError as exc:
                self.fail(f'المثال {name} فشل: {exc}')

    def test_interactive_game_with_eof(self):
        # نهاية الإدخال تُلغي اللعبة بأمان
        import builtins
        original_input = builtins.input
        builtins.input = lambda prompt='': ''
        try:
            with open(os.path.join(self.EXAMPLES_DIR,
                                   '10_لعبة_التخمين.عربي'),
                      encoding='utf-8') as f:
                run_code(f.read())
        finally:
            builtins.input = original_input


class TestKwargs(unittest.TestCase):
    """القيم الافتراضية والمعاملات بالاسم."""

    def test_default_value_used(self):
        src = '''
دالة ترحيب(الاسم، تحية = "مرحبا"):
    أعد تحية + " " + الاسم
اطبع(ترحيب("أحمد"))'''
        self.assertEqual(run_arabi(src), 'مرحبا أحمد\n')

    def test_default_value_overridden(self):
        src = '''
دالة ترحيب(الاسم، تحية = "مرحبا"):
    أعد تحية + " " + الاسم
اطبع(ترحيب("سارة"، "أهلاً"))'''
        self.assertEqual(run_arabi(src), 'أهلاً سارة\n')

    def test_all_defaults(self):
        src = '''
دالة قوة(أساس = ٢، أس = ٣):
    أعد أساس ** أس
اطبع(قوة())
اطبع(قوة(٣))
اطبع(قوة(٣، ٢))'''
        self.assertEqual(run_arabi(src), '8\n27\n9\n')

    def test_kwargs_call(self):
        src = '''
دالة تعريف(الاسم، العمر):
    أعد الاسم + " عمره " + نص(العمر)
اطبع(تعريف(العمر = ٣٠، الاسم = "ليلى"))'''
        self.assertEqual(run_arabi(src), 'ليلى عمره 30\n')

    def test_mixed_positional_and_kwargs(self):
        src = '''
دالة فاتورة(الصنف، الكمية = ١، سعر = ١٠):
    أعد الصنف + ": " + نص(الكمية * سعر)
اطبع(فاتورة("قلم"، سعر = ٢.٥))
اطبع(فاتورة("دفتر"، ٣، سعر = ٥))'''
        self.assertEqual(run_arabi(src), 'قلم: 2.5\nدفتر: 15\n')

    def test_kwargs_in_method(self):
        src = '''
صنف دائرة:
    دالة إنشاء(نق = ١):
        هذا.نق = نق
    دالة مساحة():
        أعد ٣ * هذا.نق * هذا.نق
ك = دائرة()
اطبع(ك.مساحة())
ك٢ = دائرة(نق = ٢)
اطبع(ك٢.مساحة())
اطبع(دائرة(نق = ٣).مساحة())'''
        self.assertEqual(run_arabi(src), '3\n12\n27\n')

    def test_missing_required_param(self):
        expect_error('دالة عملية(أ، ب = ٢):\n    أعد أ\nعملية()',
                     ArabiRuntimeError, "قيمة للمعامل 'أ'")

    def test_unknown_kwarg(self):
        expect_error('دالة عملية(أ):\n    أعد أ\nعملية(م = ١)',
                     ArabiRuntimeError, "معامل بالاسم 'م'")

    def test_duplicate_kwarg(self):
        expect_error('دالة عملية(أ):\n    أعد أ\nعملية(١، أ = ٢)',
                     ArabiRuntimeError, "أُرسل مرتين")

    def test_too_many_args(self):
        expect_error('دالة عملية(أ = ١):\n    أعد أ\nعملية(١، ٢)',
                     ArabiRuntimeError, 'كحد أقصى')

    def test_positional_after_kwarg(self):
        expect_error('دالة عملية(أ، ب):\n    أعد أ + ب\nعملية(أ = ١، ٢)',
                     ArabiRuntimeError, 'موضعي بعد معامل بالاسم')

    def test_default_evaluated_at_def_time(self):
        src = '''
س = ١٠
دالة اقرأ(قيمة = س):
    أعد قيمة
س = ٩٩
اطبع(اقرأ())'''
        self.assertEqual(run_arabi(src), '10\n')

    def test_kwargs_not_supported_in_builtins(self):
        expect_error('اطبع(نص = "مرحبا")', ArabiRuntimeError,
                     "لا تقبل معاملات بالاسم")


class TestLambda(unittest.TestCase):
    """الدوال السهمية على سطر واحد."""

    def test_basic(self):
        self.assertEqual(run_arabi('ضاعف = دالة(س) => س * ٢\nاطبع(ضاعف(٢١))'),
                         '42\n')

    def test_two_params(self):
        self.assertEqual(run_arabi('اجمع = دالة(أ، ب) => أ + ب\nاطبع(اجمع(٣، ٤))'),
                         '7\n')

    def test_zero_params(self):
        self.assertEqual(run_arabi('درب = دالة() => "مرحبا"\nاطبع(درب())'),
                         'مرحبا\n')

    def test_inline_call(self):
        self.assertEqual(run_arabi('اطبع((دالة(س) => س + ١)(٤١))'),
                         '42\n')

    def test_stored_in_list(self):
        src = '''
عمليات = [دالة(س) => س + ١، دالة(س) => س * ١٠]
اطبع(عمليات[٠](٥))
اطبع(عمليات[١](٥))'''
        self.assertEqual(run_arabi(src), '6\n50\n')

    def test_passed_as_callback(self):
        src = '''
دالة طبق(قيمة، تحويل):
    أعد تحويل(قيمة)
اطبع(طبق(٥، دالة(س) => س * س))'''
        self.assertEqual(run_arabi(src), '25\n')

    def test_closure_captures(self):
        src = '''
العامل = ٣
ضاعف = دالة(س) => س * العامل
اطبع(ضاعف(٧))'''
        self.assertEqual(run_arabi(src), '21\n')

    def test_default_params(self):
        self.assertEqual(
            run_arabi('سلم = دالة(أساس = ٢، أس = ٥) => أساس ** أس\nاطبع(سلم())'),
            '32\n')

    def test_recursion_style_stays_regular_func(self):
        # التعاود يستخدم دالة عادية — السهمية تعبير واحد فقط
        src = '''
مضروب = دالة(ن) => ٠
دالة حقيقية(ن):
    لو ن <= ١:
        أعد ١
    أعد ن * حقيقية(ن - ١)
اطبع(حقيقية(٥))'''
        self.assertEqual(run_arabi(src), '120\n')

    def test_display(self):
        self.assertEqual(run_arabi('اطبع(دالة(س) => س)'), '<دالة سهمية>\n')

    def test_type(self):
        self.assertEqual(run_arabi('اطبع(نوع(دالة(س) => س))'), 'دالة\n')

    def test_missing_arrow(self):
        expect_error('مربع = دالة(س) س + ١', ParseError, "'=>'")

    def test_multiline_body_rejected(self):
        expect_error('مربع = دالة(س) =>\n    س + ١', ParseError, 'سطر')


class TestFileModules(unittest.TestCase):
    """الاستيراد من ملفات .عربي — يعمل على ملفات مؤقتة."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, relpath, content):
        path = os.path.join(self.dir, relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def run_in_dir(self, source):
        return run_code(source, script_dir=self.dir)

    def test_basic_import(self):
        self.write('هندسة.عربي',
                   'ط = ٣.١٤\nدالة مساحة(نق):\n    أعد ط * نق * نق\n')
        out = self.run_in_dir('استورد هندسة\nاطبع(هندسة.مساحة(٢))\n'
                              'اطبع(هندسة.ط)\n')
        self.assertEqual(out, '12.56\n3.14\n')

    def test_from_import(self):
        self.write('أدوات.عربي',
                   'دالة ضاعف(س):\n    أعد س * ٢\n'
                   'دالة ثلث(س):\n    أعد س / ٣\n')
        out = self.run_in_dir('من أدوات استورد ضاعف\nاطبع(ضاعف(٥))\n')
        self.assertEqual(out, '10\n')

    def test_from_import_multiple_names(self):
        self.write('أدوات.عربي',
                   'أ = ١\nب = ٢\nج = ٣\n')
        out = self.run_in_dir('من أدوات استورد أ، ج\nاطبع(أ + ج)\n')
        self.assertEqual(out, '4\n')

    def test_from_import_unknown_name(self):
        self.write('أدوات.عربي', 'أ = ١\n')
        with self.assertRaises(ArabiRuntimeError) as ctx:
            self.run_in_dir('من أدوات استورد غيره\n')
        self.assertIn("لا تحتوي على 'غيره'", str(ctx.exception))

    def test_quoted_path_import(self):
        self.write('مكتبة/تحويلات.عربي',
                   'دالة مزدوج(س):\n    أعد س * ٢\n')
        out = self.run_in_dir('استورد "مكتبة/تحويلات.عربي"\n'
                              'اطبع(تحويلات.مزدوج(٨))\n')
        self.assertEqual(out, '16\n')

    def test_subfolder_import(self):
        self.write('وحدات/نصوص.عربي', 'رسالة = "من مجلد وحدات"\n')
        out = self.run_in_dir('استورد نصوص\nاطبع(نصوص.رسالة)\n')
        self.assertEqual(out, 'من مجلد وحدات\n')

    def test_module_cached_and_runs_once(self):
        self.write('عدادات.عربي', 'زيارات = ١\n')
        out = self.run_in_dir('''
استورد عدادات
استورد عدادات
م = عدادات
اطبع("تم")''')
        self.assertEqual(out, 'تم\n')

    def test_cyclic_import_detected(self):
        self.write('أ.عربي', 'استورد ب\n')
        self.write('ب.عربي', 'استورد أ\n')
        with self.assertRaises(ArabiRuntimeError) as ctx:
            self.run_in_dir('استورد أ\n')
        self.assertIn('استيراد دائري', str(ctx.exception))

    def test_nested_module_import(self):
        self.write('أساس.عربي', 'قيمة = ٥\n')
        self.write('أعلى.عربي', 'استورد أساس\nالنتيجة = أساس.قيمة * ٢\n')
        out = self.run_in_dir('استورد أعلى\nاطبع(أعلى.النتيجة)\n')
        self.assertEqual(out, '10\n')

    def test_module_with_class(self):
        self.write('حيوانات.عربي', '''
صنف كلب:
    دالة إنشاء(اسم):
        هذا.اسم = اسم
    دالة عوّ():
        أعد هذا.اسم + ": هَو هَو!"
''')
        out = self.run_in_dir('''
استورد حيوانات
ك = حيوانات.كلب(اسم = "ريكس")
اطبع(ك.عوّ())''')
        self.assertEqual(out, 'ريكس: هَو هَو!\n')

    def test_module_isolation(self):
        # متغيرات الوحدة لا تتسرب للبرنامج الرئيسي
        self.write('خفي.عربي', 'سر = ٤٢\n')
        with self.assertRaises(ArabiRuntimeError):
            self.run_in_dir('استورد خفي\nاطبع(سر)\n')

    def test_module_sees_builtins(self):
        self.write('مستخدم.عربي', 'النتيجة = طول("أبجدي")\n')
        out = self.run_in_dir('استورد مستخدم\nاطبع(مستخدم.النتيجة)\n')
        self.assertEqual(out, '5\n')

    def test_module_error_line(self):
        self.write('مكسور.عربي', 'أ = ١\nب = ٢ / ٠\n')
        with self.assertRaises(ArabiRuntimeError) as ctx:
            self.run_in_dir('استورد مكسور\n')
        self.assertIn('قسمة على صفر', str(ctx.exception))

    def test_missing_module_lists_paths(self):
        with self.assertRaises(ArabiRuntimeError) as ctx:
            self.run_in_dir('استورد غير_موجودة\n')
        self.assertIn('بحثت في', str(ctx.exception))

    def test_import_builtin_still_works(self):
        out = self.run_in_dir('استورد رياضيات\nاطبع(رياضيات.جذر(٩))\n')
        self.assertEqual(out, '3.0\n')


class TestSwitch(unittest.TestCase):
    """اختبارات جملة بدّل/حالة/افتراض."""

    def test_string_match(self):
        out = run_arabi('''
يوم = "السبت"
بدّل يوم
حالة "الجمعة":
    اطبع("صلاة")
حالة "السبت":
    اطبع("عطلة")
حالة "الأحد":
    اطبع("أسبوع")
''')
        self.assertEqual(out, 'عطلة\n')

    def test_number_match(self):
        out = run_arabi('''
بدّل ٢ + ١
حالة ١:
    اطبع("واحد")
حالة ٣:
    اطبع("ثلاثة")
''')
        self.assertEqual(out, 'ثلاثة\n')

    def test_default_runs_when_no_match(self):
        out = run_arabi('''
بدّل "خميس"
حالة "السبت":
    اطبع("عطلة")
افتراض:
    اطبع("يوم عادي")
''')
        self.assertEqual(out, 'يوم عادي\n')

    def test_default_skipped_when_match(self):
        out = run_arabi('''
بدّل "السبت"
حالة "السبت":
    اطبع("عطلة")
افتراض:
    اطبع("يوم عادي")
''')
        self.assertEqual(out, 'عطلة\n')

    def test_no_match_no_default_is_silent(self):
        out = run_arabi('''
بدّل ٩٩
حالة ١:
    اطبع("واحد")
اطبع("استمر البرنامج")
''')
        self.assertEqual(out, 'استمر البرنامج\n')

    def test_break_inside_switch_breaks_loop(self):
        out = run_arabi('''
لكل س في مدى(١، ٦):
    بدّل س
    حالة ٣:
        كسر
    افتراض:
        اطبع(س)
اطبع("انتهى")
''')
        self.assertEqual(out, '1\n2\nانتهى\n')

    def test_cases_use_equality_not_truthiness(self):
        out = run_arabi('''
بدّل ٠
حالة صح:
    اطبع("خطأ: صح تطابق صفر")
حالة ٠:
    اطبع("صفر صحيح")
''')
        self.assertEqual(out, 'صفر صحيح\n')

    def test_switch_needs_newline_after_subject(self):
        expect_error('بدّل ١ حالة ٢:\n    اطبع(١)\n',
                     ParseError, 'سطرًا جديدًا')

    def test_switch_needs_at_least_one_case(self):
        expect_error('بدّل ١\nاطبع(٢)\n', ParseError, 'حالة')

    def test_switch_in_function(self):
        out = run_arabi('''
دالة اسم_اليوم(رقم):
    بدّل رقم
    حالة ١:
        أعد "الاثنين"
    حالة ٢:
        أعد "الثلاثاء"
    افتراض:
        أعد "غير معروف"
اطبع(اسم_اليوم(٢))
اطبع(اسم_اليوم(٩))
''')
        self.assertEqual(out, 'الثلاثاء\nغير معروف\n')


class TestHigherOrder(unittest.TestCase):
    """اختبارات خريطة/مرشّح/اختزل."""

    def test_map_with_lambda(self):
        out = run_arabi('اطبع(خريطة(دالة(س) => س * س، [١، ٢، ٣، ٤]))')
        self.assertEqual(out, '[1، 4، 9، 16]\n')

    def test_map_with_named_function(self):
        out = run_arabi('''
دالة تحية(اسم):
    أعد "مرحبا " + اسم
اطبع(خريطة(تحية، ["سالم"، "ريم"]))''')
        self.assertEqual(out, '[مرحبا سالم، مرحبا ريم]\n')

    def test_map_on_range(self):
        out = run_arabi('اطبع(خريطة(دالة(س) => س + ١، مدى(٠، ٣)))')
        self.assertEqual(out, '[1، 2، 3]\n')

    def test_filter_keeps_truthy(self):
        out = run_arabi(
            'اطبع(مرشّح(دالة(س) => س % ٢ == ٠، مدى(١، ١١)))')
        self.assertEqual(out, '[2، 4، 6، 8، 10]\n')

    def test_filter_strings(self):
        out = run_arabi('''
كلمات = ["تفاح"، "برتقال"، "زيتون"]
أطول = مرشّح(دالة(ك) => طول(ك) >= ٥، كلمات)
اطبع(أطول)''')
        self.assertEqual(out, '[برتقال، زيتون]\n')

    def test_reduce_without_initial(self):
        out = run_arabi('اطبع(اختزل(دالة(أ، ب) => أ + ب، [١٠، ٢٠، ٣٠]))')
        self.assertEqual(out, '60\n')

    def test_reduce_with_initial(self):
        out = run_arabi('اطبع(اختزل(دالة(أ، ب) => أ + ب، [١، ٢، ٣]، ١٠٠))')
        self.assertEqual(out, '106\n')

    def test_reduce_max_with_function(self):
        out = run_arabi('''
دالة الأكبر(أ، ب):
    لو ب > أ:
        أعد ب
    وإلا:
        أعد أ
اطبع(اختزل(الأكبر، [٣، ٩، ٢]))''')
        self.assertEqual(out, '9\n')

    def test_map_requires_function(self):
        expect_error('خريطة(٥، [١، ٢])', ArabiRuntimeError, 'تحتاج دالة')

    def test_map_requires_list(self):
        expect_error('خريطة(دالة(س) => س، ٥)', ArabiRuntimeError,
                     'قائمة أو نصًا أو مدى')

    def test_reduce_empty_without_initial(self):
        expect_error('اختزل(دالة(أ، ب) => أ، [])', ArabiRuntimeError,
                     'قيمة بداية')

    def test_map_on_string(self):
        out = run_arabi('اطبع(خريطة(دالة(ح) => ح + "!"، "أب"))')
        self.assertEqual(out, '[أ!، ب!]\n')


class TestChoose(unittest.TestCase):
    """اختبارات دالة اختر العشوائية."""

    def test_choose_returns_element(self):
        out = run_arabi('''
فواكه = ["تفاح"، "موز"، "عنب"]
اختيار = اختر(فواكه)
اطبع(اختيار في فواكه)''')
        self.assertEqual(out, 'صح\n')

    def test_choose_on_range(self):
        out = run_arabi('اطبع(اختر(مدى(٥، ٦)) == ٥)')
        self.assertEqual(out, 'صح\n')

    def test_choose_empty_errors(self):
        expect_error('اختر([])', ArabiRuntimeError, 'فارغ')

    def test_choose_number_errors(self):
        expect_error('اختر(٥)', ArabiRuntimeError, 'قائمة')


class TestFilesModule(unittest.TestCase):
    """اختبارات وحدة ملفات."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='arabi_files_')
        self.path = os.path.join(self.dir, 'دفتر.txt')

    def test_write_read_roundtrip(self):
        out = run_arabi(
            'ملفات.اكتب("%s"، "مرحبا بالملفات")\n'
            'اطبع(ملفات.اقرأ("%s"))\n' % (self.path, self.path))
        self.assertEqual(out, 'مرحبا بالملفات\n')

    def test_write_overwrites(self):
        run_arabi('ملفات.اكتب("%s"، "أول")\n' % self.path)
        out = run_arabi(
            'ملفات.اكتب("%s"، "ثانٍ")\n'
            'اطبع(ملفات.اقرأ("%s"))\n' % (self.path, self.path))
        self.assertEqual(out, 'ثانٍ\n')

    def test_append_adds_to_end(self):
        run_arabi('ملفات.اكتب("%s"، "سطر أول\\n")\n' % self.path)
        out = run_arabi(
            'ملفات.أضف("%s"، "سطر ثانٍ\\n")\n'
            'اطبع(ملفات.أسطر("%s"))\n' % (self.path, self.path))
        self.assertEqual(out, '[سطر أول، سطر ثانٍ]\n')

    def test_lines_returns_list(self):
        run_arabi('ملفات.اكتب("%s"، "أ\\nب\\nج")\n' % self.path)
        out = run_arabi('اطبع(طول(ملفات.أسطر("%s")))\n' % self.path)
        self.assertEqual(out, '3\n')

    def test_exists(self):
        out = run_arabi(
            'اطبع(ملفات.موجود("%s"))\n'
            'ملفات.اكتب("%s"، "محتوى")\n'
            'اطبع(ملفات.موجود("%s"))\n' % (self.path, self.path, self.path))
        self.assertEqual(out, 'خطأ\nصح\n')

    def test_delete(self):
        run_arabi('ملفات.اكتب("%s"، "سأحذف")\n' % self.path)
        out = run_arabi(
            'اطبع(ملفات.احذف("%s"))\n'
            'اطبع(ملفات.موجود("%s"))\n' % (self.path, self.path))
        self.assertEqual(out, 'صح\nخطأ\n')

    def test_delete_missing_returns_false(self):
        out = run_arabi('اطبع(ملفات.احذف("%s"))\n' % self.path)
        self.assertEqual(out, 'خطأ\n')

    def test_read_missing_file_errors(self):
        expect_error('ملفات.اقرأ("%s")\n' % self.path,
                     ArabiRuntimeError, 'غير موجود')

    def test_write_non_string_content_errors(self):
        expect_error('ملفات.اكتب("%s"، ٥)\n' % self.path,
                     ArabiRuntimeError, 'نصًا')

    def test_path_must_be_string(self):
        expect_error('ملفات.اقرأ(٥)\n', ArabiRuntimeError, 'مسار نصي')

    def test_files_module_with_json_roundtrip(self):
        out = run_arabi('''
الطريق = "%s"
ملفات.اكتب(الطريق، جيسون.نص({"اسم": "ليلى"، "عمر": ٢٨}))
بيانات = جيسون.حلل(ملفات.اقرأ(الطريق))
اطبع(بيانات["اسم"] + " عمرها " + نص(بيانات["عمر"]))
ملفات.احذف(الطريق)
''' % self.path)
        self.assertEqual(out, 'ليلى عمرها 28\n')


class TestJsonModule(unittest.TestCase):
    """اختبارات وحدة جيسون."""

    def test_parse_simple(self):
        out = run_arabi('''
بيانات = جيسون.حلل("{\\"اسم\\": \\"سالم\\"، \\"عمر\\": ٢٥}")
اطبع(بيانات["اسم"])''')
        self.assertEqual(out, 'سالم\n')

    def test_parse_with_arabic_commas(self):
        out = run_arabi(
            'ب = جيسون.حلل("[١، ٢، ٣]")\n'
            'اطبع(ب[٢])\n')
        self.assertEqual(out, '3\n')

    def test_parse_accepts_ascii_digits(self):
        out = run_arabi('اطبع(جيسون.حلل("٥") + ١)\n')
        self.assertEqual(out, '6\n')

    def test_stringify_preserves_arabic(self):
        out = run_arabi('اطبع(جيسون.نص({"اسم": "ليلى"}))\n')
        self.assertEqual(out, '{"اسم": "ليلى"}\n')

    def test_roundtrip(self):
        out = run_arabi('''
المصدر = {"مهارات": ["برمجة"، "تصميم"]، "متاح": صح، "ملاحظة": ولا شيء}
سلسلة = جيسون.نص(المصدر)
المعاد = جيسون.حلل(سلسلة)
اطبع(المعاد["مهارات"][١])
اطبع(المعاد["متاح"])
اطبع(المعاد["ملاحظة"])''')
        self.assertEqual(out, 'تصميم\nصح\nولا شيء\n')

    def test_json_true_parses_to_arabic(self):
        out = run_arabi('اطبع(جيسون.حلل("true"))\n')
        self.assertEqual(out, 'صح\n')

    def test_parse_invalid_json(self):
        expect_error('جيسون.حلل("{اسم بدون اقتباس}")',
                     ArabiRuntimeError, 'غير صالح')

    def test_parse_requires_string(self):
        expect_error('جيسون.حلل(٥)', ArabiRuntimeError, 'نص')

    def test_stringify_unsupported_value(self):
        expect_error('اطبع(جيسون.نص(ملفات))\n',
                     ArabiRuntimeError, 'JSON')


class TestFStrings(unittest.TestCase):
    """السلاسل المنسقة: ق"مرحبا {الاسم}" """

    def test_lexer_fstring_token(self):
        from arabi_lang.lexer import Lexer
        from arabi_lang.tokens import T
        toks = Lexer('ق"نص {س}"').tokenize()
        self.assertEqual(toks[0].type, T.FSTRING)
        self.assertEqual(toks[0].value, 'نص {س}')

    def test_lexer_ident_ق_alone(self):
        from arabi_lang.lexer import Lexer
        from arabi_lang.tokens import T
        toks = Lexer('ق = ٥').tokenize()
        self.assertEqual(toks[0].type, T.IDENT)
        self.assertEqual(toks[0].value, 'ق')

    def test_lexer_ident_starting_with_ق(self):
        from arabi_lang.lexer import Lexer
        from arabi_lang.tokens import T
        toks = Lexer('قائمة = [١، ٢]').tokenize()
        self.assertEqual(toks[0].type, T.IDENT)
        self.assertEqual(toks[0].value, 'قائمة')

    def test_basic(self):
        self.assertEqual(run_arabi('الاسم = "أحمد"\nاطبع(ق"مرحبا {الاسم}!")'),
                         'مرحبا أحمد!\n')

    def test_expression(self):
        self.assertEqual(run_arabi('أ = ٣\nب = ٤\nاطبع(ق"الناتج {أ + ب}")'),
                         'الناتج 7\n')

    def test_call_same_quote_nesting(self):
        # اقتباس متشابه داخل التعبير — مسموح داخل الأقواس
        self.assertEqual(run_arabi('اطبع(ق"الطول {طول("مرحبا")}")'),
                         'الطول 5\n')

    def test_dict_index_same_quote(self):
        self.assertEqual(
            run_arabi('د = {"اسم": "سلمى"}\nاطبع(ق"أهلًا {د["اسم"]}")'),
            'أهلًا سلمى\n')

    def test_nested_fstring(self):
        self.assertEqual(
            run_arabi('اطبع(ق"خارجي {ق"داخلي"} نهاية")'),
            'خارجي داخلي نهاية\n')

    def test_doubled_braces(self):
        self.assertEqual(run_arabi('اطبع(ق"{{نص}}")'), '{نص}\n')

    def test_method_call(self):
        self.assertEqual(run_arabi('النص = "عربي"\nاطبع(ق"{النص.كبير()}")'),
                         'عربي'.upper() + '\n')

    def test_index(self):
        self.assertEqual(
            run_arabi('قائمة = [١٠، ٢٠]\nاطبع(ق"الثاني {قائمة[١]}")'),
            'الثاني 20\n')

    def test_bool_and_none(self):
        self.assertEqual(run_arabi('اطبع(ق"{٣ > ٢}")'), 'صح\n')
        self.assertEqual(run_arabi('اطبع(ق"{ولا شيء}")'), 'ولا شيء\n')

    def test_float(self):
        self.assertEqual(run_arabi('اطبع(ق"السعر {٢.٥}")'), 'السعر 2.5\n')

    def test_concat_with_regular_string(self):
        self.assertEqual(run_arabi('ن = ق"أ{١+١}" + "ج"\nاطبع(ن)'), 'أ2ج\n')

    def test_as_argument_and_return(self):
        self.assertEqual(
            run_arabi('دالة انسخ(ن):\n'
                      '    أعد ن\n'
                      'اطبع(انسخ(ق"قيمة {٤٢}"))'),
            'قيمة 42\n')

    def test_empty_fstring(self):
        self.assertEqual(run_arabi('اطبع(ق"")'), '\n')

    def test_escaped_quote_inside(self):
        self.assertEqual(run_arabi('اطبع(ق"يقول: \\"مرحبا\\"")'),
                         'يقول: "مرحبا"\n')

    def test_unclosed_brace_error(self):
        # بدون إغلاق } يبتلع النص المنسق حتى نهاية السطر ثم يرفع خطأ لفطي
        expect_error('اطبع(ق"نص {١+٢")', LexerError, 'غير مغلق')

    def test_empty_expression_error(self):
        expect_error('اطبع(ق"نص {}")', ParseError, 'فارغ')

    def test_lone_close_brace_error(self):
        expect_error('اطبع(ق"نص }")', ParseError, '}')

    def test_unclosed_quote_error(self):
        expect_error('اطبع(ق"نص)', LexerError, 'غير مغلق')


class TestMultilineStrings(unittest.TestCase):
    """النصوص متعددة الأسطر بثلاث علامات اقتباس"""

    def test_two_lines_length(self):
        self.assertEqual(
            run_arabi('ن = """سطر أول\nسطر ثاني"""\nاطبع(طول(ن))'), '16\n')

    def test_content(self):
        self.assertEqual(
            run_arabi('ن = """أ\nب"""\nاطبع(ن)'), 'أ\nب\n')

    def test_three_lines(self):
        self.assertEqual(run_arabi('اطبع(طول("""أ\nب\nج"""))'), '5\n')

    def test_single_quote_style(self):
        self.assertEqual(
            run_arabi("ن = '''سطر\nثاني'''\nاطبع(ن)"), 'سطر\nثاني\n')

    def test_quotes_inside(self):
        self.assertEqual(
            run_arabi('ن = """قال: "مرحبا" ثم انصرف"""\nاطبع(ن)'),
            'قال: "مرحبا" ثم انصرف\n')

    def test_escapes_inside(self):
        self.assertEqual(
            run_arabi('ن = """سطر\\nجديد بِتاب\\tوصلة"""\nاطبع(ن)'),
            'سطر\nجديد بِتاب\tوصلة\n')

    def test_empty_triple(self):
        self.assertEqual(run_arabi('اطبع(طول(""""""))'), '0\n')

    def test_in_function(self):
        self.assertEqual(
            run_arabi('دالة شعار():\n'
                      '    أعد """لغة عربي"""\n'
                      'اطبع(شعار())'),
            'لغة عربي\n')

    def test_unclosed_triple_error(self):
        expect_error('ن = """نص\nبلا إغلاق', LexerError, 'غير مغلق')


class TestStringMethodsV14(unittest.TestCase):
    """الطرق النصية الجديدة: أوجد / يحتوي / عدد_التكرار / اعكس"""

    # ---------- أوجد ----------

    def test_find_found(self):
        self.assertEqual(run_arabi('اطبع("مرحبا".أوجد("حب"))'), '2\n')

    def test_find_at_start(self):
        self.assertEqual(run_arabi('اطبع("مرحبا".أوجد("م"))'), '0\n')

    def test_find_not_found(self):
        self.assertEqual(run_arabi('اطبع("مرحبا".أوجد("س"))'), '-1\n')

    def test_find_needs_string(self):
        expect_error('اطبع("مرحبا".أوجد(٥))', ArabiRuntimeError, 'نصًا')

    def test_find_one_arg(self):
        expect_error('اطبع("مرحبا".أوجد())', ArabiRuntimeError, 'أوجد')

    # ---------- يحتوي ----------

    def test_contains_true(self):
        self.assertEqual(run_arabi('اطبع("اللغة العربية".يحتوي("عرب"))'),
                         'صح\n')

    def test_contains_false(self):
        self.assertEqual(run_arabi('اطبع("اللغة العربية".يحتوي("فرنس"))'),
                         'خطأ\n')

    def test_contains_empty(self):
        self.assertEqual(run_arabi('اطبع("نص".يحتوي(""))'), 'صح\n')

    def test_contains_needs_string(self):
        expect_error('اطبع("نص".يحتوي([١]))', ArabiRuntimeError, 'نصًا')

    # ---------- عدد_التكرار ----------

    def test_count_basic(self):
        self.assertEqual(run_arabi('اطبع("أبأبأ".عدد_التكرار("أب"))'), '2\n')

    def test_count_char(self):
        self.assertEqual(
            run_arabi('اطبع("برمجة".عدد_التكرار("م"))'), '1\n')

    def test_count_zero(self):
        self.assertEqual(
            run_arabi('اطبع("نص".عدد_التكرار("س"))'), '0\n')

    def test_count_needs_string(self):
        expect_error('اطبع("نص".عدد_التكرار(٣))', ArabiRuntimeError, 'نصًا')

    # ---------- اعكس ----------

    def test_reverse(self):
        self.assertEqual(run_arabi('اطبع("مرحبا".اعكس())'), 'ابحرم\n')

    def test_reverse_palindrome(self):
        self.assertEqual(run_arabi('اطبع("كلك".اعكس())'), 'كلك\n')

    def test_reverse_empty(self):
        self.assertEqual(run_arabi('اطبع("".اعكس())'), '\n')

    def test_reverse_no_args(self):
        expect_error('اطبع("نص".اعكس("س"))', ArabiRuntimeError, 'اعكس')

    # ---------- تركيبات ----------

    def test_find_with_slice(self):
        self.assertEqual(
            run_arabi('اطبع("مرحبا يا عالم".أوجد("عالم"))'), '9\n')

    def test_contains_in_condition(self):
        self.assertEqual(
            run_arabi('لو "النص العربي".يحتوي("عرب"):\n'
                      '    اطبع("موجود")\n'
                      'وإلا:\n'
                      '    اطبع("مفقود")'),
            'موجود\n')


# ============================================================
#              اختبارات الإصدار 1.5.0 — الميزات الجديدة
# ============================================================

class TestTernary(unittest.TestCase):
    """التعبير الثلاثي: لو شرط: قيمة وإلا قيمة"""

    def test_basic_true(self):
        self.assertEqual(
            run_arabi('اطبع(لو صح: "نعم" وإلا "لا")'), 'نعم\n')

    def test_basic_false(self):
        self.assertEqual(
            run_arabi('اطبع(لو خطأ: "نعم" وإلا "لا")'), 'لا\n')

    def test_with_condition(self):
        self.assertEqual(
            run_arabi('العمر = ٢٠\nاطبع(لو العمر >= ١٨: "بالغ" وإلا "طفل")'),
            'بالغ\n')

    def test_in_assignment(self):
        self.assertEqual(
            run_arabi('س = ٥\nالنتيجة = لو س > ٠: "موجب" وإلا "سالب"\n'
                      'اطبع(النتيجة)'), 'موجب\n')

    def test_in_function_arg(self):
        self.assertEqual(
            run_arabi('اطبع(لو ١ > ٢: "أ" وإلا "ب")'), 'ب\n')

    def test_nested_ternary(self):
        self.assertEqual(
            run_arabi('س = ٠\nاطبع(لو س > ٠: "موجب" وإلا لو س < ٠: "سالب" وإلا "صفر")'),
            'صفر\n')

    def test_with_complex_condition(self):
        self.assertEqual(
            run_arabi('اطبع(لو ٢ + ٢ == ٤ و ٥ > ٣: "صحيح" وإلا "خطأ")'),
            'صحيح\n')

    def test_lazy_evaluation(self):
        # الفرع غير المختار لا يُنفذ (لا يسبب خطأ)
        self.assertEqual(
            run_arabi('اطبع(لو صح: "سليم" وإلا ١ / ٠)'), 'سليم\n')

    def test_missing_else(self):
        expect_error('س = لو صح: ١', ParseError, 'وإلا')

    def test_missing_colon(self):
        expect_error('س = لو صح ١ وإلا ٢', ParseError, "':'")


class TestEnums(unittest.TestCase):
    """جملة تعداد"""

    ENUM_SRC = (
        'تعداد يوم:\n'
        '    السبت\n'
        '    الأحد\n'
        '    الاثنين\n'
    )

    def test_auto_values_start_from_one(self):
        out = run_arabi(self.ENUM_SRC
                        + 'اطبع(يوم.السبت.القيمة)\nاطبع(يوم.الأحد.القيمة)')
        self.assertEqual(out, '1\n2\n')

    def test_explicit_value_continues(self):
        out = run_arabi('تعداد يوم:\n    السبت\n    الأحد = ٧\n    الاثنين\n'
                        'اطبع(يوم.الأحد.القيمة)\nاطبع(يوم.الاثنين.القيمة)')
        self.assertEqual(out, '7\n8\n')

    def test_member_display(self):
        self.assertEqual(run_arabi(self.ENUM_SRC + 'اطبع(يوم.السبت)'),
                         'يوم.السبت\n')

    def test_member_name_attribute(self):
        self.assertEqual(run_arabi(self.ENUM_SRC + 'اطبع(يوم.السبت.الاسم)'),
                         'السبت\n')

    def test_members_equal(self):
        out = run_arabi(self.ENUM_SRC
                        + 'اطبع(يوم.السبت == يوم.السبت)\n'
                          'اطبع(يوم.السبت == يوم.الأحد)')
        self.assertEqual(out, 'صح\nخطأ\n')

    def test_member_in_switch(self):
        out = run_arabi(self.ENUM_SRC
                        + 'بدّل يوم.الأحد\n'
                          'حالة يوم.السبت:\n    اطبع("أول أيام الراحة")\n'
                          'حالة يوم.الأحد:\n    اطبع("بداية الأسبوع")\n')
        self.assertEqual(out, 'بداية الأسبوع\n')

    def test_unknown_member(self):
        expect_error(self.ENUM_SRC + 'اطبع(يوم.الجمعة)',
                     ArabiRuntimeError, 'لا يحتوي')

    def test_member_attributes(self):
        expect_error(self.ENUM_SRC + 'اطبع(يوم.السبت.مجهول)',
                     ArabiRuntimeError, 'الاسم، القيمة')

    def test_empty_enum(self):
        expect_error('تعداد فارغ:\n    تجاهل\n', ParseError, 'تعداد')

    def test_duplicate_member(self):
        expect_error('تعداد ت:\n    أ\n    أ\n', ArabiRuntimeError, 'تكرار')

    def test_non_int_value(self):
        expect_error('تعداد ت:\n    أ = "نص"\n', ArabiRuntimeError, 'عددًا صحيحًا')

    def test_enum_typename(self):
        self.assertEqual(run_arabi(self.ENUM_SRC + 'اطبع(نوع(يوم))'), 'تعداد\n')


class TestProperties(unittest.TestCase):
    """خاصية محسوبة داخل صنف"""

    RECT_SRC = (
        'صنف مستطيل:\n'
        '    دالة إنشاء(العرض، الارتفاع):\n'
        '        هذا.العرض = العرض\n'
        '        هذا.الارتفاع = الارتفاع\n'
        '    خاصية المساحة:\n'
        '        أعد هذا.العرض * هذا.الارتفاع\n'
        '    خاصية المحيط:\n'
        '        أعد (هذا.العرض + هذا.الارتفاع) * ٢\n'
    )

    def test_property_evaluation(self):
        self.assertEqual(
            run_arabi(self.RECT_SRC + 'اطبع(مستطيل(٤، ٥).المساحة)'), '20\n')

    def test_property_updates_dynamically(self):
        out = run_arabi(self.RECT_SRC
                        + 'م = مستطيل(٤، ٥)\n'
                          'م.العرض = ١٠\n'
                          'اطبع(م.المساحة)')
        self.assertEqual(out, '50\n')

    def test_property_in_expression(self):
        self.assertEqual(
            run_arabi(self.RECT_SRC
                      + 'اطبع(مستطيل(٢، ٣).المساحة + مستطيل(١، ١).المحيط)'),
            '10\n')

    def test_property_not_callable(self):
        expect_error(self.RECT_SRC + 'م = مستطيل(٢، ٣)\nم.المساحة()',
                     ArabiRuntimeError, 'خاصية محسوبة')

    def test_property_inherited(self):
        src = (self.RECT_SRC
               + 'صنف مربع من مستطيل:\n'
                 '    دالة إنشاء(طول):\n'
                 '        الأصل.إنشاء(هذا، طول، طول)\n')
        self.assertEqual(run_arabi(src + 'اطبع(مربع(٦).المساحة)'), '36\n')

    def test_property_with_condition(self):
        src = ('صنف شخص:\n'
               '    دالة إنشاء(العمر):\n'
               '        هذا.العمر = العمر\n'
               '    خاصية مرحلة:\n'
               '        أعد لو هذا.العمر < ١٨: "طفل" وإلا "بالغ"\n')
        out = run_arabi(src + 'اطبع(شخص(١٠).مرحلة)\nاطبع(شخص(٣٠).مرحلة)')
        self.assertEqual(out, 'طفل\nبالغ\n')

    def test_property_can_read_fields(self):
        self.assertEqual(
            run_arabi(self.RECT_SRC + 'م = مستطيل(٣، ٤)\nاطبع(م.المحيط)'), '14\n')

    def test_duplicate_member_name(self):
        src = ('صنف ص:\n'
               '    دالة ط():\n'
               '        أعد ١\n'
               '    خاصية ط:\n'
               '        أعد ٢\n')
        expect_error(src, ArabiRuntimeError, 'تكرار')


class TestOperatorOverload(unittest.TestCase):
    """تحميل العوامل عبر الطرق الخاصة"""

    VEC_SRC = (
        'صنف متجه:\n'
        '    دالة إنشاء(س، ص):\n'
        '        هذا.س = س\n'
        '        هذا.ص = ص\n'
        '    دالة اجمع(آخر):\n'
        '        أعد متجه(هذا.س + آخر.س، هذا.ص + آخر.ص)\n'
        '    دالة اطرح(آخر):\n'
        '        أعد متجه(هذا.س - آخر.س، هذا.ص - آخر.ص)\n'
        '    دالة اضرب(معامل):\n'
        '        لو نوع(معامل) == "عدد صحيح":\n'
        '            أعد متجه(هذا.س * معامل، هذا.ص * معامل)\n'
        '        أعد متجه(هذا.س * معامل.س، هذا.ص * معامل.ص)\n'
        '    دالة نص():\n'
        '        أعد ق"({هذا.س}، {هذا.ص})"\n'
        '    دالة يساوي(آخر):\n'
        '        أعد هذا.س == آخر.س و هذا.ص == آخر.ص\n'
    )

    def test_add(self):
        out = run_arabi(self.VEC_SRC + 'اطبع(متجه(١، ٢) + متجه(٣، ٤))')
        self.assertEqual(out, '(4، 6)\n')

    def test_subtract(self):
        out = run_arabi(self.VEC_SRC + 'اطبع(متجه(٥، ٧) - متجه(١، ٢))')
        self.assertEqual(out, '(4، 5)\n')

    def test_multiply_by_object(self):
        out = run_arabi(self.VEC_SRC + 'اطبع(متجه(٢، ٣) * متجه(٤، ٥))')
        self.assertEqual(out, '(8، 15)\n')

    def test_multiply_by_number(self):
        out = run_arabi(self.VEC_SRC + 'اطبع(متجه(٢، ٣) * ٣)')
        self.assertEqual(out, '(6، 9)\n')

    def test_reflected_number_first(self):
        # العدد على اليسار والكائن على اليمين — عكس العملية يعمل أيضًا
        out = run_arabi(self.VEC_SRC + 'اطبع(٣ * متجه(٢، ٣))')
        self.assertEqual(out, '(6، 9)\n')

    def test_display_uses_special_text(self):
        self.assertEqual(run_arabi(self.VEC_SRC + 'اطبع(نص(متجه(١، ٢)))'),
                         '(1، 2)\n')

    def test_equality_operator(self):
        out = run_arabi(self.VEC_SRC + 'أ = متجه(١، ٢)\n'
                       'اطبع(أ == متجه(١، ٢))\nاطبع(أ == متجه(٩، ٩))')
        self.assertEqual(out, 'صح\nخطأ\n')

    def test_not_equal(self):
        out = run_arabi(self.VEC_SRC + 'اطبع(متجه(١، ٢) != متجه(٣، ٤))')
        self.assertEqual(out, 'صح\n')

    def test_custom_text_in_fstring(self):
        out = run_arabi(self.VEC_SRC + 'أ = متجه(١، ٢)\nاطبع(ق"المتجه {أ}")')
        self.assertEqual(out, 'المتجه (1، 2)\n')

    def test_custom_len(self):
        src = ('صنف كيس:\n'
               '    دالة إنشاء(عناصر):\n'
               '        هذا.عناصر = عناصر\n'
               '    دالة طول():\n'
               '        أعد طول(هذا.عناصر)\n')
        self.assertEqual(run_arabi(src + 'اطبع(طول(كيس([١، ٢، ٣])))'), '3\n')

    def test_custom_len_must_return_int(self):
        src = ('صنف ص:\n'
               '    دالة طول():\n'
               '        أعد "نص"\n')
        expect_error(src + 'طول(ص())', ArabiRuntimeError, 'عددًا صحيحًا')

    def test_index_get(self):
        src = ('صنف ص:\n'
               '    دالة إنشاء(عناصر):\n'
               '        هذا.عناصر = عناصر\n'
               '    دالة فهرس(م):\n'
               '        أعد هذا.عناصر[م]\n'
               '    دالة عيّن_فهرس(م، قيمة):\n'
               '        هذا.عناصر[م] = قيمة\n')
        out = run_arabi(src + 'ك = ص([١، ٢])\nاطبع(ك[٠])\nك[٠] = ٩\nاطبع(ك[٠])')
        self.assertEqual(out, '1\n9\n')

    def test_index_without_method(self):
        expect_error('صنف ص:\n    تجاهل\nاطبع(ص()[٠])',
                     ArabiRuntimeError, 'فهرس')

    def test_contains(self):
        src = ('صنف ص:\n'
               '    دالة إنشاء(عناصر):\n'
               '        هذا.عناصر = عناصر\n'
               '    دالة يحتوي(قيمة):\n'
               '        أعد قيمة في هذا.عناصر\n')
        out = run_arabi(src + 'لو ٢ في ص([١، ٢، ٣]):\n    اطبع("موجود")')
        self.assertEqual(out, 'موجود\n')

    def test_comparison_operators(self):
        src = ('صنف صندوق:\n'
               '    دالة إنشاء(حجم):\n'
               '        هذا.حجم = حجم\n'
               '    دالة أصغر_من(آخر):\n'
               '        أعد هذا.حجم < آخر.حجم\n'
               '    دالة أكبر_من(آخر):\n'
               '        أعد هذا.حجم > آخر.حجم\n')
        out = run_arabi(src + 'اطبع(صندوق(٣) < صندوق(٥))\n'
                        'اطبع(صندوق(١٠) > صندوق(٥))')
        self.assertEqual(out, 'صح\nصح\n')

    def test_unary_minus(self):
        src = ('صنف ص:\n'
               '    دالة إنشاء(قيمة):\n'
               '        هذا.قيمة = قيمة\n'
               '    دالة سالب():\n'
               '        أعد ص(-هذا.قيمة)\n'
               '    دالة نص():\n'
               '        أعد نص(هذا.قيمة)\n')
        self.assertEqual(run_arabi(src + 'اطبع(-ص(٥))'), '-5\n')

    def test_no_overload_falls_back_to_error(self):
        expect_error('صنف ص:\n    تجاهل\nاطبع(ص() + ١)',
                     ArabiRuntimeError, 'لا يمكن جمع')


class TestGlobalStmt(unittest.TestCase):
    """جملة عالمي"""

    def test_modify_existing_global(self):
        out = run_arabi('العداد = ٠\n'
                        'دالة زيّن():\n'
                        '    عالمي العداد\n'
                        '    العداد += ١\n'
                        'زيّن()\n'
                        'زيّن()\n'
                        'اطبع(العداد)')
        self.assertEqual(out, '2\n')

    def test_create_global_from_function(self):
        out = run_arabi('دالة عرّف():\n'
                        '    عالمي جديد\n'
                        '    جديد = ٤٢\n'
                        'عرّف()\n'
                        'اطبع(جديد)')
        self.assertEqual(out, '42\n')

    def test_multiple_names(self):
        out = run_arabi('أ = ١\nب = ١\n'
                        'دالة صفر():\n'
                        '    عالمي أ، ب\n'
                        '    أ = ٠\n'
                        '    ب = ٠\n'
                        'صفر()\n'
                        'اطبع(أ + ب)')
        self.assertEqual(out, '0\n')

    def test_without_global_new_var_stays_local(self):
        # بدون 'عالمي' المتغير الجديد يبقى محليًا في الدالة
        expect_error('دالة ص():\n    محلي = ٥\nص()\nاطبع(محلي)',
                     ArabiRuntimeError, 'غير معرّف')

    def test_existing_global_modified_either_way(self):
        # لغة عربي تعدل المتغير الموجود في أي نطاق — 'عالمي' للتوثيق والإنشاء
        out = run_arabi('العداد = ٠\n'
                        'دالة زيّن():\n'
                        '    العداد = ٩٩\n'
                        'زيّن()\n'
                        'اطبع(العداد)')
        self.assertEqual(out, '99\n')


class TestAssertStmt(unittest.TestCase):
    """جملة تحقق"""

    def test_passes_when_true(self):
        self.assertEqual(run_arabi('تحقق ١ + ١ == ٢\nاطبع("تم")'), 'تم\n')

    def test_fails_with_message(self):
        exc = expect_error('تحقق ١ > ٢، "الأرقام معكوسة"',
                           ArabiRuntimeError, 'فشل التحقق: الأرقام معكوسة')
        self.assertIsNotNone(exc)

    def test_fails_without_message(self):
        expect_error('تحقق خطأ', ArabiRuntimeError, 'فشل التحقق')

    def test_catchable_in_try(self):
        out = run_arabi('جرب:\n    تحقق ١ > ٢\nباستثناء:\n    اطبع("أُمسك")')
        self.assertEqual(out, 'أُمسك\n')


class TestDeleteStmt(unittest.TestCase):
    """جملة احذف"""

    def test_delete_variable(self):
        self.assertEqual(
            run_arabi('أ = ١\nاحذف أ\nأ = ٢\nاطبع(أ)'), '2\n')

    def test_delete_undefined_variable(self):
        expect_error('احذف مجهول', ArabiRuntimeError, 'غير معرّف')

    def test_delete_list_element(self):
        out = run_arabi('ل = [١، ٢، ٣]\nاحذف ل[٠]\nاطبع(ل)')
        self.assertEqual(out, '[2، 3]\n')

    def test_delete_list_index_out_of_range(self):
        expect_error('ل = [١]\nاحذف ل[٥]', ArabiRuntimeError, 'خارج النطاق')

    def test_delete_dict_key(self):
        out = run_arabi('ق = {"أ": ١، "ب": ٢}\nاحذف ق["أ"]\nاطبع(ق)')
        self.assertEqual(out, '{ب: 2}\n')

    def test_delete_missing_dict_key(self):
        expect_error('ق = {"أ": ١}\nاحذف ق["مفقود"]',
                     ArabiRuntimeError, 'غير موجود')

    def test_delete_object_attribute(self):
        out = run_arabi('صنف ص:\n    دالة إنشاء():\n        هذا.سمة = ١\n'
                        'ك = ص()\nاحذف ك.سمة\nاطبع(نوع(ك))')
        self.assertEqual(out, 'كائن\n')

    def test_delete_attribute_then_read_fails(self):
        expect_error('صنف ص:\n    دالة إنشاء():\n        هذا.سمة = ١\n'
                     'ك = ص()\nاحذف ك.سمة\nاطبع(ك.سمة)',
                     ArabiRuntimeError, 'لا يحتوي')

    def test_deleted_variable_read_fails(self):
        expect_error('أ = ١\nاحذف أ\nاطبع(أ)', ArabiRuntimeError, 'غير معرّف')


class TestCustomExceptions(unittest.TestCase):
    """الصنف المدمج استثناء والأخطاء المخصصة"""

    ERR_SRC = (
        'صنف خطأ_دفع من استثناء:\n'
        '    دالة تفاصيل():\n'
        '        أعد ق"سبب الفشل: {هذا.رسالة}"\n'
    )

    def test_raise_and_bind(self):
        out = run_arabi(self.ERR_SRC
                        + 'جرب:\n'
                          '    ارفع خطأ_دفع("الرصيد غير كافٍ")\n'
                          'باستثناء هـ:\n'
                          '    اطبع(هـ.رسالة)')
        self.assertEqual(out, 'الرصيد غير كافٍ\n')

    def test_custom_methods_on_error(self):
        self.assertEqual(
            run_arabi(self.ERR_SRC
                      + 'جرب:\n'
                        '    ارفع خطأ_دفع("بطاقة منتهية")\n'
                        'باستثناء هـ:\n'
                        '    اطبع(هـ.تفاصيل())'),
            'سبب الفشل: بطاقة منتهية\n')

    def test_display_shows_message(self):
        out = run_arabi(self.ERR_SRC
                        + 'جرب:\n    ارفع خطأ_دفع("مرفوض")\nباستثناء هـ:\n'
                          '    اطبع(هـ)')
        self.assertEqual(out, 'خطأ_دفع: مرفوض\n')

    def test_builtin_error_class(self):
        out = run_arabi('جرب:\n    ارفع استثناء("مشكلة عامة")\n'
                        'باستثناء هـ:\n    اطبع(هـ.رسالة)')
        self.assertEqual(out, 'مشكلة عامة\n')

    def test_error_propagates_out_of_try(self):
        exc = expect_error(self.ERR_SRC + 'ارفع خطأ_دفع("انفجار")',
                           ArabiError, 'خطأ_دفع: انفجار')
        self.assertIsNotNone(exc)

    def test_error_class_chain(self):
        out = run_arabi('صنف خطأ_أ من استثناء:\n    تجاهل\n'
                        'صنف خطأ_ب من خطأ_أ:\n    تجاهل\n'
                        'جرب:\n    ارفع خطأ_ب("عميق")\n'
                        'باستثناء هـ:\n    اطبع(هـ.رسالة)')
        self.assertEqual(out, 'عميق\n')

    def test_error_with_non_string_message(self):
        out = run_arabi('جرب:\n    ارفع استثناء(٤٠٤)\n'
                        'باستثناء هـ:\n    اطبع(هـ.رسالة)')
        self.assertEqual(out, '404\n')

    def test_binding_takes_runtime_message(self):
        out = run_arabi('جرب:\n    اطبع(١ / ٠)\nباستثناء هـ:\n'
                        '    اطبع(نوع(هـ) == "نص")')
        self.assertEqual(out, 'صح\n')

    def test_raise_plain_string_unchanged(self):
        expect_error('ارفع "رسالة عادية"', ArabiRuntimeError, 'رسالة عادية')

    def test_exception_available_in_module(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as td:
            mod = os.path.join(td, 'وحدة_أخطاء.عربي')
            with open(mod, 'w', encoding='utf-8') as f:
                f.write('صنف خطأ_وحدة من استثناء:\n    تجاهل\n')
            main = os.path.join(td, 'رئيسي.عربي')
            with open(main, 'w', encoding='utf-8') as f:
                f.write('استورد وحدة_أخطاء\n'
                        'جرب:\n'
                        '    ارفع وحدة_أخطاء.خطأ_وحدة("من وحدة")\n'
                        'باستثناء هـ:\n'
                        '    اطبع(هـ.رسالة)\n')
            with open(main, encoding='utf-8') as f:
                out = run_code(f.read(), script_dir=td)
        self.assertEqual(out, 'من وحدة\n')


class TestRandomModule(unittest.TestCase):
    """وحدة عشوائية"""

    def test_seed_makes_deterministic(self):
        out = run_arabi('عشوائية.بذرة(٧)\nأ = عشوائية.صحيح(١، ١٠٠)\n'
                        'عشوائية.بذرة(٧)\nب = عشوائية.صحيح(١، ١٠٠)\n'
                        'اطبع(أ == ب)')
        self.assertEqual(out, 'صح\n')

    def test_int_in_range(self):
        out = run_arabi('عشوائية.بذرة(١)\nق = عشوائية.صحيح(٥، ٥)\nاطبع(ق)')
        self.assertEqual(out, '5\n')

    def test_choice(self):
        out = run_arabi('عشوائية.بذرة(٣)\nق = عشوائية.اختيار(["أ"، "ب"، "ج"])\n'
                        'اطبع(ق == "أ" أو ق == "ب" أو ق == "ج")')
        self.assertEqual(out, 'صح\n')

    def test_choice_empty(self):
        expect_error('عشوائية.اختيار([])', ArabiRuntimeError, 'فارغ')

    def test_shuffle_returns_new_list(self):
        out = run_arabi('عشوائية.بذرة(١)\nأصل = [١، ٢، ٣، ٤، ٥]\n'
                        'مخلوق = عشوائية.خلط(أصل)\n'
                        'اطبع(طول(مخلوق) == ٥ و طول(أصل) == ٥)')
        self.assertEqual(out, 'صح\n')

    def test_sample_size(self):
        out = run_arabi('عشوائية.بذرة(٢)\nع = عشوائية.عينة(مدى(١٠)، ٣)\n'
                        'اطبع(طول(ع))')
        self.assertEqual(out, '3\n')

    def test_sample_too_big(self):
        expect_error('عشوائية.عينة([١، ٢]، ٥)', ArabiRuntimeError, 'العينة')

    def test_float_between_zero_and_one(self):
        out = run_arabi('عشوائية.بذرة(١)\nق = عشوائية.عشري()\n'
                        'اطبع(ق >= ٠ و ق < ١)')
        self.assertEqual(out, 'صح\n')


class TestSystemModule(unittest.TestCase):
    """وحدة نظام"""

    def test_cwd_is_string(self):
        self.assertEqual(run_arabi('اطبع(نوع(نظام.مجلد_العمل()))'), 'نص\n')

    def test_env_var(self):
        import os
        os.environ['ARABI_TEST_VAR'] = '١٢٣'
        self.assertEqual(run_arabi('اطبع(نظام.متغير("ARABI_TEST_VAR"))'),
                         '١٢٣\n')

    def test_env_var_default(self):
        self.assertEqual(
            run_arabi('اطبع(نظام.متغير("ARABI_MISSING_XYZ"، "افتراضي"))'),
            'افتراضي\n')

    def test_platform_string(self):
        out = run_arabi('اطبع(نظام.النظام() != "")')
        self.assertEqual(out, 'صح\n')

    def test_join_paths(self):
        self.assertEqual(run_arabi('اطبع(نظام.فصل("مجلد"، "ملف.عربي"))').strip(),
                          os.path.join('مجلد', 'ملف.عربي'))

    def test_basename_dirname(self):
        out = run_arabi('اطبع(نظام.اسم_الملف("أ/ب/ج.عربي"))\n'
                        'اطبع(نظام.المجلد("أ/ب/ج.عربي"))')
        self.assertEqual(out.splitlines()[0], 'ج.عربي')

    def test_listdir_missing(self):
        expect_error('نظام.ملفات_في("مجلد_غير_موجود_سزا")',
                     ArabiRuntimeError, 'غير موجود')

    def test_mkdir_and_isdir(self, td=None):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            target = os.path.join(td, 'مجلد_جديد').replace('\\', '/')
            out = run_arabi(f'نظام.انشاء_مجلد("{target}")\n'
                            f'اطبع(نظام.مجلد_موجود("{target}"))')
            self.assertEqual(out, 'صح\n')


class TestRegexModule(unittest.TestCase):
    """وحدة تنظيم"""

    def test_find(self):
        self.assertEqual(
            run_arabi(r'اطبع(تنظيم.يجد("[٠-٩]+"، "عندي ٤٢ تفاحة"))'), '٤٢\n')

    def test_find_none(self):
        self.assertEqual(
            run_arabi(r'اطبع(تنظيم.يجد("[٠-٩]+"، "لا أرقام هنا"))'), 'ولا شيء\n')

    def test_findall(self):
        self.assertEqual(
            run_arabi(r'اطبع(تنظيم.كل_المطابقات("\d+"، "أ ١ ب ٢٢ ج ٣٣٣"))'),
            '[١، ٢٢، ٣٣٣]\n')

    def test_sub(self):
        self.assertEqual(
            run_arabi(r'اطبع(تنظيم.يستبدل("\s+"، " "، "نص    متباعد  جدًا"))'),
            'نص متباعد جدًا\n')

    def test_split(self):
        self.assertEqual(
            run_arabi(r'اطبع(تنظيم.ينقسم("[،،]\s*"، "واحد، اثنان، ثلاثة"))'),
            '[واحد، اثنان، ثلاثة]\n')

    def test_fullmatch(self):
        out = run_arabi(r'اطبع(تنظيم.يطابق("[٠-٩]+"، "١٢٣"))' + '\n'
                        + r'اطبع(تنظيم.يطابق("[٠-٩]+"، "١٢٣أ"))')
        self.assertEqual(out, 'صح\nخطأ\n')

    def test_match_start(self):
        out = run_arabi(r'اطبع(تنظيم.يبدأ("مرحبا"، "مرحبا بالعالم"))')
        self.assertEqual(out, 'صح\n')

    def test_invalid_pattern(self):
        expect_error(r'تنظيم.يجد("[مفتوح"، "نص")',
                     ArabiRuntimeError, 'نمط غير صالح')

    def test_non_string_text(self):
        expect_error('تنظيم.يجد("أ"، ١٢٣)', ArabiRuntimeError, 'نصًا')


class TestNetworkModule(unittest.TestCase):
    """وحدة شبكة — اختبارات بلا اتصال فعلي (التحقق من المدخلات)"""

    def test_requires_http(self):
        expect_error('شبكة.اطلب("ftp://مثال.كوم")',
                     ArabiRuntimeError, 'http')

    def test_requires_string_url(self):
        expect_error('شبكة.اطلب(١٢٣)', ArabiRuntimeError, 'نصيًا')

    def test_invalid_method(self):
        expect_error('شبكة.اطلب("https://مثال.كوم"، "رفع")',
                     ArabiRuntimeError, 'طريقة الطلب')

    def test_invalid_headers(self):
        expect_error('شبكة.اطلب("https://مثال.كوم"، "GET"، "ليست قاموس")',
                     ArabiRuntimeError, 'قاموسًا')

    def test_invalid_data(self):
        expect_error('شبكة.اطلب("https://مثال.كوم"، "GET"، {}، ١٢٣)',
                     ArabiRuntimeError, 'البيانات')

    def test_wrong_timeout(self):
        expect_error('شبكة.اطلب("https://مثال.كوم"، "GET"، {}، ولا شيء، -١)',
                     ArabiRuntimeError, 'المهلة')


class TestConvertModule(unittest.TestCase):
    """وحدة تحويل — التفقيط والأرقام العربية"""

    def test_words_zero(self):
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(٠))'), 'صفر\n')

    def test_words_single_digits(self):
        out = run_arabi('اطبع(تحويل.كلمات(١))\nاطبع(تحويل.كلمات(٩))')
        self.assertEqual(out, 'واحد\nتسعة\n')

    def test_words_teens(self):
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(١١))'), 'أحد عشر\n')
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(١٩))'), 'تسعة عشر\n')

    def test_words_tens(self):
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(٢٠))'), 'عشرون\n')
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(٦٥))'), 'خمسة وستون\n')

    def test_words_hundreds(self):
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(١٠٠))'), 'مئة\n')
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(٢٠٠))'), 'مئتان\n')
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(٢٠٥))'), 'مئتان وخمسة\n')

    def test_words_thousands(self):
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(١٠٠٠))'), 'ألف\n')
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(٢٠٠٠))'), 'ألفان\n')
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(٣٠٠٠))'), 'ثلاثة آلاف\n')
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(١٢٣٤))'),
                         'ألف ومئتان وأربعة وثلاثون\n')
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(١١٠٠٠))'),
                         'أحد عشر ألفًا\n')
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(١٠٠٠٠٠))'), 'مئة ألف\n')

    def test_words_millions(self):
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(١٠٠٠٠٠٠))'), 'مليون\n')
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(٢٠٠٠٠٠٠))'), 'مليونان\n')
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(٣٠٠٠٠٠٠))'), 'ثلاثة ملايين\n')
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(١٠٠٠٠٠٠٠))'), 'عشرة ملايين\n')

    def test_words_billions(self):
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(١٠٠٠٠٠٠٠٠٠))'), 'مليار\n')
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(٢٠٠٠٠٠٠٠٠٠))'), 'ملياران\n')

    def test_words_negative(self):
        self.assertEqual(run_arabi('اطبع(تحويل.كلمات(-٥))'), 'سالب خمسة\n')

    def test_words_rejects_float(self):
        expect_error('تحويل.كلمات(١.٥)', ArabiRuntimeError, 'عددًا صحيحًا')

    def test_words_rejects_too_big(self):
        expect_error('تحويل.كلمات(١٠٠٠٠٠٠٠٠٠٠٠٠٠)',
                     ArabiRuntimeError, 'كبير جدًا')

    def test_eastern_digits(self):
        self.assertEqual(
            run_arabi('اطبع(تحويل.إلى_شرقية(1234567890))'), '١٢٣٤٥٦٧٨٩٠\n')
        self.assertEqual(
            run_arabi('اطبع(تحويل.إلى_شرقية("سنة ٢٠٢٦"))'), 'سنة ٢٠٢٦\n')

    def test_western_digits(self):
        self.assertEqual(
            run_arabi('اطبع(تحويل.إلى_غربية("١٢٣٤٥"))'), '12345\n')

    def test_roundtrip(self):
        self.assertEqual(
            run_arabi('اطبع(تحويل.إلى_غربية(تحويل.إلى_شرقية("٧٨٩")))'),
            '789\n')


class TestMathTimeExpansion(unittest.TestCase):
    """توسيع وحدتي رياضيات ووقت"""

    def test_gcd(self):
        self.assertEqual(
            run_arabi('اطبع(رياضيات.مشترك_الأكبر(١٢، ١٨))'), '6\n')

    def test_lcm(self):
        self.assertEqual(
            run_arabi('اطبع(رياضيات.مشترك_الأصغر(٤، ٦))'), '12\n')

    def test_lcm_with_zero(self):
        self.assertEqual(
            run_arabi('اطبع(رياضيات.مشترك_الأصغر(٠، ٥))'), '0\n')

    def test_sign(self):
        out = run_arabi('اطبع(رياضيات.علامة(-٧))\n'
                        'اطبع(رياضيات.علامة(٠))\n'
                        'اطبع(رياضيات.علامة(٣))')
        self.assertEqual(out, '-1\n0\n1\n')

    def test_log10(self):
        self.assertEqual(
            run_arabi('اطبع(رياضيات.لوغاريتم_عشري(١٠٠٠))'), '3.0\n')

    def test_now_structure(self):
        out = run_arabi('الآن = وقت.الآن()\n'
                        'اطبع(نوع(الآن))\n'
                        'اطبع(الآن["السنة"] >= ٢٠٢٦)')
        self.assertEqual(out.splitlines()[0], 'قاموس')
        self.assertEqual(out.splitlines()[1], 'صح')

    def test_format(self):
        out = run_arabi('ن = وقت.تنسيق("سنة %س شهر %ش يوم %ي")\n'
                        'اطبع("سنة" في ن و "شهر" في ن)')
        self.assertEqual(out, 'صح\n')

    def test_time_still_works(self):
        out = run_arabi('اطبع(وقت.زمن() > ٠)')
        self.assertEqual(out, 'صح\n')


# ================== الإصدار 1.6: الوحدات والأدوات الجديدة ==================

class TestTestsModule(unittest.TestCase):
    """وحدة اختبارات — إطار الاختبارات داخل اللغة."""

    def test_passing_flow(self):
        out = run_arabi(
            'اختبارات.ابدأ("مجموعتي")\n'
            'اختبارات.يساوي(١ + ١، ٢، "الجمع")\n'
            'اختبارات.يختلف(١، ٢)\n'
            'اختبارات.يصح("نص")\n'
            'اختبارات.يخطئ(ولا شيء)\n'
            'اختبارات.ملخص()\n')
        self.assertIn('== مجموعتي ==', out)
        self.assertIn('✓ الجمع', out)
        self.assertIn('✓ الاختبار رقم 2', out)
        self.assertIn('== الملخص: 4 ناجحة، 0 فاشلة من 4 اختبارًا ==', out)

    def test_failure_output(self):
        out = run_arabi('اختبارات.يساوي(١، ٢، "فاشل")\nاختبارات.ملخص()\n')
        self.assertIn('✗ فاشل — المتوقع: 2، الفعلي: 1', out)
        self.assertIn('1 فاشلة', out)

    def test_summary_dict_auto_start(self):
        out = run_arabi(
            'ن = اختبارات.ملخص()\n'
            'اطبع(ن["ناجح"]، ن["فاشل"]، ن["الكل"])\n')
        self.assertEqual(
            out, '== الملخص: 0 ناجحة، 0 فاشلة من 0 اختبارًا ==\n0 0 0\n')

    def test_eq_with_lists_and_dicts(self):
        out = run_arabi(
            'اختبارات.يساوي([١، ٢]، [١، ٢]، "قوائم")\n'
            'اختبارات.يساوي({أ: ١}، {"أ": ١}، "قواميس")\n'
            'اختبارات.ملخص()\n')
        self.assertIn('2 ناجحة', out)

    def test_raises_passes_on_error(self):
        out = run_arabi('اختبارات.يرفع(دالة() => عدد("خطأ")، "يرفع خطأ")\n')
        self.assertIn('✓ يرفع خطأ', out)

    def test_raises_fails_without_error(self):
        out = run_arabi('اختبارات.يرفع(دالة() => ٥، "لا يرفع")\n')
        self.assertIn('✗ لا يرفع — لم ترفع الدالة أي خطأ', out)

    def test_raises_accepts_user_class_error(self):
        out = run_arabi(
            'صنف خطأي من استثناء:\n'
            '    تجاهل\n'
            'دالة رامي():\n'
            '    ارفع خطأي("بوم")\n'
            'اختبارات.يرفع(رامي، "خطأ مخصص")\n')
        self.assertIn('✓ خطأ مخصص', out)

    def test_state_resets_on_start(self):
        out = run_arabi(
            'اختبارات.ابدأ()\n'
            'اختبارات.يصح(صح)\n'
            'اختبارات.ابدأ("جديدة")\n'
            'ن = اختبارات.ملخص()\n'
            'اطبع(ن["الكل"])\n')
        self.assertTrue(out.rstrip().endswith('0'))

    def test_arg_validation(self):
        expect_error('اختبارات.يساوي(١)', ArabiRuntimeError, 'تقبل')
        expect_error('اختبارات.ابدأ(٥)', ArabiRuntimeError, 'نصًا')
        expect_error('اختبارات.يرفع(٥)', ArabiRuntimeError, 'دالة')
        expect_error('اختبارات.يصح(صح، ٥)', ArabiRuntimeError, 'نصًا')


class TestServerModule(unittest.TestCase):
    """وحدة خادم — خوادم ويب حقيقية بلغة عربي."""

    ROUTES = (
        'دالة معالج(طلب):\n'
        '    لو طلب["المسار"] == "/":\n'
        '        أعد "الصفحة الرئيسية"\n'
        '    وإلا إذا طلب["المسار"] == "/بحث":\n'
        '        أعد "نتائج: " + طلب["المعاملات"]["كلمة"]\n'
        '    أعد {الحالة: 404، النص: "غير موجودة"}\n'
    )

    def tearDown(self):
        run_arabi('جرب:\n    خادم.قف()\nباستثناء:\n    تجاهل\n')

    def test_roundtrip_get(self):
        out = run_arabi(
            self.ROUTES +
            'المنفذ = خادم.ابدأ(٠، معالج)\n'
            'اطبع(المنفذ > ٠)\n'
            'ر = شبكة.اطلب("http://127.0.0.1:" + نص(المنفذ) + "/")\n'
            'اطبع(ر["الحالة"]، ر["النص"])\n'
            'خادم.قف()\n')
        self.assertIn('صح', out)
        self.assertIn('200 الصفحة الرئيسية', out)

    def test_query_params_arabic(self):
        out = run_arabi(
            self.ROUTES +
            'المنفذ = خادم.ابدأ(٠، معالج)\n'
            'ر = شبكة.اطلب("http://127.0.0.1:" + نص(المنفذ) + "/بحث؟كلمة=سلام")\n'
            'اطبع(ر["النص"])\n'
            'خادم.قف()\n')
        self.assertIn('نتائج: سلام', out)

    def test_post_body(self):
        out = run_arabi(
            'دالة معالج(طلب):\n'
            '    أعد "تحية " + طلب["النص"]\n'
            'المنفذ = خادم.ابدأ(٠، معالج)\n'
            'ر = شبكة.اطلب("http://127.0.0.1:" + نص(المنفذ)، "POST"، {}، "زائر")\n'
            'اطبع(ر["النص"])\n'
            'خادم.قف()\n')
        self.assertIn('تحية زائر', out)

    def test_status_and_headers(self):
        out = run_arabi(
            'دالة معالج(طلب):\n'
            '    أعد {الحالة: 201، النص: "أُنشئ"، الترويسات: {نوع_المحتوى: "text/plain"}}\n'
            'المنفذ = خادم.ابدأ(٠، معالج)\n'
            'ر = شبكة.اطلب("http://127.0.0.1:" + نص(المنفذ) + "/")\n'
            'اطبع(ر["الحالة"]، ر["الترويسات"]["Content-Type"])\n'
            'خادم.قف()\n')
        self.assertIn('201 text/plain', out)

    def test_404_from_handler(self):
        out = run_arabi(
            self.ROUTES +
            'المنفذ = خادم.ابدأ(٠، معالج)\n'
            'ر = شبكة.اطلب("http://127.0.0.1:" + نص(المنفذ) + "/مفقود")\n'
            'اطبع(ر["الحالة"])\n'
            'خادم.قف()\n')
        self.assertIn('404', out)

    def test_restart_after_stop(self):
        out = run_arabi(
            'دالة معالج(طلب):\n'
            '    أعد "أهلا"\n'
            'م١ = خادم.ابدأ(٠، معالج)\n'
            'خادم.قف()\n'
            'م٢ = خادم.ابدأ(٠، معالج)\n'
            'اطبع(م١ > ٠ و م٢ > ٠)\n'
            'خادم.قف()\n')
        self.assertIn('صح', out)

    def test_double_start_error(self):
        out = run_arabi(
            'دالة معالج(طلب):\n'
            '    أعد ""\n'
            'خادم.ابدأ(٠، معالج)\n')
        expect_error(out if False else
                     'دالة معالج(طلب):\n    أعد ""\n'
                     'خادم.ابدأ(٠، معالج)\nخادم.ابدأ(٠، معالج)\n',
                     ArabiRuntimeError, 'يعمل بالفعل')

    def test_stop_and_wait_without_server(self):
        expect_error('خادم.قف()', ArabiRuntimeError, 'لا يوجد خادم')
        expect_error('خادم.انتظر()', ArabiRuntimeError, 'لا يوجد خادم')

    def test_invalid_port_and_handler(self):
        body = 'دالة معالج(طلب):\n    أعد ""\n'
        expect_error(body + 'خادم.ابدأ(٧٠٠٠٠، معالج)\n',
                     ArabiRuntimeError, '٦٥٥٣٥')
        expect_error(body + 'خادم.ابدأ(٠، ٥)\n',
                     ArabiRuntimeError, 'دالة')


class TestSysAdditions(unittest.TestCase):
    """إضافات وحدة نظام: وسيطات وخروج."""

    def test_args(self):
        old = sys.argv
        try:
            sys.argv = ['arabi.py', 'برنامج.عربي', 'أول', 'ثانٍ']
            out = run_arabi('اطبع(نظام.وسيطات())')
            self.assertEqual(out, '[أول، ثانٍ]\n')
        finally:
            sys.argv = old

    def test_exit_with_code(self):
        with self.assertRaises(SystemExit) as cm:
            run_arabi('نظام.خروج(٣)')
        self.assertEqual(cm.exception.code, 3)

    def test_exit_default(self):
        with self.assertRaises(SystemExit) as cm:
            run_arabi('نظام.خروج()')
        self.assertEqual(cm.exception.code, 0)

    def test_exit_type_validation(self):
        expect_error('نظام.خروج("نص")', ArabiRuntimeError, 'عددًا صحيحًا')
        expect_error('نظام.خروج(صح)', ArabiRuntimeError, 'عددًا صحيحًا')


class TestDictBareKeys(unittest.TestCase):
    """مفاتيح القواميس بلا اقتباس — {الحالة: 200} ≡ {"الحالة": 200}."""

    def test_bare_keys_basic(self):
        out = run_arabi(
            'شخص = {الاسم: "خالد"، العمر: ٣٠}\n'
            'اطبع(شخص["الاسم"]، شخص["العمر"])\n')
        self.assertEqual(out, 'خالد 30\n')

    def test_mixed_keys(self):
        out = run_arabi(
            'د = {أ: ١، "ب": ٢}\n'
            'اطبع(د["أ"] + د["ب"])\n')
        self.assertEqual(out, '3\n')

    def test_nested_bare_keys(self):
        out = run_arabi(
            'ر = {الحالة: 200، البيانات: {الاسم: "نورة"}}\n'
            'اطبع(ر["البيانات"]["الاسم"])\n')
        self.assertEqual(out, 'نورة\n')

    def test_variable_value_not_affected(self):
        out = run_arabi(
            'مفتاح = "ديناميكي"\n'
            'د = {مفتاح_ثابت: ١}\n'
            'اطبع(د["مفتاح_ثابت"]، مفتاح)\n')
        self.assertEqual(out, '1 ديناميكي\n')


class TestLibrariesPath(unittest.TestCase):
    """مجلد مكتبات/ في مسار البحث عن الوحدات."""

    def test_import_from_libraries_dir(self):
        with tempfile.TemporaryDirectory() as d:
            lib_dir = os.path.join(d, 'مكتبات')
            os.makedirs(lib_dir)
            with open(os.path.join(lib_dir, 'مكتبتي.عربي'), 'w',
                      encoding='utf-8') as f:
                f.write('القيمة = ٤٢\n')
            out = run_code('استورد مكتبتي\nاطبع(مكتبتي.القيمة)\n',
                           script_dir=d)
            self.assertEqual(out, '42\n')


class TestFormatter(unittest.TestCase):
    """المنسق --نسق."""

    def test_tabs_to_spaces(self):
        fixed, _ = format_source('لو صح:\n\tاطبع(١)\n')
        self.assertIn('\n    اطبع(١)', fixed)

    def test_depth_normalization(self):
        fixed, _ = format_source('لو صح:\n  اطبع(١)\n  اطبع(٢)\n')
        lines = fixed.splitlines()
        self.assertEqual(lines[1], '    اطبع(١)')
        self.assertEqual(lines[2], '    اطبع(٢)')

    def test_trailing_whitespace_removed(self):
        fixed, _ = format_source('اطبع(١)   \n')
        self.assertEqual(fixed, 'اطبع(١)\n')

    def test_blank_lines_collapse(self):
        fixed, _ = format_source('اطبع(١)\n\n\n\nاطبع(٢)\n')
        self.assertEqual(fixed, 'اطبع(١)\n\nاطبع(٢)\n')

    def test_idempotent(self):
        src = 'لو صح:\n\tاطبع(١)\n\n\n\nاطبع(٢)  \n'
        once, _ = format_source(src)
        twice, changes = format_source(once)
        self.assertEqual(once, twice)
        self.assertEqual(changes, 0)

    def test_multiline_string_preserved(self):
        src = 'نص = """سطر أول\n    بإزاحة داخل النص\nسطر ثالث"""\nاطبع(نص)\n'
        fixed, _ = format_source(src)
        self.assertIn('    بإزاحة داخل النص', fixed)

    def test_continuation_lines_preserved(self):
        src = 'ق = [\n    ١،\n    ٢\n]\n'
        fixed, changes = format_source(src)
        self.assertEqual(fixed, src)
        self.assertEqual(changes, 0)

    def test_valid_code_stays_valid(self):
        src = 'لو صح:\n\tاطبع(١)\n'
        fixed, _ = format_source(src)
        Parser(Lexer(fixed).tokenize()).parse()   # فحص صارم ينجح

    def test_broken_original_best_effort(self):
        # ملف غير سليم بنيويًا — لا ينهار المنسق
        fixed, _ = format_source('اطبع(١)\n')
        self.assertEqual(fixed, 'اطبع(١)\n')


class TestLinter(unittest.TestCase):
    """الفاحص --افحص."""

    def lint(self, src):
        return lint_source(src)

    def has(self, src, keyword, kind=None):
        issues = self.lint(src)
        for line, k, msg in issues:
            if keyword in msg and (kind is None or k == kind):
                return True
        return False

    def test_unused_variable(self):
        self.assertTrue(self.has('س = ٥\n', "المتغير 'س' معرّف لكنه غير مستخدم"))

    def test_used_variable_clean(self):
        self.assertEqual(self.lint('س = ٥\nاطبع(س)\n'), [])

    def test_unused_import(self):
        self.assertTrue(self.has('استورد رياضيات\n', "الاستيراد 'رياضيات' غير مستخدم"))

    def test_used_import_clean(self):
        self.assertEqual(self.lint('استورد رياضيات\nاطبع(رياضيات.بي)\n'), [])

    def test_unreachable_code(self):
        self.assertTrue(self.has(
            'دالة خ():\n    أعد ١\n    اطبع(٢)\n',
            'كود غير قابل للوصول'))

    def test_duplicate_params(self):
        self.assertTrue(self.has('دالة خ(س، س):\n    تجاهل\n', "المعامل 'س' مكرر"))

    def test_undefined_name(self):
        self.assertTrue(self.has('اطبع(غير_موجود)\n',
                                 "الاسم 'غير_موجود' غير معرّف", 'تحذير'))

    def test_return_outside_function(self):
        self.assertTrue(self.has('أعد ١\n', "جملة 'أعد' خارج الدالة", 'خطأ'))

    def test_break_outside_loop(self):
        self.assertTrue(self.has('كسر\n', "جملة 'كسر' خارج حلقة", 'خطأ'))

    def test_break_inside_loop_clean(self):
        self.assertEqual(self.lint('طالما صح:\n    كسر\n'), [])

    def test_shadowing_builtin_variable(self):
        self.assertTrue(self.has('اطبع = ٥\n', 'يظلّل'))

    def test_underscore_exempt(self):
        self.assertEqual(self.lint('_س = ٥\n'), [])

    def test_syntax_error_passthrough(self):
        issues = self.lint('دالة خ(:\n')
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0][1], 'خطأ')

    def test_closure_no_false_positive(self):
        src = ('دالة عداد():\n'
               '    العدد = ٠\n'
               '    دالة زد():\n'
               '        العدد = العدد + ١\n'
               '        أعد العدد\n'
               '    أعد زد\n'
               'اطبع(عداد()())\n')
        self.assertEqual(self.lint(src), [])

    def test_try_then_use_no_false_positive(self):
        src = ('جرب:\n'
               '    س = ١\n'
               'باستثناء:\n'
               '    تجاهل\n'
               'اطبع(س)\n')
        self.assertEqual(self.lint(src), [])

    def test_clean_program(self):
        src = ('دالة جمع(أ، ب):\n'
               '    أعد أ + ب\n'
               'اطبع(جمع(١، ٢))\n')
        self.assertEqual(self.lint(src), [])


class TestDocGen(unittest.TestCase):
    """مولد التوثيق --وثق."""

    def test_module_docstring_and_function(self):
        docs = generate_docs('مثال.عربي',
                             '"""وحدة تجريبية."""\n'
                             'دالة جمع(أ، ب):\n'
                             '    """يجمع عددين."""\n'
                             '    أعد أ + ب\n')
        self.assertIn('# توثيق مثال.عربي', docs)
        self.assertIn('وحدة تجريبية', docs)
        self.assertIn('### جمع(أ، ب)', docs)
        self.assertIn('يجمع عددين', docs)

    def test_params_with_defaults(self):
        docs = generate_docs('م.عربي',
                             'دالة ترحيب(الاسم، تحية = "مرحبا"):\n'
                             '    أعد ١\n')
        self.assertIn('ترحيب(الاسم، تحية = "مرحبا")', docs)

    def test_class_with_members(self):
        docs = generate_docs('م.عربي',
                             'صنف حساب:\n'
                             '    """صنف الحساب."""\n'
                             '    السقف = ١٠\n'
                             '    دالة مضاعف(س):\n'
                             '        """يضاعف."""\n'
                             '        أعد س * ٢\n'
                             '    خاصية الاسم:\n'
                             '        أعد "حساب"\n')
        self.assertIn('### حساب', docs)
        self.assertIn('صنف الحساب', docs)
        self.assertIn('**الثوابت:** `السقف`', docs)
        self.assertIn('`مضاعف(س)`', docs)
        self.assertIn('**الخصائص المحسوبة:** `الاسم`', docs)

    def test_enum_table(self):
        docs = generate_docs('م.عربي',
                             'تعداد ألوان:\n'
                             '    أحمر\n'
                             '    أخضر = ٢\n')
        self.assertIn('## التعدادات', docs)
        self.assertIn('| `أحمر` | تلقائي |', docs)
        self.assertIn('| `أخضر` | 2 |', docs)

    def test_imports_listed(self):
        docs = generate_docs('م.عربي',
                             'استورد رياضيات\n'
                             'من وقت استورد الآن\n')
        self.assertIn('## الاعتماديات', docs)
        self.assertIn('`رياضيات`', docs)
        self.assertIn('من `وقت`', docs)

    def test_empty_file(self):
        docs = generate_docs('فارغ.عربي', 'تجاهل\n')
        self.assertIn('لا يوجد عناصر موثقة', docs)


class TestPackages(unittest.TestCase):
    """مدير الحزم --ثبت و--حزم."""

    def test_install_local_file(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'مكتبة_جيدة.عربي')
            with open(src, 'w', encoding='utf-8') as f:
                f.write('دالة ن():\n    أعد ١\n')
            libs = os.path.join(d, 'libs')
            name, dest = install_package(src, libs)
            self.assertEqual(name, 'مكتبة_جيدة')
            self.assertTrue(os.path.isfile(dest))
            self.assertEqual(list_packages(libs), ['مكتبة_جيدة.عربي'])

    def test_install_adds_extension(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'بلا_امتداد')
            with open(src, 'w', encoding='utf-8') as f:
                f.write('تجاهل\n')
            libs = os.path.join(d, 'libs')
            name, dest = install_package(src, libs)
            self.assertEqual(name, 'بلا_امتداد')
            self.assertTrue(dest.endswith('بلا_امتداد.عربي'))

    def test_install_rejects_broken_code(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'سيئة.عربي')
            with open(src, 'w', encoding='utf-8') as f:
                f.write('دالة ناقصة(:\n')
            libs = os.path.join(d, 'libs')
            with self.assertRaises(ArabiError):
                install_package(src, libs)
            self.assertEqual(list_packages(libs), [])

    def test_install_missing_file(self):
        with self.assertRaises(ArabiError):
            install_package('غير_موجود_إطلاقا.عربي',
                            os.path.join(tempfile.gettempdir(), 'libs_عربي'))


class TestLexerLineNumbers(unittest.TestCase):
    """إصلاحات المحلل اللفظي: أرقام الأسطر بعد النصوص الممتدة وخطأ القوس المفتوح."""

    def test_lines_after_multiline_string(self):
        toks = Lexer('نص = """\nأ\nب\n"""\nاطبع(نص)').tokenize()
        print_tok = [t for t in toks if t.value == 'اطبع'][0]
        self.assertEqual(print_tok.line, 5)

    def test_multiline_string_token_carries_start_line(self):
        toks = Lexer('نص = """\nأ\nب\n"""').tokenize()
        str_tok = [t for t in toks if t.type is T.STRING][0]
        self.assertEqual(str_tok.line, 1)

    def test_unclosed_bracket_reports_opening_line(self):
        with self.assertRaises(LexerError) as cm:
            Lexer('اطبع(١\nاطبع(٢\n').tokenize()
        # القوس الأعمق (الأخير) هو المُبلَّغ عنه
        self.assertEqual(cm.exception.line, 2)
        self.assertIn("قوس '(' بقي مفتوحًا", cm.exception.message)

    def test_strict_mode_still_rejects_inconsistent_indent(self):
        with self.assertRaises(LexerError):
            Lexer('لو صح:\n        اطبع(١)\n   اطبع(٢)\n').tokenize()

    def test_lenient_mode_accepts_inconsistent_indent(self):
        toks = Lexer('لو صح:\n        اطبع(١)\n   اطبع(٢)\n',
                     lenient_indent=True).tokenize()
        self.assertTrue(any(t.type is T.EOF for t in toks))


class TestMultilineFString(unittest.TestCase):
    """النصوص المنسقة متعددة الأسطر: ق + ثلاث علامات اقتباس."""

    def test_basic_interpolation(self):
        out = run_arabi('الاسم = "نورة"\n'
                        'صفحة = ق"""مرحبا\n{الاسم}"""\n'
                        'اطبع(صفحة)\n')
        self.assertEqual(out, 'مرحبا\nنورة\n')

    def test_expressions(self):
        out = run_arabi('نص = ق"""المجموع: {٣ + ٤}\nالضِعف: {(٣ + ٤) * ٢}"""\n'
                        'اطبع(نص)\n')
        self.assertEqual(out, 'المجموع: 7\nالضِعف: 14\n')

    def test_quotes_inside(self):
        out = run_arabi('صفحة = ق"""<html dir="rtl">\n  <p>{١ + ١}</p>\n</html>"""\n'
                        'اطبع(صفحة)\n')
        self.assertEqual(out, '<html dir="rtl">\n  <p>2</p>\n</html>\n')

    def test_unclosed_raises(self):
        expect_error('نص = ق"""سطر\n', LexerError, 'غير مغلق')

    def test_line_numbers_after(self):
        toks = Lexer('ن = ق"""أ\nب"""\nاطبع(ن)').tokenize()
        print_tok = [t for t in toks if t.value == 'اطبع'][0]
        self.assertEqual(print_tok.line, 3)


# ================== المولدات ==================

class TestGenerators(unittest.TestCase):
    """جملة 'أنتج' وقيم المولدات."""

    def test_yield_keyword_token(self):
        toks = Lexer('أنتج ١').tokenize()
        self.assertEqual(toks[0].type, T.YIELD)

    def test_basic_generator_for_loop(self):
        out = run_arabi(
            'دالة اثنان():\n'
            '    أنتج 10\n'
            '    أنتج 20\n'
            'لكل ق في اثنان():\n'
            '    اطبع(ق)\n')
        self.assertEqual(out, '10\n20\n')

    def test_generator_fibonacci(self):
        out = run_arabi(
            'دالة فيبوناتشي(الحد):\n'
            '    أ = 0\n'
            '    ب = 1\n'
            '    لكل س في مدى(الحد):\n'
            '        أنتج أ\n'
            '        أ، ب = ب، أ + ب\n'
            'م = قائمة(فيبوناتشي(8))\n'
            'اطبع(م)\n')
        self.assertEqual(out, '[0، 1، 1، 2، 3، 5، 8، 13]\n')

    def test_list_consumes_generator(self):
        out = run_arabi(
            'دالة أعداد():\n'
            '    لكل س في مدى(4):\n'
            '        أنتج س * 10\n'
            'اطبع(قائمة(أعداد()))\n')
        self.assertEqual(out, '[0، 10، 20، 30]\n')

    def test_list_empty_generator(self):
        out = run_arabi(
            'دالة فارغ():\n'
            '    لو خطأ:\n'
            '        أنتج 1\n'
            'اطبع(قائمة(فارغ()))\n')
        self.assertEqual(out, '[]\n')

    def test_break_closes_generator(self):
        out = run_arabi(
            'دالة أعداد():\n'
            '    لكل س في مدى(100):\n'
            '        أنتج س\n'
            'المجموع = 0\n'
            'لكل ن في أعداد():\n'
            '    لو ن > 4:\n'
            '        كسر\n'
            '    المجموع += ن\n'
            'اطبع(المجموع)\n')
        self.assertEqual(out, '10\n')

    def test_generator_with_return_stops(self):
        out = run_arabi(
            'دالة حتى_ثلاثة():\n'
            '    أنتج 1\n'
            '    أنتج 2\n'
            '    أعد\n'
            '    أنتج 99\n'
            'اطبع(قائمة(حتى_ثلاثة()))\n')
        self.assertEqual(out, '[1، 2]\n')

    def test_next_method(self):
        out = run_arabi(
            'دالة اثنان():\n'
            '    أنتج "أ"\n'
            '    أنتج "ب"\n'
            'م = اثنان()\n'
            'اطبع(م.التالي())\n'
            'اطبع(م.التالي())\n')
        self.assertEqual(out, 'أ\nب\n')

    def test_next_at_end_raises(self):
        expect_error(
            'دالة واحد():\n'
            '    أنتج 1\n'
            'م = واحد()\n'
            'م.التالي()\n'
            'م.التالي()\n',
            ArabiRuntimeError, 'انتهى المولد')

    def test_generator_type_and_display(self):
        out = run_arabi(
            'دالة م():\n'
            '    أنتج 1\n'
            'اطبع(نوع(م()))\n'
            'اطبع(نص(م()))\n')
        self.assertEqual(out, 'مولد\n<مولد م>\n')

    def test_generator_is_lazy(self):
        # المولد لا ينفذ شيئًا قبل أول طلب — لا طباعة حتى التالي
        out = run_arabi(
            'دالة كسول():\n'
            '    اطبع("بدأ")\n'
            '    أنتج 1\n'
            'م = كسول()\n'
            'اطبع("بعد الإنشاء")\n'
            'م.التالي()\n')
        self.assertEqual(out, 'بعد الإنشاء\nبدأ\n')

    def test_generator_in_class(self):
        out = run_arabi(
            'صنف عدّاد:\n'
            '    دالة إنشاء(النهاية):\n'
            '        هذا.النهاية = النهاية\n'
            '    دالة اعد():\n'
            '        لكل س في مدى(هذا.النهاية):\n'
            '            أنتج س\n'
            'ع = عدّاد(3)\n'
            'لكل قيمة في ع.اعد():\n'
            '    اطبع(قيمة)\n')
        self.assertEqual(out, '0\n1\n2\n')

    def test_generator_error_propagates(self):
        expect_error(
            'دالة معطوبة():\n'
            '    أنتج 1\n'
            '    ارفع("عطل داخل المولد")\n'
            'لكل ق في معطوبة():\n'
            '    اطبع(ق)\n',
            ArabiRuntimeError, 'عطل داخل المولد')

    def test_generator_error_caught_in_try(self):
        out = run_arabi(
            'دالة معطوبة():\n'
            '    أنتج 1\n'
            '    ارفع("عطل")\n'
            'جرب:\n'
            '    لكل ق في معطوبة():\n'
            '        اطبع(ق)\n'
            'باستثناء هـ:\n'
            '    اطبع("أُمسك")\n')
        self.assertEqual(out, '1\nأُمسك\n')

    def test_yield_outside_function(self):
        expect_error('أنتج 5\n', ArabiRuntimeError, 'أنتج')

    def test_bare_yield(self):
        out = run_arabi(
            'دالة فارغة():\n'
            '    أنتج\n'
            '    أنتج 5\n'
            'لكل ق في فارغة():\n'
            '    اطبع(ق)\n')
        self.assertEqual(out, 'ولا شيء\n5\n')

    def test_generator_with_finally(self):
        out = run_arabi(
            'دالة م():\n'
            '    جرب:\n'
            '        أنتج 1\n'
            '    اخيرا:\n'
            '        اطبع("تغليق")\n'
            'لكل ق في م():\n'
            '    اطبع(ق)\n')
        self.assertEqual(out, '1\nتغليق\n')

    def test_nested_generator_function_not_outer(self):
        # أنتج داخل دالة داخلية لا يجعل الخارجية مولدًا
        out = run_arabi(
            'دالة الخارجية():\n'
            '    دالة الداخلية():\n'
            '        أنتج 7\n'
            '    أعد الداخلية\n'
            'صانع = الخارجية()\n'
            'اطبع(نوع(صانع))\n'
            'اطبع(قائمة(صانع()))\n')
        self.assertEqual(out, 'دالة\n[7]\n')

    def test_generator_with_filter_map(self):
        out = run_arabi(
            'دالة أعداد():\n'
            '    لكل س في مدى(10):\n'
            '        أنتج س\n'
            'زوجية = دالة(س) => س % 2 == 0\n'
            'اطبع(مرشّح(زوجية، أعداد()))\n'
            'اطبع(خريطة(دالة(س) => س * س، مرشّح(زوجية، أعداد())))\n')
        self.assertEqual(out, '[0، 2، 4، 6، 8]\n[0، 4، 16، 36، 64]\n')

    def test_generator_closure_captures(self):
        out = run_arabi(
            'دالة صانع(البداية):\n'
            '    لكل س في مدى(3):\n'
            '        أنتج البداية + س\n'
            'اطبع(قائمة(صانع(100)))\n')
        self.assertEqual(out, '[100، 101، 102]\n')


# ================== المزخرفات ==================

class TestDecorators(unittest.TestCase):
    """علامة @ لتزيين الدوال."""

    def test_at_token(self):
        toks = Lexer('@مزخرف').tokenize()
        self.assertEqual(toks[0].type, T.AT)

    def test_basic_decorator(self):
        out = run_arabi(
            'دالة مضاعف(د):\n'
            '    دالة داخلية(س):\n'
            '        أعد د(س) * 2\n'
            '    أعد داخلية\n'
            '@مضاعف\n'
            'دالة زد(س):\n'
            '    أعد س + 1\n'
            'اطبع(زد(5))\n')
        self.assertEqual(out, '12\n')

    def test_stacked_decorators_order(self):
        # الأقرب للدالة يُطبق أولًا
        out = run_arabi(
            'دالة قوسان(د):\n'
            '    دالة داخلية(نص):\n'
            '        أعد "[" + د(نص) + "]"\n'
            '    أعد داخلية\n'
            'دالة نجمتان(د):\n'
            '    دالة داخلية(نص):\n'
            '        أعد "**" + د(نص) + "**"\n'
            '    أعد داخلية\n'
            '@قوسان\n'
            '@نجمتان\n'
            'دالة تحية(اسم):\n'
            '    أعد "مرحبا"\n'
            'اطبع(تحية(""))\n')
        self.assertEqual(out, '[**مرحبا**]\n')

    def test_decorator_with_call_expression(self):
        out = run_arabi(
            'دالة بتكرار(د):\n'
            '    دالة داخلية(س):\n'
            '        أعد د(س) + د(س)\n'
            '    أعد داخلية\n'
            '@بتكرار\n'
            'دالة اسمي(س):\n'
            '    أعد نص(س)\n'
            'اطبع(اسمي(7))\n')
        self.assertEqual(out, '77\n')

    def test_decorator_logging_args(self):
        out = run_arabi(
            'دالة سجل(د):\n'
            '    دالة داخلية(أ، ب):\n'
            '        اطبع("قبل")\n'
            '        نتيجة = د(أ، ب)\n'
            '        اطبع("بعد")\n'
            '        أعد نتيجة\n'
            '    أعد داخلية\n'
            '@سجل\n'
            'دالة اجمع(أ، ب):\n'
            '    أعد أ + ب\n'
            'اطبع(اجمع(2، 3))\n')
        self.assertEqual(out, 'قبل\nبعد\n5\n')

    def test_decorator_caching_counter(self):
        out = run_arabi(
            'استدعاءات = 0\n'
            'دالة عدّاد(د):\n'
            '    دالة داخلية(س):\n'
            '        عالمي استدعاءات\n'
            '        استدعاءات += 1\n'
            '        أعد د(س)\n'
            '    أعد داخلية\n'
            '@عدّاد\n'
            'دالة تربيع(س):\n'
            '    أعد س * س\n'
            'تربيع(3)\n'
            'تربيع(4)\n'
            'اطبع(استدعاءات)\n')
        self.assertEqual(out, '2\n')

    def test_decorator_on_class_method(self):
        out = run_arabi(
            'دالة هادئ(د):\n'
            '    دالة داخلية():\n'
            '        أعد د() + "!"\n'
            '    أعد داخلية\n'
            'صنف مطرقة:\n'
            '    دالة إنشاء(صوت):\n'
            '        هذا.صوت = صوت\n'
            '    @هادئ\n'
            '    دالة اطرق():\n'
            '        أعد هذا.صوت\n'
            'م = مطرقة("طق")\n'
            'اطبع(م.اطرق())\n')
        self.assertEqual(out, 'طق!\n')

    def test_decorator_must_return_callable(self):
        expect_error(
            'دالة سيئ(د):\n'
            '    أعد 5\n'
            '@سيئ\n'
            'دالة م():\n'
            '    أعد 1\n',
            ArabiRuntimeError, 'المزخرف')

    def test_decorator_requires_function(self):
        expect_error(
            '@متغير\n'
            'أ = 5\n',
            ParseError, 'المزخرف')

    def test_undefined_decorator(self):
        expect_error(
            '@غير_موجود\n'
            'دالة م():\n'
            '    أعد 1\n',
            ArabiRuntimeError, 'غير معرّف')


# ================== الوراثة المتعددة ==================

class TestMultipleInheritance(unittest.TestCase):
    """صنف ابن من أصل₁، أصل₂ — مع MRO (ترتيب C3)."""

    def test_two_parents_methods(self):
        out = run_arabi(
            'صنف طائر:\n'
            '    دالة طِر():\n'
            '        أعد "أطير"\n'
            'صنف سباح:\n'
            '    دالة اسبح():\n'
            '        أعد "أسبح"\n'
            'صنف بطريق من طائر، سباح:\n'
            '    تجاهل\n'
            'ك = بطريق()\n'
            'اطبع(ك.طِر())\n'
            'اطبع(ك.اسبح())\n')
        self.assertEqual(out, 'أطير\nأسبح\n')

    def test_method_resolution_order(self):
        # الميراث يبدأ من الأصل الأول عند التعارض
        out = run_arabi(
            'صنف أ:\n'
            '    دالة هوية():\n'
            '        أعد "أ"\n'
            'صنف ب:\n'
            '    دالة هوية():\n'
            '        أعد "ب"\n'
            'صنف ج من أ، ب:\n'
            '    تجاهل\n'
            'اطبع(ج().هوية())\n')
        self.assertEqual(out, 'أ\n')

    def test_diamond_not_broken(self):
        out = run_arabi(
            'صنف أساس:\n'
            '    دالة صوت():\n'
            '        أعد "أساس"\n'
            'صنف أ من أساس:\n'
            '    تجاهل\n'
            'صنف ب من أساس:\n'
            '    دالة صوت():\n'
            '        أعد "ب"\n'
            'صنف ج من أ، ب:\n'
            '    تجاهل\n'
            'اطبع(ج().صوت())\n')
        self.assertEqual(out, 'ب\n')

    def test_first_parent_is_super(self):
        out = run_arabi(
            'صنف أ:\n'
            '    دالة اسمي():\n'
            '        أعد "أ"\n'
            'صنف ب:\n'
            '    دالة اسمي():\n'
            '        أعد "ب"\n'
            'صنف ج من أ، ب:\n'
            '    دالة كاملة():\n'
            '        أعد الأصل.اسمي(هذا)\n'
            'اطبع(ج().كاملة())\n')
        self.assertEqual(out, 'أ\n')

    def test_constants_from_both_parents(self):
        out = run_arabi(
            'صنف أ:\n'
            '    لون = "أحمر"\n'
            'صنف ب:\n'
            '    حجم = 10\n'
            'صنف ج من أ، ب:\n'
            '    تجاهل\n'
            'اطبع(ج.لون + " " + نص(ج.حجم))\n')
        self.assertEqual(out, 'أحمر 10\n')

    def test_single_inheritance_still_works(self):
        out = run_arabi(
            'صنف أب:\n'
            '    دالة تحية():\n'
            '        أعد "مرحبا"\n'
            'صنف ابن من أب:\n'
            '    تجاهل\n'
            'اطبع(ابن().تحية())\n')
        self.assertEqual(out, 'مرحبا\n')

    def test_circular_inheritance(self):
        # إعادة تعريف الصنف بوراثة نفسه (النسخة القديمة موجودة)
        expect_error(
            'صنف س:\n'
            '    تجاهل\n'
            'صنف س من س:\n'
            '    تجاهل\n',
            ArabiRuntimeError, 'دائرية')

    def test_parent_must_be_class(self):
        expect_error(
            'س = 5\n'
            'صنف م من س:\n'
            '    تجاهل\n',
            ArabiRuntimeError, 'ليس صنفًا')

    def test_parse_three_parents(self):
        out = run_arabi(
            'صنف أ:\n'
            '    تجاهل\n'
            'صنف ب:\n'
            '    تجاهل\n'
            'صنف ج:\n'
            '    تجاهل\n'
            'صنف د من أ، ب، ج:\n'
            '    تجاهل\n'
            'اطبع(نوع(د()))\n')
        self.assertEqual(out, 'كائن\n')

    def test_auto_super_binding(self):
        # الأصل.طريقة() بلا هذا — ربط تلقائي من السياق (جديد 1.7)
        out = run_arabi(
            'صنف أ:\n'
            '    دالة اسمي():\n'
            '        أعد "أ"\n'
            'صنف ب:\n'
            '    تجاهل\n'
            'صنف ج من أ، ب:\n'
            '    دالة كاملة():\n'
            '        أعد الأصل.اسمي()\n'
            'اطبع(ج().كاملة())\n')
        self.assertEqual(out, 'أ\n')

    def test_auto_super_binding_with_args(self):
        out = run_arabi(
            'صنف شكل:\n'
            '    دالة إنشاء(الاسم):\n'
            '        هذا.الاسم = الاسم\n'
            'صنف مربع من شكل:\n'
            '    دالة إنشاء(الاسم، الطول):\n'
            '        الأصل.إنشاء(الاسم)\n'
            '        هذا.الطول = الطول\n'
            'م = مربع("م1", 5)\n'
            'اطبع(م.الاسم + " " + نص(م.الطول))\n')
        self.assertEqual(out, 'م1 5\n')

    def test_override_with_super_call(self):
        out = run_arabi(
            'صنف أ:\n'
            '    دالة صوت():\n'
            '        أعد "مواء"\n'
            'صنف ب:\n'
            '    تجاهل\n'
            'صنف قط من أ، ب:\n'
            '    دالة صوت():\n'
            '        أعد الأصل.صوت(هذا) + " مياو"\n'
            'اطبع(قط().صوت())\n')
        self.assertEqual(out, 'مواء مياو\n')


# ================== وحدة قاعدة ==================

class TestDatabaseModule(unittest.TestCase):
    """وحدة قاعدة — SQLite."""

    def test_open_memory(self):
        out = run_arabi(
            'استورد قاعدة\n'
            'ق = قاعدة.افتح()\n'
            'اطبع(نوع(ق))\n'
            'ق.أغلق()\n')
        self.assertEqual(out, 'قاعدة بيانات\n')

    def test_create_insert_query(self):
        out = run_arabi(
            'استورد قاعدة\n'
            'ق = قاعدة.افتح()\n'
            'ق.نفذ("CREATE TABLE ن (الاسم TEXT, العمر INTEGER)")\n'
            'ق.نفذ("INSERT INTO ن VALUES (?, ?)", ["سارة", 30])\n'
            'صفوف = ق.استعلم("SELECT الاسم, العمر FROM ن")\n'
            'اطبع(صفوف)\n'
            'ق.أغلق()\n')
        self.assertEqual(out, "[[سارة، 30]]\n")

    def test_rowcount(self):
        out = run_arabi(
            'استورد قاعدة\n'
            'ق = قاعدة.افتح()\n'
            'ق.نفذ("CREATE TABLE ن (س INTEGER)")\n'
            'ن = ق.نفذ("INSERT INTO ن VALUES (?), (?), (?)", [1, 2, 3])\n'
            'اطبع(ن)\n'
            'ق.أغلق()\n')
        self.assertEqual(out, '3\n')

    def test_parameterized_query(self):
        out = run_arabi(
            'استورد قاعدة\n'
            'ق = قاعدة.افتح()\n'
            'ق.نفذ("CREATE TABLE ن (س INTEGER)")\n'
            'ق.نفذ("INSERT INTO ن VALUES (?)", [5])\n'
            'ق.نفذ("INSERT INTO ن VALUES (?)", [9])\n'
            'صفوف = ق.استعلم("SELECT س FROM ن WHERE س > ?", [6])\n'
            'اطبع(صفوف)\n'
            'ق.أغلق()\n')
        self.assertEqual(out, '[[9]]\n')

    def test_columns(self):
        out = run_arabi(
            'استورد قاعدة\n'
            'ق = قاعدة.افتح()\n'
            'ق.نفذ("CREATE TABLE أصحاب (الاسم TEXT, العمر INTEGER)")\n'
            'أعمدة = ق.أعمدة("SELECT * FROM أصحاب")\n'
            'اطبع(أعمدة)\n'
            'ق.أغلق()\n')
        self.assertEqual(out, "[الاسم، العمر]\n")

    def test_empty_query_returns_empty_list(self):
        out = run_arabi(
            'استورد قاعدة\n'
            'ق = قاعدة.افتح()\n'
            'ق.نفذ("CREATE TABLE ن (س INTEGER)")\n'
            'اطبع(ق.استعلم("SELECT س FROM ن"))\n'
            'ق.أغلق()\n')
        self.assertEqual(out, '[]\n')

    def test_function_form(self):
        out = run_arabi(
            'استورد قاعدة\n'
            'ق = قاعدة.افتح()\n'
            'قاعدة.نفذ(ق, "CREATE TABLE ن (س INTEGER)")\n'
            'قاعدة.نفذ(ق, "INSERT INTO ن VALUES (?)", [7])\n'
            'اطبع(قاعدة.استعلم(ق, "SELECT س FROM ن"))\n'
            'قاعدة.أغلق(ق)\n')
        self.assertEqual(out, '[[7]]\n')

    def test_closed_connection_error(self):
        expect_error(
            'استورد قاعدة\n'
            'ق = قاعدة.افتح()\n'
            'ق.أغلق()\n'
            'ق.استعلم("SELECT 1")\n',
            ArabiRuntimeError, 'قاعدة البيانات')

    def test_bad_sql_error(self):
        expect_error(
            'استورد قاعدة\n'
            'ق = قاعدة.افتح()\n'
            'ق.نفذ("SELECT * FROM غير_موجود")\n',
            ArabiRuntimeError, 'قاعدة البيانات')

    def test_needs_connection(self):
        expect_error(
            'استورد قاعدة\n'
            'قاعدة.نفذ("CREATE TABLE ن (س INTEGER)")\n',
            ArabiRuntimeError, 'اتصال')


# ================== وحدة ترميز ==================

class TestEncodingModule(unittest.TestCase):
    """وحدة ترميز — Base64 والبصمات."""

    def test_base64_roundtrip(self):
        out = run_arabi(
            'استورد ترميز\n'
            'م = ترميز.شفّر64("مرحبا بالعالم")\n'
            'اطبع(ترميز.فك64(م))\n')
        self.assertEqual(out, 'مرحبا بالعالم\n')

    def test_base64_known_value(self):
        out = run_arabi(
            'استورد ترميز\n'
            'اطبع(ترميز.شفّر64("abc"))\n')
        self.assertEqual(out, 'YWJj\n')

    def test_base64_invalid(self):
        expect_error(
            'استورد ترميز\n'
            'ترميز.فك64("!!!ليس ترميز!!!")\n',
            ArabiRuntimeError, 'Base64')

    def test_sha256_length_and_stability(self):
        out = run_arabi(
            'استورد ترميز\n'
            'أ = ترميز.هش256("نص")\n'
            'ب = ترميز.هش256("نص")\n'
            'اطبع(طول(أ) == 64 و أ == ب)\n')
        self.assertEqual(out, 'صح\n')

    def test_sha256_known(self):
        # بصمة "abc" القياسية
        out = run_arabi(
            'استورد ترميز\n'
            'اطبع(ترميز.هش256("abc"))\n')
        self.assertEqual(
            out,
            'ba7816bf8f01cfea414140de5dae2223'
            'b00361a396177a9cb410ff61f20015ad\n')

    def test_sha1_known(self):
        out = run_arabi(
            'استورد ترميز\n'
            'اطبع(ترميز.هش1("abc"))\n')
        self.assertEqual(
            out, 'a9993e364706816aba3e25717850c26c9cd0d89d\n')

    def test_md5_known(self):
        out = run_arabi(
            'استورد ترميز\n'
            'اطبع(ترميز.ام_دي_5("abc"))\n')
        self.assertEqual(out, '900150983cd24fb0d6963f7d28e17f72\n')

    def test_different_hashes_for_different_text(self):
        out = run_arabi(
            'استورد ترميز\n'
            'اطبع(ترميز.هش256("أ") != ترميز.هش256("ب"))\n')
        self.assertEqual(out, 'صح\n')

    def test_requires_text(self):
        expect_error(
            'استورد ترميز\n'
            'ترميز.هش256(123)\n',
            ArabiRuntimeError, 'نص')


# ================== وحدة جداول ==================

class TestCsvModule(unittest.TestCase):
    """وحدة جداول — قراءة وكتابة CSV."""

    def test_parse_basic(self):
        out = run_arabi(
            'استورد جداول\n'
            'صفوف = جداول.حلل("الاسم,العمر\\nأحمد,25")\n'
            'اطبع(صفوف)\n')
        self.assertEqual(out, "[[الاسم، العمر]، [أحمد، 25]]\n")

    def test_text_from_rows(self):
        out = run_arabi(
            'استورد جداول\n'
            'ن = جداول.نص([["أ", "ب"], ["ج", 2]])\n'
            'اطبع(ن)\n')
        self.assertEqual(out, 'أ,ب\nج,2\n\n')

    def test_roundtrip(self):
        out = run_arabi(
            'استورد جداول\n'
            'نصي = جداول.نص([["الاسم", "العمر"], ["نورة", 22]])\n'
            'صفوف = جداول.حلل(نصي)\n'
            'اطبع(صفوف[1][0])\n'
            'اطبع(صفوف[1][1])\n')
        self.assertEqual(out, 'نورة\n22\n')

    def test_custom_delimiter(self):
        out = run_arabi(
            'استورد جداول\n'
            'صفوف = جداول.حلل("أ؛ب؛ج", "؛")\n'
            'اطبع(صفوف)\n'
            'ن = جداول.نص([["أ", "ب"]], "؛")\n'
            'اطبع(ن)\n')
        self.assertEqual(out, "[[أ، ب، ج]]\nأ؛ب\n\n")

    def test_quoted_cell_with_comma(self):
        out = run_arabi(
            'استورد جداول\n'
            'صفوف = جداول.حلل(\'"مرحبا، عالم",ثاني\')\n'
            'اطبع(صفوف[0][0])\n'
            'اطبع(طول(صفوف[0]))\n')
        self.assertEqual(out, 'مرحبا، عالم\n2\n')

    def test_bool_and_empty_cells(self):
        out = run_arabi(
            'استورد جداول\n'
            'ن = جداول.نص([["س", "ف"], [صح, ولا شيء]])\n'
            'اطبع(ن)\n')
        self.assertEqual(out, 'س,ف\nصح,\n\n')

    def test_file_write_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'بيانات.csv')
            out = run_arabi(
                'استورد جداول\n'
                f"جداول.اكتب(\"{path}\", [[\"أ\", 1], [\"ب\", 2]])\n"
                f'صفوف = جداول.اقرأ("{path}")\n'
                'اطبع(صفوف)\n')
            self.assertEqual(out, "[[أ، 1]، [ب، 2]]\n")

    def test_read_missing_file(self):
        expect_error(
            'استورد جداول\n'
            'جداول.اقرأ("/غير/موجود_إطلاقًا.csv")\n',
            ArabiRuntimeError, 'غير موجود')

    def test_write_needs_rows(self):
        expect_error(
            'استورد جداول\n'
            'جداول.اكتب("/tmp/ن.csv", "ليس قائمة")\n',
            ArabiRuntimeError, 'قائمة صفوف')

    def test_delimiter_must_be_one_char(self):
        expect_error(
            'استورد جداول\n'
            'جداول.حلل("أ،ب", "اب")\n',
            ArabiRuntimeError, 'حرفًا واحدًا')


if __name__ == '__main__':    unittest.main(verbosity=2)
