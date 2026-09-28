# -*- coding: utf-8 -*-
"""أدوات النظام البيئي للغة عربي — الإصدار 1.6.

تشمل:
- format_source  : منسق الكود — إصلاح الإزاحة والتبويب والمسافات الزائدة
- lint_source    : الفاحص — كشف المشكلات قبل التشغيل (متغيرات غير مستخدمة،
                   كود غير قابل للوصول، أسماء غير معرفة، ...)
- generate_docs  : مولد التوثيق — استخراج الدوال والأصناف والتعدادات إلى Markdown
- install_package: مدير الحزم — تثبيت مكتبة .عربي من مسار محلي أو رابط
- list_packages  : عرض المكتبات المثبتة في مجلد مكتبات/
"""

import os
import re
import urllib.parse
import urllib.request

from .errors import ArabiError
from .lexer import Lexer
from .parser import Parser
from .tokens import T
from . import nodes as N


def _quote_url(url):
    """يرمز حروف الرابط غير الآسكية (عربية مثلاً) بترميز النسبة —
    فسطر طلب HTTP لا يقبل إلا آسكي، والرموز والترميزات القائمة تبقى
    (تطابق حارس packages._quote_url — تقرير التدقيق م11)."""
    return urllib.parse.quote(url, safe=";/?:@&=+$,~*'()#%![]")

INDENT_UNIT = '    '

_OPENERS = (T.LPAREN, T.LBRACKET, T.LBRACE)
_CLOSERS = (T.RPAREN, T.RBRACKET, T.RBRACE)


# ================== المنسق ==================

def _leading_ws(line):
    m = re.match(r'^[ \t]*', line)
    return m.group(0), m.end()


def _tabs_to_spaces(line):
    """يحول التبويبات في بداية السطر إلى ٤ مسافات لكل توقف تبويب."""
    lead, end = _leading_ws(line)
    width = 0
    out = []
    for c in lead:
        if c == '\t':
            w = 4 - (width % 4)
            out.append(' ' * w)
            width += w
        else:
            out.append(' ')
            width += 1
    return ''.join(out) + line[end:]


def _analyze_lines(tokens):
    """يستخرج من تدفق الرموز: عمق كل سطر، أسطر استكمال الأقواس،
    وامتداد النصوص متعددة الأسطر."""
    line_depth = {}       # رقم السطر (١-مبني) ← العمق المنطقي
    continuation = set()  # أسطر تكمّل قوسًا مفتوحًا — لا يُعاد إزاحتها
    string_span = {}      # سطر بداية النص الممتد ← عدد أسطره الإضافية

    depth = 0
    bracket_depth = 0
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        ttype = tok.type
        if ttype in (T.NEWLINE, T.INDENT, T.DEDENT, T.EOF):
            if ttype == T.INDENT:
                depth += 1
            elif ttype == T.DEDENT:
                depth -= 1
            i += 1
            continue
        # أول رمز حقيقي في السطر — امسح بقية رموز السطر نفسه
        open_before = bracket_depth
        j = i
        while j < len(tokens) and tokens[j].line == tok.line \
                and tokens[j].type not in (T.NEWLINE, T.EOF):
            tj = tokens[j]
            if tj.type in (T.STRING, T.FSTRING) and isinstance(tj.value, str) \
                    and '\n' in tj.value:
                # النص الممتد: سطر البداية ← عدد أسطره الداخلية
                string_span[tj.line] = tj.value.count('\n')
            if tj.type in _OPENERS:
                bracket_depth += 1
            elif tj.type in _CLOSERS:
                bracket_depth -= 1
            j += 1
        line_depth[tok.line] = depth
        if open_before > 0 and bracket_depth > 0:
            continuation.add(tok.line)
        i = j
    return line_depth, continuation, string_span


def _in_string_span(string_span, lineno):
    for start, extra in string_span.items():
        if start < lineno <= start + extra:
            return True
    return False


