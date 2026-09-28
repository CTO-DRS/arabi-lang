# -*- coding: utf-8 -*-
"""الدولاب الافتراضي (Virtual Machine) — الإصدار 1.24.

يترجم أجسام الدوال إلى تعليمات بايت-كود تنفذها حلقة دولاب واحدة سريعة،
بدل المرور الشجري على عقد شجرة الصياغة في كل استدعاء (getattr + استدعاء
طريقة لكل عقدة). النتيجة: تنفيذ أسرع للدوال الساخنة مع دلالات متطابقة.

الفلسفة: الشفافية الكاملة عبر الاحتياط التلقائي.
- الجمل المدعومة (تعبير، إسناد، شرط، حلقتان، أعد، كسر، استمر، تجاهل)
  تترجم إلى تعليمات صريحة.
- أي جملة أخرى (جرّب، بدّل، طابق، صنف، استورد...) تترجم إلى تعليمة
  EXEC_STMT تنفذها عبر الممسح الشجري الأصلي عند الوصول إليها.
- أي تعبير آخر (فهم، سهمية، تقطيع، الأصل...) تترجم إلى تعليمة
  EVAL_EXPR تقيّمها عبر الممسح الشجري.
فلا يمكن أبدًا أن يختلف سلوك البرنامج — الدولاب يسرّع المألوف
ويسلّم الاستثنائي للمفسّر الأصلي نفسه.

التعليمات ثلاثيات (op, arg, line): op عدد صحيح، arg معامل التعليمة
(فهرس ثابت أو اسم، أو موضع قفزة، أو عقدة احتياط)، line رقم السطر
للحفاظ على رسائل الأخطاء الدقيقة.

بنية الحلقة for/while: كل حلقة تدفع سياقها (هدف الكسر، هدف الاستمرار)
عند دخول جسمها (LOOP_PUSH) ويطفوه عند كل مخرجاتها (LOOP_POP)، وكسر
واستمر يترجمان قفزات مباشرة، وإشارات كسر/استمر العابرة من جمل احتياطية
(كبدّل داخل حلقة) تُمسك على مستوى الإطار وتوجه للسياق الأعمق — تمامًا
كما يفعل الممسح الشجري. حالة حلقة لكل (العناصر والمؤشر) تعيش في
for_states المستقلة عن مكدس القيم.
"""

from . import nodes as N
from .errors import ArabiRuntimeError
from .runtime import (
    BreakSignal, ContinueSignal, ReturnSignal,
)

import operator

# الأنواع العددية الخالصة (النوع الصريح يستثني المنطقية تلقائيًا)
_NUM_TYPES = frozenset({int, float})

# عمليات سريعة بلا دلالات خاصة — القسمة والباقي والأس لها قواعد خاصة
# في _binop (قسمة نظيفة، قسمة على صفر...) فلا تُسرَّع أبدًا
_FAST_BINOPS = {
    '+': operator.add,
    '-': operator.sub,
    '*': operator.mul,
    '==': operator.eq,
    '!=': operator.ne,
    '<': operator.lt,
    '>': operator.gt,
    '<=': operator.le,
    '>=': operator.ge,
}

# ================== التعليمات ==================

(OP_LOAD_CONST, OP_LOAD_NAME, OP_STORE_NAME, OP_LOAD_NULL, OP_POP,
 OP_BINOP, OP_UNARY, OP_AND_J, OP_OR_J, OP_JIF, OP_JUMP,
 OP_CALL, OP_METHOD_CALL, OP_LOAD_ATTR, OP_GET_INDEX,
 OP_LIST, OP_DICT, OP_FSTRING, OP_THIS,
 OP_ASSIGN_TO, OP_RETURN,
 OP_LOOP_PUSH, OP_LOOP_POP,
 OP_FOR_SETUP, OP_FOR_NEXT, OP_FOR_POP_STATE,
 OP_EVAL_EXPR, OP_EXEC_STMT,
 OP_DICT_CHECK_KEY) = range(29)

# عدد التعليمات (للاختبارات والتوثيق)
OPCODE_COUNT = 29


class _Lbl:
    """عنوان رمزي يُستبدل بموضع رقمي عند إغلاق الترجمة."""

    __slots__ = ()


class VmCode:
    """كود وسيط تنفيذي لدالة واحدة: الثوابت والأسماء والتعليمات."""

    __slots__ = ('consts', 'names', 'instrs')

    def __init__(self, consts, names, instrs):
        self.consts = consts      # قيم حرفية (أعداد ونصوص وصح/خطأ)
        self.names = names        # أسماء متغيرات وعوامل وطرق
        self.instrs = instrs      # [(op, arg, line), ...]


