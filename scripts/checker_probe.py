# -*- coding: utf-8 -*-
"""مسبار بوابة التصميم — المدقق الساكن v1 (الإصدار 1.36).

يثبت بالقياس الحي قبل التنفيذ:
  1. الفجوة: توصيف باسم عائلة مكتوب خطأ في دالة لم تُستدعَ → البرنامج
     يعمل بلا أي كشف (الحسم وقت التشغيل عند أول استدعاء فقط — ق١٣).
  2. الفجوة: «أعد نص» في دالة تعلن إرجاع عدد ولم تُستدعَ → يعمل بلا كشف.
  3. الفجوة: دالة تعلن إرجاعًا بلا أي «أعد» في جسمها → سقوط ضمني مضمون
     لو استدعيت — وبلا استدعاء لا كشف.
  4. الأدلة الساكنة الممكنة في v1: النص/العدد/المنطق/القائمة/القاموس/
     عدم حرفيًا + عمليات حسابية على حرفيات + استدعاء دوال التحويل
     (عدد/نص/...) — تصنيف حي يثبت قابلية الحسم دون استنتاج.
  5. حدود v1: المتغيرات والاستدعاءات العامة غير قابلة للحسم —
     قرار: تخطى الصامت (لا استنتاج في v1 — بند أفق ٣ v2).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arabi_lang.lexer import Lexer
from arabi_lang.parser import Parser
from arabi_lang.interpreter import Interpreter
from arabi_lang.nodes import (Num, Str, Bool, Null, ListLit, DictLit,
                              BinOp, Call, Name, Ternary)

OK = '✓'
FAIL = '✗'
results = []


def check(name, cond, detail=''):
    results.append((name, cond))
    print(f'{OK if cond else FAIL} {name}' + (f' — {detail}' if detail else ''))


def parse(src):
    return Parser(Lexer(src).tokenize()).parse()


def run_quietly(src):
    """يشغل برنامجًا ويعيد (نجح؟، رسالة الخطأ أو None)."""
    try:
        Interpreter(script_dir='.').run(parse(src))
        return True, None
    except Exception as exc:
        return False, str(exc)[:90]


# ========== ١+٢+٣. الفجوات الثلاث ==========
GAP_TYPO = '''دالة مجموع(قيم: قائمة[عددد]) → عدد:
    أعد 1
اطبع("البرنامج اكتمل بلا كشف")
'''
ok, err = run_quietly(GAP_TYPO)
check('١. توصيف باسم نوع مخطئ في دالة غير مستدعاة يمر صامتًا', ok,
      f'(وقت التشغيل: {err or "لا خطأ"} — الفجوة الساكنة)')

GAP_RET = '''دالة اسمي() → عدد:
    أعد "مرحى"
اطبع("اكتمل")
'''
ok, err = run_quietly(GAP_RET)
check('٢. مخالفة إرجاع حرفية في دالة غير مستدعاة تمر صامتة', ok)

GAP_FALL = '''دالة بلا_أعد() → عدد:
    س = 1
اطبع("اكتمل")
'''
ok, err = run_quietly(GAP_FALL)
check('٣. دالة موصّفة بلا أي أعد (سقوط ضمني مضمون) تمر صامتة', ok)

# ========== ٤. الأدلة الساكنة ==========
def classify(expr):
    """محاكاة مصنف v1 — يعيد اسم العائلة أو None."""
    if isinstance(expr, Num):
        return 'عدد' if isinstance(expr.value, float) else 'صحيح'
    if isinstance(expr, Str):
        return 'نص'
    if isinstance(expr, Bool):
        return 'منطقي'
    if isinstance(expr, Null):
        return 'عدم'
    if isinstance(expr, ListLit):
        return 'قائمة'
    if isinstance(expr, DictLit):
        return 'قاموس'
    if isinstance(expr, BinOp) and expr.op in ('+', '-', '*', '/', '٪', '%'):
        left, right = classify(expr.left), classify(expr.right)
        if left in ('صحيح', 'عدد') and right in ('صحيح', 'عدد'):
            return 'عدد' if expr.op in ('/',) else (
                'صحيح' if left == right == 'صحيح' else 'عدد')
        if left == 'نص' and right == 'نص':
            return 'نص'
    if isinstance(expr, Call) and isinstance(expr.func, Name):
        if expr.func.name in ('عدد', 'صحيح', 'عشري', 'نص', 'منطقي'):
            return expr.func.name
    return None


tree = parse('''س = "نص حرفي"
ع = 2 + 3 * 4
قسمة = 10 / 2
منطقي_حرفي = صح
ق = [1، 2]
د = {"أ": 1}
تحويل = عدد("42")
''')
evidence = {}
for stmt in tree.statements:
    if type(stmt).__name__ == 'Assign':
        name = stmt.targets[0].name
        evidence[name] = classify(stmt.value)

check('٤. النص الحرفي يُصنَّف', evidence['س'] == 'نص', str(evidence['س']))
check('٤.ب الحساب على حرفيات يُصنَّف صحيحًا', evidence['ع'] == 'صحيح')
check('٤.ج القسمة تعطي دليل عدد', evidence['قسمة'] == 'عدد')
check('٤.د المنطقي الحرفي يُصنَّف', evidence['منطقي_حرفي'] == 'منطقي')
check('٤.هـ القائمة والقاموس الحرفيان يُصنَّفان',
      evidence['ق'] == 'قائمة' and evidence['د'] == 'قاموس')
check('٤.و استدعاء دالة تحويل يعطي دليل العائلة', evidence['تحويل'] == 'عدد')

# ========== ٥. حدود الاستنتاج ==========
tree2 = parse('ناتج = مجهول(5)')
unknown = classify(tree2.statements[0].value)
check('٥. الاستدعاءات العامة بلا دليل — تخطى صامتًا (حد v1)', unknown is None)

# ========== قصاصة نطاق: أعد داخل دالة متداخلة لا يعود لأمها ==========
tree3 = parse('''دالة خارجية() → عدد:
    دالة داخلية() → نص:
        أعد "نص"
    أعد 1
''')
outer = tree3.statements[0]
inner = outer.body[0]
check('٥.ب الدوال المتداخلة عقود مستقلة (قطع النطاق ضروري)',
      outer.name == 'خارجية' and inner.name == 'داخلية'
      and type(inner.body[0]).__name__ == 'Return')

passed = sum(1 for _, ok_ in results if ok_)
print(f'\n=== نتيجة المسبار: {passed}/{len(results)} ===')
if passed == len(results):
    print('القرارات المؤسسة:')
    print('  ص١: المدقق يحل أسماء التوصيفات ساكنًا (عائلات فورًا + أصناف من نطاق الوحدة)')
    print('  ص٢: مسار الأعد يفحص بالأدلة الحرفية والتحويلية — والمجهول يُتخطى صامتًا')
    print('  ص٣: صفر أعد مع إرجاع معلن = مخالفة ساكنة (سقوط ضمني مضمون)')
    print('  ص٤: قطع النطاق عند الدوال المتداخلة والأصناف — كل عقد عقد دالته')
    print('  ص٥: رمز خروج 1 عند أي مخالفة — عقد CI')
sys.exit(0 if passed == len(results) else 1)