def format_source(source):
    """ينسق كود لغة عربي ويعيد (النص المنسق، عدد الأسطر المعدلة).

    يعمل على مستوى الرموز اللفظية فيصلح التبويب والإزاحة حتى في الملفات
    غير السليمة بنيويًا. وإذا كان الأصل سليمًا صياغيًا فيضمن أن الناتج
    يظل سليمًا تمامًا (فحص صرامة نهائي).
    """
    tokens = Lexer(source, lenient_indent=True).tokenize()

    try:
        Parser(Lexer(source).tokenize()).parse()
        valid_original = True
    except ArabiError:
        valid_original = False          # ملف معطوب أصلًا — تنسيق بأفضل جهد

    src = source.replace('\r\n', '\n').replace('\r', '\n')
    if not src.endswith('\n'):
        src += '\n'
    lines = src.split('\n')[:-1]

    line_depth, continuation, string_span = _analyze_lines(tokens)

    result = []
    changed = 0
    prev_blank = False
    for idx, line in enumerate(lines):
        lineno = idx + 1
        if _in_string_span(string_span, lineno):
            result.append(line)                # داخل نص متعدد الأسطر — كما هو
            prev_blank = False
            continue
        stripped = line.strip()
        if not stripped:
            # ضغط الأسطر الفارغة المتتالية إلى سطر واحد
            if prev_blank:
                changed += 1
                continue
            if line != '':
                changed += 1
            result.append('')
            prev_blank = True
            continue
        prev_blank = False
        if lineno in continuation:
            new = _tabs_to_spaces(line).rstrip()
        elif stripped.startswith('#'):
            new = _tabs_to_spaces(line).rstrip()
        else:
            d = line_depth.get(lineno, 0)
            new = INDENT_UNIT * d + stripped
        if new != line:
            changed += 1
        result.append(new)

    text = '\n'.join(result) + '\n'
    # شبكة أمان: الأصل السليم يجب أن يظل ناتجه سليمًا تمامًا
    if valid_original:
        Parser(Lexer(text).tokenize()).parse()
    return text, changed


# ================== الفاحص ==================

class _Scope:
    """نطاق تحليلي لتتبع التعريفات والاستخدام."""

    def __init__(self, parent=None, kind='module'):
        self.parent = parent
        self.kind = kind             # module | function | class
        self.defs = {}               # الاسم ← (السطر، النوع)
        self.used = set()

    def define(self, name, line, kind):
        if name not in self.defs:
            self.defs[name] = (line, kind)

    def find(self, name):
        scope = self
        while scope is not None:
            if name in scope.defs:
                return scope
            scope = scope.parent
        return None

    def mark_use(self, name):
        scope = self.find(name)
        target = scope if scope is not None else self
        target.used.add(name)


def _builtin_names():
    """أسماء الجاهزات والوحدات المدمجة (محسوبة من المفسر نفسه)."""
    from .interpreter import Interpreter
    names = set(Interpreter().globals.vars.keys())
    names.add('استثناء')
    return frozenset(names)


