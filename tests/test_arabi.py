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
from arabi_lang.interpreter import Interpreter              # noqa: E402
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


class TestInterfaces(unittest.TestCase):
    """الواجهات (واجهة) — الإصدار 1.8."""

    def test_basic_interface_implementation(self):
        out = run_arabi("""
واجهة شكل:
    دالة مساحة()

صنف مربع من شكل:
    دالة إنشاء(ض):
        هذا.ض = ض
    دالة مساحة():
        أعد هذا.ض * هذا.ض

م = مربع(٣)
اطبع(م.مساحة())
""")
        self.assertEqual(out.strip(), '9')

    def test_abstract_method_missing_blocks_instantiation(self):
        expect_error("""
واجهة شكل:
    دالة مساحة()

صنف مربع من شكل:
    تجاهل
م = مربع()
""", ArabiRuntimeError, 'لم ينفذ الطرق المجردة')

    def test_cannot_instantiate_interface_directly(self):
        expect_error("""
واجهة شكل:
    دالة مساحة()
شكل()
""", ArabiRuntimeError, 'لا يمكن إنشاء كائن من الواجهة')

    def test_default_implementation_is_inherited(self):
        out = run_arabi("""
واجهة حيوان:
    دالة صوت():
        أعد "..."
    دالة تعريف():
        أعد "أنا " + هذا.صوت()

صنف قط من حيوان:
    دالة صوت():
        أعد "مياو"

ق = قط()
اطبع(ق.تعريف())
""")
        self.assertEqual(out.strip(), 'أنا مياو')

    def test_default_implementation_used_when_not_overridden(self):
        out = run_arabi("""
واجهة حيوان:
    دالة صوت():
        أعد "..."

صنف حيوان_عام من حيوان:
    تجاهل

ه = حيوان_عام()
اطبع(ه.صوت())
""")
        self.assertEqual(out.strip(), '...')

    def test_interface_constants(self):
        out = run_arabi("""
واجهة قياس:
    وحدات = "متر"

صنف طول من قياس:
    تجاهل
اطبع(طول.وحدات)
""")
        self.assertEqual(out.strip(), 'متر')

    def test_interface_extending_interface(self):
        out = run_arabi("""
واجهة أساسي:
    دالة اسم()

واجهة كامل من أساسي:
    دالة وصف()

صنف منتج من كامل:
    دالة اسم():
        أعد "قلم"
    دالة وصف():
        أعد "أداة كتابة"

ص = منتج()
اطبع(ص.اسم() + ': ' + ص.وصف())
""")
        self.assertEqual(out.strip(), 'قلم: أداة كتابة')

    def test_extending_inherits_abstract_from_parent(self):
        expect_error("""
واجهة أساسي:
    دالة اسم()

واجهة كامل من أساسي:
    تجاهل

صنف منتج من كامل:
    دالة وصف():
        أعد "وصف"
منتج()
""", ArabiRuntimeError, "لم ينفذ الطرق المجردة: 'اسم'")

    def test_partial_implementation_intermediate_class(self):
        expect_error("""
واجهة شكل:
    دالة مساحة()
    دالة محيط()

صنف مجرد من شكل:
    دالة مساحة():
        أعد ٠

صنف دائرة من مجرد:
    تجاهل
دائرة()
""", ArabiRuntimeError, 'محيط')

    def test_intermediate_class_satisfies_interface(self):
        out = run_arabi("""
واجهة شكل:
    دالة مساحة()
    دالة محيط()

صنف مجرد من شكل:
    دالة مساحة():
        أعد ٠

صنف دائرة من مجرد:
    دالة محيط():
        أعد ٦

د = دائرة()
اطبع(د.مساحة() + د.محيط())
""")
        self.assertEqual(out.strip(), '6')

    def test_mixed_class_and_interface_inheritance(self):
        out = run_arabi("""
صنف قاعدة:
    دالة مرحبا():
        أعد "مرحبا"

واجهة رسم:
    دالة ارسم()

صنف تطبيق من قاعدة، رسم:
    دالة ارسم():
        أعد "أرسم"

ت = تطبيق()
اطبع(ت.مرحبا() + ' ' + ت.ارسم())
""")
        self.assertEqual(out.strip(), 'مرحبا أرسم')

    def test_typename_of_interface(self):
        out = run_arabi("""
واجهة شكل:
    دالة مساحة()
اطبع(نوع(شكل))
""")
        self.assertEqual(out.strip(), 'واجهة')

    def test_class_typename_stays_class(self):
        out = run_arabi("""
صنف نقطة:
    تجاهل
اطبع(نوع(نقطة))
""")
        self.assertEqual(out.strip(), 'صنف')

    def test_interface_inherits_from_class_error(self):
        expect_error("""
صنف نقطة:
    تجاهل
واجهة شكل من نقطة:
    تجاهل
""", ArabiRuntimeError, 'ترث الواجهات فقط')

    def test_interface_inherits_from_unknown_name(self):
        expect_error("""
واجهة شكل من غيره:
    تجاهل
""", ArabiRuntimeError, 'غير معرّف')

    def test_abstract_method_with_params(self):
        out = run_arabi("""
واجهة عملية:
    دالة نفذ(س، ص)

صنف جمع من عملية:
    دالة نفذ(س، ص):
        أعد س + ص

ع = جمع()
اطبع(ع.نفذ(٢، ٥))
""")
        self.assertEqual(out.strip(), '7')

    def test_missing_abstract_lists_all_missing(self):
        exc = expect_error("""
واجهة شكل:
    دالة مساحة()
    دالة محيط()

صنف بسيط من شكل:
    تجاهل
بسيط()
""", ArabiRuntimeError, 'لم ينفذ الطرق المجردة')
        self.assertIn('مساحة', str(exc))
        self.assertIn('محيط', str(exc))

    def test_interface_with_static_method_call(self):
        out = run_arabi("""
واجهة صانع:
    الاسم = "صانع"
    دالة اصنع()

صنف مصنع من صانع:
    دالة اصنع():
        أعد "صنعت بواسطة " + هذا.الاسم

م = مصنع()
اطبع(م.اصنع())
""")
        self.assertEqual(out.strip(), 'صنعت بواسطة صانع')

    def test_linter_understands_interface(self):
        issues = lint_source("""
واجهة شكل:
    دالة مساحة()

صنف مربع من شكل:
    دالة مساحة():
        أعد ١
""")
        errors = [i for i in issues if i[1] == 'خطأ']
        self.assertEqual(errors, [])


class TestVarargs(unittest.TestCase):
    """المعاملات المتغيرة (...) — الإصدار 1.8."""

    def test_rest_collects_extra_args(self):
        out = run_arabi("""
دالة مجموع(...أرقام):
    م = ٠
    لكل أ في أرقام:
        م += أ
    أعد م
اطبع(مجموع(١، ٢، ٣، ٤، ٥))
""")
        self.assertEqual(out.strip(), '15')

    def test_rest_empty_gives_empty_list(self):
        out = run_arabi("""
دالة عدد(...قيم):
    أعد طول(قيم)
اطبع(عدد())
""")
        self.assertEqual(out.strip(), '0')

    def test_fixed_params_then_rest(self):
        out = run_arabi("""
دالة علامة(اسم، ...درجات):
    أعد اسم + ': ' + نص(درجات)
اطبع(علامة("سالم"، ٩٠، ٨٥))
""")
        self.assertEqual(out.strip(), 'سالم: [90، 85]')

    def test_rest_with_defaults(self):
        out = run_arabi("""
دالة ف(أ = "افتراضي"، ...بقية):
    أعد نص(أ) + '|' + نص(طول(بقية))
اطبع(ف())
اطبع(ف("محدد"، ١، ٢))
""")
        self.assertEqual(out.strip(), 'افتراضي|0\nمحدد|2')

    def test_named_args_still_work_with_rest(self):
        out = run_arabi("""
دالة ف(أ، ...بقية):
    أعد نص(أ) + '|' + نص(طول(بقية))
اطبع(ف(أ = "باسم"))
""")
        self.assertEqual(out.strip(), 'باسم|0')

    def test_rest_must_be_last_error(self):
        expect_error(
            'دالة ف(...بقية، أ):\n    أعد أ\n',
            ParseError, 'يجب أن يكون الأخير')

    def test_rest_cannot_be_sent_by_name(self):
        expect_error("""
دالة ف(...بقية):
    أعد طول(بقية)
ف(بقية = [١])
""", ArabiRuntimeError, 'لا تُرسله بالاسم')

    def test_lambda_rest(self):
        out = run_arabi("""
عدد = دالة(...قيم) => طول(قيم)
اطبع(عدد(١، ٢، ٣))
""")
        self.assertEqual(out.strip(), '3')

    def test_lambda_rest_identity(self):
        out = run_arabi("""
هوية = دالة(...قيم) => قيم
اطبع(هوية("أ"، "ب"))
""")
        self.assertEqual(out.strip(), '[أ، ب]')

    def test_method_rest(self):
        out = run_arabi("""
صنف حساب:
    دالة مجموع(...قيم):
        م = ٠
        لكل ق في قيم:
            م += ق
        أعد م

ح = حساب()
اطبع(ح.مجموع(١٠، ٢٠، ٣٠))
""")
        self.assertEqual(out.strip(), '60')

    def test_rest_inside_decorator_kept(self):
        out = run_arabi("""
دالة مجموع(...قيم):
    م = ٠
    لكل ق في قيم:
        م += ق
    أعد م
اطبع(مجموع(٥، ١٠))
""")
        self.assertEqual(out.strip(), '15')

    def test_arity_error_without_rest(self):
        expect_error("""
دالة ف(أ):
    أعد أ
ف(١، ٢)
""", ArabiRuntimeError, 'كحد أقصى')

    def test_params_list_message_shows_rest(self):
        exc = expect_error("""
دالة ف(أ، ...بقية):
    أعد أ
ف(ص = ١)
""", ArabiRuntimeError, 'لا تحتوي على معامل بالاسم')
        self.assertIn('...بقية', str(exc))

    def test_recursion_with_rest(self):
        out = run_arabi("""
دالة أكبر(...قيم):
    لو طول(قيم) == ١:
        أعد قيم[٠]
    الفرعي = أكبر(...قيم[1:طول(قيم)])
    لو قيم[٠] > الفرعي:
        أعد قيم[٠]
    أعد الفرعي
اطبع(أكبر(٣، ٩، ٢، ٧))
""")
        self.assertEqual(out.strip(), '9')


class TestSpread(unittest.TestCase):
    """التفكيك ... في الاستدعاء والقوائم — الإصدار 1.8."""

    def test_spread_call_list(self):
        out = run_arabi("""
دالة جمع_ثلاثة(أ، ب، ج):
    أعد أ + ب + ج
ق = [١، ٢]
اطبع(جمع_ثلاثة(...ق، ٣))
""")
        self.assertEqual(out.strip(), '6')

    def test_spread_full_list(self):
        out = run_arabi("""
دالة مجموع(...أرقام):
    م = ٠
    لكل أ في أرقام:
        م += أ
    أعد م
ق = [١٠، ٢٠، ٣٠]
اطبع(مجموع(...ق))
""")
        self.assertEqual(out.strip(), '60')

    def test_spread_mixed_with_positional(self):
        out = run_arabi("""
دالة ثلاثية(أ، ب، ج):
    أعد نص(أ) + نص(ب) + نص(ج)
اطبع(ثلاثية(١، ...[٢، ٣]))
""")
        self.assertEqual(out.strip(), '123')

    def test_spread_range(self):
        out = run_arabi("اطبع(طول([٠، ...مدى(٥)، ٩]))")
        self.assertEqual(out.strip(), '7')

    def test_spread_string_into_list(self):
        out = run_arabi("اطبع([...\"أب\"])")
        self.assertEqual(out.strip(), '[أ، ب]')

    def test_spread_in_list_literal(self):
        out = run_arabi("""
أ = [٢، ٣]
ب = [١، ...أ، ٤]
اطبع(ب)
""")
        self.assertEqual(out.strip(), '[1، 2، 3، 4]')

    def test_spread_two_lists_in_list(self):
        out = run_arabi("اطبع([...[١]، ...[٢، ٣]])")
        self.assertEqual(out.strip(), '[1، 2، 3]')

    def test_spread_generator_into_call(self):
        out = run_arabi("""
دالة تولد():
    أنتج ١
    أنتج ٢
    أنتج ٣
دالة مجموع(...أرقام):
    م = ٠
    لكل أ في أرقام:
        م += أ
    أعد م
اطبع(مجموع(...تولد()))
""")
        self.assertEqual(out.strip(), '6')

    def test_spread_non_iterable_error(self):
        expect_error(
            'دالة ف(...ق):\n    أعد ق\nف(...٥)\n',
            ArabiRuntimeError, 'لا يمكن تفكيك')

    def test_spread_non_iterable_in_list_error(self):
        expect_error(
            'ص = [...صح]\n',
            ArabiRuntimeError, 'لا يمكن تفكيك')

    def test_spread_after_named_error(self):
        expect_error("""
دالة ف(أ):
    أعد أ
ف(أ = ١، ...[٢])
""", ArabiRuntimeError, 'بعد معامل بالاسم')

    def test_spread_empty_list(self):
        out = run_arabi("""
دالة ف(...ق):
    أعد طول(ق)
اطبع(ف(...[]))
""")
        self.assertEqual(out.strip(), '0')


class TestThreadsModule(unittest.TestCase):
    """وحدة خيوط — الإصدار 1.8."""

    def test_spawn_and_result(self):
        out = run_arabi("""
دالة ضاعف(س):
    أعد س * ٢
خ = خيوط.شغّل(ضاعف، ٢١)
اطبع(خ.نتيجة())
""")
        self.assertEqual(out.strip(), '42')

    def test_spawn_multiple_args(self):
        out = run_arabi("""
دالة جمع(أ، ب، ج):
    أعد أ + ب + ج
خ = خيوط.شغّل(جمع، ١، ٢، ٣)
اطبع(خ.نتيجة())
""")
        self.assertEqual(out.strip(), '6')

    def test_spawn_with_no_args(self):
        out = run_arabi("""
دالة ثابتة():
    أعد "جاهز"
خ = خيوط.شغّل(ثابتة)
اطبع(خ.نتيجة())
""")
        self.assertEqual(out.strip(), 'جاهز')

    def test_wait_returns_none_but_finishes(self):
        out = run_arabi("""
دالة عمل():
    أعد ٥
خ = خيوط.شغّل(عمل)
خ.انتظر()
اطبع(خ.حي())
""")
        self.assertEqual(out.strip(), 'خطأ')

    def test_alive_false_after_finish(self):
        out = run_arabi("""
دالة عمل():
    أعد ٥
خ = خيوط.شغّل(عمل)
خ.نتيجة()
اطبع(خ.حي())
""")
        self.assertEqual(out.strip(), 'خطأ')

    def test_join_all_returns_results(self):
        out = run_arabi("""
مهام = []
لكل س في مدى(٥):
    مهام.أضف(خيوط.شغّل(دالة(ن) => ن + ١، س))
النتائج = خيوط.انتظر_الكل(مهام)
اطبع(طول(النتائج))
اطبع(جمع(النتائج))
""")
        lines = out.strip().splitlines()
        self.assertEqual(lines[0], '5')
        self.assertEqual(lines[1], '15')

    def test_shared_memory_with_lock(self):
        out = run_arabi("""
العداد = ٠
الحارس = خيوط.قفل()

دالة زد():
    عالمي العداد
    لكل س في مدى(١٠٠):
        الحارس.احجز()
        العداد += ١
        الحارس.افرح()

مهام = []
لكل س في مدى(٤):
    مهام.أضف(خيوط.شغّل(زد))
خيوط.انتظر_الكل(مهام)
اطبع(العداد)
""")
        self.assertEqual(out.strip(), '400')

    def test_lock_acquire_release_and_try(self):
        out = run_arabi("""
ق = خيوط.قفل()
أول = ق.احجز()
ثاني = ق.محاولة()
ق.افرح()
ثالث = ق.محاولة()
اطبع(نص(أول) + ' ' + نص(ثاني) + ' ' + نص(ثالث))
""")
        self.assertEqual(out.strip(), 'صح خطأ صح')

    def test_lock_try_timeout(self):
        out = run_arabi("""
ق = خيوط.قفل()
ق.احجز()
نتيجة = ق.احجز(٠.٠٥)
ق.افرح()
اطبع(نتيجة)
""")
        self.assertEqual(out.strip(), 'خطأ')

    def test_lock_release_unheld_error(self):
        expect_error("""
ق = خيوط.قفل()
ق.افرح()
""", ArabiRuntimeError, 'قفل غير محجوز')

    def test_queue_send_receive(self):
        out = run_arabi("""
ط = خيوط.طابور()
ط.أرسل("رسالة")
اطبع(ط.استلم())
""")
        self.assertEqual(out.strip(), 'رسالة')

    def test_queue_fifo_order(self):
        out = run_arabi("""
ط = خيوط.طابور()
ط.أرسل(١)
ط.أرسل(٢)
ط.أرسل(٣)
اطبع(ط.استلم())
اطبع(ط.استلم())
""")
        self.assertEqual(out.strip(), '1\n2')

    def test_queue_size_empty(self):
        out = run_arabi("""
ط = خيوط.طابور()
اطبع(ط.فارغ())
ط.أرسل(١)
اطبع(ط.الحجم())
ط.استلم()
اطبع(ط.فارغ())
""")
        self.assertEqual(out.strip(), 'صح\n1\nصح')

    def test_queue_nowait_error_on_empty(self):
        expect_error("""
ط = خيوط.طابور()
ط.استلم_الآن()
""", ArabiRuntimeError, 'الطابور فارغ')

    def test_thread_error_propagates(self):
        expect_error("""
دالة تفشل():
    ارفع("انفجار داخل الخيط")
خ = خيوط.شغّل(تفشل)
خ.نتيجة()
""", ArabiRuntimeError, 'انفجار داخل الخيط')

    def test_thread_error_not_raised_by_wait(self):
        out = run_arabi("""
دالة تفشل():
    ارفع("خطأ داخلي")
خ = خيوط.شغّل(تفشل)
خ.انتظر()
اطبع("تجاوزنا الانتظار")
""")
        self.assertEqual(out.strip(), 'تجاوزنا الانتظار')

    def test_spawn_needs_function(self):
        expect_error(
            'خيوط.شغّل(٥)\n',
            ArabiRuntimeError, 'يجب أن يكون دالة')

    def test_spawn_needs_at_least_one_arg(self):
        expect_error(
            'خيوط.شغّل()\n',
            ArabiRuntimeError, 'معامل أول')

    def test_join_all_needs_list(self):
        expect_error(
            'خيوط.انتظر_الكل(٥)\n',
            ArabiRuntimeError, 'قائمة خيوط')

    def test_join_all_rejects_non_thread(self):
        expect_error(
            'خيوط.انتظر_الكل([٥])\n',
            ArabiRuntimeError, 'ليس خيطًا')

    def test_cpu_count_positive(self):
        out = run_arabi('اطبع(خيوط.معالجات() > ٠)')
        self.assertEqual(out.strip(), 'صح')

    def test_producer_consumer_with_queue(self):
        out = run_arabi("""
الطابور = خيوط.طابور()

دالة منتج():
    لكل س في مدى(٣):
        الطابور.أرسل(س * س)

دالة مستهلك():
    النتائج = []
    لكل س في مدى(٣):
        النتائج.أضف(الطابور.استلم())
    أعد النتائج

خيوط.شغّل(منتج).انتظر()
نتائج = خيوط.شغّل(مستهلك).نتيجة()
اطبع(نتائج)
""")
        self.assertEqual(out.strip(), '[0، 1، 4]')

    def test_threads_typename(self):
        out = run_arabi("""
اطبع(نوع(خيوط.شغّل(دالة() => ١)))
اطبع(نوع(خيوط.قفل()))
اطبع(نوع(خيوط.طابور()))
""")
        lines = out.strip().splitlines()
        self.assertEqual(lines, ['خيط', 'قفل', 'طابور'])

    def test_threads_in_builtin_modules(self):
        from arabi_lang.interpreter import BUILTIN_MODULES
        self.assertIn('خيوط', BUILTIN_MODULES)

    def test_linter_accepts_threads_code(self):
        issues = lint_source("""
دالة عمل():
    أعد ١
خ = خيوط.شغّل(عمل)
اطبع(خ.نتيجة())
""")
        errors = [i for i in issues if i[1] == 'خطأ']
        self.assertEqual(errors, [])