# ================== المترجم ==================

class Compiler:
    """يترجم جسم دالة عربي إلى VmCode.

    الترجمة لا تفشل أبدًا: ما لا يدعمه يغلفه بتعليمة احتياطية تنفذها
    الممسح الشجري الأصلي، فيبقى السلوك صحيحًا مهما كان الكود.
    """

    def __init__(self):
        self.consts = []
        self._cmap = {}
        self.names = []
        self._nmap = {}
        self.instrs = []          # [op, arg, line] قابلة للتعديل قبل الإغلاق
        self._pos = {}            # العنوان ← موضعه

    # ---------- أدوات الترميز ----------

    def konst(self, value):
        key = (type(value), value)
        idx = self._cmap.get(key)
        if idx is None:
            idx = len(self.consts)
            self._cmap[key] = idx
            self.consts.append(value)
        return idx

    def name(self, text):
        idx = self._nmap.get(text)
        if idx is None:
            idx = len(self.names)
            self._nmap[text] = idx
            self.names.append(text)
        return idx

    def emit(self, op, arg, line):
        self.instrs.append([op, arg, line])

    def lbl(self):
        return _Lbl()

    def place(self, label):
        self._pos[label] = len(self.instrs)

    def close(self):
        """يستبدل العناوين الرمزية بمواضع ويعيد VmCode نهائيًا."""
        instrs = []
        for op, arg, line in self.instrs:
            if type(arg) is _Lbl:
                arg = self._pos[arg]
            elif type(arg) is tuple:
                arg = tuple(self._pos[x] if type(x) is _Lbl else x
                            for x in arg)
            instrs.append((op, arg, line))
        return VmCode(self.consts, self.names, instrs)

    # ---------- الجمل ----------

    def stmts(self, statements, loop):
        for stmt in statements:
            self.stmt(stmt, loop)

    def stmt(self, node, loop):
        """يترجم جملة — loop سياق الحلقة الأعمق أو None."""
        if isinstance(node, N.ExprStmt):
            self.expr(node.expr)
            self.emit(OP_POP, None, node.line)
        elif isinstance(node, N.Assign):
            if len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, N.Name):
                    self.expr(node.value)
                    self.emit(OP_STORE_NAME, self.name(target.name),
                              node.line)
                    return
                if isinstance(target, (N.Index, N.Attribute)):
                    self.expr(node.value)
                    self.emit(OP_ASSIGN_TO, target, node.line)
                    return
            self._fallback_stmt(node, loop)
        elif isinstance(node, N.AugAssign):
            target = node.target
            op_str = node.op
            if isinstance(target, N.Name):
                self.emit(OP_LOAD_NAME, self.name(target.name), target.line)
                self.expr(node.value)
                self.emit(OP_BINOP, op_str, node.line)
                self.emit(OP_STORE_NAME, self.name(target.name), node.line)
            elif isinstance(target, (N.Index, N.Attribute)):
                # القراءة ثم القيمة ثم العملية ثم التعيين — بترتيب الممسح
                self.emit(OP_EVAL_EXPR, target, target.line)
                self.expr(node.value)
                self.emit(OP_BINOP, op_str, node.line)
                self.emit(OP_ASSIGN_TO, target, node.line)
            else:
                self._fallback_stmt(node, loop)
        elif isinstance(node, N.If):
            self._if_chain(node, loop)
        elif isinstance(node, N.While):
            self._while(node, loop)
        elif isinstance(node, N.For):
            self._for(node, loop)
        elif isinstance(node, N.Return):
            if node.value is None:
                self.emit(OP_LOAD_NULL, None, node.line)
            else:
                self.expr(node.value)
            self.emit(OP_RETURN, None, node.line)
        elif isinstance(node, N.Break):
            if loop is not None:
                self.emit(OP_JUMP, loop[0], node.line)
            else:
                self._fallback_stmt(node, loop)
        elif isinstance(node, N.Continue):
            if loop is not None:
                self.emit(OP_JUMP, loop[1], node.line)
            else:
                self._fallback_stmt(node, loop)
        elif isinstance(node, N.Pass):
            pass
        else:
            self._fallback_stmt(node, loop)

    def _fallback_stmt(self, node, loop):
        # جملة غير مدعومة تُنفذ شجريًا كما هي — إشارات الكسر/الاستمرار
        # الخارجة منها تلتقط عند إطار الحلقة في vm_exec فلا حاجة
        # لمطابقة أهداف القفز هنا (كانت بيانات ميتة مضللة)
        self.emit(OP_EXEC_STMT, node, node.line)

    def _if_chain(self, node, loop):
        end = self.lbl()
        nxt = self.lbl()
        self.expr(node.test)
        self.emit(OP_JIF, nxt, node.line)
        self.stmts(node.body, loop)
        self.emit(OP_JUMP, end, None)
        for test, body in node.elifs:
            self.place(nxt)
            nxt = self.lbl()
            self.expr(test)
            self.emit(OP_JIF, nxt, node.line)
            self.stmts(body, loop)
            self.emit(OP_JUMP, end, None)
        self.place(nxt)
        if node.orelse is not None:
            self.stmts(node.orelse, loop)
        self.place(end)

    def _while(self, node, loop):
        top = self.lbl()      # دخول الحلقة: دفع السياق
        test = self.lbl()     # هدف الاستمرار
        sig = self.lbl()      # هدف الخروج (كسر أو فشل الشرط)
        self.place(top)
        self.emit(OP_LOOP_PUSH, (sig, test), None)
        self.place(test)
        self.expr(node.test)
        self.emit(OP_JIF, sig, node.line)
        self.stmts(node.body, (sig, test, 'while'))
        self.emit(OP_JUMP, test, None)
        self.place(sig)
        self.emit(OP_LOOP_POP, None, None)

    def _for(self, node, loop):
        self.expr(node.iterable)
        top = self.lbl()
        nxt = self.lbl()
        body = self.lbl()
        sig = self.lbl()
        self.emit(OP_FOR_SETUP, node, node.line)
        self.place(top)
        self.emit(OP_LOOP_PUSH, (sig, nxt), None)
        self.place(nxt)
        self.emit(OP_FOR_NEXT, (node, body, sig), node.line)
        self.place(body)
        self.stmts(node.body, (sig, nxt, 'for'))
        self.emit(OP_JUMP, nxt, None)
        self.place(sig)
        self.emit(OP_FOR_POP_STATE, None, None)
        self.emit(OP_LOOP_POP, None, None)

    # ---------- التعبيرات ----------

    def expr(self, node):
        """يترجم تعبيرًا ي push قيمة واحدة على المكدس."""
        if isinstance(node, N.Num) or isinstance(node, N.Str) \
                or isinstance(node, N.Bool):
            self.emit(OP_LOAD_CONST, self.konst(node.value), node.line)
        elif isinstance(node, N.Null):
            self.emit(OP_LOAD_NULL, None, node.line)
        elif isinstance(node, N.Name):
            self.emit(OP_LOAD_NAME, self.name(node.name), node.line)
        elif isinstance(node, N.ListLit):
            if not any(isinstance(i, N.SpreadArg) for i in node.items):
                for item in node.items:
                    self.expr(item)
                self.emit(OP_LIST, len(node.items), node.line)
            else:
                self.emit(OP_EVAL_EXPR, node, node.line)
        elif isinstance(node, N.DictLit):
            # تناوب مفتاح/قيمة مع فحص المفتاح فور حسابه وقبل قيمته
            # (1.23) — نفس ترتيب الأثر الجانبي في الممسح الشجري
            # زوجًا زوجًا: مفتاح₁ ← فحص₁ ← قيمة₁ ← مفتاح₂ ...
            for key, value in zip(node.keys, node.values):
                self.expr(key)
                self.emit(OP_DICT_CHECK_KEY, key.line, key.line)
                self.expr(value)
            self.emit(OP_DICT, len(node.keys), node.line)
        elif isinstance(node, N.BinOp):
            if node.op == 'و' or node.op == 'أو':
                self._logical(node)
            else:
                self.expr(node.left)
                self.expr(node.right)
                # اسم العامل نفسه في التعليمة — مقارنة سريعة في الحلقة
                self.emit(OP_BINOP, node.op, node.line)
        elif isinstance(node, N.UnaryOp):
            self.expr(node.operand)
            self.emit(OP_UNARY, node.op, node.line)
        elif isinstance(node, N.Ternary):
            false_lbl = self.lbl()
            end = self.lbl()
            self.expr(node.test)
            self.emit(OP_JIF, false_lbl, node.line)
            self.expr(node.if_true)
            self.emit(OP_JUMP, end, None)
            self.place(false_lbl)
            self.expr(node.if_false)
            self.place(end)
        elif isinstance(node, N.Call):
            if all(name is None and not isinstance(e, N.SpreadArg)
                   for name, e in node.args):
                self.expr(node.func)
                for _name, arg_expr in node.args:
                    self.expr(arg_expr)
                self.emit(OP_CALL, len(node.args), node.line)
            else:
                self.emit(OP_EVAL_EXPR, node, node.line)
        elif isinstance(node, N.Index):
            self.expr(node.obj)
            self.expr(node.index)
            self.emit(OP_GET_INDEX, None, node.line)
        elif isinstance(node, N.MethodCall):
            if all(name is None and not isinstance(e, N.SpreadArg)
                   for name, e in node.args):
                self.expr(node.obj)
                for _name, arg_expr in node.args:
                    self.expr(arg_expr)
                self.emit(OP_METHOD_CALL,
                          (self.name(node.name), len(node.args)), node.line)
            else:
                self.emit(OP_EVAL_EXPR, node, node.line)
        elif isinstance(node, N.Attribute):
            self.expr(node.obj)
            self.emit(OP_LOAD_ATTR, self.name(node.name), node.line)
        elif isinstance(node, N.This):
            self.emit(OP_THIS, None, node.line)
        elif isinstance(node, N.FString):
            parts_arg = tuple(lit if kind == 'str' else None
                              for kind, lit in node.parts)
            for kind, part in node.parts:
                if kind != 'str':
                    self.expr(part)
            self.emit(OP_FSTRING, parts_arg, node.line)
        else:
            # فهم، سهمية، تقطيع، الأصل، ... — عبر الممسح الشجري الأصلي
            self.emit(OP_EVAL_EXPR, node, node.line)

    def _logical(self, node):
        """و/أو بقيمهما القصيرة: يبقي اليسار أو يكمل لليمين."""
        end = self.lbl()
        if node.op == 'و':
            self.expr(node.left)
            self.emit(OP_AND_J, end, node.line)
        else:
            self.expr(node.left)
            self.emit(OP_OR_J, end, node.line)
        self.expr(node.right)
        self.place(end)