class _Linter:
    """ماسح شجرة الصياغة بحثًا عن المشكلات الشائعة."""

    def __init__(self, tree, builtins):
        self.tree = tree
        self.builtins = builtins
        self.issues = []             # (السطر، النوع، الرسالة)
        self.scopes = []

    def report(self, line, kind, msg):
        self.issues.append((line or 0, kind, msg))

    # ---------- التشغيل ----------

    def run(self):
        module = _Scope(kind='module')
        self.scopes.append(module)
        self._register_block(self.tree.statements, module)
        self._walk_block(self.tree.statements, module,
                         in_function=False, loop_depth=0)
        self._report_unused(module)
        self.issues.sort(key=lambda x: x[0])
        return self.issues

    # ---------- تسجيل التعريفات (المرحلة ١) ----------

    def _register_block(self, stmts, scope):
        for stmt in stmts:
            self._register_stmt(stmt, scope)

    def _register_stmt(self, stmt, scope):
        if isinstance(stmt, N.FuncDef):
            self._define(scope, stmt.name, stmt.line, 'دالة')
        elif isinstance(stmt, N.ClassDef):
            self._define(scope, stmt.name, stmt.line, 'صنف')
        elif isinstance(stmt, N.InterfaceDef):
            self._define(scope, stmt.name, stmt.line, 'واجهة')
        elif isinstance(stmt, N.EnumDef):
            self._define(scope, stmt.name, stmt.line, 'تعداد')
        elif isinstance(stmt, N.Import):
            if stmt.names is not None:
                # صيغة «من...استورد»: المرتبط فعليًا هو الأسماء المستوردة فقط
                for name in stmt.names:
                    self._define(scope, name, stmt.line, 'استيراد')
            elif stmt.bound_name:
                self._define(scope, stmt.bound_name, stmt.line, 'استيراد')
        elif isinstance(stmt, N.Assign):
            for target in stmt.targets:
                self._register_target(target, scope)
        elif isinstance(stmt, N.AugAssign):
            if isinstance(stmt.target, N.Name):
                self._assign_name(stmt.target.name, scope, stmt.line)
        elif isinstance(stmt, N.For):
            for target in stmt.targets:
                # أهداف الحلقة نصوص (من expect_ident) وليست عقد Name
                self._define(scope, target, stmt.line, 'متغير')
            self._register_block(stmt.body, scope)
        elif isinstance(stmt, N.Try):
            self._register_block(stmt.body, scope)
            for _flt, _binding, _cbody in stmt.clauses:
                if _binding:
                    self._define(scope, _binding, stmt.line, 'ربط')
                self._register_block(_cbody, scope)
            if stmt.finally_body:
                self._register_block(stmt.finally_body, scope)
        elif isinstance(stmt, N.Global):
            root = scope
            while root.parent is not None:
                root = root.parent
            for name in stmt.names:
                self._define(root, name, stmt.line, 'متغير')
        elif isinstance(stmt, N.If):
            self._register_block(stmt.body, scope)
            for _test, body in stmt.elifs:
                self._register_block(body, scope)
            if stmt.orelse:
                self._register_block(stmt.orelse, scope)
        elif isinstance(stmt, N.While):
            self._register_block(stmt.body, scope)
        elif isinstance(stmt, N.Switch):
            for _value, body in stmt.cases:
                self._register_block(body, scope)
            if stmt.default_body:
                self._register_block(stmt.default_body, scope)
        elif isinstance(stmt, N.Match):
            for pattern, _guard, body in stmt.cases:
                self._register_pattern(pattern, scope)
                self._register_block(body, scope)
            if stmt.default_body:
                self._register_block(stmt.default_body, scope)

    def _register_pattern(self, pat, scope):
        """يسجل أسماء الالتقاط في النمط حتى لا تُعد غير معرفة."""
        if isinstance(pat, N.PLiteral):
            return                      # تعبير قيمة — يُمشى في المرحلة الثانية
        if isinstance(pat, N.PCapture):
            if pat.name is not None:
                self._define(scope, pat.name, pat.line, 'متغير')
        elif isinstance(pat, N.POr):
            for sub in pat.patterns:
                self._register_pattern(sub, scope)
        elif isinstance(pat, N.PList):
            for item in pat.items:
                self._register_pattern(item, scope)
            if isinstance(pat.rest, str):
                self._define(scope, pat.rest, pat.line, 'متغير')
        elif isinstance(pat, N.PDict):
            for sub in pat.patterns:
                self._register_pattern(sub, scope)

    def _walk_pattern(self, pat, scope):
        """يمشي على تعبيرات النمط (أنماط القيمة) ويعلم الالتقاط مستخدمة."""
        if isinstance(pat, N.PLiteral):
            self._walk_expr(pat.expr, scope)
        elif isinstance(pat, N.PCapture):
            if pat.name is not None:
                scope.mark_use(pat.name)
        elif isinstance(pat, N.POr):
            for sub in pat.patterns:
                self._walk_pattern(sub, scope)
        elif isinstance(pat, N.PList):
            for item in pat.items:
                self._walk_pattern(item, scope)
            if isinstance(pat.rest, str):
                scope.mark_use(pat.rest)
        elif isinstance(pat, N.PDict):
            for key, sub in zip(pat.keys, pat.patterns):
                self._walk_expr(key, scope)
                self._walk_pattern(sub, scope)

    def _assign_name(self, name, scope, line):
        """دلالات الإسناد في عربي: إن وُجد الاسم في نطاق خارجي فيُعدّل
        هناك (يحسب استخدامًا)، وإلا يُعرّف محليًا."""
        found = scope.find(name)
        if found is not None:
            found.used.add(name)
        else:
            self._define(scope, name, line, 'متغير')

    def _register_target(self, target, scope):
        if isinstance(target, N.Name):
            self._assign_name(target.name, scope, target.line)

    def _define(self, scope, name, line, kind):
        # التظليل يُحذَّر للمتغيرات فقط — تسمية دالة/صنف بكلمة شائعة أمر طبيعي
        if name in self.builtins and kind == 'متغير':
            self.report(line, 'تحذير',
                        f"الاسم '{name}' يظلّل دالة/وحدة جاهزة للغة")
        scope.define(name, line, kind)

    # ---------- المشي والفحص (المرحلة ٢) ----------

    def _walk_block(self, stmts, scope, in_function, loop_depth):
        for stmt in stmts:
            self._walk_stmt(stmt, scope, in_function, loop_depth)
        # كشف الكود غير القابل للوصول: جملة إنهاء يليها كود
        for idx, stmt in enumerate(stmts):
            if isinstance(stmt, (N.Return, N.Break, N.Continue, N.Raise)):
                if idx + 1 < len(stmts):
                    after = stmts[idx + 1]
                    self.report(after.line, 'تحذير',
                                'كود غير قابل للوصول — يأتي بعد جملة إنهاء '
                                '(أعد/كسر/استمر/ارفع)')
                break

    def _walk_method(self, method, class_scope, outer_scope):
        """يمشي جسم طريقة صنف/واجهة بنطاقها الخاص."""
        for name, default in method.params:
            if default is not None:
                self._walk_expr(default, outer_scope)
        fn_scope = _Scope(parent=class_scope, kind='function')
        self.scopes.append(fn_scope)
        for pname, _d in method.params:
            fn_scope.define(pname, method.line, 'معامل')
        if method.rest is not None:
            fn_scope.define(method.rest, method.line, 'معامل')
        self._register_block(method.body, fn_scope)
        self._walk_block(method.body, fn_scope,
                         in_function=True, loop_depth=0)
        self._report_unused(fn_scope)

    def _walk_stmt(self, stmt, scope, in_function, loop_depth):
        if isinstance(stmt, N.ExprStmt):
            self._walk_expr(stmt.expr, scope)
        elif isinstance(stmt, N.Assign):
            self._walk_expr(stmt.value, scope)
            for target in stmt.targets:
                self._walk_target_read(target, scope)
        elif isinstance(stmt, N.AugAssign):
            self._walk_expr(stmt.value, scope)
            if isinstance(stmt.target, N.Name):
                scope.mark_use(stmt.target.name)
            else:
                self._walk_target_read(stmt.target, scope)
        elif isinstance(stmt, N.If):
            self._walk_expr(stmt.test, scope)
            self._walk_block(stmt.body, scope, in_function, loop_depth)
            for test, body in stmt.elifs:
                self._walk_expr(test, scope)
                self._walk_block(body, scope, in_function, loop_depth)
            if stmt.orelse:
                self._walk_block(stmt.orelse, scope, in_function, loop_depth)
        elif isinstance(stmt, N.While):
            self._walk_expr(stmt.test, scope)
            self._walk_block(stmt.body, scope, in_function, loop_depth + 1)
        elif isinstance(stmt, N.For):
            self._walk_expr(stmt.iterable, scope)
            self._walk_block(stmt.body, scope, in_function, loop_depth + 1)
        elif isinstance(stmt, N.FuncDef):
            seen_params = set()
            for name, default in stmt.params:
                if default is not None:
                    self._walk_expr(default, scope)
                if name in seen_params:
                    self.report(stmt.line, 'تحذير',
                                f"المعامل '{name}' مكرر في تعريف الدالة")
                seen_params.add(name)
            if stmt.rest is not None and stmt.rest in seen_params:
                self.report(stmt.line, 'خطأ',
                            f"اسم المعامل المتغير '{stmt.rest}' مكرر مع معامل عادي")
            child = _Scope(parent=scope, kind='function')
            self.scopes.append(child)
            for name, _default in stmt.params:
                child.define(name, stmt.line, 'معامل')
            if stmt.rest is not None:
                child.define(stmt.rest, stmt.line, 'معامل')
            self._register_block(stmt.body, child)
            self._walk_block(stmt.body, child, in_function=True, loop_depth=0)
            self._report_unused(child)
        elif isinstance(stmt, N.Return):
            if not in_function:
                self.report(stmt.line, 'خطأ', "جملة 'أعد' خارج الدالة")
            if stmt.value is not None:
                self._walk_expr(stmt.value, scope)
        elif isinstance(stmt, N.Break):
            if loop_depth == 0:
                self.report(stmt.line, 'خطأ', "جملة 'كسر' خارج حلقة")
        elif isinstance(stmt, N.Continue):
            if loop_depth == 0:
                self.report(stmt.line, 'خطأ', "جملة 'استمر' خارج حلقة")
        elif isinstance(stmt, N.Try):
            self._walk_block(stmt.body, scope, in_function, loop_depth)
            for _flt, _binding, _cbody in stmt.clauses:
                self._walk_block(_cbody, scope, in_function, loop_depth)
            if stmt.finally_body:
                self._walk_block(stmt.finally_body, scope, in_function,
                                 loop_depth)
        elif isinstance(stmt, N.Raise):
            if stmt.value is not None:
                self._walk_expr(stmt.value, scope)
        elif isinstance(stmt, N.ClassDef):
            child = _Scope(parent=scope, kind='class')
            self.scopes.append(child)
            for m in stmt.body:
                if isinstance(m, N.FuncDef):
                    child.define(m.name, m.line, 'طريقة')
                elif isinstance(m, N.Assign):
                    for target in m.targets:
                        if isinstance(target, N.Name):
                            child.define(target.name, m.line, 'ثابت صنف')
                elif isinstance(m, N.PropertyDef):
                    child.define(m.name, m.line, 'خاصية')
            for m in stmt.body:
                if isinstance(m, N.FuncDef):
                    self._walk_method(m, child, scope)
                elif isinstance(m, N.Assign):
                    self._walk_expr(m.value, scope)
                elif isinstance(m, N.PropertyDef):
                    p_scope = _Scope(parent=child, kind='function')
                    self.scopes.append(p_scope)
                    self._register_block(m.body, p_scope)
                    self._walk_block(m.body, p_scope,
                                     in_function=True, loop_depth=0)
        elif isinstance(stmt, N.InterfaceDef):
            child = _Scope(parent=scope, kind='class')
            self.scopes.append(child)
            for m in stmt.body:
                if isinstance(m, N.FuncDef):
                    child.define(m.name, m.line,
                                 'طريقة مجردة' if m.body is None else 'طريقة')
                elif isinstance(m, N.Assign):
                    for target in m.targets:
                        if isinstance(target, N.Name):
                            child.define(target.name, m.line, 'ثابت واجهة')
            for m in stmt.body:
                if isinstance(m, N.FuncDef) and m.body is not None:
                    self._walk_method(m, child, scope)
                elif isinstance(m, N.Assign):
                    self._walk_expr(m.value, scope)
        elif isinstance(stmt, N.Switch):
            self._walk_expr(stmt.subject, scope)
            for value, body in stmt.cases:
                self._walk_expr(value, scope)
                self._walk_block(body, scope, in_function, loop_depth)
            if stmt.default_body:
                self._walk_block(stmt.default_body, scope, in_function,
                                 loop_depth)
        elif isinstance(stmt, N.Match):
            self._walk_expr(stmt.subject, scope)
            for pattern, guard, body in stmt.cases:
                self._walk_pattern(pattern, scope)
                if guard is not None:
                    self._walk_expr(guard, scope)
                self._walk_block(body, scope, in_function, loop_depth)
            if stmt.default_body:
                self._walk_block(stmt.default_body, scope, in_function,
                                 loop_depth)
        elif isinstance(stmt, N.EnumDef):
            for member in stmt.members:
                value = member[1]
                if value is not None:
                    self._walk_expr(value, scope)
        elif isinstance(stmt, N.Global):
            root = scope
            while root.parent is not None:
                root = root.parent
            for name in stmt.names:
                root.mark_use(name)
        elif isinstance(stmt, N.Assert):
            self._walk_expr(stmt.test, scope)
            if stmt.message is not None:
                self._walk_expr(stmt.message, scope)
        elif isinstance(stmt, N.Delete):
            if isinstance(stmt.target, N.Name):
                scope.mark_use(stmt.target.name)
            else:
                self._walk_target_read(stmt.target, scope)
        elif isinstance(stmt, N.Yield):
            if not in_function:
                self.report(stmt.line, 'خطأ', "جملة 'أنتج' خارج الدالة")
            if stmt.value is not None:
                self._walk_expr(stmt.value, scope)
        # Pass: لا شيء

    def _walk_target_read(self, target, scope):
        """يمشي على هدف إسناد غير الاسم (فهرسة/خاصية) — قراءةً للكائن الحامل."""
        if isinstance(target, N.Index):
            self._walk_expr(target.obj, scope)
            self._walk_expr(target.index, scope)
        elif isinstance(target, N.Attribute):
            self._walk_expr(target.obj, scope)

    def _walk_expr(self, expr, scope):
        if expr is None:
            return
        if isinstance(expr, N.Name):
            if scope.find(expr.name) is not None:
                scope.mark_use(expr.name)
            elif expr.name in self.builtins:
                pass
            else:
                self.report(expr.line, 'تحذير',
                            f"الاسم '{expr.name}' غير معرّف — قد يسبب خطأ تشغيل")
        elif isinstance(expr, N.BinOp):
            self._walk_expr(expr.left, scope)
            self._walk_expr(expr.right, scope)
        elif isinstance(expr, N.UnaryOp):
            self._walk_expr(expr.operand, scope)
        elif isinstance(expr, N.Await):
            self._walk_expr(expr.operand, scope)
        elif isinstance(expr, N.Call):
            self._walk_expr(expr.func, scope)
            for _name, arg in expr.args:
                self._walk_expr(arg, scope)
        elif isinstance(expr, N.Index):
            self._walk_expr(expr.obj, scope)
            self._walk_expr(expr.index, scope)
        elif isinstance(expr, N.Slice):
            self._walk_expr(expr.obj, scope)
            for part in (expr.start, expr.stop, expr.step):
                self._walk_expr(part, scope)
        elif isinstance(expr, N.MethodCall):
            self._walk_expr(expr.obj, scope)
            for _name, arg in expr.args:
                self._walk_expr(arg, scope)
        elif isinstance(expr, N.Attribute):
            self._walk_expr(expr.obj, scope)
        elif isinstance(expr, N.ListLit):
            for item in expr.items:
                self._walk_expr(item, scope)
        elif isinstance(expr, N.SpreadArg):
            self._walk_expr(expr.expr, scope)
        elif isinstance(expr, N.DictLit):
            for k, v in zip(expr.keys, expr.values):
                self._walk_expr(k, scope)
                self._walk_expr(v, scope)
        elif isinstance(expr, N.FString):
            for kind, part in expr.parts:
                if kind == 'expr':
                    self._walk_expr(part, scope)
        elif isinstance(expr, N.Ternary):
            self._walk_expr(expr.test, scope)
            self._walk_expr(expr.if_true, scope)
            self._walk_expr(expr.if_false, scope)
        elif isinstance(expr, N.Lambda):
            child = _Scope(parent=scope, kind='function')
            self.scopes.append(child)
            for name, default in expr.params:
                if default is not None:
                    self._walk_expr(default, scope)
                child.define(name, expr.line, 'معامل')
            if expr.rest is not None:
                child.define(expr.rest, expr.line, 'معامل')
            self._walk_expr(expr.body, child)
        elif isinstance(expr, (N.ListComp, N.DictComp)):
            # فهم قائمة/قاموس: أهداف العبارات نطاق مستقل لا يسرّب للخارج
            child = _Scope(parent=scope, kind='block')
            self.scopes.append(child)
            for targets, iterable, cond in expr.clauses:
                # المتتالية قبل تعريف الأهداف (لا رؤية ذاتية) —
                # وعبارات 'لكل' التالية ترى أهداف العبارة السابقة
                self._walk_expr(iterable, child)
                for t in targets:
                    child.define(t, expr.line, 'متغير')
                if cond is not None:
                    self._walk_expr(cond, child)
            if isinstance(expr, N.ListComp):
                self._walk_expr(expr.elt, child)
            else:
                self._walk_expr(expr.key, child)
                self._walk_expr(expr.value, child)
        # Num / Str / Bool / Null / This / Super: لا شيء

    # ---------- تقرير غير المستخدم ----------

    def _report_unused(self, scope):
        if scope.kind == 'class':
            return                      # أعضاء الصنف تُستخدم عبر الكائنات
        used = getattr(scope, 'used', set())
        labels = {'متغير': "المتغير '{n}' معرّف لكنه غير مستخدم",
                  'معامل': "المعامل '{n}' مستلم لكنه غير مستخدم",
                  'استيراد': "الاستيراد '{n}' غير مستخدم"}
        for name, (line, kind) in scope.defs.items():
            if name in used or name.startswith('_'):
                continue
            if scope.kind == 'module' and kind in ('دالة', 'صنف', 'تعداد'):
                continue                # تصديرات الوحدة
            template = labels.get(kind)
            if template:
                self.report(line, 'تحذير', template.format(n=name))