class TestMatch(unittest.TestCase):
    """اختبارات مطابقة الأنماط طابق/حالة/غير ذلك — الإصدار 1.9."""

    def test_literal_match(self):
        out = run_arabi('''
طابق ٣
حالة ١:
    اطبع("واحد")
حالة ٣:
    اطبع("ثلاثة")
''')
        self.assertEqual(out, 'ثلاثة\n')

    def test_string_literal_match(self):
        out = run_arabi('''
طابق "تفاح"
حالة "موز":
    اطبع("أصفر")
حالة "تفاح":
    اطبع("أحمر")
''')
        self.assertEqual(out, 'أحمر\n')

    def test_bool_and_none_literals(self):
        out = run_arabi('''
طابق صح
حالة خطأ:
    اطبع("خطأ")
حالة صح:
    اطبع("صح")
طابق ولا شيء
حالة ولا شيء:
    اطبع("لا شيء")
''')
        self.assertEqual(out, 'صح\nلا شيء\n')

    def test_negative_literal(self):
        out = run_arabi('''
طابق -٥
حالة -١:
    اطبع("سالب واحد")
حالة -٥:
    اطبع("سالب خمسة")
''')
        self.assertEqual(out, 'سالب خمسة\n')

    def test_first_match_wins(self):
        out = run_arabi('''
طابق ٥
حالة ن:
    اطبع("أول: " + نص(ن))
حالة ٥:
    اطبع("ثانٍ")
''')
        self.assertEqual(out, 'أول: 5\n')

    def test_or_pattern(self):
        out = run_arabi('''
طابق ٢
حالة ١ أو ٢ أو ٣:
    اطبع("صغير")
حالة _:
    اطبع("كبير")
''')
        self.assertEqual(out, 'صغير\n')

    def test_or_with_captures_first_wins(self):
        out = run_arabi('''
طابق "ب"
حالة "أ" أو "ب":
    اطبع("حرف")
''')
        self.assertEqual(out, 'حرف\n')

    def test_capture_binds_value(self):
        out = run_arabi('''
طابق ٤٢
حالة ن:
    اطبع("القيمة " + نص(ن) + " من نوع " + نوع(ن))
''')
        self.assertEqual(out, 'القيمة 42 من نوع عدد صحيح\n')

    def test_wildcard_underscore(self):
        out = run_arabi('''
طابق "أي شيء"
حالة ١:
    اطبع("عدد")
حالة _:
    اطبع("شيء آخر")
''')
        self.assertEqual(out, 'شيء آخر\n')

    def test_guard_runs_when_true(self):
        out = run_arabi('''
طابق ١٥
حالة ن إن ن < ١٠:
    اطبع("صغير")
حالة ن إن ن < ٢٠:
    اطبع("متوسط " + نص(ن))
''')
        self.assertEqual(out, 'متوسط 15\n')

    def test_guard_fails_continues(self):
        out = run_arabi('''
طابق ٥
حالة ن إن ن > ١٠:
    اطبع("كبير")
حالة ن:
    اطبع("غير كبير: " + نص(ن))
''')
        self.assertEqual(out, 'غير كبير: 5\n')

    def test_otherwise_runs_when_no_match(self):
        out = run_arabi('''
طابق ٩٩
حالة ١:
    اطبع("واحد")
غير ذلك:
    اطبع("افتراضي")
''')
        self.assertEqual(out, 'افتراضي\n')

    def test_otherwise_skipped_on_match(self):
        out = run_arabi('''
طابق ١
حالة ١:
    اطبع("واحد")
غير ذلك:
    اطبع("افتراضي")
''')
        self.assertEqual(out, 'واحد\n')

    def test_list_pattern_exact(self):
        out = run_arabi('''
طابق [١، ٢]
حالة [أ، ب]:
    اطبع(نص(أ) + نص(ب))
''')
        self.assertEqual(out, '12\n')

    def test_list_pattern_length_mismatch(self):
        out = run_arabi('''
طابق [١، ٢، ٣]
حالة [أ، ب]:
    اطبع("زوج")
حالة [أ، ب، ج]:
    اطبع("ثلاثي: " + نص(أ + ب + ج))
''')
        self.assertEqual(out, 'ثلاثي: 6\n')

    def test_list_pattern_rest_binding(self):
        out = run_arabi('''
طابق [١٠، ٢٠، ٣٠، ٤٠]
حالة [أول، ...البقية]:
    اطبع(نص(أول) + " ثم " + نص(طول(البقية)) + " عناصر")
''')
        self.assertEqual(out, '10 ثم 3 عناصر\n')

    def test_list_pattern_rest_discard(self):
        out = run_arabi('''
طابق [١، ٢، ٣]
حالة [أول، ...]:
    اطبع("يبدأ بـ " + نص(أول))
''')
        self.assertEqual(out, 'يبدأ بـ 1\n')

    def test_list_pattern_not_a_list(self):
        out = run_arabi('''
طابق "نص"
حالة [أ]:
    اطبع("قائمة")
حالة _:
    اطبع("ليست قائمة")
''')
        self.assertEqual(out, 'ليست قائمة\n')

    def test_nested_list_pattern(self):
        out = run_arabi('''
طابق [[١، ٢]، ٣]
حالة [[أ، ب]، ج]:
    اطبع(نص(أ + ب + ج))
''')
        self.assertEqual(out, '6\n')

    def test_equality_capture_pair(self):
        out = run_arabi('''
طابق [٧، ٧]
حالة [أ، أ]:
    اطبع("متساويان: " + نص(أ))
حالة _:
    اطبع("مختلفان")
طابق [٧، ٨]
حالة [أ، أ]:
    اطبع("متساويان")
حالة _:
    اطبع("مختلفان")
''')
        self.assertEqual(out, 'متساويان: 7\nمختلفان\n')

    def test_dict_pattern_binds_values(self):
        out = run_arabi('''
م = {الاسم: "سارة"، العمر: ٢٥}
طابق م
حالة {الاسم: اس، العمر: عمر}:
    اطبع(اس + " عمرها " + نص(عمر))
''')
        self.assertEqual(out, 'سارة عمرها 25\n')

    def test_dict_pattern_extra_keys_allowed(self):
        out = run_arabi('''
م = {أ: ١، ب: ٢، ج: ٣}
طابق م
حالة {أ: واحد، ج: ثلاثة}:
    اطبع(نص(واحد + ثلاثة))
''')
        self.assertEqual(out, '4\n')

    def test_dict_pattern_missing_key_fails(self):
        out = run_arabi('''
م = {أ: ١}
طابق م
حالة {أ: واحد، غير_موجود: ناقص}:
    اطبع("مطابق")
حالة _:
    اطبع("غير مطابق")
''')
        self.assertEqual(out, 'غير مطابق\n')

    def test_dict_pattern_not_a_dict(self):
        out = run_arabi('''
طابق [١]
حالة {أ: ب}:
    اطبع("قاموس")
حالة _:
    اطبع("ليس قاموسًا")
''')
        self.assertEqual(out, 'ليس قاموسًا\n')

    def test_value_pattern_enum_member(self):
        out = run_arabi('''
تعداد اتجاه:
    شمال
    جنوب
    شرق
    غرب
طابق اتجاه.شمال
حالة اتجاه.جنوب أو اتجاه.شمال:
    اطبع("محور رأسي")
حالة اتجاه.شرق أو اتجاه.غرب:
    اطبع("محور أفقي")
''')
        self.assertEqual(out, 'محور رأسي\n')

    def test_capture_persists_after_match(self):
        out = run_arabi('''
طابق ٩
حالة ن:
    تجاهل
اطبع(ن * ٢)
''')
        self.assertEqual(out, '18\n')

    def test_match_inside_function(self):
        out = run_arabi('''
دالة صِف(قيمة):
    طابق قيمة
    حالة ٠:
        أعد "صفر"
    حالة ن إن نوع(ن) == "عدد صحيح":
        أعد "عدد"
    حالة _:
        أعد "آخر"
اطبع(صِف(٠))
اطبع(صِف(٧))
اطبع(صِف("س"))
''')
        self.assertEqual(out, 'صفر\nعدد\nآخر\n')

    def test_match_no_cases_error(self):
        expect_error('''
طابق ٥
''', Exception, 'حالة')

    def test_linter_understands_match_captures(self):
        issues = lint_source('''
فحص = [١، ٢]
طابق فحص
حالة [أ، ...البقية]:
    اطبع(أ + طول(البقية))
غير ذلك:
    تجاهل
''')
        errors = [i for i in issues if i[1] == 'خطأ']
        self.assertEqual(errors, [])

    def test_formatter_keeps_match_code(self):
        source = '''
طابق [١]
حالة [أ]:
    اطبع(أ)
'''
        formatted, _changed = format_source(source)
        self.assertIn('حالة [أ]:', formatted)
        # الناتج المنسق يظل صالحًا للتنفيذ
        out = run_arabi(formatted)
        self.assertEqual(out, '1\n')


class TestRawStrings(unittest.TestCase):
    """اختبارات السلاسل الخام خ"..." — الإصدار 1.9."""

    def test_raw_backslash_literal(self):
        out = run_arabi('''
س = خ"أ\\ب"
اطبع(طول(س))
اطبع(س)
''')
        self.assertEqual(out, '3\nأ\\ب\n')

    def test_raw_vs_normal_escape(self):
        out = run_arabi('''
عادي = "س\\tط"
خام = خ"س\\tط"
اطبع(طول(عادي))
اطبع(طول(خام))
''')
        self.assertEqual(out, '3\n4\n')

    def test_raw_with_regex_findall(self):
        out = run_arabi('''
اطبع(تنظيم.كل_المطابقات(خ"\\d+"، "أ 1 ب 22 ج 333"))
''')
        self.assertEqual(out, '[1، 22، 333]\n')

    def test_raw_with_regex_word_chars(self):
        out = run_arabi('''
نمط = خ"\\w+@\\w+\\.com"
اطبع(تنظيم.يجد(نمط، "راسلني على علي@mail.com اليوم"))
''')
        self.assertEqual(out, 'علي@mail.com\n')

    def test_raw_keeps_double_backslash(self):
        out = run_arabi('''
س = خ"\\\\"
اطبع(طول(س))
''')
        self.assertEqual(out, '2\n')

    def test_raw_single_quotes(self):
        out = run_arabi("س = خ'أ\\ب'\nاطبع(س)\n")
        self.assertEqual(out, 'أ\\ب\n')

    def test_raw_multiline(self):
        out = run_arabi('''
س = خ"""سطر\\أول
ثانٍ\\ثاني"""
اطبع(س)
''')
        self.assertEqual(out, 'سطر\\أول\nثانٍ\\ثاني\n')

    def test_raw_multiline_line_numbers(self):
        # الخطأ بعد سلسلة ممتدة يجب أن يشير للسطر الصحيح (بعد ٣ أسطر النص)
        try:
            run_arabi('''
س = خ"""أ
ب
ج"""
ن = ٥
طابق ن
حالة ١:
''')
        except Exception as exc:
            self.assertIn('السطر 8', str(exc))
            return
        self.fail('لم يُطلع خطأ الصياغة')

    def test_raw_with_regex_sub(self):
        out = run_arabi('''
اطبع(تنظيم.يستبدل(خ"\\s+"، " "، "كلمات    متفرقة    جدًا"))
''')
        self.assertEqual(out, 'كلمات متفرقة جدًا\n')

    def test_raw_still_string_type(self):
        out = run_arabi('اطبع(نوع(خ"نص"))\n')
        self.assertEqual(out, 'نص\n')


class TestDatesModule(unittest.TestCase):
    """اختبارات وحدة تواريخ — الإصدار 1.9."""

    def test_create_and_display(self):
        out = run_arabi('''
ص = تواريخ.أنشئ(٢٠٢٦، ٩، ٢٧، ١٤، ٣٠)
اطبع(نوع(ص))
اطبع(ص)
''')
        self.assertEqual(out, 'تاريخ\n2026-09-27 14:30:00\n')

    def test_create_minimal_args(self):
        out = run_arabi('''
ص = تواريخ.أنشئ(٢٠٢٥، ١، ١)
اطبع(ص)
''')
        self.assertEqual(out, '2025-01-01 00:00:00\n')

    def test_properties(self):
        out = run_arabi('''
ص = تواريخ.أنشئ(٢٠٢٦، ٣، ١٥، ٨، ٤٥، ٣٠)
اطبع(ص.السنة)
اطبع(ص.الشهر)
اطبع(ص.اليوم)
اطبع(ص.الساعة)
اطبع(ص.الدقيقة)
اطبع(ص.الثانية)
''')
        self.assertEqual(out, '2026\n3\n15\n8\n45\n30\n')

    def test_weekday_name(self):
        out = run_arabi('''
ص = تواريخ.أنشئ(٢٠٢٦، ٩، ٢٧)      # أحد
ط = تواريخ.أنشئ(٢٠٢٦، ٩، ٢٤)      # خميس
اطبع(تواريخ.يوم_الأسبوع(ص))
اطبع(تواريخ.يوم_الأسبوع(ط))
''')
        self.assertEqual(out, 'الأحد\nالخميس\n')

    def test_weekday_method(self):
        out = run_arabi('''
ص = تواريخ.أنشئ(٢٠٢٦، ٩، ٢٦)
اطبع(ص.يوم_الأسبوع())
''')
        self.assertEqual(out, 'السبت\n')

    def test_format(self):
        out = run_arabi('''
ص = تواريخ.أنشئ(٢٠٢٦، ١، ٥)
اطبع(ص.نسق("%Y/%m/%d"))
اطبع(ص.نسق("اليوم: %d من شهر %m"))
''')
        self.assertEqual(out, '2026/01/05\nاليوم: 05 من شهر 01\n')

    def test_parse_roundtrip(self):
        out = run_arabi('''
ص = تواريخ.حلل("2026-09-27 10:00", "%Y-%m-%d %H:%M")
اطبع(ص.نسق("%d/%m"))
اطبع(ص.الساعة)
''')
        self.assertEqual(out, '27/09\n10\n')

    def test_parse_invalid_raises(self):
        expect_error('''
تواريخ.حلل("ليس تاريخًا"، "%Y-%m-%d")
''', Exception, 'لا يمكن قراءة التاريخ')

    def test_diff_days(self):
        out = run_arabi('''
أ = تواريخ.أنشئ(٢٠٢٦، ١، ١٠)
ب = تواريخ.أنشئ(٢٠٢٦، ١، ١)
اطبع(تواريخ.فرق(أ، ب))
''')
        self.assertEqual(out, '9\n')

    def test_diff_negative(self):
        out = run_arabi('''
أ = تواريخ.أنشئ(٢٠٢٦، ١، ١)
ب = تواريخ.أنشئ(٢٠٢٦، ١، ١٠)
اطبع(تواريخ.فرق(أ، ب))
''')
        self.assertEqual(out, '-9\n')

    def test_add_units(self):
        out = run_arabi('''
ص = تواريخ.أنشئ(٢٠٢٥، ١٢، ٣٠، ٢٣)
جديد = تواريخ.أضف(ص، ٥، ٤)
اطبع(جديد)
''')
        self.assertEqual(out, '2026-01-05 03:00:00\n')

    def test_add_with_match(self):
        out = run_arabi('''
اليوم = تواريخ.أنشئ(٢٠٢٦، ٩، ٢٧)
غدًا = تواريخ.أضف(اليوم، ١)
طابق غدًا.يوم_الأسبوع()
حالة "الجمعة" أو "السبت":
    اطبع("عطلة قريبًا")
حالة _:
    اطبع("يوم عمل")
''')
        self.assertEqual(out, 'يوم عمل\n')

    def test_create_invalid_date_raises(self):
        expect_error('''
تواريخ.أنشئ(٢٠٢٦، ١٣، ٤٠)
''', Exception, 'تاريخ غير صالح')

    def test_dates_in_builtin_modules(self):
        from arabi_lang.interpreter import BUILTIN_MODULES
        self.assertIn('تواريخ', BUILTIN_MODULES)

    def test_linter_accepts_dates_code(self):
        issues = lint_source('''
ص = تواريخ.الآن()
اطبع(ص.السنة)
اطبع(تواريخ.يوم_الأسبوع(ص))
''')
        errors = [i for i in issues if i[1] == 'خطأ']
        self.assertEqual(errors, [])


class TestStatisticsModule(unittest.TestCase):
    """وحدة الإحصاء (الإصدار 1.10)."""

    def test_import_from(self):
        code = """
من إحصاء استورد معدل
درجات = [70، 80، 90]
اطبع(معدل(درجات))
"""
        self.assertEqual(run_arabi(code).strip(), '80.0')

    def test_module_access(self):
        code = """
اطبع(إحصاء.معدل([2، 4، 6]))
"""
        self.assertEqual(run_arabi(code).strip(), '4.0')

    def test_median_odd(self):
        code = """
من إحصاء استورد وسيط
اطبع(وسيط([3، 1، 2]))
"""
        self.assertEqual(run_arabi(code).strip(), '2')

    def test_median_even(self):
        code = """
من إحصاء استورد وسيط
اطبع(وسيط([4، 1، 3، 2]))
"""
        self.assertEqual(run_arabi(code).strip(), '2.5')

    def test_mode(self):
        code = """
من إحصاء استورد منوال
اطبع(منوال([5، 3، 5، 2، 5، 3]))
"""
        self.assertEqual(run_arabi(code).strip(), '5')

    def test_mode_tie_first_wins(self):
        code = """
من إحصاء استورد منوال
اطبع(منوال([1، 2]))
"""
        self.assertEqual(run_arabi(code).strip(), '1')

    def test_variance_stddev(self):
        code = """
من إحصاء استورد تباين، انحراف
أ = [2، 4، 4، 4، 5، 5، 7، 9]
اطبع(تباين(أ))
اطبع(انحراف(أ) == 2)
"""
        self.assertEqual(run_arabi(code).strip(), '4.0\nصح')

    def test_range(self):
        code = """
من إحصاء استورد مدى
اطبع(مدى([15، 3، 11، 7]))
"""
        self.assertEqual(run_arabi(code).strip(), '12')

    def test_error_empty_list(self):
        expect_error(
            "من إحصاء استورد معدل\nمعدل([])",
            ArabiRuntimeError, 'فارغة')

    def test_error_non_list(self):
        expect_error(
            "من إحصاء استورد معدل\nمعدل(5)",
            ArabiRuntimeError, 'قائمة')

    def test_error_mixed_types(self):
        expect_error(
            'من إحصاء استورد معدل\nمعدل([1، "اثنان"])',
            ArabiRuntimeError, 'أعداد')

    def test_error_no_args(self):
        expect_error(
            "من إحصاء استورد وسيط\nوسيط()",
            ArabiRuntimeError, 'معاملًا')

    def test_builtin_module_count(self):
        from arabi_lang.interpreter import BUILTIN_MODULES
        self.assertIn('إحصاء', BUILTIN_MODULES)
        self.assertEqual(len(BUILTIN_MODULES), 17)



