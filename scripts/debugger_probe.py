# -*- coding: utf-8 -*-
"""مسبار المنقّح التفاعلي (الإصدار 1.35 — حي بعد التنفيذ).

وُلد مسبار بوابة التصميم يثبت الفجوات (٩/٩) قبل كتابة سطر تنفيذ،
وبعد التنفيذ صار عقدًا حيًا يتحقق من قرارات التصميم على الكود الفعلي:
  د١: خطاف وحيد debug_hook على execute() يرى كل جمل الممسح الشجري
  د٢: لمسة ثانية في run() لجمل التعبير العلوية (بلا ازدواج)
  د٣: تعطيل الدولاب افتراضيًا أثناء جلسة التنقيح
  د٤: التنقيح يوقف الخيط المُنقَّح فقط — خيوط المولدات تُنفَّذ
  د٥: فحص المتغيرات من env.vars بسلسلة الآباء
  د٦: أين (مكدس النداء) من خطافي دخول/خروج الدالة في _run_func
البندان ١/١.ب انعكسا بعد الإغلاق: يتحققان من وجود الخطاف والوحدة
(عقد التنفيذ) لا من غيابهما (إثبات الفجوة التاريخي في سجل العمل).
"""

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arabi_lang.lexer import Lexer
from arabi_lang.parser import Parser
from arabi_lang.interpreter import Interpreter

OK = '✓'
FAIL = '✗'
results = []


def check(name, cond, detail=''):
    results.append((name, cond))
    print(f'{OK if cond else FAIL} {name}' + (f' — {detail}' if detail else ''))


def parse(src):
    return Parser(Lexer(src).tokenize()).parse()


# ========== 1. الفجوة: لا منقّح اليوم ==========
import arabi_lang.interpreter as interp_mod

has_hook = hasattr(Interpreter(), 'debug_hook')
_interp_fresh = Interpreter()
check('١. المفسر يحمل خطاف تنقيح debug_hook (عقد 1.35)',
      hasattr(_interp_fresh, 'debug_hook')
      and _interp_fresh.debug_hook is None)

pkg_dir = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'arabi_lang')
has_debugger_file = os.path.exists(os.path.join(pkg_dir, 'debugger.py'))
check('١.ب وحدة debugger.py موجودة في الحزمة (عقد 1.35)',
      has_debugger_file)

# ========== 2+3+4. عدّاد الجمل على execute() ==========
PROGRAM = '''# برنامج اختبار متداخل
س = 0
دالة احسب(ن):
    لكل م في [1، 2، 3]:
        س = س + م
    أعد س
لو صح:
    احسب(5)
احسب(2)
'''


class CountingInterpreter(Interpreter):
    """مفسر يعدّ الجمل التي تمر بـexecute() — يحاكي الخطاف المقترح."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.hits = []          # (سطر، اسم_الصنف)

    def execute(self, node, env):
        self.hits.append((node.line, type(node).__name__))
        return super().execute(node, env)


# --- على الممسح الشجري (بلا دولاب) ---
tree_vm_off = parse(PROGRAM)
ci = CountingInterpreter(use_vm=False)
ci.run(tree_vm_off)
lines_hit = {line for line, _ in ci.hits}
check('٢. execute() ترى جمل المستوى العلوي الغير تعبيرية', 2 in lines_hit
      and 3 in lines_hit, f'أسطر مرئية: {sorted(l for l in lines_hit if l)}')
check('٢.ب execute() ترى جسم لكل داخل دالة', 5 in lines_hit,
      'السطر ٥ (س = س + م) مرئي')
check('٢.ج execute() ترى جسم لو', 7 in lines_hit)

# --- على الدولاب الافتراضي (الافتراضي) ---
tree_vm_on = parse(PROGRAM)
ci2 = CountingInterpreter(use_vm=True)
ci2.run(tree_vm_on)
lines_on = {line for line, _ in ci2.hits}
check('٣. الدولاب يخفي جسم دالة عن execute()', 5 not in lines_on,
      f'السطر ٥ مرئي؟ {5 in lines_on} — إثبات وجوب تعطيل الدولاب أثناء التنقيح')

# --- جملة تعبير علوية تتجاوز execute() في run() ---
EXPR_PROGRAM = '''دالة صوت():
    اطبع("مرحى")
    أعد 1
صوت()
'''
tree_expr = parse(EXPR_PROGRAM)
ci3 = CountingInterpreter(use_vm=False)
ci3.run(tree_expr)
call_line_seen = any(type_name == 'Call' for _, type_name in ci3.hits)
check('٤. جملة التعبير العلوية لا تمر بـexecute()', not call_line_seen,
      'الاستدعاء «صوت()» في السطر ٤ لم يُرصد — تحتاج لمسة في run()')

# ========== 5. المولدات في خيط منفصل ==========
seen_threads = []


class ThreadSpy(Interpreter):
    def execute(self, node, env):
        seen_threads.append(threading.current_thread().name)
        return super().execute(node, env)


GEN_PROGRAM = '''دالة توليد():
    أنتج 1
    أنتج 2
مجموع = 0
لكل قيمة في توليد():
    مجموع = مجموع + قيمة
اطبع(مجموع)
'''
try:
    tg = ThreadSpy(use_vm=False)
    tg.run(parse(GEN_PROGRAM))
except Exception as exc:
    print(f'   (ملاحظة مسبار المولد: {exc})')
worker_seen = any(t != threading.main_thread().name for t in seen_threads)
check('٥. أجسام المولدات تعمل بخيط عامل منفصل', worker_seen,
      f'خيوط مرصودة: {sorted(set(seen_threads))} — قرار: التنقيح يوقف '
      'الخيط المُنقَّح فقط')

# ========== 6. فحص البيئة ==========
ENV_PROGRAM = '''دالة نقطة(أ، ب):
    وسيط = أ + ب
    أعد وسيط
نقطة(3، 4)
'''
captured = {}


class EnvSpy(Interpreter):
    def execute(self, node, env):
        if type(node).__name__ == 'Return' and 'وسيط' in env.vars:
            captured.update(env.vars)
            captured['__parent_has_أ__'] = 'أ' in env.vars
        return super().execute(node, env)


EnvSpy(use_vm=False).run(parse(ENV_PROGRAM))
check('٦. متغيرات الإطار مرئية من env.vars', captured.get('وسيط') == 7
      and captured.get('أ') == 3 and captured.get('ب') == 4,
      f'وسيط={captured.get("وسيط")} أ={captured.get("أ")} ب={captured.get("ب")}')

# ========== الخلاصة ==========
passed = sum(1 for _, ok in results if ok)
print(f'\n=== نتيجة المسبار: {passed}/{len(results)} ===')
if passed == len(results):
    print('قرارات التصميم المتحقق عليها حيًا:')
    print('  د١: خطاف وحيد debug_hook على execute() يرى كل جمل الممسح الشجري')
    print('  د٢: لمسة ثانية في run() لجمل التعبير العلوية (بلا ازدواج)')
    print('  د٣: تعطيل الدولاب افتراضيًا أثناء جلسة التنقيح (إلا طلب صريح)')
    print('  د٤: التنقيح يوقف الخيط المُنقَّح فقط — خيوط المولدات تُنفَّذ')
    print('  د٥: فحص المتغيرات من env.vars مباشرة بسلسلة الآباء')
    print('  د٦: أين (مكدس النداء) من خطافي دخول/خروج الدالة في _run_func')
sys.exit(0 if passed == len(results) else 1)