def lint_source(source):
    """يفحص مصدر لغة عربي ويعيد قائمة (السطر، النوع، الرسالة).

    النوع 'خطأ' يعني مشكلة مؤكدة، و'تحذير' مشكلة محتملة.
    إذا كانت الصياغة غير سليمة يعيد فحصًا واحدًا بخطأ التحليل نفسه.
    """
    try:
        tokens = Lexer(source, lenient_indent=True).tokenize()
        tree = Parser(tokens).parse()
    except ArabiError as exc:
        return [(exc.line or 0, 'خطأ', exc.message)]
    return _Linter(tree, _builtin_names()).run()


# ================== مولد التوثيق ==================

def _docstring(body):
    """يستخرج توثيق الكتلة: أول جملة نصية داخلها."""
    if body and isinstance(body[0], N.ExprStmt) \
            and isinstance(body[0].expr, N.Str):
        return body[0].expr.value.strip()
    return None


def _render_literal(expr):
    """يعرض تعبيرًا حرفيًا بسيطًا كنص — للتوثيق فقط."""
    if isinstance(expr, N.Num):
        return str(expr.value)
    if isinstance(expr, N.Str):
        return f'"{expr.value}"'
    if isinstance(expr, N.Bool):
        return 'صح' if expr.value else 'خطأ'
    if isinstance(expr, N.Null):
        return 'ولا شيء'
    if isinstance(expr, N.UnaryOp) and expr.op == '-' \
            and isinstance(expr.operand, N.Num):
        return f'-{expr.operand.value}'
    return '…'