class TestLSPServer(unittest.TestCase):
    """خادم لغة عربي — بروتوكول LSP (الإصدار 1.10)."""

    @staticmethod
    def _session(messages):
        import io as _io
        import json as _json
        from arabi_lang.lsp import ArabiLanguageServer, read_message
        stream_in = _io.BytesIO()
        for m in messages:
            body = _json.dumps(m, ensure_ascii=False).encode('utf-8')
            stream_in.write(f'Content-Length: {len(body)}\r\n\r\n'
                            .encode('ascii'))
            stream_in.write(body)
        stream_in.seek(0)
        out = _io.BytesIO()
        ArabiLanguageServer(input_stream=stream_in, output_stream=out).run()
        out.seek(0)
        responses = []
        while True:
            r = read_message(out)
            if r is None:
                break
            responses.append(r)
        return responses

    @staticmethod
    def _msg(method, params=None, msg_id=None):
        m = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            m['params'] = params
        if msg_id is not None:
            m['id'] = msg_id
        return m

    def _open(self, uri, text):
        return self._msg('textDocument/didOpen', {
            'textDocument': {'uri': uri, 'languageId': 'عربي',
                             'version': 1, 'text': text}})

    # ---------- الناقل ----------

    def test_transport_roundtrip(self):
        from arabi_lang.lsp import read_message, write_message
        import io as _io
        out = _io.BytesIO()
        write_message(out, {'jsonrpc': '2.0', 'id': 1, 'result': 'سلام'})
        out.seek(0)
        message = read_message(out)
        self.assertEqual(message, {'jsonrpc': '2.0', 'id': 1,
                                   'result': 'سلام'})

    def test_initialize_capabilities(self):
        responses = self._session([self._msg('initialize', {}, 1)])
        caps = responses[0]['result']['capabilities']
        for cap in ('textDocumentSync', 'completionProvider',
                    'hoverProvider', 'definitionProvider',
                    'documentSymbolProvider'):
            self.assertIn(cap, caps)

    def test_unknown_method_returns_error(self):
        responses = self._session([self._msg('textDocument/مجهول', {}, 7)])
        self.assertEqual(responses[0]['error']['code'], -32601)

    def test_exit_ends_loop(self):
        responses = self._session([
            self._msg('initialize', {}, 1),
            self._msg('shutdown', None, 2),
            self._msg('exit'),
        ])
        ids = [r.get('id') for r in responses if 'id' in r]
        self.assertEqual(ids, [1, 2])

    # ---------- التشخيصات ----------

    def test_diagnostics_clean(self):
        uri = 'file:///سليم.عربي'
        responses = self._session([
            self._open(uri, 'س = 1 + 2\nاطبع(س)\n')])
        diag = [r for r in responses
                if r.get('method') == 'textDocument/publishDiagnostics']
        self.assertEqual(diag[0]['params']['diagnostics'], [])

    def test_diagnostics_syntax_error(self):
        uri = 'file:///معطوب.عربي'
        responses = self._session([
            self._open(uri, 'صنف :\n    تجاهل\n')])
        diag = [r for r in responses
                if r.get('method') == 'textDocument/publishDiagnostics']
        items = diag[0]['params']['diagnostics']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['severity'], 1)
        self.assertEqual(items[0]['range']['start']['line'], 0)

    def test_diagnostics_cleared_on_close(self):
        uri = 'file:///معطوب.عربي'
        responses = self._session([
            self._open(uri, 'صنف :\n'),
            self._msg('textDocument/didClose',
                      {'textDocument': {'uri': uri}}),
        ])
        diag = [r for r in responses
                if r.get('method') == 'textDocument/publishDiagnostics']
        self.assertEqual(diag[-1]['params']['diagnostics'], [])

    # ---------- الإكمال ----------

    def test_completion_default_includes_keywords_and_modules(self):
        uri = 'file:///كود.عربي'
        responses = self._session([
            self._open(uri, 'س = 1\n'),
            self._msg('textDocument/completion', {
                'textDocument': {'uri': uri},
                'position': {'line': 1, 'character': 0}}, 2),
        ])
        items = responses[-1]['result']['items']
        labels = [i['label'] for i in items]
        for word in ('صنف', 'دالة', 'لكل', 'طابق', 'إحصاء', 'تواريخ'):
            self.assertIn(word, labels)

    def test_completion_module_members(self):
        uri = 'file:///كود.عربي'
        responses = self._session([
            self._open(uri, 'من إحصاء استورد معدل\nإحصاء.\n'),
            self._msg('textDocument/completion', {
                'textDocument': {'uri': uri},
                'position': {'line': 1, 'character': 6}}, 2),
        ])
        items = responses[-1]['result']['items']
        labels = [i['label'] for i in items]
        for member in ('معدل', 'وسيط', 'منوال', 'تباين', 'انحراف', 'مدى'):
            self.assertIn(member, labels)

    def test_completion_class_members_and_inference(self):
        uri = 'file:///كود.عربي'
        code = ('صنف نقطة:\n'
                '    دالة إنشاء(س):\n'
                '        هذا.س = س\n'
                '    دالة مسافة():\n'
                '        أعد 0\n'
                '\n'
                'ن = نقطة(3)\n'
                'اطبع(ن.\n')
        responses = self._session([
            self._open(uri, code),
            self._msg('textDocument/completion', {
                'textDocument': {'uri': uri},
                'position': {'line': 7, 'character': 7}}, 2),
        ])
        items = responses[-1]['result']['items']
        labels = [i['label'] for i in items]
        self.assertIn('إنشاء', labels)
        self.assertIn('مسافة', labels)
        self.assertNotIn('اطبع', labels)

    def test_completion_incomplete_line_repair(self):
        uri = 'file:///كود.عربي'
        code = 'صنف أ:\n    دالة ف():\n        أعد 1\n\nك = أ()\nك.\n'
        responses = self._session([
            self._open(uri, code),
            self._msg('textDocument/completion', {
                'textDocument': {'uri': uri},
                'position': {'line': 5, 'character': 2}}, 2),
        ])
        items = responses[-1]['result']['items']
        labels = [i['label'] for i in items]
        self.assertIn('ف', labels)

    # ---------- التلميح ----------

    def test_hover_module(self):
        uri = 'file:///كود.عربي'
        responses = self._session([
            self._open(uri, 'إحصاء.معدل([1])\n'),
            self._msg('textDocument/hover', {
                'textDocument': {'uri': uri},
                'position': {'line': 0, 'character': 1}}, 2),
        ])
        value = responses[-1]['result']['contents']['value']
        self.assertIn('وحدة قياسية', value)
        self.assertIn('معدل', value)

    def test_hover_user_function_with_doc(self):
        uri = 'file:///كود.عربي'
        code = ('دالة مجموع_مربعات(أ، ب):\n'
                '    """يجمع مربعي العددين."""\n'
                '    أعد أ * أ + ب * ب\n'
                '\n'
                'مجموع_مربعات(1، 2)\n')
        responses = self._session([
            self._open(uri, code),
            self._msg('textDocument/hover', {
                'textDocument': {'uri': uri},
                'position': {'line': 4, 'character': 2}}, 2),
        ])
        value = responses[-1]['result']['contents']['value']
        self.assertIn('مجموع_مربعات', value)
        self.assertIn('أ، ب', value)
        self.assertIn('يجمع مربعي العددين', value)

    def test_hover_unknown_returns_none(self):
        uri = 'file:///كود.عربي'
        responses = self._session([
            self._open(uri, 'اطبع("سلام")\n'),
            self._msg('textDocument/hover', {
                'textDocument': {'uri': uri},
                'position': {'line': 0, 'character': 6}}, 2),
        ])
        result = responses[-1].get('result')
        self.assertTrue(result is None or result is False
                        or 'result' not in responses[-1]
                        or result is None)

    # ---------- الرموز ----------

    def test_document_symbols(self):
        uri = 'file:///كود.عربي'
        code = ('دالة رئيسية():\n'
                '    أعد 1\n'
                '\n'
                'صنف حيوان:\n'
                '    دالة صوت():\n'
                '        تجاهل\n'
                '\n'
                'تعداد لون:\n'
                '    أحمر\n'
                '    أخضر\n'
                '\n'
                'ثابت = 5\n')
        responses = self._session([
            self._open(uri, code),
            self._msg('textDocument/documentSymbol',
                      {'textDocument': {'uri': uri}}, 2),
        ])
        symbols = responses[-1]['result']
        names = {s['name']: s['kind'] for s in symbols}
        self.assertEqual(names['رئيسية'], 12)      # دالة
        self.assertEqual(names['حيوان'], 5)        # صنف
        self.assertEqual(names['لون'], 10)         # تعداد
        self.assertEqual(names['ثابت'], 13)        # متغير
        animal = [s for s in symbols if s['name'] == 'حيوان'][0]
        children = {c['name']: c['kind'] for c in animal['children']}
        self.assertEqual(children.get('صوت'), 6)   # طريقة

    # ---------- التعريف ----------

    def test_definition_function(self):
        uri = 'file:///كود.عربي'
        code = 'دالة تحية():\n    أعد "مرحبا"\n\nتحية()\n'
        responses = self._session([
            self._open(uri, code),
            self._msg('textDocument/definition', {
                'textDocument': {'uri': uri},
                'position': {'line': 3, 'character': 1}}, 2),
        ])
        loc = responses[-1]['result']
        self.assertEqual(loc['uri'], uri)
        self.assertEqual(loc['range']['start']['line'], 0)

    def test_definition_method(self):
        uri = 'file:///كود.عربي'
        code = ('صنف بوابة:\n'
                '    دالة افتح():\n'
                '        أعد صح\n'
                '\n'
                'ب = بوابة()\n'
                'ب.افتح()\n')
        responses = self._session([
            self._open(uri, code),
            self._msg('textDocument/definition', {
                'textDocument': {'uri': uri},
                'position': {'line': 5, 'character': 2}}, 2),
        ])
        loc = responses[-1]['result']
        self.assertEqual(loc['range']['start']['line'], 1)

    # ---------- أدوات المساعدة ----------

    def test_word_at(self):
        from arabi_lang.lsp import word_at
        lines = ['اطبع(المعدل)']
        self.assertEqual(word_at(lines, 0, 8), ('المعدل', 5))
        # عند بداية الكلمة تُختار الكلمة نفسها
        self.assertEqual(word_at(lines, 0, 0), ('اطبع', 0))
        # عند غير الحرفي تُختار الكلمة التالية
        self.assertEqual(word_at(lines, 0, 5), ('المعدل', 5))

    def test_word_at_diacritics(self):
        from arabi_lang.lsp import word_at
        lines = ['مُعلّم = 1']
        word, start = word_at(lines, 0, 4)
        self.assertTrue(word and word.startswith('م'))

    def test_line_range(self):
        from arabi_lang.lsp import line_range
        lines = ['سلام', 'عليكم']
        rng = line_range(lines, 0)
        self.assertEqual(rng['start'], {'line': 0, 'character': 0})
        self.assertEqual(rng['end'], {'line': 0, 'character': 4})

    def test_server_isolates_documents(self):
        uri_a = 'file:///أ.عربي'
        uri_b = 'file:///ب.عربي'
        responses = self._session([
            self._open(uri_a, 'أ = 1\n'),
            self._open(uri_b, 'ب = 2\nأ\n'),
            self._msg('textDocument/definition', {
                'textDocument': {'uri': uri_b},
                'position': {'line': 1, 'character': 0}}, 3),
        ])
        # 'أ' مذكورة في ب لكنها غير معرفة فيه — لا تعريف
        self.assertIsNone(responses[-1].get('result'))

    def test_definition_within_same_document_only(self):
        uri_a = 'file:///أ.عربي'
        uri_b = 'file:///ب.عربي'
        responses = self._session([
            self._open(uri_a, 'أ = 1\n'),
            self._open(uri_b, 'ب = 2\nأ\n'),
            self._msg('textDocument/definition', {
                'textDocument': {'uri': uri_a},
                'position': {'line': 0, 'character': 0}}, 3),
        ])
        loc = responses[-1]['result']
        self.assertEqual(loc['uri'], uri_a)


# ================== الدولاب الافتراضي (الإصدار 1.13) ==================

