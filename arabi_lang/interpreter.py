# -*- coding: utf-8 -*-
"""المفسر (Interpreter) — ينفذ شجرة الصياغة سطرًا بسطر (Tree-Walking).

يرفع ArabiRuntimeError برسائل عربية عند كل مشكلة، ويدعم:
متغيرات، شروط، حلقات، دوال (مع تعاود وإغلاق وافتراضات ومعاملات بالاسم)،
دوال سهمية، قوائم وقواميس، تقطيع، معالجة أخطاء، إسناد متعدد،
أصناف ووراثة، واستيراد وحدات من ملفات .عربي.
"""

import os
import sys
import threading

from . import nodes as N
from .errors import ArabiRuntimeError, ArabiUserError
from .lexer import Lexer
from .parser import Parser
from .runtime import (
    Env, ArabiFunc, BuiltinFunc, ModuleValue,
    ClassValue, InstanceValue, BoundMethod,
    EnumValue, EnumMember, Property, NativeCtor,
    GeneratorValue, GeneratorClose, DBValue, SuperValue, _gen_tls,
    ThreadValue, LockValue, QueueValue, DateValue,
    typename, display, install_builtins, NO_DEFAULT,
    LIST_METHODS, STR_METHODS, DICT_METHODS, OVERLOAD_METHODS,
    GENERATOR_METHODS, DB_METHODS,
    THREAD_METHODS, LOCK_METHODS, QUEUE_METHODS, DATE_METHODS,
)

# للسماح بالتعاود العميق (مثل مضروب أعداد كبيرة)
sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))

# الأخطاء التي تمسكها كتلة "جرب"
CATCHABLE = (
    ArabiRuntimeError,
    ZeroDivisionError, ValueError, TypeError, IndexError,
    KeyError, AttributeError, OverflowError,
)

# الوحدات الجاهزة المدمجة في اللغة
BUILTIN_MODULES = ('رياضيات', 'وقت', 'ملفات', 'جيسون', 'عشوائية',
                   'نظام', 'تنظيم', 'شبكة', 'تحويل', 'اختبارات', 'خادم',
                   'قاعدة', 'ترميز', 'جداول', 'خيوط', 'تواريخ')

# علامة داخلية: لا يوجد تحميل عامل مطبق (يستخدمها _try_overload)
_SKIP = object()


class BreakSignal(Exception):
    """إشارة داخلية لجملة كسر."""


class ContinueSignal(Exception):
    """إشارة داخلية لجملة استمر."""


class ReturnSignal(Exception):
    """إشارة داخلية لجملة أعد."""

    def __init__(self, value):
        self.value = value