def _render_params(params, rest=None):
    """يعرض قائمة المعاملات للتوثيق، مع الافتراضيات والمعامل المتغير."""
    parts = []
    for name, default in params:
        if default is None:
            parts.append(name)
        else:
            parts.append(f'{name} = {_render_literal(default)}')
    if rest is not None:
        parts.append('...' + rest)
    return '، '.join(parts)


def _fn_tags(fn):
    """وسوم الدالة في التوثيق: مولد ومزخرفات."""
    tags = []
    if getattr(fn, 'is_generator', False):
        tags.append('مولد')
    for dec in getattr(fn, 'decorators', None) or []:
        tags.append(f'@{_decorator_name(dec)}')
    if not tags:
        return ''
    return ' — ' + '، '.join(f'`{t}`' for t in tags)


def _decorator_name(expr):
    """يستخرج اسم المزخرف من تعبيره (اسم أو استدعاء)."""
    if isinstance(expr, N.Name):
        return expr.name
    if isinstance(expr, N.Call):
        return _decorator_name(expr.func)
    if isinstance(expr, N.Attribute):
        return expr.name
    return 'مزخرف'


def _render_parents(superclass):
    """يعرض أصول الصنف للتوثيق — أصل واحد أو قائمة وراثة متعددة."""
    if superclass is None:
        return ''
    if isinstance(superclass, list):
        return ' (يرث ' + '، '.join(f'`{s}`' for s in superclass) + ')'
    return f' (يرث `{superclass}`)'