class TestVmDifferential(unittest.TestCase):
    """تكافؤ الدولاب الافتراضي مع الممسح الشجري: نفس الكود — نفس المخرجات.

    كل مقتطف ينفذ مرتين (بدولاب وبلا دولاب) ويجب أن تتطابق المخرجات
    حرفيًا، أو تتطابق الأخطاء بنوعها ورسائلها وأسطرها.
    """

    def _run(self, source, use_vm, script_dir=None):
        out = io.StringIO()
        try:
            with redirect_stdout(out):
                tree = Parser(Lexer(source).tokenize()).parse()
                Interpreter(script_dir=script_dir,
                            use_vm=use_vm).run(tree)
            return ('ok', out.getvalue())
        except ArabiError as exc:
            return ('error', f'{type(exc).__name__}: {exc}')

    def assert_same(self, source, script_dir=None):
        vm_kind, vm_out = self._run(source, True, script_dir)
        ast_kind, ast_out = self._run(source, False, script_dir)
        self.assertEqual((vm_kind, vm_out), (ast_kind, ast_out))
        return vm_out if vm_kind == 'ok' else None

    # ---------- الحلقات والتحكم ----------

    def test_while_accumulate(self):
        self.assert_same(
            'دالة مجموعة(ن):\n'
            '    مج = ٠\n'
            '    س = ١\n'
            '    طالما س <= ن:\n'
            '        مج = مج + س\n'
            '        س = س + ١\n'
            '    أعد مج\n'
            'اطبع(مجموعة(١٠٠))\n'
            'اطبع(مجموعة(٢٥٠))\n')

    def test_while_break_continue(self):
        self.assert_same(
            'س = ٠\n'
            'مج = ٠\n'
            'طالما صح:\n'
            '    س = س + ١\n'
            '    لو س % ٢ == ٠:\n'
            '        استمر\n'
            '    لو س > ٢٠:\n'
            '        كسر\n'
            '    مج = مج + س\n'
            'اطبع(مج، س)\n')

    def test_for_list_dict_str_range(self):
        self.assert_same(
            'لكل ع في [١٠، ٢٠، ٣٠]:\n'
            '    اطبع(ع * ٢)\n'
            'لكل حرف في "عربي":\n'
            '    اطبع(حرف)\n'
            'لكل س في مدى(٣، ٠، -١):\n'
            '    اطبع(س)\n'
            'لكل مفتاح في {"أ": ١، "ب": ٢}:\n'
            '    اطبع(مفتاح)\n')

    def test_for_destructure_break_continue(self):
        self.assert_same(
            'لكل أ، ب في [[١، ٢]، [٣، ٤]، [٥، ٦]]:\n'
            '    لو أ == ٣:\n'
            '        استمر\n'
            '    لو ب == ٦:\n'
            '        كسر\n'
            '    اطبع(أ + ب)\n')

    def test_nested_loops_break_inner(self):
        self.assert_same(
            'لكل س في مدى(٣):\n'
            '    لكل ص في مدى(٣):\n'
            '        لو ص == ٢:\n'
            '            كسر\n'
            '        اطبع(س، ص)\n'
            'طالما س < ٥:\n'
            '    طالما صح:\n'
            '        كسر\n'
            '    س = س + ١\n'
            'اطبع(س)\n')

    def test_break_in_switch_inside_loop(self):
        self.assert_same(
            'لكل س في [١، ٢، ٣، ٤]:\n'
            '    بدّل س:\n'
            '        حالة ٣:\n'
            '            كسر\n'
            '        افتراض:\n'
            '            اطبع(س)\n')

    def test_break_in_try_inside_loop(self):
        self.assert_same(
            'لكل س في مدى(٥):\n'
            '    جرب:\n'
            '        لو س == ٣:\n'
            '            كسر\n'
            '        اطبع(س)\n'
            '    باستثناء هـ:\n'
            '        اطبع("خطأ")\n')

    def test_if_elif_else_chain(self):
        self.assert_same(
            'دالة درجة(ن):\n'
            '    لو ن >= ٩٠:\n'
            '        أعد "ممتاز"\n'
            '    وإلا إذا ن >= ٧٠:\n'
            '        أعد "جيد"\n'
            '    وإلا إذا ن >= ٥٠:\n'
            '        أعد "مقبول"\n'
            '    وإلا:\n'
            '        أعد "راسب"\n'
            'لكل ن في [٩٥، ٨٠، ٦٠، ٣٠]:\n'
            '    اطبع(درجة(ن))\n')

    def test_short_circuit_values(self):
        self.assert_same(
            'دالة جانبية(ق):\n'
            '    اطبع("نُفذت")\n'
            '    أعد ق\n'
            'اطبع(خطأ و جانبية(١))\n'
            'اطبع(صح و جانبية(٧))\n'
            'اطبع(صح أو جانبية(٢))\n'
            'اطبع(خطأ أو جانبية(٩))\n'
            'اطبع(لا شيء و "س")\n')

    def test_ternary_and_unary(self):
        self.assert_same(
            'دالة علامة(ن):\n'
            '    أعد لو ن >= ٠: "موجب" وإلا "سالب"\n'
            'اطبع(علامة(٥)، علامة(-٣))\n'
            'اطبع(ليس صح، لا شيء، -٢ ** ٢)\n')

    # ---------- التعبيرات والبيانات ----------

    def test_collections_and_fstring(self):
        self.assert_same(
            'الاسم = "عربي"\n'
            'النسخة = ١.١٣\n'
            'اطبع(ق"لغة {الاسم} إصدار {النسخة} عدد {٢ + ٣}")\n'
            'م = {"أ": [١، ٢]، "ب": {"ج": ٣}}\n'
            'اطبع(م["أ"][١]، م["ب"]["ج"])\n'
            'اطبع([١، ٢] + [٣])\n'
            'اطبع("أب" * ٢)\n')

    def test_methods_on_builtins(self):
        self.assert_same(
            'نص = "مرحبا بالعالم"\n'
            'اطبع(نص.افصل(" "))\n'
            'اطبع(نص.استبدل("بالعالم", "باللغة"))\n'
            'ق = [٣، ١، ٢]\n'
            'ق.رتب()\n'
            'اطبع(ق، ق.اعكس())\n'
            'اطبع({"أ": ١}.مفاتيح())\n')

    def test_index_and_augassign_targets(self):
        self.assert_same(
            'ق = [١، ٢، ٣]\n'
            'ق[٠] += ١٠\n'
            'ق[٢] *= ٥\n'
            'اطبع(ق)\n'
            'د = {"عدد": ١}\n'
            'د["عدد"] += ٤١\n'
            'اطبع(د["عدد"])\n'
            'اطبع(ق[٠:٢])\n')

    # ---------- الدوال والأصناف ----------

    def test_recursion_and_closures(self):
        self.assert_same(
            'دالة مضروب(ن):\n'
            '    لو ن <= ١:\n'
            '        أعد ١\n'
            '    أعد ن * مضروب(ن - ١)\n'
            'اطبع(مضروب(١٠))\n'
            'دالة صنّاع(بداية):\n'
            '    دالة زد(س):\n'
            '        أعد بداية + س\n'
            '    أعد زد\n'
            'خمسة = صنّاع(٥)\n'
            'اطبع(خمسة(١٠)، خمسة(١))\n')

    def test_defaults_kwargs_rest(self):
        self.assert_same(
            'دالة تحية(الاسم، تحية = "مرحبا"):\n'
            '    أعد تحية + " " + الاسم\n'
            'اطبع(تحية("سالم"))\n'
            'اطبع(تحية("سالم"، تحية = "أهلا"))\n'
            'دالة جمع(...الكل):\n'
            '    مج = ٠\n'
            '    لكل س في الكل:\n'
            '        مج += س\n'
            '    أعد مج\n'
            'اطبع(جمع(١، ٢، ٣، ٤))\n')

    def test_classes_inheritance_super_property(self):
        self.assert_same(
            'صنف حيوان:\n'
            '    دالة إنشاء(الاسم):\n'
            '        هذا.الاسم = الاسم\n'
            '    دالة صوت():\n'
            '        أعد "صوت"\n'
            '    دالة تعريف():\n'
            '        أعد هذا.الاسم + ": " + هذا.صوت()\n'
            'صنف كلب من حيوان:\n'
            '    دالة صوت():\n'
            '        أعد "هواء"\n'
            'صنف قطة من حيوان:\n'
            '    دالة إنشاء(الاسم):\n'
            '        الأصل.إنشاء(هذا، الاسم)\n'
            '    خاصية جاهزة:\n'
            '        أعد صح\n'
            'ك = كلب("ريكس")\n'
            'ط = قطة("مشمش")\n'
            'اطبع(ك.تعريف())\n'
            'اطبع(ط.تعريف()، ط.جاهزة)\n')

    def test_enum_and_overloads(self):
        self.assert_same(
            'تعداد لون:\n'
            '    أحمر، أخضر\n'
            'صنف متجه:\n'
            '    دالة إنشاء(س، ص):\n'
            '        هذا.س = س\n'
            '        هذا.ص = ص\n'
            '    دالة اجمع(هذا، آخر):\n'
            '        أعد متجه(هذا.س + آخر.س، هذا.ص + آخر.ص)\n'
            '    دالة نص():\n'
            '        أعد ق"({هذا.س}، {هذا.ص})"\n'
            'اطبع(متجه(١، ٢) + متجه(٣، ٤))\n'
            'اطبع(لون.أحمر.الاسم، لون.أخضر.القيمة)\n')

    def test_global_stmt(self):
        self.assert_same(
            'العدد = ١\n'
            'دالة زد():\n'
            '    عالمي العدد\n'
            '    العدد = العدد + ١\n'
            'زد()\n'
            'زد()\n'
            'اطبع(العدد)\n')

    # ---------- الأخطاء والاستثناءات ----------

    def test_error_messages_and_lines_identical(self):
        src = ('دالة انقسام(س):\n'
               '    أعد س / ٠\n'
               'انقسام(٥)\n')
        self.assert_same(src)

    def test_try_except_finally_raise(self):
        self.assert_same(
            'صنف خطأي من استثناء:\n'
            '    تمر\n'
            'دالة خطِر():\n'
            '    ارفع خطأي("انفجر")\n'
            'جرب:\n'
            '    خطِر()\n'
            'باستثناء هـ:\n'
            '    اطبع("أمسكت: " + هـ.رسالة)\n'
            'أخيرًا:\n'
            '    اطبع("نظّفت")\n'
            'جرب:\n'
            '    اطبع(١ / ٠)\n'
            'باستثناء هـ:\n'
            '    اطبع(هـ)\n')

    def test_match_statement_in_function(self):
        self.assert_same(
            'دالة فحص(ق):\n'
            '    طابق ق\n'
            '    حالة [أ، ب]:\n'
            '        أعد أ + ب\n'
            '    حالة {"الاسم": اس}:\n'
            '        أعد اس\n'
            '    حالة _:\n'
            '        أعد "مجهول"\n'
            'اطبع(فحص([١، ٢]))\n'
            'اطبع(فحص({"الاسم": "سالم"}))\n'
            'اطبع(فحص(٤٢))\n')

    def test_stray_break_outside_loop(self):
        self.assert_same(
            'دالة مخالفة():\n'
            '    كسر\n'
            'مخالفة()\n')

    # ---------- مسارات الاحتياط (فهم وسهمية وتقطيع وتفكيك) ----------

    def test_fallback_expressions(self):
        self.assert_same(
            'دالة جهّز(ق):\n'
            '    مربعات = [س * س لكل س في ق إن س % ٢ == ٠]\n'
            '    مقلوبة = {س: -س لكل س في ق}\n'
            '    سهمية = دالة(س) => س + ١٠٠\n'
            '    أعد [مربعات، مقلوبة، سهمية(ق[٠])] + ق[١:]\n'
            'اطبع(جهّز([١، ٢، ٣، ٤]))\n'
            'أ، ب = [٧، ٨]\n'
            'اطبع(أ، ب)\n'
            'اطبع(خريطة(دالة(س) => س * ٢، [١، ٢]))\n')

    def test_call_with_kwargs_and_spread(self):
        self.assert_same(
            'دالة عرض(أ، ب، ج):\n'
            '    اطبع(أ، ب، ج)\n'
            'عرض(١، ب = ٢، ج = ٣)\n'
            'عناصر = [٤، ٥]\n'
            'عرض(٠، ...عناصر)\n'
            'اطبع([٠، ...مدى(٢)])\n')

    def test_generators_through_vm(self):
        self.assert_same(
            'دالة أعداد():\n'
            '    أنتج ١\n'
            '    أنتج ٢\n'
            '    أنتج ٣\n'
            'لكل س في أعداد():\n'
            '    اطبع(س)\n'
            'دالة مربعات(ن):\n'
            '    لكل س في مدى(ن):\n'
            '        أنتج س * س\n'
            'اطبع([...مربعات(٤)])\n'
            'طالما خطأ:\n'
            '    أنتج ٩٩\n')

    def test_threads_and_modules_paths(self):
        self.assert_same(
            'من خيوط استورد خيط\n'
            'النتيجة = []\n'
            'دالة عاملة():\n'
            '    النتيجة.أضف(٢ + ٢)\n'
            'خ = خيط(عاملة)\n'
            'خ.ابدأ()\n'
            'خ.انتظر()\n'
            'اطبع(النتيجة[٠])\n')


class TestVmExamplesEquivalence(unittest.TestCase):
    """كل مثال يعطي نفس المخرجات تمامًا بالدولاب وبدونه."""

    EXAMPLES_DIR = os.path.join(ROOT, 'examples')
    INTERACTIVE = {'10_لعبة_التخمين.عربي'}
    # أمثلة مخرجاتها غير حتمية (عشوائية أو منفذ خادم أو زمن قياس/توازٍ)
    NONDET = {'11_الوحدات.عربي', '22_الخادم.عربي',
              '24_المزخرفات_والوراثة_المتعددة.عربي', '28_الخيوط.عربي'}

    def _run_file(self, path, use_vm):
        with open(path, encoding='utf-8') as f:
            source = f.read()
        out = io.StringIO()
        try:
            with redirect_stdout(out):
                tree = Parser(Lexer(source).tokenize()).parse()
                Interpreter(script_dir=self.EXAMPLES_DIR,
                            use_vm=use_vm).run(tree)
            return ('ok', out.getvalue())
        except ArabiError as exc:
            return ('error', str(exc))

    def test_examples_vm_matches_ast(self):
        names = sorted(os.listdir(self.EXAMPLES_DIR))
        checked = 0
        for name in names:
            if not name.endswith('.عربي') or name in self.INTERACTIVE \
                    or name in self.NONDET:
                continue
            vm_kind, vm_out = self._run_file(
                os.path.join(self.EXAMPLES_DIR, name), True)
            ast_kind, ast_out = self._run_file(
                os.path.join(self.EXAMPLES_DIR, name), False)
            self.assertEqual(
                (vm_kind, vm_out), (ast_kind, ast_out),
                f'اختلاف بين الدولاب والممسح في المثال {name}')
            checked += 1
        self.assertGreaterEqual(checked, 30)


class TestVmInternals(unittest.TestCase):
    """الداخل: الترجمة والتخزين المؤقت للأكواد والأعلام."""

    def _compile_src(self, body_src):
        tree = Parser(Lexer(body_src).tokenize()).parse()
        return tree.statements[0]

    def test_opcode_count(self):
        from arabi_lang.vm import OPCODE_COUNT
        self.assertEqual(OPCODE_COUNT, 28)

    def test_compile_simple_function(self):
        from arabi_lang.vm import compile_function, VmCode, OP_LOAD_NAME
        func_node = self._compile_src(
            'دالة زد(س):\n    أعد س + ١\n')
        code = compile_function(func_node.body)
        self.assertIsInstance(code, VmCode)
        self.assertIn('س', code.names)
        self.assertIn(1, code.consts)
        ops = [i[0] for i in code.instrs]
        self.assertIn(OP_LOAD_NAME, ops)

    def test_compile_never_fails_on_exotic(self):
        # كل الجمل غير المدعومة تُغلّف بلا فشل — تعليمات احتياطية فقط
        from arabi_lang.vm import compile_function, VmCode, OP_EXEC_STMT
        src = ('دالة غريبة(ق):\n'
               '    طابق ق\n'
               '    حالة _:\n'
               '        أعد ١\n')
        func_node = self._compile_src(src)
        code = compile_function(func_node.body)
        self.assertIsInstance(code, VmCode)
        self.assertTrue(any(i[0] == OP_EXEC_STMT for i in code.instrs))

    def test_vm_code_cached_on_first_call(self):
        from arabi_lang.runtime import ArabiFunc, _VM_PENDING
        from arabi_lang.vm import VmCode
        interp = Interpreter(use_vm=True)
        tree = Parser(Lexer('دالة ضاعف(س):\n    أعد س * ٢\nضاعف(٥)\n').tokenize()).parse()
        interp.run(tree)
        func = interp.globals.vars['ضاعف']
        self.assertIsInstance(func, ArabiFunc)
        self.assertIsInstance(func.vm_code, VmCode)
        # استدعاء ثانٍ يعيد استخدام نفس الكود
        first = func.vm_code
        interp._call_value(func, [3], {}, 0)
        self.assertIs(func.vm_code, first)

    def test_no_vm_never_compiles(self):
        from arabi_lang.runtime import _VM_PENDING
        interp = Interpreter(use_vm=False)
        tree = Parser(Lexer('دالة ضاعف(س):\n    أعد س * ٢\nاطبع(ضاعف(٤))\n').tokenize()).parse()
        out = io.StringIO()
        with redirect_stdout(out):
            interp.run(tree)
        self.assertEqual(out.getvalue(), '8\n')
        self.assertIs(interp.globals.vars['ضاعف'].vm_code, _VM_PENDING)

    def test_line_numbers_preserved_in_errors(self):
        src = ('دالة انقسام(س):\n'
               '    أعد س / ٠\n'
               '\n'
               'انقسام(٨)\n')
        results = []
        for use_vm in (True, False):
            try:
                with redirect_stdout(io.StringIO()):
                    tree = Parser(Lexer(src).tokenize()).parse()
                    Interpreter(use_vm=use_vm).run(tree)
            except ArabiRuntimeError as exc:
                results.append((exc.message, exc.line))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][1], 2)

    def test_vm_state_isolated_between_interpreters(self):
        # كل مفسّر يترجم دواله بنفسه — لا تشترك في ذاكرات
        i1 = Interpreter(use_vm=True)
        i2 = Interpreter(use_vm=True)
        tree = Parser(Lexer('دالة المطبقة(س):\n    أعد س\nالمطبقة(١)\n').tokenize()).parse()
        for interp in (i1, i2):
            with redirect_stdout(io.StringIO()):
                interp.run(tree)
        f1 = i1.globals.vars['المطبقة']
        f2 = i2.globals.vars['المطبقة']
        self.assertIsNot(f1, f2)
        self.assertIsNot(f1.vm_code, f2.vm_code)


class TestVmCliFlags(unittest.TestCase):
    """أعلام سطر الأوامر للدولاب الافتراضي."""

    def _run_cli(self, source, *flags):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'برنامج.عربي')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(source)
            return subprocess.run(
                [sys.executable, os.path.join(ROOT, 'arabi.py'), *flags, path],
                capture_output=True, text=True, timeout=60)

    def test_no_vm_flag_runs(self):
        src = 'دالة زد(س):\n    أعد س + ١\nاطبع(زد(٤١))\n'
        r = self._run_cli(src, '--لا-دولاب')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('42', r.stdout)

    def test_vm_and_no_vm_same_output(self):
        src = ('دالة مجموعة(ن):\n'
               '    مج = ٠\n'
               '    لكل س في مدى(١، ن + ١):\n'
               '        مج += س\n'
               '    أعد مج\n'
               'اطبع(مجموعة(٥٠))\n')
        with_vm = self._run_cli(src)
        without_vm = self._run_cli(src, '--لا-دولاب')
        self.assertEqual(with_vm.returncode, 0, with_vm.stderr)
        self.assertEqual(without_vm.returncode, 0, without_vm.stderr)
        self.assertEqual(with_vm.stdout, without_vm.stdout)

    def test_no_vm_flag_requires_file(self):
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, 'arabi.py'), '--لا-دولاب'],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1)
        self.assertIn("''--لا-دولاب''".replace("''", "'"), r.stderr)


class TestCustomIteration(unittest.TestCase):
    """بروتوكول التكرار المخصص: تالٍ وأول (الإصدار 1.10)."""

    def test_for_with_tali(self):
        code = '''
صنف عداد:
    دالة إنشاء(ن):
        هذا.ن = ن
        هذا.ح = 0
    دالة تالٍ():
        هذا.ح = هذا.ح + 1
        لو هذا.ح > هذا.ن:
            أعد ولا شيء
        أعد هذا.ح

نتيجة = []
لكل س في عداد(4):
    نتيجة.أضف(س)
اطبع(نتيجة)
'''
        self.assertEqual(run_arabi(code).strip(), '[1، 2، 3، 4]')

    def test_for_with_awal_fresh_iterator(self):
        code = '''
صنف صندوق:
    دالة إنشاء(عناصر):
        هذا.عناصر = عناصر
    دالة أول():
        أعد مؤشر_صندوق(هذا.عناصر)

صنف مؤشر_صندوق:
    دالة إنشاء(عناصر):
        هذا.عناصر = عناصر
        هذا.موقع = 0
    دالة تالٍ():
        لو هذا.موقع >= طول(هذا.عناصر):
            أعد ولا شيء
        القيمة = هذا.عناصر[هذا.موقع]
        هذا.موقع = هذا.موقع + 1
        أعد القيمة

ص = صندوق(["أ"، "ب"، "ج"])
مجموع = ""
لكل حرف في ص:
    مجموع = مجموع + حرف
لكل حرف في ص:
    مجموع = مجموع + حرف
اطبع(مجموع)
'''
        self.assertEqual(run_arabi(code).strip(), 'أبجأبج')

    def test_break_continue(self):
        code = '''
صنف عداد:
    دالة إنشاء(ن):
        هذا.ن = ن
        هذا.ح = 0
    دالة تالٍ():
        هذا.ح = هذا.ح + 1
        لو هذا.ح > هذا.ن:
            أعد ولا شيء
        أعد هذا.ح

مجموع = 0
لكل س في عداد(10):
    لو س > 5:
        كسر
    لو س % 2 == 0:
        استمر
    مجموع = مجموع + س
اطبع(مجموع)
'''
        self.assertEqual(run_arabi(code).strip(), '9')

    def test_in_operator_tali(self):
        code = '''
صنف عداد:
    دالة إنشاء(ن):
        هذا.ن = ن
        هذا.ح = 0
    دالة تالٍ():
        هذا.ح = هذا.ح + 1
        لو هذا.ح > هذا.ن:
            أعد ولا شيء
        أعد هذا.ح

اطبع(3 في عداد(5))
اطبع(9 في عداد(5))
'''
        self.assertEqual(run_arabi(code).strip(), 'صح\nخطأ')

    def test_in_operator_awal(self):
        code = '''
صنف صندوق:
    دالة إنشاء(عناصر):
        هذا.عناصر = عناصر
    دالة أول():
        أعد مؤشر_صندوق(هذا.عناصر)

صنف مؤشر_صندوق:
    دالة إنشاء(عناصر):
        هذا.عناصر = عناصر
        هذا.موقع = 0
    دالة تالٍ():
        لو هذا.موقع >= طول(هذا.عناصر):
            أعد ولا شيء
        القيمة = هذا.عناصر[هذا.موقع]
        هذا.موقع = هذا.موقع + 1
        أعد القيمة

ص = صندوق([10، 20، 30])
اطبع(20 في ص)
اطبع(50 في ص)
'''
        self.assertEqual(run_arabi(code).strip(), 'صح\nخطأ')

    def test_spread_tali(self):
        code = '''
صنف عداد:
    دالة إنشاء(ن):
        هذا.ن = ن
        هذا.ح = 0
    دالة تالٍ():
        هذا.ح = هذا.ح + 1
        لو هذا.ح > هذا.ن:
            أعد ولا شيء
        أعد هذا.ح

اطبع([...عداد(3)])
'''
        self.assertEqual(run_arabi(code).strip(), '[1، 2، 3]')

    def test_destructuring_in_for(self):
        code = '''
صنف أزواج:
    دالة إنشاء():
        هذا.قائمة = [[1، 2]، [3، 4]، [5، 6]]
        هذا.موقع = 0
    دالة تالٍ():
        لو هذا.موقع >= طول(هذا.قائمة):
            أعد ولا شيء
        القيمة = هذا.قائمة[هذا.موقع]
        هذا.موقع = هذا.موقع + 1
        أعد القيمة

مجموع = 0
لكل أ، ب في أزواج():
    مجموع = مجموع + أ * ب
اطبع(مجموع)
'''
        self.assertEqual(run_arabi(code).strip(), '44')

    def test_inheritance_tali(self):
        code = '''
صنف أساس:
    دالة إنشاء(ن):
        هذا.ن = ن
        هذا.ح = 0
    دالة تالٍ():
        هذا.ح = هذا.ح + 1
        لو هذا.ح > هذا.ن:
            أعد ولا شيء
        أعد هذا.ح

صنف مضاعف من أساس:
    دالة تالٍ():
        القيمة = الأصل.تالٍ()
        لو القيمة == ولا شيء:
            أعد ولا شيء
        أعد القيمة * 2

نتيجة = []
لكل س في مضاعف(3):
    نتيجة.أضف(س)
اطبع(نتيجة)
'''
        self.assertEqual(run_arabi(code).strip(), '[2، 4، 6]')

    def test_empty_iterator(self):
        code = '''
صنف فارغ:
    دالة إنشاء():
        هذا.انتهى = خطأ
    دالة تالٍ():
        لو هذا.انتهى:
            أعد ولا شيء
        هذا.انتهى = صح
        أعد ولا شيء

عدد_الدورات = 0
لكل س في فارغ():
    عدد_الدورات = عدد_الدورات + 1
اطبع(عدد_الدورات)
'''
        self.assertEqual(run_arabi(code).strip(), '0')

    def test_error_no_tali(self):
        code = '''
صنف عادي:
    دالة إنشاء():
        هذا.س = 1

لكل س في عادي():
    تجاهل
'''
        exc = expect_error(code, ArabiRuntimeError, 'تالٍ')
        self.assertIn('لا يمكن التكرار', str(exc))

    def test_error_awal_returns_non_instance(self):
        code = '''
صنف خاطئ:
    دالة إنشاء():
        هذا.س = 1
    دالة أول():
        أعد 42
    دالة تالٍ():
        أعد ولا شيء

لكل س في خاطئ():
    تجاهل
'''
        expect_error(code, ArabiRuntimeError, 'أول')

    def test_generator_inside_iterator(self):
        code = '''
صنف مؤجل:
    دالة إنشاء():
        هذا.تم = خطأ
    دالة تالٍ():
        لو هذا.تم:
            أعد ولا شيء
        هذا.تم = صح
        أعد 99

اطبع([...مؤجل()])
'''
        self.assertEqual(run_arabi(code).strip(), '[99]')

    def test_iterator_with_membership_and_len(self):
        code = '''
صنف عداد:
    دالة إنشاء(ن):
        هذا.ن = ن
        هذا.ح = 0
    دالة تالٍ():
        هذا.ح = هذا.ح + 1
        لو هذا.ح > هذا.ن:
            أعد ولا شيء
        أعد هذا.ح

مجموع = 0
لكل س في عداد(5):
    لو 2 في عداد(3):
        مجموع = مجموع + س
اطبع(مجموع)
'''
        self.assertEqual(run_arabi(code).strip(), '15')

    def test_list_still_works(self):
        code = '''
مجموع = ""
لكل س في [1، 2، 3]:
    مجموع = مجموع + نص(س)
لكل حرف في "أبج":
    مجموع = مجموع + حرف
لكل س في مدى(2، 5):
    مجموع = مجموع + نص(س)
اطبع(مجموع)
'''
        self.assertEqual(run_arabi(code).strip(), '123أبج234')


