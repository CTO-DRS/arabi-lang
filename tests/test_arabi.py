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
        expect_error('أ = ٣ @ ٤', LexerError, 'رمز غير معروف')

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


if __name__ == '__main__':
    unittest.main(verbosity=2)