def generate_docs(filename, source):
    """يولد توثيق Markdown لملف لغة عربي ويعيده نصًا."""
    tokens = Lexer(source).tokenize()
    tree = Parser(tokens).parse()
    out = []
    title = os.path.basename(filename)
    out.append(f'# توثيق {title}')
    out.append('')

    module_doc = _docstring(tree.statements)
    if module_doc:
        out.append(module_doc)
        out.append('')

    imports = [s for s in tree.statements if isinstance(s, N.Import)]
    funcs = [s for s in tree.statements if isinstance(s, N.FuncDef)]
    classes = [s for s in tree.statements if isinstance(s, N.ClassDef)]
    interfaces = [s for s in tree.statements
                  if isinstance(s, N.InterfaceDef)]
    enums = [s for s in tree.statements if isinstance(s, N.EnumDef)]
    consts = [s for s in tree.statements
              if isinstance(s, N.Assign) and len(s.targets) == 1
              and isinstance(s.targets[0], N.Name)]
    documented_any = False

    if imports:
        documented_any = True
        out.append('## الاعتماديات')
        out.append('')
        for imp in imports:
            if imp.module:
                if imp.names:
                    out.append(f'- من `{imp.module}`: '
                               + '، '.join(f'`{n}`' for n in imp.names))
                else:
                    out.append(f'- `{imp.module}`')
            else:
                out.append(f'- المسار `{imp.path}`')
        out.append('')

    if funcs:
        documented_any = True
        out.append('## الدوال')
        out.append('')
        for fn in funcs:
            tags = _fn_tags(fn)
            out.append(f'### {fn.name}({_render_params(fn.params, fn.rest)}){tags}')
            out.append('')
            doc = _docstring(fn.body)
            if doc:
                out.append(doc)
                out.append('')
        out.append('')

    if classes:
        documented_any = True
        out.append('## الأصناف')
        out.append('')
        for cls in classes:
            parent = _render_parents(cls.superclass)
            out.append(f'### {cls.name}{parent}')
            out.append('')
            doc = _docstring(cls.body)
            if doc:
                out.append(doc)
                out.append('')
            methods = [m for m in cls.body if isinstance(m, N.FuncDef)]
            props = [m for m in cls.body if isinstance(m, N.PropertyDef)]
            constants = [m for m in cls.body if isinstance(m, N.Assign)
                         and len(m.targets) == 1
                         and isinstance(m.targets[0], N.Name)]
            if constants:
                out.append('**الثوابت:** ' + '، '.join(
                    f'`{c.targets[0].name}`' for c in constants))
                out.append('')
            if methods:
                out.append('**الطرق:**')
                out.append('')
                for m in methods:
                    tags = _fn_tags(m)
                    out.append(f'- `{m.name}({_render_params(m.params, m.rest)})`{tags}')
                    mdoc = _docstring(m.body)
                    if mdoc:
                        out.append(f'  - {mdoc}')
                out.append('')
            if props:
                out.append('**الخصائص المحسوبة:** ' + '، '.join(
                    f'`{p.name}`' for p in props))
                out.append('')

    if interfaces:
        documented_any = True
        out.append('## الواجهات')
        out.append('')
        for iface in interfaces:
            parent = _render_parents(iface.superclass)
            out.append(f'### واجهة {iface.name}{parent}')
            out.append('')
            doc = _docstring(iface.body)
            if doc:
                out.append(doc)
                out.append('')
            if iface.abstract:
                out.append('**الطرق المجردة:** ' + '، '.join(
                    f'`{name}()`' for name in iface.abstract))
                out.append('')
            defaults = [m for m in iface.body
                        if isinstance(m, N.FuncDef) and m.body is not None]
            constants = [m for m in iface.body if isinstance(m, N.Assign)
                         and len(m.targets) == 1
                         and isinstance(m.targets[0], N.Name)]
            if defaults:
                out.append('**التنفيذ الافتراضي:**')
                out.append('')
                for m in defaults:
                    tags = _fn_tags(m)
                    out.append(f'- `{m.name}({_render_params(m.params, m.rest)})`{tags}')
                out.append('')
            if constants:
                out.append('**الثوابت:** ' + '، '.join(
                    f'`{c.targets[0].name}`' for c in constants))
                out.append('')

    if enums:
        documented_any = True
        out.append('## التعدادات')
        out.append('')
        for enum in enums:
            out.append(f'### {enum.name}')
            out.append('')
            out.append('| العضو | القيمة |')
            out.append('|--------|--------|')
            for member in enum.members:
                name, value = member[0], member[1]
                v = 'تلقائي' if value is None else _render_literal(value)
                out.append(f'| `{name}` | {v} |')
            out.append('')

    if consts:
        documented_any = True
        out.append('## المتغيرات العامة')
        out.append('')
        for c in consts:
            out.append(f'- **{c.targets[0].name}** = '
                       f'{_render_literal(c.value)}')
        out.append('')

    if not documented_any and not module_doc:
        out.append('لا يوجد عناصر موثقة في هذا الملف.')
        out.append('')
    return '\n'.join(out)