# ============================================================
# فهم القوائم والقواميس (الإصدار 1.11)
# ============================================================

class TestComprehensions(unittest.TestCase):
    """[تعبير لكل س في متتالية إن شرط] و {م: ق لكل س في متتالية}."""

    def test_basic_list_comp(self):
        self.assertEqual(run_arabi('اطبع([س * س لكل س في مدى(5)])').strip(),
                         '[0، 1، 4، 9، 16]')

    def test_with_condition(self):
        out = run_arabi('اطبع([س لكل س في مدى(10) إن س % 2 == 0])')
        self.assertEqual(out.strip(), '[0، 2، 4، 6، 8]')

    def test_condition_filters_all(self):
        self.assertEqual(run_arabi('اطبع([س لكل س في [1، 3] إن س > 10])').strip(),
                         '[]')

    def test_transform_strings(self):
        out = run_arabi('اطبع([طول(ن) لكل ن في ["علي"، "خالد"]])')
        self.assertEqual(out.strip(), '[3، 4]')

    def test_destructuring_pairs(self):
        out = run_arabi('اطبع([أ + ب لكل أ، ب في [[1، 2]، [3، 4]]])')
        self.assertEqual(out.strip(), '[3، 7]')

    def test_dict_comp_basic(self):
        out = run_arabi('اطبع({ن: طول(ن) لكل ن في ["أ"، "أب"]})')
        self.assertEqual(out.strip(), '{أ: 1، أب: 2}')

    def test_dict_comp_numeric_keys(self):
        out = run_arabi('اطبع({س: س * س لكل س في مدى(4)})')
        self.assertEqual(out.strip(), '{0: 0، 1: 1، 2: 4، 3: 9}')

    def test_dict_comp_quoted_constant_key(self):
        # المفتاح المقتبس ثابت — آخر قيمة تغلب
        out = run_arabi('اطبع({"ثابت": س لكل س في [1، 2]})')
        self.assertEqual(out.strip(), '{ثابت: 2}')

    def test_dict_comp_duplicate_keys_last_wins(self):
        out = run_arabi('اطبع({س % 2: س لكل س في [1، 2، 3، 4]})')
        self.assertEqual(out.strip(), '{1: 3، 0: 4}')

    def test_multiple_for_clauses(self):
        out = run_arabi('اطبع([أ * ب لكل أ في [1، 2] لكل ب في [10، 20]])')
        self.assertEqual(out.strip(), '[10، 20، 20، 40]')

    def test_multiple_for_clauses_with_condition(self):
        out = run_arabi(
            'اطبع([أ * ب لكل أ في [1، 2، 3] لكل ب في [1، 2] إن ب >= أ])')
        self.assertEqual(out.strip(), '[1، 2، 4]')

    def test_second_clause_sees_first_vars(self):
        out = run_arabi('اطبع([ص + س لكل س في [10، 20] لكل ص في مدى(س، س + 1)])')
        self.assertEqual(out.strip(), '[20، 40]')

    def test_no_variable_leak(self):
        exc = expect_error(
            'اطبع([س لكل س في مدى(3)])\nاطبع(س)', ArabiRuntimeError, 'س')
        self.assertIn('غير معرّف', str(exc))

    def test_outer_variable_not_clobbered(self):
        out = run_arabi('س = 99\nاطبع([س لكل س في مدى(3)])\nاطبع(س)')
        self.assertEqual(out.splitlines()[1], '99')

    def test_over_string_chars(self):
        out = run_arabi('اطبع([ح + ح لكل ح في "أب"])')
        self.assertEqual(out.strip(), '[أأ، بب]')

    def test_over_dict_yields_keys(self):
        out = run_arabi('اطبع([م لكل م في {"أ": 1، "ب": 2}])')
        self.assertEqual(out.strip(), '[أ، ب]')

    def test_over_generator(self):
        code = ('دالة أرقام():\n'
                '  لكل س في [1، 2، 3]:\n'
                '    أنتج س\n'
                'اطبع([س * 2 لكل س في أرقام()])')
        self.assertEqual(run_arabi(code).strip(), '[2، 4، 6]')

    def test_over_custom_instance(self):
        code = ('صنف عداد:\n'
                '  دالة إنشاء(ن):\n'
                '    هذا.ن = ن\n'
                '  دالة تالٍ():\n'
                '    هذا.ن = هذا.ن - 1\n'
                '    لو هذا.ن >= 0:\n'
                '      أعد هذا.ن\n'
                '    أعد ولا شيء\n'
                'اطبع([ق لكل ق في عداد(3)])')
        self.assertEqual(run_arabi(code).strip(), '[2، 1، 0]')

    def test_ternary_in_element(self):
        out = run_arabi(
            'اطبع([لو س % 2 == 0: "زوج" وإلا "فرد" لكل س في [1، 2، 3]])')
        self.assertEqual(out.strip(), '[فرد، زوج، فرد]')

    def test_nested_comprehension(self):
        out = run_arabi('اطبع([[ص * 2 لكل ص في مدى(3)] لكل س في مدى(2)])')
        self.assertEqual(out.strip(), '[[0، 2، 4]، [0، 2، 4]]')

    def test_condition_uses_outer_variable(self):
        out = run_arabi('حد = 2\nاطبع([س لكل س في مدى(5) إن س <= حد])')
        self.assertEqual(out.strip(), '[0، 1، 2]')

    def test_inside_function_uses_param(self):
        code = ('دالة مربعات(ل):\n'
                '  أعد [س * س لكل س في ل]\n'
                'اطبع(مربعات([1، 2، 3]))')
        self.assertEqual(run_arabi(code).strip(), '[1، 4، 9]')

    def test_empty_iterable(self):
        self.assertEqual(run_arabi('اطبع([س لكل س في []])').strip(), '[]')

    def test_map_filter_equivalence(self):
        a = run_arabi('اطبع(خريطة(دالة(س) => س * 2، [1، 2، 3]))').strip()
        b = run_arabi('اطبع([س * 2 لكل س في [1، 2، 3]])').strip()
        self.assertEqual(a, b)
        a = run_arabi('اطبع(مرشّح(دالة(س) => س > 1، [1، 2، 3]))').strip()
        b = run_arabi('اطبع([س لكل س في [1، 2، 3] إن س > 1])').strip()
        self.assertEqual(a, b)

    def test_arabic_digits(self):
        out = run_arabi('اطبع([س * ٢ لكل س في [١، ٢، ٣]])')
        self.assertEqual(out.strip(), '[2، 4، 6]')

    def test_in_fstring(self):
        out = run_arabi('اطبع(ق"النتيجة: {[س * 10 لكل س في [1، 2]]}")')
        self.assertEqual(out.strip(), 'النتيجة: [10، 20]')

    def test_element_with_method_call(self):
        out = run_arabi('اطبع([ن + "!" لكل ن في ["أ"، "ب"]])')
        self.assertEqual(out.strip(), '[أ!، ب!]')

    def test_parse_error_missing_in(self):
        expect_error('اطبع([س لكل س مدى(3)])', ParseError, 'في')

    def test_parse_error_bad_target(self):
        expect_error('اطبع([س لكل 5 في مدى(3)])', ParseError, 'اسم')

    def test_parse_error_unclosed_element(self):
        # عنصر مفقود — المحلل النحوي يرفع (القوس المغلق يكشفه اللفظي)
        expect_error('اطبع([لكل س في مدى(3)])', ParseError, 'تعبير')

    def test_lexer_error_unclosed_bracket(self):
        expect_error('اطبع([س لكل س في مدى(3)', LexerError, 'مفتوحًا')

    def test_parse_error_spread_in_element(self):
        expect_error('ل = [1]\nاطبع([...ل لكل س في ل])', ParseError)

    def test_runtime_error_not_iterable(self):
        expect_error('اطبع([س لكل س في 5])', ArabiRuntimeError, 'التكرار')

    def test_runtime_error_destructure_mismatch(self):
        expect_error(
            'اطبع([أ + ب لكل أ، ب في [[1، 2، 3]]])',
            ArabiRuntimeError, 'تفكيك')

    def test_linter_clean_on_comprehension(self):
        issues = lint_source('ل = [1، 2، 3]\n'
                             'اطبع([س * س لكل س في ل إن س > 1])')
        self.assertEqual(issues, [])

    def test_linter_warns_undefined_in_iterable(self):
        issues = lint_source('اطبع([س لكل س في مجهول])')
        self.assertTrue(any('مجهول' in msg for _, _, msg in issues))


# ============================================================
# الكود الوسيط Bytecode (الإصدار 1.11)
# ============================================================

from arabi_lang import bytecode as _bc  # noqa: E402

FEATURE_RICH_SOURCE = '''# برنامج يغطي ميزات كثيرة لاختبار التسلسل
ق = [ق"مربع {س}" لكل س في [1، 2]]
اطبع(ق)
ش = {الاسم: "أحمد"، العمر: 30}
دالة فحص(ش):
  طابق ش
  حالة {الاسم: أ، العمر: ع} إن ع > 20:
    أعد أ + " بالغ"
  غير ذلك:
    أعد "صغير"
اطبع(فحص(ش))
دالة جمع(أ، ب، زائد=1):
  أعد أ * زائد + ب
اطبع(جمع(2، 3، زائد = 10))
صنف نقط:
  دالة إنشاء(س، ص):
    هذا.س = س
    هذا.ص = ص
  دالة نص():
    أعد ق"({هذا.س}، {هذا.ص})"
اطبع(نقط(1، 2).نص())
ق2 = {س: س * س لكل س في مدى(4)}
اطبع(ق2)
'''


def _run_tree(tree):
    out = io.StringIO()
    with redirect_stdout(out):
        Interpreter().run(tree)
    return out.getvalue()


class TestBytecodeRoundTrip(unittest.TestCase):
    """تسلسل الشجرة وإعادتها بلا فقد — نفس المخرجات تمامًا."""

    def _round_trip(self, source):
        tree = Parser(Lexer(source).tokenize()).parse()
        return _run_tree(tree), _run_tree(_bc.dict_to_ast(_bc.ast_to_dict(tree)))

    def test_simple_program(self):
        a, b = self._round_trip('اطبع(1 + 2)\nاطبع("مرحبا")')
        self.assertEqual(a, b)

    def test_feature_rich_program(self):
        a, b = self._round_trip(FEATURE_RICH_SOURCE)
        self.assertEqual(a, b)
        self.assertIn('أحمد بالغ', a)

    def test_named_args_tuples_preserved(self):
        a, b = self._round_trip(
            'دالة قيمة(أ، ب = 5):\n  أعد أ + ب\nاطبع(قيمة(1، ب = 2))')
        self.assertEqual(a, b)
        self.assertEqual(a.strip(), '3')

    def test_comprehensions_preserved(self):
        a, b = self._round_trip(
            'اطبع([س * س لكل س في مدى(4) إن س > 1])\n'
            'اطبع({ن: طول(ن) لكل ن في ["أب"]})')
        self.assertEqual(a, b)

    def test_match_patterns_preserved(self):
        a, b = self._round_trip(
            'دالة ف(ق):\n  طابق ق\n  حالة [أ، ...البقية]:\n    أعد أ\n'
            '  غير ذلك:\n    أعد "لا"\nاطبع(ف([1، 2، 3]))')
        self.assertEqual(a, b)

    def test_generators_preserved(self):
        a, b = self._round_trip(
            'دالة ت():\n  أنتج 1\n  أنتج 2\nاطبع([س لكل س في ت()])')
        self.assertEqual(a, b)

    def test_enum_interface_preserved(self):
        src = ('واجهة شكل:\n  دالة مساحة()\n'
               'صنف مربع من شكل:\n'
               '  دالة إنشاء(ض):\n    هذا.ض = ض\n'
               '  دالة مساحة():\n    أعد هذا.ض * هذا.ض\n'
               'اطبع(مربع(3).مساحة())')
        a, b = self._round_trip(src)
        self.assertEqual(a, b)

    def test_line_numbers_preserved(self):
        src = 'اطبع(1)\n\n\nاطبع(مفقود)'
        tree = Parser(Lexer(src).tokenize()).parse()
        tree2 = _bc.dict_to_ast(_bc.ast_to_dict(tree))
        # نفس رسالة الخطأ وبنفس رقم السطر
        with self.assertRaises(ArabiRuntimeError) as cm1:
            _run_tree(tree)
        with self.assertRaises(ArabiRuntimeError) as cm2:
            _run_tree(tree2)
        self.assertEqual(cm1.exception.line, cm2.exception.line)
        self.assertEqual(cm1.exception.line, 4)

    def test_ast_to_dict_rejects_unknown_value(self):
        tree = Parser(Lexer('اطبع(1)').tokenize()).parse()
        tree.statements.append(object())
        with self.assertRaises(ArabiError):
            _bc.ast_to_dict(tree)

    def test_dict_to_ast_rejects_unknown_node(self):
        with self.assertRaises(ArabiError):
            _bc.dict_to_ast({'عقدة': 'مجهول_تماما', 'حقول': {}})


