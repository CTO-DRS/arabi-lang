# -*- coding: utf-8 -*-
"""المفسر (Interpreter) — ينفذ شجرة الصياغة سطرًا بسطر (Tree-Walking).

يرفع ArabiRuntimeError برسائل عربية عند كل مشكلة، ويدعم:
متغيرات، شروط، حلقات، دوال (مع تعاود وإغلاق)، قوائم وقواميس،
تقطيع، معالجة أخطاء، إسناد متعدد، ووحدات جاهزة.
"""

import sys

from . import nodes as N
from .errors import ArabiRuntimeError
from .runtime import (
    Env, ArabiFunc, BuiltinFunc, ModuleValue,
    typename, display, install_builtins,
    LIST_METHODS, STR_METHODS, DICT_METHODS,
)

# للسماح بالتعاود العميق (مثل مضروب أعداد كبيرة)
sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))

# الأخطاء التي تمسكها كتلة "جرب"
CATCHABLE = (
    ArabiRuntimeError,
    ZeroDivisionError, ValueError, TypeError, IndexError,
    KeyError, AttributeError, OverflowError,
)


class BreakSignal(Exception):
    """إشارة داخلية لجملة كسر."""


class ContinueSignal(Exception):
    """إشارة داخلية لجملة استمر."""


class ReturnSignal(Exception):
    """إشارة داخلية لجملة أعد."""

    def __init__(self, value):
        self.value = value