# ================== مدير الحزم ==================

def install_package(source, libraries_dir='مكتبات'):
    """يثبت مكتبة .عربي من مسار محلي أو رابط HTTP إلى مجلد المكتبات.

    يتحقق من صلاحية الكود قبل التثبيت، ويعيد (اسم المكتبة، مسارها).
    """
    is_url = source.startswith(('http://', 'https://'))
    if is_url:
        with urllib.request.urlopen(_quote_url(source), timeout=30) as resp:
            content = resp.read().decode('utf-8')
        name = os.path.basename(urllib.parse.urlsplit(source).path)
    else:
        if not os.path.isfile(source):
            raise ArabiError(f"الملف '{source}' غير موجود")
        with open(source, encoding='utf-8') as f:
            content = f.read()
        name = os.path.basename(source)

    if not name.endswith('.عربي'):
        name += '.عربي'

    # لا تثبت كودًا غير سليم
    Parser(Lexer(content).tokenize()).parse()

    os.makedirs(libraries_dir, exist_ok=True)
    dest = os.path.join(libraries_dir, name)
    with open(dest, 'w', encoding='utf-8') as f:
        f.write(content)
    return name[:-len('.عربي')], dest


def list_packages(libraries_dir='مكتبات'):
    """يعيد أسماء المكتبات المثبتة (ملفات .عربي) مرتبة."""
    if not os.path.isdir(libraries_dir):
        return []
    return sorted(f for f in os.listdir(libraries_dir)
                  if f.endswith('.عربي')
                  and os.path.isfile(os.path.join(libraries_dir, f)))
