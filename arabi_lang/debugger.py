# -*- coding: utf-8 -*-
"""المنقّح التفاعلي للغة عربي (الإصدار 1.35 — أفق التمكين).

التصميم مؤسس على مسبار حي (scripts/debugger_probe.py — ٩/٩):
  د١: خطاف وحيد debug_hook على execute() يرى كل جمل الممسح الشجري
      (المستوى العلوي، أجسام لو/طالما/لكل، أجسام الدوال، الوحدات).
  د٢: لمسة ثانية في run() لجمل التعبير العلوية — فهي تتجاوز execute()
      بنيويًا (أثبتها المسبار) — بلا ازدواج في الإيقاف.
  د٣: تعطيل الدولاب الافتراضي أثناء الجلسة — أجسام الدوال على الدولاب
      لا تمر بـexecute() أصلًا فلا يراها الخطاف.
  د٤: التنقيح يوقف الخيط المُنقَّح فقط — المولدات تعمل بخيوط عامل
      منفصلة (أثبتها المسبار) فأجسامها لا تُوقف في هذا الإصدار.
  د٥: فحص المتغيرات من سلسلة env.vars حتى الجذر المستثنى.
  د٦: «أين» من خطافي دخول/خروج الدالة في _run_func — نقطة دخول كل
      أجسام دوال المستخدم (استدعاء مباشر، طرق، مهام لامزامنة).

البنية: محرك (Debugger) يعرف متى يتوقف وماذا يعرض، وواجهات تقرر كيف
يحاور المستخدم — سطر الأوامر العربي هنا، وبروتوكول محول التنقيح (DAP)
للمحررات في debug_adapter.py.
"""

import os
import threading

from .errors import ArabiError
from .lexer import Lexer
from .parser import Parser
from .runtime import ArabiRuntimeError, display


class DebugQuit(Exception):
    """رفعته أمر «إنهاء» — يقطع البرنامج ويغلق الجلسة بنظافة."""


# أفعال الاستئناف التي تعيدها الواجهة من كل توقف
RESUME_CONTINUE = 'متابعة'      # حتى نقطة التوقف التالية أو النهاية
RESUME_STEP = 'خطوة'            # الجملة التالية أينما كانت (داخل الدوال)
RESUME_NEXT = 'تالية'           # الجملة التالية في العمق نفسه أو أضحق
RESUME_FINISH = 'من_الدالة'     # حتى خروج الدالة الحالية

# حد عرض قيمة المتغير في قوائم المنقّح — القيم الضخمة تُقتطع لا تُطبع
_DISPLAY_LIMIT = 120


def _short_display(value):
    """عرض قيمة مقتطعًا لقوائم المنقّح."""
    try:
        text = display(value)
    except Exception:
        text = f'<قيمة غير قابلة للعرض: {type(value).__name__}>'
    if len(text) > _DISPLAY_LIMIT:
        text = text[:_DISPLAY_LIMIT] + '…'
    return text


