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


if __name__ == '__main__':
    unittest.main(verbosity=2)