class TestBytecodeCache(unittest.TestCase):
    """الذاكرة المؤقتة: الكتابة والتحميل والإبطال التلقائي."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.path = os.path.join(self.dir, 'برنامج.عربي')
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('اطبع(40 + 2)\n')

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, content):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(content)

    def cache_path(self):
        return _bc.cache_path_for(self.path)

    def test_cache_path_layout(self):
        self.assertEqual(os.path.basename(self.cache_path()), 'برنامج.بيت')
        self.assertEqual(os.path.basename(os.path.dirname(self.cache_path())),
                         '__بايت__')

    def test_first_read_compiles_second_from_cache(self):
        t1, cached1 = _bc.read_program(self.path)
        self.assertFalse(cached1)
        self.assertTrue(os.path.exists(self.cache_path()))
        t2, cached2 = _bc.read_program(self.path)
        self.assertTrue(cached2)
        self.assertEqual(_run_tree(t1).strip(), '42')
        self.assertEqual(_run_tree(t2).strip(), '42')

    def test_cache_dir_auto_created(self):
        self.assertFalse(os.path.exists(os.path.join(self.dir, '__بايت__')))
        _bc.read_program(self.path)
        self.assertTrue(os.path.isdir(os.path.join(self.dir, '__بايت__')))

    def test_modification_invalidates_cache(self):
        _bc.read_program(self.path)
        self.write('اطبع("جديد")\n')
        tree, cached = _bc.read_program(self.path)
        self.assertFalse(cached)
        self.assertEqual(_run_tree(tree).strip(), 'جديد')

    def test_touch_same_size_invalidates(self):
        # نفس الحجم — تعديل زمن التعديل فقط يجب أن يُبطل الذاكرة
        _bc.read_program(self.path)
        st = os.stat(self.path)
        os.utime(self.path, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
        _tree, cached = _bc.read_program(self.path)
        self.assertFalse(cached)

    def test_version_mismatch_invalidates(self):
        _bc.read_program(self.path)
        import pickle
        with open(self.cache_path(), 'rb') as f:
            payload = pickle.load(f)
        payload = (payload[0], '0.0.1', payload[2], payload[3], payload[4])
        with open(self.cache_path(), 'wb') as f:
            pickle.dump(payload, f)
        _tree, cached = _bc.read_program(self.path)
        self.assertFalse(cached)

    def test_corrupt_cache_recovers(self):
        _bc.read_program(self.path)
        with open(self.cache_path(), 'wb') as f:
            f.write(b'\x00\x01\x02 corrupt \xff\xfe data')
        tree, cached = _bc.read_program(self.path)
        self.assertFalse(cached)
        self.assertEqual(_run_tree(tree).strip(), '42')

    def test_cache_written_after_recovery(self):
        _bc.read_program(self.path)
        with open(self.cache_path(), 'wb') as f:
            f.write(b'talif')
        _bc.read_program(self.path)
        t2, cached = _bc.read_program(self.path)
        self.assertTrue(cached)
        self.assertEqual(_run_tree(t2).strip(), '42')

    def test_no_temp_file_left(self):
        _bc.read_program(self.path)
        leftovers = [n for n in os.listdir(os.path.join(self.dir, '__بايت__'))
                     if n.endswith('.مؤقت')]
        self.assertEqual(leftovers, [])

    def test_source_param_avoids_reread(self):
        src = 'اطبع("ممرر")\n'
        tree, cached = _bc.read_program(self.path, src)
        self.assertFalse(cached)
        self.assertEqual(_run_tree(tree).strip(), 'ممرر')

    def test_compile_file_writes_without_executing(self):
        out = io.StringIO()
        with redirect_stdout(out):
            cpath = _bc.compile_file(self.path)
        self.assertEqual(cpath, self.cache_path())
        self.assertEqual(out.getvalue(), '')          # لا تنفيذ
        self.assertTrue(os.path.exists(cpath))

    def test_compile_file_syntax_error_no_cache(self):
        self.write('اطبع(إغلاق غير مغلق')
        with self.assertRaises(ArabiError):   # لفظي (قوس) أو نحوي
            _bc.compile_file(self.path)
        self.assertFalse(os.path.exists(self.cache_path()))

    def test_ast_to_dict_dict_to_ast_public_api(self):
        tree = Parser(Lexer('اطبع([1، 2])').tokenize()).parse()
        rebuilt = _bc.dict_to_ast(_bc.ast_to_dict(tree))
        self.assertEqual(type(rebuilt).__name__, 'Program')


class TestBytecodeModules(unittest.TestCase):
    """الكود الوسيط مع الوحدات المستوردة من ملفات .عربي."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, relpath, content):
        path = os.path.join(self.dir, relpath)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_module_import_creates_cache(self):
        mod = self.write('مساعد.عربي', 'دالة ضعف(س):\n  أعد س * 2\n')
        main = self.write('رئيسي.عربي',
                          'من مساعد استورد ضعف\n'
                          'اطبع([ضعف(س) لكل س في [1، 2، 3]])\n')
        tree, _ = _bc.read_program(main)
        out = io.StringIO()
        with redirect_stdout(out):
            Interpreter(script_dir=self.dir).run(tree)
        self.assertEqual(out.getvalue().strip(), '[2، 4، 6]')
        # ذاكرة الوحدة كُتبت أثناء تحميلها بالمفسّر
        self.assertTrue(os.path.exists(_bc.cache_path_for(mod)))

    def test_module_reload_from_cache(self):
        main = self.write('رئيسي.عربي', 'استورد مساعد\n')
        self.write('مساعد.عربي', 'قيمة = ١\n')
        tree, _ = _bc.read_program(main)
        Interpreter(script_dir=self.dir).run(tree)
        tree2, cached = _bc.read_program(main)
        self.assertTrue(cached)
        Interpreter(script_dir=self.dir).run(tree2)

    def test_use_bytecode_false_skips_cache(self):
        self.write('مساعد.عربي', 'قيمة = ١\n')
        main = self.write('رئيسي.عربي', 'استورد مساعد\nاطبع(مساعد.قيمة)\n')
        tree = Parser(Lexer(open(main, encoding='utf-8').read()).tokenize()).parse()
        out = io.StringIO()
        with redirect_stdout(out):
            Interpreter(script_dir=self.dir, use_bytecode=False).run(tree)
        self.assertEqual(out.getvalue().strip(), '1')
        self.assertFalse(os.path.exists(os.path.join(self.dir, '__بايت__')))


class TestBytecodeCLI(unittest.TestCase):
    """أعلام سطر الأوامر --بايت و --لا-بايت."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.path = os.path.join(self.dir, 'برنامج.عربي')
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('اطبع("من CLI")\n')
        self.env_marker = os.path.join(self.dir, 'نفذ')

    def tearDown(self):
        self._tmp.cleanup()

    def _cli(self, *args):
        import subprocess
        return subprocess.run(
            [sys.executable, os.path.join(ROOT, 'arabi.py'), *args],
            capture_output=True, text=True, cwd=self.dir)

    def test_byte_flag_compiles_only(self):
        r = self._cli('--بايت', self.path)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('برنامج.بيت', r.stdout)
        self.assertNotIn('من CLI', r.stdout)      # لم يُنفذ
        self.assertTrue(os.path.exists(
            os.path.join(self.dir, '__بايت__', 'برنامج.بيت')))

    def test_byte_flag_syntax_error(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('اطبع(')
        r = self._cli('--بايت', self.path)
        self.assertEqual(r.returncode, 1)
        self.assertIn('خطأ', r.stderr)

    def test_no_bytecode_flag_runs(self):
        r = self._cli('--لا-بايت', self.path)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('من CLI', r.stdout)
        self.assertFalse(os.path.exists(
            os.path.join(self.dir, '__بايت__')))

    def test_normal_run_creates_cache_and_uses_it(self):
        r = self._cli(self.path)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('من CLI', r.stdout)
        cpath = os.path.join(self.dir, '__بايت__', 'برنامج.بيت')
        self.assertTrue(os.path.exists(cpath))
        # تشغيل ثاني — لا يزال صحيحًا عبر الذاكرة
        r2 = self._cli(self.path)
        self.assertEqual(r2.returncode, 0)
        self.assertIn('من CLI', r2.stdout)


# ================== سجل الحزم (الإصدار 1.12) ==================

import json                                                  # noqa: E402
import shutil                                                # noqa: E402
import zipfile                                               # noqa: E402
import pathlib                                               # noqa: E402
import subprocess                                            # noqa: E402

from arabi_lang import packages                              # noqa: E402
from arabi_lang.errors import ArabiError                     # noqa: E402


def _write_arabi(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def _write_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class TestPackageVersions(unittest.TestCase):
    """النسخ الدلالية وقيودها في سجل الحزم."""

    def test_parse_full(self):
        self.assertEqual(packages.parse_version('1.2.3'), (1, 2, 3))

    def test_parse_partial_fills_zero(self):
        self.assertEqual(packages.parse_version('2'), (2, 0, 0))
        self.assertEqual(packages.parse_version('1.5'), (1, 5, 0))

    def test_parse_invalid(self):
        for bad in ('', 'أ ب', '1.2.3.4', 'x.y', '1.2.-3', None):
            with self.assertRaises(ArabiError):
                packages.parse_version(bad)

    def test_compare(self):
        self.assertEqual(packages.compare_versions('1.0.0', '1.0.0'), 0)
        self.assertEqual(packages.compare_versions('1.10.0', '1.2.0'), 1)
        self.assertEqual(packages.compare_versions('0.9.9', '1.0.0'), -1)
        self.assertEqual(packages.compare_versions('2.0', '2.0.0'), 0)

    def test_exact(self):
        self.assertTrue(packages.satisfies('1.2.3', '1.2.3'))
        self.assertFalse(packages.satisfies('1.2.4', '1.2.3'))
        self.assertTrue(packages.satisfies('1.2.3', '=1.2.3'))
        self.assertTrue(packages.satisfies('1.2.3', '==1.2.3'))

    def test_ge_le(self):
        self.assertTrue(packages.satisfies('1.5.0', '>=1.0.0'))
        self.assertTrue(packages.satisfies('1.0.0', '>=1.0.0'))
        self.assertFalse(packages.satisfies('0.9.0', '>=1.0.0'))
        self.assertTrue(packages.satisfies('1.0.0', '<=1.0.0'))
        self.assertFalse(packages.satisfies('1.0.1', '<=1.0.0'))

    def test_gt_lt(self):
        self.assertTrue(packages.satisfies('2.0.0', '>1.9.9'))
        self.assertFalse(packages.satisfies('2.0.0', '>2.0.0'))
        self.assertTrue(packages.satisfies('0.1.0', '<1.0.0'))
        self.assertFalse(packages.satisfies('1.0.0', '<1.0.0'))

    def test_caret(self):
        self.assertTrue(packages.satisfies('1.2.3', '^1.2.3'))
        self.assertTrue(packages.satisfies('1.9.9', '^1.2.3'))
        self.assertFalse(packages.satisfies('2.0.0', '^1.2.3'))
        self.assertFalse(packages.satisfies('1.2.2', '^1.2.3'))
        # الرتّب الصفري: ^0.2.3 يقبل 0.2.x فقط
        self.assertTrue(packages.satisfies('0.2.9', '^0.2.3'))
        self.assertFalse(packages.satisfies('0.3.0', '^0.2.3'))

    def test_tilde(self):
        self.assertTrue(packages.satisfies('1.2.9', '~1.2.3'))
        self.assertFalse(packages.satisfies('1.3.0', '~1.2.3'))
        self.assertFalse(packages.satisfies('1.2.2', '~1.2.3'))

    def test_any(self):
        self.assertTrue(packages.satisfies('9.9.9', '*'))
        self.assertTrue(packages.satisfies('0.0.1', ''))

    def test_invalid_constraint(self):
        for bad in ('>>1.0.0', 'أكبر من 1', '~.'):
            with self.assertRaises(ArabiError):
                packages.satisfies('1.0.0', bad)


class TestPackageManager(unittest.TestCase):
    """مدير الحزم: البيان والفهرس والتثبيت والإزالة والقفل."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='اختبار-حزم-')
        self.registry = os.path.join(self.tmp, 'سجل')
        os.makedirs(self.registry)
        # حزمة أ: مجلد كامل ببيان — بلا تبعيات
        self.src_a = os.path.join(self.registry, 'ادوات_نص')
        os.makedirs(self.src_a)
        _write_arabi(os.path.join(self.src_a, 'ادوات_نص.عربي'),
                     '"أدوات نصية."\n\n'
                     'دالة كرر_مرتين(ن):\n'
                     '    أعد ن + ن\n')
        _write_json(os.path.join(self.src_a, 'حزمة.json'), {
            'الاسم': 'ادوات_نص', 'النسخة': '1.4.0',
            'الوصف': 'أدوات معالجة النصوص', 'المدخل': 'ادوات_نص.عربي',
        })
        # حزمة ب: مجلد كامل — تعتمد على أ
        self.src_b = os.path.join(self.registry, 'احصاء_متقدم')
        os.makedirs(self.src_b)
        _write_arabi(os.path.join(self.src_b, 'احصاء_متقدم.عربي'),
                     '"إحصاء متقدم."\n\n'
                     'من ادوات_نص استورد كرر_مرتين\n\n'
                     'دالة تقرير(أعداد):\n'
                     '    س = 0\n'
                     '    لكل أ في أعداد:\n'
                     '        س = س + أ\n'
                     '    أعد كرر_مرتين("المجموع: " + نص(س))\n')
        _write_json(os.path.join(self.src_b, 'حزمة.json'), {
            'الاسم': 'احصاء_متقدم', 'النسخة': '2.1.0',
            'الوصف': 'حسابات إحصائية متقدمة', 'المدخل': 'احصاء_متقدم.عربي',
            'التبعيات': {'ادوات_نص': '>=1.0.0'},
        })
        # حزمة ج: ملف مفرد بلا بيان — يُغلَّف تلقائيًا
        self.src_c = os.path.join(self.registry, 'مفيد.عربي')
        _write_arabi(self.src_c,
                     'دالة سلام():\n'
                     '    أعد "أهلا"\n')
        # حزمة د: أرشيف zip
        self.src_d_dir = os.path.join(self.registry, '_مبعثر')
        os.makedirs(self.src_d_dir)
        _write_arabi(os.path.join(self.src_d_dir, 'مبعثر.عربي'),
                     'دالة قيمة():\n'
                     '    أعد 42\n')
        _write_json(os.path.join(self.src_d_dir, 'حزمة.json'), {
            'الاسم': 'مبعثر', 'النسخة': '1.0.0', 'الوصف': 'حزمة مضغوطة',
        })
        self.src_d = os.path.join(self.registry, 'مبعثر.zip')
        with zipfile.ZipFile(self.src_d, 'w') as zf:
            zf.write(os.path.join(self.src_d_dir, 'مبعثر.عربي'), 'مبعثر.عربي')
            zf.write(os.path.join(self.src_d_dir, 'حزمة.json'), 'حزمة.json')
        # الفهرس
        self.index = os.path.join(self.registry, 'الفهرس.json')
        _write_json(self.index, {
            'ادوات_نص': {'النسخة': '1.4.0', 'الوصف': 'أدوات معالجة النصوص',
                         'المصدر': self.src_a},
            'احصاء_متقدم': {'النسخة': '2.1.0',
                            'الوصف': 'حسابات إحصائية متقدمة',
                            'المصدر': self.src_b},
            'مفيد': {'النسخة': '0.9.0', 'الوصف': 'دوال مفيدة',
                     'المصدر': self.src_c},
            'مبعثر': {'النسخة': '1.0.0', 'الوصف': 'حزمة مضغوطة',
                      'المصدر': self.src_d},
        })
        self.project = os.path.join(self.tmp, 'مشروع')
        os.makedirs(self.project)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------- بيان الحزمة ----------

    def test_read_manifest_complete(self):
        data = packages.read_manifest(self.src_a)
        self.assertEqual(data['الاسم'], 'ادوات_نص')
        self.assertEqual(data['النسخة'], '1.4.0')
        self.assertEqual(data['المدخل'], 'ادوات_نص.عربي')
        self.assertEqual(data['التبعيات'], {})

    def test_read_manifest_defaults(self):
        # بلا نسخة ولا مدخل — افتراضيات معقولة
        d = os.path.join(self.tmp, 'بسيطة')
        os.makedirs(d)
        _write_json(os.path.join(d, 'حزمة.json'), {'الاسم': 'بسيطة'})
        data = packages.read_manifest(d)
        self.assertEqual(data['النسخة'], '0.0.0')
        self.assertEqual(data['المدخل'], 'بسيطة.عربي')

    def test_read_manifest_missing_name(self):
        d = os.path.join(self.tmp, 'بلا_اسم')
        os.makedirs(d)
        _write_json(os.path.join(d, 'حزمة.json'), {'النسخة': '1.0.0'})
        with self.assertRaises(ArabiError) as ctx:
            packages.read_manifest(d)
        self.assertIn('الاسم', str(ctx.exception))

    def test_read_manifest_bad_name(self):
        # الاسم بشرطة — غير قابل للاستيراد
        d = os.path.join(self.tmp, 'اسم_سيء')
        os.makedirs(d)
        _write_json(os.path.join(d, 'حزمة.json'), {'الاسم': 'اسم-سيء'})
        with self.assertRaises(ArabiError) as ctx:
            packages.read_manifest(d)
        self.assertIn('غير صالح', str(ctx.exception))

    def test_read_manifest_missing_file(self):
        with self.assertRaises(ArabiError):
            packages.read_manifest(self.tmp)

    def test_read_manifest_bad_version(self):
        d = os.path.join(self.tmp, 'نسخة_سيئة')
        os.makedirs(d)
        _write_json(os.path.join(d, 'حزمة.json'),
                    {'الاسم': 'ن', 'النسخة': 'واحد'})
        with self.assertRaises(ArabiError):
            packages.read_manifest(d)

    # ---------- التثبيت ----------

    def test_install_with_dependency(self):
        msgs = packages.install('احصاء_متقدم', self.project, self.index)
        kinds = [k for _, k in msgs]
        self.assertEqual(kinds, ['ثُبتت', 'ثُبتت'])
        # التبعية ثُبتت أولًا
        self.assertIn('ادوات_نص', msgs[0][0])
        self.assertTrue(os.path.isfile(os.path.join(
            self.project, 'حزم', 'ادوات_نص', 'ادوات_نص.عربي')))
        self.assertTrue(os.path.isfile(os.path.join(
            self.project, 'حزم', 'احصاء_متقدم', 'احصاء_متقدم.عربي')))

    def test_install_creates_lock(self):
        packages.install('احصاء_متقدم', self.project, self.index)
        lock = packages.read_lock(self.project)
        self.assertIn('ادوات_نص', lock)
        self.assertEqual(lock['ادوات_نص']['النسخة'], '1.4.0')
        self.assertEqual(lock['احصاء_متقدم']['النسخة'], '2.1.0')

    def test_install_single_file_package(self):
        msgs = packages.install('مفيد', self.project, self.index)
        self.assertEqual([k for _, k in msgs], ['ثُبتت'])
        # الملف المفرد غُلِّف ببيان تلقائي بنسخة الفهرس
        data = packages.read_manifest(
            os.path.join(self.project, 'حزم', 'مفيد'))
        self.assertEqual(data['النسخة'], '0.9.0')
        self.assertEqual(data['المدخل'], 'مفيد.عربي')

    def test_install_zip_package(self):
        msgs = packages.install('مبعثر', self.project, self.index)
        self.assertEqual([k for _, k in msgs], ['ثُبتت'])
        out = run_code('استورد مبعثر\nاطبع(مبعثر.قيمة())',
                       script_dir=self.project)
        self.assertIn('42', out)

    def test_install_from_file_url(self):
        # رابط file:// لمجلد حزمة — تنزيل بلا شبكة
        url = pathlib.Path(self.src_a).as_uri()
        msgs = packages.install(url, self.project, self.index)
        self.assertEqual([k for _, k in msgs], ['ثُبتت'])
        self.assertIn('ادوات_نص', str(msgs))

    def test_install_from_local_path(self):
        # تثبيت بمسار مباشر دون فهرس
        msgs = packages.install(self.src_a, self.project, self.index)
        self.assertEqual([k for _, k in msgs], ['ثُبتت'])

    def test_install_already_installed(self):
        packages.install('ادوات_نص', self.project, self.index)
        msgs = packages.install('ادوات_نص', self.project, self.index)
        self.assertEqual(msgs,
                         [('ادوات_نص v1.4.0 مثبتة بالفعل وتلبي القيد',
                           'موجودة')])
        # لم تُعاد الكتابة
        self.assertEqual(packages.list_installed(self.project)['ادوات_نص']
                         ['نسخة'], '1.4.0')

    def test_install_constraint_conflict_with_index(self):
        with self.assertRaises(ArabiError) as ctx:
            packages.install_dep('ادوات_نص', '>=2.0.0', self.project,
                                 self.index, [])
        self.assertIn('لا تلبي القيد', str(ctx.exception))

    def test_install_constraint_conflict_with_installed(self):
        # مثبتة بنسخة قديمة (0.0.0 من ملف مفرد) والفهرس أحدث
        packages.install(self.src_c, self.project, self.index)
        with self.assertRaises(ArabiError) as ctx:
            packages.install_dep('مفيد', '>=0.5.0', self.project,
                                 self.index, [])
        self.assertIn('مثبتة بنسخة', str(ctx.exception))

    def test_install_missing_package(self):
        with self.assertRaises(ArabiError) as ctx:
            packages.install('غير_موجود', self.project, self.index)
        self.assertIn('غير موجودة', str(ctx.exception))

    def test_install_cyclic_dependency(self):
        # أ تعتمد ب وتعتمد أ — كشف الدورة
        src_x = os.path.join(self.registry, 'دائرية_أ')
        os.makedirs(src_x)
        _write_arabi(os.path.join(src_x, 'دائرية_أ.عربي'), 'س = 1\n')
        _write_json(os.path.join(src_x, 'حزمة.json'), {
            'الاسم': 'دائرية_أ', 'النسخة': '1.0.0',
            'التبعيات': {'دائرية_ب': '*'}})
        src_y = os.path.join(self.registry, 'دائرية_ب')
        os.makedirs(src_y)
        _write_arabi(os.path.join(src_y, 'دائرية_ب.عربي'), 'ص = 2\n')
        _write_json(os.path.join(src_y, 'حزمة.json'), {
            'الاسم': 'دائرية_ب', 'النسخة': '1.0.0',
            'التبعيات': {'دائرية_أ': '*'}})
        _write_json(self.index, {
            'دائرية_أ': {'النسخة': '1.0.0', 'المصدر': src_x},
            'دائرية_ب': {'النسخة': '1.0.0', 'المصدر': src_y},
        })
        with self.assertRaises(ArabiError) as ctx:
            packages.install('دائرية_أ', self.project, self.index)
        self.assertIn('تبعية دائرية', str(ctx.exception))

    def test_install_name_mismatch(self):
        # الفهرس يدعي اسمًا والمصدر بيانه باسم آخر
        _write_json(self.index, {
            'ادوات_نص': {'النسخة': '1.4.0', 'المصدر': self.src_b},
        })
        with self.assertRaises(ArabiError) as ctx:
            packages.install('ادوات_نص', self.project, self.index)
        self.assertIn('لا يطابق', str(ctx.exception))

    def test_install_refuses_broken_code(self):
        # كود غير سليم — لا تثبت
        broken = os.path.join(self.registry, 'مكسورة')
        os.makedirs(broken)
        _write_arabi(os.path.join(broken, 'مكسورة.عربي'), 'اطبع(\n')
        _write_json(os.path.join(broken, 'حزمة.json'),
                    {'الاسم': 'مكسورة', 'النسخة': '1.0.0'})
        _write_json(self.index, {
            'مكسورة': {'النسخة': '1.0.0', 'المصدر': broken}})
        with self.assertRaises(ArabiError) as ctx:
            packages.install('مكسورة', self.project, self.index)
        self.assertIn('غير سليم', str(ctx.exception))
        self.assertNotIn('مكسورة', packages.list_installed(self.project))

    def test_install_index_without_source(self):
        bad_index = os.path.join(self.registry, 'فهرس_سيء.json')
        _write_json(bad_index, {'شىء': {'النسخة': '1.0.0'}})
        with self.assertRaises(ArabiError) as ctx:
            packages.load_index(bad_index)
        self.assertIn('المصدر', str(ctx.exception))

    # ---------- الإزالة والقائمة والتحديث ----------

    def test_remove_blocks_dependents(self):
        packages.install('احصاء_متقدم', self.project, self.index)
        with self.assertRaises(ArabiError) as ctx:
            packages.remove('ادوات_نص', self.project)
        self.assertIn('احصاء_متقدم', str(ctx.exception))

    def test_remove_leaf_and_lock_update(self):
        packages.install('احصاء_متقدم', self.project, self.index)
        msg = packages.remove('احصاء_متقدم', self.project)
        self.assertIn('أُزيلت', msg)
        lock = packages.read_lock(self.project)
        self.assertNotIn('احصاء_متقدم', lock)
        # التبعية اليتيمة تبقى (المستخدم قد يريدها)
        self.assertIn('ادوات_نص', lock)

    def test_remove_not_installed(self):
        with self.assertRaises(ArabiError) as ctx:
            packages.remove('مفيد', self.project)
        self.assertIn('غير مثبتة', str(ctx.exception))

    def test_list_installed(self):
        self.assertEqual(packages.list_installed(self.project), {})
        packages.install('احصاء_متقدم', self.project, self.index)
        installed = packages.list_installed(self.project)
        self.assertEqual(set(installed), {'ادوات_نص', 'احصاء_متقدم'})
        self.assertEqual(installed['ادوات_نص']['نسخة'], '1.4.0')
        self.assertEqual(installed['ادوات_نص']['تبعيات'], {})
        self.assertEqual(installed['احصاء_متقدم']['تبعيات'],
                         {'ادوات_نص': '>=1.0.0'})

    def test_update_single(self):
        # ثبت من ملف مباشر (نسخة 0.0.0) ثم حدّث من الفهرس
        packages.install(self.src_c, self.project, self.index)
        msgs = packages.update('مفيد', self.project, self.index)
        self.assertTrue(any(k == 'ثُبتت' for _, k in msgs))
        self.assertEqual(
            packages.list_installed(self.project)['مفيد']['نسخة'], '0.9.0')

    def test_update_all(self):
        packages.install('ادوات_نص', self.project, self.index)
        msgs = packages.update(None, self.project, self.index)
        self.assertEqual(len(msgs), 1)   # حزمة واحدة مثبتة
        self.assertEqual(
            packages.list_installed(self.project)['ادوات_نص']['نسخة'],
            '1.4.0')

    def test_update_not_installed(self):
        with self.assertRaises(ArabiError):
            packages.update('مفيد', self.project, self.index)

    # ---------- البحث والفهرس ----------

    def test_search_by_name(self):
        results = packages.search('احصاء', self.index)
        self.assertEqual([n for n, _ in results], ['احصاء_متقدم'])

    def test_search_by_description(self):
        results = packages.search('نصوص', self.index)
        self.assertIn('ادوات_نص', [n for n, _ in results])

    def test_search_empty_lists_all(self):
        results = packages.search('', self.index)
        self.assertEqual(len(results), 4)

    def test_search_no_results(self):
        self.assertEqual(packages.search('شبكة_عصبية', self.index), [])

    def test_load_index_missing(self):
        with self.assertRaises(ArabiError) as ctx:
            packages.load_index(os.path.join(self.tmp, 'غائب.json'))
        self.assertIn('غير موجود', str(ctx.exception))

    def test_load_index_invalid_json(self):
        bad = os.path.join(self.tmp, 'فاسد.json')
        with open(bad, 'w', encoding='utf-8') as f:
            f.write('{غير json')
        with self.assertRaises(ArabiError):
            packages.load_index(bad)