def compile_function(body):
    """يترجم جسم دالة (قائمة جمل) إلى VmCode — لا يفشل أبدًا."""
    compiler = Compiler()
    compiler.stmts(body, None)
    return compiler.close()


# ================== حلقة الدولاب ==================

def vm_exec(interp, code, env):
    """ينفذ كود دولاب في بيئة معينة — يعيد قيمة 'أعد' أو None عند النهاية.

    interp هو المفسّر نفسه: كل عملية تحتاج دلالات كاملة (استدعاء، طرق،
    عوامل محملة، فهرسة) توكل للمساعدات الأصلية نفسها، فتظهر الأخطاء
    بنصوصها وأسطرها المعتادة. 'أعد' الصريحة تعيد قيمتها مباشرة بلا
    استثناء، وأعد الصادرة من جمل احتياطية تصل كإشارة ReturnSignal.
    """
    instrs = code.instrs
    consts = code.consts
    names = code.names
    stack = []
    push = stack.append
    pop = stack.pop
    loops = None              # سياقات الحلقات: (هدف الكسر، هدف الاستمرار)
    for_states = None         # حالة حلقات لكل: [العناصر، المؤشر] أو None
    binop = interp._binop
    call_value = interp._call_value
    env_get = env.get
    env_set = env.set
    ip = 0
    n = len(instrs)

    while ip < n:
        try:
            op, arg, line = instrs[ip]
            ip += 1
            if op == OP_LOAD_NAME:
                push(env_get(names[arg], line))
            elif op == OP_LOAD_CONST:
                push(consts[arg])
            elif op == OP_BINOP:
                right = pop()
                left = pop()
                # مسار سريع للأعداد الخالصة — النوع الصريح يستثني
                # المنطقية والكائنات فالنتيجة مطابقة تمامًا للممسح
                if type(left) in _NUM_TYPES and type(right) in _NUM_TYPES:
                    fn = _FAST_BINOPS.get(arg)
                    if fn is not None:
                        push(fn(left, right))
                    else:
                        push(binop(arg, left, right, line))
                else:
                    push(binop(arg, left, right, line))
            elif op == OP_JIF:
                # الصحة عبر المفسر نفسه لا bool الخام — لئلا تنحرف
                # حلقات/شروط الدولاب عن دلالات و/أو إذا صارت للصحة
                # دلالة لغوية خاصة (تقرير التدقيق م9-1)
                if not interp._truthy(pop()):
                    ip = arg
            elif op == OP_STORE_NAME:
                env_set(names[arg], pop())
            elif op == OP_JUMP:
                ip = arg
            elif op == OP_POP:
                pop()
            elif op == OP_CALL:
                if arg:
                    args = stack[-arg:]
                    del stack[-arg:]
                else:
                    args = []
                func = pop()
                push(call_value(func, args, {}, line))
            elif op == OP_GET_INDEX:
                index = pop()
                obj = pop()
                push(interp._get_index(obj, index, line))
            elif op == OP_METHOD_CALL:
                name_idx, argc = arg
                if argc:
                    args = stack[-argc:]
                    del stack[-argc:]
                else:
                    args = []
                obj = pop()
                push(interp._call_method_value(obj, names[name_idx], args,
                                               {}, line))
            elif op == OP_LOAD_ATTR:
                obj = pop()
                push(interp._get_attribute(obj, names[arg], line))
            elif op == OP_LIST:
                if arg:
                    items = stack[-arg:]
                    del stack[-arg:]
                    push(items)
                else:
                    push([])
            elif op == OP_RETURN:
                return pop()             # قيمة الإرجاع مباشرة — بلا استثناء
            elif op == OP_LOOP_PUSH:
                if loops is None:
                    loops = []
                loops.append(arg)
            elif op == OP_LOOP_POP:
                loops.pop()
            elif op == OP_FOR_SETUP:
                if for_states is None:
                    for_states = []
                iterable = pop()
                if isinstance(iterable, dict):
                    for_states.append([list(iterable.keys()), 0])
                elif isinstance(iterable, (list, range, str)):
                    for_states.append([list(iterable), 0])
                else:
                    # مولد أو كائن بتالٍ أو غيره — الممسح الشجري يدير
                    # الحلقة كاملة (مع إغلاق المولدات) ولا تسرّ إشاراتها
                    try:
                        interp._for_iterate(arg, iterable, env)
                    except (BreakSignal, ContinueSignal):
                        pass
                    for_states.append(None)
            elif op == OP_ASSIGN_TO:
                interp._assign_to(arg, pop(), env)
            elif op == OP_FOR_NEXT:
                node, body_ip, sig_ip = arg
                state = for_states[-1]
                if state is None:
                    ip = sig_ip            # حُلّت بالمسح الشجري — انتهت
                else:
                    items, i = state
                    if i >= len(items):
                        ip = sig_ip        # نفدت — الخروج عبر التنظيف
                    else:
                        interp._for_bind(node, items[i], env)
                        state[1] = i + 1
                        ip = body_ip
            elif op == OP_FOR_POP_STATE:
                for_states.pop()
            elif op == OP_AND_J:
                if interp._truthy(stack[-1]):
                    pop()
                else:
                    ip = arg
            elif op == OP_OR_J:
                if interp._truthy(stack[-1]):
                    ip = arg
                else:
                    pop()
            elif op == OP_UNARY:
                push(interp._unary_op(arg, pop(), line))
            elif op == OP_LOAD_NULL:
                push(None)
            elif op == OP_THIS:
                this_val = interp._current_this(env)
                if this_val is None:
                    raise ArabiRuntimeError(
                        "لا يمكن استخدام 'هذا' إلا داخل طرق صنف", line)
                push(this_val)
            elif op == OP_DICT_CHECK_KEY:
                # فحص مفتاح القاموس لحظة حسابه وقبل تقييم قيمته —
                # يطابق ترتيب الممسح الشجري في الأثر الجانبي (1.23)
                key = pop()
                if isinstance(key, (list, dict)):
                    raise ArabiRuntimeError(
                        'مفتاح القاموس يجب أن يكون نصًا أو عددًا', arg)
                push(key)
            elif op == OP_DICT:
                npairs = arg
                if npairs:
                    flat = stack[-2 * npairs:]
                    del stack[-2 * npairs:]
                    result = {}
                    for j in range(npairs):
                        result[flat[2 * j]] = flat[2 * j + 1]
                    push(result)
                else:
                    push({})
            elif op == OP_FSTRING:
                count = arg.count(None)
                if count:
                    vals = stack[-count:]
                    del stack[-count:]
                else:
                    vals = []
                out = []
                j = 0
                for part in arg:
                    if part is None:
                        out.append(interp._display(vals[j]))
                        j += 1
                    else:
                        out.append(part)
                push(''.join(out))
            elif op == OP_EVAL_EXPR:
                push(interp.evaluate(arg, env))
            elif op == OP_EXEC_STMT:
                interp.execute(arg, env)
            else:
                raise ArabiRuntimeError(
                    f'تعليمة دولاب غير معروفة: {op}', line)
        except BreakSignal:
            if not loops:
                raise
            ip = loops[-1][0]
        except ContinueSignal:
            if not loops:
                raise
            ip = loops[-1][1]