class Interpreter:
    def __init__(self):
        self.globals = Env()
        install_builtins(self.globals)

    # ================== التنفيذ ==================

    def run(self, program):
        """ينفذ البرنامج ويعيد قيمة آخر تعبير (لبيئة REPL)."""
        env = self.globals
        last_value = None
        try:
            for stmt in program.statements:
                if isinstance(stmt, N.ExprStmt):
                    last_value = self.evaluate(stmt.expr, env)
                else:
                    self.execute(stmt, env)
        except BreakSignal:
            raise ArabiRuntimeError("جملة 'كسر' استُخدمت خارج حلقة")
        except ContinueSignal:
            raise ArabiRuntimeError("جملة 'استمر' استُخدمت خارج حلقة")
        except ReturnSignal:
            raise ArabiRuntimeError("جملة 'أعد' استُخدمت خارج الدوال")
        return last_value

    def execute(self, node, env):
        method = getattr(self, 'exec_' + type(node).__name__)
        return method(node, env)

    def evaluate(self, node, env):
        method = getattr(self, 'eval_' + type(node).__name__)
        return method(node, env)

    def exec_statements(self, statements, env):
        for stmt in statements:
            self.execute(stmt, env)

    # ================== الجمل ==================

    def exec_ExprStmt(self, node, env):
        self.evaluate(node.expr, env)

    def exec_Assign(self, node, env):
        value = self.evaluate(node.value, env)
        targets = node.targets
        if len(targets) == 1:
            self._assign_to(targets[0], value, env)
            return
        # إسناد متعدد: أ، ب = ١، ٢
        if not isinstance(value, (list, tuple)):
            raise ArabiRuntimeError(
                'لا يمكن تفكيك القيمة — استخدم قائمة بنفس عدد المتغيرات', node.line)
        if len(value) != len(targets):
            raise ArabiRuntimeError(
                f'عدد القيم ({len(value)}) لا يطابق عدد المتغيرات ({len(targets)})',
                node.line)
        for target, item in zip(targets, value):
            self._assign_to(target, item, env)

    def exec_AugAssign(self, node, env):
        current = self._read_target(node.target, env)
        value = self.evaluate(node.value, env)
        self._assign_to(node.target, self._binop(node.op, current, value, node.line), env)

    def exec_If(self, node, env):
        if self._truthy(self.evaluate(node.test, env)):
            self.exec_statements(node.body, env)
            return
        for test, body in node.elifs:
            if self._truthy(self.evaluate(test, env)):
                self.exec_statements(body, env)
                return
        if node.orelse is not None:
            self.exec_statements(node.orelse, env)

    def exec_While(self, node, env):
        while self._truthy(self.evaluate(node.test, env)):
            try:
                self.exec_statements(node.body, env)
            except BreakSignal:
                break
            except ContinueSignal:
                continue

    def exec_For(self, node, env):
        iterable = self.evaluate(node.iterable, env)
        if isinstance(iterable, dict):
            items = list(iterable.keys())
        elif isinstance(iterable, (list, range)):
            items = list(iterable)
        elif isinstance(iterable, str):
            items = list(iterable)
        else:
            raise ArabiRuntimeError(
                f'لا يمكن التكرار على {typename(iterable)} — استخدم قائمة أو نصًا أو مدى',
                node.line)
        for item in items:
            if len(node.targets) == 1:
                env.set(node.targets[0], item)
            else:
                if not isinstance(item, (list, tuple)) or len(item) != len(node.targets):
                    raise ArabiRuntimeError(
                        f'لا يمكن تفكيك العنصر {display(item)} على {len(node.targets)} متغيرات',
                        node.line)
                for target, part in zip(node.targets, item):
                    env.set(target, part)
            try:
                self.exec_statements(node.body, env)
            except BreakSignal:
                break
            except ContinueSignal:
                continue

    def exec_FuncDef(self, node, env):
        env.set(node.name, ArabiFunc(node.name, node.params, node.body, env))

    def exec_Return(self, node, env):
        value = None if node.value is None else self.evaluate(node.value, env)
        raise ReturnSignal(value)

    def exec_Break(self, node, env):
        raise BreakSignal()

    def exec_Continue(self, node, env):
        raise ContinueSignal()

    def exec_Pass(self, node, env):
        return None

    def exec_Try(self, node, env):
        try:
            try:
                self.exec_statements(node.body, env)
            except CATCHABLE as exc:
                if not isinstance(exc, ArabiRuntimeError):
                    # تحويل أخطاء بايثون غير المتوقعة إلى رسائل عربية
                    exc = ArabiRuntimeError(
                        self._native_error(exc),
                        getattr(exc, 'line', None) or node.line)
                    if node.except_body is None:
                        raise exc
                if node.except_body is None:
                    raise
                self.exec_statements(node.except_body, env)
        finally:
            if node.finally_body is not None:
                self.exec_statements(node.finally_body, env)

    def exec_Raise(self, node, env):
        value = self.evaluate(node.value, env)
        if isinstance(value, ArabiRuntimeError):
            raise value
        if isinstance(value, str):
            raise ArabiRuntimeError(value, node.line)
        raise ArabiRuntimeError(display(value), node.line)

    def exec_Import(self, node, env):
        module = self.globals.vars.get(node.name)
        if not isinstance(module, ModuleValue):
            raise ArabiRuntimeError(
                f"الوحدة '{node.name}' غير موجودة — الوحدات المتاحة: رياضيات، وقت",
                node.line)
        env.set(node.name, module)

    def _native_error(self, exc):
        text = str(exc)
        if isinstance(exc, ZeroDivisionError):
            return 'قسمة على صفر'
        if isinstance(exc, RecursionError):
            return 'تعاود عميق جدًا — تحقق من شرط التوقف في دالتك'
        if text:
            return f'خطأ داخلي: {text}'
        return f'خطأ من النوع {type(exc).__name__}'

    # ================== التعبيرات ==================

    def eval_Num(self, node, env):
        return node.value

    def eval_Str(self, node, env):
        return node.value

    def eval_Bool(self, node, env):
        return node.value

    def eval_Null(self, node, env):
        return None

    def eval_Name(self, node, env):
        return env.get(node.name, node.line)

    def eval_ListLit(self, node, env):
        return [self.evaluate(item, env) for item in node.items]

    def eval_DictLit(self, node, env):
        result = {}
        for key_node, value_node in zip(node.keys, node.values):
            key = self.evaluate(key_node, env)
            if isinstance(key, (list, dict)):
                raise ArabiRuntimeError(
                    'مفتاح القاموس يجب أن يكون نصًا أو عددًا', key_node.line)
            result[key] = self.evaluate(value_node, env)
        return result

    def eval_BinOp(self, node, env):
        op = node.op
        if op == 'و':
            left = self.evaluate(node.left, env)
            if not self._truthy(left):
                return left
            return self.evaluate(node.right, env)
        if op == 'أو':
            left = self.evaluate(node.left, env)
            if self._truthy(left):
                return left
            return self.evaluate(node.right, env)
        return self._binop(op, self.evaluate(node.left, env),
                           self.evaluate(node.right, env), node.line)

    def eval_UnaryOp(self, node, env):
        value = self.evaluate(node.operand, env)
        if node.op == '-':
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ArabiRuntimeError(
                    f'لا يمكن وضع سالب أمام {typename(value)}', node.line)
            return -value
        if node.op == 'ليس':
            return not self._truthy(value)
        raise ArabiRuntimeError(f"معامل أحادي غير معروف: {node.op}", node.line)

    def eval_Call(self, node, env):
        func = self.evaluate(node.func, env)
        args = [self.evaluate(a, env) for a in node.args]
        return self._call_value(func, args, node.line)

    def eval_Index(self, node, env):
        obj = self.evaluate(node.obj, env)
        index = self.evaluate(node.index, env)
        return self._get_index(obj, index, node.line)

    def eval_Slice(self, node, env):
        obj = self.evaluate(node.obj, env)
        if not isinstance(obj, (list, str, range)):
            raise ArabiRuntimeError(f'لا يمكن تقطيع {typename(obj)}', node.line)
        start = self._slice_bound(node.start, env, node.line)
        stop = self._slice_bound(node.stop, env, node.line)
        step = self._slice_bound(node.step, env, node.line)
        if step == 0:
            raise ArabiRuntimeError('خطوة التقطيع لا يمكن أن تكون صفرًا', node.line)
        try:
            return obj[start:stop:step]
        except TypeError:
            raise ArabiRuntimeError('حدود التقطيع يجب أن تكون أعدادًا صحيحة', node.line)

    def eval_MethodCall(self, node, env):
        obj = self.evaluate(node.obj, env)
        args = [self.evaluate(a, env) for a in node.args]
        if isinstance(obj, ModuleValue):
            member = obj.members.get(node.name)
            if member is None:
                raise ArabiRuntimeError(
                    f"الوحدة '{obj.name}' لا تحتوي على '{node.name}'", node.line)
            if isinstance(member, BuiltinFunc):
                return member.fn(args, node.line)
            return member
        if isinstance(obj, list):
            table = LIST_METHODS
        elif isinstance(obj, str):
            table = STR_METHODS
        elif isinstance(obj, dict):
            table = DICT_METHODS
        else:
            raise ArabiRuntimeError(
                f"النوع '{typename(obj)}' لا يدعم الطرق — لا توجد طريقة اسمها '{node.name}'",
                node.line)
        method = table.get(node.name)
        if method is None:
            raise ArabiRuntimeError(
                f"لا توجد طريقة اسمها '{node.name}' للنوع {typename(obj)}", node.line)
        return method(obj, args, node.line)

    def eval_Attribute(self, node, env):
        obj = self.evaluate(node.obj, env)
        if isinstance(obj, ModuleValue):
            member = obj.members.get(node.name)
            if member is None:
                raise ArabiRuntimeError(
                    f"الوحدة '{obj.name}' لا تحتوي على '{node.name}'", node.line)
            return member
        if isinstance(obj, dict) and node.name in obj:
            return obj[node.name]
        raise ArabiRuntimeError(
            f"النوع '{typename(obj)}' لا يدعم الوصول للخاصية '{node.name}'", node.line)

    # ================== العمليات ==================

    def _truthy(self, value):
        return bool(value)

    def _assign_to(self, target, value, env):
        if isinstance(target, N.Name):
            env.set(target.name, value)
        elif isinstance(target, N.Index):
            obj = self.evaluate(target.obj, env)
            index = self.evaluate(target.index, env)
            self._set_index(obj, index, value, target.line)
        else:
            raise ArabiRuntimeError('لا يمكن الإسناد إلى هذا التعبير', target.line)

    def _read_target(self, target, env):
        if isinstance(target, N.Name):
            return env.get(target.name, target.line)
        if isinstance(target, N.Index):
            obj = self.evaluate(target.obj, env)
            index = self.evaluate(target.index, env)
            return self._get_index(obj, index, target.line)
        raise ArabiRuntimeError('تعبير غير صالح للإسناد المركب', target.line)

    def _set_index(self, obj, index, value, line):
        if isinstance(obj, list):
            if isinstance(index, bool) or not isinstance(index, int):
                raise ArabiRuntimeError('فهرس القائمة يجب أن يكون عددًا صحيحًا', line)
            if not -len(obj) <= index < len(obj):
                raise ArabiRuntimeError(
                    f'الفهرس {index} خارج النطاق (طول القائمة {len(obj)})', line)
            obj[index] = value
            return
        if isinstance(obj, dict):
            if isinstance(index, (list, dict)):
                raise ArabiRuntimeError('مفتاح القاموس يجب أن يكون نصًا أو عددًا', line)
            obj[index] = value
            return
        raise ArabiRuntimeError(f'لا يمكن الإسناد بالفهرسة في {typename(obj)}', line)

    def _get_index(self, obj, index, line):
        if isinstance(obj, (list, range)):
            if isinstance(index, bool) or not isinstance(index, int):
                raise ArabiRuntimeError(
                    f'الفهرس يجب أن يكون عددًا صحيحًا لكن استلمت {typename(index)}', line)
            if not -len(obj) <= index < len(obj):
                raise ArabiRuntimeError(
                    f'الفهرس {index} خارج النطاق (الطول {len(obj)})', line)
            return obj[index]
        if isinstance(obj, str):
            if isinstance(index, bool) or not isinstance(index, int):
                raise ArabiRuntimeError('فهرس النص يجب أن يكون عددًا صحيحًا', line)
            if not -len(obj) <= index < len(obj):
                raise ArabiRuntimeError(
                    f'الفهرس {index} خارج النطاق (طول النص {len(obj)})', line)
            return obj[index]
        if isinstance(obj, dict):
            if index in obj:
                return obj[index]
            raise ArabiRuntimeError(
                f"المفتاح '{display(index)}' غير موجود في القاموس", line)
        raise ArabiRuntimeError(f'لا يمكن الفهرسة في {typename(obj)}', line)

    def _slice_bound(self, node, env, line):
        if node is None:
            return None
        value = self.evaluate(node, env)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ArabiRuntimeError('حدود التقطيع يجب أن تكون أعدادًا صحيحة', line)
        return value

    def _call_value(self, func, args, line):
        if isinstance(func, ArabiFunc):
            if len(args) != len(func.params):
                raise ArabiRuntimeError(
                    f"الدالة '{func.name}' تتوقع {len(func.params)} معاملًا "
                    f'لكنها استلمت {len(args)}', line)
            local = Env(func.env)
            for param, arg in zip(func.params, args):
                local.define(param, arg)
            try:
                self.exec_statements(func.body, local)
            except ReturnSignal as signal:
                return signal.value
            return None
        if isinstance(func, BuiltinFunc):
            return func.fn(args, line)
        raise ArabiRuntimeError(
            f"'{display(func)}' من نوع {typename(func)} — لا يمكن استدعاؤها كدالة", line)

    def _binop(self, op, left, right, line):
        if op == '+':
            l_num = self._is_number(left)
            r_num = self._is_number(right)
            if l_num and r_num:
                return left + right
            if isinstance(left, str) and isinstance(right, str):
                return left + right
            if isinstance(left, list) and isinstance(right, list):
                return left + right
            if isinstance(left, str) or isinstance(right, str):
                raise ArabiRuntimeError(
                    f'لا يمكن جمع نص مع {typename(right if isinstance(left, str) else left)}'
                    ' — استخدم نص() للتحويل أولًا', line)
            raise ArabiRuntimeError(
                f'لا يمكن جمع {typename(left)} مع {typename(right)}', line)
        if op == '-':
            self._both_numbers(left, right, op, line)
            return left - right
        if op == '*':
            l_num = self._is_number(left)
            r_num = self._is_number(right)
            if l_num and r_num:
                return left * right
            if isinstance(left, str) and isinstance(right, int) and not isinstance(right, bool):
                return left * right
            if isinstance(right, str) and isinstance(left, int) and not isinstance(left, bool):
                return right * left
            if isinstance(left, list) and isinstance(right, int) and not isinstance(right, bool):
                return left * right
            raise ArabiRuntimeError(
                f'لا يمكن ضرب {typename(left)} مع {typename(right)}', line)
        if op == '/':
            self._both_numbers(left, right, op, line)
            if right == 0:
                raise ArabiRuntimeError('قسمة على صفر', line)
            if isinstance(left, int) and isinstance(right, int) and left % right == 0:
                return left // right        # قسمة نظيفة تعطي عددًا صحيحًا
            return left / right
        if op == '%':
            self._both_numbers(left, right, op, line)
            if right == 0:
                raise ArabiRuntimeError('قسمة على صفر (باقي القسمة)', line)
            return left % right
        if op == '**':
            self._both_numbers(left, right, op, line)
            try:
                return left ** right
            except ZeroDivisionError:
                raise ArabiRuntimeError('لا يمكن رفع صفر إلى أس سالب', line)
        if op == '==':
            return self._values_equal(left, right)
        if op == '!=':
            return not self._values_equal(left, right)
        if op in ('<', '>', '<=', '>='):
            l_ok = self._is_number(left)
            r_ok = self._is_number(right)
            if not (l_ok and r_ok) and not (isinstance(left, str) and isinstance(right, str)):
                raise ArabiRuntimeError(
                    f"لا يمكن مقارنة {typename(left)} مع {typename(right)} باستخدام '{op}'",
                    line)
            if op == '<':
                return left < right
            if op == '>':
                return left > right
            if op == '<=':
                return left <= right
            return left >= right
        if op == 'في':
            return self._membership(left, right, line)
        if op == 'ليس في':
            return not self._membership(left, right, line)
        raise ArabiRuntimeError(f"معامل غير معروف: {op}", line)

    def _is_number(self, v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    def _both_numbers(self, left, right, op, line):
        if not self._is_number(left) or not self._is_number(right):
            raise ArabiRuntimeError(
                f"المعامل '{op}' يحتاج عددين لكن استلم {typename(left)} و {typename(right)}",
                line)

    def _values_equal(self, left, right):
        return left == right

    def _membership(self, left, right, line):
        if isinstance(right, str):
            if not isinstance(left, str):
                raise ArabiRuntimeError(
                    f"معامل 'في' مع النص يحتاج نصًا لكن استلم {typename(left)}", line)
            return left in right
        if isinstance(right, (list, range)):
            return left in right
        if isinstance(right, dict):
            return left in right
        raise ArabiRuntimeError(
            f"لا يمكن البحث في {typename(right)} — 'في' تعمل مع النصوص والقوائم والقواميس",
            line)