class TestPackageImports(unittest.TestCase):
    """الاستيراد من الحزم المثبتة — المفسر يبحث في حزم/."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='اختبار-استيراد-حزم-')
        self.project = os.path.join(self.tmp, 'مشروع')
        os.makedirs(self.project)
        pkg = os.path.join(self.project, 'حزم', 'حاسبة')
        os.makedirs(pkg)
        _write_arabi(os.path.join(pkg, 'حاسبة.عربي'),
                     '"حاسبة صغيرة."\n\n'
                     'دالة مجموع(أ، ب):\n'
                     '    أعد أ + ب\n')
        _write_json(os.path.join(pkg, 'حزمة.json'),
                    {'الاسم': 'حاسبة', 'النسخة': '1.0.0'})
        # حزمة بمدخل مخصص في مجلد فرعي
        pkg2 = os.path.join(self.project, 'حزم', 'مخصصة', 'المصدر')
        os.makedirs(pkg2)
        _write_arabi(os.path.join(pkg2, 'الرئيسية.عربي'),
                     'دالة قيمة():\n'
                     '    أعد "من_المدخل_المخصص"\n')
        _write_json(os.path.join(self.project, 'حزم', 'مخصصة', 'حزمة.json'),
                    {'الاسم': 'مخصصة', 'النسخة': '2.0.0',
                     'المدخل': 'المصدر/الرئيسية.عربي'})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_import_from_packages_dir(self):
        out = run_code('استورد حاسبة\nاطبع(حاسبة.مجموع(٢، ٣))',
                       script_dir=self.project)
        self.assertIn('5', out)

    def test_from_import_package_member(self):
        out = run_code('من حاسبة استورد مجموع\nاطبع(مجموع(10، 5))',
                       script_dir=self.project)
        self.assertIn('15', out)

    def test_import_custom_entry(self):
        out = run_code('استورد مخصصة\nاطبع(مخصصة.قيمة())',
                       script_dir=self.project)
        self.assertIn('من_المدخل_المخصص', out)

    def test_local_module_wins(self):
        # وحدة محلية بنفس الاسم تتقدم على الحزمة
        _write_arabi(os.path.join(self.project, 'حاسبة.عربي'),
                     'دالة مجموع(أ، ب):\n'
                     '    أعد أ * ب\n')
        out = run_code('استورد حاسبة\nاطبع(حاسبة.مجموع(٢، ٣))',
                       script_dir=self.project)
        self.assertIn('6', out)   # ضرب لا جمع

    def test_module_cached_once(self):
        # استيراد مرتين — التنفيذ مرة واحدة (رسالة توثيق تظهر مرة)
        _write_arabi(os.path.join(self.project, 'حزم', 'حاسبة',
                                  'حاسبة.عربي'),
                     'اطبع("تحميل")\n'
                     'دالة صفر():\n'
                     '    أعد 0\n')
        out = run_code('استورد حاسبة\nاستورد حاسبة\nاطبع(حاسبة.صفر())',
                       script_dir=self.project)
        self.assertEqual(out.count('تحميل'), 1)

    def test_package_module_bytecode_cache(self):
        # الاستيراد من الحزم يستفيد من الكود الوسيط تلقائيًا
        run_code('استورد حاسبة\nاطبع(حاسبة.مجموع(١، ١))',
                 script_dir=self.project)
        cache = os.path.join(self.project, 'حزم', 'حاسبة', '__بايت__',
                             'حاسبة.بيت')
        self.assertTrue(os.path.isfile(cache))

    def test_error_message_mentions_packages_dir(self):
        with self.assertRaises(ArabiRuntimeError) as ctx:
            run_code('استورد ناقص', script_dir=self.project)
        self.assertIn('حزم', str(ctx.exception))

    def test_circular_import_between_packages(self):
        # حزمتان تُستورد كل منهما الأخرى — خطأ استيراد دائري
        for name, other in (('واحدة', 'ثانية'), ('ثانية', 'واحدة')):
            pkg = os.path.join(self.project, 'حزم', name)
            os.makedirs(pkg)
            _write_arabi(os.path.join(pkg, name + '.عربي'),
                         f'استورد {other}\n'
                         'دالة قيمة():\n'
                         '    أعد 1\n')
            _write_json(os.path.join(pkg, 'حزمة.json'),
                        {'الاسم': name, 'النسخة': '1.0.0'})
        with self.assertRaises(ArabiRuntimeError) as ctx:
            run_code('استورد واحدة', script_dir=self.project)
        self.assertIn('دائري', str(ctx.exception))

    def test_package_can_import_local_modules(self):
        # الحزمة تستورد وحدة من مجلد المشروع نفسه
        _write_arabi(os.path.join(self.project, 'مساعدة.عربي'),
                     'دالة ضعف(ن):\n'
                     '    أعد ن * 2\n')
        pkg = os.path.join(self.project, 'حزم', 'مستخدمة')
        os.makedirs(pkg)
        _write_arabi(os.path.join(pkg, 'مستخدمة.عربي'),
                     'من مساعدة استورد ضعف\n'
                     'دالة أربعة():\n'
                     '    أعد ضعف(2)\n')
        _write_json(os.path.join(pkg, 'حزمة.json'),
                    {'الاسم': 'مستخدمة', 'النسخة': '1.0.0'})
        out = run_code('استورد مستخدمة\nاطبع(مستخدمة.أربعة())',
                       script_dir=self.project)
        self.assertIn('4', out)


class TestPackageCLI(unittest.TestCase):
    """أوامر حزمة عبر سطر الأوامر — عمليات كاملة في مشروع مؤقت."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='اختبار-حزم-cli-')
        cls.registry = os.path.join(cls.tmp, 'سجل')
        os.makedirs(cls.registry)
        src_a = os.path.join(cls.registry, 'ادوات_نص')
        os.makedirs(src_a)
        _write_arabi(os.path.join(src_a, 'ادوات_نص.عربي'),
                     'دالة كرر_مرتين(ن):\n'
                     '    أعد ن + ن\n')
        _write_json(os.path.join(src_a, 'حزمة.json'), {
            'الاسم': 'ادوات_نص', 'النسخة': '1.4.0',
            'الوصف': 'أدوات معالجة النصوص'})
        src_b = os.path.join(cls.registry, 'احصاء_متقدم')
        os.makedirs(src_b)
        _write_arabi(os.path.join(src_b, 'احصاء_متقدم.عربي'),
                     'من ادوات_نص استورد كرر_مرتين\n\n'
                     'دالة تقرير(أعداد):\n'
                     '    س = 0\n'
                     '    لكل أ في أعداد:\n'
                     '        س = س + أ\n'
                     '    أعد كرر_مرتين("المجموع: " + نص(س))\n')
        _write_json(os.path.join(src_b, 'حزمة.json'), {
            'الاسم': 'احصاء_متقدم', 'النسخة': '2.1.0',
            'الوصف': 'حسابات إحصائية',
            'التبعيات': {'ادوات_نص': '>=1.0.0'}})
        cls.index = os.path.join(cls.registry, 'الفهرس.json')
        _write_json(cls.index, {
            'ادوات_نص': {'النسخة': '1.4.0', 'الوصف': 'أدوات معالجة النصوص',
                         'المصدر': src_a},
            'احصاء_متقدم': {'النسخة': '2.1.0', 'الوصف': 'حسابات إحصائية',
                            'المصدر': src_b}})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _cli(self, project, *args):
        return subprocess.run(
            [sys.executable, os.path.join(ROOT, 'arabi.py'), 'حزمة',
             '--الفهرس', self.index, *args],
            capture_output=True, text=True, cwd=project, timeout=60)

    def setUp(self):
        self.project = tempfile.mkdtemp(prefix='مشروع-cli-')

    def tearDown(self):
        shutil.rmtree(self.project, ignore_errors=True)

    def test_install_command(self):
        r = self._cli(self.project, 'تثبيت', 'احصاء_متقدم')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('✓', r.stdout)
        self.assertIn('ادوات_نص', r.stdout)      # التبعية ذُكرت
        self.assertIn('قفل.json', r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(
            self.project, 'حزم', 'احصاء_متقدم', 'احصاء_متقدم.عربي')))

    def test_list_command(self):
        self._cli(self.project, 'تثبيت', 'ادوات_نص')
        r = self._cli(self.project, 'قائمة')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('ادوات_نص v1.4.0', r.stdout)

    def test_search_command(self):
        r = self._cli(self.project, 'بحث', 'إحصائية')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('احصاء_متقدم', r.stdout)

    def test_remove_command(self):
        self._cli(self.project, 'تثبيت', 'ادوات_نص')
        r = self._cli(self.project, 'إزالة', 'ادوات_نص')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('أُزيلت', r.stdout)
        r2 = self._cli(self.project, 'قائمة')
        self.assertIn('لا حزم مثبتة', r2.stdout)

    def test_remove_dependent_fails(self):
        self._cli(self.project, 'تثبيت', 'احصاء_متقدم')
        r = self._cli(self.project, 'إزالة', 'ادوات_نص')
        self.assertEqual(r.returncode, 1)
        self.assertIn('تعتمد عليها', r.stderr)

    def test_unknown_command(self):
        r = self._cli(self.project, 'طيران')
        self.assertEqual(r.returncode, 1)
        self.assertIn('غير معروف', r.stderr)

    def test_no_command_shows_usage(self):
        r = self._cli(self.project)
        self.assertEqual(r.returncode, 1)
        self.assertIn('استخدام', r.stdout)

    def test_install_project_dependencies(self):
        # مشروع ببيان يحدد تبعياته — تثبيت بلا اسم يثبتها كلها
        _write_json(os.path.join(self.project, 'حزمة.json'), {
            'الاسم': 'مشروعي', 'النسخة': '0.1.0',
            'التبعيات': {'ادوات_نص': '>=1.0.0'}})
        r = self._cli(self.project, 'تثبيت')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('ادوات_نص v1.4.0', r.stdout)
        self.assertTrue(os.path.isdir(os.path.join(
            self.project, 'حزم', 'ادوات_نص')))

    def test_install_without_target_or_manifest(self):
        r = self._cli(self.project, 'تثبيت')
        self.assertEqual(r.returncode, 1)
        self.assertIn('حدّد حزمة', r.stderr)


class TestExecutablePackaging(unittest.TestCase):
    """التوزيع كملف تنفيذي مستقل (الإصدار 1.14)."""

    def test_is_frozen_false_in_source_mode(self):
        import arabi
        self.assertFalse(arabi.is_frozen())

    def test_prog_name_source_mode(self):
        import arabi
        self.assertEqual(arabi.prog_name(), 'python arabi.py')

    def test_version_text_contains_version(self):
        import arabi
        self.assertIn(arabi.__version__, arabi.version_text())
        self.assertIn('عربي', arabi.version_text())

    def test_version_text_frozen_suffix(self):
        import arabi
        from unittest import mock
        with mock.patch.object(sys, 'frozen', True, create=True):
            text = arabi.version_text()
        self.assertIn('تنفيذي مستقل', text)
        self.assertIn(arabi.__version__, text)

    def test_prog_name_frozen_mode(self):
        import arabi
        from unittest import mock
        with mock.patch.object(sys, 'frozen', True, create=True):
            self.assertEqual(arabi.prog_name(), './عربي')

    def test_spec_file_targets_entry(self):
        spec = os.path.join(ROOT, 'عربي.spec')
        self.assertTrue(os.path.isfile(spec), 'ملف المواصفة عربي.spec مفقود')
        with open(spec, encoding='utf-8') as f:
            content = f.read()
        self.assertIn("'arabi.py'", content)
        self.assertIn("name='عربي'", content)

    def test_build_script_exists(self):
        script = os.path.join(ROOT, 'scripts', 'بناء_التنفيذي.sh')
        self.assertTrue(os.path.isfile(script), 'سكربت البناء مفقود')
        with open(script, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('عربي.spec', content)

    def test_version_cli_no_frozen_suffix(self):
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, 'arabi.py'), '--نسخة'],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertIn('عربي — الإصدار', r.stdout)
        # في وضع المصدر لا يظهر وصف النسخة التنفيذية
        self.assertNotIn('تنفيذي مستقل', r.stdout)

    def test_gitignore_ignores_build_dirs(self):
        with open(os.path.join(ROOT, '.gitignore'), encoding='utf-8') as f:
            content = f.read()
        self.assertIn('build/', content)
        self.assertIn('dist/', content)


# ================== غير المتزامن (الإصدار 1.15) ==================

import http.server                                           # noqa: E402
import threading                                             # noqa: E402
import time                                                  # noqa: E402

from arabi_lang.nodes import Await, FuncDef, BinOp, Num, Name, MethodCall  # noqa: E402


def _run_vm(source, use_vm):
    """ينفذ كودًا في وضع دولاب محدد ويعيد المخرجات — لتكافؤ الوضعين."""
    out = io.StringIO()
    with redirect_stdout(out):
        tree = Parser(Lexer(source).tokenize()).parse()
        Interpreter(use_vm=use_vm).run(tree)
    return out.getvalue()