class Debugger:
    """محرك التنقيح: نقاط توقف، خطوات، فحص أُطر — بلا أي إدخال/إخراج.

    الواجهة (CliFrontend أو بروتوكول DAP) تستدعي الأوامر العامة وتقرأ
    الحالة؛ المحرك وحده يقرر متى يتوقف التنفيذ.
    """

    def __init__(self, source, filename='<البرنامج>'):
        self.lines = source.splitlines()
        self.filename = filename
        # نقاط التوقف: أسطر فقط في 1.35 — الوحدات المستوردة تشترك في
        # الأرقام (حد موثق في المواصفة)
        self.breakpoints = set()
        # نقاط توقف الدوال: تُوقف عند دخول الدالة بالاسم
        self.func_breakpoints = set()
        # مكدس النداء: [(اسم_الدالة، بيئة_الدخول، سطر_الاستدعاء)]
        self.frame_stack = []
        # بيئة الجملة الحالية الموقوفة (أدق من بيئة دخول الإطار)
        self._current_env = None
        self._current_node = None
        # وضع الاستئناف الجاري + عمق التوقف عنده (لتالية/من_الدالة)
        self._mode = RESUME_STEP      # البداية: توقف على أول جملة
        self._pause_depth = 0
        self._quit = False
        self.thread_id = None
        # أسماء المتغيرات الموجودة قبل تشغيل البرنامج = المدمجات
        # («عالمي» تعرض زيادات المستخدم فقط)
        self._initial_global_names = set()
        # أسطر البرنامج التي تحمل جملة فعلية — لتوثيق نقاط التوقف
        # الصالحة في بروتوكول DAP
        self.ast_lines = set()
        self.interp = None
        # الواجهة تُمرر عبر debug_program — التوقف بلا واجهة خطأ تصميم
        self.frontend = None
        # توقف دالة معلّق: اسم الدالة الداخلة حديثًا وطابق نقطة توقف
        self._pending_func_stop = None
        # سبب آخر توقف (لبروتوكول DAP): اسم دالة أو None
        self._stopped_by_func = None
        # سبب التوقف الحالي: entry/breakpoint/function breakpoint/step
        self._stop_reason = None
        # أول توقف في الجلسة يُسمى «البداية» ما لم يسبقه سبب أدق
        self._entry_stop = True

    # ================== التركيب ==================

    def attach(self, interpreter):
        """يربط المحرك بالمفسر ويعطّل الدولاب (قرار د٣)."""
        self.interp = interpreter
        self.thread_id = threading.get_ident()
        self._initial_global_names = set(interpreter.globals.vars.keys())
        interpreter.debug_hook = self
        interpreter.use_vm = False     # أجسام الدوال يجب أن تمر بـexecute()

    def _walk_lines(self, node, _depth=0):
        """يجمع أسطر كل عقد الشجرة — مسح عام لأي بنية عقدة (لتحقق DAP)."""
        if node is None or _depth > 80:
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                self._walk_lines(item, _depth + 1)
            return
        # البيئات والدوال الحية لها parent — ليست عقد شجرة
        if not hasattr(node, 'line') or hasattr(node, 'parent'):
            return
        if getattr(node, 'line', None):
            self.ast_lines.add(node.line)
        data = getattr(node, '__dict__', None)
        if data:
            for value in data.values():
                self._walk_lines(value, _depth + 1)

    # ================== الخطافات (تستدعيها المفسر) ==================

    def before_statement(self, node, env):
        """خطاف قبل كل جملة — من execute() ومن run() للتعبيرية العلوية."""
        if threading.get_ident() != self.thread_id or self._quit:
            return
        self._current_env = env
        self._current_node = node
        if self._should_pause(node):
            self._pause(node, env)

    def enter_function(self, func, _env, _call_line):
        """خطاف دخول دالة مستخدم — يبني مكدس «أين» ويرصد نقاط الدوال."""
        if threading.get_ident() != self.thread_id or self._quit:
            return
        self.frame_stack.append((func.name, _env, _call_line))
        if func.name in self.func_breakpoints:
            self._pending_func_stop = func.name

    def exit_function(self, _func):
        """خطاف خروج الدالة — يسحب إطارها مهما كانت طريقة الخروج."""
        if threading.get_ident() != self.thread_id:
            return
        if self.frame_stack:
            self.frame_stack.pop()

    def _should_pause(self, node):
        line = getattr(node, 'line', None)
        if line is not None and line in self.breakpoints:
            return True
        if self._pending_func_stop is not None:
            return True
        depth = len(self.frame_stack)
        if self._mode == RESUME_STEP:
            return True
        if self._mode == RESUME_NEXT:
            return depth <= self._pause_depth
        if self._mode == RESUME_FINISH:
            return depth < self._pause_depth
        return False

    def _pause(self, node, env):
        self._pause_depth = len(self.frame_stack)
        self._mode = None
        self._stopped_by_func = self._pending_func_stop
        self._pending_func_stop = None
        line = getattr(node, 'line', None)
        if self._stopped_by_func:
            self._stop_reason = 'function breakpoint'
        elif line is not None and line in self.breakpoints:
            self._stop_reason = 'breakpoint'
        elif self._entry_stop:
            self._stop_reason = 'entry'
        else:
            self._stop_reason = 'step'
        self._entry_stop = False
        if self.frontend is None:
            raise ArabiRuntimeError('المنقّح مرتبط بلا واجهة — لا يمكن التوقف')
        # حلقة المعاينة: الواجهة تعيد أفعال فحص أو استئناف — التوقف
        # الأول يُعلن، وأعقابه أوامر فحص في الموقف نفسه بلا إعادة لافتة
        initial = True
        while True:
            action = self.frontend.pause(self.state(), initial)
            initial = False
            if action is None:
                action = (RESUME_CONTINUE,)
            name = action[0]
            if name in (RESUME_CONTINUE, RESUME_STEP, RESUME_NEXT,
                        RESUME_FINISH):
                self._mode = name
                if name == RESUME_NEXT:
                    self._pause_depth = len(self.frame_stack)
                elif name == RESUME_FINISH:
                    self._pause_depth = len(self.frame_stack)
                return
            if name == 'إنهاء':
                self._quit = True
                raise DebugQuit()
            self.frontend.report(self.run_inspection(action))

    # ================== الأوامر (تستدعيها الواجهات) ==================

    def state(self):
        """لقطة الحالة للعرض عند التوقف."""
        line = None
        if self._current_node is not None:
            line = getattr(self._current_node, 'line', None)
        return {
            'filename': self.filename,
            'line': line,
            'source': self.source_context(line),
            'stack': self.stack_summary(),
            'reason': self._stop_reason,
        }

    def source_context(self, line, radius=2):
        """أسطر المصدر حول سطر — بعلامة على السطر الحالي."""
        if not self.lines or line is None:
            return []
        lo = max(1, line - radius)
        hi = min(len(self.lines), line + radius)
        out = []
        for n in range(lo, hi + 1):
            marker = '→' if n == line else ' '
            out.append(f' {marker} {n:>3} | {self.lines[n - 1].rstrip()}')
        return out

    def stack_summary(self):
        """مكدس النداء: الإطار الأساسي ثم كل دالة دخلت ولم تخرج."""
        frames = [(None, '<البرنامج>', None)]
        for name, _env, call_line in self.frame_stack:
            frames.append((name, name, call_line))
        # الصيغة: [(اسم_عرض، سطر_الاستدعاء)]
        return [(name, call_line)
                for _tag, name, call_line in frames]

    def current_depth(self):
        return len(self.frame_stack)

    def variables_in_scope(self, env=None):
        """المتغيرات المرئية: سلسلة النطاقات حتى الجذر المستثنى (د٥).

        يعيد [(اسم، عرض_القيمة)] مرتبة بالإدخال، مع الأعمق غالبًا عند
        تعارض الأسماء (ظل النطاق الداخلي).
        """
        env = env or self._current_env
        if env is None:
            return []
        if env.parent is None:
            return self.global_variables()
        seen = {}
        while env is not None and env.parent is not None:
            for name, value in env.vars.items():
                if name not in seen:
                    seen[name] = _short_display(value)
            env = env.parent
        return list(seen.items())

    def global_variables(self):
        """زيادات المستخدم على العالمي — المدمجات مستثناة."""
        root = self.interp.globals
        out = []
        for name, value in root.vars.items():
            if name in self._initial_global_names:
                continue
            out.append((name, _short_display(value)))
        return out

    def evaluate(self, text):
        """يقيّم تعبيرًا في بيئة الجملة الموقوفة — لأمر «اطبع».

        يرفع ArabiRuntimeError برسالة عربية عند أي فشل (نحوي أو تشغيلي).
        """
        if self._current_env is None:
            raise ArabiRuntimeError('لا توجد بيئة موقوفة لتقييم التعبير')
        try:
            tree = Parser(Lexer(text).tokenize()).parse()
        except ArabiError as exc:
            raise ArabiRuntimeError(f'تعبير غير سليم: {exc}')
        if (len(tree.statements) != 1
                or type(tree.statements[0]).__name__ != 'ExprStmt'):
            raise ArabiRuntimeError(
                "أمر «اطبع» يقبل تعبيرًا واحدًا فقط — لا جمل ولا إسناد")
        try:
            value = self.interp.evaluate(tree.statements[0].expr,
                                         self._current_env)
        except (ArabiRuntimeError, ArabiError) as exc:
            raise ArabiRuntimeError(f'تعذر التقييم: {exc}')
        return _short_display(value)

    def add_breakpoint(self, line):
        self.breakpoints.add(line)

    def remove_breakpoint(self, line):
        self.breakpoints.discard(line)

    def add_func_breakpoint(self, name):
        self.func_breakpoints.add(name)

    def remove_func_breakpoint(self, name):
        self.func_breakpoints.discard(name)

    def breakpoints_summary(self):
        lines = sorted(self.breakpoints)
        funcs = sorted(self.func_breakpoints)
        return lines, funcs

    def run_inspection(self, action):
        """ينفذ أمر فحص ويعيد نصه — لا يغيّر وضع الاستئناف."""
        name = action[0]
        if name == 'توقف_سطر':
            line = action[1]
            self.add_breakpoint(line)
            if line in self.ast_lines:
                return f'نقطة توقف مضافة عند السطر {line} — فعّالة'
            return (f'نقطة توقف مضافة عند السطر {line} — تنبيه: لا جملة '
                    'على هذا السطر فلن تُوقف أبدًا')
        if name == 'احذف_سطر':
            line = action[1]
            if line in self.breakpoints:
                self.remove_breakpoint(line)
                return f'حُذفت نقطة التوقف عند السطر {line}'
            return f'لا نقطة توقف عند السطر {line}'
        if name == 'توقف_دالة':
            func_name = action[1]
            self.add_func_breakpoint(func_name)
            return f'توقف عند دخول الدالة «{func_name}»'
        if name == 'احذف_دالة':
            func_name = action[1]
            if func_name in self.func_breakpoints:
                self.remove_func_breakpoint(func_name)
                return f'حُذف توقف الدالة «{func_name}»'
            return f'لا توقف لدالة «{func_name}»'
        if name == 'اطبع':
            try:
                return self.evaluate(action[1])
            except (ArabiRuntimeError, ArabiError) as exc:
                return f'خطأ: {exc}'
            except RecursionError:
                return 'خطأ: تعاود عميق في تقييم التعبير'
            except Exception as exc:      # شبكة أمان — الرسالة تُعرض لا تُكتم
                return f'خطأ داخلي في التقييم: {exc}'
        if name == 'متغيرات':
            vars_list = self.variables_in_scope()
            if not vars_list:
                return 'لا متغيرات محلية في هذا الإطار'
            return '\n'.join(f'  {n} = {v}' for n, v in vars_list)
        if name == 'عالمي':
            vars_list = self.global_variables()
            if not vars_list:
                return 'لا متغيرات عالمية من تعريف المستخدم'
            return '\n'.join(f'  {n} = {v}' for n, v in vars_list)
        if name == 'نقاط':
            lines, funcs = self.breakpoints_summary()
            if not lines and not funcs:
                return 'لا نقاط توقف'
            parts = []
            if lines:
                parts.append('أسطر: ' + '، '.join(str(l) for l in lines))
            if funcs:
                parts.append('دوال: ' + '، '.join(funcs))
            return '؛ '.join(parts)
        if name == 'أين':
            stack = self.stack_summary()
            out = []
            for i, (name_, call_line) in enumerate(stack):
                at = f' (استدعاء من السطر {call_line})' if call_line else ''
                prefix = '→ ' if i == len(stack) - 1 else '  '
                out.append(f'{prefix}{i}: {name_}{at}')
            return '\n'.join(out)
        if name == 'مصدر':
            line = None
            if self._current_node is not None:
                line = getattr(self._current_node, 'line', None)
            return '\n'.join(self.source_context(line))
        if name == 'مساعدة':
            return COMMANDS_HELP
        return f"أمر غير معروف: {name} — اكتب «مساعدة»"