class Interpreter:
    def __init__(self, script_dir=None):
        self.globals = Env()
        install_builtins(self.globals)
        # الصنف المدمج 'استثناء' — أصله لأخطاء المستخدم المخصصة
        self.error_class = ClassValue('استثناء', None, {
            'إنشاء': NativeCtor('إنشاء', 'خطأ'),
        }, Env())
        self.globals.define('استثناء', self.error_class)
        # مجلد البرنامج الرئيسي (أساس البحث عن الوحدات)
        self.script_dir = script_dir or os.getcwd()
        # كومة مجلدات الوحدات قيد التحميل (للاستيراد المتداخل)
        self._module_stack = []
        # ذاكرة الوحدات المحمّلة: مسار ← ModuleValue
        self._module_cache = {}
        # مسارات قيد التحميل حاليًا — لكشف الاستيراد الدائري
        self._loading = set()
        # سياق لكل خيط: مكدس 'هذا' الحالي (للدوال المستدعاة من طرق)
        self._tls = threading.local()

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

    def exec_Switch(self, node, env):
        """بدّل: ينفذ كتلة الحالة المطابقة فقط (بدون تساقط)، أو 'افتراض'.

        تُقارن قيمة التعبير بالحالات بالترتيب حتى أول تطابق.
        'كسر' داخل 'بدّل' يخرج من الحلقة المحيطة إن وُجدت (سلوك بايثوني).
        """
        subject = self.evaluate(node.subject, env)
        for value_expr, body in node.cases:
            if self._values_equal(subject, self.evaluate(value_expr, env)):
                self.exec_statements(body, env)
                return
        if node.default_body is not None:
            self.exec_statements(node.default_body, env)

    def exec_Match(self, node, env):
        """مطابقة الأنماط: يجرب الأنماط بالترتيب حتى أول تطابق.

        روابط الالتقاط تُطبق على النطاق الحالي فور نجاح النمط (كما في
        بايثون)، ثم يُفحص الحارس إن وُجد — وفشل الحارس لا يُلغي الروابط.
        """
        subject = self.evaluate(node.subject, env)
        for pattern, guard, body in node.cases:
            bindings = {}
            if not self._match_pattern(pattern, subject, bindings, env):
                continue
            for name, value in bindings.items():
                env.set(name, value)
            if guard is not None and not self._truthy(
                    self.evaluate(guard, env)):
                continue
            self.exec_statements(body, env)
            return
        if node.default_body is not None:
            self.exec_statements(node.default_body, env)

    def _match_pattern(self, pat, subject, bindings, env):
        """يجرب نمطًا على قيمة — يعيد صح ويمتلئ bindings عند النجاح."""
        if isinstance(pat, N.PLiteral):
            return self._values_equal(subject, self.evaluate(pat.expr, env))
        if isinstance(pat, N.PCapture):
            if pat.name is None:                    # الرمز البديل '_'
                return True
            # التقاط مكرر داخل النمط الواحد يعني مطابقة تساوي: [أ، أ]
            if pat.name in bindings:
                return self._values_equal(bindings[pat.name], subject)
            bindings[pat.name] = subject
            return True
        if isinstance(pat, N.POr):
            for sub in pat.patterns:
                trial = {}
                if self._match_pattern(sub, subject, trial, env):
                    bindings.update(trial)
                    return True
            return False
        if isinstance(pat, N.PList):
            if not isinstance(subject, list):
                return False
            if pat.rest is None and len(subject) != len(pat.items):
                return False
            if pat.rest is not None and len(subject) < len(pat.items):
                return False
            trial = {}
            for item_pat, item in zip(pat.items, subject):
                if not self._match_pattern(item_pat, item, trial, env):
                    return False
            if isinstance(pat.rest, str):
                trial[pat.rest] = subject[len(pat.items):]
            bindings.update(trial)
            return True
        if isinstance(pat, N.PDict):
            if not isinstance(subject, dict):
                return False
            trial = {}
            for key_expr, val_pat in zip(pat.keys, pat.patterns):
                key = self.evaluate(key_expr, env)
                if key not in subject:
                    return False
                if not self._match_pattern(val_pat, subject[key], trial, env):
                    return False
            bindings.update(trial)
            return True
        raise ArabiRuntimeError('نمط غير مدعوم', getattr(pat, 'line', None))

    def exec_For(self, node, env):
        iterable = self.evaluate(node.iterable, env)
        if isinstance(iterable, dict):
            items = list(iterable.keys())
        elif isinstance(iterable, (list, range)):
            items = list(iterable)
        elif isinstance(iterable, str):
            items = list(iterable)
        elif isinstance(iterable, GeneratorValue):
            # التكرار على مولد: قيم تباعًا مع إغلاقه عند الخروج (كسر/خطأ)
            try:
                while True:
                    has, item = iterable._next_pair()
                    if not has:
                        break
                    self._for_bind(node, item, env)
                    try:
                        self.exec_statements(node.body, env)
                    except BreakSignal:
                        break
                    except ContinueSignal:
                        continue
            finally:
                iterable.close()
            return
        else:
            raise ArabiRuntimeError(
                f'لا يمكن التكرار على {typename(iterable)} — استخدم قائمة أو نصًا أو مدى',
                node.line)
        for item in items:
            self._for_bind(node, item, env)
            try:
                self.exec_statements(node.body, env)
            except BreakSignal:
                break
            except ContinueSignal:
                continue

    def _for_bind(self, node, item, env):
        """يربط عنصر حلقة 'لكل' بمتغير أو متغيرات التفكيك."""
        if len(node.targets) == 1:
            env.set(node.targets[0], item)
            return
        if not isinstance(item, (list, tuple)) or len(item) != len(node.targets):
            raise ArabiRuntimeError(
                f'لا يمكن تفكيك العنصر {display(item)} على {len(node.targets)} متغيرات',
                node.line)
        for target, part in zip(node.targets, item):
            env.set(target, part)

    def exec_FuncDef(self, node, env):
        params = [(name, self._eval_default(default, env))
                  for name, default in node.params]
        value = ArabiFunc(node.name, params, node.body, env,
                          is_generator=node.is_generator, rest=node.rest)
        # تطبيق المزخرفات من الأسفل إلى الأعلى (كما في بايثون)
        for dec in reversed(node.decorators):
            func_value = self.evaluate(dec, env)
            value = self._call_value(func_value, [value], {},
                                     getattr(dec, 'line', node.line))
            if not isinstance(value, (ArabiFunc, BuiltinFunc, BoundMethod)):
                raise ArabiRuntimeError(
                    f"المزخرف يجب أن يعيد دالة لكنه أعاد {typename(value)}",
                    getattr(dec, 'line', node.line))
        env.set(node.name, value)

    def _eval_default(self, node, env):
        """يقيّم تعبير القيمة الافتراضية عند التعريف، أو يعيد NO_DEFAULT."""
        if node is None:
            return NO_DEFAULT
        return self.evaluate(node, env)

    def exec_ClassDef(self, node, env):
        """تعريف صنف: يجمع الطرق والثوابت ويربطه بأصوله (وراثة متعددة)."""
        parents = []
        if node.superclass is not None:
            names = (node.superclass if isinstance(node.superclass, list)
                     else [node.superclass])
            for pname in names:
                parent = env.get(pname, node.line)
                if not isinstance(parent, ClassValue):
                    raise ArabiRuntimeError(
                        f"'{pname}' ليس صنفًا — الوراثة تكون من صنف فقط",
                        node.line)
                parents.append(parent)
        # فحص الوراثة الدائرية عبر أسلاف كل أصل
        for parent in parents:
            for ancestor in self._class_chain(parent):
                if ancestor.name == node.name:
                    raise ArabiRuntimeError(
                        f"وراثة دائرية: الصنف '{node.name}' يرث نفسه "
                        f'عبر الصنف {ancestor.name}', node.line)
        mro_ancestors = self._merge_mro(node.name, parents, node.line)
        members = {}
        # نطاق الصنف: تُبحث فيه الأسماء داخل الطرق، ويحمل 'الأصل' (الأول)
        class_env = Env(env)
        class_env.define('الأصل', parents[0] if parents else None)
        for stmt in node.body:
            if isinstance(stmt, N.FuncDef):
                if stmt.name in members:
                    raise ArabiRuntimeError(
                        f"تكرار تعريف الطريقة '{stmt.name}' في الصنف '{node.name}'",
                        stmt.line)
                params = [(name, self._eval_default(default, env))
                          for name, default in stmt.params]
                method = ArabiFunc(stmt.name, params, stmt.body, class_env,
                                   is_generator=stmt.is_generator,
                                   rest=stmt.rest)
                # تطبيق مزخرفات الطرق إن وجدت
                for dec in reversed(stmt.decorators):
                    func_value = self.evaluate(dec, env)
                    method = self._call_value(func_value, [method], {},
                                              getattr(dec, 'line', stmt.line))
                    if not isinstance(method, (ArabiFunc, BuiltinFunc, BoundMethod)):
                        raise ArabiRuntimeError(
                            f"المزخرف يجب أن يعيد دالة لكنه أعاد {typename(method)}",
                            getattr(dec, 'line', stmt.line))
                members[stmt.name] = method
            elif isinstance(stmt, N.PropertyDef):
                if stmt.name in members:
                    raise ArabiRuntimeError(
                        f"تكرار الاسم '{stmt.name}' في الصنف '{node.name}'",
                        stmt.line)
                members[stmt.name] = Property(
                    ArabiFunc(stmt.name, [], stmt.body, class_env))
            elif isinstance(stmt, N.Pass):
                continue                          # جملة تجاهل مسموحة في جسم الصنف
            elif (isinstance(stmt, N.Assign) and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], N.Name)):
                name = stmt.targets[0].name
                value = self.evaluate(stmt.value, env)
                members[name] = value              # ثابت صنف
                class_env.define(name, value)
            else:
                raise ArabiRuntimeError(
                    "داخل 'صنف' لا يُسمح إلا بتعريف دوال وخصائص وثوابت",
                    stmt.line)
        new_class = ClassValue(node.name, parents[0] if parents else None,
                               members, class_env)
        if parents:
            new_class.mro = [new_class] + mro_ancestors
        env.set(node.name, new_class)

    def exec_InterfaceDef(self, node, env):
        """تعريف واجهة: عقد مجرد تلتزم به الأصناف.

        الطرق المجردة (بلا جسم) تُسجل في abstract ولا تُخزن كأعضاء،
        والطرق بجسم تصل تنفيذًا افتراضيًا يورثه كل صنف منفذ.
        """
        parents = []
        if node.superclass is not None:
            names = (node.superclass if isinstance(node.superclass, list)
                     else [node.superclass])
            for pname in names:
                parent = env.get(pname, node.line)
                if not isinstance(parent, ClassValue):
                    raise ArabiRuntimeError(
                        f"'{pname}' ليس واجهة — وراثة الواجهات تكون من "
                        'واجهة فقط', node.line)
                if not parent.is_interface:
                    raise ArabiRuntimeError(
                        f"لا يمكن أن ترث الواجهة '{node.name}' الصنف "
                        f"'{pname}' — الواجهات ترث الواجهات فقط", node.line)
                parents.append(parent)
        members = {}
        class_env = Env(env)
        class_env.define('الأصل', parents[0] if parents else None)
        for stmt in node.body:
            if isinstance(stmt, N.FuncDef):
                if stmt.name in members:
                    raise ArabiRuntimeError(
                        f"تكرار تعريف الطريقة '{stmt.name}' في الواجهة "
                        f"'{node.name}'", stmt.line)
                if stmt.body is None:
                    continue                   # طريقة مجردة — لا عضو
                params = [(name, self._eval_default(default, env))
                          for name, default in stmt.params]
                members[stmt.name] = ArabiFunc(
                    stmt.name, params, stmt.body, class_env,
                    is_generator=stmt.is_generator, rest=stmt.rest)
            elif (isinstance(stmt, N.Assign) and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], N.Name)):
                name = stmt.targets[0].name
                value = self.evaluate(stmt.value, env)
                members[name] = value          # ثابت واجهة
                class_env.define(name, value)
            elif isinstance(stmt, N.Pass):
                continue
            else:
                raise ArabiRuntimeError(
                    "داخل 'واجهة' تُسمح الطرق (بجسم أو بلا جسم) والثوابت فقط",
                    stmt.line)
        interface = ClassValue(node.name, parents[0] if parents else None,
                               members, class_env,
                               is_interface=True, abstract=node.abstract)
        if parents:
            # الوراثة بين الواجهات خطية — نجمع الطرق المجردة من الأصول
            inherited = set(node.abstract)
            for parent in parents:
                for scope in self._class_chain(parent):
                    inherited |= scope.abstract
            interface.abstract = frozenset(inherited)
        env.set(node.name, interface)

    def _class_chain(self, cls):
        """يتكرر على سلسلة الصنف (MRO إن حُسب، وإلا سلسلة superclass)."""
        if cls.mro is not None:
            yield from cls.mro
            return
        scope = cls
        while scope is not None:
            yield scope
            scope = scope.superclass

    def _merge_mro(self, name, parents, line):
        """يحسب ترتيب حل الطرق C3 للأصول — بلا الصنف نفسه.

        يعيد قائمة الأصول بترتيب لا يكسر ترتيب أي أصل ولا يعيد
        ترتيبًا متناقضًا (كالمعينات المتعارضة).
        """
        if not parents:
            return []
        seqs = [list(self._class_chain(p)) for p in parents]
        seqs.append(list(parents))
        result = []
        while any(seqs):
            head = None
            for seq in seqs:
                candidate = seq[0]
                if not any(candidate in s[1:] for s in seqs):
                    head = candidate
                    break
            if head is None:
                raise ArabiRuntimeError(
                    f"لا يمكن بناء ترتيب الوراثة للصنف '{name}' — "
                    'تسلسل الأصول متناقض (وراثة معينية متعارضة)', line)
            result.append(head)
            seqs = [[x for x in seq if x is not head] for seq in seqs]
            seqs = [s for s in seqs if s]
        return result

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
                if node.except_binding:
                    env.define(node.except_binding,
                               self._error_binding_value(exc))
                self.exec_statements(node.except_body, env)
        finally:
            if node.finally_body is not None:
                self.exec_statements(node.finally_body, env)

    def _error_binding_value(self, exc):
        """القيمة المرتبطة بـ 'باستثناء هـ' — كائن الخطأ إن كان مخصصًا."""
        if isinstance(exc, ArabiUserError):
            return exc.instance
        if isinstance(exc, ArabiRuntimeError):
            return exc.message
        return str(exc)

    def exec_Raise(self, node, env):
        value = self.evaluate(node.value, env)
        if isinstance(value, ArabiRuntimeError):
            raise value
        if self._is_error_instance(value):
            raise ArabiUserError(value, node.line)
        if isinstance(value, str):
            raise ArabiRuntimeError(value, node.line)
        raise ArabiRuntimeError(display(value), node.line)

    def _is_error_instance(self, value):
        """صح إذا كان الكائن من الصنف المدمج 'استثناء' أو صنف يرثه."""
        if not isinstance(value, InstanceValue):
            return False
        for cls in self._class_chain(value.cls):
            if cls is self.error_class:
                return True
        return False

    def exec_Import(self, node, env):
        """تنفيذ الاستيراد بأصغاله الثلاثة."""
        module = self._resolve_module(node, env)
        if node.names is not None:
            # صيغة «من وحدة استورد أ، ب» — ربط الأسماء مباشرة
            for name in node.names:
                if name not in module.members:
                    available = '، '.join(sorted(module.members)) or 'لا شيء'
                    raise ArabiRuntimeError(
                        f"الوحدة '{module.name}' لا تحتوي على '{name}' "
                        f'— المتوفر: {available}', node.line)
                env.set(name, module.members[name])
            return
        env.set(node.bound_name, module)

    # ================== جمل الإصدار 1.5 ==================

    def exec_EnumDef(self, node, env):
        """تعريف تعداد: أعضاء بقيم تلقائية (١، ٢، ٣...) أو صريحة."""
        members = {}
        counter = 1
        for name, value_expr, line in node.members:
            if name in members:
                raise ArabiRuntimeError(
                    f"تكرار العضو '{name}' في التعداد '{node.name}'", line)
            if value_expr is not None:
                value = self.evaluate(value_expr, env)
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ArabiRuntimeError(
                        f"قيمة العضو '{name}' في التعداد يجب أن تكون عددًا صحيحًا",
                        line)
                counter = value
            members[name] = EnumMember(name, counter, node.name)
            counter += 1
        env.set(node.name, EnumValue(node.name, members))

    def exec_Global(self, node, env):
        """عالمي أسماء — التعيينات اللاحقة تذهب للنطاق العام."""
        for name in node.names:
            env.global_decls.add(name)

    def exec_Assert(self, node, env):
        """تحقق شرط، "رسالة" — يرفع خطأ إذا كان الشرط خطأ."""
        if not self._truthy(self.evaluate(node.test, env)):
            if node.message is not None:
                message = self.evaluate(node.message, env)
                raise ArabiRuntimeError(
                    f'فشل التحقق: {self._display(message)}', node.line)
            raise ArabiRuntimeError('فشل التحقق', node.line)

    def exec_Delete(self, node, env):
        """احذف اسمًا أو عنصرًا مفهرسًا أو خاصية كائن."""
        target = node.target
        if isinstance(target, N.Name):
            env.remove(target.name, target.line)
            return
        if isinstance(target, N.Index):
            obj = self.evaluate(target.obj, env)
            index = self.evaluate(target.index, env)
            self._delete_index(obj, index, target.line)
            return
        if isinstance(target, N.Attribute):
            obj = self.evaluate(target.obj, env)
            if isinstance(obj, InstanceValue):
                if target.name in obj.fields:
                    del obj.fields[target.name]
                    return
                raise ArabiRuntimeError(
                    f"الكائن لا يحتوي على الخاصية '{target.name}' لحذفها",
                    target.line)
            if isinstance(obj, dict) and target.name in obj:
                del obj[target.name]
                return
            raise ArabiRuntimeError(
                f"لا يمكن حذف '{target.name}' من {typename(obj)}", target.line)
        raise ArabiRuntimeError('هدف حذف غير صالح', node.line)

    def exec_Yield(self, node, env):
        """أنتج [تعبير] — يسلم القيمة للمستهلك ويوقف حتى الطلب التالي."""
        value = None if node.value is None else self.evaluate(node.value, env)
        gen = getattr(_gen_tls, 'gen', None)
        if gen is None:
            raise ArabiRuntimeError(
                "جملة 'أنتج' تُستخدم داخل مولد فقط — الدالة التي تحوي "
                "'أنتج' تعيد كائن مولد عند استدعائها ولا تُنفذ فورًا", node.line)
        gen._emit(value, node.line)

    def _delete_index(self, obj, index, line):
        if isinstance(obj, list):
            if isinstance(index, bool) or not isinstance(index, int):
                raise ArabiRuntimeError('فهرس القائمة يجب أن يكون عددًا صحيحًا', line)
            if not -len(obj) <= index < len(obj):
                raise ArabiRuntimeError(
                    f'الفهرس {index} خارج النطاق (طول القائمة {len(obj)})', line)
            del obj[index]
            return
        if isinstance(obj, dict):
            if index in obj:
                del obj[index]
                return
            raise ArabiRuntimeError(
                f"المفتاح '{display(index)}' غير موجود في القاموس", line)
        raise ArabiRuntimeError(f'لا يمكن الحذف بالفهرسة من {typename(obj)}', line)

    # ================== تحميل الوحدات من الملفات ==================

    def _resolve_module(self, node, env):
        """يبحث عن الوحدة ويحملها مرة واحدة ويخزنها في الذاكرة."""
        name = node.module or node.bound_name

        # ١) الوحدات الجاهزة المدمجة
        if node.module in BUILTIN_MODULES:
            return self.globals.vars[node.module]

        # ٢) تحديد مسارات البحث
        if node.path is not None:
            candidates = self._path_candidates(node.path)
        else:
            candidates = self._module_candidates(node.module)

        # ٣) البحث عن الملف
        for path in candidates:
            if os.path.isfile(path):
                return self._load_module_file(path, name, node.line)

        searched = '\n  '.join(candidates)
        raise ArabiRuntimeError(
            f"لم يتم العثور على الوحدة '{name}' — بحثت في:\n  {searched}",
            node.line)

    def _search_dirs(self):
        """مجلدات البحث عن الوحدات بالترتيب: البرنامج، الوحدة الحالية، ثم المجلد الحالي."""
        dirs = [self.script_dir]
        if self._module_stack:
            dirs.append(self._module_stack[-1])
        dirs.append(os.getcwd())
        seen = set()
        unique = []
        for d in dirs:
            d = os.path.abspath(d)
            if d not in seen:
                seen.add(d)
                unique.append(d)
        return unique

    def _module_candidates(self, name):
        """مواضع ملف الوحدة اسم.عربي في كل مجلدات البحث ومجلدا وحدات ومكتبات الفرعيان."""
        candidates = []
        for d in self._search_dirs():
            candidates.append(os.path.join(d, name + '.عربي'))
            candidates.append(os.path.join(d, 'وحدات', name + '.عربي'))
            candidates.append(os.path.join(d, 'مكتبات', name + '.عربي'))
        return candidates

    def _path_candidates(self, path):
        """مواضع مسار صريح: مطلق مباشرة، وإلا نسبي لمجلدات البحث."""
        if os.path.isabs(path):
            return [path]
        return [os.path.join(d, path) for d in self._search_dirs()]

    def _load_module_file(self, path, name, line):
        """يقرأ ملف .عربي وينفذه في بيئة مستقلة ويعيد ModuleValue."""
        path = os.path.abspath(path)
        if path in self._module_cache:            # محمّلة سابقًا — إعادة استخدام
            return self._module_cache[path]
        if path in self._loading:
            chain = ' ← '.join(
                os.path.basename(p) for p in list(self._loading) + [path])
            raise ArabiRuntimeError(
                f'استيراد دائري: {chain} — الوحدة لا تستطيع استيراد نفسها '
                'بشكل مباشر أو غير مباشر', line)
        try:
            with open(path, encoding='utf-8') as f:
                source = f.read()
        except UnicodeDecodeError:
            raise ArabiRuntimeError(
                f"ملف الوحدة '{path}' يجب أن يكون بترميز UTF-8", line)
        except OSError as exc:
            raise ArabiRuntimeError(
                f"لا يمكن قراءة ملف الوحدة '{path}': {exc}", line)

        self._loading.add(path)
        try:
            tokens = Lexer(source).tokenize()
            tree = Parser(tokens).parse()
            module_env = Env()
            install_builtins(module_env)
            builtin_names = set(module_env.vars)
            # الصنف المدمج 'استثناء' متاح داخل الوحدات (للوراثة) لكن لا يُصدَّر
            module_env.define('استثناء', self.error_class)
            builtin_names.add('استثناء')
            self._module_stack.append(os.path.dirname(path))
            try:
                self.exec_statements(tree.statements, module_env)
            finally:
                self._module_stack.pop()
            # الوحدة تصدّر ما عرّفه المستخدم فقط (وليس الجاهزات)
            members = {k: v for k, v in module_env.vars.items()
                       if k not in builtin_names}
        except ArabiRuntimeError as exc:
            if exc.line is not None:
                raise
            raise ArabiRuntimeError(
                f"خطأ داخل الوحدة '{name}': {exc.message}", line)
        finally:
            self._loading.discard(path)

        module = ModuleValue(name, members)
        self._module_cache[path] = module
        return module

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

    def eval_FString(self, node, env):
        """النص المنسق: ق"مرحبا {الاسم}، الناتج {أ + ب}" """
        out = []
        for kind, val in node.parts:
            if kind == 'str':
                out.append(val)
            else:
                out.append(self._display(self.evaluate(val, env)))
        return ''.join(out)

    def _display(self, value):
        """عرض قيمة مع احترام الطريقة الخاصة 'نص' للكائنات."""
        if isinstance(value, InstanceValue):
            func, _owner = self._lookup_member(value.cls, 'نص')
            if isinstance(func, ArabiFunc):
                result = self._invoke_bound(func, value, [], {}, None)
                if not isinstance(result, str):
                    raise ArabiRuntimeError(
                        "الطريقة الخاصة 'نص' يجب أن تعيد نصًا")
                return result
            # كائن خطأ مخصص يُعرض برسالته
            if self._is_error_instance(value):
                msg = value.fields.get('رسالة', '')
                msg = msg if isinstance(msg, str) else display(msg)
                return f'{value.cls.name}: {msg}' if msg else value.cls.name
        return display(value)

    def _call_special(self, instance, name, line):
        """يستدعي طريقة خاصة (طول/نص/...) على كائن إن وُجدت، وإلا يرفع خطأ."""
        func, _owner = self._lookup_member(instance.cls, name)
        if not isinstance(func, ArabiFunc):
            raise ArabiRuntimeError(
                f"الكائن من صنف '{instance.cls.name}' لا يعرّف '{name}'", line)
        return self._invoke_bound(func, instance, [], {}, line)

    def eval_Bool(self, node, env):
        return node.value

    def eval_Null(self, node, env):
        return None

    def _current_this(self, env):
        """يجد 'هذا' الحالي: من سلسلة النطاق ثم من مكدس الخيط."""
        scope = env
        while scope is not None:
            if 'هذا' in scope.vars:
                return scope.vars['هذا']
            scope = scope.parent
        stack = getattr(self._tls, 'this_stack', None)
        if stack:
            return stack[-1]
        return None

    def eval_This(self, node, env):
        this_val = self._current_this(env)
        if this_val is not None:
            return this_val
        raise ArabiRuntimeError(
            "لا يمكن استخدام 'هذا' إلا داخل طرق صنف", node.line)

    def eval_Super(self, node, env):
        scope = env
        while scope is not None:
            if 'الأصل' in scope.vars:
                value = scope.vars['الأصل']
                if value is None:
                    raise ArabiRuntimeError(
                        "هذا الصنف لا يرث من صنف آخر — لا يوجد 'الأصل'",
                        node.line)
                if isinstance(value, ClassValue):
                    # اربط الأصل بالكائن الحالي إن وُجد (الأصل.طريقة(...))
                    this_val = self._current_this(env)
                    if isinstance(this_val, InstanceValue):
                        return SuperValue(value, this_val)
                return value
            scope = scope.parent
        raise ArabiRuntimeError(
            "لا يمكن استخدام 'الأصل' إلا داخل جسم صنف", node.line)

    def eval_Name(self, node, env):
        return env.get(node.name, node.line)

    def eval_ListLit(self, node, env):
        result = []
        for item in node.items:
            if isinstance(item, N.SpreadArg):
                self._spread_into(result, self.evaluate(item.expr, env),
                                  item.line)
            else:
                result.append(self.evaluate(item, env))
        return result

    def _spread_into(self, target, value, line):
        """يفتّ القيمة القابلة للتكرار (قائمة/نص/مدى/مولد) في قائمة هدف."""
        if isinstance(value, list):
            target.extend(value)
        elif isinstance(value, str):
            target.extend(value)
        elif isinstance(value, range):
            target.extend(value)
        elif isinstance(value, GeneratorValue):
            while True:
                ok, item = value._next_pair()
                if not ok:
                    break
                target.append(item)
        else:
            raise ArabiRuntimeError(
                f'لا يمكن تفكيك {typename(value)} في قائمة — '
                'المتوقع قائمة أو نصًا أو مدى', line)

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
                # كائن يعرّف الطريقة الخاصة 'سالب'
                if isinstance(value, InstanceValue):
                    func, _owner = self._lookup_member(value.cls, 'سالب')
                    if isinstance(func, ArabiFunc):
                        return self._invoke_bound(func, value, [], {}, node.line)
                raise ArabiRuntimeError(
                    f'لا يمكن وضع سالب أمام {typename(value)}', node.line)
            return -value
        if node.op == 'ليس':
            return not self._truthy(value)
        raise ArabiRuntimeError(f"معامل أحادي غير معروف: {node.op}", node.line)

    def eval_Ternary(self, node, env):
        """التعبير الثلاثي: لو شرط: قيمة1 وإلا قيمة2"""
        if self._truthy(self.evaluate(node.test, env)):
            return self.evaluate(node.if_true, env)
        return self.evaluate(node.if_false, env)

    def eval_Call(self, node, env):
        func = self.evaluate(node.func, env)
        args, kwargs = self._evaluate_args(node.args, env)
        return self._call_value(func, args, kwargs, node.line)

    def _evaluate_args(self, arg_nodes, env):
        """يقيّم معاملات الاستدعاء ويفصل الموضعية عن المسماة.

        يدعم التفكيك: دالة(...قائمة) تفتّ العناصر كوسائط موضعية.
        """
        args = []
        kwargs = {}
        kw_started = False
        for name, expr in arg_nodes:
            if isinstance(expr, N.SpreadArg):
                value = self.evaluate(expr.expr, env)
                if kw_started:
                    raise ArabiRuntimeError(
                        'لا يمكن وضع تفكيك ... بعد معامل بالاسم',
                        getattr(expr, 'line', None))
                self._spread_into(args, value, getattr(expr, 'line', None))
                continue
            value = self.evaluate(expr, env)
            if name is None:
                if kw_started:
                    raise ArabiRuntimeError(
                        'لا يمكن وضع معامل موضعي بعد معامل بالاسم',
                        getattr(expr, 'line', None))
                args.append(value)
            else:
                if name in kwargs:
                    raise ArabiRuntimeError(
                        f"تكرار المعامل بالاسم '{name}' في الاستدعاء",
                        getattr(expr, 'line', None))
                kwargs[name] = value
                kw_started = True
        return args, kwargs

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
        args, kwargs = self._evaluate_args(node.args, env)
        name = node.name
        line = node.line
        # كائن من صنف معرف من قبل المستخدم
        if isinstance(obj, InstanceValue):
            if name in obj.fields:
                func = obj.fields[name]
                if isinstance(func, (ArabiFunc, BuiltinFunc)):
                    return self._call_value(func, args, kwargs, line)
                raise ArabiRuntimeError(
                    f"'{name}' خاصية من نوع {typename(func)} — لا يمكن استدعاؤها كدالة",
                    line)
            return self._call_class_method(obj.cls, obj, name, args, kwargs, line)
        # الأصل المرتبط بالكائن: الأصل.طريقة(...) — النمطان معًا مدعومان
        if isinstance(obj, SuperValue):
            args2 = args
            if args2 and args2[0] is obj.instance:
                args2 = args2[1:]      # النمط القديم: الأصل.طريقة(هذا، ...)
            return self._call_class_method(obj.cls, obj.instance, name,
                                           args2, kwargs, line)
        # استدعاء غير مرتبط من الصنف نفسه: الأصل.إنشاء(هذا، ...)
        # أو ربط تلقائي: الأصل.طريقة() داخل طريقة ترى 'هذا' الحالي
        if isinstance(obj, ClassValue):
            if not args and not kwargs:
                stack = getattr(self._tls, 'this_stack', None)
                if not stack:
                    raise ArabiRuntimeError(
                        f"استدعاء '{obj.name}.{name}' يحتاج الكائن كأول معامل",
                        line)
                return self._call_class_method(obj, stack[-1], name, [],
                                               kwargs, line)
            this_val = args[0]
            if not isinstance(this_val, InstanceValue):
                raise ArabiRuntimeError(
                    f"أول معامل في '{obj.name}.{name}' يجب أن يكون كائنًا", line)
            return self._call_class_method(obj, this_val, name, args[1:], kwargs, line)
        if isinstance(obj, ModuleValue):
            member = obj.members.get(name)
            if member is None:
                raise ArabiRuntimeError(
                    f"الوحدة '{obj.name}' لا تحتوي على '{name}'", line)
            if isinstance(member, (ArabiFunc, BuiltinFunc, ClassValue, BoundMethod)):
                return self._call_value(member, args, kwargs, line)
            raise ArabiRuntimeError(
                f"'{obj.name}.{name}' ثابت من نوع {typename(member)} وليس دالة — "
                'لا يمكن استدعاؤه', line)
        if isinstance(obj, list):
            table = LIST_METHODS
        elif isinstance(obj, str):
            table = STR_METHODS
        elif isinstance(obj, dict):
            table = DICT_METHODS
        elif isinstance(obj, GeneratorValue):
            table = GENERATOR_METHODS
        elif isinstance(obj, DBValue):
            table = DB_METHODS
        elif isinstance(obj, ThreadValue):
            table = THREAD_METHODS
        elif isinstance(obj, LockValue):
            table = LOCK_METHODS
        elif isinstance(obj, QueueValue):
            table = QUEUE_METHODS
        elif isinstance(obj, DateValue):
            table = DATE_METHODS
        else:
            raise ArabiRuntimeError(
                f"النوع '{typename(obj)}' لا يدعم الطرق — لا توجد طريقة اسمها '{name}'",
                line)
        method = table.get(name)
        if method is None:
            raise ArabiRuntimeError(
                f"لا توجد طريقة اسمها '{name}' للنوع {typename(obj)}", line)
        return method(obj, args, line)

    def eval_Lambda(self, node, env):
        """الدالة السهمية قيمة عند التقييم — تُنشئ ArabiFunc بجسم من سطر واحد."""
        params = [(name, self._eval_default(default, env))
                  for name, default in node.params]
        body = [N.Return(node.body, node.line)]
        return ArabiFunc('سهمية', params, body, env, is_lambda=True,
                         rest=node.rest)

    def eval_Attribute(self, node, env):
        obj = self.evaluate(node.obj, env)
        if isinstance(obj, EnumMember):
            if node.name == 'الاسم':
                return obj.name
            if node.name == 'القيمة':
                return obj.value
            raise ArabiRuntimeError(
                f"عضو التعداد لا يحتوي على '{node.name}' — المتوفر: الاسم، القيمة",
                node.line)
        if isinstance(obj, DateValue):
            method = DATE_METHODS.get(node.name)
            if method is None:
                raise ArabiRuntimeError(
                    f"التاريخ لا يحتوي على '{node.name}' — المتوفر: السنة، "
                    'الشهر، اليوم، الساعة، الدقيقة، الثانية، يوم_الأسبوع، نسق',
                    node.line)
            if node.name != 'نسق':                # الخصائص تُقرأ بلا أقواس
                return method(obj, [], node.line)
            # نسق طريقة تستدعى بأقواس — دالة جاهزة مرتبطة بهذا التاريخ
            def bound(args, line, _obj=obj, _m=method, _n=node.name):
                return _m(_obj, args, line)
            return BuiltinFunc(node.name, bound)
        if isinstance(obj, EnumValue):
            member = obj.members.get(node.name)
            if member is None:
                available = '، '.join(obj.members) or 'لا شيء'
                raise ArabiRuntimeError(
                    f"التعداد '{obj.name}' لا يحتوي على '{node.name}' — "
                    f'الأعضاء: {available}', node.line)
            return member
        if isinstance(obj, InstanceValue):
            if node.name in obj.fields:
                return obj.fields[node.name]
            member, _owner = self._lookup_member(obj.cls, node.name)
            if member is None:
                raise ArabiRuntimeError(
                    f"الكائن من صنف '{obj.cls.name}' لا يحتوي على '{node.name}'",
                    node.line)
            if isinstance(member, Property):
                return self._invoke_bound(member.func, obj, [], {}, node.line)
            if isinstance(member, ArabiFunc):
                return BoundMethod(obj, member)
            return member
        if isinstance(obj, SuperValue):
            member, _owner = self._lookup_member(obj.cls, node.name)
            if member is None:
                raise ArabiRuntimeError(
                    f"الصنف '{obj.cls.name}' لا يحتوي على '{node.name}'",
                    node.line)
            if isinstance(member, Property):
                return self._invoke_bound(member.func, obj.instance, [], {},
                                          node.line)
            if isinstance(member, ArabiFunc):
                return BoundMethod(obj.instance, member)
            return member
        if isinstance(obj, ClassValue):
            member, _owner = self._lookup_member(obj, node.name)
            if member is None:
                raise ArabiRuntimeError(
                    f"الصنف '{obj.name}' لا يحتوي على '{node.name}'", node.line)
            return member
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
        elif isinstance(target, N.Attribute):
            obj = self.evaluate(target.obj, env)
            if isinstance(obj, InstanceValue):
                obj.fields[target.name] = value
                return
            if isinstance(obj, ClassValue):
                raise ArabiRuntimeError(
                    "لا يمكن تعديل ثوابت الصنف بعد تعريفه", target.line)
            raise ArabiRuntimeError(
                f'لا يمكن تعيين خاصية على {typename(obj)}', target.line)
        else:
            raise ArabiRuntimeError('لا يمكن الإسناد إلى هذا التعبير', target.line)

    def _read_target(self, target, env):
        if isinstance(target, N.Name):
            return env.get(target.name, target.line)
        if isinstance(target, (N.Index, N.Attribute)):
            return self.evaluate(target, env)
        raise ArabiRuntimeError('تعبير غير صالح للإسناد المركب', target.line)

    def _set_index(self, obj, index, value, line):
        # كائن يعرّف الطريقة الخاصة 'عيّن_فهرس'
        if isinstance(obj, InstanceValue):
            func, _owner = self._lookup_member(obj.cls, 'عيّن_فهرس')
            if isinstance(func, ArabiFunc):
                self._invoke_bound(func, obj, [index, value], {}, line)
                return
            raise ArabiRuntimeError(
                f"الكائن من صنف '{obj.cls.name}' لا يدعم التعيين بالفهرسة — "
                "عرّف الطريقة الخاصة 'عيّن_فهرس'", line)
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
        # كائن يعرّف الطريقة الخاصة 'فهرس'
        if isinstance(obj, InstanceValue):
            func, _owner = self._lookup_member(obj.cls, 'فهرس')
            if isinstance(func, ArabiFunc):
                return self._invoke_bound(func, obj, [index], {}, line)
            raise ArabiRuntimeError(
                f"الكائن من صنف '{obj.cls.name}' لا يدعم الفهرسة — "
                "عرّف الطريقة الخاصة 'فهرس'", line)
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

    def _call_value(self, func, args, kwargs, line):
        if isinstance(func, ArabiFunc):
            local = self._bind_call_args(func, args, kwargs, line)
            if func.is_generator:
                return GeneratorValue(self, func, local)
            try:
                self.exec_statements(func.body, local)
            except ReturnSignal as signal:
                return signal.value
            return None
        if isinstance(func, BuiltinFunc):
            if kwargs:
                names = '، '.join(kwargs)
                raise ArabiRuntimeError(
                    f"الدالة الجاهزة '{func.name}' لا تقبل معاملات بالاسم "
                    f'(استلمت: {names})', line)
            if func.takes_interp:
                return func.fn(self, args, line)
            return func.fn(args, line)
        # إنشاء كائن: نقطة(٣، ٤)
        if isinstance(func, ClassValue):
            if func.is_interface:
                raise ArabiRuntimeError(
                    f"لا يمكن إنشاء كائن من الواجهة '{func.name}' — "
                    'الواجهة عقد تلتزم به الأصناف وليست تُنشأ مباشرة', line)
            missing = self._missing_abstract(func)
            if missing:
                details = '، '.join(
                    f"'{m}' من الواجهة '{w}'" for m, w in missing)
                raise ArabiRuntimeError(
                    f"لا يمكن إنشاء كائن من الصنف '{func.name}' — "
                    f'لم ينفذ الطرق المجردة: {details}', line)
            instance = InstanceValue(func)
            ctor, _owner = self._lookup_member(func, 'إنشاء')
            if isinstance(ctor, ArabiFunc):
                self._invoke_bound(ctor, instance, args, kwargs, line)
            elif isinstance(ctor, NativeCtor) and ctor.kind == 'خطأ':
                message = display(args[0]) if args else 'خطأ'
                instance.fields['رسالة'] = message
            return instance
        # طريقة مرتبطة كُلّمت لاحقًا: م = ك.طريقة ثم م()
        if isinstance(func, BoundMethod):
            return self._invoke_bound(func.func, func.instance, args, kwargs, line)
        raise ArabiRuntimeError(
            f"'{display(func)}' من نوع {typename(func)} — لا يمكن استدعاؤها كدالة", line)

    def _missing_abstract(self, cls):
        """يجمع الطرق المجردة غير المنفذة في سلسلة الصنف.

        يعيد قائمة (اسم الطريقة، اسم الواجهة) — فارغة إذا التزم الصنف.
        """
        chain = list(self._class_chain(cls))
        missing = []
        for scope in chain:
            if not scope.is_interface:
                continue
            for name in scope.abstract:
                # مُنفذة في أي حلقة من السلسلة؟ (الطرق المجردة ليست أعضاء)
                if not any(name in c.members for c in chain):
                    missing.append((name, scope.name))
        return missing

    def _bind_call_args(self, func, args, kwargs, line):
        """يربط معاملات الاستدعاء (موضعية وبالاسم و...المتغير) بالمعاملات الرسمية.

        يعيد بيئة محلية جاهزة للتنفيذ، ويرفع أخطاء عربية واضحة عند:
        نقص معامل إجباري، زيادة معاملات، اسم غير معروف، أو تكرار إرسال قيمة.
        """
        params = func.params                      # [(الاسم، الافتراضي)، ...]
        rest_name = getattr(func, 'rest', None)
        local = Env(func.env)
        bound = {}
        rest_values = []

        # ١) المعاملات الموضعية بالترتيب، وما زاد يجمعه المتغير ...
        for i, value in enumerate(args):
            if i >= len(params):
                if rest_name is None:
                    raise ArabiRuntimeError(
                        self._arity_message(func, len(params), len(args),
                                            kwargs), line)
                rest_values.append(value)
                continue
            bound[params[i][0]] = value

        # ٢) المعاملات بالاسم
        for name, value in kwargs.items():
            if rest_name is not None and name == rest_name:
                raise ArabiRuntimeError(
                    f"المعامل المتغير '{rest_name}' يجمع الوسائط تلقائيًا — "
                    'لا تُرسله بالاسم', line)
            if not any(p[0] == name for p in params):
                raise ArabiRuntimeError(
                    f"'{func.name}' لا تحتوي على معامل بالاسم '{name}' — "
                    f"المعاملات: {self._params_list(params, rest_name)}", line)
            if name in bound:
                raise ArabiRuntimeError(
                    f"المعامل '{name}' أُرسل مرتين في '{func.name}' "
                    '(موضعيًا وبالاسم)', line)
            bound[name] = value

        # ٣) الافتراضيات للمتبقي، وكشف الناقص
        for name, default in params:
            if name in bound:
                continue
            if default is NO_DEFAULT:
                raise ArabiRuntimeError(
                    f"'{func.name}' تحتاج قيمة للمعامل '{name}' — "
                    'أرسلها موضعيًا أو بالاسم', line)
            bound[name] = default

        for name, _default in params:
            local.define(name, bound[name])
        if rest_name is not None:
            local.define(rest_name, rest_values)
        return local

    def _arity_message(self, func, n_params, n_args, kwargs):
        if getattr(func, 'rest', None) is not None:
            required = sum(1 for _name, default in func.params
                           if default is NO_DEFAULT)
            return (f"'{func.name}' تتوقع {required} معاملًا إجباريًا "
                    'على الأقل لكنها استلمت شيئًا بالاسم غير مطابق')
        required = sum(1 for _name, default in func.params
                       if default is NO_DEFAULT)
        got = n_args + len(kwargs)
        if got > n_params:
            return (f"'{func.name}' تقبل {n_params} معاملًا كحد أقصى "
                    f'لكنها استلمت {got}')
        return (f"'{func.name}' تتوقع {required} معاملًا إجباريًا "
                f'لكنها استلمت {got}')

    def _params_list(self, params, rest=None):
        names = [p[0] for p in params]
        if rest is not None:
            names.append('...' + rest)
        return '، '.join(names) or 'لا معاملات'

    # ================== أدوات الأصناف ==================

    def _lookup_member(self, cls, name):
        """يبحث عن عضو في سلسلة الصنف (MRO للوراثة المتعددة) ويعيد (العضو، الصنف المالك)."""
        for scope in self._class_chain(cls):
            if name in scope.members:
                return scope.members[name], scope
        return None, None

    def _invoke_bound(self, func, this_val, args, kwargs, line):
        """ينفذ طريقة مع ربط 'هذا' بالكائن الممرر.

        يدفع 'هذا' على مكدس الخيط الحالي لتصله الدوال المستدعاة منه.
        """
        local = self._bind_call_args(func, args, kwargs, line)
        local.define('هذا', this_val)
        stack = getattr(self._tls, 'this_stack', None)
        if stack is None:
            stack = []
            self._tls.this_stack = stack
        stack.append(this_val)
        try:
            if func.is_generator:
                return GeneratorValue(self, func, local)
            try:
                self.exec_statements(func.body, local)
            except ReturnSignal as signal:
                return signal.value
            return None
        finally:
            stack.pop()

    def _call_class_method(self, cls, instance, name, args, kwargs, line):
        """يبحث عن الطريقة في سلسلة الصنف وينفذها مرتبطة بالكائن."""
        func, owner = self._lookup_member(cls, name)
        if func is None:
            raise ArabiRuntimeError(
                f"الصنف '{cls.name}' لا يحتوي على طريقة أو خاصية اسمها '{name}'",
                line)
        if isinstance(func, Property):
            raise ArabiRuntimeError(
                f"'{name}' خاصية محسوبة في الصنف '{owner.name}' — "
                'تُقرأ بلا أقواس ولا تُستدعى كدالة', line)
        if isinstance(func, NativeCtor):
            if owner is self.error_class and func.kind == 'خطأ':
                message = display(args[0]) if args else 'خطأ'
                instance.fields['رسالة'] = message
                return None
            raise ArabiRuntimeError(
                f"'{owner.name}.{name}' مُنشئ أصلي غير قابل للاستدعاء هنا", line)
        if not isinstance(func, ArabiFunc):
            raise ArabiRuntimeError(
                f"'{name}' في الصنف '{owner.name}' ثابت وليس طريقة", line)
        return self._invoke_bound(func, instance, args, kwargs, line)

    def _binop(self, op, left, right, line):
        # تحميل العوامل على الكائنات (اجمع، اطرح، اضرب...)
        overloaded = self._try_overload(op, left, right, line)
        if overloaded is not _SKIP:
            return overloaded
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

    def _try_overload(self, op, left, right, line):
        """يجرب الطرق الخاصة للعوامل على الكائنات (يسارًا ثم يمينًا).

        يعيد _SKIP إذا لم يجد طريقة مناسبة ليكمل المسار الأصلي.
        """
        method_name = OVERLOAD_METHODS.get(op)
        if method_name is None:
            return _SKIP
        for operand, other in ((left, right), (right, left)):
            if isinstance(operand, InstanceValue):
                func, _owner = self._lookup_member(operand.cls, method_name)
                if isinstance(func, ArabiFunc):
                    return self._invoke_bound(func, operand, [other], {}, line)
        return _SKIP

    def _is_number(self, v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    def _both_numbers(self, left, right, op, line):
        if not self._is_number(left) or not self._is_number(right):
            raise ArabiRuntimeError(
                f"المعامل '{op}' يحتاج عددين لكن استلم {typename(left)} و {typename(right)}",
                line)

    def _values_equal(self, left, right):
        # كائن يعرّف الطريقة الخاصة 'يساوي'
        if isinstance(left, InstanceValue):
            func, _owner = self._lookup_member(left.cls, 'يساوي')
            if isinstance(func, ArabiFunc):
                return bool(self._invoke_bound(func, left, [right], {}, None))
        if isinstance(right, InstanceValue):
            func, _owner = self._lookup_member(right.cls, 'يساوي')
            if isinstance(func, ArabiFunc):
                return bool(self._invoke_bound(func, right, [left], {}, None))
        return left == right

    def _membership(self, left, right, line):
        # كائن يعرّف الطريقة الخاصة 'يحتوي'
        if isinstance(right, InstanceValue):
            func, _owner = self._lookup_member(right.cls, 'يحتوي')
            if isinstance(func, ArabiFunc):
                return bool(self._invoke_bound(func, right, [left], {}, line))
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