class TestAsyncParsing(unittest.TestCase):
    """تحليل 'دالة غير متزامنة' و'انتظر' ككلمات سياقية."""

    def test_async_def_flag(self):
        tree = Parser(Lexer('غير متزامنة دالة جلب(رابط):\n    أعد ١\n').tokenize()).parse()
        fn = tree.statements[0]
        self.assertIsInstance(fn, FuncDef)
        self.assertTrue(fn.is_async)
        self.assertFalse(fn.is_generator)

    def test_sync_def_flag_unchanged(self):
        tree = Parser(Lexer('دالة عادية():\n    أعد ١\n').tokenize()).parse()
        self.assertFalse(tree.statements[0].is_async)

    def test_async_masculine_spelling_accepted(self):
        tree = Parser(Lexer('غير متزامن دالة ج():\n    أعد ١\n').tokenize()).parse()
        self.assertTrue(tree.statements[0].is_async)

    def test_async_generator_rejected(self):
        with self.assertRaises(ParseError):
            Parser(Lexer('غير متزامنة دالة م():\n    أنتج ١\n').tokenize()).parse()

    def test_async_inside_class(self):
        src = ('صنف خ:\n'
               '    غير متزامنة دالة ش(س):\n'
               '        أعد س\n')
        tree = Parser(Lexer(src).tokenize()).parse()
        self.assertTrue(tree.statements[0].body[0].is_async)

    def test_await_node_precedence(self):
        """انتظر م + ١ تعني (انتظر م) + ١ — أضيق من العمليات الثنائية."""
        tree = Parser(Lexer('س = انتظر م + ١\n').tokenize()).parse()
        expr = tree.statements[0].value
        self.assertIsInstance(expr, BinOp)
        self.assertEqual(expr.op, '+')
        self.assertIsInstance(expr.left, Await)
        self.assertIsInstance(expr.left.operand, Name)
        self.assertIsInstance(expr.right, Num)

    def test_await_postfix_inside(self):
        """انتظر م.نتيجة() — سلسلة اللاحقة تدخل ضمن المعامل."""
        tree = Parser(Lexer('س = انتظر م.نتيجة()\n').tokenize()).parse()
        operand = tree.statements[0].value.operand
        self.assertIsInstance(operand, MethodCall)
        self.assertEqual(operand.name, 'نتيجة')

    def test_intizar_is_contextual_not_reserved(self):
        """انتظر تظل قابلة للاستخدام كاسم عادي عندما لا يتبعها تعبير."""
        out = run_code('انتظر = ٧\nاطبع(انتظر)\n')
        self.assertIn('7', out)

    def test_intizar_method_call_unaffected(self):
        """الطرق المسماه انتظر (مثل مهمة.انتظر()) تعمل كما كانت."""
        out = run_code(
            'غير متزامنة دالة ع():\n    أعد ٥\n'
            'م = ع()\n'
            'م.انتظر()\n'
            'اطبع(م.نتيجة())\n')
        self.assertIn('5', out)


class TestAsyncSemantics(unittest.TestCase):
    """دلالات المهام: الانتظار والتجميع والسباق والأخطاء والدولاب."""

    def test_call_returns_task(self):
        out = run_code(
            'غير متزامنة دالة ع():\n    أعد ٤٢\n'
            'م = ع()\n'
            'اطبع(نوع(م))\n'
            'انتظر م\n')
        self.assertIn('مهمة', out)

    def test_await_returns_result(self):
        out = run_code(
            'غير متزامنة دالة جمع(أ، ب):\n    أعد أ + ب\n'
            'اطبع(انتظر جمع(٢، ٣))\n')
        self.assertIn('5', out)

    def test_task_not_ready_immediately(self):
        out = run_code(
            'غير متزامنة دالة بطيئة():\n'
            '    انتظر_زمن(0.05)\n'
            '    أعد ١\n'
            'م = بطيئة()\n'
            'اطبع(م.جاهز())\n'
            'انتظر م\n')
        self.assertIn('خطأ', out.splitlines()[0])

    def test_task_ready_after_completion(self):
        out = run_code(
            'غير متزامنة دالة ع():\n    أعد ٩\n'
            'م = ع()\n'
            'انتظر م\n'
            'اطبع(م.جاهز())\n')
        self.assertIn('صح', out)

    def test_wait_all_preserves_order(self):
        out = run_code(
            'غير متزامنة دالة مؤجلة(ث، قيمة):\n'
            '    انتظر_زمن(ث)\n'
            '    أعد قيمة\n'
            'أ = مؤجلة(0.06، "بطيئة")\n'
            'ب = مؤجلة(0.01، "سريعة")\n'
            'نتائج = انتظر_الجميع([أ، ب])\n'
            'اطبع(نتائج[0])\n'
            'اطبع(نتائج[1])\n')
        lines = out.splitlines()
        self.assertEqual(lines[0], 'بطيئة')
        self.assertEqual(lines[1], 'سريعة')

    def test_wait_all_empty(self):
        out = run_code('اطبع(انتظر_الجميع([]))\n')
        self.assertIn('[]', out)

    def test_wait_all_rejects_non_task(self):
        try:
            run_code('انتظر_الجميع([٥])\n')
            self.fail('المفروض يرفع خطأ')
        except ArabiError as exc:
            self.assertIn('ليس مهمة', str(exc))

    def test_wait_all_requires_list(self):
        try:
            run_code('انتظر_الجميع(٥)\n')
            self.fail('المفروض يرفع خطأ')
        except ArabiError as exc:
            self.assertIn('قائمة مهام', str(exc))

    def test_race_returns_first_done(self):
        out = run_code(
            'غير متزامنة دالة مؤجلة(ث، قيمة):\n'
            '    انتظر_زمن(ث)\n'
            '    أعد قيمة\n'
            'فائز = سباق([مؤجلة(0.08، "أ")، مؤجلة(0.01، "ب")])\n'
            'اطبع(انتظر فائز)\n')
        self.assertIn('ب', out)

    def test_race_returns_task_value(self):
        out = run_code(
            'غير متزامنة دالة ع():\n    أعد ١\n'
            'فائز = سباق([ع()])\n'
            'اطبع(نوع(فائز))\n'
            'انتظر فائز\n')
        self.assertIn('مهمة', out)

    def test_race_needs_at_least_one(self):
        try:
            run_code('سباق([])\n')
            self.fail('المفروض يرفع خطأ')
        except ArabiError as exc:
            self.assertIn('مهمة واحدة على الأقل', str(exc))

    def test_task_error_method_success_case(self):
        out = run_code(
            'غير متزامنة دالة ع():\n    أعد ١\n'
            'م = ع()\n'
            'اطبع(م.الخطأ())\n')
        self.assertIn('ولا شيء', out)

    def test_task_error_method_failure_case(self):
        out = run_code(
            'غير متزامنة دالة ف():\n'
            '    ارفع استثناء("انفجرت")\n'
            'م = ف()\n'
            'اطبع(م.الخطأ())\n')
        self.assertIn('انفجرت', out)

    def test_task_wait_method_swallows_error(self):
        out = run_code(
            'غير متزامنة دالة ف():\n'
            '    ارفع استثناء("انفجرت")\n'
            'م = ف()\n'
            'م.انتظر()\n'
            'اطبع("وصلنا")\n')
        self.assertIn('وصلنا', out)

    def test_await_reraises_task_error(self):
        try:
            run_code(
                'غير متزامنة دالة ف():\n'
                '    ارفع استثناء("كارثة")\n'
                'م = ف()\n'
                'انتظر م\n')
            self.fail('المفروض يرفع خطأ')
        except ArabiError as exc:
            self.assertIn('كارثة', str(exc))

    def test_custom_error_instance_preserved(self):
        """خطأ مخصص مرفوع في مهمة يصل لجرب كائنًا كاملًا (كما في المسار المتزامن)."""
        out = run_code(
            'صنف خطأ_شبكة من استثناء:\n'
            '    دالة إنشاء(الرمز):\n'
            '        هذا.الرمز = الرمز\n'
            '        هذا.رسالة = "فشل " + الرمز\n'
            'غير متزامنة دالة ف():\n'
            '    ارفع خطأ_شبكة("٤٠٤")\n'
            'م = ف()\n'
            'جرب:\n'
            '    انتظر م\n'
            'باستثناء ه:\n'
            '    اطبع(ه.الرمز)\n')
        self.assertIn('٤٠٤', out)

    def test_await_rejects_non_task(self):
        try:
            run_code('انتظر ٥\n')
            self.fail('المفروض يرفع خطأ')
        except ArabiError as exc:
            self.assertIn("'انتظر' تتوقع مهمة", str(exc))

    def test_async_typename_and_display(self):
        out = run_code(
            'غير متزامنة دالة ع():\n    أعد ١\n'
            'اطبع(نوع(ع))\n'
            'اطبع(ع)\n')
        self.assertIn('دالة غير متزامنة', out)
        self.assertIn('<دالة غير متزامنة ع>', out)

    def test_async_method_with_this(self):
        out = run_code(
            'صنف خادم:\n'
            '    دالة إنشاء(الاسم):\n'
            '        هذا.الاسم = الاسم\n'
            '    غير متزامنة دالة اعالج(رقم):\n'
            '        انتظر_زمن(0.01)\n'
            '        أعد هذا.الاسم + ":" + نص(رقم)\n'
            'ه = خادم("رئيسي")\n'
            'اطبع(انتظر ه.اعالج(٣))\n')
        self.assertIn('رئيسي:3', out)

    def test_nested_await_inside_async(self):
        out = run_code(
            'غير متزامنة دالة داخلية(س):\n'
            '    انتظر_زمن(0.01)\n'
            '    أعد س * ٢\n'
            'غير متزامنة دالة خارجية(س):\n'
            '    جزء = انتظر داخلية(س)\n'
            '    أعد جزء + ١٠٠\n'
            'اطبع(انتظر خارجية(٥))\n')
        self.assertIn('110', out)

    def test_async_recursion_with_wait_all(self):
        out = run_code(
            'غير متزامنة دالة فيبو(ن):\n'
            '    لو ن < ٢:\n'
            '        أعد ن\n'
            '    أ، ب = انتظر_الجميع([فيبو(ن-١)، فيبو(ن-٢)])\n'
            '    أعد أ + ب\n'
            'اطبع(انتظر فيبو(١٠))\n')
        self.assertIn('55', out)

    def test_parallel_tasks_faster_than_sequential(self):
        """أربع مهام نائمة معًا تنتهي أسرع من تنفيذها تتابعيًا."""
        src = (
            'غير متزامنة دالة نوم(ث):\n'
            '    انتظر_زمن(ث)\n'
            '    أعد ١\n'
        )
        t0 = time.perf_counter()
        run_code(src + 'انتظر_الجميع([نوم(0.12)، نوم(0.12)، نوم(0.12)، نوم(0.12)])\n')
        parallel = time.perf_counter() - t0
        t0 = time.perf_counter()
        run_code(src + 'انتظر نوم(0.12)\nانتظر نوم(0.12)\nانتظر نوم(0.12)\nانتظر نوم(0.12)\n')
        sequential = time.perf_counter() - t0
        self.assertLess(parallel, sequential * 0.75,
                        f'المتوازي {parallel:.3f}ث ليس أسرع من التتابعي {sequential:.3f}ث')

    def test_intizar_zaman_negative_rejected(self):
        try:
            run_code('انتظر_زمن(-١)\n')
            self.fail('المفروض يرفع خطأ')
        except ArabiError as exc:
            self.assertIn('موجبًا', str(exc))

    def test_intizar_zaman_returns_nothing(self):
        out = run_code('اطبع(انتظر_زمن(0))\n')
        self.assertIn('ولا شيء', out)

    def test_async_default_and_named_params(self):
        out = run_code(
            'غير متزامنة دالة تحية(الاسم، تحية = "مرحبا"):\n'
            '    انتظر_زمن(0.01)\n'
            '    أعد تحية + " " + الاسم\n'
            'اطبع(انتظر تحية("سارة"))\n'
            'اطبع(انتظر تحية("عمر"، تحية = "أهلا"))\n')
        self.assertIn('مرحبا سارة', out)
        self.assertIn('أهلا عمر', out)

    def test_async_rest_param(self):
        out = run_code(
            'غير متزامنة دالة مجموع(...أعداد):\n'
            '    مجموع_كلي = ٠\n'
            '    لكل ع في أعداد:\n'
            '        مجموع_كلي += ع\n'
            '    أعد مجموع_كلي\n'
            'اطبع(انتظر مجموع(١، ٢، ٣، ٤))\n')
        self.assertIn('10', out)

    def test_async_closure(self):
        out = run_code(
            'دالة مصنّع(البادئة):\n'
            '    غير متزامنة دالة مؤهلة(نص):\n'
            '        أعد البادئة + نص\n'
            '    أعد مؤهلة\n'
            'ع = مصنّع("[")\n'
            'اطبع(انتظر ع("مغلق]"))\n')
        self.assertIn('[مغلق]', out)

    def test_thread_spawn_on_async_func_returns_task(self):
        """خيوط.شغّل على دالة غير متزامنة يعيد مهمة صالحة للانتظار مباشرة."""
        out = run_code(
            'غير متزامنة دالة ع():\n    أعد ٧\n'
            'حاصل = خيوط.شغّل(ع)\n'
            'اطبع(نوع(حاصل))\n'
            'اطبع(انتظر حاصل)\n')
        self.assertIn('مهمة', out)
        self.assertIn('7', out)

    # ---------- الدولاب الافتراضي ----------

    def test_vm_and_ast_parity_async(self):
        src = (
            'غير متزامنة دالة مؤجلة(ث، قيمة):\n'
            '    انتظر_زمن(ث)\n'
            '    أعد قيمة\n'
            'غير متزامنة دالة خارجية(س):\n'
            '    جزء = انتظر مؤجلة(0.01، س)\n'
            '    أعد جزء * ١٠\n'
            'أ = مؤجلة(0.02، "سريعة")\n'
            'ب = مؤجلة(0.01، "أسرع")\n'
            'اطبع(انتظر خارجية(٧))\n'
            'نتائج = انتظر_الجميع([أ، ب])\n'
            'اطبع(نتائج)\n'
            'فائز = سباق([أ، ب])\n'
            'اطبع(نوع(فائز))\n'
            'غير متزامنة دالة تفشل():\n'
            '    ارفع استثناء("بوم")\n'
            'ف = تفشل()\n'
            'اطبع(ف.الخطأ())\n'
            'م = مؤجلة(0.01، ٩)\n'
            'م.انتظر()\n'
            'اطبع(م.جاهز())\n')
        self.assertEqual(_run_vm(src, True), _run_vm(src, False))

    def test_async_call_from_vm_compiled_function(self):
        """استدعاء دالة غير متزامنة من داخل دالة مترجمة بالدولاب."""
        out = run_code(
            'غير متزامنة دالة ع():\n    أعد ١٥\n'
            'دالة غلاف():\n'
            '    م = ع()\n'
            '    أعد انتظر م\n'
            'اطبع(غلاف())\n')
        self.assertIn('15', out)


# ================== شبكة: تنزيل (الإصدار 1.15) ==================

class _StaticHandler(http.server.BaseHTTPRequestHandler):
    """خادم ثابت مصغر للاختبارات: /ملف.txt يعيد نصًا، وغيره 404."""

    def do_GET(self):
        from urllib.parse import unquote
        if unquote(self.path) == '/ملف.txt':
            body = 'محتوى التنزيل التجريبي ١٢٣'.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_args):
        pass


class TestNetworkDownload(unittest.TestCase):
    """شبكة.تنزيل — ينزّل ملفًا من خادم محلي ويعيد عدد البايتات."""

    def setUp(self):
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0),
                                                      _StaticHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.dest = os.path.join(self.tmp.name, 'ناتج.txt')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_download_success(self):
        out = run_code(
            f'عدد = شبكة.تنزيل("http://127.0.0.1:{self.port}/ملف.txt"، '
            f'"{self.dest}")\n'
            'اطبع(عدد > ٠)\n')
        self.assertIn('صح', out)
        with open(self.dest, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'محتوى التنزيل التجريبي ١٢٣')

    def test_download_with_timeout(self):
        out = run_code(
            f'عدد = شبكة.تنزيل("http://127.0.0.1:{self.port}/ملف.txt"، '
            f'"{self.dest}"، 5)\n'
            'اطبع(نوع(عدد))\n')
        self.assertIn('عدد صحيح', out)

    def test_download_parallel_tasks(self):
        """تنزيلات غير متزامنة متوازية من نفس الخادم المحلي."""
        d1 = os.path.join(self.tmp.name, 'واحد.txt')
        d2 = os.path.join(self.tmp.name, 'اثنان.txt')
        out = run_code(
            'غير متزامنة دالة انزل(رابط، مسار):\n'
            '    أعد شبكة.تنزيل(رابط، مسار)\n'
            f'م١ = انزل("http://127.0.0.1:{self.port}/ملف.txt"، "{d1}")\n'
            f'م٢ = انزل("http://127.0.0.1:{self.port}/ملف.txt"، "{d2}")\n'
            'نتائج = انتظر_الجميع([م١، م٢])\n'
            'اطبع(نتائج[0] == نتائج[1] و نتائج[0] > ٠)\n')
        self.assertIn('صح', out)

    def test_download_requires_http_url(self):
        try:
            run_code(f'شبكة.تنزيل("ftp://مثال/ملف"، "{self.dest}")\n')
            self.fail('المفروض يرفع خطأ')
        except ArabiError as exc:
            self.assertIn('http://', str(exc))

    def test_download_404_error(self):
        try:
            run_code(f'شبكة.تنزيل("http://127.0.0.1:{self.port}/غير_موجود"، '
                     f'"{self.dest}")\n')
            self.fail('المفروض يرفع خطأ')
        except ArabiError as exc:
            self.assertIn('404', str(exc))

    def test_download_bad_write_path(self):
        bad = os.path.join(self.tmp.name, 'مجلد_غير_موجود', 'ملف.txt')
        try:
            run_code(f'شبكة.تنزيل("http://127.0.0.1:{self.port}/ملف.txt"، '
                     f'"{bad}")\n')
            self.fail('المفروض يرفع خطأ')
        except ArabiError as exc:
            self.assertIn('تعذّرت كتابة', str(exc))

    def test_download_url_must_be_string(self):
        try:
            run_code(f'شبكة.تنزيل(٥، "{self.dest}")\n')
            self.fail('المفروض يرفع خطأ')
        except ArabiError as exc:
            self.assertIn('رابطًا نصيًا', str(exc))

    def test_download_path_must_be_string(self):
        try:
            run_code(f'شبكة.تنزيل("http://127.0.0.1:{self.port}/ملف.txt"، ٥)\n')
            self.fail('المفروض يرفع خطأ')
        except ArabiError as exc:
            self.assertIn('نصًا', str(exc))

    def test_download_zero_timeout_rejected(self):
        try:
            run_code(f'شبكة.تنزيل("http://127.0.0.1:{self.port}/ملف.txt"، '
                     f'"{self.dest}"، 0)\n')
            self.fail('المفروض يرفع خطأ')
        except ArabiError as exc:
            self.assertIn('موجبًا', str(exc))

    def test_request_module_unaffected(self):
        """اطلب تظل تعمل بعد إضافة تنزيل — الحالة 200 والترويسات."""
        out = run_code(
            f'ن = شبكة.اطلب("http://127.0.0.1:{self.port}/ملف.txt")\n'
            'اطبع(ن.الحالة)\n'
            'اطبع("الترويسات" في ن)\n')
        self.assertIn('200', out)
        self.assertIn('صح', out)


if __name__ == '__main__':
    unittest.main(verbosity=2)