COMMANDS_HELP = '''أوامر المنقّح:
  متابعة (م)            استئناف حتى نقطة التوقف التالية أو النهاية
  خطوة (خ)              تنفيذ الجملة التالية ودخول الدوال
  تالية (ت)             الجملة التالية بتجاوز استدعاءات الدوال
  من_الدالة (ن)         التنفيذ حتى خروج الدالة الحالية
  توقف عند <سطر>        إضافة نقطة توقف عند سطر
  توقف عند دالة <اسم>   توقف عند دخول الدالة
  احذف <سطر|اسم>        إزالة نقطة توقف سطر أو دالة
  نقاط                  عرض نقاط التوقف
  اطبع <تعبير>          تقييم تعبير في الإطار الحالي
  متغيرات               متغيرات الإطار الحالي
  عالمي                 متغيرات المستخدم العالمية
  أين                   مكدس النداء
  مصدر                  أسطر المصدر حول الموقع الحالي
  إنهاء (خروج)          قطع البرنامج وإغلاق الجلسة
  مساعدة                هذه القائمة'''


class CliFrontend:
    """واجهة سطر الأوامر العربية — حوار تفاعلي عند كل توقف.

    آخر فعل استئناف يتكرر بسطر فارغ — راحة الأصابع في الحلقات.
    """

    def __init__(self, stdin=None, stdout=None):
        import sys
        self.stdin = stdin if stdin is not None else sys.stdin
        self.stdout = stdout if stdout is not None else sys.stdout
        self.last_resume = None

    def report(self, text):
        print(text, file=self.stdout)

    def pause(self, state, initial=True):
        if initial:
            self._show_stop(state)
        while True:
            try:
                print('(منقّح) ', end='', flush=True, file=self.stdout)
                line = self.stdin.readline()
            except KeyboardInterrupt:
                return ('إنهاء',)
            if not line:                     # نهاية التدفق = إنهاء نظيف
                return ('إنهاء',)
            action = self.parse_command(line.rstrip('\n'))
            if action is None:
                continue
            if action[0] in (RESUME_CONTINUE, RESUME_STEP, RESUME_NEXT,
                             RESUME_FINISH, 'إنهاء'):
                if action[0] != 'إنهاء':
                    self.last_resume = action
                return action
            return action      # أمر فحص — المحرك يعالجه ويعرضه

    def _show_stop(self, state):
        reason = {'entry': 'عند البداية ',
                  'breakpoint': '(نقطة توقف) ',
                  'function breakpoint': '(توقف دالة) ',
                  'step': ''}.get(state.get('reason') or '', '')
        print(f'— توقف {reason}في السطر {state["line"]} '
              f'({state["filename"]}) —', file=self.stdout)
        for text in state['source']:
            print(text, file=self.stdout)

    def parse_command(self, line):
        """يحول سطر المستخدم إلى فعل — None للأسطر المهملة."""
        text = line.strip()
        if not text:
            return self.last_resume        # تكرار آخر استئناف
        parts = text.split(None, 1)
        cmd = parts[0]
        rest = parts[1].strip() if len(parts) > 1 else ''

        if cmd in ('متابعة', 'م', 'c', 'continue'):
            return (RESUME_CONTINUE,)
        if cmd in ('خطوة', 'خ', 's', 'step'):
            return (RESUME_STEP,)
        if cmd in ('تالية', 'ت', 'n', 'next'):
            return (RESUME_NEXT,)
        if cmd in ('من_الدالة', 'ن', 'finish'):
            return (RESUME_FINISH,)
        if cmd in ('إنهاء', 'خروج', 'q', 'quit', 'exit'):
            return ('إنهاء',)
        if cmd in ('مساعدة', '؟', '?', 'help'):
            return ('مساعدة',)
        if cmd in ('نقاط', 'breakpoints'):
            return ('نقاط',)
        if cmd in ('متغيرات', 'vars', 'locals'):
            return ('متغيرات',)
        if cmd in ('عالمي', 'globals'):
            return ('عالمي',)
        if cmd in ('أين', 'where', 'bt'):
            return ('أين',)
        if cmd in ('مصدر', 'list', 'l'):
            return ('مصدر',)
        if cmd in ('اطبع', 'طباعة', 'p', 'print'):
            if not rest:
                print("استخدام: اطبع <تعبير>", file=self.stdout)
                return None
            return ('اطبع', rest)
        if cmd == 'توقف':
            if rest.startswith('دالة '):
                name = rest[len('دالة '):].strip()
                if name:
                    return ('توقف_دالة', name)
                print("استخدام: توقف عند دالة <اسم>", file=self.stdout)
                return None
            if rest.startswith('عند '):
                target = rest[len('عند '):].strip()
                if target.startswith('دالة '):
                    name = target[len('دالة '):].strip()
                    if name:
                        return ('توقف_دالة', name)
                    print("استخدام: توقف عند دالة <اسم>", file=self.stdout)
                    return None
                if target.isdigit():
                    return ('توقف_سطر', int(target))
                print("استخدام: توقف عند <سطر> أو «توقف عند دالة <اسم>»",
                      file=self.stdout)
                return None
            print("استخدام: توقف عند <سطر> أو «توقف عند دالة <اسم>»",
                  file=self.stdout)
            return None
        if cmd == 'احذف':
            if rest.isdigit():
                return ('احذف_سطر', int(rest))
            if rest.startswith('دالة '):
                name = rest[len('دالة '):].strip()
                if name:
                    return ('احذف_دالة', name)
            print("استخدام: احذف <سطر> أو «احذف دالة <اسم>»",
                  file=self.stdout)
            return None
        print(f"أمر غير معروف: {cmd} — اكتب «مساعدة»", file=self.stdout)
        return None


class ScriptedFrontend:
    """واجهة اختبار: أفعال مجدولة مسبقًا ولقطة واحدة لكل توقف."""

    def __init__(self, actions):
        # كل عنصر: فعل جاهز يُعاد عند التوقف التالي (فحص أو استئناف)
        self.actions = list(actions)
        self.snapshots = []
        self.reports = []

    def report(self, text):
        self.reports.append(text)

    def pause(self, state, initial=True):
        if initial:
            self.snapshots.append(state)
        if not self.actions:
            return (RESUME_CONTINUE,)
        return self.actions.pop(0)


def debug_program(interpreter, tree, source, filename, frontend):
    """يشغل برنامجًا تحت المنقّح — يعيد آخر قيمة أو يرفع كما المفسر.

    الشجرة تُمرر صراحة لجمع أسطر الجمل (توثيق نقاط DAP الصالحة)،
    والخطاف يُركّب قبل run() بأجزاء من الثانية فلا جملة تفلت.
    """
    debugger = Debugger(source, filename=filename)
    debugger.frontend = frontend
    debugger._walk_lines(tree)
    debugger.attach(interpreter)
    return debugger, interpreter.run(tree)
